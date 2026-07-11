"""Caché crudo con procedencia, invalidación por parámetros y escritura atómica.

Solo lo usa la capa ``ingest``. Cada JSON de una fuente externa lleva un
sidecar ``.meta.json`` con los parámetros de la consulta y el SHA-256 exacto
del payload. Cambiar años, producto o versión de la consulta invalida el
caché aunque el nombre del archivo permanezca igual.
"""

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

CACHE_SCHEMA_VERSION: Final = 1


def sha256_file(path: Path) -> str:
    """SHA-256 hexadecimal del contenido de ``path``."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def metadata_path(cache_file: Path) -> Path:
    """Ruta del sidecar de procedencia de un archivo de caché."""
    return cache_file.with_suffix(cache_file.suffix + ".meta.json")


def _atomic_write(path: Path, content: bytes) -> None:
    """Escribe bytes en la misma carpeta y publica con ``os.replace``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    """Serialización JSON estable y legible para cachés/manifiestos."""
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return text.encode("utf-8")


def read_json(cache_file: Path) -> dict[str, Any]:
    """Lee un objeto JSON; falla si la raíz no es un objeto."""
    payload: object = json.loads(cache_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"El caché {cache_file} no contiene un objeto JSON")
    return payload


def write_json_cache(
    cache_file: Path,
    payload: Mapping[str, Any],
    *,
    source: str,
    parameters: Mapping[str, Any],
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    """Publica payload + sidecar de procedencia de forma atómica.

    El JSON se reemplaza antes que su sidecar. Si el proceso cae entre ambos,
    la siguiente lectura detecta el hash/metadata ausente y repara el caché.
    """
    content = _json_bytes(payload)
    _atomic_write(cache_file, content)
    metadata: dict[str, Any] = {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "source": source,
        "parameters": dict(parameters),
        "payload_sha256": hashlib.sha256(content).hexdigest(),
        "retrieved_at_utc": retrieved_at or datetime.now(UTC).isoformat(),
    }
    _atomic_write(metadata_path(cache_file), _json_bytes(metadata))
    return metadata


def _metadata_matches(
    cache_file: Path, metadata: Mapping[str, Any], source: str, parameters: Mapping[str, Any]
) -> bool:
    """Comprueba versión, fuente, parámetros y hash del payload."""
    return (
        metadata.get("cache_schema_version") == CACHE_SCHEMA_VERSION
        and metadata.get("source") == source
        and metadata.get("parameters") == dict(parameters)
        and metadata.get("payload_sha256") == sha256_file(cache_file)
    )


def load_json_cache(
    cache_file: Path,
    fetch: Callable[[], dict[str, Any]],
    *,
    source: str,
    parameters: Mapping[str, Any],
    force: bool = False,
) -> tuple[dict[str, Any], bool]:
    """Lee un caché compatible o descarga y lo reemplaza.

    Returns:
        Tupla ``(payload, fetched)``; ``fetched`` indica si se tocó la red.

    Los cachés anteriores a los sidecars se adoptan una vez con su ``mtime``
    como fecha de recuperación. Esto conserva los datos locales existentes;
    a partir de ahí cualquier cambio de parámetros sí fuerza una descarga.
    """
    sidecar = metadata_path(cache_file)
    if cache_file.exists() and not force:
        payload = read_json(cache_file)
        if sidecar.exists():
            metadata = read_json(sidecar)
            if _metadata_matches(cache_file, metadata, source, parameters):
                return payload, False
        else:
            adopted_at = datetime.fromtimestamp(cache_file.stat().st_mtime, UTC).isoformat()
            write_json_cache(
                cache_file,
                payload,
                source=source,
                parameters=parameters,
                retrieved_at=adopted_at,
            )
            return payload, False

    payload = fetch()
    write_json_cache(cache_file, payload, source=source, parameters=parameters)
    return payload, True


def provenance_record(cache_file: Path, root: Path) -> dict[str, Any] | None:
    """Registro verificable de un caché para el manifiesto del snapshot."""
    if not cache_file.exists():
        return None
    sidecar = metadata_path(cache_file)
    metadata = read_json(sidecar) if sidecar.exists() else {}
    return {
        "path": cache_file.relative_to(root).as_posix(),
        "size_bytes": cache_file.stat().st_size,
        "sha256": sha256_file(cache_file),
        "source": metadata.get("source"),
        "parameters": metadata.get("parameters"),
        "retrieved_at_utc": metadata.get("retrieved_at_utc"),
    }
