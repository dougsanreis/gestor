"""Squad de agentes auto-otimizaveis do funil.

Mesma disciplina da fabrica de software, aplicada a conversao: agentes
especializados observam metricas reais, propoem mudancas, e nenhuma mudanca
entra em producao sem validacao.

Aqui a validacao e estatistica. Um agente pode propor trocar o angulo padrao de
uma pagina, mas a troca so e promovida quando o intervalo de confianca separa a
vencedora das demais. Promover lider sem separacao e o equivalente, no funil, a
aprovar entrega sem teste.

Tres travas contra autossabotagem:

1. ``IntegridadeAgent`` bloqueia publicacao de pagina com prova nao verificada.
   Nenhum agente pode inventar depoimento ou numero para subir conversao.
2. Promocao de variante exige ``Decisao.confiante``, nunca so a maior taxa.
3. Etapas abaixo da meta viram recomendacao explicita, nao ajuste silencioso
   da meta — o sistema nao pode aprender a baixar a propria regua.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from syra.contracts import Recommendation
from syra.funnel.blueprint import FUNIS, Funil
from syra.funnel.copy import Angulo, gerar_copy_vendas
from syra.funnel.personas import por_id as persona_por_id
from syra.funnel.variants import Decisao, VariantStore
from syra.paths import state_dir

ANGULOS = tuple(a.value for a in Angulo)


@dataclass
class ContagemEtapa:
    """Quantas pessoas entraram numa etapa e quantas avancaram."""

    entradas: int = 0
    avancos: int = 0

    @property
    def taxa(self) -> float:
        return self.avancos / self.entradas if self.entradas else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"entradas": self.entradas, "avancos": self.avancos,
                "taxa": round(self.taxa, 4)}


class StageStore:
    """Placar por etapa do funil (TOFU, MOFU, BOFU)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (state_dir() / "funnel_stages.json")
        self._dados: dict[str, dict[str, ContagemEtapa]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            bruto = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        self._dados = {
            funil: {etapa: ContagemEtapa(int(v.get("entradas", 0)),
                                         int(v.get("avancos", 0)))
                    for etapa, v in etapas.items()}
            for funil, etapas in bruto.items()
        }

    def save(self) -> None:
        """Persiste os placares de etapa de forma atomica."""
        payload = {funil: {etapa: {"entradas": c.entradas, "avancos": c.avancos}
                           for etapa, c in etapas.items()}
                   for funil, etapas in self._dados.items()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def registrar(self, funil: str, estagio: str, entradas: int = 1,
                  avancos: int = 0) -> ContagemEtapa:
        """Registra entradas e avancos de uma etapa."""
        if avancos > entradas:
            raise ValueError("avancos nao pode exceder entradas")
        contagem = self._dados.setdefault(funil, {}).setdefault(
            estagio.upper(), ContagemEtapa())
        contagem.entradas += entradas
        contagem.avancos += avancos
        self.save()
        return contagem

    def etapas(self, funil: str) -> dict[str, ContagemEtapa]:
        return dict(self._dados.get(funil, {}))


@dataclass(frozen=True)
class SinaisFunil:
    """Sinais observados de um funil."""

    funil: Funil
    etapas: dict[str, ContagemEtapa]
    decisoes: dict[str, Decisao]  # por segmento

    def to_dict(self) -> dict[str, Any]:
        return {
            "funil": self.funil.id,
            "etapas": {k: v.to_dict() for k, v in self.etapas.items()},
            "decisoes": {k: v.to_dict() for k, v in self.decisoes.items()},
        }


class AgenteFunil(Protocol):
    """Especialista que converte sinais de funil em recomendacoes."""

    name: str

    def recommend(self, sinais: SinaisFunil) -> list[Recommendation]:
        """Propoe mudancas a partir dos sinais observados."""
        ...


def _rec(agent: str, target: str, change: dict, gain: str, confidence: float,
         evidence: list[str]) -> Recommendation:
    return Recommendation(rec_id=uuid.uuid4().hex[:10], agent=agent, target=target,
                          change=change, expected_gain=gain, confidence=confidence,
                          evidence=tuple(evidence))


class CopyAgent:
    """Promove o angulo de copy vencedor, por segmento, quando ha separacao."""

    name = "copy"

    def recommend(self, sinais: SinaisFunil) -> list[Recommendation]:
        propostas: list[Recommendation] = []
        for segmento, decisao in sinais.decisoes.items():
            if not decisao.confiante or decisao.vencedora is None:
                continue
            placar = decisao.placares.get(decisao.vencedora, {})
            propostas.append(_rec(
                self.name, f"{sinais.funil.id}:{segmento}",
                {"tipo": "angulo_padrao", "valor": decisao.vencedora},
                f"pagina servida no angulo com maior taxa comprovada para "
                f"'{segmento}'",
                0.9,
                [decisao.motivo,
                 f"taxa observada {placar.get('taxa', 0):.2%} em "
                 f"{placar.get('exposicoes', 0)} exposicao(oes)"],
            ))
        return propostas


class EtapaAgent:
    """Aponta a etapa que mais perde gente em relacao a propria meta."""

    name = "etapa"

    def recommend(self, sinais: SinaisFunil) -> list[Recommendation]:
        propostas: list[Recommendation] = []
        for etapa in sinais.funil.etapas:
            contagem = sinais.etapas.get(etapa.estagio)
            if contagem is None or contagem.entradas < 50:
                continue
            if contagem.taxa >= etapa.meta:
                continue
            deficit = etapa.meta - contagem.taxa
            propostas.append(_rec(
                self.name, f"{sinais.funil.id}:{etapa.estagio}",
                {"tipo": "etapa_abaixo_da_meta", "estagio": etapa.estagio,
                 "taxa": round(contagem.taxa, 4), "meta": etapa.meta},
                f"recuperar {deficit:.1%} de passagem em {etapa.estagio}",
                min(0.95, 0.5 + deficit * 4),
                [f"{etapa.metrica}: {contagem.taxa:.1%} contra meta "
                 f"{etapa.meta:.1%}",
                 f"{contagem.entradas} entrada(s) observada(s)",
                 f"ativo atual: {etapa.ativo}"],
            ))
        return sorted(propostas, key=lambda r: -r.confidence)


class GargaloAgent:
    """Identifica em qual etapa concentrar esforco antes de mexer no resto."""

    name = "gargalo"

    def recommend(self, sinais: SinaisFunil) -> list[Recommendation]:
        candidatas = [
            (etapa, sinais.etapas[etapa.estagio])
            for etapa in sinais.funil.etapas
            if etapa.estagio in sinais.etapas
            and sinais.etapas[etapa.estagio].entradas >= 50
        ]
        if len(candidatas) < 2:
            return []

        # O gargalo e a etapa com maior distancia relativa da propria meta.
        etapa, contagem = min(candidatas,
                              key=lambda par: par[1].taxa / par[0].meta
                              if par[0].meta else 1.0)
        if contagem.taxa >= etapa.meta:
            return []
        return [_rec(
            self.name, f"{sinais.funil.id}:{etapa.estagio}",
            {"tipo": "gargalo", "estagio": etapa.estagio},
            "maior ganho por esforco esta nesta etapa",
            0.85,
            [f"{etapa.estagio} entrega {contagem.taxa / etapa.meta:.0%} da propria "
             f"meta, pior indice do funil",
             f"corrigir aqui move todas as etapas seguintes"],
        )]


class IntegridadeAgent:
    """Impede que qualquer pagina publique prova que ninguem verificou."""

    name = "integridade"

    def recommend(self, sinais: SinaisFunil) -> list[Recommendation]:
        persona = persona_por_id(sinais.funil.persona_id)
        if persona is None:
            return []
        copy = gerar_copy_vendas(sinais.funil, persona)
        if not copy.provas_pendentes:
            return []
        return [_rec(
            self.name, sinais.funil.id,
            {"tipo": "bloqueio_de_publicacao", "motivo": "prova_nao_verificada"},
            "evita alegacao que nao se sustenta e queima o funil inteiro",
            1.0,
            list(copy.provas_pendentes)
            + ["nenhum agente pode gerar depoimento ou numero de resultado"],
        )]


AGENTES_FUNIL: tuple[AgenteFunil, ...] = (
    CopyAgent(), EtapaAgent(), GargaloAgent(), IntegridadeAgent(),
)


@dataclass
class Padroes:
    """Angulo padrao promovido por funil e segmento."""

    path: Path
    dados: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> Padroes:
        alvo = path or (state_dir() / "funnel_defaults.json")
        if alvo.exists():
            try:
                return cls(path=alvo,
                           dados=json.loads(alvo.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass
        return cls(path=alvo)

    def get(self, funil: str, segmento: str, padrao: str = Angulo.DOR.value) -> str:
        """Angulo promovido para este funil e segmento."""
        return self.dados.get(funil, {}).get(segmento, padrao)

    def set(self, funil: str, segmento: str, angulo: str) -> None:
        """Promove um angulo como padrao."""
        self.dados.setdefault(funil, {})[segmento] = angulo

    def save(self) -> None:
        """Persiste os padroes de forma atomica."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.dados, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(self.path)


class FunnelSquad:
    """Ciclo do squad: observar, recomendar, validar e promover."""

    def __init__(self, variants: VariantStore | None = None,
                 stages: StageStore | None = None,
                 padroes: Padroes | None = None,
                 agentes: tuple[AgenteFunil, ...] = AGENTES_FUNIL,
                 funis: tuple[Funil, ...] = FUNIS) -> None:
        self.variants = variants or VariantStore()
        self.stages = stages or StageStore()
        self.padroes = padroes or Padroes.load()
        self.agentes = agentes
        self.funis = funis

    def servir(self, funil_id: str, segmento: str) -> str:
        """Escolhe qual angulo servir agora para este segmento."""
        return self.variants.escolher(funil_id, segmento, list(ANGULOS))

    def observar(self, funil: Funil, segmentos: list[str]) -> SinaisFunil:
        """Coleta os sinais atuais de um funil."""
        return SinaisFunil(
            funil=funil,
            etapas=self.stages.etapas(funil.id),
            decisoes={s: self.variants.decidir(funil.id, s) for s in segmentos},
        )

    def cycle(self, segmentos: list[str] | None = None,
              apply: bool = True) -> dict[str, Any]:
        """Executa um ciclo completo do squad sobre todos os funis.

        Args:
            segmentos: audiencias a avaliar; por padrao usa a persona de cada funil.
            apply: quando False, recomenda sem promover nenhuma variante.

        Returns:
            Relatorio com recomendacoes, promocoes e bloqueios de publicacao.
        """
        recomendacoes: list[dict[str, Any]] = []
        promovidas: list[dict[str, str]] = []
        bloqueios: list[dict[str, Any]] = []

        for funil in self.funis:
            alvo = segmentos or [funil.persona_id]
            sinais = self.observar(funil, alvo)

            for agente in self.agentes:
                for proposta in agente.recommend(sinais):
                    registro = proposta.to_dict()
                    recomendacoes.append(registro)

                    if proposta.change.get("tipo") == "bloqueio_de_publicacao":
                        bloqueios.append(registro)
                        continue

                    # Promocao so acontece com separacao estatistica confirmada.
                    if proposta.change.get("tipo") == "angulo_padrao" and apply:
                        _, _, segmento = proposta.target.partition(":")
                        decisao = sinais.decisoes.get(segmento)
                        if decisao and decisao.confiante and decisao.vencedora:
                            self.padroes.set(funil.id, segmento, decisao.vencedora)
                            promovidas.append({"funil": funil.id,
                                               "segmento": segmento,
                                               "angulo": decisao.vencedora})

        if apply and promovidas:
            self.padroes.save()

        return {
            "timestamp": time.time(),
            "funis_avaliados": len(self.funis),
            "recomendacoes": recomendacoes,
            "promovidas": promovidas,
            "bloqueios_de_publicacao": bloqueios,
            "padroes": self.padroes.dados,
        }
