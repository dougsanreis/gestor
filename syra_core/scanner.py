"""PPC-00A -- static capability discovery across the workspace.

Answers one question and refuses to answer any other: *for each of the 19
capabilities, where in the workspace does an implementation appear to exist?*

The discipline that makes the result usable is a single rule, restated in the
output every time:

    FOUND_DOES_NOT_MEAN_CERTIFIED

A regex match proves a file mentions a concept. It does not prove the code is
reachable, correct, deployed, or canonical. Treating discovery as certification
is how a capability gets marked "done" while the panel that depends on it is
broken.

The scan is read-only, bounded, and brackets itself with a stability check: HEAD
and working-tree status are captured before and after, so concurrent work is
reported as ``STALE_EVIDENCE`` rather than silently producing a mixed snapshot.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import git_authority, util
from .capabilities import CAPABILITIES, CAPABILITY_COUNT, Capability
from .evidence import EvidenceRun
from .git_authority import Authority
from .safety import SafetyContract

GATE = "PPC-00A-CAPABILITY-DISCOVERY"
WORK_ID = "SYRA-PRODUCT-PLATFORM-001"

#: File types worth reading. Everything else is noise or binary.
SOURCE_EXTENSIONS = frozenset(
    {
        ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
        ".json", ".yaml", ".yml", ".toml", ".md", ".sh", ".sql",
        ".go", ".rs", ".rb", ".java", ".kt",
    }
)

EXCLUDED_DIRS = frozenset(
    {
        ".git", "node_modules", ".next", ".open-next", ".wrangler",
        ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache",
        ".cache", "dist", "build", "coverage", ".npm", ".nvm", ".local",
        ".tox", ".eggs", "target",
    }
)

#: A match inside one of these is history, not a live implementation.
NONCANONICAL_SEGMENTS = frozenset(
    {
        "backup", "backups", "evidence", "reports", "snapshots",
        "emergency_backup", "archive", "old", "deprecated",
    }
)

SOURCE_CANDIDATE = "SOURCE_CANDIDATE"
NONCANONICAL_EVIDENCE = "NONCANONICAL_EVIDENCE"

MAX_FILE_BYTES = 2 * 1024 * 1024

#: Status values a capability can land in after discovery.
NO_CANONICAL_SOURCE = "NO_CANONICAL_SOURCE_EVIDENCE"
SINGLE_REPOSITORY = "SINGLE_REPOSITORY_CANDIDATE"
MULTI_REPOSITORY = "MULTI_REPOSITORY_CANDIDATE"


@dataclass
class Candidate:
    """One file that appears to implement one capability."""

    capability: str
    repo: str
    file: str
    authority_class: str
    signals: Tuple[str, ...]
    is_test: bool = False
    has_contract_signal: bool = False

    def as_row(self) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "repo": self.repo,
            "file": self.file,
            "authority_class": self.authority_class,
            "is_test": "YES" if self.is_test else "NO",
            "signals": ",".join(self.signals),
        }


@dataclass
class CapabilitySummary:
    """Aggregate discovery result for one capability."""

    capability: str
    layer: str
    fragility: str
    source_candidates: int
    noncanonical_evidence: int
    repositories: int
    test_candidates: int
    contract_candidates: int
    status: str
    repos: Tuple[str, ...] = ()

    def as_row(self) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "layer": self.layer,
            "fragility": self.fragility,
            "source_candidates": self.source_candidates,
            "noncanonical_evidence": self.noncanonical_evidence,
            "repositories": self.repositories,
            "test_candidates": self.test_candidates,
            "contract_candidates": self.contract_candidates,
            "status": self.status,
        }

    def render(self) -> str:
        return (
            "CAPABILITY={}|SOURCE={}|NONCANONICAL={}|REPOS={}|TESTS={}|STATUS={}".format(
                self.capability,
                self.source_candidates,
                self.noncanonical_evidence,
                self.repositories,
                self.test_candidates,
                self.status,
            )
        )


@dataclass
class ScanResult:
    """Everything the discovery gate produced."""

    authorities: List[Authority]
    candidates: List[Candidate]
    summaries: List[CapabilitySummary]
    risks: List[Dict[str, Any]]
    stability: git_authority.StabilityResult
    files_read: int = 0
    evidence_dir: Optional[Path] = None
    manifest: Optional[Dict[str, Any]] = None

    def by_capability(self, capability_id: str) -> Optional[CapabilitySummary]:
        for item in self.summaries:
            if item.capability == capability_id:
                return item
        return None

    def render_summary(self) -> str:
        lines = ["===== CAPABILITY SUMMARY ====="]
        lines.extend(item.render() for item in self.summaries)
        return "\n".join(lines)

    def render_risks(self) -> str:
        lines = ["===== ARCHITECTURE RISKS ====="]
        if not self.risks:
            lines.append("NO_RISK_SIGNALS=TRUE")
        for risk in self.risks:
            lines.append(
                "SEVERITY={}|CODE={}|EVIDENCE={}".format(
                    risk["severity"], risk["code"], risk["evidence"]
                )
            )
        return "\n".join(lines)


def _is_test_path(relative: Path) -> bool:
    parts = [part.lower() for part in relative.parts]
    if any(part in ("tests", "test", "__tests__", "spec") for part in parts):
        return True
    name = relative.name.lower()
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or ".test." in name
        or ".spec." in name
    )


def _classify_path(relative: Path) -> str:
    if any(part.lower() in NONCANONICAL_SEGMENTS for part in relative.parts):
        return NONCANONICAL_EVIDENCE
    return SOURCE_CANDIDATE


def _iter_source_files(repo: Path) -> Iterable[Tuple[Path, Path]]:
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(repo)
        except ValueError:
            continue
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        yield path, relative


def scan(
    root: Path | str,
    *,
    safety: SafetyContract,
    authorities: Optional[Sequence[Authority]] = None,
) -> ScanResult:
    """Run capability discovery over the selected source authorities."""
    safety.require("filesystem_read", "git_read", site="scanner.scan")

    resolved = list(
        authorities if authorities is not None else git_authority.discover(root, safety=safety)
    )
    scanned = git_authority.selected(resolved)

    compiled: List[Tuple[Capability, Tuple[Any, ...]]] = [
        (capability, capability.compiled) for capability in CAPABILITIES
    ]
    contract_capability = next(
        cap for cap in CAPABILITIES if cap.id == "CONTRACT_REGISTRY"
    )
    contract_patterns = contract_capability.compiled

    candidates: List[Candidate] = []
    counts: Dict[str, Counter] = defaultdict(Counter)
    repos_per_capability: Dict[str, set] = defaultdict(set)
    tests_per_capability: Counter = Counter()
    contracts_per_capability: Counter = Counter()
    files_read = 0

    for authority in scanned:
        repo = authority.path
        for path, relative in _iter_source_files(repo):
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            files_read += 1
            # The path participates in matching: a file named
            # `circuit_breaker.ts` is signal even if the identifier inside
            # differs.
            haystack = str(relative) + "\n" + text
            authority_class = _classify_path(relative)
            is_test = _is_test_path(relative)
            has_contract = any(
                pattern.search(haystack) for pattern in contract_patterns
            )

            for capability, patterns in compiled:
                hits: List[str] = []
                for pattern in patterns:
                    match = pattern.search(haystack)
                    if match:
                        hits.append(match.group(0)[:80])
                if not hits:
                    continue

                candidates.append(
                    Candidate(
                        capability=capability.id,
                        repo=str(repo),
                        file=str(relative),
                        authority_class=authority_class,
                        signals=tuple(sorted(set(hits))),
                        is_test=is_test,
                        has_contract_signal=has_contract,
                    )
                )
                counts[capability.id][authority_class] += 1

                if authority_class == SOURCE_CANDIDATE:
                    if is_test:
                        tests_per_capability[capability.id] += 1
                    else:
                        # Only non-test files establish an authority claim.
                        # A test that merely names a capability does not mean
                        # the repository implements it.
                        repos_per_capability[capability.id].add(str(repo))
                    if has_contract:
                        contracts_per_capability[capability.id] += 1

    summaries: List[CapabilitySummary] = []
    for capability in CAPABILITIES:
        source = counts[capability.id][SOURCE_CANDIDATE]
        historical = counts[capability.id][NONCANONICAL_EVIDENCE]
        repos = repos_per_capability[capability.id]

        if not repos:
            status = NO_CANONICAL_SOURCE
        elif len(repos) == 1:
            status = SINGLE_REPOSITORY
        else:
            status = MULTI_REPOSITORY

        summaries.append(
            CapabilitySummary(
                capability=capability.id,
                layer=capability.layer,
                fragility=capability.fragility,
                source_candidates=source,
                noncanonical_evidence=historical,
                repositories=len(repos),
                test_candidates=tests_per_capability[capability.id],
                contract_candidates=contracts_per_capability[capability.id],
                status=status,
                repos=tuple(sorted(repos)),
            )
        )

    risks = _risk_signals(summaries, resolved)
    stability = git_authority.verify_stability(scanned, safety=safety)

    return ScanResult(
        authorities=resolved,
        candidates=candidates,
        summaries=summaries,
        risks=risks,
        stability=stability,
        files_read=files_read,
    )


def _risk_signals(
    summaries: Sequence[CapabilitySummary], authorities: Sequence[Authority]
) -> List[Dict[str, Any]]:
    """Turn the summary into architecture risks worth acting on."""
    risks: List[Dict[str, Any]] = []

    for item in summaries:
        if item.status == MULTI_REPOSITORY:
            severity = "HIGH" if item.fragility != "ADDITIVE" else "MEDIUM"
            risks.append(
                {
                    "severity": severity,
                    "code": "MULTI_AUTHORITY_" + item.capability,
                    "capability": item.capability,
                    "evidence": "{} source candidates across {} repositories".format(
                        item.source_candidates, item.repositories
                    ),
                }
            )
        elif item.status == NO_CANONICAL_SOURCE:
            risks.append(
                {
                    "severity": "MEDIUM",
                    "code": "NO_SOURCE_" + item.capability,
                    "capability": item.capability,
                    "evidence": "zero canonical source candidates ({} historical)".format(
                        item.noncanonical_evidence
                    ),
                }
            )

        if item.status != NO_CANONICAL_SOURCE and item.test_candidates == 0:
            risks.append(
                {
                    "severity": "HIGH" if item.fragility == "CRITICAL_RUNTIME" else "LOW",
                    "code": "NO_TEST_EVIDENCE_" + item.capability,
                    "capability": item.capability,
                    "evidence": "implementation found with no accompanying test files",
                }
            )

    unborn = [a for a in authorities if a.classification == git_authority.UNBORN_OR_INVALID]
    if unborn:
        risks.append(
            {
                "severity": "LOW",
                "code": "UNBORN_REPOSITORIES",
                "capability": "-",
                "evidence": "{} repositories have no commits: {}".format(
                    len(unborn), ", ".join(a.path.name for a in unborn[:5])
                ),
            }
        )

    dirty = [a for a in authorities if a.scan and a.dirty_files > 0]
    if dirty:
        risks.append(
            {
                "severity": "MEDIUM",
                "code": "UNCOMMITTED_WORK_IN_SOURCE_AUTHORITY",
                "capability": "-",
                "evidence": "{} scanned repositories have uncommitted changes".format(
                    len(dirty)
                ),
            }
        )

    return risks


def persist(
    result: ScanResult,
    *,
    safety: SafetyContract,
    evidence_root: Optional[Path] = None,
) -> ScanResult:
    """Write the discovery artifacts and seal them.

    Sealing declares which artifacts had to exist. If discovery ran but
    persistence failed, the run is a documented FAIL rather than a PASS whose
    evidence quietly went missing.
    """
    run = EvidenceRun(
        work_id=WORK_ID, gate=GATE, safety=safety, root=evidence_root
    )

    run.write_tsv(
        "source-authorities.tsv",
        ["repo", "head", "kind", "scan", "branch", "dirty_files", "reason"],
        [item.as_row() for item in result.authorities],
    )
    run.write_tsv(
        "git-baseline.tsv",
        ["repo", "head", "status_sha"],
        [item.as_baseline() for item in result.authorities if item.scan],
    )
    run.write_tsv(
        "capability-candidates.tsv",
        ["capability", "repo", "file", "authority_class", "is_test", "signals"],
        [
            item.as_row()
            for item in sorted(
                result.candidates,
                key=lambda c: (c.capability, c.repo, c.authority_class, c.file),
            )
        ],
    )
    run.write_tsv(
        "capability-summary.tsv",
        [
            "capability", "layer", "fragility", "source_candidates",
            "noncanonical_evidence", "repositories", "test_candidates",
            "contract_candidates", "status",
        ],
        [item.as_row() for item in result.summaries],
    )
    run.write_tsv(
        "architecture-risk-signals.tsv",
        ["severity", "code", "capability", "evidence"],
        result.risks,
    )

    decision = "PASS" if result.stability.stable else "STALE_EVIDENCE"
    next_state = (
        "PPC00B_CANONICAL_AUTHORITY_RESOLUTION"
        if result.stability.stable
        else "MANUAL_CONCURRENCY_REVIEW"
    )

    run.write_json(
        "final-decision.json",
        {
            "schemaVersion": 1,
            "workId": WORK_ID,
            "gate": GATE,
            "decision": decision,
            "foundDoesNotMeanCertified": True,
            "certificationGranted": False,
            "implementationAuthorized": False,
            "automaticRetryAuthorized": False,
            "capabilitiesEvaluated": CAPABILITY_COUNT,
            "filesRead": result.files_read,
            "sourceAuthorities": len(result.authorities),
            "scannedAuthorities": sum(1 for a in result.authorities if a.scan),
            "concurrentChanges": len(result.stability.changed),
            "nextState": next_state,
        },
    )

    manifest = run.seal(
        decision=decision,
        next_state=next_state,
        required=[
            "source-authorities.tsv",
            "capability-candidates.tsv",
            "capability-summary.tsv",
            "architecture-risk-signals.tsv",
            "final-decision.json",
        ],
        summary={
            "capabilities": CAPABILITY_COUNT,
            "candidates": len(result.candidates),
            "risks": len(result.risks),
            "filesRead": result.files_read,
        },
    )

    result.evidence_dir = run.dir
    result.manifest = manifest
    return result
