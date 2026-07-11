"""Caché versionado de la capa ingest."""

import json
from pathlib import Path
from typing import Any

from tradefit.ingest.cache import load_json_cache, metadata_path, provenance_record, read_json


def test_cache_reutiliza_mismos_parametros(tmp_path: Path) -> None:
    """Una consulta idéntica reutiliza el payload sin llamar al fetch."""
    cache = tmp_path / "source.json"
    calls = 0

    def fetch() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"data": [1]}

    first, fetched_first = load_json_cache(
        cache, fetch, source="demo", parameters={"years": [2023, 2024]}
    )
    second, fetched_second = load_json_cache(
        cache, fetch, source="demo", parameters={"years": [2023, 2024]}
    )

    assert first == second == {"data": [1]}
    assert (fetched_first, fetched_second, calls) == (True, False, 1)
    assert metadata_path(cache).exists()


def test_cache_invalida_al_cambiar_parametros(tmp_path: Path) -> None:
    """Cambiar el vintage descarga de nuevo aunque la ruta sea la misma."""
    cache = tmp_path / "source.json"
    calls = 0

    def fetch() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"generation": calls}

    load_json_cache(cache, fetch, source="demo", parameters={"year": 2024})
    payload, fetched = load_json_cache(cache, fetch, source="demo", parameters={"year": 2025})

    assert fetched is True
    assert payload == {"generation": 2}


def test_cache_adopta_archivo_legacy_sin_red(tmp_path: Path) -> None:
    """Un caché previo a los sidecars se registra sin perderlo."""
    cache = tmp_path / "legacy.json"
    cache.write_text(json.dumps({"data": [7]}), encoding="utf-8")

    payload, fetched = load_json_cache(
        cache,
        lambda: (_ for _ in ()).throw(AssertionError("no debe descargar")),
        source="legacy",
        parameters={"year": 2024},
    )

    assert payload == {"data": [7]}
    assert fetched is False
    assert read_json(metadata_path(cache))["parameters"] == {"year": 2024}


def test_provenance_record_incluye_hash_y_parametros(tmp_path: Path) -> None:
    """El manifiesto puede citar el payload exacto que alimentó el build."""
    cache = tmp_path / "raw" / "source.json"
    load_json_cache(cache, lambda: {"data": [1]}, source="demo", parameters={"year": 2025})

    record = provenance_record(cache, tmp_path)

    assert record is not None
    assert record["path"] == "raw/source.json"
    assert record["parameters"] == {"year": 2025}
    assert len(record["sha256"]) == 64
