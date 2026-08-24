"""Failure memory -- the same defect may not be discovered twice.

Repeated errors are not bad luck; they are an absence of memory. A failure gets
worked around, the workaround is forgotten, and six weeks later the same defect
costs the same day of debugging.

This module gives failures an identity that survives restarts:

* a **fingerprint** derived from the stable error code, the call site, and a
  *normalised* message (ids, paths, ports, hex and quoted values stripped) so
  ``connection refused to 10.0.0.5:8080`` and ``... 10.0.0.9:9090`` are
  recognised as one defect, not two;
* an **open/resolved lifecycle** with a written resolution note;
* ``guard()``, which refuses to repeat a known-open failure at a known site
  before the expensive call is made.

The store is a single JSON file written atomically. It is state, not evidence:
evidence is immutable, failure memory is meant to be updated as things get
fixed.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from . import util
from .errors import RepeatedFailure, SyraError

OPEN = "OPEN"
RESOLVED = "RESOLVED"
ACCEPTED = "ACCEPTED"
"""ACCEPTED: a known failure someone deliberately chose to live with."""

STORE_NAME = "failure-memory.json"
SCHEMA_VERSION = 1

# Order matters: longer, more specific shapes are replaced before their parts.
_NORMALISERS = (
    (re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"), "<uuid>"),
    (re.compile(r"\b(?:0x)?[0-9a-fA-F]{16,}\b"), "<hash>"),
    (re.compile(r"(?:/[\w.\-@+]+){2,}/?"), "<path>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<ip>"),
    (re.compile(r"'[^']*'"), "<str>"),
    (re.compile(r'"[^"]*"'), "<str>"),
    (re.compile(r"\b\d+\b"), "<n>"),
    (re.compile(r"\s+"), " "),
)


def normalise(message: str) -> str:
    """Reduce a message to its defect shape, dropping incidental values."""
    text = str(message)
    for pattern, replacement in _NORMALISERS:
        text = pattern.sub(replacement, text)
    return text.strip().lower()[:400]


@dataclass
class FailureRecord:
    """One distinct defect and everything known about it."""

    fingerprint: str
    code: str
    site: str
    signature: str
    status: str = OPEN
    count: int = 0
    first_seen: str = field(default_factory=util.utc_iso)
    last_seen: str = field(default_factory=util.utc_iso)
    resolution: str = ""
    samples: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        return self.status == OPEN

    def as_dict(self) -> Dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "code": self.code,
            "site": self.site,
            "signature": self.signature,
            "status": self.status,
            "count": self.count,
            "firstSeen": self.first_seen,
            "lastSeen": self.last_seen,
            "resolution": self.resolution,
            "samples": self.samples,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FailureRecord":
        return cls(
            fingerprint=data["fingerprint"],
            code=data.get("code", "SYRA-E-INTERNAL"),
            site=data.get("site", "unknown"),
            signature=data.get("signature", ""),
            status=data.get("status", OPEN),
            count=int(data.get("count", 0)),
            first_seen=data.get("firstSeen", util.utc_iso()),
            last_seen=data.get("lastSeen", util.utc_iso()),
            resolution=data.get("resolution", ""),
            samples=list(data.get("samples", [])),
        )

    def render(self) -> str:
        return (
            "FINGERPRINT={}|STATUS={}|COUNT={}|CODE={}|SITE={}|SIGNATURE={}".format(
                self.fingerprint[:12],
                self.status,
                self.count,
                self.code,
                self.site,
                util.truncate(self.signature, 90),
            )
        )


class FailureMemory:
    """Persistent, deduplicating record of everything that has gone wrong."""

    MAX_SAMPLES = 5

    def __init__(
        self,
        path: Optional[Path | str] = None,
        *,
        block_repeats: bool = False,
        autoload: bool = True,
    ) -> None:
        self.path = Path(path) if path else (util.state_root() / STORE_NAME)
        self.block_repeats = block_repeats
        self._records: Dict[str, FailureRecord] = {}
        self._lock = threading.RLock()
        if autoload:
            self.load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> int:
        if not self.path.is_file():
            return 0
        try:
            data = util.read_json(self.path)
        except (OSError, ValueError):
            # A corrupt memory file must not stop a product from booting. Start
            # empty; the file is rewritten on the next recorded failure.
            return 0
        with self._lock:
            self._records = {
                entry["fingerprint"]: FailureRecord.from_dict(entry)
                for entry in data.get("failures", [])
                if "fingerprint" in entry
            }
            return len(self._records)

    def save(self) -> Path:
        with self._lock:
            payload = {
                "schemaVersion": SCHEMA_VERSION,
                "updatedAt": util.utc_iso(),
                "failures": [
                    record.as_dict()
                    for record in sorted(
                        self._records.values(), key=lambda r: r.last_seen, reverse=True
                    )
                ],
            }
        return util.write_json(self.path, payload)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @staticmethod
    def fingerprint_of(code: str, site: str, message: str) -> str:
        return util.sha256_text(
            "{}|{}|{}".format(code, site, normalise(message))
        )[:32]

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        error: BaseException,
        *,
        site: str,
        context: Optional[Mapping[str, Any]] = None,
        persist: bool = True,
    ) -> FailureRecord:
        """Register an occurrence, creating or updating the defect record."""
        code = getattr(error, "code", None) or "SYRA-E-UNCLASSIFIED:{}".format(
            type(error).__name__
        )
        message = str(getattr(error, "message", None) or error)
        signature = normalise(message)
        key = self.fingerprint_of(code, site, message)
        now = util.utc_iso()

        with self._lock:
            record = self._records.get(key)
            if record is None:
                record = FailureRecord(
                    fingerprint=key,
                    code=code,
                    site=site,
                    signature=signature,
                    first_seen=now,
                )
                self._records[key] = record
            elif record.status == RESOLVED:
                # A resolved defect that reappeared was not actually resolved.
                # Reopening it is the honest state, and the old resolution note
                # is kept as history of the failed fix.
                record.status = OPEN
                record.resolution = (
                    "REGRESSED after: {}".format(record.resolution)
                    if record.resolution
                    else "REGRESSED"
                )

            record.count += 1
            record.last_seen = now

            sample: Dict[str, Any] = {
                "at": now,
                "message": util.truncate(message, 300),
            }
            if context:
                sample["context"] = {
                    key_: util.truncate(str(value), 160)
                    for key_, value in list(context.items())[:10]
                }
            record.samples.append(sample)
            if len(record.samples) > self.MAX_SAMPLES:
                # Keep the first sample (how it started) and the most recent
                # ones (how it looks now); drop the indistinguishable middle.
                record.samples = record.samples[:1] + record.samples[-(self.MAX_SAMPLES - 1) :]

        if persist:
            try:
                self.save()
            except OSError:
                pass  # Memory is best-effort; it must never break the caller.
        return record

    # ------------------------------------------------------------------
    # Prevention
    # ------------------------------------------------------------------

    def guard(self, site: str, *, code: Optional[str] = None) -> Optional[FailureRecord]:
        """Check whether this site has a known-open defect.

        Returns the record if one exists. When ``block_repeats`` is enabled the
        call is refused instead -- the point of remembering a failure is to stop
        paying for it again.
        """
        with self._lock:
            matches = [
                record
                for record in self._records.values()
                if record.site == site
                and record.status == OPEN
                and (code is None or record.code == code)
            ]

        if not matches:
            return None

        worst = max(matches, key=lambda record: record.count)
        if not self.block_repeats:
            return worst

        raise RepeatedFailure(
            "Refusing a call at {!r}: known-open defect {} has already failed "
            "{} time(s)".format(site, worst.code, worst.count),
            detail={
                "site": site,
                "fingerprint": worst.fingerprint,
                "code": worst.code,
                "count": worst.count,
                "signature": worst.signature,
                "first_seen": worst.first_seen,
                "last_seen": worst.last_seen,
            },
            remediation=(
                "Fix the defect and mark it resolved "
                "(`syra failures resolve {}`), or accept it explicitly. "
                "Repeating it unchanged will not produce a different "
                "result.".format(worst.fingerprint[:12])
            ),
            site=site,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def resolve(self, fingerprint: str, note: str, *, status: str = RESOLVED) -> FailureRecord:
        with self._lock:
            record = self._match(fingerprint)
            record.status = status
            record.resolution = note
            record.last_seen = util.utc_iso()
        self.save()
        return record

    def accept(self, fingerprint: str, note: str) -> FailureRecord:
        """Mark a defect as a known, deliberately tolerated condition."""
        return self.resolve(fingerprint, note, status=ACCEPTED)

    def _match(self, fingerprint: str) -> FailureRecord:
        exact = self._records.get(fingerprint)
        if exact is not None:
            return exact
        prefixed = [
            record
            for key, record in self._records.items()
            if key.startswith(fingerprint)
        ]
        if len(prefixed) == 1:
            return prefixed[0]
        if not prefixed:
            raise SyraError(
                "No failure recorded under fingerprint {!r}".format(fingerprint),
                detail={"fingerprint": fingerprint},
                remediation="Run `syra failures list` to see known fingerprints.",
            )
        raise SyraError(
            "Fingerprint prefix {!r} matches {} records".format(
                fingerprint, len(prefixed)
            ),
            detail={"matches": [record.fingerprint for record in prefixed]},
            remediation="Use a longer prefix or the full fingerprint.",
        )

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def all(self) -> List[FailureRecord]:
        with self._lock:
            return sorted(
                self._records.values(), key=lambda r: (r.status != OPEN, -r.count)
            )

    def open_failures(self) -> List[FailureRecord]:
        return [record for record in self.all() if record.status == OPEN]

    def get(self, fingerprint: str) -> FailureRecord:
        with self._lock:
            return self._match(fingerprint)

    def stats(self) -> Dict[str, Any]:
        records = self.all()
        return {
            "total": len(records),
            "open": sum(1 for r in records if r.status == OPEN),
            "resolved": sum(1 for r in records if r.status == RESOLVED),
            "accepted": sum(1 for r in records if r.status == ACCEPTED),
            "occurrences": sum(r.count for r in records),
            "store": str(self.path),
        }

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
        self.save()
