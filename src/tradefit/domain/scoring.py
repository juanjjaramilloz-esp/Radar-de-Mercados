"""Combinación de métricas y ranking de mercados destino.

El score de oportunidad es un promedio ponderado de métricas normalizadas a
[0, 1] con min-max. Los pesos NO viven aquí: se reciben como argumento y su
única fuente es ``config.WEIGHTS`` (los pasa el pipeline). El RCA del origen
es constante entre destinos, así que se adjunta como columna de contexto pero
no participa del score.
"""

from collections.abc import Mapping
from typing import Final

import pandas as pd

from tradefit import config
from tradefit.contracts import MarketInputs
from tradefit.domain import indices

#: Métricas donde menos es mejor: se normalizan invertidas (mínimo → 1.0).
INVERTED_METRICS: frozenset[str] = frozenset({"tariff_faced"})

#: Relleno del NaN normalizado por métrica. El default (0.0) trata la
#: ausencia como falta de evidencia de oportunidad; el arancel, el margen de
#: preferencia y la accesibilidad sin dato se rellenan neutros (0.5) porque
#: "la fuente no publica el dato" no es evidencia de fricción alta ni de
#: desventaja — mismo criterio que la estabilidad macro neutra.
_NAN_FILL: dict[str, float] = {
    "tariff_faced": 0.5,
    "preference_margin": 0.5,
    "accessibility": 0.5,
}

#: Métricas cuyo NaN NO es hueco de fuente sino cero observado por diseño:
#: la ausencia del par (país, año) en el flujo bilateral significa flujo
#: cero (decisión 2026-07-05), no dato faltante. Para la cobertura de datos
#: cuentan siempre como observadas.
_ABSENCE_IS_ZERO: frozenset[str] = frozenset({"market_share", "share_trend"})


def data_coverage(
    metric_values: Mapping[str, "pd.Series[float]"],
    weights: Mapping[str, float],
    countries: pd.Index,
) -> pd.Series:
    """Fracción del peso del score respaldada por dato observado, por mercado.

    Definición: ``cobertura(d) = Σᵢ wᵢ · obsᵢ(d) / Σᵢ wᵢ``, donde
    ``obsᵢ(d) = 1`` si la métrica *i* trae dato crudo para el destino *d*
    (no NaN **antes** del relleno del scoring) y 0 si el hueco proviene de la
    fuente (arancel sin publicar en WITS, destino sin canasta HS2, ventana de
    CAGR inválida, destino sin distancia CEPII ni LPI…). Excepción: en las
    métricas de ``_ABSENCE_IS_ZERO`` la ausencia es un cero observado por
    diseño y cuenta como dato. Cobertura 1.0 = score respaldado al 100 % por
    datos; valores menores señalan cuánto del score descansa en los rellenos
    (0.0 o neutro 0.5) de :func:`normalized_metric`. Es un indicador de
    calidad del insumo, no una métrica económica: no pondera en el score.

    Args:
        metric_values: valores crudos por métrica (previos a normalizar),
            indexados por destino.
        weights: peso por nombre de métrica (fuente: ``config.WEIGHTS``).
        countries: universo de destinos del ranking.

    Returns:
        Series en [0, 1] indexada por ``countries``.
    """
    total_weight = sum(weights.values())
    coverage = pd.Series(0.0, index=countries)
    for name, weight in weights.items():
        if name in _ABSENCE_IS_ZERO:
            observed = pd.Series(1.0, index=countries)
        else:
            observed = metric_values[name].reindex(countries).notna().astype(float)
        coverage = coverage + observed * weight
    # El clip absorbe el error de redondeo binario de Σwᵢ/Σwᵢ (≈1+2e-16).
    return (coverage / total_weight).clip(0.0, 1.0)


def normalized_metric(name: str, values: pd.Series) -> pd.Series:
    """Normaliza una métrica a [0, 1] según su semántica (más o menos = mejor).

    Min-max directo para las métricas de oportunidad; invertido (el mínimo
    recibe 1.0) para las de ``INVERTED_METRICS``. El NaN se rellena con el
    valor de ``_NAN_FILL`` (0.0 por defecto). Lo comparten el scoring y la
    narrativa para que ambas lean cada métrica en la misma dirección.

    Args:
        name: nombre de la métrica (clave de ``config.WEIGHTS``).
        values: valores crudos indexados por destino.

    Returns:
        Series en [0, 1] sin NaN, alineada al índice de entrada.
    """
    normalized = _min_max(-values) if name in INVERTED_METRICS else _min_max(values)
    return normalized.fillna(_NAN_FILL.get(name, 0.0))


def _min_max(values: pd.Series) -> pd.Series:
    """Normaliza una serie al rango [0, 1] con min-max (ignora NaN).

    Si todos los valores son iguales, la métrica no discrimina: devuelve 1.0
    para todos, de modo que no penalice a ningún mercado.
    """
    vmin = float(values.min())
    vmax = float(values.max())
    if vmax == vmin:
        return pd.Series(1.0, index=values.index)
    normalized: pd.Series = (values - vmin) / (vmax - vmin)
    return normalized


def _complementarity_by_destination(data: MarketInputs) -> pd.Series:
    """Complementariedad origen↔destino para cada destino con canasta."""
    origin_rows = data.baskets[data.baskets[config.COL_COUNTRY] == config.ORIGIN_ISO3]
    origin_basket = origin_rows.set_index(config.COL_CMD)[config.COL_VALUE]
    values: dict[str, float] = {}
    destinations = data.baskets[data.baskets[config.COL_COUNTRY] != config.ORIGIN_ISO3]
    for iso3, group in destinations.groupby(config.COL_COUNTRY):
        destination_basket = group.set_index(config.COL_CMD)[config.COL_VALUE]
        values[str(iso3)] = indices.complementarity(origin_basket, destination_basket)
    return pd.Series(values, name=config.COL_COMPLEMENTARITY)


def rank_markets(data: MarketInputs, weights: Mapping[str, float]) -> pd.DataFrame:
    """Calcula el score de oportunidad y rankea los mercados destino.

    Definición: ``score(d) = Σᵢ wᵢ · normᵢ(métricaᵢ(d)) / Σᵢ wᵢ`` — promedio
    ponderado de métricas min-max normalizadas. Métricas disponibles:
    ``market_size``, ``import_growth``, ``market_share``, ``share_trend``,
    ``complementarity``, ``tariff_faced`` (invertida: menos arancel = mejor),
    ``preference_margin`` (arancel de los competidores − arancel del origen;
    más = mejor) y ``accessibility`` (distancia gravitacional + LPI). Un NaN
    en una métrica (p. ej. destino sin canasta) se trata como ausencia de
    evidencia: aporta 0 tras normalizar, salvo el arancel, el margen de
    preferencia y la accesibilidad sin dato, que aportan neutro (0.5 — ver
    ``normalized_metric``).
    Empates se desempatan por código ISO3 para que el ranking sea
    determinístico.

    Args:
        data: insumos validados (``contracts.MarketInputs``).
        weights: peso por nombre de métrica (fuente: ``config.WEIGHTS``).

    Returns:
        DataFrame conforme a ``ranking_schema``: una fila por mercado con las
        métricas crudas, el RCA de contexto, la cobertura de datos
        (:func:`data_coverage`) y el score, ordenado por score descendente.

    Raises:
        ValueError: si ``weights`` referencia métricas desconocidas o no
            contiene ningún peso positivo.
    """
    market_sizes = indices.market_size(data.imports)
    if data.distances is not None:
        distances = data.distances.reindex(market_sizes.index)
    else:
        distances = pd.Series(float("nan"), index=market_sizes.index)
    tariff = indices.tariff_faced(data.tariffs)
    if data.competitor_tariff is not None:
        competitor_tariff = data.competitor_tariff.reindex(market_sizes.index)
    else:
        competitor_tariff = pd.Series(float("nan"), index=market_sizes.index)
    metric_values: dict[str, pd.Series] = {
        "market_size": market_sizes,
        "import_growth": indices.import_growth(data.imports),
        "market_share": indices.market_share(data.imports, data.bilateral),
        "share_trend": indices.market_share_trend(data.imports, data.bilateral),
        "complementarity": _complementarity_by_destination(data),
        "tariff_faced": tariff,
        # Margen de preferencia relativo (Fugazza & Nicita 2013): arancel
        # que enfrentan los competidores − arancel del origen. Positivo =
        # ventaja arancelaria; NaN si falta cualquiera de los dos lados.
        "preference_margin": competitor_tariff - tariff.reindex(market_sizes.index),
        "accessibility": indices.accessibility(distances, data.lpi),
    }

    unknown = set(weights) - set(metric_values)
    if unknown:
        raise ValueError(f"Pesos para métricas desconocidas: {sorted(unknown)}")
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("Se requiere al menos un peso positivo en weights")

    countries = metric_values["market_size"].index
    score = pd.Series(0.0, index=countries)
    for name, weight in weights.items():
        aligned = metric_values[name].reindex(countries)
        score = score + normalized_metric(name, aligned) * weight
    score = score / total_weight

    names = data.imports.drop_duplicates(config.COL_COUNTRY).set_index(config.COL_COUNTRY)[
        config.COL_COUNTRY_NAME
    ]
    ranking = pd.DataFrame(
        {
            config.COL_COUNTRY_NAME: names,
            config.COL_MARKET_SIZE: metric_values["market_size"],
            config.COL_GROWTH: metric_values["import_growth"].reindex(countries),
            config.COL_SHARE: metric_values["market_share"].reindex(countries).fillna(0.0),
            config.COL_SHARE_TREND: (metric_values["share_trend"].reindex(countries).fillna(0.0)),
            config.COL_COMPLEMENTARITY: (
                metric_values["complementarity"].reindex(countries).fillna(0.0)
            ),
            # El arancel conserva el NaN: "sin dato en WITS" no es arancel 0.
            config.COL_TARIFF: metric_values["tariff_faced"].reindex(countries),
            # Arancel de los competidores (contexto) y margen de preferencia
            # relativo (pondera); NaN = sin datos de competidores.
            config.COL_COMPETITOR_TARIFF: competitor_tariff,
            config.COL_PREF_MARGIN: metric_values["preference_margin"].reindex(countries),
            # Distancia (contexto) y accesibilidad (pondera); NaN = sin dato.
            config.COL_DISTANCE_KM: distances,
            config.COL_ACCESSIBILITY: metric_values["accessibility"].reindex(countries),
            config.COL_RCA: data.rca,
            # Cobertura de datos: % del peso del score con dato observado
            # (transparencia del insumo; ver data_coverage). No pondera.
            config.COL_COVERAGE: data_coverage(metric_values, weights, countries),
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


#: Columna del snapshot que expone cada métrica del scoring. Permite
#: re-scorear un ranking ya construido (simulador de prioridades de la app)
#: sin volver a los insumos crudos de ``rank_markets``.
METRIC_COLUMNS: Final[dict[str, str]] = {
    "market_size": config.COL_MARKET_SIZE,
    "import_growth": config.COL_GROWTH,
    "market_share": config.COL_SHARE,
    "share_trend": config.COL_SHARE_TREND,
    "complementarity": config.COL_COMPLEMENTARITY,
    "tariff_faced": config.COL_TARIFF,
    "preference_margin": config.COL_PREF_MARGIN,
    "accessibility": config.COL_ACCESSIBILITY,
}


def score_contributions(ranking: pd.DataFrame, weights: Mapping[str, float]) -> pd.DataFrame:
    """Contribución de cada métrica al score de oportunidad, por mercado.

    Definición: ``contribuciónᵢ(d) = wᵢ · normᵢ(métricaᵢ(d)) / Σᵢ wᵢ`` — los
    sumandos del promedio ponderado de :func:`rank_markets`, de modo que la
    suma por fila reproduce el score de oportunidad. Opera sobre las columnas
    de métricas crudas que el ranking del snapshot ya trae
    (``METRIC_COLUMNS``), con las mismas normalizaciones que el scoring
    (``normalized_metric``): min-max sobre los mercados presentes.

    Args:
        ranking: ranking del snapshot (una fila por mercado) con
            ``config.COL_COUNTRY`` y las columnas de las métricas de ``weights``.
        weights: peso por nombre de métrica (``config.WEIGHTS`` o los pesos
            alternativos del laboratorio de la app).

    Returns:
        DataFrame indexado por ISO3 con una columna por métrica de ``weights``.

    Raises:
        ValueError: si hay pesos de métricas desconocidas, ningún peso
            positivo, o falta la columna de una métrica en ``ranking``.
    """
    unknown = set(weights) - set(METRIC_COLUMNS)
    if unknown:
        raise ValueError(f"Pesos para métricas desconocidas: {sorted(unknown)}")
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("Se requiere al menos un peso positivo en weights")
    missing = sorted(
        METRIC_COLUMNS[name] for name in weights if METRIC_COLUMNS[name] not in ranking.columns
    )
    if missing:
        raise ValueError(f"Columnas de métricas ausentes en el ranking: {missing}")

    indexed = ranking.set_index(config.COL_COUNTRY)
    contributions = {
        name: normalized_metric(name, indexed[METRIC_COLUMNS[name]]) * (weight / total_weight)
        for name, weight in weights.items()
    }
    return pd.DataFrame(contributions)


def rescore_ranking(
    ranking: pd.DataFrame,
    weights: Mapping[str, float],
    macro_floor: float = config.MACRO_FLOOR,
) -> pd.DataFrame:
    """Re-rankea un snapshot con pesos alternativos (what-if de la app).

    Reaplica las dos definiciones oficiales sobre las métricas crudas del
    ranking: ``score = Σᵢ wᵢ·normᵢ / Σᵢ wᵢ`` (:func:`rank_markets`) y
    ``final = score × (piso + (1 − piso) × estabilidad)``
    (:func:`tradefit.domain.macro_filter.apply_stability_penalty`), usando la
    estabilidad ya presente en el snapshot. Mismo desempate por ISO3. Con el
    mismo universo de mercados y ``config.WEIGHTS`` reproduce el ranking
    oficial (la normalización min-max se recalcula sobre los mercados
    presentes).

    Args:
        ranking: ranking del snapshot con ``config.COL_COUNTRY``,
            ``config.COL_STABILITY`` y las columnas de métricas de ``weights``.
        weights: peso por nombre de métrica.
        macro_floor: piso de la penalización macro (fuente:
            ``config.MACRO_FLOOR`` o el ``macro_floor`` del meta del snapshot).

    Returns:
        Copia del ranking con ``opportunity_score``, ``final_score`` y
        ``rank`` recalculados, reordenada por score final descendente.

    Raises:
        ValueError: si ``macro_floor`` está fuera de [0, 1] o los pesos son
            inválidos (ver :func:`score_contributions`).
    """
    if not 0.0 <= macro_floor <= 1.0:
        raise ValueError(f"macro_floor debe estar en [0, 1]; recibido: {macro_floor}")
    score = score_contributions(ranking, weights).sum(axis=1)
    result = ranking.copy()
    result[config.COL_SCORE] = score.reindex(result[config.COL_COUNTRY]).to_numpy()
    result[config.COL_FINAL_SCORE] = result[config.COL_SCORE] * (
        macro_floor + (1.0 - macro_floor) * result[config.COL_STABILITY]
    )
    result = result.sort_values(
        [config.COL_FINAL_SCORE, config.COL_COUNTRY], ascending=[False, True]
    ).reset_index(drop=True)
    result[config.COL_RANK] = range(1, len(result) + 1)
    return result
