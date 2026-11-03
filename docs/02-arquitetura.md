# 2. Arquitetura

## 2.1 Visão em camadas
```
┌──────────────────────────── Navegador ────────────────────────────┐
│  public/index.html + styles.css + app.js (SPA, rotas por #hash)   │
│  fetch('/api/...')  com  Authorization: Bearer <token>            │
└───────────────────────────────┬───────────────────────────────────┘
                                │ HTTP (127.0.0.1:3000)
┌───────────────────────────────▼───────────────────────────────────┐
│ src/app.js  (node:http)                                           │
│   ├─ /api/*  → Router → autenticação → permissão → leitura JSON   │
│   │            → handler (src/routes/*) → resposta JSON / 204     │
│   └─ demais  → arquivos estáticos de public/ (fallback SPA)       │
│ src/validation.js  src/metrics.js  src/auth.js  (regras puras)    │
└───────────────────────────────┬───────────────────────────────────┘
                                │ SQL (prepared statements)
┌───────────────────────────────▼───────────────────────────────────┐
│ src/db.js → SQLite (data/gestor.db)                               │
└───────────────────────────────────────────────────────────────────┘
```

## 2.2 Estrutura de pastas
```
gestor/
├── package.json           scripts start / dev / seed / test (sem dependências)
├── src/
│   ├── index.js           ponto de entrada: abre banco, seed inicial, sobe servidor
│   ├── config.js          PORT, HOST, DB_PATH (variáveis de ambiente)
│   ├── app.js             servidor HTTP, pipeline de requisição, estáticos
│   ├── router.js          roteador com parâmetros (:id)
│   ├── http.js            HttpError, readJson, sendJson
│   ├── auth.js            scrypt, sessões, autenticação Bearer
│   ├── validation.js      validação declarativa, datas, período
│   ├── metrics.js         fórmulas de KPIs
│   ├── db.js              schema SQL e transações
│   ├── seed.js            dados de demonstração determinísticos
│   └── routes/
│       ├── auth.js        login / logout / me
│       ├── users.js       gestão de usuários (admin)
│       ├── clients.js     CRUD de clientes
│       ├── campaigns.js   CRUD de campanhas + métricas diárias
│       └── dashboard.js   dashboard agregado + relatório CSV
├── public/                interface (index.html, app.js, styles.css, favicon.svg)
├── tests/                 unit.test.js, api.test.js
├── data/                  banco SQLite (criado na 1ª execução, ignorado no git)
└── docs/                  esta documentação
```

## 2.3 Ciclo de vida de uma requisição de API
1. `app.js` recebe a requisição e identifica que começa com `/api/`.
2. `router.match(method, path)` encontra a rota → `404` se não existe, `405` se o método não é aceito.
3. Se a rota é protegida (padrão), `authenticate()` valida o token Bearer na tabela `sessions` → `401`.
4. Se a rota exige papel (`role: 'admin'`), compara com o usuário → `403`.
5. Em `POST/PUT/PATCH`, lê o corpo JSON (limite 1 MB) → `400`/`413`.
6. O *handler* valida a entrada (`validate`) → `422` com erros por campo, aplica regras de negócio e executa SQL.
7. Retorno: objeto → JSON com `ctx.status` (200 ou 201); `undefined` → `204 No Content`.
8. Qualquer `HttpError` vira `{ "error": "...", "details": {...} }`; erros inesperados viram `500` e são logados.
9. Uma linha de log é impressa: `data MÉTODO caminho -> status (ms)`.

## 2.4 Frontend
- **Roteamento por hash**: `#/dashboard`, `#/clientes`, `#/campanhas`, `#/campanhas/:id`, `#/usuarios`, `#/login`.
- **Estado**: token salvo em `localStorage`; usuário carregado via `/api/auth/me`.
- **`api()`**: wrapper de `fetch` que injeta o token e, ao receber `401`, faz logout automático.
- **Segurança**: todo dado interpolado em HTML passa por `esc()`; a CSP proíbe scripts e estilos inline.
- **Componentes**: `formModal` (formulários com erros por campo vindos do 422), `confirmAction`, `toast`, `lineChart`/`barChart` (SVG).

## 2.5 Decisões de arquitetura (ADRs resumidos)
| Decisão | Alternativa descartada | Motivo |
|---|---|---|
| Zero dependências | Express, React, Chart.js | Instalação instantânea em sala; código 100% legível |
| SQLite embutido | PostgreSQL/MySQL | Nada para instalar; arquivo único |
| Token opaco em tabela | JWT | Logout real (revogação) e mais simples de explicar |
| `PUT` com substituição total | `PATCH` parcial genérico | Validação única por recurso; `PATCH` só para status |
| Upsert de métricas por (campanha, dia) | Vários lançamentos/dia | Reflete como as plataformas reportam dados |
| Seed determinístico | Dados aleatórios | Todos os alunos veem os mesmos números |
