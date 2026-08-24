"""The 19-capability taxonomy -- what a product platform must be able to do.

This is the single source of truth shared by the discovery scanner, the PPC-00B
decision engine, and the product manifest schema. Detection patterns live next
to the capability they detect so a change to one cannot silently desynchronise
the other, which is how the original scan and its summary drifted apart.

Each capability carries:

    layer        where it sits in the platform
    intent       what it is responsible for, in one sentence
    patterns     regexes that suggest an implementation exists
    contract_of  whether it defines a boundary others depend on
    fragility    how badly a wrong consolidation decision would hurt

``fragility=CRITICAL_RUNTIME`` marks capabilities whose failure takes a product
down. The decision engine refuses to recommend consolidating those on static
evidence alone -- a refactor of a working circuit breaker, decided from grep
output, is exactly the self-inflicted outage this platform exists to prevent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

# Layers, outermost first.
LAYER_EXPERIENCE = "EXPERIENCE"
LAYER_INTEGRATION = "INTEGRATION"
LAYER_CONTROL = "CONTROL"
LAYER_RESILIENCE = "RESILIENCE"
LAYER_DELIVERY = "DELIVERY"

LAYERS: Tuple[str, ...] = (
    LAYER_EXPERIENCE,
    LAYER_INTEGRATION,
    LAYER_CONTROL,
    LAYER_RESILIENCE,
    LAYER_DELIVERY,
)

# How much damage a wrong decision does.
FRAGILITY_CRITICAL_RUNTIME = "CRITICAL_RUNTIME"
FRAGILITY_STRUCTURAL = "STRUCTURAL"
FRAGILITY_ADDITIVE = "ADDITIVE"


@dataclass(frozen=True)
class Capability:
    """One platform capability and how to recognise it in source."""

    id: str
    title: str
    layer: str
    intent: str
    patterns: Tuple[str, ...]
    fragility: str = FRAGILITY_STRUCTURAL
    defines_contract: bool = False

    @property
    def compiled(self) -> Tuple[re.Pattern, ...]:
        return tuple(re.compile(pattern, re.I) for pattern in self.patterns)

    def as_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "layer": self.layer,
            "intent": self.intent,
            "fragility": self.fragility,
            "definesContract": self.defines_contract,
            "patterns": list(self.patterns),
        }


CAPABILITIES: Tuple[Capability, ...] = (
    # ---------------- EXPERIENCE ----------------
    Capability(
        id="PRODUCT_FACTORY",
        title="Product Factory",
        layer=LAYER_EXPERIENCE,
        intent="Materialise a new product from a blueprint instead of assembling it by hand.",
        patterns=(
            r"product[_ -]?factory",
            r"materiali[sz]e[_ -]?product",
            r"create[_ -]?product",
            r"scaffold",
            r"blueprint",
            r"template[_ -]?registry",
        ),
        fragility=FRAGILITY_STRUCTURAL,
    ),
    Capability(
        id="PRODUCT_SHELL",
        title="Product Shell",
        layer=LAYER_EXPERIENCE,
        intent="The application frame every panel and console is mounted inside.",
        patterns=(
            r"product[_ -]?shell",
            r"app[_ -]?shell",
            r"dashboard",
            r"workspace",
            r"control[_ -]?room",
            r"console",
        ),
        fragility=FRAGILITY_STRUCTURAL,
    ),
    Capability(
        id="DESIGN_SYSTEM",
        title="Design System",
        layer=LAYER_EXPERIENCE,
        intent="Shared visual and interaction primitives so panels are consistent by construction.",
        patterns=(
            r"design[_ -]?system",
            r"components/ui",
            r"storybook",
            r"shadcn",
            r"ui[_ -]?kit",
        ),
        fragility=FRAGILITY_ADDITIVE,
    ),
    Capability(
        id="PRODUCT_SDK",
        title="Product SDK",
        layer=LAYER_EXPERIENCE,
        intent="A typed client so panels call the backend through one governed path.",
        patterns=(
            r"product[_ -]?sdk",
            r"api[_ -]?client",
            r"typed[_ -]?client",
            r"createClient",
            r"\bsdk\b",
        ),
        fragility=FRAGILITY_STRUCTURAL,
        defines_contract=True,
    ),
    # ---------------- INTEGRATION ----------------
    Capability(
        id="AGENT_CONNECTOR",
        title="Agent Connector",
        layer=LAYER_INTEGRATION,
        intent="Attach an agent or a squad to the platform under a declared contract.",
        patterns=(
            r"agent[_ -]?connector",
            r"agent[_ -]?adapter",
            r"agent[_ -]?gateway",
            r"agent.*contract",
            r"agent.*capabilit",
        ),
        fragility=FRAGILITY_STRUCTURAL,
        defines_contract=True,
    ),
    Capability(
        id="INTEGRATION_GATEWAY",
        title="Integration Gateway",
        layer=LAYER_INTEGRATION,
        intent="One governed path for every outbound call, with policy applied uniformly.",
        patterns=(
            r"integration[_ -]?gateway",
            r"runtime[_ -]?gateway",
            r"gateway[_ -]?adapter",
            r"neo[_ -]?gateway",
            r"\bproxy\b",
        ),
        fragility=FRAGILITY_CRITICAL_RUNTIME,
        defines_contract=True,
    ),
    Capability(
        id="CONTRACT_REGISTRY",
        title="Contract Registry",
        layer=LAYER_INTEGRATION,
        intent="Versioned schemas at every boundary, with breaking-change detection.",
        patterns=(
            r"contract[_ -]?registry",
            r"contracts/",
            r"openapi",
            r"json[_ -]?schema",
            r"pydantic",
            r"\bzod\b",
        ),
        fragility=FRAGILITY_STRUCTURAL,
        defines_contract=True,
    ),
    Capability(
        id="EVENT_REALTIME",
        title="Event / Realtime",
        layer=LAYER_INTEGRATION,
        intent="Push state to panels instead of making them poll and drift.",
        patterns=(
            r"event[_ -]?bus",
            r"event[_ -]?stream",
            r"websocket",
            r"server.sent.events",
            r"\bsse\b",
        ),
        fragility=FRAGILITY_STRUCTURAL,
    ),
    # ---------------- CONTROL ----------------
    Capability(
        id="PRODUCT_MANIFEST",
        title="Product Manifest",
        layer=LAYER_CONTROL,
        intent="A machine-readable declaration of what a product is and needs.",
        patterns=(
            r"product[_ -]?manifest",
            r"capability[_ -]?manifest",
            r"artifact[_ -]?manifest",
        ),
        fragility=FRAGILITY_STRUCTURAL,
        defines_contract=True,
    ),
    Capability(
        id="CONTROL_PLANE",
        title="Control Plane",
        layer=LAYER_CONTROL,
        intent="Know every product that exists, its version, and its current state.",
        patterns=(
            r"control[_ -]?plane",
            r"control[_ -]?tower",
            r"control[_ -]?room",
            r"product[_ -]?registry",
            r"service[_ -]?registry",
        ),
        fragility=FRAGILITY_STRUCTURAL,
    ),
    Capability(
        id="ZERO_TRUST_SECURITY",
        title="Zero-Trust Security",
        layer=LAYER_CONTROL,
        intent="Authorise every call explicitly and fail closed when in doubt.",
        patterns=(
            r"zero[_ -]?trust",
            r"fail[_ -]?closed",
            r"cloudflare[_ -]?access",
            r"constant[_ -]?time",
            r"authorization",
            r"authentication",
        ),
        fragility=FRAGILITY_CRITICAL_RUNTIME,
    ),
    Capability(
        id="OBSERVABILITY",
        title="Observability",
        layer=LAYER_CONTROL,
        intent="Make failures legible: traces, structured logs, causal chains.",
        patterns=(
            r"opentelemetry",
            r"\botel\b",
            r"structured[_ -]?log",
            r"execution[_ -]?trace",
            r"telemetry",
            r"observability",
        ),
        fragility=FRAGILITY_ADDITIVE,
    ),
    # ---------------- RESILIENCE ----------------
    Capability(
        id="CIRCUIT_BREAKER",
        title="Circuit Breaker",
        layer=LAYER_RESILIENCE,
        intent="Contain a failing dependency before it exhausts the product.",
        patterns=(r"circuit[_ -]?breaker", r"CircuitBreaker"),
        fragility=FRAGILITY_CRITICAL_RUNTIME,
    ),
    Capability(
        id="WATCHDOG",
        title="Watchdog",
        layer=LAYER_RESILIENCE,
        intent="Detect stalled or wedged work and act before a human notices.",
        patterns=(r"\bwatchdog\b", r"heartbeat[_ -]?monitor", r"stall[_ -]?detect"),
        fragility=FRAGILITY_CRITICAL_RUNTIME,
    ),
    Capability(
        id="HEALTH_READINESS",
        title="Health / Readiness",
        layer=LAYER_RESILIENCE,
        intent="Answer honestly whether a product can serve right now.",
        patterns=(
            r"/health",
            r"/ready",
            r"readiness",
            r"liveness",
            r"healthcheck",
        ),
        fragility=FRAGILITY_CRITICAL_RUNTIME,
        defines_contract=True,
    ),
    Capability(
        id="RECOVERY_ROLLBACK",
        title="Recovery / Rollback",
        layer=LAYER_RESILIENCE,
        intent="Return to a known-good state without manual archaeology.",
        patterns=(
            r"self[_ -]?healing",
            r"rollback",
            r"recovery",
            r"safe[_ -]?checkpoint",
        ),
        fragility=FRAGILITY_CRITICAL_RUNTIME,
    ),
    Capability(
        id="FAILURE_LEARNING",
        title="Failure Learning",
        layer=LAYER_RESILIENCE,
        intent="Remember every defect so it is never rediscovered at full price.",
        patterns=(
            r"failure[_ -]?memory",
            r"root[_ -]?cause",
            r"incident",
            r"learning[_ -]?engine",
            r"auto[_ -]?evolution",
        ),
        fragility=FRAGILITY_ADDITIVE,
    ),
    # ---------------- DELIVERY ----------------
    Capability(
        id="FUNCTIONAL_ASSURANCE",
        title="Functional Assurance",
        layer=LAYER_DELIVERY,
        intent="Nothing is declared working without evidence that it worked.",
        patterns=(
            r"functional[_ -]?assurance",
            r"evidence[_ -]?collector",
            r"critical[_ -]?validator",
            r"critical[_ -]?review",
            r"commit[_ -]?only[_ -]?if[_ -]?green",
        ),
        fragility=FRAGILITY_STRUCTURAL,
    ),
    Capability(
        id="DEPLOYMENT_ENGINE",
        title="Deployment Engine",
        layer=LAYER_DELIVERY,
        intent="Ship to the real topology predictably and reversibly.",
        patterns=(
            r"release[_ -]?safe",
            r"release[_ -]?preview",
            r"deployment[_ -]?engine",
            r"railway",
            r"vercel",
            r"cloudflare",
        ),
        fragility=FRAGILITY_CRITICAL_RUNTIME,
    ),
)

CAPABILITY_COUNT = len(CAPABILITIES)

BY_ID: Mapping[str, Capability] = {cap.id: cap for cap in CAPABILITIES}

CAPABILITY_IDS: Tuple[str, ...] = tuple(cap.id for cap in CAPABILITIES)


def get(capability_id: str) -> Capability:
    try:
        return BY_ID[capability_id]
    except KeyError:
        raise KeyError(
            "Unknown capability {!r}. Known: {}".format(
                capability_id, ", ".join(CAPABILITY_IDS)
            )
        ) from None


def by_layer(layer: str) -> List[Capability]:
    return [cap for cap in CAPABILITIES if cap.layer == layer]


def critical_runtime() -> List[Capability]:
    """Capabilities whose failure takes a product down."""
    return [cap for cap in CAPABILITIES if cap.fragility == FRAGILITY_CRITICAL_RUNTIME]


def contract_defining() -> List[Capability]:
    return [cap for cap in CAPABILITIES if cap.defines_contract]


def as_table() -> List[Dict[str, object]]:
    return [cap.as_dict() for cap in CAPABILITIES]


# The core ships real implementations for these. A product built by the factory
# inherits them rather than reimplementing -- which is the entire point of
# having a core instead of nineteen scattered half-implementations.
CORE_PROVIDED: Tuple[str, ...] = (
    "CONTRACT_REGISTRY",
    "INTEGRATION_GATEWAY",
    "AGENT_CONNECTOR",
    "CIRCUIT_BREAKER",
    "HEALTH_READINESS",
    "OBSERVABILITY",
    "FAILURE_LEARNING",
    "PRODUCT_MANIFEST",
    "PRODUCT_FACTORY",
    "CONTROL_PLANE",
    "FUNCTIONAL_ASSURANCE",
    "ZERO_TRUST_SECURITY",
)

# Capabilities the core deliberately does not implement: they are specific to a
# product's stack and topology. The core provides the seam, the product fills it.
PRODUCT_SUPPLIED: Tuple[str, ...] = tuple(
    cap.id for cap in CAPABILITIES if cap.id not in CORE_PROVIDED
)
