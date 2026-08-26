# Notas verificadas de pesquisa de mercado

## Fontes primárias consultadas

### Stack Overflow — 2025 Developer Survey, seção AI

URL: https://survey.stackoverflow.co/2025/ai

A pesquisa informa que **46% dos desenvolvedores desconfiam ativamente da precisão das ferramentas de IA**, enquanto **33% confiam** e somente **3% declaram confiança elevada**. Desenvolvedores experientes apresentam cautela ainda maior. A principal frustração é receber soluções “quase certas, mas não totalmente corretas” (**66%**); em seguida aparece o tempo maior para depurar código gerado por IA (**45,2%**). Outros sinais relevantes são perda de confiança na própria capacidade de resolver problemas (**20%**) e dificuldade de entender como ou por que o código funciona (**16,3%**). Em um futuro com IA mais avançada, **75,3%** ainda procurariam uma pessoa quando não confiassem na resposta, **61,7%** quando houvesse preocupações éticas ou de segurança e **61,3%** quando quisessem compreender plenamente o assunto.

Implicação para o funil: confiança verificável, explicabilidade, revisão, testes, segurança e aprendizado estruturado são dores comerciais centrais. O marketing não deve prometer “software perfeito em um prompt”; deve vender um caminho para sair do protótipo e chegar a um produto confiável.

### METR — Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity

URL: https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/

O ensaio controlado randomizado estudou 16 desenvolvedores experientes, 246 tarefas reais e repositórios grandes nos quais os participantes já trabalhavam há anos. No cenário estudado, o uso das ferramentas de IA do início de 2025 fez as tarefas levarem **19% mais tempo**, embora os participantes previssem ganho de velocidade de **24%** e, após a experiência, ainda acreditassem ter obtido ganho de **20%**. A própria METR delimita o resultado: ele não demonstra que IA reduz a produtividade da maioria dos desenvolvedores, nem que o resultado se aplica a outros domínios ou a ferramentas futuras.

Implicação para o funil: o segmento avançado não precisa de “mais geração”; precisa de contexto de repositório, avaliação de impacto, testes direcionados, métricas reais de lead time e prevenção de retrabalho. A oferta deve prometer desempenho mensurável e governado, não velocidade presumida.

## Hipóteses iniciais de dores prioritárias

| Segmento | Dor provável | Evidência inicial | Potencial de oferta |
|---|---|---|---|
| Iniciante não técnico | Consegue gerar uma demo, mas não sabe transformar em produto seguro, publicável e vendável | Baixa compreensão e necessidade de ajuda humana aparecem na pesquisa do Stack Overflow | Sistema guiado “da ideia ao primeiro SaaS confiável” |
| Builder intermediário | Fica preso no ciclo prompt–erro–correção, com contexto perdido e retrabalho | Soluções quase corretas e depuração demorada lideram as frustrações | Método operacional para estabilizar, testar e lançar aplicações |
| Profissional/time avançado | IA aumenta volume de código, mas pode reduzir velocidade líquida e elevar risco | Resultado controlado da METR e baixa confiança entre experientes | Camada de governança, avaliação, observabilidade e CI para código assistido por IA |

Estas hipóteses ainda precisam ser confrontadas com segurança, documentação de ferramentas e sinais de demanda antes da seleção final dos três funis.

### METR — atualização de fevereiro de 2026

URL: https://metr.org/blog/2026-02-24-uplift-update/

A METR declarou que o resultado do início de 2025 não representa mais adequadamente o efeito das ferramentas atuais. Nos dados brutos do experimento iniciado em agosto de 2025, houve algum sinal de ganho, mas a organização considerou a amostra enviesada e inadequada para uma estimativa confiável. Para participantes do estudo anterior, a estimativa foi de **18% de aceleração**, com intervalo de confiança entre **38% de aceleração e 9% de desaceleração**; para novos participantes, a estimativa foi de **4% de aceleração**, com intervalo entre **15% de aceleração e 9% de desaceleração**. A principal conclusão útil não é um percentual de velocidade, mas a necessidade de medir produtividade no contexto real de cada equipe.

Implicação para o funil: o posicionamento avançado deve prometer **instrumentação e prova de ganho**, não usar o estudo antigo como argumento de que IA necessariamente desacelera. O produto deve comparar lead time, retrabalho, defeitos e custo antes/depois no próprio ambiente do cliente.

### Cloud Security Alliance — Vibe Coding Security Crisis

URL: https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-generated-code-security-vibe-coding-202/

A nota técnica da Cloud Security Alliance, publicada em março de 2026, consolida pesquisas sobre segredos expostos, vulnerabilidades, dívida de SDLC e novos vetores específicos de agentes de código. Entre os números reportados, commits assistidos por IA apresentaram exposição de segredos de **3,2%**, contra **1,5%** no conjunto geral; o GitHub público registrou **28,65 milhões** de novos segredos hardcoded em 2025, aumento anual de **34%**. A nota também cita estudos nos quais código gerado por IA apresentou vulnerabilidades em **45%** das tarefas e pull requests com IA tiveram **2,74 vezes** mais problemas de segurança que PRs humanos, ressaltando que os resultados variam conforme metodologia e maturidade dos controles.

A fonte enfatiza que ferramentas de IA criam superfícies de ataque adicionais, como arquivos de regras manipulados, dependências alucinadas e vazamento de credenciais, e que controles tradicionais do SDLC precisam ser estendidos. Para este projeto, isso valida controles obrigatórios de secrets scanning, análise de dependências, SAST/DAST, revisão de regras de agente, isolamento de ferramentas e proibição de publicação autônoma de código sensível.

## Refinamento das dores

| Prioridade | Dor comercial validada | Segmento primário | Transformação vendável |
|---|---|---|---|
| 1 | “Consigo criar algo que funciona na tela, mas não sei se está seguro nem pronto para usuários reais.” | Iniciante/fundador não técnico | Da ideia ao MVP publicável, com caminho guiado, testes e proteção de credenciais |
| 2 | “Meu projeto virou uma sequência de correções; a IA perde contexto e cada ajuste quebra outra parte.” | Builder intermediário | Resgate e estabilização do projeto, com arquitetura, memória, testes e deploy repetível |
| 3 | “A equipe gera mais código, mas não consegue provar ganho líquido nem controlar risco.” | Profissionais e times | Governança de engenharia assistida por IA, com políticas, telemetria e ROI mensurável |

### Figma — indisponibilidade regional

URL tentada: https://www.figma.com/resource-library/how-to-build-an-app-with-ai/

A página não pôde ser consultada por restrição regional. Nenhuma afirmação será derivada do snippet de busca; a fonte foi descartada para fins probatórios.

### Chrono Innovation — After Vibe Coding: Prototype to Production

URL: https://www.chronoinnovation.com/resources/vibe-coding-gap/

A análise descreve uma lacuna recorrente entre uma interface demonstrável e um produto operável. Os problemas são organizados em autenticação incompleta, integridade de dados, tratamento de erros, desempenho sob carga, ausência de padrões arquiteturais, abstrações insuficientes, falta de testes, dívida técnica, desenho de schema, API, segurança e infraestrutura. Os sinais de limite incluem gastar mais tempo corrigindo regressões do que construindo, descobrir problemas estruturais com usuários reais, insegurança antes de mostrar o produto a investidores e alto tempo de onboarding para um desenvolvedor assumir o código.

A fonte é comercial e não deve ser usada para comprovar estatísticas de mercado; ela é útil como taxonomia prática das dores. A taxonomia é consistente com as evidências de confiança, depuração e segurança das fontes primárias consultadas.

## Jobs-to-be-Done consolidados

| Nível | Situação | Trabalho que a pessoa tenta realizar | Barreira dominante | Resultado desejado |
|---|---|---|---|---|
| Iniciante | Tem uma ideia ou protótipo visual | Publicar a primeira aplicação e conquistar usuários | Não sabe distinguir demo de produto, teme quebrar segurança, pagamentos ou dados | Lançar com um caminho guiado e evidências mínimas de confiabilidade |
| Intermediário | Já acumulou prompts, arquivos e correções | Recuperar controle do código e chegar a um release estável | Contexto perdido, regressões, dívida técnica, falta de testes e deploy frágil | Estabilizar sem recomeçar às cegas e voltar a evoluir com segurança |
| Avançado | Equipe já usa agentes e assistentes | Aumentar throughput líquido sem elevar risco e custo | Métricas superficiais, governança tardia, segredos e revisões manuais sobrecarregadas | Operar uma esteira assistida por IA com ROI, políticas, auditoria e rollback |

### Google e Kaggle — curso intensivo de agentes e vibe coding

URL: https://blog.google/innovation-and-ai/technology/developers-tools/kaggle-genai-intensive-course-vibe-coding-june-2026/

O Google informa que a primeira edição de seu curso intensivo de agentes alcançou **mais de 1,5 milhão de alunos** e que a edição de 2026 evoluiu para um programa de cinco dias sobre workflows de vibe coding, integração de ferramentas e APIs, desenho, construção e implantação de agentes robustos, com projeto final prático. Este é um sinal de demanda educacional amplo, embora não seja uma medida direta de intenção de compra.

Implicação para o funil: fundamentos genéricos de agentes já são oferecidos gratuitamente por uma marca global; portanto, uma oferta paga não deve competir apenas em conteúdo introdutório. O diferencial precisa ser **execução aplicada a um produto do aluno**, diagnóstico, templates operacionais, revisão, evidência de prontidão e acompanhamento até o lançamento.

### Replit Agent — posicionamento comercial atual

URL: https://replit.com/products/agent

A página posiciona o produto como agente para construir aplicações prontas para produção por chat, “como uma equipe de engenharia sob demanda”, sem exigir experiência em código. Os pilares da promessa incluem ir da ideia ao aplicativo, banco e autenticação integrados, integrações com terceiros, proteção de chaves, testes e correção em loop, agentes e automações e lançamento no mesmo ambiente. A prova combina logotipos, depoimentos e demonstração.

Implicação competitiva: “construa um app por conversa” e “da ideia ao lançamento” já são promessas saturadas por plataformas. As páginas deste projeto devem evitar competir pela ferramenta em si e vender uma camada de transformação que a ferramenta não resolve sozinha: **clareza de oferta, engenharia verificável, estabilização de ativos existentes, aquisição de clientes e governança mensurável**.

## Lacunas de posicionamento identificadas

| Promessa saturada no mercado | Risco de copiar | Espaço estratégico recomendado |
|---|---|---|
| “Crie qualquer app com uma frase” | Baixa credibilidade e diferenciação fraca | “Transforme uma ideia específica em um lançamento verificável, com critérios de prontidão claros” |
| “Não precisa saber programar” | Pode reforçar dependência e esconder risco | “Você não precisa virar engenheiro; precisa de um sistema que explique decisões e bloqueie riscos” |
| “Pronto para produção” sem definição | Termo amplo e contestável | Publicar checklist, evidências, limites, testes e o que continua exigindo revisão humana |
| “Agente corrige o próprio trabalho” | Autoavaliação pode mascarar falhas | Separar gerador, revisor, juiz, política e aprovação de produção |
| “10x mais rápido” | Alegação difícil de provar e dependente do contexto | Medir tempo líquido, retrabalho, defeitos e custo no projeto real do cliente |
