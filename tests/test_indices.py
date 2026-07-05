"""Tests de índices económicos con valores conocidos calculados a mano."""

import pandas as pd
import pytest

from tradefit.domain.indices import market_size


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
