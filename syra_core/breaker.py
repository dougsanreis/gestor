"""Circuit breaker -- stop a failing dependency from taking the product down.

A panel wired to five integrations dies when one of them hangs: every request
queues behind the slow dependency until the whole process is exhausted. The
breaker converts that outage into a fast, explicit, local failure.

States:

    CLOSED     calls flow; consecutive failures are counted
    OPEN       calls are refused instantly for ``recovery_seconds``
    HALF_OPEN  a limited number of trial calls decide the next state

The clock is injectable, so breaker behaviour is tested deterministically rather
than with sleeps -- a test suite that sleeps is a test suite people skip.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from .errors import BreakerOpen

CLOSED = "CLOSED"
OPEN = "OPEN"
HALF_OPEN = "HALF_OPEN"


@dataclass(frozen=True)
class BreakerPolicy:
    """Thresholds governing one breaker."""

    failure_threshold: int = 5
    """Consecutive failures in CLOSED before the breaker opens."""

    recovery_seconds: float = 30.0
    """How long OPEN refuses calls before allowing a trial."""

    half_open_max_calls: int = 1
    """Concurrent trial calls permitted in HALF_OPEN."""

    success_threshold: int = 1
    """Trial successes required to close again."""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "failure_threshold": self.failure_threshold,
            "recovery_seconds": self.recovery_seconds,
            "half_open_max_calls": self.half_open_max_calls,
            "success_threshold": self.success_threshold,
        }


class CircuitBreaker:
    """Thread-safe breaker for a single named dependency."""

    def __init__(
        self,
        name: str,
        policy: Optional[BreakerPolicy] = None,
        *,
        clock: Callable[[], float] = None,  # type: ignore[assignment]
    ) -> None:
        import time

        self.name = name
        self.policy = policy or BreakerPolicy()
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()

        self._state = CLOSED
        self._failures = 0
        self._successes = 0
        self._opened_at: Optional[float] = None
        self._half_open_calls = 0
        self._total_calls = 0
        self._total_failures = 0
        self._total_rejected = 0
        self._last_error: Optional[str] = None

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        with self._lock:
            self._maybe_half_open()
            return self._state

    def _maybe_half_open(self) -> None:
        """Promote OPEN -> HALF_OPEN once the recovery window has elapsed."""
        if self._state != OPEN or self._opened_at is None:
            return
        if self._clock() - self._opened_at >= self.policy.recovery_seconds:
            self._state = HALF_OPEN
            self._half_open_calls = 0
            self._successes = 0

    def _open(self, reason: Optional[str] = None) -> None:
        self._state = OPEN
        self._opened_at = self._clock()
        self._half_open_calls = 0
        self._successes = 0
        if reason:
            self._last_error = reason

    def _close(self) -> None:
        self._state = CLOSED
        self._failures = 0
        self._successes = 0
        self._opened_at = None
        self._half_open_calls = 0

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------

    def allow(self) -> bool:
        """Whether a call may proceed right now. Reserves a HALF_OPEN slot."""
        with self._lock:
            self._maybe_half_open()

            if self._state == CLOSED:
                return True

            if self._state == OPEN:
                self._total_rejected += 1
                return False

            if self._half_open_calls < self.policy.half_open_max_calls:
                self._half_open_calls += 1
                return True

            self._total_rejected += 1
            return False

    def on_success(self) -> None:
        with self._lock:
            self._total_calls += 1
            if self._state == HALF_OPEN:
                self._successes += 1
                self._half_open_calls = max(0, self._half_open_calls - 1)
                if self._successes >= self.policy.success_threshold:
                    self._close()
            else:
                self._failures = 0

    def on_failure(self, error: Optional[BaseException] = None) -> None:
        with self._lock:
            self._total_calls += 1
            self._total_failures += 1
            if error is not None:
                self._last_error = "{}: {}".format(type(error).__name__, error)

            if self._state == HALF_OPEN:
                # A failed trial means the dependency is still sick. Re-open
                # immediately rather than spending the rest of the trial budget.
                self._half_open_calls = max(0, self._half_open_calls - 1)
                self._open()
                return

            self._failures += 1
            if self._failures >= self.policy.failure_threshold:
                self._open()

    def guard(self, *, site: Optional[str] = None) -> None:
        """Raise ``BreakerOpen`` unless the call may proceed."""
        if self.allow():
            return
        with self._lock:
            remaining = 0.0
            if self._opened_at is not None:
                elapsed = self._clock() - self._opened_at
                remaining = max(0.0, self.policy.recovery_seconds - elapsed)
            last_error = self._last_error
            state = self._state

        raise BreakerOpen(
            "Circuit breaker {!r} is {} -- call refused without contacting the "
            "dependency".format(self.name, state),
            detail={
                "breaker": self.name,
                "state": state,
                "retry_after_seconds": round(remaining, 3),
                "last_error": last_error,
            },
            remediation=(
                "The dependency is failing. Fix it, or serve degraded output "
                "for this integration; retrying now only burns latency."
            ),
            site=site or "breaker.{}".format(self.name),
        )

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run ``func`` under the breaker, recording the outcome."""
        self.guard()
        try:
            result = func(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - recorded then re-raised
            self.on_failure(exc)
            raise
        self.on_success()
        return result

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def reset(self) -> None:
        with self._lock:
            self._close()
            self._last_error = None

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            self._maybe_half_open()
            return {
                "name": self.name,
                "state": self._state,
                "consecutive_failures": self._failures,
                "total_calls": self._total_calls,
                "total_failures": self._total_failures,
                "total_rejected": self._total_rejected,
                "last_error": self._last_error,
                "policy": self.policy.as_dict(),
            }


class BreakerRegistry:
    """One breaker per dependency, created on first use."""

    def __init__(self, default_policy: Optional[BreakerPolicy] = None) -> None:
        self._default = default_policy or BreakerPolicy()
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get(
        self,
        name: str,
        policy: Optional[BreakerPolicy] = None,
        *,
        clock: Optional[Callable[[], float]] = None,
    ) -> CircuitBreaker:
        with self._lock:
            breaker = self._breakers.get(name)
            if breaker is None:
                breaker = CircuitBreaker(
                    name, policy or self._default, clock=clock  # type: ignore[arg-type]
                )
                self._breakers[name] = breaker
            return breaker

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            breakers = list(self._breakers.values())
        return {breaker.name: breaker.snapshot() for breaker in breakers}

    def open_breakers(self) -> list:
        return [
            breaker.name
            for breaker in list(self._breakers.values())
            if breaker.state == OPEN
        ]

    def reset_all(self) -> None:
        for breaker in list(self._breakers.values()):
            breaker.reset()
