#!/usr/bin/env bash
# Teste de fumaça do starter: gera mídia sintética numa cópia isolada do projeto e confere
# preflight, validação, preview, render final, versionamento e as recusas esperadas.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp -r "$HERE/scripts" "$HERE/edit-plan.example.json" "$WORK/"
mkdir -p "$WORK/media"
cd "$WORK"

ffmpeg -nostdin -v error -f lavfi -i testsrc2=size=1280x720:rate=30 -f lavfi -i sine=frequency=440 \
  -t 20 -c:v libx264 -preset ultrafast -c:a aac -shortest media/source.mp4

fail() { echo "FALHOU: $*" >&2; exit 1; }
expect_error() { # descrição, json do plano
  echo "$2" > bad.json
  if python3 -I scripts/render_edl.py bad.json --validate-only >/dev/null 2>&1; then fail "deveria recusar: $1"; fi
  echo "ok (recusado): $1"
}

python3 -I scripts/media_preflight.py media/source.mp4 >/dev/null
cp edit-plan.example.json edit-plan.json
python3 -I scripts/render_edl.py edit-plan.json --validate-only >/dev/null
python3 -I scripts/render_edl.py edit-plan.json --preview --job ci >/dev/null
python3 -I scripts/render_edl.py edit-plan.json --job ci >/dev/null
for p in landscape vertical square; do
  test -s "exports/ci/source_$p.mp4" || fail "export $p ausente"
  test -s "exports/ci-preview/source_$p.mp4" || fail "preview $p ausente"
done
test -s exports/ci/report.json || fail "report.json ausente"
python3 -I - <<'PY'
import json
r = json.load(open("exports/ci/report.json"))
dims = {o["profile"]: (o["width"], o["height"]) for o in r["outputs"]}
assert dims == {"landscape": (1920, 1080), "vertical": (1080, 1920), "square": (1080, 1080)}, dims
assert all(abs(o["duration_seconds"] - 11.3) < 0.35 for o in r["outputs"]), r["outputs"]
assert all(len(o["sha256"]) == 64 for o in r["outputs"])
PY
echo "ok: render final, preview e report.json"

if python3 -I scripts/render_edl.py edit-plan.json --job ci >/dev/null 2>&1; then fail "deveria recusar job existente"; fi
echo "ok (recusado): job existente não é sobrescrito"

expect_error "caminho fora do workspace" '{"version":1,"source":"../x.mp4","fps":30,"fit":"cover","profiles":["square"],"segments":[{"start":0,"end":1}]}'
expect_error "intervalo invertido" '{"version":1,"source":"media/source.mp4","fps":30,"fit":"cover","profiles":["square"],"segments":[{"start":3,"end":2}]}'
expect_error "fim após a duração" '{"version":1,"source":"media/source.mp4","fps":30,"fit":"cover","profiles":["square"],"segments":[{"start":3,"end":25}]}'
expect_error "fps não inteiro" '{"version":1,"source":"media/source.mp4","fps":29.97,"fit":"cover","profiles":["square"],"segments":[{"start":0,"end":1}]}'
expect_error "perfil desconhecido" '{"version":1,"source":"media/source.mp4","fps":30,"fit":"cover","profiles":["4x5"],"segments":[{"start":0,"end":1}]}'
echo "smoke test do starter: tudo ok"
