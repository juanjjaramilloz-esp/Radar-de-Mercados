"""Filtro macro de estabilidad del destino.

Funciones puras y determinísticas: reciben DataFrames ya validados (ver
``contracts.macro_schema``), no hacen I/O. El filtro convierte indicadores
macro WDI en un score de estabilidad en [0, 1] y lo aplica como penalización
multiplicativa sobre el score de oportunidad. Umbrales y piso viven en
``config`` (``MACRO_BOUNDS``, ``MACRO_FLOOR``), documentados y justificados.
"""

from collections.abc import Mapping

import pandas as pd

from tradefit import config

#: Estabilidad asignada cuando un destino no tiene ningún indicador con dato:
#: neutra (ni premia ni castiga), porque la ausencia de datos WDI en economías
#: del MVP es un hueco de la fuente, no evidencia de inestabilidad.
NEUTRAL_STABILITY = 0.5


def _ramp(values: pd.Series, worst: float, best: float) -> pd.Series:
    """Rampa lineal de ``worst`` → 0 a ``best`` → 1, recortada a [0, 1].

    Funciona en ambas direcciones (``best`` puede ser menor que ``worst``,
    p. ej. inflación: menos es mejor).
    """
    if worst == best:
        raise ValueError(f"Umbrales degenerados: worst == best == {worst}")
    return ((values - worst) / (best - worst)).clip(0.0, 1.0)


def stability_score(
    macro: pd.DataFrame,
    bounds: Mapping[str, tuple[float, float]],
    years: int = config.MACRO_YEARS,
) -> pd.Series:
    """Score de estabilidad macro del destino, en [0, 1].

    Definición: para cada indicador se promedian los últimos ``years`` años
    con dato y el promedio se normaliza con una rampa lineal entre los
    umbrales (peor, mejor) de ``bounds`` — normalización min-max con umbrales
    fijos, como recomienda el OECD/JRC *Handbook on Constructing Composite
    Indicators* (2008) para que el score no dependa de la muestra de países.
    El score del destino es el promedio simple de sus indicadores con dato.

    Args:
        macro: DataFrame validado contra ``macro_schema``.
        bounds: umbrales (peor, mejor) por indicador; fuente:
            ``config.MACRO_BOUNDS``.
        years: ventana de años recientes a promediar por indicador.

    Returns:
        Series indexada por país (ISO3) con la estabilidad en [0, 1],
        nombrada ``config.COL_STABILITY``. NaN si el país no tiene ningún
        indicador con dato.

    Raises:
        ValueError: si ``years`` no es al menos 1 o si el DataFrame trae un
            indicador sin umbrales definidos (config incompleta).
    """
    if years < 1:
        raise ValueError(f"years debe ser >= 1; recibido: {years}")
    unknown = set(macro[config.COL_INDICATOR]) - set(bounds)
    if unknown:
        raise ValueError(f"Indicadores sin umbrales en config.MACRO_BOUNDS: {sorted(unknown)}")

    recent = (
        macro.sort_values(config.COL_YEAR)
        .groupby([config.COL_COUNTRY, config.COL_INDICATOR])
        .tail(years)
    )
    means = (
        recent.groupby([config.COL_COUNTRY, config.COL_INDICATOR])[config.COL_MACRO_VALUE]
        .mean()
        .unstack()
    )
    scores = pd.DataFrame(index=means.index)
    for indicator in means.columns:
        worst, best = bounds[indicator]
        scores[indicator] = _ramp(means[indicator], worst, best)
    stability = scores.mean(axis=1, skipna=True)
    return stability.rename(config.COL_STABILITY)


def apply_stability_penalty(
    ranking: pd.DataFrame,
    stability: pd.Series,
    floor: float = config.MACRO_FLOOR,
) -> pd.DataFrame:
    """Aplica la penalización multiplicativa y re-rankea por score final.

    Definición: ``final = oportunidad × (piso + (1 − piso) × estabilidad)``.
    Con estabilidad 1 el score no cambia; con estabilidad 0 conserva el
    ``piso``. Un destino sin estabilidad calculable recibe la estabilidad
    neutra ``NEUTRAL_STABILITY``. Empates se desempatan por ISO3 para que el
    ranking sea determinístico.

    Args:
        ranking: DataFrame con las columnas del ranking de oportunidad
            (produce ``scoring.rank_markets``), indexable por
            ``config.COL_COUNTRY``.
        stability: Series indexada por país (ISO3) de :func:`stability_score`.
        floor: piso de la penalización en [0, 1]; fuente: ``config.MACRO_FLOOR``.

    Returns:
        DataFrame con las columnas nuevas ``stability_score`` y
        ``final_score``, reordenado y re-rankeado por score final.

    Raises:
        ValueError: si ``floor`` está fuera de [0, 1].
    """
    if not 0.0 <= floor <= 1.0:
        raise ValueError(f"floor debe estar en [0, 1]; recibido: {floor}")
    result = ranking.copy()
    aligned = stability.reindex(result[config.COL_COUNTRY]).fillna(NEUTRAL_STABILITY)
    result[config.COL_STABILITY] = aligned.to_numpy()
    result[config.COL_FINAL_SCORE] = result[config.COL_SCORE] * (
        floor + (1.0 - floor) * result[config.COL_STABILITY]
    )
    result = result.sort_values(
        [config.COL_FINAL_SCORE, config.COL_COUNTRY], ascending=[False, True]
    ).reset_index(drop=True)
    result[config.COL_RANK] = range(1, len(result) + 1)
    return result
