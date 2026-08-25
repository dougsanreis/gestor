"""Historico de execucoes: a base factual da governanca e do otimizador.

Sem historico, governanca vira regra fixa e otimizacao vira palpite. Toda
execucao da fabrica grava aqui um registro compacto e append-only que pode ser
reproduzido depois para validar mudancas de politica em sombra.
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from syra.paths import state_dir


@dataclass
class RunRecord:
    """Fotografia compacta de uma execucao da fabrica."""

    run_id: str
    mission_id: str
    kind: str
    verdict: str
    delivered: bool
    duration: float
    tests_total: int
    tests_passed: int
    tests_failed: int
    review_blocking: int
    repair_attempts: int
    gate_failures: list[str] = field(default_factory=list)
    error_signatures: list[str] = field(default_factory=list)
    synthesizer: str = "blueprint"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunRecord:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


class RunStore:
    """Armazenamento append-only (JSONL) do historico de execucoes."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (state_dir() / "runs.jsonl")

    def append(self, record: RunRecord) -> None:
        """Adiciona um registro ao historico."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def all(self) -> list[RunRecord]:
        """Le todo o historico, ignorando linhas corrompidas."""
        if not self.path.exists():
            return []
        records: list[RunRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(RunRecord.from_dict(json.loads(line)))
            except (json.JSONDecodeError, TypeError):
                continue
        return records

    def recent(self, limit: int = 50) -> list[RunRecord]:
        return self.all()[-limit:]

    def stats(self, limit: int = 50) -> dict[str, Any]:
        """Metricas agregadas usadas por governanca e otimizador."""
        records = self.recent(limit)
        if not records:
            return {
                "runs": 0,
                "delivery_rate": 0.0,
                "green_rate": 0.0,
                "avg_duration": 0.0,
                "median_duration": 0.0,
                "avg_repairs": 0.0,
                "top_gate_failures": {},
            }
        durations = [r.duration for r in records]
        delivered = sum(1 for r in records if r.delivered)
        green = sum(1 for r in records if r.tests_failed == 0 and r.tests_total > 0)
        gate_counter: dict[str, int] = {}
        for record in records:
            for gate in record.gate_failures:
                gate_counter[gate] = gate_counter.get(gate, 0) + 1
        return {
            "runs": len(records),
            "delivery_rate": round(delivered / len(records), 4),
            "green_rate": round(green / len(records), 4),
            "avg_duration": round(sum(durations) / len(durations), 4),
            "median_duration": round(statistics.median(durations), 4),
            "avg_repairs": round(
                sum(r.repair_attempts for r in records) / len(records), 4
            ),
            "top_gate_failures": dict(
                sorted(gate_counter.items(), key=lambda kv: kv[1], reverse=True)
            ),
        }
