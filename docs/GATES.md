# Protocolo dos gates

Os gates existem para separar **descobrir** de **decidir** de **aplicar**. Um
gate que faz as três coisas é um gate que aplica mudança baseada em suposição.

```
PPC-00A  descoberta   o que existe, e onde              read-only
   ↓
PPC-00B  decisão      o que fazer com cada coisa         advisory
   ↓
PPC-00C  sequência    em que ordem, com que evidência    (fora do núcleo)
```

Cada um só é autorizado pelo estado final do anterior. Sem `PPC00B_AUTHORIZED`,
não se avança.

---

## Contrato de segurança

Todo gate imprime a autoridade que recebeu, antes de fazer qualquer coisa:

```
===== SAFETY CONTRACT =====
NETWORK=ZERO
RUNTIME_EXECUTION=ZERO
DATABASE_QUERY=ZERO
BUILD_EXECUTION=ZERO
TEST_EXECUTION=ZERO
PACKAGE_INSTALL=ZERO
SOURCE_MUTATION=ZERO
GIT_MUTATION=ZERO
DEPLOY=ZERO
AUTOMATIC_RETRY=ZERO
PURPOSE=PPC00A_CAPABILITY_DISCOVERY
```

Não é decoração. O mesmo objeto que imprime esse banner é o que recusa a
operação em runtime, e é ele que vai gravado no manifesto de evidência. Banner e
comportamento não podem divergir porque são a mesma coisa.

Os gates de análise recebem exatamente três capacidades: `filesystem_read`,
`git_read`, `filesystem_write` (só para o diretório de evidência, que fica fora
do workspace). `source_mutation` permanece negada — é por isso que o scanner
nunca pode ser a explicação para um arquivo alterado.

---

## PPC-00A — descoberta

```bash
./syra scan --root ~/Projects/SYRA
```

**Responde:** para cada uma das 19 capacidades, onde parece existir uma
implementação.

**Não responde:** se ela funciona, se é alcançável, se está deployada, se é a
canônica.

Toda saída repete a disciplina:

```
FOUND_DOES_NOT_MEAN_CERTIFIED=YES
CERTIFICATION_GRANTED=NO
IMPLEMENTATION_AUTHORIZED=NO
```

Tratar descoberta como certificação é como uma capacidade é marcada "pronta"
enquanto o painel que depende dela está quebrado.

### Classificação de autoridade

Antes de qualquer contagem, o gate resolve quem fala por quê:

| Classe | Escaneado | Motivo |
|---|---|---|
| `PRIMARY_REPOSITORY` | sim | repositório com HEAD resolvido |
| `WORKTREE` | não | evita contar o canônico duas vezes |
| `UNBORN_OR_INVALID` | não | git válido, zero commits — vazio ≠ corrompido |
| `NON_SOURCE_AUTHORITY` | não | backup/evidence/snapshot — histórico, não fonte |

Errar isso é o que trava investigação. Worktree contado como repo separado
infla toda capacidade num falso conflito multi-autoridade. Repositório sem
commits lido como "corrompido" entra numa fila de reparo que ele não precisa.

### Artefatos

```
source-authorities.tsv          quem foi considerado, e por quê
git-baseline.tsv                HEAD + hash de status no início
capability-candidates.tsv       cada arquivo que casou, com os sinais
capability-summary.tsv          agregado por capacidade
architecture-risk-signals.tsv   riscos derivados
final-decision.json             o estado final
evidence-manifest.json          selado por último, cobre todos
```

### Estados

| Estado | Significa | Próximo |
|---|---|---|
| `PASS` | descoberta completa, fontes estáveis | `PPC00B` |
| `STALE_EVIDENCE` | fontes mudaram durante a leitura | revisão manual |
| `FAIL` | preflight rejeitou, ou artefato não foi escrito | corrigir |

---

## Concorrência

O gate captura HEAD + hash de status de cada repositório antes e depois. Se algo
mudou:

```
PPC00A_DECISION=STALE_EVIDENCE
REASON=CONCURRENT_SOURCE_CHANGE_DURING_SCAN
AUTOMATIC_RETRY_AUTHORIZED=NO
NEXT_STATE=MANUAL_CONCURRENCY_REVIEW
```

Três coisas importam nessa mensagem:

1. **É stale, não corrupção.** Trabalho concorrente torna o snapshot misto e as
   conclusões não confiáveis. Nada quebrou.
2. **O gate não escreveu.** Ele nunca abriu árvore de fonte para escrita, e a
   autoridade gravada na evidência prova isso.
3. **Sem retry automático.** Re-rodar sozinho durante trabalho concorrente
   produz outro snapshot misto. Rode quando estiver quieto.

---

## PPC-00B — decisão

```bash
./syra decide --root ~/Projects/SYRA
```

Tabela determinística. A mesma entrada sempre produz a mesma decisão, e toda
capacidade recebe exatamente uma.

| Situação | Modo | Confiança |
|---|---|---|
| ausente, núcleo implementa | `CORE_PROVIDED` | `HIGH` |
| ausente, produto precisa | `BUILD` | `HIGH` / `MEDIUM` |
| vários repos, crítico | `CONSOLIDATE` | **`LOW`** |
| vários repos | `CONSOLIDATE` | `MEDIUM` |
| um repo, crítico, testado | `DO_NOT_TOUCH` | `MEDIUM` |
| um repo, testado + contratado | `REUSE` | `HIGH` |
| um repo, testado, sem contrato | `ADAPT` | `MEDIUM` |
| um repo, sem teste | `HARDEN` | `HIGH` / `MEDIUM` |

### As duas travas anti-autossabotagem

**`DO_NOT_TOUCH`** — capacidade crítica, autoridade única, com testes. Está
carregando peso e parece saudável. Integrar pelo gateway sem modificar.
Revisitar só com evidência de runtime de um defeito real.

**Confiança `LOW` em consolidação de capacidade crítica** — a ação sai
explicitamente como *"não refatore ainda"*. Análise estática não vê qual das
duas implementações o deploy usa. Refatorar um circuit breaker que funciona,
decidindo por saída de grep, é a jogada de maior variância disponível.

### Ordem de trabalho

`CONSOLIDATE` primeiro, sempre. Múltiplas cópias divergentes da mesma capacidade
é a causa direta de integração que quebra na fronteira — resolver isso destrava
o resto.

### Autorização

```json
{
  "advisoryOnly": true,
  "implementationAuthorized": false,
  "sourceMutationAuthorized": false
}
```

O gate propõe. Nunca aplica, nunca autoriza.

---

## Regras permanentes

### SYRA-RULE-PPC-001 — ferramenta de auditoria é não-confiável até ser preflightada

Nenhum comando de governança, auditoria, recovery ou deploy recebe confiança
superior ao sistema que audita.

Nasceu de uma aspa não fechada num heredoc de centenas de linhas, que abortou um
gate **depois** de ele já ter impresso o banner de segurança. Nada foi mutado;
o run se perdeu.

Aplicada em três lugares:

```bash
./syra preflight              # valida o próprio núcleo
./syra preflight <path>       # valida qualquer ferramenta
```

e automaticamente no boot de produto e antes de cada gate.

**A parte que mais importa:** os gates deixaram de ser heredoc. Preflight pega o
erro; runner versionado elimina a superfície onde ele nasce. Código em git não
sofre truncamento de paste, é revisável antes de ser confiado, e é idêntico toda
execução.

### SYRA-RULE-PPC-002 — evidência ou não aconteceu

Um gate que não persistiu seus artefatos não passou, independente do que
imprimiu. `seal()` recusa certificar artefato declarado e ausente.

Diretório de evidência sem manifesto é a marca de um run falho. **Não apague** —
é a evidência da falha, e é ela que impede repetir a mesma investigação.

### SYRA-RULE-PPC-003 — concorrência não é corrupção

Fonte que mudou durante a leitura é `STALE_EVIDENCE`. Nunca diagnosticar como
corrupção, nunca atribuir ao gate, nunca re-rodar automaticamente.

---

## Códigos de saída

| Código | Significa |
|---|---|
| `0` | `PASS` |
| `1` | `FAIL` |
| `2` | erro de uso |
| `30` | `STALE_EVIDENCE` |

Estáveis, para uso em automação.
