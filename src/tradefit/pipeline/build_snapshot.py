"""Construye el snapshot que consume la app.

Orquesta: ingest (Comtrade o stub) → domain (índices + scoring) → validación
de contrato → escritura en ``data/processed/`` (``ranking.parquet`` +
``meta.json``). Idempotente: con el mismo input produce el mismo snapshot (no
escribe timestamps ni ningún otro valor no determinístico).
"""

import argparse
import json
import logging

import pandas as pd
from dotenv import load_dotenv

from tradefit import config
from tradefit.contracts import MarketInputs, ranking_schema
from tradefit.domain import indices
from tradefit.domain.macro_filter import apply_stability_penalty, stability_score
from tradefit.domain.narrative import build_narrative
from tradefit.domain.scoring import rank_markets
from tradefit.ingest import comtrade, stub, worldbank

logger = logging.getLogger(__name__)

SOURCES = ("comtrade", "stub")


def _rca_from_totals(export_totals: pd.DataFrame) -> float:
    """RCA del origen usando el año más reciente con las cuatro series.

    Args:
        export_totals: DataFrame validado contra ``export_totals_schema``.

    Returns:
        RCA de Balassa (escalar) calculado por ``domain.indices.rca_balassa``.

    Raises:
        RuntimeError: si ningún año trae las cuatro series completas.
    """
    pivot = export_totals.pivot_table(
        index=config.COL_YEAR,
        columns=[config.COL_SCOPE, config.COL_CMD],
        values=config.COL_VALUE,
    )
    complete = pivot.dropna()
    if complete.empty:
        raise RuntimeError("Ningún año tiene las cuatro series de exportación para el RCA")
    year = int(complete.index.max())
    row = complete.loc[year]
    logger.info("RCA calculado con datos de exportación de %d", year)
    return indices.rca_balassa(
        product_exports_origin=float(row[("origin", "product")]),
        total_exports_origin=float(row[("origin", "total")]),
        product_exports_world=float(row[("world", "product")]),
        total_exports_world=float(row[("world", "total")]),
    )


def _load_inputs(source: str, hs: str) -> tuple[MarketInputs, pd.DataFrame]:
    """Carga y valida los insumos del ranking + macro desde la fuente elegida.

    El macro real viene de WDI (sin key) aunque el comercio venga de Comtrade;
    con ``source="stub"`` todo sale de ``data/sample/`` (cero red).
    """
    if source == "comtrade":
        imports = comtrade.load_comtrade_imports(hs)
        bilateral = comtrade.load_bilateral_imports(hs)
        baskets = comtrade.load_baskets()
        export_totals = comtrade.load_export_totals(hs)
        macro = worldbank.load_wdi_macro()
    else:
        imports = stub.load_stub_imports()
        bilateral = stub.load_stub_bilateral()
        baskets = stub.load_stub_baskets()
        export_totals = stub.load_stub_export_totals()
        macro = stub.load_stub_macro()
    data = MarketInputs(
        imports=imports,
        bilateral=bilateral,
        baskets=baskets,
        rca=_rca_from_totals(export_totals),
    )
    return data, macro


def build_snapshot(source: str = "comtrade", hs: str = config.HS_CODE) -> pd.DataFrame:
    """Construye y escribe el snapshot de un producto; devuelve el ranking.

    Args:
        source: fuente de datos — ``"comtrade"`` (real, con caché en
            ``data/raw/``) o ``"stub"`` (CSVs locales, sin red; solo soporta
            el producto por defecto).
        hs: código HS del producto (debe estar en ``config.PRODUCTS``).

    Returns:
        DataFrame conforme a ``ranking_schema``, ya persistido en
        ``data/processed/<hs>/ranking.parquet``.

    Raises:
        ValueError: si ``source`` o ``hs`` no son conocidos, o si se pide el
            stub para un producto distinto del por defecto.
    """
    if source not in SOURCES:
        raise ValueError(f"Fuente desconocida: {source!r}; opciones: {SOURCES}")
    if hs not in config.PRODUCTS:
        raise ValueError(f"Producto desconocido: {hs!r}; opciones: {sorted(config.PRODUCTS)}")
    if source == "stub" and hs != config.HS_CODE:
        raise ValueError(f"El stub solo tiene datos del producto {config.HS_CODE}")
    data, macro = _load_inputs(source, hs)
    imports = data.imports
    logger.info(
        "Insumos cargados: %d filas de importaciones, %d mercados, RCA=%.2f",
        len(imports),
        imports[config.COL_COUNTRY].nunique(),
        data.rca,
    )

    ranking = rank_markets(data, config.WEIGHTS)
    stability = stability_score(macro, config.MACRO_BOUNDS)
    ranking = apply_stability_penalty(ranking, stability, config.MACRO_FLOOR)
    validated: pd.DataFrame = ranking_schema.validate(ranking)

    config.processed_dir(hs).mkdir(parents=True, exist_ok=True)
    validated.to_parquet(config.ranking_parquet(hs), index=False)

    narrative = build_narrative(validated, config.WEIGHTS)
    config.narrative_json(hs).write_text(
        json.dumps(narrative, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    meta = {
        "hs_code": hs,
        "hs_label": config.PRODUCTS[hs],
        "origin_iso3": config.ORIGIN_ISO3,
        "source": source,
        "market_size_years": config.MARKET_SIZE_YEARS,
        "basket_year": config.BASKET_YEAR,
        "data_year_min": int(imports[config.COL_YEAR].min()),
        "data_year_max": int(imports[config.COL_YEAR].max()),
        "n_markets": int(len(validated)),
        "rca_balassa": round(data.rca, 4),
        "weights": dict(config.WEIGHTS),
        "macro_indicators": dict(config.WDI_INDICATORS),
        "macro_bounds": {k: list(v) for k, v in config.MACRO_BOUNDS.items()},
        "macro_floor": config.MACRO_FLOOR,
        "macro_years": config.MACRO_YEARS,
    }
    config.snapshot_meta_json(hs).write_text(
        json.dumps(meta, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("Snapshot escrito en %s (%d mercados)", config.processed_dir(hs), len(validated))
    return validated


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    load_dotenv()
    parser = argparse.ArgumentParser(description="Construye el snapshot de TradeFit.")
    parser.add_argument(
        "--source",
        choices=SOURCES,
        default="comtrade",
        help="fuente de importaciones (default: comtrade)",
    )
    parser.add_argument(
        "--hs",
        choices=sorted(config.PRODUCTS),
        default=None,
        help="código HS del producto; sin --hs construye TODOS los de config.PRODUCTS",
    )
    args = parser.parse_args()
    if args.hs:
        products = [args.hs]
    elif args.source == "stub":
        products = [config.HS_CODE]  # el stub solo tiene datos del producto default
    else:
        products = sorted(config.PRODUCTS)
    for product in products:
        build_snapshot(source=args.source, hs=product)
