"""Fixtures compartidos. Los tests NUNCA tocan la red."""

from pathlib import Path

import pandas as pd
import pytest

from tradefit import config
from tradefit.contracts import MarketInputs, basket_schema, bilateral_schema, imports_schema

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def imports_small() -> pd.DataFrame:
    """Importaciones de juguete: 3 países, números redondos (cálculo a mano).

    USA: 2021=999 (fuera de la ventana de 3 años), 2022=100, 2023=200, 2024=300
    DEU: 2022=40, 2023=50, 2024=60
    JPN: 2022=10, 2023=10, 2024=10
    """
    raw = pd.read_csv(FIXTURES_DIR / "imports_small.csv")
    validated: pd.DataFrame = imports_schema.validate(raw)
    return validated


@pytest.fixture()
def bilateral_small() -> pd.DataFrame:
    """Flujo bilateral de juguete (desde el origen), calculable a mano.

    USA: 2022=10, 2023=30, 2024=60 → cuotas 0.10, 0.15, 0.20
    DEU: 2022=20, (2023 ausente = flujo 0), 2024=15 → cuotas 0.50, 0.00, 0.25
    JPN: sin filas → cuota 0 en todos los años
    """
    raw = pd.read_csv(FIXTURES_DIR / "bilateral_small.csv")
    validated: pd.DataFrame = bilateral_schema.validate(raw)
    return validated


@pytest.fixture()
def baskets_small() -> pd.DataFrame:
    """Canastas HS2 de juguete, calculables a mano.

    COL exporta: 09=90, 27=10 → participaciones (0.9, 0.1)
    USA importa: 09=50, 27=50 → C = 1 − (0.4 + 0.4)/2 = 0.6
    DEU importa: 09=90, 27=10 → C = 1.0 (encaje perfecto)
    JPN importa: 84=100      → C = 0.0 (canastas disjuntas)
    """
    raw = pd.read_csv(FIXTURES_DIR / "baskets_small.csv", dtype={config.COL_CMD: str})
    validated: pd.DataFrame = basket_schema.validate(raw)
    return validated


@pytest.fixture()
def market_inputs_small(
    imports_small: pd.DataFrame,
    bilateral_small: pd.DataFrame,
    baskets_small: pd.DataFrame,
) -> MarketInputs:
    """Insumos completos de juguete para el ranking (RCA de contexto = 9.0)."""
    return MarketInputs(
        imports=imports_small,
        bilateral=bilateral_small,
        baskets=baskets_small,
        rca=9.0,
    )
