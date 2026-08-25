"""Contratos tipados que atravessam todo o pipeline da SYRA.

Cada etapa do squad consome e produz dataclasses declaradas aqui. Nenhuma
etapa troca dicionarios soltos: se um campo nao existe no contrato, ele nao
atravessa a fronteira. Isso e o que impede o pipeline de "inventar" saidas.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    """Resultado de um portao de qualidade ou da governanca."""

    APPROVED = "APPROVED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLOCKED = "BLOCKED"


class Severity(str, Enum):
    """Gravidade de um achado de revisao."""

    INFO = "INFO"
    MINOR = "MINOR"
    MAJOR = "MAJOR"
    CRITICAL = "CRITICAL"


class Gain(str, Enum):
    """Tipos de ganho aceitos pela lei fundamental da governanca.

    Uma missao sem ao menos um ganho declarado e bloqueada antes de gastar
    qualquer ciclo de execucao.
    """

    CAPABILITY = "capability"
    AUTOMATION = "automation"
    PRODUCT = "product"
    REVENUE = "revenue"
    OPERATIONAL = "operational"
    HUMAN_IMPACT = "human_impact"


class RiskLevel(str, Enum):
    """Nivel de risco atribuido a um comando de shell."""

    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


def _now() -> float:
    return time.time()


def _slug(text: str, limit: int = 40) -> str:
    """Converte texto livre em identificador estavel e seguro para arquivos.

    O corte respeita fronteira de palavra: um pacote chamado
    ``gestao_escolar_com_al`` denuncia truncamento, ``gestao_escolar_com``
    parece intencional.
    """
    keep = []
    for char in text.lower():
        if char.isalnum():
            keep.append(char)
        elif keep and keep[-1] != "_":
            keep.append("_")

    slug = "".join(keep).strip("_")
    if len(slug) > limit:
        cortado = slug[:limit]
        fronteira = cortado.rfind("_")
        # So recua ate a fronteira se ainda sobrar nome util.
        if fronteira >= limit // 2:
            cortado = cortado[:fronteira]
        slug = cortado
    return slug.strip("_") or "mission"


@dataclass(frozen=True)
class Mission:
    """Pedido de construcao entregue a fabrica."""

    objective: str
    kind: str = "library"
    gains: tuple[Gain, ...] = (Gain.CAPABILITY,)
    constraints: tuple[str, ...] = ()
    mission_id: str = ""
    created_at: float = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.mission_id:
            stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(self.created_at))
            ident = f"{_slug(self.objective)}_{stamp}"
            object.__setattr__(self, "mission_id", ident)

    @property
    def package_name(self) -> str:
        """Nome do pacote Python derivado do objetivo."""
        base = _slug(self.objective, limit=28)
        if base[0].isdigit():
            base = f"p_{base}"
        return base

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["gains"] = [g.value for g in self.gains]
        data["constraints"] = list(self.constraints)
        return data


@dataclass(frozen=True)
class FunctionSpec:
    """Contrato de uma funcao publica que o projeto gerado deve expor."""

    name: str
    summary: str
    signature: str
    returns: str
    capability: str
    examples: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["examples"] = [list(pair) for pair in self.examples]
        return data


@dataclass(frozen=True)
class ModuleSpec:
    """Contrato de um modulo do projeto gerado."""

    name: str
    purpose: str
    functions: tuple[FunctionSpec, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "purpose": self.purpose,
            "functions": [f.to_dict() for f in self.functions],
        }


@dataclass(frozen=True)
class BuildSpec:
    """Plano executavel produzido pelo arquiteto a partir da missao."""

    mission: Mission
    package_name: str
    kind: str
    modules: tuple[ModuleSpec, ...]
    entrypoint: str | None = None
    rationale: str = ""

    @property
    def functions(self) -> tuple[FunctionSpec, ...]:
        return tuple(fn for module in self.modules for fn in module.functions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission": self.mission.to_dict(),
            "package_name": self.package_name,
            "kind": self.kind,
            "entrypoint": self.entrypoint,
            "rationale": self.rationale,
            "modules": [m.to_dict() for m in self.modules],
        }


@dataclass(frozen=True)
class GeneratedFile:
    """Arquivo materializado pelo sintetizador."""

    path: str
    content: str

    @property
    def is_python(self) -> bool:
        return self.path.endswith(".py")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "sha256": self.sha256, "bytes": len(self.content)}


@dataclass(frozen=True)
class GeneratedProject:
    """Conjunto completo de arquivos de um projeto sintetizado."""

    files: tuple[GeneratedFile, ...]
    synthesizer: str

    def by_path(self, path: str) -> GeneratedFile | None:
        for item in self.files:
            if item.path == path:
                return item
        return None

    def replace(self, path: str, content: str) -> GeneratedProject:
        """Retorna uma copia do projeto com ``path`` reescrito."""
        updated = [
            GeneratedFile(path=f.path, content=content) if f.path == path else f
            for f in self.files
        ]
        return GeneratedProject(files=tuple(updated), synthesizer=self.synthesizer)

    @property
    def source_files(self) -> tuple[GeneratedFile, ...]:
        return tuple(f for f in self.files if f.is_python and not _is_test_path(f.path))

    @property
    def test_files(self) -> tuple[GeneratedFile, ...]:
        return tuple(f for f in self.files if f.is_python and _is_test_path(f.path))


def _is_test_path(path: str) -> bool:
    return path.startswith("tests/") or path.rsplit("/", 1)[-1].startswith("test_")


@dataclass(frozen=True)
class ReviewFinding:
    """Achado individual da revisao estatica."""

    rule: str
    severity: Severity
    message: str
    path: str
    line: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        return data


@dataclass(frozen=True)
class ReviewReport:
    """Resultado consolidado do revisor estatico."""

    findings: tuple[ReviewFinding, ...]
    files_reviewed: int
    public_functions: int

    @property
    def blocking(self) -> tuple[ReviewFinding, ...]:
        return tuple(
            f for f in self.findings if f.severity in (Severity.CRITICAL, Severity.MAJOR)
        )

    @property
    def passed(self) -> bool:
        return not self.blocking

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "files_reviewed": self.files_reviewed,
            "public_functions": self.public_functions,
            "blocking_count": len(self.blocking),
            "findings": [f.to_dict() for f in self.findings],
        }


@dataclass(frozen=True)
class TestOutcome:
    """Resultado de um unico teste executado."""

    # Sem anotacao de tipo: nao vira campo do dataclass. Impede o pytest de
    # tentar coletar esta classe como suite so por causa do prefixo "Test".
    __test__ = False

    nodeid: str
    status: str
    duration: float
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QAReport:
    """Resultado real da execucao da suite de testes do projeto gerado."""

    runner: str
    passed: int
    failed: int
    errors: int
    skipped: int
    duration: float
    outcomes: tuple[TestOutcome, ...]
    raw_output: str = ""

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors + self.skipped

    @property
    def green(self) -> bool:
        return self.failed == 0 and self.errors == 0 and self.passed > 0

    @property
    def failures(self) -> tuple[TestOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status in ("failed", "error"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "runner": self.runner,
            "green": self.green,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "skipped": self.skipped,
            "duration": round(self.duration, 4),
            "outcomes": [o.to_dict() for o in self.outcomes],
        }


@dataclass(frozen=True)
class PackageManifest:
    """Manifesto do artefato entregavel."""

    mission_id: str
    package_name: str
    kind: str
    version: str
    files: tuple[dict[str, Any], ...]
    tests_passed: int
    created_at: float = field(default_factory=_now)
    artifact_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["files"] = list(self.files)
        return data


@dataclass(frozen=True)
class GovernanceDecision:
    """Decisao global emitida pela camada de governanca."""

    verdict: Verdict
    confidence: float
    reasons: tuple[str, ...]
    blocked_gates: tuple[str, ...] = ()
    disable_strategy: bool = False
    disable_agent: str | None = None
    replan_threshold: float = 0.0
    recommendations: tuple[str, ...] = ()

    @property
    def approved(self) -> bool:
        return self.verdict is Verdict.APPROVED

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["verdict"] = self.verdict.value
        data["reasons"] = list(self.reasons)
        data["blocked_gates"] = list(self.blocked_gates)
        data["recommendations"] = list(self.recommendations)
        return data


@dataclass(frozen=True)
class GateResult:
    """Resultado de um portao individual do pipeline."""

    name: str
    passed: bool
    detail: str
    duration: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["duration"] = round(self.duration, 4)
        return data


@dataclass(frozen=True)
class BuildResult:
    """Saida completa de uma execucao da fabrica."""

    mission: Mission
    spec: BuildSpec | None
    decision: GovernanceDecision
    gates: tuple[GateResult, ...]
    review: ReviewReport | None
    qa: QAReport | None
    manifest: PackageManifest | None
    build_dir: str | None
    artifact_path: str | None
    repair_attempts: int
    duration: float
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def delivered(self) -> bool:
        return self.decision.approved and self.artifact_path is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "mission": self.mission.to_dict(),
            "spec": self.spec.to_dict() if self.spec else None,
            "decision": self.decision.to_dict(),
            "gates": [g.to_dict() for g in self.gates],
            "review": self.review.to_dict() if self.review else None,
            "qa": self.qa.to_dict() if self.qa else None,
            "manifest": self.manifest.to_dict() if self.manifest else None,
            "build_dir": self.build_dir,
            "artifact_path": self.artifact_path,
            "repair_attempts": self.repair_attempts,
            "duration": round(self.duration, 4),
            "delivered": self.delivered,
        }


@dataclass(frozen=True)
class RiskAssessment:
    """Avaliacao de risco de um comando antes da execucao."""

    command: str
    level: RiskLevel
    score: int
    matched_rules: tuple[str, ...]
    reason: str
    safe_alternative: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["level"] = self.level.value
        data["matched_rules"] = list(self.matched_rules)
        return data


@dataclass(frozen=True)
class Recommendation:
    """Proposta de mudanca emitida por um agente de recomendacao."""

    rec_id: str
    agent: str
    target: str
    change: dict[str, Any]
    expected_gain: str
    confidence: float
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = list(self.evidence)
        return data


@dataclass(frozen=True)
class ValidationOutcome:
    """Resultado da validacao em sombra de uma recomendacao."""

    recommendation: Recommendation
    promoted: bool
    baseline_score: float
    candidate_score: float
    reason: str

    @property
    def delta(self) -> float:
        return round(self.candidate_score - self.baseline_score, 6)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation": self.recommendation.to_dict(),
            "promoted": self.promoted,
            "baseline_score": round(self.baseline_score, 6),
            "candidate_score": round(self.candidate_score, 6),
            "delta": self.delta,
            "reason": self.reason,
        }
