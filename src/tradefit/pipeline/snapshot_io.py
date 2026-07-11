"""Publicación transaccional y manifiestos verificables de snapshots."""

import json
import os
import shutil
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final
from uuid import uuid4

import pandas as pd

from tradefit.ingest.cache import sha256_file

SNAPSHOT_SCHEMA_VERSION: Final = 1
MANIFEST_FILENAME: Final = "manifest.json"


def create_staging_dir(target: Path) -> Path:
    """Crea un directorio temporal hermano de ``target`` (mismo volumen)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=target.parent))


def build_manifest(
    staging: Path,
    *,
    source_inputs: Sequence[Mapping[str, Any]],
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    """Describe parámetros, fuentes y SHA-256 de cada artefacto preparado."""
    artifacts = [
        {
            "path": path.relative_to(staging).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(staging.rglob("*"))
        if path.is_file() and path.name != MANIFEST_FILENAME
    ]
    return {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "parameters": dict(parameters),
        "source_inputs": [dict(item) for item in source_inputs],
        "artifacts": artifacts,
    }


def write_manifest(
    staging: Path,
    *,
    source_inputs: Sequence[Mapping[str, Any]],
    parameters: Mapping[str, Any],
) -> Path:
    """Escribe ``manifest.json`` dentro del staging y devuelve su ruta."""
    path = staging / MANIFEST_FILENAME
    payload = build_manifest(staging, source_inputs=source_inputs, parameters=parameters)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def refresh_manifest(snapshot: Path) -> None:
    """Recalcula hashes conservando parámetros y procedencia existentes."""
    path = snapshot / MANIFEST_FILENAME
    if not path.exists():
        return  # compatibilidad con snapshots anteriores al manifiesto
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Manifiesto inválido: {path}")
    source_inputs = payload.get("source_inputs")
    parameters = payload.get("parameters")
    if not isinstance(source_inputs, list) or not isinstance(parameters, dict):
        raise RuntimeError(f"Manifiesto incompleto: {path}")
    write_manifest(snapshot, source_inputs=source_inputs, parameters=parameters)


def verify_manifest(snapshot: Path) -> None:
    """Verifica versión, existencia, tamaño y hash de todos los artefactos."""
    manifest_path = snapshot / MANIFEST_FILENAME
    payload: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("snapshot_schema_version") != SNAPSHOT_SCHEMA_VERSION
    ):
        raise RuntimeError(f"Manifiesto incompatible: {manifest_path}")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise RuntimeError(f"Manifiesto sin lista de artefactos: {manifest_path}")
    for record in artifacts:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise RuntimeError(f"Registro inválido en {manifest_path}: {record!r}")
        path = snapshot / record["path"]
        if not path.resolve().is_relative_to(snapshot.resolve()):
            raise RuntimeError(f"Ruta fuera del snapshot en {manifest_path}: {record['path']}")
        if not path.is_file():
            raise RuntimeError(f"Artefacto ausente: {path}")
        if path.stat().st_size != record.get("size_bytes") or sha256_file(path) != record.get(
            "sha256"
        ):
            raise RuntimeError(f"Artefacto no coincide con el manifiesto: {path}")


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    """Lock por creación exclusiva; evita builds/publicaciones concurrentes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"Ya hay una construcción en curso ({path.name})") from exc
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        yield
    finally:
        os.close(descriptor)
        path.unlink(missing_ok=True)


def publish_snapshot(staging: Path, target: Path) -> None:
    """Reemplaza el snapshot completo; restaura el anterior si falla el swap.

    El staging debe ser hermano del destino para que los renombres permanezcan
    en el mismo volumen. Sustituir el directorio completo elimina artefactos
    opcionales obsoletos que una reconstrucción ya no produzca.
    """
    if staging.parent != target.parent:
        raise ValueError("staging y target deben ser hermanos para publicar el snapshot")
    lock_path = target.parent / f".{target.name}.publish.lock"
    backup = target.parent / f".{target.name}.backup-{uuid4().hex}"
    with exclusive_lock(lock_path):
        had_target = target.exists()
        if had_target:
            os.replace(target, backup)
        try:
            os.replace(staging, target)
        except BaseException:
            if had_target and backup.exists():
                os.replace(backup, target)
            raise
        if backup.exists():
            shutil.rmtree(backup)


def atomic_write_parquet(frame: pd.DataFrame, path: Path) -> None:
    """Publica un Parquet individual con reemplazo atómico."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}.", suffix=path.suffix, dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        frame.to_parquet(temporary, index=False)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
