"""Fuente de datos stub para la Fase 1 (cero red).

Expone la misma interfaz que tendrán las fuentes reales (función que devuelve
un DataFrame validado contra ``imports_schema``), pero lee un CSV pequeño y
explícito versionado en ``data/sample/``. En la Fase 2 se reemplaza por
Comtrade/WDI sin tocar ``domain/`` ni ``app/``.
"""

import logging

import pandas as pd

from tradefit import config
from tradefit.contracts import imports_schema

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
