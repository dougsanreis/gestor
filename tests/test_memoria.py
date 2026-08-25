"""Testes da memoria de erros e do historico de execucoes."""

from __future__ import annotations

from syra.memory.error_memory import ErrorMemory, signature
from syra.memory.run_store import RunRecord, RunStore


def test_assinatura_ignora_numero_de_linha_e_endereco():
    a = signature("assertion", "assert 1 == 2 at line 40 in 0xdeadbeef", "t.py")
    b = signature("assertion", "assert 1 == 2 at line 999 in 0xcafef00d", "t.py")
    assert a == b


def test_assinatura_distingue_causas_diferentes():
    assert signature("assertion", "assert 1 == 2") != signature("assertion",
                                                                "assert 3 == 4")


def test_ocorrencias_acumulam_na_mesma_assinatura():
    memoria = ErrorMemory()
    memoria.record("import", "No module named x", "a.py")
    registro = memoria.record("import", "No module named x", "a.py")
    assert registro.occurrences == 2


def test_recorrencia_vira_falha_sistemica():
    memoria = ErrorMemory()
    for _ in range(3):
        registro = memoria.record("import", "No module named x", "a.py")
    assert memoria.is_recurrent(registro.sig, threshold=3)
    assert memoria.systemic_failures(3)


def test_correcao_conhecida_encerra_a_recorrencia():
    memoria = ErrorMemory()
    for _ in range(3):
        registro = memoria.record("import", "No module named x", "a.py")
    memoria.resolve(registro.sig, "ressintetizar_projeto")
    assert memoria.is_recurrent(registro.sig, threshold=3) is False
    assert memoria.known_fix("import", "No module named x",
                             "a.py") == "ressintetizar_projeto"


def test_memoria_sobrevive_a_arquivo_corrompido():
    memoria = ErrorMemory()
    memoria.record("x", "y")
    memoria.path.write_text("{ isto nao e json", encoding="utf-8")
    recuperada = ErrorMemory(memoria.path)
    assert len(recuperada) == 0
    assert memoria.path.with_suffix(".corrupt.json").exists()


def test_memoria_persiste_entre_instancias():
    primeira = ErrorMemory()
    primeira.record("tipo", "mensagem", "local")
    assert len(ErrorMemory(primeira.path)) == 1


def _registro(**kwargs) -> RunRecord:
    base = dict(run_id="r", mission_id="m", kind="library", verdict="APPROVED",
                delivered=True, duration=1.0, tests_total=10, tests_passed=10,
                tests_failed=0, review_blocking=0, repair_attempts=0)
    base.update(kwargs)
    return RunRecord(**base)


def test_historico_vazio_devolve_estatisticas_neutras():
    assert RunStore().stats()["runs"] == 0


def test_estatisticas_agregam_entrega_e_duracao():
    store = RunStore()
    store.append(_registro(run_id="a", duration=2.0))
    store.append(_registro(run_id="b", duration=4.0, delivered=False,
                           verdict="BLOCKED", tests_failed=2, tests_passed=8,
                           gate_failures=["testes"]))
    stats = store.stats()
    assert stats["runs"] == 2
    assert stats["delivery_rate"] == 0.5
    assert stats["median_duration"] == 3.0
    assert stats["top_gate_failures"] == {"testes": 1}


def test_historico_ignora_linha_corrompida():
    store = RunStore()
    store.append(_registro())
    with store.path.open("a", encoding="utf-8") as arquivo:
        arquivo.write("linha invalida\n")
    assert len(store.all()) == 1
