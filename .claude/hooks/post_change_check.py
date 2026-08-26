#!/usr/bin/env python3
"""PostToolUse check for edited files.

The edit already occurred. Exit 2 surfaces actionable feedback to Claude so it
can remediate before proceeding.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key material"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "possible AWS access key"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"), "possible GitHub token"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "possible API secret"),
    (re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{12,}['\"]"), "hardcoded credential-like value"),
]

DANGEROUS_CONTENT: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\beval\s*\("), "dynamic eval introduced"),
    (re.compile(r"child_process\.(?:exec|execSync)\s*\("), "shell execution introduced"),
    (re.compile(r"subprocess\.(?:run|Popen|call)\([^\n]*shell\s*=\s*True"), "Python shell=True introduced"),
]

TEXT_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".json", ".yaml", ".yml",
    ".toml", ".md", ".sql", ".sh", ".css", ".scss", ".html", ".env", ".txt",
}


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("Post-change check could not parse hook JSON; review the last edit manually.", file=sys.stderr)
        return 2

    tool_name = str(event.get("tool_name", ""))
    if tool_name not in {"Write", "Edit", "MultiEdit"}:
        return 0

    tool_input = event.get("tool_input") or {}
    raw_path = tool_input.get("file_path") or tool_input.get("path")
    if not isinstance(raw_path, str):
        return 0

    path = Path(raw_path)
    if path.suffix.lower() not in TEXT_EXTENSIONS or not path.exists() or not path.is_file():
        return 0

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"Post-change check could not read {path}: {exc}", file=sys.stderr)
        return 2

    findings: list[str] = []
    for pattern, label in SECRET_PATTERNS:
        if pattern.search(text):
            findings.append(label)
    for pattern, label in DANGEROUS_CONTENT:
        if pattern.search(text):
            findings.append(label)

    if findings:
        unique = ", ".join(sorted(set(findings)))
        print(
            f"Review required for {path}: {unique}. Remove secrets or add an explicit, tested safety justification before continuing.",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
