# govio-kit — governança proporcional ao risco

Kit operacional que substitui a máquina de estados cerimonial do projeto GOVIO por
gates **proporcionais ao raio de destruição** da mudança.

Sem dependências. Apenas `python3` (≥3.8), `git` e coreutils.

## Por que existe

Uma sessão inteira foi consumida para alterar **dois campos de um arquivo JSON local
rastreado por git** — com três bindings SHA, sonda TOCTOU, transaction arm,
verificação de rollback e watchdog de imutabilidade. Zero linha de produto entregue.
No mesmo período, o `$HOME` acumulou 57 repositórios git sem nenhuma fonte canônica
declarada, e um caminho-modelo (`/CAMINHO/REAL/DO/govio-core`) foi executado
literalmente três vezes.

Diagnóstico completo, com evidência: [`docs/01-DIAGNOSTICO-AUTOSABOTAGEM.md`](docs/01-DIAGNOSTICO-AUTOSABOTAGEM.md).

## Princípio

> Mecânica barata (`tmp` + `fsync` + `os.replace`) fica **sempre** ligada — não custa sessão.
> Prova cara (bindings SHA, contrato de autoridade, revisor humano) entra a partir do
> TIER-2 — porque é ela que consome sessões inteiras sem entregar produto.

Em TIER-0/1 o git já é o log transacional e o rollback é `git checkout -- <arquivo>`.
Construir transação sobre um sistema que já é transacional é o defeito, não a virtude.

## Ferramentas

| Comando | Responde | Antídoto para |
|---|---|---|
| `govio-ssot` | onde fica a fonte canônica | `/CAMINHO/REAL/DO/govio-core`; 57 repos sem canônico |
| `govio-tier` | quanto gate este risco merece | cerimônia de TIER-3 sobre mudança de TIER-0 |
| `govio-apply` | escrita com custo proporcional | `ATOMIC_APPLY` monolítico |
| `govio-dedupe` | isto já existe? | 5× painel, 2× worker, 2× critical |
| `govio-ledger` | a sessão entregou algo? | 4 estados percorridos, 0 linha entregue |
| `govio-preflight` | **o comando único de abertura** | sessão que começa sem saber onde nem para quê |

## Início rápido

```bash
export PATH="$PWD/bin:$PATH"
bash tests/test_kit.sh                       # PASS=34 FAIL=0

govio-ssot scan --roots ~                    # descobrir e agrupar
govio-ssot pin <caminho-real> --marker package.json
cd "$(govio-ssot path)"

govio-preflight --intent "govio-<area>-<resultado>" \
                --goal "<o que a prefeitura passa a conseguir fazer>" \
                --files <arquivos>
```

## Documentação

| Documento | Para quem |
|---|---|
| [`docs/01-DIAGNOSTICO-AUTOSABOTAGEM.md`](docs/01-DIAGNOSTICO-AUTOSABOTAGEM.md) | quem decide o que corrigir |
| [`docs/02-CONTRATO-AGENTE-GPT.md`](docs/02-CONTRATO-AGENTE-GPT.md) | o agente GPT/Codex — cole como instrução permanente |
| [`docs/03-RUNBOOK-UBUNTU.md`](docs/03-RUNBOOK-UBUNTU.md) | quem opera o terminal |
| [`policy/risk-tiers.json`](policy/risk-tiers.json) | tiers, gates e orçamentos |
| [`policy/invariants.json`](policy/invariants.json) | invariantes com dono, TTL e teto rígido |

## Verificação

```bash
bash tests/test_kit.sh
```

34 asserções, sem rede e sem dependências. A suíte encontrou 5 defeitos reais
durante o desenvolvimento — entre eles um em que **caminho absoluto rebaixava
silenciosamente o tier de risco**, o que teria permitido tratar uma migração
destrutiva como mudança comum.
