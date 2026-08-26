"""Testes do nucleo do Vibe Funnel OS: contratos, politica, agregado e store."""

from __future__ import annotations

import copy
import json

import pytest

from syra.vfos import contracts, ids, policy
from syra.vfos.jsonschema_lite import (
    SchemaNaoSuportado,
    assert_suportado,
    is_valid,
    validate,
)
from syra.vfos.mission import (
    TERMINAIS,
    TRANSICOES,
    EnvelopeExcedido,
    Estado,
    Mission,
    TransicaoInvalida,
    evento_de_transicao,
)
from syra.vfos.store import (
    ConflitoDeVersao,
    MemoryMissionRepository,
    MissaoNaoEncontrada,
    SqliteMissionRepository,
)
from syra.vfos.worker import OutboxWorker, PublicadorEmMemoria, backoff_segundos

MISSAO_VALIDA = {
    "mission_id": "mis_abcd1234",
    "tenant_id": "ten_abcd1234",
    "type": "IMPLEMENT_FEATURE",
    "goal": "Implementar o slice vertical de Mission com evidencia executavel",
    "scope": {"funnel_id": "vibe_rescue"},
    "required_outputs": ["mission_persisted", "event_emitted"],
    "risk_class": "LOW",
    "autonomy_level": "L2",
    "budgets": {"max_cost_usd": 5, "max_duration_seconds": 600, "max_turns": 20},
    "policies": ["vfos.policy.v1"],
    "success_criteria": ["estado consultavel via API"],
    "created_by": "tech-lead",
    "created_at": "2026-08-25T12:00:00Z",
}


@pytest.fixture()
def payload():
    return copy.deepcopy(MISSAO_VALIDA)


@pytest.fixture(params=["memoria", "sqlite"])
def repositorio(request, tmp_path):
    """Mesmo conjunto de testes de contrato contra os dois adapters."""
    if request.param == "memoria":
        return MemoryMissionRepository()
    return SqliteMissionRepository(tmp_path / "vfos.db")


# ------------------------------------------------------- validador lite ---

def test_todos_os_contratos_sao_integralmente_aplicaveis():
    """Nenhum contrato usa palavra-chave que o validador ignora."""
    for contrato in contracts.todos().values():
        assert_suportado(contrato.schema, contrato.nome)


def test_schema_com_palavra_chave_desconhecida_e_recusado():
    with pytest.raises(SchemaNaoSuportado):
        assert_suportado({"type": "object", "patternProperties": {}})


@pytest.mark.parametrize("instancia,schema,esperado", [
    ("abc", {"type": "string"}, True),
    (1, {"type": "string"}, False),
    (True, {"type": "integer"}, False),          # bool nao e integer em JSON
    (1, {"type": "number"}, True),
    (1.5, {"type": "integer"}, False),
    (None, {"type": ["string", "null"]}, True),
    ([1, 1], {"type": "array", "uniqueItems": True}, False),
    ([{"a": 1}, {"a": 1}], {"type": "array", "uniqueItems": True}, False),
    ("2026-13-45T99:99:99Z", {"type": "string", "format": "date-time"}, False),
    ("2026-08-25T12:00:00Z", {"type": "string", "format": "date-time"}, True),
    ("2026-02-30T10:00:00Z", {"type": "string", "format": "date-time"}, False),
    ({"a": 1}, {"type": "object", "additionalProperties": False}, False),
])
def test_regras_basicas_do_validador(instancia, schema, esperado):
    assert is_valid(instancia, schema) is esperado


def test_validador_devolve_todas_as_violacoes_de_uma_vez():
    schema = {"type": "object", "required": ["a", "b", "c"],
              "additionalProperties": False}
    violacoes = validate({}, schema)
    assert len(violacoes) == 3
    assert {v.keyword for v in violacoes} == {"required"}


def test_validador_concorda_com_a_implementacao_de_referencia():
    """Diferencial contra ``jsonschema`` com verificacao de formato ativa.

    Este e o teste que sustenta a decisao de nao depender da biblioteca em
    producao: se as duas divergirem, o validador proprio esta errado.
    """
    jsonschema = pytest.importorskip("jsonschema")
    from jsonschema.validators import validator_for

    schema = contracts.get("mission").schema
    referencia = validator_for(schema)(schema,
                                       format_checker=jsonschema.FormatChecker())

    variacoes = [MISSAO_VALIDA]
    for chave in MISSAO_VALIDA:
        for valor in (None, "", 0, [], {}, True, "x" * 600):
            mutante = copy.deepcopy(MISSAO_VALIDA)
            mutante[chave] = valor
            variacoes.append(mutante)
        sem_chave = copy.deepcopy(MISSAO_VALIDA)
        del sem_chave[chave]
        variacoes.append(sem_chave)

    for instancia in variacoes:
        assert referencia.is_valid(instancia) == is_valid(instancia, schema), (
            f"divergencia em {json.dumps(instancia)[:160]}")


# -------------------------------------------------------------- contratos ---

def test_contrato_desconhecido_lista_os_disponiveis():
    with pytest.raises(KeyError, match="disponiveis"):
        contracts.get("nao_existe")


def test_violacao_de_contrato_carrega_o_caminho_do_campo(payload):
    payload["risk_class"] = "IMPOSSIVEL"
    with pytest.raises(contracts.ViolacaoDeContrato) as erro:
        contracts.get("mission").exigir(payload)
    caminhos = [v["path"] for v in erro.value.to_dict()["violations"]]
    assert "$.risk_class" in caminhos


def test_chave_de_idempotencia_independe_da_ordem_das_chaves():
    assert ids.idempotency_key({"a": 1, "b": 2}) == ids.idempotency_key({"b": 2, "a": 1})


def test_chave_de_idempotencia_muda_com_o_conteudo():
    assert ids.idempotency_key({"a": 1}) != ids.idempotency_key({"a": 2})


# --------------------------------------------------------------- politica ---

@pytest.mark.parametrize("risco,teto", [
    ("LOW", "L4"), ("MEDIUM", "L3"), ("HIGH", "L2"), ("CRITICAL", "L1"),
])
def test_envelope_respeita_o_teto_por_risco(risco, teto):
    assert policy.verificar_envelope(risco, teto).permitido
    acima = policy.NIVEIS[policy.NIVEIS.index(teto) + 1:]
    for nivel in acima:
        assert not policy.verificar_envelope(risco, nivel).permitido


def test_envelope_recusa_risco_desconhecido():
    assert not policy.verificar_envelope("INVENTADO", "L1").permitido


def test_envelope_recusa_autonomia_desconhecida():
    assert not policy.verificar_envelope("LOW", "L9").permitido


def _decidir(**kwargs):
    base = dict(tenant_id="ten_abcd1234", subject_type="artifact",
                subject_id="mis_abcd1234", risk_class="LOW",
                autonomy_level="L2", evidence_ids=["ev_1"])
    base.update(kwargs)
    return policy.decidir(**base)


def test_risco_baixo_com_evidencia_aprova():
    assert _decidir()["decision"] == "APPROVE"


def test_sem_evidencia_nunca_aprova():
    """O contrato proibe APPROVE sem evidencia; a politica antecipa a recusa."""
    assert _decidir(evidence_ids=[])["decision"] == "REQUIRE_APPROVAL"


def test_falha_bloqueante_impede_aprovacao():
    decisao = _decidir(blocking_failures=["suite vermelha"])
    assert decisao["decision"] == "REWORK"


def test_risco_alto_exige_aprovacao_humana():
    decisao = _decidir(risk_class="HIGH", autonomy_level="L2")
    assert decisao["decision"] == "REQUIRE_APPROVAL"
    assert decisao["required_approvals"]


def test_risco_alto_aprova_com_todas_as_assinaturas():
    decisao = _decidir(risk_class="HIGH", autonomy_level="L2",
                       aprovacoes_obtidas=["owner", "security"])
    assert decisao["decision"] == "APPROVE"


def test_autonomia_fora_do_envelope_rejeita():
    decisao = _decidir(risk_class="CRITICAL", autonomy_level="L4")
    assert decisao["decision"] == "REJECT"
    assert "AUTONOMY_ENVELOPE_EXCEEDED" in decisao["reason_codes"]


def test_decisao_emitida_satisfaz_o_contrato():
    contracts.get("governance-decision").exigir(_decidir())


# --------------------------------------------------------------- agregado ---

def test_criacao_valida_contrato(payload):
    payload["goal"] = "curto"
    with pytest.raises(contracts.ViolacaoDeContrato):
        Mission.criar(payload)


def test_criacao_valida_envelope(payload):
    payload.update({"risk_class": "CRITICAL", "autonomy_level": "L4"})
    with pytest.raises(EnvelopeExcedido):
        Mission.criar(payload)


def test_todos_os_estados_sao_alcancaveis():
    alcancaveis = {d for destinos in TRANSICOES.values() for d in destinos}
    alcancaveis.add(Estado.DRAFT)
    assert alcancaveis == set(Estado)


def test_estados_terminais_nao_tem_saida():
    assert all(not TRANSICOES[estado] for estado in TERMINAIS)


def test_transicao_fora_da_tabela_e_recusada(payload):
    mission = Mission.criar(payload)
    with pytest.raises(TransicaoInvalida, match="nao existe"):
        mission.transicionar(Estado.RELEASED, ator="x", motivo="pular a fila")


def test_estado_terminal_recusa_qualquer_transicao(payload):
    mission = Mission.criar(payload).transicionar(
        Estado.CANCELLED, ator="x", motivo="cancelada pelo autor")
    with pytest.raises(TransicaoInvalida, match="terminal"):
        mission.transicionar(Estado.RUNNING, ator="x", motivo="retomar")


def test_transicao_exige_motivo(payload):
    with pytest.raises(TransicaoInvalida, match="motivo"):
        Mission.criar(payload).transicionar(Estado.VALIDATING, ator="x", motivo="")


def _ate_evaluating(payload) -> Mission:
    mission = Mission.criar(payload)
    for destino, ator in ((Estado.VALIDATING, "api"), (Estado.PLANNED, "validator"),
                          (Estado.RUNNING, "worker"), (Estado.EVALUATING, "worker")):
        mission = mission.transicionar(destino, ator=ator, motivo="passo do fluxo")
    return mission


def test_aprovacao_sem_decisao_de_governanca_e_recusada(payload):
    mission = _ate_evaluating(payload)
    with pytest.raises(TransicaoInvalida, match="GovernanceDecision"):
        mission.transicionar(Estado.APPROVED, ator="governor", motivo="aprovar")


def test_aprovacao_com_decisao_de_outro_assunto_e_recusada(payload):
    mission = _ate_evaluating(payload)
    decisao = _decidir(subject_id="mis_outra12345")
    with pytest.raises(TransicaoInvalida, match="refere-se"):
        mission.transicionar(Estado.APPROVED, ator="governor",
                             motivo="aprovar", decisao=decisao)


def test_aprovacao_com_decisao_de_outro_tenant_e_recusada(payload):
    mission = _ate_evaluating(payload)
    decisao = _decidir(tenant_id="ten_outro12345", subject_id=payload["mission_id"])
    with pytest.raises(TransicaoInvalida, match="outro tenant"):
        mission.transicionar(Estado.APPROVED, ator="governor",
                             motivo="aprovar", decisao=decisao)


def test_aprovacao_exige_decisao_de_aprovacao(payload):
    mission = _ate_evaluating(payload)
    negada = _decidir(subject_id=payload["mission_id"], evidence_ids=[])
    with pytest.raises(TransicaoInvalida, match="APPROVE"):
        mission.transicionar(Estado.APPROVED, ator="governor",
                             motivo="tentar aprovar", decisao=negada)


def test_caminho_feliz_completo(payload):
    mission = _ate_evaluating(payload)
    decisao = _decidir(subject_id=payload["mission_id"])
    mission = mission.transicionar(Estado.APPROVED, ator="governor",
                                   motivo="gate aprovado", decisao=decisao)
    assert mission.estado is Estado.APPROVED
    assert mission.versao == 6
    assert len(mission.historico) == 5


def test_transicao_nao_muta_o_agregado_original(payload):
    original = Mission.criar(payload)
    original.transicionar(Estado.VALIDATING, ator="api", motivo="submetida")
    assert original.estado is Estado.DRAFT
    assert original.versao == 1


def test_evento_de_transicao_satisfaz_o_contrato(payload):
    mission = Mission.criar(payload).transicionar(Estado.VALIDATING, ator="api",
                                                  motivo="submetida")
    evento = evento_de_transicao(mission, mission.historico[-1])
    contracts.get("event").exigir(evento)
    assert evento["event_name"] == "mission_validating"


def test_evento_nao_vaza_o_objetivo_da_missao(payload):
    """Objetivo e escopo sao texto livre e nao entram em analytics."""
    mission = Mission.criar(payload).transicionar(Estado.VALIDATING, ator="api",
                                                  motivo="submetida")
    evento = evento_de_transicao(mission, mission.historico[-1])
    assert payload["goal"] not in json.dumps(evento)


# ------------------------------------------------------------------ store ---

def test_round_trip_preserva_estado_versao_e_historico(repositorio, payload):
    mission = Mission.criar(payload).transicionar(Estado.VALIDATING, ator="api",
                                                  motivo="submetida")
    repositorio.salvar(mission, [], versao_esperada=0)
    lida = repositorio.obter(mission.tenant_id, mission.mission_id)
    assert lida.estado is mission.estado
    assert lida.versao == mission.versao
    assert lida.historico == mission.historico


def test_conflito_de_versao_e_detectado(repositorio, payload):
    mission = Mission.criar(payload)
    repositorio.salvar(mission, [], versao_esperada=0)
    with pytest.raises(ConflitoDeVersao):
        repositorio.salvar(mission, [], versao_esperada=99)


def test_missao_de_outro_tenant_nao_vaza(repositorio, payload):
    repositorio.salvar(Mission.criar(payload), [], versao_esperada=0)
    with pytest.raises(MissaoNaoEncontrada):
        repositorio.obter("ten_outro12345", payload["mission_id"])


def test_evento_invalido_impede_a_gravacao_da_missao(repositorio, payload):
    """A janela do outbox: agregado e evento vivem ou morrem juntos."""
    mission = Mission.criar(payload)
    with pytest.raises(contracts.ViolacaoDeContrato):
        repositorio.salvar(mission, [{"event_name": "x", "idempotency_key": None}],
                           versao_esperada=0)
    with pytest.raises(MissaoNaoEncontrada):
        repositorio.obter(mission.tenant_id, mission.mission_id)


def test_mesmo_evento_gravado_duas_vezes_nao_duplica(repositorio, payload):
    mission = Mission.criar(payload).transicionar(Estado.VALIDATING, ator="api",
                                                  motivo="submetida")
    evento = evento_de_transicao(mission, mission.historico[-1])
    repositorio.salvar(mission, [evento], versao_esperada=0)
    repositorio.salvar(mission, [evento], versao_esperada=None)
    assert len(repositorio.pendentes()) == 1


def test_reserva_de_idempotencia_pertence_a_um_dono(repositorio):
    assert repositorio.reservar_processamento("k", "dono-a") is True
    assert repositorio.reservar_processamento("k", "dono-b") is False
    assert repositorio.reservar_processamento("k", "dono-a") is True


def test_reserva_liberada_fica_disponivel(repositorio):
    repositorio.reservar_processamento("k", "dono-a")
    repositorio.liberar_processamento("k", "dono-a")
    assert repositorio.reservar_processamento("k", "dono-b") is True


def test_liberacao_por_dono_errado_nao_tem_efeito(repositorio):
    repositorio.reservar_processamento("k", "dono-a")
    repositorio.liberar_processamento("k", "dono-b")
    assert repositorio.reservar_processamento("k", "dono-b") is False


# ----------------------------------------------------------------- worker ---

class PublicadorIntermitente:
    """Falha as primeiras ``falhas`` entregas e depois funciona."""

    def __init__(self, falhas: int) -> None:
        self.restantes = falhas
        self.publicados: list[dict] = []

    def publicar(self, evento: dict) -> None:
        if self.restantes > 0:
            self.restantes -= 1
            raise ConnectionError("destino indisponivel")
        self.publicados.append(evento)


class PublicadorQuebrado:
    """Nunca entrega."""

    def publicar(self, evento: dict) -> None:
        raise ConnectionError("destino permanentemente fora")


def _com_eventos(repositorio, payload):
    mission = Mission.criar(payload).transicionar(Estado.VALIDATING, ator="api",
                                                  motivo="submetida")
    repositorio.salvar(mission, [evento_de_transicao(mission, mission.historico[-1])],
                       versao_esperada=0)
    return mission


def test_worker_publica_e_marca(repositorio, payload):
    _com_eventos(repositorio, payload)
    publicador = PublicadorEmMemoria()
    lote = OutboxWorker(repositorio, publicador).processar_lote()
    assert lote.publicadas == 1
    assert len(publicador.publicados) == 1
    assert repositorio.pendentes() == []


def test_falha_transitoria_nao_perde_evento(repositorio, payload):
    """A regressao que este teste tranca: falha marcava a chave e o evento
    era descartado como duplicata na tentativa seguinte."""
    _com_eventos(repositorio, payload)
    publicador = PublicadorIntermitente(falhas=2)
    worker = OutboxWorker(repositorio, publicador, max_tentativas=5)
    for _ in range(4):
        worker.processar_lote()
    assert len(publicador.publicados) == 1
    assert repositorio.pendentes() == []


def test_falha_permanente_vira_dead_letter(repositorio, payload):
    _com_eventos(repositorio, payload)
    worker = OutboxWorker(repositorio, PublicadorQuebrado(), max_tentativas=3)
    for _ in range(3):
        worker.processar_lote()
    lote = worker.processar_lote()
    assert lote.dead_letter == 1
    assert repositorio.pendentes()


def test_drenar_nao_gira_em_falso(repositorio, payload):
    _com_eventos(repositorio, payload)
    worker = OutboxWorker(repositorio, PublicadorQuebrado(), max_tentativas=2)
    total = worker.drenar(max_ciclos=50)
    assert total.publicadas == 0
    assert total.processadas <= 4


@pytest.mark.parametrize("tentativas,esperado", [(0, 0.0), (1, 2.0), (2, 4.0),
                                                 (3, 8.0), (20, 300.0)])
def test_backoff_cresce_com_teto(tentativas, esperado):
    assert backoff_segundos(tentativas) == esperado
