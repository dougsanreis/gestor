"""Testes da CLI: os codigos de saida sao contrato com scripts e CI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from syra.cli import (
    CODIGO_BLOQUEADO,
    CODIGO_OK,
    CODIGO_RESSALVA,
    CODIGO_USO,
    main,
)


def test_doctor_aprova_ambiente_valido():
    assert main(["doctor"]) == CODIGO_OK


def test_guard_libera_comando_rotineiro():
    assert main(["guard", "ls", "-la"]) == CODIGO_OK


@pytest.mark.parametrize("comando", [
    ["guard", "rm", "-rf", "/"],
    ["guard", "mkfs.ext4", "/dev/sda"],
    ["guard", "git", "reset", "--hard"],
])
def test_guard_bloqueia_comando_destrutivo(comando):
    assert main(comando) == CODIGO_BLOQUEADO


def test_guard_pede_revisao_em_comando_ambiguo():
    assert main(["guard", "kill", "-9", "999"]) == CODIGO_RESSALVA


def test_guard_recusa_chamada_sem_comando():
    assert main(["guard"]) == CODIGO_USO


def test_guard_em_json_devolve_estrutura_completa(capsys):
    main(["guard", "--json", "rm", "-rf", "/"])
    dados = json.loads(capsys.readouterr().out)
    assert dados["level"] == "BLOCK"
    assert dados["matched_rules"]
    assert dados["safe_alternative"]


def test_build_aprova_missao_valida():
    assert main(["build", "validar CPF e email no cadastro",
                 "--gain", "capability"]) == CODIGO_OK


def test_build_em_json_reporta_artefato(capsys):
    main(["build", "--json", "validar CPF e email", "--gain", "capability"])
    dados = json.loads(capsys.readouterr().out)
    assert dados["delivered"] is True
    assert dados["decision"]["verdict"] == "APPROVED"
    assert dados["manifest"]["artifact_sha256"]


def test_build_recusa_ganho_invalido():
    with pytest.raises(SystemExit):
        main(["build", "x", "--gain", "ganho_inexistente"])


def test_report_funciona_com_sistema_zerado():
    assert main(["report"]) == CODIGO_OK


def test_learn_funciona_sem_historico():
    assert main(["learn", "--dry-run"]) == CODIGO_OK


def test_funnel_list_descreve_dores_e_funis(capsys):
    assert main(["funnel", "list", "--json"]) == CODIGO_OK
    dados = json.loads(capsys.readouterr().out)
    assert len(dados["funis"]) == 3
    assert dados["dores"]


def test_funnel_page_gera_arquivos(tmp_path, capsys):
    codigo = main(["funnel", "page", "--funil", "fim_do_loop_de_erro",
                   "--out", str(tmp_path), "--json"])
    dados = json.loads(capsys.readouterr().out)
    # Ressalva, nao aprovacao: as paginas saem com prova pendente.
    assert codigo == CODIGO_RESSALVA
    assert len(dados["paginas"]) == 4
    assert all(Path(p["arquivo"]).exists() for p in dados["paginas"])


def test_funnel_page_recusa_funil_desconhecido(tmp_path):
    assert main(["funnel", "page", "--funil", "nao_existe",
                 "--out", str(tmp_path)]) == CODIGO_USO


def test_funnel_track_e_serve_operam_juntos(capsys):
    assert main(["funnel", "track", "--funil", "f", "--segmento", "s",
                 "--angulo", "dor", "--exposicoes", "10",
                 "--conversoes", "3"]) == CODIGO_OK
    capsys.readouterr()
    assert main(["funnel", "serve", "--funil", "f",
                 "--segmento", "s", "--json"]) == CODIGO_OK
    dados = json.loads(capsys.readouterr().out)
    assert dados["angulo"] in {"dor", "promessa", "mecanismo"}


def test_funnel_track_recusa_conversao_maior_que_exposicao():
    assert main(["funnel", "track", "--funil", "f", "--angulo", "dor",
                 "--exposicoes", "1", "--conversoes", "9"]) == CODIGO_USO


def test_funnel_optimize_bloqueia_com_prova_pendente():
    assert main(["funnel", "optimize", "--dry-run"]) == CODIGO_BLOQUEADO
