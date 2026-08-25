"""Resolucao de diretorios de estado da SYRA.

Todo estado persistente fica sob ``SYRA_HOME`` (padrao: ``./.syra``), de modo
que testes e execucoes paralelas possam isolar completamente o estado apenas
trocando a variavel de ambiente.
"""

from __future__ import annotations

import os
from pathlib import Path


def syra_home() -> Path:
    """Retorna a raiz de estado da SYRA, criando-a se necessario."""
    raw = os.environ.get("SYRA_HOME")
    root = Path(raw).expanduser() if raw else Path.cwd() / ".syra"
    root.mkdir(parents=True, exist_ok=True)
    return root


def state_dir() -> Path:
    """Diretorio de estado mutavel (memoria de erros, historico, timings)."""
    path = syra_home() / "state"
    path.mkdir(parents=True, exist_ok=True)
    return path


def builds_dir() -> Path:
    """Diretorio onde cada build materializa o projeto gerado."""
    path = syra_home() / "builds"
    path.mkdir(parents=True, exist_ok=True)
    return path


def reports_dir() -> Path:
    """Diretorio de relatorios legiveis por humanos e por maquina."""
    path = syra_home() / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def artifacts_dir() -> Path:
    """Diretorio onde os pacotes .zip entregaveis sao escritos."""
    path = syra_home() / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path
