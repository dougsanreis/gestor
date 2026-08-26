# Backlog priorizado de implementação

Este backlog converte o roadmap em tarefas verticais. Os IDs são estáveis. A execução deve atualizar somente estado, evidência e decisões, sem renumerar tarefas concluídas.

## Estados

`READY` significa que dependências e critérios estão claros. `BLOCKED` exige blocker explícito. `IN_PROGRESS` possui branch/worktree. `IN_REVIEW` possui evidence bundle. `DONE` exige Governor e gate da fase quando aplicável.

## Fase 0

| ID | Tarefa | Depende de | Owner primário | Critérios de aceite | Estado inicial |
|---|---|---|---|---|---|
| VF-0001 | Inicializar monorepo e comandos padrão | — | implementation-engineer | install, lint, typecheck, test e build reproduzíveis | READY |
| VF-0002 | Registrar ADR da stack e fronteiras | VF-0001 | product-architect | alternativas, decisão, consequências e rollback | READY |
| VF-0003 | Implementar configuração tipada | VF-0001 | implementation-engineer | env inválida falha cedo; segredo não loga | READY |
| VF-0004 | Importar e validar JSON Schemas | VF-0001 | implementation-engineer | exemplos válidos/ inválidos testados | READY |
| VF-0005 | Implementar Mission aggregate | VF-0004 | implementation-engineer | transições e invariantes unit-tested | READY |
| VF-0006 | Criar repository port e memory adapter | VF-0005 | implementation-engineer | contract tests compartilhados | READY |
| VF-0007 | Criar schema PostgreSQL e migrations | VF-0006 | implementation-engineer | up/down ou forward repair testado | READY |
| VF-0008 | Implementar API POST/GET Mission | VF-0006 | implementation-engineer | OpenAPI, erros e auth boundary | READY |
| VF-0009 | Implementar outbox transacional | VF-0007 | implementation-engineer | evento e aggregate atômicos | READY |
| VF-0010 | Implementar worker idempotente | VF-0009 | implementation-engineer | duplicate e retry sem efeito duplo | READY |
| VF-0011 | Instrumentar health e OpenTelemetry | VF-0008 | implementation-engineer | trace IDs, redaction e readiness | READY |
| VF-0012 | Implementar policy de risco/autonomia | VF-0005 | implementation-engineer | fail-closed e matriz testada | READY |
| VF-0013 | Criar CI e evidence manifest | VF-0001 | implementation-engineer | pipeline local/CI equivalentes | READY |
| VF-0014 | Revisão independente F0 | VF-0003–VF-0013 | independent-evaluator | sem blocking finding | BLOCKED |
| VF-0015 | Security/privacy review F0 | VF-0003–VF-0013 | security-privacy-reviewer | verdict PASS/CONDITIONAL resolvido | BLOCKED |
| VF-0016 | Decisão de gate F0 | VF-0014, VF-0015 | governor | APPROVE com evidence completo | BLOCKED |

## Fase 1

| ID | Tarefa | Depende de | Owner | Critério principal |
|---|---|---|---|---|
| VF-0101 | Modelar DAG e Step aggregate | VF-0016 | implementation-engineer | estado persistente sem órfão |
| VF-0102 | Lease, heartbeat e recovery | VF-0101 | implementation-engineer | crash/restart testado |
| VF-0103 | Budgets e cancellation | VF-0101 | implementation-engineer | tempo, custo, turns e tools limitados |
| VF-0104 | Model Router port e fake adapter | VF-0103 | implementation-engineer | sem SDK no domínio |
| VF-0105 | Adapter de modelo configurável | VF-0104 | implementation-engineer | timeout, retry e schema |
| VF-0106 | Tool Gateway e allowlists | VF-0012 | implementation-engineer | todas as tool calls auditadas |
| VF-0107 | Artifact store e provenance | VF-0101 | implementation-engineer | hash e classificação |
| VF-0108 | Evaluation pipeline | VF-0107 | implementation-engineer | autor separado do evaluator |
| VF-0109 | GovernanceDecision e approvals | VF-0108 | implementation-engineer | risk matrix enforced |
| VF-0110 | Failure lab do runtime | VF-0102–VF-0109 | security-privacy-reviewer | timeout, loop, JSON e provider down |
| VF-0111 | Gate F1 | VF-0110 | governor | APPROVE |

## Fase 2 — Vibe Rescue

| ID | Tarefa | Depende de | Owner | Critério principal |
|---|---|---|---|---|
| VF-0201 | Implementar tokens e componentes compartilhados | VF-0111 | experience-designer | WCAG e responsividade |
| VF-0202 | Criar Content Registry | VF-0107 | implementation-engineer | status/hash/risco/expiração |
| VF-0203 | Criar Claim Registry | VF-0202 | implementation-engineer | fail-closed sem evidence |
| VF-0204 | Codificar módulos de copy Vibe Rescue | VF-0202, VF-0203 | human-copywriter | copy aprovada e placeholders tipados |
| VF-0205 | Implementar página SSR | VF-0201, VF-0204 | implementation-engineer | SEO, a11y e budgets |
| VF-0206 | Implementar assessment | VF-0205 | implementation-engineer | score, reason codes e rotas |
| VF-0207 | Implementar Consent Service | VF-0205 | implementation-engineer | grant/deny/withdraw e audit |
| VF-0208 | Implementar eventos Vibe Rescue | VF-0205–VF-0207 | analytics-engineer | schema, sem PII, server truth |
| VF-0209 | Testar journeys por teclado/mobile | VF-0205–VF-0208 | independent-evaluator | PASS sem blockers |
| VF-0210 | Security/privacy review da página | VF-0205–VF-0208 | security-privacy-reviewer | CSP, forms, privacy e claims |
| VF-0211 | Release de homologação | VF-0209, VF-0210 | release-engineer | synthetic + rollback |
| VF-0212 | Gate F2 | VF-0211 | governor | APPROVE |

## Fase 3 — Experimentação

| ID | Tarefa | Depende de | Owner | Critério principal |
|---|---|---|---|---|
| VF-0301 | Persistir ExperimentSpec imutável | VF-0212 | implementation-engineer | mudança após start bloqueada |
| VF-0302 | Assignment determinístico | VF-0301 | implementation-engineer | unidade estável e namespace |
| VF-0303 | Exposure logging | VF-0302 | analytics-engineer | um exposure por epoch |
| VF-0304 | Metric Registry e transforms | VF-0303 | analytics-engineer | lineage e versões |
| VF-0305 | Data quality e SRM | VF-0303 | analytics-engineer | pausa automática |
| VF-0306 | Analysis engine baseline | VF-0304, VF-0305 | experiment-analyst | golden datasets |
| VF-0307 | Guardrails multiobjetivo | VF-0306 | implementation-engineer | hard constraints |
| VF-0308 | Release Controller | VF-0307 | implementation-engineer | canary e rollback |
| VF-0309 | Drill completo | VF-0308 | release-engineer | falha sintética volta ao controle |
| VF-0310 | Gate F3 | VF-0309 | governor | APPROVE |

## Fases 4 e 5

| ID | Tarefa | Dependência | Owner | Critério principal |
|---|---|---|---|---|
| VF-0401 | Implementar página AgentOps ROI | VF-0310 | squad page | copy, claims, a11y e events |
| VF-0402 | Readiness assessment B2B | VF-0401 | implementation-engineer | score explicável |
| VF-0403 | Scorecard e baseline export | VF-0402 | analytics-engineer | definições versionadas |
| VF-0404 | Trust package | VF-0402 | security-privacy-reviewer | owner approval |
| VF-0405 | Booking adapter | VF-0402 | implementation-engineer | webhook idempotente |
| VF-0406 | Gate F4 | VF-0403–VF-0405 | governor | APPROVE |
| VF-0501 | Implementar página Launch OS | VF-0310 | squad page | copy, a11y e events |
| VF-0502 | Quiz e roteamento | VF-0501 | implementation-engineer | reason codes e risk stop |
| VF-0503 | Workspace e Mapa 6D | VF-0502 | implementation-engineer | isolamento e artifacts |
| VF-0504 | Milestones e ativação | VF-0503 | analytics-engineer | evidência de progresso |
| VF-0505 | Gate F5 | VF-0504 | governor | APPROVE |

## Fase 6 — Personalização

| ID | Tarefa | Dependência | Owner | Critério principal |
|---|---|---|---|---|
| VF-0601 | Eligibility engine | VF-0212, VF-0406, VF-0505 | implementation-engineer | claims/status/risco/TTL |
| VF-0602 | Decision API | VF-0601 | implementation-engineer | retorna IDs, não copy online |
| VF-0603 | Consent e opt-out propagation | VF-0602 | implementation-engineer | efeito imediato |
| VF-0604 | Edge/server fallback | VF-0602 | implementation-engineer | controle em timeout |
| VF-0605 | Reason codes e UI | VF-0602 | experience-designer | compreensível |
| VF-0606 | Cross-tenant/fairness test | VF-0601–VF-0605 | security-privacy-reviewer | zero vazamento e sinais proibidos |
| VF-0607 | Gate F6 | VF-0606 | governor | APPROVE |

## Fases 7 e 8 — Auto-otimização

| ID | Tarefa | Dependência | Owner | Critério principal |
|---|---|---|---|---|
| VF-0701 | Observer aggregate | VF-0607 | analytics-engineer | qualidade e provenance |
| VF-0702 | Diagnosis artifact | VF-0701 | funnel-strategist | causas com evidência |
| VF-0703 | Hypothesis generator | VF-0702 | funnel-strategist | falsificável |
| VF-0704 | Candidate generation | VF-0703 | copy/UX agents | dentro de envelope |
| VF-0705 | Comparative evaluation | VF-0704 | independent-evaluator | calibration dataset |
| VF-0706 | Shadow decision log | VF-0705 | governor | nenhuma publicação |
| VF-0707 | Gate F7 | VF-0706 | governor + human owners | APPROVE |
| VF-0801 | Autonomy envelope | VF-0707 | product-architect | capability × risk × tenant |
| VF-0802 | Pre-approval templates | VF-0801 | governor + human owners | escopo e expiração |
| VF-0803 | L3 low-risk execution | VF-0802 | implementation-engineer | auto-pause e rollback |
| VF-0804 | L4 approved allocation | VF-0803 | experiment-analyst | variantes já aprovadas |
| VF-0805 | Kill-switch drill | VF-0803, VF-0804 | release-engineer | todos os escopos testados |
| VF-0806 | Final production gate | VF-0805 | governor + human owners | APPROVE |

## Regra de priorização dinâmica

Entre tarefas READY da mesma fase, selecione a que maximiza `unblocked_value / risk_adjusted_effort`, desde que não quebre a ordem de dependências. Incidentes, falhas de dados e findings críticos precedem desenvolvimento de novas features.
