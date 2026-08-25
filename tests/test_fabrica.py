"""Testes do squad de construcao: arquiteto, sintese, revisao, QA e pipeline."""

from __future__ import annotations

import ast
import zipfile

import pytest

from syra.contracts import (
    GeneratedFile,
    GeneratedProject,
    Mission,
    Verdict,
)
from syra.factory.architect import Architect
from syra.factory.catalog import CAPABILITIES
from syra.factory.pipeline import Factory
from syra.factory.qa import QAEngine, materialize
from syra.factory.reviewer import Reviewer, untested_public_functions
from syra.factory.synthesis import (
    BlueprintSynthesizer,
    SubprocessSynthesizer,
    SynthesisError,
    split_source,
)


# --------------------------------------------------------------- catalogo ---

@pytest.mark.parametrize("capacidade", CAPABILITIES, ids=lambda c: c.name)
def test_toda_capacidade_compila_e_executa(capacidade):
    escopo: dict = {}
    exec(compile(capacidade.source, capacidade.name, "exec"), escopo)
    assert capacidade.name in escopo
    assert callable(escopo[capacidade.name])


@pytest.mark.parametrize("capacidade", CAPABILITIES, ids=lambda c: c.name)
def test_toda_capacidade_tem_teste_que_a_invoca(capacidade):
    arvore = ast.parse(capacidade.tests)
    chamadas = {
        no.func.id for no in ast.walk(arvore)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
    }
    assert capacidade.name in chamadas


@pytest.mark.parametrize("capacidade",
                         [c for c in CAPABILITIES if c.examples],
                         ids=lambda c: c.name)
def test_exemplos_do_catalogo_produzem_o_valor_documentado(capacidade):
    escopo: dict = {}
    exec(compile(capacidade.source, capacidade.name, "exec"), escopo)
    for chamada, esperado in capacidade.examples:
        assert repr(eval(chamada, escopo)) == esperado


# --------------------------------------------------------------- arquiteto ---

def test_arquiteto_seleciona_por_aderencia_ao_objetivo():
    spec = Architect().plan(Mission(objective="validar CPF e email no cadastro"))
    nomes = {f.name for f in spec.functions}
    assert "validar_cpf" in nomes
    assert "validar_email" in nomes


def test_arquiteto_nunca_entrega_plano_vazio():
    spec = Architect().plan(Mission(objective="zzz qqq xxx sem correspondencia"))
    assert len(spec.functions) >= 3


def test_arquiteto_define_entrypoint_por_tipo():
    assert Architect().plan(Mission(objective="x", kind="cli")).entrypoint
    assert Architect().plan(Mission(objective="x", kind="library")).entrypoint is None


# ------------------------------------------------------------------ sintese ---

def test_split_source_hasteia_imports():
    imports, corpo = split_source("import os\nfrom x import y\n\ndef f():\n    return 1\n")
    assert imports == ["import os", "from x import y"]
    assert "import" not in corpo


@pytest.mark.parametrize("kind", ["library", "cli", "service"])
def test_projeto_gerado_compila_inteiro(kind):
    spec = Architect().plan(Mission(objective="gestao escolar notas", kind=kind))
    projeto = BlueprintSynthesizer().synthesize(spec)
    for arquivo in projeto.files:
        if arquivo.is_python:
            ast.parse(arquivo.content)
    assert projeto.source_files and projeto.test_files


def test_sintetizador_externo_recusa_caminho_para_fora_do_projeto():
    saida = (
        "```python\n# file: ../fuga.py\nx = 1\n```\n"
        "```python\n# file: /etc/passwd\nx = 2\n```\n"
        "```python\n# file: pacote/ok.py\nx = 3\n```\n"
    )
    arquivos = SubprocessSynthesizer.parse(saida)
    assert [a.path for a in arquivos] == ["pacote/ok.py"]


def test_sintetizador_externo_falha_alto_quando_comando_nao_existe():
    with pytest.raises(SynthesisError):
        SubprocessSynthesizer("binario_que_nao_existe_12345").synthesize(
            Architect().plan(Mission(objective="x")))


# ------------------------------------------------------------------ revisor ---

def _projeto(codigo: str) -> GeneratedProject:
    return GeneratedProject(files=(GeneratedFile("mod.py", codigo),),
                            synthesizer="teste")


def test_revisor_bloqueia_implementacao_vazia():
    relatorio = Reviewer().review(_projeto(
        '"""m."""\n\n\ndef f():\n    """d."""\n    raise NotImplementedError\n'))
    assert not relatorio.passed
    assert any(f.rule == "implementacao_vazia" for f in relatorio.blocking)


def test_revisor_bloqueia_funcao_que_so_tem_pass():
    relatorio = Reviewer().review(_projeto('"""m."""\n\n\ndef f():\n    pass\n'))
    assert any(f.rule == "implementacao_vazia" for f in relatorio.blocking)


@pytest.mark.parametrize("trecho,regra", [
    ("eval(x)", "chamada_proibida"),
    ("os.system(x)", "chamada_proibida"),
    ("pickle.loads(x)", "chamada_proibida"),
    ("subprocess.run(x, shell=True)", "shell_true"),
])
def test_revisor_bloqueia_chamada_insegura(trecho, regra):
    codigo = f'"""m."""\nimport os, pickle, subprocess\n\n\ndef f(x):\n    """d."""\n    return {trecho}\n'
    relatorio = Reviewer().review(_projeto(codigo))
    assert any(f.rule == regra for f in relatorio.blocking)


def test_revisor_bloqueia_marcador_de_pendencia():
    relatorio = Reviewer().review(_projeto(
        '"""m."""\n\n\ndef f():\n    """d."""\n    return 1  # TODO revisar\n'))
    assert any(f.rule == "marcador_pendente" for f in relatorio.blocking)


def test_revisor_nao_confunde_metodo_com_marcador_todo():
    """A palavra "metodo" contem "TODO"; a regra exige fronteira de palavra."""
    relatorio = Reviewer().review(_projeto(
        '"""m."""\n\n\ndef f():\n    """d."""\n    return {"metodo": "POST"}\n'))
    assert not any(f.rule == "marcador_pendente" for f in relatorio.findings)


def test_revisor_aprova_codigo_bem_formado():
    relatorio = Reviewer().review(_projeto(
        '"""Modulo."""\n\n\ndef somar(a, b):\n    """Soma dois numeros."""\n    return a + b\n'))
    assert relatorio.passed


def test_cobertura_detecta_funcao_publica_sem_teste():
    projeto = GeneratedProject(
        files=(GeneratedFile("p/m.py", '"""m."""\n\n\ndef usada():\n    """d."""\n    return 1\n\n\ndef orfa():\n    """d."""\n    return 2\n'),
               GeneratedFile("tests/test_m.py", '"""t."""\n\n\ndef test_x():\n    assert usada() == 1\n')),
        synthesizer="teste")
    assert untested_public_functions(projeto) == ["orfa"]


# ------------------------------------------------------------------ qa real ---

def test_qa_executa_a_suite_de_verdade(tmp_path):
    spec = Architect().plan(Mission(objective="validar CPF e email"))
    projeto = BlueprintSynthesizer().synthesize(spec)
    destino = materialize(projeto, tmp_path / "p")
    relatorio = QAEngine().run(destino)
    assert relatorio.green
    assert relatorio.passed > 0
    assert all(o.duration >= 0 for o in relatorio.outcomes)


def _sabotar(codigo: str) -> str:
    """Injeta uma falha na primeira funcao publica do modulo.

    Feito por AST para nao depender de nenhum trecho textual especifico: a
    sabotagem precisa valer para qualquer capacidade do catalogo.
    """
    arvore = ast.parse(codigo)
    for no in arvore.body:
        if isinstance(no, ast.FunctionDef) and not no.name.startswith("_"):
            no.body.insert(0, ast.parse('raise RuntimeError("sabotado")').body[0])
            return ast.unparse(ast.fix_missing_locations(arvore))
    raise AssertionError("modulo gerado nao expoe funcao publica")


def test_qa_detecta_suite_sabotada(tmp_path):
    spec = Architect().plan(Mission(objective="validar CPF e email"))
    projeto = BlueprintSynthesizer().synthesize(spec)
    alvo = next(f for f in projeto.source_files
                if not f.path.endswith("__init__.py"))
    sabotado = projeto.replace(alvo.path, _sabotar(alvo.content))
    relatorio = QAEngine().run(materialize(sabotado, tmp_path / "quebrado"))
    assert relatorio.green is False
    assert relatorio.failures
    assert any("sabotado" in o.message for o in relatorio.failures)


# ----------------------------------------------------------------- pipeline ---

def test_pipeline_entrega_artefato_verificavel(missao_simples):
    resultado = Factory().build(missao_simples)
    assert resultado.decision.verdict is Verdict.APPROVED
    assert resultado.delivered
    assert resultado.qa.green
    assert zipfile.is_zipfile(resultado.artifact_path)
    assert len(resultado.manifest.artifact_sha256) == 64


def test_artefato_contem_codigo_e_testes(missao_simples):
    resultado = Factory().build(missao_simples)
    with zipfile.ZipFile(resultado.artifact_path) as pacote:
        nomes = pacote.namelist()
    assert any(n.startswith("tests/") for n in nomes)
    assert "package_manifest.json" in nomes
    assert "pyproject.toml" in nomes


def test_pipeline_bloqueia_missao_sem_ganho():
    resultado = Factory().build(Mission(objective="x", gains=()))
    assert resultado.decision.verdict is Verdict.BLOCKED
    assert resultado.artifact_path is None


def test_pipeline_bloqueia_codigo_de_sintetizador_hostil(missao_simples):
    class Hostil:
        name = "hostil"

        def synthesize(self, spec):
            return GeneratedProject(
                files=(GeneratedFile("p/__init__.py", '"""p."""\n'),
                       GeneratedFile("p/m.py",
                                     '"""m."""\nimport os\n\n\ndef f(c):\n'
                                     '    """d."""\n    return os.system(c)\n'),
                       GeneratedFile("tests/test_m.py",
                                     '"""t."""\nfrom p.m import f\n\n\n'
                                     'def test_f():\n    assert f("true") == 0\n')),
                synthesizer=self.name)

    resultado = Factory(synthesizer=Hostil()).build(missao_simples)
    assert resultado.decision.verdict is Verdict.BLOCKED
    assert "review" in resultado.decision.blocked_gates
    assert resultado.artifact_path is None


def test_execucao_e_registrada_no_historico(missao_simples):
    fabrica = Factory()
    fabrica.build(missao_simples)
    assert fabrica.store.stats()["runs"] == 1
