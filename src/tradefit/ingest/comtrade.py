"""Ingesta de importaciones producto-nivel desde UN Comtrade Plus.

Descarga las importaciones anuales del producto (HS ``config.HS_CODE``) de
cada mercado destino desde el mundo (partner: World), cachea la respuesta
cruda en ``data/raw/`` y la normaliza al contrato ``imports_schema``.

Con ``COMTRADE_API_KEY`` en el entorno usa el endpoint autenticado; sin key
cae al preview público (máx. 500 registros — alcanza para la consulta acotada
del MVP, pero se registra una advertencia). Cualquier cambio de formato de la
fuente falla ruidosamente aquí, nunca silenciosamente aguas abajo.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from tradefit import config
from tradefit.contracts import imports_schema

logger = logging.getLogger(__name__)

_TIMEOUT_S = 60
_RATE_LIMIT_RETRIES = 4
_RATE_LIMIT_WAIT_S = 2.0


def _fetch_one_year(year: int, url: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    """Descarga los registros de un año (el preview solo acepta 1 período/request).

    Raises:
        RuntimeError: si la API responde con error HTTP o sin clave ``data``.
    """
    params: dict[str, str] = {
        "reporterCode": ",".join(str(c) for c in config.COMTRADE_REPORTER_CODES.values()),
        "period": str(year),
        "cmdCode": config.HS_CODE,
        "flowCode": "M",
        "partnerCode": "0",
        "partner2Code": "0",
        "customsCode": "C00",
        "motCode": "0",
        "includeDesc": "false",
    }
    for attempt in range(_RATE_LIMIT_RETRIES):
        response = requests.get(url, params=params, headers=headers, timeout=_TIMEOUT_S)
        if response.status_code != 429:
            break
        wait = _RATE_LIMIT_WAIT_S * (attempt + 1)
        logger.info("Rate limit de Comtrade para %d; reintento en %.1f s", year, wait)
        time.sleep(wait)
    if response.status_code != 200:
        raise RuntimeError(
            f"Comtrade respondió HTTP {response.status_code} para {year}: {response.text[:500]}"
        )
    payload: dict[str, Any] = response.json()
    if "data" not in payload:
        raise RuntimeError(
            f"Respuesta de Comtrade sin clave 'data' para {year}; claves: {sorted(payload)}"
        )
    records: list[dict[str, Any]] = payload["data"]
    logger.info("Comtrade %d: %d registros", year, len(records))
    return records


def fetch_comtrade_imports() -> dict[str, Any]:
    """Descarga de la API las importaciones del producto para los destinos.

    Consulta: flujo M (importaciones), partner World, reporters
    ``config.COMTRADE_REPORTER_CODES``, un request por año de
    ``config.IMPORT_YEARS`` (límite del preview público), fusionados en un
    único payload con la clave ``data``.

    Returns:
        Payload JSON con la clave ``data`` (registros de todos los años).

    Raises:
        RuntimeError: si la API responde con error HTTP o el payload no
            trae la clave ``data`` (formato cambió).
    """
    api_key = os.environ.get(config.ENV_COMTRADE_KEY)
    if api_key:
        url = config.COMTRADE_URL_AUTH
        headers = {"Ocp-Apim-Subscription-Key": api_key}
        logger.info("Descargando de Comtrade (endpoint autenticado)")
    else:
        url = config.COMTRADE_URL_PREVIEW
        headers = {}
        logger.warning(
            "Sin %s en el entorno: usando el preview público de Comtrade (tope de 500 registros)",
            config.ENV_COMTRADE_KEY,
        )
    merged: list[dict[str, Any]] = []
    for year in config.IMPORT_YEARS:
        merged.extend(_fetch_one_year(year, url, headers))
    return {"data": merged}


def parse_comtrade_response(payload: dict[str, Any]) -> pd.DataFrame:
    """Normaliza un payload crudo de Comtrade al contrato ``imports_schema``.

    Identifica al destino por ``reporterCode`` numérico (el preview devuelve
    ``reporterISO`` en null) usando ``config.COMTRADE_REPORTER_CODES``
    invertido, toma ``primaryValue`` como importaciones en USD y usa los
    nombres de país de ``config`` (no los de la API). Función sin red:
    testeable con respuestas guardadas.

    Args:
        payload: JSON de la API con la clave ``data`` (lista de registros).

    Returns:
        DataFrame validado contra ``imports_schema``, ordenado por país y año.

    Raises:
        RuntimeError: si el payload no tiene ``data``, si un registro no trae
            los campos esperados, o si ningún registro corresponde a los
            destinos del MVP.
    """
    records = payload.get("data")
    if records is None:
        raise RuntimeError(f"Payload de Comtrade sin clave 'data'; claves: {sorted(payload)}")

    code_to_iso3 = {code: iso3 for iso3, code in config.COMTRADE_REPORTER_CODES.items()}
    rows: list[dict[str, object]] = []
    for record in records:
        try:
            reporter_code = int(record["reporterCode"])
            year = int(record.get("refYear") or record["period"])
            value = float(record["primaryValue"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Registro de Comtrade con formato inesperado: {record!r}") from exc
        iso3 = code_to_iso3.get(reporter_code)
        if iso3 is None:
            continue
        rows.append(
            {
                config.COL_COUNTRY: iso3,
                config.COL_COUNTRY_NAME: config.DESTINATIONS[iso3],
                config.COL_YEAR: year,
                config.COL_IMPORTS_USD: value,
            }
        )
    if not rows:
        raise RuntimeError(
            "Ningún registro de Comtrade corresponde a los destinos del MVP; "
            "¿cambiaron los códigos de reporter?"
        )

    df = pd.DataFrame(rows).sort_values([config.COL_COUNTRY, config.COL_YEAR], ignore_index=True)
    missing = sorted(set(config.DESTINATIONS) - set(df[config.COL_COUNTRY]))
    if missing:
        logger.warning("Destinos sin datos en Comtrade: %s", missing)
    validated: pd.DataFrame = imports_schema.validate(df)
    return validated


def load_comtrade_imports(
    cache_file: Path = config.COMTRADE_CACHE_FILE, force: bool = False
) -> pd.DataFrame:
    """Carga las importaciones reales, descargando solo si no hay caché.

    Args:
        cache_file: ruta del JSON crudo cacheado (default: ``data/raw/``).
        force: si es True, re-descarga aunque exista caché.

    Returns:
        DataFrame validado contra ``imports_schema``.
    """
    if force or not cache_file.exists():
        payload = fetch_comtrade_imports()
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        logger.info("Respuesta cruda de Comtrade cacheada en %s", cache_file)
    else:
        logger.info("Usando caché de Comtrade: %s", cache_file)
    cached: dict[str, Any] = json.loads(cache_file.read_text(encoding="utf-8"))
    return parse_comtrade_response(cached)
