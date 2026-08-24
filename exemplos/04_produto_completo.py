#!/usr/bin/env python3
"""Exemplo 4 — Um produto inteiro, blindado, em ~30 linhas.

Mostra o caminho real de plugar: um agente e um serviço interno entrando no
gateway e herdando contratos, breaker, health, trace e memória de falhas sem
mudar o código deles.

Rode:  python3 exemplos/04_produto_completo.py
"""

import json

from _comum import TEMP, licao, passo, titulo  # noqa: F401

from syra_core import ProductRuntime, agent_connector, service_connector
from syra_core.health import healthy, unhealthy

PEDIDO = {
    "type": "object",
    "required": ["objetivo"],
    "properties": {"objetivo": {"type": "string", "minLength": 1}},
}

PLANO = {
    "type": "object",
    "required": ["ok", "passos"],
    "properties": {
        "ok": {"type": "boolean"},
        "passos": {"type": "array", "items": {"type": "string"}},
    },
}


def meu_agente(payload):
    """Um agente qualquer. Não sabe que existe núcleo, e não precisa saber."""
    objetivo = payload["objetivo"]
    return {"ok": True, "passos": ["analisar " + objetivo, "executar", "validar"]}


def analytics(payload):
    """Dependência opcional que está fora do ar."""
    raise RuntimeError("serviço de analytics indisponível")


def main() -> int:
    titulo("EXEMPLO 4 — Produto completo com tudo blindado")

    # ------------------------------------------------------------------
    passo(1, "Uma chamada monta o produto inteiro")

    runtime = ProductRuntime.bootstrap(
        product_id="painel-vendas",
        name="Painel de Vendas",
        kind="platform",
        state_dir=TEMP / "state",
    )
    print("Produto:", runtime.manifest.product_id)
    print("Autoridade concedida:", ", ".join(runtime.safety.granted()))

    # ------------------------------------------------------------------
    passo(2, "Declarar as fronteiras")

    runtime.define_contract("plano.pedido", "1.0.0", PEDIDO)
    runtime.define_contract("plano.resposta", "1.0.0", PLANO)
    print("Contratos registrados:", len(runtime.contracts))

    # ------------------------------------------------------------------
    passo(3, "Plugar um agente e uma dependência opcional")

    runtime.register(agent_connector(
        "planejador", meu_agente,
        request_contract="plano.pedido",
        response_contract="plano.resposta",
        timeout_seconds=30.0,
    ))
    runtime.register(service_connector(
        "analytics", analytics,
        critical=False,                       # o produto serve sem ele
        probe=lambda: unhealthy("analytics", "fora do ar"),
        timeout_seconds=None,
    ))
    print("Conectores:", runtime.gateway.names())

    # ------------------------------------------------------------------
    passo(4, "Chamada válida")

    resultado = runtime.invoke("planejador", {"objetivo": "aumentar conversão"})
    print("ok:", resultado.ok)
    print("valor:", resultado.value)
    print("duração: {}ms".format(resultado.duration_ms))
    print("trace_id:", resultado.trace_id)

    # ------------------------------------------------------------------
    passo(5, "Chamada inválida NÃO chega no agente")

    resultado = runtime.invoke("planejador", {"objetivoo": "erro de digitação"})
    print("ok:", resultado.ok)
    print("parou na etapa:", resultado.stage)
    print("código:", resultado.error["code"])
    print("o que fazer:", resultado.error["remediation"])

    licao(
        "Parou em 'request_contract'. O agente nunca foi executado — o erro "
        "foi pego na fronteira, não três camadas adiante."
    )

    # ------------------------------------------------------------------
    passo(6, "Ensaio (dry-run): valida tudo, não executa nada")

    resultado = runtime.invoke(
        "planejador", {"objetivo": "testar"}, dry_run=True
    )
    print("ok:", resultado.ok, "| dry_run:", resultado.dry_run,
          "| valor:", resultado.value)

    # ------------------------------------------------------------------
    passo(7, "Dependência opcional fora do ar DEGRADA, não derruba")

    prontidao = runtime.readiness()
    print("status:", prontidao["status"])
    print("consegue servir?", "SIM" if prontidao["ready"] else "NAO")
    for componente in prontidao["components"]:
        print("   {} -> {} (crítico: {})".format(
            componente["component"], componente["status"], componente["critical"]
        ))

    licao(
        "DEGRADED e ready=True. Uma integração opcional quebrada reduz "
        "função; ela não apaga o produto."
    )

    # ------------------------------------------------------------------
    passo(8, "Diagnóstico completo num payload só")

    diagnostico = runtime.diagnostics()
    print("chaves disponíveis:", ", ".join(sorted(diagnostico)))
    print()
    print("Estado dos breakers:")
    print(json.dumps(diagnostico["breakers"], indent=2)[:400])

    runtime.shutdown()

    licao(
        "Quando um painel quebrar, isto é o que você olha primeiro: "
        "manifesto, autoridade, prontidão, conectores, breakers e defeitos "
        "abertos — tudo de uma vez."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
