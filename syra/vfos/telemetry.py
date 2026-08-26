"""Observabilidade com redaction por padrao.

Principio 7 do CLAUDE.md: PII nao entra em analytics, prompts, logs ou traces.
A redaction aqui e por lista de negacao de chaves e por deteccao de padrao no
valor, aplicada antes de qualquer escrita. Conteudo integral de prompt e de
payload fica desligado por padrao, como recomenda a convencao de GenAI.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

REDIGIDO = "[REDIGIDO]"

# Chaves cujo valor nunca sai em log, metrica ou trace.
CHAVES_SENSIVEIS = frozenset({
    "password", "senha", "secret", "token", "api_key", "apikey", "authorization",
    "cookie", "session_token", "private_key", "credential", "credentials",
    "email", "e_mail", "cpf", "cnpj", "phone", "telefone", "user_id",
    "anonymous_id", "ip", "ip_address", "prompt", "completion", "content",
})

_PADROES_SENSIVEIS = (
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),                       # e-mail
    re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),              # CPF
    re.compile(r"\b(?:sk|pk|ghp|gho|xox[baprs])[-_][A-Za-z0-9_-]{16,}\b"),  # chaves
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{16,}\b", re.I),        # bearer
)

MAX_PROFUNDIDADE = 6


def redigir(valor: Any, profundidade: int = 0) -> Any:
    """Remove dados sensiveis de uma estrutura antes de registra-la.

    Redige por chave (nome conhecido como sensivel) e por conteudo (valor que
    casa com padrao de segredo ou de dado pessoal). Estruturas muito profundas
    sao truncadas: log nao e lugar de despejar objeto inteiro.
    """
    if profundidade > MAX_PROFUNDIDADE:
        return "[PROFUNDO]"
    if isinstance(valor, dict):
        saida = {}
        for chave, item in valor.items():
            if str(chave).lower() in CHAVES_SENSIVEIS:
                saida[chave] = REDIGIDO
            else:
                saida[chave] = redigir(item, profundidade + 1)
        return saida
    if isinstance(valor, (list, tuple)):
        return [redigir(v, profundidade + 1) for v in valor[:50]]
    if isinstance(valor, str):
        texto = valor
        for padrao in _PADROES_SENSIVEIS:
            texto = padrao.sub(REDIGIDO, texto)
        return texto if len(texto) <= 512 else texto[:512] + "…"
    return valor


@dataclass
class Span:
    """Unidade de trabalho instrumentada."""

    nome: str
    trace_id: str
    span_id: str
    inicio: float
    atributos: dict[str, Any] = field(default_factory=dict)
    status: str = "OK"
    erro: str | None = None
    duracao_ms: float = 0.0

    def set(self, chave: str, valor: Any) -> None:
        """Anota um atributo, ja redigido."""
        self.atributos[chave] = redigir(valor)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.nome, "trace_id": self.trace_id, "span_id": self.span_id,
            "duration_ms": round(self.duracao_ms, 3), "status": self.status,
            "error": self.erro, "attributes": self.atributos,
        }


class Tracer:
    """Emissor de spans em JSON de linha unica.

    Deliberadamente simples e sem dependencia: os atributos seguem a convencao
    de nomes do OpenTelemetry, entao trocar por um exporter real e questao de
    adapter, nao de reescrita.
    """

    def __init__(self, destino=None, habilitado: bool | None = None) -> None:
        self.destino = destino or sys.stderr
        if habilitado is None:
            habilitado = os.environ.get("VFOS_TRACE", "0") not in ("0", "", "false")
        self.habilitado = habilitado
        self.spans: list[Span] = []

    @contextmanager
    def span(self, nome: str, trace_id: str | None = None,
             **atributos: Any) -> Iterator[Span]:
        """Abre um span, registra duracao e status, e o emite ao fechar."""
        atual = Span(
            nome=nome,
            trace_id=trace_id or uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            inicio=time.perf_counter(),
            atributos={k: redigir(v) for k, v in atributos.items()},
        )
        try:
            yield atual
        except Exception as erro:
            atual.status = "ERROR"
            atual.erro = f"{type(erro).__name__}: {str(erro)[:200]}"
            raise
        finally:
            atual.duracao_ms = (time.perf_counter() - atual.inicio) * 1000
            self.spans.append(atual)
            if self.habilitado:
                self.destino.write(
                    json.dumps(atual.to_dict(), ensure_ascii=False) + "\n")
                self.destino.flush()


TRACER = Tracer()
