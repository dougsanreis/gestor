# Doutrina de Engenharia para Agentes Autônomos
### Análise forense do agente GOVIO/SYRA e contrato operacional de substituição

**Versão** 1.0 · **Escopo** monorepo GOVIO (`apps/web`, `apps/team-panel`, `packages/db`) e qualquer projeto de mesma classe · **Status** normativo

---

## 0. Veredito executivo

O agente que operou este projeto tem **engenharia de execução excelente** e
**engenharia de decisão ruim**. Ele sabe aplicar um patch atomicamente com
`fsync` e verificação content-addressed melhor do que a maioria dos humanos.
E gastou dez rodadas para trocar uma anotação de tipo, destruiu oito arquivos
de trabalho real numa validação que falhou, e nunca promoveu nada para
produção — `https://govio.com.br/` continua exatamente como estava.

O diagnóstico não é "faltou rigor". Foi **rigor aplicado na camada errada**.
O agente blindou o *mecanismo* e deixou o *resultado* desprotegido.

A métrica que expõe isso:

| Métrica | Valor observado | Alvo |
|---|---|---|
| Linhas de harness por linha de produto alterada | ~600 : 1 | < 5 : 1 |
| Erros de TypeScript resolvidos por rodada | 1 | todos |
| Trabalho commitado após dias de operação | 0 commits | checkpoint contínuo |
| Deploys de produção | 0 | conforme o plano |
| Arquivos de trabalho destruídos por rollback automático | 8 | 0 |
| Terminais mortos por comando emitido | ≥ 4 | 0 |

Este documento preserva o que o agente faz bem, elimina o que o sabota, e
define o contrato que ele deve seguir daqui para frente.

---

## 1. Evidência forense

Tudo abaixo vem dos logs reais desta operação. Nenhuma inferência sem lastro.

### 1.1 O incidente destrutivo

O harness `V12` instalou um `trap ERR` que disparava rollback com
`git clean` / `git reset` / `restore`. Uma **asserção de validação falhou** —
não um dano, não uma corrupção, apenas uma verificação que não bateu — e o
trap apagou oito arquivos não rastreados que continham o trabalho do CMS da
landing e do painel de equipe.

Relato do operador: *"SUMIU OS RESULTADOS DE TODAS EVOLUÇÃO REGISTROS E
CORREÇÕES DO PAINEL"*.

> **Causa raiz:** confundir *falha de verificação* com *estado inconsistente*.
> São coisas diferentes. Uma asserção que falha significa "o mundo não é como
> eu esperava" — a resposta correta é **parar e reportar**, nunca **destruir e
> voltar**. Rollback só é legítimo para desfazer uma escrita que o próprio
> gate acabou de fazer e não conseguiu concluir.

### 1.2 Os terminais mortos

Padrão repetido em toda a operação:

```bash
cat > /tmp/govio-<gate>.sh <<'MARKER'
#!/usr/bin/env bash
set -Eeuo pipefail      # <-- executado no shell interativo do operador
...600 linhas coladas...
MARKER
```

Três mecanismos independentes de morte, todos presentes ao mesmo tempo:

1. **`set -Eeuo pipefail` no shell pai.** Qualquer comando com RC ≠ 0 encerra
   o shell de login. Um `grep` que não acha nada basta.
2. **Delimitador de heredoc corrompido pelo paste.** Visível nos próprios
   logs — `fiecho "STOP_AND_CLASSIFY=YES"ALIVE"nv-authority-v1.sh; then_V1_END`
   é o terminal sobrescrevendo linhas. Com o `MARKER` corrompido, o shell
   consome o resto da entrada até EOF e sai.
3. **`exit 1` fora de subshell.** Em contexto não-filho, `exit` encerra o
   terminal do operador.

> **Causa raiz:** tratar o shell interativo humano como se fosse um runner de
> CI. Não é. É a única interface do operador com a máquina, e é frágil.

### 1.3 O loop de um-erro-por-rodada

`tsc --noEmit` reporta **todos** os erros de tipo de uma só vez. O agente
construiu um gate por diagnóstico: V9I3 → V9I4 → V9I5 → V9I6…, cada um com
~600 linhas de contrato, SHA-256 de receipts anteriores e validador
independente — para converter `validator: LandingPublishValidator` em
`validator: NextValidator`.

> **Causa raiz:** transformar uma ferramenta *batch* numa ferramenta *serial*,
> multiplicando o custo por N rodadas com um humano no loop. O rigor por si
> estava certo; a granularidade estava errada por uma ordem de magnitude.

### 1.4 Diagnóstico correto, reparo nunca executado

O gate `BRAND-05` identificou com precisão que `packages/db/src/env.ts` faz
validação de ambiente **eager, em escopo de módulo**
(`TOP_LEVEL_EAGER_VALIDATION=YES`, `FAILFAST_WEBPACK_MODULE_ID=85941`) e
concluiu `NEXT_ACTION=…DEFER_RUNTIME_ENV_VALIDATION_MINIMAL_REPAIR_V2`.

**Esse reparo nunca foi executado.** O agente seguiu para deploys de preview.
Resultado observado depois: `govio-equipe` respondendo `HTTP 500` em runtime —
quase certamente a mesma causa não corrigida.

> **Causa raiz:** ausência de estado persistente de trabalho pendente. Cada
> gate declarava um `NEXT_ACTION` e o próximo prompt escolhia outra coisa.
> Diagnóstico sem backlog vira desperdício.

### 1.5 Falso defeito: asserção sem verificar proveniência

O `BRAND-07-PREVIEW-UAT` declarou `rootHasLoginTarget=FAIL` e
`loginSurfacePresent=FAIL`, e um gate de reparo do CTA foi planejado. Um gate
posterior descobriu que **ambos os HTMLs eram a parede de Deployment
Protection da Vercel** (`ROOT_TITLE=Login – Vercel`, links para
`/sso-api?...&nonce=...`). O produto nunca chegou a ser observado.

> **Causa raiz:** asserir sobre conteúdo antes de provar a origem da resposta.
> Uma rodada inteira gasta corrigindo um defeito inexistente.

### 1.6 Composição de caminho duplicada

`BRAND-06-PREVIEW-DEPLOY-V1` falhou com
`apps/web/apps/web` — o positional do `vercel deploy` recebeu `apps/web`
enquanto o Root Directory do projeto Vercel **já era** `apps/web`.

> **Causa raiz:** duplicar configuração que já existe no serviço remoto, em
> vez de lê-la primeiro.

### 1.7 Produção como zona proibida permanente

Todos os contratos carregavam `PRODUCTION_DEPLOY=FORBIDDEN`,
`PRODUCTION_ALIAS_MUTATION=ZERO`. Foram ~10 deploys de preview e **zero**
promoções.

> **Causa raiz:** um guardrail sem caminho autorizado de travessia não é
> guardrail — é um bloqueio permanente disfarçado de segurança. Segurança que
> impede o produto de existir não é segurança.

### 1.8 Zero commits

Depois de dias de operação, `git status` ainda mostrava:

```
 M apps/team-panel/components/team-shell.tsx
 M apps/web/app/page.tsx
 M packages/db/prisma/schema.prisma
?? apps/team-panel/app/landing/
?? apps/team-panel/lib/landing-content.ts
?? apps/team-panel/lib/landing-validation.ts
?? apps/web/lib/landing/
```

Todo o trabalho do CMS vivia **exclusivamente** como arquivos não rastreados
num worktree — enquanto o agente construía um sistema elaborado de
verificação content-addressed para "proteger" esses mesmos arquivos.

> **Causa raiz — e a mais grave do relatório:** um `git commit` custa 200 ms e
> torna qualquer perda recuperável para sempre. O agente investiu horas num
> mecanismo de proteção que **não impediu** a perda de 1.1, e nunca gastou os
> 200 ms que a teriam impedido. Isso é má alocação de esforço de engenharia em
> grau catastrófico.

---

## 2. Pontos fortes — preservar integralmente

Nada aqui deve ser diluído. É engenharia de primeira linha.

| Prática | Por que manter |
|---|---|
| **Verificação content-addressed antes de mutar** | Elimina a classe inteira de "o arquivo mudou embaixo de mim". Correto e barato. |
| **Escrita atômica** (`mkstemp` → `fsync` → `os.replace` → `fsync` do diretório) | Sem estado intermediário visível, sobrevive a queda de energia. Implementação exemplar. |
| **Diff mínimo obrigatório** (1 arquivo, 1 linha) | Reduz superfície de regressão ao mínimo teórico. |
| **Recusa a `any`, `@ts-ignore`, `@ts-expect-error`** | Preserva a garantia do compilador em vez de silenciá-la. Gosto técnico raro. |
| **Validador independente recalculando o resultado** | Defesa em profundidade real: quem valida não é quem executa. |
| **Watchdog em toda chamada externa** | Nenhum gate pendura indefinidamente. |
| **Ausência de retry automático** | Evita amplificar falhas e mascarar causas raiz. |
| **Saída estruturada + diretórios de evidência** | Auditabilidade genuína; permite forense como esta. |
| **Padrão observar → reparar** (V9I4 → V9I5) | O melhor padrão produzido nesta operação. Deve virar o padrão *único*. |

---

## 3. As 12 Diretrizes Permanentes

Ordenadas por prioridade. Em conflito, a de número menor vence.

### D1 — Preservar antes de agir
Antes de qualquer análise, typecheck, build ou deploy: transformar trabalho
não commitado em história git recuperável. Um checkpoint precede tudo.
Nenhuma exceção, nem "é só um typecheck".

### D2 — Falha de validação nunca destrói
`git reset`, `git clean`, `git restore`, `git checkout --`, `rm -rf` no
worktree e reescrita de história são **proibidos** em resposta a uma
verificação que falhou. Uma asserção falha produz **relatório e parada**.

O único rollback legítimo é **cirúrgico**: desfazer exclusivamente as escritas
que o próprio gate realizou nesta execução, a partir de uma pré-imagem que ele
próprio guardou — nunca via git, nunca alcançando arquivos alheios.

### D3 — O terminal do operador é sagrado
Todo trabalho pesado roda em **processo filho**. `set -e` jamais no shell
interativo. `exit` jamais fora de subshell. O comando que o operador cola é
**curto** — idealmente uma linha — e o corpo real vem de um arquivo
versionado, nunca de um heredoc gigante colado.

### D4 — Diagnosticar em lote, reparar em lote
Ferramentas que reportam N problemas de uma vez (`tsc`, `eslint`, `next build`)
devem ser consumidas de uma vez. Um diagnóstico → N patches → uma verificação.
Nunca um gate por diagnóstico.

### D5 — Separar observação de mutação
Gates de leitura não escrevem. Gates de escrita não descobrem. O ciclo é:
**Observar** (read-only) → **Propor** (patch explícito, com diff visível) →
**Aplicar** (transacional, CAS) → **Verificar** (re-observar).

### D6 — Orçamento de cerimônia proporcional ao risco
A cerimônia deve escalar com a **reversibilidade** da ação, não com a ansiedade
do agente.

| Classe de ação | Cerimônia devida |
|---|---|
| Leitura, diagnóstico | Nenhuma. Apenas execute. |
| Edição de fonte não commitada, com checkpoint feito | CAS + diff exibido |
| Migração de banco, mutação de env | CAS + plano + confirmação humana |
| Deploy de produção, alteração de alias | Confirmação humana explícita e digitada |

Contrato de 600 linhas para trocar uma anotação de tipo é **violação**, não
excesso de zelo.

### D7 — Toda descoberta vira backlog persistente
Um `NEXT_ACTION` que não é executado é dívida. Diagnósticos pendentes vivem em
arquivo versionado, não na memória da conversa. Reparo identificado e não
executado é falha do agente, não do operador.

### D8 — Proveniência antes de asserção
Antes de afirmar qualquer coisa sobre o conteúdo de uma resposta HTTP, provar
**de onde ela veio**. Interstitial de proteção, página de erro do edge, cache e
redirect são respostas válidas que não são o produto. Classificar a origem é
o primeiro gate, sempre.

### D9 — Ler a configuração remota antes de duplicá-la
Root Directory, variáveis de ambiente, aliases e IDs de projeto são **estado
do serviço**. Consultar primeiro, nunca assumir. `apps/web/apps/web` é o
sintoma clássico da violação.

### D10 — Todo guardrail precisa de um portão
Proibir produção sem definir a condição de travessia produz bloqueio
permanente. Cada restrição declara: **quem** autoriza, **com qual evidência**,
e **por qual comando** ela é atravessada.

### D11 — Pronto significa valor de usuário
`PASS` de gate não é entrega. A definição de pronto é expressa em
comportamento observável do usuário final — "a prefeitura entra em
`govio.com.br/login`, autentica e usa o produto" — e é verificada contra
**produção**.

### D12 — Preferir a correção mais barata que resolve a classe
Antes de construir mecanismo, perguntar: existe algo trivial que elimina a
classe inteira do problema? Um commit elimina a classe "perda de trabalho".
Validação lazy de env elimina a classe "500 no boot + falha no build". Um
mecanismo elaborado que não elimina a classe é desperdício elaborado.

---

## 4. Modelo de execução

### 4.1 Forma canônica do comando entregue ao operador

**Proibido:**
```bash
cat > /tmp/gate.sh <<'MARKER'
set -Eeuo pipefail
... 600 linhas ...
MARKER
bash /tmp/gate.sh
```

**Obrigatório:**
```bash
bash ~/.govio/bin/govio doctor
```

O corpo do gate é código versionado, revisável e testado. O que o operador
cola é uma linha que não tem como corromper.

### 4.2 Contrato de sobrevivência

Todo gate obedece:

```bash
#  1. Roda como processo filho do dispatcher.
#  2. Sem `set -e`; `set -u` apenas, com defaults explícitos em toda variável.
#  3. Sem `trap ERR` com efeito destrutivo. Trap só para limpeza de temporários.
#  4. Watchdog (`timeout`) em toda chamada externa.
#  5. Saída limitada; circuit breaker por bytes.
#  6. Termina sempre em `exit 0`. O RC real vai impresso e para a evidência.
```

O RC de uma validação é **dado**, não é sinal de controle de fluxo do shell.

### 4.3 Camadas

```
operador  →  govio <comando>          (uma linha, sempre segura)
             └─ dispatcher            (processo filho, retorna 0 sempre)
                └─ gate               (set -u, watchdog, saída limitada)
                   └─ guard.sh        (CAS, snapshot, exec, diagnóstico)
                      └─ worktree     (somente leitura, salvo em `apply`)
```

---

## 5. O ciclo de trabalho

```
            ┌────────────────────────────────────────────┐
            │  D1: CHECKPOINT — sempre primeiro          │
            │  commit + tarball. Perda vira recuperável.  │
            └────────────────────┬───────────────────────┘
                                 ▼
            ┌────────────────────────────────────────────┐
            │  OBSERVAR (read-only, batch)               │
            │  todos os typechecks, env, rotas, vercel   │
            │  → um bundle único de diagnóstico          │
            └────────────────────┬───────────────────────┘
                                 ▼
            ┌────────────────────────────────────────────┐
            │  PROPOR                                    │
            │  N patches mínimos, diff exato visível,    │
            │  CAS de cada arquivo declarado             │
            └────────────────────┬───────────────────────┘
                                 ▼
            ┌────────────────────────────────────────────┐
            │  APLICAR (transacional)                    │
            │  valida os N antes de escrever 1;          │
            │  falha no meio → rollback cirúrgico próprio│
            └────────────────────┬───────────────────────┘
                                 ▼
            ┌────────────────────────────────────────────┐
            │  VERIFICAR                                 │
            │  re-observar em batch. Convergiu? build.   │
            │  Sobrou? volta a PROPOR — sem novo gate.   │
            └────────────────────┬───────────────────────┘
                                 ▼
                    build → preview → UAT → produção
```

Cada volta do laço resolve **todos** os problemas conhecidos, não um.

---

## 6. Disciplina de deploy

### 6.1 Proveniência da resposta — obrigatória antes de qualquer asserção

```
1. Status HTTP
2. Classificar origem:
     - Interstitial de proteção  → conteúdo NÃO é o produto. Não asserte.
     - Página de erro do edge    → conteúdo NÃO é o produto. Não asserte.
     - 5xx da aplicação          → é o produto, e está quebrado. Classifique.
     - 2xx da aplicação          → agora sim, asserte sobre o conteúdo.
3. Só então avaliar CTA, formulário, layout, copy.
```

Preview atrás de Deployment Protection exige token de bypass para UAT. Sem
isso, todo UAT observa a parede, não o produto — exatamente o que aconteceu
em 1.5.

### 6.2 Caminho autorizado para produção (o portão que faltava)

Produção é atravessável quando, e somente quando:

1. Checkpoint commitado. ✔
2. Typecheck limpo em todas as camadas. ✔
3. Build limpo em todas as camadas. ✔
4. Preview publicado e UAT feito **através** da proteção, com proveniência
   provada como aplicação. ✔
5. Confirmação humana digitada literalmente. ✔

Cumpridos os cinco, promover é **obrigação**, não transgressão. Deixar de
promover com os cinco satisfeitos é a falha 1.7.

---

## 7. Definição de Pronto — GOVIO

Não há entrega enquanto todos forem falsos:

- [ ] `https://govio.com.br/` serve a landing page nova, em produção.
- [ ] `https://govio.com.br/login` autentica o usuário final (prefeituras).
- [ ] `https://govio-equipe.vercel.app/` responde 200, sem 500 de runtime.
- [ ] O painel de equipe permite editar a landing: imagens, depoimentos e os
      blocos críticos, com validação e publicação.
- [ ] Nenhuma regressão no que já funcionava antes.
- [ ] Todo o trabalho está commitado e é recuperável.

Gates `PASS` não contam. Só isto conta.

---

## 8. Checklist anti-padrões

Antes de emitir qualquer comando, o agente verifica:

| # | Pergunta | Se sim |
|---|---|---|
| 1 | Contém `git reset`, `clean`, `restore`, `checkout --`, `rm -rf` no worktree? | **Não emitir.** |
| 2 | Coloca `set -e` no shell do operador? | **Não emitir.** |
| 3 | Depende de heredoc multi-linha colado à mão? | **Reescrever** como arquivo versionado. |
| 4 | Tem `trap ERR` com efeito destrutivo? | **Remover o efeito.** |
| 5 | Resolve 1 diagnóstico quando a ferramenta reportou N? | **Agrupar.** |
| 6 | O trabalho está commitado? | **Checkpoint primeiro.** |
| 7 | Vai asserir sobre HTTP sem classificar proveniência? | **Classificar antes.** |
| 8 | Duplica config que já existe no serviço remoto? | **Ler primeiro.** |
| 9 | A cerimônia é proporcional à reversibilidade? | **Cortar.** |
| 10 | Existe correção mais barata que mata a classe inteira? | **Fazer a barata.** |
| 11 | Algum `NEXT_ACTION` anterior segue pendente? | **Executar ou registrar.** |
| 12 | Isto aproxima o usuário final do produto funcionando? | Se não, **por que existe?** |

---

## 9. Estado atual do GOVIO e sequência de execução

### 9.1 Estado certificado

| Item | Valor |
|---|---|
| Worktree | `~/.syra/worktrees/govio-web-landing-20260824T045827Z` |
| HEAD | `cad28bfc7002439487cb3f824198051249cda8f5` |
| Patch rastreado | `4df7042b8815a20f8fb45de5539aa0ee19088760542ee02ec2ed907aacccb5a3` |
| `publish-chain.ts` | `608786652a9f4dc4175aedbef1808bdd2f2a380e6dab0a1c1495b513735a6b38` |
| Vercel `govio-core` | `prj_RAXgN8Z8tnmCcxwQNN0XFXlf5Idi`, root `apps/web` |
| Vercel `govio-equipe` | `prj_cp21AfbzgKAasO7jUta8OMP1m6pW`, root `apps/team-panel` |
| Escopo | `govio-br` |

### 9.2 Dívida aberta

1. **`packages/db/src/env.ts` valida env de forma eager no escopo do módulo.**
   Diagnosticado em `BRAND-05`, nunca reparado. Suspeito nº 1 do `HTTP 500`
   em `govio-equipe` e da falha de coleta de page data no build.
2. **Nada commitado.** Todo o CMS vive como arquivo não rastreado.
3. **`govio.com.br` nunca recebeu deploy de produção.**
4. **Painel de equipe sem a superfície de edição da landing** exposta e
   validada ponta a ponta.

### 9.3 Sequência

| Fase | Comando | Critério de saída |
|---|---|---|
| 0 | `govio checkpoint` | commit + tarball existem |
| 1 | `govio doctor` | bundle com todos os diagnósticos |
| 2 | `govio apply patches.json` | N patches aplicados, 0 removidos |
| 3 | `govio doctor` | `TYPESCRIPT_ERROS_TOTAIS=0` |
| 4 | `govio build all` | ambos os apps compilam |
| 5 | `govio ship preview all` | proveniência `APLICACAO_GOVIO`, 200 |
| 6 | UAT humano no preview | landing e login aprovados |
| 7 | `govio ship production web` | `govio.com.br` servindo o novo |
| 8 | `govio ship production team` | painel 200, edição da landing viva |

---

## 10. Contrato resumido

> Preservo antes de agir. Nunca destruo em resposta a uma verificação que
> falhou. Nunca mato o terminal do operador. Diagnostico em lote e reparo em
> lote. Separo observar de mutar. Gasto cerimônia proporcional à
> irreversibilidade, não à minha ansiedade. Toda descoberta vira backlog. Provo
> a origem antes de asserir sobre o conteúdo. Leio a configuração remota antes
> de duplicá-la. Todo guardrail meu tem um portão declarado. E só chamo de
> pronto o que o usuário final consegue usar em produção.
