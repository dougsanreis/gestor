# Squad de Funil — nicho de vibe code

Documentação técnica do sistema de funil implementado em `syra/funnel/`.
Tudo descrito aqui é código executável, coberto por 43 testes.

> **Nota sobre o anexo.** Você mencionou um anexo com tentativas anteriores.
> O conteúdo dele não chegou até mim — o que está aqui foi construído do
> zero a partir do que você descreveu na mensagem. Se colar o material,
> eu incorporo o que fizer sentido.

---

## 1. Como as dores foram mapeadas e ranqueadas

Cada dor recebe dois números de 1 a 10: **intensidade** (o quanto dói) e
**frequência** (quantos no nicho sentem). A prioridade é o produto dos dois.
Isso substitui opinião por ordenação.

```bash
syra funnel list                      # todas as dores, ordenadas
syra funnel list --nivel iniciante    # filtra por nível
```

| Prio | Nível | Dor |
|---:|---|---|
| 81 | iniciante | Funciona na demo, quebra com gente de verdade |
| 80 | iniciante | A IA entra em loop e cada correção quebra outra coisa |
| 72 | iniciante | Não sabe colocar no ar |
| 72 | intermediário | Nova funcionalidade quebra a antiga sem ninguém perceber |
| 72 | intermediário | Mantém código que não consegue explicar |
| 70 | avançado | Revisão humana virou o gargalo |
| 64 | intermediário | Projeto grande demais para o contexto da IA |
| 64 | avançado | Qualidade varia por pessoa e por dia |
| 56 | iniciante | Medo de ter deixado algo exposto |
| 54 | avançado | Não sabe dizer quem aprovou o que a IA escreveu |

Fonte: `syra/funnel/personas.py`. Três personas, cada uma com dores na fala
literal do cliente, objeções e a prova que convence aquele perfil.

### Por que a fala literal importa

Cada dor carrega `fala_do_cliente` — a frase como a pessoa diria. A copy usa
essa frase sem reescrever. É a diferença entre:

> "Otimize seu fluxo de desenvolvimento com IA" *(adjetivo sobre o produto)*

> "Peço pra consertar, ela conserta, e aí quebra outra parte. Fico duas horas
> girando e volto pro mesmo erro do começo." *(a pessoa se reconhece)*

---

## 2. Os três funis

Selecionados por uma regra: **cada funil ataca a dor de maior prioridade de uma
persona diferente**. Três funis disputando a mesma audiência desperdiçariam
tráfego e canibalizariam a lista.

### Funil 1 — Do protótipo ao ar (`do_prototipo_ao_ar`)

- **Persona:** iniciante · **Dor:** funciona na demo, quebra com gente de verdade (81)
- **Promessa:** transformar o que já construiu num link que aguenta outras pessoas usando — sem virar programador
- **Inimigo:** o conteúdo que ensina a construir a demo e some na hora de colocar no ar
- **Mecanismo:** a demo quebra por um número pequeno de motivos que se repetem — entrada não testada, chave exposta, estado local, erro sem tratamento. Fechar essa lista, nessa ordem, resolve a maior parte dos casos
- **Oferta:** Kit Protótipo ao Ar · garantia de 7 dias

| Etapa | Objetivo | Ativo | Métrica | Meta |
|---|---|---|---|---|
| TOFU | reconhecimento em uma frase | post/vídeo curto | CTR para captura | 4% |
| MOFU | entregar valor antes de vender | checklist dos 12 motivos | visita→lead | 30% |
| BOFU | converter quem viu o próprio problema | página de vendas | lead→cliente | 5% |

### Funil 2 — Fim do loop de erro (`fim_do_loop_de_erro`)

- **Persona:** intermediário · **Dor:** regressão silenciosa (72)
- **Promessa:** parar o ciclo em que cada correção da IA quebra outra coisa
- **Inimigo:** a crença de que basta pedir com mais detalhe. O problema não é o prompt: é a ausência de um critério que diga quando parar
- **Mecanismo:** o loop acontece porque nada mede se a correção piorou o resto. Com suíte que roda em segundos e teto de tentativas, a IA para de girar
- **Oferta:** Protocolo Anti-Loop · garantia de 14 dias

| Etapa | Objetivo | Ativo | Métrica | Meta |
|---|---|---|---|---|
| TOFU | nomear o padrão que ela vive | thread/vídeo sobre o loop | CTR para captura | 5% |
| MOFU | provar o diagnóstico no projeto dela | diagnóstico de regressão | visita→lead | 28% |
| BOFU | vender o critério de parada | página de vendas | lead→cliente | 6% |

### Funil 3 — Governança de código gerado por IA (`governanca_de_codigo_gerado`)

- **Persona:** avançado · **Dor:** revisão humana virou o gargalo (70)
- **Promessa:** manter a velocidade que a IA deu ao time sem que a revisão vire gargalo
- **Inimigo:** a escolha falsa entre travar a entrega ou aceitar código que ninguém revisou
- **Mecanismo:** revisão humana não escala com geração automática — é corrida perdida por construção. O que escala é mover o critério para fora da cabeça do revisor
- **Oferta:** Camada de Governança para Times de IA · garantia de 30 dias, piloto em um repositório

| Etapa | Objetivo | Ativo | Métrica | Meta |
|---|---|---|---|---|
| TOFU | colocar número no gargalo | artigo com dados | CTR para captura | 3% |
| MOFU | virar diagnóstico defensável | relatório do repositório | visita→lead | 22% |
| BOFU | converter com piloto de baixo risco | página + piloto guiado | lead→cliente | 8% |

---

## 3. As páginas

```bash
syra funnel page --funil fim_do_loop_de_erro --out paginas/
```

Gera quatro arquivos por funil: três páginas de venda (uma por ângulo) e uma
página de captura. Doze arquivos no total para os três funis.

### Anatomia da página de vendas

1. **Hero** — kicker, headline, subhead, CTA, e a linha de reversão de risco
2. **Reconhecimento** — as falas literais do cliente como citações
3. **Custo e inimigo** — o que continuar assim custa, e com quem a página concorda
4. **Mecanismo** — por que isto funciona, antes de qualquer preço
5. **Oferta** — entregáveis, âncora de valor, garantia
6. **Objeções** — acordeão `<details>` nativo, uma resposta por objeção da persona
7. **Transparência** — para quem é, para quem **não** é
8. **Fechamento** — o custo de não decidir, e o CTA final

### Decisões técnicas e por quê

| Decisão | Razão |
|---|---|
| HTML autocontido, zero dependência externa | página que depende de CDN carrega mais devagar, quebra sozinha e vaza dado do visitante |
| Zero JavaScript estrutural | se o script não carregar, a página continua vendendo; o acordeão é `<details>` nativo |
| Tema claro/escuro via `prefers-color-scheme` | respeita a preferência do visitante sem pedir nada |
| Todo texto passa por `html.escape` | prova fornecida por você é conteúdo externo; um `<script>` no depoimento não vira XSS |
| `data-variante` e `data-segmento` no `<body>` | qualquer ferramenta de analytics lê qual variante foi servida; a página não envia nada sozinha |

### Os três ângulos

Cada ângulo é uma variante testável, com headline e abertura diferentes:

- **`dor`** — abre com a dor nomeada. Converte melhor com iniciante
- **`promessa`** — abre com o resultado. Converte melhor com quem já sabe o que quer
- **`mecanismo`** — abre com o porquê. Converte melhor com público técnico e cético

Não é palpite: qual vence em cada segmento é decidido por dados (seção 4).

### A trava contra prova inventada

O gerador de copy **nunca** produz depoimento, faturamento ou número de alunos.
Sem `provas_reais` fornecidas por você, a página declara prova pendente e o
`IntegridadeAgent` bloqueia a publicação — `syra funnel optimize` sai com
código 2.

```python
gerar_copy_vendas(funil, persona, provas_reais=("120 alunos concluíram o módulo 1",))
```

Prova falsa não é atalho de conversão: é o que queima o funil inteiro quando
alguém checa.

---

## 4. Como a página se remodela conforme a audiência

O mecanismo é estatística, não regra fixa.

### Placar por segmento

Cada segmento de audiência mantém o próprio placar por variante. A mesma
página serve ângulos diferentes para iniciante e para líder técnico, porque
cada um tem seu próprio histórico.

```bash
syra funnel serve --funil fim_do_loop_de_erro --segmento intermediario
# -> qual ângulo servir agora

syra funnel track --funil fim_do_loop_de_erro --segmento intermediario \
                  --angulo dor --exposicoes 1 --conversoes 1
```

### Intervalo de Wilson, não taxa bruta

Uma variante com 1 conversão em 2 visitas tem taxa de 50%. Uma com 40 em 200
tem 20%. A taxa bruta escolheria a primeira — e estaria errada.

O limite inferior de Wilson pune amostra pequena:

| Variante | Taxa | Intervalo de 95% | Limite inferior |
|---|---|---|---|
| 1/2 | 50,0% | [9,5% – 90,5%] | **9,5%** |
| 40/200 | 20,0% | [15,0% – 26,1%] | **15,0%** |

A decisão usa o limite inferior. A segunda vence, corretamente.

### Duas fases: explorar e depois explorar mais

1. **Exploração inicial** — toda variante recebe pelo menos 30 exposições
2. **Exploração contínua** — 15% do tráfego vai para a variante menos amostrada

A segunda fase não é desperdício. Sem ela o líder monopoliza o tráfego, os
intervalos das outras nunca estreitam, o experimento jamais atinge
significância — e o motor fica cego a mudança de audiência ao longo do tempo.

### Promoção só com separação estatística

O ângulo padrão só é promovido quando o **limite inferior do líder supera o
limite superior de todas as demais**. Enquanto os intervalos se sobrepõem, o
experimento continua.

Resultado real de uma simulação com taxas verdadeiras conhecidas:

```
[iniciante] vencedora=dor        CONFIANTE=True
   dor         241/2524   9,6%  IC [8,5%, 10,8%]     (taxa real: 9%)
   promessa      9/238    3,8%  IC [2,0%,  7,0%]     (taxa real: 5%)
   mecanismo     9/238    3,8%  IC [2,0%,  7,0%]     (taxa real: 4%)

[avancado]  vencedora=mecanismo  CONFIANTE=False
   intervalos ainda se sobrepõem: experimento continua
```

Repare no segundo caso: o motor identifica o líder correto mas **se recusa a
declarar vencedor** porque a amostra ainda não separa. Declarar cedo é o
equivalente, no funil, a aprovar entrega sem teste.

---

## 5. O squad de agentes

```bash
syra funnel optimize            # ciclo completo
syra funnel optimize --dry-run  # recomenda sem promover
```

| Agente | O que observa | O que propõe |
|---|---|---|
| `CopyAgent` | decisão estatística por segmento | promover o ângulo vencedor como padrão |
| `EtapaAgent` | conversão de cada etapa vs. meta | qual etapa está abaixo e por quanto |
| `GargaloAgent` | distância relativa da meta em todas as etapas | onde concentrar esforço primeiro |
| `IntegridadeAgent` | provas declaradas nas páginas | bloquear publicação sem prova verificada |

### Por que o gargalo é medido em distância *relativa*

Uma etapa TOFU a 1,8% com meta de 4% entrega 45% da própria meta. Uma BOFU a
3% com meta de 5% entrega 60%. A TOFU é o gargalo, embora seu número absoluto
seja menor. Corrigir a etapa mais alta move todas as seguintes.

### O que o squad não faz

Ele **não ajusta a meta para baixo** quando uma etapa fica abaixo dela. Etapa
sob a meta vira recomendação explícita, nunca acomodação silenciosa da régua.
É a mesma trava que impede o otimizador da fábrica de baixar a taxa exigida de
aprovação de testes.

---

## 6. A jornada completa

```
TOFU  ─ conteúdo que nomeia a dor
        métrica: CTR para a captura
        gatilho: reconhecimento ("isso aconteceu comigo ontem")
   ↓
MOFU  ─ página de captura + material que entrega valor real
        métrica: visita → lead
        gatilho: ela encontra um problema real no próprio projeto
   ↓
BOFU  ─ página de vendas no ângulo vencedor do segmento dela
        métrica: lead → cliente
        gatilho: viu o problema, não sabe corrigir sozinha
   ↓
LOOP  ─ syra funnel track alimenta o placar
        syra funnel optimize promove o que ganhou
        a próxima pessoa do mesmo segmento recebe a variante melhor
```

O loop é o produto. Sem ele são só três páginas bonitas.

---

## 7. Construindo agentes novos no Claude Code

Um agente de funil implementa um único método:

```python
class MeuAgente:
    """Uma frase dizendo o que este agente observa e por quê."""

    name = "meu_agente"

    def recommend(self, sinais: SinaisFunil) -> list[Recommendation]:
        """Propõe mudanças a partir dos sinais observados."""
        if sinais.etapas.get("MOFU", ContagemEtapa()).entradas < 50:
            return []          # amostra insuficiente: silêncio é a resposta
        return [_rec(
            self.name,
            f"{sinais.funil.id}:MOFU",
            {"tipo": "minha_proposta", "valor": 42},
            "ganho esperado, em uma frase",
            confidence=0.8,
            evidence=["o número que sustenta a proposta"],
        )]
```

Registre em `AGENTES_FUNIL` e escreva o teste. Quatro regras não negociáveis:

1. **Amostra insuficiente → lista vazia.** Recomendar sem dado é palpite com
   aparência de método.
2. **Toda recomendação carrega `evidence`.** Sem o número que a sustenta, ela
   não deveria existir.
3. **Nenhum agente promove sozinho.** Promoção passa por validação — no funil,
   separação estatística; na fábrica, replay do histórico em sombra.
4. **Nenhum agente pode afrouxar critério.** Meta abaixo, prova inventada,
   teste desligado: essas propostas são descartadas antes da validação.

O mesmo padrão vale para os agentes da fábrica em
`syra/intelligence/optimizer.py`, com uma diferença: lá a validação é replay
do histórico gravado sob a política candidata, e sete campos de política estão
em `CAMPOS_CONGELADOS`.

---

## 8. Referência de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `syra/funnel/personas.py` | audiência, dores com fala literal, objeções |
| `syra/funnel/blueprint.py` | os 3 funis, oferta e etapas TOFU/MOFU/BOFU |
| `syra/funnel/copy.py` | copy humanizada e a trava contra prova inventada |
| `syra/funnel/pages.py` | HTML autocontido, tema duplo, escape de conteúdo |
| `syra/funnel/variants.py` | Wilson, exploração, decisão de vencedor |
| `syra/funnel/squad.py` | os 4 agentes e o ciclo de promoção |
| `tests/test_funil.py` | 43 testes cobrindo estatística, copy, páginas e squad |
