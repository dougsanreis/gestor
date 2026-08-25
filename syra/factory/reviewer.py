"""Revisor estatico: o portao que separa software de artefato.

A regra mais importante deste modulo e a deteccao de implementacao vazia.
Um sistema que "gera codigo" mas devolve funcoes com ``pass``, ``...`` ou
``NotImplementedError`` esta produzindo artefato, nao software. Aqui isso e
achado CRITICO e bloqueia a entrega.
"""

from __future__ import annotations

import ast
import re

from syra.contracts import (
    GeneratedFile,
    GeneratedProject,
    ReviewFinding,
    ReviewReport,
    Severity,
)

# Chamadas que executam codigo arbitrario ou desserializam dados nao confiaveis.
_CHAMADAS_PROIBIDAS = {
    "eval": "execucao de codigo arbitrario a partir de texto",
    "exec": "execucao de codigo arbitrario a partir de texto",
    "compile": "compilacao dinamica de codigo",
    "__import__": "importacao dinamica dificulta auditoria",
}
_ATRIBUTOS_PROIBIDOS = {
    ("os", "system"): "execucao de shell sem controle de argumentos",
    ("os", "popen"): "execucao de shell sem controle de argumentos",
    ("pickle", "loads"): "desserializacao insegura de dados nao confiaveis",
    ("pickle", "load"): "desserializacao insegura de dados nao confiaveis",
    ("yaml", "load"): "use yaml.safe_load para entrada nao confiavel",
}

# Fronteira de palavra e obrigatoria: sem ela, "metodo" casa com "TODO".
_MARCADOR_PENDENTE = re.compile(r"(?<![A-Za-z])(TODO|FIXME|XXX|HACK)(?![A-Za-z])")

MAX_LINHAS_FUNCAO = 60
MAX_RAMIFICACOES = 12


def _e_placeholder(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Indica se o corpo da funcao nao implementa nada de fato."""
    corpo = [n for n in node.body if not isinstance(n, ast.Expr)
             or not isinstance(n.value, ast.Constant)
             or not isinstance(n.value.value, str)]
    if not corpo:
        return True
    for statement in corpo:
        if isinstance(statement, ast.Pass):
            continue
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant) \
                and statement.value.value is Ellipsis:
            continue
        if isinstance(statement, ast.Raise):
            alvo = statement.exc
            nome = None
            if isinstance(alvo, ast.Call):
                nome = getattr(alvo.func, "id", None)
            elif isinstance(alvo, ast.Name):
                nome = alvo.id
            if nome == "NotImplementedError":
                continue
        return False
    return True


def _ramificacoes(node: ast.AST) -> int:
    """Conta pontos de decisao, aproximando complexidade ciclomatica."""
    total = 0
    for filho in ast.walk(node):
        if isinstance(filho, (ast.If, ast.For, ast.While, ast.ExceptHandler,
                              ast.With, ast.Assert, ast.IfExp)):
            total += 1
        elif isinstance(filho, ast.BoolOp):
            total += len(filho.values) - 1
    return total


class Reviewer:
    """Aplica regras estaticas sobre todos os arquivos gerados."""

    def review(self, project: GeneratedProject) -> ReviewReport:
        """Revisa o projeto e devolve o relatorio consolidado."""
        findings: list[ReviewFinding] = []
        publicos = 0
        revisados = 0

        for arquivo in project.files:
            if not arquivo.is_python:
                continue
            revisados += 1
            try:
                arvore = ast.parse(arquivo.content)
            except SyntaxError as erro:
                findings.append(ReviewFinding(
                    rule="sintaxe_invalida",
                    severity=Severity.CRITICAL,
                    message=f"arquivo nao compila: {erro.msg}",
                    path=arquivo.path,
                    line=erro.lineno or 0,
                ))
                continue

            findings.extend(self._regras_de_modulo(arquivo, arvore))
            for node in ast.walk(arvore):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith("_") and not _is_test(node.name):
                        publicos += 1
                    findings.extend(self._regras_de_funcao(arquivo, node))
                findings.extend(self._regras_de_chamada(arquivo, node))

        return ReviewReport(findings=tuple(findings), files_reviewed=revisados,
                            public_functions=publicos)

    def _regras_de_modulo(self, arquivo: GeneratedFile,
                          arvore: ast.Module) -> list[ReviewFinding]:
        achados: list[ReviewFinding] = []
        if not ast.get_docstring(arvore):
            achados.append(ReviewFinding(
                rule="modulo_sem_docstring",
                severity=Severity.MINOR,
                message="modulo sem docstring: proposito nao documentado",
                path=arquivo.path,
                line=1,
            ))
        for numero, linha in enumerate(arquivo.content.splitlines(), start=1):
            marcador = _MARCADOR_PENDENTE.search(linha.upper())
            if marcador:
                achados.append(ReviewFinding(
                    rule="marcador_pendente",
                    severity=Severity.MAJOR,
                    message=f"marcador '{marcador.group(1)}' em codigo entregue",
                    path=arquivo.path,
                    line=numero,
                ))
        return achados

    def _regras_de_funcao(self, arquivo: GeneratedFile,
                          node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ReviewFinding]:
        achados: list[ReviewFinding] = []
        publico = not node.name.startswith("_") and not _is_test(node.name)

        if _e_placeholder(node):
            achados.append(ReviewFinding(
                rule="implementacao_vazia",
                severity=Severity.CRITICAL,
                message=(f"'{node.name}' nao implementa comportamento: "
                         "isto e artefato, nao software"),
                path=arquivo.path,
                line=node.lineno,
            ))

        if publico and not ast.get_docstring(node):
            achados.append(ReviewFinding(
                rule="funcao_publica_sem_docstring",
                severity=Severity.MAJOR,
                message=f"funcao publica '{node.name}' sem docstring",
                path=arquivo.path,
                line=node.lineno,
            ))

        for argumento in node.args.defaults + [d for d in node.args.kw_defaults if d]:
            if isinstance(argumento, (ast.List, ast.Dict, ast.Set)):
                achados.append(ReviewFinding(
                    rule="default_mutavel",
                    severity=Severity.MAJOR,
                    message=f"'{node.name}' usa valor padrao mutavel: estado vaza "
                            "entre chamadas",
                    path=arquivo.path,
                    line=node.lineno,
                ))

        linhas = (node.end_lineno or node.lineno) - node.lineno
        if linhas > MAX_LINHAS_FUNCAO:
            achados.append(ReviewFinding(
                rule="funcao_longa",
                severity=Severity.MINOR,
                message=f"'{node.name}' tem {linhas} linhas (limite {MAX_LINHAS_FUNCAO})",
                path=arquivo.path,
                line=node.lineno,
            ))

        ramos = _ramificacoes(node)
        if ramos > MAX_RAMIFICACOES:
            achados.append(ReviewFinding(
                rule="complexidade_alta",
                severity=Severity.MINOR,
                message=f"'{node.name}' tem {ramos} pontos de decisao "
                        f"(limite {MAX_RAMIFICACOES})",
                path=arquivo.path,
                line=node.lineno,
            ))
        return achados

    def _regras_de_chamada(self, arquivo: GeneratedFile,
                           node: ast.AST) -> list[ReviewFinding]:
        achados: list[ReviewFinding] = []

        if isinstance(node, ast.ExceptHandler) and node.type is None:
            achados.append(ReviewFinding(
                rule="except_pelado",
                severity=Severity.MAJOR,
                message="'except:' captura ate KeyboardInterrupt e mascara falhas",
                path=arquivo.path,
                line=node.lineno,
            ))

        if not isinstance(node, ast.Call):
            return achados

        funcao = node.func
        if isinstance(funcao, ast.Name) and funcao.id in _CHAMADAS_PROIBIDAS:
            achados.append(ReviewFinding(
                rule="chamada_proibida",
                severity=Severity.CRITICAL,
                message=f"'{funcao.id}': {_CHAMADAS_PROIBIDAS[funcao.id]}",
                path=arquivo.path,
                line=node.lineno,
            ))
        elif isinstance(funcao, ast.Attribute) and isinstance(funcao.value, ast.Name):
            chave = (funcao.value.id, funcao.attr)
            if chave in _ATRIBUTOS_PROIBIDOS:
                achados.append(ReviewFinding(
                    rule="chamada_proibida",
                    severity=Severity.CRITICAL,
                    message=f"'{chave[0]}.{chave[1]}': {_ATRIBUTOS_PROIBIDOS[chave]}",
                    path=arquivo.path,
                    line=node.lineno,
                ))

        for palavra in node.keywords:
            if palavra.arg == "shell" and isinstance(palavra.value, ast.Constant) \
                    and palavra.value.value is True:
                achados.append(ReviewFinding(
                    rule="shell_true",
                    severity=Severity.CRITICAL,
                    message="subprocess com shell=True permite injecao de comando",
                    path=arquivo.path,
                    line=node.lineno,
                ))
        return achados


def _is_test(nome: str) -> bool:
    return nome.startswith("test_")


def untested_public_functions(project: GeneratedProject) -> list[str]:
    """Lista funcoes publicas que nenhum teste chega a invocar.

    Cobertura aqui e verificada por chamada explicita no codigo de teste, nao
    por instrumentacao: e barato, deterministico e suficiente para impedir que
    uma funcao entre na entrega sem nenhuma evidencia de execucao.
    """
    publicas: set[str] = set()
    for arquivo in project.source_files:
        try:
            arvore = ast.parse(arquivo.content)
        except SyntaxError:
            continue
        for node in arvore.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and not node.name.startswith("_"):
                publicas.add(node.name)

    exercitadas: set[str] = set()
    for arquivo in project.test_files:
        try:
            arvore = ast.parse(arquivo.content)
        except SyntaxError:
            continue
        for node in ast.walk(arvore):
            if isinstance(node, ast.Call):
                alvo = node.func
                if isinstance(alvo, ast.Name):
                    exercitadas.add(alvo.id)
                elif isinstance(alvo, ast.Attribute):
                    exercitadas.add(alvo.attr)

    return sorted(publicas - exercitadas)
