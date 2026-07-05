"""Tests de la ingesta Comtrade con respuestas guardadas — NUNCA red."""

import json
from pathlib import Path
from typing import Any

import pytest

from tradefit import config
from tradefit.ingest import comtrade

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def comtrade_payload() -> dict[str, Any]:
    """Respuesta cruda guardada de la API de Comtrade (recortada)."""
    payload: dict[str, Any] = json.loads(
        (FIXTURES_DIR / "comtrade_response.json").read_text(encoding="utf-8")
    )
    return payload


def test_parse_normaliza_al_contrato(comtrade_payload: dict[str, Any]) -> None:
    df = comtrade.parse_comtrade_response(comtrade_payload)
    # El reporter desconocido "XXX" se filtra; quedan USA y DEU, 2 años cada uno
    assert sorted(df[config.COL_COUNTRY].unique()) == ["DEU", "USA"]
    assert len(df) == 4
    usa_2023 = df[(df[config.COL_COUNTRY] == "USA") & (df[config.COL_YEAR] == 2023)]
    assert usa_2023[config.COL_IMPORTS_USD].item() == 6800000000.0
    # Los nombres salen de config, no de la API
    assert set(df[config.COL_COUNTRY_NAME]) == {"Estados Unidos", "Alemania"}


def test_parse_falla_ruidosamente_sin_data() -> None:
    with pytest.raises(RuntimeError, match="data"):
        comtrade.parse_comtrade_response({"error": "algo"})


def test_parse_falla_ruidosamente_con_registro_malformado() -> None:
    payload = {"data": [{"reporterCode": 842, "refYear": 2023}]}  # sin primaryValue
    with pytest.raises(RuntimeError, match="formato inesperado"):
        comtrade.parse_comtrade_response(payload)


def test_parse_falla_si_ningun_destino_conocido() -> None:
    payload = {"data": [{"reporterCode": 999, "refYear": 2023, "primaryValue": 1.0}]}
    with pytest.raises(RuntimeError, match="destinos"):
        comtrade.parse_comtrade_response(payload)


def test_load_usa_cache_sin_tocar_la_red(
    tmp_path: Path, comtrade_payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _explota() -> dict[str, Any]:
        raise AssertionError("No debe tocar la red si hay caché")

    monkeypatch.setattr(comtrade, "fetch_comtrade_imports", _explota)
    cache = tmp_path / "comtrade_cache.json"
    cache.write_text(json.dumps(comtrade_payload), encoding="utf-8")

    df = comtrade.load_comtrade_imports(cache_file=cache)
    assert len(df) == 4


def test_load_descarga_y_cachea_si_no_hay_cache(
    tmp_path: Path, comtrade_payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(comtrade, "fetch_comtrade_imports", lambda: comtrade_payload)
    cache = tmp_path / "comtrade_cache.json"

    df = comtrade.load_comtrade_imports(cache_file=cache)
    assert cache.exists(), "Debe cachear la respuesta cruda"
    assert len(df) == 4
