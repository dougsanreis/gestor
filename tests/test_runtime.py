"""ProductRuntime boot, manifest validation, and the control plane."""

from __future__ import annotations

import unittest

from tests.support import TempDirCase

from syra_core import manifest as manifest_mod
from syra_core import util
from syra_core.connector import service_connector
from syra_core.errors import ManifestInvalid, ProductExists, ProductUnknown
from syra_core.manifest import MANIFEST_FILENAME, ProductManifest
from syra_core.registry import ProductRegistry
from syra_core.runtime import ProductRuntime
from syra_core.safety import SafetyContract


class TestManifest(TempDirCase):
    def test_valid_manifest_builds(self) -> None:
        built = manifest_mod.build(
            product_id="painel-vendas", name="Painel", kind="platform"
        )
        self.assertEqual(built.product_id, "painel-vendas")
        self.assertEqual(built.kind, "platform")

    def assert_violation(self, code: str, pointer: str, **kwargs) -> None:
        """Assert the manifest was refused for the specific stated reason.

        Asserting only that *something* raised lets a test pass for an unrelated
        defect -- which is how a suite keeps reporting green while the rule it
        claims to cover has stopped working.
        """
        payload = {"product_id": "valido", "name": "x", "kind": "tool"}
        payload.update(kwargs)
        with self.assertRaises(ManifestInvalid) as caught:
            manifest_mod.build(**payload)

        violations = caught.exception.detail["violations"]
        matched = [
            item
            for item in violations
            if item["code"] == code and item["pointer"] == pointer
        ]
        self.assertTrue(
            matched,
            msg="expected {} at {}, got {}".format(code, pointer, violations),
        )

    def test_invalid_slug_is_refused(self) -> None:
        self.assert_violation(
            "FORMAT_MISMATCH", "$.productId", product_id="Painel Vendas!"
        )

    def test_too_short_id_is_refused(self) -> None:
        self.assert_violation("MIN_LENGTH", "$.productId", product_id="p")

    def test_unknown_kind_is_refused(self) -> None:
        self.assert_violation("ENUM_MISMATCH", "$.kind", kind="spaceship")

    def test_bad_semver_is_refused(self) -> None:
        self.assert_violation("FORMAT_MISMATCH", "$.version", version="one")

    def test_unknown_capability_is_refused(self) -> None:
        self.assert_violation(
            "ENUM_MISMATCH",
            "$.capabilities[0].id",
            capabilities=[{"id": "TELEPORTATION", "mode": "BUILD"}],
        )

    def test_unknown_capability_mode_is_refused(self) -> None:
        self.assert_violation(
            "ENUM_MISMATCH",
            "$.capabilities[0].mode",
            capabilities=[{"id": "WATCHDOG", "mode": "YOLO"}],
        )

    def test_round_trip_through_disk(self) -> None:
        built = manifest_mod.build(product_id="prod", name="x", kind="tool")
        path = built.save(self.path("prod"))
        loaded = ProductManifest.load(path)
        self.assertEqual(loaded.fingerprint, built.fingerprint)

    def test_missing_manifest_gives_actionable_error(self) -> None:
        with self.assertRaises(ManifestInvalid) as caught:
            ProductManifest.load(self.path("nowhere"))
        self.assertIn("syra product new", caught.exception.remediation or "")


class TestRuntimeBoot(TempDirCase):
    def test_bootstrap_without_a_manifest_on_disk(self) -> None:
        with ProductRuntime.bootstrap(
            product_id="scratch", name="Scratch", state_dir=self.path("state")
        ) as runtime:
            self.assertEqual(runtime.manifest.product_id, "scratch")
            self.assertTrue(runtime.safety.allows("runtime_execution"))
            self.assertFalse(runtime.safety.allows("network"))

    def test_from_manifest_boots_and_loads_contracts(self) -> None:
        root = self.path("prod")
        root.mkdir(parents=True)
        util.write_json(
            root / "contracts" / "c.json",
            {
                "schemaVersion": 1,
                "contracts": [
                    {
                        "name": "echo.request",
                        "version": "1.0.0",
                        "schema": {"type": "object"},
                    }
                ],
            },
        )
        built = manifest_mod.build(
            product_id="prod",
            name="Prod",
            kind="tool",
            contracts=[
                {"name": "echo.request", "version": "1.0.0", "file": "contracts/c.json"}
            ],
        )
        built.save(root)

        with ProductRuntime.from_manifest(
            root / MANIFEST_FILENAME, state_dir=self.path("state")
        ) as runtime:
            self.assertTrue(runtime.contracts.has("echo.request"))

    def test_missing_contract_file_fails_boot(self) -> None:
        root = self.path("prod")
        root.mkdir(parents=True)
        built = manifest_mod.build(
            product_id="prod",
            name="Prod",
            kind="tool",
            contracts=[{"name": "a", "version": "1.0.0", "file": "contracts/gone.json"}],
        )
        built.save(root)

        with self.assertRaises(ManifestInvalid) as caught:
            ProductRuntime.from_manifest(
                root / MANIFEST_FILENAME, state_dir=self.path("state")
            )
        self.assertIn("may not claim a boundary", caught.exception.remediation or "")

    def test_runtime_cannot_escalate_beyond_the_manifest(self) -> None:
        root = self.path("prod")
        root.mkdir(parents=True)
        built = manifest_mod.build(
            product_id="prod",
            name="Prod",
            kind="tool",
            safety=SafetyContract.product_runtime("P", network=False).as_dict(),
        )
        built.save(root)

        from syra_core.errors import PreflightFailed

        with self.assertRaises(PreflightFailed):
            ProductRuntime.from_manifest(
                root / MANIFEST_FILENAME,
                safety=SafetyContract.product_runtime("P", network=True),
                state_dir=self.path("state"),
            )

    def test_readiness_and_diagnostics(self) -> None:
        with ProductRuntime.bootstrap(
            product_id="scratch", name="Scratch", state_dir=self.path("state")
        ) as runtime:
            runtime.register(service_connector("svc", lambda p: {"ok": True}))

            readiness = runtime.readiness()
            self.assertEqual(readiness["product"], "scratch")
            self.assertTrue(readiness["ready"])
            self.assertEqual(readiness["connectors"], 1)

            diagnostics = runtime.diagnostics()
            self.assertIn("safety", diagnostics)
            self.assertIn("breakers", diagnostics)
            self.assertEqual(len(diagnostics["connectors"]), 1)

    def test_capability_report_covers_all_nineteen(self) -> None:
        from syra_core.capabilities import CAPABILITY_COUNT

        with ProductRuntime.bootstrap(
            product_id="scratch", name="Scratch", state_dir=self.path("state")
        ) as runtime:
            rows = runtime.capability_report()
            self.assertEqual(len(rows), CAPABILITY_COUNT)
            modes = {row["mode"] for row in rows}
            self.assertIn("CORE_PROVIDED", modes)


class TestControlPlane(TempDirCase):
    def make_product(self, product_id: str) -> ProductManifest:
        root = self.path(product_id)
        root.mkdir(parents=True)
        built = manifest_mod.build(product_id=product_id, name=product_id, kind="tool")
        built.save(root)
        return built

    def test_register_and_lookup(self) -> None:
        registry = ProductRegistry(self.path("registry.json"))
        built = self.make_product("alpha")
        entry = registry.register(built)

        self.assertEqual(entry.product_id, "alpha")
        self.assertEqual(registry.get("alpha").kind, "tool")
        self.assertTrue(registry.has("alpha"))

    def test_duplicate_registration_is_refused(self) -> None:
        registry = ProductRegistry(self.path("registry.json"))
        built = self.make_product("alpha")
        registry.register(built)
        with self.assertRaises(ProductExists):
            registry.register(built)

    def test_replace_updates_in_place(self) -> None:
        registry = ProductRegistry(self.path("registry.json"))
        built = self.make_product("alpha")
        first = registry.register(built)
        second = registry.register(built, replace=True)
        self.assertEqual(first.registered_at, second.registered_at)
        self.assertEqual(len(registry), 1)

    def test_unknown_product_raises(self) -> None:
        registry = ProductRegistry(self.path("registry.json"))
        with self.assertRaises(ProductUnknown):
            registry.get("ghost")

    def test_survives_restart(self) -> None:
        registry = ProductRegistry(self.path("registry.json"))
        registry.register(self.make_product("alpha"))

        reloaded = ProductRegistry(self.path("registry.json"))
        self.assertTrue(reloaded.has("alpha"))

    def test_drift_is_detected(self) -> None:
        registry = ProductRegistry(self.path("registry.json"))
        built = self.make_product("alpha")
        registry.register(built)
        self.assertEqual(registry.drift_report(), [])

        # Someone edits the manifest without re-registering.
        changed = manifest_mod.build(
            product_id="alpha", name="alpha", kind="tool", version="0.2.0"
        )
        changed.save(self.path("alpha"))

        drift = registry.drift_report()
        self.assertEqual(len(drift), 1)
        self.assertEqual(drift[0]["reason"], "FINGERPRINT_MISMATCH")

    def test_missing_manifest_is_drift(self) -> None:
        registry = ProductRegistry(self.path("registry.json"))
        registry.register(self.make_product("alpha"))
        (self.path("alpha") / MANIFEST_FILENAME).unlink()
        self.assertEqual(registry.drift_report()[0]["reason"], "MANIFEST_MISSING")


if __name__ == "__main__":
    unittest.main()
