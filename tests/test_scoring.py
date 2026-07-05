"""Tests del ranking con un caso sintético donde el orden esperado es obvio."""

import pandas as pd
import pytest

from tradefit import config
from tradefit.contracts import ranking_schema
from tradefit.domain.scoring import rank_markets


def test_orden_obvio(imports_small: pd.DataFrame) -> None:
    ranking = rank_markets(imports_small, {"market_size": 1.0})
    # USA (200) > DEU (50) > JPN (10): el orden no admite discusión
    assert list(ranking[config.COL_COUNTRY]) == ["USA", "DEU", "JPN"]
    assert list(ranking[config.COL_RANK]) == [1, 2, 3]


def test_scores_min_max_a_mano(imports_small: pd.DataFrame) -> None:
    ranking = rank_markets(imports_small, {"market_size": 1.0}).set_index(config.COL_COUNTRY)
    # min-max sobre {200, 50, 10}: USA = 1.0; DEU = (50-10)/(200-10); JPN = 0.0
    assert ranking.loc["USA", config.COL_SCORE] == pytest.approx(1.0)
    assert ranking.loc["DEU", config.COL_SCORE] == pytest.approx(40 / 190)
    assert ranking.loc["JPN", config.COL_SCORE] == pytest.approx(0.0)


def test_ranking_cumple_contrato(imports_small: pd.DataFrame) -> None:
    ranking_schema.validate(rank_markets(imports_small, config.WEIGHTS))


def test_peso_desconocido_falla(imports_small: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="desconocidas"):
        rank_markets(imports_small, {"tariff": 1.0})


def test_sin_pesos_positivos_falla(imports_small: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="positivo"):
        rank_markets(imports_small, {"market_size": 0.0})


def test_ranking_determinista(imports_small: pd.DataFrame) -> None:
    a = rank_markets(imports_small, config.WEIGHTS)
    b = rank_markets(imports_small, config.WEIGHTS)
    pd.testing.assert_frame_equal(a, b)
