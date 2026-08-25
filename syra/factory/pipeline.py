"""Pipeline da fabrica: missao entra, software auditavel sai.

A ordem dos portoes e deliberada e vai do mais barato ao mais caro: sintaxe,
revisao estatica, execucao de testes, cobertura de contrato e, por fim,
governanca. Falhar cedo economiza ciclos; a decisao final so acontece com
evidencia executada em maos.
"""

from __future__ import annotations

import ast
import json
import time
from pathlib import Path

from syra.contracts import (
    BuildResult,
    BuildSpec,
    GateResult,
    GeneratedProject,
    GovernanceDecision,
    Mission,
    Verdict,
)
from syra.factory.architect import Architect
from syra.factory.packager import build_manifest, package
from syra.factory.qa import QAEngine, materialize
from syra.factory.repair import RepairEngine, classify
from syra.factory.reviewer import Reviewer, untested_public_functions
from syra.factory.synthesis import BlueprintSynthesizer, SynthesisError
from syra.governance.engine import GovernanceEngine
from syra.governance.policy import Policy
from syra.memory.error_memory import ErrorMemory
from syra.memory.run_store import RunRecord, RunStore
from syra.paths import builds_dir, reports_dir


def _bloqueio(motivo: str, portao: str) -> GovernanceDecision:
    return GovernanceDecision(
        verdict=Verdict.BLOCKED, confidence=0.0, reasons=(motivo,),
        blocked_gates=(portao,),
    )


class Factory:
    """Orquestra o squad completo: arquiteto, sintese, revisao, QA e governanca."""

    def __init__(self, policy: Policy | None = None, synthesizer=None,
                 memory: ErrorMemory | None = None,
                 store: RunStore | None = None) -> None:
        self.policy = policy or Policy.load()
        self.synthesizer = synthesizer or BlueprintSynthesizer()
        self.memory = memory or ErrorMemory()
        self.store = store or RunStore()
        self.architect = Architect()
        self.reviewer = Reviewer()
        self.qa = QAEngine()
        self.repairer = RepairEngine(self.memory)
        self.governance = GovernanceEngine(self.policy, self.memory)

    def build(self, mission: Mission) -> BuildResult:
        """Executa a missao de ponta a ponta e devolve o resultado auditavel."""
        inicio = time.perf_counter()
        gates: list[GateResult] = []
        spec: BuildSpec | None = None
        review = None
        qa = None
        tentativas = 0
        assinaturas: list[str] = []

        # Portao 0: lei fundamental. Sem ganho declarado, nao se gasta ciclo.
        if not mission.gains:
            gates.append(GateResult("lei_do_ganho", False,
                                    "missao sem ganho declarado"))
            return self._finalizar(mission, None, None, None, None, None, None,
                                   gates, _bloqueio("missao nao declara ganho",
                                                    "gain_law"),
                                   0, time.perf_counter() - inicio)
        gates.append(GateResult("lei_do_ganho", True,
                                f"ganhos: {', '.join(g.value for g in mission.gains)}"))

        # Planejamento.
        marco = time.perf_counter()
        spec = self.architect.plan(mission)
        gates.append(GateResult("arquiteto", bool(spec.modules), spec.rationale,
                                time.perf_counter() - marco))
        if not spec.modules:
            return self._finalizar(mission, spec, None, None, None, None, None, gates,
                                   _bloqueio("arquiteto nao produziu modulos", "plan"),
                                   0, time.perf_counter() - inicio)

        # Sintese.
        marco = time.perf_counter()
        try:
            project = self.synthesizer.synthesize(spec)
        except SynthesisError as erro:
            self.memory.record("sintese", str(erro))
            gates.append(GateResult("sintese", False, str(erro),
                                    time.perf_counter() - marco))
            return self._finalizar(mission, spec, None, None, None, None, None, gates,
                                   _bloqueio(f"sintese falhou: {erro}", "synthesis"),
                                   0, time.perf_counter() - inicio)
        gates.append(GateResult("sintese", True,
                                f"{len(project.files)} arquivo(s) via "
                                f"{project.synthesizer}",
                                time.perf_counter() - marco))

        build_dir = builds_dir() / mission.mission_id

        # Laco: sintaxe -> revisao -> testes, com reparo limitado e auditado.
        while True:
            marco = time.perf_counter()
            erro_sintaxe = self._checar_sintaxe(project)
            gates.append(GateResult("sintaxe", erro_sintaxe is None,
                                    erro_sintaxe or "todos os arquivos compilam",
                                    time.perf_counter() - marco))

            if erro_sintaxe is None:
                marco = time.perf_counter()
                review = self.reviewer.review(project)
                gates.append(GateResult(
                    "revisao", review.passed,
                    f"{len(review.blocking)} bloqueante(s) em "
                    f"{review.files_reviewed} arquivo(s)",
                    time.perf_counter() - marco))

                materialize(project, build_dir)
                marco = time.perf_counter()
                qa = self.qa.run(build_dir)
                gates.append(GateResult(
                    "testes", qa.green,
                    f"{qa.passed}/{qa.total} verdes em {qa.duration:.2f}s "
                    f"({qa.runner})",
                    time.perf_counter() - marco))
                if qa.green:
                    break
                falhas = classify(qa, spec)
            else:
                falhas = classify_syntax(erro_sintaxe, spec)

            assinaturas.extend(f.sig for f in falhas)

            if tentativas >= self.policy.max_repair_attempts:
                gates.append(GateResult("reparo", False,
                                        f"limite de {self.policy.max_repair_attempts} "
                                        "tentativa(s) atingido"))
                break

            reparo = self.repairer.repair(spec, project, falhas, self.synthesizer)
            if reparo is None:
                gates.append(GateResult("reparo", False,
                                        "nenhuma estrategia aplicavel para as falhas"))
                break

            spec, project, estrategia = reparo
            tentativas += 1
            gates.append(GateResult("reparo", True,
                                    f"tentativa {tentativas}: {estrategia}"))
            self.repairer.learn(falhas, estrategia)

        # Cobertura de contrato.
        marco = time.perf_counter()
        sem_teste = untested_public_functions(project)
        gates.append(GateResult("cobertura", not sem_teste,
                                f"{len(sem_teste)} funcao(oes) publica(s) sem teste",
                                time.perf_counter() - marco))

        # Governanca decide com todas as evidencias reunidas.
        decisao = self.governance.decide(
            mission, review, qa,
            error_signatures=assinaturas,
            run_stats=self.store.stats(),
            untested_functions=sem_teste,
        )

        artifact = None
        manifest = None
        if decisao.approved and qa is not None:
            manifest = build_manifest(spec, project, qa)
            caminho, manifest = package(build_dir, manifest)
            artifact = str(caminho)
            gates.append(GateResult("entrega", True,
                                    f"artefato {manifest.artifact_sha256[:12]}"))

        return self._finalizar(mission, spec, project, review, qa, manifest,
                               artifact, gates, decisao, tentativas,
                               time.perf_counter() - inicio, build_dir)

    @staticmethod
    def _checar_sintaxe(project: GeneratedProject) -> str | None:
        """Devolve a primeira falha de compilacao encontrada, se houver."""
        for arquivo in project.files:
            if not arquivo.is_python:
                continue
            try:
                ast.parse(arquivo.content)
            except SyntaxError as erro:
                return f"{arquivo.path}:{erro.lineno}: {erro.msg}"
        return None

    def _finalizar(self, mission, spec, project, review, qa, manifest, artifact,
                   gates, decisao, tentativas, duracao,
                   build_dir: Path | None = None) -> BuildResult:
        """Persiste historico e relatorios e devolve o resultado final."""
        resultado = BuildResult(
            mission=mission, spec=spec, decision=decisao, gates=tuple(gates),
            review=review, qa=qa, manifest=manifest,
            build_dir=str(build_dir) if build_dir else None,
            artifact_path=artifact, repair_attempts=tentativas, duration=duracao,
        )

        self.store.append(RunRecord(
            run_id=resultado.run_id,
            mission_id=mission.mission_id,
            kind=mission.kind,
            verdict=decisao.verdict.value,
            delivered=resultado.delivered,
            duration=duracao,
            tests_total=qa.total if qa else 0,
            tests_passed=qa.passed if qa else 0,
            tests_failed=(qa.failed + qa.errors) if qa else 0,
            review_blocking=len(review.blocking) if review else 0,
            repair_attempts=tentativas,
            gate_failures=[g.name for g in gates if not g.passed],
            synthesizer=project.synthesizer if project else self.synthesizer.name,
        ))

        destino = reports_dir() / f"{mission.mission_id}.json"
        destino.write_text(json.dumps(resultado.to_dict(), indent=2,
                                      ensure_ascii=False), encoding="utf-8")
        return resultado


def classify_syntax(erro: str, spec: BuildSpec):
    """Converte uma falha de compilacao no mesmo formato de falha de teste."""
    from syra.factory.repair import Failure

    caminho = erro.split(":", 1)[0]
    alvo = next((f.name for f in spec.functions if f.name in erro), None)
    return [Failure(kind="erro_de_sintaxe", nodeid=caminho, message=erro,
                    capability=alvo)]
