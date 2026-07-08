"""Tests de índices económicos con valores conocidos calculados a mano."""

import pandas as pd
import pytest

from tradefit import config
from tradefit.domain.indices import (
    aggregate_unit_value,
    complementarity,
    destination_concentration,
    destination_shares,
    import_growth,
    market_share,
    market_share_trend,
    market_size,
    rca_balassa,
    supplier_shares,
    tariff_faced,
    unit_value_premium,
)

# --- market_size -----------------------------------------------------------


def test_market_size_promedio_3_anios_a_mano(imports_small: pd.DataFrame) -> None:
    sizes = market_size(imports_small, years=3)
    # USA: (100 + 200 + 300) / 3 = 200 — el 2021 (999) queda fuera de la ventana
    assert sizes["USA"] == pytest.approx(200.0)
    # DEU: (40 + 50 + 60) / 3 = 50
    assert sizes["DEU"] == pytest.approx(50.0)
    # JPN: (10 + 10 + 10) / 3 = 10
    assert sizes["JPN"] == pytest.approx(10.0)


def test_market_size_ventana_configurable(imports_small: pd.DataFrame) -> None:
    sizes = market_size(imports_small, years=2)
    # USA: (200 + 300) / 2 = 250
    assert sizes["USA"] == pytest.approx(250.0)


def test_market_size_years_invalido(imports_small: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="years"):
        market_size(imports_small, years=0)


# --- import_growth (CAGR) --------------------------------------------------


def test_import_growth_cagr_a_mano(imports_small: pd.DataFrame) -> None:
    growth = import_growth(imports_small, years=3)
    # USA: (300/100)^(1/2) − 1 = √3 − 1 ≈ 0.7321 — el 2021 queda fuera
    assert growth["USA"] == pytest.approx(3**0.5 - 1)
    # DEU: (60/40)^(1/2) − 1 = √1.5 − 1 ≈ 0.2247
    assert growth["DEU"] == pytest.approx(1.5**0.5 - 1)
    # JPN: (10/10)^(1/2) − 1 = 0 (importaciones planas)
    assert growth["JPN"] == pytest.approx(0.0)


def test_import_growth_ventana_2(imports_small: pd.DataFrame) -> None:
    growth = import_growth(imports_small, years=2)
    # USA: (300/200)^(1/1) − 1 = 0.5
    assert growth["USA"] == pytest.approx(0.5)


def test_import_growth_un_solo_anio_es_nan() -> None:
    solo_un_anio = pd.DataFrame(
        {
            "country_iso3": ["USA"],
            "country_name": ["Estados Unidos"],
            "year": [2024],
            "imports_usd": [100.0],
        }
    )
    growth = import_growth(solo_un_anio, years=3)
    assert pd.isna(growth["USA"])


def test_import_growth_years_invalido(imports_small: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="years"):
        import_growth(imports_small, years=1)


# --- market_share y market_share_trend --------------------------------------


def test_market_share_ultimo_anio_a_mano(
    imports_small: pd.DataFrame, bilateral_small: pd.DataFrame
) -> None:
    shares = market_share(imports_small, bilateral_small)
    # USA 2024: 60 / 300 = 0.20
    assert shares["USA"] == pytest.approx(0.20)
    # DEU 2024: 15 / 60 = 0.25
    assert shares["DEU"] == pytest.approx(0.25)
    # JPN: sin flujo bilateral registrado → cuota 0
    assert shares["JPN"] == pytest.approx(0.0)


def test_market_share_trend_a_mano(
    imports_small: pd.DataFrame, bilateral_small: pd.DataFrame
) -> None:
    trend = market_share_trend(imports_small, bilateral_small, years=3)
    # USA: 0.20 (2024) − 0.10 (2022) = +0.10
    assert trend["USA"] == pytest.approx(0.10)
    # DEU: 0.25 (2024) − 0.50 (2022) = −0.25
    assert trend["DEU"] == pytest.approx(-0.25)
    # JPN: 0 − 0 = 0
    assert trend["JPN"] == pytest.approx(0.0)


def test_market_share_trend_years_invalido(
    imports_small: pd.DataFrame, bilateral_small: pd.DataFrame
) -> None:
    with pytest.raises(ValueError, match="years"):
        market_share_trend(imports_small, bilateral_small, years=1)


# --- rca_balassa (Balassa, 1965) --------------------------------------------


def test_rca_a_mano() -> None:
    # (900/1000) / (100/1000) = 0.9 / 0.1 = 9: fuerte ventaja comparativa
    assert rca_balassa(900.0, 1000.0, 100.0, 1000.0) == pytest.approx(9.0)


def test_rca_uno_es_neutral() -> None:
    # Participaciones idénticas → RCA = 1 (sin ventaja revelada)
    assert rca_balassa(50.0, 1000.0, 500.0, 10000.0) == pytest.approx(1.0)


def test_rca_denominador_no_positivo_falla() -> None:
    with pytest.raises(ValueError, match="positivos"):
        rca_balassa(900.0, 0.0, 100.0, 1000.0)


def test_rca_producto_negativo_falla() -> None:
    with pytest.raises(ValueError, match="negativas"):
        rca_balassa(-1.0, 1000.0, 100.0, 1000.0)


# --- complementarity (Michaely, 1996) ---------------------------------------


def test_complementarity_a_mano() -> None:
    origen = pd.Series({"09": 90.0, "27": 10.0})  # x = (0.9, 0.1)
    destino = pd.Series({"09": 50.0, "27": 50.0})  # m = (0.5, 0.5)
    # C = 1 − (|0.9−0.5| + |0.1−0.5|)/2 = 1 − 0.8/2 = 0.6
    assert complementarity(origen, destino) == pytest.approx(0.6)


def test_complementarity_encaje_perfecto() -> None:
    origen = pd.Series({"09": 90.0, "27": 10.0})
    destino = pd.Series({"09": 900.0, "27": 100.0})  # mismas participaciones
    assert complementarity(origen, destino) == pytest.approx(1.0)


def test_complementarity_canastas_disjuntas() -> None:
    origen = pd.Series({"09": 100.0})
    destino = pd.Series({"84": 100.0})
    assert complementarity(origen, destino) == pytest.approx(0.0)


def test_complementarity_canasta_vacia_falla() -> None:
    with pytest.raises(ValueError, match="positivo"):
        complementarity(pd.Series({"09": 0.0}), pd.Series({"09": 100.0}))


# --- tariff_faced (AHS de WITS: min(MFN, PREF), promedio simple HS6) ---------


def test_tariff_faced_a_mano(tariffs_small: pd.DataFrame) -> None:
    result = tariff_faced(tariffs_small)
    # USA: 090111 → min(MFN último año 10, PREF 2) = 2; 090121 → 4;
    # promedio simple = 3 % = 0.03
    assert result["USA"] == pytest.approx(0.03)
    # DEU: MFN 0 sin preferencial → 0
    assert result["DEU"] == pytest.approx(0.0)
    # JPN sin filas → no aparece (sin dato ≠ arancel 0)
    assert "JPN" not in result.index


def test_tariff_faced_toma_el_ultimo_anio_del_mfn(tariffs_small: pd.DataFrame) -> None:
    # Sin el preferencial, USA/090111 usa el MFN de 2023 (10 %), no el de 2022 (12 %)
    sin_pref = tariffs_small[tariffs_small["tariff_type"] == "MFN"]
    result = tariff_faced(sin_pref)
    assert result["USA"] == pytest.approx((10.0 + 4.0) / 2 / 100)


def test_tariff_faced_vacio_devuelve_serie_vacia() -> None:
    assert tariff_faced(pd.DataFrame()).empty


# --- Concentración de destinos (HHI de Herfindahl–Hirschman) -----------------


def test_destination_shares_a_mano() -> None:
    exports = pd.Series({"USA": 50.0, "DEU": 30.0, "JPN": 20.0})
    shares = destination_shares(exports)
    # A mano: 50/100, 30/100, 20/100
    assert shares["USA"] == pytest.approx(0.50)
    assert shares["DEU"] == pytest.approx(0.30)
    assert shares["JPN"] == pytest.approx(0.20)
    assert shares.sum() == pytest.approx(1.0)


def test_destination_concentration_a_mano() -> None:
    exports = pd.Series({"USA": 50.0, "DEU": 30.0, "JPN": 20.0})
    # HHI = 0.5² + 0.3² + 0.2² = 0.25 + 0.09 + 0.04 = 0.38
    assert destination_concentration(exports) == pytest.approx(0.38)


def test_destination_concentration_extremos() -> None:
    # n destinos iguales → 1/n; un solo destino → 1
    iguales = pd.Series({"A": 25.0, "B": 25.0, "C": 25.0, "D": 25.0})
    assert destination_concentration(iguales) == pytest.approx(0.25)
    unico = pd.Series({"USA": 100.0})
    assert destination_concentration(unico) == pytest.approx(1.0)


def test_destination_concentration_invalidos_fallan() -> None:
    with pytest.raises(ValueError, match="positivo"):
        destination_concentration(pd.Series(dtype=float))
    with pytest.raises(ValueError, match="negativas"):
        destination_shares(pd.Series({"USA": -1.0, "DEU": 2.0}))


# --- supplier_shares -------------------------------------------------------


def _partner_imports(rows: list[tuple[str, str, str, int, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=[
            config.COL_COUNTRY,
            config.COL_PARTNER_CODE,
            config.COL_PARTNER_NAME,
            config.COL_YEAR,
            config.COL_VALUE,
        ],
    )


def test_supplier_shares_a_mano_con_world() -> None:
    # USA importa 100 (World); COL 40, BRA 35, VNM 25 → cuotas 0.40/0.35/0.25
    imports = _partner_imports(
        [
            ("USA", "0", "World", 2024, 100.0),
            ("USA", "170", "Colombia", 2024, 40.0),
            ("USA", "76", "Brazil", 2024, 35.0),
            ("USA", "704", "Viet Nam", 2024, 25.0),
        ]
    )
    result = supplier_shares(imports).set_index(config.COL_PARTNER_CODE)
    assert result.loc["170", config.COL_SUPPLIER_SHARE] == pytest.approx(0.40)
    assert result.loc["76", config.COL_SUPPLIER_SHARE] == pytest.approx(0.35)
    assert result.loc["704", config.COL_SUPPLIER_SHARE] == pytest.approx(0.25)
    assert result.loc["170", config.COL_SUPPLIER_RANK] == 1
    assert result.loc["76", config.COL_SUPPLIER_RANK] == 2
    assert result.loc["704", config.COL_SUPPLIER_RANK] == 3
    assert "0" not in result.index  # el agregado World no es un proveedor


def test_supplier_shares_sin_world_usa_la_suma() -> None:
    # Sin agregado World: denominador = 60 + 40 = 100
    imports = _partner_imports(
        [
            ("DEU", "170", "Colombia", 2024, 60.0),
            ("DEU", "756", "Switzerland", 2024, 40.0),
        ]
    )
    result = supplier_shares(imports).set_index(config.COL_PARTNER_CODE)
    assert result.loc["170", config.COL_SUPPLIER_SHARE] == pytest.approx(0.60)
    assert result.loc["756", config.COL_SUPPLIER_SHARE] == pytest.approx(0.40)


def test_supplier_shares_usa_el_ultimo_anio_por_destino() -> None:
    # USA tiene 2024; JPN solo llega a 2023 → cada uno usa su último año
    imports = _partner_imports(
        [
            ("USA", "170", "Colombia", 2023, 999.0),  # año viejo: fuera
            ("USA", "170", "Colombia", 2024, 80.0),
            ("USA", "76", "Brazil", 2024, 20.0),
            ("JPN", "76", "Brazil", 2023, 50.0),
            ("JPN", "170", "Colombia", 2023, 50.0),
        ]
    )
    result = supplier_shares(imports)
    usa = result[result[config.COL_COUNTRY] == "USA"]
    jpn = result[result[config.COL_COUNTRY] == "JPN"]
    assert set(usa[config.COL_YEAR]) == {2024}
    assert set(jpn[config.COL_YEAR]) == {2023}
    assert usa.set_index(config.COL_PARTNER_CODE).loc[
        "170", config.COL_SUPPLIER_SHARE
    ] == pytest.approx(0.80)


def test_supplier_shares_vacio_devuelve_vacio() -> None:
    assert supplier_shares(_partner_imports([])).empty


def test_supplier_shares_valor_no_positivo_falla() -> None:
    imports = _partner_imports([("USA", "170", "Colombia", 2024, 0.0)])
    with pytest.raises(ValueError, match="positivas"):
        supplier_shares(imports)


# --- Valores unitarios (UN IMTS 2010; premium: Hummels & Klenow 2005) --------


def test_aggregate_unit_value_a_mano() -> None:
    # (100 + 200) USD / (10 + 40) kg = 300/50 = 6 USD/kg — cociente de sumas,
    # NO promedio de cocientes ((10 + 5)/2 = 7.5 daría otra cosa)
    values = pd.Series([100.0, 200.0])
    weights = pd.Series([10.0, 40.0])
    assert aggregate_unit_value(values, weights) == pytest.approx(6.0)


def test_aggregate_unit_value_excluye_registros_sin_peso() -> None:
    # El registro con peso NaN se excluye del numerador Y del denominador:
    # (100 + 200) / (10 + 40) = 6, el valor 999 no sesga el UV al alza
    values = pd.Series([100.0, 200.0, 999.0])
    weights = pd.Series([10.0, 40.0, float("nan")])
    assert aggregate_unit_value(values, weights) == pytest.approx(6.0)


def test_aggregate_unit_value_peso_cero_cuenta_como_sin_dato() -> None:
    values = pd.Series([100.0, 200.0])
    weights = pd.Series([10.0, 0.0])
    assert aggregate_unit_value(values, weights) == pytest.approx(10.0)


def test_aggregate_unit_value_sin_pesos_validos_es_nan() -> None:
    values = pd.Series([100.0, 200.0])
    weights = pd.Series([float("nan"), 0.0])
    assert pd.isna(aggregate_unit_value(values, weights))


def test_aggregate_unit_value_longitudes_distintas_falla() -> None:
    with pytest.raises(ValueError, match="longitud"):
        aggregate_unit_value(pd.Series([1.0, 2.0]), pd.Series([1.0]))


def test_unit_value_premium_a_mano() -> None:
    # 6 USD/kg del origen sobre 5 USD/kg del destino = 6/5 − 1 = +20 %
    assert unit_value_premium(6.0, 5.0) == pytest.approx(0.20)
    # descuento: 4 sobre 5 = −20 %
    assert unit_value_premium(4.0, 5.0) == pytest.approx(-0.20)


def test_unit_value_premium_sin_evidencia_es_nan() -> None:
    assert pd.isna(unit_value_premium(float("nan"), 5.0))
    assert pd.isna(unit_value_premium(6.0, float("nan")))
    assert pd.isna(unit_value_premium(0.0, 5.0))
