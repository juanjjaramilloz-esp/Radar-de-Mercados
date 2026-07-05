"""Tests de la narrativa por reglas: frases esperadas y ninguna sin número."""

import re

import pandas as pd
import pytest

from tradefit import config
from tradefit.domain.narrative import build_narrative, market_sentences, top_recommendations


def _row(**overrides: object) -> pd.Series:
    base: dict[str, object] = {
        config.COL_RANK: 1,
        config.COL_COUNTRY: "USA",
        config.COL_COUNTRY_NAME: "Estados Unidos",
        config.COL_MARKET_SIZE: 9_000_000_000.0,
        config.COL_GROWTH: 0.092,
        config.COL_SHARE: 0.168,
        config.COL_SHARE_TREND: -0.035,
        config.COL_COMPLEMENTARITY: 0.33,
        config.COL_RCA: 35.7,
        config.COL_STABILITY: 0.66,
        config.COL_SCORE: 0.552,
        config.COL_FINAL_SCORE: 0.458,
    }
    base.update(overrides)
    return pd.Series(base)


def _ranking_small() -> pd.DataFrame:
    # AAA domina todas las métricas; el orden del top es obvio.
    return pd.DataFrame(
        [
            _row(
                **{
                    config.COL_RANK: 1,
                    config.COL_COUNTRY: "AAA",
                    config.COL_COUNTRY_NAME: "Alfalandia",
                    config.COL_MARKET_SIZE: 1000.0,
                    config.COL_GROWTH: 0.5,
                    config.COL_SHARE: 0.5,
                    config.COL_SHARE_TREND: 0.1,
                    config.COL_COMPLEMENTARITY: 0.9,
                    config.COL_FINAL_SCORE: 0.9,
                }
            ),
            _row(
                **{
                    config.COL_RANK: 2,
                    config.COL_COUNTRY: "BBB",
                    config.COL_COUNTRY_NAME: "Betalandia",
                    config.COL_MARKET_SIZE: 500.0,
                    config.COL_GROWTH: 0.1,
                    config.COL_SHARE: 0.2,
                    config.COL_SHARE_TREND: 0.05,
                    config.COL_COMPLEMENTARITY: 0.5,
                    config.COL_FINAL_SCORE: 0.5,
                }
            ),
            _row(
                **{
                    config.COL_RANK: 3,
                    config.COL_COUNTRY: "CCC",
                    config.COL_COUNTRY_NAME: "Gamalandia",
                    config.COL_MARKET_SIZE: 100.0,
                    config.COL_GROWTH: -0.2,
                    config.COL_SHARE: 0.0,
                    config.COL_SHARE_TREND: 0.0,
                    config.COL_COMPLEMENTARITY: 0.1,
                    config.COL_FINAL_SCORE: 0.1,
                }
            ),
        ]
    )


def test_frases_esperadas_con_sus_numeros() -> None:
    sentences = market_sentences(_row(), window_years=3)
    text = " ".join(sentences)
    assert "USD 9.000 M" in text  # tamaño con separador de miles
    assert "crece al 9.2 % anual" in text  # signo positivo → "crece"
    assert "16.8 %" in text  # cuota
    assert "pierde 3.5 pp" in text  # tendencia negativa → "pierde"
    assert "0.33" in text  # complementariedad
    assert "0.458 (bruto 0.552)" in text  # score final vs bruto


def test_demanda_en_contraccion_y_cuota_ganando() -> None:
    sentences = market_sentences(_row(**{config.COL_GROWTH: -0.043, config.COL_SHARE_TREND: 0.012}))
    text = " ".join(sentences)
    assert "se contrae al 4.3 % anual" in text
    assert "gana 1.2 pp" in text


def test_sin_crecimiento_y_sin_cuota() -> None:
    sentences = market_sentences(_row(**{config.COL_GROWTH: float("nan"), config.COL_SHARE: 0.0}))
    text = " ".join(sentences)
    assert "Sin dato suficiente de crecimiento" in text
    assert "cuota 0 %" in text


def test_ninguna_frase_sin_numero() -> None:
    """Regla de oro de la fase: cada afirmación lleva el número que la respalda."""
    ranking = _ranking_small()
    narrative = build_narrative(ranking, config.WEIGHTS)
    all_sentences = [s for sentences in narrative["markets"].values() for s in sentences]
    for rec in narrative["recommendations"]:
        all_sentences.extend(rec["reasons"])
    assert all_sentences, "La narrativa no puede salir vacía"
    for sentence in all_sentences:
        assert re.search(r"\d", sentence), f"Frase sin número: {sentence!r}"


def test_top_recomendaciones_orden_y_porque() -> None:
    recs = top_recommendations(_ranking_small(), config.WEIGHTS, n=3)
    assert [r["iso3"] for r in recs] == ["AAA", "BBB", "CCC"]
    # AAA domina todo: sus razones citan posición 1.º
    assert all("1.º" in reason for reason in recs[0]["reasons"])
    assert len(recs[0]["reasons"]) == 2  # dos drivers por mercado


def test_top_recomendaciones_deterministas() -> None:
    a = top_recommendations(_ranking_small(), config.WEIGHTS)
    b = top_recommendations(_ranking_small(), config.WEIGHTS)
    assert a == b


def test_metrica_desconocida_falla() -> None:
    with pytest.raises(ValueError, match="columna"):
        top_recommendations(_ranking_small(), {"tariff": 1.0})
