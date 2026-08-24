"""The SYRA gates: authority resolution, PPC-00A discovery, PPC-00B decisions.

Tests build real git repositories in a temp directory. Discovery that is only
tested against mocks is discovery that has never met a worktree.
"""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

from tests.support import TempDirCase

from syra_core import decision as decision_mod
from syra_core import git_authority, scanner
from syra_core.capabilities import CAPABILITY_COUNT
from syra_core.errors import SafetyDenied, StaleEvidence
from syra_core.evidence import load_manifest
from syra_core.git_authority import (
    PRIMARY_REPOSITORY,
    UNBORN_OR_INVALID,
    WORKTREE,
)
from syra_core.safety import SafetyContract
from syra_core.scanner import (
    MULTI_REPOSITORY,
    NO_CANONICAL_SOURCE,
    SINGLE_REPOSITORY,
)

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(GIT_ENV)
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )


class WorkspaceCase(TempDirCase):
    def setUp(self) -> None:
        super().setUp()
        self.workspace = self.path("workspace")
        self.workspace.mkdir(parents=True)
        self.safety = SafetyContract.static_analysis("TEST")

    def make_repo(self, name: str, files: dict, *, commit: bool = True) -> Path:
        repo = self.workspace / name
        repo.mkdir(parents=True, exist_ok=True)
        git(repo, "init", "-q", "-b", "main")

        for relative, content in files.items():
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        if commit and files:
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "initial")
        return repo

    def make_unborn_repo(self, name: str) -> Path:
        repo = self.workspace / name
        repo.mkdir(parents=True, exist_ok=True)
        git(repo, "init", "-q", "-b", "main")
        return repo


class TestAuthorityResolution(WorkspaceCase):
    def test_classifies_a_normal_repository(self) -> None:
        self.make_repo("app", {"main.py": "print('hi')\n"})
        authorities = git_authority.discover(self.workspace, safety=self.safety)

        self.assertEqual(len(authorities), 1)
        self.assertEqual(authorities[0].classification, PRIMARY_REPOSITORY)
        self.assertTrue(authorities[0].scan)
        self.assertEqual(authorities[0].branch, "main")

    def test_unborn_repository_is_not_corrupt(self) -> None:
        """A valid git with no commits holds no source. It needs no repair."""
        self.make_unborn_repo("research-os")
        authorities = git_authority.discover(self.workspace, safety=self.safety)

        self.assertEqual(authorities[0].classification, UNBORN_OR_INVALID)
        self.assertFalse(authorities[0].scan)
        self.assertEqual(authorities[0].head, "NONE")
        self.assertIn("UNBORN", authorities[0].reason)

    def test_worktree_is_not_a_second_authority(self) -> None:
        """Counting a worktree separately invents multi-authority conflicts."""
        repo = self.make_repo("app", {"main.py": "x = 1\n"})
        worktree = self.workspace / "app-wt"
        git(repo, "worktree", "add", "-q", "-b", "feature", str(worktree))

        authorities = git_authority.discover(self.workspace, safety=self.safety)
        kinds = {a.path.name: a.classification for a in authorities}

        self.assertEqual(kinds["app"], PRIMARY_REPOSITORY)
        self.assertEqual(kinds["app-wt"], WORKTREE)
        self.assertEqual(len(git_authority.selected(authorities)), 1)

    def test_requires_git_read_capability(self) -> None:
        with self.assertRaises(SafetyDenied):
            git_authority.discover(
                self.workspace, safety=SafetyContract.sealed()
            )

    def test_dirty_files_are_counted(self) -> None:
        repo = self.make_repo("app", {"main.py": "x = 1\n"})
        (repo / "untracked.py").write_text("y = 2\n")

        authorities = git_authority.discover(self.workspace, safety=self.safety)
        self.assertEqual(authorities[0].dirty_files, 1)


class TestStability(WorkspaceCase):
    def test_stable_workspace_passes(self) -> None:
        self.make_repo("app", {"main.py": "x = 1\n"})
        authorities = git_authority.discover(self.workspace, safety=self.safety)
        result = git_authority.verify_stability(
            git_authority.selected(authorities), safety=self.safety
        )
        self.assertTrue(result.stable)

    def test_concurrent_change_is_stale_not_corruption(self) -> None:
        repo = self.make_repo("app", {"main.py": "x = 1\n"})
        authorities = git_authority.discover(self.workspace, safety=self.safety)

        # Simulate concurrent work while the gate was reading.
        (repo / "new_file.py").write_text("y = 2\n")

        result = git_authority.verify_stability(
            git_authority.selected(authorities), safety=self.safety
        )
        self.assertFalse(result.stable)
        self.assertEqual(len(result.changed), 1)

        with self.assertRaises(StaleEvidence) as caught:
            git_authority.require_stable(result, gate="TEST")
        self.assertIn("does not indicate corruption", caught.exception.remediation or "")


class TestScanner(WorkspaceCase):
    def test_finds_capabilities_and_counts_authorities(self) -> None:
        self.make_repo(
            "app",
            {
                "src/breaker.py": "class CircuitBreaker:\n    pass\n",
                "tests/test_breaker.py": "def test_circuit_breaker():\n    pass\n",
            },
        )
        result = scanner.scan(self.workspace, safety=self.safety)

        summary = result.by_capability("CIRCUIT_BREAKER")
        self.assertEqual(summary.status, SINGLE_REPOSITORY)
        self.assertEqual(summary.repositories, 1)
        self.assertGreater(summary.test_candidates, 0)

    def test_reports_every_capability_even_when_absent(self) -> None:
        self.make_repo("app", {"main.py": "x = 1\n"})
        result = scanner.scan(self.workspace, safety=self.safety)
        self.assertEqual(len(result.summaries), CAPABILITY_COUNT)

    def test_multi_authority_is_flagged_as_high_risk(self) -> None:
        self.make_repo("app-a", {"src/breaker.py": "class CircuitBreaker: pass\n"})
        self.make_repo("app-b", {"lib/breaker.py": "class CircuitBreaker: pass\n"})

        result = scanner.scan(self.workspace, safety=self.safety)
        summary = result.by_capability("CIRCUIT_BREAKER")
        self.assertEqual(summary.status, MULTI_REPOSITORY)
        self.assertEqual(summary.repositories, 2)

        codes = {risk["code"] for risk in result.risks}
        self.assertIn("MULTI_AUTHORITY_CIRCUIT_BREAKER", codes)

    def test_backup_directories_are_historical_not_canonical(self) -> None:
        self.make_repo(
            "app", {"backup/old_breaker.py": "class CircuitBreaker: pass\n"}
        )
        result = scanner.scan(self.workspace, safety=self.safety)
        summary = result.by_capability("CIRCUIT_BREAKER")

        self.assertEqual(summary.status, NO_CANONICAL_SOURCE)
        self.assertGreater(summary.noncanonical_evidence, 0)

    def test_tests_alone_do_not_establish_authority(self) -> None:
        """A test naming a capability is not an implementation of it."""
        self.make_repo(
            "app", {"tests/test_watchdog.py": "def test_watchdog(): pass\n"}
        )
        result = scanner.scan(self.workspace, safety=self.safety)
        summary = result.by_capability("WATCHDOG")
        self.assertEqual(summary.repositories, 0)
        self.assertEqual(summary.status, NO_CANONICAL_SOURCE)

    def test_vendored_directories_are_skipped(self) -> None:
        self.make_repo(
            "app",
            {
                "node_modules/pkg/breaker.js": "class CircuitBreaker {}\n",
                "main.py": "x = 1\n",
            },
        )
        result = scanner.scan(self.workspace, safety=self.safety)
        self.assertEqual(
            result.by_capability("CIRCUIT_BREAKER").status, NO_CANONICAL_SOURCE
        )

    def test_evidence_is_sealed_and_verifiable(self) -> None:
        self.make_repo("app", {"src/breaker.py": "class CircuitBreaker: pass\n"})
        result = scanner.scan(self.workspace, safety=self.safety)
        scanner.persist(
            result, safety=self.safety, evidence_root=self.path("evidence")
        )

        self.assertIsNotNone(result.evidence_dir)
        manifest = load_manifest(result.evidence_dir)
        self.assertEqual(manifest["decision"], "PASS")

        names = {item["file"] for item in manifest["artifacts"]}
        self.assertIn("capability-summary.tsv", names)
        self.assertIn("capability-candidates.tsv", names)
        self.assertIn("architecture-risk-signals.tsv", names)

        # The invariant that matters: discovery never mutates what it reads.
        self.assertFalse(manifest["invariants"]["source_mutation"])
        self.assertFalse(manifest["invariants"]["git_mutation"])


class TestDecisionTable(WorkspaceCase):
    def decide_for(self, files: dict, capability: str, *, repos: int = 1):
        if repos == 1:
            self.make_repo("app", files)
        else:
            for index in range(repos):
                self.make_repo(
                    "app-{}".format(index),
                    {"copy{}/{}".format(index, k): v for k, v in files.items()},
                )
        result = scanner.scan(self.workspace, safety=self.safety)
        decisions = decision_mod.from_scan(result)
        return next(d for d in decisions.decisions if d.capability == capability)

    def test_absent_and_core_provided_is_core_provided(self) -> None:
        self.make_repo("app", {"main.py": "x = 1\n"})
        result = scanner.scan(self.workspace, safety=self.safety)
        decisions = decision_mod.from_scan(result)
        found = next(
            d for d in decisions.decisions if d.capability == "CONTRACT_REGISTRY"
        )
        self.assertEqual(found.mode, decision_mod.CORE_PROVIDED_MODE)

    def test_absent_and_product_supplied_is_build(self) -> None:
        self.make_repo("app", {"main.py": "x = 1\n"})
        result = scanner.scan(self.workspace, safety=self.safety)
        decisions = decision_mod.from_scan(result)
        found = next(d for d in decisions.decisions if d.capability == "DESIGN_SYSTEM")
        self.assertEqual(found.mode, decision_mod.BUILD)

    def test_multi_authority_is_consolidate(self) -> None:
        found = self.decide_for(
            {"design_system/index.ts": "export const uiKit = 1\n"},
            "DESIGN_SYSTEM",
            repos=2,
        )
        self.assertEqual(found.mode, decision_mod.CONSOLIDATE)

    def test_single_untested_is_harden(self) -> None:
        found = self.decide_for(
            {"src/design_system.ts": "export const x = 1\n"}, "DESIGN_SYSTEM"
        )
        self.assertEqual(found.mode, decision_mod.HARDEN)
        self.assertIn("NO_TEST_EVIDENCE", found.signals)

    def test_single_tested_critical_is_frozen(self) -> None:
        found = self.decide_for(
            {
                "src/breaker.py": "class CircuitBreaker: pass\n",
                "tests/test_breaker.py": "def test_circuit_breaker(): pass\n",
            },
            "CIRCUIT_BREAKER",
        )
        self.assertEqual(found.mode, decision_mod.DO_NOT_TOUCH)
        self.assertIn("Freeze", found.action)

    def test_critical_multi_authority_gets_low_confidence(self) -> None:
        """Refactoring critical runtime from grep output is the dangerous move."""
        found = self.decide_for(
            {"src/breaker.py": "class CircuitBreaker: pass\n"},
            "CIRCUIT_BREAKER",
            repos=2,
        )
        self.assertEqual(found.mode, decision_mod.CONSOLIDATE)
        self.assertEqual(found.confidence, decision_mod.LOW)
        self.assertIn("Do not refactor yet", found.action)

    def test_every_capability_gets_exactly_one_decision(self) -> None:
        self.make_repo("app", {"main.py": "x = 1\n"})
        result = scanner.scan(self.workspace, safety=self.safety)
        decisions = decision_mod.from_scan(result)

        self.assertEqual(len(decisions.decisions), CAPABILITY_COUNT)
        names = [d.capability for d in decisions.decisions]
        self.assertEqual(len(names), len(set(names)))

    def test_decision_evidence_is_advisory_only(self) -> None:
        self.make_repo("app", {"main.py": "x = 1\n"})
        result = scanner.scan(self.workspace, safety=self.safety)
        decisions = decision_mod.from_scan(result)
        decision_mod.persist(
            decisions, safety=self.safety, evidence_root=self.path("evidence")
        )

        import json

        final = json.loads(
            (decisions.evidence_dir / "final-decision.json").read_text()
        )
        self.assertTrue(final["advisoryOnly"])
        self.assertFalse(final["implementationAuthorized"])
        self.assertFalse(final["sourceMutationAuthorized"])

    def test_consolidate_is_sequenced_first(self) -> None:
        self.make_repo("app-a", {"design_system/a.ts": "export const uiKit = 1\n"})
        self.make_repo("app-b", {"design_system/b.ts": "export const uiKit = 2\n"})
        result = scanner.scan(self.workspace, safety=self.safety)
        decisions = decision_mod.from_scan(result)

        ordered = decisions.ordered()
        self.assertEqual(ordered[0].mode, decision_mod.CONSOLIDATE)


if __name__ == "__main__":
    unittest.main()
