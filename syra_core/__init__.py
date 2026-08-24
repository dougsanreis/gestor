"""SYRA Core -- the product integration platform kernel.

A dependency-free Python core that every SYRA product plugs into, so panels,
platforms, agents, squads, SaaS products and tools stop being assembled by hand
and stop breaking at their integration boundaries.

Quick start::

    from syra_core import ProductRuntime, agent_connector

    runtime = ProductRuntime.bootstrap(product_id="painel-vendas", name="Painel")
    runtime.define_contract("plan.request", "1.0.0", {"type": "object"})
    runtime.register(agent_connector("planner", plan_fn,
                                     request_contract="plan.request"))
    result = runtime.invoke("planner", {"goal": "..."})

Design rules, in the order they matter:

1. **Zero external dependencies.** Adding the core to a project can never break
   that project's dependency tree.
2. **Fail closed.** Every capability is denied until explicitly granted.
3. **Evidence over assertion.** A gate that cannot persist its artifacts did not
   pass.
4. **Preflight before execution.** SYRA-RULE-PPC-001: tooling is untrusted until
   it validates.
5. **Remember every failure.** A defect that recurs unrecognised is a defect
   paid for twice.
"""

from __future__ import annotations

from .breaker import BreakerPolicy, BreakerRegistry, CircuitBreaker
from .capabilities import CAPABILITIES, CAPABILITY_IDS, Capability
from .connector import (
    CallableConnector,
    Connector,
    ConnectorSpec,
    HttpConnector,
    agent_connector,
    http_connector,
    service_connector,
)
from .contracts import (
    CompatibilityReport,
    Contract,
    ContractRegistry,
    Violation,
    compatibility,
)
from .errors import (
    BreakerOpen,
    ContractViolation,
    OperationTimeout,
    PreflightFailed,
    RepeatedFailure,
    SafetyDenied,
    StaleEvidence,
    SyraError,
)
from .evidence import ArtifactRef, EvidenceRun, load_manifest
from .failure_memory import FailureMemory, FailureRecord
from .gateway import GatewayResult, IntegrationGateway
from .health import (
    AggregateHealth,
    HealthRegistry,
    HealthReport,
    degraded,
    healthy,
    unhealthy,
)
from .manifest import ProductManifest
from .preflight import Preflight, PreflightReport, self_check
from .registry import ProductRegistry
from .runtime import ProductRuntime
from .safety import SafetyContract
from .telemetry import Telemetry
from .version import CORE_NAME, CORE_VERSION

__version__ = CORE_VERSION

__all__ = [
    # runtime
    "ProductRuntime",
    "IntegrationGateway",
    "GatewayResult",
    # safety
    "SafetyContract",
    # contracts
    "Contract",
    "ContractRegistry",
    "CompatibilityReport",
    "Violation",
    "compatibility",
    # connectors
    "Connector",
    "ConnectorSpec",
    "CallableConnector",
    "HttpConnector",
    "agent_connector",
    "service_connector",
    "http_connector",
    # resilience
    "CircuitBreaker",
    "BreakerPolicy",
    "BreakerRegistry",
    "HealthRegistry",
    "HealthReport",
    "AggregateHealth",
    "healthy",
    "degraded",
    "unhealthy",
    # governance
    "EvidenceRun",
    "ArtifactRef",
    "load_manifest",
    "Preflight",
    "PreflightReport",
    "self_check",
    "FailureMemory",
    "FailureRecord",
    "ProductManifest",
    "ProductRegistry",
    "Telemetry",
    # taxonomy
    "Capability",
    "CAPABILITIES",
    "CAPABILITY_IDS",
    # errors
    "SyraError",
    "SafetyDenied",
    "ContractViolation",
    "BreakerOpen",
    "OperationTimeout",
    "RepeatedFailure",
    "PreflightFailed",
    "StaleEvidence",
    # meta
    "CORE_NAME",
    "CORE_VERSION",
    "__version__",
]
