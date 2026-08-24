"""Git source-authority resolution -- which repository actually speaks for a thing.

Before any capability can be judged, one question must be settled: which of the
repositories in a workspace is *authoritative*? Getting this wrong produces
exactly the confusion that stalls investigations:

* a **worktree** counted as a separate repository inflates every capability into
  a fake multi-authority conflict;
* an **unborn** repository (valid ``.git``, no commits, no tracked files) reads
  as "corrupted" when it is merely empty, and gets scheduled for repair it does
  not need;
* an **evidence or backup directory** scanned as source turns historical
  artifacts into apparent live implementations.

Each classification is recorded with the reason it was assigned, so a later
reader can disagree with the judgement instead of re-deriving it.

Every git call here is read-only plumbing and requires the ``git_read``
capability. Nothing in this module can mutate a repository.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import util
from .errors import StaleEvidence
from .safety import SafetyContract

# Classifications
PRIMARY_REPOSITORY = "PRIMARY_REPOSITORY"
WORKTREE = "WORKTREE"
UNBORN_OR_INVALID = "UNBORN_OR_INVALID"
NON_SOURCE_AUTHORITY = "NON_SOURCE_AUTHORITY"

#: Directories that are never source, even when they contain a ``.git``.
PRUNED = frozenset(
    {
        "node_modules",
        ".next",
        ".open-next",
        ".wrangler",
        ".venv",
        "venv",
        "__pycache__",
        ".cache",
        ".npm",
        ".nvm",
        ".local",
        "dist",
        "build",
        "coverage",
    }
)

#: Path segments whose contents are historical rather than canonical.
NONCANONICAL_SEGMENTS = frozenset(
    {
        "backup",
        "backups",
        "evidence",
        "reports",
        "snapshots",
        "emergency_backup",
        ".worktrees",
    }
)

GIT_ENV = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_OPTIONAL_LOCKS": "0",
    "NO_COLOR": "1",
}


@dataclass
class Authority:
    """One git repository and what role it plays in this investigation."""

    path: Path
    head: str
    classification: str
    scan: bool
    reason: str
    branch: str = ""
    dirty_files: int = 0
    status_sha: str = ""

    def as_row(self) -> Dict[str, Any]:
        return {
            "repo": str(self.path),
            "head": self.head,
            "kind": self.classification,
            "scan": "YES" if self.scan else "NO",
            "branch": self.branch,
            "dirty_files": self.dirty_files,
            "reason": self.reason,
        }

    def as_baseline(self) -> Dict[str, Any]:
        return {
            "repo": str(self.path),
            "head": self.head,
            "status_sha": self.status_sha,
        }

    def render(self) -> str:
        return "AUTHORITY={}|KIND={}|SCAN={}|HEAD={}|REASON={}".format(
            self.path,
            self.classification,
            "YES" if self.scan else "NO",
            self.head[:12] if self.head != "NONE" else "NONE",
            self.reason,
        )


def _git(repo: Path, *args: str, timeout: float = 30.0) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ)
    env.update(GIT_ENV)
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _status_snapshot(repo: Path) -> Tuple[str, int]:
    """Hash of the working-tree status, plus the number of dirty entries."""
    result = _git(repo, "status", "--porcelain=v1", "-uall")
    text = result.stdout if result.returncode == 0 else ""
    lines = [line for line in text.splitlines() if line.strip()]
    return util.sha256_text(text), len(lines)


def discover(
    root: Path | str,
    *,
    safety: SafetyContract,
    max_depth: int = 6,
) -> List[Authority]:
    """Find and classify every git repository under ``root``.

    Depth-limited: a workspace with deeply nested vendored checkouts should not
    turn discovery into an unbounded filesystem walk.
    """
    safety.require("git_read", "filesystem_read", site="git_authority.discover")

    base = Path(root).expanduser().resolve()
    found: Dict[Path, None] = {}

    for marker in base.rglob(".git"):
        try:
            relative = marker.relative_to(base)
        except ValueError:
            continue
        if len(relative.parts) > max_depth:
            continue
        if any(part in PRUNED for part in relative.parts):
            continue
        if not (marker.is_dir() or marker.is_file()):
            continue

        resolved = _git(marker.parent, "rev-parse", "--show-toplevel")
        if resolved.returncode == 0 and resolved.stdout.strip():
            found[Path(resolved.stdout.strip()).resolve()] = None

    return [_classify(repo, base) for repo in sorted(found)]


def _classify(repo: Path, workspace: Path) -> Authority:
    head = _git(repo, "rev-parse", "--verify", "HEAD")

    if head.returncode != 0 or not head.stdout.strip():
        # Valid git, no commits. Empty is not corrupt: it holds no source, so
        # it cannot be an authority for anything, and it needs no repair.
        return Authority(
            path=repo,
            head="NONE",
            classification=UNBORN_OR_INVALID,
            scan=False,
            reason="NO_RESOLVED_HEAD_UNBORN_REPOSITORY",
        )

    sha = head.stdout.strip()
    branch_result = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else ""

    common = _git(repo, "rev-parse", "--git-common-dir")
    git_dir = _git(repo, "rev-parse", "--git-dir")
    is_worktree = (
        common.returncode == 0
        and git_dir.returncode == 0
        and common.stdout.strip() != git_dir.stdout.strip()
    )

    status_sha, dirty = _status_snapshot(repo)

    try:
        relative_parts = repo.relative_to(workspace).parts
    except ValueError:
        relative_parts = repo.parts

    if is_worktree or ".worktrees" in repo.parts:
        classification = WORKTREE
        scan = False
        reason = "AVOID_DOUBLE_COUNTING_CANONICAL_REPOSITORY"
    elif any(part.lower() in NONCANONICAL_SEGMENTS for part in relative_parts):
        classification = NON_SOURCE_AUTHORITY
        scan = False
        reason = "HISTORICAL_OR_BACKUP_LOCATION"
    else:
        classification = PRIMARY_REPOSITORY
        scan = True
        reason = "RESOLVED_HEAD"

    return Authority(
        path=repo,
        head=sha,
        classification=classification,
        scan=scan,
        reason=reason,
        branch=branch,
        dirty_files=dirty,
        status_sha=status_sha,
    )


def selected(authorities: Sequence[Authority]) -> List[Authority]:
    return [item for item in authorities if item.scan]


@dataclass
class StabilityResult:
    """Whether the sources held still while they were being read."""

    stable: bool
    changed: List[Dict[str, Any]] = field(default_factory=list)
    checked: int = 0

    def render(self) -> str:
        lines = ["===== CONCURRENCY / IMMUTABILITY VALIDATOR ====="]
        for entry in self.changed:
            lines.append(
                "REPO_STABILITY={}|HEAD_SAME={}|STATUS_SAME={}|RESULT=CONCURRENT_CHANGE".format(
                    entry["repo"],
                    "YES" if entry["head_same"] else "NO",
                    "YES" if entry["status_same"] else "NO",
                )
            )
        lines.append(util.kv("REPOS_CHECKED", self.checked))
        lines.append(util.kv("CONCURRENT_CHANGE_COUNT", len(self.changed)))
        lines.append(
            util.kv("SOURCE_SNAPSHOT_STABILITY", "PASS" if self.stable else "STALE")
        )
        return "\n".join(lines)


def verify_stability(
    baseline: Sequence[Authority], *, safety: SafetyContract
) -> StabilityResult:
    """Re-read HEAD and status; report anything that moved during the scan.

    A repository that changed mid-scan makes the scan's conclusions unreliable.
    That is ``STALE_EVIDENCE`` -- a reason to re-run, not evidence of
    corruption, and never a reason for the scanner to suspect itself of having
    written to a source tree it never opened for writing.
    """
    safety.require("git_read", site="git_authority.verify_stability")

    changed: List[Dict[str, Any]] = []
    for authority in baseline:
        head = _git(authority.path, "rev-parse", "--verify", "HEAD")
        current_head = head.stdout.strip() if head.returncode == 0 else "NONE"
        current_status, _ = _status_snapshot(authority.path)

        head_same = current_head == authority.head
        status_same = current_status == authority.status_sha

        if not (head_same and status_same):
            changed.append(
                {
                    "repo": str(authority.path),
                    "head_same": head_same,
                    "status_same": status_same,
                    "baseline_head": authority.head,
                    "current_head": current_head,
                }
            )

    return StabilityResult(
        stable=not changed, changed=changed, checked=len(baseline)
    )


def require_stable(result: StabilityResult, *, gate: str) -> None:
    """Raise ``StaleEvidence`` when sources moved. No automatic retry."""
    if result.stable:
        return
    raise StaleEvidence(
        "Sources changed while {} was reading them ({} repositor{})".format(
            gate, len(result.changed), "y" if len(result.changed) == 1 else "ies"
        ),
        detail={"gate": gate, "changed": result.changed},
        remediation=(
            "Concurrent work touched the workspace. Re-run the gate when it is "
            "quiet. This does not indicate corruption, and the gate did not "
            "write to any source tree -- automatic retry stays unauthorised."
        ),
        site="gate.{}".format(gate),
    )
