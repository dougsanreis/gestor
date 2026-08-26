"""Testes da camada de aplicacao: servico, API, claims, evidencia e telemetria."""

from __future__ import annotations

import copy
import json
import threading
import urllib.error
import urllib.request

import pytest

from syra.vfos import contracts
from syra.vfos.api import ControlAPI, criar_servidor
from syra.vfos.claims import ClaimRegistry, detectar
from syra.vfos.evidence import EvidenceBundle, ManifestSelado
from syra.vfos.mission import Estado, TransicaoInvalida
from syra.vfos.service import MissionService
from syra.vfos.store import MemoryMissionRepository
from syra.vfos.telemetry import Tracer, redigir
from syra.vfos.worker import OutboxWorker, PublicadorEmMemoria

MISSAO = {
    "mission_id": "mis_appflow001",
    "tenant_id": "ten_abcd1234",
    "type": "CREATE_SALES_PAGE_VARIANT",
    "goal": "Criar variante da pagina de vendas do Vibe Rescue com copy aprovada",
    "scope": {"funnel_id": "vibe_rescue"},
    "required_outputs": ["copy_bundle", "test_report"],
    "risk_class": "LOW",
    "autonomy_level": "L2",
    "budgets": {"max_cost_usd": 8, "max_duration_seconds": 1800, "max_turns": 40},
    "policies": ["vfos.policy.v1"],
    "success_criteria": ["copy lastreada no Claim Registry"],
    "created_by": "tech-lead",
    "created_at": "2026-08-25T12:00:00Z",
}


@pytest.fixture()
def payload():
    return copy.deepcopy(MISSAO)


@pytest.fixture()
def servico():
    return MissionService(MemoryMissionRepository(), tracer=Tracer(habilitado=False))


# ---------------------------------------------------------------- servico ---

def test_criacao_leva_a_planned_e_emite_eventos(servico, payload):
    resultado = servico.criar(payload)
    assert resultado.criada is True
    assert resultado.mission.estado is Estado.PLANNED
    assert len(servico.repositorio.pendentes()) == 2


def test_repeticao_com_mesma_chave_nao_cria_outra_missao(servico, payload):
    primeira = servico.criar(payload, idempotency_key="req-1")
    segunda = servico.criar(payload, idempotency_key="req-1")
    assert segunda.criada is False
    assert segunda.mission.mission_id == primeira.mission.mission_id
    assert segunda.mission.versao == primeira.mission.versao


def test_chaves_diferentes_criam_missoes_diferentes(servico, payload):
    servico.criar(payload, idempotency_key="req-1")
    outra = {**payload, "mission_id": "mis_appflow002"}
    assert servico.criar(outra, idempotency_key="req-2").criada is True


def test_slice_vertical_completo(servico, payload):
    """Criar, validar, persistir, emitir evento, publicar e consultar."""
    servico.criar(payload)
    publicador = PublicadorEmMemoria()
    OutboxWorker(servico.repositorio, publicador).drenar()

    servico.transicionar(payload["tenant_id"], payload["mission_id"],
                         Estado.RUNNING, ator="worker", motivo="execucao iniciada")
    servico.transicionar(payload["tenant_id"], payload["mission_id"],
                         Estado.EVALUATING, ator="worker", motivo="trabalho concluido")
    mission, decisao = servico.avaliar_e_decidir(
        payload["tenant_id"], payload["mission_id"], evidence_ids=["ev_slice"])
    OutboxWorker(servico.repositorio, publicador).drenar()

    assert decisao["decision"] == "APPROVE"
    assert mission.estado is Estado.APPROVED
    assert [e["event_name"] for e in publicador.publicados] == [
        "mission_validating", "mission_planned", "mission_running",
        "mission_evaluating", "mission_approved",
    ]
    for evento in publicador.publicados:
        contracts.get("event").exigir(evento)


def test_governanca_sem_evidencia_manda_para_espera(servico, payload):
    servico.criar(payload)
    for destino in (Estado.RUNNING, Estado.EVALUATING):
        servico.transicionar(payload["tenant_id"], payload["mission_id"], destino,
                             ator="worker", motivo="passo do fluxo")
    mission, decisao = servico.avaliar_e_decidir(
        payload["tenant_id"], payload["mission_id"], evidence_ids=[])
    assert decisao["decision"] == "REQUIRE_APPROVAL"
    assert mission.estado is Estado.WAITING_APPROVAL


def test_governanca_exige_estado_evaluating(servico, payload):
    servico.criar(payload)
    with pytest.raises(TransicaoInvalida, match="EVALUATING"):
        servico.avaliar_e_decidir(payload["tenant_id"], payload["mission_id"],
                                  evidence_ids=["ev_1"])


def test_risco_alto_nao_aprova_sozinho(servico, payload):
    payload.update({"risk_class": "HIGH", "autonomy_level": "L2"})
    servico.criar(payload)
    for destino in (Estado.RUNNING, Estado.EVALUATING):
        servico.transicionar(payload["tenant_id"], payload["mission_id"], destino,
                             ator="worker", motivo="passo do fluxo")
    mission, decisao = servico.avaliar_e_decidir(
        payload["tenant_id"], payload["mission_id"], evidence_ids=["ev_1"])
    assert decisao["decision"] == "REQUIRE_APPROVAL"
    assert mission.estado is Estado.WAITING_APPROVAL


# -------------------------------------------------------------------- API ---

@pytest.fixture()
def api(servico):
    return ControlAPI(servico, ClaimRegistry())


def test_healthz_responde(api):
    assert api.healthz()[0] == 200


def test_readyz_confere_contratos_e_repositorio(api):
    status, corpo = api.readyz()
    assert status == 200
    assert corpo["ready"] is True
    assert len(corpo["checks"]["contracts"]) == 7


def test_criar_missao_devolve_201(api, payload):
    status, corpo = api.criar_missao(payload)
    assert status == 201
    assert corpo["created"] is True
    assert corpo["state"] == "PLANNED"


def test_repeticao_idempotente_devolve_200(api, payload):
    api.criar_missao(payload, idempotency_key="req-1")
    status, corpo = api.criar_missao(payload, idempotency_key="req-1")
    assert status == 200
    assert corpo["created"] is False


def test_contrato_violado_devolve_422_com_campos(api, payload):
    payload["risk_class"] = "IMPOSSIVEL"
    status, corpo = api.criar_missao(payload)
    assert status == 422
    assert any(v["path"] == "$.risk_class" for v in corpo["violations"])


def test_envelope_excedido_devolve_403(api, payload):
    payload.update({"risk_class": "CRITICAL", "autonomy_level": "L4"})
    assert api.criar_missao(payload)[0] == 403


def test_corpo_nao_objeto_devolve_400(api):
    assert api.criar_missao(["nao", "e", "objeto"])[0] == 400


def test_consulta_sem_tenant_devolve_401(api, payload):
    api.criar_missao(payload)
    assert api.obter_missao(payload["mission_id"], "")[0] == 401


def test_missao_inexistente_devolve_404(api):
    assert api.obter_missao("mis_naoexiste1", "ten_abcd1234")[0] == 404


def test_consulta_expoe_transicoes_permitidas(api, payload):
    api.criar_missao(payload)
    status, corpo = api.obter_missao(payload["mission_id"], payload["tenant_id"])
    assert status == 200
    assert set(corpo["allowed_transitions"]) == {"RUNNING", "CANCELLED"}


def test_transicao_invalida_devolve_409(api, payload):
    api.criar_missao(payload)
    status, _ = api.transicionar_missao(
        payload["mission_id"], payload["tenant_id"],
        {"to_state": "RELEASED", "reason": "pular a fila"})
    assert status == 409


def test_estado_desconhecido_devolve_422(api, payload):
    api.criar_missao(payload)
    status, corpo = api.transicionar_missao(
        payload["mission_id"], payload["tenant_id"],
        {"to_state": "INVENTADO", "reason": "teste"})
    assert status == 422
    assert "valid_states" in corpo


def test_rota_desconhecida_devolve_404(api):
    assert api.rotear("GET", "/v1/nada", None, {})[0] == 404


def test_api_sobre_http_real(api, payload):
    """Exercita o transporte de verdade, nao apenas o roteador."""
    servidor = criar_servidor(api, "127.0.0.1", 0)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{servidor.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base}/healthz") as resposta:
            assert resposta.status == 200

        requisicao = urllib.request.Request(
            f"{base}/v1/missions", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     "Idempotency-Key": "req-http"})
        with urllib.request.urlopen(requisicao) as resposta:
            assert resposta.status == 201
            assert resposta.headers.get("X-Trace-Id")

        consulta = urllib.request.Request(
            f"{base}/v1/missions/{payload['mission_id']}",
            headers={"X-Tenant-Id": payload["tenant_id"]})
        with urllib.request.urlopen(consulta) as resposta:
            assert json.loads(resposta.read())["state"] == "PLANNED"

        ausente = urllib.request.Request(
            f"{base}/v1/missions/mis_naoexiste1",
            headers={"X-Tenant-Id": payload["tenant_id"]})
        with pytest.raises(urllib.error.HTTPError) as erro:
            urllib.request.urlopen(ausente)
        assert erro.value.code == 404
    finally:
        servidor.server_close()


# ----------------------------------------------------------------- claims ---

COPY_COM_CLAIMS = (
    "Nossos alunos reduzem 40% do tempo de depuracao em apenas 7 dias. "
    "Mais de 1.200 devs ja passaram pelo protocolo. "
    "Garantia de 14 dias ou devolvemos o dinheiro. "
    "Somos o melhor do mercado em governanca. "
    "Ultimas vagas: restam 8 lugares por R$ 497."
)


@pytest.mark.parametrize("texto,tipo", [
    ("Reduza 40% do tempo gasto", "FACTUAL"),
    ("Investimento de R$ 497 a vista", "FACTUAL"),
    ("3x mais rapido que o processo manual", "COMPARISON"),
    ("Mais de 1.200 alunos concluiram", "CASE"),
    ("Resolva em 7 dias", "FACTUAL"),
    ("Garantia de 30 dias ou reembolso", "GUARANTEE"),
    ("Somos o melhor do mercado", "COMPARISON"),
    ("Ultimas vagas para a turma", "FACTUAL"),
])
def test_deteccao_reconhece_cada_tipo_de_alegacao(texto, tipo):
    assert any(d.tipo == tipo for d in detectar(texto))


def test_texto_sem_alegacao_nao_gera_deteccao():
    assert detectar("O metodo funciona com a ferramenta que voce ja usa.") == []


def test_registry_vazio_bloqueia_toda_alegacao():
    resultado = ClaimRegistry().avaliar_publicacao(COPY_COM_CLAIMS,
                                                   funnel_id="vibe_rescue")
    assert resultado.pode_publicar is False
    assert len(resultado.bloqueios) >= 5


def test_texto_sem_alegacao_publica_sem_registry():
    resultado = ClaimRegistry().avaliar_publicacao(
        "O metodo funciona com a ferramenta que voce ja usa.",
        funnel_id="vibe_rescue")
    assert resultado.pode_publicar is True


@pytest.fixture()
def registry_com_garantia():
    registry = ClaimRegistry()
    claim = registry.registrar(
        tenant_id="ten_abcd1234",
        exact_text="Garantia de 14 dias ou devolvemos o dinheiro",
        claim_type="GUARANTEE", risk_class="HIGH",
        funnel_ids=["vibe_rescue"], locales=["pt-BR"],
        evidence_ids=["ev_contrato"])
    return registry, claim["claim_id"]


TEXTO_GARANTIA = "Garantia de 14 dias ou devolvemos o dinheiro."


def test_claim_em_draft_ainda_bloqueia(registry_com_garantia):
    registry, _ = registry_com_garantia
    assert not registry.avaliar_publicacao(TEXTO_GARANTIA,
                                           funnel_id="vibe_rescue").pode_publicar


def test_claim_aprovada_libera(registry_com_garantia):
    registry, claim_id = registry_com_garantia
    registry.aprovar(claim_id, "juridico@empresa")
    assert registry.avaliar_publicacao(TEXTO_GARANTIA,
                                       funnel_id="vibe_rescue").pode_publicar


def test_aprovacao_exige_identificar_o_aprovador(registry_com_garantia):
    registry, claim_id = registry_com_garantia
    with pytest.raises(ValueError, match="quem aprova"):
        registry.aprovar(claim_id, "")


def test_claim_aprovada_nao_vale_em_outro_funil(registry_com_garantia):
    registry, claim_id = registry_com_garantia
    registry.aprovar(claim_id, "juridico@empresa")
    assert not registry.avaliar_publicacao(TEXTO_GARANTIA,
                                           funnel_id="outro_funil").pode_publicar


def test_claim_aprovada_nao_vale_em_outro_locale(registry_com_garantia):
    registry, claim_id = registry_com_garantia
    registry.aprovar(claim_id, "juridico@empresa")
    assert not registry.avaliar_publicacao(TEXTO_GARANTIA, funnel_id="vibe_rescue",
                                           locale="en-US").pode_publicar


def test_revogacao_tem_efeito_imediato(registry_com_garantia):
    registry, claim_id = registry_com_garantia
    registry.aprovar(claim_id, "juridico@empresa")
    registry.revogar(claim_id, "clausula alterada")
    assert not registry.avaliar_publicacao(TEXTO_GARANTIA,
                                           funnel_id="vibe_rescue").pode_publicar


def test_claim_expirada_nao_vale():
    registry = ClaimRegistry()
    claim = registry.registrar(
        tenant_id="ten_abcd1234", exact_text="Garantia de 14 dias",
        claim_type="GUARANTEE", risk_class="MEDIUM", funnel_ids=["f"],
        locales=["pt-BR"], evidence_ids=["ev_1"],
        valid_until="2026-01-01T00:00:00Z")
    registry.aprovar(claim["claim_id"], "juridico@empresa")
    assert not registry.avaliar_publicacao("Garantia de 14 dias.",
                                           funnel_id="f").pode_publicar


def test_numero_aprovado_nao_autoriza_numero_diferente():
    """Aprovar "40%" nao pode liberar a publicacao de "400%"."""
    registry = ClaimRegistry()
    claim = registry.registrar(
        tenant_id="ten_abcd1234", exact_text="reduzem 40% do tempo de depuracao",
        claim_type="FACTUAL", risk_class="MEDIUM", funnel_ids=["f"],
        locales=["pt-BR"], evidence_ids=["ev_estudo"])
    registry.aprovar(claim["claim_id"], "analista@empresa")
    assert registry.avaliar_publicacao("Alunos reduzem 40% do tempo de depuracao.",
                                       funnel_id="f").pode_publicar
    assert not registry.avaliar_publicacao("Alunos reduzem 400% do tempo de depuracao.",
                                           funnel_id="f").pode_publicar


def test_tipo_divergente_bloqueia():
    """Lastro FACTUAL nao cobre um texto que faz promessa de garantia."""
    registry = ClaimRegistry()
    claim = registry.registrar(
        tenant_id="ten_abcd1234", exact_text="devolvemos o dinheiro em 14 dias",
        claim_type="FACTUAL", risk_class="MEDIUM", funnel_ids=["f"],
        locales=["pt-BR"], evidence_ids=["ev_1"])
    registry.aprovar(claim["claim_id"], "analista@empresa")
    resultado = registry.avaliar_publicacao("Sim, devolvemos o dinheiro em 14 dias.",
                                            funnel_id="f")
    assert not resultado.pode_publicar
    assert any("GUARANTEE" in b for b in resultado.bloqueios)


def test_registry_persiste_entre_instancias(tmp_path):
    caminho = tmp_path / "claims.json"
    registry = ClaimRegistry(caminho)
    claim = registry.registrar(
        tenant_id="ten_abcd1234", exact_text="Garantia de 14 dias",
        claim_type="GUARANTEE", risk_class="MEDIUM", funnel_ids=["f"],
        locales=["pt-BR"], evidence_ids=["ev_1"])
    registry.aprovar(claim["claim_id"], "juridico@empresa")
    assert ClaimRegistry(caminho).avaliar_publicacao("Garantia de 14 dias.",
                                                     funnel_id="f").pode_publicar


def test_registry_corrompido_bloqueia_tudo(tmp_path):
    """Fail-closed: registry ilegivel nao pode liberar publicacao."""
    caminho = tmp_path / "claims.json"
    caminho.write_text("{ isto nao e json", encoding="utf-8")
    assert not ClaimRegistry(caminho).avaliar_publicacao(
        "Garantia de 14 dias.", funnel_id="f").pode_publicar


def test_gate_pela_api(api):
    status, corpo = api.avaliar_publicacao({"text": COPY_COM_CLAIMS,
                                            "funnel_id": "vibe_rescue"})
    assert status == 403
    assert corpo["can_publish"] is False


# -------------------------------------------------------------- evidencia ---

def test_bundle_registra_resultado_real_do_comando():
    bundle = EvidenceBundle(task_id="TASK-TESTE")
    registro = bundle.registrar_comando("python3 -c 'print(1)'")
    assert registro["exit_code"] == 0
    assert bundle.comandos_verdes is True


def test_bundle_registra_falha_sem_mascarar():
    bundle = EvidenceBundle(task_id="TASK-TESTE")
    bundle.registrar_comando("python3 -c 'raise SystemExit(3)'")
    assert bundle.commands[0]["exit_code"] == 3
    assert bundle.comandos_verdes is False


def test_comando_inexistente_e_registrado_e_nao_explode():
    bundle = EvidenceBundle(task_id="TASK-TESTE")
    registro = bundle.registrar_comando("binario_que_nao_existe_98765")
    assert registro["exit_code"] != 0


def test_manifest_selado_recusa_alteracao(tmp_path):
    bundle = EvidenceBundle(task_id="TASK-TESTE")
    bundle.registrar_comando("python3 -c 'print(1)'")
    bundle.selar(tmp_path / "manifest.json")
    with pytest.raises(ManifestSelado):
        bundle.registrar_comando("python3 -c 'print(2)'")


def test_manifest_carrega_hash_do_proprio_conteudo(tmp_path):
    bundle = EvidenceBundle(task_id="TASK-TESTE")
    bundle.registrar_comando("python3 -c 'print(1)'")
    destino = bundle.selar(tmp_path / "manifest.json")
    corpo = json.loads(destino.read_text(encoding="utf-8"))
    assert len(corpo["manifest_sha256"]) == 64
    assert corpo["task_id"] == "TASK-TESTE"


def test_artefato_registrado_com_hash(tmp_path):
    alvo = tmp_path / "artefato.txt"
    alvo.write_text("conteudo", encoding="utf-8")
    bundle = EvidenceBundle(task_id="TASK-TESTE")
    registro = bundle.registrar_artefato(alvo)
    assert len(registro["sha256"]) == 64


# -------------------------------------------------------------- telemetria ---

# Fixtures com forma de segredo sao montadas em tempo de execucao, nunca
# escritas como literal. Segredo falso no codigo-fonte dispara scanner de
# credencial para sempre — inclusive o hook deste proprio repositorio.
CHAVE_FALSA = "sk-" + ("a" * 24)
TOKEN_FALSO = "Bearer " + ("b" * 24)


@pytest.mark.parametrize("chave,valor", [
    ("password", "x" * 16),
    ("api_key", CHAVE_FALSA),
    ("email", "pessoa@exemplo.com"),
    ("user_id", "u-12345"),
    ("prompt", "texto integral do prompt"),
])
def test_chave_sensivel_e_redigida(chave, valor):
    assert "[REDIGIDO]" in json.dumps(redigir({chave: valor}))


@pytest.mark.parametrize("texto", [
    "contato: pessoa@exemplo.com",
    "documento 529.982.247-25",
    f"Authorization: {TOKEN_FALSO}",
    f"chave {CHAVE_FALSA} vazada",
])
def test_padrao_sensivel_no_valor_e_redigido(texto):
    assert "[REDIGIDO]" in redigir({"detalhe": texto})["detalhe"]


def test_valor_inofensivo_atravessa_intacto():
    assert redigir({"mission_id": "mis_abcd1234"})["mission_id"] == "mis_abcd1234"


def test_estrutura_profunda_e_truncada():
    aninhado: dict = {"n": 1}
    for _ in range(12):
        aninhado = {"n": aninhado}
    assert "[PROFUNDO]" in json.dumps(redigir(aninhado))


def test_span_registra_duracao_e_status():
    tracer = Tracer(habilitado=False)
    with tracer.span("teste", chave="valor") as span:
        span.set("extra", 1)
    assert tracer.spans[0].status == "OK"
    assert tracer.spans[0].duracao_ms >= 0


def test_span_marca_erro_e_repropaga():
    tracer = Tracer(habilitado=False)
    with pytest.raises(ValueError):
        with tracer.span("teste"):
            raise ValueError("falhou")
    assert tracer.spans[0].status == "ERROR"
    assert "ValueError" in tracer.spans[0].erro


def test_atributo_de_span_e_redigido():
    tracer = Tracer(habilitado=False)
    with tracer.span("teste") as span:
        span.set("email", "pessoa@exemplo.com")
    assert tracer.spans[0].atributos["email"] == "[REDIGIDO]"
