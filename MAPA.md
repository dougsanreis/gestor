# Mapa do pacote

O que é cada arquivo, em uma linha. Para quando você precisar mexer em algo e
não souber onde.

---

## Raiz

| Arquivo | O que é |
|---|---|
| `COMECE-AQUI.md` | três passos para começar — leia primeiro |
| `VERIFICAR.sh` | um comando que prova que tudo funciona |
| `syra` | o CLI. Roda de qualquer lugar, sem instalar nada |
| `README.md` | visão geral, comandos, limites conhecidos |
| `ARCHITECTURE.md` | as decisões e o porquê de cada uma |
| `MAPA.md` | este arquivo |
| `syra-core.bundle` | histórico git completo, para clonar |

---

## `syra_core/` — o núcleo (20 módulos)

### Kernel — a base, não depende de nada acima

| Módulo | Responsabilidade |
|---|---|
| `safety.py` | autoridade fail-closed. Só existe `narrow()`, não existe `widen()` |
| `evidence.py` | escrita atômica, hash na escrita, `seal()` que recusa certificar o que não escreveu |
| `preflight.py` | SYRA-RULE-PPC-001. Valida ferramenta antes de executar |
| `telemetry.py` | spans JSONL com trace id. Sink quebrado vira silêncio, nunca queda |
| `errors.py` | taxonomia de erros com códigos estáveis e `remediation` |
| `util.py` | hash, JSON canônico, escrita atômica, caminhos |
| `version.py` | versão e identidade do núcleo |

### Contratos — a camada anti-quebra

| Módulo | Responsabilidade |
|---|---|
| `contracts.py` | validador de schema, registro versionado, detecção de mudança que quebra |

### Resiliência

| Módulo | Responsabilidade |
|---|---|
| `breaker.py` | circuit breaker com relógio injetável (testável sem `sleep`) |
| `health.py` | health/readiness separando dependência crítica de opcional |
| `failure_memory.py` | fingerprint normalizado, sobrevive a restart, reabre em regressão |

### Integração

| Módulo | Responsabilidade |
|---|---|
| `connector.py` | agente, squad, serviço e HTTP. Todos declaram contrato e autoridade |
| `gateway.py` | o pipeline único: safety → memória → contrato → breaker → timeout → chamada |

### Produto

| Módulo | Responsabilidade |
|---|---|
| `runtime.py` | `ProductRuntime.from_manifest()` — a API de plug |
| `manifest.py` | declaração governável de um produto |
| `registry.py` | control plane: quais produtos existem, com detecção de drift |
| `factory.py` | gera produto novo e verifica o próprio resultado |
| `blueprints.py` | os templates que o factory materializa |
| `capabilities.py` | a taxonomia das 19 capacidades — fonte única do scanner e do decisor |

### Gates

| Módulo | Responsabilidade |
|---|---|
| `git_authority.py` | quem é autoridade de fonte: primário, worktree, unborn, histórico |
| `scanner.py` | PPC-00A — descoberta de capacidades, com validador de concorrência |
| `decision.py` | PPC-00B — tabela REUSE/HARDEN/ADAPT/CONSOLIDATE/BUILD/DO_NOT_TOUCH |
| `cli.py` | os comandos do `./syra` |

---

## `exemplos/` — código que roda

| Arquivo | Mostra |
|---|---|
| `01_contrato_protege_painel.py` | payload errado recusado na fronteira; mudança que quebra detectada antes de subir |
| `02_breaker_contem_falha.py` | dependência doente contida; recuperação automática sem retry cego |
| `03_memoria_de_falhas.py` | três mensagens diferentes = um defeito; bloqueio de repetição; reabertura |
| `04_produto_completo.py` | produto inteiro com agente, dependência opcional, readiness e diagnóstico |
| `05_safety_bloqueia.py` | gate read-only não consegue fazer chamada de rede, mesmo com conector HTTP registrado |
| `_comum.py` | prepara `sys.path` e aponta o estado para um diretório temporário |

---

## `tests/` — 201 testes

Sem rede, sem `sleep`, sem escrita fora de diretório temporário.

| Arquivo | Cobre |
|---|---|
| `test_safety.py` | fail-closed, `narrow()` não amplia, contrato imutável |
| `test_contracts.py` | validação, ponteiros JSON, compatibilidade, registro |
| `test_breaker.py` | máquina de estados completa com relógio falso |
| `test_evidence.py` | atomicidade, selagem, detecção de adulteração |
| `test_failure_memory.py` | normalização, dedupe, bloqueio, regressão |
| `test_gateway.py` | o pipeline inteiro, ordem das etapas, degradação |
| `test_preflight.py` | inclui a linha exata do incidente da aspa não fechada |
| `test_runtime.py` | boot, manifesto, control plane, drift |
| `test_gates.py` | repositórios git reais: worktree, unborn, concorrência, decisões |
| `test_factory.py` | todo tipo de produto gera e boota |
| `test_cli.py` | comandos, códigos de saída, saída JSON |
| `support.py` | relógio falso e caso de teste com diretório temporário |

---

## `docs/`

| Arquivo | Para |
|---|---|
| `INTEGRATION.md` | plugar na SYRA AIOS, passo a passo, com erros comuns |
| `GATES.md` | protocolo dos gates e as três regras permanentes |

---

## Onde mexer para cada tarefa

| Quero | Mexo em |
|---|---|
| Adicionar um tipo de produto novo | `blueprints.py` → `KIND_PROFILES` |
| Adicionar uma capacidade à taxonomia | `capabilities.py` → `CAPABILITIES` |
| Mudar a regra de decisão do PPC-00B | `decision.py` → `decide_one()` |
| Adicionar um comando ao CLI | `cli.py` → `build_parser()` + a função `cmd_*` |
| Suportar mais um keyword de schema | `contracts.py` → `validate()` |
| Mudar o que o scanner ignora | `scanner.py` → `EXCLUDED_DIRS` |
| Adicionar um tipo de conector | `connector.py` |
