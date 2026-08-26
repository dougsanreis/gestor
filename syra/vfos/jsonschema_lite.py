"""Validador JSON Schema sem dependencia externa.

Por que existe: o runtime aplica contratos em todo caminho de mutacao. Se a
validacao dependesse de uma biblioteca instalada, um ambiente sem ela
degradaria silenciosamente para "sem validacao" — o oposto de fail-closed.

Cobre exatamente as palavras-chave usadas pelos contratos do Vibe Funnel OS,
verificadas por inventario: type, properties, additionalProperties, required,
pattern, enum, const, items, minItems, maxItems, uniqueItems, minLength,
maxLength, minimum, maximum, exclusiveMinimum, maxProperties, format,
allOf, anyOf, not, if/then/else.

Palavra-chave desconhecida nao e ignorada em silencio: ``strict=True`` faz o
registro recusar o schema, para que um contrato futuro nunca passe menos
validado do que o autor supunha.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

SUPORTADAS = frozenset({
    "$schema", "$id", "title", "description", "default", "examples",
    "type", "properties", "additionalProperties", "required",
    "pattern", "enum", "const", "items", "minItems", "maxItems", "uniqueItems",
    "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum",
    "exclusiveMaximum", "maxProperties", "minProperties", "format",
    "allOf", "anyOf", "oneOf", "not", "if", "then", "else", "$defs",
})

_DATE_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_URI = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


@dataclass(frozen=True)
class Violation:
    """Uma violacao de contrato, localizada e nomeada."""

    path: str
    keyword: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.keyword}: {self.message}"

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "keyword": self.keyword, "message": self.message}


class SchemaNaoSuportado(ValueError):
    """Schema usa palavra-chave que este validador nao aplica."""


def assert_suportado(schema: Any, path: str = "$") -> None:
    """Recusa schemas com palavra-chave que este validador nao implementa.

    Falhar aqui e deliberado: aceitar um schema e aplicar menos regras do que
    ele declara e pior do que recusa-lo.
    """
    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        raise SchemaNaoSuportado(f"{path}: schema deve ser objeto ou booleano")

    for chave, valor in schema.items():
        if chave not in SUPORTADAS:
            raise SchemaNaoSuportado(f"{path}: palavra-chave nao suportada: {chave}")
        if chave in ("properties", "$defs"):
            for nome, sub in (valor or {}).items():
                assert_suportado(sub, f"{path}.{chave}.{nome}")
        elif chave in ("allOf", "anyOf", "oneOf"):
            for indice, sub in enumerate(valor or []):
                assert_suportado(sub, f"{path}.{chave}[{indice}]")
        elif chave in ("items", "not", "if", "then", "else"):
            assert_suportado(valor, f"{path}.{chave}")
        elif chave == "additionalProperties" and not isinstance(valor, bool):
            assert_suportado(valor, f"{path}.additionalProperties")


def _tipo_json(valor: Any) -> str:
    # Ordem importa: em Python bool e subclasse de int.
    if valor is None:
        return "null"
    if isinstance(valor, bool):
        return "boolean"
    if isinstance(valor, int):
        return "integer"
    if isinstance(valor, float):
        return "number"
    if isinstance(valor, str):
        return "string"
    if isinstance(valor, list):
        return "array"
    if isinstance(valor, dict):
        return "object"
    return "desconhecido"


def _tipo_confere(valor: Any, esperado: str) -> bool:
    real = _tipo_json(valor)
    if esperado == "number":
        return real in ("number", "integer")
    return real == esperado


def _canonico(valor: Any) -> str:
    """Serializacao estavel usada para igualdade estrutural."""
    return json.dumps(valor, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _formato_valido(texto: str, formato: str) -> bool:
    if formato == "date-time":
        # A forma sozinha nao basta: "2026-13-45T99:99:99Z" casa com o regex
        # mas nao existe. A data tambem precisa ser parseavel.
        if not _DATE_TIME.match(texto):
            return False
        try:
            datetime.fromisoformat(texto.replace("Z", "+00:00").replace("z", "+00:00"))
        except ValueError:
            return False
        return True
    if formato == "date":
        if not _DATE.match(texto):
            return False
        try:
            date.fromisoformat(texto)
        except ValueError:
            return False
        return True
    if formato == "uri":
        return bool(_URI.match(texto))
    # Formato desconhecido e anotacao, nao restricao.
    return True


def validate(instance: Any, schema: Any, path: str = "$") -> list[Violation]:
    """Valida ``instance`` contra ``schema`` e devolve todas as violacoes.

    Devolve a lista completa, nao a primeira falha: quem corrige um payload
    precisa ver tudo que esta errado de uma vez.
    """
    if schema is True or schema == {}:
        return []
    if schema is False:
        return [Violation(path, "schema", "nenhum valor e valido aqui")]

    erros: list[Violation] = []

    tipos = schema.get("type")
    if tipos is not None:
        aceitos = tipos if isinstance(tipos, list) else [tipos]
        if not any(_tipo_confere(instance, t) for t in aceitos):
            erros.append(Violation(
                path, "type",
                f"esperado {'|'.join(str(t) for t in aceitos)}, "
                f"recebido {_tipo_json(instance)}"))
            # Sem o tipo certo, as demais regras produziriam ruido.
            return erros

    if "const" in schema and _canonico(instance) != _canonico(schema["const"]):
        erros.append(Violation(path, "const",
                               f"valor deve ser {schema['const']!r}"))

    if "enum" in schema:
        permitidos = {_canonico(v) for v in schema["enum"]}
        if _canonico(instance) not in permitidos:
            erros.append(Violation(path, "enum",
                                   f"valor fora do conjunto permitido: {instance!r}"))

    erros.extend(_validar_string(instance, schema, path))
    erros.extend(_validar_numero(instance, schema, path))
    erros.extend(_validar_array(instance, schema, path))
    erros.extend(_validar_objeto(instance, schema, path))
    erros.extend(_validar_combinadores(instance, schema, path))
    return erros


def _validar_string(instance: Any, schema: dict, path: str) -> list[Violation]:
    if not isinstance(instance, str):
        return []
    erros: list[Violation] = []
    minimo = schema.get("minLength")
    if minimo is not None and len(instance) < minimo:
        erros.append(Violation(path, "minLength",
                               f"comprimento {len(instance)} abaixo de {minimo}"))
    maximo = schema.get("maxLength")
    if maximo is not None and len(instance) > maximo:
        erros.append(Violation(path, "maxLength",
                               f"comprimento {len(instance)} acima de {maximo}"))
    padrao = schema.get("pattern")
    # JSON Schema usa busca, nao ancoragem implicita.
    if padrao is not None and not re.search(padrao, instance):
        erros.append(Violation(path, "pattern",
                               f"nao casa com {padrao}"))
    formato = schema.get("format")
    if formato is not None and not _formato_valido(instance, formato):
        erros.append(Violation(path, "format", f"nao e um {formato} valido"))
    return erros


def _validar_numero(instance: Any, schema: dict, path: str) -> list[Violation]:
    if isinstance(instance, bool) or not isinstance(instance, (int, float)):
        return []
    erros: list[Violation] = []
    minimo = schema.get("minimum")
    if minimo is not None and instance < minimo:
        erros.append(Violation(path, "minimum", f"{instance} menor que {minimo}"))
    maximo = schema.get("maximum")
    if maximo is not None and instance > maximo:
        erros.append(Violation(path, "maximum", f"{instance} maior que {maximo}"))
    exclusivo_min = schema.get("exclusiveMinimum")
    if exclusivo_min is not None and instance <= exclusivo_min:
        erros.append(Violation(path, "exclusiveMinimum",
                               f"{instance} deve ser maior que {exclusivo_min}"))
    exclusivo_max = schema.get("exclusiveMaximum")
    if exclusivo_max is not None and instance >= exclusivo_max:
        erros.append(Violation(path, "exclusiveMaximum",
                               f"{instance} deve ser menor que {exclusivo_max}"))
    return erros


def _validar_array(instance: Any, schema: dict, path: str) -> list[Violation]:
    if not isinstance(instance, list):
        return []
    erros: list[Violation] = []
    minimo = schema.get("minItems")
    if minimo is not None and len(instance) < minimo:
        erros.append(Violation(path, "minItems",
                               f"{len(instance)} item(ns), minimo {minimo}"))
    maximo = schema.get("maxItems")
    if maximo is not None and len(instance) > maximo:
        erros.append(Violation(path, "maxItems",
                               f"{len(instance)} item(ns), maximo {maximo}"))
    if schema.get("uniqueItems") is True:
        vistos: set[str] = set()
        for indice, item in enumerate(instance):
            marca = _canonico(item)
            if marca in vistos:
                erros.append(Violation(f"{path}[{indice}]", "uniqueItems",
                                       "item duplicado"))
            vistos.add(marca)
    sub = schema.get("items")
    if sub is not None:
        for indice, item in enumerate(instance):
            erros.extend(validate(item, sub, f"{path}[{indice}]"))
    return erros


def _validar_objeto(instance: Any, schema: dict, path: str) -> list[Violation]:
    if not isinstance(instance, dict):
        return []
    erros: list[Violation] = []

    for obrigatorio in schema.get("required", []):
        if obrigatorio not in instance:
            erros.append(Violation(f"{path}.{obrigatorio}", "required",
                                   "propriedade obrigatoria ausente"))

    maximo = schema.get("maxProperties")
    if maximo is not None and len(instance) > maximo:
        erros.append(Violation(path, "maxProperties",
                               f"{len(instance)} propriedades, maximo {maximo}"))
    minimo = schema.get("minProperties")
    if minimo is not None and len(instance) < minimo:
        erros.append(Violation(path, "minProperties",
                               f"{len(instance)} propriedades, minimo {minimo}"))

    propriedades = schema.get("properties") or {}
    for nome, valor in instance.items():
        if nome in propriedades:
            erros.extend(validate(valor, propriedades[nome], f"{path}.{nome}"))

    extras = schema.get("additionalProperties")
    if extras is not None:
        nao_declaradas = [n for n in instance if n not in propriedades]
        if extras is False:
            for nome in nao_declaradas:
                erros.append(Violation(f"{path}.{nome}", "additionalProperties",
                                       "propriedade nao declarada no contrato"))
        elif extras is not True:
            for nome in nao_declaradas:
                erros.extend(validate(instance[nome], extras, f"{path}.{nome}"))
    return erros


def _validar_combinadores(instance: Any, schema: dict, path: str) -> list[Violation]:
    erros: list[Violation] = []

    for indice, sub in enumerate(schema.get("allOf", [])):
        erros.extend(validate(instance, sub, path))

    if "anyOf" in schema:
        alternativas = schema["anyOf"]
        if not any(not validate(instance, sub, path) for sub in alternativas):
            erros.append(Violation(path, "anyOf",
                                   "nenhuma das alternativas do contrato foi satisfeita"))

    if "oneOf" in schema:
        satisfeitas = sum(1 for sub in schema["oneOf"]
                          if not validate(instance, sub, path))
        if satisfeitas != 1:
            erros.append(Violation(path, "oneOf",
                                   f"{satisfeitas} alternativa(s) satisfeitas, esperado 1"))

    if "not" in schema and not validate(instance, schema["not"], path):
        erros.append(Violation(path, "not", "valor casa com um schema proibido"))

    if "if" in schema:
        condicao_ok = not validate(instance, schema["if"], path)
        ramo = schema.get("then") if condicao_ok else schema.get("else")
        if ramo is not None:
            erros.extend(validate(instance, ramo, path))
    return erros


def is_valid(instance: Any, schema: Any) -> bool:
    """Atalho booleano."""
    return not validate(instance, schema)
