"""Narrativa por reglas del ranking de mercados.

Generador puro y determinístico: convierte las filas del ranking (ya
validadas contra ``contracts.ranking_schema``) en frases transparentes donde
**cada afirmación incluye el número que la respalda** — regla de calidad del
proyecto: nada de adjetivos sin dato. Las únicas calificaciones ("crece",
"pierde terreno") se derivan directamente del signo del número citado.

Sin I/O: el pipeline serializa el resultado a ``data/processed/`` y la app
solo lo lee.
"""

from collections.abc import Callable, Mapping
from typing import Any, cast

import pandas as pd

from tradefit import config

#: Etiquetas en español de cada métrica ponderada (para el "porqué" del top-3).
METRIC_LABELS: dict[str, str] = {
    "market_size": "tamaño de mercado",
    "import_growth": "crecimiento de la demanda",
    "market_share": "cuota ya ganada",
    "share_trend": "momentum de la cuota",
    "complementarity": "complementariedad de canastas",
}

#: Columna del ranking donde vive el valor crudo de cada métrica ponderada.
_METRIC_COLUMNS: dict[str, str] = {
    "market_size": config.COL_MARKET_SIZE,
    "import_growth": config.COL_GROWTH,
    "market_share": config.COL_SHARE,
    "share_trend": config.COL_SHARE_TREND,
    "complementarity": config.COL_COMPLEMENTARITY,
}


def _fmt_millions(usd: float) -> str:
    """Formatea USD como millones con separador de miles: ``USD 8.993 M``."""
    millions = usd / 1e6
    return f"USD {millions:,.0f} M".replace(",", ".")


def _fmt_decimal(value: float, decimals: int) -> str:
    """Decimales con coma, convención española de la narrativa: ``0.42 → 0,42``."""
    return f"{value:.{decimals}f}".replace(".", ",")


def _fmt_pct(fraction: float, decimals: int = 1) -> str:
    """Formatea una fracción como porcentaje español: ``0.092 → 9,2 %``."""
    return f"{_fmt_decimal(fraction * 100, decimals)} %"


def _fmt_pp_signed(fraction: float) -> str:
    """Puntos porcentuales con signo explícito: ``0.077 → +7,7 pp``."""
    sign = "+" if fraction >= 0 else "−"
    return f"{sign}{_fmt_decimal(abs(fraction) * 100, 1)} pp"


#: Formateador del valor crudo de cada métrica para las frases del porqué.
_METRIC_FORMATTERS: dict[str, Callable[[float], str]] = {
    "market_size": lambda v: f"{_fmt_millions(v)}/año",
    "import_growth": lambda v: f"{_fmt_pct(v)} anual",
    "market_share": lambda v: f"cuota de {_fmt_pct(v)}",
    "share_trend": lambda v: f"{_fmt_pp_signed(v)} en la ventana",
    "complementarity": lambda v: f"índice {_fmt_decimal(v, 2)} (escala 0–1)",
}


def market_sentences(
    row: "Mapping[str, Any] | pd.Series[Any]",
    window_years: int = config.MARKET_SIZE_YEARS,
    *,
    product_label: str,
    origin_name: str,
) -> list[str]:
    """Frases de narrativa para un mercado (una fila del ranking).

    Reglas transparentes: cada frase cita el número del snapshot que la
    respalda; los verbos ("crece"/"se contrae", "gana"/"pierde") se deciden
    solo por el signo de ese número. Producto, origen y destino aparecen con
    su nombre (el destino sale de la propia fila).

    Args:
        row: fila del ranking (Series o dict) con las columnas de
            ``ranking_schema``.
        window_years: ventana de años de las métricas (para citarla).
        product_label: nombre legible del producto, p. ej. ``"Café (HS 0901)"``.
        origin_name: nombre del país de origen, p. ej. ``"Colombia"``.

    Returns:
        Lista de frases en español, todas con al menos un número.
    """
    sentences: list[str] = []
    destination = str(row[config.COL_COUNTRY_NAME])

    size = float(row[config.COL_MARKET_SIZE])
    sentences.append(
        f"{destination} importa {_fmt_millions(size)} al año de {product_label} "
        f"(promedio de los últimos {window_years} años)."
    )

    growth = row[config.COL_GROWTH]
    if pd.isna(growth):
        sentences.append(
            f"Sin dato suficiente de crecimiento en la ventana de {window_years} años."
        )
    elif float(growth) >= 0:
        sentences.append(f"La demanda crece al {_fmt_pct(float(growth))} anual (CAGR).")
    else:
        sentences.append(f"La demanda se contrae al {_fmt_pct(abs(float(growth)))} anual (CAGR).")

    share = float(row[config.COL_SHARE])
    trend = float(row[config.COL_SHARE_TREND])
    if share == 0:
        sentences.append(
            f"{origin_name} no registra ventas de {product_label} en {destination} (cuota 0 %)."
        )
    else:
        verb = "gana" if trend >= 0 else "pierde"
        sentences.append(
            f"{origin_name} ya tiene {_fmt_pct(share)} del mercado y {verb} "
            f"{_fmt_decimal(abs(trend) * 100, 1)} pp de cuota en la ventana."
        )

    comp = float(row[config.COL_COMPLEMENTARITY])
    sentences.append(
        f"La canasta exportadora de {origin_name} encaja {_fmt_decimal(comp, 2)} "
        f"(escala 0–1) con la demanda importadora de {destination}."
    )

    stability = float(row[config.COL_STABILITY])
    raw = float(row[config.COL_SCORE])
    final = float(row[config.COL_FINAL_SCORE])
    sentences.append(
        f"Estabilidad macro de {destination} {_fmt_decimal(stability, 2)}: el filtro "
        f"deja el score en {_fmt_decimal(final, 3)} (bruto {_fmt_decimal(raw, 3)})."
    )
    return sentences


def top_recommendations(
    ranking: pd.DataFrame,
    weights: Mapping[str, float],
    n: int = config.TOP_RECOMMENDATIONS,
) -> list[dict[str, Any]]:
    """Top-N de mercados recomendados con el porqué (drivers del score).

    El porqué de cada mercado son sus dos métricas con mayor contribución al
    score (peso × valor min-max normalizado dentro del ranking), citadas con
    el valor crudo y la posición del destino en esa métrica.

    Args:
        ranking: DataFrame conforme a ``ranking_schema`` (ordenado o no).
        weights: peso por métrica (fuente: ``config.WEIGHTS``).
        n: cuántos mercados recomendar.

    Returns:
        Lista de dicts ``{iso3, name, final_score, reasons}`` en orden de
        ranking; ``reasons`` son frases con número.

    Raises:
        ValueError: si ``weights`` referencia métricas sin columna conocida.
    """
    unknown = set(weights) - set(_METRIC_COLUMNS)
    if unknown:
        raise ValueError(f"Métricas sin columna en el ranking: {sorted(unknown)}")

    by_country = ranking.set_index(config.COL_COUNTRY)
    contributions = pd.DataFrame(index=by_country.index)
    positions = pd.DataFrame(index=by_country.index)
    for metric, weight in weights.items():
        values = by_country[_METRIC_COLUMNS[metric]]
        spread = values.max() - values.min()
        norm = (
            (values - values.min()) / spread if spread > 0 else pd.Series(1.0, index=values.index)
        )
        contributions[metric] = norm.fillna(0.0) * weight
        positions[metric] = values.rank(ascending=False, method="min")

    top_iso3 = ranking.sort_values(config.COL_RANK).head(n)[config.COL_COUNTRY]
    recommendations: list[dict[str, Any]] = []
    for iso3 in top_iso3:
        drivers = contributions.loc[iso3].sort_values(ascending=False).index[:2]
        reasons = []
        for metric in drivers:
            raw_value = cast(float, by_country.at[iso3, _METRIC_COLUMNS[metric]])
            if pd.isna(raw_value):
                continue
            position = int(cast(float, positions.at[iso3, metric]))
            reasons.append(
                f"{position}.º destino por {METRIC_LABELS[metric]} "
                f"({_METRIC_FORMATTERS[metric](raw_value)})"
            )
        recommendations.append(
            {
                "iso3": iso3,
                "name": str(by_country.at[iso3, config.COL_COUNTRY_NAME]),
                "final_score": round(cast(float, by_country.at[iso3, config.COL_FINAL_SCORE]), 3),
                "reasons": reasons,
            }
        )
    return recommendations


def build_narrative(
    ranking: pd.DataFrame,
    weights: Mapping[str, float],
    window_years: int = config.MARKET_SIZE_YEARS,
    top_n: int = config.TOP_RECOMMENDATIONS,
    *,
    product_label: str,
    origin_name: str = config.ORIGIN_NAME,
) -> dict[str, Any]:
    """Narrativa completa del snapshot, lista para serializar a JSON.

    Args:
        ranking: DataFrame conforme a ``ranking_schema``.
        weights: peso por métrica (fuente: ``config.WEIGHTS``).
        window_years: ventana de años de las métricas.
        top_n: cuántos mercados recomendar.
        product_label: nombre legible del producto, p. ej. ``"Café (HS 0901)"``.
        origin_name: nombre del país de origen (fijo: Colombia).

    Returns:
        Dict determinístico ``{"recommendations": [...], "markets":
        {iso3: [frases...]}}``.
    """
    markets = {
        str(row[config.COL_COUNTRY]): market_sentences(
            row, window_years, product_label=product_label, origin_name=origin_name
        )
        for _, row in ranking.iterrows()
    }
    return {
        "recommendations": top_recommendations(ranking, weights, top_n),
        "markets": markets,
    }
