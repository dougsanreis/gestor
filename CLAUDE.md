# Vibe Funnel OS — Instruções operacionais para Claude Code

## Missão

Construir e manter um sistema de funis de vendas para o nicho de vibe coding, com três ofertas iniciais: **Vibe Rescue**, **AgentOps ROI** e **Launch OS**. O sistema cria páginas, journeys e variantes, mas só publica mudanças após contratos, avaliações, políticas, testes e aprovação proporcionais ao risco.

## Resultado esperado

O repositório precisa gerar software executável, não apenas planos. Cada fase termina com código, testes, evidência, documentação e um comando reproduzível. Nunca declare uma capacidade como pronta sem teste ou artefato verificável.

## Princípios não negociáveis

1. **Fail closed para risco.** Se política, consentimento, prova, schema ou aprovação estiverem indisponíveis, use o controle ou bloqueie a mutação.
2. **Autonomia limitada.** Agentes propõem e preparam; serviços determinísticos e pessoas governam promoção e produção.
3. **Segregação de funções.** Autor não avalia nem aprova o próprio artefato.
4. **Trabalho isolado.** Toda alteração relevante usa branch e, para agentes mutadores, worktree.
5. **Reversibilidade.** Nenhum release sem flag, versão anterior saudável e rollback testado.
6. **Sem claims inventados.** Prova, depoimento, preço, garantia, escassez e compatibilidade vêm de registries aprovados.
7. **Privacidade por padrão.** PII não entra em analytics, prompts, logs ou traces genéricos.
8. **Métrica de resultado.** Não otimize clique isolado; inclua fit, receita líquida, ativação, reembolso, churn, suporte e confiança.
9. **Portabilidade.** Domínio, contratos e dados não dependem de um único modelo ou provedor.
10. **Evidência antes de status.** “Pronto” significa testes verdes, artifact hashes, gates aprovados e documentação atualizada.

## Stack de referência

Use TypeScript em monorepo com `pnpm`. O baseline é um modular monolith com fronteiras claras:

- `apps/web`: páginas públicas, quizzes e console.
- `apps/api`: BFF, domínio, decisão, consentimento, experimentos e governança.
- `apps/worker`: missões, agentes, avaliações e jobs.
- PostgreSQL: fonte de verdade transacional.
- Fila persistente PostgreSQL no MVP; adapter pronto para workflow engine dedicado.
- Object storage S3-compatible para artifacts/evidence.
- OpenTelemetry para logs, métricas e traces.
- OpenFeature-compatible feature flags.
- Policy engine por interface; implementação inicial determinística e adapter para OPA.

Antes de adicionar framework ou serviço, registre um ADR com problema, alternativas, decisão e consequência.

## Estrutura-alvo

```text
apps/
  web/
  api/
  worker/
packages/
  domain/
  contracts/
  db/
  events/
  policy/
  agents/
  experiments/
  observability/
  ui/
  config/
  testkit/
docs/
  adr/
  architecture/
  product/
  runbooks/
  evidence/
.claude/
  agents/
  hooks/
  rules/
  settings.json
```

## Fluxo obrigatório por tarefa

1. Ler o issue, o contrato relevante e o estado atual.
2. Declarar hipótese, risco, arquivos afetados e critérios de aceite.
3. Confirmar que não existe implementação equivalente.
4. Criar branch/worktree e plano curto.
5. Implementar o menor incremento vertical completo.
6. Executar formatter, typecheck, lint e testes seletivos.
7. Executar testes de contrato, policy e segurança aplicáveis.
8. Revisar diff e atualizar documentação.
9. Gerar `evidence/<task-id>/manifest.json` com comandos, resultados e hashes.
10. Solicitar avaliação independente.
11. Somente após gates, marcar a tarefa como concluída.

## Proibições

Não execute `rm -rf`, `git reset --hard`, `git clean -fdx`, `sudo rm`, `mkfs`, `dd` destrutivo, `curl | sh`, `wget | sh`, `shutdown`, `reboot`, `kill -9` indiscriminado, alteração de firewall, destruição de banco, rotação de segredo ou deploy de produção sem política e aprovação.

Não edite `.env`, credenciais, settings gerenciados, políticas de produção, preços, garantias, textos legais ou evidence records sem autorização explícita. Não desative testes para obter verde. Não reduza limiares ou remova asserts sem explicar a causa.

## Tratamento de falhas

Uma mesma tentativa pode ser repetida no máximo duas vezes após diagnóstico. A terceira tentativa exige mudança de abordagem e registro da causa. Loops, regressões recorrentes e falhas iguais geram `learning_candidate`; não geram regra global automaticamente.

Quando faltar dado, não invente. Crie placeholder tipado e fail-closed. Quando faltar credencial, implemente adapter fake somente em teste e documente a configuração real. Quando o requisito for ambíguo, escolha a alternativa mais segura e reversível, registrando a premissa.

## Definition of Done global

Uma capability está pronta apenas quando:

| Gate | Evidência |
|---|---|
| Funcional | Teste de aceitação executável |
| Contrato | JSON Schema/OpenAPI validado |
| Qualidade | Typecheck, lint e testes verdes |
| Segurança | Scans e threat checks aplicáveis |
| Privacidade | Data inventory e finalidade atualizados |
| Observabilidade | Logs/métricas/traces e IDs de correlação |
| Operação | Runbook, alerta e rollback |
| UX | Acessibilidade e estados de erro |
| Documentação | Técnica e linguagem direta |
| Governança | Decision record e approvals conforme risco |

## Ordem de implementação

1. Fundamentos do monorepo, contratos, banco, observabilidade e política.
2. Workflow/Mission runtime com idempotência, budgets e state machine.
3. Vibe Rescue end-to-end: página, assessment, eventos e oferta sem checkout real.
4. Experimentos, exposure logging, métricas e rollback.
5. AgentOps ROI e piloto readiness.
6. Launch OS, quiz e onboarding.
7. Personalização por módulos aprovados.
8. Auto-otimização L3/L4 somente após shadow mode e baseline.

## Formato de status

Ao terminar um ciclo, responda com:

```text
STATUS: COMPLETE | PARTIAL | BLOCKED
TASK: <id e título>
CHANGED: <arquivos e migrations>
VALIDATED: <comandos e resultados>
EVIDENCE: <paths>
RISKS: <riscos residuais>
NEXT: <uma próxima tarefa de maior ROI>
```

`COMPLETE` é proibido quando qualquer critério obrigatório estiver pendente.
