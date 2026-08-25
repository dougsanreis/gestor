"""Sintetizadores: transformam um ``BuildSpec`` em arquivos de projeto.

O contrato ``CodeSynthesizer`` e deliberadamente estreito para que a origem do
codigo seja intercambiavel. O ``BlueprintSynthesizer`` e o piso deterministico
que funciona sem rede e sem modelo. O ``SubprocessSynthesizer`` eleva o teto
delegando a um agente externo, mas passa exatamente pelos mesmos portoes de
revisao, teste e governanca: a fabrica confia na evidencia, nunca na origem.
"""

from __future__ import annotations

import ast
import json
import re
import shlex
import subprocess
from typing import Protocol

from syra.contracts import BuildSpec, GeneratedFile, GeneratedProject
from syra.factory.catalog import Capability, by_name


class SynthesisError(RuntimeError):
    """Falha irrecuperavel durante a sintese do projeto."""


class CodeSynthesizer(Protocol):
    """Qualquer origem de codigo aceita pela fabrica."""

    name: str

    def synthesize(self, spec: BuildSpec) -> GeneratedProject:
        """Materializa os arquivos do projeto descrito por ``spec``."""
        ...


def split_source(source: str) -> tuple[list[str], str]:
    """Separa imports de topo do restante do corpo de um trecho de codigo.

    Necessario porque varias capacidades sao fundidas num mesmo modulo: os
    imports precisam ser hasteados e deduplicados, senao o arquivo gerado fica
    com imports no meio do corpo.
    """
    tree = ast.parse(source)
    linhas = source.splitlines()
    imports: list[str] = []
    descartar: set[int] = set()

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            fim = node.end_lineno or node.lineno
            imports.append("\n".join(linhas[node.lineno - 1:fim]))
            descartar.update(range(node.lineno - 1, fim))

    corpo = "\n".join(l for i, l in enumerate(linhas) if i not in descartar)
    return imports, corpo.strip("\n")


def _module_header(package: str, module: str, purpose: str) -> str:
    return f'"""{purpose}\n\nModulo ``{package}.{module}`` gerado pela SYRA Software Factory.\n"""\n'


def _cli_smoke(capacidades: list[Capability | None]) -> tuple[str, list[str], object] | None:
    """Deriva uma invocacao real de CLI a partir dos exemplos do catalogo.

    O teste de fumaca do CLI precisa de argumentos que a capacidade de fato
    aceite. Inventar argumentos sinteticos produz falhas falsas, entao a
    invocacao e extraida do exemplo ja validado no catalogo.
    """
    for capability in capacidades:
        if capability is None:
            continue
        for chamada, esperado in capability.examples:
            try:
                arvore = ast.parse(chamada, mode="eval")
            except SyntaxError:
                continue
            no = next(
                (n for n in ast.walk(arvore)
                 if isinstance(n, ast.Call)
                 and getattr(n.func, "id", None) == capability.name),
                None,
            )
            if no is None or no.keywords:
                continue
            try:
                argv = [json.dumps(ast.literal_eval(a)) for a in no.args]
            except (ValueError, SyntaxError, TypeError):
                continue

            valor = None
            if arvore.body is no:
                try:
                    valor = ast.literal_eval(esperado)
                except (ValueError, SyntaxError):
                    valor = None
            return capability.name, argv, valor
    return None


class BlueprintSynthesizer:
    """Gera projetos completos a partir do catalogo de capacidades."""

    name = "blueprint"

    def synthesize(self, spec: BuildSpec) -> GeneratedProject:
        """Materializa pacote, testes, documentacao e entrypoint do projeto."""
        arquivos: list[GeneratedFile] = []
        pacote = spec.package_name

        exportados: list[str] = []
        for module in spec.modules:
            capacidades = [by_name(f.capability) for f in module.functions]
            capacidades = [c for c in capacidades if c is not None]
            if not capacidades:
                continue
            arquivos.append(self._render_module(pacote, module.name, module.purpose,
                                                capacidades))
            arquivos.append(self._render_tests(pacote, module.name, capacidades))
            exportados.extend(c.name for c in capacidades)

        if not exportados:
            raise SynthesisError("plano nao selecionou nenhuma capacidade construivel")

        arquivos.append(self._render_init(spec, exportados))

        if spec.kind == "cli":
            arquivos.extend(self._render_cli(spec, exportados))
        elif spec.kind == "service":
            arquivos.extend(self._render_service(spec, exportados))

        arquivos.append(self._render_readme(spec, exportados))
        arquivos.append(self._render_pyproject(spec))

        return GeneratedProject(files=tuple(arquivos), synthesizer=self.name)

    def _render_module(self, pacote: str, nome: str, proposito: str,
                       capacidades: list[Capability]) -> GeneratedFile:
        imports: list[str] = []
        corpos: list[str] = []
        for capability in capacidades:
            cap_imports, corpo = split_source(capability.source)
            for item in cap_imports:
                if item not in imports:
                    imports.append(item)
            corpos.append(corpo)

        publicos = [c.name for c in capacidades]
        partes = [_module_header(pacote, nome, proposito)]
        partes.append("from __future__ import annotations\n")
        if imports:
            partes.append("\n".join(sorted(imports)) + "\n")
        partes.append("__all__ = [\n" + "".join(f'    "{n}",\n' for n in publicos) + "]\n")
        partes.append("\n\n".join(corpos))
        return GeneratedFile(path=f"{pacote}/{nome}.py",
                             content="\n".join(partes).rstrip() + "\n")

    def _render_tests(self, pacote: str, nome: str,
                      capacidades: list[Capability]) -> GeneratedFile:
        publicos = ", ".join(c.name for c in capacidades)
        imports: list[str] = []
        corpos: list[str] = []
        for capability in capacidades:
            test_imports, corpo = split_source(capability.tests)
            for item in test_imports:
                if item not in imports:
                    imports.append(item)
            corpos.append(corpo)

        cabecalho = (
            f'"""Testes gerados para ``{pacote}.{nome}``.\n\n'
            "Cada teste exercita a funcao publica correspondente com entradas\n"
            "validas, limites e erros esperados.\n\"\"\"\n"
        )
        partes = [cabecalho]
        if imports:
            partes.append("\n".join(sorted(imports)) + "\n")
        partes.append(f"from {pacote}.{nome} import {publicos}\n")
        partes.append("\n\n".join(corpos))
        return GeneratedFile(path=f"tests/test_{nome}.py",
                             content="\n".join(partes).rstrip() + "\n")

    def _render_init(self, spec: BuildSpec, exportados: list[str]) -> GeneratedFile:
        linhas = [
            f'"""{spec.mission.objective}\n\n'
            f"Pacote gerado pela SYRA Software Factory a partir da missao\n"
            f"``{spec.mission.mission_id}``.\n\"\"\"\n",
            "from __future__ import annotations\n",
        ]
        for module in spec.modules:
            nomes = ", ".join(f.name for f in module.functions)
            if nomes:
                linhas.append(f"from {spec.package_name}.{module.name} import {nomes}")
        linhas.append("")
        linhas.append('__version__ = "0.1.0"')
        linhas.append("__all__ = [\n" + "".join(f'    "{n}",\n' for n in sorted(exportados)) + "]")
        return GeneratedFile(path=f"{spec.package_name}/__init__.py",
                             content="\n".join(linhas).rstrip() + "\n")

    def _render_cli(self, spec: BuildSpec, exportados: list[str]) -> list[GeneratedFile]:
        pacote = spec.package_name
        comandos = "\n".join(
            f'    "{nome}": {nome},' for nome in sorted(exportados)
        )
        cli = f'''"""Interface de linha de comando de ``{pacote}``.

Cada capacidade publica vira um subcomando. Os argumentos chegam como texto e
sao convertidos por ``_coerce``, de modo que o CLI aceite numeros e listas JSON
sem exigir aspas extras do usuario.
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys

from {pacote} import (
{chr(10).join(f"    {n}," for n in sorted(exportados))}
)

COMANDOS = {{
{comandos}
}}


def _coerce(valor: str):
    """Converte um argumento textual no tipo Python mais provavel."""
    try:
        return json.loads(valor)
    except (json.JSONDecodeError, TypeError):
        return valor


def build_parser() -> argparse.ArgumentParser:
    """Monta o parser com um subcomando por capacidade."""
    parser = argparse.ArgumentParser(
        prog="{pacote}",
        description="{spec.mission.objective}",
    )
    subparsers = parser.add_subparsers(dest="comando", required=True)
    for nome, funcao in COMANDOS.items():
        sub = subparsers.add_parser(nome, help=(funcao.__doc__ or "").strip().split("\\n")[0])
        for parametro in inspect.signature(funcao).parameters.values():
            if parametro.default is inspect.Parameter.empty:
                sub.add_argument(parametro.name)
            else:
                sub.add_argument(f"--{{parametro.name}}", default=parametro.default)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Executa um subcomando e imprime o resultado em JSON.

    Returns:
        0 em caso de sucesso, 2 quando a capacidade rejeita a entrada.
    """
    args = build_parser().parse_args(argv)
    funcao = COMANDOS[args.comando]
    parametros = list(inspect.signature(funcao).parameters)
    valores = {{p: _coerce(getattr(args, p)) for p in parametros if hasattr(args, p)}}

    try:
        resultado = funcao(**valores)
    except (ValueError, TypeError) as erro:
        print(json.dumps({{"erro": str(erro)}}, ensure_ascii=False))
        return 2

    print(json.dumps({{"comando": args.comando, "resultado": resultado}},
                     ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''
        main_py = f'''"""Permite executar o pacote com ``python -m {pacote}``."""

import sys

from {pacote}.cli import main

if __name__ == "__main__":
    sys.exit(main())
'''
        smoke = _cli_smoke([by_name(n) for n in sorted(exportados)])
        if smoke is None:
            bloco_smoke = ""
        else:
            nome_cmd, argv, esperado = smoke
            args = ", ".join(repr(a) for a in argv)
            afirmacao = (
                f"assert saida[\"resultado\"] == {esperado!r}"
                if esperado is not None
                else "assert \"resultado\" in saida"
            )
            bloco_smoke = f"""

def test_main_executa_capacidade_real(capsys):
    codigo = main(["{nome_cmd}", {args}])
    saida = json.loads(capsys.readouterr().out)
    assert codigo == 0
    assert saida["comando"] == "{nome_cmd}"
    {afirmacao}
"""

        teste_cli = f'''"""Testes da interface de linha de comando."""

import json

import pytest

from {pacote}.cli import COMANDOS, build_parser, main

ESPERADOS = {{{", ".join(repr(n) for n in sorted(exportados))}}}


def test_todas_as_capacidades_estao_registradas():
    assert set(COMANDOS) == ESPERADOS


def test_parser_rejeita_comando_desconhecido():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["comando_que_nao_existe"])


def test_parser_exige_um_comando():
    with pytest.raises(SystemExit):
        build_parser().parse_args([]){bloco_smoke}'''

        return [
            GeneratedFile(path=f"{pacote}/cli.py", content=cli),
            GeneratedFile(path=f"{pacote}/__main__.py", content=main_py),
            GeneratedFile(path="tests/test_cli.py", content=teste_cli),
        ]

    def _render_service(self, spec: BuildSpec, exportados: list[str]) -> list[GeneratedFile]:
        pacote = spec.package_name
        service = f'''"""Servico HTTP JSON de ``{pacote}``.

Usa apenas a biblioteca padrao: nao ha dependencia para instalar e o servico
sobe em qualquer maquina com Python. Cada capacidade publica e exposta em
``POST /api/<capacidade>`` recebendo um corpo JSON com os argumentos nomeados.
"""

from __future__ import annotations

import inspect
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from {pacote} import (
{chr(10).join(f"    {n}," for n in sorted(exportados))}
)

CAPACIDADES = {{
{chr(10).join(f'    "{n}": {n},' for n in sorted(exportados))}
}}

MAX_CORPO = 1_000_000


def descrever_api() -> dict:
    """Descreve as rotas disponiveis e a assinatura de cada capacidade."""
    return {{
        "servico": "{pacote}",
        "objetivo": "{spec.mission.objective}",
        "rotas": [
            {{
                "metodo": "POST",
                "caminho": f"/api/{{nome}}",
                "parametros": [p for p in inspect.signature(funcao).parameters],
            }}
            for nome, funcao in sorted(CAPACIDADES.items())
        ],
    }}


def executar(nome: str, payload: dict) -> tuple[int, dict]:
    """Executa uma capacidade e devolve status HTTP e corpo de resposta."""
    funcao = CAPACIDADES.get(nome)
    if funcao is None:
        return 404, {{"erro": f"capacidade desconhecida: {{nome}}"}}

    aceitos = set(inspect.signature(funcao).parameters)
    desconhecidos = set(payload) - aceitos
    if desconhecidos:
        return 400, {{"erro": f"parametros nao aceitos: {{sorted(desconhecidos)}}"}}

    try:
        return 200, {{"capacidade": nome, "resultado": funcao(**payload)}}
    except (ValueError, TypeError) as erro:
        return 400, {{"erro": str(erro)}}


class Handler(BaseHTTPRequestHandler):
    """Roteador HTTP minimo sobre as capacidades do pacote."""

    server_version = "{pacote}/0.1"

    def _responder(self, status: int, corpo: dict) -> None:
        dados = json.dumps(corpo, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self) -> None:  # noqa: N802 - nome exigido por BaseHTTPRequestHandler
        """Responde a descricao da API na raiz e em /api."""
        if self.path in ("/", "/api", "/api/"):
            self._responder(200, descrever_api())
        else:
            self._responder(404, {{"erro": "rota nao encontrada"}})

    def do_POST(self) -> None:  # noqa: N802 - nome exigido por BaseHTTPRequestHandler
        """Executa a capacidade indicada no caminho."""
        if not self.path.startswith("/api/"):
            self._responder(404, {{"erro": "rota nao encontrada"}})
            return

        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho > MAX_CORPO:
            self._responder(413, {{"erro": "corpo excede o limite"}})
            return

        bruto = self.rfile.read(tamanho) if tamanho else b"{{}}"
        try:
            payload = json.loads(bruto or b"{{}}")
        except json.JSONDecodeError:
            self._responder(400, {{"erro": "corpo nao e JSON valido"}})
            return
        if not isinstance(payload, dict):
            self._responder(400, {{"erro": "corpo deve ser um objeto JSON"}})
            return

        status, corpo = executar(self.path[len("/api/"):], payload)
        self._responder(status, corpo)

    def log_message(self, formato: str, *args) -> None:
        """Descarta o log de acesso padrao.

        O log do BaseHTTPRequestHandler escreve direto em stderr e polui a
        saida de teste. A supressao e deliberada e explicita.
        """
        return None


def criar_servidor(host: str = "127.0.0.1", porta: int = 8000) -> HTTPServer:
    """Cria o servidor HTTP ja vinculado ao endereco informado.

    Porta 0 faz o sistema operacional escolher uma porta livre, o que permite
    testar o servidor real sem conflito com outros processos.
    """
    return HTTPServer((host, porta), Handler)


def main(host: str = "127.0.0.1", porta: int = 8000, bloquear: bool = True) -> int:
    """Sobe o servidor HTTP ate receber interrupcao.

    Args:
        host: endereco de escuta.
        porta: porta de escuta; 0 escolhe uma porta livre.
        bloquear: quando False, o servidor sobe, reporta o endereco e encerra.
            Existe para que o caminho de inicializacao seja testavel.

    Returns:
        0 ao encerrar de forma limpa.
    """
    servidor = criar_servidor(host, porta)
    print(f"servico em http://{{host}}:{{servidor.server_address[1]}}")
    try:
        if bloquear:
            servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''
        teste_service = f'''"""Testes do servico HTTP, exercitando o roteamento real."""

import json
import threading
import urllib.error
import urllib.request

import pytest

from {pacote}.service import Handler, criar_servidor, descrever_api, executar, main


def test_descrever_api_lista_todas_as_capacidades():
    descricao = descrever_api()
    assert descricao["servico"] == "{pacote}"
    assert len(descricao["rotas"]) == {len(exportados)}


def test_executar_rejeita_capacidade_desconhecida():
    status, corpo = executar("nao_existe", {{}})
    assert status == 404
    assert "erro" in corpo


def test_executar_rejeita_parametro_desconhecido():
    status, corpo = executar("{sorted(exportados)[0]}", {{"parametro_invalido": 1}})
    assert status == 400


@pytest.fixture()
def servidor():
    """Sobe o servico real numa porta livre e o encerra ao fim do teste."""
    httpd = criar_servidor("127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{{httpd.server_address[1]}}"
    httpd.shutdown()
    httpd.server_close()


def test_get_raiz_descreve_api(servidor):
    with urllib.request.urlopen(f"{{servidor}}/") as resposta:
        corpo = json.loads(resposta.read())
    assert resposta.status == 200
    assert corpo["servico"] == "{pacote}"


def test_criar_servidor_vincula_porta_livre():
    httpd = criar_servidor("127.0.0.1", 0)
    try:
        assert httpd.server_address[1] > 0
    finally:
        httpd.server_close()


def test_main_sobe_e_encerra_sem_bloquear(capsys):
    assert main(porta=0, bloquear=False) == 0
    assert "servico em http://" in capsys.readouterr().out


def test_post_em_rota_inexistente_retorna_404(servidor):
    requisicao = urllib.request.Request(
        f"{{servidor}}/api/inexistente",
        data=b"{{}}",
        headers={{"Content-Type": "application/json"}},
    )
    with pytest.raises(urllib.error.HTTPError) as erro:
        urllib.request.urlopen(requisicao)
    assert erro.value.code == 404
'''
        return [
            GeneratedFile(path=f"{pacote}/service.py", content=service),
            GeneratedFile(path="tests/test_service.py", content=teste_service),
        ]

    def _render_readme(self, spec: BuildSpec, exportados: list[str]) -> GeneratedFile:
        linhas = [
            f"# {spec.package_name}",
            "",
            spec.mission.objective,
            "",
            "> Gerado pela SYRA Software Factory. Todo o codigo abaixo foi revisado",
            "> estaticamente e validado por uma suite de testes executada de verdade",
            "> antes da aprovacao.",
            "",
            "## Instalacao",
            "",
            "```bash",
            "python -m pip install -e .",
            "```",
            "",
            "## Capacidades",
            "",
        ]
        for module in spec.modules:
            linhas.append(f"### `{spec.package_name}.{module.name}`")
            linhas.append("")
            for funcao in module.functions:
                linhas.append(f"- **`{funcao.signature}`** — {funcao.summary}")
                for chamada, esperado in funcao.examples:
                    linhas.append(f"  - `{chamada}` → `{esperado}`")
            linhas.append("")

        if spec.kind == "cli":
            primeiro = sorted(exportados)[0]
            linhas += ["## Uso", "", "```bash",
                       f"python -m {spec.package_name} {primeiro} --help", "```", ""]
        elif spec.kind == "service":
            linhas += ["## Uso", "", "```bash",
                       f"python -m {spec.package_name}.service",
                       "curl http://127.0.0.1:8000/", "```", ""]

        linhas += ["## Testes", "", "```bash", "python -m pytest -q", "```", ""]
        return GeneratedFile(path="README.md", content="\n".join(linhas))

    def _render_pyproject(self, spec: BuildSpec) -> GeneratedFile:
        conteudo = f'''[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "{spec.package_name.replace("_", "-")}"
version = "0.1.0"
description = "{spec.mission.objective[:120]}"
requires-python = ">=3.9"
dependencies = []

[project.optional-dependencies]
test = ["pytest>=7"]
'''
        if spec.entrypoint:
            conteudo += f'\n[project.scripts]\n{spec.package_name} = "{spec.entrypoint}"\n'
        conteudo += f'\n[tool.setuptools]\npackages = ["{spec.package_name}"]\n'
        return GeneratedFile(path="pyproject.toml", content=conteudo)


_FENCE = re.compile(
    r"```(?:python|py)?\s*\n#\s*(?:file|arquivo):\s*(?P<path>[^\n]+)\n(?P<body>.*?)```",
    re.DOTALL,
)


class SubprocessSynthesizer:
    """Delega a sintese a um agente externo, sem afrouxar nenhum portao.

    O comando recebe o plano em JSON via stdin e deve responder com blocos de
    codigo cercados, cada um precedido por ``# file: caminho``. A saida passa
    exatamente pela mesma revisao, testes e governanca do modo deterministico.
    """

    def __init__(self, command: str, timeout: float = 300.0) -> None:
        self.command = command
        self.timeout = timeout
        self.name = f"subprocess:{shlex.split(command)[0] if command else 'vazio'}"

    def synthesize(self, spec: BuildSpec) -> GeneratedProject:
        """Executa o agente externo e converte a resposta em arquivos."""
        entrada = json.dumps(spec.to_dict(), ensure_ascii=False)
        try:
            processo = subprocess.run(  # noqa: S603 - comando definido pelo operador
                shlex.split(self.command),
                input=entrada,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as erro:
            raise SynthesisError(f"agente externo falhou: {erro}") from erro

        if processo.returncode != 0:
            raise SynthesisError(
                f"agente externo retornou {processo.returncode}: "
                f"{processo.stderr.strip()[:300]}"
            )

        arquivos = self.parse(processo.stdout)
        if not arquivos:
            raise SynthesisError("agente externo nao produziu nenhum arquivo valido")
        return GeneratedProject(files=tuple(arquivos), synthesizer=self.name)

    @staticmethod
    def parse(saida: str) -> list[GeneratedFile]:
        """Extrai arquivos de blocos cercados marcados com ``# file:``."""
        arquivos: list[GeneratedFile] = []
        for correspondencia in _FENCE.finditer(saida or ""):
            caminho = correspondencia.group("path").strip()
            # Caminhos absolutos ou com ".." escapariam do diretorio de build.
            if not caminho or caminho.startswith("/") or ".." in caminho:
                continue
            arquivos.append(GeneratedFile(path=caminho,
                                          content=correspondencia.group("body")))
        return arquivos
