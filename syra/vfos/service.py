"""Servico de missao: o slice vertical completo.

Criar -> validar contrato -> verificar envelope -> persistir com evento no
mesmo commit -> consultar estado. Cada passo tem dono unico e o servico nao
duplica regra que ja vive no agregado ou na politica.

Idempotencia na criacao e responsabilidade daqui, nao do agregado: a mesma
chave de idempotencia devolve a missao ja criada em vez de criar outra.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from syra.vfos import contracts, ids, policy
from syra.vfos.mission import (
    EnvelopeExcedido,
    Estado,
    Mission,
    TransicaoInvalida,
    evento_de_transicao,
)
from syra.vfos.store import MissaoNaoEncontrada, MissionRepository
from syra.vfos.telemetry import TRACER, Tracer


@dataclass(frozen=True)
class ResultadoCriacao:
    """Saida da criacao, distinguindo criacao nova de repeticao idempotente."""

    mission: Mission
    criada: bool
    decisao: dict[str, Any] | None = None


class MissionService:
    """Orquestra criacao e transicao de missoes sobre um repositorio."""

    def __init__(self, repositorio: MissionRepository,
                 tracer: Tracer | None = None) -> None:
        self.repositorio = repositorio
        self.tracer = tracer or TRACER

    def criar(self, payload: dict[str, Any],
              idempotency_key: str | None = None,
              ator: str = "api") -> ResultadoCriacao:
        """Cria uma missao e a leva a PLANNED, emitindo eventos no mesmo commit.

        Args:
            payload: corpo conforme ``mission.schema.json``.
            idempotency_key: repeticao com a mesma chave nao cria outra missao.
            ator: quem originou a criacao.

        Returns:
            O resultado com o agregado e se houve criacao de fato.

        Raises:
            ViolacaoDeContrato: payload fora do contrato.
            EnvelopeExcedido: autonomia acima do teto do risco.
        """
        with self.tracer.span("mission.create",
                              mission_type=payload.get("type"),
                              risk_class=payload.get("risk_class")) as span:
            if idempotency_key and self.repositorio.ja_processado(idempotency_key):
                existente = self.repositorio.obter(payload["tenant_id"],
                                                   payload["mission_id"])
                span.set("idempotent_replay", True)
                return ResultadoCriacao(mission=existente, criada=False)

            # Contrato e envelope sao verificados dentro de Mission.criar.
            mission = Mission.criar(payload)
            span.set("mission_id", mission.mission_id)

            mission = mission.transicionar(Estado.VALIDATING, ator=ator,
                                           motivo="submetida para validacao")
            mission = mission.transicionar(Estado.PLANNED, ator="validator",
                                           motivo="contrato e envelope validados")

            eventos = [evento_de_transicao(mission, t) for t in mission.historico]
            self.repositorio.salvar(mission, eventos, versao_esperada=0)

            if idempotency_key:
                # Marcado apos a gravacao ter sucesso: uma criacao que falhou
                # nao deve bloquear a proxima tentativa com a mesma chave.
                self.repositorio.marcar_processado(idempotency_key,
                                                   mission.mission_id)
            span.set("state", mission.estado.value)
            span.set("events", len(eventos))
            return ResultadoCriacao(mission=mission, criada=True)

    def obter(self, tenant_id: str, mission_id: str) -> Mission:
        """Le uma missao pelo par tenant/id."""
        with self.tracer.span("mission.get", mission_id=mission_id):
            return self.repositorio.obter(tenant_id, mission_id)

    def transicionar(self, tenant_id: str, mission_id: str, destino: Estado, *,
                     ator: str, motivo: str,
                     decisao: dict[str, Any] | None = None) -> Mission:
        """Aplica uma transicao persistida, com evento no mesmo commit.

        Raises:
            MissaoNaoEncontrada: missao inexistente no tenant.
            TransicaoInvalida: transicao fora da tabela ou invariante violada.
            ConflitoDeVersao: outra escrita alterou a missao no meio do caminho.
        """
        with self.tracer.span("mission.transition", mission_id=mission_id,
                              to_state=destino.value) as span:
            atual = self.repositorio.obter(tenant_id, mission_id)
            span.set("from_state", atual.estado.value)

            proxima = atual.transicionar(destino, ator=ator, motivo=motivo,
                                         decisao=decisao)
            evento = evento_de_transicao(proxima, proxima.historico[-1])
            self.repositorio.salvar(proxima, [evento],
                                    versao_esperada=atual.versao)
            span.set("version", proxima.versao)
            return proxima

    def avaliar_e_decidir(self, tenant_id: str, mission_id: str, *,
                          evidence_ids: list[str],
                          blocking_failures: list[str] | None = None,
                          aprovacoes_obtidas: list[str] | None = None,
                          ator: str = "governor") -> tuple[Mission, dict[str, Any]]:
        """Emite a decisao de governanca e move a missao conforme o veredito.

        A missao precisa estar em EVALUATING. O destino nao e escolhido por
        quem chama: e consequencia da decisao emitida pela politica.
        """
        atual = self.repositorio.obter(tenant_id, mission_id)
        if atual.estado is not Estado.EVALUATING:
            raise TransicaoInvalida(
                f"decisao de governanca exige estado EVALUATING, "
                f"encontrado {atual.estado.value}")

        decisao = policy.decidir(
            tenant_id=tenant_id, subject_type="artifact", subject_id=mission_id,
            risk_class=atual.risk_class, autonomy_level=atual.autonomy_level,
            evidence_ids=evidence_ids, blocking_failures=blocking_failures,
            aprovacoes_obtidas=aprovacoes_obtidas, issued_by=ator)

        destino = {
            "APPROVE": Estado.APPROVED,
            "REQUIRE_APPROVAL": Estado.WAITING_APPROVAL,
            "REWORK": Estado.WAITING_APPROVAL,
            "REJECT": Estado.REJECTED,
            "PAUSE": Estado.WAITING_APPROVAL,
            "ROLLBACK": Estado.REJECTED,
        }[decisao["decision"]]

        motivo = f"governanca: {decisao['decision']} ({', '.join(decisao['reason_codes'][:2])})"
        # Somente APPROVED exige a decisao anexada; nas demais ela vira historico.
        anexo = decisao if destino is Estado.APPROVED else None
        mission = self.transicionar(tenant_id, mission_id, destino, ator=ator,
                                    motivo=motivo, decisao=anexo)
        return mission, decisao
