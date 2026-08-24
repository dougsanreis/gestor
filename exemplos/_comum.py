"""Preparação compartilhada pelos exemplos.

Faz duas coisas, ambas para que rodar um exemplo seja sempre seguro:

1. Coloca o núcleo no ``sys.path`` sem precisar instalar nada.
2. Aponta o estado da SYRA (memória de falhas, registro de produtos) para um
   diretório temporário, descartado ao fim.

O segundo ponto importa: um exemplo que escreve no estado real da sua máquina é
um exemplo que você só pode rodar uma vez, e que polui a memória de falhas com
defeitos que nunca existiram.
"""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

_TEMP = tempfile.mkdtemp(prefix="syra-exemplo-")
os.environ["SYRA_STATE_ROOT"] = str(Path(_TEMP) / "state")
os.environ["SYRA_EVIDENCE_ROOT"] = str(Path(_TEMP) / "evidence")

atexit.register(lambda: shutil.rmtree(_TEMP, ignore_errors=True))

TEMP = Path(_TEMP)


def titulo(texto: str) -> None:
    print()
    print("=" * 72)
    print(texto)
    print("=" * 72)


def passo(numero: int, texto: str) -> None:
    print()
    print("[{}] {}".format(numero, texto))
    print("-" * 72)


def licao(texto: str) -> None:
    print()
    print(">> LIÇÃO: {}".format(texto))
