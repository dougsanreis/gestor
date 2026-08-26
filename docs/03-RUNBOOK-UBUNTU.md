# Runbook — Ubuntu / SYRA AIOS

Sem dependências externas: apenas `python3` (≥3.8), `git` e coreutils.
Nada de `pip install`, nada de rede.

---

## 1. Instalação (uma vez)

```bash
# 1. clonar o kit
git clone https://github.com/dougsanreis/gestor ~/govio-kit
cd ~/govio-kit && git checkout claude/govio-project-analysis-9giksb

# 2. colocar no PATH de forma persistente
mkdir -p ~/.local/bin
for f in ~/govio-kit/bin/govio-*; do ln -sf "$f" ~/.local/bin/$(basename "$f"); done
grep -q 'HOME/.local/bin' ~/.bashrc || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
export PATH="$HOME/.local/bin:$PATH"

# 3. validar a instalação ANTES de confiar nela
bash ~/govio-kit/tests/test_kit.sh          # esperado: PASS=34 FAIL=0
```

Se a suíte não fechar em `FAIL=0`, **pare**. Ferramenta de governança não verificada
é pior que nenhuma: cria confiança sem base.

---

## 2. Resolver a fonte canônica (uma vez, e este é o passo que estava faltando)

```bash
govio-ssot scan --roots ~ | head -40
```

A saída agrupa os 57 repositórios por `origin` e marca `<-- DUPLICACAO` onde houver
mais de um checkout do mesmo remoto. Escolha o que contém o produto e fixe-o
com um marcador que **prove** ser o produto:

```bash
govio-ssot pin ~/Projects/SYRA/gestor --marker package.json
govio-ssot verify
```

A partir daqui, todo comando começa por:

```bash
cd "$(govio-ssot path)"
```

Nunca digite o caminho. `govio-ssot path` falha alto se o pin não valer mais —
é isso que impede o `/CAMINHO/REAL/DO/govio-core` de acontecer de novo.

---

## 3. Limpar a duplicação já instalada

```bash
govio-dedupe audit --roots ~/.syra/worktrees ~/Projects/SYRA
```

Para cada família com mais de um membro, escolha **um** sobrevivente e arquive o resto.
Arquivar, não apagar — histórico é barato, perda de trabalho não:

```bash
mkdir -p ~/.syra/archive/$(date -u +%Y%m%dT%H%M%SZ)
mv ~/.syra/worktrees/ratia-r4-panel-ui       ~/.syra/archive/$(date -u +%Y%m%d)*/
mv ~/.syra/worktrees/ratia-r4-panel-real-r1  ~/.syra/archive/$(date -u +%Y%m%d)*/
# ... mantendo apenas o worktree escolhido como sobrevivente
git -C "$(govio-ssot path)" worktree prune
```

---

## 4. Ciclo diário

```bash
cd "$(govio-ssot path)"

# a) abertura — responde as 4 perguntas antes de gastar sessão
govio-preflight \
  --intent "govio-relatorio-fiscal" \
  --goal   "prefeitura exporta relatório fiscal em PDF" \
  --files  src/app/relatorios/fiscal.tsx tests/fiscal.test.ts \
  --roots  ~/.syra/worktrees

# b) só se VERDICT=AUTHORIZED
govio-ledger open govio-relatorio-fiscal --goal "prefeitura exporta relatório fiscal em PDF"

# c) trabalhar; escrever pelo kit para herdar a cerimônia certa
govio-apply --file src/app/relatorios/fiscal.tsx --content-from /tmp/novo.tsx

# d) validar no escopo do tier (T1 = lint + typecheck + teste do escopo)
npm run lint -- src/app/relatorios && npx tsc --noEmit && npm test -- fiscal

# e) fechar com delta REAL
govio-ledger ship "prefeitura exporta relatório fiscal em PDF" \
  --session govio-relatorio-fiscal --tier 1 \
  --files src/app/relatorios/fiscal.tsx tests/fiscal.test.ts

govio-ledger report
```

---

## 5. Endurecimento do terminal

### 5.1 Guarda contra caminho-modelo no shell

A causa raiz de `/CAMINHO/REAL/DO/govio-core` foi um caminho-modelo virando comando.
Trave no shell:

```bash
cat >> ~/.bashrc <<'BASHRC'

# GOVIO: bloqueia cd para caminho-modelo não substituído
cd() {
  if [[ "$1" =~ (CAMINHO|SEU_|SUA_|PATH_TO|YOUR_|EXEMPLO|PLACEHOLDER|\<|\>) ]]; then
    echo "govio: caminho-modelo não substituído: $1" >&2
    echo "govio: use  cd \"\$(govio-ssot path)\"" >&2
    return 1
  fi
  builtin cd "$@"
}
BASHRC
```

### 5.2 Modo estrito em todo script

Todo script do projeto começa com:

```bash
#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'
```

Sem isto, um comando que falha no meio de um pipeline segue adiante e o script
relata sucesso sobre trabalho não feito — outra fonte de "passou no gate, nada mudou".

### 5.3 Hook de pre-commit

```bash
cat > "$(govio-ssot path)/.git/hooks/pre-commit" <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail
FILES=$(git diff --cached --name-only)
[ -z "$FILES" ] && exit 0
TIER=$(govio-tier classify $FILES | sed -n 's/^TIER=\([0-9]\).*/\1/p')
echo "govio: TIER-${TIER:-?} nesta mudanca"
if [ "${TIER:-1}" -ge 2 ]; then
  echo "govio: TIER-$TIER exige build verde e revisor humano antes do commit." >&2
fi
HOOK
chmod +x "$(govio-ssot path)/.git/hooks/pre-commit"
```

Ele **informa** o tier a cada commit. Não bloqueia TIER-0/1 — bloquear o barato é
exatamente o erro que estamos corrigindo.

### 5.4 Atalhos

```bash
cat >> ~/.bashrc <<'BASHRC'
alias gcd='cd "$(govio-ssot path)"'
alias gpf='govio-preflight'
alias glr='govio-ledger report'
alias gta='govio-tier classify'
BASHRC
```

---

## 6. Ligação com a SYRA AIOS

Os artefatos são JSON com contrato versionado (`formatVersion` + `artifactType`) —
consumíveis por qualquer orquestrador sem inferência de gramática, que foi
exatamente a causa do `MALFORMED_POSTIMAGE_AUTHORITY`:

| Artefato | Caminho | `artifactType` |
|---|---|---|
| Tiers de risco | `policy/risk-tiers.json` | `govio.policy.risk-tiers` |
| Invariantes | `policy/invariants.json` | `govio.policy.invariants` |
| Pin da fonte | `~/.govio/ssot.json` | `govio.ssot.pin` |
| Ledger | `~/.govio/ledger.jsonl` | JSONL, um registro por linha |

Leitura programática:

```bash
jq -r '.tiers[] | "T\(.tier) \(.name) orcamento=\(.maxSecondsBudget)s"' policy/risk-tiers.json
jq -r '.invariants[] | "\(.id) \(.rule)"'                                policy/invariants.json
jq -r 'select(.kind=="SHIP") | "\(.ts) \(.desc)"'                        ~/.govio/ledger.jsonl
```

Contrato de integração para a SYRA: **ler `artifactType` antes de interpretar
o conteúdo. `artifactType` desconhecido é falha de ferramenta, nunca normalização
automática.**

---

## 7. Limites conhecidos desta entrega

Declarados por honestidade operacional — não descubra isto por conta própria depois:

- **`govio-equipe.vercel.app` e `govio.com.br/dashboard` não foram inspecionados.**
  O egress desta sessão está bloqueado para ambos os domínios. As pendências do
  painel de equipe **não** entraram no diagnóstico. Para incluí-las, exporte o
  conteúdo do painel para arquivo e rode a análise sobre ele.
- **Os anexos não chegaram ao container** (`GOVIO_RECOVERY_PACKAGE.zip`,
  as auditorias v2/v3, `govio-grounding-*.tar.gz`). O diagnóstico se apoia no
  transcript colado, na saída real do `find` e nos repositórios acessíveis.
- **A fonte real do GOVIO não estava acessível.** `dougsanreis/gestor` tem
  1 commit e só `.gitkeep`. Os tiers em `policy/risk-tiers.json` usam convenções
  Next.js/TypeScript; ajuste os `patterns` à árvore real na primeira execução do
  `govio-tier classify`.
