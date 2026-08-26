# GOVIO — Diagnóstico Técnico de Autossabotagem

**Destinatário:** agente GPT/Codex que opera o projeto GOVIO
**Data:** 2026-08-26
**Método:** análise do transcript de execução, da saída real do terminal e dos
repositórios acessíveis. Cada achado tem evidência verificável e um comando de correção.

---

## 0. Veredito em uma frase

O projeto não está travado por falta de rigor. **Está travado por excesso de rigor
aplicado no eixo errado** — cerimônia criptográfica sobre mudanças locais reversíveis,
enquanto a pergunta básica "onde fica o código do produto?" permanecia sem resposta.

| Métrica | Valor observado |
|---|---|
| Estados de controle percorridos | 4 (`AUTHORIZED` → `ATOMIC_APPLY` → `POST_APPLY_RECONCILIATION` → decisão externa) |
| Bindings criptográficos exigidos | 3 (`PREIMAGE`, `POSTIMAGE`, `AUTHORIZATION`) |
| Superfície autorizada | 1 arquivo, 2 campos |
| Linhas de produto entregues | **0** |
| Repositórios git sob `$HOME` | **57** |
| Fonte canônica declarada | **nenhuma** |

---

## 1. ACHADO CRÍTICO — a transação blindava um repositório vazio

**Severidade: P0. Este é o achado que explica todos os outros.**

Toda a máquina de `CONTROL_PLANE_REAL_SOURCE_CONFIGURATION` existia para escrever
dois campos: `$.project.repository` e `$.source.headSha`.

O valor destinado a `$.project.repository` é `dougsanreis/gestor`. Verificação direta:

```bash
git ls-tree -r origin/master --name-only    # -> .gitkeep
git rev-list --count origin/master          # -> 1
```

O repositório tem **um commit e um arquivo vazio**. Não há produto nele.

**Mecanismo da falha.** Os três SHA fecharam. O TOCTOU fechou. O rollback fechou.
A transação estava criptograficamente impecável — e semanticamente vazia. Rigor
perfeito sobre um ponteiro para lugar nenhum. Nenhum gate perguntou a única coisa
que importava: *o alvo contém o produto?*

**Correção — o marcador de produto passa a ser condição de existência da fonte:**

```bash
govio-ssot pin /caminho/real/govio-core --marker package.json
# FAIL MARKER_ABSENT se o alvo não contiver o produto — o pin não acontece
```

---

## 2. ACHADO CRÍTICO — não existe fonte canônica

**Severidade: P0.**

Evidência literal do terminal:

```
douglas-reis@syra-aios:~$ TARGET="/CAMINHO/REAL/DO/govio-core"
fatal: cannot change to '/CAMINHO/REAL/DO/govio-core': Arquivo ou diretório inexistente
fatal: cannot change to '/CAMINHO/REAL/DO/govio-core': Arquivo ou diretório inexistente
fatal: cannot change to '/CAMINHO/REAL/DO/govio-core': Arquivo ou diretório inexistente
```

Um caminho-modelo foi executado como caminho real, três vezes seguidas. Isto não é
descuido de digitação: é o sintoma de que **ninguém sabia onde ficava a fonte do produto.**

O `find` corrobora: **57 repositórios git sob `$HOME`**, incluindo pelo menos seis
candidatos plausíveis a "GOVIO":

```
~/Projects/SYRA/gestor/.git
~/.syra/runtime/govio-equipe/executor-source/.git
~/.syra/worktrees/govio-web-landing-20260824T045827Z/.git
~/.syra/worktrees/govio-mission-control-observability-20260822T004420Z/.git
~/.syra/worktrees/govio-p0-001-tenant-20260822T211157Z/.git
~/.syra/worktrees/govio-final-grounding-hotfix-20260821T144527Z/.git
```

Nenhum declarado canônico. Toda sessão recomeça adivinhando onde trabalhar.

**Correção — o caminho-modelo passa a ser rejeitado antes de virar comando:**

```bash
govio-ssot candidates --roots ~                 # ranqueia por evidência de conter o produto
govio-ssot scan --roots ~                       # expõe os 57 e agrupa por origin
govio-ssot pin ~/Projects/SYRA/gestor --marker package.json
govio-ssot verify                               # PASS/FAIL, exit code utilizável
cd "$(govio-ssot path)"                         # falha alto se o pin não valer mais
```

Teste de regressão que trava esta classe de falha para sempre:

```bash
govio-ssot pin "/CAMINHO/REAL/DO/govio-core"
# FAIL PLACEHOLDER_PATH: token de modelo não substituído: 'CAMINHO'
```

---

## 3. ACHADO CRÍTICO — cerimônia desproporcional ao risco

**Severidade: P0. Custo medido: ~180 minutos, zero entrega.**

O arquivo `.govio/project-state.json` é local, pequeno e **rastreado por git**.
Em git, o rollback de um arquivo é `git checkout -- <arquivo>` — atômico, instantâneo,
verificável. O git já É o log transacional.

Sobre esse arquivo foram exigidos:

| Gate aplicado | Necessário aqui? |
|---|---|
| `PREIMAGE_SHA256` | não — `git diff` já prova o estado anterior |
| `POSTIMAGE_SHA256` | não — o conteúdo é determinístico |
| `AUTHORIZATION_SHA256` | não — não há autoridade externa em jogo |
| sonda TOCTOU | não — arquivo local, escritor único |
| transaction arm | não — `os.replace()` já é atômico |
| rollback + verificação de rollback | não — `git checkout --` |
| immutability watchdog | não |
| `MAX_APPLY_ATTEMPTS=1` | não — em git, reaplicar é seguro |

**Mecanismo.** O custo do gate estava indexado à ansiedade do operador, não ao raio
de destruição da mudança. Como a ansiedade não tem teto, o custo não tem teto.

**Princípio corretivo:**

> Mecânica barata (`tmp` + `fsync` + `os.replace`) fica **sempre** ligada — não custa sessão.
> Prova cara (bindings SHA, contrato de autoridade, revisor humano) só a partir do TIER-2 —
> porque é ela que consome sessões inteiras sem entregar produto.

**Correção — o gate excessivo passa a ser tratado como defeito, não como zelo:**

```bash
govio-tier classify .govio/project-state.json
#   TIER=0 (LOCAL_REVERSIVEL)   ORCAMENTO_SEGUNDOS=20
#   GATES=git_tracked,diff_visivel
#   GATES_PROIBIDOS=preimage_sha,postimage_sha,toctou_probe,transaction_arm,...

govio-apply --file .govio/project-state.json --content-from novo.json --expect-postimage <sha>
#   FAIL CERIMONIA_EXCESSIVA: --expect-postimage é proibido em TIER-0.
#   O rollback aqui é 'git checkout -- .govio/project-state.json'. Viola INV-002.
```

Os quatro tiers e seus orçamentos estão em [`policy/risk-tiers.json`](../policy/risk-tiers.json):

| Tier | Nome | Raio de destruição | Orçamento |
|---|---|---|---|
| 0 | LOCAL_REVERSIVEL | arquivo local em git | 20 s |
| 1 | CODIGO_APLICACAO | comportamento do produto | 300 s |
| 2 | PLATAFORMA_E_ENTREGA | todos os tenants na próxima entrega | 1800 s |
| 3 | IRREVERSIVEL_OU_MULTITENANT | dados de prefeitura; rollback pode ser impossível | 7200 s |

---

## 4. ACHADO CRÍTICO — catraca de governança

**Severidade: P0. Esta é a razão de o problema "se repetir todas as vezes".**

Cada incidente produziu regra nova e **permanente**. Do transcript:

```
RULE=AUTHORITY_FORMATS_ARE_VERSIONED_CONTRACTS
PARSER=EXPLICIT_AND_ZERO_TRUST
GRAMMAR_INFERENCE=FORBIDDEN_FOR_TRANSACTIONAL_AUTHORITY
UNKNOWN_FORMAT=FAIL_TOOLING
AUTOMATIC_NORMALIZATION=FORBIDDEN
SOURCE_AUTHORITY_REWRITE=FORBIDDEN
MAX_APPLY_ATTEMPTS=1
```

Sete regras nascidas de **um** incidente (`MALFORMED_POSTIMAGE_AUTHORITY`).
Nenhuma com dono. Nenhuma com validade. Nenhuma com teto.

**Mecanismo — a matemática da catraca:**

1. Toda falha gera regra permanente.
2. Regras nunca saem do conjunto.
3. O custo de qualquer mudança cresce monotonicamente.
4. Em algum ponto, o custo de mover um byte excede o valor do byte.
5. **O projeto para — e cada nova sessão herda um conjunto maior que a anterior.**

O passo 5 é exatamente o "estamos rodando em círculo" relatado.

**Correção — regra vira contrato com dono e prazo, sob teto rígido:**

```bash
jq '.hardCap, (.invariants | length)' policy/invariants.json   # -> 12, 7
jq -r '.invariants[] | "\(.id) ttl=\(.ttlDays) dono=\(.owner)"' policy/invariants.json
```

Para adicionar uma regra com o conjunto cheio, **uma outra tem de sair**. É o teto
que quebra a catraca — não a boa intenção.

---

## 5. ACHADO ALTO — estado de controle avança sem produto

A cadeia `AUTHORIZED → ATOMIC_APPLY → POST_APPLY_RECONCILIATION → decisão externa`
progrediu quatro vezes sem uma linha entregue. A máquina mede a si mesma.

**Correção — sessão sem delta visível é incidente P0 registrado:**

```bash
govio-ledger open <sessao> --goal "<delta visível ao usuário final>"
govio-ledger ship "prefeitura exporta relatório fiscal em PDF" --session <sessao> --tier 1 --files src/...
govio-ledger report --enforce      # exit 1 se houver sessão ZERO DELTA
```

Reconstituindo a sessão real do transcript:

```
SESSAO                       SHIP  CERIM  MIN_CERIM
control-plane-real-source       0      4        180   <-- ZERO DELTA (P0)
razao cerimonia/entrega: INFINITA   (saudavel <= 1.0)
ENFORCE FAIL
```

---

## 6. ACHADO ALTO — trabalho duplicado sem trava

Do `find` real, o mesmo painel existe **cinco vezes**:

```
~/.syra/worktrees/ratia-r4-panel/
~/.syra/worktrees/ratia-r4-panel-ui/
~/.syra/worktrees/ratia-r4-panel-real-r1/
~/.syra/worktrees/ratia-panel-fast-v1/
~/.syra/worktrees/ratia-team-panel-v1/
```

Mais `ratia-r4-worker-r1` / `ratia-r4-worker-runtime-r1`, e
`ratia-critical-v1` / `ratia-r4-critical`. Os sufixos `-r1`, `-v1`, `-real`, `-fast`
não são versões: são **tentativas**. Nada impediu da segunda à quinta.

**Correção — colisão de slug bloqueia a criação:**

```bash
govio-dedupe audit --roots ~/.syra/worktrees          # expõe as famílias já instaladas
govio-dedupe check "ratia-r4-panel-v2-new" --roots ~/.syra/worktrees
#   5 colisão(ões) — este trabalho provavelmente JÁ EXISTE
#   VERDICT=CREATE_BLOCKED (INV-004)
```

E "já feito" passa a ser saída rápida, nunca motivo de reconstrução:

```bash
govio-apply --file X --content-from Y     # segunda execução -> VERDICT=NOOP
```

---

## 7. ACHADO MÉDIO — taxonomia de falha inacionável

A taxonomia em uso é `PASS / FAIL_PRODUCT / FAIL_TOOLING / BLOCKED_EXTERNAL`.
Quatro baldes, nenhum diz **o que fazer em seguida**. O próprio transcript admite a
ambiguidade: *"nesta etapa totalmente local, `BLOCKED_EXTERNAL` normalmente indica
que o executor tentou depender de uma autoridade externa que não deveria"*.
Um código de falha que precisa de parágrafo explicativo não é código de falha.

**Correção — todo código nomeia a saída.** Códigos emitidos pelo kit:

| Código | Ação imediata |
|---|---|
| `PLACEHOLDER_PATH` | `govio-ssot scan` e escolher caminho real |
| `MARKER_ABSENT` | alvo não é a fonte do produto; escolher outro |
| `NO_PIN` / `PIN_STALE` | `govio-ssot pin <caminho> --marker <arquivo>` |
| `CERIMONIA_EXCESSIVA` | remover o gate; usar `git checkout --` como rollback |
| `PROVA_AUSENTE` | tier ≥ 2 exige `--expect-postimage <sha256>` |
| `POSTIMAGE_DIVERGENTE` | conteúdo ≠ autorizado; nada foi escrito |
| `CREATE_BLOCKED` | retomar o trabalho existente listado |
| `ZERO_DELTA` | fechar a sessão com um SHIP real |

Também: `MAX_APPLY_ATTEMPTS=1` é dogma equivocado em TIER-0/1. Sob git, reaplicar é
seguro e idempotente. Retentativa única faz sentido a partir do TIER-2.

---

## 8. ACHADO MÉDIO — cerimônia de repositório desproporcional (evidência independente)

`dougsanreis/reposentinel`, medido nesta sessão:

```bash
wc -l reposentinel/*.py tests/*.py     # -> 72 linhas no total
```

72 linhas de código, envoltas em ~15 arquivos de governança: README com badges,
ROADMAP `v0.1 → v1.0`, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, dois
templates de issue, template de PR, CI, e três documentos em `docs/`.
A CI executa `py_compile` e um teste de 14 linhas.

**Por que isto importa:** é um segundo projeto, independente, com **a mesma
patologia**. Confirma que não é acidente de uma sessão — é hábito sistêmico.
A cerimônia de repositório é adotada como identidade ("nível big tech"), não como
resposta a um risco real.

**Correção — proporção como regra:** `SECURITY.md`, `CONTRIBUTING.md` e templates
entram quando houver 2+ contribuidores ou superfície pública real. Antes disso,
custam manutenção e não compram nada.

---

## 9. Ranking de causa raiz

| # | Causa | Severidade | Custo observado | Corrigido por |
|---|---|---|---|---|
| 1 | Fonte canônica inexistente | P0 | toda sessão recomeça do zero | `govio-ssot` |
| 2 | Control plane apontando para repo vazio | P0 | transação impecável, valor nulo | `govio-ssot --marker` |
| 3 | Cerimônia indexada à ansiedade | P0 | ~180 min / 0 entrega | `govio-tier` + `govio-apply` |
| 4 | Catraca de governança | P0 | agrava a cada sessão | `policy/invariants.json` |
| 5 | Estado avança sem produto | Alta | 4 estados / 0 linha | `govio-ledger --enforce` |
| 6 | Duplicação sem trava | Alta | 5× painel, 2× worker, 2× critical | `govio-dedupe` |
| 7 | Taxonomia inacionável | Média | falhas sem próximo passo | códigos acionáveis |
| 8 | Cerimônia de repo desproporcional | Média | manutenção sem retorno | regra de proporção |

---

## 10. O que NÃO deve mudar

Para não jogar fora o que está certo — vários instintos do agente GPT são bons e
devem ser **preservados**, apenas realocados para o tier onde pagam:

- **Escrita atômica** (`tmp` no mesmo filesystem + `fsync` + `os.replace`): correta.
  Mantida em **todos** os tiers no `govio-apply`, porque não custa sessão.
- **Fail-closed em divergência**: correto. Mantido em TIER ≥ 2.
- **Formatos de autoridade versionados** (`formatVersion`, `artifactType`): correto e
  adotado em `policy/*.json` e no pin do SSOT.
- **Recusar normalização automática de autoridade**: correto para TIER ≥ 2.
- **Fronteira entre mutação local determinística e observação externa
  não determinística**: conceitualmente correta e preservada.

O erro nunca foi o rigor. Foi aplicá-lo onde o git já resolvia, e não aplicá-lo
onde a pergunta real estava aberta.

---

## 11. Verificação

Todo o kit tem suíte de regressão sem rede e sem dependências:

```bash
bash tests/test_kit.sh      # 40 asserções, PASS=40 FAIL=0
```

A suíte trava, entre outras, estas regressões:
`/CAMINHO/REAL/DO/...` rejeitado; `.govio/*.json` classificado T0; migração
destrutiva classificada T3; caminho absoluto **não** rebaixa o tier; gate excessivo
em T0 reprova; prova divergente não escreve nada; reaplicação vira `NOOP`;
sessão zero-delta reprova no `--enforce`.
