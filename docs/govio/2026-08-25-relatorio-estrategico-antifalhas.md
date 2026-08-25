# Relatório Estratégico Anti-Falhas — GOVIO

**Work ID:** GOVIO-LANDING-CMS-001
**Ponto de parada:** V9J3C-RUNTIME-R4 — `FAIL_CLOSED:R3_STRUCTURED_AUTHORITY_FAILED`
**Data:** 2026-08-25
**Classificação do estado:** produto parcialmente construído, não certificado para entrega; pipeline de diagnóstico em recursão.

---

## 0. Base de evidência e limites deste relatório

Este relatório é derivado de:

1. o transcript integral dos gates GOVIO (V9 → V9F → V9G → R7 → R7B1 → R7B1R → R7B2 → R7B2R1 → R3 → R4 → R4F0);
2. a saída literal do terminal Ubuntu (`douglas-reis@syra-aios`);
3. auditoria estática dos próprios scripts de gate (bash + Node/TypeScript AST + Python), lidos linha a linha.

**Limite declarado:** o código-fonte do GOVIO **não foi lido** para este relatório. O worktree auditado (`~/.syra/worktrees/govio-web-landing-20260824T045827Z`) está na sua máquina local; o repositório disponível nesta sessão (`dougsanreis/gestor`) contém apenas `.gitkeep`. Portanto:

* toda afirmação sobre **harness, scripts, terminal e processo** é verificável na evidência anexa e está marcada como `PROVADO`;
* toda afirmação sobre **`repository.ts`, banco físico e runtime** é marcada como `RELATADO` ou `PREVISTO`, nunca como provada.

Essa separação é justamente a disciplina que falhou nos últimos gates.

---

## 1. Veredito executivo

> O GOVIO não está bloqueado por falta de código, nem por falta de autorização, nem por defeito comprovado em `repository.ts`.
> Está bloqueado por **recursão de diagnóstico**: o sistema de verificação passou a consumir mais capacidade do que a entrega, e passou a gerar bloqueios falsos.

Quatro fatos sustentam o veredito:

| # | Fato | Status |
|---|---|---|
| 1 | Dos últimos 4 `FAIL_CLOSED`, **3 foram defeitos do validador**, não do produto | `PROVADO` |
| 2 | O R4 morreu antes de tocar no alvo (`publicLandingOrigin`) — a falha foi no consumo do receipt do R3 | `PROVADO` |
| 3 | O R4, mesmo com o schema corrigido, **falharia de novo** por 3 defeitos latentes independentes (§5) | `PREVISTO — alta confiança` |
| 4 | Existe uma falha de produto real e não resolvida: `APPLICATION_HTTP_STATUS=500` no Team Panel | `PROVADO` |

**Decisão de engenharia recomendada:** parar de construir gates, fechar a provenance de `origin` por leitura direta (§6.1), corrigir num único PR, e convergir para **um** Release Candidate.

---

## 2. Onde exatamente o pipeline parou

```
R3  ──►  CERTIFICADO
         SEMANTIC_GATE_SUCCESS=PASS
         result.json presente, SHA b1a0...16ab
         NÃO REPETIR
           │
           ▼
R4  ──►  FALHOU NO PORTÃO G2
         KeyError: 'state'
         FAIL_CLOSED:R3_STRUCTURED_AUTHORITY_FAILED
         nunca chegou ao G5 (AST trace)
           │
           ▼
repository.ts  ──►  NÃO CONDENADO, NÃO LIDO PELO GATE
origin provenance ──►  ABERTA
V12 / produção / migration ──►  NÃO EXECUTAR
```

O R4 falhou em `G2`. Os gates `G3` (CAS do reader), `G4` (compilador TS) e `G5` (o trace que realmente importa) **nunca executaram**. Nenhuma informação nova sobre `origin` foi produzida — o custo do ciclo foi integralmente desperdiçado.

---

## 3. Taxonomia completa de falhas

Todas as falhas observadas, classificadas pela **camada onde a causa realmente reside**. Essa é a classificação que estava faltando: o pipeline vinha tratando falha de canal e falha de validador como se fossem falha de produto.

### Camada A — Canal de entrada (terminal / paste)

| ID | Evidência | Causa-raiz | Severidade |
|---|---|---|---|
| **E-04** | `[200~printf: comando não encontrado` | Bracketed paste (`ESC[200~`) chegou literal ao shell | Média |
| **E-05** | `fiprintf 'FASTPATH=STOP_ON_EXACT...'ESULT\n'END\n'==\n\n'IED\n'` | Redraw do readline colapsando um paste de centenas de linhas numa linha visual | **Alta (risco latente)** |
| **E-06** | Prompt `>` durante heredoc, seguido de `^C` | Heredoc gigante inacabado / delimitador não alcançado | Média |
| **E-08** | `SingletonLock: Arquivo existe`, erros Mesa/GCM | `xdg-open` abrindo navegador dentro do pipeline | Baixa (ruído) |

**E-05 é o item perigoso.** No caso concreto o blast radius foi zero, porque o script era read-only. O mesmo padrão de paste, num script que contivesse `git reset --hard`, `rm -rf` ou `prisma migrate`, poderia executar **uma linha parcial** com efeito destrutivo. O risco não é ergonômico, é operacional.

### Camada B — Harness / validadores (falso bloqueio)

| ID | Evidência | Causa-raiz | Severidade |
|---|---|---|---|
| **E-01** | `KeyError: 'state'` → `R3_STRUCTURED_AUTHORITY_FAILED` | **Contract drift**: R4 exigiu campo que R3 nunca prometeu | **Crítica** |
| **E-02** | `UNRESOLVED_IMPORT=... → ../../../../lib/server/landing/factory` | Resolver de import com falso negativo; arquivo existia | **Crítica** |
| **E-03** | `rootHasLoginTarget=FAIL`, `loginSurfacePresent=FAIL` | Probe atingiu o interstitial de autenticação da Vercel, não a aplicação | Alta |
| **E-15** | Bloco `python3 - "$R3_RESULT" <<'PY' / raise_system_exit=1 / PY` | Contaminação de copy/paste dentro de um gate "certificado" | Baixa (sintomática) |

**E-02 é o precedente mais importante do projeto**: um validador defeituoso quase provocou *reparo de código-fonte correto*. A conclusão correta na época — `SOURCE_REPAIR_REQUIRED=NO` — deveria ter sido promovida imediatamente a regra permanente. Não foi, e **E-01 é a mesma falha se repetindo 3 gates depois.**

### Camada C — Método do agente

| ID | Sintoma | Custo |
|---|---|---|
| **E-07** | Interpretar `exit 1` de um `bash <<EOF` filho como "terminal destruído" | Arquitetura de recuperação inteira construída para um problema inexistente |
| **E-16** | Proliferação de gates: V9→V9F→V9F4→V9G→R7→R7B1→R7B1R→R7B2→R7B2R1→R3→R4→R4F0 | **Crítico** — capacidade gasta verificando o verificador do verificador |
| **E-26** | Scripts de 300–600 linhas entregues para copy/paste interativo | Causa direta de E-04, E-05, E-06 |
| **E-27** | Contrato declarado ≠ contrato implementado (o gate declara `SHADOWING_AWARE`, `TypeChecker authority`, mas classifica por regex — §5.5) | Confiança falsamente calibrada |

### Camada D — Produto (falhas reais, abertas)

| ID | Evidência | Status |
|---|---|---|
| **E-10** | `VERCEL_CURL_RC=0` + `APPLICATION_HTTP_STATUS=500` no Team Panel | **P0 — falha provada, causa-raiz não provada** |
| **E-11** | Perda relatada de registros, evoluções, correções, configuração visual e funcionalidades no painel | **P0 — violação de política de evolução** |
| **E-12** | Landing abaixo da referência visual (cores, imagens sem relação com o produto, sem acabamento premium) | P2 — track de design |
| **E-13** | Autoridade física da tabela `LandingContent` não certificada | Congelado (**correto**) |
| **E-14** | "Construído ≠ conectado": WorkflowEngine nunca instanciado, RBAC sem call sites, tenant extension ignorada | Dívida estrutural |
| **E-09** | `apps/web/apps/web` (double application root) | **Resolvido** — preview válido gerado |

---

## 4. Os cinco erros críticos, em ordem de dano

### CRÍTICO 1 — Contract drift entre gates (E-01)

O R4 executou o equivalente a `result["state"]` sobre um receipt cujo schema nunca foi declarado. O CAS do R3 passou (`b1a0...16ab`) e o gate ainda assim morreu.

**A regra que faltava, e que agora é permanente:**

```
UPSTREAM_RECEIPT_CAS_PASS  ≠  ASSUMED_UPSTREAM_SCHEMA_PASS
```

Hash prova **bytes**. Não prova **forma**. Um pipeline que verifica SHA-256 em cinco pontos e não versiona o schema do próprio receipt tem segurança teatral: parece rigoroso e quebra na primeira suposição não declarada.

**Correção estrutural — não use `.get()`.** `result.get("state")` esconde a incompatibilidade. Todo receipt passa a carregar:

```json
{
  "schemaVersion": 1,
  "gate": "...",
  "finalState": "...",
  "nextAction": "...",
  "invariants": {},
  "artifacts": {}
}
```

E todo consumidor valida `schemaVersion` **antes** de qualquer asserção semântica. Incompatibilidade vira erro explícito de versão, não `KeyError`.

### CRÍTICO 2 — Falha do harness tratada como falha do produto (E-01, E-02, E-03)

Três vezes o sistema apontou o produto quando o defeito era do instrumento. Em E-02 isso chegou a um passo de reparar código correto.

**Ordem de atribuição obrigatória, daqui em diante:**

```
1. o canal entregou o comando íntegro?        (paste/heredoc)
2. os bytes de entrada são os esperados?      (CAS)
3. o schema de entrada é o declarado?         (schemaVersion)
4. a resposta veio da aplicação?              (provenance HTTP)
5. o resolver/parser está correto?            (validado contra ground truth)
── só depois ──
6. o produto está defeituoso.
```

Pular do passo 1 para o 6 é o que produziu todos os bloqueios falsos.

### CRÍTICO 3 — Recursão de diagnóstico (E-16)

Cada gate individual é defensável. O agregado não é. O sistema entrou num regime onde a saída mais provável de um gate é **outro gate** — inclusive por desenho (§5.4: `ORIGIN_DATAFLOW_AMBIGUOUS` → `..._REMAINING_DEPENDENCY_AUTHORITY`).

Isso viola o próprio princípio declarado (`SYSTEM_GREATER_THAN_MODEL=YES`): o sistema global deixou de maximizar entrega.

**Circuit breaker permanente:**

```
MAX_DIAGNOSTIC_DEPTH = 2

Dois gates consecutivos falhando por defeito do harness
   ⇒ PARAR de emitir gates
   ⇒ corrigir a arquitetura do harness
   ⇒ ou resolver a pergunta por leitura direta
```

Estamos hoje em profundidade ≥ 3 (E-02 → E-01 → R4F0 proposto). O breaker **já deveria ter disparado**.

### CRÍTICO 4 — Scripts monolíticos no canal interativo (E-26 → E-04/E-05/E-06)

Um artefato de 600 linhas colado num terminal não é um script: é um vetor de corrupção de entrada. O `R4F0` proposto (≈200 linhas de heredoc) **reincide no mesmo padrão** para obter uma informação de uma linha.

**Padrão obrigatório para lógica não-trivial:**

```
cat > /tmp/gate.sh <<'SH'   # arquivo, não paste interativo
...
SH
bash -n /tmp/gate.sh        # valida sintaxe antes de executar
sha256sum /tmp/gate.sh      # registra o que foi executado
bash /tmp/gate.sh           # subprocesso; nunca `source`, nunca `.`
```

`bash script.sh` confina qualquer `exit` ao filho — o que também encerra E-07 definitivamente.

### CRÍTICO 5 — Falha de produto real represada atrás do diagnóstico (E-10, E-11)

Enquanto a cadeia investigava a proveniência de uma string, **o Team Panel está retornando 500** e sofreu regressão funcional relatada. Essas são as únicas falhas com impacto direto no usuário na lista inteira, e são as que menos receberam ciclos.

Classificação correta:

```
TEAM_PANEL_RUNTIME_FAILURE = PROVEN
ROOT_CAUSE                 = NOT_YET_PROVEN   (falta stack trace)
```

Não atribuir automaticamente ao CMS, ao banco, ao auth ou a env sem o trace do runtime da Vercel.

---

## 5. Auditoria do script R4 — as falhas que **ainda não dispararam**

Esta seção é a de maior valor operacional: mesmo corrigindo o schema do R3, o R4 **não converge**. Foram encontrados seis defeitos independentes por leitura do código do gate.

### 5.1 `LOCAL_CALLEE_DECLARATION_CARDINALITY` — falha quase certa

```js
const declarations = symbolDeclarations(calleeSymbol)
  .filter(d => d.getSourceFile().fileName === source.fileName);
if (declarations.length !== 1) throw new Error("LOCAL_CALLEE_DECLARATION_CARDINALITY:" + declarations.length);
```

O gate **exige que `publicLandingOrigin` esteja declarada dentro do próprio `repository.ts`**. Se ela for importada de outro módulo — o caso mais provável para um helper com esse nome — o resultado é `cardinality:0` e `FAIL_CLOSED`.

Pior: `symbolDeclarations()` faz o trabalho de resolver o alias de import (`getAliasedSymbol`) e o filtro seguinte **descarta exatamente esse resultado**. O gate resolve o símbolo corretamente e depois joga a resposta fora. É uma auto-contradição interna.

### 5.2 `tsconfig.json` nunca é lido — imports com alias não resolvem

```js
const compilerOptions = { target, module, moduleResolution: Bundler, strict, skipLibCheck, noEmit, allowJs:false };
const program = ts.createProgram([sourcePath], compilerOptions, host);
```

O `compilerOptions` é construído à mão. **`paths` do `apps/web/tsconfig.json` não é carregado.** Qualquer import `@/lib/...` (padrão em Next.js) fica não resolvido → símbolo inválido → `TARGET_CALLEE_SYMBOL_UNRESOLVED` ou `cardinality:0`.

O gate declara "TypeChecker como autoridade primária de binding" e priva o TypeChecker do arquivo de configuração que define o binding.

### 5.3 Fallback `??` / `||` é classificado como ambíguo — falsa ambiguidade

```js
if (classes.length === 1 && results.every(r => r.proven)) { ...MESMA CLASSE... }
return { terminalClass: "ORIGIN_DATAFLOW_AMBIGUOUS", ... };
```

Portanto:

```ts
process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"
```

→ esquerda = `ENV` (provada), direita = `STATIC_ABSOLUTE` (provada) → classes divergem → **`ORIGIN_DATAFLOW_AMBIGUOUS`**.

Este é o padrão de origin **mais comum que existe em Next.js**, e o classificador o declara indecidível. Semanticamente ele é perfeitamente decidível: *env com fallback estático*.

### 5.4 Template literal com substituição — nunca classificável

```js
if (ts.isTemplateExpression(e)) { /* traça apenas templateSpans */ }
```

O **head literal é ignorado**. Logo:

```ts
`https://${host}`
```

→ traça só `host` → se `host` é parâmetro ou import → `IDENTIFIER_TERMINAL_UNPROVEN` → **ambíguo**, apesar de o valor ser comprovadamente absoluto.

**Consequência combinada de 5.3 + 5.4:** para as duas formas mais frequentes de compor uma origin, a saída do gate é `ORIGIN_DATAFLOW_AMBIGUOUS`. E `ORIGIN_DATAFLOW_AMBIGUOUS` mapeia para `NEXT_ACTION=..._REMAINING_DEPENDENCY_AUTHORITY` — **ou seja, mais um gate. A recursão está codificada no classificador.**

### 5.5 Heurística de regex dentro de um gate que proíbe heurística

```js
function requestContextSignal(expr) {
  const raw = text(expr);
  return /\bheaders\s*\(/.test(raw) || /\bnextUrl\b/.test(raw) || ...;
}
```

Classificação terminal por **regex sobre texto-fonte**, dentro de um gate cuja regra permanente é `LEXICAL_BINDING_MUST_BE_RESOLVED_WITH_TYPESCRIPT_SYMBOL_AUTHORITY`. Um comentário ou uma string contendo `nextUrl` produz classificação positiva. O contrato declarado e o contrato implementado divergem.

### 5.6 Defeitos menores confirmados

| Item | Efeito |
|---|---|
| `findTargetCall()` exige **exatamente 1** call site e só casa `Identifier` — `mod.publicLandingOrigin()` não casa | `TARGET_CALLEE_CALL_CARDINALITY:0` |
| `env` validado por módulo (`env.NEXT_PUBLIC_SITE_URL`, t3-env) não é reconhecido como env | classificação errada / ambígua |
| `EXPECTED_PATCH` via `git diff --binary` depende de config git (`diff.noprefix`, `autocrlf`, versão) | `PATCH_MISMATCH` espúrio |
| `ts.isTypeAssertionExpression` / `ModuleResolutionKind.Bundler` dependem de TS ≥ 5 | `TypeError` em runtime se TS for antigo |
| Bloco python morto (`raise_system_exit=1`) executa um processo inútil e engole um caminho de erro | ruído + falsa cobertura |

**Conclusão da auditoria:** a probabilidade de o R4 (mesmo corrigido no schema) produzir uma classificação acionável é baixa. O valor esperado do gate é negativo: custa um round-trip humano completo e devolve, com alta probabilidade, "faça outro gate".

---

## 6. Correção mínima — como sair do bloqueio hoje

### 6.1 Passo 1 — o schema do R3, em uma linha (10 segundos)

Substitui integralmente o `R4F0` de ~200 linhas. Sem heredoc, sem paste grande, sem gate:

```bash
R3="$HOME/.syra/evidence/govio-release-convergence/20260825T191615Z-GOVIO-LANDING-CMS-001-V9J3C-RUNTIME-R3-ORIGIN-AMBIGUITY-DISAMBIGUATION/result.json"
sha256sum "$R3"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("KEYS:", sorted(d)); print(json.dumps(d, indent=2, ensure_ascii=False))' "$R3"
```

Read-only, idempotente, zero rede, zero DB, zero mutação. Entrega exatamente `R3_KEYS` + todos os `R3_FIELD`.

### 6.2 Passo 2 — fechar a provenance de `origin` por leitura (30 segundos)

Esta é a recomendação central do relatório.

```bash
WT="$HOME/.syra/worktrees/govio-web-landing-20260824T045827Z"
grep -rn "publicLandingOrigin" "$WT/apps/web" --include=*.ts --include=*.tsx
grep -rn -A25 "function publicLandingOrigin\|const publicLandingOrigin" "$WT/apps/web" --include=*.ts
```

**A pergunta que a cadeia R3/R4 persegue há vários ciclos é um problema de leitura de ~25 linhas.** Olho humano sobre a declaração fecha a provenance com o mesmo nível de autoridade que o AST trace pretendia — e sem os seis defeitos da §5. Isso não é abrir mão do rigor: é aplicar rigor onde ele muda a decisão.

### 6.3 Passo 3 — o valor de decisão real da classificação

O argumento decisivo para não gastar mais ciclos: **as quatro classificações possíveis levam a um conjunto pequeno e já enumerável de correções.**

| Classificação | O que significa | Remediação |
|---|---|---|
| `ENV` (com ou sem fallback) | Depende de variável de ambiente | Garantir a var nos **dois** projetos Vercel; se `NEXT_PUBLIC_*`, ela é fixada em **build time** — o preview precisa ser rebuildado |
| `STATIC_ABSOLUTE` | URL hardcoded | Trocar por env + fallback; risco de apontar para o host errado em prod |
| `REQUEST_CONTEXT` (`headers()`) | Deriva do request | **Força render dinâmico** — a landing perde SSG/ISR. Impacto direto em performance/SEO |
| `RELATIVE` | Path relativo | Quebra em `fetch` server-side (precisa de URL absoluta); funciona só no browser |

Todas as quatro cabem em **um PR pequeno** sobre `repository.ts` + configuração de env. A classificação refina a correção; ela não desbloqueia nada que a leitura direta não desbloqueie.

### 6.4 Passo 4 — se ainda quiser o trace automatizado, corrija o classificador

Só vale a pena se for reutilizável. Requisitos mínimos:

* carregar `tsconfig.json` via `ts.parseJsonConfigFileHost` (respeitar `paths`);
* **remover** o filtro same-file — seguir a declaração no módulo onde ela estiver;
* conjunto terminal que cubra o espaço real da linguagem:

```
ORIGIN_ENV_DIRECT
ORIGIN_ENV_WITH_STATIC_FALLBACK      ← decidível, hoje vira "ambíguo"
ORIGIN_STATIC_ABSOLUTE
ORIGIN_COMPOSED_ABSOLUTE             ← template com head absoluto
ORIGIN_REQUEST_CONTEXT
ORIGIN_RELATIVE
ORIGIN_INDIRECT_MODULE               ← segue-se para o outro módulo, não falha
ORIGIN_UNDECIDABLE                   ← só quando realmente indecidível
```

* substituir `requestContextSignal` (regex) por resolução de símbolo real (`next/headers`);
* **invariante de qualidade do gate:** se `ORIGIN_UNDECIDABLE` sair para a forma mais comum do construto inspecionado, **o defeito é do gate, não do código**.

---

## 7. O que está certificado — não repetir

| Item | Evidência | Regra |
|---|---|---|
| R3 | `SEMANTIC_GATE_SUCCESS=PASS`, `result.json` SHA `b1a0...16ab` | **NÃO REPETIR** |
| Baseline do worktree | `HEAD=cad28bfc...`, `PATCH=8bf8be7a...` | congelado |
| `repository.ts` | SHA `12bdeb97...` | intocado, **não condenado** |
| Factory do Team Panel | `FACTORY_AUTHORITY=WORKTREE`, `SOURCE_REPAIR_REQUIRED=NO` | falso negativo, encerrado |
| Binding dos projetos Vercel | `govio-core→apps/web`, `govio-equipe→apps/team-panel` | ambiguidade eliminada |
| Double application root | corrigido, preview válido | encerrado |
| UAT anterior contra interstitial | `PREVIOUS_*_FAILURE=INVALIDATED` | encerrado |
| V12 / migration / produção | — | **NÃO EXECUTAR** |

---

## 8. Plano de convergência ao Release Candidate

Um RC. Um build. Uma bateria de validação. Não quinze pipelines sobrepostos.

```
BASELINE CONGELADO
      │
      ▼
P1  origin provenance fechada (§6.2) ──► PR único
      │
      ▼
P2  Team Panel: stack trace do 500 ──► causa-raiz provada ──► fix
      │
      ▼
P3  Matriz de invariantes de regressão do painel ──► portar o que falta
      │
      ▼
P4  Editor da Landing: Draft → Validate → Preview → Publish
      │
      ▼
P5  Migration certificada (forward-only) da LandingContent
      │
      ▼
P6  Design premium da landing
      │
      ▼
P7  RC único: lint · typecheck · unit · guards · integration · build · preview · smoke · UAT
      │
      ▼
P8  Produção govio.com.br + smoke + observabilidade + release receipt
```

### P2 — critério de saída (P0)

Sem stack trace, não há causa-raiz. Ordem: logs de runtime da Vercel do deployment específico → identificar o módulo → só então formular hipótese. Proibido atribuir a CMS/DB/auth/env por inferência.

### P3 — matriz de invariantes (P0)

Política permanente:

```
EVOLUTION = EXISTING_CAPABILITIES + NEW_CAPABILITIES
EVOLUTION ≠ REPLACEMENT_WITH_SMALLER_SURFACE
```

| Invariante | Exigência |
|---|---|
| `/projeto` | MUST_EXIST |
| registros históricos | MUST_EXIST |
| evoluções | MUST_EXIST |
| correções | MUST_EXIST |
| monitoramento | MUST_EXIST |
| autenticação | MUST_WORK |
| editor da landing | MUST_EXIST |
| draft / preview / publish | MUST_WORK |
| configuração visual anterior | MUST_BE_PRESERVED |

Diff de capacidades contra a versão boa conhecida — **portar**, nunca `checkout` destrutivo.

### P5 — banco (risco máximo)

Regras já estabelecidas e mantidas:

```
PRISMA_MODEL_IS_NOT_PHYSICAL_TABLE_AUTHORITY
GENERATED_CLIENT_IS_NOT_PHYSICAL_TABLE_AUTHORITY
```

Proibido `prisma db push`. Migration versionada, forward-only, com backup e rollback de aplicação. Em produto B2G com auditoria, banco é exatamente onde não se "tenta para ver".

---

## 9. Política operacional permanente

**Proibido**

* `git reset --hard`, `git clean -fd`, `git restore`/`checkout` destrutivo em worktree com trabalho não commitado
* `prisma db push`, migration improvisada, mutação de banco antes de autoridade física provada
* produção antes de RC verde; `xdg-open` no pipeline; `source`/`.` de script de gate; retry automático
* correção baseada só em `grep` quando a semântica importa (usar parser/compiler)
* consumir receipt sem `schemaVersion`; emitir gate novo quando o anterior falhou por defeito do harness
* substituir painel existente por versão com superfície funcional menor
* repetir R3 ou executar V12 agora

**Obrigatório**

* comandos pequenos; lógica grande vai para arquivo + `bash -n` + `sha256sum` + subprocesso
* ordem de atribuição de causa (§4, CRÍTICO 2) antes de qualquer reparo de fonte
* provenance da resposta HTTP antes de qualquer asserção de UAT (`HTTP 200 ≠ application response`)
* `MAX_DIAGNOSTIC_DEPTH = 2`
* todo gate declara, no próprio receipt, o schema que produz e o schema que consome

---

## 10. Definição de pronto

| Área | Critério |
|---|---|
| govio.com.br | landing premium publicada |
| /login | login real funcionando |
| Produto | fluxos principais da prefeitura funcionando |
| Team Panel | funcionalidades anteriores preservadas + 0 regressão |
| CMS | edição + draft + preview + publish |
| Imagens | relacionadas ao produto real |
| Banco | migration certificada, forward-only |
| Auth | sem regressão |
| Histórico | registros / evoluções / correções preservados |
| Build · Tests · Guards | PASS |
| Preview · UAT · Produção · Smoke | PASS |
| Observabilidade | ativa |
| Evidência | release receipt imutável |

---

## 11. Conclusão

Existe engenharia válida e considerável no GOVIO — inclusive uma cultura de guard tests que é um dos melhores ativos do repositório. O problema recente não foi falta de rigor; foi **rigor mal alocado**: o instrumento de verificação ficou mais complexo que o objeto verificado, começou a falhar por conta própria, e passou a produzir bloqueios falsos que consumiram os ciclos que a falha real (Team Panel 500 + regressão) precisava.

A regra final que fica de todos os erros catalogados:

> **Complexidade de validação que impede continuamente a entrega é, ela própria, uma falha do sistema.**

O próximo passo correto não é V12, não é produção, não é `R4F1`. É:

1. `sha256sum` + `python3 -c` no `result.json` do R3 — uma linha;
2. `grep -A25` na declaração de `publicLandingOrigin` — uma linha;
3. um PR pequeno com a correção de origin;
4. stack trace do 500 do Team Panel;
5. RC único.

`FASTPATH = CLOSE_ORIGIN_BY_DIRECT_READ → SINGLE_PR → TEAM_PANEL_ROOT_CAUSE → ONE_RELEASE_CANDIDATE`
