"""Single source of truth for the core's identity and release version."""

from __future__ import annotations

CORE_NAME = "syra-core"
CORE_VERSION = "1.0.0"
CONTRACT_SCHEMA_VERSION = 1
EVIDENCE_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1

# Minimum interpreter the core is validated against. The core is stdlib-only on
# purpose: nothing it needs can be missing from a working Python install, so it
# can never break a host system by being added to it.
MIN_PYTHON = (3, 8)
