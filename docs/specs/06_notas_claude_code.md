# Notas verificadas — Claude Code e Agent SDK

## Subagentes

Fonte: https://code.claude.com/docs/en/sub-agents

A documentação oficial define subagentes como assistentes especializados que executam em janelas de contexto próprias, com prompt de sistema, acesso a ferramentas e permissões independentes. Eles são indicados para preservar contexto, impor restrições, reutilizar configurações, especializar comportamento e controlar custo por roteamento de modelos.

Definições de projeto ficam em `.claude/agents/` e podem ser versionadas. Os campos incluem `name`, `description`, `tools`, `disallowedTools`, `model`, `permissionMode`, `mcpServers`, `hooks`, `maxTurns`, `skills`, `memory`, `effort`, `background` e `isolation`. O modo `isolation: worktree` permite executar um subagente em cópia isolada do repositório, reduzindo colisões e risco de alterações no checkout principal. Subagentes não recebem automaticamente todo o prompt interno do Claude Code; o corpo do arquivo Markdown funciona como seu prompt de sistema, o que torna os contratos explícitos essenciais.

Implicação arquitetural: o squad será representado por agentes de projeto versionados, com ferramentas mínimas e segregação de funções. Autores de copy não terão permissão de deploy; agentes de experimento não poderão aprovar a própria hipótese; agentes de implementação usarão worktrees; agentes de avaliação serão read-only; e qualquer mutação de produção dependerá de policy gate determinístico e aprovação conforme risco.

## Hooks

Fonte: https://code.claude.com/docs/en/hooks

Hooks são comandos, endpoints HTTP ou handlers acionados em pontos do ciclo de vida. A referência inclui eventos como `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PermissionRequest`, `PostToolUse`, `PostToolUseFailure`, `PostToolBatch` e `PermissionDenied`. Handlers recebem JSON de contexto, podem adicionar contexto, registrar ações ou controlar decisões. Códigos de saída e saídas JSON permitem bloquear, permitir, pedir revisão ou instruir retry em situações específicas.

Implicação arquitetural: regras que não podem depender de interpretação probabilística serão implementadas em hooks e serviços de política. Exemplos incluem bloqueio de arquivos de segredo, proibição de comandos destrutivos, limites de domínio, verificação de branch, exigência de ticket de mudança, schema validation, scanner de claims comerciais e registro obrigatório de tool calls.

## Princípio de integração

Claude Code será o ambiente de implementação e coordenação de desenvolvimento, mas não o único runtime de produção do funil. O sistema comercial persistente deverá operar em serviços próprios, com filas, banco de dados, observabilidade e políticas. O Agent SDK ou execução programática poderá ser utilizado para tarefas limitadas e auditáveis, mantendo o core de decisão, métricas e publicação independente do cliente de terminal.

## Equipes de agentes

Fonte: https://code.claude.com/docs/en/agent-teams

As equipes de agentes coordenam múltiplas instâncias do Claude Code com um líder, colegas independentes, lista compartilhada de tarefas e caixas de mensagem. Porém, o recurso é experimental e a documentação aponta limitações em retomada de sessões, atualização de status, shutdown, um único time por sessão, ausência de equipes aninhadas e liderança fixa.

Implicação arquitetural: equipes experimentais podem acelerar **desenvolvimento e revisão paralela**, mas não serão usadas como orquestrador primário de produção. O runtime comercial terá máquina de estados, filas e contratos persistentes próprios. Claude Code atuará como executor dentro de tarefas delimitadas, enquanto o banco de controle permanece fonte de verdade.

## Execução programática

Fonte: https://code.claude.com/docs/en/headless

O Claude Code pode operar de forma não interativa com `claude -p`, ou via Agent SDK em Python e TypeScript. A documentação recomenda saídas estruturadas, allowlists de ferramentas, códigos de saída e modo `--bare` para scripts e CI, porque esse modo evita auto-descoberta de hooks, plugins, MCPs, memória e instruções não declaradas. Em modo não-bare, um repositório pode carregar configurações e servidores sem um diálogo de confiança em sessão `-p`, o que exige cuidado com conteúdo não confiável. Processos em background não devem ser tratados como serviços persistentes; são encerrados ao final e a espera de agentes tem teto configurável.

Implicação arquitetural: automações de CI usarão `--bare`, configurações versionadas, agentes fornecidos explicitamente, ferramentas permitidas, timeout, idempotency key, schema de saída e verificação de exit code. Serviços 24/7 não rodarão como processos filhos de uma sessão Claude Code.
