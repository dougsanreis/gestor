"""Empacotamento e entrega: transforma o build aprovado em artefato verificavel."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from syra.contracts import BuildSpec, GeneratedProject, PackageManifest, QAReport
from syra.paths import artifacts_dir


def build_manifest(spec: BuildSpec, project: GeneratedProject,
                   qa: QAReport) -> PackageManifest:
    """Monta o manifesto com o inventario e o hash de cada arquivo."""
    return PackageManifest(
        mission_id=spec.mission.mission_id,
        package_name=spec.package_name,
        kind=spec.kind,
        version="0.1.0",
        files=tuple(f.to_dict() for f in project.files),
        tests_passed=qa.passed,
    )


def package(project_dir: Path, manifest: PackageManifest,
            destino: Path | None = None) -> tuple[Path, PackageManifest]:
    """Escreve o manifesto e compacta o projeto num artefato .zip.

    Returns:
        O caminho do artefato e o manifesto atualizado com o hash do pacote.
    """
    manifest_path = project_dir / "package_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    destino = destino or (artifacts_dir() / f"{manifest.mission_id}.zip")
    destino.parent.mkdir(parents=True, exist_ok=True)

    arquivos = sorted(p for p in project_dir.rglob("*")
                      if p.is_file() and "__pycache__" not in p.parts)
    # Compactacao determinista: mesma entrada produz o mesmo hash de artefato.
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as pacote:
        for arquivo in arquivos:
            info = zipfile.ZipInfo(str(arquivo.relative_to(project_dir)),
                                   date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            pacote.writestr(info, arquivo.read_bytes())

    digest = hashlib.sha256(destino.read_bytes()).hexdigest()
    atualizado = PackageManifest(
        mission_id=manifest.mission_id, package_name=manifest.package_name,
        kind=manifest.kind, version=manifest.version, files=manifest.files,
        tests_passed=manifest.tests_passed, created_at=manifest.created_at,
        artifact_sha256=digest,
    )
    manifest_path.write_text(
        json.dumps(atualizado.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return destino, atualizado
