"""Motor de politica deterministico: risco x autonomia, fail-closed.

O contrato ``governance-decision`` ja impoe duas travas estruturais: risco
HIGH/CRITICAL exige ao menos uma aprovacao, e APPROVE exige zero falhas
bloqueantes com ao menos uma evidencia. Este modulo produz decisoes que
satisfazem o contrato por construcao — nao por convencao.

Fail-closed nao e slogan: ausencia de politica, de evidencia ou de nivel de
autonomia conhecido resulta em bloqueio, nunca em liberacao por omissao.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from syra.vfos import contracts, ids

POLICY_VERSION = "vfos.policy.v1"

NIVEIS = ("L0", "L1", "L2", "L3", "L4")
RISCOS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

# Autonomia maxima admissivel por classe de risco. Acima disso a missao e
# recusada antes de executar: o envelope e verificado na entrada, nao na saida.
AUTONOMIA_MAXIMA = {
    "LOW": "L4",
    "MEDIUM": "L3",
    "HIGH": "L2",
    "CRITICAL": "L1",
}

# Quem precisa aprovar por classe de risco.
APROVACOES = {
    "LOW": (),
    "MEDIUM": ("owner",),
    "HIGH": ("owner", "security"),
    "CRITICAL": ("owner", "security", "legal"),
}

# Somente risco baixo admite aprovacao automatica, e ainda assim exige
# evidencia. Publicacao em producao nunca e automatica.
AUTO_APROVAVEL = frozenset({"LOW"})

VALIDADE_PADRAO = timedelta(hours=24)


def agora_iso() -> str:
    """Timestamp UTC no formato exigido pelos contratos."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def _futuro_iso(delta: timedelta) -> str:
    instante = datetime.now(timezone.utc).replace(microsecond=0) + delta
    return instante.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Envelope:
    """Resultado da verificacao de envelope de autonomia."""

    permitido: bool
    motivo: str
    autonomia_maxima: str


def verificar_envelope(risk_class: str, autonomy_level: str) -> Envelope:
    """Confere se o nivel de autonomia cabe na classe de risco.

    Args:
        risk_class: LOW, MEDIUM, HIGH ou CRITICAL.
        autonomy_level: L0 a L4.

    Returns:
        O veredito com o motivo legivel e o teto aplicavel.
    """
    if risk_class not in AUTONOMIA_MAXIMA:
        return Envelope(False, f"classe de risco desconhecida: {risk_class}", "L0")
    if autonomy_level not in NIVEIS:
        return Envelope(False, f"nivel de autonomia desconhecido: {autonomy_level}",
                        AUTONOMIA_MAXIMA[risk_class])

    teto = AUTONOMIA_MAXIMA[risk_class]
    if NIVEIS.index(autonomy_level) > NIVEIS.index(teto):
        return Envelope(False,
                        f"autonomia {autonomy_level} excede o teto {teto} "
                        f"para risco {risk_class}", teto)
    return Envelope(True, f"autonomia {autonomy_level} dentro do teto {teto}", teto)


def decidir(
    *,
    tenant_id: str,
    subject_type: str,
    subject_id: str,
    risk_class: str,
    autonomy_level: str,
    evidence_ids: list[str],
    blocking_failures: list[str] | None = None,
    aprovacoes_obtidas: list[str] | None = None,
    validade: timedelta = VALIDADE_PADRAO,
    issued_by: str = "governor",
) -> dict[str, Any]:
    """Emite uma GovernanceDecision valida contra o contrato.

    A decisao segue uma ordem estrita de bloqueio: envelope de autonomia,
    falhas bloqueantes, evidencia, aprovacoes. A primeira condicao violada
    determina o veredito — nenhuma condicao posterior pode "compensar" uma
    anterior.

    Returns:
        O dicionario da decisao, ja validado contra ``governance-decision``.

    Raises:
        ViolacaoDeContrato: se a decisao produzida nao satisfizer o contrato,
            o que indicaria defeito neste motor e nunca deve ser silenciado.
    """
    bloqueios = list(blocking_failures or [])
    obtidas = set(aprovacoes_obtidas or [])
    motivos: list[str] = []

    envelope = verificar_envelope(risk_class, autonomy_level)
    if not envelope.permitido:
        bloqueios.append(envelope.motivo)
        motivos.append("AUTONOMY_ENVELOPE_EXCEEDED")

    exigidas = list(APROVACOES.get(risk_class, ("owner",)))
    faltantes = [a for a in exigidas if a not in obtidas]

    if bloqueios:
        decisao = "REJECT" if not envelope.permitido else "REWORK"
        motivos.append("BLOCKING_FAILURES_PRESENT")
    elif not evidence_ids:
        # Sem evidencia o contrato proibe APPROVE; ser explicito e melhor
        # do que deixar o validador recusar depois.
        decisao = "REQUIRE_APPROVAL"
        motivos.append("EVIDENCE_MISSING")
    elif risk_class not in AUTO_APROVAVEL:
        decisao = "REQUIRE_APPROVAL" if faltantes else "APPROVE"
        motivos.append("HUMAN_APPROVAL_REQUIRED" if faltantes
                       else "APPROVALS_SATISFIED")
    elif faltantes:
        decisao = "REQUIRE_APPROVAL"
        motivos.append("HUMAN_APPROVAL_REQUIRED")
    else:
        decisao = "APPROVE"
        motivos.append("LOW_RISK_AUTO_APPROVED")

    if envelope.permitido:
        motivos.append("AUTONOMY_ENVELOPE_OK")

    payload = {
        "decision_id": ids.novo_id("decision"),
        "tenant_id": tenant_id,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "policy_version": POLICY_VERSION,
        "risk_class": risk_class if risk_class in RISCOS else "CRITICAL",
        "decision": decisao,
        "reason_codes": list(dict.fromkeys(motivos)),
        "blocking_failures": bloqueios,
        # O contrato exige aprovacoes para HIGH/CRITICAL; declaramos as que
        # ainda faltam, que e a informacao acionavel.
        "required_approvals": faltantes if faltantes else list(exigidas),
        "evidence_ids": list(dict.fromkeys(evidence_ids)),
        "issued_by": issued_by,
        "issued_at": agora_iso(),
        "expires_at": _futuro_iso(validade),
    }

    if decisao == "APPROVE":
        # Redundante com o contrato, e proposital: um defeito aqui vira
        # excecao imediata em vez de aprovacao indevida.
        assert not payload["blocking_failures"], "APPROVE com falha bloqueante"
        assert payload["evidence_ids"], "APPROVE sem evidencia"

    contracts.get("governance-decision").exigir(payload)
    return payload
