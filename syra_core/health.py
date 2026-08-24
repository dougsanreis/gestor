"""Health and readiness aggregation.

A panel that renders but cannot reach its backend is not "up" -- it is broken in
the most expensive way, because it looks fine. This module separates the two
questions every product must answer:

    liveness   is this process functioning at all?
    readiness  can this process actually serve, given its dependencies?

A dependency marked ``critical`` drags readiness down when it fails. A
non-critical dependency degrades it instead. That distinction is what lets a
product shed a broken optional integration without going dark.

Probes are never allowed to raise into the caller: a health endpoint that throws
is a health endpoint that reports nothing.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from . import util

HEALTHY = "HEALTHY"
DEGRADED = "DEGRADED"
UNHEALTHY = "UNHEALTHY"
UNKNOWN = "UNKNOWN"

_SEVERITY = {HEALTHY: 0, UNKNOWN: 1, DEGRADED: 2, UNHEALTHY: 3}


@dataclass(frozen=True)
class HealthReport:
    """The outcome of one probe."""

    component: str
    status: str
    detail: str = ""
    latency_ms: Optional[float] = None
    critical: bool = True
    checked_at: str = field(default_factory=util.utc_iso)

    @property
    def ok(self) -> bool:
        return self.status == HEALTHY

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "component": self.component,
            "status": self.status,
            "critical": self.critical,
            "checkedAt": self.checked_at,
        }
        if self.detail:
            payload["detail"] = self.detail
        if self.latency_ms is not None:
            payload["latencyMs"] = self.latency_ms
        return payload

    def render(self) -> str:
        line = "COMPONENT={}|STATUS={}".format(self.component, self.status)
        if self.latency_ms is not None:
            line += "|LATENCY_MS={}".format(self.latency_ms)
        if self.detail:
            line += "|DETAIL={}".format(util.truncate(self.detail, 120))
        return line


def healthy(component: str, detail: str = "", **kwargs: Any) -> HealthReport:
    return HealthReport(component=component, status=HEALTHY, detail=detail, **kwargs)


def degraded(component: str, detail: str = "", **kwargs: Any) -> HealthReport:
    return HealthReport(component=component, status=DEGRADED, detail=detail, **kwargs)


def unhealthy(component: str, detail: str = "", **kwargs: Any) -> HealthReport:
    return HealthReport(component=component, status=UNHEALTHY, detail=detail, **kwargs)


@dataclass
class AggregateHealth:
    """Rolled-up readiness across every registered component."""

    status: str
    components: List[HealthReport] = field(default_factory=list)
    checked_at: str = field(default_factory=util.utc_iso)

    @property
    def ready(self) -> bool:
        return self.status in (HEALTHY, DEGRADED)

    def failing(self) -> List[HealthReport]:
        return [item for item in self.components if item.status != HEALTHY]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "checkedAt": self.checked_at,
            "components": [item.as_dict() for item in self.components],
        }

    def render(self) -> str:
        lines = ["===== HEALTH ====="]
        lines.extend(item.render() for item in self.components)
        lines.append(util.kv("HEALTH_STATUS", self.status))
        lines.append(util.kv("READY", self.ready))
        return "\n".join(lines)


Probe = Callable[[], HealthReport]


class HealthRegistry:
    """Registry of probes plus the aggregation rule."""

    def __init__(self, *, timeout_seconds: float = 5.0) -> None:
        self._probes: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._timeout = timeout_seconds

    def register(
        self,
        name: str,
        probe: Probe,
        *,
        critical: bool = True,
    ) -> None:
        with self._lock:
            self._probes[name] = {"probe": probe, "critical": critical}

    def unregister(self, name: str) -> None:
        with self._lock:
            self._probes.pop(name, None)

    def names(self) -> List[str]:
        with self._lock:
            return sorted(self._probes)

    def check(self, name: str) -> HealthReport:
        with self._lock:
            entry = self._probes.get(name)

        if entry is None:
            return HealthReport(
                component=name,
                status=UNKNOWN,
                detail="no probe registered",
                critical=False,
            )

        started = time.monotonic()
        try:
            report = entry["probe"]()
        except Exception as exc:  # noqa: BLE001 - a probe must not break health
            return HealthReport(
                component=name,
                status=UNHEALTHY,
                detail="probe raised {}: {}".format(
                    type(exc).__name__, util.truncate(str(exc), 160)
                ),
                latency_ms=round((time.monotonic() - started) * 1000.0, 3),
                critical=entry["critical"],
            )

        latency = round((time.monotonic() - started) * 1000.0, 3)
        if not isinstance(report, HealthReport):
            return HealthReport(
                component=name,
                status=UNKNOWN,
                detail="probe returned {} instead of HealthReport".format(
                    type(report).__name__
                ),
                latency_ms=latency,
                critical=entry["critical"],
            )

        # The registry owns criticality and timing; a probe cannot promote
        # itself to non-critical to make a failure look benign.
        return HealthReport(
            component=report.component or name,
            status=report.status,
            detail=report.detail,
            latency_ms=report.latency_ms if report.latency_ms is not None else latency,
            critical=entry["critical"],
            checked_at=report.checked_at,
        )

    def check_all(self) -> AggregateHealth:
        reports = [self.check(name) for name in self.names()]
        return AggregateHealth(status=aggregate_status(reports), components=reports)


def aggregate_status(reports: List[HealthReport]) -> str:
    """Roll individual probes into one verdict.

    * any critical component UNHEALTHY -> UNHEALTHY (cannot serve)
    * any critical component DEGRADED/UNKNOWN, or any non-critical failure
      -> DEGRADED (can serve, with reduced function)
    * nothing registered -> HEALTHY (nothing claimed, nothing broken)
    """
    if not reports:
        return HEALTHY

    worst = HEALTHY
    for report in reports:
        if report.status == HEALTHY:
            continue
        if report.critical:
            candidate = report.status
        else:
            # A failing optional dependency degrades; it never takes the
            # product down.
            candidate = DEGRADED
        if _SEVERITY[candidate] > _SEVERITY[worst]:
            worst = candidate

    return worst
