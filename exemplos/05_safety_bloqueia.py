#!/usr/bin/env python3
"""Exemplo 5 — Autoridade negada bloqueia ANTES da chamada cara.

Esta é a trava anti-autossabotagem mais importante: um gate de análise
read-only não consegue fazer chamada de rede nem mutar fonte, mesmo que alguém
registre um conector que faria isso.

Rode:  python3 exemplos/05_safety_bloqueia.py
"""

from _comum import licao, passo, titulo  # noqa: F401

from syra_core import ContractRegistry, IntegrationGateway, SafetyContract
from syra_core.connector import http_connector, service_connector
from syra_core.errors import SafetyDenied


def main() -> int:
    titulo("EXEMPLO 5 — Fail-closed: negado por padrão, impossível ampliar")

    # ------------------------------------------------------------------
    passo(1, "O contrato de um gate de análise estática")

    analise = SafetyContract.static_analysis("PPC00A_DESCOBERTA")
    print(analise.render())
    print()
    print("Concedido:", ", ".join(analise.granted()))

    licao(
        "Ele lê fontes e git, e escreve evidência (fora do workspace). "
        "'source_mutation' fica negada — é por isso que o scanner nunca "
        "pode ser a explicação para um arquivo alterado."
    )

    # ------------------------------------------------------------------
    passo(2, "Pedir autoridade que não foi concedida é recusado")

    try:
        analise.require("network", "deploy", site="exemplo")
    except SafetyDenied as erro:
        print("RECUSADO —", erro.message)
        print("faltando:", erro.detail["missing"])
        print("o que fazer:", erro.remediation)

    # ------------------------------------------------------------------
    passo(3, "NÃO EXISTE como ampliar autoridade em runtime")

    try:
        analise.narrow(network=True)
    except SafetyDenied as erro:
        print("RECUSADO —", erro.message)
        print("tentativa de escalada:", erro.detail["attempted_escalation"])

    print()
    print("Reduzir sempre funciona:")
    filho = analise.narrow(filesystem_write=False, purpose="FILHO")
    print("   pai   ->", ", ".join(analise.granted()))
    print("   filho ->", ", ".join(filho.granted()))

    licao(
        "Só existe narrow(). Não existe widen(). Se existisse um caminho "
        "para ampliar, ele seria usado — por pressa, por bug, ou por um "
        "except mal colocado. Não existir é mais forte que existir e ser "
        "desencorajado."
    )

    # ------------------------------------------------------------------
    passo(4, "Na prática: um conector HTTP dentro de um gate read-only")

    gateway = IntegrationGateway(
        safety=analise, contracts=ContractRegistry()
    )
    gateway.register(http_connector(
        "api-externa",
        base_url="https://exemplo.invalido",
        path="/dados",
    ))
    print("Conector registrado:", gateway.names())
    print("Ele declara precisar de:",
          gateway.get("api-externa").spec.required_capabilities)

    resultado = gateway.invoke("api-externa", {"x": 1})
    print()
    print("ok:", resultado.ok)
    print("parou na etapa:", resultado.stage)
    print("código:", resultado.error["code"])

    licao(
        "Parou em 'safety', a PRIMEIRA etapa. Nenhum pacote saiu da máquina. "
        "Registrar o conector foi permitido; usá-lo não. É o mecanismo "
        "funcionando, não um bug."
    )

    # ------------------------------------------------------------------
    passo(5, "Por que 'safety' vem antes de tudo no pipeline")

    print("Ordem do gateway:")
    print("   safety -> memória -> contrato-in -> breaker -> timeout")
    print("          -> chamada -> contrato-out -> trace")
    print()
    print("Barato e local antes de caro e remoto. Uma autoridade faltando")
    print("falha em microssegundos. Se 'safety' viesse depois de 'breaker',")
    print("o mesmo erro custaria uma ida à dependência.")

    gateway.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
