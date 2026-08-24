#!/usr/bin/env python3
"""Exemplo 3 — O mesmo erro não é redescoberto do zero toda semana.

Erro repetido não é azar: é ausência de memória. O defeito é contornado, o
contorno é esquecido, e seis semanas depois custa o mesmo dia de depuração.

Rode:  python3 exemplos/03_memoria_de_falhas.py
"""

from _comum import TEMP, licao, passo, titulo  # noqa: F401

from syra_core.errors import ConnectorFailure, RepeatedFailure
from syra_core.failure_memory import FailureMemory, normalise


def main() -> int:
    titulo("EXEMPLO 3 — Memória de falhas: defeito ganha identidade")

    memoria = FailureMemory(TEMP / "falhas.json")

    # ------------------------------------------------------------------
    passo(1, "Mensagens diferentes, MESMO defeito")

    a = "connection refused to 10.0.0.5:8080"
    b = "connection refused to 192.168.1.9:9090"

    print("Mensagem A:", a)
    print("Mensagem B:", b)
    print()
    print("Normalizada A:", normalise(a))
    print("Normalizada B:", normalise(b))
    print()
    print("São o mesmo defeito?", "SIM" if normalise(a) == normalise(b) else "NAO")

    licao(
        "IPs, portas, ids, caminhos e números são removidos. Sem isso, a "
        "memória viraria uma lista de ocorrências únicas e não aprenderia nada."
    )

    # ------------------------------------------------------------------
    passo(2, "Três ocorrências viram UM registro com contagem 3")

    for mensagem in (a, b, "connection refused to 172.16.0.3:5432"):
        memoria.record(ConnectorFailure(mensagem), site="gateway.railway")

    registro = memoria.all()[0]
    print(registro.render())
    print()
    print("Total de defeitos distintos:", len(memoria.all()))
    print("Total de ocorrências:", memoria.stats()["occurrences"])

    # ------------------------------------------------------------------
    passo(3, "Modo bloqueante: repetir defeito conhecido é RECUSADO")

    bloqueante = FailureMemory(TEMP / "falhas.json", block_repeats=True)
    try:
        bloqueante.guard("gateway.railway")
    except RepeatedFailure as erro:
        print("BLOQUEADO —", erro.message)
        print()
        print("O que fazer:", erro.remediation)

    licao(
        "Em trabalho não-supervisionado (cron, agente autônomo), isso evita "
        "queimar uma execução inteira repetindo algo que já se sabe que falha."
    )

    # ------------------------------------------------------------------
    passo(4, "Corrigiu? Registre. Aí para de bloquear.")

    memoria.resolve(registro.fingerprint, "timeout do railway subiu para 15s")
    print("Status agora:", memoria.get(registro.fingerprint).status)
    print("Defeitos abertos:", len(memoria.open_failures()))

    bloqueante = FailureMemory(TEMP / "falhas.json", block_repeats=True)
    print("guard() agora retorna:", bloqueante.guard("gateway.railway"))

    # ------------------------------------------------------------------
    passo(5, "Voltou? Ele REABRE e guarda a correção que não funcionou")

    memoria.record(ConnectorFailure(a), site="gateway.railway")
    reaberto = memoria.get(registro.fingerprint)
    print("Status:", reaberto.status)
    print("Histórico:", reaberto.resolution)
    print("Contagem total:", reaberto.count)

    licao(
        "Um defeito resolvido que voltou não estava resolvido. Manter "
        "RESOLVED seria mentir para quem lê depois — e a nota antiga fica "
        "como registro de que aquela correção não bastou."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
