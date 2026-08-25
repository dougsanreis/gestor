"""Politica operacional da SYRA.

Todos os limiares que governam o comportamento do sistema vivem aqui, em
campos numericos. Isso e deliberado: o otimizador so consegue propor e validar
mudancas em sombra porque a politica e um vetor de numeros, nao codigo espalhado.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from syra.paths import state_dir


@dataclass
class Policy:
    """Limiares de decisao aplicados a cada execucao."""

    # --- Portoes de qualidade ---
    min_test_pass_rate: float = 1.0
    max_blocking_findings: int = 0
    require_test_per_public_function: bool = True
    min_public_functions: int = 1

    # --- Reparo ---
    max_repair_attempts: int = 3

    # --- Orcamento de tempo (anti-lentidao) ---
    test_budget_seconds: float = 60.0
    slow_test_threshold: float = 1.0
    speed_regression_factor: float = 2.0

    # --- Governanca ---
    recurrence_threshold: int = 3
    min_confidence_to_approve: float = 0.7
    min_delivery_rate: float = 0.5
    replan_threshold: float = 0.4

    # --- Quarentena de comandos ---
    quarantine_block_score: int = 70
    quarantine_review_score: int = 35

    # --- Otimizador ---
    optimizer_min_runs: int = 5
    optimizer_min_improvement: float = 0.02
    optimizer_max_promotions: int = 2

    @classmethod
    def default_path(cls) -> Path:
        return state_dir() / "policy.json"

    @classmethod
    def load(cls, path: Path | None = None) -> Policy:
        """Carrega a politica do disco, caindo nos padroes quando ausente."""
        target = path or cls.default_path()
        if not target.exists():
            return cls()
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: Path | None = None) -> Path:
        """Persiste a politica de forma atomica."""
        target = path or self.default_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(target)
        return target

    def with_change(self, field_name: str, value: Any) -> Policy:
        """Retorna uma copia com um unico campo alterado (usado em sombra)."""
        if field_name not in {f.name for f in fields(self)}:
            raise KeyError(f"campo de politica desconhecido: {field_name}")
        data = self.to_dict()
        data[field_name] = value
        return Policy(**data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
