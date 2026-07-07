"""Tests del catálogo local de partidas HS (sin red: lee el CSV versionado)."""

import pandas as pd
import pytest

from tradefit import hs_codes


@pytest.fixture()
def catalog() -> pd.DataFrame:
    """Catálogo chico y determinístico para no depender del CSV completo."""
    return pd.DataFrame(
        {
            hs_codes.COL_HS: ["09", "0901", "090111", "1701", "8703"],
            hs_codes.COL_DESC: [
                "Coffee, tea, mate and spices",
                "Coffee, whether or not roasted",
                "Coffee; not roasted or decaffeinated",
                "Cane or beet sugar",
                "Cars; motor vehicles for transport of persons",
            ],
        }
    )


# --- normalize_hs / is_valid_hs ------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("0901", "0901"), (" 09.01 ", "0901"), ("09 01 11", "090111"), ("", "")],
)
def test_normalize_quita_separadores(raw: str, expected: str) -> None:
    assert hs_codes.normalize_hs(raw) == expected


@pytest.mark.parametrize("valid", ["09", "0901", "090111"])
def test_is_valid_acepta_2_4_6_digitos(valid: str) -> None:
    assert hs_codes.is_valid_hs(valid)


@pytest.mark.parametrize("invalid", ["9", "090", "09011", "0901111", "09x1", "", "TOTAL"])
def test_is_valid_rechaza_otros_formatos(invalid: str) -> None:
    assert not hs_codes.is_valid_hs(invalid)


# --- search_hs ------------------------------------------------------------------


def test_search_por_prefijo_de_codigo(catalog: pd.DataFrame) -> None:
    result = hs_codes.search_hs("09", catalog)
    assert list(result[hs_codes.COL_HS]) == ["09", "0901", "090111"]


def test_search_por_codigo_con_puntos(catalog: pd.DataFrame) -> None:
    result = hs_codes.search_hs("09.01", catalog)
    assert list(result[hs_codes.COL_HS]) == ["0901", "090111"]


def test_search_por_descripcion_todas_las_palabras(catalog: pd.DataFrame) -> None:
    result = hs_codes.search_hs("coffee roasted", catalog)
    assert list(result[hs_codes.COL_HS]) == ["0901", "090111"]


def test_search_sin_coincidencias_devuelve_vacio(catalog: pd.DataFrame) -> None:
    assert hs_codes.search_hs("zeppelin", catalog).empty
    assert hs_codes.search_hs("   ", catalog).empty


def test_search_respeta_el_limite(catalog: pd.DataFrame) -> None:
    assert len(hs_codes.search_hs("09", catalog, limit=1)) == 1


def test_search_en_espanol_con_acento(catalog: pd.DataFrame) -> None:
    result = hs_codes.search_hs("café", catalog)
    assert list(result[hs_codes.COL_HS]) == ["09", "0901", "090111"]


def test_search_en_espanol_azucar(catalog: pd.DataFrame) -> None:
    assert list(hs_codes.search_hs("azúcar", catalog)[hs_codes.COL_HS]) == ["1701"]


def test_search_espanol_no_pisa_un_match_en_ingles(catalog: pd.DataFrame) -> None:
    # "cars" matchea directo en inglés: no se debe traducir nada.
    assert list(hs_codes.search_hs("cars", catalog)[hs_codes.COL_HS]) == ["8703"]


def test_search_espanol_sin_traduccion_devuelve_vacio(catalog: pd.DataFrame) -> None:
    assert hs_codes.search_hs("dirigible", catalog).empty


def test_search_lang_en_no_traduce_espanol(catalog: pd.DataFrame) -> None:
    # En modo inglés, un término en español no debe traducirse ni matchear.
    assert hs_codes.search_hs("café", catalog, lang="en").empty


def test_search_lang_en_matches_ingles_directo(catalog: pd.DataFrame) -> None:
    result = hs_codes.search_hs("coffee", catalog, lang="en")
    assert list(result[hs_codes.COL_HS]) == ["09", "0901", "090111"]


# --- catálogo versionado y etiquetas ---------------------------------------------


def test_catalogo_versionado_carga_y_trae_el_cafe() -> None:
    catalog = hs_codes.load_hs_reference()
    assert set(catalog.columns) == {hs_codes.COL_HS, hs_codes.COL_DESC}
    assert (catalog[hs_codes.COL_HS] == "0901").any()
    assert catalog[hs_codes.COL_HS].str.len().isin([2, 4, 6]).all()


def test_busqueda_en_espanol_contra_el_catalogo_real() -> None:
    catalog = hs_codes.load_hs_reference()
    result = hs_codes.search_hs("aguacate", catalog)
    assert result[hs_codes.COL_HS].str.startswith("0804").any()


def test_label_prefiere_el_producto_curado() -> None:
    assert hs_codes.hs_label("0901") == "Café (HS 0901)"


def test_label_cae_al_catalogo_y_luego_al_generico() -> None:
    assert hs_codes.hs_label("1701").endswith("(HS 1701)")
    assert hs_codes.hs_label("777777") == "HS 777777"  # no existe en la nomenclatura
