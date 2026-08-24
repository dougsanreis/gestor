"""Canonical error taxonomy.

Every failure the core raises carries a stable machine code. Stable codes are
what make failure fingerprinting possible, and fingerprinting is what stops the
same defect from being rediscovered a third time: a human-readable message may
change between releases, a code may not.

Each error also carries ``remediation`` -- the next operator action. An error
that does not tell you what to do next is an error that gets worked around
instead of fixed, and worked-around errors are how panels rot.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class SyraError(Exception):
    """Base class for every deliberate failure raised by the core."""

    code = "SYRA-E-INTERNAL"
    """Stable machine identifier. Never reuse a retired code for a new meaning."""

    def __init__(
        self,
        message: str,
        *,
        detail: Optional[Dict[str, Any]] = None,
        remediation: Optional[str] = None,
        site: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.detail: Dict[str, Any] = dict(detail or {})
        self.remediation = remediation
        self.site = site

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.site:
            payload["site"] = self.site
        if self.detail:
            payload["detail"] = self.detail
        if self.remediation:
            payload["remediation"] = self.remediation
        return payload

    def __str__(self) -> str:  # pragma: no cover - formatting only
        if self.remediation:
            return "[{}] {} :: remediation: {}".format(
                self.code, self.message, self.remediation
            )
        return "[{}] {}".format(self.code, self.message)


# ---------------------------------------------------------------------------
# Safety / authorization
# ---------------------------------------------------------------------------


class SafetyDenied(SyraError):
    """An operation asked for a capability its safety contract does not grant."""

    code = "SYRA-E-SAFETY-DENIED"


class PreflightFailed(SyraError):
    """Tooling failed validation and therefore was never executed."""

    code = "SYRA-E-PREFLIGHT-FAILED"


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------


class ContractViolation(SyraError):
    """A payload did not satisfy the contract it was checked against."""

    code = "SYRA-E-CONTRACT-VIOLATION"

    def __init__(
        self,
        message: str,
        *,
        contract: str,
        violations: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> None:
        detail = dict(kwargs.pop("detail", None) or {})
        detail["contract"] = contract
        detail["violations"] = violations or []
        super().__init__(message, detail=detail, **kwargs)
        self.contract = contract
        self.violations = violations or []


class ContractUnknown(SyraError):
    """A contract was requested by name/version and is not registered."""

    code = "SYRA-E-CONTRACT-UNKNOWN"


class ContractIncompatible(SyraError):
    """A new contract version breaks existing consumers."""

    code = "SYRA-E-CONTRACT-INCOMPATIBLE"


# ---------------------------------------------------------------------------
# Integration runtime
# ---------------------------------------------------------------------------


class ConnectorUnknown(SyraError):
    code = "SYRA-E-CONNECTOR-UNKNOWN"


class ConnectorFailure(SyraError):
    """The downstream integration returned an error or was unreachable."""

    code = "SYRA-E-CONNECTOR-FAILURE"


class BreakerOpen(SyraError):
    """The circuit breaker refused the call because the dependency is failing."""

    code = "SYRA-E-BREAKER-OPEN"


class OperationTimeout(SyraError):
    code = "SYRA-E-TIMEOUT"


class RepeatedFailure(SyraError):
    """A known-unresolved failure is about to be repeated. Blocked on purpose."""

    code = "SYRA-E-REPEATED-FAILURE"


# ---------------------------------------------------------------------------
# Evidence / governance
# ---------------------------------------------------------------------------


class EvidenceError(SyraError):
    code = "SYRA-E-EVIDENCE"


class StaleEvidence(SyraError):
    """Sources changed underneath a scan; the result is not trustworthy."""

    code = "SYRA-E-STALE-EVIDENCE"


class AuthorityUnresolved(SyraError):
    code = "SYRA-E-AUTHORITY-UNRESOLVED"


# ---------------------------------------------------------------------------
# Product lifecycle
# ---------------------------------------------------------------------------


class ManifestInvalid(SyraError):
    code = "SYRA-E-MANIFEST-INVALID"


class ProductExists(SyraError):
    code = "SYRA-E-PRODUCT-EXISTS"


class ProductUnknown(SyraError):
    code = "SYRA-E-PRODUCT-UNKNOWN"


ALL_ERRORS = (
    SyraError,
    SafetyDenied,
    PreflightFailed,
    ContractViolation,
    ContractUnknown,
    ContractIncompatible,
    ConnectorUnknown,
    ConnectorFailure,
    BreakerOpen,
    OperationTimeout,
    RepeatedFailure,
    EvidenceError,
    StaleEvidence,
    AuthorityUnresolved,
    ManifestInvalid,
    ProductExists,
    ProductUnknown,
)

ERROR_CODES = tuple(sorted({cls.code for cls in ALL_ERRORS}))
