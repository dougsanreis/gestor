"""Contract registry and schema validator -- the anti-drift layer.

Panels break at integration boundaries, not inside components. A backend adds a
required field, a frontend keeps sending the old shape, and the failure surfaces
three layers away as an unhelpful runtime error. This module makes the boundary
explicit and checkable:

* a **contract** is a named, versioned, content-hashed schema;
* payloads are validated at the boundary and violations are reported with a JSON
  pointer to the exact offending field;
* ``compatibility()`` compares two versions and tells you whether shipping the
  new one breaks existing consumers *before* you ship it.

The validator is a deliberate subset of JSON Schema -- enough to describe real
payloads, small enough to audit in one sitting, and stdlib-only so adding it to
a project can never break that project's dependency tree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import util
from .errors import ContractIncompatible, ContractUnknown, ContractViolation
from .version import CONTRACT_SCHEMA_VERSION

REF_PREFIX = "syra://contract/"

_FORMAT_PATTERNS = {
    "uuid": re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    ),
    "email": re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    "uri": re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:\S*$"),
    "date-time": re.compile(
        r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}"
        r"(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
    ),
    "date": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    "semver": re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$"),
    "slug": re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
}


@dataclass(frozen=True)
class Violation:
    """One contract breach, addressed by JSON pointer."""

    pointer: str
    code: str
    message: str
    expected: Any = None
    actual: Any = None

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "pointer": self.pointer,
            "code": self.code,
            "message": self.message,
        }
        if self.expected is not None:
            payload["expected"] = self.expected
        if self.actual is not None:
            payload["actual"] = self.actual
        return payload

    def render(self) -> str:
        return "{} :: {} :: {}".format(self.pointer, self.code, self.message)


# ---------------------------------------------------------------------------
# Type handling
# ---------------------------------------------------------------------------


def type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (list, tuple)):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _type_matches(expected: str, actual: str) -> bool:
    if expected == "number":
        return actual in ("number", "integer")
    return expected == actual


def _as_type_list(declared: Any) -> List[str]:
    if declared is None:
        return []
    if isinstance(declared, str):
        return [declared]
    return list(declared)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate(
    schema: Mapping[str, Any],
    value: Any,
    *,
    pointer: str = "$",
    registry: Optional["ContractRegistry"] = None,
) -> List[Violation]:
    """Validate ``value`` against ``schema``. Returns every violation found.

    All violations are collected rather than short-circuiting on the first: one
    round trip should tell an operator everything that is wrong, not the first
    thing that happened to be wrong.
    """
    violations: List[Violation] = []

    ref = schema.get("$ref")
    if ref:
        resolved = _resolve_ref(ref, registry)
        if resolved is None:
            violations.append(
                Violation(
                    pointer=pointer,
                    code="REF_UNRESOLVED",
                    message="Cannot resolve contract reference {}".format(ref),
                    expected=ref,
                )
            )
            return violations
        return validate(resolved, value, pointer=pointer, registry=registry)

    if value is None and schema.get("nullable"):
        return violations

    declared_types = _as_type_list(schema.get("type"))
    if declared_types:
        actual = type_name(value)
        if not any(_type_matches(item, actual) for item in declared_types):
            violations.append(
                Violation(
                    pointer=pointer,
                    code="TYPE_MISMATCH",
                    message="Expected {}, received {}".format(
                        " or ".join(declared_types), actual
                    ),
                    expected=declared_types if len(declared_types) > 1 else declared_types[0],
                    actual=actual,
                )
            )
            # Further keyword checks would be noise once the type is wrong.
            return violations

    if "const" in schema and value != schema["const"]:
        violations.append(
            Violation(
                pointer=pointer,
                code="CONST_MISMATCH",
                message="Value must be exactly {!r}".format(schema["const"]),
                expected=schema["const"],
                actual=value,
            )
        )

    if "enum" in schema and value not in schema["enum"]:
        violations.append(
            Violation(
                pointer=pointer,
                code="ENUM_MISMATCH",
                message="Value must be one of {}".format(schema["enum"]),
                expected=schema["enum"],
                actual=value,
            )
        )

    if "anyOf" in schema:
        branches = schema["anyOf"]
        if not any(
            not validate(branch, value, pointer=pointer, registry=registry)
            for branch in branches
        ):
            violations.append(
                Violation(
                    pointer=pointer,
                    code="ANY_OF_MISMATCH",
                    message="Value satisfies none of the {} allowed shapes".format(
                        len(branches)
                    ),
                    actual=type_name(value),
                )
            )

    if isinstance(value, str) and not isinstance(value, bool):
        violations.extend(_validate_string(schema, value, pointer))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        violations.extend(_validate_number(schema, value, pointer))
    elif isinstance(value, (list, tuple)):
        violations.extend(_validate_array(schema, value, pointer, registry))
    elif isinstance(value, dict):
        violations.extend(_validate_object(schema, value, pointer, registry))

    return violations


def _validate_string(
    schema: Mapping[str, Any], value: str, pointer: str
) -> List[Violation]:
    found: List[Violation] = []

    minimum = schema.get("minLength")
    if minimum is not None and len(value) < minimum:
        found.append(
            Violation(
                pointer=pointer,
                code="MIN_LENGTH",
                message="String shorter than {} characters".format(minimum),
                expected=minimum,
                actual=len(value),
            )
        )

    maximum = schema.get("maxLength")
    if maximum is not None and len(value) > maximum:
        found.append(
            Violation(
                pointer=pointer,
                code="MAX_LENGTH",
                message="String longer than {} characters".format(maximum),
                expected=maximum,
                actual=len(value),
            )
        )

    pattern = schema.get("pattern")
    if pattern is not None and not re.search(pattern, value):
        found.append(
            Violation(
                pointer=pointer,
                code="PATTERN_MISMATCH",
                message="String does not match {}".format(pattern),
                expected=pattern,
                actual=util.truncate(value, 80),
            )
        )

    fmt = schema.get("format")
    if fmt:
        compiled = _FORMAT_PATTERNS.get(fmt)
        if compiled is not None and not compiled.match(value):
            found.append(
                Violation(
                    pointer=pointer,
                    code="FORMAT_MISMATCH",
                    message="String is not a valid {}".format(fmt),
                    expected=fmt,
                    actual=util.truncate(value, 80),
                )
            )

    return found


def _validate_number(
    schema: Mapping[str, Any], value: Any, pointer: str
) -> List[Violation]:
    found: List[Violation] = []

    minimum = schema.get("minimum")
    if minimum is not None and value < minimum:
        found.append(
            Violation(
                pointer=pointer,
                code="MINIMUM",
                message="Value below minimum {}".format(minimum),
                expected=minimum,
                actual=value,
            )
        )

    maximum = schema.get("maximum")
    if maximum is not None and value > maximum:
        found.append(
            Violation(
                pointer=pointer,
                code="MAXIMUM",
                message="Value above maximum {}".format(maximum),
                expected=maximum,
                actual=value,
            )
        )

    return found


def _validate_array(
    schema: Mapping[str, Any],
    value: Sequence[Any],
    pointer: str,
    registry: Optional["ContractRegistry"],
) -> List[Violation]:
    found: List[Violation] = []

    minimum = schema.get("minItems")
    if minimum is not None and len(value) < minimum:
        found.append(
            Violation(
                pointer=pointer,
                code="MIN_ITEMS",
                message="Array needs at least {} items".format(minimum),
                expected=minimum,
                actual=len(value),
            )
        )

    maximum = schema.get("maxItems")
    if maximum is not None and len(value) > maximum:
        found.append(
            Violation(
                pointer=pointer,
                code="MAX_ITEMS",
                message="Array allows at most {} items".format(maximum),
                expected=maximum,
                actual=len(value),
            )
        )

    if schema.get("uniqueItems"):
        seen: List[str] = []
        for item in value:
            key = util.canonical_json(item)
            if key in seen:
                found.append(
                    Violation(
                        pointer=pointer,
                        code="UNIQUE_ITEMS",
                        message="Array contains duplicate entries",
                        actual=util.truncate(key, 80),
                    )
                )
                break
            seen.append(key)

    item_schema = schema.get("items")
    if isinstance(item_schema, dict):
        for index, item in enumerate(value):
            found.extend(
                validate(
                    item_schema,
                    item,
                    pointer="{}[{}]".format(pointer, index),
                    registry=registry,
                )
            )

    return found


def _validate_object(
    schema: Mapping[str, Any],
    value: Mapping[str, Any],
    pointer: str,
    registry: Optional["ContractRegistry"],
) -> List[Violation]:
    found: List[Violation] = []
    properties: Mapping[str, Any] = schema.get("properties", {}) or {}

    for name in schema.get("required", []) or []:
        if name not in value:
            found.append(
                Violation(
                    pointer="{}.{}".format(pointer, name),
                    code="REQUIRED_MISSING",
                    message="Required property {!r} is absent".format(name),
                    expected=name,
                )
            )

    additional = schema.get("additionalProperties", True)
    if additional is False:
        for name in sorted(set(value) - set(properties)):
            found.append(
                Violation(
                    pointer="{}.{}".format(pointer, name),
                    code="ADDITIONAL_PROPERTY",
                    message="Property {!r} is not part of this contract".format(name),
                    actual=name,
                )
            )

    for name, sub_schema in properties.items():
        if name in value:
            found.extend(
                validate(
                    sub_schema,
                    value[name],
                    pointer="{}.{}".format(pointer, name),
                    registry=registry,
                )
            )

    if isinstance(additional, dict):
        for name in sorted(set(value) - set(properties)):
            found.extend(
                validate(
                    additional,
                    value[name],
                    pointer="{}.{}".format(pointer, name),
                    registry=registry,
                )
            )

    return found


def _resolve_ref(
    ref: str, registry: Optional["ContractRegistry"]
) -> Optional[Mapping[str, Any]]:
    if registry is None or not ref.startswith(REF_PREFIX):
        return None
    target = ref[len(REF_PREFIX) :]
    name, _, version = target.partition("@")
    try:
        contract = registry.get(name, version or None)
    except ContractUnknown:
        return None
    return contract.schema


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Contract:
    """A named, versioned, content-hashed schema."""

    name: str
    version: str
    schema: Mapping[str, Any]
    description: str = ""
    owner: str = ""

    @property
    def ref(self) -> str:
        return "{}{}@{}".format(REF_PREFIX, self.name, self.version)

    @property
    def fingerprint(self) -> str:
        """Content hash of the schema. Identical schemas share a fingerprint."""
        return util.fingerprint(self.schema)

    def validate(
        self, value: Any, *, registry: Optional["ContractRegistry"] = None
    ) -> List[Violation]:
        return validate(self.schema, value, registry=registry)

    def enforce(
        self,
        value: Any,
        *,
        role: str = "payload",
        registry: Optional["ContractRegistry"] = None,
        site: Optional[str] = None,
    ) -> Any:
        """Validate or raise. Returns ``value`` unchanged so it can be chained."""
        violations = self.validate(value, registry=registry)
        if violations:
            raise ContractViolation(
                "{} violates contract {}@{} ({} violation{})".format(
                    role,
                    self.name,
                    self.version,
                    len(violations),
                    "" if len(violations) == 1 else "s",
                ),
                contract="{}@{}".format(self.name, self.version),
                violations=[item.as_dict() for item in violations],
                remediation=(
                    "Fix the payload at: "
                    + "; ".join(item.render() for item in violations[:5])
                ),
                site=site,
            )
        return value

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schemaVersion": CONTRACT_SCHEMA_VERSION,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "owner": self.owner,
            "fingerprint": self.fingerprint,
            "schema": dict(self.schema),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Contract":
        return cls(
            name=data["name"],
            version=data["version"],
            schema=data["schema"],
            description=data.get("description", ""),
            owner=data.get("owner", ""),
        )


# ---------------------------------------------------------------------------
# Compatibility analysis
# ---------------------------------------------------------------------------

COMPATIBLE = "COMPATIBLE"
BREAKING = "BREAKING"
IDENTICAL = "IDENTICAL"


@dataclass
class CompatibilityReport:
    """Whether a new contract version can be shipped without breaking callers."""

    verdict: str
    breaking: List[Dict[str, Any]] = field(default_factory=list)
    additive: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def is_safe(self) -> bool:
        return self.verdict in (COMPATIBLE, IDENTICAL)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "breaking": self.breaking,
            "additive": self.additive,
        }


def compatibility(
    old: Mapping[str, Any],
    new: Mapping[str, Any],
    *,
    pointer: str = "$",
) -> CompatibilityReport:
    """Compare two schemas from the perspective of an existing consumer.

    Breaking, because deployed callers stop working:
      * a new required property;
      * a removed property;
      * a narrowed type or enum;
      * newly forbidding additional properties.

    Additive, because deployed callers keep working:
      * a new optional property;
      * a widened enum or type.
    """
    breaking: List[Dict[str, Any]] = []
    additive: List[Dict[str, Any]] = []

    if util.canonical_json(old) == util.canonical_json(new):
        return CompatibilityReport(verdict=IDENTICAL)

    old_types = set(_as_type_list(old.get("type")))
    new_types = set(_as_type_list(new.get("type")))
    if old_types and new_types:
        removed = old_types - new_types
        if removed:
            breaking.append(
                {"pointer": pointer, "change": "TYPE_NARROWED", "removed": sorted(removed)}
            )
        gained = new_types - old_types
        if gained:
            additive.append(
                {"pointer": pointer, "change": "TYPE_WIDENED", "added": sorted(gained)}
            )

    if "enum" in old and "enum" in new:
        removed_values = [item for item in old["enum"] if item not in new["enum"]]
        if removed_values:
            breaking.append(
                {"pointer": pointer, "change": "ENUM_NARROWED", "removed": removed_values}
            )
        added_values = [item for item in new["enum"] if item not in old["enum"]]
        if added_values:
            additive.append(
                {"pointer": pointer, "change": "ENUM_WIDENED", "added": added_values}
            )
    elif "enum" in new and "enum" not in old:
        breaking.append({"pointer": pointer, "change": "ENUM_INTRODUCED"})

    old_required = set(old.get("required", []) or [])
    new_required = set(new.get("required", []) or [])
    for name in sorted(new_required - old_required):
        breaking.append(
            {"pointer": "{}.{}".format(pointer, name), "change": "REQUIRED_ADDED"}
        )
    for name in sorted(old_required - new_required):
        additive.append(
            {"pointer": "{}.{}".format(pointer, name), "change": "REQUIRED_RELAXED"}
        )

    old_props: Mapping[str, Any] = old.get("properties", {}) or {}
    new_props: Mapping[str, Any] = new.get("properties", {}) or {}

    for name in sorted(set(old_props) - set(new_props)):
        breaking.append(
            {"pointer": "{}.{}".format(pointer, name), "change": "PROPERTY_REMOVED"}
        )
    for name in sorted(set(new_props) - set(old_props)):
        additive.append(
            {"pointer": "{}.{}".format(pointer, name), "change": "PROPERTY_ADDED"}
        )

    for name in sorted(set(old_props) & set(new_props)):
        nested = compatibility(
            old_props[name], new_props[name], pointer="{}.{}".format(pointer, name)
        )
        breaking.extend(nested.breaking)
        additive.extend(nested.additive)

    old_items = old.get("items")
    new_items = new.get("items")
    if isinstance(old_items, dict) and isinstance(new_items, dict):
        nested = compatibility(old_items, new_items, pointer="{}[]".format(pointer))
        breaking.extend(nested.breaking)
        additive.extend(nested.additive)

    if old.get("additionalProperties", True) is not False and (
        new.get("additionalProperties", True) is False
    ):
        breaking.append({"pointer": pointer, "change": "ADDITIONAL_PROPERTIES_CLOSED"})

    if old.get("nullable") and not new.get("nullable"):
        breaking.append({"pointer": pointer, "change": "NULLABLE_REMOVED"})

    verdict = BREAKING if breaking else COMPATIBLE
    return CompatibilityReport(verdict=verdict, breaking=breaking, additive=additive)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ContractRegistry:
    """The catalogue of every boundary in a product.

    Registering a second version of a name runs a compatibility check. By
    default a breaking change is refused unless the caller says it is intended,
    which turns "we broke the panel again" into a decision someone made on
    purpose and can point at.
    """

    def __init__(self) -> None:
        self._contracts: Dict[Tuple[str, str], Contract] = {}
        self._order: Dict[str, List[str]] = {}

    # -- registration --------------------------------------------------

    def register(
        self, contract: Contract, *, allow_breaking: bool = False
    ) -> Contract:
        key = (contract.name, contract.version)
        existing = self._contracts.get(key)
        if existing is not None:
            if existing.fingerprint != contract.fingerprint:
                raise ContractIncompatible(
                    "Contract {}@{} is already registered with different content".format(
                        contract.name, contract.version
                    ),
                    detail={
                        "registered_fingerprint": existing.fingerprint,
                        "incoming_fingerprint": contract.fingerprint,
                    },
                    remediation=(
                        "Publish the change as a new version instead of mutating "
                        "an existing one. Versions are immutable by design."
                    ),
                )
            return existing

        previous_versions = self._order.get(contract.name, [])
        if previous_versions and not allow_breaking:
            previous = self._contracts[(contract.name, previous_versions[-1])]
            report = compatibility(previous.schema, contract.schema)
            if not report.is_safe:
                raise ContractIncompatible(
                    "Contract {} {} -> {} breaks existing consumers".format(
                        contract.name, previous.version, contract.version
                    ),
                    detail={"report": report.as_dict()},
                    remediation=(
                        "Either keep the old shape valid, or register with "
                        "allow_breaking=True and plan the consumer migration."
                    ),
                )

        self._contracts[key] = contract
        self._order.setdefault(contract.name, []).append(contract.version)
        return contract

    def define(
        self,
        name: str,
        version: str,
        schema: Mapping[str, Any],
        *,
        description: str = "",
        owner: str = "",
        allow_breaking: bool = False,
    ) -> Contract:
        return self.register(
            Contract(
                name=name,
                version=version,
                schema=schema,
                description=description,
                owner=owner,
            ),
            allow_breaking=allow_breaking,
        )

    # -- lookup --------------------------------------------------------

    def get(self, name: str, version: Optional[str] = None) -> Contract:
        if version is None:
            versions = self._order.get(name)
            if not versions:
                raise ContractUnknown(
                    "No contract registered under {!r}".format(name),
                    detail={"known": sorted(self._order)},
                    remediation="Register the contract before referencing it.",
                )
            version = versions[-1]

        contract = self._contracts.get((name, version))
        if contract is None:
            raise ContractUnknown(
                "Contract {}@{} is not registered".format(name, version),
                detail={"known_versions": self._order.get(name, [])},
                remediation="Register this version or reference an existing one.",
            )
        return contract

    def has(self, name: str, version: Optional[str] = None) -> bool:
        try:
            self.get(name, version)
        except ContractUnknown:
            return False
        return True

    def names(self) -> List[str]:
        return sorted(self._order)

    def versions(self, name: str) -> List[str]:
        return list(self._order.get(name, []))

    def all(self) -> List[Contract]:
        return [self._contracts[key] for key in sorted(self._contracts)]

    def __len__(self) -> int:
        return len(self._contracts)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._order

    # -- convenience ---------------------------------------------------

    def enforce(
        self,
        name: str,
        value: Any,
        *,
        version: Optional[str] = None,
        role: str = "payload",
        site: Optional[str] = None,
    ) -> Any:
        return self.get(name, version).enforce(
            value, role=role, registry=self, site=site
        )

    # -- persistence ---------------------------------------------------

    def export(self) -> Dict[str, Any]:
        return {
            "schemaVersion": CONTRACT_SCHEMA_VERSION,
            "contracts": [contract.as_dict() for contract in self.all()],
        }

    def load(self, data: Mapping[str, Any], *, allow_breaking: bool = True) -> int:
        """Load an exported catalogue.

        Defaults to ``allow_breaking=True`` because a stored catalogue is a
        record of history, not a new proposal -- refusing to load it would make
        past decisions unreadable.
        """
        count = 0
        for entry in data.get("contracts", []):
            self.register(Contract.from_dict(entry), allow_breaking=allow_breaking)
            count += 1
        return count

    def save(self, path: Any) -> None:
        util.write_json(path, self.export())

    @classmethod
    def from_file(cls, path: Any) -> "ContractRegistry":
        registry = cls()
        registry.load(util.read_json(path))
        return registry
