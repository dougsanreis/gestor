"""Testes da selecao inteligente de testes e da auto-otimizacao governada."""

from __future__ import annotations

import pytest

from syra.contracts import QAReport, TestOutcome
from syra.governance.policy import Policy
from syra.intelligence.optimizer import (
    CAMPOS_CONGELADOS,
    Optimizer,
    _teria_entregue,
    _viola_invariante,
    score,
)
from syra.intelligence.test_selector import TestIntelligence
from syra.memory.run_store import RunRecord, RunStore


def _relatorio(dados: list[tuple[str, float, str]]) -> QAReport:
    return QAReport(runner="pytest", passed=sum(1 for d in dados if d[2] == "passed"),
                    failed=sum(1 for d in dados if d[2] == "failed"), errors=0,
                    skipped=0, duration=sum(d[1] for d in dados),
                    outcomes=tuple(TestOutcome(n, s, t) for n, t, s in dados))


@pytest.fixture()
def inteligencia():
    ti = TestIntelligence()
    for _ in range(4):
        ti.record(_relatorio([("rapido", 0.01, "passed"), ("medio", 0.30, "passed"),
                              ("lento", 2.50, "passed"), ("flaky", 0.05, "failed")]))
    return ti


def test_identifica_o_teste_que_domina_a_suite(inteligencia):
    lentos = inteligencia.slow_tests(threshold=1.0)
    assert lentos[0].nodeid == "lento"
    assert lentos[0].share > 0.8


def test_detecta_regressao_de_velocidade(inteligencia):
    inteligencia.record(_relatorio([("lento", 9.0, "passed")]))
    regressoes = inteligencia.regressions(factor=2.0)
    assert regressoes and regressoes[0].nodeid == "lento"
    assert regressoes[0].factor >= 3


def test_nao_acusa_regressao_em_ruido_de_milissegundos(inteligencia):
    inteligencia.record(_relatorio([("rapido", 0.03, "passed")]))
    assert all(r.nodeid != "rapido" for r in inteligencia.regressions(2.0))


def test_selecao_respeita_o_orcamento_de_tempo(inteligencia):
    escolhidos = inteligencia.select(["rapido", "medio", "lento", "flaky"], 0.5)
    assert "lento" not in escolhidos
    assert set(escolhidos) <= {"rapido", "medio", "flaky"}


def test_selecao_prioriza_teste_que_falhou(inteligencia):
    escolhidos = inteligencia.select(["rapido", "medio", "lento", "flaky"], 0.5)
    assert escolhidos[0] == "flaky"


def test_selecao_nunca_devolve_vazio(inteligencia):
    assert inteligencia.select(["lento"], budget_seconds=0.001) == ["lento"]


def test_teste_aprovado_sai_da_lista_de_falhas(inteligencia):
    inteligencia.record(_relatorio([("flaky", 0.05, "passed")]))
    assert "flaky" not in inteligencia.summary()["recent_failures"]


# ------------------------------------------------------------- otimizador ---

def _historico(store: RunStore, quantidade: int = 8, **kwargs) -> RunStore:
    base = dict(kind="library", verdict="APPROVED", delivered=True, duration=12.0,
                tests_total=20, tests_passed=20, tests_failed=0,
                review_blocking=0, repair_attempts=0)
    base.update(kwargs)
    for i in range(quantidade):
        store.append(RunRecord(run_id=f"r{i}", mission_id=f"m{i}", **base))
    return store


def test_contrafactual_reprova_execucao_com_teste_falhando():
    registro = RunRecord("r", "m", "library", "BLOCKED", False, 1.0,
                         tests_total=10, tests_passed=7, tests_failed=3,
                         review_blocking=0, repair_attempts=0)
    assert _teria_entregue(registro, Policy()) is False


def test_invariante_rejeita_politica_que_entregaria_suite_vermelha():
    registro = RunRecord("r", "m", "library", "BLOCKED", False, 1.0,
                         tests_total=10, tests_passed=7, tests_failed=3,
                         review_blocking=0, repair_attempts=0)
    frouxa = Policy(min_test_pass_rate=0.5)
    assert _viola_invariante([registro], frouxa) is not None


def test_score_penaliza_estouro_de_orcamento():
    rapido = RunRecord("a", "m", "library", "APPROVED", True, 1.0, 10, 10, 0, 0, 0)
    lento = RunRecord("b", "m", "library", "APPROVED", True, 999.0, 10, 10, 0, 0, 0)
    politica = Policy(test_budget_seconds=60.0)
    assert score([rapido], politica) > score([lento], politica)


def test_agente_malicioso_nao_altera_campo_congelado():
    from syra.intelligence.optimizer import _rec

    class Malicioso:
        name = "malicioso"

        def recommend(self, signals, policy):
            return [_rec(self.name, campo, 999, "mais entregas", 0.99, ["-"])
                    for campo in CAMPOS_CONGELADOS]

    otimizador = Optimizer(Policy(), _historico(RunStore()), agents=(Malicioso(),))
    relatorio = otimizador.cycle(apply=True)
    assert relatorio["propostas"] == 0
    assert relatorio["promovidas"] == 0
    resultante = relatorio["politica_resultante"]
    assert resultante["min_test_pass_rate"] == 1.0
    assert resultante["max_blocking_findings"] == 0
    assert resultante["quarantine_block_score"] == 70


def test_validacao_recusa_proposta_com_historico_insuficiente():
    from syra.intelligence.optimizer import _rec

    store = _historico(RunStore(), quantidade=2)
    otimizador = Optimizer(Policy(), store)
    proposta = _rec("t", "max_repair_attempts", 1, "menos ciclo", 0.9, ["-"])
    resultado = otimizador.validate(proposta, store.all())
    assert resultado.promoted is False
    assert "historico insuficiente" in resultado.reason


def test_ciclo_registra_auditoria():
    otimizador = Optimizer(Policy(), _historico(RunStore()))
    otimizador.cycle(apply=False)
    assert otimizador.audit_path.exists()
    assert otimizador.audit_path.read_text(encoding="utf-8").strip()


def test_dry_run_nao_grava_politica():
    otimizador = Optimizer(Policy(), _historico(RunStore(), repair_attempts=1))
    otimizador.cycle(apply=False)
    assert Policy.default_path().exists() is False
