#!/usr/bin/env bash
# GATE: apply <manifest.json>
#
# Aplica N patches minimos em UMA transacao, com CAS por arquivo.
#
# Doutrina: manter o que o agente anterior fez BEM (CAS + replace atomico +
# fsync + diff exato) e remover o que fez MAL (um gate por linha alterada,
# rollback destrutivo em falha).
#
# Semantica transacional:
#   - Verifica CAS de TODOS os arquivos ANTES de escrever qualquer um.
#   - Se qualquer CAS falhar: aborta sem escrever nada. Worktree intacto.
#   - Se escrever parcialmente e falhar no meio: restaura APENAS os arquivos
#     que este gate escreveu, a partir do pre-imagem que ele proprio guardou.
#     Nunca `git checkout`, nunca `git clean`, nunca toca em nada alheio.
#
# Formato do manifest:
# { "patches": [ { "path": "apps/web/lib/x.ts",
#                  "expectSha256": "<sha do arquivo ATUAL>",
#                  "find": "<texto exato>", "replace": "<texto exato>",
#                  "occurrences": 1 } ] }
# Alternativa por arquivo inteiro: { "path": ..., "expectSha256": ..., "contentB64": "..." }

# shellcheck source=../lib/guard.sh
. "$GOVIO_LIB/guard.sh"

MANIFEST="${1:-}"

g::head "APPLY — patch transacional com CAS"
g::init "apply" || exit 0

if [ -z "$MANIFEST" ] || [ ! -f "$MANIFEST" ]; then
  g::fail "MANIFEST_NAO_ENCONTRADO:${MANIFEST:-<vazio>}"
  g::say "uso: govio apply /caminho/patches.json"
  g::finish "APPLY_ABORTADO" "govio doctor"
  exit 0
fi

g::kv MANIFEST     "$MANIFEST"
g::kv MANIFEST_SHA "$(g::sha "$MANIFEST")"

PREIMAGE="$GOVIO_EVIDENCE/preimage"
mkdir -p "$PREIMAGE"

g::snapshot "$GOVIO_EVIDENCE/before" >/dev/null 2>&1

python3 - "$MANIFEST" "$GOVIO_WT" "$PREIMAGE" "$GOVIO_EVIDENCE" <<'PY'
import base64, hashlib, json, os, shutil, stat, sys, tempfile
from pathlib import Path

manifest, wt, preimage, evidence = (Path(a) for a in sys.argv[1:5])
spec = json.loads(manifest.read_text(encoding="utf-8"))
patches = spec.get("patches", [])

def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

print(f"PATCHES_NO_MANIFEST={len(patches)}")
if not patches:
    print("NADA_A_APLICAR=YES")
    raise SystemExit(0)

# ---- FASE 1: validar TUDO antes de escrever qualquer coisa ----------------
plan = []
for i, p in enumerate(patches, 1):
    rel = p["path"]
    target = wt / rel

    if target.is_symlink():
        print(f"FAIL_CLOSED=ALVO_E_SYMLINK:{rel}", file=sys.stderr); raise SystemExit(1)
    if not target.is_file():
        print(f"FAIL_CLOSED=ALVO_INEXISTENTE:{rel}", file=sys.stderr); raise SystemExit(1)

    current = target.read_bytes()
    cur_sha = sha(current)

    if p.get("expectSha256") and p["expectSha256"] != cur_sha:
        print(f"FAIL_CLOSED=CAS_DIVERGENTE:{rel}", file=sys.stderr)
        print(f"  esperado={p['expectSha256']}", file=sys.stderr)
        print(f"  atual   ={cur_sha}", file=sys.stderr)
        raise SystemExit(1)

    if "contentB64" in p:
        new = base64.b64decode(p["contentB64"])
        mode = "REESCRITA_INTEGRAL"
    else:
        text = current.decode("utf-8")
        find, repl = p["find"], p["replace"]
        want = int(p.get("occurrences", 1))
        got = text.count(find)
        if got != want:
            print(f"FAIL_CLOSED=OCORRENCIAS_INESPERADAS:{rel} "
                  f"esperado={want} encontrado={got}", file=sys.stderr)
            raise SystemExit(1)
        if p.get("forbidIfPresent") and p["forbidIfPresent"] in text:
            print(f"FAIL_CLOSED=PATCH_JA_APLICADO:{rel}", file=sys.stderr)
            raise SystemExit(1)
        new = text.replace(find, repl, want).encode("utf-8")
        mode = "SUBSTITUICAO_EXATA"

    if new == current:
        print(f"FAIL_CLOSED=PATCH_SEM_EFEITO:{rel}", file=sys.stderr); raise SystemExit(1)

    # Recusa supressao de type-safety introduzida pelo patch.
    added = new.decode("utf-8", "replace")
    for banned in ("@ts-ignore", "@ts-expect-error", " as any", ": any"):
        if added.count(banned) > current.decode("utf-8", "replace").count(banned):
            print(f"FAIL_CLOSED=SUPRESSAO_DE_TIPO_PROIBIDA:{rel}:{banned}", file=sys.stderr)
            raise SystemExit(1)

    plan.append({"rel": rel, "target": target, "old": current, "new": new,
                 "oldSha": cur_sha, "newSha": sha(new), "mode": mode})
    print(f"VALIDADO[{i}] {rel} {mode} {cur_sha[:12]} -> {sha(new)[:12]}")

print("FASE1_VALIDACAO=PASS  (nenhuma escrita realizada ainda)")

# ---- FASE 2: pre-imagem em disco -----------------------------------------
for item in plan:
    dst = preimage / item["rel"].replace("/", "__")
    dst.write_bytes(item["old"])
print(f"PREIMAGEM_GRAVADA={len(plan)}")

# ---- FASE 3: escrita atomica ---------------------------------------------
written = []
try:
    for item in plan:
        t = item["target"]
        if sha(t.read_bytes()) != item["oldSha"]:
            raise RuntimeError(f"ALVO_MUDOU_ANTES_DA_ESCRITA:{item['rel']}")

        mode = stat.S_IMODE(t.stat().st_mode)
        fd, tmpname = tempfile.mkstemp(prefix=".govio-apply.", dir=str(t.parent))
        tmp = Path(tmpname)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(item["new"]); f.flush(); os.fsync(f.fileno())
            os.chmod(tmp, mode)
            os.replace(tmp, t)
            dfd = os.open(t.parent, os.O_RDONLY)
            try: os.fsync(dfd)
            finally: os.close(dfd)
        finally:
            if tmp.exists(): tmp.unlink()

        if sha(t.read_bytes()) != item["newSha"]:
            raise RuntimeError(f"SHA_POS_ESCRITA_DIVERGENTE:{item['rel']}")

        written.append(item)
        print(f"APLICADO {item['rel']} -> {item['newSha'][:12]}")

except Exception as exc:
    # Rollback CIRURGICO: apenas o que ESTE gate escreveu, do pre-imagem proprio.
    print(f"FAIL_CLOSED={exc}", file=sys.stderr)
    print("ROLLBACK_CIRURGICO=INICIANDO (apenas arquivos escritos por este gate)",
          file=sys.stderr)
    for item in written:
        item["target"].write_bytes(item["old"])
        print(f"  restaurado {item['rel']}", file=sys.stderr)
    print("ROLLBACK_CIRURGICO=CONCLUIDO  GIT_CLEAN=ZERO  GIT_RESET=ZERO", file=sys.stderr)
    raise SystemExit(1)

# ---- FASE 4: relatorio ----------------------------------------------------
report = {"applied": [{"path": i["rel"], "preSha256": i["oldSha"],
                       "postSha256": i["newSha"], "mode": i["mode"]} for i in plan]}
(evidence / "applied.json").write_text(
    json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

print(f"APLICADOS_COM_SUCESSO={len(plan)}")
PY

APPLY_RC=$?

g::say ""
if [ "$APPLY_RC" -ne 0 ]; then
  g::say "Nenhuma mudanca parcial permanece. Worktree consistente."
  g::finish "APPLY_ABORTADO_SEM_DANO" "corrigir manifest e repetir"
  exit 0
fi

g::say "### DIFF RESULTANTE"
g::git diff --stat 2>/dev/null | tail -20

g::snapshot "$GOVIO_EVIDENCE/after" >/dev/null 2>&1
g::say ""
g::say "### DELTA DE ARQUIVOS (deve mostrar apenas CHANGED, nunca REMOVED)"
g::snapshot_diff "$GOVIO_EVIDENCE/before" "$GOVIO_EVIDENCE/after"

g::finish "PATCHES_APLICADOS" "govio doctor  (re-verificar em batch)"
exit 0
