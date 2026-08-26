# ADR-0001 — Stack de implementação do Vibe Funnel OS

- **Status:** aceito
- **Data:** 2026-08-25
- **Decisores:** tech lead do repositório
- **Contexto normativo:** `CLAUDE.md`, `docs/PROMPT_MESTRE_CLAUDE_CODE.md`

## Problema

O `CLAUDE.md` do pacote Vibe Funnel OS estabelece como stack de referência um
monorepo TypeScript com `pnpm`, dividido em `apps/web`, `apps/api` e
`apps/worker`, com PostgreSQL como fonte de verdade.

O repositório, porém, não estava vazio quando o pacote chegou. Já continha a
SYRA implementada em Python: motor de política determinístico, quarentena de
comandos com 21 regras, memória de erros com assinatura estável, fábrica de
software com sete portões executáveis e squad de funil com decisão por
intervalo de Wilson — 185 testes verdes.

A decisão é: implementar a Fase 0 em TypeScript conforme a stack de
referência, ou implementá-la em Python sobre o que já existe?

## Alternativas consideradas

### A. Monorepo TypeScript do zero, conforme a stack de referência

- **A favor:** aderência literal ao `CLAUDE.md`; `apps/web` com SSR é caminho
  natural para as três páginas de vendas; ecossistema maduro para OpenFeature
  e OpenTelemetry.
- **Contra:** descarta ou duplica capacidades já testadas. Cria dois motores
  de política e duas quarentenas, que divergem na primeira semana. Adia o
  primeiro slice vertical por dias de andaime.
- **Bloqueio decisivo:** o `PROMPT_MESTRE_CLAUDE_CODE.md`, §2, proíbe
  explicitamente: *"Nunca recomece um componente funcional apenas porque você
  preferiria outra arquitetura."*

### B. Python sobre a base existente, contratos do pacote intactos

- **A favor:** o primeiro slice vertical fica executável no mesmo dia.
  Reutiliza política, quarentena e memória já testadas. Os contratos — que são
  a parte normativa de verdade — entram sem alteração.
- **Contra:** diverge da stack de referência; `apps/web` com SSR fica para uma
  decisão posterior; o ecossistema de feature flags é menos maduro.

### C. Híbrido: domínio em Python, experiência em TypeScript

- **A favor:** cada camada na stack mais adequada.
- **Contra:** duas cadeias de build e dois conjuntos de contratos gerados
  desde já, com custo de coordenação antes de existir uma página sequer.
  Complexidade adiantada sem entrega correspondente.

## Decisão

**Alternativa B**, com a alternativa C mantida em aberto para o plano de
experiência quando as páginas entrarem (Fase 2).

O que sustenta a decisão não é preferência de linguagem, e sim uma
propriedade do próprio pacote: **os contratos são portáveis**. JSON Schema e
OpenAPI não pertencem a linguagem nenhuma. O princípio 9 do `CLAUDE.md` diz
que domínio, contratos e dados não dependem de um provedor — pela mesma
lógica, não dependem de um runtime.

Consequentemente:

- Os 7 JSON Schemas e o `openapi.yaml` são consumidos **verbatim**, com hash
  verificado. A implementação se ajusta ao contrato, nunca o contrário.
- O `mission.schema.json` é validado em todo caminho de mutação.
- A superfície HTTP segue os caminhos e códigos do `openapi.yaml`.
- O `reference_schema.sql` continua sendo o alvo de persistência quando a
  operação justificar um servidor.

## Consequências

### Positivas

- Slice vertical completo funcionando: criar → validar → persistir → emitir
  evento → publicar → consultar, com 326 testes verdes em menos de 5 segundos.
- Um único motor de política e uma única quarentena no repositório.
- Zero dependência externa em produção: validação de contrato, persistência,
  API e telemetria usam apenas a biblioteca padrão.

### Negativas e como são mitigadas

| Consequência | Mitigação |
|---|---|
| Divergência da stack de referência | Registrada aqui e em `docs/DIVERGENCIAS_DO_PACOTE.md` |
| `apps/web` com SSR não existe | Decisão adiada para a Fase 2, quando houver página real a servir |
| SQLite não é PostgreSQL | `MissionRepository` é uma porta; os testes de contrato rodam idênticos nos dois adapters, o que mantém o terceiro adapter a um arquivo de distância |
| Ecossistema de feature flags menos maduro | O contrato OpenFeature é uma interface; a implementação inicial é determinística, como já é o policy engine |

### Rollback

A decisão é reversível a custo conhecido. Os contratos não mudaram, então uma
implementação TypeScript futura parte exatamente dos mesmos schemas. O que
seria descartado é a camada `syra/vfos/` — cerca de 2.000 linhas — e não os
contratos, os testes de contrato ou as decisões de governança, que são
independentes de linguagem.

O gatilho para reavaliar: a Fase 2 exigir SSR com hidratação e o custo de
manter dois runtimes ficar abaixo do custo de manter um runtime inadequado
para a camada de experiência.
