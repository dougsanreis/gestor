#!/usr/bin/env bash
#
# VERIFICAR.sh — prova, em um comando, que este pacote funciona nesta máquina.
#
# Roda tudo que pode ser verificado sem tocar em nada seu:
#
#   1. o interpretador serve
#   2. o núcleo compila (SYRA-RULE-PPC-001)
#   3. os 201 testes passam
#   4. os 5 exemplos rodam
#   5. um produto novo é gerado, boota e passa nos próprios testes
#   6. os gates rodam contra um repositório git de verdade
#
# Nada escreve fora de um diretório temporário, que é apagado no fim. Rode
# quantas vezes quiser.
#
# Saída final:  VERIFICACAO_FINAL=PASS  ou  VERIFICACAO_FINAL=FAIL
# Código de saída: 0 em PASS, 1 em FAIL.

set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$RAIZ"

TEMP="$(mktemp -d -t syra-verificar-XXXXXX)"
trap 'rm -rf "$TEMP"' EXIT

# Isola o estado: a verificação nunca escreve na memória de falhas nem na
# evidência reais.
export SYRA_STATE_ROOT="$TEMP/state"
export SYRA_EVIDENCE_ROOT="$TEMP/evidence"

PASSOU=0
FALHOU=0
LOG="$TEMP/saida.log"

cabecalho() {
    printf '\n%s\n' "========================================================================"
    printf '%s\n'   "$1"
    printf '%s\n'   "========================================================================"
}

etapa() {
    local nome="$1"
    shift
    printf '%-52s' "  $nome"
    if "$@" >"$LOG" 2>&1; then
        printf 'PASS\n'
        PASSOU=$((PASSOU + 1))
        return 0
    fi
    printf 'FAIL\n'
    FALHOU=$((FALHOU + 1))
    printf '\n    ---- saída da falha ----\n'
    sed 's/^/    /' "$LOG" | tail -25
    printf '    ------------------------\n\n'
    return 1
}

# ---------------------------------------------------------------------------
cabecalho "SYRA CORE — VERIFICAÇÃO COMPLETA"

PY="$(command -v python3 || true)"
if [[ -z "$PY" ]]; then
    echo "  python3 não encontrado no PATH."
    echo
    echo "VERIFICACAO_FINAL=FAIL"
    echo "MOTIVO=PYTHON3_AUSENTE"
    exit 1
fi

echo "  python3 : $("$PY" --version 2>&1)"
echo "  git     : $(command -v git >/dev/null && git --version || echo 'AUSENTE (gates ficarão indisponíveis)')"
echo "  raiz    : $RAIZ"

# ---------------------------------------------------------------------------
cabecalho "1/6  AMBIENTE"

etapa "versão mínima do Python (3.8+)" \
    "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'

etapa "núcleo importa sem dependência externa" \
    "$PY" -c 'import sys; sys.path.insert(0, "."); import syra_core; print(syra_core.CORE_VERSION)'

# ---------------------------------------------------------------------------
cabecalho "2/6  PREFLIGHT (SYRA-RULE-PPC-001)"

etapa "o núcleo valida a si mesmo" ./syra preflight

# ---------------------------------------------------------------------------
cabecalho "3/6  SUÍTE DE TESTES"

etapa "testes do núcleo" "$PY" -m unittest discover -s tests -t . -b

# ---------------------------------------------------------------------------
cabecalho "4/6  EXEMPLOS"

for exemplo in exemplos/0*.py; do
    etapa "$(basename "$exemplo")" "$PY" "$exemplo"
done

# ---------------------------------------------------------------------------
cabecalho "5/6  FACTORY — produto gerado do zero"

for tipo in tool agent platform; do
    destino="$TEMP/prod-$tipo"
    etapa "gerar e verificar tipo '$tipo'" \
        ./syra product new "verif-$tipo" --kind "$tipo" --into "$destino"
done

etapa "produto gerado reporta readiness" \
    ./syra product readiness "$TEMP/prod-tool"

# ---------------------------------------------------------------------------
cabecalho "6/6  GATES — contra um repositório git real"

if command -v git >/dev/null 2>&1; then
    WS="$TEMP/workspace/app"
    mkdir -p "$WS/src"
    printf 'class CircuitBreaker:\n    pass\n' > "$WS/src/breaker.py"
    (
        cd "$WS"
        git init -q -b main
        git add -A
        git -c user.email=verificar@local -c user.name=Verificar commit -qm inicial
    ) >/dev/null 2>&1

    etapa "resolução de autoridade de fonte" \
        ./syra authority --root "$TEMP/workspace"

    etapa "PPC-00A — descoberta com evidência selada" \
        ./syra scan --root "$TEMP/workspace"

    etapa "PPC-00B — tabela de decisão" \
        ./syra decide --root "$TEMP/workspace"
else
    echo "  git ausente — etapas de gate puladas (o núcleo funciona sem elas)"
fi

# ---------------------------------------------------------------------------
cabecalho "RESULTADO"

echo "  ETAPAS_PASSOU=$PASSOU"
echo "  ETAPAS_FALHOU=$FALHOU"
echo

if [[ "$FALHOU" -eq 0 ]]; then
    echo "VERIFICACAO_FINAL=PASS"
    echo
    echo "O núcleo está pronto para plugar. Próximo passo:"
    echo "  ./syra decide --root ~/Projects/SYRA"
    exit 0
fi

echo "VERIFICACAO_FINAL=FAIL"
echo
echo "Etapas com falha estão acima, com a saída completa. Nada foi instalado"
echo "nem alterado na sua máquina — pode corrigir e rodar de novo."
exit 1
