"""``syra`` -- the operational entrypoint.

Deliberately a small versioned runner rather than a pasted heredoc. The incident
that motivated this core was a several-hundred-line block whose syntax error
only surfaced after the safety banner had already printed. A file in git, with
``--preflight`` and ``--dry-run``, cannot fail that way: it is validated before
it runs, reviewable before it is trusted, and identical every time it executes.

Every command prints ``KEY=VALUE`` lines matching the existing SYRA gate
convention, or machine JSON with ``--json``. Exit codes are stable:

    0   PASS
    1   FAIL (an operation was refused or failed a check)
    2   usage error
    30  STALE_EVIDENCE (sources moved during a scan; re-run when quiet)
"""

from __future__ import annotations

import argparse
import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import capabilities as caps_mod
from . import decision as decision_mod
from . import factory as factory_mod
from . import git_authority, scanner, util
from .errors import StaleEvidence, SyraError
from .evidence import load_manifest
from .failure_memory import FailureMemory
from .manifest import MANIFEST_FILENAME, ProductManifest
from .preflight import Preflight, self_check
from .registry import ProductRegistry
from .safety import SafetyContract
from .version import CORE_NAME, CORE_VERSION, MIN_PYTHON

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_STALE = 30


def _emit(lines: Sequence[str], payload: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    else:
        for line in lines:
            print(line)


def _fail(message: str, *, remediation: str = "", as_json: bool = False) -> int:
    payload = {"decision": "FAIL", "message": message}
    lines = [util.kv("DECISION", "FAIL"), util.kv("REASON", message)]
    if remediation:
        payload["remediation"] = remediation
        lines.append(util.kv("REMEDIATION", remediation))
    _emit(lines, payload, as_json=as_json)
    return EXIT_FAIL


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_version(args: argparse.Namespace) -> int:
    payload = {
        "core": CORE_NAME,
        "version": CORE_VERSION,
        "python": ".".join(str(p) for p in sys.version_info[:3]),
        "dependencies": [],
        "evidenceRoot": str(util.evidence_root()),
        "stateRoot": str(util.state_root()),
        "workspace": str(util.workspace_root()),
    }
    lines = [
        util.kv("CORE", CORE_NAME),
        util.kv("VERSION", CORE_VERSION),
        util.kv("PYTHON", payload["python"]),
        util.kv("EXTERNAL_DEPENDENCIES", 0),
        util.kv("EVIDENCE_ROOT", payload["evidenceRoot"]),
        util.kv("STATE_ROOT", payload["stateRoot"]),
        util.kv("WORKSPACE", payload["workspace"]),
    ]
    _emit(lines, payload, as_json=args.json)
    return EXIT_OK


def cmd_preflight(args: argparse.Namespace) -> int:
    """SYRA-RULE-PPC-001 on demand."""
    if args.paths:
        checker = Preflight(gate="cli-preflight")
        checker.python_version(MIN_PYTHON)
        for raw in args.paths:
            path = Path(raw).expanduser()
            if path.is_dir():
                checker.python_tree(path)
            elif path.suffix == ".json":
                checker.json_file(path)
            else:
                checker.python_file(path)
        report = checker.report()
    else:
        report = self_check()

    _emit([report.render()], report.as_dict(), as_json=args.json)
    return EXIT_OK if report.ok else EXIT_FAIL


def cmd_doctor(args: argparse.Namespace) -> int:
    """Is this machine ready to run the core and its gates?"""
    workspace = Path(args.workspace).expanduser() if args.workspace else util.workspace_root()

    checker = Preflight(gate="doctor")
    checker.python_version(MIN_PYTHON)
    checker.python_tree(Path(__file__).resolve().parent, label="syra_core")
    checker.required_command("git")
    checker.writable_path(util.evidence_root(), label="evidence_root")
    checker.writable_path(util.state_root(), label="state_root")
    checker.required_path(workspace, kind="dir", label="workspace")

    report = checker.report()
    payload = report.as_dict()
    payload["workspace"] = str(workspace)

    lines = [report.render(), util.kv("WORKSPACE", workspace)]
    _emit(lines, payload, as_json=args.json)
    return EXIT_OK if report.ok else EXIT_FAIL


def cmd_selftest(args: argparse.Namespace) -> int:
    """Run the core's own suite. The controlled test before trusting anything."""
    root = Path(__file__).resolve().parent.parent
    loader = unittest.TestLoader()
    suite = loader.discover(str(root / "tests"), top_level_dir=str(root))
    runner = unittest.TextTestRunner(
        verbosity=2 if args.verbose else 1, stream=sys.stderr
    )
    result = runner.run(suite)

    payload = {
        "decision": "PASS" if result.wasSuccessful() else "FAIL",
        "tests": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
    }
    lines = [
        "===== SELFTEST =====",
        util.kv("TESTS_RUN", result.testsRun),
        util.kv("FAILURES", len(result.failures)),
        util.kv("ERRORS", len(result.errors)),
        util.kv("SELFTEST_DECISION", payload["decision"]),
    ]
    _emit(lines, payload, as_json=args.json)
    return EXIT_OK if result.wasSuccessful() else EXIT_FAIL


def cmd_capabilities(args: argparse.Namespace) -> int:
    table = caps_mod.as_table()
    lines = ["===== CAPABILITY TAXONOMY ====="]
    for entry in table:
        lines.append(
            "CAPABILITY={}|LAYER={}|FRAGILITY={}|CORE_PROVIDED={}".format(
                entry["id"],
                entry["layer"],
                entry["fragility"],
                "YES" if entry["id"] in caps_mod.CORE_PROVIDED else "NO",
            )
        )
    lines.append(util.kv("CAPABILITIES", len(table)))
    _emit(lines, {"capabilities": table, "count": len(table)}, as_json=args.json)
    return EXIT_OK


def cmd_authority(args: argparse.Namespace) -> int:
    safety = SafetyContract.static_analysis("PPC00A_AUTHORITY_RESOLUTION")
    root = Path(args.root).expanduser() if args.root else util.workspace_root()

    if not root.is_dir():
        return _fail(
            "Workspace not found: {}".format(root),
            remediation="Pass --root, or set SYRA_WORKSPACE.",
            as_json=args.json,
        )

    authorities = git_authority.discover(root, safety=safety)
    selected = git_authority.selected(authorities)

    lines = [safety.render(), "", "===== SOURCE AUTHORITIES ====="]
    lines.extend(item.render() for item in authorities)
    lines.append(util.kv("GIT_AUTHORITIES_OBSERVED", len(authorities)))
    lines.append(util.kv("SOURCE_AUTHORITIES_SELECTED", len(selected)))

    payload = {
        "workspace": str(root),
        "observed": len(authorities),
        "selected": len(selected),
        "authorities": [item.as_row() for item in authorities],
    }
    _emit(lines, payload, as_json=args.json)
    return EXIT_OK


def cmd_scan(args: argparse.Namespace) -> int:
    """PPC-00A: discover which capabilities appear to exist, and where."""
    safety = SafetyContract.static_analysis("PPC00A_CAPABILITY_DISCOVERY")
    root = Path(args.root).expanduser() if args.root else util.workspace_root()

    if not root.is_dir():
        return _fail(
            "Workspace not found: {}".format(root),
            remediation="Pass --root, or set SYRA_WORKSPACE.",
            as_json=args.json,
        )

    checker = Preflight(gate=scanner.GATE)
    checker.python_version(MIN_PYTHON)
    checker.required_command("git")
    checker.required_path(root, kind="dir", label="workspace")
    if not args.no_evidence:
        checker.writable_path(util.evidence_root(), label="evidence_root")
    checker.enforce()

    result = scanner.scan(root, safety=safety)

    if not args.no_evidence:
        scanner.persist(result, safety=safety)

    decision = "PASS" if result.stability.stable else "STALE_EVIDENCE"
    lines = [
        safety.render(),
        "",
        result.render_summary(),
        "",
        result.render_risks(),
        "",
        result.stability.render(),
        "",
        "===== FINAL =====",
        util.kv("PPC00A_DECISION", decision),
        util.kv("FOUND_DOES_NOT_MEAN_CERTIFIED", True),
        util.kv("CERTIFICATION_GRANTED", False),
        util.kv("IMPLEMENTATION_AUTHORIZED", False),
        util.kv("SOURCE_MUTATION_AUTHORIZED", False),
        util.kv("AUTOMATIC_RETRY_AUTHORIZED", False),
        util.kv("FILES_READ", result.files_read),
        util.kv("CANDIDATE_ROWS", len(result.candidates)),
    ]
    if result.evidence_dir:
        lines.append(util.kv("EVIDENCE_DIR", result.evidence_dir))
        if result.manifest:
            lines.append(
                util.kv("EVIDENCE_MANIFEST_SHA256", result.manifest.get("manifestSha256"))
            )
    lines.append(
        util.kv(
            "NEXT_STATE",
            "PPC00B_CANONICAL_AUTHORITY_RESOLUTION"
            if result.stability.stable
            else "MANUAL_CONCURRENCY_REVIEW",
        )
    )

    payload = {
        "decision": decision,
        "workspace": str(root),
        "filesRead": result.files_read,
        "candidates": len(result.candidates),
        "summaries": [item.as_row() for item in result.summaries],
        "risks": result.risks,
        "evidenceDir": str(result.evidence_dir) if result.evidence_dir else None,
        "concurrentChanges": result.stability.changed,
    }
    _emit(lines, payload, as_json=args.json)
    return EXIT_OK if result.stability.stable else EXIT_STALE


def cmd_decide(args: argparse.Namespace) -> int:
    """PPC-00B: resolve canonical authority into an actionable disposition."""
    safety = SafetyContract.static_analysis("PPC00B_CANONICAL_AUTHORITY_RESOLUTION")
    root = Path(args.root).expanduser() if args.root else util.workspace_root()

    if not root.is_dir():
        return _fail(
            "Workspace not found: {}".format(root),
            remediation="Pass --root, or set SYRA_WORKSPACE.",
            as_json=args.json,
        )

    result = scanner.scan(root, safety=safety)
    if not result.stability.stable:
        lines = [
            result.stability.render(),
            "",
            util.kv("PPC00B_DECISION", "STALE_EVIDENCE"),
            util.kv("REASON", "CONCURRENT_SOURCE_CHANGE_DURING_SCAN"),
            util.kv("AUTOMATIC_RETRY_AUTHORIZED", False),
            util.kv("NEXT_STATE", "MANUAL_CONCURRENCY_REVIEW"),
        ]
        _emit(
            lines,
            {"decision": "STALE_EVIDENCE", "changed": result.stability.changed},
            as_json=args.json,
        )
        return EXIT_STALE

    decisions = decision_mod.from_scan(result)

    source_evidence = None
    if not args.no_evidence:
        scanner.persist(result, safety=safety)
        source_evidence = str(result.evidence_dir)
        decision_mod.persist(decisions, safety=safety, source_evidence=source_evidence)

    lines = [
        safety.render(),
        "",
        decisions.render(),
        "",
        decisions.render_plan(),
        "",
        "===== FINAL =====",
        util.kv("PPC00B_DECISION", "PASS"),
        util.kv("CAPABILITIES_RESOLVED", len(decisions.decisions)),
        util.kv("ADVISORY_ONLY", True),
        util.kv("IMPLEMENTATION_AUTHORIZED", False),
        util.kv("SOURCE_MUTATION_AUTHORIZED", False),
    ]
    if decisions.evidence_dir:
        lines.append(util.kv("EVIDENCE_DIR", decisions.evidence_dir))
    lines.append(util.kv("NEXT_STATE", "PPC00C_INTEGRATION_SEQUENCING"))

    payload = {
        "decision": "PASS",
        "counts": decisions.counts(),
        "decisions": [item.as_dict() for item in decisions.ordered()],
        "evidenceDir": str(decisions.evidence_dir) if decisions.evidence_dir else None,
        "sourceEvidence": source_evidence,
    }
    _emit(lines, payload, as_json=args.json)
    return EXIT_OK


def cmd_evidence(args: argparse.Namespace) -> int:
    """Verify a sealed evidence directory still matches its manifest."""
    target = Path(args.path).expanduser()
    manifest = load_manifest(target)
    lines = [
        "===== EVIDENCE VERIFICATION =====",
        util.kv("GATE", manifest.get("gate")),
        util.kv("DECISION", manifest.get("decision")),
        util.kv("SEALED_AT", manifest.get("sealedAt")),
        util.kv("ARTIFACTS", len(manifest.get("artifacts", []))),
        util.kv("INTEGRITY", "PASS"),
    ]
    _emit(lines, manifest, as_json=args.json)
    return EXIT_OK


# -- product ---------------------------------------------------------------


def cmd_product_new(args: argparse.Namespace) -> int:
    destination = Path(args.into).expanduser() if args.into else Path.cwd() / args.product_id
    result = factory_mod.create(
        destination,
        product_id=args.product_id,
        name=args.name,
        kind=args.kind,
        version=args.product_version,
        description=args.description or "",
        owner=args.owner or "",
        connectors=args.connector or None,
        dry_run=args.dry_run,
        verify=not args.no_verify,
    )

    lines = [result.render()]
    if not args.dry_run:
        lines.append("")
        lines.append("===== NEXT =====")
        lines.append("cd {}".format(result.root))
        lines.append("python3 -m unittest discover -s tests -v")
        lines.append("python3 -m app.runtime")

    _emit(lines, result.as_dict(), as_json=args.json)

    if not args.dry_run and args.register:
        registry = ProductRegistry()
        manifest = ProductManifest.load(result.root)
        entry = registry.register(manifest, path=result.root, replace=True)
        if not args.json:
            print(util.kv("REGISTERED", entry.product_id))

    return EXIT_OK


def cmd_product_validate(args: argparse.Namespace) -> int:
    target = Path(args.path).expanduser().resolve()
    report = factory_mod.verify_product(target)
    lines = [
        "===== PRODUCT VALIDATION =====",
        util.kv("PATH", target),
        util.kv("VALIDATION_DECISION", "PASS" if report["ok"] else "FAIL"),
    ]
    for name, detail in sorted(report.get("checks", {}).items()):
        status = detail.get("status") or detail.get("decision") or "?"
        lines.append("CHECK={}|STATUS={}".format(name, status))
        if isinstance(detail, dict) and detail.get("output") and not report["ok"]:
            lines.append("OUTPUT={}".format(util.truncate(detail["output"], 600)))
    _emit(lines, report, as_json=args.json)
    return EXIT_OK if report["ok"] else EXIT_FAIL


def cmd_product_list(args: argparse.Namespace) -> int:
    registry = ProductRegistry()
    entries = registry.all()
    drift = {item["productId"]: item["reason"] for item in registry.drift_report()}

    lines = ["===== PRODUCT REGISTRY ====="]
    for entry in entries:
        line = entry.render()
        if entry.product_id in drift:
            line += "|DRIFT={}".format(drift[entry.product_id])
        lines.append(line)
    lines.append(util.kv("PRODUCTS", len(entries)))
    lines.append(util.kv("DRIFTED", len(drift)))

    payload = {
        "products": [entry.as_dict() for entry in entries],
        "drift": registry.drift_report(),
        "stats": registry.stats(),
    }
    _emit(lines, payload, as_json=args.json)
    return EXIT_OK


def cmd_product_register(args: argparse.Namespace) -> int:
    target = Path(args.path).expanduser().resolve()
    manifest = ProductManifest.load(target)
    registry = ProductRegistry()
    entry = registry.register(manifest, path=target, replace=args.replace)
    lines = ["===== PRODUCT REGISTERED =====", entry.render()]
    _emit(lines, entry.as_dict(), as_json=args.json)
    return EXIT_OK


def cmd_product_readiness(args: argparse.Namespace) -> int:
    from .runtime import ProductRuntime

    target = Path(args.path).expanduser().resolve()
    with ProductRuntime.from_manifest(target / MANIFEST_FILENAME) as runtime:
        report = runtime.readiness()

    lines = [
        "===== READINESS =====",
        util.kv("PRODUCT", report.get("product")),
        util.kv("STATUS", report.get("status")),
        util.kv("READY", report.get("ready")),
        util.kv("CONNECTORS", report.get("connectors")),
        util.kv("OPEN_BREAKERS", ",".join(report.get("openBreakers", [])) or "none"),
        util.kv("OPEN_DEFECTS", report.get("openDefects")),
    ]
    _emit(lines, report, as_json=args.json)
    return EXIT_OK if report.get("ready") else EXIT_FAIL


# -- failures --------------------------------------------------------------


def cmd_failures_list(args: argparse.Namespace) -> int:
    memory = FailureMemory(args.store)
    records = memory.open_failures() if args.open_only else memory.all()

    lines = ["===== FAILURE MEMORY ====="]
    lines.extend(record.render() for record in records)
    stats = memory.stats()
    lines.append(
        "TOTAL={}|OPEN={}|RESOLVED={}|ACCEPTED={}|OCCURRENCES={}".format(
            stats["total"],
            stats["open"],
            stats["resolved"],
            stats["accepted"],
            stats["occurrences"],
        )
    )
    payload = {"failures": [r.as_dict() for r in records], "stats": stats}
    _emit(lines, payload, as_json=args.json)
    return EXIT_OK


def cmd_failures_resolve(args: argparse.Namespace) -> int:
    memory = FailureMemory(args.store)
    record = (
        memory.accept(args.fingerprint, args.note)
        if args.accept
        else memory.resolve(args.fingerprint, args.note)
    )
    lines = ["===== FAILURE UPDATED =====", record.render()]
    _emit(lines, record.as_dict(), as_json=args.json)
    return EXIT_OK


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="syra",
        description=(
            "SYRA Core -- product integration platform. Zero dependencies, "
            "fail-closed, evidence-first."
        ),
    )
    parser.add_argument(
        "--json", action="store_true", help="machine-readable output"
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("version", help="core version and resolved paths")
    p.set_defaults(func=cmd_version)

    p = sub.add_parser(
        "preflight",
        help="validate tooling before it runs (SYRA-RULE-PPC-001)",
    )
    p.add_argument(
        "paths", nargs="*", help="files or directories; omit to self-check the core"
    )
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("doctor", help="is this machine ready to run the gates?")
    p.add_argument("--workspace", help="workspace root (default: $SYRA_WORKSPACE)")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("selftest", help="run the core's own test suite")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_selftest)

    p = sub.add_parser("capabilities", help="the 19-capability taxonomy")
    p.set_defaults(func=cmd_capabilities)

    p = sub.add_parser(
        "authority", help="classify git source authorities (read-only)"
    )
    p.add_argument("--root", help="workspace root")
    p.set_defaults(func=cmd_authority)

    p = sub.add_parser(
        "scan", help="PPC-00A: discover which capabilities exist, and where"
    )
    p.add_argument("--root", help="workspace root")
    p.add_argument(
        "--no-evidence", action="store_true", help="skip writing evidence artifacts"
    )
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser(
        "decide",
        help="PPC-00B: REUSE / HARDEN / ADAPT / CONSOLIDATE / BUILD / DO_NOT_TOUCH",
    )
    p.add_argument("--root", help="workspace root")
    p.add_argument("--no-evidence", action="store_true")
    p.set_defaults(func=cmd_decide)

    p = sub.add_parser("evidence", help="verify a sealed evidence directory")
    p.add_argument("path", help="evidence directory")
    p.set_defaults(func=cmd_evidence)

    # -- product ------------------------------------------------------
    product = sub.add_parser("product", help="product lifecycle")
    product_sub = product.add_subparsers(dest="product_command")

    p = product_sub.add_parser("new", help="materialise a new product")
    p.add_argument("product_id", help="slug, e.g. painel-vendas")
    p.add_argument("--name", help="display name")
    p.add_argument(
        "--kind",
        default="tool",
        choices=sorted(factory_mod.blueprints.KIND_PROFILES),
        help="what is being built",
    )
    p.add_argument("--product-version", default="0.1.0")
    p.add_argument("--description")
    p.add_argument("--owner")
    p.add_argument(
        "--connector", action="append", help="connector name (repeatable)"
    )
    p.add_argument("--into", help="destination directory")
    p.add_argument("--dry-run", action="store_true", help="plan without writing")
    p.add_argument("--no-verify", action="store_true", help="skip post-generation checks")
    p.add_argument("--register", action="store_true", help="add to the control plane")
    p.set_defaults(func=cmd_product_new)

    p = product_sub.add_parser("validate", help="manifest + compile + smoke tests")
    p.add_argument("path", nargs="?", default=".")
    p.set_defaults(func=cmd_product_validate)

    p = product_sub.add_parser("list", help="registered products and drift")
    p.set_defaults(func=cmd_product_list)

    p = product_sub.add_parser("register", help="add a product to the control plane")
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--replace", action="store_true")
    p.set_defaults(func=cmd_product_register)

    p = product_sub.add_parser("readiness", help="boot a product and report readiness")
    p.add_argument("path", nargs="?", default=".")
    p.set_defaults(func=cmd_product_readiness)

    # -- failures -----------------------------------------------------
    failures = sub.add_parser("failures", help="failure memory")
    failures_sub = failures.add_subparsers(dest="failures_command")

    p = failures_sub.add_parser("list", help="known defects")
    p.add_argument("--store", help="path to a failure-memory file")
    p.add_argument("--open-only", action="store_true")
    p.set_defaults(func=cmd_failures_list)

    p = failures_sub.add_parser("resolve", help="mark a defect fixed")
    p.add_argument("fingerprint", help="full fingerprint or unique prefix")
    p.add_argument("note", help="what was actually changed")
    p.add_argument("--store")
    p.add_argument(
        "--accept",
        action="store_true",
        help="mark as tolerated rather than fixed",
    )
    p.set_defaults(func=cmd_failures_resolve)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_USAGE

    try:
        return args.func(args)
    except StaleEvidence as exc:
        _emit(
            [
                util.kv("DECISION", "STALE_EVIDENCE"),
                util.kv("REASON", exc.message),
                util.kv("AUTOMATIC_RETRY_AUTHORIZED", False),
                util.kv("REMEDIATION", exc.remediation or ""),
            ],
            exc.to_dict(),
            as_json=args.json,
        )
        return EXIT_STALE
    except SyraError as exc:
        _emit(
            [
                util.kv("DECISION", "FAIL"),
                util.kv("ERROR_CODE", exc.code),
                util.kv("REASON", exc.message),
                util.kv("REMEDIATION", exc.remediation or ""),
            ],
            exc.to_dict(),
            as_json=args.json,
        )
        return EXIT_FAIL
    except KeyboardInterrupt:
        print(util.kv("DECISION", "INTERRUPTED"), file=sys.stderr)
        return EXIT_FAIL


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
