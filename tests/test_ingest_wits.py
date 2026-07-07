"""Tests de la ingesta WITS con respuestas XML reales guardadas — NUNCA red."""

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from tradefit import config
from tradefit.ingest import wits

FIXTURES = Path(__file__).parent / "fixtures"

#: Miembros de la UE entre los destinos del MVP (reporter 918 en WITS).
EU_DESTINATIONS = sorted(
    iso3 for iso3, code in config.WITS_REPORTER_CODES.items() if code == config.WITS_EU_CODE
)


@pytest.fixture()
def wits_payload() -> dict[str, Any]:
    """Payload como el que cachea fetch: XML crudos reales de la UE (060311)."""
    mfn = (FIXTURES / "wits_eu_mfn_060311.xml").read_text(encoding="utf-8")
    pref = (FIXTURES / "wits_eu_pref_060311.xml").read_text(encoding="utf-8")
    return {
        "hs": "060311",
        "products": "060311",
        "responses": {str(config.WITS_EU_CODE): {"mfn": mfn, "pref": pref}},
    }


def test_parse_normaliza_al_contrato(wits_payload: dict[str, Any]) -> None:
    df = wits.parse_wits_response(wits_payload)
    # El reporter UE se expande a los 11 destinos comunitarios del MVP.
    assert sorted(df[config.COL_COUNTRY].unique()) == EU_DESTINATIONS
    deu = df[df[config.COL_COUNTRY] == "DEU"]
    # MFN de la UE para rosas frescas (060311): 8.5 % todos los años (2018–2023).
    mfn = deu[deu[config.COL_TARIFF_TYPE] == "MFN"]
    assert set(mfn[config.COL_RATE_PCT]) == {8.5}
    assert mfn[config.COL_YEAR].max() == 2023
    # Preferencial hacia Colombia (acuerdo UE–Colombia): 0 %, reportado hasta 2021.
    pref = deu[deu[config.COL_TARIFF_TYPE] == "PREF"]
    assert set(pref[config.COL_RATE_PCT]) == {0.0}
    assert pref[config.COL_YEAR].max() == 2021


def test_parse_sin_preferencial_solo_deja_mfn(wits_payload: dict[str, Any]) -> None:
    wits_payload["responses"][str(config.WITS_EU_CODE)]["pref"] = None  # 404 NoRecordsFound
    df = wits.parse_wits_response(wits_payload)
    assert set(df[config.COL_TARIFF_TYPE]) == {"MFN"}


def test_parse_sin_registro_alguno_devuelve_vacio() -> None:
    df = wits.parse_wits_response({"responses": {"918": {"mfn": None, "pref": None}}})
    assert df.empty
    assert list(df.columns) == [
        config.COL_COUNTRY,
        config.COL_CMD,
        config.COL_TARIFF_TYPE,
        config.COL_YEAR,
        config.COL_RATE_PCT,
    ]


def test_parse_falla_sin_responses() -> None:
    with pytest.raises(RuntimeError, match="responses"):
        wits.parse_wits_response({"data": []})


def test_parse_falla_con_xml_invalido() -> None:
    payload = {"responses": {"918": {"mfn": "Service Unavailable", "pref": None}}}
    with pytest.raises(RuntimeError, match="XML"):
        wits.parse_wits_response(payload)


def test_load_usa_cache_sin_tocar_la_red(
    tmp_path: Path, wits_payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _explota(hs: str) -> dict[str, Any]:
        raise AssertionError("No debe tocar la red si hay caché")

    monkeypatch.setattr(wits, "fetch_wits_tariffs", _explota)
    cache = tmp_path / "wits_cache.json"
    cache.write_text(json.dumps(wits_payload), encoding="utf-8")

    df = wits.load_wits_tariffs("060311", cache_file=cache)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
