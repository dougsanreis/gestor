"""Fixtures compartilhadas: todo teste roda com estado isolado."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def syra_home_isolado(tmp_path, monkeypatch):
    """Aponta SYRA_HOME para um diretorio temporario em cada teste.

    Sem isso, um teste contaminaria o estado do proximo e do usuario. O
    escopo e por teste, de proposito: isolamento vale mais que o custo de
    criar um diretorio.
    """
    home = tmp_path / "syra_home"
    home.mkdir()
    monkeypatch.setenv("SYRA_HOME", str(home))
    return home


@pytest.fixture()
def missao_simples():
    """Missao pequena e deterministica, usada nos testes de pipeline."""
    from syra.contracts import Gain, Mission

    return Mission(
        objective="biblioteca de validacao de cadastro com CPF e email",
        kind="library",
        gains=(Gain.CAPABILITY,),
    )
