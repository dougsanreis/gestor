"""Motor de reparo: corrige a causa, nunca enfraquece a evidencia.

Regra inegociavel deste modulo: nenhuma estrategia apaga, pula ou afrouxa um
teste para obter verde. Quando a causa raiz nao pode ser corrigida, a
capacidade defeituosa e posta em quarentena e removida da entrega, com registro
na memoria de erros. Verde obtido removendo o teste e autossabotagem, nao reparo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from syra.contracts import BuildSpec, GeneratedProject, ModuleSpec, QAReport
from syra.memory.error_memory import ErrorMemory, signature

_PADROES = (
    ("erro_de_sintaxe", re.compile(r"SyntaxError|IndentationError")),
    ("import_ausente", re.compile(r"ModuleNotFoundError|ImportError|cannot import name")),
    ("nome_indefinido", re.compile(r"NameError: name '([^']+)'")),
    ("falha_de_coleta", re.compile(r"ERROR collecting|INTERNALERROR")),
    ("assercao", re.compile(r"AssertionError|assert ")),
    ("tipo_invalido", re.compile(r"TypeError")),
    ("valor_invalido", re.compile(r"ValueError")),
)


@dataclass(frozen=True)
class Failure:
    """Falha classificada, pronta para escolha de estrategia."""

    kind: str
    nodeid: str
    message: str
    capability: str | None

    @property
    def sig(self) -> str:
        return signature(self.kind, self.message, self.nodeid.split("::")[0])


def classify(qa: QAReport, spec: BuildSpec) -> list[Failure]:
    """Converte falhas de teste em falhas classificadas e atribuidas."""
    conhecidas = {f.name for f in spec.functions}
    falhas: list[Failure] = []

    for resultado in qa.failures:
        texto = f"{resultado.nodeid}\n{resultado.message}"
        tipo = next((nome for nome, padrao in _PADROES if padrao.search(texto)),
                    "desconhecido")
        alvo = next((nome for nome in conhecidas if nome in texto), None)
        falhas.append(Failure(kind=tipo, nodeid=resultado.nodeid,
                              message=resultado.message[:1500], capability=alvo))
    return falhas


def _sem_capacidade(spec: BuildSpec, nome: str) -> BuildSpec:
    """Devolve um plano identico, porem sem a capacidade indicada."""
    modules: list[ModuleSpec] = []
    for module in spec.modules:
        restantes = tuple(f for f in module.functions if f.capability != nome)
        if restantes:
            modules.append(ModuleSpec(name=module.name, purpose=module.purpose,
                                      functions=restantes))
    return BuildSpec(mission=spec.mission, package_name=spec.package_name,
                     kind=spec.kind, modules=tuple(modules),
                     entrypoint=spec.entrypoint,
                     rationale=spec.rationale + f" | capacidade '{nome}' em quarentena")


class RepairEngine:
    """Escolhe e aplica estrategias de reparo, com memoria do que ja funcionou."""

    def __init__(self, memory: ErrorMemory | None = None) -> None:
        self.memory = memory or ErrorMemory()

    def strategies_for(self, failure: Failure) -> list[str]:
        """Ordena estrategias, priorizando a que ja resolveu esta falha antes."""
        base = {
            "erro_de_sintaxe": ["ressintetizar_projeto", "quarentena_capacidade"],
            "import_ausente": ["ressintetizar_projeto", "quarentena_capacidade"],
            "nome_indefinido": ["ressintetizar_projeto", "quarentena_capacidade"],
            "falha_de_coleta": ["ressintetizar_projeto", "quarentena_capacidade"],
        }.get(failure.kind, ["quarentena_capacidade"])

        conhecida = self.memory.known_fix(failure.kind, failure.message,
                                          failure.nodeid.split("::")[0])
        if conhecida and conhecida in base:
            base.remove(conhecida)
            base.insert(0, conhecida)
        elif conhecida:
            base.insert(0, conhecida)
        return base

    def repair(self, spec: BuildSpec, project: GeneratedProject,
               failures: list[Failure], synthesizer) -> tuple[BuildSpec, GeneratedProject, str] | None:
        """Aplica a primeira estrategia viavel e devolve o novo estado.

        Returns:
            Uma tupla ``(spec, project, estrategia)`` quando algo mudou, ou
            ``None`` quando nenhuma estrategia se aplica — caso em que o
            pipeline para e reporta, em vez de girar em falso.
        """
        if not failures:
            return None

        for failure in failures:
            self.memory.record(failure.kind, failure.message,
                               failure.nodeid.split("::")[0])

            for estrategia in self.strategies_for(failure):
                if estrategia == "ressintetizar_projeto":
                    novo = synthesizer.synthesize(spec)
                    if novo.files != project.files:
                        return spec, novo, estrategia
                    continue

                if estrategia == "quarentena_capacidade" and failure.capability:
                    reduzido = _sem_capacidade(spec, failure.capability)
                    if not reduzido.modules:
                        continue
                    return reduzido, synthesizer.synthesize(reduzido), estrategia
        return None

    def learn(self, failures: list[Failure], estrategia: str) -> None:
        """Registra que ``estrategia`` resolveu as falhas informadas."""
        for failure in failures:
            self.memory.resolve(
                failure.sig,
                estrategia,
                prevention=f"falha '{failure.kind}' resolvida por {estrategia}",
            )
