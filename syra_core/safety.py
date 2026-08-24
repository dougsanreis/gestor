"""Safety contracts: capability authorization that is closed by default.

The rule this module enforces is the one the SYRA gates already run on: an
operation may only do what it was explicitly authorized to do, and a nested
operation can never be granted more than its parent. Adding a capability is
always an explicit, auditable act; losing one is free.

``SafetyContract`` is frozen and ``narrow()`` is the only transformation, so
there is no code path -- accidental or otherwise -- that widens authority at
runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import Any, Dict, Iterable, Mapping, Tuple

from .errors import SafetyDenied

#: Every capability the core knows how to gate. The names are deliberately
#: fine-grained: ``git_read`` is not ``git_mutation``, and writing an evidence
#: file outside the workspace is not ``source_mutation``. Coarse capabilities
#: force operators to over-grant, and over-granting is how audit tooling starts
#: mutating the thing it audits.
CAPABILITIES: Tuple[str, ...] = (
    "network",
    "git_read",
    "git_mutation",
    "filesystem_read",
    "filesystem_write",
    "source_mutation",
    "runtime_execution",
    "database_query",
    "build_execution",
    "test_execution",
    "package_install",
    "deploy",
    "automatic_retry",
)

#: Rendered in the same order the existing SYRA gate banners use.
_BANNER_ORDER: Tuple[str, ...] = (
    "network",
    "runtime_execution",
    "database_query",
    "build_execution",
    "test_execution",
    "package_install",
    "source_mutation",
    "git_mutation",
    "deploy",
    "automatic_retry",
)


@dataclass(frozen=True)
class SafetyContract:
    """An immutable grant of capabilities for one unit of work."""

    purpose: str = "UNSPECIFIED"

    network: bool = False
    git_read: bool = False
    git_mutation: bool = False
    filesystem_read: bool = True
    filesystem_write: bool = False
    source_mutation: bool = False
    runtime_execution: bool = False
    database_query: bool = False
    build_execution: bool = False
    test_execution: bool = False
    package_install: bool = False
    deploy: bool = False
    automatic_retry: bool = False

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    @classmethod
    def sealed(cls, purpose: str = "SEALED") -> "SafetyContract":
        """Nothing is permitted. Useful as a parent for dry-run planning."""
        return cls(purpose=purpose, filesystem_read=False)

    @classmethod
    def static_analysis(cls, purpose: str = "STATIC_ANALYSIS") -> "SafetyContract":
        """Read sources, read git, write evidence. Mutate nothing.

        This is the contract the discovery and decision gates run under.
        ``git_read`` covers read-only plumbing (``rev-parse``, ``status``);
        ``filesystem_write`` covers the evidence directory only, which lives
        outside the scanned workspace, so ``source_mutation`` stays denied.
        """
        return cls(
            purpose=purpose,
            filesystem_read=True,
            filesystem_write=True,
            git_read=True,
        )

    @classmethod
    def product_runtime(
        cls, purpose: str = "PRODUCT_RUNTIME", *, network: bool = False
    ) -> "SafetyContract":
        """A materialized product serving traffic through the gateway."""
        return cls(
            purpose=purpose,
            filesystem_read=True,
            filesystem_write=True,
            runtime_execution=True,
            network=network,
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "SafetyContract":
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise SafetyDenied(
                "Unknown safety capability requested",
                detail={"unknown": unknown, "known": sorted(known)},
                remediation="Remove the unknown keys or add them to CAPABILITIES.",
            )
        payload: Dict[str, Any] = {}
        for key, value in data.items():
            payload[key] = value if key == "purpose" else bool(value)
        return cls(**payload)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def allows(self, capability: str) -> bool:
        if capability not in CAPABILITIES:
            raise SafetyDenied(
                "Unknown capability queried: {}".format(capability),
                detail={"capability": capability, "known": list(CAPABILITIES)},
                remediation="Use a capability name from SafetyContract.CAPABILITIES.",
            )
        return bool(getattr(self, capability))

    def granted(self) -> Tuple[str, ...]:
        return tuple(name for name in CAPABILITIES if getattr(self, name))

    def denied(self) -> Tuple[str, ...]:
        return tuple(name for name in CAPABILITIES if not getattr(self, name))

    def require(self, *capabilities: str, site: str = "unknown") -> None:
        """Assert every capability is granted, or refuse the operation.

        This is the single choke point. Code that needs authority calls
        ``require`` before doing the work, never after.
        """
        missing = [name for name in capabilities if not self.allows(name)]
        if missing:
            raise SafetyDenied(
                "Operation requires capabilities the safety contract denies",
                detail={
                    "site": site,
                    "purpose": self.purpose,
                    "required": list(capabilities),
                    "missing": missing,
                    "granted": list(self.granted()),
                },
                remediation=(
                    "Grant {} explicitly on the SafetyContract for this run, "
                    "or use an operation that does not need it.".format(
                        ", ".join(missing)
                    )
                ),
                site=site,
            )

    # ------------------------------------------------------------------
    # Transformations
    # ------------------------------------------------------------------

    def narrow(self, **overrides: Any) -> "SafetyContract":
        """Return a contract with capabilities removed.

        Attempting to grant a capability the parent does not hold raises. There
        is intentionally no ``widen``: authority only ever flows downward.
        """
        purpose = overrides.pop("purpose", self.purpose)
        escalated = []
        payload: Dict[str, Any] = {}
        for key, value in overrides.items():
            if key not in CAPABILITIES:
                raise SafetyDenied(
                    "Unknown capability in narrow(): {}".format(key),
                    detail={"capability": key},
                    remediation="Use a capability name from CAPABILITIES.",
                )
            wanted = bool(value)
            if wanted and not getattr(self, key):
                escalated.append(key)
            payload[key] = wanted and getattr(self, key)

        if escalated:
            raise SafetyDenied(
                "narrow() cannot grant capabilities the parent contract lacks",
                detail={"attempted_escalation": escalated, "purpose": self.purpose},
                remediation=(
                    "Build the wider contract at the call site that owns the "
                    "authority; a child may only drop capabilities."
                ),
            )
        return replace(self, purpose=purpose, **payload)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"purpose": self.purpose}
        for name in CAPABILITIES:
            payload[name] = bool(getattr(self, name))
        return payload

    def invariants(self) -> Dict[str, bool]:
        """The ``invariants`` block embedded in every evidence manifest."""
        return {name: bool(getattr(self, name)) for name in CAPABILITIES}

    def render(self) -> str:
        """The human-readable banner, matching the existing gate output."""
        lines = ["===== SAFETY CONTRACT ====="]
        for name in _BANNER_ORDER:
            state = "ALLOWED" if getattr(self, name) else "ZERO"
            lines.append("{}={}".format(name.upper(), state))
        lines.append("PURPOSE={}".format(self.purpose))
        return "\n".join(lines)


#: Convenience alias so callers can reference the tuple from the class module.
SafetyContract.CAPABILITIES = CAPABILITIES  # type: ignore[attr-defined]
