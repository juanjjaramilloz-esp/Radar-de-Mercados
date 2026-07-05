"""Combinación de métricas y ranking de mercados destino.

El score de oportunidad es un promedio ponderado de métricas normalizadas a
[0, 1] con min-max. Los pesos NO viven aquí: se reciben como argumento y su
única fuente es ``config.WEIGHTS`` (los pasa el pipeline).
"""

from collections.abc import Mapping

import pandas as pd

from tradefit import config
from tradefit.domain import indices


def _min_max(values: pd.Series) -> pd.Series:
    """Normaliza una serie al rango [0, 1] con min-max.

    Si todos los valores son iguales, la métrica no discrimina: devuelve 1.0
    para todos, de modo que no penalice a ningún mercado.
    """
    vmin = float(values.min())
    vmax = float(values.max())
    if vmax == vmin:
        return pd.Series(1.0, index=values.index)
    normalized: pd.Series = (values - vmin) / (vmax - vmin)
    return normalized


def rank_markets(imports: pd.DataFrame, weights: Mapping[str, float]) -> pd.DataFrame:
    """Calcula el score de oportunidad y rankea los mercados destino.

    Definición: ``score(d) = Σᵢ wᵢ · normᵢ(métricaᵢ(d)) / Σᵢ wᵢ``, es decir,
    promedio ponderado de métricas min-max normalizadas. En la Fase 1 la única
    métrica es ``market_size``. Empates se desempatan por código ISO3 para que
    el ranking sea determinístico.

    Args:
        imports: DataFrame validado contra ``imports_schema``.
        weights: peso por nombre de métrica (fuente: ``config.WEIGHTS``).

    Returns:
        DataFrame conforme a ``ranking_schema``: una fila por mercado con
        rank, ISO3, nombre, valor de la métrica y score, ordenado por score
        descendente.

    Raises:
        ValueError: si ``weights`` referencia métricas desconocidas o no
            contiene ningún peso positivo.
    """
    metric_values = {"market_size": indices.market_size(imports)}

    unknown = set(weights) - set(metric_values)
    if unknown:
        raise ValueError(f"Pesos para métricas desconocidas: {sorted(unknown)}")
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("Se requiere al menos un peso positivo en weights")

    countries = metric_values["market_size"].index
    score = pd.Series(0.0, index=countries)
    for name, weight in weights.items():
        score = score + _min_max(metric_values[name]) * weight
    score = score / total_weight

    names = imports.drop_duplicates(config.COL_COUNTRY).set_index(config.COL_COUNTRY)[
        config.COL_COUNTRY_NAME
    ]
    ranking = pd.DataFrame(
        {
            config.COL_COUNTRY_NAME: names,
            config.COL_MARKET_SIZE: metric_values["market_size"],
            config.COL_SCORE: score,
        }
    )
    ranking = (
        ranking.rename_axis(config.COL_COUNTRY)
        .reset_index()
        .sort_values([config.COL_SCORE, config.COL_COUNTRY], ascending=[False, True])
        .reset_index(drop=True)
    )
    ranking.insert(0, config.COL_RANK, range(1, len(ranking) + 1))
    return ranking
