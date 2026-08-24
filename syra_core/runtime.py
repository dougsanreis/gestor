"""ProductRuntime -- one call assembles a hardened product.

This is the plug. A new product does not wire safety, contracts, breakers,
health, tracing, and failure memory together by hand -- doing that nineteen
times is how nineteen subtly different, subtly broken versions come to exist.
It calls::

    runtime = ProductRuntime.from_manifest("product.manifest.json")
    runtime.register(agent_connector("planner", plan))
    result = runtime.invoke("planner", {"goal": "..."})

and inherits every guarantee the core provides.

Boot is fail-closed and ordered: preflight the environment, validate the
manifest, derive authority from it, load contracts, wire the gateway. A product
that cannot pass its own boot checks does not start half-working -- it refuses,
and says exactly what is wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from . import util
from .breaker import BreakerRegistry
from .capabilities import CORE_PROVIDED
from .connector import Connector
from .contracts import Contract, ContractRegistry
from .errors import ManifestInvalid, SyraError
from .failure_memory import FailureMemory
from .gateway import GatewayResult, IntegrationGateway
from .health import HealthRegistry
from .manifest import MANIFEST_FILENAME, ProductManifest
from .preflight import Preflight, PreflightReport
from .safety import SafetyContract
from .telemetry import Telemetry
from .version import CORE_VERSION, MIN_PYTHON


@dataclass
class ProductRuntime:
    """Everything a governed product needs, assembled and validated."""

    manifest: ProductManifest
    safety: SafetyContract
    contracts: ContractRegistry
    telemetry: Telemetry
    failures: FailureMemory
    health: HealthRegistry
    breakers: BreakerRegistry
    gateway: IntegrationGateway
    root: Optional[Path] = None
    boot_report: Optional[PreflightReport] = None

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_manifest(
        cls,
        manifest_path: Path | str,
        *,
        safety: Optional[SafetyContract] = None,
        telemetry_sink: Optional[Path | str] = None,
        state_dir: Optional[Path | str] = None,
        block_repeats: bool = False,
        strict: bool = True,
    ) -> "ProductRuntime":
        """Boot a product from its manifest.

        ``safety`` overrides what the manifest declares; it can only narrow.
        ``block_repeats`` turns failure memory from advisory into enforcing --
        recommended for scheduled or unattended work, where silently repeating a
        known-broken call wastes a whole run.
        """
        target = Path(manifest_path)
        root = target.parent if target.is_file() else target
        manifest = ProductManifest.load(target)

        # 1. Preflight the environment before anything is constructed.
        checker = Preflight(gate="product-boot:{}".format(manifest.product_id))
        checker.python_version(MIN_PYTHON)
        checker.note("core_version", CORE_VERSION)
        checker.note("manifest_fingerprint", manifest.fingerprint[:16])

        declared_safety = cls._safety_from_manifest(manifest)
        effective = declared_safety if safety is None else safety
        if safety is not None:
            # An explicit contract may restrict the manifest, never exceed it.
            over = [
                cap
                for cap in SafetyContract.CAPABILITIES  # type: ignore[attr-defined]
                if safety.allows(cap) and not declared_safety.allows(cap)
            ]
            if over:
                checker._add(  # noqa: SLF001 - internal accumulator by design
                    "safety:escalation",
                    "FAIL",
                    "runtime asked for {} which the manifest does not declare".format(
                        ", ".join(over)
                    ),
                    "Declare the capability in the manifest, or drop it here.",
                )

        state_root = Path(state_dir) if state_dir else util.state_root()
        checker.writable_path(state_root, label="state")

        report = checker.report()
        if strict:
            report.enforce(gate="product-boot:{}".format(manifest.product_id))

        # 2. Build the substrate.
        telemetry = Telemetry(
            service=manifest.product_id,
            sink=telemetry_sink,
        )
        contracts = ContractRegistry()
        failures = FailureMemory(
            state_root / "{}-failures.json".format(manifest.product_id),
            block_repeats=block_repeats,
        )
        health = HealthRegistry()
        breakers = BreakerRegistry()

        # 3. Load declared contracts from disk.
        loaded = cls._load_contracts(manifest, root, contracts)
        telemetry.event(
            "product.contracts_loaded",
            product=manifest.product_id,
            count=loaded,
        )

        gateway = IntegrationGateway(
            safety=effective,
            contracts=contracts,
            telemetry=telemetry,
            failures=failures,
            health=health,
            breakers=breakers,
        )

        runtime = cls(
            manifest=manifest,
            safety=effective,
            contracts=contracts,
            telemetry=telemetry,
            failures=failures,
            health=health,
            breakers=breakers,
            gateway=gateway,
            root=root,
            boot_report=report,
        )

        telemetry.event(
            "product.booted",
            product=manifest.product_id,
            kind=manifest.kind,
            version=manifest.version,
            contracts=len(contracts),
            granted=list(effective.granted()),
        )
        return runtime

    @classmethod
    def bootstrap(
        cls,
        *,
        product_id: str,
        name: str,
        kind: str = "tool",
        version: str = "0.1.0",
        safety: Optional[SafetyContract] = None,
        state_dir: Optional[Path | str] = None,
    ) -> "ProductRuntime":
        """Build an in-memory runtime with no manifest on disk.

        For tests, notebooks, and throwaway experiments. Anything that ships
        should use ``from_manifest`` so its declaration is reviewable.
        """
        from . import manifest as manifest_mod

        declared = safety or SafetyContract.product_runtime(
            "PRODUCT_RUNTIME:{}".format(product_id)
        )
        built = manifest_mod.build(
            product_id=product_id,
            name=name,
            kind=kind,
            version=version,
            safety=declared.as_dict(),
        )

        state_root = Path(state_dir) if state_dir else util.state_root()
        telemetry = Telemetry(service=product_id)
        contracts = ContractRegistry()
        failures = FailureMemory(
            state_root / "{}-failures.json".format(product_id), autoload=False
        )
        health = HealthRegistry()
        breakers = BreakerRegistry()
        gateway = IntegrationGateway(
            safety=declared,
            contracts=contracts,
            telemetry=telemetry,
            failures=failures,
            health=health,
            breakers=breakers,
        )
        return cls(
            manifest=built,
            safety=declared,
            contracts=contracts,
            telemetry=telemetry,
            failures=failures,
            health=health,
            breakers=breakers,
            gateway=gateway,
        )

    # ------------------------------------------------------------------
    # Boot helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safety_from_manifest(manifest: ProductManifest) -> SafetyContract:
        declared = manifest.safety_mapping()
        if not declared:
            # No declaration means the most restrictive posture that still lets
            # a product run: execute code, write state, reach nothing.
            return SafetyContract.product_runtime(
                "PRODUCT_RUNTIME:{}".format(manifest.product_id)
            )
        declared.setdefault("purpose", "PRODUCT_RUNTIME:{}".format(manifest.product_id))
        return SafetyContract.from_mapping(declared)

    @staticmethod
    def _load_contracts(
        manifest: ProductManifest, root: Path, registry: ContractRegistry
    ) -> int:
        loaded = 0
        for entry in manifest.contracts():
            file_ref = entry.get("file")
            if not file_ref:
                continue
            path = (root / file_ref).resolve()
            if not path.is_file():
                raise ManifestInvalid(
                    "Manifest declares contract file {} which does not exist".format(
                        file_ref
                    ),
                    detail={"expected": str(path), "contract": entry.get("name")},
                    remediation=(
                        "Create the contract file, or remove the declaration. A "
                        "product may not claim a boundary it cannot produce."
                    ),
                )
            try:
                payload = util.read_json(path)
            except ValueError as exc:
                raise ManifestInvalid(
                    "Contract file {} is not valid JSON: {}".format(file_ref, exc),
                    detail={"path": str(path)},
                    remediation="Repair the JSON syntax.",
                ) from exc

            if "contracts" in payload:
                loaded += registry.load(payload)
            else:
                registry.register(Contract.from_dict(payload), allow_breaking=True)
                loaded += 1
        return loaded

    # ------------------------------------------------------------------
    # Delegation
    # ------------------------------------------------------------------

    def register(self, connector: Connector, *, replace: bool = False) -> Connector:
        return self.gateway.register(connector, replace=replace)

    def define_contract(
        self,
        name: str,
        version: str,
        schema: Mapping[str, Any],
        **kwargs: Any,
    ) -> Contract:
        return self.contracts.define(name, version, schema, **kwargs)

    def invoke(self, name: str, payload: Any = None, **kwargs: Any) -> GatewayResult:
        return self.gateway.invoke(name, payload, **kwargs)

    def call(self, name: str, payload: Any = None, **kwargs: Any) -> Any:
        return self.gateway.call(name, payload, **kwargs)

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def readiness(self) -> Dict[str, Any]:
        """The honest answer to 'can this product serve right now?'"""
        payload = self.gateway.readiness()
        payload.update(
            {
                "product": self.manifest.product_id,
                "kind": self.manifest.kind,
                "version": self.manifest.version,
                "coreVersion": CORE_VERSION,
                "openDefects": len(self.failures.open_failures()),
            }
        )
        return payload

    def liveness(self) -> Dict[str, Any]:
        """Process-level check only. Never touches a dependency."""
        return {
            "status": "HEALTHY",
            "product": self.manifest.product_id,
            "coreVersion": CORE_VERSION,
            "checkedAt": util.utc_iso(),
        }

    def capability_report(self) -> List[Dict[str, Any]]:
        """What this product claims per capability, and who provides it."""
        declared = {entry["id"]: entry for entry in self.manifest.capabilities()}
        rows: List[Dict[str, Any]] = []
        from .capabilities import CAPABILITIES

        for capability in CAPABILITIES:
            entry = declared.get(capability.id)
            if entry is not None:
                mode = entry["mode"]
                source = entry.get("source", "")
            elif capability.id in CORE_PROVIDED:
                mode = "CORE_PROVIDED"
                source = "syra_core"
            else:
                mode = "NOT_APPLICABLE"
                source = ""
            rows.append(
                {
                    "capability": capability.id,
                    "layer": capability.layer,
                    "mode": mode,
                    "source": source,
                    "fragility": capability.fragility,
                }
            )
        return rows

    def diagnostics(self) -> Dict[str, Any]:
        """Everything an operator needs when a panel misbehaves, in one payload."""
        return {
            "product": self.manifest.as_dict(),
            "safety": self.safety.as_dict(),
            "readiness": self.readiness(),
            "connectors": self.gateway.specs(),
            "breakers": self.breakers.snapshot(),
            "failures": self.failures.stats(),
            "openFailures": [
                record.as_dict() for record in self.failures.open_failures()[:20]
            ],
            "contracts": [
                {
                    "name": contract.name,
                    "version": contract.version,
                    "fingerprint": contract.fingerprint[:16],
                }
                for contract in self.contracts.all()
            ],
            "boot": self.boot_report.as_dict() if self.boot_report else None,
        }

    def shutdown(self) -> None:
        self.telemetry.event("product.shutdown", product=self.manifest.product_id)
        self.gateway.shutdown()

    def __enter__(self) -> "ProductRuntime":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.shutdown()
