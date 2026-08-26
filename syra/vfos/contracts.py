"""Registro de contratos: os JSON Schemas sao a fonte de verdade.

Os schemas sao lidos de ``contracts/`` sem modificacao. O registro recusa
carregar um schema que use palavra-chave nao aplicada pelo validador, para
que nenhum contrato passe menos validado do que declara.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from syra.vfos.jsonschema_lite import Violation, assert_suportado, validate


class ContratoAusente(FileNotFoundError):
    """O diretorio de contratos nao foi encontrado."""


class ViolacaoDeContrato(ValueError):
    """Um payload nao satisfaz o contrato declarado."""

    def __init__(self, contrato: str, violacoes: list[Violation]) -> None:
        self.contrato = contrato
        self.violacoes = violacoes
        detalhe = "; ".join(str(v) for v in violacoes[:5])
        super().__init__(f"{contrato}: {len(violacoes)} violacao(oes): {detalhe}")

    def to_dict(self) -> dict[str, Any]:
        return {"contract": self.contrato,
                "violations": [v.to_dict() for v in self.violacoes]}


def contracts_dir() -> Path:
    """Diretorio dos contratos, sobrescrevivel por ``VFOS_CONTRACTS_DIR``."""
    bruto = os.environ.get("VFOS_CONTRACTS_DIR")
    if bruto:
        return Path(bruto).expanduser().resolve()
    # Sobe de syra/vfos/ ate a raiz do repositorio.
    return Path(__file__).resolve().parents[2] / "contracts"


@dataclass(frozen=True)
class Contrato:
    """Um schema carregado e aprovado pelo validador estrito."""

    nome: str
    schema: dict
    caminho: Path

    def validar(self, payload: Any) -> list[Violation]:
        """Devolve todas as violacoes do payload contra este contrato."""
        return validate(payload, self.schema)

    def exigir(self, payload: Any) -> None:
        """Valida e levanta ``ViolacaoDeContrato`` quando houver violacao."""
        violacoes = self.validar(payload)
        if violacoes:
            raise ViolacaoDeContrato(self.nome, violacoes)


@lru_cache(maxsize=1)
def _carregar() -> dict[str, Contrato]:
    raiz = contracts_dir()
    if not raiz.is_dir():
        raise ContratoAusente(f"diretorio de contratos ausente: {raiz}")

    registro: dict[str, Contrato] = {}
    for caminho in sorted(raiz.glob("*.schema.json")):
        schema = json.loads(caminho.read_text(encoding="utf-8"))
        # Fail-closed: schema que o validador nao aplica integralmente nao entra.
        assert_suportado(schema, caminho.name)
        nome = caminho.name.replace(".schema.json", "")
        registro[nome] = Contrato(nome=nome, schema=schema, caminho=caminho)

    if not registro:
        raise ContratoAusente(f"nenhum contrato encontrado em {raiz}")
    return registro


def get(nome: str) -> Contrato:
    """Recupera um contrato pelo nome (ex.: ``mission``, ``event``).

    Raises:
        KeyError: quando o contrato nao existe, com a lista dos disponiveis.
    """
    registro = _carregar()
    if nome not in registro:
        raise KeyError(f"contrato desconhecido: {nome}. "
                       f"disponiveis: {sorted(registro)}")
    return registro[nome]


def todos() -> dict[str, Contrato]:
    """Todos os contratos carregados."""
    return dict(_carregar())


def recarregar() -> None:
    """Limpa o cache; usado em teste ao trocar o diretorio de contratos."""
    _carregar.cache_clear()
