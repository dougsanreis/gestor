# Síntese de requisitos extraídos

**Projeto:** Squad de agentes auto-otimizáveis para funis do nicho de vibe coding  
**Fonte primária:** histórico fornecido pelo usuário em `pasted_content.txt`  
**Status:** baseline de requisitos para arquitetura e documentação

## 1. Resultado de negócio

O sistema deve deixar de ser um gerador de artefatos isolados e atuar como uma fábrica operacional de funis de vendas. A primeira entrega precisa priorizar três páginas de vendas, cada uma ligada a uma dor relevante do mercado de vibe coding e a um funil completo. O objetivo central é aumentar conversão com experimentação governada, sem permitir que o sistema publique alterações baseadas apenas em opinião ou em sinais estatisticamente frágeis.

## 2. Públicos obrigatórios

O mapeamento deve cobrir iniciantes, intermediários e usuários avançados. A jornada deve distinguir topo, meio e fundo do funil, bem como estado de consciência, intenção, objeções, maturidade técnica, urgência e prontidão para compra. A personalização não pode usar atributos sensíveis nem criar promessas enganosas.

## 3. Entregáveis obrigatórios

| Área | Entrega mínima |
|---|---|
| Estratégia | Segmentação, dores priorizadas, ICPs, JTBDs, matriz de oferta e seleção de três funis |
| Páginas | Três especificações de páginas de vendas premium, com copy humanizada, estrutura, componentes, estados responsivos, acessibilidade e SEO |
| Funis | Jornada completa por funil, incluindo aquisição, captura, nutrição, venda, recuperação, onboarding, retenção e indicação |
| Agentes | Catálogo de agentes, contratos de entrada/saída, ferramentas permitidas, memória, handoffs, limites e critérios de aprovação |
| Auto-otimização | Coleta de sinais, hipóteses, experimentos, avaliação, promoção, rollback, aprendizado e replanejamento |
| Governança | Políticas, níveis de risco, revisão humana, quarentena, trilhas de auditoria, segregação de funções e kill switch |
| Engenharia | Arquitetura, serviços, eventos, APIs, schemas, modelo de dados, filas, idempotência, testes, CI/CD, observabilidade e SLOs |
| Claude Code | Estrutura do repositório, arquivos de instrução, contratos, prompts, comandos, fases de implementação e critérios de pronto |
| Documentação | Documento técnico principal, guia de implementação, especificações dos três funis, copy das páginas e material executivo |

## 4. Princípios preservados do histórico

A arquitetura deve aplicar **execução antes de complexidade**, **produto antes de infraestrutura ornamental**, **segurança por padrão**, **memória de erros**, **aprendizado derivado de execução real**, **governança por métricas**, **quarentena de ações arriscadas**, **testes seletivos antes de testes totais** e **entregas tangíveis**. A autonomia precisa ser limitada por políticas, orçamentos, aprovações e rollback automático.

## 5. Correções necessárias em relação às tentativas anteriores

| Fragilidade observada | Correção de projeto |
|---|---|
| Conceitos e prompts sem software operacional | Transformar cada requisito em contrato testável, interface, evento, schema e critério de aceite |
| Percentuais de maturidade não comprovados | Usar evidência verificável: testes, telemetria, artefatos assinados, deploys e SLOs |
| Scripts tolerando falhas com `set +e` | Aplicar fail-fast, erros tipados, códigos de saída, retries delimitados e compensação |
| Autonomia irrestrita | Adotar níveis de risco, sandbox, allowlists, aprovação humana e políticas como código |
| Métricas sem decisão global | Conectar telemetria a um motor de decisão com limites, significância, promoção e rollback |
| “Auto-otimização” por alteração direta | Separar descoberta, geração de hipótese, experimento, avaliação independente e promoção governada |
| Copy e design tratados apenas como geração | Versionar como ativos, validar por revisão editorial, acessibilidade, legalidade e experimentos controlados |
| Otimização local de conversão | Incluir qualidade do lead, receita, reembolso, churn, satisfação, reputação e margem como guardrails |
| Memória textual sem controle | Usar memória estruturada, proveniência, validade temporal, retenção e mecanismo de esquecimento |
| Ausência de definição da oferta | Tratar oferta, preço, prova e mecanismo como hipóteses explícitas antes de atribuir desempenho à página |

## 6. Requisitos não funcionais

O sistema precisa ser auditável, multi-tenant, seguro, reversível, observável, idempotente, resiliente a falhas parciais e econômico. Nenhuma alteração material de oferta, preço, depoimento, garantia, privacidade, checkout ou identidade visual poderá ser publicada autonomamente. Toda decisão deverá registrar contexto, evidência, versão do modelo, prompt, ferramentas utilizadas, custos, política aplicada e resultado.

## 7. Definição operacional de “à prova de falhas”

“À prova de falhas” não significa ausência absoluta de falhas. Significa que falhas previsíveis são prevenidas; falhas restantes são detectadas cedo, contidas, recuperáveis, rastreáveis e convertidas em aprendizado. O sistema deve preferir degradação segura a comportamento não controlado.

## 8. Premissas para a documentação

A documentação será pronta para implementação no Claude Code, mas manterá os componentes independentes do provedor de modelo. O baseline arquitetural deverá aceitar execução local para desenvolvimento e uma opção gerenciada para produção. Serão apresentadas pelo menos duas alternativas de implantação, com diferenças de custo operacional, complexidade e controle.

## 9. Questões tratadas como configuração, não bloqueio

Nome final da marca, oferta, ticket, garantia, ativos de prova, stack preferida, orçamento de mídia e canais de aquisição serão modelados como parâmetros configuráveis. A ausência desses dados não bloqueia a especificação; impede apenas a publicação comercial definitiva sem validação humana.

## 10. Critério de sucesso desta entrega

A entrega será considerada pronta quando um time técnico puder criar o repositório, executar a implementação por fases, levantar o sistema localmente, semear os três funis, renderizar as três páginas de vendas, simular eventos, executar testes, observar decisões de agentes e promover ou reverter variantes em ambiente de homologação sem depender de interpretação adicional do autor.
