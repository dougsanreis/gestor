"""Inteligencia de testes: velocidade sem abrir mao de evidencia.

Suites ficam lentas porque ninguem mede. Este modulo mantem o historico de
duracao de cada teste e usa esse historico para tres coisas: escolher um
subconjunto que caiba num orcamento de tempo, apontar os testes que dominam a
suite e detectar regressoes de velocidade.

Restricao deliberada: a selecao nunca e usada como criterio de aprovacao. O
modo rapido serve ao laco de desenvolvimento; a governanca so aprova entrega
com a suite completa executada.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path

from syra.contracts import QAReport
from syra.paths import state_dir

HISTORICO_MAXIMO = 20
# Abaixo deste piso a variacao e ruido de agendamento do sistema operacional,
# nao regressao real. Sem ele, um teste de 10ms que oscila para 30ms geraria
# alarme a cada execucao e o sinal viraria barulho.
PISO_DE_RUIDO = 0.05


@dataclass(frozen=True)
class SlowTest:
    """Teste que consome parcela relevante do tempo da suite."""

    nodeid: str
    median: float
    share: float

    def to_dict(self) -> dict:
        return {"nodeid": self.nodeid, "median": round(self.median, 4),
                "share": round(self.share, 4)}


@dataclass(frozen=True)
class SpeedRegression:
    """Teste que ficou significativamente mais lento que seu proprio historico."""

    nodeid: str
    baseline: float
    latest: float

    @property
    def factor(self) -> float:
        return round(self.latest / self.baseline, 2) if self.baseline else 0.0

    def to_dict(self) -> dict:
        return {"nodeid": self.nodeid, "baseline": round(self.baseline, 4),
                "latest": round(self.latest, 4), "factor": self.factor}


class TestIntelligence:
    """Historico de duracao por teste e decisoes derivadas dele."""

    # Sem anotacao: nao vira campo nem atributo de instancia. Impede o pytest
    # de tentar coletar esta classe como suite so pelo prefixo "Test".
    __test__ = False

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (state_dir() / "test_timing.json")
        self._timings: dict[str, list[float]] = {}
        self._failures: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            dados = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        self._timings = {k: [float(x) for x in v]
                         for k, v in dados.get("timings", {}).items()}
        self._failures = {k: int(v) for k, v in dados.get("failures", {}).items()}

    def save(self) -> None:
        """Persiste o historico de forma atomica."""
        payload = {"timings": self._timings, "failures": self._failures}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def record(self, qa: QAReport) -> None:
        """Incorpora os resultados de uma execucao ao historico."""
        for resultado in qa.outcomes:
            serie = self._timings.setdefault(resultado.nodeid, [])
            serie.append(round(resultado.duration, 6))
            if len(serie) > HISTORICO_MAXIMO:
                del serie[:-HISTORICO_MAXIMO]
            if resultado.status in ("failed", "error"):
                self._failures[resultado.nodeid] = self._failures.get(
                    resultado.nodeid, 0) + 1
            else:
                self._failures.pop(resultado.nodeid, None)
        self.save()

    def median(self, nodeid: str) -> float:
        """Duracao mediana conhecida de um teste; 0.0 quando nunca rodou."""
        serie = self._timings.get(nodeid)
        return statistics.median(serie) if serie else 0.0

    def select(self, nodeids: list[str], budget_seconds: float,
               priorizar_falhas: bool = True) -> list[str]:
        """Escolhe testes que cabem no orcamento de tempo informado.

        A ordem e deliberada: testes que falharam recentemente vem primeiro
        (falham cedo e cortam o ciclo), depois testes ainda sem historico
        (risco desconhecido) e por fim os demais do mais rapido ao mais lento.

        Args:
            nodeids: universo de testes disponiveis.
            budget_seconds: tempo maximo estimado da selecao.
            priorizar_falhas: coloca os testes que falharam recentemente a frente.

        Returns:
            Subconjunto ordenado que cabe no orcamento. Sempre devolve ao menos
            um teste quando ha candidatos, para nunca entregar selecao vazia.
        """
        def chave(nodeid: str) -> tuple[int, float]:
            falhou = self._failures.get(nodeid, 0) if priorizar_falhas else 0
            mediana = self.median(nodeid)
            sem_historico = 0 if mediana else 1
            return (-falhou, -sem_historico, mediana)

        ordenados = sorted(nodeids, key=chave)
        escolhidos: list[str] = []
        acumulado = 0.0
        for nodeid in ordenados:
            custo = self.median(nodeid) or 0.05  # estimativa para teste inedito
            if escolhidos and acumulado + custo > budget_seconds:
                continue
            escolhidos.append(nodeid)
            acumulado += custo
        return escolhidos

    def slow_tests(self, threshold: float = 1.0, limit: int = 10) -> list[SlowTest]:
        """Testes acima do limiar de duracao, ordenados por peso na suite."""
        medianas = {n: self.median(n) for n in self._timings}
        total = sum(medianas.values()) or 1.0
        lentos = [SlowTest(nodeid=n, median=m, share=m / total)
                  for n, m in medianas.items() if m >= threshold]
        return sorted(lentos, key=lambda s: -s.median)[:limit]

    def regressions(self, factor: float = 2.0) -> list[SpeedRegression]:
        """Testes cuja ultima execucao destoa da propria mediana historica."""
        achados: list[SpeedRegression] = []
        for nodeid, serie in self._timings.items():
            if len(serie) < 3:
                continue
            anteriores = serie[:-1]
            base = statistics.median(anteriores)
            ultimo = serie[-1]
            if base >= PISO_DE_RUIDO and ultimo >= factor * base:
                achados.append(SpeedRegression(nodeid=nodeid, baseline=base,
                                               latest=ultimo))
        return sorted(achados, key=lambda r: -r.factor)

    def summary(self, threshold: float = 1.0, factor: float = 2.0) -> dict:
        """Panorama usado pelo relatorio e pelos agentes de otimizacao."""
        medianas = [self.median(n) for n in self._timings]
        return {
            "tests_tracked": len(self._timings),
            "estimated_full_run": round(sum(medianas), 4),
            "slowest": [s.to_dict() for s in self.slow_tests(threshold)],
            "regressions": [r.to_dict() for r in self.regressions(factor)],
            "recent_failures": dict(sorted(self._failures.items(),
                                           key=lambda kv: -kv[1])[:10]),
        }
