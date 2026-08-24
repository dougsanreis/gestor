"""The CLI is the operator surface. Its exit codes are a contract."""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from tests.support import TempDirCase

from syra_core.cli import EXIT_FAIL, EXIT_OK, main


def run(*argv: str):
    """Invoke the CLI, returning (exit_code, stdout)."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(list(argv))
    return code, buffer.getvalue()


def run_json(*argv: str):
    code, output = run("--json", *argv)
    return code, json.loads(output)


class TestBasics(TempDirCase):
    def test_version(self) -> None:
        code, payload = run_json("version")
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(payload["core"], "syra-core")
        self.assertEqual(
            payload["dependencies"], [], "the core must stay dependency-free"
        )

    def test_no_command_prints_help(self) -> None:
        code, output = run()
        self.assertEqual(code, 2)
        self.assertIn("usage", output.lower())

    def test_capabilities_lists_all_nineteen(self) -> None:
        from syra_core.capabilities import CAPABILITY_COUNT

        code, payload = run_json("capabilities")
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(payload["count"], CAPABILITY_COUNT)

    def test_preflight_self_check_passes(self) -> None:
        code, payload = run_json("preflight")
        self.assertEqual(code, EXIT_OK, msg=payload)
        self.assertEqual(payload["decision"], "PASS")

    def test_preflight_fails_on_broken_source(self) -> None:
        broken = self.path("broken.py")
        broken.write_text("def f(:\n")
        code, payload = run_json("preflight", str(broken))
        self.assertEqual(code, EXIT_FAIL)
        self.assertEqual(payload["decision"], "FAIL")


class TestGateCommands(TempDirCase):
    def setUp(self) -> None:
        super().setUp()
        import os
        import subprocess

        self.workspace = self.path("workspace")
        (self.workspace / "app" / "src").mkdir(parents=True)
        (self.workspace / "app" / "src" / "breaker.py").write_text(
            "class CircuitBreaker:\n    pass\n"
        )

        env = dict(os.environ)
        env.update(
            {
                "GIT_AUTHOR_NAME": "T",
                "GIT_AUTHOR_EMAIL": "t@e.com",
                "GIT_COMMITTER_NAME": "T",
                "GIT_COMMITTER_EMAIL": "t@e.com",
            }
        )
        repo = self.workspace / "app"
        for args in (
            ["init", "-q", "-b", "main"],
            ["add", "-A"],
            ["commit", "-q", "-m", "init"],
        ):
            subprocess.run(
                ["git", "-C", str(repo), *args], check=True, capture_output=True, env=env
            )

    def test_authority(self) -> None:
        code, payload = run_json("authority", "--root", str(self.workspace))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(payload["selected"], 1)

    def test_authority_on_missing_workspace_fails_cleanly(self) -> None:
        code, payload = run_json("authority", "--root", str(self.path("nowhere")))
        self.assertEqual(code, EXIT_FAIL)
        self.assertEqual(payload["decision"], "FAIL")
        self.assertIn("SYRA_WORKSPACE", payload["remediation"])

    def test_scan_reports_without_certifying(self) -> None:
        code, payload = run_json(
            "scan", "--root", str(self.workspace), "--no-evidence"
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(payload["decision"], "PASS")
        self.assertTrue(payload["summaries"])

    def test_scan_human_output_states_the_discipline(self) -> None:
        code, output = run("scan", "--root", str(self.workspace), "--no-evidence")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("FOUND_DOES_NOT_MEAN_CERTIFIED=YES", output)
        self.assertIn("IMPLEMENTATION_AUTHORIZED=NO", output)
        self.assertIn("SOURCE_MUTATION=ZERO", output)

    def test_decide_produces_a_full_table(self) -> None:
        from syra_core.capabilities import CAPABILITY_COUNT

        code, payload = run_json(
            "decide", "--root", str(self.workspace), "--no-evidence"
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(len(payload["decisions"]), CAPABILITY_COUNT)
        self.assertEqual(sum(payload["counts"].values()), CAPABILITY_COUNT)

    def test_scan_writes_verifiable_evidence(self) -> None:
        code, payload = run_json("scan", "--root", str(self.workspace))
        self.assertEqual(code, EXIT_OK)
        self.assertIsNotNone(payload["evidenceDir"])

        code, manifest = run_json("evidence", payload["evidenceDir"])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(manifest["decision"], "PASS")


class TestProductCommands(TempDirCase):
    def test_new_dry_run_then_real(self) -> None:
        destination = self.path("painel")

        code, payload = run_json(
            "product", "new", "painel", "--kind", "tool", "--into",
            str(destination), "--dry-run",
        )
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(payload["dryRun"])
        self.assertFalse(destination.exists())

        code, payload = run_json(
            "product", "new", "painel", "--kind", "tool", "--into", str(destination)
        )
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(payload["verified"])
        self.assertTrue((destination / "product.manifest.json").is_file())

    def test_validate_a_generated_product(self) -> None:
        destination = self.path("painel")
        run_json("product", "new", "painel", "--into", str(destination))

        code, payload = run_json("product", "validate", str(destination))
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(payload["ok"])

    def test_register_and_list(self) -> None:
        destination = self.path("painel")
        run_json(
            "product", "new", "painel", "--into", str(destination), "--register"
        )

        code, payload = run_json("product", "list")
        self.assertEqual(code, EXIT_OK)
        ids = {item["productId"] for item in payload["products"]}
        self.assertIn("painel", ids)

    def test_readiness_of_a_generated_product(self) -> None:
        destination = self.path("painel")
        run_json("product", "new", "painel", "--into", str(destination))

        code, payload = run_json("product", "readiness", str(destination))
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["product"], "painel")


class TestFailureCommands(TempDirCase):
    def test_list_and_resolve(self) -> None:
        from syra_core.errors import ConnectorFailure
        from syra_core.failure_memory import FailureMemory

        store = self.path("failures.json")
        memory = FailureMemory(store)
        record = memory.record(ConnectorFailure("timeout"), site="gateway.api")

        code, payload = run_json("failures", "list", "--store", str(store))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(payload["stats"]["open"], 1)

        code, payload = run_json(
            "failures", "resolve", record.fingerprint[:12], "raised the timeout",
            "--store", str(store),
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(payload["status"], "RESOLVED")

        code, payload = run_json("failures", "list", "--store", str(store))
        self.assertEqual(payload["stats"]["open"], 0)

    def test_resolving_an_unknown_fingerprint_fails_cleanly(self) -> None:
        code, payload = run_json(
            "failures", "resolve", "deadbeef", "note",
            "--store", str(self.path("f.json")),
        )
        self.assertEqual(code, EXIT_FAIL)
        self.assertIn("syra failures list", payload["remediation"])


if __name__ == "__main__":
    unittest.main()
