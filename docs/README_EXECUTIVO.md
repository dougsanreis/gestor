# Vibe Funnel OS — Resumo executivo

**Autor:** Manus AI  
**Data:** 25 de agosto de 2026  
**Status:** especificação técnica pronta para implementação no Claude Code

## Decisão estratégica

O projeto não será uma fábrica autônoma de landing pages que altera produção com base em cliques. Ele será um **sistema de crescimento governado**: agentes pesquisam, diagnosticam, propõem, escrevem, implementam e avaliam; serviços determinísticos aplicam contratos e políticas; humanos aprovam domínios sensíveis; o runtime publica por canary, observa efeitos e reverte quando necessário.

A pesquisa mostra um mercado com adoção ampla e confiança limitada. Na pesquisa de 2025 do Stack Overflow, 84% dos respondentes usavam ou planejavam usar IA no desenvolvimento, mas 46% desconfiavam da precisão; 66% apontavam soluções “quase certas” como frustração e 45,2% relatavam depuração mais demorada.[1] A demanda educacional é grande, mas conteúdo introdutório é abundante: o Google informou mais de 1,5 milhão de participantes na edição anterior de sua iniciativa intensiva.[2] O diferencial, portanto, não é vender mais prompts. É transformar criação assistida por IA em **lançamento, recuperação e governança verificáveis**.

## Os três funis escolhidos

| Prioridade | Funil | Público | Dor principal | Oferta inicial | Transformação |
|---:|---|---|---|---|---|
| 1 | **Vibe Rescue** | Builder/founder com projeto ativo | Cada correção gera regressão e o deploy virou aposta | Diagnóstico + Sprint Rescue | Do caos para um release reproduzível |
| 2 | **AgentOps ROI** | CTO, engenharia, plataforma, segurança e agência | Uso de IA cresce sem prova de ganho líquido ou controle | Readiness + piloto limitado | De atividade dispersa para governança com ROI medido |
| 3 | **Launch OS** | Iniciante e founder não técnico | Acumula demos, mas não chega a produto publicável | Diagnóstico + Sprint Launch OS | Da ideia ao primeiro release e sinal de valor |

Cada funil possui página de vendas completa, jornada topo/meio/fundo, critérios de fit, ativos, eventos, métricas, guardrails e rotas para os outros funis. As páginas são distintas em conceito visual: **recuperação**, **controle** e **progressão**.

![Blueprint das páginas](docs/assets/blueprint_paginas.png)

## Arquitetura

O sistema é dividido em quatro planos:

| Plano | Responsabilidade |
|---|---|
| Experiência | Páginas, quizzes, formulários, checkout/agenda e personalização |
| Controle | API/BFF, workflow, policy, experimentos, consentimento e release |
| Inteligência | Orquestrador, Model Router, agentes, Tool Gateway, avaliações e memória |
| Evidência | Eventos, perfil/jornada, métricas, attribution, artifacts e observabilidade |

![Arquitetura do squad](docs/assets/arquitetura_squad.png)

A implementação começa como **modular monolith**, com interfaces para extrair componentes somente quando escala, isolamento ou confiabilidade justificarem. Claude Code será o ambiente de desenvolvimento e poderá usar subagentes, hooks e execução programática, mas o runtime de produção continuará em serviços persistentes e auditáveis. A documentação oficial do Claude Code confirma isolamento de contexto dos subagentes e a capacidade dos hooks de interceptar o ciclo de ferramentas; a especificação usa esses recursos como defesa adicional, não como única barreira.[3] [4]

## Squad

O pacote inclui 11 papéis operacionais:

| Grupo | Agentes |
|---|---|
| Estratégia | product-architect, funnel-strategist |
| Experiência | human-copywriter, experience-designer |
| Construção | implementation-engineer, analytics-engineer |
| Julgamento | experiment-analyst, independent-evaluator, security-privacy-reviewer |
| Governança | governor, release-engineer |

A segregação é obrigatória. Autor não avalia nem aprova o próprio artifact. O Governor não cria a evidência que usa. O Release Engineer não altera código nem ignora gates.

## Auto-otimização

O loop tem oito movimentos:

> Observar → Diagnosticar → Hipotetizar → Gerar candidato → Avaliar → Governar → Experimentar → Aprender.

Ele evolui por níveis. L0 lê; L1 propõe; L2 aplica apenas em branch/sandbox; L3 inicia ação low-risk previamente aprovada; L4 ajusta alocação somente entre variantes já aprovadas. A criação de nova variante online não pertence ao L4.

A função objetivo combina conversão qualificada, receita líquida e ativação, descontando reembolso, reclamação e custo de suporte. Guardrails são restrições duras: uma variante não pode “compensar” risco ou reclamação com mais conversão.

## Segurança, privacidade e operação

A orientação de segurança considera riscos específicos de aplicações agentic, como prompt injection indireta, abuso de ferramentas, excesso de autonomia, vazamento, supply chain, memória contaminada, cross-tenant e negação de serviço econômico. A OWASP mantém guia prático para o desenho e implantação segura dessas aplicações.[5]

A observabilidade segue atributos padronizados para GenAI e registra modelo, tokens, finish reason, tool call, duração, status e custo. Prompt e conteúdo integral ficam desligados por padrão porque podem ser volumosos e sensíveis.[6]

A personalização respeita finalidade, necessidade, transparência, segurança e direitos do titular. A LGPD prevê informação sobre critérios e procedimentos e direito de solicitar revisão em decisões exclusivamente automatizadas que afetem interesses.[7] A ANPD mantém orientação específica sobre cookies e proteção de dados.[8] O sistema, portanto, oferece consentimento por finalidade, opt-out, reason codes, fallback controle, export/delete workflows e bloqueio de sinais sensíveis.

## O pacote entregue

| Componente | Entrega |
|---|---|
| Estratégia | Mapa de mercado, matriz de seleção e três FunnelSpecs |
| Conversão | Três páginas de vendas completas, design system e personalização |
| Arquitetura | Runtime multiagente, planos, estados, contratos e antifalhas |
| Dados | Event model, métricas, experimentação e schema PostgreSQL de referência |
| Governança | Risk matrix, RACI, approvals, evidence e Claim Registry |
| Claude Code | CLAUDE.md, prompt mestre, 11 subagentes, 2 hooks e settings |
| Execução | Roadmap de 9 fases e backlog com 60+ tarefas |
| Contratos | OpenAPI e sete JSON Schemas |
| Operação | SLOs, incidentes, kill switches, backups e runbooks |
| Validação | Testes de hooks, validação de pack e manifest SHA-256 |

## Primeira implementação

O primeiro marco não é a página. É a criação de uma `Mission` validada, persistida, observável e governada. Em seguida, o runtime executa uma missão em sandbox com budgets, Tool Gateway, artifacts e avaliação. Só então o Vibe Rescue entra como primeiro vertical público.

A ordem evita construir três páginas bonitas sobre uma base incapaz de rastrear decisões, bloquear claims, pausar experimentos ou reverter releases.

## Próximo passo

Leia `README_INSTALACAO.md`, copie o pacote para a raiz de um repositório, execute `python3 scripts/validate_pack.py`, inicie o Claude Code com permissão padrão e cole o bloco de `PROMPT_MESTRE_CLAUDE_CODE.md`. O prompt já instrui o executor a começar pela primeira tarefa READY, produzir software e registrar evidências.

## Limites

A documentação não contém preços, garantias, depoimentos, cases, credenciais nem integrações reais. Esses itens foram deixados como dependências tipadas e fail-closed. A publicação em produção exige validação técnica, comercial, jurídica, de privacidade e segurança de acordo com o contexto da organização.

## Referências

[1]: https://survey.stackoverflow.co/2025/ai "Stack Overflow — 2025 Developer Survey: AI"
[2]: https://blog.google/innovation-and-ai/technology/developers-tools/kaggle-genai-intensive-course-vibe-coding-june-2026/ "Google — AI Agents Vibe Coding Course"
[3]: https://code.claude.com/docs/en/sub-agents "Claude Code Docs — Subagents"
[4]: https://code.claude.com/docs/en/hooks "Claude Code Docs — Hooks reference"
[5]: https://genai.owasp.org/resource/securing-agentic-applications-guide-1-0/ "OWASP — Securing Agentic Applications Guide 1.0"
[6]: https://opentelemetry.io/blog/2026/genai-observability/ "OpenTelemetry — GenAI Observability"
[7]: https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm "Presidência da República — LGPD"
[8]: https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia_orientativo_cookies_e_protecao_de_dados_pessoais "ANPD — Guia de Cookies e Proteção de Dados"
