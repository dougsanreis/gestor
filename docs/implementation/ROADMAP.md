# Roadmap executável — Vibe Funnel OS

**Princípio:** entregar capacidade vertical antes de ampliar arquitetura. Cada fase é demonstrável, testável e reversível.

## Visão geral

| Fase | Resultado demonstrável | Dependência | Gate principal |
|---:|---|---|---|
| 0 | Criar e consultar uma Mission com eventos e policy | Nenhuma | CI + evidence bundle |
| 1 | Executar missão com agente e ferramenta em sandbox | F0 | Idempotência, budget e falhas |
| 2 | Vibe Rescue completo até assessment | F1 | Acessibilidade, tracking e privacy |
| 3 | Experimento e release controlado | F2 | Exposure, SRM, canary e rollback |
| 4 | AgentOps ROI e readiness B2B | F3 | Qualificação e trust package |
| 5 | Launch OS e onboarding | F3 | Roteamento e ativação |
| 6 | Personalização modular | F2–F5 | Fallback, opt-out e reason codes |
| 7 | Shadow optimization | F3/F6 | Avaliação offline e zero publicação |
| 8 | Autonomia limitada L3/L4 | F7 | Kill switch e guardrails exercitados |

## Fase 0 — Fundação executável

### Objetivo

Criar o monorepo, os contratos, o domínio de Mission, a persistência inicial, a outbox, observabilidade e policy mínima. O usuário deve conseguir criar uma missão por API, consultar seu estado e ver o evento correspondente.

| Epic | Entrega | Testes | Gate |
|---|---|---|---|
| F0-E1 Workspace | pnpm workspace, TypeScript, lint, format, test e build | Smoke CI | Todos os comandos reproduzíveis |
| F0-E2 Config | Env tipada, sem secrets em repo | Invalid/missing env | Fail-fast |
| F0-E3 Contracts | Schemas importados e validator | Válidos e inválidos | 100% exemplos esperados |
| F0-E4 Domain | Mission aggregate e transições | Unit + property-based opcional | Invariantes verdes |
| F0-E5 Persistence | Repo port, memory adapter e PostgreSQL | Integration | Migração reversível |
| F0-E6 API | POST/GET missions e erros tipados | Contract + integration | OpenAPI consistente |
| F0-E7 Outbox | Event persistido na transação | Duplicate/retry | Sem efeito duplicado |
| F0-E8 Observability | Traces, logs redigidos e health | Telemetry smoke | IDs de correlação |
| F0-E9 Policy | Risco/autonomia inicial | Policy unit | Fail-closed |
| F0-E10 Evidence | Manifest e docs de execução | Pack validation | Auditável |

**Demo:** criar missão, receber ID, consultar estado, listar evento outbox e abrir trace.

## Fase 1 — Runtime de missão e agentes

### Objetivo

Executar Steps persistentes com budgets, retries, cancellation, Agent Adapter e Tool Gateway. A primeira missão usa um agente fake determinístico em teste e um adapter real configurável fora do domínio.

| Epic | Entrega | Testes | Gate |
|---|---|---|---|
| F1-E1 DAG | Step dependencies e state transitions | Unit + integration | Sem estado órfão |
| F1-E2 Worker | Claim, lease, heartbeat e recovery | Crash/restart | At-least-once sem efeito duplicado |
| F1-E3 Budgets | Tempo, custo, turns e tools | Boundary tests | Interrupção previsível |
| F1-E4 Model Router | Port, catálogo e fallback | Contract | Provider independente |
| F1-E5 Tool Gateway | Allowlists, schema e audit | Deny/allow | Toda chamada governada |
| F1-E6 Artifacts | Storage, hash e provenance | Tamper test | Integridade verificável |
| F1-E7 Evaluations | Rubric, evaluator e verdict | Independent evaluator | Autor separado |
| F1-E8 Governance | Decision aggregate e approvals | Risk matrix | High/critical exige humano |
| F1-E9 Failure Lab | Timeout, duplicate, provider down, invalid JSON | Chaos suite | Degradação segura |

**Demo:** missão cria copy candidate fake, chama ferramenta permitida, gera artifact, falha em avaliação, rework uma vez e termina aprovada com evidence bundle.

## Fase 2 — Vibe Rescue vertical

### Objetivo

Publicar a página Vibe Rescue com módulos versionados, assessment, roteamento, consentimento e eventos. Checkout permanece adapter stub ou modo sandbox até aprovação comercial.

| Epic | Entrega | Testes | Gate |
|---|---|---|---|
| F2-E1 Design System | Tokens e componentes | Visual/a11y | Sem bloqueio de teclado |
| F2-E2 Content Registry | Conteúdo da página e claims fail-closed | Contract | Placeholder não renderiza |
| F2-E3 Page Runtime | SSR/SEO/responsivo | E2E mobile/desktop | Performance budget |
| F2-E4 Assessment | Perguntas, score e reason codes | Unit/E2E | Sem PII em analytics |
| F2-E5 Journey State | Estado e rota Vibe Rescue/Launch/AgentOps | State tests | Próxima ação explicável |
| F2-E6 Consent | Cookies e preferências | E2E | Não essencial off por padrão |
| F2-E7 Events | Page, CTA, assessment e route | Schema/replay | Exposure/event integrity |
| F2-E8 Proof Registry | Cases e evidências | Expiry tests | Claim sem prova bloqueado |
| F2-E9 Release | Homologação, synthetic e flag | Rollback | Controle saudável |

**Demo:** visitante recusa personalização, navega, faz assessment, recebe rota com reason codes, e eventos válidos aparecem sem PII.

## Fase 3 — Experimentação e release control

### Objetivo

Executar um experimento interno/sintético de módulo da página, registrar exposure, detectar SRM, pausar por guardrail e reverter release.

| Epic | Entrega | Testes | Gate |
|---|---|---|---|
| F3-E1 ExperimentSpec | Imutabilidade e approvals | Contract | Não altera após start |
| F3-E2 Assignment | Randomização estável e namespace | Determinism | Sem colisão |
| F3-E3 Exposure | Evento server-side | Duplicate | Um exposure por epoch |
| F3-E4 Metrics | Definitions e transforms | Fixture | Reproduzível |
| F3-E5 Integrity | SRM, completeness e contamination | Synthetic | Pausa automática |
| F3-E6 Analysis | Método configurável | Golden dataset | Decision explicável |
| F3-E7 Guardrails | Quality, complaints, errors | Boundary | Hard constraint |
| F3-E8 Release Control | Canary e rollback | Drill | ≤5 min em teste |

**Demo:** experimento sintético inicia, recebe dados, detecta SRM, pausa e serve controle; após correção, nova versão executa e produz decisão.

## Fase 4 — AgentOps ROI

### Objetivo

Entregar página, scorecard e readiness assessment B2B, com trust package, qualificação e agendamento por adapter.

| Epic | Entrega | Gate |
|---|---|---|
| F4-E1 Page | Copy e arquitetura aprovadas | Claims e a11y |
| F4-E2 Readiness | Inventário, maturidade e risk bands | Reason codes |
| F4-E3 Scorecard | Definições e baseline export | Métricas versionadas |
| F4-E4 Trust Package | Security, privacy, deployment options | Owner approval |
| F4-E5 Qualification | Sponsor, squad, repo e fit | Sem vigilância individual |
| F4-E6 Schedule Adapter | Booking sandbox/real config | Webhook idempotente |

**Demo:** organização completa readiness, recebe scorecard explicável e agenda workshop em sandbox.

## Fase 5 — Launch OS

### Objetivo

Entregar página, quiz, Mapa 6D, plano inicial e onboarding por marco.

| Epic | Entrega | Gate |
|---|---|---|
| F5-E1 Page | Copy e Mapa 6D | A11y/performance |
| F5-E2 Quiz | Ideia/demo/risco e roteamento | Explicável |
| F5-E3 Project Workspace | Decisões e artifacts | Tenant isolation |
| F5-E4 Milestones | Definição e progresso | Evidência, não scroll |
| F5-E5 Onboarding | Primeiro marco e suporte | Time-to-value |
| F5-E6 Expansion | Rota para Rescue/AgentOps | Fit antes de ticket |

**Demo:** visitante com demo instável é roteado para Vibe Rescue; iniciante recebe plano 6D e cria marco.

## Fase 6 — Personalização modular

### Objetivo

Selecionar módulos aprovados por contexto autorizado, sem geração online e com fallback controle.

| Epic | Entrega | Gate |
|---|---|---|
| F6-E1 Content eligibility | Status, risco, claims e expiração | Fail-closed |
| F6-E2 Decision API | Input minimizado e output por IDs | p95 e fallback |
| F6-E3 Consent | Opt-in/out e reset | Propagação imediata |
| F6-E4 Reason codes | Explicação para rota e experiência | UX validada |
| F6-E5 Cache | Edge/server cache sem cross-tenant | Isolation |
| F6-E6 Fairness | Segmentos proibidos e proxies | Policy tests |

**Demo:** serviço indisponível serve controle; retirada de consentimento remove personalização na próxima decisão.

## Fase 7 — Auto-otimização em shadow mode

### Objetivo

Agentes observam, diagnosticam, geram hipóteses e candidatos, mas não iniciam experimentos nem publicam.

| Epic | Entrega | Gate |
|---|---|---|
| F7-E1 Observe | Aggregate signals | Data quality |
| F7-E2 Diagnose | Problema e causa provável | Evidence links |
| F7-E3 Hypothesis | Spec falsificável | Analyst review |
| F7-E4 Generate | Copy/UX candidate | Claims and policy |
| F7-E5 Evaluate | Rubrics e comparative eval | Independent verdict |
| F7-E6 Shadow score | Comparação com decisões humanas | Calibration |

**Demo:** sistema recomenda variante, explica a hipótese, é avaliado e arquivado sem tocar em tráfego.

## Fase 8 — Autonomia limitada

### Objetivo

Liberar L3 para experimentos de baixo risco pré-aprovados e L4 somente para alocação entre variantes aprovadas.

| Epic | Entrega | Gate |
|---|---|---|
| F8-E1 Autonomy envelope | Capacidade × risco × tenant | Policy coverage |
| F8-E2 Approval templates | Pre-approval limitada | Expiração |
| F8-E3 Online monitor | Sequential guardrails | Auto-pause |
| F8-E4 Canary | Gradual exposure | Error budget |
| F8-E5 Kill switches | Global/tenant/agent/model/tool/experiment | Drill |
| F8-E6 Learning | Candidate → approval → memory | Scope/TTL |

**Demo:** variante low-risk pré-aprovada inicia, guardrail sintético dispara, tráfego volta ao controle e incidente/evidence são gerados.

## Gates transversais

| Gate | Fases |
|---|---|
| Contratos e schemas | Todas |
| Tenant isolation | Desde F0 |
| Segurança e privacidade | Todas |
| Acessibilidade e performance | F2/F4/F5/F6 |
| Experiment integrity | F3 em diante |
| Evidence bundle | Todas |
| Rollback | Toda publicação |
| Aprovação humana | High/critical e domínios reservados |

## Política de sequenciamento

Não iniciar F4 ou F5 enquanto F2 não estiver em homologação estável. Não iniciar F6 sem páginas controle e conteúdo aprovado. Não iniciar F7 sem dados íntegros. Não iniciar F8 sem pelo menos um ciclo de shadow mode, drill de kill switch e assinatura dos owners.
