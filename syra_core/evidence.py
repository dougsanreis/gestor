"""Evidence runs: decisions that exist on disk, hashed, or not at all.

The failure that produced this core was a gate whose discovery passed in memory
and whose artifacts were never persisted -- so the next gate had nothing to read
and the whole investigation had to be redone. This module makes that
structurally impossible:

* every artifact is written atomically, so there is no partial-file state;
* every artifact is hashed as it is written, not later;
* the manifest is sealed last and covers everything, so a truncated run is
  visibly unsealed rather than quietly incomplete;
* ``seal()`` refuses to certify a run whose declared artifacts are missing.

An unsealed evidence directory is evidence of a failed run. Do not delete it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from . import util
from .errors import EvidenceError
from .safety import SafetyContract
from .version import CORE_VERSION, EVIDENCE_SCHEMA_VERSION

MANIFEST_NAME = "evidence-manifest.json"


@dataclass(frozen=True)
class ArtifactRef:
    """A persisted artifact and the hash it had at write time."""

    name: str
    path: Path
    bytes: int
    sha256: str

    def as_dict(self) -> Dict[str, Any]:
        return {"file": self.name, "bytes": self.bytes, "sha256": self.sha256}

    def render(self) -> str:
        return "ARTIFACT={}|BYTES={}|SHA256={}".format(self.name, self.bytes, self.sha256)


@dataclass
class EvidenceRun:
    """One gate execution and the directory that holds its proof."""

    work_id: str
    gate: str
    safety: SafetyContract
    root: Optional[Path] = None
    variant: str = "V1"
    _artifacts: List[ArtifactRef] = field(default_factory=list, init=False, repr=False)
    _sealed: bool = field(default=False, init=False, repr=False)
    _dir: Path = field(init=False, repr=False)

    def __post_init__(self) -> None:
        base = Path(self.root) if self.root else util.evidence_root()
        stamp = util.utc_stamp()
        self._dir = Path(base) / "{}-{}-{}-{}".format(
            stamp, self.work_id, self.gate, self.variant
        )
        self.safety.require("filesystem_write", site="evidence.run")
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def dir(self) -> Path:
        return self._dir

    @property
    def artifacts(self) -> Sequence[ArtifactRef]:
        return tuple(self._artifacts)

    @property
    def sealed(self) -> bool:
        return self._sealed

    # ------------------------------------------------------------------
    # Writers
    # ------------------------------------------------------------------

    def _record(self, name: str, path: Path) -> ArtifactRef:
        ref = ArtifactRef(
            name=name,
            path=path,
            bytes=path.stat().st_size,
            sha256=util.sha256_file(path),
        )
        # Rewriting an artifact replaces its record rather than appending a
        # second one; the manifest must describe the final state exactly once.
        self._artifacts = [item for item in self._artifacts if item.name != name]
        self._artifacts.append(ref)
        return ref

    def _guard_open(self) -> None:
        if self._sealed:
            raise EvidenceError(
                "Evidence run is already sealed and cannot accept new artifacts",
                detail={"gate": self.gate, "dir": str(self._dir)},
                remediation="Start a new EvidenceRun for follow-up work.",
            )

    def write_text(self, name: str, text: str) -> ArtifactRef:
        self._guard_open()
        path = util.atomic_write_text(self._dir / name, text)
        return self._record(name, path)

    def write_json(self, name: str, value: Any) -> ArtifactRef:
        return self.write_text(name, util.pretty_json(value))

    def write_tsv(
        self,
        name: str,
        fieldnames: Sequence[str],
        rows: Iterable[Dict[str, Any]],
    ) -> ArtifactRef:
        return self.write_text(name, util.render_tsv(fieldnames, rows))

    # ------------------------------------------------------------------
    # Sealing
    # ------------------------------------------------------------------

    def seal(
        self,
        *,
        decision: str,
        next_state: str,
        required: Sequence[str] = (),
        summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Write the manifest that closes the run.

        ``required`` names artifacts this gate promised to produce. If any is
        missing or empty the run is refused -- a gate cannot report PASS on
        evidence it did not actually write.
        """
        self._guard_open()

        missing: List[str] = []
        empty: List[str] = []
        by_name = {item.name: item for item in self._artifacts}
        for name in required:
            ref = by_name.get(name)
            if ref is None:
                missing.append(name)
            elif ref.bytes == 0:
                empty.append(name)

        if missing or empty:
            raise EvidenceError(
                "Gate declared artifacts it did not produce",
                detail={
                    "gate": self.gate,
                    "missing": missing,
                    "empty": empty,
                    "dir": str(self._dir),
                },
                remediation=(
                    "Treat this run as FAIL. The evidence directory is kept as "
                    "proof of the failed run -- do not delete it."
                ),
            )

        manifest: Dict[str, Any] = {
            "schemaVersion": EVIDENCE_SCHEMA_VERSION,
            "coreVersion": CORE_VERSION,
            "workId": self.work_id,
            "gate": self.gate,
            "decision": decision,
            "nextState": next_state,
            "sealedAt": util.utc_iso(),
            "safety": self.safety.as_dict(),
            "invariants": self.safety.invariants(),
            "artifacts": [
                ref.as_dict() for ref in sorted(self._artifacts, key=lambda r: r.name)
            ],
        }
        if summary:
            manifest["summary"] = summary

        path = util.atomic_write_text(self._dir / MANIFEST_NAME, util.pretty_json(manifest))
        self._sealed = True
        manifest["manifestSha256"] = util.sha256_file(path)
        return manifest

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def render_artifacts(self) -> str:
        lines = ["===== ARTIFACT VALIDATOR ====="]
        lines.extend(ref.render() for ref in sorted(self._artifacts, key=lambda r: r.name))
        return "\n".join(lines)


def load_manifest(evidence_dir: Path | str) -> Dict[str, Any]:
    """Read a sealed manifest and verify every artifact still hashes true.

    This is the guard against a later gate consuming evidence that was edited,
    truncated, or partially overwritten after it was certified.
    """
    directory = Path(evidence_dir)
    path = directory / MANIFEST_NAME

    if not path.is_file():
        raise EvidenceError(
            "Evidence directory has no sealed manifest",
            detail={"dir": str(directory)},
            remediation=(
                "The run that produced this directory did not complete. Re-run "
                "the gate; do not consume unsealed evidence."
            ),
        )

    manifest = util.read_json(path)
    drifted: List[Dict[str, Any]] = []
    for entry in manifest.get("artifacts", []):
        artifact_path = directory / entry["file"]
        if not artifact_path.is_file():
            drifted.append({"file": entry["file"], "reason": "MISSING"})
            continue
        actual = util.sha256_file(artifact_path)
        if actual != entry["sha256"]:
            drifted.append(
                {
                    "file": entry["file"],
                    "reason": "SHA256_MISMATCH",
                    "expected": entry["sha256"],
                    "actual": actual,
                }
            )

    if drifted:
        raise EvidenceError(
            "Sealed evidence no longer matches its manifest",
            detail={"dir": str(directory), "drifted": drifted},
            remediation=(
                "The evidence was modified after sealing. Re-run the gate that "
                "produced it; do not trust these artifacts."
            ),
        )

    return manifest


def latest_run(gate: Optional[str] = None, root: Optional[Path] = None) -> Optional[Path]:
    """Most recent evidence directory, optionally filtered by gate name."""
    base = Path(root) if root else util.evidence_root()
    if not base.is_dir():
        return None
    candidates = [
        item
        for item in base.iterdir()
        if item.is_dir() and (gate is None or "-{}-".format(gate) in item.name)
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item.name)[-1]
