"""Agentes de recomendacao auto-otimizaveis.

Cada agente e um especialista estreito que le metricas reais e propoe uma
mudanca numerica de politica. Nenhuma proposta entra em producao direto: o
validador em sombra reexecuta o historico gravado sob a politica candidata e
so promove o que melhora o objetivo de forma mensuravel.

Duas travas impedem que a auto-otimizacao vire autossabotagem:

1. ``CAMPOS_CONGELADOS`` - o nucleo de seguranca (taxa de aprovacao de testes,
   achados bloqueantes, cobertura, limiar de bloqueio de comandos) nao e
   otimizavel. O sistema nao pode aprender a baixar a propria guarda.
2. ``_viola_invariante`` - qualquer politica candidata que teria entregue uma
   execucao com teste falhando ou achado bloqueante e rejeitada, mesmo que
   pontue melhor.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from syra.contracts import Recommendation, ValidationOutcome
from syra.governance.policy import Policy
from syra.memory.error_memory import ErrorMemory
from syra.memory.run_store import RunRecord, RunStore
from syra.intelligence.test_selector import TestIntelligence
from syra.paths import state_dir

# O nucleo de seguranca e imune a auto-otimizacao, por construcao.
CAMPOS_CONGELADOS = frozenset({
    "min_test_pass_rate",
    "max_blocking_findings",
    "require_test_per_public_function",
    "min_public_functions",
    "min_confidence_to_approve",
    "quarantine_block_score",
    "quarantine_review_score",
})


@dataclass(frozen=True)
class Signals:
    """Fotografia das metricas que os agentes observam."""

    stats: dict
    timing: dict
    systemic_errors: int
    runs: list[RunRecord]


class RecommenderAgent(Protocol):
    """Especialista que converte sinais em propostas de mudanca."""

    name: str

    def recommend(self, signals: Signals, policy: Policy) -> list[Recommendation]:
        """Propoe mudancas de politica a partir dos sinais observados."""
        ...


def _rec(agent: str, field: str, value, gain: str, confidence: float,
         evidence: list[str]) -> Recommendation:
    return Recommendation(
        rec_id=uuid.uuid4().hex[:10], agent=agent, target=field,
        change={"field": field, "value": value}, expected_gain=gain,
        confidence=confidence, evidence=tuple(evidence),
    )


class TestSpeedAgent:
    """Ajusta o orcamento de tempo da suite ao custo real observado."""

    name = "test_speed"

    def recommend(self, signals: Signals, policy: Policy) -> list[Recommendation]:
        estimado = float(signals.timing.get("estimated_full_run") or 0.0)
        propostas: list[Recommendation] = []
        if estimado <= 0:
            return propostas

        # Orcamento util fica um pouco acima do custo real; nem folgado
        # demais (nao detecta nada) nem apertado demais (alarme constante).
        alvo = round(max(5.0, estimado * 1.5), 2)
        if abs(alvo - policy.test_budget_seconds) / max(policy.test_budget_seconds, 1) > 0.25:
            propostas.append(_rec(
                self.name, "test_budget_seconds", alvo,
                "orcamento alinhado ao custo real da suite", 0.8,
                [f"suite completa estimada em {estimado:.2f}s",
                 f"orcamento atual {policy.test_budget_seconds:.2f}s"],
            ))

        lentos = signals.timing.get("slowest") or []
        if lentos:
            mediana_maior = float(lentos[0]["median"])
            novo_limiar = round(max(0.25, mediana_maior * 0.5), 2)
            if abs(novo_limiar - policy.slow_test_threshold) > 0.2:
                propostas.append(_rec(
                    self.name, "slow_test_threshold", novo_limiar,
                    "limiar sensivel aos testes que realmente dominam a suite", 0.6,
                    [f"teste mais lento: {lentos[0]['nodeid']} "
                     f"({mediana_maior:.2f}s, {lentos[0]['share']:.0%} da suite)"],
                ))
        return propostas


class ReliabilityAgent:
    """Ajusta o orcamento de reparo ao que de fato converge."""

    name = "reliability"

    def recommend(self, signals: Signals, policy: Policy) -> list[Recommendation]:
        if not signals.runs:
            return []

        reparados = [r for r in signals.runs if r.repair_attempts > 0]
        if not reparados:
            return []

        uteis = [r.repair_attempts for r in reparados if r.delivered]
        if uteis:
            necessario = max(uteis)
            if necessario < policy.max_repair_attempts:
                return [_rec(
                    self.name, "max_repair_attempts", necessario,
                    "menos ciclos gastos em reparo que nunca converge", 0.7,
                    [f"{len(reparados)} execucao(oes) com reparo",
                     f"maximo de tentativas que resultou em entrega: {necessario}"],
                )]
            return []

        # Reparo nunca converteu em entrega: insistir e desperdicio.
        if policy.max_repair_attempts > 1:
            return [_rec(
                self.name, "max_repair_attempts", 1,
                "corta ciclos de reparo improdutivos", 0.75,
                [f"{len(reparados)} execucao(oes) com reparo, nenhuma entregue"],
            )]
        return []


class ErrorMemoryAgent:
    """Aperta o gatilho de falha sistemica quando erros se repetem."""

    name = "error_memory"

    def recommend(self, signals: Signals, policy: Policy) -> list[Recommendation]:
        if signals.systemic_errors >= 2 and policy.recurrence_threshold > 2:
            return [_rec(
                self.name, "recurrence_threshold", policy.recurrence_threshold - 1,
                "detecta falha sistemica mais cedo", 0.65,
                [f"{signals.systemic_errors} falha(s) recorrente(s) sem correcao"],
            )]
        return []


class DeliveryAgent:
    """Alinha a expectativa de entrega ao desempenho historico real."""

    name = "delivery"

    def recommend(self, signals: Signals, policy: Policy) -> list[Recommendation]:
        stats = signals.stats
        if stats.get("runs", 0) < policy.optimizer_min_runs:
            return []

        taxa = float(stats.get("delivery_rate", 0.0))
        # So aperta a meta quando o sistema ja opera com folga sobre ela.
        if taxa >= policy.min_delivery_rate + 0.25 and policy.min_delivery_rate < 0.9:
            alvo = round(min(0.9, taxa - 0.1), 2)
            if alvo > policy.min_delivery_rate:
                return [_rec(
                    self.name, "min_delivery_rate", alvo,
                    "meta de entrega acompanha o desempenho ja alcancado", 0.6,
                    [f"taxa historica de entrega {taxa:.0%}",
                     f"meta atual {policy.min_delivery_rate:.0%}"],
                )]
        return []


AGENTES: tuple[RecommenderAgent, ...] = (
    TestSpeedAgent(), ReliabilityAgent(), ErrorMemoryAgent(), DeliveryAgent(),
)


def _teria_entregue(record: RunRecord, policy: Policy) -> bool:
    """Contrafactual deterministico: esta execucao passaria sob esta politica?"""
    if record.tests_total == 0:
        return False
    if record.review_blocking > policy.max_blocking_findings:
        return False
    if record.tests_passed / record.tests_total < policy.min_test_pass_rate:
        return False
    return record.repair_attempts <= policy.max_repair_attempts


def score(records: list[RunRecord], policy: Policy) -> float:
    """Pontua uma politica sobre o historico gravado.

    Objetivo: maximizar entrega e penalizar execucoes que estouram o orcamento
    de tempo. Entrega vale mais que velocidade, por isso o peso menor da
    penalidade.
    """
    if not records:
        return 0.0
    entregues = sum(1 for r in records if _teria_entregue(r, policy))
    estourados = sum(1 for r in records if r.duration > policy.test_budget_seconds)
    return round(entregues / len(records) - 0.2 * (estourados / len(records)), 6)


def _viola_invariante(records: list[RunRecord], policy: Policy) -> str | None:
    """Rejeita politicas que aprovariam entregas sem evidencia limpa."""
    for record in records:
        if not _teria_entregue(record, policy):
            continue
        if record.tests_failed > 0:
            return (f"politica candidata entregaria a execucao {record.run_id} "
                    f"com {record.tests_failed} teste(s) falhando")
        if record.review_blocking > 0:
            return (f"politica candidata entregaria a execucao {record.run_id} "
                    f"com {record.review_blocking} achado(s) bloqueante(s)")
    return None


class Optimizer:
    """Ciclo completo: observar, recomendar, validar em sombra, promover."""

    def __init__(self, policy: Policy | None = None, store: RunStore | None = None,
                 timing: TestIntelligence | None = None,
                 memory: ErrorMemory | None = None,
                 agents: tuple[RecommenderAgent, ...] = AGENTES,
                 audit_path: Path | None = None) -> None:
        self.policy = policy or Policy.load()
        self.store = store or RunStore()
        self.timing = timing or TestIntelligence()
        self.memory = memory or ErrorMemory()
        self.agents = agents
        self.audit_path = audit_path or (state_dir() / "optimizer_audit.jsonl")

    def observe(self) -> Signals:
        """Coleta os sinais atuais do sistema."""
        return Signals(
            stats=self.store.stats(),
            timing=self.timing.summary(self.policy.slow_test_threshold,
                                       self.policy.speed_regression_factor),
            systemic_errors=len(self.memory.systemic_failures(
                self.policy.recurrence_threshold)),
            runs=self.store.recent(50),
        )

    def recommend(self, signals: Signals) -> list[Recommendation]:
        """Reune as propostas de todos os agentes, descartando campos congelados."""
        propostas: list[Recommendation] = []
        for agente in self.agents:
            for proposta in agente.recommend(signals, self.policy):
                if proposta.change["field"] in CAMPOS_CONGELADOS:
                    continue
                propostas.append(proposta)
        return sorted(propostas, key=lambda r: -r.confidence)

    def validate(self, recommendation: Recommendation,
                 records: list[RunRecord]) -> ValidationOutcome:
        """Valida uma proposta em sombra, sem tocar na politica ativa."""
        campo = recommendation.change["field"]
        valor = recommendation.change["value"]

        if campo in CAMPOS_CONGELADOS:
            return ValidationOutcome(recommendation, False, 0.0, 0.0,
                                     f"campo '{campo}' e congelado por seguranca")
        try:
            candidata = self.policy.with_change(campo, valor)
        except KeyError as erro:
            return ValidationOutcome(recommendation, False, 0.0, 0.0, str(erro))

        violacao = _viola_invariante(records, candidata)
        if violacao:
            return ValidationOutcome(recommendation, False, 0.0, 0.0, violacao)

        base = score(records, self.policy)
        candidato = score(records, candidata)

        if len(records) < self.policy.optimizer_min_runs:
            return ValidationOutcome(recommendation, False, base, candidato,
                                     f"historico insuficiente: {len(records)} execucao(oes), "
                                     f"minimo {self.policy.optimizer_min_runs}")

        if candidato < base:
            return ValidationOutcome(recommendation, False, base, candidato,
                                     "politica candidata piora o objetivo")

        # Mudancas neutras no objetivo ainda valem quando o agente as propoe
        # por reducao de desperdicio (tempo ou ciclo), nunca por afrouxamento.
        if candidato - base < self.policy.optimizer_min_improvement:
            neutra_util = campo in {"test_budget_seconds", "slow_test_threshold",
                                    "max_repair_attempts", "recurrence_threshold"}
            if not neutra_util:
                return ValidationOutcome(recommendation, False, base, candidato,
                                         "ganho abaixo do minimo exigido")

        return ValidationOutcome(recommendation, True, base, candidato,
                                 "validada em sombra sobre o historico real")

    def cycle(self, apply: bool = True) -> dict:
        """Executa um ciclo completo de auto-otimizacao.

        Args:
            apply: quando False, avalia e reporta sem gravar a nova politica.

        Returns:
            Dicionario com propostas, validacoes e a politica resultante.
        """
        signals = self.observe()
        propostas = self.recommend(signals)
        resultados: list[ValidationOutcome] = []
        promovidas = 0

        for proposta in propostas:
            resultado = self.validate(proposta, signals.runs)
            if resultado.promoted and promovidas < self.policy.optimizer_max_promotions:
                self.policy = self.policy.with_change(
                    proposta.change["field"], proposta.change["value"])
                promovidas += 1
            elif resultado.promoted:
                resultado = ValidationOutcome(
                    proposta, False, resultado.baseline_score,
                    resultado.candidate_score,
                    f"limite de {self.policy.optimizer_max_promotions} promocao(oes) "
                    "por ciclo atingido")
            resultados.append(resultado)

        if apply and promovidas:
            self.policy.save()

        relatorio = {
            "timestamp": time.time(),
            "runs_analisadas": len(signals.runs),
            "propostas": len(propostas),
            "promovidas": promovidas,
            "aplicado": bool(apply and promovidas),
            "validacoes": [r.to_dict() for r in resultados],
            "politica_resultante": self.policy.to_dict(),
            "sinais": {"stats": signals.stats, "timing": signals.timing,
                       "systemic_errors": signals.systemic_errors},
        }
        self._auditar(relatorio)
        return relatorio

    def _auditar(self, relatorio: dict) -> None:
        """Grava o ciclo no rastro de auditoria append-only."""
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps(relatorio, ensure_ascii=False) + "\n")
