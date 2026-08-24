"""Failure memory: the same defect must not be rediscovered at full price."""

from __future__ import annotations

import unittest

from tests.support import TempDirCase

from syra_core.errors import ConnectorFailure, RepeatedFailure, SyraError
from syra_core.failure_memory import (
    ACCEPTED,
    OPEN,
    RESOLVED,
    FailureMemory,
    normalise,
)


class TestNormalisation(unittest.TestCase):
    def test_incidental_values_are_stripped(self) -> None:
        a = normalise("connection refused to 10.0.0.5:8080")
        b = normalise("connection refused to 192.168.1.9:9090")
        self.assertEqual(a, b)

    def test_paths_collapse(self) -> None:
        a = normalise("cannot open /home/alice/projects/app/main.py")
        b = normalise("cannot open /home/bob/work/other/thing.py")
        self.assertEqual(a, b)

    def test_uuids_collapse(self) -> None:
        a = normalise("job 3f2b1c4d-5e6f-4a8b-9c0d-1e2f3a4b5c6d failed")
        b = normalise("job aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee failed")
        self.assertEqual(a, b)

    def test_genuinely_different_failures_stay_different(self) -> None:
        self.assertNotEqual(
            normalise("connection refused"), normalise("permission denied")
        )


class TestRecording(TempDirCase):
    def setUp(self) -> None:
        super().setUp()
        self.memory = FailureMemory(self.path("failures.json"))

    def test_first_occurrence_creates_an_open_record(self) -> None:
        record = self.memory.record(
            ConnectorFailure("timeout talking to 10.0.0.1"), site="gateway.api"
        )
        self.assertEqual(record.status, OPEN)
        self.assertEqual(record.count, 1)
        self.assertEqual(record.code, "SYRA-E-CONNECTOR-FAILURE")
        self.assertEqual(record.site, "gateway.api")

    def test_equivalent_failures_deduplicate(self) -> None:
        self.memory.record(ConnectorFailure("timeout talking to 10.0.0.1"), site="g")
        self.memory.record(ConnectorFailure("timeout talking to 10.0.0.9"), site="g")
        records = self.memory.all()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].count, 2)

    def test_different_sites_are_different_defects(self) -> None:
        self.memory.record(ConnectorFailure("timeout"), site="a")
        self.memory.record(ConnectorFailure("timeout"), site="b")
        self.assertEqual(len(self.memory.all()), 2)

    def test_samples_are_bounded(self) -> None:
        for index in range(20):
            self.memory.record(
                ConnectorFailure("timeout number {}".format(index)), site="g"
            )
        record = self.memory.all()[0]
        self.assertLessEqual(len(record.samples), FailureMemory.MAX_SAMPLES)
        self.assertEqual(record.count, 20)

    def test_unclassified_exceptions_still_get_a_code(self) -> None:
        record = self.memory.record(ValueError("odd"), site="g")
        self.assertTrue(record.code.startswith("SYRA-E-UNCLASSIFIED"))

    def test_survives_a_restart(self) -> None:
        self.memory.record(ConnectorFailure("timeout"), site="g")
        reloaded = FailureMemory(self.path("failures.json"))
        self.assertEqual(len(reloaded.all()), 1)

    def test_corrupt_store_does_not_block_boot(self) -> None:
        self.path("broken.json").write_text("{ not json")
        memory = FailureMemory(self.path("broken.json"))
        self.assertEqual(memory.all(), [])


class TestLifecycle(TempDirCase):
    def setUp(self) -> None:
        super().setUp()
        self.memory = FailureMemory(self.path("failures.json"))
        self.record = self.memory.record(
            ConnectorFailure("timeout"), site="gateway.api"
        )

    def test_resolve_marks_fixed(self) -> None:
        updated = self.memory.resolve(self.record.fingerprint, "raised the timeout")
        self.assertEqual(updated.status, RESOLVED)
        self.assertEqual(updated.resolution, "raised the timeout")
        self.assertEqual(self.memory.open_failures(), [])

    def test_resolve_by_prefix(self) -> None:
        updated = self.memory.resolve(self.record.fingerprint[:10], "fixed")
        self.assertEqual(updated.status, RESOLVED)

    def test_unknown_fingerprint_raises(self) -> None:
        with self.assertRaises(SyraError):
            self.memory.resolve("ffffffffff", "nope")

    def test_accept_marks_tolerated(self) -> None:
        updated = self.memory.accept(self.record.fingerprint, "known upstream bug")
        self.assertEqual(updated.status, ACCEPTED)

    def test_regression_reopens_and_keeps_history(self) -> None:
        self.memory.resolve(self.record.fingerprint, "raised the timeout")
        again = self.memory.record(ConnectorFailure("timeout"), site="gateway.api")
        self.assertEqual(again.status, OPEN)
        self.assertIn("REGRESSED", again.resolution)
        self.assertIn("raised the timeout", again.resolution)


class TestGuard(TempDirCase):
    def test_advisory_mode_returns_the_record(self) -> None:
        memory = FailureMemory(self.path("f.json"), block_repeats=False)
        memory.record(ConnectorFailure("timeout"), site="gateway.api")
        known = memory.guard("gateway.api")
        self.assertIsNotNone(known)
        self.assertEqual(known.count, 1)

    def test_blocking_mode_refuses_the_repeat(self) -> None:
        memory = FailureMemory(self.path("f.json"), block_repeats=True)
        memory.record(ConnectorFailure("timeout"), site="gateway.api")

        with self.assertRaises(RepeatedFailure) as caught:
            memory.guard("gateway.api")

        error = caught.exception
        self.assertEqual(error.detail["site"], "gateway.api")
        self.assertIn("syra failures resolve", error.remediation or "")

    def test_resolved_defects_stop_blocking(self) -> None:
        memory = FailureMemory(self.path("f.json"), block_repeats=True)
        record = memory.record(ConnectorFailure("timeout"), site="gateway.api")
        memory.resolve(record.fingerprint, "fixed")
        self.assertIsNone(memory.guard("gateway.api"))

    def test_clean_site_is_never_blocked(self) -> None:
        memory = FailureMemory(self.path("f.json"), block_repeats=True)
        self.assertIsNone(memory.guard("gateway.other"))


if __name__ == "__main__":
    unittest.main()
