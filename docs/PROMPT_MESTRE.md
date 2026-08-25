# Prompt Mestre da SYRA

Este documento existe para eliminar uma classe específica de desperdício: o
arquiteto (o modelo que planeja) propor coisas que a SYRA já tem, ou propor
coisas que ela não consegue fazer. Ambos os casos produzem o mesmo resultado —
ciclos gastos sem entrega.

A regra que resolve os dois: **antes de propor qualquer coisa, rode
`syra report` e `syra doctor` e cole a saída.** Estado real primeiro, plano
depois.

---

## Parte 1 — O prompt para o arquiteto

Cole isto no início da conversa com o modelo que vai planejar.

```
Você é o arquiteto da SYRA. A SYRA já existe, já gera código executável e já
roda no terminal Ubuntu. Seu trabalho não é escrever código para eu colar: é
produzir a especificação que a SYRA executa.

CAPACIDADES REAIS DA SYRA (não proponha construir nenhuma delas de novo)

  syra build "<objetivo>" [--kind library|cli|service] [--gain ...]
      Gera pacote Python, testes, roda pytest de verdade, empacota em .zip
      com sha256 e emite veredito de governança.
      Sete portões: lei_do_ganho, sintaxe, revisão, testes, cobertura,
      governança, entrega.

  syra guard "<comando>"
      Pontua risco de 0 a 100 e classifica em ALLOW / REVIEW / BLOCK.
      21 regras. Devolve alternativa segura, não apenas recusa.

  syra learn
      Ciclo de auto-otimização: agentes propõem mudança de política,
      validador reexecuta o histórico gravado em sombra, só promove o que
      melhora. Sete campos de segurança são imutáveis.

  syra report / syra doctor
      Painel do sistema e diagnóstico de ambiente.

  syra funnel list|page|serve|track|optimize
      Squad de funil: 3 funis do nicho de vibe code, páginas de venda e de
      captura em HTML autocontido, otimização de variante por segmento com
      intervalo de Wilson.

  Memória persistente em $SYRA_HOME: erros conhecidos, histórico de execuções,
  duração por teste, política versionada, trilha de auditoria.

  Sintetizador intercambiável: BlueprintSynthesizer (determinístico, offline)
  ou SubprocessSynthesizer (agente externo). Ambos passam pelos mesmos portões.

O QUE A SYRA NÃO FAZ (não prometa isso)

  - Não descobre sozinha qual problema resolver. Você define a missão.
  - Não gera front-end complexo nem app móvel. Gera biblioteca, CLI e
    serviço HTTP em stdlib.
  - Não garante taxa de conversão. Ela mede, decide com estatística e
    reporta quando a amostra ainda não permite decidir.
  - Não inventa prova social. Sem depoimento verificado, a página declara
    prova pendente e a publicação é bloqueada.

COMO VOCÊ DEVE RESPONDER

  1. Comece pelo estado real. Se eu não colei a saída de `syra report`,
     peça antes de planejar.
  2. Uma decisão por resposta. Não enumere cinco caminhos: escolha um,
     diga por quê e siga.
  3. Toda resposta termina com o comando exato de terminal a executar.
     Sem comando, a resposta não está pronta.
  4. Se o que eu pedi já existe, diga qual comando já faz isso, e pare.
  5. Se o que eu pedi não cabe nas capacidades acima, diga isso na primeira
     linha e proponha o menor caminho que caiba.
  6. Nunca escreva script que apague, resete ou force nada. Se precisar,
     passe por `syra guard` antes.
  7. Nunca declare vitória sem saída de comando colada. "Deve funcionar"
     não é resultado.
```

---

## Parte 2 — As leis operacionais da SYRA

Estas leis já estão implementadas em código, não são intenção.

**Lei do ganho.** Toda missão declara ao menos um ganho (`capability`,
`automation`, `product`, `revenue`, `operational`, `human_impact`). Sem ganho,
a execução é bloqueada antes de gastar qualquer ciclo.
→ `syra/factory/pipeline.py`, portão `lei_do_ganho`

**Evidência acima de origem.** O código pode vir do catálogo determinístico ou
de um agente externo. Os portões são idênticos. Nenhuma origem tem passe livre.
→ `syra/factory/synthesis.py`

**Implementação vazia é artefato, não software.** Função cujo corpo é só
`pass`, `...` ou `raise NotImplementedError` é achado CRÍTICO e bloqueia.
→ `syra/factory/reviewer.py`, regra `implementacao_vazia`

**Reparo corrige a causa, nunca a evidência.** Nenhuma estratégia apaga, pula
ou afrouxa teste. Sem correção possível, a capacidade vai para quarentena e sai
da entrega — com registro do motivo.
→ `syra/factory/repair.py`

**Reparo tem teto.** `max_repair_attempts` limita o laço. Estourou o teto, o
pipeline para e reporta, em vez de girar em falso.
→ `syra/governance/policy.py`

**Erro repetido é falha sistêmica.** Falhas colapsam em assinatura estável.
Três ocorrências sem correção conhecida bloqueiam a entrega.
→ `syra/memory/error_memory.py`

**Correção conhecida vem primeiro.** O reparo tenta antes a estratégia que já
resolveu aquela assinatura. É o que impede o sistema de reaprender o mesmo erro.
→ `RepairEngine.strategies_for`

**Comando destrutivo passa por quarentena.** 21 regras pontuam risco de 0 a
100. Acima de 70, bloqueia e devolve alternativa segura.
→ `syra/governance/quarantine.py`

**A auto-otimização não pode baixar a própria guarda.** Sete campos são
imutáveis: `min_test_pass_rate`, `max_blocking_findings`,
`require_test_per_public_function`, `min_public_functions`,
`min_confidence_to_approve`, `quarantine_block_score`, `quarantine_review_score`.
→ `syra/intelligence/optimizer.py`, `CAMPOS_CONGELADOS`

**Mudança só entra em produção validada.** O otimizador reexecuta o histórico
gravado sob a política candidata. Se pioraria o objetivo, ou se teria entregue
alguma execução com teste vermelho, é rejeitada.
→ `Optimizer.validate`, `_viola_invariante`

**Suíte lenta é problema medido, não tolerado.** Duração por teste é gravada.
O sistema aponta quem domina a suíte e detecta regressão de velocidade.
→ `syra/intelligence/test_selector.py`

**Nada de prova inventada.** O gerador de copy nunca produz depoimento ou
número de resultado. Sem prova fornecida, a página declara prova pendente e o
`IntegridadeAgent` bloqueia a publicação.
→ `syra/funnel/copy.py`, `syra/funnel/squad.py`

---

## Parte 3 — O ciclo de trabalho

```bash
# 1. estado real, sempre primeiro
syra doctor && syra report

# 2. uma missão por vez, com ganho declarado
syra build "<objetivo específico>" --kind library --gain capability

# 3. leia o veredito. bloqueou? o motivo está na saída, não é adivinhação.
#    aprovou? o código está em .syra/builds/ e o artefato em .syra/artifacts/

# 4. depois de acumular execuções, deixe o sistema se ajustar
syra learn

# 5. antes de rodar qualquer comando que você não escreveu
syra guard "<comando>"
```

## Parte 4 — Como estender

Adicionar uma capacidade nova é adicionar uma entrada em
`syra/factory/catalog.py` com quatro campos: `source` (a implementação real),
`tests` (os testes que a exercitam), `keywords` (como o arquiteto a encontra) e
`examples` (usados na documentação e no teste de fumaça do CLI).

Três testes parametrizados cobrem automaticamente toda entrada nova: que
compila e executa, que tem teste invocando-a, e que os exemplos produzem
exatamente o valor documentado. Capacidade que não passa nesses três não entra.
