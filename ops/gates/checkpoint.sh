#!/usr/bin/env bash
# GATE: checkpoint
#
# Prioridade ZERO. Antes de qualquer analise, typecheck, build ou deploy:
# transformar trabalho nao commitado em historia git recuperavel.
#
# Doutrina: um commit custa 200ms e sobrevive a qualquer erro humano ou de
# agente. Um sistema de evidencias com SHA-256 custa horas e NAO impediu que
# um `git clean` apagasse 8 arquivos neste projeto.
#
# Este gate NUNCA usa reset/clean/restore/checkout. So adiciona e commita.

# shellcheck source=../lib/guard.sh
. "$GOVIO_LIB/guard.sh"

g::head "CHECKPOINT — rede de seguranca antes de tudo"
g::init "checkpoint" || exit 0

BRANCH_NOW="$(g::git rev-parse --abbrev-ref HEAD 2>/dev/null || echo DETACHED)"
CKPT_BRANCH="govio/checkpoint-$(date -u +%Y%m%dT%H%M%SZ)"

g::kv BRANCH_ATUAL "$BRANCH_NOW"

DIRTY="$(g::git status --porcelain=v1 | wc -l | tr -d ' ')"
g::kv ARQUIVOS_PENDENTES "$DIRTY"

if [ "$DIRTY" -eq 0 ]; then
  g::say "NADA_A_SALVAR=YES  (worktree limpo)"
  g::finish "CHECKPOINT_NOOP" "govio doctor"
  exit 0
fi

g::say ""
g::say "=== O QUE SERA PRESERVADO ==="
g::git status --porcelain=v1

# 1) Bundle fisico primeiro: funciona mesmo se o commit falhar.
BUNDLE="$GOVIO_EVIDENCE/worktree-snapshot.tar.gz"
g::say ""
g::say "Criando snapshot fisico (independente do git)..."
tar -czf "$BUNDLE" \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='.next' \
  --exclude='.turbo' \
  --exclude='.vercel' \
  --exclude='dist' \
  -C "$GOVIO_WT" apps packages 2>/dev/null

if [ -f "$BUNDLE" ]; then
  g::kv SNAPSHOT_TARBALL "$BUNDLE"
  g::kv SNAPSHOT_BYTES   "$(wc -c < "$BUNDLE")"
  g::kv SNAPSHOT_SHA256  "$(g::sha "$BUNDLE")"
else
  g::say "AVISO: snapshot fisico falhou; seguindo para o commit mesmo assim."
fi

# 2) Commit em branch nova. Nao mexe na branch atual, nao reescreve historia.
g::say ""
g::say "Criando branch de checkpoint: $CKPT_BRANCH"

if ! g::git switch -c "$CKPT_BRANCH" >/dev/null 2>&1; then
  g::say "Nao foi possivel criar branch; commitando na branch atual (sem reescrever nada)."
  CKPT_BRANCH="$BRANCH_NOW"
fi

g::git add -A -- apps packages 2>/dev/null || g::git add -A

g::git -c user.name="govio-ops" \
       -c user.email="ops@govio.local" \
       commit --no-verify -m "checkpoint: landing CMS + team panel (work in progress)

Preserva trabalho nao commitado antes de typecheck/build/deploy.
Gerado por: govio checkpoint" >/dev/null 2>&1

CKPT_SHA="$(g::head_sha)"

g::say ""
g::kv CHECKPOINT_BRANCH "$CKPT_BRANCH"
g::kv CHECKPOINT_COMMIT "$CKPT_SHA"
g::kv ARQUIVOS_NO_COMMIT "$(g::git show --stat --oneline "$CKPT_SHA" | tail -n 1)"

g::say ""
g::say "A partir de agora, QUALQUER perda e recuperavel com:"
g::say "  git -C $GOVIO_WT checkout $CKPT_BRANCH"
g::say "  # ou: tar -xzf $BUNDLE -C <destino>"
g::say ""
g::say "Voce esta agora na branch $CKPT_BRANCH."
g::say "Para voltar a anterior sem perder nada: git -C $GOVIO_WT switch $BRANCH_NOW"

g::finish "CHECKPOINT_CRIADO" "govio doctor"
exit 0
