"""Fuente de datos stub (cero red).

Expone la misma interfaz que las fuentes reales (funciones que devuelven
DataFrames validados contra los esquemas de ``contracts``), pero lee CSVs
pequeños y explícitos versionados en ``data/sample/``. Sirve de fallback sin
red y de dato de demostración; se intercambia por Comtrade sin tocar
``domain/`` ni ``app/``.
"""

import logging

import pandas as pd

from tradefit import config
from tradefit.contracts import (
    basket_schema,
    bilateral_schema,
    export_totals_schema,
    imports_schema,
    macro_schema,
    tariffs_schema,
)

logger = logging.getLogger(__name__)


def load_stub_imports() -> pd.DataFrame:
    """Carga las importaciones stub del producto en los mercados destino.

    Returns:
        DataFrame validado contra ``imports_schema``: una fila por
        (país destino, año) con las importaciones del producto en USD.

    Raises:
        FileNotFoundError: si falta ``data/sample/stub_imports.csv``.
        pandera.errors.SchemaError: si el CSV no cumple el contrato.
    """
    logger.info("Leyendo stub de importaciones desde %s", config.STUB_IMPORTS_CSV)
    raw = pd.read_csv(config.STUB_IMPORTS_CSV)
    validated: pd.DataFrame = imports_schema.validate(raw)
    return validated


def load_stub_bilateral() -> pd.DataFrame:
    """Carga las importaciones stub desde el origen (flujo bilateral).

    Returns:
        DataFrame validado contra ``bilateral_schema``; los (país, año)
        ausentes significan flujo cero.
    """
    logger.info("Leyendo stub bilateral desde %s", config.STUB_BILATERAL_CSV)
    raw = pd.read_csv(config.STUB_BILATERAL_CSV)
    validated: pd.DataFrame = bilateral_schema.validate(raw)
    return validated


def load_stub_baskets() -> pd.DataFrame:
    """Carga las canastas HS2 stub del origen y los destinos.

    Returns:
        DataFrame validado contra ``basket_schema``.
    """
    logger.info("Leyendo stub de canastas desde %s", config.STUB_BASKETS_CSV)
    # dtype=str preserva el cero inicial de capítulos como "09".
    raw = pd.read_csv(config.STUB_BASKETS_CSV, dtype={config.COL_CMD: str})
    validated: pd.DataFrame = basket_schema.validate(raw)
    return validated


def load_stub_macro() -> pd.DataFrame:
    """Carga los indicadores macro stub de los destinos.

    Returns:
        DataFrame validado contra ``macro_schema``.
    """
    logger.info("Leyendo stub macro desde %s", config.STUB_MACRO_CSV)
    raw = pd.read_csv(config.STUB_MACRO_CSV)
    validated: pd.DataFrame = macro_schema.validate(raw)
    return validated


def load_stub_tariffs() -> pd.DataFrame:
    """Carga los aranceles stub que enfrenta el origen en los destinos.

    Los destinos ausentes del CSV quedan sin dato a propósito: ejercitan el
    camino "sin arancel publicado" (NaN neutro en el scoring).

    Returns:
        DataFrame validado contra ``tariffs_schema``.
    """
    logger.info("Leyendo stub de aranceles desde %s", config.STUB_TARIFFS_CSV)
    # dtype=str preserva el cero inicial de subpartidas como "090111".
    raw = pd.read_csv(config.STUB_TARIFFS_CSV, dtype={config.COL_CMD: str})
    validated: pd.DataFrame = tariffs_schema.validate(raw)
    return validated


def load_stub_export_totals() -> pd.DataFrame:
    """Carga los totales de exportación stub (origen y mundo) para el RCA.

    Returns:
        DataFrame validado contra ``export_totals_schema``.
    """
    logger.info("Leyendo stub de totales de exportación desde %s", config.STUB_EXPORT_TOTALS_CSV)
    raw = pd.read_csv(config.STUB_EXPORT_TOTALS_CSV)
    validated: pd.DataFrame = export_totals_schema.validate(raw)
    return validated
