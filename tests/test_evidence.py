"""Evidence runs: atomic, hashed, and refusing to certify what they did not write."""

from __future__ import annotations

import unittest

from tests.support import TempDirCase

from syra_core import util
from syra_core.errors import EvidenceError, SafetyDenied
from syra_core.evidence import EvidenceRun, load_manifest
from syra_core.safety import SafetyContract


class TestEvidenceRun(TempDirCase):
    def make_run(self, **kwargs) -> EvidenceRun:
        return EvidenceRun(
            work_id="TEST-001",
            gate="TEST-GATE",
            safety=SafetyContract.static_analysis(),
            root=self.path("evidence"),
            **kwargs,
        )

    def test_requires_write_capability(self) -> None:
        with self.assertRaises(SafetyDenied):
            EvidenceRun(
                work_id="TEST-001",
                gate="TEST-GATE",
                safety=SafetyContract.sealed(),
                root=self.path("evidence"),
            )

    def test_directory_name_follows_convention(self) -> None:
        run = self.make_run()
        self.assertIn("TEST-001", run.dir.name)
        self.assertIn("TEST-GATE", run.dir.name)
        self.assertTrue(run.dir.name.endswith("-V1"))

    def test_artifacts_are_hashed_at_write_time(self) -> None:
        run = self.make_run()
        ref = run.write_text("note.txt", "hello\n")
        self.assertEqual(ref.sha256, util.sha256_text("hello\n"))
        self.assertEqual(ref.bytes, 6)

    def test_tsv_escapes_embedded_control_characters(self) -> None:
        run = self.make_run()
        run.write_tsv(
            "rows.tsv", ["a", "b"], [{"a": "x\ty", "b": "line1\nline2"}]
        )
        content = (run.dir / "rows.tsv").read_text()
        self.assertEqual(len(content.strip().splitlines()), 2)
        self.assertIn("\\t", content)
        self.assertIn("\\n", content)

    def test_rewriting_an_artifact_replaces_its_record(self) -> None:
        run = self.make_run()
        run.write_text("a.txt", "one")
        run.write_text("a.txt", "two")
        self.assertEqual(len(run.artifacts), 1)
        manifest = run.seal(decision="PASS", next_state="NEXT", required=["a.txt"])
        self.assertEqual(len(manifest["artifacts"]), 1)

    def test_seal_refuses_missing_declared_artifact(self) -> None:
        run = self.make_run()
        run.write_text("present.txt", "x")
        with self.assertRaises(EvidenceError) as caught:
            run.seal(
                decision="PASS",
                next_state="NEXT",
                required=["present.txt", "absent.tsv"],
            )
        self.assertEqual(caught.exception.detail["missing"], ["absent.tsv"])

    def test_seal_refuses_empty_declared_artifact(self) -> None:
        run = self.make_run()
        run.write_text("empty.tsv", "")
        with self.assertRaises(EvidenceError) as caught:
            run.seal(decision="PASS", next_state="NEXT", required=["empty.tsv"])
        self.assertEqual(caught.exception.detail["empty"], ["empty.tsv"])

    def test_sealed_run_rejects_further_writes(self) -> None:
        run = self.make_run()
        run.write_text("a.txt", "x")
        run.seal(decision="PASS", next_state="NEXT", required=["a.txt"])
        with self.assertRaises(EvidenceError):
            run.write_text("b.txt", "y")

    def test_manifest_records_invariants(self) -> None:
        run = self.make_run()
        run.write_text("a.txt", "x")
        manifest = run.seal(decision="PASS", next_state="NEXT", required=["a.txt"])
        self.assertFalse(manifest["invariants"]["source_mutation"])
        self.assertFalse(manifest["invariants"]["deploy"])
        self.assertTrue(manifest["invariants"]["git_read"])
        self.assertIn("manifestSha256", manifest)


class TestLoadManifest(TempDirCase):
    def seal_one(self) -> EvidenceRun:
        run = EvidenceRun(
            work_id="TEST-001",
            gate="TEST-GATE",
            safety=SafetyContract.static_analysis(),
            root=self.path("evidence"),
        )
        run.write_text("a.txt", "original")
        run.seal(decision="PASS", next_state="NEXT", required=["a.txt"])
        return run

    def test_round_trip(self) -> None:
        run = self.seal_one()
        manifest = load_manifest(run.dir)
        self.assertEqual(manifest["decision"], "PASS")
        self.assertEqual(manifest["gate"], "TEST-GATE")

    def test_detects_post_seal_tampering(self) -> None:
        run = self.seal_one()
        (run.dir / "a.txt").write_text("tampered")

        with self.assertRaises(EvidenceError) as caught:
            load_manifest(run.dir)
        self.assertEqual(
            caught.exception.detail["drifted"][0]["reason"], "SHA256_MISMATCH"
        )

    def test_detects_deleted_artifact(self) -> None:
        run = self.seal_one()
        (run.dir / "a.txt").unlink()
        with self.assertRaises(EvidenceError) as caught:
            load_manifest(run.dir)
        self.assertEqual(caught.exception.detail["drifted"][0]["reason"], "MISSING")

    def test_unsealed_directory_is_refused(self) -> None:
        directory = self.path("evidence", "unsealed")
        directory.mkdir(parents=True)
        (directory / "a.txt").write_text("x")
        with self.assertRaises(EvidenceError) as caught:
            load_manifest(directory)
        self.assertIn("did not complete", caught.exception.remediation or "")


class TestAtomicWrite(TempDirCase):
    def test_write_is_all_or_nothing(self) -> None:
        target = self.path("out", "file.txt")
        util.atomic_write_text(target, "content")
        self.assertEqual(target.read_text(), "content")
        # No temp files left behind.
        leftovers = [p for p in target.parent.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_overwrite_replaces_completely(self) -> None:
        target = self.path("file.txt")
        util.atomic_write_text(target, "a much longer original value")
        util.atomic_write_text(target, "short")
        self.assertEqual(target.read_text(), "short")


if __name__ == "__main__":
    unittest.main()
