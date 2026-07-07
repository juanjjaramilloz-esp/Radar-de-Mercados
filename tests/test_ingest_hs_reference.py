"""Tests del parseo del codebook HS de Comtrade (payload guardado, sin red)."""

import pytest

from tradefit import hs_codes
from tradefit.ingest import hs_reference


def test_parse_filtra_agregados_y_quita_prefijo() -> None:
    payload = {
        "results": [
            {"id": "TOTAL", "text": "Total - All H6 commodities"},
            {"id": "09", "text": "09 - Coffee, tea, mate and spices"},
            {"id": "0901", "text": "0901 - Coffee, whether or not roasted"},
            {"id": "090111", "text": "090111 - Coffee; not roasted"},
            {"id": "ABC", "text": "ABC - no numérico"},
        ]
    }
    df = hs_reference.parse_hs_reference(payload)
    assert list(df[hs_codes.COL_HS]) == ["09", "0901", "090111"]
    assert df[hs_codes.COL_DESC].iloc[1] == "Coffee, whether or not roasted"


def test_parse_falla_sin_results() -> None:
    with pytest.raises(RuntimeError, match="results"):
        hs_reference.parse_hs_reference({"error": "x"})


def test_parse_falla_si_queda_vacio() -> None:
    with pytest.raises(RuntimeError, match="ningún código"):
        hs_reference.parse_hs_reference({"results": [{"id": "TOTAL", "text": "Total"}]})
