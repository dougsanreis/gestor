# Notas verificadas — observabilidade e segurança de agentes

## OpenTelemetry GenAI

Fonte: https://opentelemetry.io/blog/2026/genai-observability/

As convenções semânticas de GenAI padronizam o registro de operações com atributos como `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` e `gen_ai.response.finish_reasons`. O conteúdo completo de prompts, respostas, chamadas de ferramenta e resultados pode ser registrado apenas quando habilitado, mas é volumoso e potencialmente sensível.

Aplicação no projeto: traces devem registrar modelo, uso, duração, finish reason, tool name, status, custo estimado, missão e artefato. Prompt e conteúdo integral ficarão desabilitados por padrão. Quando estritamente necessários para debugging, serão enviados a um cofre com retenção curta, acesso restrito e redaction.

## OWASP — Securing Agentic Applications Guide 1.0

Fonte: https://genai.owasp.org/resource/securing-agentic-applications-guide-1-0/

A OWASP apresenta o guia como orientação prática e acionável para projetar, desenvolver e implantar aplicações agentic com segurança, complementar ao documento de ameaças e mitigações de Agentic AI. A página consultada confirma escopo, publicação e acesso ao guia completo.

Aplicação no projeto: o threat model incluirá prompt injection direta e indireta, abuso de ferramentas, excesso de autonomia, vazamento de segredos e dados, supply chain de skills/MCPs/plugins, execução de código, identidade de agente, memória contaminada, escalada de privilégios, negação de serviço econômico e comprometimento de dependências. Os controles serão convertidos em policies, tool allowlists, isolamento, scanners, budgets, content provenance e revisão humana conforme risco.

## LGPD — texto oficial

Fonte: https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm

A LGPD protege liberdade, privacidade e livre desenvolvimento da personalidade; aplica-se a tratamento digital e define dado pessoal e sensível, controlador, operador e outras funções. Para este sistema, os princípios de finalidade, adequação, necessidade, livre acesso, qualidade, transparência, segurança, prevenção, não discriminação e responsabilização orientam a personalização. O artigo 20 estabelece direito de solicitar revisão de decisões tomadas unicamente com base em tratamento automatizado que afetem interesses e prevê informação clara sobre critérios e procedimentos, observados segredos comercial e industrial.

Aplicação: toda personalização relevante deve ter finalidade, base apropriada, minimização, reason codes, canal de revisão quando aplicável e fallback não personalizado. O sistema não deve usar dados sensíveis ou proxies para persuasão e deve registrar versões de decisão, fontes e critérios.

## ANPD — Guia de Cookies e Proteção de Dados Pessoais

Fonte: https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia_orientativo_cookies_e_protecao_de_dados_pessoais

A ANPD mantém guia específico sobre cookies e proteção de dados pessoais. A documentação final deve tratar cookies necessários separadamente de analytics, personalização e marketing, oferecer controles claros e permitir redefinição de preferências. Scripts não essenciais não serão carregados antes da decisão correspondente.
