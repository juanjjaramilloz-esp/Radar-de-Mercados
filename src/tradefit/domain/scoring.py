"""Combinación de métricas y ranking de mercados destino.

El score de oportunidad es un promedio ponderado de métricas normalizadas a
[0, 1] con min-max. Los pesos NO viven aquí: se reciben como argumento y su
única fuente es ``config.WEIGHTS`` (los pasa el pipeline). El RCA del origen
es constante entre destinos, así que se adjunta como columna de contexto pero
no participa del score.
"""

from collections.abc import Mapping

import pandas as pd

from tradefit import config
from tradefit.contracts import MarketInputs
from tradefit.domain import indices

#: Métricas donde menos es mejor: se normalizan invertidas (mínimo → 1.0).
INVERTED_METRICS: frozenset[str] = frozenset({"tariff_faced"})

#: Relleno del NaN normalizado por métrica. El default (0.0) trata la
#: ausencia como falta de evidencia de oportunidad; el arancel sin dato se
#: rellena neutro (0.5) porque "WITS no publica el arancel" no es evidencia
#: de arancel alto — mismo criterio que la estabilidad macro neutra.
_NAN_FILL: dict[str, float] = {"tariff_faced": 0.5}


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
    ``complementarity`` y ``tariff_faced`` (esta última invertida: menos
    arancel = mejor). Un NaN en una métrica (p. ej. destino sin canasta) se
    trata como ausencia de evidencia: aporta 0 tras normalizar, salvo el
    arancel sin dato, que aporta neutro (0.5 — ver ``normalized_metric``).
    Empates se desempatan por código ISO3 para que el ranking sea
    determinístico.

    Args:
        data: insumos validados (``contracts.MarketInputs``).
        weights: peso por nombre de métrica (fuente: ``config.WEIGHTS``).

    Returns:
        DataFrame conforme a ``ranking_schema``: una fila por mercado con las
        métricas crudas, el RCA de contexto y el score, ordenado por score
        descendente.

    Raises:
        ValueError: si ``weights`` referencia métricas desconocidas o no
            contiene ningún peso positivo.
    """
    metric_values: dict[str, pd.Series] = {
        "market_size": indices.market_size(data.imports),
        "import_growth": indices.import_growth(data.imports),
        "market_share": indices.market_share(data.imports, data.bilateral),
        "share_trend": indices.market_share_trend(data.imports, data.bilateral),
        "complementarity": _complementarity_by_destination(data),
        "tariff_faced": indices.tariff_faced(data.tariffs),
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
            config.COL_RCA: data.rca,
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
