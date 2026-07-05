"""Ingesta de indicadores macro desde World Bank WDI (sin API key).

Descarga los indicadores de ``config.WDI_INDICATORS`` para los mercados
destino, cachea la respuesta cruda en ``data/raw/`` y la normaliza al
contrato ``macro_schema``. Un request por indicador (la API acepta la lista
de países separada por ``;``). Cualquier cambio de formato de la fuente
falla ruidosamente aquí.
"""

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from tradefit import config
from tradefit.contracts import macro_schema

logger = logging.getLogger(__name__)

_TIMEOUT_S = 60
# 18 países × 5 años = 90 registros por indicador; 500 da margen holgado.
_PER_PAGE = 500


def fetch_wdi_indicators() -> dict[str, Any]:
    """Descarga los indicadores WDI para todos los destinos, por indicador.

    Consulta ``config.WDI_URL`` con formato JSON y el rango
    ``config.WDI_DATE_RANGE``; fusiona las respuestas en un único payload con
    la clave ``data`` (la misma convención que la ingesta de Comtrade).

    Returns:
        Payload JSON con la clave ``data`` (registros de todos los
        indicadores, tal como los devuelve la API).

    Raises:
        RuntimeError: si la API responde con error HTTP o el cuerpo no tiene
            la forma ``[metadata, registros]`` esperada.
    """
    countries = ";".join(config.DESTINATIONS)
    merged: list[dict[str, Any]] = []
    for indicator_code in config.WDI_INDICATORS:
        url = config.WDI_URL.format(countries=countries, indicator=indicator_code)
        params = {
            "format": "json",
            "date": config.WDI_DATE_RANGE,
            "per_page": str(_PER_PAGE),
        }
        response = requests.get(url, params=params, timeout=_TIMEOUT_S)
        if response.status_code != 200:
            raise RuntimeError(
                f"WDI respondió HTTP {response.status_code} ({indicator_code}): "
                f"{response.text[:500]}"
            )
        body = response.json()
        if not isinstance(body, list) or len(body) < 2 or not isinstance(body[1], list):
            raise RuntimeError(
                f"Respuesta de WDI sin la forma [metadata, registros] ({indicator_code}): "
                f"{str(body)[:300]}"
            )
        records: list[dict[str, Any]] = body[1]
        logger.info("WDI %s: %d registros", indicator_code, len(records))
        merged.extend(records)
    return {"data": merged}


def parse_wdi_response(payload: dict[str, Any]) -> pd.DataFrame:
    """Normaliza un payload crudo de WDI al contrato ``macro_schema``.

    Mapea el código del indicador (``record["indicator"]["id"]``) al nombre
    corto de ``config.WDI_INDICATORS`` y descarta los años sin dato
    (``value`` null): la ausencia la maneja ``domain`` aguas abajo. Función
    sin red: testeable con respuestas guardadas.

    Args:
        payload: JSON con la clave ``data`` (lista de registros WDI).

    Returns:
        DataFrame validado contra ``macro_schema``, ordenado por país,
        indicador y año.

    Raises:
        RuntimeError: si el payload no tiene ``data``, un registro no trae
            los campos esperados, o ningún registro corresponde a los
            destinos del MVP. Un destino sin datos solo genera un warning:
            el filtro macro le asigna estabilidad neutra aguas abajo.
    """
    records = payload.get("data")
    if records is None:
        raise RuntimeError(f"Payload de WDI sin clave 'data'; claves: {sorted(payload)}")

    rows: list[dict[str, object]] = []
    for record in records:
        try:
            iso3 = str(record["countryiso3code"])
            indicator_code = str(record["indicator"]["id"])
            year = int(record["date"])
            value = record["value"]
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Registro de WDI con formato inesperado: {record!r}") from exc
        indicator = config.WDI_INDICATORS.get(indicator_code)
        if indicator is None or iso3 not in config.DESTINATIONS or value is None:
            continue
        rows.append(
            {
                config.COL_COUNTRY: iso3,
                config.COL_INDICATOR: indicator,
                config.COL_YEAR: year,
                config.COL_MACRO_VALUE: float(value),
            }
        )
    if not rows:
        raise RuntimeError("Ningún registro de WDI corresponde a los destinos del MVP")

    df = pd.DataFrame(rows).sort_values(
        [config.COL_COUNTRY, config.COL_INDICATOR, config.COL_YEAR], ignore_index=True
    )
    missing = sorted(set(config.DESTINATIONS) - set(df[config.COL_COUNTRY]))
    if missing:
        logger.warning("Destinos sin datos macro en WDI (estabilidad neutra): %s", missing)
    validated: pd.DataFrame = macro_schema.validate(df)
    return validated


def load_wdi_macro(cache_file: Path = config.WDI_CACHE_FILE, force: bool = False) -> pd.DataFrame:
    """Carga los indicadores macro, descargando solo si no hay caché.

    Args:
        cache_file: ruta del JSON crudo cacheado (default: ``data/raw/``).
        force: si es True, re-descarga aunque exista caché.

    Returns:
        DataFrame validado contra ``macro_schema``.
    """
    if force or not cache_file.exists():
        payload = fetch_wdi_indicators()
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        logger.info("Respuesta cruda de WDI cacheada en %s", cache_file)
    else:
        logger.info("Usando caché de WDI: %s", cache_file)
    cached: dict[str, Any] = json.loads(cache_file.read_text(encoding="utf-8"))
    return parse_wdi_response(cached)
