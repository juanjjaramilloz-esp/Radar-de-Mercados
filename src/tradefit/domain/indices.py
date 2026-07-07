"""Índices económicos del motor de oportunidad.

Todas las funciones son puras y determinísticas: reciben DataFrames ya
validados (ver ``contracts.py``), no hacen I/O ni tocan la red, y cada una
documenta la definición que implementa.
"""

import pandas as pd

from tradefit import config


def market_size(imports: pd.DataFrame, years: int = config.MARKET_SIZE_YEARS) -> pd.Series:
    """Tamaño del mercado importador del destino.

    Definición: promedio simple del valor anual de importaciones del producto
    en el destino (USD) sobre los últimos ``years`` años con datos para ese
    destino. Promediar una ventana reciente en lugar de tomar solo el último
    año suaviza shocks puntuales; es la noción de "demanda del mercado" usada
    en el Export Potential Indicator del ITC (Decreux & Spies, 2016), que
    también parte de promedios de importaciones recientes.

    Args:
        imports: DataFrame validado contra ``imports_schema``
            (país destino, año, importaciones en USD).
        years: tamaño de la ventana de años recientes
            (por defecto ``config.MARKET_SIZE_YEARS``).

    Returns:
        Series indexada por país destino (ISO3) con el tamaño de mercado en
        USD, nombrada ``config.COL_MARKET_SIZE``.

    Raises:
        ValueError: si ``years`` no es al menos 1.
    """
    if years < 1:
        raise ValueError(f"years debe ser >= 1; recibido: {years}")
    recent = imports.sort_values(config.COL_YEAR).groupby(config.COL_COUNTRY).tail(years)
    sizes = recent.groupby(config.COL_COUNTRY)[config.COL_IMPORTS_USD].mean()
    return sizes.rename(config.COL_MARKET_SIZE)


def import_growth(imports: pd.DataFrame, years: int = config.MARKET_SIZE_YEARS) -> pd.Series:
    """Crecimiento de las importaciones del destino (CAGR de la ventana).

    Definición: tasa de crecimiento anual compuesta (CAGR) entre el primer y
    el último año con datos dentro de la ventana de ``years`` años:
    ``(V_final / V_inicial)^(1/n) − 1``, con ``n`` = años transcurridos.
    Es la medida estándar de dinámica de demanda (cf. ITC Trade Map, que
    reporta el crecimiento anual compuesto de las importaciones).

    Args:
        imports: DataFrame validado contra ``imports_schema``.
        years: tamaño de la ventana de años recientes.

    Returns:
        Series indexada por país (ISO3) con el CAGR en fracción (0.12 = 12%
        anual), nombrada ``config.COL_GROWTH``. NaN si el país tiene un solo
        año de datos o valor inicial no positivo.
    """
    if years < 2:
        raise ValueError(f"years debe ser >= 2 para calcular crecimiento; recibido: {years}")
    recent = imports.sort_values(config.COL_YEAR).groupby(config.COL_COUNTRY).tail(years)
    grouped = recent.sort_values(config.COL_YEAR).groupby(config.COL_COUNTRY)
    first_value = grouped[config.COL_IMPORTS_USD].first()
    last_value = grouped[config.COL_IMPORTS_USD].last()
    span = grouped[config.COL_YEAR].last() - grouped[config.COL_YEAR].first()
    # span=0 (un solo año) o base no positiva → NaN, que el scoring trata
    # como ausencia de evidencia (normaliza a 0).
    valid_span = span.where(span > 0)
    ratio = (last_value / first_value).where(first_value > 0)
    growth = ratio.pow(1.0 / valid_span) - 1.0
    # pow(1.0, NaN) devuelve 1.0 (IEEE 754): enmascarar explícitamente los
    # países sin ventana válida para que queden en NaN y no en crecimiento 0.
    growth = growth.where(valid_span.notna())
    return growth.rename(config.COL_GROWTH)


def _share_by_year(imports: pd.DataFrame, bilateral: pd.DataFrame) -> pd.DataFrame:
    """Cuota del origen por (país, año): bilateral / total; sin flujo = 0."""
    merged = imports.merge(bilateral, on=[config.COL_COUNTRY, config.COL_YEAR], how="left")
    merged[config.COL_IMPORTS_FROM_ORIGIN] = merged[config.COL_IMPORTS_FROM_ORIGIN].fillna(0.0)
    merged[config.COL_SHARE] = (
        merged[config.COL_IMPORTS_FROM_ORIGIN] / merged[config.COL_IMPORTS_USD]
    )
    return merged


def market_share(imports: pd.DataFrame, bilateral: pd.DataFrame) -> pd.Series:
    """Cuota de mercado del origen en el destino (último año con datos).

    Definición: participación del origen en las importaciones del producto
    del destino, ``M_d←o / M_d`` (import market share; cf. WITS "partner
    share"). Un destino sin flujo bilateral registrado tiene cuota 0.

    Args:
        imports: DataFrame validado contra ``imports_schema``.
        bilateral: DataFrame validado contra ``bilateral_schema``.

    Returns:
        Series indexada por país (ISO3) con la cuota en fracción [0, 1],
        nombrada ``config.COL_SHARE``.
    """
    shares = _share_by_year(imports, bilateral).sort_values(config.COL_YEAR)
    return shares.groupby(config.COL_COUNTRY)[config.COL_SHARE].last().rename(config.COL_SHARE)


def market_share_trend(
    imports: pd.DataFrame, bilateral: pd.DataFrame, years: int = config.MARKET_SIZE_YEARS
) -> pd.Series:
    """Tendencia de la cuota del origen: Δ cuota dentro de la ventana.

    Definición: diferencia simple entre la cuota del último y del primer año
    de la ventana, en puntos de participación (fracción): ``s_final −
    s_inicial``. Positiva = el origen está ganando terreno en ese destino.

    Args:
        imports: DataFrame validado contra ``imports_schema``.
        bilateral: DataFrame validado contra ``bilateral_schema``.
        years: tamaño de la ventana de años recientes.

    Returns:
        Series indexada por país (ISO3) con el Δ de cuota en fracción
        (0.02 = +2 puntos porcentuales), nombrada ``config.COL_SHARE_TREND``.
    """
    if years < 2:
        raise ValueError(f"years debe ser >= 2 para calcular tendencia; recibido: {years}")
    shares = _share_by_year(imports, bilateral).sort_values(config.COL_YEAR)
    recent = shares.groupby(config.COL_COUNTRY).tail(years).sort_values(config.COL_YEAR)
    grouped = recent.groupby(config.COL_COUNTRY)[config.COL_SHARE]
    trend = grouped.last() - grouped.first()
    return trend.rename(config.COL_SHARE_TREND)


def tariff_faced(tariffs: pd.DataFrame) -> pd.Series:
    """Arancel efectivamente aplicado que enfrenta el origen en cada destino.

    Definición: el "effectively applied tariff" (AHS) de WITS — para cada
    línea, el menor arancel disponible: el preferencial si existe un acuerdo
    con el origen, el MFN en caso contrario (cf. WITS Glossary, World Bank).
    A nivel de partida se agrega como promedio simple de las subpartidas HS6,
    la convención de agregación "simple average" de WITS.

    De cada serie (destino, subpartida, tipo) se toma el último año
    disponible: los preferenciales se publican con más rezago que el MFN y
    las preferencias de un acuerdo vigente persisten entre años, así que
    comparar el último MFN con el último preferencial (aunque sean de años
    distintos) es la lectura razonable del arancel vigente.

    Args:
        tariffs: DataFrame validado contra ``tariffs_schema`` (tasas en %,
            tipos MFN/PREF). La ausencia de un destino significa "sin dato".

    Returns:
        Series indexada por país destino (ISO3) con el arancel en fracción
        (0.085 = 8,5 %), nombrada ``config.COL_TARIFF``. Los destinos sin
        filas no aparecen (el scoring los trata como sin evidencia).
    """
    if tariffs.empty:
        return pd.Series(dtype=float, name=config.COL_TARIFF)
    latest = (
        tariffs.sort_values(config.COL_YEAR)
        .groupby([config.COL_COUNTRY, config.COL_CMD, config.COL_TARIFF_TYPE])[config.COL_RATE_PCT]
        .last()
    )
    effective = latest.groupby([config.COL_COUNTRY, config.COL_CMD]).min()
    per_country = effective.groupby(config.COL_COUNTRY).mean() / 100.0
    return per_country.rename(config.COL_TARIFF)


def rca_balassa(
    product_exports_origin: float,
    total_exports_origin: float,
    product_exports_world: float,
    total_exports_world: float,
) -> float:
    """Ventaja comparativa revelada del origen en el producto (RCA).

    Definición (Balassa, 1965, "Trade Liberalisation and 'Revealed'
    Comparative Advantage"): ``RCA = (X_ok / X_o) / (X_wk / X_w)`` — la
    participación del producto k en las exportaciones del origen, relativa a
    la participación de k en las exportaciones mundiales. RCA > 1 revela
    ventaja comparativa.

    Args:
        product_exports_origin: exportaciones del origen del producto (USD).
        total_exports_origin: exportaciones totales del origen (USD).
        product_exports_world: exportaciones mundiales del producto (USD).
        total_exports_world: exportaciones mundiales totales (USD).

    Returns:
        RCA (adimensional, >= 0).

    Raises:
        ValueError: si algún denominador o el numerador mundial no es positivo.
    """
    if min(total_exports_origin, product_exports_world, total_exports_world) <= 0:
        raise ValueError("Los totales y el numerador mundial deben ser positivos")
    if product_exports_origin < 0:
        raise ValueError("Las exportaciones del producto no pueden ser negativas")
    origin_share = product_exports_origin / total_exports_origin
    world_share = product_exports_world / total_exports_world
    return origin_share / world_share


def complementarity(origin_basket: pd.Series, destination_basket: pd.Series) -> float:
    """Complementariedad comercial entre la oferta del origen y la demanda del destino.

    Definición (índice de complementariedad de Michaely, 1996; usado por el
    Banco Mundial en WITS como "Trade Complementarity Index", allí escalado a
    0–100): ``C_od = 1 − Σ_k |m_dk − x_ok| / 2``, donde ``x_ok`` es la
    participación del producto k en las exportaciones del origen y ``m_dk``
    su participación en las importaciones del destino. 1 = las canastas
    encajan perfectamente; 0 = no se solapan en nada.

    Args:
        origin_basket: valores (o participaciones) exportados por el origen,
            indexados por código de producto (HS2).
        destination_basket: valores (o participaciones) importados por el
            destino, indexados por código de producto (HS2).

    Returns:
        Índice en [0, 1].

    Raises:
        ValueError: si alguna canasta suma cero.
    """
    origin_total = float(origin_basket.sum())
    destination_total = float(destination_basket.sum())
    if origin_total <= 0 or destination_total <= 0:
        raise ValueError("Las canastas deben tener valor total positivo")
    x = origin_basket / origin_total
    m = destination_basket / destination_total
    products = x.index.union(m.index)
    gap = x.reindex(products, fill_value=0.0) - m.reindex(products, fill_value=0.0)
    return float(1.0 - gap.abs().sum() / 2.0)
