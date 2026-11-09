# 4. Referência da API REST

Base: `http://127.0.0.1:3000/api`. Formato JSON (UTF-8). Exceto onde indicado, toda rota exige o cabeçalho:
```
Authorization: Bearer <token>
```

## 4.1 Padrão de erros
```json
{ "error": "Dados inválidos", "details": { "email": "E-mail inválido" } }
```
| Status | Quando |
|---|---|
| 400 | JSON malformado, ID ou período inválido |
| 401 | Sem token, token inválido ou expirado; login incorreto |
| 403 | Perfil sem permissão (rotas de admin) |
| 404 | Recurso ou rota inexistente |
| 405 | Método não suportado na rota |
| 409 | E-mail de usuário duplicado |
| 413 | Corpo maior que 1 MB |
| 422 | Validação falhou (`details` por campo) |
| 500 | Erro inesperado (logado no terminal) |

Rotas com período aceitam `?from=AAAA-MM-DD&to=AAAA-MM-DD` (padrão: últimos 30 dias).

## 4.2 Sistema e autenticação
| Método | Rota | Auth | Descrição |
|---|---|---|---|
| GET | `/health` | pública | `{ status: "ok", time }` |
| POST | `/auth/login` | pública | corpo `{ email, password }` → `{ token, expires_at, user }` |
| POST | `/auth/logout` | sim | revoga o token → 204 |
| GET | `/auth/me` | sim | usuário logado |

## 4.3 Usuários (somente admin)
| Método | Rota | Corpo |
|---|---|---|
| GET | `/users` | — |
| POST | `/users` | `{ name*, email*, password* (≥6), role: admin\|gestor }` → 201 |
| DELETE | `/users/:id` | não pode excluir a si mesmo → 204 |

## 4.4 Clientes
| Método | Rota | Descrição |
|---|---|---|
| GET | `/clients?q=` | lista com `campaigns_count` e `active_campaigns` |
| GET | `/clients/:id` | detalhe |
| POST | `/clients` | `{ name*, company, email, phone, segment }` → 201 |
| PUT | `/clients/:id` | substitui todos os campos |
| DELETE | `/clients/:id` | apaga também campanhas e métricas → 204 |

## 4.5 Campanhas
| Método | Rota | Descrição |
|---|---|---|
| GET | `/campaigns?client_id=&platform=&status=&q=&from=&to=` | lista com objeto `kpis` do período |
| GET | `/campaigns/:id` | detalhe (inclui `client_name`) |
| POST | `/campaigns` | ver campos abaixo → 201 |
| PUT | `/campaigns/:id` | substitui todos os campos |
| PATCH | `/campaigns/:id/status` | `{ status }` |
| DELETE | `/campaigns/:id` | → 204 |

Campos: `client_id*` (cliente existente), `name*`, `platform*` (`meta|google|tiktok|linkedin`), `objective` (`conversao|trafego|alcance|leads|engajamento`, padrão `conversao`), `status` (`rascunho|ativa|pausada|encerrada`, padrão `rascunho`), `daily_budget` (aceita `"50,5"`), `start_date`, `end_date` (≥ início).

## 4.6 Métricas diárias
| Método | Rota | Descrição |
|---|---|---|
| GET | `/campaigns/:id/metrics?from=&to=` | `{ period, totals, daily[] }` com KPIs |
| POST | `/campaigns/:id/metrics` | `{ date*, impressions, clicks, spend, conversions, revenue }` — *upsert* por dia → 201 |
| DELETE | `/metrics/:id` | → 204 |

Regra: `clicks ≤ impressions`.

## 4.7 Dashboard e relatórios
| Método | Rota | Resposta |
|---|---|---|
| GET | `/dashboard?from=&to=` | `{ period, counts, totals, daily[], by_platform[], top_campaigns[] }` |
| GET | `/reports/campaigns.csv?from=&to=` | arquivo CSV (`;`, UTF-8 com BOM) |

Objeto de KPIs (presente em `totals`, `daily[]`, `kpis` etc.):
```json
{ "impressions": 10000, "clicks": 200, "spend": 100, "conversions": 10, "revenue": 500,
  "ctr": 2, "cpc": 0.5, "cpm": 10, "cpa": 10, "conversion_rate": 5, "roas": 5, "profit": 400 }
```

## 4.8 Exemplos com curl
```bash
TOKEN=$(curl -s -X POST localhost:3000/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@gestor.local","password":"admin123"}' | node -pe 'JSON.parse(require("fs").readFileSync(0)).token')

curl -s localhost:3000/api/dashboard -H "Authorization: Bearer $TOKEN"

curl -s -X POST localhost:3000/api/clients -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"name":"Novo Cliente","segment":"Varejo"}'

curl -s -X POST localhost:3000/api/campaigns/1/metrics -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"date":"2026-11-03","impressions":5000,"clicks":120,"spend":80,"conversions":4,"revenue":600}'
```

### ID no corpo de atualizações

Em `PUT /clients/:id`, `PUT /campaigns/:id` e `PATCH /campaigns/:id/status`,
o `id` no corpo é opcional; quando presente, deve ser número JSON inteiro,
positivo e seguro, idêntico ao ID da URL. Caso contrário, a API retorna 422
sem escrita. A autenticação continua obrigatória. A interface existente envia
o ID apenas na URL. `client_id` e `campaign_id` identificam relacionamentos;
`POST /campaigns/:id/metrics` mantém o contrato de upsert por campanha e data.
