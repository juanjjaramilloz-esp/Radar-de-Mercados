"""Refresh programado de fuentes y snapshots con política de frescura.

El workflow puede ejecutarse cada mes sin descargar todo cada mes: consulta
los sidecars de ``ingest.cache`` y refresca únicamente Comtrade, WDI o WITS
cuando exceden la edad definida en ``config.REFRESH_MAX_AGE_DAYS``.
"""

import argparse
import json
import logging
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from tradefit import config, hs_codes
from tradefit.ingest import comtrade, worldbank
from tradefit.ingest.cache import metadata_path, read_json
from tradefit.pipeline.backtest import run_backtest
from tradefit.pipeline.build_snapshot import build_snapshot

logger = logging.getLogger(__name__)
SOURCES = frozenset(config.REFRESH_MAX_AGE_DAYS)


def cache_group_due(paths: Sequence[Path], max_age_days: int, now: datetime) -> bool:
    """True si falta un caché/sidecar o alguno excede ``max_age_days``."""
    if max_age_days < 1:
        raise ValueError(f"max_age_days debe ser positivo; recibido: {max_age_days}")
    reference = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
    for path in paths:
        sidecar = metadata_path(path)
        if not path.exists() or not sidecar.exists():
            return True
        retrieved = read_json(sidecar).get("retrieved_at_utc")
        if not isinstance(retrieved, str):
            return True
        try:
            timestamp = datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
        except ValueError:
            return True
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        if (reference - timestamp.astimezone(UTC)).days >= max_age_days:
            return True
    return False


def _cache_groups(products: Sequence[str]) -> dict[str, list[Path]]:
    """Cachés dinámicos que representan la frescura de cada fuente."""
    comtrade_paths = [config.COMTRADE_BASKETS_CACHE]
    wits_paths: list[Path] = []
    for hs in products:
        comtrade_paths.extend(
            [
                config.comtrade_imports_cache(hs),
                config.comtrade_bilateral_cache(hs),
                config.comtrade_exports_cache(hs),
                config.comtrade_destinations_cache(hs),
                config.comtrade_competitors_cache(hs),
            ]
        )
        wits_paths.extend([config.wits_tariffs_cache(hs), config.wits_competitor_tariffs_cache(hs)])
    return {
        "comtrade": comtrade_paths,
        "wdi": [config.WDI_CACHE_FILE],
        "wits": wits_paths,
    }


def due_sources(
    products: Sequence[str],
    now: datetime | None = None,
    policy: Mapping[str, int] | None = None,
) -> frozenset[str]:
    """Fuentes vencidas según sidecars y política centralizada."""
    reference = now or datetime.now(UTC)
    groups = _cache_groups(products)
    active_policy = policy or config.REFRESH_MAX_AGE_DAYS
    return frozenset(
        source
        for source, max_age in active_policy.items()
        if cache_group_due(groups[source], max_age, reference)
    )


def refresh_catalog(
    products: Sequence[str] | None = None,
    requested_sources: frozenset[str] | None = None,
    *,
    force: bool = False,
    dry_run: bool = False,
    now: datetime | None = None,
) -> dict[str, object]:
    """Refresca fuentes seleccionadas, reconstruye snapshots y backtest.

    Sin ``requested_sources`` elige solo las fuentes vencidas; ``force``
    selecciona las tres. ``dry_run`` calcula el plan sin red ni escrituras.
    """
    product_codes = tuple(products or config.PRODUCTS)
    invalid = [hs for hs in product_codes if not hs_codes.is_valid_hs(hs)]
    if invalid:
        raise ValueError(f"Partidas HS inválidas: {invalid}")
    unknown = set(requested_sources or ()) - SOURCES
    if unknown:
        raise ValueError(f"Fuentes de refresh desconocidas: {sorted(unknown)}")

    if requested_sources is not None:
        selected = requested_sources
    elif force:
        selected = SOURCES
    else:
        selected = due_sources(product_codes, now)
    report: dict[str, object] = {
        "dry_run": dry_run,
        "products": list(product_codes),
        "sources": sorted(selected),
    }
    if dry_run or not selected:
        return report

    load_dotenv()
    if "comtrade" in selected and not os.environ.get(config.ENV_COMTRADE_KEY):
        raise RuntimeError(
            f"El refresh de Comtrade requiere {config.ENV_COMTRADE_KEY}; "
            "configúrala como secreto del workflow"
        )

    # Insumos compartidos: una descarga por tanda, no una por producto.
    if "comtrade" in selected:
        comtrade.load_baskets(force=True)
    if "wdi" in selected:
        worldbank.load_wdi_macro(force=True)

    product_sources = frozenset(selected & {"comtrade", "wits"})
    for hs in product_codes:
        build_snapshot(source="comtrade", hs=hs, force_sources=product_sources)

    # La validación publicada debe corresponder a la misma generación de
    # snapshots. Se recalcula después de cualquier fuente actualizada.
    run_backtest()
    return report


def main() -> None:
    """CLI de refresh para uso local y GitHub Actions."""
    parser = argparse.ArgumentParser(description="Refresca fuentes y snapshots de TradeFit.")
    parser.add_argument("--force", action="store_true", help="ignora la política de antigüedad")
    parser.add_argument(
        "--dry-run", action="store_true", help="muestra el plan sin tocar red/disco"
    )
    parser.add_argument("--sources", nargs="+", choices=sorted(SOURCES), default=None)
    parser.add_argument(
        "--hs", nargs="+", default=None, help="partidas concretas (default: catálogo)"
    )
    args = parser.parse_args()
    requested = frozenset(args.sources) if args.sources is not None else None
    report = refresh_catalog(
        products=args.hs,
        requested_sources=requested,
        force=args.force,
        dry_run=args.dry_run,
    )
    logger.info("Plan/resultado de refresh:\n%s", json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    main()
