"""Tests de la ingesta de distancias CEPII (sin red: sintético + CSV versionado)."""

import pandas as pd
import pytest

from tradefit import config
from tradefit.ingest.geodist import extract_origin_distances, load_distances


def _raw_cepii(rows: list[tuple[str, str, float, float, int]]) -> pd.DataFrame:
    """DataFrame con la forma del dist_cepii crudo (columnas relevantes)."""
    return pd.DataFrame(rows, columns=["iso_o", "iso_d", "dist", "distw", "contig"])


def test_extract_origin_distances_filtra_y_renombra() -> None:
    raw = _raw_cepii(
        [
            ("COL", "USA", 4021.2, 4251.4, 0),
            ("COL", "PAN", 686.1, 733.5, 1),
            ("COL", "COL", 227.9, 260.2, 0),  # distancia interna: fuera
            ("PER", "USA", 5000.0, 5100.0, 0),  # otro origen: fuera
        ]
    )
    result = extract_origin_distances(raw)
    assert list(result[config.COL_COUNTRY]) == ["PAN", "USA"]
    assert result.set_index(config.COL_COUNTRY).at["USA", "distw_km"] == pytest.approx(4251.4)
    assert result.set_index(config.COL_COUNTRY).at["PAN", "contig"] == 1


def test_extract_origin_distances_sin_origen_falla() -> None:
    raw = _raw_cepii([("PER", "USA", 5000.0, 5100.0, 0)])
    with pytest.raises(RuntimeError, match=config.ORIGIN_ISO3):
        extract_origin_distances(raw)


def test_load_distances_cubre_los_destinos_del_radar() -> None:
    # El CSV versionado en data/sample/ debe traer distancia (distw con
    # fallback a dist) para TODOS los destinos configurados del radar.
    distances = load_distances()
    missing = [iso3 for iso3 in config.DESTINATIONS if iso3 not in distances.index]
    assert missing == []
    assert (distances.reindex(list(config.DESTINATIONS)) > 0).all()
    # Sanity con la geografía real: Panamá (frontera) más cerca que Japón.
    assert distances["PAN"] < distances["JPN"]
