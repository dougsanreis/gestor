#!/usr/bin/env bash
# GATE: build [web|team|all]
#
# Build isolado por app, com watchdog. Falha de build NAO destroi nada.
# Extrai a causa raiz do erro de build em vez de despejar 5000 linhas.

# shellcheck source=../lib/guard.sh
. "$GOVIO_LIB/guard.sh"

TARGET="${1:-all}"

g::head "BUILD — $TARGET"
g::init "build-$TARGET" || exit 0

g::snapshot "$GOVIO_EVIDENCE/before" >/dev/null 2>&1

case "$TARGET" in
  web)  APPS="web" ;;
  team) APPS="team-panel" ;;
  all)  APPS="web team-panel" ;;
  *)    g::fail "ALVO_INVALIDO:$TARGET"; g::finish "BUILD_ABORTADO" "govio build all"; exit 0 ;;
esac

FALHAS=0
for app in $APPS; do
  DIR="$GOVIO_WT/apps/$app"
  [ -d "$DIR" ] || { g::say "SKIP apps/$app (ausente)"; continue; }

  g::say ""
  g::say ">>> build apps/$app"
  g::run "build-$app" 900 "$DIR" -- pnpm build

  if [ "$GOVIO_LAST_RC" -eq 0 ]; then
    g::kv "BUILD_$app" "PASS"
  else
    FALHAS=$(( FALHAS + 1 ))
    g::kv "BUILD_$app" "FAIL(rc=$GOVIO_LAST_RC)"

    g::say ""
    g::say "### CAUSA RAIZ — apps/$app"
    python3 - "$GOVIO_LAST_STDOUT" "$GOVIO_LAST_STDERR" <<'PY'
import re, sys
from pathlib import Path

def read(p):
    try: return Path(p).read_text(encoding="utf-8", errors="replace")
    except OSError: return ""

text = read(sys.argv[1]) + "\n" + read(sys.argv[2])
lines = text.splitlines()

signals = [
    (r"error TS\d+",                       "TYPESCRIPT"),
    (r"Module not found",                  "MODULO_AUSENTE"),
    (r"Invalid environment variables",     "ENV_INVALIDO"),
    (r"ZodError|ZodIssue",                 "ENV_ZOD"),
    (r"Error: Failed to collect page data","PAGE_DATA_ENV"),
    (r"PrismaClient(Initialization)?Error","PRISMA"),
    (r"ECONNREFUSED|ENOTFOUND",            "REDE"),
    (r"Cannot find module",                "IMPORT_QUEBRADO"),
    (r"out of memory|heap",                "MEMORIA"),
]

found = []
for i, line in enumerate(lines):
    for rx, tag in signals:
        if re.search(rx, line):
            found.append((tag, i, line.strip()))
            break

if not found:
    print("CLASSIFICACAO=NAO_RECONHECIDA")
    print("--- ultimas 40 linhas ---")
    for l in lines[-40:]: print(l)
else:
    tags = sorted({t for t, _, _ in found})
    print("CLASSIFICACAO=" + ",".join(tags))
    seen = set()
    for tag, i, line in found:
        if tag in seen: continue
        seen.add(tag)
        print(f"\n>>> {tag} (linha {i+1})")
        for l in lines[max(0, i-4): i+8]:
            print("   " + l)
PY
  fi
done

g::snapshot "$GOVIO_EVIDENCE/after" >/dev/null 2>&1
g::say ""
g::say "### PROVA DE NAO-DESTRUICAO"
g::snapshot_diff "$GOVIO_EVIDENCE/before" "$GOVIO_EVIDENCE/after" | grep -E '^(SOURCE_FILES_REMOVED|SOURCE_MUTATION)='

if [ "$FALHAS" -eq 0 ]; then
  g::finish "BUILD_PASS" "govio ship preview"
else
  g::finish "BUILD_FAIL_${FALHAS}_APPS" "enviar causa raiz ao agente -> govio apply"
fi
exit 0
