"""Índices económicos del motor de oportunidad.

Todas las funciones son puras y determinísticas: reciben DataFrames ya
validados (ver ``contracts.py``), no hacen I/O ni tocan la red, y cada una
documenta la definición que implementa.
"""

import math

import numpy as np
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


def accessibility(
    distance_km: "pd.Series[float]",
    lpi: "pd.Series[float] | None" = None,
    distance_bounds_km: tuple[float, float] = config.ACCESSIBILITY_DISTANCE_BOUNDS_KM,
    lpi_bounds: tuple[float, float] = config.ACCESSIBILITY_LPI_BOUNDS,
) -> "pd.Series[float]":
    """Accesibilidad logística del destino: fricción gravitacional + LPI.

    Definición: promedio simple de dos subíndices en [0, 1] —

    1. **Distancia (gravedad).** En el modelo gravitacional del comercio
       (Tinbergen 1962, *Shaping the World Economy*) los flujos bilaterales
       caen con la distancia; empíricamente el efecto es log-lineal con
       elasticidad ≈ −0.9 (Disdier & Head 2008, "The Puzzling Persistence of
       the Distance Effect on Bilateral Trade", *REStat* 90(1)). El subíndice
       es una rampa lineal en **log-distancia** entre extremos físicos, no
       muestrales: ``(ln d_peor − ln d) / (ln d_peor − ln d_mejor)``,
       recortada a [0, 1] (d_peor = media circunferencia terrestre, d_mejor =
       frontera contigua efectiva; ver ``config``).
    2. **Logística (LPI).** Rampa lineal del Logistics Performance Index del
       destino (World Bank, *Connecting to Compete*; escala 1–5) sobre la
       escala completa: ``(LPI − 1) / 4``. Un destino sin LPI publicado
       recibe subíndice **neutro (0.5)**: la ausencia en la fuente no es
       evidencia de mala logística (mismo criterio que el filtro macro).

    Args:
        distance_km: distancia bilateral origen→destino en km (CEPII
            GeoDist), indexada por ISO3. NaN = sin dato → accesibilidad NaN.
        lpi: LPI del destino (1–5) indexado por ISO3; ``None`` equivale a
            "sin dato para todos" (componente neutro).
        distance_bounds_km: extremos ``(peor, mejor)`` de la rampa de
            distancia, en km.
        lpi_bounds: extremos ``(peor, mejor)`` de la rampa del LPI.

    Returns:
        Series en [0, 1] indexada como ``distance_km``, nombrada
        ``config.COL_ACCESSIBILITY``; NaN donde no hay distancia.

    Raises:
        ValueError: si algún par de extremos no define una rampa (iguales o
            distancia no positiva).
    """
    worst_km, best_km = distance_bounds_km
    if worst_km <= 0 or best_km <= 0 or worst_km == best_km:
        raise ValueError(f"Extremos de distancia inválidos: {distance_bounds_km}")
    worst_lpi, best_lpi = lpi_bounds
    if worst_lpi == best_lpi:
        raise ValueError(f"Extremos de LPI inválidos: {lpi_bounds}")

    log_worst, log_best = math.log(worst_km), math.log(best_km)
    with np.errstate(invalid="ignore"):
        log_distance = pd.Series(np.log(distance_km.to_numpy(dtype=float)), index=distance_km.index)
    distance_score = ((log_worst - log_distance) / (log_worst - log_best)).clip(0.0, 1.0)

    if lpi is None:
        lpi_aligned = pd.Series(float("nan"), index=distance_km.index)
    else:
        lpi_aligned = lpi.reindex(distance_km.index).astype(float)
    lpi_score = ((lpi_aligned - worst_lpi) / (best_lpi - worst_lpi)).clip(0.0, 1.0).fillna(0.5)

    combined = (distance_score + lpi_score) / 2.0
    # Sin distancia no hay accesibilidad que afirmar: NaN explícito (el
    # scoring lo rellena neutro), aunque el LPI exista.
    combined = combined.where(distance_score.notna())
    return combined.rename(config.COL_ACCESSIBILITY)


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


def aggregate_unit_value(values_usd: pd.Series, weights_kg: pd.Series) -> float:
    """Valor unitario agregado de un flujo comercial (USD/kg).

    Definición: el valor unitario es el cociente entre el valor comercial y
    la cantidad física del flujo — el proxy estándar de precio en las
    estadísticas de comercio cuando no hay precios observados (UN,
    *International Merchandise Trade Statistics: Concepts and Definitions
    2010*, §B.9 sobre índices de valor unitario). Sobre una ventana de
    registros se agrega como cociente de sumas, ``UV = Σ_t v_t / Σ_t q_t``
    (no como promedio de cocientes): cada registro pondera por su cantidad.

    Los registros sin peso conocido (NaN o ≤ 0) se excluyen del numerador Y
    del denominador: sumar sus valores sin sus cantidades sesgaría el UV al
    alza.

    Args:
        values_usd: valores del flujo en USD, alineados con ``weights_kg``.
        weights_kg: pesos netos en kg (NaN o ≤ 0 = cantidad no reportada).

    Returns:
        Valor unitario en USD/kg, o NaN si ningún registro trae peso válido.

    Raises:
        ValueError: si las series tienen longitudes distintas.
    """
    if len(values_usd) != len(weights_kg):
        raise ValueError(
            f"Series de distinta longitud: {len(values_usd)} valores, {len(weights_kg)} pesos"
        )
    mask = (weights_kg > 0).to_numpy()  # NaN > 0 es False: excluye sin dato
    total_weight = float(weights_kg.to_numpy()[mask].sum())
    if total_weight <= 0:
        return float("nan")
    return float(values_usd.to_numpy()[mask].sum() / total_weight)


def unit_value_premium(uv_origin: float, uv_market: float) -> float:
    """Premium (o descuento) del valor unitario del origen frente al destino.

    Definición: valor unitario relativo, ``premium = UV_origen / UV_destino
    − 1``. Los valores unitarios relativos se usan como señal de
    posicionamiento de precio/calidad dentro de un producto (cf. Hummels &
    Klenow 2005, "The Variety and Quality of a Nation's Exports", *AER*
    95(3), que miden calidad vía precios/valores unitarios de exportación).
    > 0: el origen vende por encima del precio implícito promedio del
    destino (posicionamiento premium); < 0: por debajo (commodity/precio).

    Args:
        uv_origin: valor unitario del flujo origen→destino (USD/kg).
        uv_market: valor unitario promedio de las importaciones del destino.

    Returns:
        Premium en fracción (0.25 = +25 %), o NaN si algún UV no es
        positivo o es NaN (sin evidencia no hay premium que afirmar).
    """
    if not uv_origin > 0 or not uv_market > 0:  # NaN falla ambas comparaciones
        return float("nan")
    return uv_origin / uv_market - 1.0


def destination_shares(exports_by_destination: pd.Series) -> pd.Series:
    """Cuota de cada destino en las exportaciones del origen del producto.

    Definición: ``s_i = x_i / Σ_j x_j``, con ``x_i`` el valor exportado al
    destino i (cf. WITS *market share*, aplicado a los destinos del origen).

    Args:
        exports_by_destination: valor exportado por destino, indexado por
            país (ISO3 o código).

    Returns:
        Series de cuotas en [0, 1] que suman 1, con el índice de entrada.

    Raises:
        ValueError: si hay valores negativos o el total no es positivo.
    """
    if (exports_by_destination < 0).any():
        raise ValueError("Las exportaciones por destino no pueden ser negativas")
    total = float(exports_by_destination.sum())
    if total <= 0:
        raise ValueError("Las exportaciones por destino deben sumar un total positivo")
    shares: pd.Series = exports_by_destination / total
    return shares


def destination_concentration(exports_by_destination: pd.Series) -> float:
    """Concentración de los destinos de exportación del producto (HHI).

    Definición (índice de Herfindahl–Hirschman; Hirschman 1964, "The
    Paternity of an Index", *AER* 54(5)): ``HHI = Σ_i s_i²`` con ``s_i`` la
    cuota del destino i. Rango (0, 1]: ``1/n`` con n destinos iguales, 1 con
    un solo destino. Lectura de referencia (guías de fusión DOJ/FTC 2010):
    > 0.25 altamente concentrado, 0.15–0.25 moderado.

    Args:
        exports_by_destination: valor exportado por destino, indexado por país.

    Returns:
        HHI como fracción en (0, 1].

    Raises:
        ValueError: si hay valores negativos o el total no es positivo.
    """
    shares = destination_shares(exports_by_destination)
    return float((shares**2).sum())


#: Código del agregado World en las importaciones por proveedor (Comtrade).
_PARTNER_WORLD = "0"


def supplier_shares(imports_by_partner: pd.DataFrame) -> pd.DataFrame:
    """Cuota y posición de cada proveedor en las importaciones del destino.

    Definición: ``s_p = m_p / M_d`` — cuota del proveedor p en las
    importaciones del producto del destino d (cf. WITS *partner share*).
    El denominador ``M_d`` es el agregado World que reporta el propio
    destino si está presente (partner "0"); si no, la suma de los
    proveedores individuales. Para cada destino se usa **el último año con
    dato** (los reporters publican con rezago distinto), y los proveedores
    se rankean por valor descendente (1 = mayor proveedor; empates por
    código de partner para que el resultado sea determinístico).

    Args:
        imports_by_partner: DataFrame conforme a
            ``contracts.competitor_imports_schema`` (columnas: destino,
            código y nombre del proveedor, año, valor; puede incluir el
            agregado World).

    Returns:
        DataFrame con una fila por (destino, proveedor individual) del
        último año con dato del destino, columnas de entrada + ``supplier_share``
        y ``supplier_rank``, ordenado por destino y rank. Vacío si la
        entrada está vacía.

    Raises:
        ValueError: si algún valor no es positivo (el contrato de entrada
            exige > 0).
    """
    if imports_by_partner.empty:
        return imports_by_partner.assign(
            **{config.COL_SUPPLIER_SHARE: [], config.COL_SUPPLIER_RANK: []}
        )
    if (imports_by_partner[config.COL_VALUE] <= 0).any():
        raise ValueError("Las importaciones por proveedor deben ser positivas")
    latest_year = imports_by_partner.groupby(config.COL_COUNTRY)[config.COL_YEAR].transform("max")
    latest = imports_by_partner[imports_by_partner[config.COL_YEAR] == latest_year]
    is_world = latest[config.COL_PARTNER_CODE] == _PARTNER_WORLD
    partners = latest[~is_world].copy()
    if partners.empty:
        return partners.assign(**{config.COL_SUPPLIER_SHARE: [], config.COL_SUPPLIER_RANK: []})
    world_totals = latest[is_world].set_index(config.COL_COUNTRY)[config.COL_VALUE]
    partner_sums = partners.groupby(config.COL_COUNTRY)[config.COL_VALUE].transform("sum")
    denominators = partners[config.COL_COUNTRY].map(world_totals).fillna(partner_sums).to_numpy()
    partners[config.COL_SUPPLIER_SHARE] = (partners[config.COL_VALUE] / denominators).clip(
        upper=1.0
    )
    partners = partners.sort_values(
        [config.COL_COUNTRY, config.COL_VALUE, config.COL_PARTNER_CODE],
        ascending=[True, False, True],
        ignore_index=True,
    )
    partners[config.COL_SUPPLIER_RANK] = partners.groupby(config.COL_COUNTRY).cumcount() + 1
    return partners
