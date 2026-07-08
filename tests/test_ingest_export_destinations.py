"""Tests de exportaciones por destino (ingest/export_destinations.py), sin red."""

from typing import Any

import pytest

from tradefit import config
from tradefit.ingest.export_destinations import parse_export_destinations


def _payload() -> dict[str, Any]:
    """Payload sintético: World a descartar, destino del radar y partner ajeno."""
    return {
        "data": [
            {"partnerCode": 0, "primaryValue": 999.0},  # World → descartado
            {"partnerCode": 842, "primaryValue": 60.0},  # USA (destino del radar)
            {"partnerCode": 276, "primaryValue": 30.0},  # DEU
            {"partnerCode": 156, "primaryValue": 10.0},  # China: no es destino del radar
            {"partnerCode": 392, "primaryValue": 0.0},  # valor 0 → descartado
        ]
    }


def test_parse_mapea_destinos_y_ordena() -> None:
    result = parse_export_destinations(_payload())
    assert list(result[config.COL_COUNTRY]) == ["USA", "DEU", "156"]
    assert list(result[config.COL_VALUE]) == [60.0, 30.0, 10.0]


def test_origen_sin_exportaciones_devuelve_vacio() -> None:
    # Caso legítimo (cf. RCA 0): vacío con warning, no error
    result = parse_export_destinations({"data": [{"partnerCode": 0, "primaryValue": 5.0}]})
    assert result.empty


def test_payload_sin_data_falla() -> None:
    with pytest.raises(RuntimeError, match="data"):
        parse_export_destinations({"results": []})
