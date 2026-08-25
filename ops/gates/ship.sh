#!/usr/bin/env bash
# GATE: ship preview|production
#
# Doutrina: um guardrail sem caminho autorizado para producao nao e guardrail,
# e um bloqueio permanente. Este projeto fez ~10 deploys de preview e ZERO
# promocoes; govio.com.br nunca mudou. Producao aqui e explicita, com
# confirmacao humana, mas EXISTE.
#
# preview    -> deploy de preview + URL COM bypass de Deployment Protection
# production -> exige confirmacao digitada; promove e mostra o alias

# shellcheck source=../lib/guard.sh
. "$GOVIO_LIB/guard.sh"

MODE="${1:-preview}"
APP="${2:-all}"

g::head "SHIP — $MODE ($APP)"
g::init "ship-$MODE-$APP" || exit 0

g::have vercel || { g::fail "VERCEL_CLI_AUSENTE"; g::finish "SHIP_ABORTADO" "instalar vercel cli"; exit 0; }

SCOPE="${GOVIO_SCOPE:-govio-br}"
case "$APP" in
  web)  LIST="govio-core:prj_RAXgN8Z8tnmCcxwQNN0XFXlf5Idi" ;;
  team) LIST="govio-equipe:prj_cp21AfbzgKAasO7jUta8OMP1m6pW" ;;
  all)  LIST="govio-core:prj_RAXgN8Z8tnmCcxwQNN0XFXlf5Idi govio-equipe:prj_cp21AfbzgKAasO7jUta8OMP1m6pW" ;;
  *)    g::fail "APP_INVALIDO:$APP"; g::finish "SHIP_ABORTADO" "govio ship preview all"; exit 0 ;;
esac

if [ "$MODE" = "production" ]; then
  g::say ""
  g::say "!!! DEPLOY DE PRODUCAO !!!"
  g::say "Isso altera o que os socios e as prefeituras veem em govio.com.br."
  g::say ""
  printf 'Digite exatamente PROMOVER para continuar: '
  read -r CONFIRM
  if [ "$CONFIRM" != "PROMOVER" ]; then
    g::say "Confirmacao ausente. Nada foi promovido."
    g::finish "PRODUCAO_NAO_CONFIRMADA" "govio ship preview $APP"
    exit 0
  fi
fi

for entry in $LIST; do
  NAME="${entry%%:*}"; PID="${entry##*:}"
  g::say ""
  g::say ">>> $NAME ($PID)"

  # Deploy sempre a partir da RAIZ do monorepo: o Root Directory ja esta
  # configurado no projeto Vercel. Passar apps/web aqui gera apps/web/apps/web.
  if [ "$MODE" = "production" ]; then
    g::run "deploy-$NAME" 900 "$GOVIO_WT" -- \
      env VERCEL_PROJECT_ID="$PID" vercel deploy --prod --yes --scope "$SCOPE"
  else
    g::run "deploy-$NAME" 900 "$GOVIO_WT" -- \
      env VERCEL_PROJECT_ID="$PID" vercel deploy --yes --scope "$SCOPE"
  fi

  if [ "$GOVIO_LAST_RC" -ne 0 ]; then
    g::kv "DEPLOY_$NAME" "FAIL(rc=$GOVIO_LAST_RC)"
    g::tail "$GOVIO_LAST_STDERR" 40
    continue
  fi

  URL="$(grep -oE 'https://[a-z0-9.-]+\.vercel\.app' "$GOVIO_LAST_STDOUT" | tail -n 1)"
  g::kv "DEPLOY_$NAME" "PASS"
  g::kv "URL_$NAME"    "$URL"

  # Prova de que a URL responde COMO A APLICACAO, nao como interstitial da Vercel.
  if [ -n "$URL" ]; then
    g::say ""
    g::say "Verificando proveniencia da resposta (app real vs. interstitial Vercel)..."
    BODY="$GOVIO_EVIDENCE/probe-$NAME.html"

    if [ "$MODE" = "preview" ]; then
      # Preview fica atras de Deployment Protection: gera bypass para o UAT.
      (cd "$GOVIO_WT" && timeout 90s vercel curl "$URL" --scope "$SCOPE" \
        -sS -D "$GOVIO_EVIDENCE/probe-$NAME.headers" -o "$BODY") >/dev/null 2>&1
    else
      curl -sS -m 60 -D "$GOVIO_EVIDENCE/probe-$NAME.headers" -o "$BODY" "$URL" >/dev/null 2>&1
    fi

    python3 - "$BODY" "$GOVIO_EVIDENCE/probe-$NAME.headers" <<'PY'
import re, sys
from pathlib import Path

def read(p):
    try: return Path(p).read_text(encoding="utf-8", errors="replace")
    except OSError: return ""

body, headers = read(sys.argv[1]), read(sys.argv[2])
status = "?"
m = re.search(r"HTTP/[\d.]+ (\d{3})", headers)
if m: status = m.group(1)

title = ""
t = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
if t: title = t.group(1).strip()

vercel_wall = ("Login – Vercel" in title or "vercel.com/sso-api" in body
               or "_vercel_sso_nonce" in body)

print(f"HTTP_STATUS={status}")
print(f"TITLE={title[:80]}")
print("PROVENIENCIA=" + ("INTERSTITIAL_VERCEL" if vercel_wall else "APLICACAO_GOVIO"))
if vercel_wall:
    print("AVISO=Nao asserte conteudo do produto sobre esta resposta.")
    print("      E a parede de protecao da Vercel, nao a landing page.")
elif status.startswith("5"):
    print("CLASSIFICACAO=ERRO_DE_RUNTIME_DA_APLICACAO")
    print("      Causa mais provavel: validacao de env eager no boot do modulo.")
elif status == "200":
    print("CLASSIFICACAO=APLICACAO_RESPONDENDO")
PY
  fi
done

if [ "$MODE" = "production" ]; then
  g::say ""
  g::say "### ALIASES DE PRODUCAO"
  (cd "$GOVIO_WT" && timeout 60s vercel alias ls --scope "$SCOPE" 2>&1 | head -20)
  g::finish "PRODUCAO_PROMOVIDA" "validar https://govio.com.br/ e https://govio.com.br/login"
else
  g::finish "PREVIEW_PUBLICADO" "UAT no preview -> govio ship production <app>"
fi
exit 0
