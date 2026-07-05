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
