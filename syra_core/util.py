"""Dependency-free helpers shared across the core.

Everything here is stdlib-only and side-effect free except the explicit write
helpers. Writes are atomic (temp file + ``os.replace``) so a crashed or killed
process can never leave a half-written artifact that a later gate would read as
truth.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_stamp(moment: Optional[datetime] = None) -> str:
    """Compact UTC stamp used for evidence directories: ``20260824T163200Z``."""
    return (moment or utc_now()).strftime("%Y%m%dT%H%M%SZ")


def utc_iso(moment: Optional[datetime] = None) -> str:
    """RFC3339 timestamp with second precision and a ``Z`` suffix."""
    value = (moment or utc_now()).astimezone(timezone.utc).replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Hashing / canonical serialisation
# ---------------------------------------------------------------------------


def canonical_json(value: Any) -> str:
    """Deterministic JSON: stable key order, no incidental whitespace.

    Two structurally identical objects always produce the same bytes, which is
    what makes content hashing meaningful for contracts and evidence.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def pretty_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: os.PathLike[str] | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(value: Any) -> str:
    """Content hash of any JSON-serialisable structure."""
    return sha256_text(canonical_json(value))


def short_id(seed: Optional[str] = None, length: int = 16) -> str:
    """Deterministic-if-seeded, random-if-not identifier."""
    if seed is None:
        return os.urandom(16).hex()[:length]
    return sha256_text(seed)[:length]


# ---------------------------------------------------------------------------
# Filesystem
# ---------------------------------------------------------------------------


def atomic_write_text(
    path: os.PathLike[str] | str,
    text: str,
    *,
    mode: int = 0o600,
) -> Path:
    """Write ``text`` to ``path`` atomically.

    The file either does not change or contains the complete new content. There
    is no observable intermediate state for another process (or a later gate) to
    misread.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    handle_fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent),
        prefix="." + target.name + ".",
        suffix=".tmp",
    )
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, str(target))
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return target


def read_json(path: os.PathLike[str] | str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: os.PathLike[str] | str, value: Any, *, mode: int = 0o600) -> Path:
    return atomic_write_text(path, pretty_json(value), mode=mode)


def render_tsv(fieldnames: Sequence[str], rows: Iterable[Dict[str, Any]]) -> str:
    """Render rows as TSV.

    Tabs and newlines inside values are escaped rather than quoted so the output
    stays parseable by ``cut``/``awk``/``column`` the way the existing SYRA gate
    artifacts are consumed.
    """
    lines: List[str] = ["\t".join(fieldnames)]
    for row in rows:
        cells = []
        for name in fieldnames:
            raw = row.get(name, "")
            text = "" if raw is None else str(raw)
            cells.append(text.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n"))
        lines.append("\t".join(cells))
    return "\n".join(lines) + "\n"


def env_path(name: str, default: os.PathLike[str] | str) -> Path:
    """Resolve a path from an environment override, falling back to ``default``."""
    raw = os.environ.get(name)
    if raw:
        return Path(raw).expanduser()
    return Path(default).expanduser()


def state_root() -> Path:
    return env_path("SYRA_STATE_ROOT", Path.home() / ".syra" / "state")


def evidence_root() -> Path:
    return env_path(
        "SYRA_EVIDENCE_ROOT",
        Path.home() / ".syra" / "evidence" / "product-platform",
    )


def workspace_root() -> Path:
    return env_path("SYRA_WORKSPACE", Path.home() / "Projects" / "SYRA")


# ---------------------------------------------------------------------------
# Structured console output
# ---------------------------------------------------------------------------


def kv(key: str, value: Any) -> str:
    """Render one ``KEY=VALUE`` line in the SYRA gate output convention."""
    if isinstance(value, bool):
        value = "YES" if value else "NO"
    return "{}={}".format(key, value)


def truncate(text: str, limit: int = 160) -> str:
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "\u2026"
