"""Narrativa por reglas del ranking de mercados.

Generador puro y determinístico: convierte las filas del ranking (ya
validadas contra ``contracts.ranking_schema``) en frases transparentes donde
**cada afirmación incluye el número que la respalda** — regla de calidad del
proyecto: nada de adjetivos sin dato. Las únicas calificaciones ("crece",
"pierde terreno") se derivan directamente del signo del número citado.

Bilingüe (``es``/``en``): las plantillas y el formato numérico (RAE vs.
convención inglesa) viven aquí, por idioma; el pipeline serializa ambas
versiones a ``data/processed/`` y la app solo elige cuál leer. Sin I/O.
"""

from collections.abc import Callable, Mapping
from typing import Any, Literal, cast

import pandas as pd

from tradefit import config
from tradefit.domain import scoring

#: Idiomas soportados por la narrativa (los mismos del toggle de la app).
Lang = Literal["es", "en"]
LANGS: tuple[Lang, ...] = ("es", "en")

#: Etiquetas de cada métrica ponderada (para el "porqué" del top-3), por idioma.
METRIC_LABELS: dict[Lang, dict[str, str]] = {
    "es": {
        "market_size": "tamaño de mercado",
        "import_growth": "crecimiento de la demanda",
        "market_share": "cuota ya ganada",
        "share_trend": "momentum de la cuota",
        "complementarity": "complementariedad de canastas",
        "tariff_faced": "arancel enfrentado",
    },
    "en": {
        "market_size": "market size",
        "import_growth": "demand growth",
        "market_share": "share already won",
        "share_trend": "share momentum",
        "complementarity": "basket complementarity",
        "tariff_faced": "tariff faced",
    },
}

#: Columna del ranking donde vive el valor crudo de cada métrica ponderada.
_METRIC_COLUMNS: dict[str, str] = {
    "market_size": config.COL_MARKET_SIZE,
    "import_growth": config.COL_GROWTH,
    "market_share": config.COL_SHARE,
    "share_trend": config.COL_SHARE_TREND,
    "complementarity": config.COL_COMPLEMENTARITY,
    "tariff_faced": config.COL_TARIFF,
}

#: Plantillas de las frases, por idioma. Los verbos con carga ("crece",
#: "pierde") son claves separadas: la elección la hace el signo del número.
_TEMPLATES: dict[str, dict[Lang, str]] = {
    "imports": {
        "es": ("{dest} importa {size} al año de {product} (promedio de los últimos {years} años)."),
        "en": "{dest} imports {size} a year of {product} (average of the last {years} years).",
    },
    "growth_missing": {
        "es": "Sin dato suficiente de crecimiento en la ventana de {years} años.",
        "en": "Not enough growth data over the {years}-year window.",
    },
    "growth_up": {
        "es": "La demanda crece al {pct} anual (CAGR).",
        "en": "Demand grows at {pct} per year (CAGR).",
    },
    "growth_down": {
        "es": "La demanda se contrae al {pct} anual (CAGR).",
        "en": "Demand shrinks at {pct} per year (CAGR).",
    },
    "share_zero": {
        "es": "{origin} no registra ventas de {product} en {dest} (cuota 0 %).",
        "en": "{origin} records no sales of {product} in {dest} (0 % share).",
    },
    "share_gain": {
        "es": "{origin} ya tiene {share} del mercado y gana {pp} pp de cuota en la ventana.",
        "en": (
            "{origin} already holds {share} of the market and gains {pp} pp "
            "of share over the window."
        ),
    },
    "share_loss": {
        "es": "{origin} ya tiene {share} del mercado y pierde {pp} pp de cuota en la ventana.",
        "en": (
            "{origin} already holds {share} of the market and loses {pp} pp "
            "of share over the window."
        ),
    },
    "complementarity": {
        "es": (
            "La canasta exportadora de {origin} encaja {comp} (escala 0–1) "
            "con la demanda importadora de {dest}."
        ),
        "en": (
            "The export basket of {origin} fits the import demand of {dest} at {comp} (0–1 scale)."
        ),
    },
    "tariff_free": {
        "es": "{product} entra a {dest} sin arancel (0 % efectivamente aplicado).",
        "en": "{product} enters {dest} duty-free (0 % effectively applied).",
    },
    "tariff_paid": {
        "es": "{product} paga en {dest} un arancel efectivamente aplicado de {pct}.",
        "en": "{product} faces an effectively applied tariff of {pct} in {dest}.",
    },
    "stability": {
        "es": (
            "Estabilidad macro de {dest} {stability}: el filtro deja el "
            "score en {final} (bruto {raw})."
        ),
        "en": (
            "Macro stability of {dest} at {stability}: the filter leaves "
            "the score at {final} (raw {raw})."
        ),
    },
    "reason": {
        "es": "{pos}.º destino por {label} ({value})",
        "en": "destination #{pos} by {label} ({value})",
    },
}


def _fmt_millions(usd: float, lang: Lang) -> str:
    """Formatea USD como millones con miles según el idioma: ``USD 8.993 M``."""
    text = f"USD {usd / 1e6:,.0f} M"
    return text.replace(",", ".") if lang == "es" else text


def _fmt_decimal(value: float, decimals: int, lang: Lang) -> str:
    """Decimales según el idioma: ``0.42 → "0,42"`` (es) / ``"0.42"`` (en)."""
    text = f"{value:.{decimals}f}"
    return text.replace(".", ",") if lang == "es" else text


def _fmt_pct(fraction: float, lang: Lang, decimals: int = 1) -> str:
    """Fracción como porcentaje: ``0.092 → "9,2 %"`` (es) / ``"9.2 %"`` (en)."""
    return f"{_fmt_decimal(fraction * 100, decimals, lang)} %"


def _fmt_pp_signed(fraction: float, lang: Lang) -> str:
    """Puntos porcentuales con signo explícito: ``0.077 → +7,7 pp``."""
    sign = "+" if fraction >= 0 else "−"
    return f"{sign}{_fmt_decimal(abs(fraction) * 100, 1, lang)} pp"


def _metric_formatters(lang: Lang) -> dict[str, Callable[[float], str]]:
    """Formateador del valor crudo de cada métrica para las frases del porqué."""
    per_year = "/año" if lang == "es" else "/year"
    annual = "anual" if lang == "es" else "per year"
    share_of = "cuota de" if lang == "es" else "share of"
    window = "en la ventana" if lang == "es" else "over the window"
    index_scale = "índice {v} (escala 0–1)" if lang == "es" else "index {v} (0–1 scale)"
    applied = "efectivamente aplicado" if lang == "es" else "effectively applied"
    return {
        "market_size": lambda v: f"{_fmt_millions(v, lang)}{per_year}",
        "import_growth": lambda v: f"{_fmt_pct(v, lang)} {annual}",
        "market_share": lambda v: f"{share_of} {_fmt_pct(v, lang)}",
        "share_trend": lambda v: f"{_fmt_pp_signed(v, lang)} {window}",
        "complementarity": lambda v: index_scale.format(v=_fmt_decimal(v, 2, lang)),
        "tariff_faced": lambda v: f"{_fmt_pct(v, lang)} {applied}",
    }


def _t(key: str, lang: Lang, **kwargs: object) -> str:
    """Plantilla ``key`` en ``lang``, formateada con ``kwargs``."""
    return _TEMPLATES[key][lang].format(**kwargs)


def market_sentences(
    row: "Mapping[str, Any] | pd.Series[Any]",
    window_years: int = config.MARKET_SIZE_YEARS,
    *,
    product_label: str,
    origin_name: str,
    lang: Lang = "es",
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
        lang: idioma de las frases (``"es"`` por defecto).

    Returns:
        Lista de frases en el idioma pedido, todas con al menos un número.
    """
    sentences: list[str] = []
    destination = str(row[config.COL_COUNTRY_NAME])

    size = float(row[config.COL_MARKET_SIZE])
    sentences.append(
        _t(
            "imports",
            lang,
            dest=destination,
            size=_fmt_millions(size, lang),
            product=product_label,
            years=window_years,
        )
    )

    growth = row[config.COL_GROWTH]
    if pd.isna(growth):
        sentences.append(_t("growth_missing", lang, years=window_years))
    elif float(growth) >= 0:
        sentences.append(_t("growth_up", lang, pct=_fmt_pct(float(growth), lang)))
    else:
        sentences.append(_t("growth_down", lang, pct=_fmt_pct(abs(float(growth)), lang)))

    share = float(row[config.COL_SHARE])
    trend = float(row[config.COL_SHARE_TREND])
    if share == 0:
        sentences.append(
            _t("share_zero", lang, origin=origin_name, product=product_label, dest=destination)
        )
    else:
        key = "share_gain" if trend >= 0 else "share_loss"
        sentences.append(
            _t(
                key,
                lang,
                origin=origin_name,
                share=_fmt_pct(share, lang),
                pp=_fmt_decimal(abs(trend) * 100, 1, lang),
            )
        )

    comp = float(row[config.COL_COMPLEMENTARITY])
    sentences.append(
        _t(
            "complementarity",
            lang,
            origin=origin_name,
            comp=_fmt_decimal(comp, 2, lang),
            dest=destination,
        )
    )

    # Snapshots construidos antes de la métrica de aranceles no traen la
    # columna; NaN = WITS no publica el dato para ese destino.
    if config.COL_TARIFF in row and not pd.isna(row[config.COL_TARIFF]):
        tariff = float(row[config.COL_TARIFF])
        if tariff == 0:
            sentences.append(_t("tariff_free", lang, product=product_label, dest=destination))
        else:
            sentences.append(
                _t(
                    "tariff_paid",
                    lang,
                    product=product_label,
                    dest=destination,
                    pct=_fmt_pct(tariff, lang),
                )
            )

    stability = float(row[config.COL_STABILITY])
    raw = float(row[config.COL_SCORE])
    final = float(row[config.COL_FINAL_SCORE])
    sentences.append(
        _t(
            "stability",
            lang,
            dest=destination,
            stability=_fmt_decimal(stability, 2, lang),
            final=_fmt_decimal(final, 3, lang),
            raw=_fmt_decimal(raw, 3, lang),
        )
    )
    return sentences


def top_recommendations(
    ranking: pd.DataFrame,
    weights: Mapping[str, float],
    n: int = config.TOP_RECOMMENDATIONS,
    *,
    lang: Lang = "es",
) -> list[dict[str, Any]]:
    """Top-N de mercados recomendados con el porqué (drivers del score).

    El porqué de cada mercado son sus dos métricas con mayor contribución al
    score (peso × valor min-max normalizado dentro del ranking), citadas con
    el valor crudo y la posición del destino en esa métrica.

    Args:
        ranking: DataFrame conforme a ``ranking_schema`` (ordenado o no).
        weights: peso por métrica (fuente: ``config.WEIGHTS``).
        n: cuántos mercados recomendar.
        lang: idioma de las razones (``"es"`` por defecto).

    Returns:
        Lista de dicts ``{iso3, name, final_score, reasons}`` en orden de
        ranking; ``reasons`` son frases con número.

    Raises:
        ValueError: si ``weights`` referencia métricas sin columna conocida.
    """
    unknown = set(weights) - set(_METRIC_COLUMNS)
    if unknown:
        raise ValueError(f"Métricas sin columna en el ranking: {sorted(unknown)}")

    formatters = _metric_formatters(lang)
    by_country = ranking.set_index(config.COL_COUNTRY)
    contributions = pd.DataFrame(index=by_country.index)
    positions = pd.DataFrame(index=by_country.index)
    for metric, weight in weights.items():
        values = by_country[_METRIC_COLUMNS[metric]]
        # La normalización (incluida la dirección: en el arancel menos es
        # mejor) es la misma del scoring, para que el "porqué" cite las
        # contribuciones reales al score.
        contributions[metric] = scoring.normalized_metric(metric, values) * weight
        ascending = metric in scoring.INVERTED_METRICS
        positions[metric] = values.rank(ascending=ascending, method="min")

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
                _t(
                    "reason",
                    lang,
                    pos=position,
                    label=METRIC_LABELS[lang][metric],
                    value=formatters[metric](raw_value),
                )
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
    lang: Lang = "es",
) -> dict[str, Any]:
    """Narrativa de un idioma del snapshot, lista para serializar a JSON.

    Con ``lang="en"`` los nombres de los destinos del MVP se toman de
    ``config.DESTINATIONS_EN`` (el resto conserva el nombre del ranking).

    Args:
        ranking: DataFrame conforme a ``ranking_schema``.
        weights: peso por métrica (fuente: ``config.WEIGHTS``).
        window_years: ventana de años de las métricas.
        top_n: cuántos mercados recomendar.
        product_label: nombre legible del producto, p. ej. ``"Café (HS 0901)"``.
        origin_name: nombre del país de origen (fijo: Colombia).
        lang: idioma de la narrativa (``"es"`` por defecto).

    Returns:
        Dict determinístico ``{"recommendations": [...], "markets":
        {iso3: [frases...]}}``.
    """
    if lang == "en":
        names = ranking[config.COL_COUNTRY].map(config.DESTINATIONS_EN.get)
        ranking = ranking.assign(
            **{config.COL_COUNTRY_NAME: names.fillna(ranking[config.COL_COUNTRY_NAME])}
        )
    markets = {
        str(row[config.COL_COUNTRY]): market_sentences(
            row,
            window_years,
            product_label=product_label,
            origin_name=origin_name,
            lang=lang,
        )
        for _, row in ranking.iterrows()
    }
    return {
        "recommendations": top_recommendations(ranking, weights, top_n, lang=lang),
        "markets": markets,
    }
