"""Worker do outbox: publica eventos sem duplicar efeito.

Tres garantias, nesta ordem:

1. **Idempotencia.** A chave do evento e consultada antes de publicar e
   marcada depois. Reentrega nao produz efeito duplo.
2. **Retry delimitado.** Falha incrementa tentativas com backoff exponencial
   limitado. Nao existe retry infinito consumindo recurso.
3. **Dead letter.** Estourado o teto, a mensagem para de ser tentada e fica
   visivel para inspecao — em vez de girar para sempre ou sumir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from syra.vfos.store import MensagemOutbox, MissionRepository
from syra.vfos.telemetry import TRACER, Tracer

MAX_TENTATIVAS = 5
BACKOFF_BASE_SEGUNDOS = 2.0
BACKOFF_MAXIMO_SEGUNDOS = 300.0


class Publicador(Protocol):
    """Destino dos eventos. Trocavel sem tocar no worker."""

    def publicar(self, evento: dict[str, Any]) -> None:
        """Entrega o evento; excecao sinaliza falha e provoca retry."""
        ...


class PublicadorEmMemoria:
    """Publicador de teste que apenas acumula o que recebeu."""

    def __init__(self) -> None:
        self.publicados: list[dict[str, Any]] = []

    def publicar(self, evento: dict[str, Any]) -> None:
        self.publicados.append(evento)


@dataclass(frozen=True)
class ResultadoLote:
    """Contabilidade de um ciclo de processamento."""

    processadas: int
    publicadas: int
    duplicadas: int
    falhas: int
    dead_letter: int

    def to_dict(self) -> dict[str, int]:
        return {"processed": self.processadas, "published": self.publicadas,
                "duplicated": self.duplicadas, "failed": self.falhas,
                "dead_letter": self.dead_letter}


def backoff_segundos(tentativas: int) -> float:
    """Espera antes da proxima tentativa, com teto.

    O teto existe para que uma indisponibilidade longa nao produza uma espera
    que na pratica nunca termina.
    """
    if tentativas <= 0:
        return 0.0
    return min(BACKOFF_BASE_SEGUNDOS * (2 ** (tentativas - 1)),
               BACKOFF_MAXIMO_SEGUNDOS)


class OutboxWorker:
    """Consome o outbox e publica com idempotencia e retry delimitado."""

    def __init__(self, repositorio: MissionRepository, publicador: Publicador,
                 max_tentativas: int = MAX_TENTATIVAS,
                 tracer: Tracer | None = None) -> None:
        self.repositorio = repositorio
        self.publicador = publicador
        self.max_tentativas = max_tentativas
        self.tracer = tracer or TRACER

    def processar_lote(self, limite: int = 20) -> ResultadoLote:
        """Processa ate ``limite`` mensagens pendentes."""
        publicadas = duplicadas = falhas = mortas = 0
        pendentes = self.repositorio.pendentes(limite)

        for mensagem in pendentes:
            estado = self._processar_uma(mensagem)
            if estado == "publicada":
                publicadas += 1
            elif estado == "duplicada":
                duplicadas += 1
            elif estado == "dead_letter":
                mortas += 1
            else:
                falhas += 1

        return ResultadoLote(processadas=len(pendentes), publicadas=publicadas,
                             duplicadas=duplicadas, falhas=falhas,
                             dead_letter=mortas)

    def _processar_uma(self, mensagem: MensagemOutbox) -> str:
        with self.tracer.span("outbox.publish", outbox_id=mensagem.outbox_id,
                              event_type=mensagem.tipo) as span:
            if mensagem.tentativas >= self.max_tentativas:
                span.set("outcome", "dead_letter")
                return "dead_letter"

            # A reserva acontece ANTES da publicacao e vence a corrida entre
            # workers. O dono e a propria mensagem: se a publicacao falhar, a
            # reserva e devolvida e a MESMA mensagem pode tentar de novo. Sem
            # isso, uma falha marcaria a chave para sempre e o evento seria
            # descartado como "duplicata" — perda silenciosa.
            dono = f"outbox:{mensagem.outbox_id}"
            if not self.repositorio.reservar_processamento(
                    mensagem.idempotency_key, dono):
                self.repositorio.marcar_publicada(mensagem.outbox_id)
                span.set("outcome", "duplicada")
                return "duplicada"

            try:
                self.publicador.publicar(mensagem.payload)
            except Exception as erro:
                self.repositorio.liberar_processamento(
                    mensagem.idempotency_key, dono)
                tentativas = self.repositorio.registrar_falha(
                    mensagem.outbox_id, f"{type(erro).__name__}: {erro}")
                span.set("outcome", "falha")
                span.set("attempts", tentativas)
                span.set("next_retry_seconds", backoff_segundos(tentativas))
                return "dead_letter" if tentativas >= self.max_tentativas else "falha"

            self.repositorio.marcar_publicada(mensagem.outbox_id)
            span.set("outcome", "publicada")
            return "publicada"

    def drenar(self, max_ciclos: int = 100) -> ResultadoLote:
        """Processa ate esvaziar o outbox ou atingir o limite de ciclos.

        O limite de ciclos existe para que uma mensagem em falha permanente
        nao transforme a drenagem num laco infinito.
        """
        total = ResultadoLote(0, 0, 0, 0, 0)
        for _ in range(max_ciclos):
            lote = self.processar_lote()
            total = ResultadoLote(
                total.processadas + lote.processadas,
                total.publicadas + lote.publicadas,
                total.duplicadas + lote.duplicadas,
                total.falhas + lote.falhas,
                total.dead_letter + lote.dead_letter)
            if lote.processadas == 0 or lote.publicadas + lote.duplicadas == 0:
                break
        return total
