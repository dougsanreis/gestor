#!/usr/bin/env bash
# GATE: doctor
#
# Varredura de diagnostico COMPLETA em uma unica execucao, 100% read-only.
#
# Doutrina: `tsc --noEmit` ja reporta TODOS os erros de uma vez. Construir um
# gate por diagnostico converte uma ferramenta batch em serial e multiplica o
# custo por N rodadas com humano no loop. Um doctor, N patches, um verify.
#
# ZERO mutacao: nao escreve no worktree, nao instala, nao builda, nao deploya.

# shellcheck source=../lib/guard.sh
. "$GOVIO_LIB/guard.sh"

g::head "DOCTOR — diagnostico completo (read-only)"
g::init "doctor" || exit 0

BUNDLE="$GOVIO_EVIDENCE/bundle.txt"

g::snapshot "$GOVIO_EVIDENCE/before" >/dev/null 2>&1

{
  printf '=== GOVIO DOCTOR BUNDLE ===\n'
  printf 'GERADO_EM=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'WORKTREE=%s\n' "$GOVIO_WT"
  printf 'HEAD=%s\n' "$(g::head_sha)"
  printf 'PATCH_SHA=%s\n' "$(g::patch_sha)"
} > "$BUNDLE"

# ------------------------------------------------------------ 1. estado git
g::say ""
g::say "### 1. ESTADO DO REPOSITORIO"
{
  printf '\n--- git status ---\n'
  g::git status --porcelain=v1
  printf '\n--- branches locais ---\n'
  g::git branch --format='%(refname:short) %(objectname:short)' 2>/dev/null | head -30
  printf '\n--- ultimos commits ---\n'
  g::git log --oneline -8 2>/dev/null
} | tee -a "$BUNDLE"

# ------------------------------------------------------------ 2. topologia
g::say ""
g::say "### 2. TOPOLOGIA DO MONOREPO"
{
  printf '\n--- apps ---\n'
  ls -1 "$GOVIO_WT/apps" 2>/dev/null
  printf '\n--- packages ---\n'
  ls -1 "$GOVIO_WT/packages" 2>/dev/null
  printf '\n--- scripts por app ---\n'
  for pkg in "$GOVIO_WT"/apps/*/package.json "$GOVIO_WT"/packages/*/package.json; do
    [ -f "$pkg" ] || continue
    printf '%s\n' "${pkg#"$GOVIO_WT"/}"
    python3 -c '
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
print("  name:", d.get("name"))
for k,v in sorted((d.get("scripts") or {}).items()):
    print(f"    {k}: {v}")
' "$pkg" 2>/dev/null
  done
} | tee -a "$BUNDLE"

# ------------------------------------------------------------ 3. env bootstrap
g::say ""
g::say "### 3. VALIDACAO DE ENV (causa raiz historica do 500 e do build)"
{
  printf '\n--- packages/db/src/env.ts ---\n'
  if [ -f "$GOVIO_WT/packages/db/src/env.ts" ]; then
    printf 'SHA256=%s\n' "$(g::sha "$GOVIO_WT/packages/db/src/env.ts")"
    printf 'LINHAS=%s\n' "$(wc -l < "$GOVIO_WT/packages/db/src/env.ts")"
    printf -- '--- conteudo ---\n'
    cat "$GOVIO_WT/packages/db/src/env.ts"
    printf -- '--- fim ---\n'
  else
    printf 'AUSENTE\n'
  fi

  printf '\n--- outros arquivos de env ---\n'
  find "$GOVIO_WT/apps" "$GOVIO_WT/packages" \
    -maxdepth 4 -name 'env.ts' -o -maxdepth 4 -name 'env.mjs' 2>/dev/null \
    | sed "s|$GOVIO_WT/||" | head -20

  printf '\n--- validacao eager no topo do modulo (parse) ---\n'
  python3 - "$GOVIO_WT" <<'PY'
import re, sys
from pathlib import Path
wt = Path(sys.argv[1])
pats = [
    (r'^\s*export\s+const\s+env\s*=\s*\w+\.parse\(', "EAGER_TOP_LEVEL_PARSE"),
    (r'^\s*const\s+env\s*=\s*\w+\.parse\(',          "EAGER_TOP_LEVEL_PARSE"),
    (r'\.parse\(process\.env\)',                     "PARSE_PROCESS_ENV"),
    (r'throw new Error\(',                           "THROW_AT_MODULE_SCOPE"),
]
for f in sorted(wt.glob("packages/*/src/env.ts")) + sorted(wt.glob("apps/*/lib/env.ts")):
    txt = f.read_text(encoding="utf-8", errors="replace")
    hits = [tag for rx, tag in pats if re.search(rx, txt, re.M)]
    rel = f.relative_to(wt)
    print(f"{rel}: {'/'.join(sorted(set(hits))) or 'SEM_SINAL_EAGER'}")
PY
} | tee -a "$BUNDLE"

# ------------------------------------------------------------ 4. landing CMS
g::say ""
g::say "### 4. SUPERFICIE DO CMS DA LANDING"
{
  for d in \
    "apps/web/lib/landing" \
    "apps/team-panel/app/landing" \
    "apps/team-panel/lib"
  do
    printf '\n--- %s ---\n' "$d"
    if [ -d "$GOVIO_WT/$d" ]; then
      find "$GOVIO_WT/$d" -type f \( -name '*.ts' -o -name '*.tsx' \) \
        -printf '%P\n' 2>/dev/null | sort | while read -r f; do
          printf '  %-42s %8s bytes  %s\n' "$f" \
            "$(wc -c < "$GOVIO_WT/$d/$f")" \
            "$(g::sha "$GOVIO_WT/$d/$f" | cut -c1-12)"
        done
    else
      printf '  AUSENTE\n'
    fi
  done

  printf '\n--- schema prisma (diff vs HEAD) ---\n'
  g::git diff -- packages/db/prisma/schema.prisma 2>/dev/null | head -80
} | tee -a "$BUNDLE"

# ------------------------------------------------------------ 5. typecheck
g::say ""
g::say "### 5. TYPECHECK DE TODAS AS CAMADAS (batch, nao serial)"

TS_TOTAL=0
for app in web team-panel; do
  APP_DIR="$GOVIO_WT/apps/$app"
  [ -d "$APP_DIR" ] || { g::say "SKIP app=$app (ausente)"; continue; }

  g::say ""
  g::say ">>> typecheck: apps/$app"
  g::run "typecheck-$app" 300 "$APP_DIR" -- pnpm typecheck

  {
    printf '\n=== TYPECHECK apps/%s (rc=%s) ===\n' "$app" "$GOVIO_LAST_RC"
    cat "$GOVIO_LAST_STDOUT"
    cat "$GOVIO_LAST_STDERR"
  } >> "$BUNDLE"

  N="$(g::ts_diagnostics "$GOVIO_LAST_STDOUT" "$GOVIO_LAST_STDERR" \
        "$GOVIO_EVIDENCE/ts-$app.json" | tee -a "$BUNDLE" | tee /dev/stderr \
        | sed -n 's/^TS_DIAGNOSTICS=//p')"
  TS_TOTAL=$(( TS_TOTAL + ${N:-0} ))
done

# ------------------------------------------------------------ 6. vercel
g::say ""
g::say "### 6. VERCEL (somente leitura de metadados)"
{
  if g::have vercel; then
    printf '\n--- projetos ---\n'
    (cd "$GOVIO_WT" && timeout 60s vercel project ls --scope govio-br 2>&1 | head -30)
    printf '\n--- binding local ---\n'
    for p in "$GOVIO_WT/.vercel/project.json" "$HOME/Projects/RATIA/ratia-core/.vercel/project.json"; do
      [ -f "$p" ] && { printf '%s:\n' "$p"; cat "$p"; printf '\n'; }
    done
  else
    printf 'vercel CLI ausente\n'
  fi
} 2>&1 | tee -a "$BUNDLE"

# ------------------------------------------------------------ 7. imutabilidade
g::say ""
g::say "### 7. PROVA DE IMUTABILIDADE (doctor nao pode ter mudado nada)"
g::snapshot "$GOVIO_EVIDENCE/after" >/dev/null 2>&1
g::snapshot_diff "$GOVIO_EVIDENCE/before" "$GOVIO_EVIDENCE/after" | tee -a "$BUNDLE"

# ------------------------------------------------------------ resumo
g::say ""
g::hr
g::kv TYPESCRIPT_ERROS_TOTAIS "$TS_TOTAL"
g::kv BUNDLE                  "$BUNDLE"
g::kv BUNDLE_BYTES            "$(wc -c < "$BUNDLE")"
g::say ""
g::say "Envie o BUNDLE inteiro para o agente. Ele gera TODOS os patches de uma vez."
g::say "  cat $BUNDLE"

if [ "$TS_TOTAL" -eq 0 ]; then
  g::finish "DIAGNOSTICO_LIMPO" "govio build"
else
  g::finish "DIAGNOSTICO_COM_${TS_TOTAL}_ERROS_TS" "enviar bundle ao agente -> govio apply"
fi
exit 0
