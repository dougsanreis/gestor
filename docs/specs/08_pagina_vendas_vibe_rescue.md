# Página de vendas 01 — Vibe Rescue

**Funil:** resgate de projeto travado  
**Público:** builders intermediários, founders e pequenos times  
**Objetivo primário:** compra do Diagnóstico Rescue ou aplicação para a Sprint  
**Tom:** competente, humano, direto e sem julgamento  
**Conceito visual:** **sala de controle para recuperar um sistema em turbulência**

## 1. Direção criativa

A página deve transmitir alívio e precisão. Ela não pode parecer um template genérico de ferramenta de IA, nem usar excesso de robôs, neon ou linhas de código decorativas. O protagonista é o projeto do visitante recuperando estabilidade.

| Elemento | Especificação |
|---|---|
| Fundo | Obsidian `#090D14`, com painéis `#111824` e superfícies elevadas `#172131` |
| Primária | Cyan técnico `#37D7E8` para foco, status e CTA |
| Secundária | Verde recuperação `#49D69B` para aprovado/estável |
| Alerta | Âmbar `#F5B942`, nunca usado como pressão falsa |
| Texto | Branco frio `#F4F7FB`; secundário `#A9B5C5` |
| Tipografia display | Geist/Inter Tight, 700–800, tracking negativo discreto |
| Tipografia corpo | Inter/Geist, 400–500, line-height 1.55–1.7 |
| Grid | 12 colunas desktop, 8 tablet, 4 mobile; largura máxima 1240 px |
| Raio | 16 px em cards; 999 px apenas em badges |
| Ícones | Lineares, 1.5–2 px, sem ilustrações infantis |
| Movimento | Curto e funcional; respeitar `prefers-reduced-motion` |

A metáfora visual principal é um **release que sai do vermelho e volta ao verde**. A página pode usar uma faixa de execução com estados “baseline”, “teste”, “correção”, “release” e “observação”. Nenhum gráfico deve exibir números inventados.

## 2. SEO e compartilhamento

| Campo | Conteúdo recomendado |
|---|---|
| Title | Vibe Rescue — Recupere seu projeto sem mais ciclos de correção |
| Meta description | Diagnóstico técnico e sprint de estabilização para projetos criados com IA que entraram em loops de bugs, regressões e deploys frágeis. |
| H1 | Seu projeto não precisa de mais um prompt. Precisa voltar a ser previsível. |
| Slug | `/vibe-rescue` |
| Open Graph | Visual de um pipeline saindo de “regressão” para “release estável”, sem números de performance |
| Schema | `Service`, `FAQPage` e `BreadcrumbList`, somente com dados reais |

## 3. Copy completa da página

### Barra superior

**Seu projeto já está no ar?** Se existe risco de perda de dados, exposição de chave ou cobrança duplicada, pause alterações e solicite uma triagem de risco.

CTA discreto: **Solicitar triagem**

### Navegação

Logo: `{{BRAND_NAME}}`  
Links: Como funciona · O que analisamos · Entregas · Perguntas  
CTA: **Diagnosticar meu projeto**

---

## Seção 1 — Hero

Eyebrow:

**VIBE RESCUE · DIAGNÓSTICO E ESTABILIZAÇÃO**

Headline:

# Seu projeto não precisa de mais um prompt. Precisa voltar a ser previsível.

Subheadline:

Você já construiu mais do que parece. O problema é que cada ajuste começou a quebrar outra parte, o contexto se perdeu e publicar virou um risco. Nós mapeamos o que funciona, reproduzimos as falhas e transformamos o caos em um plano de resgate executável.

CTA primário:

**Diagnosticar meu projeto**

CTA secundário:

**Ver o Protocolo SAVE**

Microcopy do CTA:

Você começa pelos sintomas. Não precisa saber explicar a arquitetura nem entregar acesso ao repositório agora.

Bloco de confiança:

- **Sem julgamento do seu código.**
- **Sem reescrita automática.**
- **Sem publicação sem aprovação.**

Especificação visual: à esquerda, copy; à direita, um painel realista com quatro estados do protocolo. O painel deve exibir labels, não métricas falsas: `Scan concluído`, `Baseline criado`, `2 gates pendentes`, `Release em homologação`.

---

## Seção 2 — Reconhecimento da dor

Headline:

## Quando o projeto começa a lutar contra você

Body:

No começo, cada prompt parecia uma vitória. Uma tela aparecia, uma integração funcionava, uma ideia ficava concreta. Depois vieram os detalhes: um login que funciona só às vezes, uma alteração no dashboard que quebra o formulário, um deploy que passa localmente e falha quando encontra usuários reais.

Não é falta de esforço. E nem sempre é falta de capacidade da ferramenta. O que se perdeu foi a **estrutura que permite mudar sem destruir o que já funciona**.

Cards de sintomas:

| Título | Texto de interface |
|---|---|
| A correção volta como regressão | Você resolve o erro de hoje e reencontra outro que já tinha desaparecido. |
| A IA perde o contexto | Cada conversa recomeça a história e toma decisões diferentes sobre a mesma parte do sistema. |
| O deploy virou aposta | Você só descobre se funcionou depois de publicar. |
| Ninguém sabe o que é seguro manter | Reescrever tudo parece desperdício; continuar parece perigoso. |
| O projeto funciona apenas no caminho feliz | Auth, pagamentos, concorrência, rede ruim e dados inesperados revelam o que a demo escondia. |
| Você parou de construir | O tempo foi consumido por investigação, retrabalho e medo de quebrar mais. |

Fechamento:

**Se você reconheceu três ou mais sinais, o próximo passo não é acelerar. É recuperar controle.**

CTA contextual: **Quero saber o nível de risco**

---

## Seção 3 — Reframe

Headline:

## Mais geração não corrige ausência de baseline

Body:

Um agente pode produzir código rapidamente. Mas, se ninguém registrou o comportamento atual, definiu o que não pode quebrar e separou sintomas de causas, toda mudança vira uma nova hipótese jogada sobre o sistema.

É assim que nasce o ciclo:

> Prompt → patch → aparente melhora → regressão → novo prompt → contexto maior → menos certeza.

O Vibe Rescue interrompe esse ciclo antes de adicionar complexidade. Primeiro tornamos o problema reproduzível. Depois decidimos o que preservar, corrigir, isolar ou substituir. Só então mudamos o código.

Visual: diagrama circular do ciclo quebradiço transformando-se em fluxo linear `baseline → mudança → teste → decisão`.

---

## Seção 4 — Protocolo SAVE

Headline:

## Um resgate em quatro movimentos. Cada um deixa uma prova.

Introdução:

O Protocolo SAVE foi desenhado para evitar dois extremos: remendar indefinidamente ou jogar fora um projeto que ainda tem valor.

### S — Scan

**Nós levantamos o que existe antes de opinar sobre o que mudar.**

Mapeamos arquitetura, dependências, autenticação, banco, integrações, segredos, testes, pipeline e ambientes. O resultado é um inventário objetivo do sistema, não uma impressão.

Entrega visível: **Mapa de componentes e riscos**

### A — Assess

**Cada parte recebe uma decisão técnica e uma justificativa.**

Classificamos módulos em quatro caminhos: manter, corrigir, isolar ou substituir. A decisão considera risco, acoplamento, esforço, impacto e urgência.

Entrega visível: **Matriz keep / refactor / isolate / replace**

### V — Validate

**Antes de corrigir, reproduzimos. Antes de avançar, protegemos.**

Criamos testes de caracterização para preservar comportamentos importantes, reproduzimos falhas críticas e estabelecemos um baseline. Isso reduz a chance de uma correção criar outra regressão silenciosa.

Entrega visível: **Baseline executável e relatório de testes**

### E — Evolve

**A evolução acontece em incrementos pequenos, revisáveis e reversíveis.**

As mudanças são isoladas, avaliadas, publicadas em homologação e observadas. Cada gate deixa evidência. O release só avança com aprovação conforme o risco.

Entrega visível: **Release candidate, checklist e plano de continuidade**

CTA: **Aplicar o SAVE ao meu projeto**

---

## Seção 5 — O que analisamos

Headline:

## O que está por trás da sensação de “qualquer coisa pode quebrar”

Texto:

O diagnóstico não procura apenas bugs. Ele procura as condições que fazem bugs voltarem.

| Área | O que verificamos | O que você recebe |
|---|---|---|
| Arquitetura | Limites, acoplamento, duplicação e caminhos críticos | Mapa e decisões por módulo |
| Código | Erros, complexidade, padrões frágeis e inconsistência | Lista priorizada com evidência |
| Dados | Schema, validação, transação, migração e backup | Riscos de integridade e plano |
| Autenticação | Sessão, autorização, recuperação e abuso | Threat checklist e gaps |
| Integrações | Timeout, retry, idempotência e contratos | Matriz de falhas e fallback |
| Segurança | Segredos, dependências e superfície exposta | Relatório e ações críticas |
| Testes | Cobertura de comportamento e regressão | Pirâmide mínima de proteção |
| Deploy | Build, ambiente, config, logs e rollback | Caminho reproduzível de release |
| Observabilidade | Logs, métricas, alertas e contexto | Plano de diagnóstico contínuo |

Nota honesta:

O diagnóstico identifica e prioriza. Ele não transforma automaticamente todo passivo em escopo fechado. Você recebe clareza suficiente para decidir o que deve ser corrigido agora e o que pode esperar.

---

## Seção 6 — A decisão que ninguém deveria tomar no escuro

Headline:

## Manter, refatorar ou reescrever?

Body:

“Reescreve tudo” pode ser uma conclusão preguiçosa. “Dá para consertar” também. A decisão correta depende do comportamento que precisa ser preservado, do custo de mudança, do risco e do valor que já existe.

Tabela de decisão:

| Situação | Direção provável | O que precisa ser verdade |
|---|---|---|
| Fluxo gera valor e está isolado | Manter | Testes preservam comportamento |
| Estrutura é confusa, mas comportamento é recuperável | Refatorar | Mudanças podem ser incrementais |
| Módulo compromete o restante | Isolar | Contrato entre partes é definido |
| Segurança ou arquitetura inviabilizam evolução | Substituir | Migração e rollback são planejados |

Callout:

> Você não compra uma resposta pronta. Compra um processo que torna a resposta defensável.

---

## Seção 7 — Como começa

Headline:

## Primeiro, o diagnóstico. Depois, uma decisão de verdade.

### Etapa 1 — Conte os sintomas

Um formulário curto registra o que está acontecendo, onde o projeto roda e qual impacto você já sente.

### Etapa 2 — Defina o acesso

Se houver fit, você escolhe o escopo mínimo de acesso. Projetos sensíveis podem exigir acordo e fluxo específico antes de qualquer análise.

### Etapa 3 — Receba o mapa

Você recebe achados priorizados, evidências, riscos, decisão por módulo e plano de ação. O relatório separa urgente, importante e desejável.

### Etapa 4 — Escolha o caminho

Você pode executar o plano com seu time, aplicar para a Sprint Rescue ou interromper sem compromisso adicional.

CTA: **Começar pelo diagnóstico**

Microcopy: `{{DIAGNOSTIC_PRICE_OR_APPROVED_COPY}}`. Preço, prazo e disponibilidade devem vir do catálogo aprovado, nunca do modelo de geração.

---

## Seção 8 — Entregas

Headline:

## O que fica com você

| Entrega | Por que importa |
|---|---|
| Mapa do sistema | Reduz dependência de memória e conversas antigas |
| Registro de riscos | Mostra o que pode gerar perda, incidente ou bloqueio |
| Matriz de decisão | Evita tratar todo arquivo da mesma forma |
| Baseline de comportamento | Define o que não pode quebrar |
| Backlog priorizado | Transforma ansiedade em ordem de execução |
| Plano de release | Mostra como validar, publicar e voltar atrás |
| Documento para leigos | Permite que você entenda a decisão sem traduzir engenharia sozinho |
| Evidence bundle | Reúne testes, relatórios e versões que sustentam a recomendação |

---

## Seção 9 — Prova sem teatro

Headline:

## Você não precisa confiar em uma promessa. Precisa enxergar o processo.

Body:

Esta seção deve mostrar três tipos de prova, somente quando disponíveis e autorizados: um relatório anonimizado, um fluxo de testes antes/depois e um caso com contexto suficiente para não parecer universal.

Placeholder obrigatório:

`{{APPROVED_CASE_STUDY}}`

Formato do caso:

- Contexto inicial real.
- Risco principal identificado.
- O que foi preservado, corrigido ou substituído.
- Evidência do release.
- Resultado observado e janela.
- Limitações e o que não foi resolvido.

Nunca usar depoimento inventado, número sem fonte, logotipo sem licença ou “mais de X projetos” sem registro verificável.

---

## Seção 10 — Oferta

Headline:

## Escolha o nível de ajuda que o projeto precisa agora

### Diagnóstico Rescue

Para quem precisa sair da incerteza.

Inclui mapa, riscos, baseline possível, matriz de decisão e plano priorizado.

CTA: **Quero o diagnóstico**

Preço: `{{APPROVED_DIAGNOSTIC_PRICE}}`

### Sprint Rescue

Para quem já tem urgência, acesso ao repositório e quer executar o plano com acompanhamento.

Inclui diagnóstico, estabilização do escopo aprovado, testes, pipeline, homologação e release assistido.

CTA: **Aplicar para a Sprint**

Preço: **sob escopo aprovado**, sem âncora falsa.

### Rescue Care

Para quem quer manter a estabilidade e evoluir sem voltar ao ciclo anterior.

Inclui monitoramento, triagem, manutenção e revisão de mudanças conforme contrato.

CTA: **Ver continuidade**

---

## Seção 11 — Para quem é e não é

### É para você se

Você já tem um repositório ou aplicação, consegue descrever sintomas e aceita que o diagnóstico pode recomendar manter, refatorar, isolar ou substituir partes diferentes.

### Não é o caminho certo se

Você ainda tem somente uma ideia, quer publicar uma aplicação sensível sem revisão, espera garantia de zero bugs ou quer que qualquer ação seja executada sem aprovação. Nesses casos, a página deve sugerir Launch OS, avaliação especializada ou pausa segura.

---

## Seção 12 — FAQ

### Vocês vão mandar reescrever tudo?

Não. Reescrever é uma opção de último caso para partes cuja estrutura, risco ou custo de evolução tornem a substituição mais racional. A recomendação vem acompanhada por critérios e evidência.

### Preciso entender programação?

Não para começar. O relatório terá uma camada técnica e uma camada em linguagem direta. Você precisa entender o impacto e a decisão; os detalhes de implementação ficam disponíveis para quem vai executar.

### Preciso dar acesso ao meu repositório agora?

Não. O primeiro passo registra sintomas e contexto. Acesso só é solicitado depois de escopo, consentimento e regras de retenção definidos.

### Meu código será usado para treinar modelos?

A resposta exibida deve refletir exatamente a política, o provedor e o contrato vigentes: `{{APPROVED_DATA_USAGE_POLICY}}`. Nunca gerar uma garantia não confirmada.

### Vocês publicam mudanças diretamente?

Não sem o fluxo de aprovação aplicável. Mudanças são isoladas, testadas e preparadas em homologação. A publicação depende do risco e do contrato.

### E se o projeto não tiver testes?

Isso é comum. O diagnóstico identifica comportamentos críticos e propõe testes de caracterização para criar um baseline antes de mudanças relevantes.

### O diagnóstico já corrige tudo?

Não. Ele organiza o problema e pode incluir correções de verificação previamente definidas, mas a estabilização é um escopo separado. A página deve mostrar o limite com clareza.

### O que acontece se surgir um risco crítico?

Você recebe um alerta prioritário com ação de contenção recomendada. Qualquer operação que possa afetar produção ou dados exige autorização conforme o plano de resposta.

---

## Seção 13 — CTA final

Headline:

# Você não precisa abandonar o que construiu. Precisa descobrir o que merece ser salvo.

Body:

Comece pelos sintomas. Em poucos minutos, o sistema organiza o contexto e mostra qual é o próximo passo seguro para avaliar seu projeto.

CTA primário: **Diagnosticar meu projeto**

CTA secundário: **Tenho um risco urgente**

Microcopy:

Sem acesso automático. Sem mudança em produção. Sem pressão para contratar uma sprint.

---

## Rodapé

Links obrigatórios: Termos · Privacidade · Política de cookies · Segurança · Contato · Status  
Texto de responsabilidade: resultados dependem de escopo, estado do projeto, acesso, riscos e capacidade de implementação. Nenhuma página deve prometer ausência absoluta de bugs ou segurança total.

## 4. Comportamento responsivo

| Faixa | Layout | Regras |
|---|---|---|
| ≥1280 px | 12 colunas, hero 6/6 | Sticky CTA discreto após 35% de scroll |
| 768–1279 px | 8 colunas | Painel do hero abaixo da copy em telas estreitas |
| <768 px | 4 colunas | Uma coluna, CTA full-width, tabelas viram cards acessíveis |
| <390 px | 4 colunas compactas | Headline reduzida sem perder contraste; nada de carrossel obrigatório |

O CTA sticky deve desaparecer quando o CTA principal ou o checkout estiver visível. Não bloquear conteúdo com banners. FAQs usam `<details>` acessível ou componente equivalente com foco visível.

## 5. Personalização aprovada

| Estado | Headline alternativa | CTA | Limite |
|---|---|---|---|
| Tráfego de conteúdo sobre regressão | “Cada correção cria outra? Pare o ciclo antes do próximo deploy.” | Mapear regressões | Sem afirmar que o projeto está quebrado |
| Tráfego de conteúdo sobre segurança | “Seu app funciona. Agora precisamos saber se ele está exposto.” | Fazer triagem de risco | Não usar medo exagerado |
| Retorno após quiz de alto risco | “Seu diagnóstico apontou sinais que merecem revisão.” | Continuar diagnóstico | Exibir reason codes compreensíveis |
| Projeto sem repositório | “Talvez você ainda não precise de resgate.” | Ver Launch OS | Não empurrar oferta errada |
| Time com múltiplos repositórios | “O problema pode não estar em um projeto, mas no sistema de entrega.” | Ver AgentOps ROI | Pedir confirmação antes de redirecionar |

## 6. Eventos

| Evento | Quando dispara | Propriedades mínimas |
|---|---|---|
| `vr_page_viewed` | Pageview válido | page_version, variant_id, consent_state |
| `vr_symptom_engaged` | Usuário interage com sintomas | symptom_id |
| `vr_protocol_viewed` | 50% da seção SAVE visível | protocol_version |
| `vr_cta_clicked` | Clique em CTA | cta_id, section_id |
| `vr_assessment_started` | Primeiro campo válido | source, page_variant |
| `vr_assessment_completed` | Resultado exibido | risk_band, route_recommendation |
| `vr_checkout_started` | Checkout inicia | offer_id, price_version |
| `vr_purchase_completed` | Confirmação verificada server-side | order_id, offer_id |
| `vr_application_submitted` | Aplicação enviada | fit_band, no_sensitive_answers |

Nenhum evento deve enviar código-fonte, segredo, descrição livre completa ou PII em parâmetros de analytics.

## 7. Critérios de aceite

| Gate | Critério |
|---|---|
| Copy | Nenhum claim sem prova, nenhum prazo/escassez não comprovado, leitura humana aprovada |
| UX | Fluxo principal completo por teclado, foco visível e estados de erro claros |
| Performance | LCP e peso de assets dentro do orçamento definido |
| Tracking | Eventos validados em ambiente de teste e sem PII |
| Segurança | CSP, headers, dependências e formulários verificados |
| Privacidade | Consentimento, finalidade, retenção e acesso descritos |
| SEO | Metadados, headings, canonical e structured data válidos |
| Release | Feature flag, canary, synthetic checks e rollback testado |
