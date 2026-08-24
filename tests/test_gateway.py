"""The gateway pipeline: safety, contracts, breaker, timeout, trace, memory."""

from __future__ import annotations

import time
import unittest

from tests.support import TempDirCase

from syra_core.breaker import BreakerPolicy, BreakerRegistry
from syra_core.connector import ConnectorSpec, agent_connector, service_connector
from syra_core.contracts import ContractRegistry
from syra_core.errors import (
    BreakerOpen,
    ConnectorUnknown,
    ContractViolation,
    OperationTimeout,
    SafetyDenied,
    SyraError,
)
from syra_core.failure_memory import FailureMemory
from syra_core.gateway import IntegrationGateway
from syra_core.health import healthy, unhealthy
from syra_core.safety import SafetyContract
from syra_core.telemetry import Telemetry

REQUEST_SCHEMA = {
    "type": "object",
    "required": ["goal"],
    "properties": {"goal": {"type": "string", "minLength": 1}},
}

RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["ok", "plan"],
    "properties": {"ok": {"type": "boolean"}, "plan": {"type": "string"}},
}


class GatewayCase(TempDirCase):
    def setUp(self) -> None:
        super().setUp()
        self.contracts = ContractRegistry()
        self.contracts.define("plan.request", "1.0.0", REQUEST_SCHEMA)
        self.contracts.define("plan.response", "1.0.0", RESPONSE_SCHEMA)
        self.telemetry = Telemetry(capture=256)
        self.failures = FailureMemory(self.path("failures.json"), autoload=False)
        self.gateway = IntegrationGateway(
            safety=SafetyContract.product_runtime("TEST"),
            contracts=self.contracts,
            telemetry=self.telemetry,
            failures=self.failures,
        )
        self.addCleanup(self.gateway.shutdown)

    def register_planner(self, func=None, **kwargs):
        func = func or (lambda payload: {"ok": True, "plan": "do " + payload["goal"]})
        connector = agent_connector(
            "planner",
            func,
            request_contract="plan.request",
            response_contract="plan.response",
            **kwargs,
        )
        return self.gateway.register(connector)


class TestRegistration(GatewayCase):
    def test_registers_and_lists(self) -> None:
        self.register_planner()
        self.assertEqual(self.gateway.names(), ["planner"])

    def test_unknown_contract_is_refused_at_registration(self) -> None:
        connector = service_connector(
            "x", lambda p: p, request_contract="does.not.exist"
        )
        with self.assertRaises(ConnectorUnknown) as caught:
            self.gateway.register(connector)
        self.assertIn("does.not.exist", str(caught.exception))

    def test_duplicate_registration_is_refused(self) -> None:
        self.register_planner()
        with self.assertRaises(SyraError):
            self.register_planner()

    def test_replace_is_explicit(self) -> None:
        self.register_planner()
        connector = agent_connector(
            "planner",
            lambda p: {"ok": True, "plan": "new"},
            request_contract="plan.request",
            response_contract="plan.response",
        )
        self.gateway.register(connector, replace=True)
        self.assertEqual(self.gateway.call("planner", {"goal": "x"})["plan"], "new")

    def test_unknown_connector_raises(self) -> None:
        with self.assertRaises(ConnectorUnknown):
            self.gateway.invoke("nope", {})

    def test_contracts_defined_after_construction_are_visible(self) -> None:
        """The gateway must keep the exact registry it was handed.

        An empty ContractRegistry is falsy, so `contracts or ContractRegistry()`
        silently swapped in a fresh one whenever the caller's registry happened
        to be empty at construction time -- and every contract added afterwards
        became invisible to the gateway.
        """
        registry = ContractRegistry()
        gateway = IntegrationGateway(
            safety=SafetyContract.product_runtime("TEST"), contracts=registry
        )
        self.addCleanup(gateway.shutdown)
        self.assertIs(gateway.contracts, registry)

        registry.define("late.request", "1.0.0", REQUEST_SCHEMA)
        gateway.register(
            service_connector(
                "late", lambda p: {"ok": True}, request_contract="late.request"
            )
        )
        self.assertFalse(gateway.invoke("late", {"wrong": 1}).ok)
        self.assertTrue(gateway.invoke("late", {"goal": "x"}).ok)


class TestPipeline(GatewayCase):
    def test_happy_path(self) -> None:
        self.register_planner()
        result = self.gateway.invoke("planner", {"goal": "ship"})
        self.assertTrue(result.ok)
        self.assertEqual(result.value, {"ok": True, "plan": "do ship"})
        self.assertGreaterEqual(result.duration_ms, 0.0)
        self.assertTrue(result.trace_id)

    def test_bad_request_is_caught_at_the_boundary(self) -> None:
        calls = []
        self.register_planner(lambda p: calls.append(p) or {"ok": True, "plan": "x"})

        result = self.gateway.invoke("planner", {"wrong": "shape"})
        self.assertFalse(result.ok)
        self.assertEqual(result.stage, "request_contract")
        self.assertEqual(result.error["code"], "SYRA-E-CONTRACT-VIOLATION")
        self.assertEqual(calls, [], "connector must not be reached")

    def test_bad_response_is_caught_too(self) -> None:
        self.register_planner(lambda p: {"ok": True})  # missing "plan"
        result = self.gateway.invoke("planner", {"goal": "x"})
        self.assertFalse(result.ok)
        self.assertEqual(result.stage, "response_contract")

    def test_safety_denial_precedes_everything(self) -> None:
        calls = []
        gateway = IntegrationGateway(
            safety=SafetyContract.static_analysis("READ_ONLY"),
            contracts=self.contracts,
            telemetry=self.telemetry,
        )
        self.addCleanup(gateway.shutdown)
        gateway.register(
            service_connector("svc", lambda p: calls.append(p) or {"ok": True})
        )

        result = gateway.invoke("svc", {"goal": "x"})
        self.assertFalse(result.ok)
        self.assertEqual(result.stage, "safety")
        self.assertEqual(result.error["code"], "SYRA-E-SAFETY-DENIED")
        self.assertEqual(calls, [])

    def test_dry_run_validates_but_does_not_call(self) -> None:
        calls = []
        self.register_planner(lambda p: calls.append(p) or {"ok": True, "plan": "x"})

        result = self.gateway.invoke("planner", {"goal": "x"}, dry_run=True)
        self.assertTrue(result.ok)
        self.assertTrue(result.dry_run)
        self.assertIsNone(result.value)
        self.assertEqual(calls, [])

    def test_dry_run_still_rejects_a_bad_request(self) -> None:
        self.register_planner()
        result = self.gateway.invoke("planner", {"bad": 1}, dry_run=True)
        self.assertFalse(result.ok)
        self.assertEqual(result.stage, "request_contract")

    def test_unwrap_raises_on_failure(self) -> None:
        self.register_planner()
        result = self.gateway.invoke("planner", {"bad": 1})
        with self.assertRaises(SyraError):
            result.unwrap()

    def test_raise_on_error_propagates(self) -> None:
        self.register_planner()
        with self.assertRaises(ContractViolation):
            self.gateway.invoke("planner", {"bad": 1}, raise_on_error=True)


class TestResilience(GatewayCase):
    def test_failures_open_the_breaker(self) -> None:
        def broken(payload):
            raise RuntimeError("dependency down")

        self.gateway.register(
            service_connector(
                "flaky", broken, timeout_seconds=None
            )
        )
        self.gateway.breakers.get("flaky", BreakerPolicy(failure_threshold=2))

        first = self.gateway.invoke("flaky", {})
        second = self.gateway.invoke("flaky", {})
        third = self.gateway.invoke("flaky", {})

        self.assertFalse(first.ok)
        self.assertFalse(second.ok)
        self.assertEqual(third.stage, "breaker")
        self.assertEqual(third.error["code"], "SYRA-E-BREAKER-OPEN")

    def test_timeout_is_bounded(self) -> None:
        def slow(payload):
            time.sleep(2.0)
            return {"ok": True}

        self.gateway.register(
            service_connector("slow", slow, timeout_seconds=0.05)
        )
        started = time.monotonic()
        result = self.gateway.invoke("slow", {})
        elapsed = time.monotonic() - started

        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "SYRA-E-TIMEOUT")
        self.assertLess(elapsed, 1.0, "gateway must stop waiting well before the call ends")

    def test_failures_are_remembered(self) -> None:
        def broken(payload):
            raise RuntimeError("dependency down")

        self.gateway.register(
            service_connector("flaky", broken, timeout_seconds=None)
        )
        self.gateway.invoke("flaky", {})

        records = self.failures.all()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].site, "gateway.flaky")

    def test_one_broken_connector_does_not_break_the_others(self) -> None:
        self.register_planner()
        self.gateway.register(
            service_connector(
                "flaky",
                lambda p: (_ for _ in ()).throw(RuntimeError("down")),
                timeout_seconds=None,
            )
        )

        self.assertFalse(self.gateway.invoke("flaky", {}).ok)
        self.assertTrue(self.gateway.invoke("planner", {"goal": "x"}).ok)


class TestObservability(GatewayCase):
    def test_every_call_emits_a_span(self) -> None:
        self.register_planner()
        self.gateway.invoke("planner", {"goal": "x"})
        spans = self.telemetry.spans("gateway.invoke")
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["status"], "ok")
        self.assertEqual(spans[0]["attributes"]["connector"], "planner")

    def test_failed_calls_record_the_stage(self) -> None:
        self.register_planner()
        self.gateway.invoke("planner", {"bad": 1})
        span = self.telemetry.spans("gateway.invoke")[0]
        self.assertEqual(span["attributes"]["stage"], "request_contract")
        self.assertEqual(span["attributes"]["error_code"], "SYRA-E-CONTRACT-VIOLATION")

    def test_readiness_degrades_when_a_breaker_is_open(self) -> None:
        self.gateway.register(
            service_connector(
                "flaky",
                lambda p: (_ for _ in ()).throw(RuntimeError("down")),
                timeout_seconds=None,
                probe=lambda: healthy("flaky"),
            )
        )
        self.gateway.breakers.get("flaky", BreakerPolicy(failure_threshold=1))
        self.gateway.invoke("flaky", {})

        report = self.gateway.readiness()
        self.assertEqual(report["openBreakers"], ["flaky"])
        # The probe says healthy, but calls are being refused. Reporting
        # HEALTHY here would be the "it says it's up but nothing works" bug.
        self.assertEqual(report["status"], "DEGRADED")

    def test_non_critical_failure_degrades_rather_than_downs(self) -> None:
        self.gateway.register(
            service_connector(
                "optional",
                lambda p: {"ok": True},
                critical=False,
                probe=lambda: unhealthy("optional", "offline"),
            )
        )
        report = self.gateway.readiness()
        self.assertEqual(report["status"], "DEGRADED")
        self.assertTrue(report["ready"])


if __name__ == "__main__":
    unittest.main()
