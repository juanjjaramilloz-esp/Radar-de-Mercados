"""Fixtures compartidos. Los tests NUNCA tocan la red."""

from pathlib import Path

import pandas as pd
import pytest

from tradefit.contracts import imports_schema

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
