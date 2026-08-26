#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    ROOT / "CLAUDE.md",
    ROOT / ".claude/settings.json",
    ROOT / ".claude/hooks/guard_pre_tool.py",
    ROOT / ".claude/hooks/post_change_check.py",
    ROOT / "contracts/mission.schema.json",
    ROOT / "contracts/artifact.schema.json",
    ROOT / "contracts/governance-decision.schema.json",
    ROOT / "contracts/experiment.schema.json",
    ROOT / "contracts/event.schema.json",
]


def validate_json(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"{path}: invalid JSON: {exc}"]
    if path.name.endswith("schema.json"):
        if data.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            errors.append(f"{path}: unexpected or missing $schema")
        if data.get("additionalProperties") is not False:
            errors.append(f"{path}: root additionalProperties must be false")
        if not data.get("required"):
            errors.append(f"{path}: required must not be empty")
    return errors


def validate_python(path: Path) -> list[str]:
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        return []
    except SyntaxError as exc:
        return [f"{path}: Python syntax error: {exc}"]


def validate_agent(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return [f"{path}: missing YAML frontmatter"]
    end = text.find("\n---\n", 4)
    if end < 0:
        return [f"{path}: unclosed YAML frontmatter"]
    frontmatter = text[4:end]
    errors = []
    for field in ("name:", "description:", "tools:"):
        if field not in frontmatter:
            errors.append(f"{path}: missing {field[:-1]}")
    return errors


def main() -> int:
    errors: list[str] = []
    for path in REQUIRED:
        if not path.is_file():
            errors.append(f"missing required file: {path}")

    for path in ROOT.rglob("*.json"):
        errors.extend(validate_json(path))
    for path in (ROOT / ".claude/hooks").glob("*.py"):
        errors.extend(validate_python(path))
    for path in (ROOT / ".claude/agents").glob("*.md"):
        errors.extend(validate_agent(path))

    if errors:
        print("PACK VALIDATION: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("PACK VALIDATION: PASSED")
    print(f"Agents: {len(list((ROOT / '.claude/agents').glob('*.md')))}")
    print(f"Schemas: {len(list((ROOT / 'contracts').glob('*.json')))}")
    print(f"Hooks: {len(list((ROOT / '.claude/hooks').glob('*.py')))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
