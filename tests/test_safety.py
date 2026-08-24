"""Safety contracts must be closed by default and impossible to widen."""

from __future__ import annotations

import unittest

from tests.support import TempDirCase

from syra_core.errors import SafetyDenied
from syra_core.safety import CAPABILITIES, SafetyContract


class TestDefaults(unittest.TestCase):
    def test_everything_but_read_is_denied_by_default(self) -> None:
        contract = SafetyContract(purpose="TEST")
        for capability in CAPABILITIES:
            if capability == "filesystem_read":
                continue
            self.assertFalse(
                contract.allows(capability),
                msg="{} should be denied by default".format(capability),
            )

    def test_sealed_denies_everything(self) -> None:
        contract = SafetyContract.sealed()
        self.assertEqual(contract.granted(), ())

    def test_static_analysis_grants_read_and_evidence_only(self) -> None:
        contract = SafetyContract.static_analysis()
        self.assertTrue(contract.allows("git_read"))
        self.assertTrue(contract.allows("filesystem_write"))
        # The whole point: a discovery gate cannot mutate what it inspects.
        self.assertFalse(contract.allows("source_mutation"))
        self.assertFalse(contract.allows("git_mutation"))
        self.assertFalse(contract.allows("network"))
        self.assertFalse(contract.allows("deploy"))


class TestRequire(unittest.TestCase):
    def test_require_passes_when_granted(self) -> None:
        SafetyContract.static_analysis().require("git_read", "filesystem_read")

    def test_require_raises_with_actionable_detail(self) -> None:
        contract = SafetyContract.static_analysis()
        with self.assertRaises(SafetyDenied) as caught:
            contract.require("network", "deploy", site="test.site")

        error = caught.exception
        self.assertEqual(error.code, "SYRA-E-SAFETY-DENIED")
        self.assertEqual(error.detail["missing"], ["network", "deploy"])
        self.assertEqual(error.detail["site"], "test.site")
        self.assertIn("network", error.remediation or "")

    def test_unknown_capability_is_refused(self) -> None:
        with self.assertRaises(SafetyDenied):
            SafetyContract().allows("teleportation")


class TestNarrowing(unittest.TestCase):
    def test_narrow_can_remove(self) -> None:
        parent = SafetyContract.static_analysis()
        child = parent.narrow(filesystem_write=False, purpose="CHILD")
        self.assertTrue(child.allows("git_read"))
        self.assertFalse(child.allows("filesystem_write"))
        self.assertEqual(child.purpose, "CHILD")

    def test_narrow_cannot_escalate(self) -> None:
        parent = SafetyContract.static_analysis()
        with self.assertRaises(SafetyDenied) as caught:
            parent.narrow(network=True)
        self.assertEqual(caught.exception.detail["attempted_escalation"], ["network"])

    def test_narrow_leaves_parent_untouched(self) -> None:
        parent = SafetyContract.static_analysis()
        parent.narrow(git_read=False)
        self.assertTrue(parent.allows("git_read"))

    def test_contract_is_immutable(self) -> None:
        contract = SafetyContract.static_analysis()
        with self.assertRaises(Exception):
            contract.network = True  # type: ignore[misc]


class TestSerialisation(unittest.TestCase):
    def test_round_trip(self) -> None:
        original = SafetyContract.product_runtime("RUNTIME", network=True)
        restored = SafetyContract.from_mapping(original.as_dict())
        self.assertEqual(original, restored)

    def test_from_mapping_rejects_unknown_keys(self) -> None:
        with self.assertRaises(SafetyDenied):
            SafetyContract.from_mapping({"purpose": "X", "root_access": True})

    def test_banner_reports_zero_for_denied(self) -> None:
        banner = SafetyContract.static_analysis("SCAN").render()
        self.assertIn("SOURCE_MUTATION=ZERO", banner)
        self.assertIn("DEPLOY=ZERO", banner)
        self.assertIn("PURPOSE=SCAN", banner)


if __name__ == "__main__":
    unittest.main()
