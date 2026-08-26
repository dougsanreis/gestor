# RACI, autonomia e gates de decisão

## 1. Autoridade por papel

| Capacidade | Estrategista | Copy/UX | Implementador | Analytics | Avaliador | Segurança/Privacidade | Governor | Release | Humano owner |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Criar hipótese | R | C | I | C | I | C | A | I | I |
| Criar copy/UX candidata | C | R | I | I | I | C | A | I | I |
| Alterar código | I | C | R | C | I | C | A | I | I |
| Definir evento/métrica | C | I | C | R | C | C | A | I | I |
| Avaliar artefato | I | I | I | C | R | C | A | I | I |
| Security/privacy review | I | I | C | C | C | R | A | I | C |
| Aprovar experimento low-risk | C | I | I | C | C | C | R/A | I | I |
| Aprovar experimento high-risk | C | I | I | C | C | R | C | I | A |
| Alterar preço/garantia/termo | C | C | I | I | I | C | C | I | R/A |
| Promover homologação | I | I | I | I | C | C | A | R | I |
| Promover produção | I | I | I | I | C | C | C | R | A |
| Acionar rollback | I | I | I | C | I | C | A | R | A em critical |
| Promover aprendizado global | C | C | I | C | R | C | C | I | A |

**Legenda:** R = executa; A = responde/aprova; C = consultado; I = informado.

## 2. Segregação obrigatória

O mesmo `actor_id` ou `agent_run_id` não pode preencher simultaneamente os papéis de autor e avaliador do mesmo artifact. O implementador não assina GovernanceDecision nem ReleaseApproval do próprio commit. A aprovação humana deve ser autenticada por identidade externa ao modelo e vinculada ao hash do subject.

| Invariante | Enforce em |
|---|---|
| `artifact.generator.run_id != evaluation.evaluator_run_id` | banco + domínio |
| `commit_author != release_approver` para risco high/critical | release policy |
| policy bundle não é alterado pelo job que avalia | IAM + repository ownership |
| ExperimentSpec não muda após RUNNING | domínio + banco |
| Approval referencia subject hash | contrato + policy |
| Approval expirada não autoriza ação | policy engine |
| Evidence revogada invalida claims dependentes | content eligibility |

## 3. Níveis de autonomia

| Nível | Sistema pode | Sistema não pode | Exemplo |
|---|---|---|---|
| L0 | Ler e explicar | Criar ou alterar | Diagnóstico do funil |
| L1 | Propor artifact | Aplicar mudança | Variante de headline em draft |
| L2 | Aplicar em branch/worktree/sandbox | Publicar ou iniciar experimento | Implementar página em preview |
| L3 | Iniciar ação low-risk pré-aprovada | Alterar domínios reservados | Abrir experimento de ordem de FAQ |
| L4 | Ajustar alocação entre variantes aprovadas | Gerar nova variante online | Bandit entre módulos já aprovados |

L4 nunca significa acesso irrestrito. O envelope inclui tenant, funil, módulo, variantes, janela, budget, volume, guardrails, modelos, ferramentas, dados e kill switch.

## 4. Matriz de risco

| Classe | Exemplos | Gate mínimo | Fallback |
|---|---|---|---|
| LOW | Ordem de FAQ, espaçamento, label sem claim | Tests + evaluator + Governor | Controle |
| MEDIUM | Hero aprovado, assessment wording, coleta nova não sensível | Tests + privacy/claim checks + Governor | Controle |
| HIGH | Oferta, segmentação, nova integração, comportamento de checkout | Reviews independentes + humano owner | Bloqueio |
| CRITICAL | Pagamento, produção, dados sensíveis, auth, legal, cross-tenant | Dois owners aplicáveis + security/privacy + release drill | Deny/rollback |

## 5. Domínios reservados

Preço, desconto, garantia, escassez, termos, privacidade, base legal, exclusão de dados, pagamentos, reembolso, produção crítica, segredo, identidade, mudança de policy, decisão sobre dado sensível e comunicação de incidente nunca entram em L3/L4 sem aprovação humana específica.

## 6. Gates por artifact

| Artifact | Gates obrigatórios |
|---|---|
| Copy bundle | OfferSpec, Claim Registry, editorial rubric, evaluator |
| UX spec | Accessibility, privacy, dark-pattern review |
| Source code | typecheck, lint, unit, contract, integration, security |
| Metric definition | owner, formula, grain, source, quality, version |
| ExperimentSpec | analyst, data integrity plan, policy, approval |
| Security report | independent reviewer, remediation owners |
| Release manifest | CI, scans, evidence, approvals, flag, rollback |
| Learning candidate | multiple evidence, scope, TTL, Governor/human by risk |

## 7. Decision record

Toda decisão registra:

```json
{
  "subject_id": "...",
  "subject_hash": "sha256:...",
  "policy_version": "...",
  "risk_class": "HIGH",
  "decision": "REQUIRE_APPROVAL",
  "reason_codes": ["HUMAN_OWNER_REQUIRED"],
  "evidence_ids": ["..."],
  "required_approvals": ["marketing_owner", "security_owner"],
  "issued_at": "...",
  "expires_at": "..."
}
```

Se o subject muda, a decisão não acompanha automaticamente. Um novo hash exige nova avaliação e nova decisão.

## 8. Gate de aprendizado

Um `LearningCandidate` nasce com escopo mínimo. Ele só sobe de Mission para Funnel, Tenant ou Global quando há evidência repetida, ausência de contradição material, avaliação independente, TTL e decisão aprovada. Memória global não é log de tudo; é um conjunto pequeno de regras versionadas e reversíveis.
