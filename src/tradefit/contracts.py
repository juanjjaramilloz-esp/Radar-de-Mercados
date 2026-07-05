"""Contratos de datos entre capas (esquemas pandera).

Todo DataFrame que cruza una frontera de capa (ingest → domain → snapshot →
app) se valida contra uno de estos esquemas: si una fuente cambia su formato,
el pipeline falla aquí, temprano y con un mensaje claro.
"""

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

#: Ranking de mercados destino (el snapshot que consume la app).
ranking_schema = pa.DataFrameSchema(
    {
        config.COL_RANK: pa.Column(int, pa.Check.ge(1)),
        config.COL_COUNTRY: pa.Column(str, pa.Check.str_length(3, 3)),
        config.COL_COUNTRY_NAME: pa.Column(str),
        config.COL_MARKET_SIZE: pa.Column(float, pa.Check.ge(0)),
        config.COL_SCORE: pa.Column(float, pa.Check.in_range(0.0, 1.0)),
    },
    unique=[config.COL_COUNTRY],
    coerce=True,
    strict=True,
    name="ranking",
)
