#!/usr/bin/env python3
"""Gera o evidence bundle de uma tarefa executando as validacoes de verdade.

Uso:
    python3 scripts/gerar_evidencia.py VF-0001 "descricao curta"

Nao aceita resultado digitado a mao: cada comando e executado, o exit code
real e capturado e o manifest e selado com hash do proprio conteudo.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from syra.vfos.evidence import EvidenceBundle  # noqa: E402

COMANDOS = [
    "python3 -m pytest tests/ -q --no-header -p no:cacheprovider",
    "python3 scripts/validate_pack.py",
    "python3 scripts/test_hooks.py",
]

CONTRATOS = [
    "mission", "event", "governance-decision", "artifact", "claim",
    "experiment", "learning-candidate",
]


def commit_atual() -> str:
    """SHA do commit corrente, ou vazio quando indisponivel."""
    try:
        processo = subprocess.run(["git", "rev-parse", "HEAD"], cwd=RAIZ,
                                  capture_output=True, text=True, check=False)
        return processo.stdout.strip()
    except OSError:
        return ""


def arquivos_alterados() -> list[str]:
    """Arquivos versionados sob o pacote implementado."""
    processo = subprocess.run(["git", "ls-files", "syra/vfos", "tests"], cwd=RAIZ,
                              capture_output=True, text=True, check=False)
    return [linha for linha in processo.stdout.splitlines() if linha]


def main(argv: list[str]) -> int:
    """Executa as validacoes e sela o manifest da tarefa."""
    task_id = argv[1] if len(argv) > 1 else "VF-0000"
    riscos = argv[2:] or ["adapter PostgreSQL ainda nao implementado",
                          "Model Router e Tool Gateway pertencem a Fase 1"]

    bundle = EvidenceBundle(task_id=task_id, commit=commit_atual())
    bundle.changed_files = arquivos_alterados()
    bundle.contracts_usados = CONTRATOS
    bundle.residual_risks = riscos

    for comando in COMANDOS:
        registro = bundle.registrar_comando(comando, cwd=str(RAIZ))
        estado = "OK" if registro["exit_code"] == 0 else "FALHA"
        print(f"  {estado:5} exit={registro['exit_code']:<3} {comando}")

    for caminho in sorted(RAIZ.glob("contracts/*.json")):
        bundle.registrar_artefato(caminho)

    destino = RAIZ / "docs" / "evidence" / task_id / "manifest.json"
    caminho = bundle.selar(destino)

    print()
    print(f"comandos verdes : {bundle.comandos_verdes}")
    print(f"arquivos        : {len(bundle.changed_files)}")
    print(f"artefatos       : {len(bundle.artifacts)}")
    print(f"manifest        : {caminho}")
    return 0 if bundle.comandos_verdes else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
