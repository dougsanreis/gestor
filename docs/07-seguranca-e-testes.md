# 7. Segurança, Qualidade e Testes

## 7.1 Controles de segurança implementados
| Ameaça | Controle | Arquivo |
|---|---|---|
| Vazamento de senhas | `scrypt` com salt aleatório de 16 bytes; comparação em tempo constante (`timingSafeEqual`) | `src/auth.js` |
| Sequestro de sessão | Token de 256 bits aleatório, expiração de 8h, revogação no logout | `src/auth.js` |
| SQL Injection | 100% *prepared statements* (`?`) | `src/routes/*` |
| XSS | Função `esc()` em toda interpolação + CSP sem `unsafe-inline` | `public/app.js`, `src/app.js` |
| Clickjacking | `X-Frame-Options: DENY` | `src/app.js` |
| Path traversal | Caminho resolvido precisa estar dentro de `public/` | `src/app.js` |
| CSV injection | Células iniciadas com `= + - @` recebem `'` | `src/routes/dashboard.js` |
| Abuso de payload | Corpo limitado a 1 MB | `src/http.js` |
| Escalada de privilégio | Rotas de usuários com `role: 'admin'` | `src/routes/users.js` |
| Exposição na rede | Escuta em `127.0.0.1` por padrão | `src/config.js` |

### Limitações conhecidas (sistema didático)
- Sem HTTPS (desnecessário em `127.0.0.1`; obrigatório se for publicado).
- Limitador de login em memória, por endereço IP direto: após cinco falhas em 60 segundos, responde 429 e Retry-After. Não usa X-Forwarded-For. Reinício ou múltiplos processos reiniciam/dividem os contadores; atrás de proxy, usuários podem compartilhar um limite. Não é um controle distribuído nem bloqueio de conta.
- Token em `localStorage` (em produção, preferir cookie `HttpOnly` + `SameSite`).
- Sem multi-tenant: todos os usuários veem todos os clientes.
- Senhas de demonstração conhecidas — troque-as antes de qualquer uso real.

## 7.2 Testes automatizados
```bash
npm test
```
| Arquivo | Tipo | Cobertura |
|---|---|---|
| `tests/unit.test.js` | Unitário | fórmulas de KPI, divisão por zero, validação, datas, período, hash de senha, CSV, roteador |
| `tests/api.test.js` | Integração | sobe o servidor real em porta aleatória com banco **em memória**: health, 401, login, CRUD de clientes, 422, JSON inválido, fluxo completo campanha→status→métricas→KPIs, upsert, cascata, dashboard, CSV, 403/409, logout, estáticos, CSP, path traversal, 404/405 |

Resultado esperado: `# tests 19 / # pass 19 / # fail 0`.

## 7.3 Teste ponta a ponta (manual ou Playwright)
O fluxo da interface foi validado em navegador real (Chromium via Playwright): login → dashboard → criar cliente (incluindo erro de validação) → criar campanha → lançar métricas → conferir ROAS → usuários → tema escuro → logout, sem erros de JavaScript nem violações de CSP. As capturas em `docs/img/` vêm dessa execução.
