# SYRA Core

Núcleo de plataforma de produto para a SYRA AIOS. Zero dependências externas,
fail-closed por padrão, evidência antes de afirmação.

Existe para resolver um problema específico: **painéis que existem mas quebram
ao integrar**. Não por falta de engenharia — por falta de um núcleo único que
governe as fronteiras.

```bash
git clone <este-repo> ~/Projects/SYRA/syra-core
cd ~/Projects/SYRA/syra-core

./syra doctor      # esta máquina está pronta?
./syra selftest    # o núcleo funciona aqui?
```

Se os dois derem `PASS`, o núcleo está plugável. Nenhum `pip install`, nenhum
virtualenv, nenhum `node_modules`. Só Python 3.8+.

---

## Por que zero dependências

Esta é a decisão arquitetural mais importante do núcleo, e ela é deliberada.

Você já tem engenharia funcionando. Um núcleo que exige instalar pacotes é um
núcleo que pode quebrar a árvore de dependências de qualquer projeto onde for
plugado. Um núcleo que só usa a stdlib **não tem como quebrar nada ao ser
adicionado**. O custo é escrever mais código; o benefício é que plugar nunca é
um risco.

---

## Os cinco problemas que ele resolve

| Sintoma que você tem | O que o núcleo faz |
|---|---|
| Painel quebra ao conectar backend | **Contract Registry** — payload inválido é recusado na fronteira, apontando o campo exato. `compatibility()` diz se uma mudança quebra consumidores **antes** de subir |
| Uma integração fora derruba o painel | **Circuit Breaker + timeout** — dependência doente vira falha local e rápida, não travamento |
| "Está no ar" mas nada funciona | **Health/Readiness honesto** — breaker aberto degrada o status mesmo com probe verde |
| Mesmo erro toda semana | **Failure Memory** — defeito ganha fingerprint que sobrevive a restart; em modo bloqueante, repetir um defeito conhecido é recusado |
| Cada produto novo é montado à mão | **Product Factory** — produto nasce com manifesto, contratos e testes passando |

---

## Comandos

```bash
./syra doctor                       # a máquina está pronta
./syra preflight [PATH...]          # SYRA-RULE-PPC-001
./syra selftest                     # suíte do núcleo (teste controlado)
./syra capabilities                 # a taxonomia de 19 capacidades

./syra authority --root ~/Projects/SYRA   # quem é autoridade de fonte
./syra scan      --root ~/Projects/SYRA   # PPC-00A: o que existe, e onde
./syra decide    --root ~/Projects/SYRA   # PPC-00B: o que fazer com cada coisa
./syra evidence <dir>                     # a evidência ainda bate com o manifest

./syra product new <slug> --kind platform --into <dir> [--dry-run]
./syra product validate <dir>
./syra product list
./syra product readiness <dir>

./syra failures list [--open-only]
./syra failures resolve <fingerprint> "o que foi corrigido"
```

Todo comando aceita `--json`. Códigos de saída: `0` PASS, `1` FAIL, `2` uso,
`30` STALE_EVIDENCE.

---

## Plugando um produto

Uma chamada monta tudo — safety, contratos, breakers, health, trace, memória de
falhas:

```python
from syra_core import ProductRuntime, agent_connector

runtime = ProductRuntime.from_manifest("product.manifest.json")

runtime.register(agent_connector(
    "planner",
    minha_funcao_de_agente,
    request_contract="painel.plan.request",
    response_contract="painel.plan.response",
    timeout_seconds=30.0,
))

result = runtime.invoke("planner", {"goal": "..."})
if result.ok:
    usar(result.value)
else:
    print(result.error["code"], result.error["remediation"])
```

Toda chamada passa por esta ordem, barato antes de caro:

```
safety → memória de falhas → contrato de entrada → breaker
       → timeout → chamada → contrato de saída → trace + registro
```

Se a autoridade não foi concedida, falha em microssegundos — não depois de 10
segundos de timeout.

---

## Os gates SYRA

O núcleo implementa `PPC-00A` (descoberta) e `PPC-00B` (decisão) como um runner
versionado, não como heredoc colado no terminal. Essa mudança é a
**SYRA-RULE-PPC-001** em código: ferramenta de auditoria não recebe mais
confiança que o sistema auditado.

**PPC-00A** responde *onde cada capacidade parece existir*, e repete a
disciplina em toda saída:

```
FOUND_DOES_NOT_MEAN_CERTIFIED=YES
```

Um match de regex prova que um arquivo menciona um conceito. Não prova que o
código é alcançável, correto, deployado ou canônico.

**PPC-00B** responde *o que fazer*:

| Modo | Quando | O que significa |
|---|---|---|
| `CONSOLIDATE` | vários repos implementam | causa raiz dos painéis que quebram na integração — resolver primeiro |
| `BUILD` | nenhuma implementação canônica | construir sobre as costuras do núcleo |
| `HARDEN` | um repo, sem teste | teste de caracterização antes de qualquer mudança |
| `ADAPT` | um repo, testado, sem contrato | escrever o contrato do que já retorna; não reescrever |
| `CORE_PROVIDED` | o núcleo já implementa | parar de manter cópia |
| `REUSE` | um repo, testado e contratado | plugar como está |
| `DO_NOT_TOUCH` | crítico, testado, funcionando | congelar até haver evidência de runtime |

`DO_NOT_TOUCH` e a confiança `LOW` em consolidação de capacidade crítica são
**anti-autossabotagem explícita**: refatorar um circuit breaker que funciona,
decidindo por saída de grep, é exatamente como um sistema saudável é quebrado
pela própria limpeza.

Todo artefato do PPC-00B carrega `implementationAuthorized: false`. O gate
propõe; nunca aplica.

---

## Evidência

Todo gate escreve num diretório selado com SHA256 por artefato:

```
~/.syra/evidence/product-platform/<TS>-<WORK_ID>-<GATE>-V1/
├── source-authorities.tsv
├── capability-candidates.tsv
├── capability-summary.tsv
├── architecture-risk-signals.tsv
├── final-decision.json
└── evidence-manifest.json     ← selado por último, cobre todos
```

Três garantias:

1. **Escrita atômica** — não existe arquivo pela metade.
2. **`seal()` recusa certificar o que não escreveu** — um gate não reporta PASS
   sobre evidência que sumiu. Foi exatamente essa a falha do R2 original.
3. **`load_manifest()` recomputa os hashes** — evidência editada depois de
   selada é detectada, não consumida.

Diretório sem manifesto = run que falhou. **Não apague** — é a evidência da
falha.

---

## Concorrência não é corrupção

Os gates capturam HEAD + status antes e depois de ler. Se algo mudou no meio:

```
PPC00A_DECISION=STALE_EVIDENCE
AUTOMATIC_RETRY_AUTHORIZED=NO
NEXT_STATE=MANUAL_CONCURRENCY_REVIEW
```

Trabalho concorrente torna o snapshot misto e as conclusões não confiáveis. É
motivo para re-rodar quando estiver quieto — **não** evidência de corrupção, e
nunca motivo para o scanner suspeitar de si mesmo. Ele nunca abriu nenhuma
árvore de fonte para escrita.

---

## As 19 capacidades

`./syra capabilities` lista todas. O núcleo implementa 12; as outras 7 dependem
do stack de cada produto — o núcleo fornece a costura, o produto preenche.

| Camada | Capacidades |
|---|---|
| `EXPERIENCE` | Product Factory, Product Shell, Design System, Product SDK |
| `INTEGRATION` | Agent Connector, Integration Gateway, Contract Registry, Event/Realtime |
| `CONTROL` | Product Manifest, Control Plane, Zero-Trust Security, Observability |
| `RESILIENCE` | Circuit Breaker, Watchdog, Health/Readiness, Recovery/Rollback, Failure Learning |
| `DELIVERY` | Functional Assurance, Deployment Engine |

---

## Documentação

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — decisões e o porquê de cada uma
- [`docs/INTEGRATION.md`](docs/INTEGRATION.md) — plugar na SYRA AIOS, passo a passo
- [`docs/GATES.md`](docs/GATES.md) — protocolo operacional dos gates

---

## Limites conhecidos

Declarados porque um limite escondido vira defeito:

- **Timeout de callable abandona, não mata.** Python não encerra threads. O
  produto para de esperar; o worker termina sozinho. HTTP tem timeout nativo
  real via `urllib`.
- **Descoberta estática não vê alcançabilidade.** O scanner não sabe se o código
  encontrado roda em produção. Por isso `FOUND_DOES_NOT_MEAN_CERTIFIED`, e por
  isso consolidação de capacidade crítica sai com confiança `LOW`.
- **O validador de schema é um subconjunto de JSON Schema.** Cobre payloads
  reais; não cobre `allOf`, `not`, ou `$ref` remoto. É pequeno o bastante para
  ser auditado numa sentada — o que é o ponto.
