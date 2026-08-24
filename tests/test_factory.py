"""The factory must produce products that work on the first run."""

from __future__ import annotations

import unittest

from tests.support import TempDirCase

from syra_core import factory as factory_mod
from syra_core.blueprints import KIND_PROFILES
from syra_core.errors import ProductExists, SyraError
from syra_core.manifest import MANIFEST_FILENAME, ProductManifest


class TestPlanning(TempDirCase):
    def test_dry_run_writes_nothing(self) -> None:
        destination = self.path("products", "painel")
        result = factory_mod.create(
            destination, product_id="painel", kind="tool", dry_run=True
        )
        self.assertTrue(result.dry_run)
        self.assertGreater(len(result.files), 5)
        self.assertFalse(destination.exists())

    def test_plan_matches_what_create_writes(self) -> None:
        """A rehearsal that differs from the real thing is not a rehearsal."""
        planned, _ = factory_mod.plan(product_id="painel", kind="tool")
        result = factory_mod.create(
            self.path("p"), product_id="painel", kind="tool", verify=False
        )
        self.assertEqual(
            sorted(item.relative for item in planned),
            sorted(item.relative for item in result.files),
        )

    def test_invalid_slug_is_refused_with_guidance(self) -> None:
        with self.assertRaises(SyraError) as caught:
            factory_mod.plan(product_id="Painel Vendas", kind="tool")
        self.assertIn("painel-vendas", caught.exception.remediation or "")

    def test_unknown_kind_lists_the_valid_ones(self) -> None:
        with self.assertRaises(SyraError) as caught:
            factory_mod.plan(product_id="p", kind="spaceship")
        self.assertIn("agent_squad", caught.exception.remediation or "")


class TestGeneration(TempDirCase):
    def test_generated_product_passes_its_own_verification(self) -> None:
        result = factory_mod.create(
            self.path("painel"), product_id="painel", kind="tool"
        )
        self.assertTrue(result.verified, msg=result.verification)
        self.assertTrue(result.verification["ok"])
        self.assertEqual(result.verification["checks"]["tests"]["status"], "PASS")

    def test_manifest_is_valid_and_loadable(self) -> None:
        result = factory_mod.create(
            self.path("painel"), product_id="painel", kind="platform"
        )
        manifest = ProductManifest.load(result.root)
        self.assertEqual(manifest.product_id, "painel")
        self.assertEqual(manifest.kind, "platform")
        self.assertTrue(manifest.connectors())
        self.assertTrue(manifest.contracts())

    def test_refuses_to_overwrite_existing_work(self) -> None:
        destination = self.path("painel")
        destination.mkdir(parents=True)
        (destination / "important.txt").write_text("do not lose me")

        with self.assertRaises(ProductExists):
            factory_mod.create(destination, product_id="painel", kind="tool")

        self.assertEqual((destination / "important.txt").read_text(), "do not lose me")

    def test_core_provided_capabilities_are_declared_not_rebuilt(self) -> None:
        result = factory_mod.create(
            self.path("painel"), product_id="painel", kind="tool"
        )
        manifest = ProductManifest.load(result.root)
        self.assertEqual(manifest.capability_mode("CONTRACT_REGISTRY"), "CORE_PROVIDED")
        self.assertEqual(manifest.capability_mode("CIRCUIT_BREAKER"), "CORE_PROVIDED")

    def test_network_authority_matches_the_product_kind(self) -> None:
        agent = factory_mod.create(
            self.path("a"), product_id="agente", kind="agent", verify=False
        )
        platform = factory_mod.create(
            self.path("b"), product_id="plataforma", kind="platform", verify=False
        )

        self.assertFalse(
            ProductManifest.load(agent.root).safety_mapping()["network"]
        )
        self.assertTrue(
            ProductManifest.load(platform.root).safety_mapping()["network"]
        )

    def test_custom_connectors(self) -> None:
        result = factory_mod.create(
            self.path("squad"),
            product_id="squad",
            kind="agent_squad",
            connectors=["scout", "builder"],
        )
        manifest = ProductManifest.load(result.root)
        names = {item["name"] for item in manifest.connectors()}
        self.assertEqual(names, {"scout", "builder"})


class TestEveryKind(TempDirCase):
    """Each product kind must generate something that actually boots."""

    def test_all_kinds_generate_and_verify(self) -> None:
        for kind in sorted(KIND_PROFILES):
            with self.subTest(kind=kind):
                product_id = "prod-{}".format(kind.replace("_", "-"))
                result = factory_mod.create(
                    self.path(kind),
                    product_id=product_id,
                    kind=kind,
                )
                self.assertTrue(
                    result.verified,
                    msg="{} failed: {}".format(kind, result.verification),
                )


class TestVerification(TempDirCase):
    def test_broken_product_fails_verification(self) -> None:
        result = factory_mod.create(
            self.path("painel"), product_id="painel", kind="tool", verify=False
        )
        (result.root / "app" / "connectors.py").write_text("def broken(:\n")

        report = factory_mod.verify_product(result.root)
        self.assertFalse(report["ok"])

    def test_missing_manifest_fails_verification(self) -> None:
        result = factory_mod.create(
            self.path("painel"), product_id="painel", kind="tool", verify=False
        )
        (result.root / MANIFEST_FILENAME).unlink()

        report = factory_mod.verify_product(result.root)
        self.assertFalse(report["ok"])


if __name__ == "__main__":
    unittest.main()
