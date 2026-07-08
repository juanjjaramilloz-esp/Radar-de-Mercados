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
    def _explota(hs: str = config.HS_CODE) -> dict[str, Any]:
        raise AssertionError("No debe tocar la red si hay caché")

    monkeypatch.setattr(comtrade, "fetch_comtrade_imports", _explota)
    cache = tmp_path / "comtrade_cache.json"
    cache.write_text(json.dumps(comtrade_payload), encoding="utf-8")

    df = comtrade.load_comtrade_imports(cache_file=cache)
    assert len(df) == 4


def test_load_descarga_y_cachea_si_no_hay_cache(
    tmp_path: Path, comtrade_payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(comtrade, "fetch_comtrade_imports", lambda hs: comtrade_payload)
    cache = tmp_path / "comtrade_cache.json"

    df = comtrade.load_comtrade_imports(cache_file=cache)
    assert cache.exists(), "Debe cachear la respuesta cruda"
    assert len(df) == 4


# --- parse_bilateral_response ------------------------------------------------


def test_parse_bilateral_normaliza_al_contrato() -> None:
    payload = {
        "data": [
            {"reporterCode": 842, "refYear": 2024, "primaryValue": 60.0},
            {"reporterCode": 276, "refYear": 2024, "primaryValue": 15.0},
            {"reporterCode": 999, "refYear": 2024, "primaryValue": 1.0},  # desconocido
        ]
    }
    df = comtrade.parse_bilateral_response(payload)
    assert sorted(df[config.COL_COUNTRY]) == ["DEU", "USA"]
    usa = df[df[config.COL_COUNTRY] == "USA"]
    assert usa[config.COL_IMPORTS_FROM_ORIGIN].item() == 60.0


def test_parse_bilateral_vacio_es_flujo_cero_no_error() -> None:
    # El origen puede no exportar el producto a ningún destino: DataFrame
    # vacío válido (cuota 0 aguas abajo), no un error.
    payload = {"data": [{"reporterCode": 999, "refYear": 2024, "primaryValue": 1.0}]}
    df = comtrade.parse_bilateral_response(payload)
    assert df.empty
    assert list(df.columns) == [
        config.COL_COUNTRY,
        config.COL_YEAR,
        config.COL_IMPORTS_FROM_ORIGIN,
    ]


# --- parse_flow_weights (insumo de valores unitarios) -------------------------


def test_parse_flow_weights_normaliza_al_contrato() -> None:
    payload = {
        "data": [
            {"reporterCode": 842, "refYear": 2024, "primaryValue": 300.0, "netWgt": 50.0},
            {"reporterCode": 276, "refYear": 2024, "primaryValue": 100.0, "netWgt": None},
            {"reporterCode": 999, "refYear": 2024, "primaryValue": 1.0, "netWgt": 1.0},
        ]
    }
    df = comtrade.parse_flow_weights(payload).set_index(config.COL_COUNTRY)
    assert sorted(df.index) == ["DEU", "USA"]  # el reporter desconocido se filtra
    assert df.loc["USA", config.COL_VALUE] == 300.0
    assert df.loc["USA", config.COL_NET_WGT] == 50.0
    # netWgt nulo → NaN (cantidad no reportada), el valor se conserva
    assert df.loc["DEU", config.COL_VALUE] == 100.0
    assert df.loc["DEU", config.COL_NET_WGT] != df.loc["DEU", config.COL_NET_WGT]  # NaN


def test_parse_flow_weights_peso_cero_es_nan() -> None:
    payload = {"data": [{"reporterCode": 842, "refYear": 2024, "primaryValue": 5.0, "netWgt": 0}]}
    df = comtrade.parse_flow_weights(payload)
    assert df[config.COL_NET_WGT].isna().all()


def test_parse_flow_weights_vacio_no_es_error() -> None:
    payload = {"data": [{"reporterCode": 999, "refYear": 2024, "primaryValue": 1.0}]}
    df = comtrade.parse_flow_weights(payload)
    assert df.empty


def test_parse_flow_weights_falla_sin_data() -> None:
    with pytest.raises(RuntimeError, match="data"):
        comtrade.parse_flow_weights({"error": "algo"})


# --- parse_baskets_response ---------------------------------------------------


def test_parse_baskets_normaliza_y_filtra_agregados() -> None:
    payload = {
        "data": [
            {"reporterCode": config.ORIGIN_COMTRADE_CODE, "cmdCode": "09", "primaryValue": 90.0},
            {"reporterCode": config.ORIGIN_COMTRADE_CODE, "cmdCode": "27", "primaryValue": 10.0},
            # Un agregado (no es capítulo de 2 dígitos) debe filtrarse
            {
                "reporterCode": config.ORIGIN_COMTRADE_CODE,
                "cmdCode": "TOTAL",
                "primaryValue": 100.0,
            },
            {"reporterCode": 842, "cmdCode": "09", "primaryValue": 50.0},
        ]
    }
    df = comtrade.parse_baskets_response(payload)
    assert sorted(df[config.COL_COUNTRY].unique()) == [config.ORIGIN_ISO3, "USA"]
    assert "TOTAL" not in set(df[config.COL_CMD])
    col = df[df[config.COL_COUNTRY] == config.ORIGIN_ISO3]
    assert col[config.COL_VALUE].sum() == 100.0


def test_parse_baskets_falla_sin_canasta_del_origen() -> None:
    payload = {"data": [{"reporterCode": 842, "cmdCode": "09", "primaryValue": 50.0}]}
    with pytest.raises(RuntimeError, match="origen"):
        comtrade.parse_baskets_response(payload)


# --- parse_export_totals_response ---------------------------------------------


def test_parse_export_totals_agrega_el_mundo() -> None:
    payload = {
        "data": [
            {"_scope": "origin", "cmdCode": config.HS_CODE, "refYear": 2024, "primaryValue": 900.0},
            {"_scope": "origin", "cmdCode": "TOTAL", "refYear": 2024, "primaryValue": 1000.0},
            # El mundo llega desagregado por reporter: debe sumarse
            {"_scope": "world", "cmdCode": config.HS_CODE, "refYear": 2024, "primaryValue": 60.0},
            {"_scope": "world", "cmdCode": config.HS_CODE, "refYear": 2024, "primaryValue": 40.0},
            {"_scope": "world", "cmdCode": "TOTAL", "refYear": 2024, "primaryValue": 1000.0},
        ]
    }
    df = comtrade.parse_export_totals_response(payload).set_index(
        [config.COL_SCOPE, config.COL_CMD]
    )
    assert df.loc[("world", "product"), config.COL_VALUE].item() == 100.0
    assert df.loc[("origin", "total"), config.COL_VALUE].item() == 1000.0


def test_parse_export_totals_falla_si_falta_una_serie() -> None:
    payload = {
        "data": [
            {"_scope": "origin", "cmdCode": config.HS_CODE, "refYear": 2024, "primaryValue": 900.0}
        ]
    }
    with pytest.raises(RuntimeError, match="RCA"):
        comtrade.parse_export_totals_response(payload)


def test_parse_export_totals_tolera_origen_sin_producto() -> None:
    # El origen puede no exportar el producto (RCA 0 aguas abajo): las otras
    # tres series bastan.
    payload = {
        "data": [
            {"_scope": "origin", "cmdCode": "TOTAL", "refYear": 2024, "primaryValue": 1000.0},
            {"_scope": "world", "cmdCode": config.HS_CODE, "refYear": 2024, "primaryValue": 50.0},
            {"_scope": "world", "cmdCode": "TOTAL", "refYear": 2024, "primaryValue": 900.0},
        ]
    }
    df = comtrade.parse_export_totals_response(payload)
    present = set(zip(df[config.COL_SCOPE], df[config.COL_CMD], strict=True))
    assert ("origin", "product") not in present
    assert ("origin", "total") in present


def test_parse_export_totals_falla_sin_scope() -> None:
    payload = {"data": [{"cmdCode": config.HS_CODE, "refYear": 2024, "primaryValue": 1.0}]}
    with pytest.raises(RuntimeError, match="formato inesperado"):
        comtrade.parse_export_totals_response(payload)
