# Comece aqui

Três passos. Nada além disso é necessário para começar.

---

## Passo 1 — Provar que funciona na sua máquina

```bash
cd syra-core
./VERIFICAR.sh
```

Isso roda tudo: preflight, 201 testes, os 5 exemplos, e cria um produto de
teste do zero. Leva menos de um minuto.

Você deve ver:

```
VERIFICACAO_FINAL=PASS
```

**Se der `PASS`, o núcleo está pronto para plugar.** Não instalou nada, não
criou virtualenv, não baixou pacote. Só Python 3.8+.

Se der `FAIL`, a saída diz exatamente qual etapa falhou e o que fazer.

---

## Passo 2 — Entender o que ele faz (10 minutos)

Rode os exemplos na ordem. Cada um resolve **um** dos seus problemas e imprime
a lição no fim.

```bash
python3 exemplos/01_contrato_protege_painel.py   # painel quebra ao conectar backend
python3 exemplos/02_breaker_contem_falha.py      # uma integração fora derruba tudo
python3 exemplos/03_memoria_de_falhas.py         # mesmo erro toda semana
python3 exemplos/04_produto_completo.py          # produto inteiro em ~30 linhas
python3 exemplos/05_safety_bloqueia.py           # autossabotagem bloqueada
```

São scripts de verdade, não pseudocódigo. Podem ser editados e re-rodados à
vontade — cada um usa um diretório temporário e não toca no estado da sua
máquina.

---

## Passo 3 — Apontar para a SYRA real

```bash
export SYRA_WORKSPACE=~/Projects/SYRA

./syra scan   --root ~/Projects/SYRA    # o que existe, e onde
./syra decide --root ~/Projects/SYRA    # o que fazer com cada coisa
```

O `decide` te entrega, para cada uma das 19 capacidades, uma disposição e uma
ordem de trabalho. **Nada é aplicado** — todo artefato sai com
`implementationAuthorized: false`. O gate propõe; você decide.

Comece pelos `CONSOLIDATE`. Múltiplas cópias divergentes da mesma capacidade é
a causa direta dos painéis que quebram na integração.

---

## Onde ler o quê

| Você quer | Leia |
|---|---|
| Visão geral e comandos | [`README.md`](README.md) |
| Plugar passo a passo | [`docs/INTEGRATION.md`](docs/INTEGRATION.md) |
| Como os gates funcionam | [`docs/GATES.md`](docs/GATES.md) |
| Por que cada decisão foi tomada | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| O que é cada arquivo | [`MAPA.md`](MAPA.md) |

---

## Criar seu primeiro produto

Sempre ensaie primeiro:

```bash
./syra product new meu-painel --kind platform --into ~/Projects/SYRA/meu-painel --dry-run
```

Lista os arquivos exatos sem tocar no disco. Satisfeito, tire o `--dry-run`.

O produto nasce com manifesto válido, contratos e **testes passando**. O factory
roda os testes do produto gerado antes de te entregar — se não passarem, ele
recusa a entrega e diz que o defeito é dele, não seu.

---

## Se algo der errado

Todo erro do núcleo carrega uma linha `remediation` — a próxima ação concreta.
Erro que não diz o que fazer vira contorno, e contorno é como painel apodrece.

```bash
./syra doctor                # a máquina está bem?
./syra preflight             # o núcleo está íntegro?
./syra failures list         # o que já quebrou antes?
```

---

## O histórico git está no pacote

```bash
git clone -b claude/syra-core-panels-recovery-m19bxc syra-core.bundle syra-core-git
```

Se preferir trabalhar com git desde o começo, use isso em vez da pasta solta.
