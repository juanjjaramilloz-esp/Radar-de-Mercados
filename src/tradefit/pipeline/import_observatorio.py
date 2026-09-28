"""Importa el paquete del Observatorio de subsectores con su contrato verificado.

El Observatorio (repositorio Observatorio-comercio) construye cuatro tablas a
partir de los microdatos del DANE y las deja en su ``data/processed/radar/``
con un ``manifest.json`` en el mismo formato que los snapshots de Radar: hash y
tamaño de cada archivo, versión del contrato, commit que lo produjo y hash de
cada archivo del DANE de origen. Antes de este comando los archivos se copiaban
a mano, y nada impedía traer una tabla vieja o a medio regenerar.

Qué verifica, en orden, antes de tocar ``data/processed/observatorio/``:

1. El manifiesto: versión de formato, existencia, tamaño y SHA-256 de cada
   artefacto (``snapshot_io.verify_manifest``).
2. El contrato: nombre y versión que esta versión de Radar sabe leer.
3. Que estén las cuatro tablas y ``meta.json``, y que cada tabla cumpla su
   esquema pandera (``contracts.OBSERVATORIO_TABLES``).

Si todo pasa, publica el paquete completo de forma atómica (``publish_snapshot``):
o queda el paquete nuevo entero, o el anterior intacto.

    python -m tradefit.pipeline.import_observatorio ../Observatorio-comercio/data/processed/radar
"""

import argparse
import json
import shutil
from pathlib import Path

import pandas as pd

from tradefit import config
from tradefit.contracts import (
    OBSERVATORIO_CONTRACT,
    OBSERVATORIO_CONTRACT_VERSIONS,
    OBSERVATORIO_TABLES,
)
from tradefit.pipeline.snapshot_io import (
    MANIFEST_FILENAME,
    create_staging_dir,
    publish_snapshot,
    verify_manifest,
)

META_FILENAME = "meta.json"


def verify_package(package: Path) -> dict[str, object]:
    """Verifica manifiesto, contrato y esquemas del paquete; devuelve el manifiesto.

    Raises:
        RuntimeError: si falta el manifiesto, un hash no coincide, la versión
            del contrato no es compatible o falta una tabla.
        pandera.errors.SchemaError: si una tabla no cumple su esquema.
    """
    manifest_path = package / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise RuntimeError(
            f"Falta {manifest_path}: regenerar el paquete con python -m observatorio.paquete_radar"
        )
    verify_manifest(package)
    manifest: dict[str, object] = json.loads(manifest_path.read_text(encoding="utf-8"))
    parameters = manifest.get("parameters")
    if not isinstance(parameters, dict) or parameters.get("contrato") != OBSERVATORIO_CONTRACT:
        raise RuntimeError(f"{manifest_path} no es un paquete del Observatorio")
    version = parameters.get("contrato_version")
    if version not in OBSERVATORIO_CONTRACT_VERSIONS:
        raise RuntimeError(
            f"Versión del contrato {version!r} no soportada "
            f"(esta versión de Radar lee {sorted(OBSERVATORIO_CONTRACT_VERSIONS)})"
        )
    artifacts = manifest.get("artifacts")
    records = artifacts if isinstance(artifacts, list) else []
    listed = {a["path"] for a in records if isinstance(a, dict)}
    missing = sorted({*OBSERVATORIO_TABLES, META_FILENAME} - listed)
    if missing:
        raise RuntimeError(f"El paquete no trae {missing}")
    for filename, schema in OBSERVATORIO_TABLES.items():
        schema.validate(pd.read_parquet(package / filename), lazy=True)
    return manifest


def import_package(package: Path, target: Path | None = None) -> dict[str, object]:
    """Verifica el paquete y lo publica en ``target`` (por defecto, el del Observatorio).

    Solo se copian los archivos listados en el manifiesto, más el manifiesto
    mismo; cualquier otro archivo del directorio de origen se ignora.
    """
    destination = target if target is not None else config.OBSERVATORIO_DIR
    manifest = verify_package(package)
    staging = create_staging_dir(destination)
    try:
        artifacts = manifest["artifacts"]
        assert isinstance(artifacts, list)
        for record in [*artifacts, {"path": MANIFEST_FILENAME}]:
            relative = Path(record["path"])
            (staging / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(package / relative, staging / relative)
        verify_manifest(staging)
        publish_snapshot(staging, destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return manifest


def main() -> None:
    """CLI: ``python -m tradefit.pipeline.import_observatorio <paquete>``."""
    parser = argparse.ArgumentParser(description="Importa el paquete del Observatorio.")
    parser.add_argument(
        "package", type=Path, help="directorio data/processed/radar del Observatorio"
    )
    args = parser.parse_args()
    manifest = import_package(args.package)
    parameters = manifest["parameters"]
    assert isinstance(parameters, dict)
    print(
        f"Observatorio importado en {config.OBSERVATORIO_DIR} | contrato "
        f"v{parameters['contrato_version']} | commit {str(parameters.get('commit'))[:7]}"
    )


if __name__ == "__main__":
    main()
