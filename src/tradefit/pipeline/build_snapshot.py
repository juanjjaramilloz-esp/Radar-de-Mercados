"""Construye el snapshot que consume la app.

Orquesta: ingest (Comtrade o stub) → domain (índices + scoring) → validación
de contrato → escritura en ``data/processed/`` (``ranking.parquet`` +
``meta.json``). Idempotente: con el mismo input produce el mismo snapshot (no
escribe timestamps ni ningún otro valor no determinístico).
"""

import argparse
import json
import logging
from collections.abc import Callable

import pandas as pd
from dotenv import load_dotenv

from tradefit import config, hs_codes
from tradefit.contracts import MarketInputs, ranking_schema
from tradefit.domain import indices
from tradefit.domain.macro_filter import (
    apply_stability_penalty,
    latest_indicator_value,
    stability_score,
)
from tradefit.domain.narrative import LANGS, build_narrative
from tradefit.domain.scoring import rank_markets
from tradefit.ingest import comtrade, export_destinations, stub, wits, worldbank

logger = logging.getLogger(__name__)

SOURCES = ("comtrade", "stub")

#: Callback opcional de progreso: recibe la descripción de la etapa que inicia.
OnStage = Callable[[str], None] | None


def _notify(on_stage: OnStage, stage: str) -> None:
    """Avisa el inicio de una etapa al callback (si hay) y al log."""
    logger.info("%s", stage)
    if on_stage is not None:
        on_stage(stage)


def _rca_from_totals(export_totals: pd.DataFrame) -> float:
    """RCA del origen usando el año más reciente con las cuatro series.

    La serie ``(origin, product)`` puede faltar (total o parcialmente) si el
    origen no exporta el producto: se toma como 0 y el RCA resulta 0, que es
    el valor correcto del índice de Balassa en ese caso.

    Args:
        export_totals: DataFrame validado contra ``export_totals_schema``.

    Returns:
        RCA de Balassa (escalar) calculado por ``domain.indices.rca_balassa``.

    Raises:
        RuntimeError: si ningún año trae las tres series restantes completas.
    """
    pivot = export_totals.pivot_table(
        index=config.COL_YEAR,
        columns=[config.COL_SCOPE, config.COL_CMD],
        values=config.COL_VALUE,
    )
    origin_product = ("origin", "product")
    if origin_product not in pivot.columns:
        pivot[origin_product] = 0.0
    pivot[origin_product] = pivot[origin_product].fillna(0.0)
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


def _load_inputs(
    source: str, hs: str, on_stage: OnStage = None
) -> tuple[MarketInputs, pd.DataFrame]:
    """Carga y valida los insumos del ranking + macro desde la fuente elegida.

    El macro real viene de WDI (sin key) aunque el comercio venga de Comtrade;
    con ``source="stub"`` todo sale de ``data/sample/`` (cero red).
    """
    if source == "comtrade":
        _notify(on_stage, "Importaciones del producto por destino (UN Comtrade)")
        imports = comtrade.load_comtrade_imports(hs)
        _notify(on_stage, "Flujo bilateral desde el origen")
        bilateral = comtrade.load_bilateral_imports(hs)
        _notify(on_stage, "Canastas exportadora e importadora (complementariedad)")
        baskets = comtrade.load_baskets()
        _notify(on_stage, "Totales de exportación para el RCA")
        export_totals = comtrade.load_export_totals(hs)
        _notify(on_stage, "Aranceles que enfrenta el origen (World Bank WITS)")
        tariffs = wits.load_wits_tariffs(hs)
        _notify(on_stage, "Indicadores macro (World Bank WDI)")
        macro = worldbank.load_wdi_macro()
    else:
        _notify(on_stage, "Insumos locales de ejemplo (stub, sin red)")
        imports = stub.load_stub_imports()
        bilateral = stub.load_stub_bilateral()
        baskets = stub.load_stub_baskets()
        export_totals = stub.load_stub_export_totals()
        tariffs = stub.load_stub_tariffs()
        macro = stub.load_stub_macro()
    data = MarketInputs(
        imports=imports,
        bilateral=bilateral,
        baskets=baskets,
        tariffs=tariffs,
        rca=_rca_from_totals(export_totals),
    )
    return data, macro


def build_snapshot(
    source: str = "comtrade", hs: str = config.HS_CODE, on_stage: OnStage = None
) -> pd.DataFrame:
    """Construye y escribe el snapshot de un producto; devuelve el ranking.

    Args:
        source: fuente de datos — ``"comtrade"`` (real, con caché en
            ``data/raw/``) o ``"stub"`` (CSVs locales, sin red; solo soporta
            el producto por defecto).
        hs: partida HS del producto (2, 4 o 6 dígitos; cualquier código
            válido, no solo los curados de ``config.PRODUCTS``).
        on_stage: callback opcional de progreso; recibe la descripción de
            cada etapa cuando esta inicia (lo usa la app para pintar el
            avance — el pipeline sigue sin conocer Streamlit).

    Returns:
        DataFrame conforme a ``ranking_schema``, ya persistido en
        ``data/processed/<hs>/ranking.parquet``.

    Raises:
        ValueError: si ``source`` no es conocida, ``hs`` no tiene formato de
            partida HS, o se pide el stub para un producto distinto del
            por defecto.
    """
    if source not in SOURCES:
        raise ValueError(f"Fuente desconocida: {source!r}; opciones: {SOURCES}")
    hs = hs_codes.normalize_hs(hs)
    if not hs_codes.is_valid_hs(hs):
        raise ValueError(f"Partida HS inválida: {hs!r}; se esperan 2, 4 o 6 dígitos")
    if source == "stub" and hs != config.HS_CODE:
        raise ValueError(f"El stub solo tiene datos del producto {config.HS_CODE}")
    data, macro = _load_inputs(source, hs, on_stage)
    imports = data.imports
    logger.info(
        "Insumos cargados: %d filas de importaciones, %d mercados, RCA=%.2f",
        len(imports),
        imports[config.COL_COUNTRY].nunique(),
        data.rca,
    )

    # Concentración de destinos: exportaciones del origen a TODOS los partners
    # (no solo los del radar). Solo con fuente real; el stub no trae este dato.
    destination_hhi: float | None = None
    export_shares: pd.Series[float] | None = None
    if source == "comtrade":
        _notify(on_stage, "Destinos de exportación del origen (concentración)")
        destinations = export_destinations.load_export_destinations(hs)
        if not destinations.empty:
            exports_series = destinations.set_index(config.COL_COUNTRY)[config.COL_VALUE]
            export_shares = indices.destination_shares(exports_series)
            destination_hhi = indices.destination_concentration(exports_series)

    _notify(on_stage, "Calculando índices, estabilidad macro y ranking")
    ranking = rank_markets(data, config.WEIGHTS)
    # El caché macro también trae indicadores de contexto (LPI): al filtro
    # de estabilidad solo entran los que tienen umbrales en MACRO_BOUNDS.
    core = macro[macro[config.COL_INDICATOR].isin(config.WDI_INDICATORS.values())]
    stability = stability_score(core, config.MACRO_BOUNDS)
    ranking = apply_stability_penalty(ranking, stability, config.MACRO_FLOOR)
    share_of_origin = (
        ranking[config.COL_COUNTRY].map(export_shares).fillna(0.0)
        if export_shares is not None
        else pd.Series(float("nan"), index=ranking.index)
    )
    position = int(ranking.columns.get_indexer([config.COL_SHARE_TREND])[0]) + 1
    ranking.insert(position, config.COL_ORIGIN_EXPORT_SHARE, share_of_origin)
    # LPI del destino (contexto logístico, no pondera): último año con dato
    # por país — la publicación es esparsa. NaN si el país no tiene dato.
    lpi = latest_indicator_value(macro, config.COL_LPI)
    position = int(ranking.columns.get_indexer([config.COL_STABILITY])[0])
    ranking.insert(position, config.COL_LPI, ranking[config.COL_COUNTRY].map(lpi))
    validated: pd.DataFrame = ranking_schema.validate(ranking)

    _notify(on_stage, "Escribiendo el snapshot")
    config.processed_dir(hs).mkdir(parents=True, exist_ok=True)
    validated.to_parquet(config.ranking_parquet(hs), index=False)
    imports.to_parquet(config.imports_timeseries_parquet(hs), index=False)

    hs_label = hs_codes.hs_label(hs)
    _write_narrative(hs, validated, dict(config.WEIGHTS), config.MARKET_SIZE_YEARS, hs_label)

    meta = {
        "hs_code": hs,
        "hs_label": hs_label,
        "origin_iso3": config.ORIGIN_ISO3,
        "source": source,
        "market_size_years": config.MARKET_SIZE_YEARS,
        "basket_year": config.BASKET_YEAR,
        "data_year_min": int(imports[config.COL_YEAR].min()),
        "data_year_max": int(imports[config.COL_YEAR].max()),
        "n_markets": int(len(validated)),
        "rca_balassa": round(data.rca, 4),
        # HHI de concentración de destinos (Hirschman 1964) de las
        # exportaciones del origen del producto; None si no hay dato.
        "destination_hhi": round(destination_hhi, 4) if destination_hhi is not None else None,
        "weights": dict(config.WEIGHTS),
        "tariff_years": list(config.WITS_YEARS),
        "macro_indicators": dict(config.WDI_INDICATORS),
        # Indicadores de contexto (no ponderan): hoy solo el LPI.
        "context_indicators": dict(config.WDI_CONTEXT_INDICATORS),
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


def _write_narrative(
    hs: str,
    ranking: pd.DataFrame,
    weights: dict[str, float],
    window_years: int,
    hs_label: str,
) -> None:
    """Serializa ``narrative.json`` bilingüe: ``{"es": {...}, "en": {...}}``.

    La etiqueta del producto en inglés sale de ``config.PRODUCTS_EN`` para los
    curados; las partidas on-demand ya traen su descripción del catálogo de
    Comtrade en inglés, así que sirve para ambos idiomas.
    """
    labels = {"es": hs_label, "en": config.PRODUCTS_EN.get(hs, hs_label)}
    narrative = {
        lang: build_narrative(
            ranking,
            weights,
            window_years=window_years,
            product_label=labels[lang],
            origin_name=config.ORIGIN_NAME,
            lang=lang,
        )
        for lang in LANGS
    }
    config.narrative_json(hs).write_text(
        json.dumps(narrative, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def refresh_narrative(hs: str) -> None:
    """Reescribe solo ``narrative.json`` desde un snapshot ya construido (sin red).

    Para propagar cambios del generador de narrativa a snapshots existentes
    sin re-descargar nada: lee ``ranking.parquet`` + ``meta.json`` y vuelve a
    serializar la narrativa con los pesos y la ventana del propio snapshot.

    Args:
        hs: partida HS cuyo snapshot ya existe en ``data/processed/<hs>/``.

    Raises:
        FileNotFoundError: si el snapshot no fue construido todavía.
    """
    ranking = pd.read_parquet(config.ranking_parquet(hs))
    meta = json.loads(config.snapshot_meta_json(hs).read_text(encoding="utf-8"))
    _write_narrative(
        hs,
        ranking,
        {str(k): float(v) for k, v in meta["weights"].items()},
        int(meta["market_size_years"]),
        str(meta["hs_label"]),
    )
    logger.info("Narrativa de %s regenerada en %s", hs, config.narrative_json(hs))


def ensure_snapshot(hs: str, source: str = "comtrade", on_stage: OnStage = None) -> str:
    """Garantiza que exista el snapshot de una partida; lo construye si falta.

    Punto de entrada para la construcción on-demand (p. ej. el buscador de la
    app): si el snapshot ya está en ``data/processed/<hs>/`` no toca la red
    (los datos crudos además quedan cacheados en ``data/raw/``, así que
    reconstruir tampoco re-descarga).

    Args:
        hs: partida HS (2, 4 o 6 dígitos; se normaliza).
        source: fuente de datos (ver :func:`build_snapshot`).
        on_stage: callback opcional de progreso (ver :func:`build_snapshot`).

    Returns:
        La partida normalizada cuyo snapshot quedó disponible.

    Raises:
        ValueError: partida con formato inválido.
        RuntimeError: la fuente falló o no tiene datos para la partida.
    """
    load_dotenv()
    hs = hs_codes.normalize_hs(hs)
    if not hs_codes.is_valid_hs(hs):
        raise ValueError(f"Partida HS inválida: {hs!r}; se esperan 2, 4 o 6 dígitos")
    if config.ranking_parquet(hs).exists() and config.snapshot_meta_json(hs).exists():
        logger.info("Snapshot de %s ya existe; no se reconstruye", hs)
        return hs
    build_snapshot(source=source, hs=hs, on_stage=on_stage)
    return hs


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
        default=None,
        help="partida HS (2/4/6 dígitos, cualquiera); sin --hs construye los de config.PRODUCTS",
    )
    parser.add_argument(
        "--refresh-narrative",
        action="store_true",
        help="solo reescribe narrative.json de snapshots ya construidos (sin red); "
        "con --hs uno, sin --hs todos los de data/processed/",
    )
    args = parser.parse_args()
    if args.refresh_narrative:
        if args.hs:
            targets = [hs_codes.normalize_hs(args.hs)]
        else:
            targets = sorted(p.parent.name for p in config.PROCESSED_DIR.glob("*/meta.json"))
        for product in targets:
            refresh_narrative(product)
    else:
        if args.hs:
            products = [args.hs]
        elif args.source == "stub":
            products = [config.HS_CODE]  # el stub solo tiene datos del producto default
        else:
            products = sorted(config.PRODUCTS)
        for product in products:
            build_snapshot(source=args.source, hs=product)
