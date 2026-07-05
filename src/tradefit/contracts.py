"""Contratos de datos entre capas (esquemas pandera + insumos del ranking).

Todo DataFrame que cruza una frontera de capa (ingest → domain → snapshot →
app) se valida contra uno de estos esquemas: si una fuente cambia su formato,
el pipeline falla aquí, temprano y con un mensaje claro.
"""

from dataclasses import dataclass

import pandas as pd
import pandera.pandas as pa

from tradefit import config

#: Importaciones anuales del producto por mercado destino (entrada de domain/).
imports_schema = pa.DataFrameSchema(
    {
        config.COL_COUNTRY: pa.Column(str, pa.Check.str_length(3, 3)),
        config.COL_COUNTRY_NAME: pa.Column(str),
        config.COL_YEAR: pa.Column(int, pa.Check.in_range(1990, 2100)),
        config.COL_IMPORTS_USD: pa.Column(float, pa.Check.ge(0)),
    },
    unique=[config.COL_COUNTRY, config.COL_YEAR],
    coerce=True,
    strict=True,
    name="imports",
)

#: Importaciones anuales del producto en el destino DESDE el origen (bilateral).
#: Puede no traer todos los (país, año): la ausencia significa flujo cero.
bilateral_schema = pa.DataFrameSchema(
    {
        config.COL_COUNTRY: pa.Column(str, pa.Check.str_length(3, 3)),
        config.COL_YEAR: pa.Column(int, pa.Check.in_range(1990, 2100)),
        config.COL_IMPORTS_FROM_ORIGIN: pa.Column(float, pa.Check.ge(0)),
    },
    unique=[config.COL_COUNTRY, config.COL_YEAR],
    coerce=True,
    strict=True,
    name="bilateral",
)

#: Canastas comerciales a nivel HS2 (exportadora del origen, importadora de
#: cada destino) para el índice de complementariedad. Un año (BASKET_YEAR).
basket_schema = pa.DataFrameSchema(
    {
        config.COL_COUNTRY: pa.Column(str, pa.Check.str_length(3, 3)),
        config.COL_CMD: pa.Column(str, pa.Check.str_length(2, 2)),
        config.COL_VALUE: pa.Column(float, pa.Check.ge(0)),
    },
    unique=[config.COL_COUNTRY, config.COL_CMD],
    coerce=True,
    strict=True,
    name="baskets",
)

#: Totales de exportación (origen y mundo; producto y total) para el RCA.
export_totals_schema = pa.DataFrameSchema(
    {
        config.COL_SCOPE: pa.Column(str, pa.Check.isin(["origin", "world"])),
        config.COL_CMD: pa.Column(str, pa.Check.isin(["product", "total"])),
        config.COL_YEAR: pa.Column(int, pa.Check.in_range(1990, 2100)),
        config.COL_VALUE: pa.Column(float, pa.Check.ge(0)),
    },
    unique=[config.COL_SCOPE, config.COL_CMD, config.COL_YEAR],
    coerce=True,
    strict=True,
    name="export_totals",
)

#: Ranking de mercados destino (el snapshot que consume la app).
ranking_schema = pa.DataFrameSchema(
    {
        config.COL_RANK: pa.Column(int, pa.Check.ge(1)),
        config.COL_COUNTRY: pa.Column(str, pa.Check.str_length(3, 3)),
        config.COL_COUNTRY_NAME: pa.Column(str),
        config.COL_MARKET_SIZE: pa.Column(float, pa.Check.ge(0)),
        config.COL_GROWTH: pa.Column(float, pa.Check.in_range(-1.0, 10.0), nullable=True),
        config.COL_SHARE: pa.Column(float, pa.Check.in_range(0.0, 1.0)),
        config.COL_SHARE_TREND: pa.Column(float, pa.Check.in_range(-1.0, 1.0)),
        config.COL_COMPLEMENTARITY: pa.Column(float, pa.Check.in_range(0.0, 1.0)),
        config.COL_RCA: pa.Column(float, pa.Check.ge(0)),
        config.COL_SCORE: pa.Column(float, pa.Check.in_range(0.0, 1.0)),
    },
    unique=[config.COL_COUNTRY],
    coerce=True,
    strict=True,
    name="ranking",
)


@dataclass(frozen=True)
class MarketInputs:
    """Insumos del ranking: el contrato entre ingest/pipeline y domain.

    Attributes:
        imports: importaciones totales del producto por destino y año,
            conforme a ``imports_schema``.
        bilateral: importaciones del producto desde el origen por destino y
            año, conforme a ``bilateral_schema`` (ausencia = flujo cero).
        baskets: canastas HS2 (origen exporta, destinos importan) conforme a
            ``basket_schema``; incluye la fila del origen.
        rca: RCA de Balassa del origen en el producto (escalar, contexto).
    """

    imports: pd.DataFrame
    bilateral: pd.DataFrame
    baskets: pd.DataFrame
    rca: float
