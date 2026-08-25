"""Arquiteto: transforma uma missao em plano executavel.

O arquiteto nao escreve codigo. Ele decide o que sera construido, com base em
correspondencia entre o objetivo da missao e o catalogo de capacidades, e
produz um ``BuildSpec`` que o sintetizador consegue materializar sem ambiguidade.
"""

from __future__ import annotations

import re
import unicodedata

from syra.contracts import BuildSpec, FunctionSpec, Mission, ModuleSpec
from syra.factory.catalog import CAPABILITIES, Capability

# Palavras sem poder discriminante que so geram ruido na correspondencia.
_STOPWORDS = {
    "de", "da", "do", "das", "dos", "para", "com", "sem", "um", "uma", "os", "as",
    "que", "por", "em", "no", "na", "nos", "nas", "e", "ou", "ao", "aos", "the",
    "criar", "crie", "fazer", "gerar", "sistema", "software", "projeto", "modulo",
    "quero", "preciso", "novo", "nova",
}

# Conjuntos minimos por tipo de projeto, usados quando a missao e generica.
_FALLBACK = {
    "library": ("gerar_slug", "remover_duplicados", "dividir_em_lotes"),
    "cli": ("gerar_slug", "resumir_indicadores", "dividir_em_lotes"),
    "service": ("paginar", "filtrar_registros", "resumir_indicadores"),
}

MIN_CAPABILITIES = 3
MAX_CAPABILITIES = 8


def _tokens(text: str) -> set[str]:
    """Extrai tokens normalizados (sem acento, sem stopword) de um texto."""
    normalizado = unicodedata.normalize("NFKD", text.lower())
    sem_acento = "".join(c for c in normalizado if not unicodedata.combining(c))
    brutos = re.findall(r"[a-z0-9]+", sem_acento)
    return {t for t in brutos if len(t) > 2 and t not in _STOPWORDS}


def _score(capability: Capability, tokens: set[str]) -> int:
    """Pontua a aderencia de uma capacidade ao objetivo da missao."""
    score = 0
    for keyword in capability.keywords:
        if keyword in tokens:
            score += 3
        elif any(token.startswith(keyword[:5]) for token in tokens if len(keyword) >= 5):
            score += 1
    if any(token in capability.name for token in tokens):
        score += 4
    return score


class Architect:
    """Seleciona capacidades e organiza o plano de construcao."""

    def __init__(self, capabilities: tuple[Capability, ...] = CAPABILITIES) -> None:
        self.capabilities = capabilities

    def select(self, mission: Mission) -> tuple[Capability, ...]:
        """Escolhe as capacidades que atendem a missao.

        A selecao e ordenada por aderencia. Quando nenhuma capacidade casa com
        o objetivo, o arquiteto cai num conjunto minimo coerente com o tipo do
        projeto, em vez de entregar um pacote vazio.
        """
        tokens = _tokens(mission.objective)
        pontuadas = [(self._rank(c, tokens), c) for c in self.capabilities]
        escolhidas = [c for score, c in sorted(pontuadas, key=lambda p: -p[0]) if score > 0]

        if not escolhidas:
            nomes = _FALLBACK.get(mission.kind, _FALLBACK["library"])
            escolhidas = [c for c in self.capabilities if c.name in nomes]

        if len(escolhidas) < MIN_CAPABILITIES:
            restantes = [c for c in self.capabilities if c not in escolhidas]
            escolhidas.extend(restantes[: MIN_CAPABILITIES - len(escolhidas)])

        return tuple(escolhidas[:MAX_CAPABILITIES])

    @staticmethod
    def _rank(capability: Capability, tokens: set[str]) -> int:
        return _score(capability, tokens)

    def plan(self, mission: Mission) -> BuildSpec:
        """Produz o ``BuildSpec`` completo para a missao."""
        selecionadas = self.select(mission)

        agrupadas: dict[str, list[Capability]] = {}
        for capability in selecionadas:
            agrupadas.setdefault(capability.module, []).append(capability)

        modules = tuple(
            ModuleSpec(
                name=nome,
                purpose=f"Capacidades de {nome} exigidas pela missao.",
                functions=tuple(
                    FunctionSpec(
                        name=c.name,
                        summary=c.summary,
                        signature=c.signature,
                        returns=c.returns,
                        capability=c.name,
                        examples=c.examples,
                    )
                    for c in itens
                ),
            )
            for nome, itens in sorted(agrupadas.items())
        )

        entrypoint = None
        if mission.kind == "cli":
            entrypoint = f"{mission.package_name}.cli:main"
        elif mission.kind == "service":
            entrypoint = f"{mission.package_name}.service:main"

        rationale = (
            f"{len(selecionadas)} capacidade(s) selecionada(s) por aderencia ao "
            f"objetivo, distribuidas em {len(modules)} modulo(s)."
        )

        return BuildSpec(
            mission=mission,
            package_name=mission.package_name,
            kind=mission.kind,
            modules=modules,
            entrypoint=entrypoint,
            rationale=rationale,
        )
