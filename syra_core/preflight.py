"""SYRA-RULE-PPC-001 -- auditor tooling is untrusted until preflighted.

No governance, audit, recovery, or deploy command may be trusted more than the
system it inspects. This module is that rule as executable code: validate the
tooling's syntax, its inputs, its required paths and binaries, and its declared
authority *before* a single operational line runs.

The rule exists because of a real incident: an unterminated string literal in a
several-hundred-line pasted heredoc aborted a recovery gate after it had already
printed its safety banner. Nothing was mutated, but the run was lost. The fix
was never "paste more carefully" -- it was to stop trusting unvalidated tooling.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from . import util
from .errors import PreflightFailed
from .safety import SafetyContract

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

#: Directories never worth compiling: vendored code, caches, build output.
PRUNED_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        ".next",
        ".open-next",
        ".wrangler",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".cache",
        "dist",
        "build",
        "coverage",
        ".npm",
        ".nvm",
        ".tox",
        ".eggs",
    }
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str = ""
    remediation: str = ""

    @property
    def ok(self) -> bool:
        return self.status in (PASS, SKIP)

    def as_dict(self) -> Dict[str, Any]:
        payload = {"check": self.name, "status": self.status}
        if self.detail:
            payload["detail"] = self.detail
        if self.remediation:
            payload["remediation"] = self.remediation
        return payload

    def render(self) -> str:
        line = "CHECK={}|STATUS={}".format(self.name, self.status)
        if self.detail:
            line += "|DETAIL={}".format(util.truncate(self.detail, 200))
        return line


@dataclass
class PreflightReport:
    checks: List[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def failures(self) -> List[CheckResult]:
        return [check for check in self.checks if check.status == FAIL]

    def counts(self) -> Dict[str, int]:
        totals = {PASS: 0, FAIL: 0, SKIP: 0}
        for check in self.checks:
            totals[check.status] = totals.get(check.status, 0) + 1
        return totals

    def as_dict(self) -> Dict[str, Any]:
        return {
            "decision": PASS if self.ok else FAIL,
            "counts": self.counts(),
            "checks": [check.as_dict() for check in self.checks],
        }

    def render(self) -> str:
        lines = ["===== PREFLIGHT ====="]
        lines.extend(check.render() for check in self.checks)
        totals = self.counts()
        lines.append(
            "PREFLIGHT_PASS={}|PREFLIGHT_FAIL={}|PREFLIGHT_SKIP={}".format(
                totals[PASS], totals[FAIL], totals[SKIP]
            )
        )
        lines.append(util.kv("PREFLIGHT_DECISION", PASS if self.ok else FAIL))
        return "\n".join(lines)

    def enforce(self, *, gate: str = "unknown") -> "PreflightReport":
        """Raise unless every check passed. Nothing operational runs before this."""
        if self.ok:
            return self
        raise PreflightFailed(
            "Preflight rejected the tooling before execution ({} failing check{})".format(
                len(self.failures), "" if len(self.failures) == 1 else "s"
            ),
            detail={"gate": gate, "failures": [c.as_dict() for c in self.failures]},
            remediation=(
                "Fix the failing checks and re-run. Do not bypass preflight: "
                "SYRA-RULE-PPC-001 forbids trusting unvalidated tooling."
            ),
            site="preflight.{}".format(gate),
        )


class Preflight:
    """Accumulates checks, then reports. Nothing here executes user logic."""

    def __init__(self, *, gate: str = "unknown") -> None:
        self.gate = gate
        self._checks: List[CheckResult] = []

    # -- primitives ----------------------------------------------------

    def _add(
        self, name: str, status: str, detail: str = "", remediation: str = ""
    ) -> "Preflight":
        self._checks.append(
            CheckResult(name=name, status=status, detail=detail, remediation=remediation)
        )
        return self

    def note(self, name: str, detail: str = "") -> "Preflight":
        return self._add(name, PASS, detail)

    # -- checks --------------------------------------------------------

    def python_source(self, source: str, label: str) -> "Preflight":
        """Compile Python source without executing it.

        ``compile()`` catches exactly the class of defect that killed the
        recovery gate: syntax that only fails once the interpreter reaches it.
        """
        try:
            compile(source, "<{}>".format(label), "exec")
        except SyntaxError as exc:
            return self._add(
                "python_syntax:{}".format(label),
                FAIL,
                "line {}: {}".format(exc.lineno, exc.msg),
                "Fix the syntax error before executing this tooling.",
            )
        return self._add("python_syntax:{}".format(label), PASS)

    def python_file(self, path: Path | str) -> "Preflight":
        target = Path(path)
        if not target.is_file():
            return self._add(
                "python_syntax:{}".format(target.name),
                FAIL,
                "file not found: {}".format(target),
                "Provide a readable Python file.",
            )
        try:
            source = target.read_text(encoding="utf-8")
        except OSError as exc:
            return self._add(
                "python_syntax:{}".format(target.name),
                FAIL,
                "unreadable: {}".format(exc),
                "Check filesystem permissions.",
            )
        return self.python_source(source, str(target))

    def python_tree(self, root: Path | str, *, label: Optional[str] = None) -> "Preflight":
        """Compile every ``.py`` under ``root``. This is how the core audits itself."""
        base = Path(root)
        name = label or base.name

        if not base.is_dir():
            return self._add(
                "python_tree:{}".format(name),
                FAIL,
                "not a directory: {}".format(base),
                "Point at the package directory to validate.",
            )

        failures: List[str] = []
        compiled = 0
        for path in sorted(base.rglob("*.py")):
            if any(part in PRUNED_DIRS for part in path.relative_to(base).parts):
                continue
            try:
                compile(path.read_text(encoding="utf-8"), str(path), "exec")
                compiled += 1
            except SyntaxError as exc:
                failures.append("{}:{}: {}".format(path, exc.lineno, exc.msg))
            except OSError as exc:
                failures.append("{}: {}".format(path, exc))

        if failures:
            return self._add(
                "python_tree:{}".format(name),
                FAIL,
                "; ".join(failures[:5]),
                "Fix the listed syntax errors before running this tooling.",
            )
        return self._add(
            "python_tree:{}".format(name), PASS, "{} modules compiled".format(compiled)
        )

    def json_file(self, path: Path | str) -> "Preflight":
        target = Path(path)
        if not target.is_file():
            return self._add(
                "json_parse:{}".format(target.name),
                FAIL,
                "file not found: {}".format(target),
                "Provide a readable JSON file.",
            )
        try:
            json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return self._add(
                "json_parse:{}".format(target.name),
                FAIL,
                str(exc),
                "Repair the JSON document before it is consumed.",
            )
        return self._add("json_parse:{}".format(target.name), PASS)

    def required_command(self, command: str) -> "Preflight":
        found = shutil.which(command)
        if found is None:
            return self._add(
                "command:{}".format(command),
                FAIL,
                "not found on PATH",
                "Install {} or run this gate on a host that has it.".format(command),
            )
        return self._add("command:{}".format(command), PASS, found)

    def required_path(
        self, path: Path | str, *, kind: str = "any", label: Optional[str] = None
    ) -> "Preflight":
        target = Path(path).expanduser()
        name = "path:{}".format(label or target.name)

        if kind == "dir":
            ok = target.is_dir()
            expectation = "directory"
        elif kind == "file":
            ok = target.is_file()
            expectation = "file"
        else:
            ok = target.exists()
            expectation = "path"

        if not ok:
            return self._add(
                name,
                FAIL,
                "missing {}: {}".format(expectation, target),
                "Create it, or point the gate at the correct location.",
            )
        return self._add(name, PASS, str(target))

    def writable_path(self, path: Path | str, *, label: Optional[str] = None) -> "Preflight":
        """Confirm a directory can actually be written to, not merely that it exists."""
        target = Path(path).expanduser()
        name = "writable:{}".format(label or target.name)
        try:
            target.mkdir(parents=True, exist_ok=True)
            probe = target / ".syra-preflight-probe"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            return self._add(
                name,
                FAIL,
                str(exc),
                "Grant write access to {} or set SYRA_EVIDENCE_ROOT.".format(target),
            )
        return self._add(name, PASS, str(target))

    def schema(
        self, contract: Any, value: Any, *, label: Optional[str] = None
    ) -> "Preflight":
        """Validate a payload against a ``Contract`` before the gate consumes it."""
        name = "schema:{}".format(label or getattr(contract, "name", "payload"))
        violations = contract.validate(value)
        if violations:
            return self._add(
                name,
                FAIL,
                "; ".join(item.render() for item in violations[:5]),
                "Correct the payload to satisfy the contract.",
            )
        return self._add(name, PASS)

    def safety(
        self, contract: SafetyContract, *, requires: Sequence[str] = ()
    ) -> "Preflight":
        """Confirm the declared authority covers what the gate intends to do."""
        missing = [cap for cap in requires if not contract.allows(cap)]
        if missing:
            return self._add(
                "safety:{}".format(contract.purpose),
                FAIL,
                "missing capabilities: {}".format(", ".join(missing)),
                "Grant them explicitly, or choose a gate that does not need them.",
            )
        return self._add(
            "safety:{}".format(contract.purpose),
            PASS,
            "granted: {}".format(", ".join(contract.granted()) or "none"),
        )

    def predicate(
        self,
        name: str,
        test: Callable[[], bool],
        *,
        detail: str = "",
        remediation: str = "",
    ) -> "Preflight":
        """Arbitrary boolean gate. Exceptions are treated as failures, never raised."""
        try:
            ok = bool(test())
        except Exception as exc:  # noqa: BLE001 - preflight must not explode
            return self._add(name, FAIL, "raised {}: {}".format(type(exc).__name__, exc), remediation)
        return self._add(name, PASS if ok else FAIL, detail, "" if ok else remediation)

    def python_version(self, minimum: Sequence[int]) -> "Preflight":
        import sys

        current = sys.version_info[: len(tuple(minimum))]
        if tuple(current) < tuple(minimum):
            return self._add(
                "python_version",
                FAIL,
                "found {}, need >= {}".format(
                    ".".join(str(p) for p in current),
                    ".".join(str(p) for p in minimum),
                ),
                "Run the core on a newer Python 3 interpreter.",
            )
        return self._add(
            "python_version", PASS, ".".join(str(p) for p in current)
        )

    # -- terminal ------------------------------------------------------

    def report(self) -> PreflightReport:
        return PreflightReport(checks=list(self._checks))

    def enforce(self) -> PreflightReport:
        return self.report().enforce(gate=self.gate)


def self_check(*, package_root: Optional[Path] = None) -> PreflightReport:
    """Preflight the core itself.

    Run before anything else. If the core cannot validate its own source, it has
    no standing to validate anyone else's.
    """
    from .version import MIN_PYTHON

    root = package_root or Path(__file__).resolve().parent
    checker = Preflight(gate="syra-core-self-check")
    checker.python_version(MIN_PYTHON)
    checker.python_tree(root, label="syra_core")
    checker.required_command("git")
    return checker.report()
