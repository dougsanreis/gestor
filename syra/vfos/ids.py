"""Identificadores tipados, com prefixo exigido pelos contratos.

Os schemas do Vibe Funnel OS exigem prefixos (``mis_``, ``ten_``, ``evt_``).
Gerar o ID no lugar certo evita que um payload chegue ao validador so para
ser rejeitado por formato — e evita colisao de tipos entre entidades.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

PREFIXOS = {
    "mission": "mis", "tenant": "ten", "event": "evt", "artifact": "art",
    "experiment": "exp", "decision": "gov", "release": "rel", "claim": "clm",
    "learning": "lrn", "approval": "apr", "run": "run",
}


def novo_id(entidade: str, entropia: int = 12) -> str:
    """Gera um identificador para ``entidade`` com o prefixo do contrato.

    Raises:
        KeyError: quando a entidade nao tem prefixo definido, o que impediria
            o payload de passar no schema.
    """
    prefixo = PREFIXOS[entidade]
    return f"{prefixo}_{secrets.token_urlsafe(entropia).replace('-', '').replace('_', '')[:16]}"


def idempotency_key(payload: Any) -> str:
    """Chave de idempotencia estavel no formato exigido pelo contrato de evento.

    Usa serializacao canonica: a mesma carga logica produz a mesma chave
    independentemente da ordem das chaves do dicionario.
    """
    canonico = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def sha256_texto(texto: str) -> str:
    """Hash hexadecimal de um texto, no formato aceito pelos contratos."""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()
