"""Persistencia de missao com outbox transacional.

O problema que este modulo resolve: gravar o agregado e publicar o evento sao
duas escritas. Se forem dois recursos, existe uma janela em que o estado mudou
e ninguem soube — ou em que o evento saiu e o estado nao mudou. O outbox
transacional elimina a janela: agregado e evento entram na MESMA transacao,
e a publicacao le do outbox depois.

Ha dois adapters atras da mesma porta. O de memoria serve a teste rapido; o
de SQLite da durabilidade real sem exigir servidor. Os testes de contrato
rodam identicos nos dois — e o PostgreSQL entra pela mesma porta quando a
operacao justificar, sem tocar no dominio.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Protocol

from syra.vfos import contracts, policy
from syra.vfos.mission import Estado, Mission, Transicao


class ConflitoDeVersao(RuntimeError):
    """Outra escrita alterou a missao desde a leitura (optimistic locking)."""


class MissaoNaoEncontrada(KeyError):
    """A missao pedida nao existe neste tenant."""


@dataclass(frozen=True)
class MensagemOutbox:
    """Um evento pendente de publicacao."""

    outbox_id: int
    mission_id: str
    tipo: str
    payload: dict[str, Any]
    idempotency_key: str
    tentativas: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"outbox_id": self.outbox_id, "mission_id": self.mission_id,
                "type": self.tipo, "payload": self.payload,
                "idempotency_key": self.idempotency_key,
                "attempts": self.tentativas}


class MissionRepository(Protocol):
    """Porta de persistencia. O dominio depende disto, nunca de SQL."""

    def salvar(self, mission: Mission, eventos: list[dict[str, Any]],
               versao_esperada: int | None = None) -> Mission:
        """Grava agregado e eventos atomicamente."""
        ...

    def obter(self, tenant_id: str, mission_id: str) -> Mission:
        """Le uma missao; levanta ``MissaoNaoEncontrada`` se nao existir."""
        ...

    def listar(self, tenant_id: str, limite: int = 50) -> list[Mission]:
        """Lista missoes do tenant, mais recentes primeiro."""
        ...

    def pendentes(self, limite: int = 20) -> list[MensagemOutbox]:
        """Mensagens do outbox ainda nao publicadas."""
        ...

    def marcar_publicada(self, outbox_id: int) -> None:
        """Marca a mensagem como publicada; operacao idempotente."""
        ...

    def registrar_falha(self, outbox_id: int, erro: str) -> int:
        """Incrementa tentativas e devolve o total acumulado."""
        ...

    def ja_processado(self, idempotency_key: str) -> bool:
        """Indica se a chave de idempotencia ja foi consumida."""
        ...

    def reservar_processamento(self, idempotency_key: str, dono: str) -> bool:
        """Reivindica a chave para ``dono``.

        Devolve True quando o chamador passa a deter a reserva — inclusive
        quando ja a detinha, o que permite retomar a propria tentativa que
        falhou. Devolve False apenas quando OUTRO dono detem a chave, que e
        a duplicata verdadeira.
        """
        ...

    def liberar_processamento(self, idempotency_key: str, dono: str) -> None:
        """Devolve a reserva quando o trabalho falhou, permitindo retentativa."""
        ...

    def marcar_processado(self, idempotency_key: str, resultado: str) -> bool:
        """Registra o consumo definitivo da chave. False se ja existia."""
        ...


def _exigir_eventos_validos(eventos: list[dict[str, Any]]) -> None:
    """Valida os eventos contra o contrato antes de qualquer escrita.

    Falhar aqui, fora da transacao, garante que um evento malformado nunca
    chegue a competir com a gravacao do agregado.
    """
    contrato = contracts.get("event")
    for evento in eventos:
        contrato.exigir(evento)


def _reconstruir(payload: dict, estado: str, versao: int,
                 historico: list[dict]) -> Mission:
    """Remonta o agregado a partir da forma persistida."""
    return Mission(
        payload=payload,
        estado=Estado(estado),
        versao=versao,
        historico=tuple(
            Transicao(de=Estado(h["from"]), para=Estado(h["to"]), ator=h["actor"],
                      motivo=h["reason"], em=h["at"],
                      decision_id=h.get("decision_id"))
            for h in historico
        ),
    )


class MemoryMissionRepository:
    """Adapter em memoria: rapido, isolado, sem I/O."""

    def __init__(self) -> None:
        self._missoes: dict[tuple[str, str], Mission] = {}
        self._outbox: list[dict[str, Any]] = []
        self._processados: dict[str, str] = {}
        self._proximo_id = 1
        self._lock = threading.RLock()

    def salvar(self, mission: Mission, eventos: list[dict[str, Any]],
               versao_esperada: int | None = None) -> Mission:
        _exigir_eventos_validos(eventos)
        chave = (mission.tenant_id, mission.mission_id)
        with self._lock:
            atual = self._missoes.get(chave)
            if versao_esperada is not None:
                versao_atual = atual.versao if atual else 0
                if versao_atual != versao_esperada:
                    raise ConflitoDeVersao(
                        f"versao esperada {versao_esperada}, encontrada {versao_atual}")
            self._missoes[chave] = mission
            # Deduplicacao por chave de idempotencia, igual a restricao UNIQUE
            # do adapter SQLite: os dois precisam se comportar identicamente,
            # senao o teste de contrato compartilhado nao prova nada.
            ja_enfileiradas = {m["idempotency_key"] for m in self._outbox}
            for evento in eventos:
                if evento["idempotency_key"] in ja_enfileiradas:
                    continue
                ja_enfileiradas.add(evento["idempotency_key"])
                self._outbox.append({
                    "outbox_id": self._proximo_id, "mission_id": mission.mission_id,
                    "tipo": evento["event_name"], "payload": evento,
                    "idempotency_key": evento["idempotency_key"],
                    "publicada": False, "tentativas": 0,
                })
                self._proximo_id += 1
            return mission

    def obter(self, tenant_id: str, mission_id: str) -> Mission:
        with self._lock:
            mission = self._missoes.get((tenant_id, mission_id))
        if mission is None:
            raise MissaoNaoEncontrada(f"{mission_id} nao existe em {tenant_id}")
        return mission

    def listar(self, tenant_id: str, limite: int = 50) -> list[Mission]:
        with self._lock:
            achadas = [m for (t, _), m in self._missoes.items() if t == tenant_id]
        return sorted(achadas, key=lambda m: m.payload["created_at"],
                      reverse=True)[:limite]

    def pendentes(self, limite: int = 20) -> list[MensagemOutbox]:
        with self._lock:
            return [
                MensagemOutbox(m["outbox_id"], m["mission_id"], m["tipo"],
                               m["payload"], m["idempotency_key"], m["tentativas"])
                for m in self._outbox if not m["publicada"]
            ][:limite]

    def marcar_publicada(self, outbox_id: int) -> None:
        with self._lock:
            for m in self._outbox:
                if m["outbox_id"] == outbox_id:
                    m["publicada"] = True

    def registrar_falha(self, outbox_id: int, erro: str) -> int:
        with self._lock:
            for m in self._outbox:
                if m["outbox_id"] == outbox_id:
                    m["tentativas"] += 1
                    m["ultimo_erro"] = erro[:500]
                    return m["tentativas"]
        return 0

    def ja_processado(self, idempotency_key: str) -> bool:
        with self._lock:
            return idempotency_key in self._processados

    def reservar_processamento(self, idempotency_key: str, dono: str) -> bool:
        with self._lock:
            atual = self._processados.get(idempotency_key)
            if atual is None:
                self._processados[idempotency_key] = dono
                return True
            return atual == dono

    def liberar_processamento(self, idempotency_key: str, dono: str) -> None:
        with self._lock:
            if self._processados.get(idempotency_key) == dono:
                del self._processados[idempotency_key]

    def marcar_processado(self, idempotency_key: str, resultado: str) -> bool:
        with self._lock:
            if idempotency_key in self._processados:
                return False
            self._processados[idempotency_key] = resultado
            return True


_DDL = """
CREATE TABLE IF NOT EXISTS missions (
    tenant_id   TEXT NOT NULL,
    mission_id  TEXT NOT NULL,
    state       TEXT NOT NULL,
    version     INTEGER NOT NULL,
    payload     TEXT NOT NULL,
    history     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (tenant_id, mission_id)
);
CREATE TABLE IF NOT EXISTS outbox (
    outbox_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id      TEXT NOT NULL,
    type            TEXT NOT NULL,
    payload         TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    published       INTEGER NOT NULL DEFAULT 0,
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outbox_pendentes
    ON outbox(published, outbox_id);
CREATE TABLE IF NOT EXISTS processed_keys (
    idempotency_key TEXT PRIMARY KEY,
    result          TEXT NOT NULL,
    processed_at    TEXT NOT NULL
);
"""


class SqliteMissionRepository:
    """Adapter duravel em SQLite, com outbox na mesma transacao.

    SQLite e escolha deliberada para o MVP: da durabilidade, transacao e
    unicidade sem exigir servidor, e mantem o pacote executavel em qualquer
    maquina. A porta permanece a mesma para PostgreSQL.
    """

    def __init__(self, caminho: Path | str = ":memory:") -> None:
        self.caminho = str(caminho)
        self._local = threading.local()
        with self._conexao() as conexao:
            conexao.executescript(_DDL)

    def _conectar(self) -> sqlite3.Connection:
        conexao = sqlite3.connect(self.caminho, timeout=10,
                                  isolation_level=None, check_same_thread=False)
        conexao.row_factory = sqlite3.Row
        conexao.execute("PRAGMA journal_mode=WAL")
        conexao.execute("PRAGMA foreign_keys=ON")
        return conexao

    @contextmanager
    def _conexao(self) -> Iterator[sqlite3.Connection]:
        # Uma conexao por thread: SQLite nao compartilha conexao com seguranca.
        conexao = getattr(self._local, "conexao", None)
        if conexao is None:
            conexao = self._conectar()
            self._local.conexao = conexao
        yield conexao

    @contextmanager
    def _transacao(self) -> Iterator[sqlite3.Connection]:
        with self._conexao() as conexao:
            conexao.execute("BEGIN IMMEDIATE")
            try:
                yield conexao
            except Exception:
                conexao.execute("ROLLBACK")
                raise
            conexao.execute("COMMIT")

    def salvar(self, mission: Mission, eventos: list[dict[str, Any]],
               versao_esperada: int | None = None) -> Mission:
        _exigir_eventos_validos(eventos)
        agora = policy.agora_iso()
        with self._transacao() as conexao:
            linha = conexao.execute(
                "SELECT version FROM missions WHERE tenant_id=? AND mission_id=?",
                (mission.tenant_id, mission.mission_id)).fetchone()
            versao_atual = linha["version"] if linha else 0

            if versao_esperada is not None and versao_atual != versao_esperada:
                raise ConflitoDeVersao(
                    f"versao esperada {versao_esperada}, encontrada {versao_atual}")

            dados = mission.to_dict()
            conexao.execute(
                """INSERT INTO missions
                       (tenant_id, mission_id, state, version, payload, history,
                        created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(tenant_id, mission_id) DO UPDATE SET
                       state=excluded.state, version=excluded.version,
                       payload=excluded.payload, history=excluded.history,
                       updated_at=excluded.updated_at""",
                (mission.tenant_id, mission.mission_id, mission.estado.value,
                 mission.versao, json.dumps(dados["mission"], ensure_ascii=False),
                 json.dumps(dados["history"], ensure_ascii=False),
                 mission.payload["created_at"], agora))

            for evento in eventos:
                # ON CONFLICT no indice de idempotencia, e NAO "OR IGNORE":
                # "OR IGNORE" tambem engoliria violacao de NOT NULL, deixando
                # o agregado comitar sem o evento — exatamente a janela que o
                # outbox existe para fechar.
                conexao.execute(
                    """INSERT INTO outbox
                           (mission_id, type, payload, idempotency_key, created_at)
                       VALUES (?,?,?,?,?)
                       ON CONFLICT(idempotency_key) DO NOTHING""",
                    (mission.mission_id, evento["event_name"],
                     json.dumps(evento, ensure_ascii=False),
                     evento["idempotency_key"], agora))
        return mission

    def obter(self, tenant_id: str, mission_id: str) -> Mission:
        with self._conexao() as conexao:
            linha = conexao.execute(
                """SELECT payload, state, version, history FROM missions
                   WHERE tenant_id=? AND mission_id=?""",
                (tenant_id, mission_id)).fetchone()
        if linha is None:
            raise MissaoNaoEncontrada(f"{mission_id} nao existe em {tenant_id}")
        return _reconstruir(json.loads(linha["payload"]), linha["state"],
                            linha["version"], json.loads(linha["history"]))

    def listar(self, tenant_id: str, limite: int = 50) -> list[Mission]:
        with self._conexao() as conexao:
            linhas = conexao.execute(
                """SELECT payload, state, version, history FROM missions
                   WHERE tenant_id=? ORDER BY created_at DESC LIMIT ?""",
                (tenant_id, limite)).fetchall()
        return [_reconstruir(json.loads(l["payload"]), l["state"], l["version"],
                             json.loads(l["history"])) for l in linhas]

    def pendentes(self, limite: int = 20) -> list[MensagemOutbox]:
        with self._conexao() as conexao:
            linhas = conexao.execute(
                """SELECT outbox_id, mission_id, type, payload, idempotency_key,
                          attempts
                   FROM outbox WHERE published=0
                   ORDER BY outbox_id LIMIT ?""", (limite,)).fetchall()
        return [MensagemOutbox(l["outbox_id"], l["mission_id"], l["type"],
                               json.loads(l["payload"]), l["idempotency_key"],
                               l["attempts"]) for l in linhas]

    def marcar_publicada(self, outbox_id: int) -> None:
        with self._transacao() as conexao:
            conexao.execute("UPDATE outbox SET published=1 WHERE outbox_id=?",
                            (outbox_id,))

    def registrar_falha(self, outbox_id: int, erro: str) -> int:
        with self._transacao() as conexao:
            conexao.execute(
                "UPDATE outbox SET attempts=attempts+1, last_error=? WHERE outbox_id=?",
                (erro[:500], outbox_id))
            linha = conexao.execute(
                "SELECT attempts FROM outbox WHERE outbox_id=?",
                (outbox_id,)).fetchone()
        return linha["attempts"] if linha else 0

    def ja_processado(self, idempotency_key: str) -> bool:
        with self._conexao() as conexao:
            linha = conexao.execute(
                "SELECT 1 FROM processed_keys WHERE idempotency_key=?",
                (idempotency_key,)).fetchone()
        return linha is not None

    def reservar_processamento(self, idempotency_key: str, dono: str) -> bool:
        with self._transacao() as conexao:
            conexao.execute(
                """INSERT INTO processed_keys
                       (idempotency_key, result, processed_at)
                   VALUES (?,?,?)
                   ON CONFLICT(idempotency_key) DO NOTHING""",
                (idempotency_key, dono, policy.agora_iso()))
            linha = conexao.execute(
                "SELECT result FROM processed_keys WHERE idempotency_key=?",
                (idempotency_key,)).fetchone()
        return bool(linha) and linha["result"] == dono

    def liberar_processamento(self, idempotency_key: str, dono: str) -> None:
        with self._transacao() as conexao:
            conexao.execute(
                "DELETE FROM processed_keys WHERE idempotency_key=? AND result=?",
                (idempotency_key, dono))

    def marcar_processado(self, idempotency_key: str, resultado: str) -> bool:
        try:
            with self._transacao() as conexao:
                conexao.execute(
                    """INSERT INTO processed_keys
                           (idempotency_key, result, processed_at)
                       VALUES (?,?,?)""",
                    (idempotency_key, resultado, policy.agora_iso()))
            return True
        except sqlite3.IntegrityError:
            # Chave ja consumida: consumo concorrente perdeu a corrida.
            return False
