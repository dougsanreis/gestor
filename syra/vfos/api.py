"""API de controle: superficie HTTP conforme ``contracts/openapi.yaml``.

Somente biblioteca padrao. Erros seguem o formato ``Problem`` do OpenAPI, com
o detalhe de violacao de contrato incluido — quem chamou precisa saber qual
campo recusou, nao apenas que "deu 400".

Idempotencia entra pelo cabecalho ``Idempotency-Key``, que e onde ela pertence:
o contrato de Mission descreve a missao, nao a requisicao que a criou.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from syra.vfos import contracts
from syra.vfos.claims import ClaimRegistry
from syra.vfos.contracts import ViolacaoDeContrato
from syra.vfos.mission import EnvelopeExcedido, Estado, TransicaoInvalida
from syra.vfos.service import MissionService
from syra.vfos.store import ConflitoDeVersao, MissaoNaoEncontrada
from syra.vfos.telemetry import TRACER

MAX_CORPO = 1_048_576
_ROTA_MISSAO = re.compile(r"^/v1/missions/(?P<id>[A-Za-z0-9_-]+)$")


def problema(status: int, titulo: str, detalhe: str,
             extras: dict[str, Any] | None = None) -> dict[str, Any]:
    """Monta um corpo de erro no formato Problem."""
    corpo = {"type": "about:blank", "title": titulo, "status": status,
             "detail": detalhe}
    if extras:
        corpo.update(extras)
    return corpo


class ControlAPI:
    """Nucleo da API, independente de transporte.

    Separar o roteamento do servidor HTTP permite testar cada endpoint sem
    abrir socket, e permite hospedar a mesma logica sob outro servidor depois.
    """

    def __init__(self, servico: MissionService,
                 registry: ClaimRegistry | None = None) -> None:
        self.servico = servico
        self.registry = registry or ClaimRegistry()
        self.pronto = True

    # ---------------------------------------------------------- saude ---

    def healthz(self) -> tuple[int, dict[str, Any]]:
        """Liveness: o processo responde."""
        return 200, {"status": "ok"}

    def readyz(self) -> tuple[int, dict[str, Any]]:
        """Readiness: dependencias carregadas e utilizaveis.

        Contratos ausentes tornam o servico inapto: sem eles nao ha validacao,
        e servir sem validacao seria o oposto de fail-closed.
        """
        verificacoes: dict[str, Any] = {}
        pronto = True
        try:
            verificacoes["contracts"] = sorted(contracts.todos())
        except Exception as erro:
            verificacoes["contracts"] = f"indisponivel: {erro}"
            pronto = False
        try:
            self.servico.repositorio.pendentes(1)
            verificacoes["repository"] = "ok"
        except Exception as erro:
            verificacoes["repository"] = f"indisponivel: {erro}"
            pronto = False
        return (200 if pronto else 503), {"ready": pronto, "checks": verificacoes}

    # -------------------------------------------------------- missoes ---

    def criar_missao(self, corpo: Any,
                     idempotency_key: str | None = None) -> tuple[int, dict[str, Any]]:
        """POST /v1/missions."""
        if not isinstance(corpo, dict):
            return 400, problema(400, "Corpo invalido",
                                 "o corpo deve ser um objeto JSON")
        try:
            resultado = self.servico.criar(corpo, idempotency_key=idempotency_key)
        except ViolacaoDeContrato as erro:
            return 422, problema(422, "Violacao de contrato", str(erro),
                                 {"violations": erro.to_dict()["violations"]})
        except EnvelopeExcedido as erro:
            return 403, problema(403, "Envelope de autonomia excedido", str(erro))
        except ConflitoDeVersao as erro:
            return 409, problema(409, "Conflito de versao", str(erro))

        # 200 sinaliza repeticao idempotente; 201 sinaliza criacao nova.
        status = 201 if resultado.criada else 200
        return status, {"mission_id": resultado.mission.mission_id,
                        "state": resultado.mission.estado.value,
                        "version": resultado.mission.versao,
                        "created": resultado.criada}

    def obter_missao(self, mission_id: str,
                     tenant_id: str) -> tuple[int, dict[str, Any]]:
        """GET /v1/missions/{missionId}."""
        if not tenant_id:
            return 401, problema(401, "Tenant ausente",
                                 "informe o cabecalho X-Tenant-Id")
        try:
            mission = self.servico.obter(tenant_id, mission_id)
        except MissaoNaoEncontrada:
            return 404, problema(404, "Missao nao encontrada",
                                 f"{mission_id} nao existe neste tenant")
        return 200, {"mission_id": mission.mission_id,
                     "state": mission.estado.value, "version": mission.versao,
                     "risk_class": mission.risk_class,
                     "autonomy_level": mission.autonomy_level,
                     "allowed_transitions": [e.value for e in mission.destinos()],
                     "history": [t.to_dict() for t in mission.historico]}

    def transicionar_missao(self, mission_id: str, tenant_id: str,
                            corpo: Any) -> tuple[int, dict[str, Any]]:
        """POST /v1/missions/{missionId}/transitions."""
        if not tenant_id:
            return 401, problema(401, "Tenant ausente",
                                 "informe o cabecalho X-Tenant-Id")
        if not isinstance(corpo, dict) or "to_state" not in corpo:
            return 400, problema(400, "Corpo invalido",
                                 "informe to_state e reason")
        try:
            destino = Estado(corpo["to_state"])
        except ValueError:
            return 422, problema(422, "Estado desconhecido",
                                 f"{corpo['to_state']} nao e um estado valido",
                                 {"valid_states": [e.value for e in Estado]})
        try:
            mission = self.servico.transicionar(
                tenant_id, mission_id, destino,
                ator=str(corpo.get("actor", "api")),
                motivo=str(corpo.get("reason", "")),
                decisao=corpo.get("decision"))
        except MissaoNaoEncontrada:
            return 404, problema(404, "Missao nao encontrada", mission_id)
        except TransicaoInvalida as erro:
            return 409, problema(409, "Transicao invalida", str(erro))
        except ViolacaoDeContrato as erro:
            return 422, problema(422, "Violacao de contrato", str(erro),
                                 {"violations": erro.to_dict()["violations"]})
        except ConflitoDeVersao as erro:
            return 409, problema(409, "Conflito de versao", str(erro))
        return 200, {"mission_id": mission.mission_id,
                     "state": mission.estado.value, "version": mission.versao}

    # --------------------------------------------------------- claims ---

    def avaliar_publicacao(self, corpo: Any) -> tuple[int, dict[str, Any]]:
        """POST /v1/claims/evaluate — gate de publicacao de copy."""
        if not isinstance(corpo, dict) or "text" not in corpo:
            return 400, problema(400, "Corpo invalido",
                                 "informe text e funnel_id")
        resultado = self.registry.avaliar_publicacao(
            str(corpo["text"]), funnel_id=str(corpo.get("funnel_id", "")),
            locale=str(corpo.get("locale", "pt-BR")))
        # 200 descreve o veredito; 403 e o proprio bloqueio.
        return (200 if resultado.pode_publicar else 403), resultado.to_dict()

    # ----------------------------------------------------- roteamento ---

    def rotear(self, metodo: str, caminho: str, corpo: Any,
               cabecalhos: dict[str, str]) -> tuple[int, dict[str, Any]]:
        """Despacha uma requisicao ja desserializada."""
        tenant = cabecalhos.get("x-tenant-id", "")

        if metodo == "GET" and caminho == "/healthz":
            return self.healthz()
        if metodo == "GET" and caminho == "/readyz":
            return self.readyz()
        if metodo == "POST" and caminho == "/v1/missions":
            return self.criar_missao(corpo, cabecalhos.get("idempotency-key"))
        if metodo == "POST" and caminho == "/v1/claims/evaluate":
            return self.avaliar_publicacao(corpo)

        casamento = _ROTA_MISSAO.match(caminho)
        if casamento and metodo == "GET":
            return self.obter_missao(casamento.group("id"), tenant)

        transicao = re.match(r"^/v1/missions/(?P<id>[A-Za-z0-9_-]+)/transitions$",
                             caminho)
        if transicao and metodo == "POST":
            return self.transicionar_missao(transicao.group("id"), tenant, corpo)

        return 404, problema(404, "Rota nao encontrada", f"{metodo} {caminho}")


def criar_handler(api: ControlAPI):
    """Constroi o handler HTTP ligado a uma instancia de ``ControlAPI``."""

    class Handler(BaseHTTPRequestHandler):
        """Adaptador HTTP fino sobre ``ControlAPI``."""

        server_version = "vfos-control/1.0"
        protocol_version = "HTTP/1.1"

        def _responder(self, status: int, corpo: dict[str, Any],
                       trace_id: str = "") -> None:
            dados = json.dumps(corpo, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            if trace_id:
                self.send_header("X-Trace-Id", trace_id)
            self.end_headers()
            self.wfile.write(dados)

        def _cabecalhos(self) -> dict[str, str]:
            return {k.lower(): v for k, v in self.headers.items()}

        def _corpo(self) -> tuple[bool, Any]:
            tamanho = int(self.headers.get("Content-Length") or 0)
            if tamanho > MAX_CORPO:
                return False, problema(413, "Corpo grande demais",
                                       f"limite de {MAX_CORPO} bytes")
            if tamanho == 0:
                return True, {}
            try:
                return True, json.loads(self.rfile.read(tamanho))
            except json.JSONDecodeError as erro:
                return False, problema(400, "JSON invalido", str(erro))

        def _atender(self, metodo: str) -> None:
            cabecalhos = self._cabecalhos()
            ok, corpo = self._corpo()
            if not ok:
                self._responder(corpo["status"], corpo)
                return
            with TRACER.span("http.request", method=metodo,
                             route=self.path.split("?")[0]) as span:
                status, resposta = api.rotear(metodo, self.path.split("?")[0],
                                              corpo, cabecalhos)
                span.set("http.status_code", status)
                self._responder(status, resposta, span.trace_id)

        def do_GET(self) -> None:  # noqa: N802 - exigido pela classe base
            """Atende requisicoes GET."""
            self._atender("GET")

        def do_POST(self) -> None:  # noqa: N802 - exigido pela classe base
            """Atende requisicoes POST."""
            self._atender("POST")

        def log_message(self, formato: str, *args) -> None:
            """Silencia o log de acesso padrao; a telemetria ja registra."""
            return None

    return Handler


def criar_servidor(api: ControlAPI, host: str = "127.0.0.1",
                   porta: int = 8080) -> HTTPServer:
    """Cria o servidor HTTP vinculado. Porta 0 escolhe uma livre."""
    return HTTPServer((host, porta), criar_handler(api))
