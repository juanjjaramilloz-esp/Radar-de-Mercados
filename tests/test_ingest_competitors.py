"""Tests de importaciones por proveedor (ingest/competitors.py), sin red."""

from typing import Any

import pytest

from tradefit import config
from tradefit.ingest.competitors import parse_competitor_imports


def _payload() -> dict[str, Any]:
    """Payload sintético: World conservado, proveedores con nombre, ruido fuera."""
    return {
        "data": [
            # USA (reporter 842, destino del radar): World + 2 proveedores
            {
                "reporterCode": 842,
                "partnerCode": 0,
                "partnerDesc": "World",
                "refYear": 2024,
                "primaryValue": 100.0,
            },
            {
                "reporterCode": 842,
                "partnerCode": 170,
                "partnerDesc": "Colombia",
                "refYear": 2024,
                "primaryValue": 60.0,
            },
            {
                "reporterCode": 842,
                "partnerCode": 704,
                "partnerDesc": "Viet Nam",
                "refYear": 2024,
                "primaryValue": 40.0,
            },
            # Reporter ajeno al radar → descartado
            {
                "reporterCode": 156,
                "partnerCode": 170,
                "partnerDesc": "Colombia",
                "refYear": 2024,
                "primaryValue": 999.0,
            },
            # Valor 0 → descartado
            {
                "reporterCode": 842,
                "partnerCode": 76,
                "partnerDesc": "Brazil",
                "refYear": 2024,
                "primaryValue": 0.0,
            },
        ]
    }


def test_parse_conserva_world_y_nombres() -> None:
    result = parse_competitor_imports(_payload())
    assert len(result) == 3  # World + Colombia + Viet Nam (USA)
    assert set(result[config.COL_COUNTRY]) == {"USA"}
    indexed = result.set_index(config.COL_PARTNER_CODE)
    assert indexed.loc["0", config.COL_VALUE] == pytest.approx(100.0)
    assert indexed.loc["170", config.COL_PARTNER_NAME] == "Colombia"
    assert indexed.loc["704", config.COL_PARTNER_NAME] == "Viet Nam"


def test_parse_sin_destinos_devuelve_vacio() -> None:
    # Solo reporters ajenos al radar: vacío con warning, no error
    payload = {
        "data": [
            {
                "reporterCode": 156,
                "partnerCode": 0,
                "partnerDesc": "World",
                "refYear": 2024,
                "primaryValue": 5.0,
            }
        ]
    }
    assert parse_competitor_imports(payload).empty


def test_parse_partner_sin_nombre_usa_el_codigo() -> None:
    payload = {
        "data": [{"reporterCode": 842, "partnerCode": 704, "refYear": 2024, "primaryValue": 10.0}]
    }
    result = parse_competitor_imports(payload)
    assert result.iloc[0][config.COL_PARTNER_NAME] == "704"


def test_payload_sin_data_falla() -> None:
    with pytest.raises(RuntimeError, match="data"):
        parse_competitor_imports({"results": []})


def test_registro_malformado_falla() -> None:
    payload = {"data": [{"reporterCode": "no-numérico", "partnerCode": 0}]}
    with pytest.raises(RuntimeError, match="formato"):
        parse_competitor_imports(payload)
