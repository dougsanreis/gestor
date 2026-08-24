# Plugando na SYRA AIOS

Passo a passo, na ordem. Cada passo termina num estado verificável — se algo
falhar, você sabe exatamente onde parou.

---

## 1. Instalar (não há instalação)

```bash
cd ~/Projects/SYRA
git clone <este-repo> syra-core
cd syra-core

./syra doctor
./syra selftest
```

Esperado:

```
PREFLIGHT_DECISION=PASS
SELFTEST_DECISION=PASS
```

Se `doctor` reclamar de `writable:evidence_root`, aponte para outro lugar:

```bash
export SYRA_EVIDENCE_ROOT=~/.syra/evidence/product-platform
export SYRA_STATE_ROOT=~/.syra/state
export SYRA_WORKSPACE=~/Projects/SYRA
```

Não rode mais nada até os dois darem `PASS`. É a SYRA-RULE-PPC-001 aplicada ao
próprio núcleo: se ele não valida a si mesmo, não tem autoridade para validar
o resto.

---

## 2. Descobrir o terreno (read-only)

```bash
./syra authority --root ~/Projects/SYRA
```

Confirma quantos repositórios existem e como cada um foi classificado.
Worktrees e repositórios sem commits aparecem marcados `SCAN=NO`, com o motivo.

```bash
./syra scan --root ~/Projects/SYRA
```

Escreve evidência selada. Guarde o `EVIDENCE_DIR` da saída.

**Se sair `STALE_EVIDENCE`** (exit 30): havia trabalho concorrente no workspace.
Rode de novo quando estiver quieto. Não é corrupção, e o scanner não escreveu em
nenhuma árvore de fonte.

Verificar a evidência a qualquer momento depois:

```bash
./syra evidence <EVIDENCE_DIR>
```

---

## 3. Decidir o que fazer

```bash
./syra decide --root ~/Projects/SYRA
```

Leia `recommended-sequence.txt` no diretório de evidência. A ordem é
deliberada:

1. **`CONSOLIDATE` primeiro.** É a causa raiz dos painéis que quebram na
   integração — várias implementações divergentes da mesma coisa.
2. **`BUILD`** — o que falta.
3. **`HARDEN`** — o que existe sem prova.
4. **`ADAPT`** — o que funciona mas não fala os contratos do núcleo.
5. **`CORE_PROVIDED`** — pare de manter cópia.
6. **`DO_NOT_TOUCH`** — congelado. Não mexa sem evidência de runtime.

Nada aqui é aplicado automaticamente. Todo artefato carrega
`implementationAuthorized: false`.

---

## 4. Criar um produto novo

Sempre ensaie antes:

```bash
./syra product new painel-vendas --kind platform \
    --into ~/Projects/SYRA/painel-vendas --dry-run
```

Lista os arquivos exatos sem tocar no disco. Satisfeito:

```bash
./syra product new painel-vendas --kind platform \
    --into ~/Projects/SYRA/painel-vendas --register
```

Termina com `VERIFIED=YES` — o factory rodou os testes do produto gerado antes
de entregar. Se falhar, é defeito do factory, não seu, e o produto fica no disco
para inspeção.

Tipos disponíveis:

| `--kind` | Para |
|---|---|
| `platform` | plataforma online com painéis |
| `multi_agent_platform` | plataforma coordenando squads |
| `agent_squad` | squad de agentes num problema |
| `agent` | agente único para uma dor específica |
| `saas` | SaaS multi-tenant |
| `tool` | ferramenta estratégica focada |

---

## 5. Implementar

O produto nasce com stubs que passam. Substitua os corpos em
`app/connectors.py`:

```python
def _backend_api(payload: Dict[str, Any]) -> Dict[str, Any]:
    resultado = minha_logica_real(payload)
    return {"ok": True, "connector": "backend_api", "data": resultado}
```

**Regra do conector:** levante exceção em caso de falha. Nunca retorne um objeto
de erro — o gateway distingue sucesso de falha por exceção, e um erro retornado
parece uma chamada bem-sucedida para o breaker.

Aperte o contrato em `contracts/<produto>.json` conforme o formato real se
firma. Contrato apertado demais cedo demais ensina gente a desligar validação,
o que é pior que não ter.

---

## 6. Conectar coisas externas

### Agente ou squad

```python
from syra_core import agent_connector

runtime.register(agent_connector(
    "planner", minha_funcao,
    request_contract="painel.plan.request",
    response_contract="painel.plan.response",
    timeout_seconds=30.0,
    squad=True,          # para um passo de squad
))
```

### API HTTP (Railway, Vercel, Cloudflare, GitHub)

```python
from syra_core import http_connector
from syra_core.breaker import BreakerPolicy

runtime.register(http_connector(
    "railway-api",
    base_url="https://backend.up.railway.app",
    path="/api/v1/orders",
    health_path="/health",
    response_contract="painel.orders.response",
    timeout_seconds=8.0,
    breaker_policy=BreakerPolicy(failure_threshold=3, recovery_seconds=20.0),
))
```

`http_connector` declara `network` automaticamente. O manifesto do produto
precisa conceder — senão a chamada é recusada antes de sair. Isso é o mecanismo
funcionando, não um bug.

### Dependência opcional

```python
runtime.register(service_connector("analytics", enviar, critical=False))
```

Falhando, degrada o readiness em vez de derrubar o produto.

---

## 7. Operar

```bash
./syra product readiness ~/Projects/SYRA/painel-vendas
./syra product list                    # inclui drift entre registro e disco
./syra failures list --open-only
```

Ao corrigir um defeito, registre:

```bash
./syra failures resolve a1b2c3d4e5f6 "timeout do railway subiu para 15s"
```

Isso não é burocracia. Se o defeito voltar, a memória reabre e mostra que a
correção anterior não resolveu — informação que se perde quando ninguém anota.

Para trabalho não-supervisionado (cron, agente autônomo), ligue o modo
bloqueante:

```python
runtime = ProductRuntime.from_manifest(MANIFEST, block_repeats=True)
```

Defeito conhecido e aberto passa a ser recusado antes da chamada cara.

---

## 8. Diagnosticar quando algo quebra

```python
import json
print(json.dumps(runtime.diagnostics(), indent=2))
```

Traz num payload só: manifesto, safety concedida, readiness, conectores,
estado dos breakers, defeitos abertos, contratos carregados e o relatório de
boot.

Para trace por chamada, aponte a telemetria para um arquivo:

```python
runtime = ProductRuntime.from_manifest(
    MANIFEST, telemetry_sink="~/.syra/state/painel-vendas.jsonl"
)
```

JSONL — `grep`, `tail` e `jq` funcionam.

---

## Erros comuns e o que significam

| Código | Significa | Ação |
|---|---|---|
| `SYRA-E-SAFETY-DENIED` | conector pediu autoridade não concedida | declarar no manifesto, ou usar conector que não precisa |
| `SYRA-E-CONTRACT-VIOLATION` | payload fora do formato | `remediation` aponta o campo exato |
| `SYRA-E-BREAKER-OPEN` | dependência falhando, chamada recusada | corrija a dependência; insistir só queima latência |
| `SYRA-E-TIMEOUT` | estourou o orçamento | ou a dependência está lenta, ou o timeout está apertado demais |
| `SYRA-E-REPEATED-FAILURE` | defeito conhecido e aberto | corrija e marque resolvido, ou aceite explicitamente |
| `SYRA-E-STALE-EVIDENCE` | fontes mudaram durante o scan | re-rode quando o workspace estiver quieto |
| `SYRA-E-PREFLIGHT-FAILED` | ferramenta não validou | corrija; não contorne |

Todo erro carrega `remediation` — a próxima ação. Erro que não diz o que fazer
vira workaround, e workaround é como painel apodrece.
