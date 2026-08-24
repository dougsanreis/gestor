"""SYRA-RULE-PPC-001: tooling is untrusted until it validates.

The first test is the incident that created the rule.
"""

from __future__ import annotations

import unittest

from tests.support import TempDirCase

from syra_core.contracts import Contract
from syra_core.errors import PreflightFailed
from syra_core.preflight import FAIL, PASS, Preflight, self_check
from syra_core.safety import SafetyContract


class TestPythonSyntax(TempDirCase):
    def test_catches_the_unterminated_string_that_started_all_this(self) -> None:
        source = 'status = run(repo, "status", "--porcelain=v1", "-uall)\n'
        report = Preflight(gate="t").python_source(source, "pasted").report()
        self.assertFalse(report.ok)
        self.assertEqual(report.failures[0].status, FAIL)
        self.assertIn("unterminated", report.failures[0].detail.lower())

    def test_accepts_the_corrected_line(self) -> None:
        source = 'status = run(repo, "status", "--porcelain=v1", "-uall")\n'
        self.assertTrue(Preflight(gate="t").python_source(source, "pasted").report().ok)

    def test_syntax_check_does_not_execute(self) -> None:
        marker = self.path("side-effect.txt")
        source = "open({!r}, 'w').write('executed')\n".format(str(marker))
        report = Preflight(gate="t").python_source(source, "dangerous").report()
        self.assertTrue(report.ok)
        self.assertFalse(marker.exists(), "preflight must never run the code")

    def test_tree_compilation_reports_the_offending_file(self) -> None:
        package = self.path("pkg")
        package.mkdir()
        (package / "good.py").write_text("x = 1\n")
        (package / "bad.py").write_text("def f(:\n")

        report = Preflight(gate="t").python_tree(package).report()
        self.assertFalse(report.ok)
        self.assertIn("bad.py", report.failures[0].detail)

    def test_tree_skips_vendored_directories(self) -> None:
        package = self.path("pkg")
        (package / "node_modules").mkdir(parents=True)
        (package / "node_modules" / "broken.py").write_text("def f(:\n")
        (package / "ok.py").write_text("x = 1\n")

        self.assertTrue(Preflight(gate="t").python_tree(package).report().ok)


class TestOtherChecks(TempDirCase):
    def test_json_parse(self) -> None:
        good = self.path("good.json")
        good.write_text('{"a": 1}')
        bad = self.path("bad.json")
        bad.write_text("{ nope")

        self.assertTrue(Preflight(gate="t").json_file(good).report().ok)
        self.assertFalse(Preflight(gate="t").json_file(bad).report().ok)

    def test_required_command(self) -> None:
        self.assertTrue(Preflight(gate="t").required_command("git").report().ok)
        self.assertFalse(
            Preflight(gate="t").required_command("definitely-not-installed-xyz")
            .report()
            .ok
        )

    def test_required_path(self) -> None:
        self.assertFalse(
            Preflight(gate="t").required_path(self.path("nope"), kind="dir").report().ok
        )
        self.assertTrue(
            Preflight(gate="t").required_path(self.tmp, kind="dir").report().ok
        )

    def test_writable_path_actually_writes(self) -> None:
        target = self.path("new", "nested")
        self.assertTrue(Preflight(gate="t").writable_path(target).report().ok)
        self.assertTrue(target.is_dir())
        # The probe file must not survive.
        self.assertEqual(list(target.iterdir()), [])

    def test_schema_check(self) -> None:
        contract = Contract(
            name="c",
            version="1.0.0",
            schema={"type": "object", "required": ["a"]},
        )
        self.assertTrue(Preflight(gate="t").schema(contract, {"a": 1}).report().ok)
        self.assertFalse(Preflight(gate="t").schema(contract, {}).report().ok)

    def test_safety_check_reports_missing_capabilities(self) -> None:
        contract = SafetyContract.static_analysis()
        report = Preflight(gate="t").safety(contract, requires=["deploy"]).report()
        self.assertFalse(report.ok)
        self.assertIn("deploy", report.failures[0].detail)

    def test_predicate_treats_exceptions_as_failure(self) -> None:
        def explode() -> bool:
            raise RuntimeError("boom")

        report = Preflight(gate="t").predicate("risky", explode).report()
        self.assertFalse(report.ok)
        self.assertIn("RuntimeError", report.failures[0].detail)


class TestEnforcement(TempDirCase):
    def test_enforce_raises_on_failure(self) -> None:
        checker = Preflight(gate="my-gate")
        checker.python_source("def f(:\n", "bad")
        with self.assertRaises(PreflightFailed) as caught:
            checker.enforce()

        error = caught.exception
        self.assertEqual(error.detail["gate"], "my-gate")
        self.assertIn("SYRA-RULE-PPC-001", error.remediation or "")

    def test_enforce_returns_report_on_success(self) -> None:
        checker = Preflight(gate="my-gate")
        checker.python_source("x = 1\n", "good")
        self.assertTrue(checker.enforce().ok)

    def test_report_renders_gate_convention(self) -> None:
        checker = Preflight(gate="t")
        checker.python_source("x = 1\n", "good")
        rendered = checker.report().render()
        self.assertIn("PREFLIGHT_DECISION=PASS", rendered)


class TestSelfCheck(unittest.TestCase):
    def test_the_core_validates_itself(self) -> None:
        """If the core cannot compile its own source, nothing else matters."""
        report = self_check()
        self.assertTrue(report.ok, msg=report.render())


if __name__ == "__main__":
    unittest.main()
