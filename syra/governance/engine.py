"""Motor de governanca: transforma metricas em decisao global.

Antes desta camada, cada portao decidia localmente e ninguem respondia
"esta entrega pode ir para producao?". O motor consome revisao, testes,
memoria de erros e historico de execucoes e emite uma unica decisao
auditavel, com confianca calculada e motivos explicitos.
"""

from __future__ import annotations

from typing import Any, Iterable

from syra.contracts import (
    GovernanceDecision,
    Mission,
    QAReport,
    ReviewReport,
    Verdict,
)
from syra.governance.policy import Policy
from syra.memory.error_memory import ErrorMemory


class GovernanceEngine:
    """Decide aprovacao, revisao ou bloqueio a partir de evidencias reais."""

    def __init__(self, policy: Policy | None = None,
                 memory: ErrorMemory | None = None) -> None:
        self.policy = policy or Policy()
        self.memory = memory

    def decide(
        self,
        mission: Mission,
        review: ReviewReport | None,
        qa: QAReport | None,
        *,
        error_signatures: Iterable[str] = (),
        run_stats: dict[str, Any] | None = None,
        untested_functions: Iterable[str] = (),
    ) -> GovernanceDecision:
        """Emite a decisao final da execucao.

        A confianca comeca em 1.0 e cai a cada evidencia negativa. Um veredito
        de aprovacao exige tanto ausencia de bloqueios quanto confianca acima
        do minimo definido em politica.
        """
        reasons: list[str] = []
        blocked: list[str] = []
        recommendations: list[str] = []
        confidence = 1.0

        # Lei fundamental: sem ganho declarado, a execucao nao se justifica.
        if not mission.gains:
            blocked.append("gain_law")
            reasons.append("missao nao declara nenhum ganho: execucao sem justificativa")
            confidence -= 0.5

        # Portao de revisao estatica.
        if review is None:
            blocked.append("review")
            reasons.append("revisao estatica nao foi executada")
            confidence -= 0.4
        else:
            blocking = len(review.blocking)
            if blocking > self.policy.max_blocking_findings:
                blocked.append("review")
                reasons.append(
                    f"revisao encontrou {blocking} achado(s) bloqueante(s) "
                    f"(limite {self.policy.max_blocking_findings})"
                )
                confidence -= min(0.5, 0.12 * blocking)
            if review.public_functions < self.policy.min_public_functions:
                blocked.append("surface")
                reasons.append(
                    f"projeto expoe {review.public_functions} funcao(oes) publica(s), "
                    f"minimo {self.policy.min_public_functions}"
                )
                confidence -= 0.3

        # Portao de testes: a evidencia mais forte de que o software funciona.
        if qa is None:
            blocked.append("tests")
            reasons.append("suite de testes nao foi executada")
            confidence -= 0.5
        else:
            if qa.total == 0:
                blocked.append("tests")
                reasons.append("nenhum teste foi coletado: entrega sem evidencia")
                confidence -= 0.5
            else:
                pass_rate = qa.passed / qa.total
                if pass_rate < self.policy.min_test_pass_rate:
                    blocked.append("tests")
                    reasons.append(
                        f"taxa de aprovacao {pass_rate:.0%} abaixo do minimo "
                        f"{self.policy.min_test_pass_rate:.0%} "
                        f"({qa.failed} falha(s), {qa.errors} erro(s))"
                    )
                    confidence -= min(0.6, 0.6 * (1 - pass_rate))
            if qa.duration > self.policy.test_budget_seconds:
                reasons.append(
                    f"suite levou {qa.duration:.1f}s, acima do orcamento "
                    f"{self.policy.test_budget_seconds:.0f}s"
                )
                recommendations.append(
                    "acionar selecao inteligente de testes: syra learn"
                )
                confidence -= 0.1

        # Cobertura de contrato: toda funcao publica precisa ser exercitada.
        untested = list(untested_functions)
        if self.policy.require_test_per_public_function and untested:
            blocked.append("coverage")
            preview = ", ".join(untested[:5])
            reasons.append(
                f"{len(untested)} funcao(oes) publica(s) sem teste: {preview}"
            )
            confidence -= min(0.4, 0.1 * len(untested))

        # Memoria de erros: recorrencia e falha sistemica, nao acidente.
        if self.memory is not None:
            recurrent = [
                sig for sig in error_signatures
                if self.memory.is_recurrent(sig, self.policy.recurrence_threshold)
            ]
            if recurrent:
                blocked.append("error_memory")
                reasons.append(
                    f"{len(recurrent)} falha(s) recorrente(s) sem correcao conhecida: "
                    "tratar como falha sistemica"
                )
                recommendations.append(
                    "registrar correcao permanente com: syra memory --resolve <sig>"
                )
                confidence -= 0.3

        # Historico: entrega cronicamente baixa exige replanejamento.
        stats = run_stats or {}
        disable_agent: str | None = None
        replan = 0.0
        if stats.get("runs", 0) >= self.policy.optimizer_min_runs:
            delivery_rate = float(stats.get("delivery_rate", 0.0))
            if delivery_rate < self.policy.min_delivery_rate:
                replan = round(self.policy.min_delivery_rate - delivery_rate, 4)
                reasons.append(
                    f"taxa historica de entrega {delivery_rate:.0%} abaixo do minimo "
                    f"{self.policy.min_delivery_rate:.0%}"
                )
                recommendations.append("replanejar: reduzir escopo por missao")
                confidence -= 0.1
            gate_failures = stats.get("top_gate_failures") or {}
            if gate_failures:
                worst, count = next(iter(gate_failures.items()))
                if count >= max(2, int(0.5 * stats["runs"])):
                    disable_agent = worst
                    recommendations.append(
                        f"limitar o agente '{worst}': responsavel por {count} "
                        f"falha(s) em {stats['runs']} execucao(oes)"
                    )

        confidence = round(max(0.0, min(1.0, confidence)), 4)

        if blocked:
            verdict = Verdict.BLOCKED
        elif confidence < self.policy.min_confidence_to_approve:
            verdict = Verdict.NEEDS_REVIEW
            reasons.append(
                f"confianca {confidence:.2f} abaixo do minimo "
                f"{self.policy.min_confidence_to_approve:.2f}"
            )
        else:
            verdict = Verdict.APPROVED
            reasons.append("todos os portoes aprovados com evidencia executada")

        return GovernanceDecision(
            verdict=verdict,
            confidence=confidence,
            reasons=tuple(reasons),
            blocked_gates=tuple(dict.fromkeys(blocked)),
            disable_strategy=replan > self.policy.replan_threshold,
            disable_agent=disable_agent,
            replan_threshold=replan,
            recommendations=tuple(dict.fromkeys(recommendations)),
        )
