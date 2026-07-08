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

#: Aranceles TRAINS por destino y subpartida HS6: promedio simple de las
#: líneas ad-valorem en % (tal como lo reporta WITS), tipo MFN (erga omnes) o
#: PREF (preferencial hacia el origen). Solo años con dato: un destino o
#: subpartida ausente se maneja en domain (MFN faltante → arancel NaN).
tariffs_schema = pa.DataFrameSchema(
    {
        config.COL_COUNTRY: pa.Column(str, pa.Check.str_length(3, 3)),
        config.COL_CMD: pa.Column(str, pa.Check.str_length(6, 6)),
        config.COL_TARIFF_TYPE: pa.Column(str, pa.Check.isin(["MFN", "PREF"])),
        config.COL_YEAR: pa.Column(int, pa.Check.in_range(1990, 2100)),
        config.COL_RATE_PCT: pa.Column(float, pa.Check.ge(0)),
    },
    unique=[config.COL_COUNTRY, config.COL_CMD, config.COL_TARIFF_TYPE, config.COL_YEAR],
    coerce=True,
    strict=True,
    name="tariffs",
)

#: Indicadores macro WDI por destino y año (solo años con dato: los null de
#: la API se descartan en ingest; la ausencia se maneja en domain).
macro_schema = pa.DataFrameSchema(
    {
        config.COL_COUNTRY: pa.Column(str, pa.Check.str_length(3, 3)),
        config.COL_INDICATOR: pa.Column(str, pa.Check.isin(list(config.WDI_INDICATORS.values()))),
        config.COL_YEAR: pa.Column(int, pa.Check.in_range(1990, 2100)),
        config.COL_MACRO_VALUE: pa.Column(float),
    },
    unique=[config.COL_COUNTRY, config.COL_INDICATOR, config.COL_YEAR],
    coerce=True,
    strict=True,
    name="macro",
)

#: Ranking de mercados destino (el snapshot que consume la app). El orden lo
#: define ``final_score`` (oportunidad × penalización de estabilidad macro);
#: ``opportunity_score`` queda como score bruto para poder compararlos.
ranking_schema = pa.DataFrameSchema(
    {
        config.COL_RANK: pa.Column(int, pa.Check.ge(1)),
        config.COL_COUNTRY: pa.Column(str, pa.Check.str_length(3, 3)),
        config.COL_COUNTRY_NAME: pa.Column(str),
        config.COL_MARKET_SIZE: pa.Column(float, pa.Check.ge(0)),
        config.COL_GROWTH: pa.Column(float, pa.Check.in_range(-1.0, 10.0), nullable=True),
        config.COL_SHARE: pa.Column(float, pa.Check.in_range(0.0, 1.0)),
        config.COL_SHARE_TREND: pa.Column(float, pa.Check.in_range(-1.0, 1.0)),
        # Cuota del destino en las exportaciones del origen del producto
        # (contexto, no pondera). NaN = fuente stub o el origen no reporta
        # exportaciones del producto. required=False: la inserta el pipeline
        # al armar el snapshot (rank_markets no la conoce) y los snapshots
        # anteriores a 2026-07-08 no la traen.
        config.COL_ORIGIN_EXPORT_SHARE: pa.Column(
            float, pa.Check.in_range(0.0, 1.0), nullable=True, required=False
        ),
        config.COL_COMPLEMENTARITY: pa.Column(float, pa.Check.in_range(0.0, 1.0)),
        # Arancel efectivamente aplicado que enfrenta el origen (fracción;
        # 0.085 = 8,5 %). NaN = destino sin datos en WITS (no se penaliza).
        config.COL_TARIFF: pa.Column(float, pa.Check.ge(0), nullable=True),
        config.COL_RCA: pa.Column(float, pa.Check.ge(0)),
        config.COL_STABILITY: pa.Column(float, pa.Check.in_range(0.0, 1.0)),
        config.COL_SCORE: pa.Column(float, pa.Check.in_range(0.0, 1.0)),
        config.COL_FINAL_SCORE: pa.Column(float, pa.Check.in_range(0.0, 1.0)),
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
        tariffs: aranceles MFN y preferenciales que enfrenta el origen,
            conforme a ``tariffs_schema`` (ausencia = sin dato, no arancel 0).
        rca: RCA de Balassa del origen en el producto (escalar, contexto).
    """

    imports: pd.DataFrame
    bilateral: pd.DataFrame
    baskets: pd.DataFrame
    tariffs: pd.DataFrame
    rca: float
