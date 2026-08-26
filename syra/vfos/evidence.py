"""Evidence bundle: "pronto" so existe com prova reproduzivel.

Formato conforme a secao 10 do prompt mestre. Duas regras estruturais:

1. O manifest e imutavel depois de selado. Correcao gera nova versao, nunca
   reescrita — senao a evidencia deixa de provar qualquer coisa.
2. Resultado de comando nao e digitado a mao. ``registrar_comando`` executa,
   captura exit code e horarios reais e grava o que aconteceu.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from syra.vfos import policy


class ManifestSelado(RuntimeError):
    """Tentativa de alterar um manifest ja selado."""


def sha256_arquivo(caminho: Path) -> str:
    """Hash de um arquivo, lido em blocos."""
    digest = hashlib.sha256()
    with Path(caminho).open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(65536), b""):
            digest.update(bloco)
    return digest.hexdigest()


@dataclass
class EvidenceBundle:
    """Coletor de evidencia de uma tarefa."""

    task_id: str
    commit: str = ""
    changed_files: list[str] = field(default_factory=list)
    contracts_usados: list[str] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, str]] = field(default_factory=list)
    evaluations: list[dict[str, Any]] = field(default_factory=list)
    security_findings: list[dict[str, Any]] = field(default_factory=list)
    governance_decision: dict[str, Any] | None = None
    residual_risks: list[str] = field(default_factory=list)
    selado: bool = False

    def _garantir_aberto(self) -> None:
        if self.selado:
            raise ManifestSelado(
                f"{self.task_id}: manifest selado. Correcao exige nova versao.")

    def registrar_comando(self, comando: str, cwd: str | None = None,
                          timeout: float = 900.0) -> dict[str, Any]:
        """Executa o comando e grava o resultado real.

        O comando roda sem shell: a lista de argumentos vem de ``shlex.split``,
        o que evita interpretacao de metacaractere e injecao.
        """
        self._garantir_aberto()
        iniciado = policy.agora_iso()
        try:
            processo = subprocess.run(  # noqa: S603 - sem shell, args explicitos
                shlex.split(comando), cwd=cwd, capture_output=True, text=True,
                timeout=timeout, check=False)
            codigo, saida = processo.returncode, processo.stdout + processo.stderr
        except (OSError, subprocess.TimeoutExpired) as erro:
            codigo, saida = 127, f"{type(erro).__name__}: {erro}"

        registro = {
            "command": comando,
            "exit_code": codigo,
            "started_at": iniciado,
            "finished_at": policy.agora_iso(),
            "output_tail": saida[-2000:],
        }
        self.commands.append(registro)
        return registro

    def registrar_artefato(self, caminho: Path | str) -> dict[str, str]:
        """Adiciona um arquivo ao inventario, com hash calculado agora."""
        self._garantir_aberto()
        alvo = Path(caminho)
        registro = {"path": str(alvo), "sha256": sha256_arquivo(alvo)}
        self.artifacts.append(registro)
        return registro

    def registrar_avaliacao(self, avaliador: str, veredito: str,
                            detalhe: str = "") -> None:
        """Registra uma avaliacao independente."""
        self._garantir_aberto()
        self.evaluations.append({"evaluator": avaliador, "verdict": veredito,
                                 "detail": detalhe,
                                 "at": policy.agora_iso()})

    @property
    def comandos_verdes(self) -> bool:
        """Todos os comandos registrados terminaram com exit code zero."""
        return bool(self.commands) and all(c["exit_code"] == 0
                                           for c in self.commands)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "commit": self.commit,
            "changed_files": self.changed_files,
            "contracts": self.contracts_usados,
            "commands": self.commands,
            "artifacts": self.artifacts,
            "evaluations": self.evaluations,
            "security_findings": self.security_findings,
            "governance_decision": self.governance_decision,
            "residual_risks": self.residual_risks,
            "sealed_at": policy.agora_iso() if self.selado else None,
        }

    def selar(self, destino: Path | str) -> Path:
        """Grava e sela o manifest.

        Depois disto o bundle recusa qualquer alteracao. O proprio manifest
        recebe um hash de conteudo, para que adulteracao posterior seja
        detectavel.
        """
        self._garantir_aberto()
        self.selado = True

        alvo = Path(destino)
        alvo.parent.mkdir(parents=True, exist_ok=True)
        corpo = self.to_dict()
        canonico = json.dumps(corpo, sort_keys=True, ensure_ascii=False,
                              separators=(",", ":"))
        corpo["manifest_sha256"] = hashlib.sha256(
            canonico.encode("utf-8")).hexdigest()
        alvo.write_text(json.dumps(corpo, indent=2, ensure_ascii=False),
                        encoding="utf-8")
        return alvo
