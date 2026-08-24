#!/usr/bin/env python3
"""Exemplo 2 — Uma integração quebrada não derruba o painel inteiro.

Sem breaker: a dependência trava, cada requisição fica esperando, e o processo
morre exaurido. Com breaker: a falha vira local, rápida e explícita.

Rode:  python3 exemplos/02_breaker_contem_falha.py
"""

from _comum import licao, passo, titulo  # noqa: F401

from syra_core import BreakerPolicy, CircuitBreaker
from syra_core.errors import BreakerOpen


class RelogioFalso:
    """Relógio controlado — o exemplo não precisa esperar 20 segundos reais."""

    def __init__(self) -> None:
        self.agora = 0.0

    def __call__(self) -> float:
        return self.agora

    def avancar(self, segundos: float) -> None:
        self.agora += segundos
        print("   (tempo avançou {}s)".format(segundos))


def main() -> int:
    titulo("EXEMPLO 2 — Circuit breaker contém uma dependência doente")

    relogio = RelogioFalso()
    breaker = CircuitBreaker(
        "api-railway",
        BreakerPolicy(failure_threshold=3, recovery_seconds=20.0),
        clock=relogio,
    )

    contatos = {"total": 0}

    def dependencia_quebrada(_payload=None):
        contatos["total"] += 1
        raise RuntimeError("connection refused")

    # ------------------------------------------------------------------
    passo(1, "Estado inicial: FECHADO, tudo passa")
    print("Estado:", breaker.state)

    # ------------------------------------------------------------------
    passo(2, "Três falhas seguidas abrem o breaker")

    for tentativa in (1, 2, 3):
        try:
            breaker.call(dependencia_quebrada)
        except RuntimeError as erro:
            print("   tentativa {}: falhou ({}) — estado agora: {}".format(
                tentativa, erro, breaker.state
            ))

    # ------------------------------------------------------------------
    passo(3, "Com o breaker ABERTO, a dependência não é nem contatada")

    contatos_antes = contatos["total"]
    for tentativa in (4, 5, 6):
        try:
            breaker.call(dependencia_quebrada)
        except BreakerOpen as erro:
            print("   tentativa {}: RECUSADA sem sair da máquina".format(tentativa))
            print("      retry_after: {}s".format(
                erro.detail["retry_after_seconds"]
            ))

    print()
    print("Dependência foi contatada {} vezes nessas 3 tentativas.".format(
        contatos["total"] - contatos_antes
    ))

    licao(
        "Zero. É isso que impede uma dependência lenta de enfileirar "
        "requisições até esgotar o processo. A falha custa microssegundos, "
        "não o timeout inteiro."
    )

    # ------------------------------------------------------------------
    passo(4, "Passada a janela de recuperação, ele testa de novo")

    relogio.avancar(21.0)
    print("Estado:", breaker.state, "(uma chamada de teste é permitida)")

    # ------------------------------------------------------------------
    passo(5, "A dependência voltou — o breaker fecha sozinho")

    def dependencia_curada(_payload=None):
        return {"ok": True}

    resultado = breaker.call(dependencia_curada)
    print("Chamada de teste:", resultado)
    print("Estado:", breaker.state)

    print()
    print("Resumo:", breaker.snapshot())

    licao(
        "Recuperação é automática e sem retry cego. O breaker deixa de "
        "insistir numa dependência doente — insistir só multiplica a carga "
        "sobre quem já está caindo."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
