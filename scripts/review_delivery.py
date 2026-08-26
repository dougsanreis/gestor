#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import yaml
from jsonschema.validators import validator_for

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DOCS = [
    ROOT / "CLAUDE.md",
    ROOT / "PROMPT_MESTRE_CLAUDE_CODE.md",
    ROOT / "README_INSTALACAO.md",
    ROOT / "docs/specs/00_indice.md",
    ROOT / "docs/specs/07_arquitetura_squad_auto_otimizavel.md",
    ROOT / "docs/specs/13_dados_experimentacao_seguranca_operacoes.md",
    ROOT / "docs/implementation/ROADMAP.md",
    ROOT / "docs/implementation/TASKS.md",
    ROOT / "docs/implementation/RACI_E_GATES.md",
]

READ_ONLY_AGENTS = {
    "product-architect",
    "experiment-analyst",
    "independent-evaluator",
    "governor",
}

LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_required(errors: list[str]) -> None:
    for path in REQUIRED_DOCS:
        if not path.is_file():
            errors.append(f"missing required document: {path.relative_to(ROOT)}")


def check_schemas(errors: list[str]) -> None:
    schemas = list((ROOT / "contracts").glob("*.schema.json"))
    if len(schemas) < 7:
        errors.append(f"expected at least 7 schemas, found {len(schemas)}")
    for path in schemas:
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
            validator_for(schema).check_schema(schema)
        except Exception as exc:
            errors.append(f"invalid JSON Schema {path.relative_to(ROOT)}: {exc}")


def check_openapi(errors: list[str]) -> None:
    path = ROOT / "contracts/openapi.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"invalid OpenAPI YAML: {exc}")
        return
    if str(data.get("openapi", "")).split(".")[0] != "3":
        errors.append("OpenAPI major version must be 3")
    if not data.get("paths") or not data.get("components"):
        errors.append("OpenAPI must define paths and components")
    for ref in re.findall(r"\$ref:\s*['\"]?([^'\"\s]+)", path.read_text(encoding="utf-8")):
        if ref.startswith("./"):
            target = (path.parent / ref).resolve()
            if not target.is_file():
                errors.append(f"broken OpenAPI ref: {ref}")


def check_agents(errors: list[str]) -> None:
    agents = list((ROOT / ".claude/agents").glob("*.md"))
    if len(agents) < 10:
        errors.append(f"expected at least 10 agents, found {len(agents)}")
    for path in agents:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n") or "\n---\n" not in text[4:]:
            errors.append(f"invalid frontmatter: {path.relative_to(ROOT)}")
            continue
        end = text.find("\n---\n", 4)
        try:
            meta = yaml.safe_load(text[4:end]) or {}
        except Exception as exc:
            errors.append(f"invalid agent YAML {path.relative_to(ROOT)}: {exc}")
            continue
        if meta.get("name") != path.stem:
            errors.append(f"agent name/path mismatch: {path.relative_to(ROOT)}")
        if not meta.get("description") or not meta.get("tools"):
            errors.append(f"agent missing description/tools: {path.relative_to(ROOT)}")
        tools = meta.get("tools")
        if isinstance(tools, str):
            tools = [item.strip() for item in tools.split(",")]
        if path.stem in READ_ONLY_AGENTS and any(tool in {"Write", "Edit"} for tool in tools or []):
            errors.append(f"read-only agent has mutating tools: {path.stem}")


def check_settings(errors: list[str]) -> None:
    path = ROOT / ".claude/settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"invalid settings JSON: {exc}")
        return
    if "PreToolUse" not in data.get("hooks", {}) or "PostToolUse" not in data.get("hooks", {}):
        errors.append("settings must include PreToolUse and PostToolUse")
    for hook in (ROOT / ".claude/hooks").glob("*.py"):
        if not hook.is_file():
            errors.append(f"missing hook: {hook}")


def check_markdown_links(errors: list[str]) -> None:
    for path in ROOT.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for raw_target in LINK_RE.findall(text):
            target = raw_target.split("#", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = target.strip("<>")
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                errors.append(f"broken local link in {path.relative_to(ROOT)}: {raw_target}")


def write_manifest() -> None:
    ignored = {"DELIVERY_MANIFEST.sha256"}
    files = [p for p in ROOT.rglob("*") if p.is_file() and p.name not in ignored and "__pycache__" not in p.parts]
    lines = [f"{sha256(path)}  {path.relative_to(ROOT).as_posix()}" for path in sorted(files)]
    (ROOT / "DELIVERY_MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    errors: list[str] = []
    check_required(errors)
    check_schemas(errors)
    check_openapi(errors)
    check_agents(errors)
    check_settings(errors)
    check_markdown_links(errors)

    if errors:
        print("DELIVERY REVIEW: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    write_manifest()
    print("DELIVERY REVIEW: PASSED")
    print(f"Files hashed: {sum(1 for _ in (ROOT / 'DELIVERY_MANIFEST.sha256').read_text(encoding='utf-8').splitlines())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
