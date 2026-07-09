"""Validación predictiva del score (backtest fuera de muestra).

Funciones puras: el pipeline recalcula las métricas de comercio del score
con datos históricos (as-of T), re-scorea con los pesos oficiales y usa
estas funciones para contrastar el ranking resultante contra el crecimiento
bilateral realizado después de T. Sin red, sin I/O; cada función cita su
definición y se testea con valores calculados a mano.
"""

import pandas as pd


def symmetric_growth(base: "pd.Series[float]", outcome: "pd.Series[float]") -> "pd.Series[float]":
    """Tasa de crecimiento simétrica entre dos periodos, robusta a ceros.

    Definición: ``g = (y − x) / ((x + y) / 2)`` — la tasa de
    Davis-Haltiwanger-Schuh (Davis, Haltiwanger & Schuh 1996, *Job Creation
    and Destruction*, MIT Press), estándar para flujos con entradas y
    salidas: queda acotada en [−2, 2], vale +2 para un flujo que nace de 0
    y −2 para uno que muere, y coincide con la tasa convencional para
    cambios pequeños. Ambos periodos en 0 → NaN (sin señal).

    Args:
        base: valor del periodo inicial por mercado (p. ej. promedio de la
            ventana de entrenamiento; los ausentes cuentan como 0).
        outcome: valor del periodo posterior por mercado (mismo criterio).

    Returns:
        Series de tasas indexada por la unión de ambos índices.
    """
    x = base.reindex(base.index.union(outcome.index)).fillna(0.0)
    y = outcome.reindex(x.index).fillna(0.0)
    mid = (x + y) / 2.0
    growth: pd.Series = (y - x).where(mid > 0) / mid.where(mid > 0)
    return growth


def spearman_correlation(a: "pd.Series[float]", b: "pd.Series[float]") -> float:
    """Correlación de rangos de Spearman entre dos series alineadas.

    Definición: coeficiente de Pearson sobre los rangos (Spearman 1904;
    empates con rango promedio, la convención estándar). Mide si el orden
    de ``a`` anticipa el orden de ``b`` sin asumir linealidad — la pregunta
    exacta del backtest: ¿los mercados mejor rankeados crecieron más?

    Args:
        a: primera serie (p. ej. score as-of T) indexada por mercado.
        b: segunda serie (p. ej. crecimiento realizado) indexada por mercado.

    Returns:
        ρ en [−1, 1] sobre los mercados con dato en ambas series; NaN si
        quedan menos de 3 pares (una correlación de 2 puntos no informa).
    """
    common = a.dropna().index.intersection(b.dropna().index)
    if len(common) < 3:
        return float("nan")
    ranks_a = a.loc[common].rank()
    ranks_b = b.loc[common].rank()
    return float(ranks_a.corr(ranks_b))


def top_k_hit_rate(score: "pd.Series[float]", realized: "pd.Series[float]", k: int = 5) -> float:
    """Fracción del top-k del score que quedó en el top-k del crecimiento real.

    Definición: ``|top_k(score) ∩ top_k(realized)| / k`` — la métrica de
    "aciertos" más legible para un no estadístico: de los k mercados que el
    score puso arriba, ¿cuántos efectivamente crecieron entre los k que más
    crecieron? Solo cuenta mercados con dato en ambas series.

    Args:
        score: score por mercado (as-of T).
        realized: crecimiento realizado por mercado.
        k: tamaño del top (default 5).

    Returns:
        Fracción en [0, 1]; NaN si hay menos de ``k`` pares con dato.

    Raises:
        ValueError: si ``k`` no es positivo.
    """
    if k <= 0:
        raise ValueError(f"k debe ser positivo; recibido: {k}")
    common = score.dropna().index.intersection(realized.dropna().index)
    if len(common) < k:
        return float("nan")
    top_score = set(score.loc[common].nlargest(k).index)
    top_real = set(realized.loc[common].nlargest(k).index)
    return len(top_score & top_real) / k
