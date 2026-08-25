"""Motor de variantes: a pagina se remodela conforme a audiencia, com evidencia.

"Remodelar conforme a audiencia" so tem valor se a escolha for estatistica, e
nao palpite. Aqui a decisao usa o limite inferior do intervalo de Wilson: uma
variante com 1 conversao em 2 visitas nao vence uma com 40 em 200, porque o
limite inferior pune amostra pequena.

Cada segmento de audiencia mantem o proprio placar. A mesma pagina pode servir
angulos diferentes para iniciante e para lider tecnico, porque cada um tem seu
proprio historico de conversao.

Exploracao: variantes sem amostra suficiente sao servidas antes das demais.
Sem isso o motor congela na primeira variante que teve sorte.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from syra.paths import state_dir

Z_95 = 1.959964
AMOSTRA_MINIMA_EXPLORACAO = 30
AMOSTRA_MINIMA_DECISAO = 100
# Fracao do trafego reservada a exploracao continua depois da fase inicial.
# Sem ela o lider monopoliza as exposicoes, os intervalos das demais nunca
# estreitam e o experimento jamais atinge significancia — alem de o motor
# ficar cego a mudanca de audiencia ao longo do tempo.
EXPLORACAO_CONTINUA = 0.15


def wilson(sucessos: int, tentativas: int, z: float = Z_95) -> tuple[float, float]:
    """Intervalo de confianca de Wilson para uma proporcao.

    Preferido ao intervalo normal porque continua valido com poucas amostras e
    com taxas proximas de 0 ou 1 — exatamente o caso de pagina nova.

    Args:
        sucessos: numero de conversoes.
        tentativas: numero de exposicoes.
        z: escore normal correspondente a confianca desejada.

    Returns:
        Limite inferior e superior da proporcao.

    Raises:
        ValueError: quando os valores sao negativos ou sucessos excede tentativas.
    """
    if sucessos < 0 or tentativas < 0:
        raise ValueError("sucessos e tentativas nao podem ser negativos")
    if sucessos > tentativas:
        raise ValueError("sucessos nao pode exceder tentativas")
    if tentativas == 0:
        return 0.0, 1.0

    p = sucessos / tentativas
    denominador = 1 + z * z / tentativas
    centro = (p + z * z / (2 * tentativas)) / denominador
    margem = z * math.sqrt(p * (1 - p) / tentativas
                           + z * z / (4 * tentativas * tentativas)) / denominador
    return max(0.0, centro - margem), min(1.0, centro + margem)


@dataclass
class Placar:
    """Contagem de exposicoes e conversoes de uma variante num segmento."""

    exposicoes: int = 0
    conversoes: int = 0

    @property
    def taxa(self) -> float:
        return self.conversoes / self.exposicoes if self.exposicoes else 0.0

    @property
    def limite_inferior(self) -> float:
        return wilson(self.conversoes, self.exposicoes)[0]

    @property
    def limite_superior(self) -> float:
        return wilson(self.conversoes, self.exposicoes)[1]

    def to_dict(self) -> dict[str, Any]:
        return {"exposicoes": self.exposicoes, "conversoes": self.conversoes,
                "taxa": round(self.taxa, 4),
                "limite_inferior": round(self.limite_inferior, 4),
                "limite_superior": round(self.limite_superior, 4)}


@dataclass(frozen=True)
class Decisao:
    """Resultado da avaliacao de um experimento de variantes."""

    vencedora: str | None
    confiante: bool
    motivo: str
    placares: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class VariantStore:
    """Placar persistente por funil, segmento e variante."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (state_dir() / "funnel_variants.json")
        self._dados: dict[str, dict[str, dict[str, Placar]]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            bruto = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for funil, segmentos in bruto.items():
            self._dados[funil] = {
                segmento: {
                    variante: Placar(int(v.get("exposicoes", 0)),
                                     int(v.get("conversoes", 0)))
                    for variante, v in variantes.items()
                }
                for segmento, variantes in segmentos.items()
            }

    def save(self) -> None:
        """Persiste os placares de forma atomica."""
        payload = {
            funil: {segmento: {variante: {"exposicoes": p.exposicoes,
                                          "conversoes": p.conversoes}
                               for variante, p in variantes.items()}
                    for segmento, variantes in segmentos.items()}
            for funil, segmentos in self._dados.items()
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def _bucket(self, funil: str, segmento: str) -> dict[str, Placar]:
        return self._dados.setdefault(funil, {}).setdefault(segmento, {})

    def registrar(self, funil: str, segmento: str, variante: str,
                  exposicoes: int = 1, conversoes: int = 0) -> Placar:
        """Registra exposicoes e conversoes de uma variante."""
        if conversoes > exposicoes:
            raise ValueError("conversoes nao pode exceder exposicoes")
        placar = self._bucket(funil, segmento).setdefault(variante, Placar())
        placar.exposicoes += exposicoes
        placar.conversoes += conversoes
        self.save()
        return placar

    def placares(self, funil: str, segmento: str) -> dict[str, Placar]:
        """Placares conhecidos de um funil dentro de um segmento."""
        return dict(self._bucket(funil, segmento))

    def escolher(self, funil: str, segmento: str, variantes: list[str],
                 epsilon: float = EXPLORACAO_CONTINUA) -> str:
        """Escolhe qual variante servir agora.

        Duas fases. Primeiro toda variante recebe amostra minima. Depois a
        escolha segue o limite inferior de Wilson, com uma fracao ``epsilon``
        do trafego reservada a variante menos amostrada — o que mantem os
        intervalos vivos e permite detectar mudanca de audiencia.

        Args:
            funil: identificador do funil.
            segmento: audiencia sendo servida agora.
            variantes: variantes disponiveis.
            epsilon: fracao do trafego reservada a exploracao continua.

        Returns:
            O identificador da variante a servir.
        """
        if not variantes:
            raise ValueError("nenhuma variante disponivel")

        placares = self._bucket(funil, segmento)
        inexploradas = [v for v in variantes
                        if placares.get(v, Placar()).exposicoes < AMOSTRA_MINIMA_EXPLORACAO]
        if inexploradas:
            return min(inexploradas,
                       key=lambda v: placares.get(v, Placar()).exposicoes)

        lider = max(variantes, key=lambda v: placares[v].limite_inferior)

        # Exploracao deterministica: a cada N exposicoes do segmento, uma vai
        # para a variante menos amostrada. Deterministico em vez de aleatorio
        # para que o comportamento seja reproduzivel em teste.
        if epsilon > 0:
            passo = max(2, round(1 / epsilon))
            total = sum(p.exposicoes for p in placares.values())
            if total % passo == 0:
                candidatas = [v for v in variantes if v != lider]
                if candidatas:
                    return min(candidatas, key=lambda v: placares[v].exposicoes)
        return lider

    def decidir(self, funil: str, segmento: str,
                amostra_minima: int = AMOSTRA_MINIMA_DECISAO) -> Decisao:
        """Declara uma vencedora apenas quando a separacao e estatistica.

        A vencedora precisa ter limite inferior acima do limite superior de
        todas as demais. Enquanto os intervalos se sobrepoem, o experimento
        continua: declarar vencedor cedo e como aprovar entrega sem teste.
        """
        placares = self._bucket(funil, segmento)
        detalhe = {v: p.to_dict() for v, p in placares.items()}

        if not placares:
            return Decisao(None, False, "nenhuma variante registrada", detalhe)
        if len(placares) == 1:
            unica = next(iter(placares))
            return Decisao(unica, False, "apenas uma variante em teste", detalhe)

        total = sum(p.exposicoes for p in placares.values())
        if total < amostra_minima:
            return Decisao(None, False,
                           f"amostra insuficiente: {total} de {amostra_minima}",
                           detalhe)

        lider = max(placares, key=lambda v: placares[v].limite_inferior)
        teto_dos_outros = max(
            (p.limite_superior for v, p in placares.items() if v != lider),
            default=0.0)

        if placares[lider].limite_inferior > teto_dos_outros:
            return Decisao(lider, True,
                           f"limite inferior de '{lider}' "
                           f"({placares[lider].limite_inferior:.1%}) supera o "
                           f"limite superior das demais ({teto_dos_outros:.1%})",
                           detalhe)
        return Decisao(lider, False,
                       "intervalos ainda se sobrepoem: experimento continua",
                       detalhe)
