"""Publicación íntegra de snapshots."""

from pathlib import Path

import pandas as pd
import pytest

from tradefit.pipeline.snapshot_io import (
    atomic_write_parquet,
    create_staging_dir,
    exclusive_lock,
    publish_snapshot,
    refresh_manifest,
    verify_manifest,
    write_manifest,
)


def test_publicacion_reemplaza_directorio_y_elimina_stale(tmp_path: Path) -> None:
    """Un artefacto opcional viejo no sobrevive a la nueva generación."""
    target = tmp_path / "0901"
    target.mkdir()
    (target / "stale.parquet").write_bytes(b"viejo")
    staging = create_staging_dir(target)
    (staging / "ranking.parquet").write_bytes(b"nuevo")

    publish_snapshot(staging, target)

    assert (target / "ranking.parquet").read_bytes() == b"nuevo"
    assert not (target / "stale.parquet").exists()
    assert not staging.exists()


def test_manifiesto_detecta_modificacion(tmp_path: Path) -> None:
    """Cambiar un byte después de publicar invalida el snapshot."""
    snapshot = tmp_path / "0901"
    snapshot.mkdir()
    artifact = snapshot / "ranking.parquet"
    artifact.write_bytes(b"contenido")
    write_manifest(snapshot, source_inputs=[], parameters={"hs": "0901"})

    verify_manifest(snapshot)
    artifact.write_bytes(b"alterado")

    with pytest.raises(RuntimeError, match="no coincide"):
        verify_manifest(snapshot)

    refresh_manifest(snapshot)
    verify_manifest(snapshot)


def test_lock_rechaza_segunda_construccion(tmp_path: Path) -> None:
    """Dos sesiones no pueden publicar el mismo producto simultáneamente."""
    lock = tmp_path / ".0901.lock"

    with (
        exclusive_lock(lock),
        pytest.raises(RuntimeError, match="en curso"),
        exclusive_lock(lock),
    ):
        pass

    assert not lock.exists()


def test_parquet_compartido_se_publica_atomicamente(tmp_path: Path) -> None:
    """El macro compartido queda como un Parquet válido completo."""
    path = tmp_path / "macro.parquet"
    expected = pd.DataFrame({"country": ["COL"], "value": [1.0]})

    atomic_write_parquet(expected, path)

    pd.testing.assert_frame_equal(pd.read_parquet(path), expected)
