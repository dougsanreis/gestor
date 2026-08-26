# CurrentStateReport — Vibe Funnel OS

Exigido pelo `PROMPT_MESTRE_CLAUDE_CODE.md`, §2: quando já existe software, o
executor produz primeiro um relatório de estado baseado em evidência e
continua do primeiro gate não atendido.

- **Data:** 2026-08-25
- **Branch:** `claude/session-pw477k`
- **Comando de verificação:** `python3 scripts/gerar_evidencia.py VF-0000-FASE0`
- **Suíte:** 360 testes, 7,85 s
- **Evidência selada:** `docs/evidence/VF-0000-FASE0/manifest.json`

## Fase 0 — Fundação executável

O prompt mestre lista onze critérios de saída. Estado real de cada um:

| Critério de saída (§2) | Estado | Evidência |
|---|---|---|
| Monorepo TypeScript com `apps/web`, `apps/api`, `apps/worker` | **Divergente** | Decisão em `docs/adr/ADR-0001-stack.md` |
| Comandos reprodutíveis de dev, build, typecheck, lint e test | **Parcial** | `pytest` e `validate_pack.py` reproduzíveis; typecheck e lint não configurados |
| Contratos carregáveis e testes de schema | **Atendido** | `syra/vfos/contracts.py`; 7 contratos carregados e validados |
| Configuração tipada e validação de env sem segredo em repo | **Atendido** | `syra/vfos/policy.py` (`Policy`), redaction em `telemetry.py` |
| PostgreSQL local ou adapter de teste documentado | **Atendido com desvio** | `SqliteMissionRepository` + `MemoryMissionRepository` atrás da mesma porta |
| Health/readiness endpoints | **Atendido** | `GET /healthz`, `GET /readyz` em `syra/vfos/api.py` |
| OpenTelemetry inicial com redaction | **Parcial** | Spans com convenção de atributos e redaction por padrão; exporter OTLP não plugado |
| Policy engine determinístico inicial | **Atendido** | Matriz risco × autonomia, fail-closed |
| CI local equivalente ao remoto | **Não atendido** | Sem workflow de CI |
| Vertical slice: criar Mission → validar → persistir → emitir evento → consultar | **Atendido** | `test_slice_vertical_completo` |
| Evidence manifest e documentação atualizada | **Atendido** | `syra/vfos/evidence.py`, manifest selado com hash |

## Backlog VF-00xx

| ID | Tarefa | Estado | Onde |
|---|---|---|---|
| VF-0001 | Inicializar monorepo e comandos padrão | PARCIAL | `pyproject.toml`; falta lint/typecheck |
| VF-0002 | ADR da stack e fronteiras | **DONE** | `docs/adr/ADR-0001-stack.md` |
| VF-0003 | Configuração tipada | **DONE** | `syra/vfos/policy.py` |
| VF-0004 | Importar e validar JSON Schemas | **DONE** | `syra/vfos/contracts.py`, `jsonschema_lite.py` |
| VF-0005 | Mission aggregate | **DONE** | `syra/vfos/mission.py` — 13 estados, transições puras |
| VF-0006 | Repository port e memory adapter | **DONE** | `syra/vfos/store.py` — testes de contrato parametrizados |
| VF-0007 | Schema PostgreSQL e migrations | PARCIAL | DDL SQLite implementado; `reference_schema.sql` não migrado |
| VF-0008 | API POST/GET Mission | **DONE** | `syra/vfos/api.py` |
| VF-0009 | Outbox transacional | **DONE** | `store.py` — agregado e evento no mesmo commit |
| VF-0010 | Worker idempotente | **DONE** | `syra/vfos/worker.py` — reserva com dono, retry com teto |
| VF-0011 | Health e OpenTelemetry | PARCIAL | Endpoints e spans prontos; exporter pendente |
| VF-0012 | Policy de risco/autonomia | **DONE** | `syra/vfos/policy.py` |
| VF-0013 | CI e evidence manifest | PARCIAL | Manifest pronto; CI pendente |
| VF-0014 | Revisão independente F0 | BLOCKED | Depende de VF-0003–VF-0013 |
| VF-0015 | Security/privacy review F0 | BLOCKED | Idem |
| VF-0016 | Decisão de gate F0 | BLOCKED | Depende de VF-0014 e VF-0015 |

Antecipada da Fase 2, por ser o maior redutor de risco do projeto:

| VF-0203 | Claim Registry | **DONE** | `syra/vfos/claims.py` — fail-closed, com detecção |

## O que já existia antes do pacote

A SYRA, no mesmo repositório, com 185 testes. Não foi reescrita — foi reusada:

| Capacidade SYRA | Papel no Vibe Funnel OS |
|---|---|
| `CommandQuarantine` — 21 regras, score 0–100, alternativa segura | Passou a alimentar a recusa do `guard_pre_tool.py` |
| `ErrorMemory` — assinatura estável, recorrência = falha sistêmica | Base do `learning_candidate` da Fase 7 |
| Fábrica com sete portões executáveis | Modelo dos portões de missão |
| Squad de funil com intervalo de Wilson | Base do motor de experimentos da Fase 3 |
| Motor de copy que se recusa a inventar prova | Ancorado agora no Claim Registry contratual |

## Defeitos encontrados e corrigidos durante a implementação

Registrados porque um relatório de estado que só lista acertos não serve para
decidir nada.

| # | Defeito | Onde | Como apareceu |
|---|---|---|---|
| 1 | `INSERT OR IGNORE` engolia violação de `NOT NULL`: a missão commitava e o evento sumia | `store.py` | Teste de atomicidade com evento inválido |
| 2 | Falha de publicação marcava a chave de idempotência para sempre; o evento era descartado como duplicata na retentativa — perda silenciosa | `worker.py` | Publicador intermitente no teste |
| 3 | Adapter de memória não deduplicava por chave de idempotência, divergindo do SQLite | `store.py` | Teste de contrato parametrizado |
| 4 | Validador aceitava `2026-13-45T99:99:99Z` — forma válida, data inexistente | `jsonschema_lite.py` | Diferencial contra `jsonschema` |
| 5 | `shutdown` casava em qualquer posição, bloqueando `servidor.shutdown()` | `guard_pre_tool.py` | O hook bloqueou o teste da própria API |
| 6 | `curl … \| sudo sh` passava pelo padrão de download-and-execute | `guard_pre_tool.py` | Corpus de verdadeiros positivos |
| 7 | Literais com forma de segredo em arquivo de teste | `test_vfos_app.py` | `post_change_check.py` recusou, corretamente |

Os defeitos 1, 2 e 6 eram silenciosos: nenhum deles produzia erro visível.

## Próximo gate não atendido

**VF-0013 (CI) e VF-0001 (lint/typecheck).** São o que falta para VF-0014 e
VF-0015 saírem de BLOCKED e o gate da Fase 0 poder ser julgado.

Antes de qualquer página, na ordem do próprio roadmap:

1. Workflow de CI executando `pytest`, `validate_pack.py` e o corpus do hook.
2. `ruff` e `mypy` configurados, com o baseline registrado.
3. Revisão independente (VF-0014) e revisão de segurança/privacidade (VF-0015).
4. Decisão de gate F0 (VF-0016).

A Fase 1 — Tool Gateway, Model Router, budgets e cancelamento — só começa
depois disso.
