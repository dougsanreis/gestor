#!/usr/bin/env python3
"""PreToolUse safety gate for Claude Code.

Reads hook JSON from stdin. Emits a deny decision for explicitly dangerous
operations. Silence means normal Claude Code permission flow continues.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


DENY_COMMAND_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(^|[;&|]\s*)rm\s+-[^\n]*r[^\n]*f", re.I), "recursive forced deletion"),
    (re.compile(r"\bgit\s+reset\s+--hard\b", re.I), "destructive git reset"),
    (re.compile(r"\bgit\s+clean\s+-[^\n]*[fdx]", re.I), "destructive git clean"),
    # Posição de comando é obrigatória. O padrão anterior casava a palavra em
    # qualquer lugar da linha, então `servidor.shutdown()` num script Python,
    # um comentário ou um `grep` pela palavra eram bloqueados como se fossem
    # desligamento de host. Aqui o termo só conta como comando quando abre a
    # linha ou vem após separador/sudo/systemctl, e nunca quando é seguido de
    # parêntese — o que caracteriza chamada de método.
    (re.compile(r"(?:^|[;&|]\s*|\bsudo\s+|\bsystemctl\s+)"
                r"(?:shutdown|reboot|poweroff|halt)\b(?!\s*\()", re.I | re.M),
     "host shutdown"),
    (re.compile(r"\bmkfs(?:\.[a-z0-9]+)?\b", re.I), "filesystem formatting"),
    (re.compile(r"\bdd\s+[^\n]*\bof=/dev/", re.I), "raw device write"),
    (re.compile(r"\bsudo\s+rm\b", re.I), "privileged deletion"),
    # `curl ... | sudo sh` passava pelo padrão anterior, que exigia `sh` logo
    # após o pipe: qualquer prefixo de elevação ou de ambiente escapava. Agora
    # o prefixo é consumido e outros shells são cobertos.
    (re.compile(r"(?:curl|wget)[^\n|]*\|\s*(?:sudo\s+|doas\s+|env\s+\S+\s+)*"
                r"(?:ba|z|k|da|fi)?sh\b", re.I),
     "download-and-execute pipeline"),
    (re.compile(r"\bchmod\s+-R\s+777\b", re.I), "world-writable recursive permissions"),
    (re.compile(r"\bkill\s+-9\s+(?:-1|1|0)\b", re.I), "broad forced process termination"),
    (re.compile(r"\bterraform\s+destroy\b", re.I), "infrastructure destruction"),
    (re.compile(r"\bDROP\s+(?:DATABASE|SCHEMA)\b", re.I), "database/schema destruction"),
    (re.compile(r"\bkubectl\b[^\n]*(?:--context|--namespace|-n)\s+[^\s]*(?:prod|production)", re.I), "direct production cluster operation"),
]

SENSITIVE_FILE_PATTERNS = [
    re.compile(r"(^|/)\.env(?:\.|$)"),
    re.compile(r"(^|/)(?:id_rsa|id_ed25519|.*\.pem|.*\.key)$", re.I),
    re.compile(r"(^|/)(?:secrets?|credentials?)(?:\.|/|$)", re.I),
]

PROTECTED_FILE_PATTERNS = [
    re.compile(r"(^|/)policies?/production/", re.I),
    re.compile(r"(^|/)pricing/approved", re.I),
    re.compile(r"(^|/)evidence/[^/]+/manifest\.json$", re.I),
]


def _alternativa_segura(command: str) -> str:
    """Consulta o motor de quarentena da SYRA por uma alternativa reversível.

    A dependência é opcional de propósito: o hook precisa funcionar num
    repositório que ainda não tenha a SYRA instalada. Quando ela existe, a
    recusa deixa de ser só um "não" e passa a apontar o caminho seguro.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from syra.governance.quarantine import CommandQuarantine

        avaliacao = CommandQuarantine().assess(command)
    except Exception:
        return ""
    if avaliacao.safe_alternative:
        return (f" Alternativa segura: {avaliacao.safe_alternative} "
                f"(risco {avaliacao.score}/100).")
    return f" Risco avaliado em {avaliacao.score}/100."


def deny(reason: str, command: str = "") -> None:
    sugestao = _alternativa_segura(command) if command else ""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Bloqueado pelo safety gate: {reason}. Use uma alternativa "
                f"reversível e solicite aprovação quando aplicável.{sugestao}"
            ),
        }
    }
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def normalized_path(value: object) -> str:
    if not isinstance(value, str):
        return ""
    try:
        return Path(value).as_posix()
    except Exception:
        return value.replace("\\", "/")


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        deny("entrada JSON inválida no hook")
        return 0

    tool_name = str(event.get("tool_name", ""))
    tool_input = event.get("tool_input") or {}

    if tool_name == "Bash":
        command = str(tool_input.get("command", ""))
        for pattern, reason in DENY_COMMAND_PATTERNS:
            if pattern.search(command):
                deny(reason, command)
                return 0

    if tool_name in {"Write", "Edit", "MultiEdit"}:
        file_path = normalized_path(tool_input.get("file_path") or tool_input.get("path"))
        for pattern in SENSITIVE_FILE_PATTERNS:
            if pattern.search(file_path):
                deny(f"escrita em arquivo sensível: {file_path}")
                return 0
        for pattern in PROTECTED_FILE_PATTERNS:
            if pattern.search(file_path):
                deny(f"arquivo protegido exige fluxo próprio: {file_path}")
                return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
