"""Importaciones de cada destino por proveedor (competidores) — UN Comtrade.

Alimenta la pregunta «¿quién le vende este producto a cada destino?»: una
consulta por producto (reporters = todos los destinos del radar, flujo M,
todos los partners, años ``config.IMPORT_YEARS``), cacheada en ``data/raw/``.
El cálculo de cuotas y ranking de proveedores vive en
``domain/indices.supplier_shares``; aquí solo se descarga y normaliza.

Un destino que no reporta el producto simplemente no aparece (caso legítimo,
como en el resto de consultas Comtrade); un cambio de formato de la fuente
falla ruidosamente.
"""

import logging
from pathlib import Path
from typing import Any, Final

import pandas as pd

from tradefit import config
from tradefit.contracts import competitor_imports_schema

# Reuso intra-capa: mismo request con retry y mismo caché que el resto de
# consultas Comtrade; no se duplica la lógica de red.
from tradefit.ingest.comtrade import _BASE_PARAMS, _fetch_records, _load_cached

logger = logging.getLogger(__name__)

#: Código de partner del agregado World en Comtrade: se conserva en el parse
#: (es el denominador natural de las cuotas de proveedor aguas abajo).
PARTNER_WORLD_CODE: Final = "0"


def fetch_competitor_imports(hs: str) -> dict[str, Any]:
    """Descarga las importaciones del producto en cada destino, por proveedor.

    Consulta: reporters = ``config.COMTRADE_REPORTER_CODES`` (los destinos
    del radar), flujo M, ``cmdCode=hs``, **sin** ``partnerCode`` (todos los
    proveedores, incluido el agregado World) y ``includeDesc=true`` para
    traer el nombre de cada proveedor — los competidores pueden ser países
    ajenos al radar (China, Vietnam…) que no están en los catálogos locales.
    Un request por año de ``config.IMPORT_YEARS``: el ranking usa el último
    año con dato de cada destino (los reporters publican con rezago).

    Args:
        hs: partida HS del producto.

    Returns:
        Payload JSON con la clave ``data`` (registros de todos los años).

    Raises:
        RuntimeError: si la API responde con error o truncamiento.
    """
    merged: list[dict[str, Any]] = []
    for year in config.IMPORT_YEARS:
        params = _BASE_PARAMS | {
            "reporterCode": ",".join(str(c) for c in config.COMTRADE_REPORTER_CODES.values()),
            "period": str(year),
            "cmdCode": hs,
            "flowCode": "M",
            "includeDesc": "true",
        }
        del params["partnerCode"]  # la base pide solo World (0); aquí van todos
        merged.extend(_fetch_records(params, f"competidores {hs} {year}"))
    return {"data": merged}


def parse_competitor_imports(payload: dict[str, Any]) -> pd.DataFrame:
    """Normaliza el payload a importaciones por (destino, proveedor, año).

    Identifica al destino por ``reporterCode`` (los partners ajenos al radar
    conservan su código M49 como texto y el nombre que trae el catálogo de
    Comtrade). El agregado World (partner 0) se **conserva**: es el
    denominador de las cuotas en ``domain``. Valores no positivos se
    descartan.

    Args:
        payload: JSON crudo de Comtrade con la clave ``data``.

    Returns:
        DataFrame validado contra ``competitor_imports_schema``; VACÍO si
        ningún destino reporta el producto (caso legítimo — warning).

    Raises:
        RuntimeError: si el payload no trae ``data`` o un registro viene
            malformado.
    """
    records = payload.get("data")
    if records is None:
        raise RuntimeError(f"Payload de Comtrade sin clave 'data'; claves: {sorted(payload)}")
    code_to_iso3 = {code: iso3 for iso3, code in config.COMTRADE_REPORTER_CODES.items()}
    rows: list[dict[str, object]] = []
    for record in records:
        try:
            reporter_code = int(record["reporterCode"])
            partner_code = int(record["partnerCode"])
            year = int(record.get("refYear") or record["period"])
            value = float(record["primaryValue"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Registro de Comtrade con formato inesperado: {record!r}") from exc
        destination = code_to_iso3.get(reporter_code)
        if destination is None or value <= 0:
            continue
        partner_name = str(record.get("partnerDesc") or partner_code)
        rows.append(
            {
                config.COL_COUNTRY: destination,
                config.COL_PARTNER_CODE: str(partner_code),
                config.COL_PARTNER_NAME: partner_name,
                config.COL_YEAR: year,
                config.COL_VALUE: value,
            }
        )
    if not rows:
        logger.warning("Ningún destino reporta importaciones del producto: sin competidores")
        df = pd.DataFrame(
            {
                config.COL_COUNTRY: pd.Series(dtype=str),
                config.COL_PARTNER_CODE: pd.Series(dtype=str),
                config.COL_PARTNER_NAME: pd.Series(dtype=str),
                config.COL_YEAR: pd.Series(dtype=int),
                config.COL_VALUE: pd.Series(dtype=float),
            }
        )
    else:
        df = (
            pd.DataFrame(rows)
            .groupby(
                [
                    config.COL_COUNTRY,
                    config.COL_PARTNER_CODE,
                    config.COL_PARTNER_NAME,
                    config.COL_YEAR,
                ]
            )[config.COL_VALUE]
            .sum()
            .reset_index()
            .sort_values(
                [config.COL_COUNTRY, config.COL_YEAR, config.COL_VALUE],
                ascending=[True, True, False],
                ignore_index=True,
            )
        )
    validated: pd.DataFrame = competitor_imports_schema.validate(df)
    return validated


def load_competitor_imports(
    hs: str, cache_file: Path | None = None, force: bool = False
) -> pd.DataFrame:
    """Carga las importaciones por proveedor, descargando solo si no hay caché.

    Args:
        hs: partida HS del producto.
        cache_file: ruta del JSON crudo; default:
            ``config.comtrade_competitors_cache(hs)``.
        force: si es True, re-descarga aunque exista caché.

    Returns:
        DataFrame de :func:`parse_competitor_imports`.
    """
    cache = cache_file or config.comtrade_competitors_cache(hs)
    return _load_cached(
        cache,
        lambda: fetch_competitor_imports(hs),
        parse_competitor_imports,
        force,
        source="un_comtrade_competitors",
        parameters={"hs": hs, "years": list(config.IMPORT_YEARS)},
    )
