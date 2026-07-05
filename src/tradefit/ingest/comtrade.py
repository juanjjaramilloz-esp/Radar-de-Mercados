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
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from tradefit import config
from tradefit.contracts import basket_schema, bilateral_schema, export_totals_schema, imports_schema

logger = logging.getLogger(__name__)

_TIMEOUT_S = 60
_RATE_LIMIT_RETRIES = 4
_RATE_LIMIT_WAIT_S = 2.0


_PREVIEW_CAP = 500

_BASE_PARAMS: dict[str, str] = {
    "partnerCode": "0",
    "partner2Code": "0",
    "customsCode": "C00",
    "motCode": "0",
    "includeDesc": "false",
}


def _endpoint() -> tuple[str, dict[str, str]]:
    """Elige endpoint y headers según haya o no COMTRADE_API_KEY."""
    api_key = os.environ.get(config.ENV_COMTRADE_KEY)
    if api_key:
        return config.COMTRADE_URL_AUTH, {"Ocp-Apim-Subscription-Key": api_key}
    logger.warning(
        "Sin %s en el entorno: usando el preview público de Comtrade (tope de 500 registros)",
        config.ENV_COMTRADE_KEY,
    )
    return config.COMTRADE_URL_PREVIEW, {}


def _fetch_records(params: dict[str, str], label: str) -> list[dict[str, Any]]:
    """Un request a Comtrade con reintento ante rate limit (HTTP 429).

    Raises:
        RuntimeError: error HTTP, payload sin clave ``data``, o respuesta en
            el tope del preview (posible truncamiento silencioso).
    """
    url, headers = _endpoint()
    response = None
    for attempt in range(_RATE_LIMIT_RETRIES):
        response = requests.get(url, params=params, headers=headers, timeout=_TIMEOUT_S)
        if response.status_code != 429:
            break
        wait = _RATE_LIMIT_WAIT_S * (attempt + 1)
        logger.info("Rate limit de Comtrade (%s); reintento en %.1f s", label, wait)
        time.sleep(wait)
    assert response is not None  # _RATE_LIMIT_RETRIES >= 1
    if response.status_code != 200:
        raise RuntimeError(
            f"Comtrade respondió HTTP {response.status_code} ({label}): {response.text[:500]}"
        )
    payload: dict[str, Any] = response.json()
    if "data" not in payload:
        raise RuntimeError(
            f"Respuesta de Comtrade sin clave 'data' ({label}); claves: {sorted(payload)}"
        )
    records: list[dict[str, Any]] = payload["data"]
    if not os.environ.get(config.ENV_COMTRADE_KEY) and len(records) >= _PREVIEW_CAP:
        raise RuntimeError(
            f"El preview devolvió {len(records)} registros ({label}): posible truncamiento; "
            f"se requiere {config.ENV_COMTRADE_KEY} para esta consulta"
        )
    logger.info("Comtrade %s: %d registros", label, len(records))
    return records


def fetch_comtrade_imports() -> dict[str, Any]:
    """Descarga las importaciones del producto (destinos ← mundo), por año.

    Consulta: flujo M, partner World, reporters
    ``config.COMTRADE_REPORTER_CODES``, un request por año de
    ``config.IMPORT_YEARS`` (límite del preview público), fusionados en un
    único payload con la clave ``data``.

    Returns:
        Payload JSON con la clave ``data`` (registros de todos los años).

    Raises:
        RuntimeError: si la API responde con error o cambió de formato.
    """
    merged: list[dict[str, Any]] = []
    for year in config.IMPORT_YEARS:
        params = _BASE_PARAMS | {
            "reporterCode": ",".join(str(c) for c in config.COMTRADE_REPORTER_CODES.values()),
            "period": str(year),
            "cmdCode": config.HS_CODE,
            "flowCode": "M",
        }
        merged.extend(_fetch_records(params, f"importaciones {year}"))
    return {"data": merged}


def fetch_bilateral_imports() -> dict[str, Any]:
    """Descarga las importaciones de cada destino DESDE el origen, por año.

    Igual que :func:`fetch_comtrade_imports` pero con partner = origen
    (``config.ORIGIN_COMTRADE_CODE``) en lugar de World.
    """
    merged: list[dict[str, Any]] = []
    for year in config.IMPORT_YEARS:
        params = _BASE_PARAMS | {
            "reporterCode": ",".join(str(c) for c in config.COMTRADE_REPORTER_CODES.values()),
            "period": str(year),
            "cmdCode": config.HS_CODE,
            "flowCode": "M",
            "partnerCode": str(config.ORIGIN_COMTRADE_CODE),
        }
        merged.extend(_fetch_records(params, f"bilateral {year}"))
    return {"data": merged}


def fetch_export_totals() -> dict[str, Any]:
    """Descarga exportaciones del origen y del mundo (producto y TOTAL), por año.

    Para el "mundo" se consulta sin ``reporterCode`` (todos los reporters) y
    aguas abajo se suma: el total mundial es la suma de lo que reportan los
    países exportadores.
    """
    cmd = f"{config.HS_CODE},{config.COMTRADE_CMD_TOTAL}"
    merged: list[dict[str, Any]] = []
    for year in config.IMPORT_YEARS:
        origin_params = _BASE_PARAMS | {
            "reporterCode": str(config.ORIGIN_COMTRADE_CODE),
            "period": str(year),
            "cmdCode": cmd,
            "flowCode": "X",
        }
        for record in _fetch_records(origin_params, f"exportaciones origen {year}"):
            record["_scope"] = "origin"
            merged.append(record)
        world_params = _BASE_PARAMS | {
            "period": str(year),
            "cmdCode": cmd,
            "flowCode": "X",
        }
        for record in _fetch_records(world_params, f"exportaciones mundo {year}"):
            record["_scope"] = "world"
            merged.append(record)
    return {"data": merged}


def _chunked(values: list[int], size: int) -> list[list[int]]:
    """Parte una lista en trozos de a lo sumo ``size`` elementos."""
    return [values[i : i + size] for i in range(0, len(values), size)]


def fetch_baskets() -> dict[str, Any]:
    """Descarga canastas HS2 del año ``config.BASKET_YEAR``.

    Canasta exportadora del origen (flujo X) + canasta importadora de cada
    destino (flujo M), todas a nivel de capítulo HS de 2 dígitos (``AG2``).
    Los reporters se piden en trozos de 4 para no rozar el tope de 500
    registros del preview (4 × ~97 capítulos < 500).
    """
    year = str(config.BASKET_YEAR)
    merged: list[dict[str, Any]] = []
    origin_params = _BASE_PARAMS | {
        "reporterCode": str(config.ORIGIN_COMTRADE_CODE),
        "period": year,
        "cmdCode": config.COMTRADE_CMD_ALL_HS2,
        "flowCode": "X",
    }
    merged.extend(_fetch_records(origin_params, "canasta origen"))
    codes = list(config.COMTRADE_REPORTER_CODES.values())
    for i, chunk in enumerate(_chunked(codes, 4), start=1):
        params = _BASE_PARAMS | {
            "reporterCode": ",".join(str(c) for c in chunk),
            "period": year,
            "cmdCode": config.COMTRADE_CMD_ALL_HS2,
            "flowCode": "M",
        }
        merged.extend(_fetch_records(params, f"canastas destinos {i}"))
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


def parse_bilateral_response(payload: dict[str, Any]) -> pd.DataFrame:
    """Normaliza el payload bilateral (destino ← origen) a ``bilateral_schema``.

    Misma identificación por ``reporterCode`` que
    :func:`parse_comtrade_response`. Los (país, año) ausentes significan flujo
    cero y NO se rellenan aquí: eso lo resuelve ``domain`` al cruzar con las
    importaciones totales.

    Args:
        payload: JSON de la API con la clave ``data`` (lista de registros).

    Returns:
        DataFrame validado contra ``bilateral_schema``, ordenado por país y año.

    Raises:
        RuntimeError: si el payload no tiene ``data``, un registro viene
            malformado, o ningún registro corresponde a los destinos del MVP
            (el origen exporta el producto a varios de ellos: cero filas
            delata una consulta rota, no flujos cero).
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
                config.COL_YEAR: year,
                config.COL_IMPORTS_FROM_ORIGIN: value,
            }
        )
    if not rows:
        raise RuntimeError(
            "Ningún registro bilateral corresponde a los destinos del MVP; "
            "¿cambiaron los códigos de reporter o el partner del origen?"
        )
    df = pd.DataFrame(rows).sort_values([config.COL_COUNTRY, config.COL_YEAR], ignore_index=True)
    validated: pd.DataFrame = bilateral_schema.validate(df)
    return validated


def parse_baskets_response(payload: dict[str, Any]) -> pd.DataFrame:
    """Normaliza las canastas HS2 (origen y destinos) a ``basket_schema``.

    Identifica países por ``reporterCode`` (destinos + el origen); conserva
    solo los capítulos HS de 2 dígitos (descarta agregados como ``TOTAL``) y
    suma duplicados por (país, capítulo).

    Args:
        payload: JSON de la API con la clave ``data`` (lista de registros).

    Returns:
        DataFrame validado contra ``basket_schema``.

    Raises:
        RuntimeError: si el payload no tiene ``data``, un registro viene
            malformado, o falta la canasta del origen (sin ella no hay
            complementariedad que calcular).
    """
    records = payload.get("data")
    if records is None:
        raise RuntimeError(f"Payload de Comtrade sin clave 'data'; claves: {sorted(payload)}")

    code_to_iso3 = {code: iso3 for iso3, code in config.COMTRADE_REPORTER_CODES.items()}
    code_to_iso3[config.ORIGIN_COMTRADE_CODE] = config.ORIGIN_ISO3
    rows: list[dict[str, object]] = []
    for record in records:
        try:
            reporter_code = int(record["reporterCode"])
            cmd_code = str(record["cmdCode"])
            value = float(record["primaryValue"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Registro de Comtrade con formato inesperado: {record!r}") from exc
        iso3 = code_to_iso3.get(reporter_code)
        if iso3 is None or len(cmd_code) != 2:
            continue
        rows.append({config.COL_COUNTRY: iso3, config.COL_CMD: cmd_code, config.COL_VALUE: value})
    if not rows:
        raise RuntimeError("Ningún registro de canastas corresponde a países conocidos")
    df = (
        pd.DataFrame(rows)
        .groupby([config.COL_COUNTRY, config.COL_CMD])[config.COL_VALUE]
        .sum()
        .reset_index()
        .sort_values([config.COL_COUNTRY, config.COL_CMD], ignore_index=True)
    )
    if config.ORIGIN_ISO3 not in set(df[config.COL_COUNTRY]):
        raise RuntimeError(
            f"Falta la canasta exportadora del origen ({config.ORIGIN_ISO3}) en la respuesta"
        )
    validated: pd.DataFrame = basket_schema.validate(df)
    return validated


def parse_export_totals_response(payload: dict[str, Any]) -> pd.DataFrame:
    """Normaliza los totales de exportación a ``export_totals_schema``.

    Cada registro trae ``_scope`` (``origin``/``world``, inyectado por
    :func:`fetch_export_totals`); el ``cmdCode`` se mapea a ``product``
    (``config.HS_CODE``) o ``total`` (``TOTAL``). El "mundo" se agrega
    sumando lo que reporta cada país exportador.

    Args:
        payload: JSON con la clave ``data`` (registros anotados con ``_scope``).

    Returns:
        DataFrame validado contra ``export_totals_schema``: una fila por
        (scope, cmd, año) con el valor agregado en USD.

    Raises:
        RuntimeError: si el payload no tiene ``data``, un registro viene sin
            ``_scope`` o con ``cmdCode`` inesperado, o falta alguna de las
            cuatro series que exige el RCA.
    """
    records = payload.get("data")
    if records is None:
        raise RuntimeError(f"Payload de Comtrade sin clave 'data'; claves: {sorted(payload)}")

    cmd_names = {config.HS_CODE: "product", config.COMTRADE_CMD_TOTAL: "total"}
    rows: list[dict[str, object]] = []
    for record in records:
        try:
            scope = str(record["_scope"])
            cmd = cmd_names[str(record["cmdCode"])]
            year = int(record.get("refYear") or record["period"])
            value = float(record["primaryValue"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Registro de Comtrade con formato inesperado: {record!r}") from exc
        rows.append(
            {
                config.COL_SCOPE: scope,
                config.COL_CMD: cmd,
                config.COL_YEAR: year,
                config.COL_VALUE: value,
            }
        )
    if not rows:
        raise RuntimeError("Respuesta de totales de exportación vacía")
    df = (
        pd.DataFrame(rows)
        .groupby([config.COL_SCOPE, config.COL_CMD, config.COL_YEAR])[config.COL_VALUE]
        .sum()
        .reset_index()
        .sort_values([config.COL_SCOPE, config.COL_CMD, config.COL_YEAR], ignore_index=True)
    )
    required = {
        ("origin", "product"),
        ("origin", "total"),
        ("world", "product"),
        ("world", "total"),
    }
    present = set(zip(df[config.COL_SCOPE], df[config.COL_CMD], strict=True))
    missing = required - present
    if missing:
        raise RuntimeError(f"Faltan series de exportación para el RCA: {sorted(missing)}")
    validated: pd.DataFrame = export_totals_schema.validate(df)
    return validated


def _load_cached(
    cache_file: Path,
    fetch: Callable[[], dict[str, Any]],
    parse: Callable[[dict[str, Any]], pd.DataFrame],
    force: bool = False,
) -> pd.DataFrame:
    """Descarga (solo si no hay caché), cachea el JSON crudo y parsea."""
    if force or not cache_file.exists():
        payload = fetch()
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        logger.info("Respuesta cruda de Comtrade cacheada en %s", cache_file)
    else:
        logger.info("Usando caché de Comtrade: %s", cache_file)
    cached: dict[str, Any] = json.loads(cache_file.read_text(encoding="utf-8"))
    return parse(cached)


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
    return _load_cached(cache_file, fetch_comtrade_imports, parse_comtrade_response, force)


def load_bilateral_imports(
    cache_file: Path = config.COMTRADE_BILATERAL_CACHE, force: bool = False
) -> pd.DataFrame:
    """Carga las importaciones desde el origen (caché en ``data/raw/``).

    Returns:
        DataFrame validado contra ``bilateral_schema``.
    """
    return _load_cached(cache_file, fetch_bilateral_imports, parse_bilateral_response, force)


def load_baskets(
    cache_file: Path = config.COMTRADE_BASKETS_CACHE, force: bool = False
) -> pd.DataFrame:
    """Carga las canastas HS2 de origen y destinos (caché en ``data/raw/``).

    Returns:
        DataFrame validado contra ``basket_schema``.
    """
    return _load_cached(cache_file, fetch_baskets, parse_baskets_response, force)


def load_export_totals(
    cache_file: Path = config.COMTRADE_EXPORTS_CACHE, force: bool = False
) -> pd.DataFrame:
    """Carga los totales de exportación para el RCA (caché en ``data/raw/``).

    Returns:
        DataFrame validado contra ``export_totals_schema``.
    """
    return _load_cached(cache_file, fetch_export_totals, parse_export_totals_response, force)
