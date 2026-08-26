"""Agregado Mission: estados, transicoes puras e invariantes.

O ciclo de vida e explicito e fechado. Nao existe transicao implicita, nao
existe estado alcancavel fora da tabela e estado terminal nao aceita saida.
Transicoes sao puras: recebem um agregado e devolvem outro, sem tocar em
banco, relogio global ou rede — o que torna cada invariante testavel sozinha.

A validacao de contrato acontece na criacao, nao no salvamento. Um agregado
so existe se o payload ja satisfez ``mission.schema.json``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

from syra.vfos import contracts, ids, policy


class Estado(str, Enum):
    """Estados do ciclo de vida de uma missao."""

    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EVALUATING = "EVALUATING"
    APPROVED = "APPROVED"
    RELEASED = "RELEASED"
    OBSERVING = "OBSERVING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    ROLLED_BACK = "ROLLED_BACK"


TERMINAIS = frozenset({Estado.COMPLETED, Estado.REJECTED, Estado.CANCELLED,
                       Estado.ROLLED_BACK})

# Tabela fechada de transicoes. Qualquer par ausente e invalido por definicao.
TRANSICOES: dict[Estado, frozenset[Estado]] = {
    Estado.DRAFT: frozenset({Estado.VALIDATING, Estado.CANCELLED}),
    Estado.VALIDATING: frozenset({Estado.PLANNED, Estado.REJECTED,
                                  Estado.CANCELLED}),
    Estado.PLANNED: frozenset({Estado.RUNNING, Estado.CANCELLED}),
    Estado.RUNNING: frozenset({Estado.EVALUATING, Estado.REJECTED,
                               Estado.CANCELLED}),
    Estado.EVALUATING: frozenset({Estado.WAITING_APPROVAL, Estado.APPROVED,
                                  Estado.REJECTED, Estado.CANCELLED}),
    Estado.WAITING_APPROVAL: frozenset({Estado.APPROVED, Estado.REJECTED,
                                        Estado.CANCELLED}),
    Estado.APPROVED: frozenset({Estado.RELEASED, Estado.CANCELLED}),
    Estado.RELEASED: frozenset({Estado.OBSERVING, Estado.ROLLED_BACK}),
    Estado.OBSERVING: frozenset({Estado.COMPLETED, Estado.ROLLED_BACK}),
    Estado.COMPLETED: frozenset(),
    Estado.REJECTED: frozenset(),
    Estado.CANCELLED: frozenset(),
    Estado.ROLLED_BACK: frozenset(),
}


class TransicaoInvalida(ValueError):
    """A transicao pedida nao existe na tabela ou viola uma invariante."""


class EnvelopeExcedido(ValueError):
    """A missao pede autonomia acima do teto da propria classe de risco."""


@dataclass(frozen=True)
class Transicao:
    """Registro imutavel de uma mudanca de estado."""

    de: Estado
    para: Estado
    ator: str
    motivo: str
    em: str
    decision_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"from": self.de.value, "to": self.para.value, "actor": self.ator,
                "reason": self.motivo, "at": self.em,
                "decision_id": self.decision_id}


@dataclass(frozen=True)
class Mission:
    """Agregado de missao: payload validado, estado e historico."""

    payload: dict[str, Any]
    estado: Estado = Estado.DRAFT
    versao: int = 1
    historico: tuple[Transicao, ...] = field(default_factory=tuple)

    @property
    def mission_id(self) -> str:
        return self.payload["mission_id"]

    @property
    def tenant_id(self) -> str:
        return self.payload["tenant_id"]

    @property
    def risk_class(self) -> str:
        return self.payload["risk_class"]

    @property
    def autonomy_level(self) -> str:
        return self.payload["autonomy_level"]

    @property
    def terminal(self) -> bool:
        return self.estado in TERMINAIS

    @classmethod
    def criar(cls, payload: dict[str, Any]) -> Mission:
        """Cria a missao a partir de um payload, validando contrato e envelope.

        Raises:
            ViolacaoDeContrato: payload fora de ``mission.schema.json``.
            EnvelopeExcedido: autonomia acima do teto da classe de risco.
        """
        contracts.get("mission").exigir(payload)

        envelope = policy.verificar_envelope(payload["risk_class"],
                                             payload["autonomy_level"])
        if not envelope.permitido:
            raise EnvelopeExcedido(envelope.motivo)

        return cls(payload=dict(payload), estado=Estado.DRAFT, versao=1)

    def pode_ir_para(self, destino: Estado) -> bool:
        """Indica se a transicao existe na tabela."""
        return destino in TRANSICOES[self.estado]

    def destinos(self) -> tuple[Estado, ...]:
        """Estados alcancaveis a partir do estado atual."""
        return tuple(sorted(TRANSICOES[self.estado], key=lambda e: e.value))

    def transicionar(self, destino: Estado, *, ator: str, motivo: str,
                     decisao: dict[str, Any] | None = None,
                     em: str | None = None) -> Mission:
        """Aplica uma transicao e devolve um novo agregado.

        Args:
            destino: estado alvo.
            ator: quem provocou a transicao (humano ou agente).
            motivo: justificativa curta, registrada no historico.
            decisao: GovernanceDecision exigida nas transicoes de aprovacao.
            em: timestamp; por padrao, o instante atual em UTC.

        Returns:
            Um novo agregado; o original permanece intocado.

        Raises:
            TransicaoInvalida: transicao fora da tabela ou invariante violada.
        """
        if self.terminal:
            raise TransicaoInvalida(
                f"{self.estado.value} e terminal: nenhuma transicao e possivel")
        if not self.pode_ir_para(destino):
            permitidos = ", ".join(e.value for e in self.destinos())
            raise TransicaoInvalida(
                f"transicao {self.estado.value} -> {destino.value} nao existe. "
                f"permitidos: {permitidos}")
        if not motivo or len(motivo) < 3:
            raise TransicaoInvalida("toda transicao exige motivo registrado")

        self._checar_invariantes(destino, decisao)

        transicao = Transicao(
            de=self.estado, para=destino, ator=ator, motivo=motivo,
            em=em or policy.agora_iso(),
            decision_id=(decisao or {}).get("decision_id"),
        )
        return replace(self, estado=destino, versao=self.versao + 1,
                       historico=self.historico + (transicao,))

    def _checar_invariantes(self, destino: Estado,
                            decisao: dict[str, Any] | None) -> None:
        """Invariantes que a tabela de transicoes sozinha nao expressa."""
        exige_decisao = destino in (Estado.APPROVED, Estado.RELEASED,
                                    Estado.ROLLED_BACK)
        if not exige_decisao:
            return

        if decisao is None:
            raise TransicaoInvalida(
                f"transicao para {destino.value} exige GovernanceDecision")

        contracts.get("governance-decision").exigir(decisao)

        if decisao["subject_id"] != self.mission_id:
            raise TransicaoInvalida(
                f"decisao refere-se a {decisao['subject_id']}, "
                f"nao a {self.mission_id}")
        if decisao["tenant_id"] != self.tenant_id:
            raise TransicaoInvalida("decisao pertence a outro tenant")

        if destino is Estado.APPROVED and decisao["decision"] != "APPROVE":
            raise TransicaoInvalida(
                f"aprovacao exige decisao APPROVE, recebida "
                f"{decisao['decision']}")
        if destino is Estado.ROLLED_BACK and decisao["decision"] not in (
                "ROLLBACK", "PAUSE", "REJECT"):
            raise TransicaoInvalida(
                "rollback exige decisao ROLLBACK, PAUSE ou REJECT")

    def to_dict(self) -> dict[str, Any]:
        """Representacao serializavel do agregado."""
        return {
            "mission": self.payload,
            "state": self.estado.value,
            "version": self.versao,
            "history": [t.to_dict() for t in self.historico],
        }


def evento_de_transicao(mission: Mission, transicao: Transicao,
                        session_id: str = "system-runtime") -> dict[str, Any]:
    """Converte uma transicao em JourneyEvent valido contra o contrato.

    O evento nao carrega o payload da missao: objetivo e escopo podem conter
    texto livre e o contrato de evento so admite valores escalares. Ir alem
    disso seria vazar conteudo para a camada de analytics.
    """
    propriedades = {
        "mission_id": mission.mission_id,
        "from_state": transicao.de.value,
        "to_state": transicao.para.value,
        "actor": transicao.ator,
        "risk_class": mission.risk_class,
        "autonomy_level": mission.autonomy_level,
        "mission_type": mission.payload["type"],
        "version": mission.versao,
    }
    if transicao.decision_id:
        propriedades["decision_id"] = transicao.decision_id

    evento = {
        "event_id": ids.novo_id("event"),
        "event_name": f"mission_{transicao.para.value.lower()}",
        "schema_version": "1.0.0",
        "occurred_at": transicao.em,
        "tenant_id": mission.tenant_id,
        "anonymous_id": None,
        "user_id": transicao.ator[:128],
        "session_id": session_id,
        # Missao nao e trafego de visitante: sem consentimento de marketing.
        "consent_state": {"analytics": True, "personalization": False,
                          "marketing": False},
        "properties": propriedades,
        "context": {"locale": None, "device_class": None, "source_group": "runtime"},
        "idempotency_key": ids.idempotency_key({
            "mission_id": mission.mission_id,
            "version": mission.versao,
            "to": transicao.para.value,
        }),
    }
    contracts.get("event").exigir(evento)
    return evento
