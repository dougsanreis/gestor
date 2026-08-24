"""The integration gateway -- one governed path for every external call.

Every connector invocation passes through the same pipeline, in this order:

    1. safety      does this run hold the capabilities the connector needs?
    2. memory      is this a known-open defect we already know will fail?
    3. contract    does the request satisfy its declared shape?
    4. breaker     is the dependency currently healthy enough to call?
    5. timeout     bound the call so one hung dependency cannot hang the product
    6. call        the actual integration
    7. contract    does the response satisfy its declared shape?
    8. record      trace the span; remember the failure if there was one

The order is deliberate. Cheap, local checks run before expensive remote ones,
so a misconfigured run fails in microseconds instead of after a 10-second
timeout. Contract validation happens on both sides because a dependency that
starts returning a different shape is exactly how a panel breaks without
anything appearing in its own logs.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from . import health as health_mod
from . import util
from .breaker import BreakerRegistry
from .connector import Connector
from .contracts import ContractRegistry
from .errors import (
    ConnectorFailure,
    ConnectorUnknown,
    OperationTimeout,
    SyraError,
)
from .failure_memory import FailureMemory
from .health import HealthRegistry
from .safety import SafetyContract
from .telemetry import Telemetry, null_telemetry


@dataclass
class GatewayResult:
    """Outcome of one governed invocation."""

    connector: str
    ok: bool
    value: Any = None
    error: Optional[Dict[str, Any]] = None
    duration_ms: float = 0.0
    trace_id: str = ""
    dry_run: bool = False
    stage: str = "complete"

    def unwrap(self) -> Any:
        """Return the value, or re-raise the failure as a ``SyraError``."""
        if self.ok:
            return self.value
        payload = self.error or {}
        raise SyraError(
            payload.get("message", "Gateway call failed"),
            detail={"connector": self.connector, **payload.get("detail", {})},
            remediation=payload.get("remediation"),
            site="gateway.{}".format(self.connector),
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "connector": self.connector,
            "ok": self.ok,
            "stage": self.stage,
            "durationMs": self.duration_ms,
            "traceId": self.trace_id,
            "dryRun": self.dry_run,
            "error": self.error,
        }


class IntegrationGateway:
    """Registry of connectors plus the pipeline that governs calling them."""

    def __init__(
        self,
        *,
        safety: SafetyContract,
        contracts: Optional[ContractRegistry] = None,
        telemetry: Optional[Telemetry] = None,
        failures: Optional[FailureMemory] = None,
        health: Optional[HealthRegistry] = None,
        breakers: Optional[BreakerRegistry] = None,
        max_workers: int = 8,
    ) -> None:
        self.safety = safety
        self.contracts = contracts or ContractRegistry()
        self.telemetry = telemetry or null_telemetry()
        self.failures = failures
        self.health = health or HealthRegistry()
        self.breakers = breakers or BreakerRegistry()

        self._connectors: Dict[str, Connector] = {}
        self._lock = threading.RLock()
        self._max_workers = max_workers
        self._executor: Optional[ThreadPoolExecutor] = None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, connector: Connector, *, replace: bool = False) -> Connector:
        """Add a connector and validate its declaration against the registry.

        Registration fails loudly when a connector names a contract that does
        not exist. Discovering that at call time -- in production, on a panel --
        is the expensive version of the same error.
        """
        spec = connector.spec

        with self._lock:
            if spec.name in self._connectors and not replace:
                raise SyraError(
                    "Connector {!r} is already registered".format(spec.name),
                    detail={"connector": spec.name},
                    remediation="Use replace=True if the override is intended.",
                )

        for role, contract_name in (
            ("request", spec.request_contract),
            ("response", spec.response_contract),
        ):
            if contract_name and not self.contracts.has(contract_name):
                raise ConnectorUnknown(
                    "Connector {!r} declares an unregistered {} contract "
                    "{!r}".format(spec.name, role, contract_name),
                    detail={
                        "connector": spec.name,
                        "contract": contract_name,
                        "known": self.contracts.names(),
                    },
                    remediation=(
                        "Register the contract before the connector. A connector "
                        "cannot be governed by a contract that does not exist."
                    ),
                )

        with self._lock:
            self._connectors[spec.name] = connector

        if spec.breaker_policy is not None:
            self.breakers.get(spec.name, spec.breaker_policy)

        self.health.register(
            spec.name, connector.probe, critical=spec.critical
        )
        self.telemetry.event(
            "connector.registered",
            connector=spec.name,
            kind=spec.kind,
            critical=spec.critical,
        )
        return connector

    def unregister(self, name: str) -> None:
        with self._lock:
            connector = self._connectors.pop(name, None)
        self.health.unregister(name)
        if connector is not None:
            connector.close()

    def get(self, name: str) -> Connector:
        with self._lock:
            connector = self._connectors.get(name)
        if connector is None:
            raise ConnectorUnknown(
                "No connector registered under {!r}".format(name),
                detail={"known": sorted(self._connectors)},
                remediation="Register the connector, or correct the name.",
            )
        return connector

    def names(self) -> List[str]:
        with self._lock:
            return sorted(self._connectors)

    def specs(self) -> List[Dict[str, Any]]:
        with self._lock:
            connectors = list(self._connectors.values())
        return [connector.spec.as_dict() for connector in connectors]

    # ------------------------------------------------------------------
    # Invocation
    # ------------------------------------------------------------------

    def invoke(
        self,
        name: str,
        payload: Any = None,
        *,
        dry_run: bool = False,
        context: Optional[Mapping[str, Any]] = None,
        raise_on_error: bool = False,
    ) -> GatewayResult:
        """Run the full pipeline for one connector call.

        Returns a ``GatewayResult`` rather than raising, so a caller handling
        several integrations can degrade per-dependency instead of aborting.
        Pass ``raise_on_error=True`` (or call ``.unwrap()``) when the failure
        should propagate.
        """
        connector = self.get(name)
        spec = connector.spec
        call_context: Dict[str, Any] = dict(context or {})
        stage = "safety"

        with self.telemetry.span(
            "gateway.invoke",
            connector=name,
            kind=spec.kind,
            dry_run=dry_run,
        ) as span:
            trace_id = span.trace_id
            started = self._now()
            try:
                # 1. Authority. Cheapest possible check, so it goes first.
                self.safety.require(
                    *spec.required_capabilities, site="gateway.{}".format(name)
                )

                # 2. Known-open defect at this site.
                stage = "failure_memory"
                if self.failures is not None:
                    known = self.failures.guard("gateway.{}".format(name))
                    if known is not None:
                        span.set("known_open_defect", known.fingerprint[:12])

                # 3. Request shape.
                stage = "request_contract"
                if spec.request_contract:
                    self.contracts.enforce(
                        spec.request_contract,
                        payload,
                        role="request to {}".format(name),
                        site="gateway.{}".format(name),
                    )

                if dry_run:
                    # Everything checkable has been checked; the side effect is
                    # the only thing skipped. That is what makes a dry run a
                    # real rehearsal instead of a no-op.
                    span.set("outcome", "dry_run")
                    return GatewayResult(
                        connector=name,
                        ok=True,
                        value=None,
                        duration_ms=self._elapsed_ms(started),
                        trace_id=trace_id,
                        dry_run=True,
                        stage="dry_run",
                    )

                # 4. Dependency health.
                stage = "breaker"
                breaker = self.breakers.get(name, spec.breaker_policy)
                breaker.guard(site="gateway.{}".format(name))

                # 5-6. Bounded call.
                stage = "call"
                try:
                    value = self._call_bounded(connector, payload, call_context)
                except BaseException as exc:  # noqa: BLE001 - recorded, re-raised
                    breaker.on_failure(exc)
                    raise
                breaker.on_success()

                # 7. Response shape.
                stage = "response_contract"
                if spec.response_contract:
                    self.contracts.enforce(
                        spec.response_contract,
                        value,
                        role="response from {}".format(name),
                        site="gateway.{}".format(name),
                    )

                span.set("outcome", "ok")
                return GatewayResult(
                    connector=name,
                    ok=True,
                    value=value,
                    duration_ms=self._elapsed_ms(started),
                    trace_id=trace_id,
                )

            except BaseException as exc:  # noqa: BLE001 - converted to a result
                error = self._describe(exc)
                span.set("outcome", "error")
                span.set("stage", stage)
                span.set("error_code", error.get("code"))

                if self.failures is not None and isinstance(exc, Exception):
                    try:
                        self.failures.record(
                            exc,
                            site="gateway.{}".format(name),
                            context={"stage": stage, "trace_id": trace_id},
                        )
                    except Exception:  # noqa: BLE001 - memory is best effort
                        pass

                if raise_on_error or not isinstance(exc, Exception):
                    raise

                return GatewayResult(
                    connector=name,
                    ok=False,
                    error=error,
                    duration_ms=self._elapsed_ms(started),
                    trace_id=trace_id,
                    stage=stage,
                )

    def call(self, name: str, payload: Any = None, **kwargs: Any) -> Any:
        """Invoke and unwrap. Use when the caller wants exceptions."""
        return self.invoke(name, payload, **kwargs).unwrap()

    # ------------------------------------------------------------------
    # Bounded execution
    # ------------------------------------------------------------------

    def _call_bounded(
        self, connector: Connector, payload: Any, context: Dict[str, Any]
    ) -> Any:
        spec = connector.spec
        timeout = spec.timeout_seconds

        # No bound requested, or the connector enforces its own (urllib does).
        if timeout is None or connector.native_timeout:
            return connector.call(payload, context=context)

        future = self._pool().submit(connector.call, payload, context=context)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeout as exc:
            future.cancel()
            raise OperationTimeout(
                "{} exceeded its {}s budget".format(spec.name, timeout),
                detail={
                    "connector": spec.name,
                    "timeout_seconds": timeout,
                    # Python cannot kill a running thread. The call is
                    # abandoned, not stopped: the product stops waiting, the
                    # worker finishes on its own. Stated plainly because a
                    # timeout that silently leaks workers is worse than none.
                    "note": "worker abandoned, not terminated",
                },
                remediation=(
                    "Raise the connector's timeout if the work is legitimately "
                    "slow, or fix the dependency. Repeated timeouts will open "
                    "the breaker."
                ),
                site="gateway.{}".format(spec.name),
            ) from exc

    def _pool(self) -> ThreadPoolExecutor:
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=self._max_workers,
                    thread_name_prefix="syra-gateway",
                )
            return self._executor

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _now() -> float:
        import time

        return time.monotonic()

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        import time

        return round((time.monotonic() - started) * 1000.0, 3)

    @staticmethod
    def _describe(exc: BaseException) -> Dict[str, Any]:
        if isinstance(exc, SyraError):
            return exc.to_dict()
        return {
            "code": "SYRA-E-UNCLASSIFIED",
            "message": "{}: {}".format(type(exc).__name__, exc),
            "remediation": (
                "This failure escaped the core's taxonomy. Wrap it in a "
                "SyraError at its source so it can be fingerprinted."
            ),
        }

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def readiness(self) -> Dict[str, Any]:
        """Aggregate health plus breaker state -- the panel's real status."""
        aggregate = self.health.check_all()
        open_breakers = self.breakers.open_breakers()

        status = aggregate.status
        if open_breakers and status == health_mod.HEALTHY:
            # Probes can look fine while calls are being refused. Reporting
            # HEALTHY here is how "it says it's up but nothing works" happens.
            status = health_mod.DEGRADED

        return {
            "status": status,
            "ready": status in (health_mod.HEALTHY, health_mod.DEGRADED),
            "checkedAt": util.utc_iso(),
            "connectors": len(self._connectors),
            "openBreakers": open_breakers,
            "components": [item.as_dict() for item in aggregate.components],
        }

    def shutdown(self) -> None:
        with self._lock:
            connectors = list(self._connectors.values())
            executor, self._executor = self._executor, None
        for connector in connectors:
            try:
                connector.close()
            except Exception:  # noqa: BLE001 - shutdown is best effort
                pass
        if executor is not None:
            executor.shutdown(wait=False)

    def __enter__(self) -> "IntegrationGateway":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.shutdown()
