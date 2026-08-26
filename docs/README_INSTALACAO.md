# Instalação e uso no Claude Code

Este pacote transforma a documentação em instruções, agentes, hooks, contratos e backlog executáveis. Ele não publica nada e não contém credenciais.

## 1. Pré-requisitos

Instale e autentique o Claude Code conforme a documentação oficial. O projeto precisa de Git, Node.js LTS, `pnpm`, Python 3 e Docker somente se a equipe escolher PostgreSQL local em contêiner.

Verifique:

```bash
git --version
node --version
pnpm --version
python3 --version
claude --version
```

## 2. Criar ou preparar o repositório

Para um projeto novo:

```bash
mkdir -p ~/vibe-funnel-os
cd ~/vibe-funnel-os
git init
git switch -c main
```

Para um repositório existente, entre na raiz e confirme que trabalho não relacionado está salvo:

```bash
cd /caminho/do/repo
git status --short
```

Não use reset ou limpeza destrutiva para instalar o pacote.

## 3. Copiar o pacote

Copie o conteúdo desta pasta para a raiz do repositório, preservando diretórios ocultos:

```bash
cp -R /caminho/do/claude_code_pack/. /caminho/do/repo/
cd /caminho/do/repo
chmod +x .claude/hooks/*.py scripts/*.py
python3 scripts/validate_pack.py
```

Resultado esperado:

```text
PACK VALIDATION: PASSED
```

Se o repositório já possui `CLAUDE.md`, `.claude/settings.json` ou agentes, faça merge manual. Hooks em settings diferentes podem ser combinados; não remova políticas gerenciadas da organização.

## 4. Revisar proteções

Abra os arquivos:

```text
CLAUDE.md
.claude/settings.json
.claude/hooks/guard_pre_tool.py
.claude/hooks/post_change_check.py
```

As proteções bloqueiam comandos destrutivos e escrita em arquivos sensíveis. A permissão padrão continua ativa; silêncio do hook não equivale a aprovação automática.

Teste o hook sem executar operações perigosas:

```bash
printf '%s' '{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"rm -rf /tmp/example"}}' \
  | python3 .claude/hooks/guard_pre_tool.py
```

O resultado deve conter `permissionDecision: deny`.

## 5. Iniciar a sessão

```bash
claude --permission-mode default
```

Cole o bloco de **PROMPT** em `PROMPT_MESTRE_CLAUDE_CODE.md`. Na primeira execução, o Claude deve ler os specs, inspecionar o repositório e implementar a Fase 0 ou o primeiro gate pendente.

Não use `--dangerously-skip-permissions`. O sistema foi desenhado para decisões explícitas e auditáveis.

## 6. Execução não interativa controlada

Use somente para tarefas pequenas, com output estruturado e sem ação de produção:

```bash
claude -p \
  --permission-mode default \
  --output-format json \
  "Leia CLAUDE.md e execute apenas VF-0004. Valide, gere evidence bundle e pare."
```

Para automação de CI, aplique timeout externo, working directory isolado, budget de custo, branch dedicada e artefatos persistentes. Uma execução não interativa não deve aprovar o próprio release.

## 7. Sequência recomendada de sessões

| Sessão | Objetivo | Saída esperada |
|---:|---|---|
| 1 | VF-0001 a VF-0004 | Workspace e schemas verdes |
| 2 | VF-0005 a VF-0008 | Mission e API |
| 3 | VF-0009 a VF-0013 | Outbox, worker, policy e telemetry |
| 4 | VF-0014 a VF-0016 | Reviews e gate F0 |
| 5+ | Fase 1 do roadmap | Runtime de agentes |

Essa divisão é orientativa. O Claude Code deve respeitar a unidade vertical e não ultrapassar contexto, custo ou risco.

## 8. Artefatos que devem aparecer

Após cada tarefa, procure:

```text
evidence/<task-id>/manifest.json
docs/adr/ADR-*.md
docs/implementation/TASKS.md
docs/runbooks/*.md
```

O status `COMPLETE` só é válido se comandos, resultados, hashes e riscos estiverem registrados.

## 9. Variáveis e segredos

Forneça um `.env.example` sem valores reais. Segredos ficam em secret manager, CI secret ou arquivo local ignorado. Nunca cole chaves em prompt, issue, trace ou artifact.

## 10. Git e revisão

Use uma branch por tarefa ou incremento:

```bash
git switch -c feat/VF-0001-workspace
git status --short
git diff --check
```

Antes de merge, peça revisão independente e decisão de gate conforme risco. O agente implementador não aprova a própria alteração.

## 11. Quando o Claude parar

Se a sessão parar apenas com plano, envie:

> Execute agora a fase atual conforme o Prompt Mestre. Pare somente nos blockers autorizados. Não gere outro plano.

Se houver loop, peça:

> Interrompa a abordagem atual. Registre tentativas e evidências, identifique a causa provável e escolha uma alternativa menor e reversível.

Se houver blocker real, responda somente com a decisão solicitada. Não forneça segredos no chat quando existir canal de configuração apropriado.

## 12. Checklist antes de qualquer produção

| Verificação | Obrigatória |
|---|---|
| Reviews independentes concluídos | Sim |
| Claims, preços e termos aprovados | Sim |
| Consentimento e privacidade validados | Sim |
| Testes, scans e synthetic checks verdes | Sim |
| Feature flag e rollback testados | Sim |
| Observabilidade e alertas ativos | Sim |
| Kill switch exercitado | Sim |
| Autorização humana aplicável | Sim |

Sem qualquer item, o release permanece em homologação.
