"""Control plane -- the list of every product that exists.

"Which panels do we actually have, where do they live, and what version are
they?" should be a lookup, not an archaeology project. This registry is that
lookup: a single JSON file recording every governed product, its manifest
fingerprint, and where it lives on disk.

Registration validates the manifest first, so a product cannot enter the control
plane in a shape nothing can reason about. Fingerprints are stored, so drift
between what was registered and what is on disk is detectable rather than
assumed.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from . import util
from .errors import ProductExists, ProductUnknown
from .manifest import MANIFEST_FILENAME, ProductManifest

REGISTRY_NAME = "product-registry.json"
SCHEMA_VERSION = 1


@dataclass
class ProductEntry:
    """One product as the control plane knows it."""

    product_id: str
    name: str
    kind: str
    version: str
    path: str
    fingerprint: str
    registered_at: str = field(default_factory=util.utc_iso)
    updated_at: str = field(default_factory=util.utc_iso)
    tags: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "productId": self.product_id,
            "name": self.name,
            "kind": self.kind,
            "version": self.version,
            "path": self.path,
            "fingerprint": self.fingerprint,
            "registeredAt": self.registered_at,
            "updatedAt": self.updated_at,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProductEntry":
        return cls(
            product_id=data["productId"],
            name=data.get("name", data["productId"]),
            kind=data.get("kind", "tool"),
            version=data.get("version", "0.0.0"),
            path=data.get("path", ""),
            fingerprint=data.get("fingerprint", ""),
            registered_at=data.get("registeredAt", util.utc_iso()),
            updated_at=data.get("updatedAt", util.utc_iso()),
            tags=list(data.get("tags", [])),
        )

    def render(self) -> str:
        return "PRODUCT={}|KIND={}|VERSION={}|PATH={}".format(
            self.product_id, self.kind, self.version, self.path
        )

    def drifted(self) -> Optional[str]:
        """Compare the registered fingerprint against the manifest on disk.

        Returns a reason string when the two disagree, ``None`` when they match.
        A drifted product is one the control plane can no longer describe
        accurately -- worth knowing before something depends on that
        description.
        """
        manifest_path = Path(self.path) / MANIFEST_FILENAME
        if not manifest_path.is_file():
            return "MANIFEST_MISSING"
        try:
            manifest = ProductManifest.load(manifest_path)
        except Exception:  # noqa: BLE001 - any load failure is drift
            return "MANIFEST_UNREADABLE"
        if manifest.fingerprint != self.fingerprint:
            return "FINGERPRINT_MISMATCH"
        return None


class ProductRegistry:
    """Persistent catalogue of governed products."""

    def __init__(self, path: Optional[Path | str] = None, *, autoload: bool = True) -> None:
        self.path = Path(path) if path else (util.state_root() / REGISTRY_NAME)
        self._entries: Dict[str, ProductEntry] = {}
        self._lock = threading.RLock()
        if autoload:
            self.load()

    # -- persistence ---------------------------------------------------

    def load(self) -> int:
        if not self.path.is_file():
            return 0
        try:
            data = util.read_json(self.path)
        except (OSError, ValueError):
            return 0
        with self._lock:
            self._entries = {
                entry["productId"]: ProductEntry.from_dict(entry)
                for entry in data.get("products", [])
                if "productId" in entry
            }
            return len(self._entries)

    def save(self) -> Path:
        with self._lock:
            payload = {
                "schemaVersion": SCHEMA_VERSION,
                "updatedAt": util.utc_iso(),
                "products": [
                    entry.as_dict()
                    for entry in sorted(
                        self._entries.values(), key=lambda e: e.product_id
                    )
                ],
            }
        return util.write_json(self.path, payload)

    # -- mutation ------------------------------------------------------

    def register(
        self,
        manifest: ProductManifest,
        *,
        path: Optional[Path | str] = None,
        tags: Optional[List[str]] = None,
        replace: bool = False,
    ) -> ProductEntry:
        location = Path(path) if path else (manifest.path.parent if manifest.path else None)
        if location is None:
            raise ProductUnknown(
                "Cannot register {!r} without a filesystem location".format(
                    manifest.product_id
                ),
                remediation="Pass path=, or load the manifest from disk.",
            )

        with self._lock:
            existing = self._entries.get(manifest.product_id)
            if existing is not None and not replace:
                raise ProductExists(
                    "Product {!r} is already registered".format(manifest.product_id),
                    detail={"existing_path": existing.path, "incoming": str(location)},
                    remediation=(
                        "Use replace=True to update the registration, or choose "
                        "a different productId."
                    ),
                )

            entry = ProductEntry(
                product_id=manifest.product_id,
                name=manifest.name,
                kind=manifest.kind,
                version=manifest.version,
                path=str(Path(location).resolve()),
                fingerprint=manifest.fingerprint,
                registered_at=existing.registered_at if existing else util.utc_iso(),
                tags=tags if tags is not None else (existing.tags if existing else []),
            )
            self._entries[entry.product_id] = entry

        self.save()
        return entry

    def deregister(self, product_id: str) -> None:
        with self._lock:
            if product_id not in self._entries:
                raise ProductUnknown(
                    "Product {!r} is not registered".format(product_id),
                    detail={"known": sorted(self._entries)},
                    remediation="Run `syra product list` to see registered products.",
                )
            del self._entries[product_id]
        self.save()

    # -- lookup --------------------------------------------------------

    def get(self, product_id: str) -> ProductEntry:
        with self._lock:
            entry = self._entries.get(product_id)
        if entry is None:
            raise ProductUnknown(
                "Product {!r} is not registered".format(product_id),
                detail={"known": sorted(self._entries)},
                remediation="Register it with `syra product register <path>`.",
            )
        return entry

    def has(self, product_id: str) -> bool:
        with self._lock:
            return product_id in self._entries

    def all(self) -> List[ProductEntry]:
        with self._lock:
            return sorted(self._entries.values(), key=lambda e: e.product_id)

    def by_kind(self, kind: str) -> List[ProductEntry]:
        return [entry for entry in self.all() if entry.kind == kind]

    def drift_report(self) -> List[Dict[str, Any]]:
        """Every registered product whose on-disk manifest no longer matches."""
        drifted: List[Dict[str, Any]] = []
        for entry in self.all():
            reason = entry.drifted()
            if reason:
                drifted.append(
                    {"productId": entry.product_id, "path": entry.path, "reason": reason}
                )
        return drifted

    def stats(self) -> Dict[str, Any]:
        entries = self.all()
        kinds: Dict[str, int] = {}
        for entry in entries:
            kinds[entry.kind] = kinds.get(entry.kind, 0) + 1
        return {
            "total": len(entries),
            "byKind": kinds,
            "drifted": len(self.drift_report()),
            "store": str(self.path),
        }

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
