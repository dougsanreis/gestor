"""QA: executa a suite de testes de verdade e mede cada teste.

Nao existe "provavelmente passa". O projeto gerado e escrito em disco e a
suite roda num subprocesso isolado. Um plugin minimo de pytest registra
``nodeid``, resultado e duracao de cada teste, o que alimenta tanto a decisao
de governanca quanto a camada de inteligencia de testes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from syra.contracts import GeneratedProject, QAReport, TestOutcome

PLUGIN_NAME = "_syra_pytest_report"

PLUGIN_SOURCE = '''"""Plugin de relatorio da SYRA: grava resultado e duracao por teste."""

import json
import os

_RESULTADOS = {}


def pytest_runtest_logreport(report):
    """Acumula o resultado final e a duracao total de cada teste."""
    registro = _RESULTADOS.setdefault(
        report.nodeid, {"nodeid": report.nodeid, "status": "passed",
                        "duration": 0.0, "message": ""}
    )
    registro["duration"] += float(report.duration or 0.0)

    if report.when == "setup":
        if report.outcome == "skipped":
            registro["status"] = "skipped"
        elif report.outcome == "failed":
            registro["status"] = "error"
            registro["message"] = str(report.longrepr)[:2000]
    elif report.when == "call":
        if report.outcome == "failed":
            registro["status"] = "failed"
            registro["message"] = str(report.longrepr)[:2000]
        elif report.outcome == "skipped":
            registro["status"] = "skipped"
    elif report.when == "teardown" and report.outcome == "failed":
        if registro["status"] == "passed":
            registro["status"] = "error"
            registro["message"] = str(report.longrepr)[:2000]


def pytest_sessionfinish(session, exitstatus):
    """Escreve o relatorio JSON no caminho indicado pelo ambiente."""
    destino = os.environ.get("SYRA_PYTEST_REPORT")
    if not destino:
        return
    with open(destino, "w", encoding="utf-8") as arquivo:
        json.dump({"exitstatus": int(exitstatus),
                   "outcomes": list(_RESULTADOS.values())}, arquivo)
'''


def materialize(project: GeneratedProject, destino: Path) -> Path:
    """Escreve os arquivos do projeto em disco e devolve a raiz."""
    destino.mkdir(parents=True, exist_ok=True)
    for arquivo in project.files:
        caminho = destino / arquivo.path
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(arquivo.content, encoding="utf-8")
    return destino


class QAEngine:
    """Executa a suite do projeto gerado e devolve resultados medidos."""

    def __init__(self, timeout: float = 300.0) -> None:
        self.timeout = timeout

    def run(self, project_dir: Path, selected: list[str] | None = None) -> QAReport:
        """Roda a suite em ``project_dir``.

        Args:
            project_dir: raiz do projeto ja materializado.
            selected: subconjunto de ``nodeid`` a executar; ``None`` roda tudo.

        Returns:
            O relatorio real da execucao, inclusive quando ela falha.
        """
        if shutil.which("pytest") or _pytest_importavel():
            return self._run_pytest(project_dir, selected)
        return self._run_unittest(project_dir)

    def _run_pytest(self, project_dir: Path, selected: list[str] | None) -> QAReport:
        plugin_dir = Path(tempfile.mkdtemp(prefix="syra_plugin_"))
        (plugin_dir / f"{PLUGIN_NAME}.py").write_text(PLUGIN_SOURCE, encoding="utf-8")
        relatorio = plugin_dir / "report.json"

        ambiente = dict(os.environ)
        ambiente["SYRA_PYTEST_REPORT"] = str(relatorio)
        ambiente["PYTHONPATH"] = os.pathsep.join(
            [str(project_dir), str(plugin_dir), ambiente.get("PYTHONPATH", "")]
        ).strip(os.pathsep)
        # Impede que um pytest.ini ou conftest do repositorio hospedeiro
        # contamine a execucao do projeto gerado.
        ambiente["PYTEST_ADDOPTS"] = ""

        comando = [sys.executable, "-m", "pytest", "-p", PLUGIN_NAME,
                   "-q", "--no-header", "-p", "no:cacheprovider"]
        comando.extend(selected or ["tests"])

        inicio = time.perf_counter()
        try:
            processo = subprocess.run(  # noqa: S603 - comando fixo, sem shell
                comando, cwd=str(project_dir), env=ambiente,
                capture_output=True, text=True, timeout=self.timeout, check=False,
            )
            saida = processo.stdout + processo.stderr
        except subprocess.TimeoutExpired:
            duracao = time.perf_counter() - inicio
            return QAReport(runner="pytest", passed=0, failed=0, errors=1, skipped=0,
                            duration=duracao, outcomes=(TestOutcome(
                                nodeid="<suite>", status="error", duration=duracao,
                                message=f"suite excedeu {self.timeout}s"),),
                            raw_output="timeout")
        duracao = time.perf_counter() - inicio

        resultados: list[TestOutcome] = []
        if relatorio.exists():
            try:
                dados = json.loads(relatorio.read_text(encoding="utf-8"))
                resultados = [
                    TestOutcome(nodeid=o["nodeid"], status=o["status"],
                                duration=float(o["duration"]), message=o.get("message", ""))
                    for o in dados.get("outcomes", [])
                ]
            except (json.JSONDecodeError, KeyError, OSError):
                resultados = []
        shutil.rmtree(plugin_dir, ignore_errors=True)

        if not resultados and processo.returncode != 0:
            # Falha de coleta: o pytest nem chegou a rodar testes.
            resultados = [TestOutcome(nodeid="<coleta>", status="error",
                                      duration=duracao, message=saida[-2000:])]

        return self._consolidar("pytest", resultados, duracao, saida)

    def _run_unittest(self, project_dir: Path) -> QAReport:
        """Alternativa em stdlib quando pytest nao esta disponivel."""
        ambiente = dict(os.environ)
        ambiente["PYTHONPATH"] = os.pathsep.join(
            [str(project_dir), ambiente.get("PYTHONPATH", "")]
        ).strip(os.pathsep)

        inicio = time.perf_counter()
        processo = subprocess.run(  # noqa: S603 - comando fixo, sem shell
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=str(project_dir), env=ambiente, capture_output=True, text=True,
            timeout=self.timeout, check=False,
        )
        duracao = time.perf_counter() - inicio
        saida = processo.stdout + processo.stderr

        resultados = []
        for linha in saida.splitlines():
            if " ... " not in linha:
                continue
            nome, _, veredito = linha.partition(" ... ")
            estado = {"ok": "passed", "FAIL": "failed",
                      "ERROR": "error"}.get(veredito.strip(), "skipped")
            resultados.append(TestOutcome(nodeid=nome.strip(), status=estado,
                                          duration=0.0))
        return self._consolidar("unittest", resultados, duracao, saida)

    @staticmethod
    def _consolidar(runner: str, resultados: list[TestOutcome], duracao: float,
                    saida: str) -> QAReport:
        contagem = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
        for resultado in resultados:
            contagem[resultado.status] = contagem.get(resultado.status, 0) + 1
        return QAReport(
            runner=runner,
            passed=contagem["passed"],
            failed=contagem["failed"],
            errors=contagem["error"],
            skipped=contagem["skipped"],
            duration=duracao,
            outcomes=tuple(resultados),
            raw_output=saida[-8000:],
        )


def _pytest_importavel() -> bool:
    try:
        import pytest  # noqa: F401 - deteccao de disponibilidade
    except ImportError:
        return False
    return True
