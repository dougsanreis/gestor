#!/usr/bin/env bash
# Suite de regressao do govio-kit. Sem rede, sem dependencias. Rode: bash tests/test_kit.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/bin"
TMP="$(mktemp -d)"
export GOVIO_HOME="$TMP/home"
PASS=0; FAIL=0

ok(){ PASS=$((PASS+1)); printf '  \033[32mPASS\033[0m %s\n' "$1"; }
no(){ FAIL=$((FAIL+1)); printf '  \033[31mFAIL\033[0m %s\n' "$1"; }
expect_rc(){ # expect_rc <esperado> <nome> <cmd...>
  local want="$1" name="$2"; shift 2
  "$@" >/dev/null 2>&1; local got=$?
  [ "$got" = "$want" ] && ok "$name" || no "$name (rc=$got, esperado $want)"
}
expect_out(){ # expect_out <regex> <nome> <cmd...>
  local re="$1" name="$2"; shift 2
  if "$@" 2>&1 | grep -qE "$re"; then ok "$name"; else no "$name (sem /$re/)"; fi
}

# fixture: repo git isolado
REPO="$TMP/repo"; mkdir -p "$REPO"; cd "$REPO"
git init -q . && git config user.email t@t && git config user.name t
echo marker > .marker && mkdir -p docs src migrations
git add -A && git commit -qm init

echo "== govio-ssot =="
expect_rc 2 "rejeita caminho-modelo (/CAMINHO/REAL/DO/...)" "$BIN/govio-ssot" pin "/CAMINHO/REAL/DO/govio-core"
expect_rc 2 "rejeita <SEU_CAMINHO>"                        "$BIN/govio-ssot" pin "/home/<SEU_CAMINHO>/x"
expect_rc 3 "path sem pin falha alto"                      "$BIN/govio-ssot" path
expect_rc 2 "rejeita marcador ausente"                     "$BIN/govio-ssot" pin "$REPO" --marker nao-existe
expect_rc 0 "pin valido"                                   "$BIN/govio-ssot" pin "$REPO" --marker .marker
expect_rc 0 "verify apos pin"                              "$BIN/govio-ssot" verify
expect_out "^$REPO\$" "path devolve canonico"              "$BIN/govio-ssot" path

echo "== govio-tier =="
expect_out "TIER=0" "JSON de estado local e T0"     "$BIN/govio-tier" classify .govio/project-state.json
expect_out "TIER=1" "codigo de app e T1"            "$BIN/govio-tier" classify src/app/page.tsx
expect_out "TIER=2" "CI e T2"                       "$BIN/govio-tier" classify .github/workflows/ci.yml
expect_out "TIER=3" "migracao destrutiva e T3"      "$BIN/govio-tier" classify migrations/002_drop_tenants.sql
expect_out "TIER=3" "o maior tier decide o conjunto" "$BIN/govio-tier" classify docs/a.md migrations/002_drop_tenants.sql
expect_rc 1 "gate excessivo em T0 e VIOLACAO"       "$BIN/govio-tier" check-gate --tier 0 --gates git_tracked diff_visivel preimage_sha
expect_rc 1 "gate faltante em T3 e VIOLACAO"        "$BIN/govio-tier" check-gate --tier 3 --gates git_tracked
expect_rc 0 "T0 com gates exatos passa"             "$BIN/govio-tier" check-gate --tier 0 --gates git_tracked diff_visivel

echo "== govio-dedupe =="
mkdir -p "$TMP/wt"/{ratia-r4-panel,ratia-r4-panel-ui,ratia-panel-fast-v1,ratia-team-panel-v1}
expect_rc 1 "bloqueia painel duplicado"   "$BIN/govio-dedupe" check "ratia-r4-panel-v2-new" --repo "$REPO" --roots "$TMP/wt"
expect_rc 0 "libera trabalho novo"        "$BIN/govio-dedupe" check "govio-nota-fiscal-eletronica" --repo "$REPO" --roots "$TMP/wt"
expect_out "4 membros" "audit agrupa a familia painel" "$BIN/govio-dedupe" audit --repo "$REPO" --roots "$TMP/wt"

echo "== govio-apply =="
printf 'novo\n' > "$TMP/src.txt"
SHA=$(sha256sum "$TMP/src.txt" | cut -d' ' -f1)
expect_rc 4 "T0 rejeita --expect-postimage (cerimonia excessiva)" \
  "$BIN/govio-apply" --file "$REPO/docs/a.md" --content-from "$TMP/src.txt" --expect-postimage "$SHA"
expect_rc 0 "T0 aplica com custo certo" \
  "$BIN/govio-apply" --file "$REPO/docs/a.md" --content-from "$TMP/src.txt"
expect_out "VERDICT=NOOP" "reaplicar e NOOP, nao reconstrucao" \
  "$BIN/govio-apply" --file "$REPO/docs/a.md" --content-from "$TMP/src.txt"
expect_rc 4 "T2 exige prova" \
  "$BIN/govio-apply" --file "$REPO/.github/workflows/ci.yml" --content-from "$TMP/src.txt"
expect_rc 4 "T2 rejeita prova divergente" \
  "$BIN/govio-apply" --file "$REPO/.github/workflows/ci.yml" --content-from "$TMP/src.txt" \
  --expect-postimage 0000000000000000000000000000000000000000000000000000000000000000
[ ! -f "$REPO/.github/workflows/ci.yml" ] && ok "prova divergente nao escreveu nada" \
  || no "prova divergente escreveu o alvo"
expect_rc 0 "T2 aplica com prova correta" \
  "$BIN/govio-apply" --file "$REPO/.github/workflows/ci.yml" --content-from "$TMP/src.txt" --expect-postimage "$SHA"

echo "== govio-ledger =="
expect_rc 0 "abre sessao"   "$BIN/govio-ledger" open s1 --goal "meta"
expect_rc 1 "zero delta reprova no enforce" "$BIN/govio-ledger" report --enforce
expect_rc 0 "registra entrega" "$BIN/govio-ledger" ship "delta real" --session s1 --tier 1 --files x.ts
expect_rc 0 "com entrega, passa"            "$BIN/govio-ledger" report --enforce

echo "== govio-preflight =="
expect_out "VERDICT=BLOCKED"    "bloqueia duplicado" \
  "$BIN/govio-preflight" --intent "ratia-r4-panel-outro" --goal m --files src/a.tsx --roots "$TMP/wt"
expect_out "VERDICT=AUTHORIZED" "autoriza trabalho novo e saudavel" \
  "$BIN/govio-preflight" --intent "govio-nota-fiscal-eletronica" --goal m --files src/a.tsx --roots "$TMP/wt"

echo "== politicas =="
for f in "$ROOT/policy/risk-tiers.json" "$ROOT/policy/invariants.json"; do
  python3 -c "import json,sys;json.load(open(sys.argv[1]))" "$f" && ok "JSON valido: $(basename "$f")" \
    || no "JSON invalido: $(basename "$f")"
done
python3 - "$ROOT/policy/invariants.json" <<'PY' && ok "teto de invariantes respeitado" || no "teto de invariantes estourado"
import json,sys
d=json.load(open(sys.argv[1]))
sys.exit(0 if len(d["invariants"])<=d["hardCap"] else 1)
PY

cd /; rm -rf "$TMP"
echo
echo "======================================"
echo "  PASS=$PASS  FAIL=$FAIL"
echo "======================================"
[ "$FAIL" -eq 0 ] || exit 1
