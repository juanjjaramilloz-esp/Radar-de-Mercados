"""Tests del ranking con casos sintéticos donde el orden esperado es obvio."""

import pandas as pd
import pytest

from tradefit import config
from tradefit.contracts import MarketInputs, ranking_schema
from tradefit.domain.macro_filter import apply_stability_penalty
from tradefit.domain.scoring import rank_markets, rescore_ranking, score_contributions

#: Estabilidad de juguete para completar el contrato del ranking en los tests.
STABILITY_SMALL = pd.Series({"USA": 0.8, "DEU": 0.9, "JPN": 0.7})


def test_orden_obvio_por_tamanio(market_inputs_small: MarketInputs) -> None:
    ranking = rank_markets(market_inputs_small, {"market_size": 1.0})
    # USA (200) > DEU (50) > JPN (10): el orden no admite discusión
    assert list(ranking[config.COL_COUNTRY]) == ["USA", "DEU", "JPN"]
    assert list(ranking[config.COL_RANK]) == [1, 2, 3]


def test_orden_obvio_por_complementariedad(market_inputs_small: MarketInputs) -> None:
    ranking = rank_markets(market_inputs_small, {"complementarity": 1.0})
    # DEU (1.0) > USA (0.6) > JPN (0.0): ver fixture baskets_small
    assert list(ranking[config.COL_COUNTRY]) == ["DEU", "USA", "JPN"]


def test_scores_min_max_a_mano(market_inputs_small: MarketInputs) -> None:
    ranking = rank_markets(market_inputs_small, {"market_size": 1.0}).set_index(config.COL_COUNTRY)
    # min-max sobre {200, 50, 10}: USA = 1.0; DEU = (50-10)/(200-10); JPN = 0.0
    assert ranking.loc["USA", config.COL_SCORE] == pytest.approx(1.0)
    assert ranking.loc["DEU", config.COL_SCORE] == pytest.approx(40 / 190)
    assert ranking.loc["JPN", config.COL_SCORE] == pytest.approx(0.0)


def test_metricas_crudas_en_el_ranking(market_inputs_small: MarketInputs) -> None:
    ranking = rank_markets(market_inputs_small, config.WEIGHTS).set_index(config.COL_COUNTRY)
    # Las columnas del snapshot exponen las métricas sin normalizar
    assert ranking.loc["USA", config.COL_SHARE] == pytest.approx(0.20)
    assert ranking.loc["DEU", config.COL_SHARE_TREND] == pytest.approx(-0.25)
    assert ranking.loc["JPN", config.COL_COMPLEMENTARITY] == pytest.approx(0.0)
    # El RCA es contexto constante entre destinos
    assert set(ranking[config.COL_RCA]) == {9.0}


def test_orden_obvio_por_arancel(market_inputs_small: MarketInputs) -> None:
    ranking = rank_markets(market_inputs_small, {"tariff_faced": 1.0})
    # Invertido: DEU (0 %) = 1.0 > JPN (sin dato → neutro 0.5) > USA (3 %) = 0.0
    assert list(ranking[config.COL_COUNTRY]) == ["DEU", "JPN", "USA"]
    scores = ranking.set_index(config.COL_COUNTRY)[config.COL_SCORE]
    assert scores["DEU"] == pytest.approx(1.0)
    assert scores["JPN"] == pytest.approx(0.5)
    assert scores["USA"] == pytest.approx(0.0)


def test_arancel_crudo_conserva_nan(market_inputs_small: MarketInputs) -> None:
    ranking = rank_markets(market_inputs_small, config.WEIGHTS).set_index(config.COL_COUNTRY)
    # La columna expone la fracción cruda; sin dato de WITS queda NaN, no 0
    assert ranking.loc["USA", config.COL_TARIFF] == pytest.approx(0.03)
    assert ranking.loc["DEU", config.COL_TARIFF] == pytest.approx(0.0)
    assert pd.isna(ranking.loc["JPN", config.COL_TARIFF])


def test_destino_sin_canasta_no_rompe(market_inputs_small: MarketInputs) -> None:
    # JPN sin canasta → complementariedad NaN → aporta 0, el ranking sigue válido
    sin_jpn = market_inputs_small.baskets[market_inputs_small.baskets[config.COL_COUNTRY] != "JPN"]
    data = MarketInputs(
        imports=market_inputs_small.imports,
        bilateral=market_inputs_small.bilateral,
        baskets=sin_jpn,
        tariffs=market_inputs_small.tariffs,
        rca=market_inputs_small.rca,
    )
    ranking = apply_stability_penalty(rank_markets(data, config.WEIGHTS), STABILITY_SMALL)
    ranking_schema.validate(ranking)
    assert len(ranking) == 3


def test_ranking_cumple_contrato(market_inputs_small: MarketInputs) -> None:
    ranking = apply_stability_penalty(
        rank_markets(market_inputs_small, config.WEIGHTS), STABILITY_SMALL
    )
    ranking_schema.validate(ranking)


def test_cobertura_de_datos_a_mano(market_inputs_small: MarketInputs) -> None:
    ranking = rank_markets(market_inputs_small, config.WEIGHTS).set_index(config.COL_COUNTRY)
    # Sin distancias/LPI en el fixture: accesibilidad sin dato (peso 0.10)
    # para los 3; JPN además sin arancel WITS (otro 0.10). La cuota de JPN
    # (ausente del bilateral) es cero observado por diseño: no descuenta.
    assert ranking.loc["USA", config.COL_COVERAGE] == pytest.approx(0.90)
    assert ranking.loc["DEU", config.COL_COVERAGE] == pytest.approx(0.90)
    assert ranking.loc["JPN", config.COL_COVERAGE] == pytest.approx(0.80)


def test_cobertura_pondera_por_peso(market_inputs_small: MarketInputs) -> None:
    # Solo arancel: JPN sin dato de WITS → cobertura 0; USA/DEU con dato → 1
    ranking = rank_markets(market_inputs_small, {"tariff_faced": 1.0}).set_index(config.COL_COUNTRY)
    assert ranking.loc["USA", config.COL_COVERAGE] == pytest.approx(1.0)
    assert ranking.loc["JPN", config.COL_COVERAGE] == pytest.approx(0.0)


def test_cobertura_cuota_ausente_es_cero_observado(market_inputs_small: MarketInputs) -> None:
    # JPN no aparece en el bilateral: cuota 0 por diseño, NO hueco de fuente
    ranking = rank_markets(market_inputs_small, {"market_share": 1.0}).set_index(config.COL_COUNTRY)
    assert ranking.loc["JPN", config.COL_COVERAGE] == pytest.approx(1.0)


def test_peso_desconocido_falla(market_inputs_small: MarketInputs) -> None:
    with pytest.raises(ValueError, match="desconocidas"):
        rank_markets(market_inputs_small, {"tariff": 1.0})


def test_sin_pesos_positivos_falla(market_inputs_small: MarketInputs) -> None:
    with pytest.raises(ValueError, match="positivo"):
        rank_markets(market_inputs_small, {"market_size": 0.0})


def test_ranking_determinista(market_inputs_small: MarketInputs) -> None:
    a = rank_markets(market_inputs_small, config.WEIGHTS)
    b = rank_markets(market_inputs_small, config.WEIGHTS)
    pd.testing.assert_frame_equal(a, b)


# --- Re-scoring desde el snapshot (laboratorio de pesos) ---


def _snapshot_ranking(market_inputs_small: MarketInputs) -> pd.DataFrame:
    """Ranking como lo dejaría el pipeline: score + penalización macro."""
    return apply_stability_penalty(
        rank_markets(market_inputs_small, config.WEIGHTS), STABILITY_SMALL
    )


def test_rescore_con_pesos_oficiales_reproduce_el_snapshot(
    market_inputs_small: MarketInputs,
) -> None:
    snapshot = _snapshot_ranking(market_inputs_small)
    rescored = rescore_ranking(snapshot, config.WEIGHTS)
    # Mismas definiciones sobre las mismas métricas → mismo ranking
    pd.testing.assert_series_equal(rescored[config.COL_SCORE], snapshot[config.COL_SCORE])
    pd.testing.assert_series_equal(
        rescored[config.COL_FINAL_SCORE], snapshot[config.COL_FINAL_SCORE]
    )
    assert list(rescored[config.COL_COUNTRY]) == list(snapshot[config.COL_COUNTRY])
    assert list(rescored[config.COL_RANK]) == list(snapshot[config.COL_RANK])


def test_rescore_peso_extremo_orden_obvio(market_inputs_small: MarketInputs) -> None:
    snapshot = _snapshot_ranking(market_inputs_small)
    rescored = rescore_ranking(snapshot, {"market_size": 1.0}).set_index(config.COL_COUNTRY)
    # A mano: norm tamaño = {USA 1.0, DEU 40/190, JPN 0.0} y
    # final = norm × (0.5 + 0.5·estabilidad) con estabilidad {0.8, 0.9, 0.7}
    assert rescored.loc["USA", config.COL_FINAL_SCORE] == pytest.approx(1.0 * 0.90)
    assert rescored.loc["DEU", config.COL_FINAL_SCORE] == pytest.approx((40 / 190) * 0.95)
    assert rescored.loc["JPN", config.COL_FINAL_SCORE] == pytest.approx(0.0)
    assert list(rescored[config.COL_RANK]) == [1, 2, 3]
    assert list(rescored.index) == ["USA", "DEU", "JPN"]


def test_contribuciones_suman_el_score(market_inputs_small: MarketInputs) -> None:
    snapshot = _snapshot_ranking(market_inputs_small)
    contributions = score_contributions(snapshot, config.WEIGHTS)
    total = contributions.sum(axis=1).reindex(snapshot[config.COL_COUNTRY])
    assert total.to_numpy() == pytest.approx(snapshot[config.COL_SCORE].to_numpy())


def test_contribucion_valor_a_mano(market_inputs_small: MarketInputs) -> None:
    snapshot = _snapshot_ranking(market_inputs_small)
    contributions = score_contributions(snapshot, {"market_size": 3.0, "complementarity": 1.0})
    # Pesos 3:1 → tamaño aporta hasta 0.75 y complementariedad hasta 0.25;
    # USA: norm tamaño 1.0, norm complementariedad 0.6 (ver fixture)
    assert contributions.loc["USA", "market_size"] == pytest.approx(0.75)
    assert contributions.loc["USA", "complementarity"] == pytest.approx(0.25 * 0.6)


def test_rescore_columna_ausente_falla(market_inputs_small: MarketInputs) -> None:
    snapshot = _snapshot_ranking(market_inputs_small).drop(columns=[config.COL_TARIFF])
    with pytest.raises(ValueError, match="ausentes"):
        rescore_ranking(snapshot, config.WEIGHTS)


def test_rescore_floor_alternativo_a_mano(market_inputs_small: MarketInputs) -> None:
    snapshot = _snapshot_ranking(market_inputs_small)
    # Piso 1.0: el filtro macro se apaga → final == score de oportunidad
    off = rescore_ranking(snapshot, {"market_size": 1.0}, macro_floor=1.0)
    assert off[config.COL_FINAL_SCORE].to_numpy() == pytest.approx(off[config.COL_SCORE].to_numpy())
    # Piso 0.0: la estabilidad multiplica el score completo; a mano para USA:
    # norm tamaño 1.0 × estabilidad 0.8 = 0.8 (ver STABILITY_SMALL)
    full = rescore_ranking(snapshot, {"market_size": 1.0}, macro_floor=0.0).set_index(
        config.COL_COUNTRY
    )
    assert full.loc["USA", config.COL_FINAL_SCORE] == pytest.approx(1.0 * 0.8)


def test_rescore_floor_invalido_falla(market_inputs_small: MarketInputs) -> None:
    snapshot = _snapshot_ranking(market_inputs_small)
    with pytest.raises(ValueError, match="macro_floor"):
        rescore_ranking(snapshot, config.WEIGHTS, macro_floor=1.5)
