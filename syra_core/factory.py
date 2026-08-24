"""Product factory -- new products start certified, not hand-assembled.

Hand-assembling a product means re-deciding, every time, how contracts are
wired, what health means, which failures are tolerable. Nineteen of those
decisions made separately is nineteen chances to get one wrong, and the wrong
ones only surface in production.

The factory removes the decision. Every product it emits:

* carries a valid manifest and real contracts;
* boots through ``ProductRuntime``, inheriting every core guarantee;
* ships passing smoke tests before a single line is customised;
* is validated *after* generation -- the factory checks its own output and
  refuses to hand over a product that does not boot.

Generation is fail-closed: it never overwrites an existing directory, and
``dry_run=True`` shows the exact file list without touching disk.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import blueprints, manifest as manifest_mod, util
from .capabilities import CORE_PROVIDED, get as get_capability
from .errors import ProductExists, SyraError
from .manifest import MANIFEST_FILENAME, ProductManifest
from .safety import SafetyContract
from .version import CORE_VERSION

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass
class PlannedFile:
    """One file the factory intends to write."""

    relative: str
    content: str
    mode: int = 0o644

    @property
    def bytes(self) -> int:
        return len(self.content.encode("utf-8"))


@dataclass
class FactoryResult:
    """What the factory did, or would do under ``dry_run``."""

    product_id: str
    root: Path
    files: List[PlannedFile] = field(default_factory=list)
    dry_run: bool = False
    manifest: Optional[ProductManifest] = None
    verified: bool = False
    verification: Optional[Dict[str, Any]] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "productId": self.product_id,
            "root": str(self.root),
            "dryRun": self.dry_run,
            "verified": self.verified,
            "files": [
                {"path": item.relative, "bytes": item.bytes} for item in self.files
            ],
            "verification": self.verification,
        }

    def render(self) -> str:
        lines = ["===== PRODUCT FACTORY ====="]
        lines.append(util.kv("PRODUCT_ID", self.product_id))
        lines.append(util.kv("ROOT", self.root))
        lines.append(util.kv("DRY_RUN", self.dry_run))
        for item in sorted(self.files, key=lambda f: f.relative):
            lines.append("FILE={}|BYTES={}".format(item.relative, item.bytes))
        lines.append(util.kv("FILES", len(self.files)))
        lines.append(util.kv("VERIFIED", self.verified))
        return "\n".join(lines)


def _package_name(product_id: str) -> str:
    """Python package name derived from the product slug."""
    return product_id.replace("-", "_")


def _validate_id(product_id: str) -> None:
    if not SLUG_PATTERN.match(product_id):
        raise SyraError(
            "Product id {!r} is not a valid slug".format(product_id),
            detail={"productId": product_id},
            remediation=(
                "Use lowercase letters, digits and single hyphens, e.g. "
                "'painel-vendas'. The id becomes a Python package name and a "
                "filesystem path, so it cannot contain spaces or symbols."
            ),
        )


def _default_capabilities(kind: str) -> List[Dict[str, str]]:
    """Capability declarations for a fresh product of this kind."""
    profile = blueprints.KIND_PROFILES[kind]
    entries: List[Dict[str, str]] = []

    for capability_id in CORE_PROVIDED:
        entries.append(
            {
                "id": capability_id,
                "mode": "CORE_PROVIDED",
                "source": "syra_core",
            }
        )

    for capability_id in profile["supplies"]:  # type: ignore[index]
        entries.append(
            {
                "id": capability_id,
                "mode": "BUILD",
                "note": get_capability(capability_id).intent,
            }
        )

    return entries


def _contract_pair(product_id: str, connector_name: str) -> List[Dict[str, Any]]:
    """Request/response contracts for one connector.

    The generated shapes are permissive on purpose -- they accept an object and
    require the fields the stub actually produces. A scaffold that ships a
    strict contract nobody satisfies teaches people to disable validation, which
    is worse than having none.
    """
    return [
        {
            "name": "{}.{}.request".format(product_id, connector_name),
            "version": "1.0.0",
            "description": "Request accepted by the {} connector.".format(connector_name),
            "owner": product_id,
            "schema": {
                "type": "object",
                "additionalProperties": True,
                "properties": {},
            },
        },
        {
            "name": "{}.{}.response".format(product_id, connector_name),
            "version": "1.0.0",
            "description": "Response the {} connector guarantees.".format(connector_name),
            "owner": product_id,
            "schema": {
                "type": "object",
                "required": ["ok"],
                "additionalProperties": True,
                "properties": {
                    "ok": {"type": "boolean"},
                    "connector": {"type": "string"},
                },
            },
        },
    ]


def plan(
    *,
    product_id: str,
    name: Optional[str] = None,
    kind: str = "tool",
    version: str = "0.1.0",
    description: str = "",
    owner: str = "",
    connectors: Optional[Sequence[str]] = None,
    core_home: Optional[Path | str] = None,
) -> Tuple[List[PlannedFile], ProductManifest]:
    """Compute every file for a new product without writing anything.

    Separating planning from writing is what makes ``--dry-run`` honest: the
    same function produces the plan that gets executed, so a rehearsal cannot
    diverge from the real thing.
    """
    _validate_id(product_id)

    if kind not in blueprints.KIND_PROFILES:
        raise SyraError(
            "Unknown product kind {!r}".format(kind),
            detail={"known": sorted(blueprints.KIND_PROFILES)},
            remediation="Choose one of: {}".format(
                ", ".join(sorted(blueprints.KIND_PROFILES))
            ),
        )

    profile = blueprints.KIND_PROFILES[kind]
    display_name = name or product_id.replace("-", " ").title()
    package = _package_name(product_id)
    connector_names: Tuple[str, ...] = tuple(
        connectors if connectors is not None else profile["connectors"]  # type: ignore[arg-type]
    )
    resolved_core = str(
        Path(core_home).resolve()
        if core_home
        else Path(__file__).resolve().parent.parent
    )

    # -- contracts -----------------------------------------------------
    contract_entries: List[Dict[str, Any]] = []
    contract_docs: List[Dict[str, Any]] = []
    for connector_name in connector_names:
        for contract in _contract_pair(product_id, connector_name):
            contract_docs.append(contract)
            contract_entries.append(
                {
                    "name": contract["name"],
                    "version": contract["version"],
                    "file": "contracts/{}.json".format(product_id),
                }
            )

    # -- safety --------------------------------------------------------
    safety = SafetyContract.product_runtime(
        "PRODUCT_RUNTIME:{}".format(product_id),
        network=bool(profile["network"]),
    )

    # -- manifest ------------------------------------------------------
    product_manifest = manifest_mod.build(
        product_id=product_id,
        name=display_name,
        kind=kind,
        version=version,
        description=description or str(profile["summary"]),
        owner=owner,
        capabilities=_default_capabilities(kind),
        connectors=[
            {
                "name": connector_name,
                "kind": "internal_service",
                "critical": True,
                "requestContract": "{}.{}.request".format(product_id, connector_name),
                "responseContract": "{}.{}.response".format(product_id, connector_name),
                "timeoutSeconds": 10.0,
            }
            for connector_name in connector_names
        ],
        contracts=contract_entries,
        entrypoints=[
            {
                "name": "runtime",
                "target": "app.runtime:build",
                "protocol": "python",
                "cwd": ".",
            }
        ],
        safety=safety.as_dict(),
        deploy={"targets": [], "healthPath": "/health", "readyPath": "/ready"},
    )

    supplies = profile["supplies"]  # type: ignore[assignment]
    supplies_list = (
        "\n".join(
            "- **{}** — {}".format(cap_id, get_capability(cap_id).intent)
            for cap_id in supplies  # type: ignore[union-attr]
        )
        if supplies
        else "_Nada. Este tipo de produto é servido inteiramente pelo núcleo._"
    )

    files: List[PlannedFile] = [
        PlannedFile(
            relative=MANIFEST_FILENAME,
            content=util.pretty_json(product_manifest.as_dict()),
        ),
        PlannedFile(
            relative="contracts/{}.json".format(product_id),
            content=util.pretty_json(
                {"schemaVersion": 1, "contracts": contract_docs}
            ),
        ),
        PlannedFile(relative="app/__init__.py", content='"""Application package."""\n'),
        PlannedFile(
            relative="app/_bootstrap.py",
            content=blueprints.BOOTSTRAP_PY.format(core_home=resolved_core),
        ),
        PlannedFile(
            relative="app/runtime.py",
            content=blueprints.RUNTIME_PY.format(
                name=display_name, product_id=product_id
            ),
        ),
        PlannedFile(
            relative="app/connectors.py",
            content=blueprints.render_connectors(connector_names, product_id),
        ),
        PlannedFile(relative="tests/__init__.py", content=""),
        PlannedFile(
            relative="tests/test_smoke.py",
            content=blueprints.TEST_PY.format(
                name=display_name,
                package=package,
                product_id=product_id,
                kind=kind,
                connector_names=list(connector_names),
                first_connector=connector_names[0] if connector_names else "",
            ),
        ),
        PlannedFile(
            relative="README.md",
            content=blueprints.README_MD.format(
                name=display_name,
                summary=description or str(profile["summary"]),
                product_id=product_id,
                kind=kind,
                core_version=CORE_VERSION,
                package=package,
                supplies_list=supplies_list,
            ),
        ),
        PlannedFile(
            relative="syra.plug.json",
            content=util.pretty_json(
                {
                    "schemaVersion": 1,
                    "_note": blueprints.PLUG_JSON_NOTE,
                    "productId": product_id,
                    "kind": kind,
                    "coreVersion": CORE_VERSION,
                    "coreHome": resolved_core,
                    "entrypoint": "app.runtime:build",
                    "manifest": MANIFEST_FILENAME,
                    "commands": {
                        "readiness": "python3 -m app.runtime",
                        "test": "python3 -m unittest discover -s tests",
                    },
                }
            ),
        ),
    ]

    # An empty tests/__init__.py is legitimate; nothing else may be blank.
    for item in files:
        if not item.content and item.relative != "tests/__init__.py":
            raise SyraError(
                "Blueprint produced an empty file: {}".format(item.relative),
                remediation="This is a factory defect. Report it; do not patch by hand.",
            )

    return files, product_manifest


def create(
    destination: Path | str,
    *,
    product_id: str,
    name: Optional[str] = None,
    kind: str = "tool",
    version: str = "0.1.0",
    description: str = "",
    owner: str = "",
    connectors: Optional[Sequence[str]] = None,
    dry_run: bool = False,
    verify: bool = True,
    safety: Optional[SafetyContract] = None,
    core_home: Optional[Path | str] = None,
) -> FactoryResult:
    """Materialise a new product.

    Refuses to write into a directory that already contains files, so an
    accidental re-run cannot clobber work. ``verify=True`` runs the generated
    product's own smoke tests before reporting success -- the factory does not
    get to claim it produced something that works without checking.
    """
    contract = safety or SafetyContract.product_runtime("PRODUCT_FACTORY")
    if not dry_run:
        contract.require("filesystem_write", site="factory.create")

    root = Path(destination).expanduser().resolve()
    files, product_manifest = plan(
        product_id=product_id,
        name=name,
        kind=kind,
        version=version,
        description=description,
        owner=owner,
        connectors=connectors,
        core_home=core_home,
    )

    if dry_run:
        return FactoryResult(
            product_id=product_id,
            root=root,
            files=files,
            dry_run=True,
            manifest=product_manifest,
        )

    if root.exists():
        occupied = [item for item in root.iterdir() if item.name != ".git"]
        if occupied:
            raise ProductExists(
                "Refusing to generate into a non-empty directory: {}".format(root),
                detail={"path": str(root), "entries": [i.name for i in occupied[:10]]},
                remediation=(
                    "Choose an empty directory, or delete the existing contents "
                    "deliberately. The factory never overwrites."
                ),
            )

    root.mkdir(parents=True, exist_ok=True)
    for item in files:
        target = root / item.relative
        target.parent.mkdir(parents=True, exist_ok=True)
        util.atomic_write_text(target, item.content, mode=item.mode)

    result = FactoryResult(
        product_id=product_id,
        root=root,
        files=files,
        dry_run=False,
        manifest=product_manifest,
    )

    if verify:
        result.verification = verify_product(root)
        result.verified = bool(result.verification.get("ok"))
        if not result.verified:
            raise SyraError(
                "Factory generated a product that does not pass its own checks",
                detail={"path": str(root), "verification": result.verification},
                remediation=(
                    "This is a factory defect, not yours. The product was written "
                    "to {} so it can be inspected; report the failure "
                    "output.".format(root)
                ),
            )

    return result


def verify_product(root: Path | str) -> Dict[str, Any]:
    """Check a generated product actually works.

    Three questions, cheapest first: does the manifest validate, does every
    module compile, and do the smoke tests pass. The last one runs in a
    subprocess so a product's import side effects cannot contaminate the
    verifying process.
    """
    from .preflight import Preflight

    target = Path(root).resolve()
    checks: Dict[str, Any] = {}

    checker = Preflight(gate="product-verify")
    checker.required_path(target / MANIFEST_FILENAME, kind="file", label="manifest")
    checker.json_file(target / MANIFEST_FILENAME)
    checker.python_tree(target, label="product")
    report = checker.report()
    checks["preflight"] = report.as_dict()

    if not report.ok:
        return {"ok": False, "path": str(target), "checks": checks}

    try:
        ProductManifest.load(target)
        checks["manifest"] = {"status": "PASS"}
    except SyraError as exc:
        checks["manifest"] = {"status": "FAIL", "error": exc.to_dict()}
        return {"ok": False, "path": str(target), "checks": checks}

    tests_dir = target / "tests"
    if tests_dir.is_dir():
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
            cwd=str(target),
            capture_output=True,
            text=True,
            timeout=180,
        )
        checks["tests"] = {
            "status": "PASS" if completed.returncode == 0 else "FAIL",
            "returncode": completed.returncode,
            "output": util.truncate(
                (completed.stderr or completed.stdout or "").strip(), 1200
            ),
        }
        if completed.returncode != 0:
            return {"ok": False, "path": str(target), "checks": checks}

    return {"ok": True, "path": str(target), "checks": checks}
