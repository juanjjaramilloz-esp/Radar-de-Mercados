"""Tests de índices económicos con valores conocidos calculados a mano."""

import pandas as pd
import pytest

from tradefit.domain.indices import (
    complementarity,
    import_growth,
    market_share,
    market_share_trend,
    market_size,
    rca_balassa,
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
