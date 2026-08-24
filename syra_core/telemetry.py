"""Structured tracing with no external dependencies.

Panels that "just break" are usually panels with no execution trace: the failure
is real but invisible, so it gets guessed at instead of diagnosed. Every call
that crosses the gateway emits a span here, with a trace id that survives across
connectors, so a broken panel produces a readable causal chain instead of a
stack trace with no context.

Output is newline-delimited JSON -- greppable, tailable, and ingestible by any
collector later without changing call sites.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, TextIO

from . import util

LEVELS = ("debug", "info", "warn", "error")


@dataclass
class SpanContext:
    """Handle passed to the body of a span so it can attach attributes."""

    trace_id: str
    span_id: str
    name: str
    attributes: Dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def update(self, **values: Any) -> None:
        self.attributes.update(values)


class Telemetry:
    """Span and event recorder.

    Records are kept in memory (bounded) for tests and health endpoints, and
    optionally mirrored to a JSONL sink. Nothing here blocks on I/O beyond a
    single line write, and a broken sink degrades to silence rather than taking
    the caller down with it -- telemetry must never be the reason a product
    fails.
    """

    def __init__(
        self,
        *,
        service: str = "syra-core",
        sink: Optional[Path | str | TextIO] = None,
        capture: int = 512,
        clock: Any = time.time,
        monotonic: Any = time.monotonic,
    ) -> None:
        self.service = service
        self._clock = clock
        self._monotonic = monotonic
        self._capture = max(0, int(capture))
        self._records: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._local = threading.local()
        self._sink_path: Optional[Path] = None
        self._sink_stream: Optional[TextIO] = None
        self._sink_broken = False

        if isinstance(sink, (str, os.PathLike)):
            self._sink_path = Path(sink)
            self._sink_path.parent.mkdir(parents=True, exist_ok=True)
        elif sink is not None:
            self._sink_stream = sink  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Internal state
    # ------------------------------------------------------------------

    @property
    def _stack(self) -> List[SpanContext]:
        stack = getattr(self._local, "stack", None)
        if stack is None:
            stack = []
            self._local.stack = stack
        return stack

    @property
    def trace_id(self) -> str:
        """Current trace id, minted lazily per thread."""
        existing = getattr(self._local, "trace_id", None)
        if existing is None:
            existing = util.short_id()
            self._local.trace_id = existing
        return existing

    @contextmanager
    def trace(self, trace_id: Optional[str] = None) -> Iterator[str]:
        """Scope a trace id, e.g. one inbound request across many connectors."""
        previous = getattr(self._local, "trace_id", None)
        self._local.trace_id = trace_id or util.short_id()
        try:
            yield self._local.trace_id
        finally:
            self._local.trace_id = previous

    # ------------------------------------------------------------------
    # Emission
    # ------------------------------------------------------------------

    def _emit(self, record: Dict[str, Any]) -> None:
        record.setdefault("ts", util.utc_iso())
        record.setdefault("service", self.service)

        if self._capture:
            with self._lock:
                self._records.append(record)
                if len(self._records) > self._capture:
                    del self._records[: len(self._records) - self._capture]

        if self._sink_broken:
            return

        line = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
        try:
            if self._sink_path is not None:
                with open(self._sink_path, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
            elif self._sink_stream is not None:
                self._sink_stream.write(line + "\n")
                self._sink_stream.flush()
        except OSError:
            # A telemetry sink that cannot be written to is a degraded
            # observability posture, never a product outage.
            self._sink_broken = True

    def event(self, name: str, *, level: str = "info", **attributes: Any) -> None:
        parent = self._stack[-1] if self._stack else None
        self._emit(
            {
                "kind": "event",
                "name": name,
                "level": level if level in LEVELS else "info",
                "trace_id": self.trace_id,
                "span_id": parent.span_id if parent else None,
                "attributes": attributes,
            }
        )

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[SpanContext]:
        """Time a unit of work and record how it ended."""
        parent = self._stack[-1] if self._stack else None
        context = SpanContext(
            trace_id=self.trace_id,
            span_id=util.short_id(),
            name=name,
            attributes=dict(attributes),
        )
        self._stack.append(context)
        started = self._monotonic()

        status = "ok"
        error: Optional[Dict[str, Any]] = None
        try:
            yield context
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            status = "error"
            error = {
                "type": type(exc).__name__,
                "code": getattr(exc, "code", None),
                "message": util.truncate(str(exc), 300),
            }
            raise
        finally:
            self._stack.pop()
            record: Dict[str, Any] = {
                "kind": "span",
                "name": name,
                "trace_id": context.trace_id,
                "span_id": context.span_id,
                "parent_id": parent.span_id if parent else None,
                "duration_ms": round((self._monotonic() - started) * 1000.0, 3),
                "status": status,
                "attributes": context.attributes,
            }
            if error:
                record["error"] = error
            self._emit(record)

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def records(self, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._records)
        if kind is None:
            return items
        return [item for item in items if item.get("kind") == kind]

    def spans(self, name: Optional[str] = None) -> List[Dict[str, Any]]:
        items = self.records("span")
        if name is None:
            return items
        return [item for item in items if item.get("name") == name]

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


def null_telemetry() -> Telemetry:
    """Recorder that keeps nothing. For hot paths and throwaway tests."""
    return Telemetry(capture=0)


def stderr_telemetry(service: str = "syra-core") -> Telemetry:
    return Telemetry(service=service, sink=sys.stderr)
