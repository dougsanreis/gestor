"""Memoria de erros: todo erro vira conhecimento permanente.

O objetivo desta camada e eliminar a repeticao de falhas ja resolvidas. Cada
falha e reduzida a uma assinatura estavel; quando a mesma assinatura reaparece,
o motor de reparo tenta primeiro a correcao que ja funcionou antes e a
governanca trata a recorrencia como falha sistemica, nao como acidente.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from syra.paths import state_dir

# Trechos que variam entre execucoes e por isso sao removidos da assinatura.
_VOLATILE = (
    re.compile(r"0x[0-9a-fA-F]+"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}\b"),
    re.compile(r"/tmp/[^\s'\"]+"),
    re.compile(r"\b\d{9,}\b"),
    re.compile(r"line \d+"),
)


def signature(kind: str, message: str, location: str = "") -> str:
    """Reduz uma falha a uma assinatura estavel entre execucoes.

    Numeros de linha, enderecos de memoria, timestamps e caminhos temporarios
    sao removidos para que a mesma causa raiz colida na mesma assinatura.
    """
    normalized = message.strip()
    for pattern in _VOLATILE:
        normalized = pattern.sub("<v>", normalized)
    normalized = re.sub(r"\s+", " ", normalized)[:400]
    payload = f"{kind}|{location}|{normalized}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{kind}:{digest}"


@dataclass
class ErrorRecord:
    """Conhecimento acumulado sobre uma classe de falha."""

    sig: str
    kind: str
    message: str
    location: str
    occurrences: int = 1
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    resolved_by: str | None = None
    resolutions: list[str] = field(default_factory=list)
    prevention: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ErrorRecord:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


class ErrorMemory:
    """Armazena e consulta o conhecimento sobre falhas ja vistas."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (state_dir() / "error_memory.json")
        self._records: dict[str, ErrorRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Memoria corrompida nunca derruba o pipeline: recomeca vazia e
            # preserva o arquivo anterior para inspecao humana.
            corrupt = self.path.with_suffix(".corrupt.json")
            try:
                self.path.replace(corrupt)
            except OSError:
                pass
            return
        for item in raw.get("records", []):
            try:
                record = ErrorRecord.from_dict(item)
            except TypeError:
                continue
            self._records[record.sig] = record

    def save(self) -> None:
        """Persiste a memoria de forma atomica."""
        payload = {
            "version": 1,
            "updated_at": time.time(),
            "records": [r.to_dict() for r in self._records.values()],
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def record(self, kind: str, message: str, location: str = "") -> ErrorRecord:
        """Registra uma ocorrencia de falha e devolve o conhecimento acumulado."""
        sig = signature(kind, message, location)
        existing = self._records.get(sig)
        if existing is None:
            existing = ErrorRecord(sig=sig, kind=kind, message=message.strip()[:400],
                                   location=location)
            self._records[sig] = existing
        else:
            existing.occurrences += 1
            existing.last_seen = time.time()
        self.save()
        return existing

    def resolve(self, sig: str, strategy: str, prevention: str = "") -> None:
        """Marca que ``strategy`` corrigiu a falha ``sig``.

        A estrategia vencedora e movida para o topo da lista, de modo que o
        motor de reparo sempre tente primeiro o que ja funcionou.
        """
        record = self._records.get(sig)
        if record is None:
            return
        record.resolved_by = strategy
        if strategy in record.resolutions:
            record.resolutions.remove(strategy)
        record.resolutions.insert(0, strategy)
        if prevention:
            record.prevention = prevention
        self.save()

    def known_fix(self, kind: str, message: str, location: str = "") -> str | None:
        """Retorna a estrategia que ja resolveu esta falha, se houver."""
        record = self._records.get(signature(kind, message, location))
        return record.resolved_by if record else None

    def get(self, sig: str) -> ErrorRecord | None:
        return self._records.get(sig)

    def is_recurrent(self, sig: str, threshold: int = 3) -> bool:
        """Indica se a falha ja se repetiu o bastante para ser sistemica."""
        record = self._records.get(sig)
        return bool(record and record.occurrences >= threshold and not record.resolved_by)

    def systemic_failures(self, threshold: int = 3) -> list[ErrorRecord]:
        """Falhas recorrentes e ainda sem correcao conhecida."""
        return sorted(
            (r for r in self._records.values()
             if r.occurrences >= threshold and not r.resolved_by),
            key=lambda r: r.occurrences,
            reverse=True,
        )

    def top(self, limit: int = 10) -> list[ErrorRecord]:
        return sorted(self._records.values(), key=lambda r: r.occurrences,
                      reverse=True)[:limit]

    def __len__(self) -> int:
        return len(self._records)
