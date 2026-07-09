"""Tests del backtest con valores calculados a mano."""

import pandas as pd
import pytest

from tradefit.domain.backtest import spearman_correlation, symmetric_growth, top_k_hit_rate

# --- symmetric_growth (tasa DHS: Davis, Haltiwanger & Schuh 1996) ------------


def test_symmetric_growth_a_mano() -> None:
    base = pd.Series({"USA": 100.0, "DEU": 0.0, "JPN": 50.0, "CHL": 0.0})
    outcome = pd.Series({"USA": 300.0, "DEU": 50.0, "JPN": 0.0, "CHL": 0.0})
    growth = symmetric_growth(base, outcome)
    # USA: (300−100)/200 = 1.0; flujo que nace = +2; que muere = −2
    assert growth["USA"] == pytest.approx(1.0)
    assert growth["DEU"] == pytest.approx(2.0)
    assert growth["JPN"] == pytest.approx(-2.0)
    # Cero en ambos periodos → sin señal
    assert pd.isna(growth["CHL"])


def test_symmetric_growth_ausente_cuenta_como_cero() -> None:
    # DEU solo aparece en el outcome: base 0 → tasa +2 (flujo que nace)
    growth = symmetric_growth(pd.Series({"USA": 10.0}), pd.Series({"DEU": 5.0}))
    assert growth["DEU"] == pytest.approx(2.0)
    assert growth["USA"] == pytest.approx(-2.0)


# --- spearman_correlation (Spearman 1904, rangos con empate promedio) --------


def test_spearman_perfecta_y_perfecta_inversa() -> None:
    a = pd.Series({"A": 1.0, "B": 2.0, "C": 3.0})
    assert spearman_correlation(a, a * 10) == pytest.approx(1.0)
    assert spearman_correlation(a, -a) == pytest.approx(-1.0)


def test_spearman_a_mano() -> None:
    # rangos de b = (3, 1, 2); d = (−2, 1, 1) → ρ = 1 − 6·6/(3·8) = −0.5
    a = pd.Series({"A": 1.0, "B": 2.0, "C": 3.0})
    b = pd.Series({"A": 30.0, "B": 10.0, "C": 20.0})
    assert spearman_correlation(a, b) == pytest.approx(-0.5)


def test_spearman_pocos_pares_es_nan() -> None:
    a = pd.Series({"A": 1.0, "B": 2.0})
    assert pd.isna(spearman_correlation(a, a))


def test_spearman_ignora_nan() -> None:
    a = pd.Series({"A": 1.0, "B": 2.0, "C": 3.0, "D": float("nan")})
    b = pd.Series({"A": 10.0, "B": 20.0, "C": 30.0, "D": 99.0})
    assert spearman_correlation(a, b) == pytest.approx(1.0)


# --- top_k_hit_rate -----------------------------------------------------------


def test_hit_rate_a_mano() -> None:
    score = pd.Series({"A": 3.0, "B": 2.0, "C": 1.0, "D": 0.5})
    realized = pd.Series({"B": 9.0, "C": 8.0, "A": 1.0, "D": 0.0})
    # top-2 del score {A, B} ∩ top-2 real {B, C} = {B} → 1/2
    assert top_k_hit_rate(score, realized, k=2) == pytest.approx(0.5)


def test_hit_rate_k_invalido() -> None:
    with pytest.raises(ValueError, match="positivo"):
        top_k_hit_rate(pd.Series(dtype=float), pd.Series(dtype=float), k=0)


def test_hit_rate_pocos_datos_es_nan() -> None:
    score = pd.Series({"A": 1.0})
    assert pd.isna(top_k_hit_rate(score, score, k=5))
