"""Tests del top de exportaciones HS4 (ingest/top_exports.py), sin red."""

from typing import Any

import pytest

from tradefit import config
from tradefit.hs_codes import COL_HS
from tradefit.ingest.top_exports import COL_EXPORTS, parse_top_exports


def _payload() -> dict[str, Any]:
    """Payload sintético: mineros a excluir, agregados a descartar y un split."""
    return {
        "data": [
            {"cmdCode": "2709", "primaryValue": 9_000.0},  # crudo → excluido (cap. 27)
            {"cmdCode": "7108", "primaryValue": 8_000.0},  # oro → excluido (cap. 71)
            {"cmdCode": "0901", "primaryValue": 100.0},
            {"cmdCode": "0603", "primaryValue": 80.0},
            {"cmdCode": "0803", "primaryValue": 30.0},  # partida en dos registros
            {"cmdCode": "0803", "primaryValue": 20.0},
            {"cmdCode": "TOTAL", "primaryValue": 999.0},  # agregado → descartado
            {"cmdCode": "090111", "primaryValue": 50.0},  # 6 dígitos → descartado
        ]
    }


def test_orden_suma_y_exclusiones() -> None:
    top = parse_top_exports(_payload())
    # Mineros fuera, agregados fuera, 0803 sumado: café > flores > banano
    assert list(top[COL_HS]) == ["0901", "0603", "0803"]
    assert list(top[COL_EXPORTS]) == [100.0, 80.0, 50.0]


def test_sin_exclusiones_entra_el_crudo() -> None:
    top = parse_top_exports(_payload(), exclude_chapters=frozenset())
    assert list(top[COL_HS])[:2] == ["2709", "7108"]


def test_exclusiones_default_de_config() -> None:
    # El default es la constante documentada, no un literal escondido
    assert frozenset({"27", "71"}) == config.NON_MINING_EXCLUDED_CHAPTERS


def test_payload_sin_data_falla() -> None:
    with pytest.raises(RuntimeError, match="data"):
        parse_top_exports({"results": []})


def test_todo_filtrado_falla() -> None:
    payload = {"data": [{"cmdCode": "2709", "primaryValue": 1.0}]}
    with pytest.raises(RuntimeError, match="HS4"):
        parse_top_exports(payload)
