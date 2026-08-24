"""Circuit breaker state machine, driven by a fake clock (no sleeps)."""

from __future__ import annotations

import unittest

from tests.support import FakeClock

from syra_core.breaker import (
    CLOSED,
    HALF_OPEN,
    OPEN,
    BreakerPolicy,
    BreakerRegistry,
    CircuitBreaker,
)
from syra_core.errors import BreakerOpen


class TestStateMachine(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.breaker = CircuitBreaker(
            "dep",
            BreakerPolicy(failure_threshold=3, recovery_seconds=30.0),
            clock=self.clock,
        )

    def test_starts_closed(self) -> None:
        self.assertEqual(self.breaker.state, CLOSED)
        self.assertTrue(self.breaker.allow())

    def test_opens_after_threshold(self) -> None:
        for _ in range(3):
            self.breaker.on_failure(RuntimeError("boom"))
        self.assertEqual(self.breaker.state, OPEN)
        self.assertFalse(self.breaker.allow())

    def test_success_resets_the_failure_run(self) -> None:
        self.breaker.on_failure(RuntimeError("a"))
        self.breaker.on_failure(RuntimeError("b"))
        self.breaker.on_success()
        self.breaker.on_failure(RuntimeError("c"))
        self.assertEqual(self.breaker.state, CLOSED)

    def test_half_open_after_recovery_window(self) -> None:
        for _ in range(3):
            self.breaker.on_failure(RuntimeError("boom"))
        self.assertEqual(self.breaker.state, OPEN)

        self.clock.advance(29.0)
        self.assertEqual(self.breaker.state, OPEN)

        self.clock.advance(2.0)
        self.assertEqual(self.breaker.state, HALF_OPEN)

    def test_half_open_success_closes(self) -> None:
        for _ in range(3):
            self.breaker.on_failure(RuntimeError("boom"))
        self.clock.advance(31.0)

        self.assertTrue(self.breaker.allow())
        self.breaker.on_success()
        self.assertEqual(self.breaker.state, CLOSED)

    def test_half_open_failure_reopens_immediately(self) -> None:
        for _ in range(3):
            self.breaker.on_failure(RuntimeError("boom"))
        self.clock.advance(31.0)

        self.assertTrue(self.breaker.allow())
        self.breaker.on_failure(RuntimeError("still sick"))
        self.assertEqual(self.breaker.state, OPEN)

    def test_half_open_limits_trial_calls(self) -> None:
        for _ in range(3):
            self.breaker.on_failure(RuntimeError("boom"))
        self.clock.advance(31.0)

        self.assertTrue(self.breaker.allow())
        # Only one trial is permitted by default; the rest are refused.
        self.assertFalse(self.breaker.allow())


class TestGuard(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.breaker = CircuitBreaker(
            "dep", BreakerPolicy(failure_threshold=1, recovery_seconds=10.0),
            clock=self.clock,
        )

    def test_guard_raises_with_retry_hint(self) -> None:
        self.breaker.on_failure(RuntimeError("down"))
        self.clock.advance(4.0)

        with self.assertRaises(BreakerOpen) as caught:
            self.breaker.guard()

        detail = caught.exception.detail
        self.assertEqual(detail["state"], OPEN)
        self.assertAlmostEqual(detail["retry_after_seconds"], 6.0, places=3)
        self.assertIn("down", detail["last_error"])

    def test_call_records_outcomes(self) -> None:
        self.assertEqual(self.breaker.call(lambda: "ok"), "ok")
        self.assertEqual(self.breaker.state, CLOSED)

        with self.assertRaises(ValueError):
            self.breaker.call(lambda: (_ for _ in ()).throw(ValueError("x")))
        self.assertEqual(self.breaker.state, OPEN)

    def test_open_breaker_never_reaches_the_dependency(self) -> None:
        calls = []
        self.breaker.on_failure(RuntimeError("down"))

        with self.assertRaises(BreakerOpen):
            self.breaker.call(lambda: calls.append(1))

        self.assertEqual(calls, [], "the dependency must not be contacted")

    def test_reset_clears_state(self) -> None:
        self.breaker.on_failure(RuntimeError("down"))
        self.breaker.reset()
        self.assertEqual(self.breaker.state, CLOSED)


class TestRegistry(unittest.TestCase):
    def test_breakers_are_per_dependency(self) -> None:
        registry = BreakerRegistry(BreakerPolicy(failure_threshold=1))
        first = registry.get("a")
        first.on_failure(RuntimeError("x"))

        self.assertEqual(registry.get("a").state, OPEN)
        self.assertEqual(registry.get("b").state, CLOSED)
        self.assertEqual(registry.open_breakers(), ["a"])

    def test_get_is_stable(self) -> None:
        registry = BreakerRegistry()
        self.assertIs(registry.get("a"), registry.get("a"))


if __name__ == "__main__":
    unittest.main()
