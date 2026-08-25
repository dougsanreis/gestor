# shellcheck shell=bash
#
# govio guard library
#
# Regras permanentes (nao negociaveis):
#   - NUNCA git reset / clean / restore / checkout -- / stash drop
#   - NUNCA rm -rf no worktree
#   - NUNCA rollback automatico em falha de validacao
#   - NUNCA set -e no shell pai; toda execucao pesada roda em subshell
#   - Todo gate termina em exit 0; o RC real vai para a evidencia
#
# Motivo: um rollback destrutivo ja apagou trabalho neste projeto uma vez.
# Falha de validacao e informacao, nao e motivo para destruir arquivos.

set -u
umask 077

export NO_COLOR=1
export GIT_TERMINAL_PROMPT=0
export GIT_OPTIONAL_LOCKS=0
export NEXT_TELEMETRY_DISABLED=1
export CI=1

GOVIO_HOME="${GOVIO_HOME:-$HOME/.govio}"
GOVIO_EVIDENCE_ROOT="${GOVIO_EVIDENCE_ROOT:-$GOVIO_HOME/evidence}"
GOVIO_MAX_OUTPUT_BYTES="${GOVIO_MAX_OUTPUT_BYTES:-4000000}"
GOVIO_DEFAULT_WATCHDOG="${GOVIO_DEFAULT_WATCHDOG:-600}"

GOVIO_EVIDENCE=""
GOVIO_WT=""

# ---------------------------------------------------------------- utilidades

g::say()  { printf '%s\n' "$*"; }
g::kv()   { printf '%s=%s\n' "$1" "$2"; }
g::hr()   { printf '%s\n' "------------------------------------------------------------"; }

g::head() {
  printf '\n'
  g::hr
  printf 'GOVIO %s\n' "$1"
  g::hr
}

# Falha "fail-closed": informa e devolve 1. NUNCA destroi nada.
g::fail() {
  printf '\nFAIL_CLOSED=%s\n' "$1" >&2
  [ -n "$GOVIO_EVIDENCE" ] && printf 'EVIDENCE=%s\n' "$GOVIO_EVIDENCE" >&2
  return 1
}

g::sha() {
  [ -f "$1" ] || { printf 'MISSING\n'; return 0; }
  sha256sum -- "$1" | awk '{print $1}'
}

g::have() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------- worktree

# Resolve o worktree alvo. Ordem:
#   1. $GOVIO_WT explicito
#   2. worktree mais recente em ~/.syra/worktrees/govio-web-landing-*
#   3. ~/Projects/RATIA/ratia-core
g::resolve_wt() {
  local candidate=""

  if [ -n "${GOVIO_WT_OVERRIDE:-}" ]; then
    candidate="$GOVIO_WT_OVERRIDE"
  else
    candidate="$(
      find "$HOME/.syra/worktrees" -maxdepth 1 -mindepth 1 -type d \
        -name 'govio-web-landing-*' -print 2>/dev/null | sort | tail -n 1
    )"
    [ -n "$candidate" ] || candidate="$HOME/Projects/RATIA/ratia-core"
  fi

  [ -d "$candidate" ]        || { g::fail "WORKTREE_NOT_FOUND:$candidate"; return 1; }
  [ -e "$candidate/.git" ]   || { g::fail "NOT_A_GIT_WORKTREE:$candidate"; return 1; }

  GOVIO_WT="$candidate"
  return 0
}

g::git()       { git -C "$GOVIO_WT" "$@"; }
g::head_sha()  { g::git rev-parse HEAD 2>/dev/null || printf 'UNKNOWN\n'; }
g::patch_sha() { g::git diff --binary 2>/dev/null | sha256sum | awk '{print $1}'; }

# ---------------------------------------------------------------- evidencia

g::init() {
  local gate="$1"
  local stamp
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"

  GOVIO_EVIDENCE="$GOVIO_EVIDENCE_ROOT/${stamp}-${gate}"
  mkdir -p -- "$GOVIO_EVIDENCE" || return 1
  chmod 700 -- "$GOVIO_EVIDENCE" 2>/dev/null || true

  g::resolve_wt || return 1

  g::kv GATE       "$gate"
  g::kv WORKTREE   "$GOVIO_WT"
  g::kv HEAD       "$(g::head_sha)"
  g::kv PATCH_SHA  "$(g::patch_sha)"
  g::kv EVIDENCE   "$GOVIO_EVIDENCE"
  return 0
}

# ---------------------------------------------------------------- snapshot

# Snapshot do estado dos arquivos nao commitados (para provar imutabilidade).
g::snapshot() {
  local out="$1"
  {
    g::git status --porcelain=v1 2>/dev/null
  } > "$out.status"

  g::git diff --binary > "$out.patch" 2>/dev/null

  python3 - "$GOVIO_WT" "$out.json" <<'PY'
import hashlib, json, sys
from pathlib import Path

wt = Path(sys.argv[1])
out = Path(sys.argv[2])

records = []
skip = {".git", "node_modules", ".next", "dist", "build", ".turbo", ".vercel"}

for p in sorted(wt.rglob("*")):
    if any(part in skip for part in p.parts):
        continue
    if not p.is_file() or p.is_symlink():
        continue
    rel = str(p.relative_to(wt))
    if not rel.startswith(("apps/", "packages/")):
        continue
    try:
        data = p.read_bytes()
    except OSError:
        continue
    records.append({
        "path": rel,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    })

out.write_text(json.dumps({"count": len(records), "files": records},
                          indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"SNAPSHOT_FILES={len(records)}")
PY
}

# Compara dois snapshots. Nunca corrige nada, so relata.
g::snapshot_diff() {
  python3 - "$1.json" "$2.json" <<'PY'
import json, sys

def load(p):
    d = json.load(open(p, encoding="utf-8"))
    return {f["path"]: f["sha256"] for f in d["files"]}

a, b = load(sys.argv[1]), load(sys.argv[2])

removed = sorted(set(a) - set(b))
added   = sorted(set(b) - set(a))
changed = sorted(p for p in set(a) & set(b) if a[p] != b[p])

print(f"SOURCE_FILES_REMOVED={len(removed)}")
print(f"SOURCE_FILES_ADDED={len(added)}")
print(f"SOURCE_FILES_CHANGED={len(changed)}")

for p in removed[:40]: print(f"REMOVED={p}")
for p in added[:40]:   print(f"ADDED={p}")
for p in changed[:40]: print(f"CHANGED={p}")

print("SOURCE_MUTATION=" + ("YES" if (removed or added or changed) else "ZERO"))
PY
}

# ---------------------------------------------------------------- execucao

# g::run <label> <watchdog_s> <workdir> -- <cmd...>
# Executa em subshell com watchdog. Captura rc/stdout/stderr na evidencia.
# NUNCA mata o shell pai. NUNCA faz retry automatico.
g::run() {
  local label="$1" watchdog="$2" workdir="$3"; shift 3
  [ "${1:-}" = "--" ] && shift

  local out="$GOVIO_EVIDENCE/$label.stdout"
  local err="$GOVIO_EVIDENCE/$label.stderr"
  local rcf="$GOVIO_EVIDENCE/$label.rc"

  printf '\nEXEC_BEGIN label=%s watchdog=%ss cwd=%s\n' "$label" "$watchdog" "$workdir"
  printf 'EXEC_CMD=%s\n' "$*"

  (
    cd "$workdir" 2>/dev/null || exit 125
    if g::have timeout; then
      timeout --signal=TERM --kill-after=15s "${watchdog}s" "$@"
    else
      "$@"
    fi
  ) >"$out" 2>"$err"

  local rc=$?
  printf '%s\n' "$rc" > "$rcf"

  local ob eb
  ob="$(wc -c < "$out")"; eb="$(wc -c < "$err")"

  if [ "$ob" -gt "$GOVIO_MAX_OUTPUT_BYTES" ] || [ "$eb" -gt "$GOVIO_MAX_OUTPUT_BYTES" ]; then
    printf 'OUTPUT_CIRCUIT_BREAKER=TRIPPED stdout=%s stderr=%s\n' "$ob" "$eb"
  fi

  printf 'EXEC_RC=%s stdout_bytes=%s stderr_bytes=%s\n' "$rc" "$ob" "$eb"
  printf 'EXEC_END label=%s\n\n' "$label"

  GOVIO_LAST_RC="$rc"
  GOVIO_LAST_STDOUT="$out"
  GOVIO_LAST_STDERR="$err"
  return 0
}

# Mostra as ultimas N linhas de um arquivo, com rotulo.
g::tail() {
  local file="$1" n="${2:-80}"
  [ -f "$file" ] || return 0
  printf -- '--- %s (ultimas %s linhas) ---\n' "$(basename "$file")" "$n"
  tail -n "$n" -- "$file"
  printf -- '--- fim ---\n'
}

# ---------------------------------------------------------------- diagnostico TS

# Extrai diagnosticos TypeScript de stdout+stderr para JSON + linhas legiveis.
g::ts_diagnostics() {
  local out="$1" err="$2" json="$3"
  python3 - "$out" "$err" "$json" <<'PY'
import json, re, sys
from pathlib import Path

def read(p):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

text = read(sys.argv[1]) + "\n" + read(sys.argv[2])

rx = re.compile(
    r"^(?P<file>\S.*?)\((?P<line>\d+),(?P<col>\d+)\): "
    r"error (?P<code>TS\d+): (?P<msg>.*)$",
    flags=re.M,
)

recs = [{
    "file": m.group("file"),
    "line": int(m.group("line")),
    "column": int(m.group("col")),
    "code": m.group("code"),
    "message": m.group("msg"),
} for m in rx.finditer(text)]

Path(sys.argv[3]).write_text(
    json.dumps({"count": len(recs), "records": recs}, indent=2, sort_keys=True) + "\n",
    encoding="utf-8")

print(f"TS_DIAGNOSTICS={len(recs)}")
for i, r in enumerate(recs, 1):
    print(f"TS[{i}] {r['file']}:{r['line']}:{r['column']} {r['code']} {r['message']}")
PY
}

# ---------------------------------------------------------------- encerramento

g::finish() {
  local state="$1" next="$2"
  printf '\n'
  g::hr
  printf 'FINAL_STATE=%s\n' "$state"
  printf 'NEXT_ACTION=%s\n' "$next"
  printf 'HEAD=%s\n' "$(g::head_sha)"
  printf 'PATCH_SHA=%s\n' "$(g::patch_sha)"
  printf 'GIT_RESET=ZERO GIT_CLEAN=ZERO GIT_RESTORE=ZERO GIT_CHECKOUT_DESTRUTIVO=ZERO\n'
  printf 'AUTOMATIC_ROLLBACK=NO AUTOMATIC_RETRY=NO\n'
  printf 'EVIDENCE=%s\n' "$GOVIO_EVIDENCE"
  printf 'TERMINAL_PARENT_SHELL=ALIVE\n'
  g::hr
}
