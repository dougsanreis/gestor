# 3. Banco de Dados

SQLite em `data/gestor.db` (configurável por `DB_PATH`). O schema é criado automaticamente por `src/db.js` com `CREATE TABLE IF NOT EXISTS`. Chaves estrangeiras ativas (`PRAGMA foreign_keys = ON`) e modo WAL.

## 3.1 Diagrama entidade-relacionamento
```
users 1───N sessions

clients 1───N campaigns 1───N metrics
```

## 3.2 Tabelas

### users
| Coluna | Tipo | Regras |
|---|---|---|
| id | INTEGER | PK autoincremento |
| name | TEXT | obrigatório |
| email | TEXT | único, sem diferenciar maiúsculas |
| password_hash | TEXT | formato `scrypt$<salt>$<hash>` |
| role | TEXT | `admin` \| `gestor` |
| created_at | TEXT | `datetime('now')` |

### sessions
| Coluna | Tipo | Regras |
|---|---|---|
| token | TEXT | PK, 64 caracteres hex aleatórios |
| user_id | INTEGER | FK → users, `ON DELETE CASCADE` |
| expires_at | TEXT | ISO 8601; sessões vencidas são limpas a cada login |

### clients
`id`, `name` (obrigatório), `company`, `email`, `phone`, `segment`, `created_at`.

### campaigns
| Coluna | Tipo | Regras |
|---|---|---|
| client_id | INTEGER | FK → clients, `ON DELETE CASCADE` |
| name | TEXT | obrigatório |
| platform | TEXT | `meta` \| `google` \| `tiktok` \| `linkedin` |
| objective | TEXT | `conversao` \| `trafego` \| `alcance` \| `leads` \| `engajamento` |
| status | TEXT | `rascunho` \| `ativa` \| `pausada` \| `encerrada` |
| daily_budget | REAL | ≥ 0 |
| start_date / end_date | TEXT | `AAAA-MM-DD`; término ≥ início (validado na API) |

### metrics
| Coluna | Tipo | Regras |
|---|---|---|
| campaign_id | INTEGER | FK → campaigns, `ON DELETE CASCADE` |
| date | TEXT | `AAAA-MM-DD` |
| impressions, clicks, conversions | INTEGER | ≥ 0; cliques ≤ impressões (API) |
| spend, revenue | REAL | ≥ 0 |
| — | UNIQUE | `(campaign_id, date)` → permite *upsert* |

Índices: `campaigns(client_id)`, `metrics(date)`, `sessions(user_id)`.

## 3.3 Consultas importantes
KPIs **nunca são armazenados**: são calculados a partir das somas (`SUM_COLUMNS` em `src/metrics.js`), assim nunca ficam inconsistentes.

```sql
-- Upsert de métrica diária
INSERT INTO metrics (campaign_id, date, impressions, clicks, spend, conversions, revenue)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (campaign_id, date) DO UPDATE SET
  impressions = excluded.impressions, clicks = excluded.clicks, spend = excluded.spend,
  conversions = excluded.conversions, revenue = excluded.revenue;

-- Campanhas com totais do período (LEFT JOIN mantém campanhas sem métricas)
SELECT c.*, SUM(m.spend) ... FROM campaigns c
LEFT JOIN metrics m ON m.campaign_id = c.id AND m.date BETWEEN ? AND ?
GROUP BY c.id;
```

Todas as consultas usam *prepared statements* com `?` — proteção contra SQL injection.

## 3.4 Dados de demonstração
`src/seed.js` cria 2 usuários, 4 clientes, 9 campanhas (todas as plataformas e status) e 60 dias de métricas geradas por um gerador pseudoaleatório com semente fixa (resultados idênticos para todos), relativas à data atual.

- Na **primeira execução** (`npm start`) o seed roda automaticamente.
- `npm run seed` **apaga e recria** o banco.
- Para inspecionar: `sqlite3 data/gestor.db` (se instalado) ou qualquer visualizador SQLite (ex.: DB Browser for SQLite).
