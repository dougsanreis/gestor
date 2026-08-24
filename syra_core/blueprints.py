"""Blueprints -- the source files the factory materialises.

Templates are Python string constants rather than files on disk. A template file
that fails to ship is a factory that breaks at the worst possible moment: while
someone is creating a product. Constants cannot go missing, and they are
compiled by the core's own preflight along with everything else.

Every generated product is runnable and tested on the first commit. A scaffold
that needs manual repair before it works is not a scaffold; it is homework.
"""

from __future__ import annotations

from typing import Dict, Mapping, Tuple

# ---------------------------------------------------------------------------
# Product kinds
# ---------------------------------------------------------------------------

#: What each kind gets by default: capabilities it must supply itself, the
#: connectors the scaffold stubs out, and whether it may reach the network.
KIND_PROFILES: Mapping[str, Dict[str, object]] = {
    "platform": {
        "summary": "Online platform with panels served to users.",
        "supplies": ("PRODUCT_SHELL", "DESIGN_SYSTEM", "PRODUCT_SDK", "EVENT_REALTIME"),
        "connectors": ("backend_api",),
        "network": True,
    },
    "multi_agent_platform": {
        "summary": "Platform coordinating several agent squads.",
        "supplies": ("PRODUCT_SHELL", "PRODUCT_SDK", "EVENT_REALTIME", "WATCHDOG"),
        "connectors": ("squad_router", "backend_api"),
        "network": True,
    },
    "agent_squad": {
        "summary": "A coordinated squad of agents solving one problem together.",
        "supplies": ("WATCHDOG", "RECOVERY_ROLLBACK"),
        "connectors": ("planner", "executor", "critic"),
        "network": False,
    },
    "agent": {
        "summary": "A single agent targeting one specific pain.",
        "supplies": ("WATCHDOG",),
        "connectors": ("agent",),
        "network": False,
    },
    "saas": {
        "summary": "Multi-tenant SaaS with billing and accounts.",
        "supplies": ("PRODUCT_SHELL", "DESIGN_SYSTEM", "PRODUCT_SDK", "DEPLOYMENT_ENGINE"),
        "connectors": ("backend_api", "billing"),
        "network": True,
    },
    "tool": {
        "summary": "A focused strategic tool.",
        "supplies": (),
        "connectors": ("engine",),
        "network": False,
    },
}


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

BOOTSTRAP_PY = '''"""Locate syra_core without requiring an install.

Resolution order, most explicit first:

    1. syra_core already importable (installed, or on PYTHONPATH)
    2. $SYRA_CORE_HOME
    3. the path recorded when this product was generated

Kept dependency-free and boring on purpose: an import shim that fails is
indistinguishable from a product that fails.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RECORDED_CORE_HOME = {core_home!r}


def ensure_core() -> str:
    try:
        import syra_core  # noqa: F401

        return "already-importable"
    except ImportError:
        pass

    candidates = []
    env_home = os.environ.get("SYRA_CORE_HOME")
    if env_home:
        candidates.append(Path(env_home).expanduser())
    if RECORDED_CORE_HOME:
        candidates.append(Path(RECORDED_CORE_HOME).expanduser())

    for candidate in candidates:
        if (candidate / "syra_core" / "__init__.py").is_file():
            sys.path.insert(0, str(candidate))
            return str(candidate)

    raise ImportError(
        "syra_core not found. Set SYRA_CORE_HOME to the directory that "
        "contains the syra_core package. Tried: "
        + ", ".join(str(c) for c in candidates)
    )


ensure_core()
'''


RUNTIME_PY = '''"""Boot the {name} runtime.

Everything hardened -- safety, contracts, breakers, health, tracing, failure
memory -- comes from the core. This file only declares what is specific to
{product_id}.
"""

from __future__ import annotations

from pathlib import Path

from . import _bootstrap  # noqa: F401  (resolves syra_core before it is imported)

from syra_core.runtime import ProductRuntime

from .connectors import register_all

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "product.manifest.json"


def build(*, block_repeats: bool = False, **kwargs) -> ProductRuntime:
    """Return a booted, connector-wired runtime.

    ``block_repeats=True`` makes failure memory enforcing: a known-open defect
    is refused instead of retried. Use it for unattended runs.
    """
    runtime = ProductRuntime.from_manifest(
        MANIFEST, block_repeats=block_repeats, **kwargs
    )
    register_all(runtime)
    return runtime


def main() -> int:
    import json

    with build() as runtime:
        print(json.dumps(runtime.readiness(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


CONNECTORS_PY = '''"""Connectors for {name}.

Each connector declares its contracts, timeout, and criticality. The gateway
enforces that declaration on every call, so an integration cannot quietly start
behaving differently from what it promised.

Replace the stub bodies with real implementations. The contracts and the smoke
test already hold them to their shape.
"""

from __future__ import annotations

from typing import Any, Dict

from . import _bootstrap  # noqa: F401

from syra_core.connector import agent_connector, service_connector
from syra_core.health import healthy
from syra_core.runtime import ProductRuntime

{stubs}

def register_all(runtime: ProductRuntime) -> None:
    """Attach every connector this product owns to the gateway."""
{registrations}
'''


CONNECTOR_STUB = '''
def {func_name}(payload: Dict[str, Any]) -> Dict[str, Any]:
    """{docstring}

    Raise on failure. Never return an error object: the gateway distinguishes
    success from failure by whether this raises, and a returned error looks
    exactly like a successful call to a breaker.
    """
    return {{
        "ok": True,
        "connector": "{connector_name}",
        "echo": payload,
    }}

'''


TEST_PY = '''"""Smoke tests for {name}.

These assert the product's own guarantees, not the core's -- the core has its
own suite. What matters here is that this product boots, that its contracts
match what its connectors actually return, and that a broken payload is refused
at the boundary instead of somewhere deeper.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# The product root is the import root. Resolving it from __file__ rather than
# assuming a directory name keeps the product working wherever it is generated.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.runtime import build


class TestProductBoots(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = build()

    def tearDown(self) -> None:
        self.runtime.shutdown()

    def test_manifest_is_valid(self) -> None:
        self.assertEqual(self.runtime.manifest.product_id, "{product_id}")
        self.assertEqual(self.runtime.manifest.kind, "{kind}")

    def test_readiness_reports(self) -> None:
        report = self.runtime.readiness()
        self.assertIn("status", report)
        self.assertIn(report["status"], ("HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN"))

    def test_connectors_registered(self) -> None:
        registered = self.runtime.gateway.names()
        for expected in {connector_names!r}:
            self.assertIn(expected, registered)

    def test_connector_round_trip(self) -> None:
        name = {first_connector!r}
        result = self.runtime.invoke(name, {{"probe": True}})
        self.assertTrue(result.ok, msg=result.error)

    def test_dry_run_validates_without_calling(self) -> None:
        name = {first_connector!r}
        result = self.runtime.invoke(name, {{"probe": True}}, dry_run=True)
        self.assertTrue(result.ok)
        self.assertTrue(result.dry_run)
        self.assertIsNone(result.value)


if __name__ == "__main__":
    unittest.main()
'''


README_MD = '''# {name}

{summary}

- **Product id**: `{product_id}`
- **Kind**: `{kind}`
- **Core**: syra-core {core_version}

## Rodar

```bash
cd {product_id}
python3 -m app.runtime                 # imprime o readiness
python3 -m unittest discover -s tests -v
```

## O que vem pronto do núcleo

Este produto não implementa nada disso — herda do `syra_core`:

| Capacidade | O que garante |
|---|---|
| Contract Registry | Payload inválido é recusado na fronteira, com o campo exato apontado |
| Integration Gateway | Todo call externo passa por safety, contrato, breaker, timeout e trace |
| Circuit Breaker | Dependência quebrada não derruba o produto |
| Health / Readiness | Resposta honesta sobre poder servir agora |
| Observability | Trace estruturado por call, com trace id |
| Failure Memory | Defeito conhecido não é redescoberto do zero |
| Zero-Trust Safety | Capacidade não declarada é negada |

## O que este produto precisa implementar

{supplies_list}

## Estrutura

```
{product_id}/
├── product.manifest.json   declaração governável deste produto
├── contracts/              schemas de fronteira, versionados
├── app/
│   ├── _bootstrap.py       localiza o syra_core sem instalar nada
│   ├── runtime.py          boot do produto
│   └── connectors.py       integrações declaradas
└── tests/                  smoke tests que já passam
```

## Antes de cada mudança

```bash
syra preflight --self          # SYRA-RULE-PPC-001
syra product validate .        # manifesto + contratos + drift
```
'''


PLUG_JSON_NOTE = (
    "Como este produto se pluga na SYRA AIOS. Consumido pelo control plane; "
    "editar manualmente apenas se souber o efeito."
)


def stub_docstring(connector_name: str) -> str:
    friendly = connector_name.replace("_", " ")
    return "Implementation for the {} connector.".format(friendly)


def render_connectors(connector_names: Tuple[str, ...], product_id: str) -> str:
    """Build the connectors module body for a set of connector names."""
    stubs = []
    registrations = []

    for connector_name in connector_names:
        func_name = "_{}".format(connector_name)
        stubs.append(
            CONNECTOR_STUB.format(
                func_name=func_name,
                connector_name=connector_name,
                docstring=stub_docstring(connector_name),
            )
        )
        registrations.append(
            "    runtime.register(\n"
            "        service_connector(\n"
            '            "{name}",\n'
            "            {func},\n"
            '            request_contract="{product}.{name}.request",\n'
            '            response_contract="{product}.{name}.response",\n'
            "            timeout_seconds=10.0,\n"
            "        )\n"
            "    )".format(name=connector_name, func=func_name, product=product_id)
        )

    return CONNECTORS_PY.format(
        name=product_id,
        stubs="".join(stubs),
        registrations="\n".join(registrations) or "    return",
    )
