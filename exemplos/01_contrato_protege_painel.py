#!/usr/bin/env python3
"""Exemplo 1 — O contrato impede que backend e painel se quebrem em silêncio.

Este é o problema número um: o backend muda, o painel continua mandando o
formato antigo, e a falha aparece três camadas depois como um erro sem sentido.

Rode:  python3 exemplos/01_contrato_protege_painel.py
"""

from _comum import licao, passo, titulo  # noqa: F401  (prepara o sys.path)

from syra_core import Contract, ContractRegistry
from syra_core.contracts import compatibility
from syra_core.errors import ContractIncompatible, ContractViolation

PEDIDO_V1 = {
    "type": "object",
    "required": ["cliente_id", "valor"],
    "additionalProperties": False,
    "properties": {
        "cliente_id": {"type": "string", "minLength": 1},
        "valor": {"type": "number", "minimum": 0},
        "cupom": {"type": "string"},
    },
}


def main() -> int:
    titulo("EXEMPLO 1 — Contrato protege a fronteira painel <-> backend")

    registro = ContractRegistry()
    registro.define("pedido.criar", "1.0.0", PEDIDO_V1)

    # ------------------------------------------------------------------
    passo(1, "Payload correto passa")

    bom = {"cliente_id": "c-42", "valor": 199.90}
    registro.enforce("pedido.criar", bom)
    print("OK — payload aceito:", bom)

    # ------------------------------------------------------------------
    passo(2, "Payload errado é recusado APONTANDO O CAMPO EXATO")

    ruim = {"cliente_id": "", "valor": -10, "desconto": 5}
    try:
        registro.enforce("pedido.criar", ruim)
    except ContractViolation as erro:
        print("RECUSADO —", erro.message)
        print()
        for violacao in erro.violations:
            print("   {} -> {} :: {}".format(
                violacao["pointer"], violacao["code"], violacao["message"]
            ))

    licao(
        "Todas as violações vêm de uma vez, cada uma com o caminho do campo. "
        "Uma ida ao servidor te diz tudo que está errado, não só a primeira coisa."
    )

    # ------------------------------------------------------------------
    passo(3, "Adicionar campo OPCIONAL é seguro")

    v1_1 = {
        **PEDIDO_V1,
        "properties": {**PEDIDO_V1["properties"], "observacao": {"type": "string"}},
    }
    relatorio = compatibility(PEDIDO_V1, v1_1)
    print("Veredito:", relatorio.verdict)
    print("Seguro para subir?", "SIM" if relatorio.is_safe else "NAO")
    print("Mudanças aditivas:", relatorio.additive)

    # ------------------------------------------------------------------
    passo(4, "Tornar um campo OBRIGATÓRIO quebra quem já está no ar")

    v2 = {**PEDIDO_V1, "required": ["cliente_id", "valor", "cupom"]}
    relatorio = compatibility(PEDIDO_V1, v2)
    print("Veredito:", relatorio.verdict)
    print("Seguro para subir?", "SIM" if relatorio.is_safe else "NAO")
    for mudanca in relatorio.breaking:
        print("   QUEBRA: {} em {}".format(mudanca["change"], mudanca["pointer"]))

    # ------------------------------------------------------------------
    passo(5, "O registro RECUSA registrar isso sem decisão explícita")

    try:
        registro.define("pedido.criar", "2.0.0", v2)
    except ContractIncompatible as erro:
        print("RECUSADO —", erro.message)
        print("O que fazer:", erro.remediation)

    print()
    print("Se a quebra for intencional, ela vira uma decisão consciente:")
    registro.define("pedido.criar", "2.0.0", v2, allow_breaking=True)
    print("Registrado com allow_breaking=True. Versões:",
          registro.versions("pedido.criar"))

    licao(
        "A pergunta 'isso quebra o painel?' é respondida ANTES de subir, "
        "não depois pelo suporte. E quebrar deixa de ser acidente: vira "
        "algo que alguém decidiu e pode apontar."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
