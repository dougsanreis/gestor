"""Shared test helpers."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeClock:
    """Deterministic monotonic clock.

    Time in tests should be an input, not a wait. Anything that needs a
    stopwatch takes one of these instead of calling ``time.sleep``.
    """

    def __init__(self, start: float = 0.0) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += float(seconds)
        return self.now


class TempDirCase(unittest.TestCase):
    """Test case with an isolated temp directory and redirected SYRA roots."""

    def setUp(self) -> None:
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory(prefix="syra-test-")
        self.tmp = Path(self._tmp.name)
        self._saved_env = {
            key: os.environ.get(key)
            for key in ("SYRA_STATE_ROOT", "SYRA_EVIDENCE_ROOT", "SYRA_WORKSPACE")
        }
        os.environ["SYRA_STATE_ROOT"] = str(self.tmp / "state")
        os.environ["SYRA_EVIDENCE_ROOT"] = str(self.tmp / "evidence")
        os.environ["SYRA_WORKSPACE"] = str(self.tmp / "workspace")
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def path(self, *parts: str) -> Path:
        return self.tmp.joinpath(*parts)
