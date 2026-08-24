"""Product manifest -- the declaration that makes a product governable.

A product with no manifest cannot be reasoned about: nobody knows which
capabilities it claims, which integrations it needs, or what it is allowed to
do. Every product the factory builds carries one, and the runtime refuses to
boot from a manifest that does not validate.

The manifest is validated by the core's own contract engine, so the mechanism
that guards product boundaries is the same one that guards the core's -- one
validator to trust instead of two to keep in sync.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from . import util
from .capabilities import CAPABILITY_IDS
from .contracts import Contract
from .errors import ManifestInvalid
from .safety import CAPABILITIES as SAFETY_CAPABILITIES
from .version import MANIFEST_SCHEMA_VERSION

#: What kind of thing is being built. Mirrors the product classes the platform
#: exists to produce: an online platform, a multi-agent platform, a squad, a
#: single specialised agent, a SaaS, or a strategic tool.
PRODUCT_KINDS = (
    "platform",
    "multi_agent_platform",
    "agent_squad",
    "agent",
    "saas",
    "tool",
)

#: PPC-00B dispositions. What to do with an existing implementation.
CAPABILITY_MODES = (
    "REUSE",
    "HARDEN",
    "ADAPT",
    "CONSOLIDATE",
    "BUILD",
    "DO_NOT_TOUCH",
    "CORE_PROVIDED",
    "NOT_APPLICABLE",
)

MANIFEST_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["schemaVersion", "productId", "name", "kind", "version"],
    "additionalProperties": True,
    "properties": {
        "schemaVersion": {"type": "integer", "minimum": 1},
        "productId": {
            "type": "string",
            "format": "slug",
            "minLength": 2,
            "maxLength": 64,
        },
        "name": {"type": "string", "minLength": 1, "maxLength": 120},
        "kind": {"type": "string", "enum": list(PRODUCT_KINDS)},
        "version": {"type": "string", "format": "semver"},
        "description": {"type": "string", "maxLength": 500},
        "owner": {"type": "string", "maxLength": 120},
        "coreVersion": {"type": "string"},
        "capabilities": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "mode"],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string", "enum": list(CAPABILITY_IDS)},
                    "mode": {"type": "string", "enum": list(CAPABILITY_MODES)},
                    "source": {"type": "string"},
                    "note": {"type": "string", "maxLength": 400},
                },
            },
        },
        "connectors": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "kind"],
                "additionalProperties": True,
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "kind": {"type": "string"},
                    "critical": {"type": "boolean"},
                    "requestContract": {"type": "string", "nullable": True},
                    "responseContract": {"type": "string", "nullable": True},
                    "timeoutSeconds": {"type": "number", "minimum": 0},
                },
            },
        },
        "contracts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "version"],
                "additionalProperties": True,
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "version": {"type": "string", "format": "semver"},
                    "file": {"type": "string"},
                },
            },
        },
        "safety": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "purpose": {"type": "string"},
                **{name: {"type": "boolean"} for name in SAFETY_CAPABILITIES},
            },
        },
        "entrypoints": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "target"],
                "additionalProperties": True,
                "properties": {
                    "name": {"type": "string"},
                    "target": {"type": "string"},
                    "protocol": {"type": "string"},
                },
            },
        },
        "deploy": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "targets": {"type": "array", "items": {"type": "string"}},
                "healthPath": {"type": "string"},
                "readyPath": {"type": "string"},
            },
        },
    },
}

MANIFEST_CONTRACT = Contract(
    name="syra.product.manifest",
    version="1.0.0",
    schema=MANIFEST_SCHEMA,
    description="Declaration every SYRA product must satisfy to be governable.",
    owner="syra-core",
)

MANIFEST_FILENAME = "product.manifest.json"


@dataclass
class ProductManifest:
    """A validated product declaration."""

    data: Mapping[str, Any]
    path: Optional[Path] = None

    def __post_init__(self) -> None:
        violations = MANIFEST_CONTRACT.validate(self.data)
        if violations:
            raise ManifestInvalid(
                "Product manifest is invalid ({} violation{})".format(
                    len(violations), "" if len(violations) == 1 else "s"
                ),
                detail={
                    "path": str(self.path) if self.path else None,
                    "violations": [item.as_dict() for item in violations],
                },
                remediation=(
                    "Fix: " + "; ".join(item.render() for item in violations[:5])
                ),
                site="manifest",
            )

    # -- accessors -----------------------------------------------------

    @property
    def product_id(self) -> str:
        return self.data["productId"]

    @property
    def name(self) -> str:
        return self.data["name"]

    @property
    def kind(self) -> str:
        return self.data["kind"]

    @property
    def version(self) -> str:
        return self.data["version"]

    @property
    def owner(self) -> str:
        return self.data.get("owner", "")

    @property
    def description(self) -> str:
        return self.data.get("description", "")

    def capabilities(self) -> List[Dict[str, Any]]:
        return list(self.data.get("capabilities", []))

    def capability_mode(self, capability_id: str) -> Optional[str]:
        for entry in self.capabilities():
            if entry["id"] == capability_id:
                return entry["mode"]
        return None

    def connectors(self) -> List[Dict[str, Any]]:
        return list(self.data.get("connectors", []))

    def contracts(self) -> List[Dict[str, Any]]:
        return list(self.data.get("contracts", []))

    def entrypoints(self) -> List[Dict[str, Any]]:
        return list(self.data.get("entrypoints", []))

    def safety_mapping(self) -> Dict[str, Any]:
        return dict(self.data.get("safety", {}))

    @property
    def fingerprint(self) -> str:
        return util.fingerprint(self.data)

    # -- persistence ---------------------------------------------------

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.data)

    def save(self, path: Optional[Path | str] = None) -> Path:
        target = Path(path) if path else self.path
        if target is None:
            raise ManifestInvalid(
                "No path given and this manifest was not loaded from disk",
                remediation="Pass an explicit path to save().",
            )
        if target.is_dir():
            target = target / MANIFEST_FILENAME
        util.write_json(target, dict(self.data), mode=0o644)
        self.path = target
        return target

    @classmethod
    def load(cls, path: Path | str) -> "ProductManifest":
        target = Path(path)
        if target.is_dir():
            target = target / MANIFEST_FILENAME
        if not target.is_file():
            raise ManifestInvalid(
                "No product manifest at {}".format(target),
                detail={"path": str(target)},
                remediation=(
                    "Every governed product needs a {} at its root. "
                    "`syra product new` creates one.".format(MANIFEST_FILENAME)
                ),
            )
        try:
            data = util.read_json(target)
        except ValueError as exc:
            raise ManifestInvalid(
                "Product manifest is not valid JSON: {}".format(exc),
                detail={"path": str(target)},
                remediation="Repair the JSON syntax.",
            ) from exc
        return cls(data=data, path=target)


def build(
    *,
    product_id: str,
    name: str,
    kind: str,
    version: str = "0.1.0",
    description: str = "",
    owner: str = "",
    capabilities: Optional[Sequence[Mapping[str, Any]]] = None,
    connectors: Optional[Sequence[Mapping[str, Any]]] = None,
    contracts: Optional[Sequence[Mapping[str, Any]]] = None,
    entrypoints: Optional[Sequence[Mapping[str, Any]]] = None,
    safety: Optional[Mapping[str, Any]] = None,
    deploy: Optional[Mapping[str, Any]] = None,
) -> ProductManifest:
    """Construct and validate a manifest in one step."""
    from .version import CORE_VERSION

    data: Dict[str, Any] = {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "productId": product_id,
        "name": name,
        "kind": kind,
        "version": version,
        "coreVersion": CORE_VERSION,
    }
    if description:
        data["description"] = description
    if owner:
        data["owner"] = owner
    if capabilities is not None:
        data["capabilities"] = [dict(item) for item in capabilities]
    if connectors is not None:
        data["connectors"] = [dict(item) for item in connectors]
    if contracts is not None:
        data["contracts"] = [dict(item) for item in contracts]
    if entrypoints is not None:
        data["entrypoints"] = [dict(item) for item in entrypoints]
    if safety is not None:
        data["safety"] = dict(safety)
    if deploy is not None:
        data["deploy"] = dict(deploy)

    return ProductManifest(data=data)
