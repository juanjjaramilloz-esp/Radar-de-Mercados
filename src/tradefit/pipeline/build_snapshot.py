"""Construye el snapshot que consume la app.

Orquesta: ingest (stub en Fase 1) → domain (scoring) → validación de contrato
→ escritura en ``data/processed/`` (``ranking.parquet`` + ``meta.json``).
Idempotente: con el mismo input produce el mismo snapshot (no escribe
timestamps ni ningún otro valor no determinístico).
"""

import argparse
import json
import logging

import pandas as pd
from dotenv import load_dotenv

from tradefit import config
from tradefit.contracts import ranking_schema
from tradefit.domain.scoring import rank_markets
from tradefit.ingest.comtrade import load_comtrade_imports
from tradefit.ingest.stub import load_stub_imports

logger = logging.getLogger(__name__)

SOURCES = ("comtrade", "stub")


def build_snapshot(source: str = "comtrade") -> pd.DataFrame:
    """Construye y escribe el snapshot; devuelve el ranking escrito.

    Args:
        source: fuente de importaciones — ``"comtrade"`` (real, con caché en
            ``data/raw/``) o ``"stub"`` (CSV local, sin red).

    Returns:
        DataFrame conforme a ``ranking_schema``, ya persistido en
        ``data/processed/ranking.parquet``.

    Raises:
        ValueError: si ``source`` no es una fuente conocida.
    """
    if source not in SOURCES:
        raise ValueError(f"Fuente desconocida: {source!r}; opciones: {SOURCES}")
    imports = load_comtrade_imports() if source == "comtrade" else load_stub_imports()
    logger.info(
        "Importaciones cargadas: %d filas, %d mercados",
        len(imports),
        imports[config.COL_COUNTRY].nunique(),
    )

    ranking = rank_markets(imports, config.WEIGHTS)
    validated: pd.DataFrame = ranking_schema.validate(ranking)

    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    validated.to_parquet(config.RANKING_PARQUET, index=False)

    meta = {
        "hs_code": config.HS_CODE,
        "hs_label": config.HS_LABEL,
        "origin_iso3": config.ORIGIN_ISO3,
        "source": source,
        "market_size_years": config.MARKET_SIZE_YEARS,
        "data_year_min": int(imports[config.COL_YEAR].min()),
        "data_year_max": int(imports[config.COL_YEAR].max()),
        "n_markets": int(len(validated)),
        "weights": dict(config.WEIGHTS),
    }
    config.SNAPSHOT_META_JSON.write_text(
        json.dumps(meta, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("Snapshot escrito en %s (%d mercados)", config.PROCESSED_DIR, len(validated))
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
    args = parser.parse_args()
    build_snapshot(source=args.source)
