"""Tests de la ingesta WDI con respuestas guardadas — NUNCA red."""

import json
from pathlib import Path
from typing import Any

import pytest

from tradefit import config
from tradefit.ingest import worldbank


def _record(iso3: str, indicator: str, year: int, value: float | None) -> dict[str, Any]:
    return {
        "indicator": {"id": indicator},
        "countryiso3code": iso3,
        "date": str(year),
        "value": value,
    }


@pytest.fixture()
def wdi_payload() -> dict[str, Any]:
    return {
        "data": [
            _record("USA", "FP.CPI.TOTL.ZG", 2024, 2.9),
            _record("USA", "NY.GDP.MKTP.KD.ZG", 2024, 2.8),
            _record("DEU", "FP.CPI.TOTL.ZG", 2024, 2.5),
            _record("DEU", "FP.CPI.TOTL.ZG", 2023, None),  # null → se descarta
            _record("XXX", "FP.CPI.TOTL.ZG", 2024, 1.0),  # no es destino → fuera
            _record("USA", "SL.UEM.TOTL.ZS", 2024, 4.0),  # indicador ajeno → fuera
        ]
    }


def test_parse_normaliza_al_contrato(wdi_payload: dict[str, Any]) -> None:
    df = worldbank.parse_wdi_response(wdi_payload)
    assert len(df) == 3
    assert set(df[config.COL_COUNTRY]) == {"USA", "DEU"}
    usa_inflacion = df[
        (df[config.COL_COUNTRY] == "USA") & (df[config.COL_INDICATOR] == "inflation")
    ]
    assert usa_inflacion[config.COL_MACRO_VALUE].item() == 2.9


def test_parse_falla_sin_data() -> None:
    with pytest.raises(RuntimeError, match="data"):
        worldbank.parse_wdi_response({"message": "error"})


def test_parse_falla_con_registro_malformado() -> None:
    payload = {"data": [{"countryiso3code": "USA", "date": "2024"}]}  # sin indicator
    with pytest.raises(RuntimeError, match="formato inesperado"):
        worldbank.parse_wdi_response(payload)


def test_parse_falla_si_ningun_destino() -> None:
    payload = {"data": [_record("XXX", "FP.CPI.TOTL.ZG", 2024, 1.0)]}
    with pytest.raises(RuntimeError, match="destinos"):
        worldbank.parse_wdi_response(payload)


def test_load_usa_cache_sin_tocar_la_red(
    tmp_path: Path, wdi_payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _explota() -> dict[str, Any]:
        raise AssertionError("No debe tocar la red si hay caché")

    monkeypatch.setattr(worldbank, "fetch_wdi_indicators", _explota)
    cache = tmp_path / "wdi_cache.json"
    cache.write_text(json.dumps(wdi_payload), encoding="utf-8")

    df = worldbank.load_wdi_macro(cache_file=cache)
    assert len(df) == 3
