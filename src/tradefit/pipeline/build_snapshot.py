"""Construye el snapshot que consume la app.

Orquesta: ingest (Comtrade o stub) → domain (índices + scoring) → validación
de contrato → escritura en ``data/processed/`` (``ranking.parquet`` +
``meta.json``). Idempotente: con el mismo input produce el mismo snapshot (no
escribe timestamps ni ningún otro valor no determinístico).
"""

import argparse
import json
import logging
import shutil
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from tradefit import config, hs_codes
from tradefit.contracts import (
    MarketInputs,
    competitors_schema,
    ranking_schema,
    tariff_profile_schema,
    unit_values_schema,
)
from tradefit.domain import indices
from tradefit.domain.macro_filter import (
    apply_stability_penalty,
    latest_indicator_value,
    stability_score,
)
from tradefit.domain.narrative import LANGS, build_narrative
from tradefit.domain.scoring import rank_markets
from tradefit.ingest import (
    competitors,
    comtrade,
    export_destinations,
    geodist,
    stub,
    wits,
    worldbank,
)
from tradefit.ingest.cache import provenance_record
from tradefit.pipeline.snapshot_io import (
    atomic_write_parquet,
    create_staging_dir,
    exclusive_lock,
    publish_snapshot,
    refresh_manifest,
    write_manifest,
)

logger = logging.getLogger(__name__)

SOURCES = ("comtrade", "stub")

#: Callback opcional de progreso: recibe la descripción de la etapa que inicia.
OnStage = Callable[[str], None] | None


def _source_cache_paths(hs: str, source: str) -> list[Path]:
    """Archivos exactos que alimentan el snapshot (para procedencia)."""
    if source == "stub":
        return [
            config.STUB_IMPORTS_CSV,
            config.STUB_BILATERAL_CSV,
            config.STUB_BASKETS_CSV,
            config.STUB_EXPORT_TOTALS_CSV,
            config.STUB_TARIFFS_CSV,
            config.STUB_MACRO_CSV,
            config.GEODIST_CSV,
        ]
    return [
        config.comtrade_imports_cache(hs),
        config.comtrade_bilateral_cache(hs),
        config.COMTRADE_BASKETS_CACHE,
        config.comtrade_exports_cache(hs),
        config.comtrade_destinations_cache(hs),
        config.comtrade_competitors_cache(hs),
        config.wits_tariffs_cache(hs),
        config.wits_competitor_tariffs_cache(hs),
        config.WDI_CACHE_FILE,
        config.GEODIST_CSV,
        config.HS_REFERENCE_CSV,
    ]


def _source_provenance(hs: str, source: str) -> list[dict[str, object]]:
    """Registros de hash/consulta de cada insumo disponible."""
    records = [provenance_record(path, config.ROOT_DIR) for path in _source_cache_paths(hs, source)]
    return [record for record in records if record is not None]


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


def _competitor_partner_plan(
    supplier_table: pd.DataFrame,
) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, set[str]]]:
    """Traduce el top de proveedores de cada destino al plan de consultas WITS.

    Selecciona los ``config.PREF_MARGIN_TOP_COMPETITORS`` mayores proveedores
    de cada destino excluyendo al origen y los agregados estadísticos de
    Comtrade, y traduce sus códigos M49 al vocabulario de WITS: miembro de la
    UE → bloque 918 (con arancel 0 por construcción si el destino también es
    UE — unión aduanera), excepciones de código
    (``config.COMTRADE_TO_WITS_PARTNER``) y zero-padding a 3 dígitos.

    Returns:
        ``(partners_by_reporter, competitors_by_destination, zero_rated)`` —
        qué pedir a WITS, contra quién promediar en cada destino (puede
        repetir el 918 si varios rivales son comunitarios) y qué pares
        entran con arancel 0 sin consultar.
    """
    eu_code = f"{config.WITS_EU_CODE:03d}"
    origin = str(config.ORIGIN_COMTRADE_CODE)
    partners_by_reporter: dict[str, set[str]] = {}
    competitors_by_destination: dict[str, list[str]] = {}
    zero_rated: dict[str, set[str]] = {}
    for iso3_raw, group in supplier_table.groupby(config.COL_COUNTRY):
        iso3 = str(iso3_raw)
        reporter_num = config.WITS_REPORTER_CODES.get(iso3)
        if reporter_num is None:
            continue
        chosen: list[str] = []
        for code_raw in group.sort_values(config.COL_SUPPLIER_RANK)[config.COL_PARTNER_CODE]:
            code = str(code_raw)
            if code == origin or code in config.COMTRADE_AGGREGATE_PARTNERS or not code.isdigit():
                continue
            if code in config.EU_MEMBER_COMTRADE_CODES:
                wits_code = eu_code
                if reporter_num == config.WITS_EU_CODE:
                    zero_rated.setdefault(iso3, set()).add(eu_code)
            else:
                wits_code = f"{int(config.COMTRADE_TO_WITS_PARTNER.get(code, code)):03d}"
            chosen.append(wits_code)
            if len(chosen) >= config.PREF_MARGIN_TOP_COMPETITORS:
                break
        if not chosen:
            continue
        competitors_by_destination[iso3] = chosen
        to_query = {c for c in chosen if c not in zero_rated.get(iso3, set())}
        if to_query:
            reporter = f"{reporter_num:03d}"
            partners_by_reporter.setdefault(reporter, set()).update(to_query)
    return (
        {reporter: sorted(codes) for reporter, codes in partners_by_reporter.items()},
        competitors_by_destination,
        zero_rated,
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
    # Distancias CEPII (CSV versionado en data/sample/, sin red) y LPI del
    # macro: insumos de la métrica de accesibilidad. Válidos también para el
    # stub — el CSV es local y el stub macro simplemente no trae LPI
    # (componente logístico neutro).
    _notify(on_stage, "Distancias bilaterales (CEPII GeoDist)")
    distances = geodist.load_distances()
    lpi = latest_indicator_value(macro, config.COL_LPI)
    data = MarketInputs(
        imports=imports,
        bilateral=bilateral,
        baskets=baskets,
        tariffs=tariffs,
        rca=_rca_from_totals(export_totals),
        distances=distances,
        lpi=lpi,
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

    # Competidores: quién le vende el producto a cada destino (solo fuente
    # real). El cálculo de cuotas/rank es puro (domain.indices.supplier_shares)
    # y se necesita ANTES del ranking: el margen de preferencia compara el
    # arancel del origen con el que enfrentan los top proveedores rivales.
    supplier_table: pd.DataFrame | None = None
    if source == "comtrade":
        _notify(on_stage, "Proveedores del producto en cada destino (competidores)")
        competitor_imports = competitors.load_competitor_imports(hs)
        if not competitor_imports.empty:
            supplier_table = competitors_schema.validate(
                indices.supplier_shares(competitor_imports)
            )
    if supplier_table is not None:
        _notify(on_stage, "Aranceles que enfrentan los competidores (margen de preferencia)")
        by_reporter, by_destination, zero_rated = _competitor_partner_plan(supplier_table)
        competitor_prefs = wits.load_competitor_tariffs(hs, by_reporter)
        data = replace(
            data,
            competitor_tariff=indices.competitor_tariff_faced(
                data.tariffs, competitor_prefs, by_destination, zero_rated
            ),
        )

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

    # Valores unitarios (USD/kg): análisis avanzado EXCLUSIVO del catálogo
    # curado — las partidas del buscador on-demand no llevan este artefacto.
    # Sale de los mismos cachés crudos de imports/bilateral (netWgt), así que
    # no agrega llamadas a la red.
    unit_values: pd.DataFrame | None = None
    if source == "comtrade" and hs in config.PRODUCTS:
        _notify(on_stage, "Valores unitarios (USD/kg) por destino")
        unit_values = _unit_values_table(
            comtrade.load_import_weights(hs),
            comtrade.load_bilateral_weights(hs),
            list(validated[config.COL_COUNTRY]),
        )

    # Perfil arancelario intra-partida (HS6): el desglose del arancel que el
    # ranking promedia (tariff_faced), para que la ficha muestre la
    # dispersión entre subpartidas. Sale de los aranceles ya descargados de
    # WITS — no agrega llamadas a la red.
    tariff_detail = indices.tariff_profile(data.tariffs)

    hs_label = hs_codes.hs_label(hs)
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
        # Rampas de la accesibilidad (distancia CEPII GeoDist + LPI).
        "accessibility_distance_bounds_km": list(config.ACCESSIBILITY_DISTANCE_BOUNDS_KM),
        "accessibility_lpi_bounds": list(config.ACCESSIBILITY_LPI_BOUNDS),
        "tariff_years": list(config.WITS_YEARS),
        "macro_indicators": dict(config.WDI_INDICATORS),
        # Indicadores de contexto (no ponderan): hoy solo el LPI.
        "context_indicators": dict(config.WDI_CONTEXT_INDICATORS),
        "macro_bounds": {k: list(v) for k, v in config.MACRO_BOUNDS.items()},
        "macro_floor": config.MACRO_FLOOR,
        "macro_years": config.MACRO_YEARS,
    }

    _notify(on_stage, "Escribiendo el snapshot")
    target = config.processed_dir(hs)
    staging = create_staging_dir(target)
    try:
        validated.to_parquet(staging / "ranking.parquet", index=False)
        imports.to_parquet(staging / "imports_timeseries.parquet", index=False)
        if supplier_table is not None:
            supplier_table.to_parquet(staging / "competitors.parquet", index=False)
        if unit_values is not None:
            unit_values.to_parquet(staging / "unit_values.parquet", index=False)
        if not tariff_detail.empty:
            tariff_profile_schema.validate(tariff_detail).to_parquet(
                staging / "tariff_profile.parquet", index=False
            )
        _write_narrative(
            hs,
            validated,
            dict(config.WEIGHTS),
            config.MARKET_SIZE_YEARS,
            hs_label,
            output_path=staging / "narrative.json",
        )
        (staging / "meta.json").write_text(
            json.dumps(meta, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        write_manifest(
            staging,
            source_inputs=_source_provenance(hs, source),
            parameters={
                "hs_code": hs,
                "source": source,
                "import_years": list(config.IMPORT_YEARS),
                "basket_year": config.BASKET_YEAR,
                "wits_years": list(config.WITS_YEARS),
                "wdi_date_range": config.WDI_DATE_RANGE,
                "weights": dict(config.WEIGHTS),
            },
        )
        # El macro es compartido entre productos reales. El stub nunca debe
        # sobrescribirlo: hacerlo mezclaría contexto sintético con los otros
        # 14 snapshots versionados.
        if source == "comtrade":
            atomic_write_parquet(macro, config.macro_context_parquet())
        publish_snapshot(staging, target)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    logger.info("Snapshot escrito en %s (%d mercados)", config.processed_dir(hs), len(validated))
    return validated


def _write_narrative(
    hs: str,
    ranking: pd.DataFrame,
    weights: dict[str, float],
    window_years: int,
    hs_label: str,
    output_path: Path | None = None,
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
    destination = output_path or config.narrative_json(hs)
    destination.write_text(
        json.dumps(narrative, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _unit_values_table(
    import_weights: pd.DataFrame,
    bilateral_weights: pd.DataFrame,
    countries: list[str],
    window_years: int = config.MARKET_SIZE_YEARS,
) -> pd.DataFrame:
    """Arma la tabla de valores unitarios por destino (una fila por país).

    Orquestación pura sobre funciones de ``domain``: para cada destino toma
    los últimos ``window_years`` años con datos (la misma ventana que
    ``market_size``) y calcula el UV agregado de las importaciones totales,
    el del flujo desde el origen y el premium relativo
    (``indices.aggregate_unit_value`` / ``indices.unit_value_premium``).

    Args:
        import_weights: flujo total con peso (``flow_weights_schema``).
        bilateral_weights: flujo origen→destino con peso (mismo contrato).
        countries: destinos del ranking (define las filas del artefacto).
        window_years: ventana de años recientes.

    Returns:
        DataFrame validado contra ``unit_values_schema``.
    """
    rows: list[dict[str, object]] = []
    for iso3 in countries:
        market = (
            import_weights[import_weights[config.COL_COUNTRY] == iso3]
            .sort_values(config.COL_YEAR)
            .tail(window_years)
        )
        origin = (
            bilateral_weights[bilateral_weights[config.COL_COUNTRY] == iso3]
            .sort_values(config.COL_YEAR)
            .tail(window_years)
        )
        uv_market = indices.aggregate_unit_value(
            market[config.COL_VALUE], market[config.COL_NET_WGT]
        )
        uv_origin = indices.aggregate_unit_value(
            origin[config.COL_VALUE], origin[config.COL_NET_WGT]
        )
        rows.append(
            {
                config.COL_COUNTRY: iso3,
                config.COL_UV_MARKET: uv_market,
                config.COL_UV_ORIGIN: uv_origin,
                config.COL_UV_PREMIUM: indices.unit_value_premium(uv_origin, uv_market),
            }
        )
    validated: pd.DataFrame = unit_values_schema.validate(pd.DataFrame(rows))
    return validated


def refresh_unit_values(hs: str) -> None:
    """Escribe solo ``unit_values.parquet`` desde los cachés crudos (sin red).

    Para poblar snapshots curados ya construidos sin re-correr el pipeline
    completo: lee el ranking existente (define los destinos) y los cachés
    crudos de Comtrade en ``data/raw/`` (que ya traen ``netWgt``).

    Args:
        hs: partida del catálogo curado con snapshot en ``data/processed/``.

    Raises:
        ValueError: si la partida no es del catálogo curado (el artefacto es
            exclusivo de esos productos).
        FileNotFoundError: si el snapshot no fue construido todavía.
    """
    if hs not in config.PRODUCTS:
        raise ValueError(f"Los valores unitarios son solo del catálogo curado; recibido: {hs!r}")
    ranking = pd.read_parquet(config.ranking_parquet(hs))
    table = _unit_values_table(
        comtrade.load_import_weights(hs),
        comtrade.load_bilateral_weights(hs),
        list(ranking[config.COL_COUNTRY]),
    )
    atomic_write_parquet(table, config.unit_values_parquet(hs))
    refresh_manifest(config.processed_dir(hs))
    logger.info("Valores unitarios de %s escritos en %s", hs, config.unit_values_parquet(hs))


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
    refresh_manifest(config.processed_dir(hs))
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
    lock_path = config.PROCESSED_DIR / f".{hs}.build.lock"
    with exclusive_lock(lock_path):
        # Repetir el chequeo dentro del lock: otra sesión pudo terminar el
        # mismo producto entre el primer clic y la adquisición del lock.
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
