# 1. Visão Geral do Sistema

## 1.1 O que é
O **Gestor de Anúncios** é um sistema web de demonstração, construído inteiramente com o **Claude Code**, para gestores de tráfego pago acompanharem clientes, campanhas e resultados de anúncios em **Meta Ads, Google Ads, TikTok Ads e LinkedIn Ads**.

Ele roda **localmente** (na máquina do aluno), sem nuvem, sem banco externo e **sem nenhuma dependência npm** — só o Node.js.

## 1.2 Objetivos didáticos
| Objetivo | Onde ver no código |
|---|---|
| API REST com autenticação | `src/app.js`, `src/routes/*` |
| Banco de dados relacional (SQL) | `src/db.js` |
| Regras de negócio isoladas e testáveis | `src/metrics.js`, `src/validation.js` |
| Segurança básica (hash de senha, XSS, CSP, path traversal) | `src/auth.js`, `public/app.js` (`esc`), `src/app.js` |
| Interface SPA sem framework | `public/` |
| Testes automatizados (unitários + integração) | `tests/` |

## 1.3 Funcionalidades
- **Login** com sessão por token (expira em 8h) e dois perfis: `admin` e `gestor`.
- **Dashboard**: investimento, receita, ROAS, conversões, CPA, cliques/CTR/CPC; gráfico diário de investimento × receita; investimento por plataforma; top 5 campanhas por lucro; filtro de período (7/14/30/60 dias).
- **Clientes**: cadastrar, editar, buscar, excluir (exclui campanhas em cascata).
- **Campanhas**: cadastro com plataforma, objetivo, status, orçamento diário e datas; filtros por cliente/plataforma/status/texto; ativar/pausar com um clique; KPIs do período por campanha.
- **Métricas diárias**: lançamento por dia (impressões, cliques, investimento, conversões, receita) com *upsert* — relançar o mesmo dia substitui o valor.
- **Relatório CSV** pronto para Excel (separador `;`, UTF-8 com BOM).
- **Usuários** (somente admin): listar, criar e excluir.
- Tema claro/escuro automático e layout responsivo.

## 1.4 Stack tecnológica
| Camada | Tecnologia | Por quê |
|---|---|---|
| Runtime | Node.js ≥ 22.13 | Já traz HTTP, crypto, SQLite e test runner nativos |
| Banco | SQLite via `node:sqlite` | Arquivo único, zero instalação |
| Backend | `node:http` + roteador próprio (~40 linhas) | Mostra o que frameworks fazem "por baixo" |
| Frontend | HTML + CSS + JavaScript puro | Sem build, sem CDN, funciona offline |
| Gráficos | SVG gerado em JS | Sem bibliotecas externas |
| Testes | `node:test` + `fetch` | Nativo |

## 1.5 Glossário de KPIs
| Sigla | Fórmula | Significado |
|---|---|---|
| CTR | cliques ÷ impressões × 100 | Taxa de cliques |
| CPC | investimento ÷ cliques | Custo por clique |
| CPM | investimento ÷ impressões × 1000 | Custo por mil impressões |
| CPA | investimento ÷ conversões | Custo por aquisição |
| Taxa de conversão | conversões ÷ cliques × 100 | |
| ROAS | receita ÷ investimento | Retorno sobre gasto com anúncios (>1 = lucro) |
| Lucro | receita − investimento | |

Divisões por zero retornam `0` (ver `computeKpis` em `src/metrics.js`).
