# Arquitetura

Este documento registra **decisões e o porquê**. Uma decisão sem justificativa
registrada é uma decisão que alguém vai desfazer sem saber o que estava
resolvendo.

---

## Camadas

```
┌──────────────────────────────────────────────────────────┐
│  PRODUTO   painel · plataforma · squad · agente · SaaS   │
└───────────────────────────┬──────────────────────────────┘
                            │  ProductRuntime.from_manifest()
┌───────────────────────────▼──────────────────────────────┐
│  PRODUCT     manifest · factory · registry (control plane)│
├──────────────────────────────────────────────────────────┤
│  INTEGRATION gateway · connectors                         │
│              ordem: safety → memória → contrato-in →      │
│              breaker → timeout → chamada → contrato-out   │
├──────────────────────────────────────────────────────────┤
│  RESILIENCE  breaker · health · failure memory            │
├──────────────────────────────────────────────────────────┤
│  CONTRACTS   registry · validator · compatibility         │
├──────────────────────────────────────────────────────────┤
│  KERNEL      safety · evidence · preflight · telemetry    │
│              errors · util                                │
└──────────────────────────────────────────────────────────┘
```

Dependência aponta só para baixo. `kernel` não importa nada acima dele — é o que
permite testar cada camada sem montar as de cima.

---

## Decisões

### 1. Zero dependências externas

**Contexto.** A engenharia existente já funciona. Painéis quebram na integração,
não por falta de bibliotecas.

**Decisão.** Só stdlib. Um validador de schema escrito à mão em vez de
`jsonschema`; `urllib` em vez de `requests`; JSONL em vez de OpenTelemetry SDK.

**Porquê.** Um núcleo que exige instalação pode quebrar a árvore de dependências
de qualquer projeto onde é plugado. Um núcleo stdlib-only **não tem como quebrar
nada ao ser adicionado**. Isso torna "plugar" uma operação sem risco, que é
exatamente o requisito.

**Custo aceito.** Mais código para escrever e manter. O validador cobre um
subconjunto de JSON Schema, não o padrão inteiro.

---

### 2. Fail-closed, com `narrow()` e sem `widen()`

**Decisão.** `SafetyContract` é congelado. Toda capacidade começa negada. A
única transformação é `narrow()`, que só remove.

**Porquê.** Se existisse um caminho para ampliar autoridade em runtime, ele
seria usado — por pressa, por bug, ou por um `except` mal colocado. Não existir
o método é mais forte que existir e ser desencorajado.

**Consequência observável.** Um gate de análise estática **não consegue** fazer
chamada de rede, mesmo que alguém registre um `HttpConnector` nele. O
`HttpConnector` declara `network`, o gate não concede, a chamada morre no
primeiro passo do pipeline. Testado em
`test_gateway.py::test_safety_denial_precedes_everything`.

---

### 3. Capacidades finas, não grossas

`git_read` ≠ `git_mutation`. `filesystem_write` ≠ `source_mutation`.

**Porquê.** Capacidade grossa força super-concessão. Se "git" fosse uma
capacidade só, um scanner read-only precisaria de autoridade para commitar. É
assim que ferramenta de auditoria começa a mutar o que audita.

Por isso o scanner escreve evidência (`filesystem_write`, fora do workspace) sem
nunca ter `source_mutation`. O manifesto de evidência registra as duas coisas.

---

### 4. Evidência: atômica, hasheada na escrita, selada por último

**Contexto.** O R2 original passou em memória e não persistiu. O gate seguinte
não tinha o que ler; a investigação inteira teve que ser refeita.

**Decisão.**
- escrita atômica (`tmp` + `os.replace`) — não existe arquivo pela metade;
- hash no momento da escrita, não depois;
- `seal(required=[...])` **recusa** certificar um run cujos artefatos declarados
  não existem ou estão vazios;
- `load_manifest()` recomputa os hashes na leitura.

**Consequência.** Um run truncado é visivelmente não-selado, em vez de
silenciosamente incompleto. Diretório sem manifesto é evidência de falha — não
apagar.

---

### 5. SYRA-RULE-PPC-001 como código

**Contexto.** Uma aspa não fechada (`"-uall)`) num heredoc de centenas de linhas
abortou um gate de recovery **depois** de ele já ter impresso o banner de
segurança. Nada foi mutado, mas o run se perdeu.

**Decisão.** Três mudanças, não uma:
1. `preflight.python_source()` compila sem executar — pega essa classe exata de
   defeito. O teste que cobre isso usa a linha original do incidente.
2. `self_check()` compila o núcleo inteiro antes de qualquer operação.
3. Os gates viraram um runner versionado (`./syra`), não heredoc colado.

**Porquê a terceira importa mais que as duas primeiras.** Preflight pega o erro;
o runner versionado elimina a superfície onde ele nasce. Código em git não sofre
truncamento de paste, é revisável antes de ser confiado, e é idêntico toda
execução.

---

### 6. Ordem do pipeline do gateway

```
safety → memória → contrato-in → [dry-run para aqui] → breaker → timeout
       → chamada → contrato-out → trace + registro
```

**Porquê esta ordem.** Barato e local antes de caro e remoto. Uma autoridade
faltando falha em microssegundos; se `safety` viesse depois de `breaker`, o
mesmo erro custaria uma ida à dependência.

**Contrato dos dois lados.** Validar só a entrada deixa passar o caso que mais
dói: a dependência mudou o formato de resposta. O painel quebra sem nada
aparecer no log **dele**, porque o defeito é do outro lado.

**Dry-run para depois do contrato de entrada.** Um dry-run que pula a validação
não é ensaio, é no-op. Ele valida tudo que é verificável e pula só o efeito
colateral.

---

### 7. Failure Memory reabre defeito que voltou

**Decisão.** Fingerprint = código estável + site + mensagem normalizada (ids,
paths, IPs, números e strings entre aspas removidos). Defeito marcado
`RESOLVED` que reaparece volta para `OPEN`, mantendo a nota antiga como
histórico da correção que não funcionou.

**Porquê a normalização.** `connection refused to 10.0.0.5:8080` e
`connection refused to 10.0.0.9:9090` são um defeito, não dois. Sem normalizar,
a memória vira uma lista de ocorrências únicas e não aprende nada.

**Porquê reabrir.** Um defeito resolvido que voltou não estava resolvido.
Manter `RESOLVED` seria mentir para quem lê depois.

---

### 8. `DO_NOT_TOUCH` e confiança `LOW`

**Decisão.** Capacidade `CRITICAL_RUNTIME` com autoridade única e testes recebe
`DO_NOT_TOUCH`. Com múltiplas autoridades, recebe `CONSOLIDATE` com confiança
`LOW` e a instrução explícita "não refatore ainda".

**Porquê.** Análise estática não vê alcançabilidade. Ela não sabe qual das duas
implementações de circuit breaker o deploy realmente usa. Refatorar um breaker
que funciona, decidindo por saída de grep, é a jogada de maior variância
disponível — e é autossabotagem com aparência de limpeza.

O gate propõe. `implementationAuthorized` é sempre `false`.

---

### 9. Teste só não estabelece autoridade

**Decisão.** No scanner, um arquivo de teste que menciona uma capacidade conta
como `test_candidates`, mas **não** adiciona o repositório à contagem de
autoridades.

**Porquê.** Sem isso, um repo com só `tests/test_watchdog.py` apareceria como
implementando watchdog, e dois repos com testes virariam um falso conflito
multi-autoridade. Coberto em
`test_gates.py::test_tests_alone_do_not_establish_authority`.

---

### 10. Health separa crítico de opcional

**Decisão.** Dependência crítica falhando → `UNHEALTHY`. Opcional falhando →
`DEGRADED`. Breaker aberto degrada mesmo com probe verde.

**Porquê o breaker importa aqui.** Probes podem responder bem enquanto chamadas
estão sendo recusadas. Reportar `HEALTHY` nessa situação é literalmente o bug
"diz que está no ar mas nada funciona".

---

## Invariantes testadas

Cada uma tem teste nomeado. Se quebrar, a suíte fala.

| Invariante | Onde |
|---|---|
| `narrow()` não amplia autoridade | `test_safety.py::test_narrow_cannot_escalate` |
| Gate read-only não alcança a rede | `test_gateway.py::test_safety_denial_precedes_everything` |
| Contrato ruim não chega ao conector | `test_gateway.py::test_bad_request_is_caught_at_the_boundary` |
| Breaker aberto não contata a dependência | `test_breaker.py::test_open_breaker_never_reaches_the_dependency` |
| `seal()` recusa artefato ausente | `test_evidence.py::test_seal_refuses_missing_declared_artifact` |
| Evidência adulterada é detectada | `test_evidence.py::test_detects_post_seal_tampering` |
| Preflight não executa o código | `test_preflight.py::test_syntax_check_does_not_execute` |
| Worktree não é segunda autoridade | `test_gates.py::test_worktree_is_not_a_second_authority` |
| Repo unborn não é corrupção | `test_gates.py::test_unborn_repository_is_not_corrupt` |
| Concorrência é `STALE`, não corrupção | `test_gates.py::test_concurrent_change_is_stale_not_corruption` |
| Factory não sobrescreve trabalho | `test_factory.py::test_refuses_to_overwrite_existing_work` |
| Todo tipo de produto gera e boota | `test_factory.py::test_all_kinds_generate_and_verify` |

---

## O que foi deliberadamente deixado de fora

- **Async/await.** O núcleo é síncrono. Async atravessaria toda API pública e
  forçaria produtos síncronos a se adaptarem. O `ThreadPoolExecutor` do gateway
  cobre concorrência de I/O sem esse custo.
- **Plugins/hooks.** Sem carregamento dinâmico. Um núcleo que executa código
  arbitrário de configuração não consegue mais garantir o próprio safety
  contract.
- **Retry automático.** Deliberado. Retry esconde defeito e multiplica carga
  sobre dependência doente. O breaker existe justamente para não insistir.
