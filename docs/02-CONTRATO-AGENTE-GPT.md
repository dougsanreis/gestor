# Contrato Operacional do Agente GPT/Codex — GOVIO

Cole este contrato como instrução permanente do agente. Ele **substitui** o modo de
operação por máquina de estados cerimonial. Foi escrito a partir de falhas
observadas, não de teoria.

---

## Parte 1 — O comando único de abertura

Nenhuma sessão começa sem isto. Ele responde as quatro perguntas que, não
respondidas, custaram as sessões anteriores.

```bash
govio-preflight \
  --intent  "govio-<area>-<resultado>" \
  --goal    "<o que a prefeitura passa a conseguir fazer>" \
  --files   <arquivos que serão tocados> \
  --roots   ~/.syra/worktrees ~/Projects/SYRA
```

Ele executa, em ordem, e para no primeiro bloqueio:

| # | Pergunta | Invariante | Falha significa |
|---|---|---|---|
| 1 | Estou na fonte canônica? | INV-001 | `govio-ssot pin` antes de qualquer coisa |
| 2 | Este trabalho já existe? | INV-004/005 | retomar o existente, não criar o próximo duplicado |
| 3 | Quanto gate este risco merece? | INV-002 | usar exatamente os gates do tier — nem mais, nem menos |
| 4 | A sessão anterior entregou? | INV-003/007 | fechar a anterior com um SHIP real antes de abrir outra |

Saída `VERDICT=AUTHORIZED` imprime a sequência exata autorizada.
Saída `VERDICT=BLOCKED` nomeia o bloqueio e o comando de saída.

---

## Parte 2 — As sete regras de conduta

### R1 — O gate é função do raio de destruição, nunca da ansiedade

```bash
govio-tier classify <arquivos>
```

Aplicar gate acima do tier classificado é **violação de INV-002**, não zelo.
O `govio-apply` recusa `--expect-postimage` em TIER-0/1 com `FAIL CERIMONIA_EXCESSIVA`.

Em TIER-0/1 o rollback é `git checkout -- <arquivo>`. Não construa transação sobre
um sistema que já é transacional.

### R2 — Mecânica barata sempre; prova cara só quando o tier paga

`tmp` + `fsync` + `os.replace` fica **sempre** ligado — não custa sessão.
Bindings SHA, contrato de autoridade e revisor humano entram **a partir do TIER-2**.

### R3 — Uma fonte canônica, verificada, nunca digitada

```bash
cd "$(govio-ssot path)"     # falha alto se o pin não valer mais
```

Proibido: caminho literal em comando. Proibido: `cd` para caminho de exemplo.
O guarda rejeita `CAMINHO`, `SEU_`, `PATH_TO`, `<...>`, `EXEMPLO`, `TODO` antes de virar comando.

### R4 — Antes de criar, provar que não existe

```bash
govio-dedupe check "<slug>" --roots ~/.syra/worktrees
```

`CREATE_BLOCKED` significa **retomar**, não renomear com `-v2`, `-r2`, `-real`, `-fast`, `-new`.
Esses sufixos são as cinco tentativas de painel que já existem.

### R5 — Predicado de conclusão antes de começar

Toda unidade declara como se prova que está pronta. Predicado já satisfeito é
saída rápida `NOOP` — **proibido reconstruir**.

```bash
govio-apply --file X --content-from Y    # segunda vez -> VERDICT=NOOP
```

### R6 — Sessão sem delta visível é incidente P0

```bash
govio-ledger open   <sessao> --goal "<delta>"
govio-ledger ship   "<o que a prefeitura passa a conseguir>" --session <sessao> --tier <N> --files <...>
govio-ledger report --enforce
```

Não conta como entrega: gate aprovado, estado avançado, documento de autorização,
diagnóstico, plano. Conta como entrega: comportamento novo no produto, verificável
pelo usuário final.

### R7 — Toda regra nova nasce com dono e prazo, sob teto rígido

```bash
jq '.hardCap, (.invariants|length)' policy/invariants.json
```

Conjunto cheio: para entrar uma regra, **outra tem de sair**. É o teto que quebra a
catraca. Sem teto, cada incidente encarece permanentemente todas as mudanças futuras
e o projeto volta a parar.

---

## Parte 3 — Proibições explícitas

Cada uma corresponde a um custo já pago.

1. **Proibido** criar estado de máquina de controle novo sem que o anterior tenha
   produzido delta de produto mensurável. *(4 estados, 0 linha)*
2. **Proibido** exigir binding SHA para arquivo local rastreado por git. *(~180 min, 0 entrega)*
3. **Proibido** operar fora de `$(govio-ssot path)`. *(`/CAMINHO/REAL/DO/govio-core` ×3)*
4. **Proibido** criar worktree/branch sem `govio-dedupe check`. *(5× painel, 2× worker, 2× critical)*
5. **Proibido** transformar incidente em regra permanente sem dono e TTL. *(7 regras de 1 incidente)*
6. **Proibido** reconstruir funcionalidade sem checar o predicado de conclusão.
7. **Proibido** adicionar cerimônia de repositório antes de 2+ contribuidores. *(72 linhas / 15 arquivos)*
8. **Proibido** relatar sucesso citando gate aprovado. Só `govio-ledger ship` conta.

---

## Parte 4 — Formato de resposta obrigatório do agente

Toda resposta de execução termina com este bloco, e nada além dele:

```
INTENT=<slug>
TIER=<0..3>
GATES_APLICADOS=<lista exata>
ARQUIVOS=<lista>
DELTA_USUARIO_FINAL=<uma frase, ou NENHUM>
SHIP_REGISTRADO=<sim|nao>
VERDICT=<PASS|BLOCKED|NOOP|FAIL:<codigo acionavel>>
PROXIMO_COMANDO=<comando literal, colável>
```

Regras de preenchimento:

- `DELTA_USUARIO_FINAL=NENHUM` **exige** `VERDICT=BLOCKED` com o motivo.
  Não existe execução bem-sucedida sem delta.
- `FAIL:` só aceita código acionável (`PLACEHOLDER_PATH`, `MARKER_ABSENT`,
  `CERIMONIA_EXCESSIVA`, `PROVA_AUSENTE`, `POSTIMAGE_DIVERGENTE`, `CREATE_BLOCKED`,
  `ZERO_DELTA`). **Proibido** `FAIL_TOOLING` e `BLOCKED_EXTERNAL` genéricos: não
  informam o próximo passo.
- `PROXIMO_COMANDO` é literal e colável. Nunca prosa, nunca caminho de exemplo.

---

## Parte 5 — Fronteira que se mantém

A separação entre **mutação local determinística** e **observação externa não
determinística** estava correta no modo antigo e é preservada:

- Mutação local (TIER 0/1) não consulta GitHub, Vercel, CI ou produção.
- Observação externa é fase própria, com seu próprio registro no ledger.
- `git push`, deploy e migração são TIER 2/3 e carregam os gates completos.

O que muda: essa fronteira **deixa de ser desculpa para não entregar**. Cruzá-la é
um passo do trabalho, não um novo estado de máquina a ser autorizado por si mesmo.
