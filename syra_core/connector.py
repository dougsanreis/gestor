"""Connectors -- every integration declares what it is before it is trusted.

An integration that can be added without declaring anything is an integration
that breaks the product on its first bad day. Here, a connector cannot be
registered without stating:

* the contracts its request and response must satisfy;
* the safety capabilities it needs (so a network call cannot happen inside a
  gate that declared ``network=ZERO``);
* its timeout and breaker policy;
* whether the product can serve without it.

Two implementations ship with the core. ``CallableConnector`` wraps any Python
callable -- an agent, a squad step, an internal service -- and needs no
authority beyond running code. ``HttpConnector`` speaks to Railway, Vercel,
Cloudflare, GitHub, or any HTTP API, and requires the ``network`` capability, so
it is structurally impossible to invoke from a read-only analysis gate.
"""

from __future__ import annotations

import dataclasses
import json
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

from . import health as health_mod
from . import util
from .breaker import BreakerPolicy
from .errors import ConnectorFailure
from .health import HealthReport

#: What a connector talks to. Drives defaults and reporting, not behaviour.
KINDS = (
    "agent",
    "agent_squad",
    "internal_service",
    "http_api",
    "database",
    "queue",
    "storage",
    "deployment",
    "vcs",
    "custom",
)


@dataclass(frozen=True)
class ConnectorSpec:
    """The declaration that makes an integration reviewable."""

    name: str
    kind: str = "custom"
    version: str = "1.0.0"
    description: str = ""

    request_contract: Optional[str] = None
    """Contract name validated on the way in. ``None`` means unvalidated."""

    response_contract: Optional[str] = None
    """Contract name validated on the way out."""

    required_capabilities: Tuple[str, ...] = ()
    """Safety capabilities the gateway must hold to invoke this connector."""

    timeout_seconds: Optional[float] = 10.0
    breaker_policy: Optional[BreakerPolicy] = None

    critical: bool = True
    """False means the product can serve in a degraded state without it."""

    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "version": self.version,
            "description": self.description,
            "requestContract": self.request_contract,
            "responseContract": self.response_contract,
            "requiredCapabilities": list(self.required_capabilities),
            "timeoutSeconds": self.timeout_seconds,
            "critical": self.critical,
            "breakerPolicy": (
                self.breaker_policy.as_dict() if self.breaker_policy else None
            ),
            "metadata": dict(self.metadata),
        }


class Connector(ABC):
    """Base class for anything the product talks to."""

    #: True when the implementation enforces ``timeout_seconds`` itself. When
    #: False the gateway wraps the call in a bounded worker instead.
    native_timeout = False

    def __init__(self, spec: ConnectorSpec) -> None:
        self.spec = spec

    @property
    def name(self) -> str:
        return self.spec.name

    @abstractmethod
    def call(self, payload: Any, *, context: Mapping[str, Any]) -> Any:
        """Perform the integration call. Raise on failure; never return an error."""

    def probe(self) -> HealthReport:
        """Cheap liveness check. Override for a real readiness signal."""
        return health_mod.healthy(
            self.spec.name, detail="no probe implemented", critical=self.spec.critical
        )

    def close(self) -> None:
        """Release resources. Safe to call more than once."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<{} {}>".format(type(self).__name__, self.spec.name)


class CallableConnector(Connector):
    """Wraps a plain Python callable.

    This is how an agent, a squad step, or an in-process service joins the
    gateway and inherits contracts, breakers, tracing, and failure memory
    without changing its own code.
    """

    def __init__(
        self,
        spec: ConnectorSpec,
        func: Callable[..., Any],
        *,
        probe: Optional[Callable[[], HealthReport]] = None,
        pass_context: bool = False,
    ) -> None:
        super().__init__(spec)
        self._func = func
        self._probe = probe
        self._pass_context = pass_context

    def call(self, payload: Any, *, context: Mapping[str, Any]) -> Any:
        if self._pass_context:
            return self._func(payload, context=context)
        return self._func(payload)

    def probe(self) -> HealthReport:
        if self._probe is None:
            return health_mod.healthy(
                self.spec.name, detail="callable registered", critical=self.spec.critical
            )
        return self._probe()


class HttpConnector(Connector):
    """JSON-over-HTTP connector built on ``urllib`` -- no third-party client.

    Requires the ``network`` capability. The gateway checks that before this
    class is ever reached, which is what keeps a static-analysis gate from
    making a network call by accident.
    """

    native_timeout = True

    def __init__(
        self,
        spec: ConnectorSpec,
        *,
        base_url: str,
        method: str = "POST",
        path: str = "",
        headers: Optional[Mapping[str, str]] = None,
        health_path: Optional[str] = None,
        opener: Optional[Any] = None,
    ) -> None:
        # An HTTP connector always needs network authority. Declaring anything
        # else would let it be registered inside a gate that believes it is
        # offline, so the capability is added here rather than trusted.
        if "network" not in spec.required_capabilities:
            spec = dataclasses.replace(
                spec,
                required_capabilities=tuple(spec.required_capabilities) + ("network",),
            )
        super().__init__(spec)
        self.base_url = base_url.rstrip("/")
        self.method = method.upper()
        self.path = path
        self.headers = dict(headers or {})
        self.health_path = health_path
        self._opener = opener or urllib.request.build_opener()

    # -- request -------------------------------------------------------

    def _request(
        self,
        *,
        method: str,
        url: str,
        payload: Any,
        timeout: Optional[float],
    ) -> Any:
        body: Optional[bytes] = None
        headers = {"Accept": "application/json", **self.headers}

        if payload is not None and method not in ("GET", "HEAD"):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")

        request = urllib.request.Request(
            url, data=body, headers=headers, method=method
        )

        try:
            with self._opener.open(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                status = getattr(response, "status", 200)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise ConnectorFailure(
                "{} returned HTTP {}".format(self.spec.name, exc.code),
                detail={
                    "connector": self.spec.name,
                    "status": exc.code,
                    "url": url,
                    "body": detail,
                },
                remediation=(
                    "Check the endpoint contract and credentials. A 4xx is a "
                    "request defect; a 5xx is the dependency's."
                ),
                site="connector.{}".format(self.spec.name),
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ConnectorFailure(
                "{} is unreachable: {}".format(self.spec.name, exc),
                detail={"connector": self.spec.name, "url": url},
                remediation="Verify the host, DNS, and that the service is deployed.",
                site="connector.{}".format(self.spec.name),
            ) from exc

        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConnectorFailure(
                "{} returned a non-JSON body (HTTP {})".format(self.spec.name, status),
                detail={
                    "connector": self.spec.name,
                    "url": url,
                    "body": raw[:300],
                },
                remediation=(
                    "The endpoint is not honouring its contract. Usually an HTML "
                    "error page from a proxy or a failed deploy."
                ),
                site="connector.{}".format(self.spec.name),
            ) from exc

    def call(self, payload: Any, *, context: Mapping[str, Any]) -> Any:
        url = self.base_url + (self.path or "")
        return self._request(
            method=self.method,
            url=url,
            payload=payload,
            timeout=self.spec.timeout_seconds,
        )

    def probe(self) -> HealthReport:
        if not self.health_path:
            return health_mod.HealthReport(
                component=self.spec.name,
                status=health_mod.UNKNOWN,
                detail="no health_path configured",
                critical=self.spec.critical,
            )

        started = time.monotonic()
        url = self.base_url + self.health_path
        try:
            self._request(method="GET", url=url, payload=None, timeout=3.0)
        except ConnectorFailure as exc:
            return health_mod.unhealthy(
                self.spec.name,
                detail=util.truncate(exc.message, 160),
                latency_ms=round((time.monotonic() - started) * 1000.0, 3),
                critical=self.spec.critical,
            )
        return health_mod.healthy(
            self.spec.name,
            detail=url,
            latency_ms=round((time.monotonic() - started) * 1000.0, 3),
            critical=self.spec.critical,
        )


def http_connector(
    name: str,
    base_url: str,
    *,
    path: str = "",
    method: str = "POST",
    kind: str = "http_api",
    request_contract: Optional[str] = None,
    response_contract: Optional[str] = None,
    headers: Optional[Mapping[str, str]] = None,
    health_path: Optional[str] = None,
    timeout_seconds: float = 10.0,
    critical: bool = True,
    breaker_policy: Optional[BreakerPolicy] = None,
    opener: Optional[Any] = None,
) -> HttpConnector:
    """Build an ``HttpConnector`` with ``network`` already declared.

    Use this rather than constructing the spec by hand: it guarantees the
    capability declaration matches what the connector actually does.
    """
    spec = ConnectorSpec(
        name=name,
        kind=kind,
        description="HTTP {} {}{}".format(method.upper(), base_url, path),
        request_contract=request_contract,
        response_contract=response_contract,
        required_capabilities=("network",),
        timeout_seconds=timeout_seconds,
        breaker_policy=breaker_policy,
        critical=critical,
    )
    return HttpConnector(
        spec,
        base_url=base_url,
        method=method,
        path=path,
        headers=headers,
        health_path=health_path,
        opener=opener,
    )


def agent_connector(
    name: str,
    func: Callable[..., Any],
    *,
    request_contract: Optional[str] = None,
    response_contract: Optional[str] = None,
    timeout_seconds: Optional[float] = 30.0,
    critical: bool = True,
    squad: bool = False,
    pass_context: bool = False,
    probe: Optional[Callable[[], HealthReport]] = None,
    breaker_policy: Optional[BreakerPolicy] = None,
) -> CallableConnector:
    """Register an agent (or a squad step) as a governed connector."""
    spec = ConnectorSpec(
        name=name,
        kind="agent_squad" if squad else "agent",
        description="Agent connector: {}".format(name),
        request_contract=request_contract,
        response_contract=response_contract,
        required_capabilities=("runtime_execution",),
        timeout_seconds=timeout_seconds,
        breaker_policy=breaker_policy,
        critical=critical,
    )
    return CallableConnector(spec, func, probe=probe, pass_context=pass_context)


def service_connector(
    name: str,
    func: Callable[..., Any],
    *,
    request_contract: Optional[str] = None,
    response_contract: Optional[str] = None,
    timeout_seconds: Optional[float] = 10.0,
    critical: bool = True,
    pass_context: bool = False,
    probe: Optional[Callable[[], HealthReport]] = None,
) -> CallableConnector:
    """Register an in-process service as a governed connector."""
    spec = ConnectorSpec(
        name=name,
        kind="internal_service",
        description="Internal service: {}".format(name),
        request_contract=request_contract,
        response_contract=response_contract,
        required_capabilities=("runtime_execution",),
        timeout_seconds=timeout_seconds,
        critical=critical,
    )
    return CallableConnector(spec, func, probe=probe, pass_context=pass_context)
