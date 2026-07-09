"""Backtest del score contra el crecimiento bilateral realizado (CLI).

Para cada producto curado: recalcula las 4 métricas de comercio del score
(tamaño, CAGR, cuota, momentum) con la ventana histórica
``config.BACKTEST_TRAIN_YEARS`` (as-of 2022), re-scorea el ranking del
snapshot con los pesos oficiales (``domain.scoring.rescore_ranking``) y
contrasta ese score con el crecimiento realizado del flujo Colombia→destino
en ``config.IMPORT_YEARS`` (tasa simétrica DHS). Compara además contra el
baseline ingenuo "rankear por tamaño de mercado".

Limitación documentada (también en la app): las métricas estructurales
(complementariedad, aranceles, margen, accesibilidad) y la estabilidad macro
quedan congeladas en su valor actual — cambian poco entre años, pero el
backtest no es una reconstrucción histórica perfecta.

Uso: ``python -m tradefit.pipeline.backtest`` (usa cachés; descarga la
ventana histórica de Comtrade la primera vez).
"""

import json
import logging
import math

import pandas as pd
from dotenv import load_dotenv

from tradefit import config, hs_codes
from tradefit.domain import indices, scoring
from tradefit.domain.backtest import spearman_correlation, symmetric_growth, top_k_hit_rate
from tradefit.ingest import comtrade

logger = logging.getLogger(__name__)


def _window_mean(bilateral: pd.DataFrame, years: tuple[int, ...]) -> "pd.Series[float]":
    """Flujo bilateral promedio por destino sobre una ventana fija de años.

    El denominador es el ancho completo de la ventana: un (país, año)
    ausente es flujo cero (misma convención que la cuota del score).
    """
    frame = bilateral[bilateral[config.COL_YEAR].isin(years)]
    total = frame.groupby(config.COL_COUNTRY)[config.COL_IMPORTS_FROM_ORIGIN].sum()
    result: pd.Series = total / len(years)
    return result


def _historical_scores(hs: str, ranking: pd.DataFrame, macro_floor: float) -> pd.DataFrame:
    """Ranking re-scoreado con las métricas de comercio as-of la ventana.

    Sustituye tamaño/CAGR/cuota/momentum por sus valores históricos y
    reaplica las definiciones oficiales vía ``rescore_ranking``; el resto de
    columnas (estructurales y estabilidad) queda como está en el snapshot.
    """
    imports = comtrade.load_historical_imports(hs)
    bilateral = comtrade.load_historical_bilateral(hs)
    historical = ranking.copy()
    replacements = {
        config.COL_MARKET_SIZE: indices.market_size(imports),
        config.COL_GROWTH: indices.import_growth(imports),
        config.COL_SHARE: indices.market_share(imports, bilateral).astype(float),
        config.COL_SHARE_TREND: indices.market_share_trend(imports, bilateral).astype(float),
    }
    for column, values in replacements.items():
        historical[column] = historical[config.COL_COUNTRY].map(values)
    # Misma convención del pipeline: cuota/momentum ausentes = 0 observado.
    historical[config.COL_SHARE] = historical[config.COL_SHARE].fillna(0.0)
    historical[config.COL_SHARE_TREND] = historical[config.COL_SHARE_TREND].fillna(0.0)
    return scoring.rescore_ranking(historical, config.WEIGHTS, macro_floor)


def _round(value: float, digits: int = 3) -> float | None:
    """Redondea para el JSON; NaN → None (JSON no tiene NaN)."""
    return None if value is None or math.isnan(value) else round(value, digits)


def run_backtest(products: dict[str, str] | None = None) -> dict[str, object]:
    """Corre el backtest sobre el catálogo curado y escribe ``backtest.json``.

    Args:
        products: ``{hs: etiqueta}`` a evaluar (default:
            ``config.PRODUCTS``). Cada producto necesita su snapshot en
            ``data/processed/<hs>/``.

    Returns:
        El payload escrito (por producto y agregado).
    """
    products = products or dict(config.PRODUCTS)
    train = config.BACKTEST_TRAIN_YEARS
    outcome_years = config.IMPORT_YEARS
    per_product: dict[str, dict[str, object]] = {}
    pooled_score: list[pd.Series] = []
    pooled_baseline: list[pd.Series] = []
    pooled_realized: list[pd.Series] = []

    for hs in sorted(products):
        ranking = pd.read_parquet(config.ranking_parquet(hs))
        meta = json.loads(config.snapshot_meta_json(hs).read_text(encoding="utf-8"))
        macro_floor = float(meta.get("macro_floor", config.MACRO_FLOOR))
        rescored = _historical_scores(hs, ranking, macro_floor).set_index(config.COL_COUNTRY)
        score = rescored[config.COL_FINAL_SCORE]
        baseline = rescored[config.COL_MARKET_SIZE].astype(float)

        base_flow = _window_mean(comtrade.load_historical_bilateral(hs), train)
        outcome_flow = _window_mean(comtrade.load_bilateral_imports(hs), outcome_years)
        realized = symmetric_growth(base_flow, outcome_flow).reindex(score.index)

        n = int(len(score.dropna().index.intersection(realized.dropna().index)))
        per_product[hs] = {
            "label": hs_codes.hs_label(hs),
            "label_en": config.PRODUCTS_EN.get(hs, hs_codes.hs_label(hs)),
            "n": n,
            "spearman_score": _round(spearman_correlation(score, realized)),
            "spearman_baseline": _round(spearman_correlation(baseline, realized)),
            "hit_rate_top5": _round(top_k_hit_rate(score, realized, k=5)),
        }
        logger.info("Backtest %s: n=%d, ρ=%s", hs, n, per_product[hs]["spearman_score"])

        # Para el agregado: rangos normalizados intra-producto (comparables
        # entre productos de tamaños distintos).
        common = score.dropna().index.intersection(realized.dropna().index)
        if len(common) >= 3:
            pooled_score.append(score.loc[common].rank() / len(common))
            pooled_baseline.append(baseline.loc[common].rank() / len(common))
            pooled_realized.append(realized.loc[common].rank() / len(common))

    pooled: dict[str, object] = {"n": 0}
    if pooled_score:
        all_score = pd.concat(pooled_score, ignore_index=True)
        all_baseline = pd.concat(pooled_baseline, ignore_index=True)
        all_realized = pd.concat(pooled_realized, ignore_index=True)
        pooled = {
            "n": int(len(all_score)),
            "spearman_score": _round(spearman_correlation(all_score, all_realized)),
            "spearman_baseline": _round(spearman_correlation(all_baseline, all_realized)),
        }

    payload: dict[str, object] = {
        "train_years": list(train),
        "outcome_years": list(outcome_years),
        "products": per_product,
        "pooled": pooled,
    }
    config.BACKTEST_JSON.parent.mkdir(parents=True, exist_ok=True)
    config.BACKTEST_JSON.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("Backtest escrito en %s (%d productos)", config.BACKTEST_JSON, len(per_product))
    return payload


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    load_dotenv()
    run_backtest()
