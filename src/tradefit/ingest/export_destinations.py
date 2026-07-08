"""Exportaciones del origen por destino (todos los partners) — UN Comtrade.

Alimenta la concentración de destinos del producto (HHI) y la cuota de cada
destino en las exportaciones colombianas: una consulta por producto
(reporter = origen, flujo X, todos los partners, año ``config.BASKET_YEAR``),
cacheada en ``data/raw/``. Que el origen no exporte el producto es un caso
legítimo (cf. RCA 0): devuelve vacío con warning, no error; un cambio de
formato de la fuente sí falla ruidosamente.
"""

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from tradefit import config

# Reuso intra-capa: mismo request con retry y mismo caché que el resto de
# consultas Comtrade; no se duplica la lógica de red.
from tradefit.ingest.comtrade import _BASE_PARAMS, _fetch_records, _load_cached

logger = logging.getLogger(__name__)


def fetch_export_destinations(hs: str) -> dict[str, Any]:
    """Descarga las exportaciones del origen del producto, por destino.

    Consulta: reporter = ``config.ORIGIN_COMTRADE_CODE``, flujo X,
    ``cmdCode=hs``, año ``config.BASKET_YEAR`` y **sin** ``partnerCode``
    (todos los partners; la respuesta incluye el agregado World, que el
    parse descarta).

    Args:
        hs: partida HS del producto.

    Returns:
        Payload JSON con la clave ``data``.

    Raises:
        RuntimeError: si la API responde con error o truncamiento.
    """
    params = _BASE_PARAMS | {
        "reporterCode": str(config.ORIGIN_COMTRADE_CODE),
        "period": str(config.BASKET_YEAR),
        "cmdCode": hs,
        "flowCode": "X",
    }
    del params["partnerCode"]  # la base pide solo World (0); aquí van todos
    return {"data": _fetch_records(params, f"destinos de exportación {hs} {config.BASKET_YEAR}")}


def parse_export_destinations(payload: dict[str, Any]) -> pd.DataFrame:
    """Normaliza el payload a exportaciones por destino, ordenadas desc.

    Descarta el agregado World (``partnerCode`` 0) y los valores no
    positivos; los partners que son destinos del radar se identifican por
    ISO3 (inverso de ``config.COMTRADE_REPORTER_CODES``), el resto conserva
    su código numérico como texto — solo pesan en el HHI, no se muestran.

    Args:
        payload: JSON crudo de Comtrade con la clave ``data``.

    Returns:
        DataFrame con columnas ``country_iso3`` y ``value_usd`` ordenado por
        valor descendente; VACÍO si el origen no reporta exportaciones del
        producto (caso legítimo — se registra warning).

    Raises:
        RuntimeError: si el payload no trae la clave ``data``.
    """
    records = payload.get("data")
    if records is None:
        raise RuntimeError(f"Payload de Comtrade sin clave 'data'; claves: {sorted(payload)}")
    code_to_iso3 = {code: iso3 for iso3, code in config.COMTRADE_REPORTER_CODES.items()}
    rows: list[dict[str, object]] = []
    for record in records:
        partner = record.get("partnerCode")
        if partner in (None, 0):
            continue
        value = float(record.get("primaryValue") or 0.0)
        if value <= 0:
            continue
        rows.append(
            {
                config.COL_COUNTRY: code_to_iso3.get(int(partner), str(partner)),
                config.COL_VALUE: value,
            }
        )
    if not rows:
        logger.warning(
            "El origen no reporta exportaciones del producto en %d: HHI/cuotas se omiten",
            config.BASKET_YEAR,
        )
        return pd.DataFrame({config.COL_COUNTRY: pd.Series(dtype=str), config.COL_VALUE: []})
    totals = pd.DataFrame(rows).groupby(config.COL_COUNTRY)[config.COL_VALUE].sum().reset_index()
    return totals.sort_values(
        [config.COL_VALUE, config.COL_COUNTRY], ascending=[False, True], ignore_index=True
    )


def load_export_destinations(
    hs: str, cache_file: Path | None = None, force: bool = False
) -> pd.DataFrame:
    """Carga las exportaciones por destino, descargando solo si no hay caché.

    Args:
        hs: partida HS del producto.
        cache_file: ruta del JSON crudo; default:
            ``config.comtrade_destinations_cache(hs)``.
        force: si es True, re-descarga aunque exista caché.

    Returns:
        DataFrame de :func:`parse_export_destinations`.
    """
    cache = cache_file or config.comtrade_destinations_cache(hs)
    return _load_cached(
        cache, lambda: fetch_export_destinations(hs), parse_export_destinations, force
    )
