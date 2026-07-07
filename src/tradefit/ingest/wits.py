"""Ingesta de aranceles desde World Bank WITS (dataflow TRAINS; sin API key).

Descarga, para cada destino, el arancel MFN (partner "000" = mundo) y el
preferencial que enfrenta el origen (partner Colombia), a nivel de subpartida
HS6 — el dataflow ``DF_WITS_Tariff_TRAINS`` no acepta partidas de 2/4 dígitos,
así que la partida pedida se expande a sus HS6 con el catálogo local. La UE
reporta como bloque (código 918): una sola consulta cubre a los 11 destinos
comunitarios del MVP.

La respuesta es XML SDMX 2.1 GenericData (el endpoint ignora ``format=JSON``);
se cachea cruda en ``data/raw/`` y se normaliza al contrato ``tariffs_schema``.
Un 404 "NoRecordsFound" no es error: significa que esa combinación no tiene
registros (p. ej. sin esquema preferencial hacia Colombia). Cualquier otro
error HTTP o cambio de formato falla ruidosamente aquí.
"""

import json
import logging
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from tradefit import config, hs_codes
from tradefit.contracts import tariffs_schema

logger = logging.getLogger(__name__)

_TIMEOUT_S = 60

# Namespaces del mensaje SDMX-ML 2.1 GenericData.
_NS = {
    "message": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message",
    "generic": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic",
}


def _fetch_xml(url: str) -> str | None:
    """GET de un dataflow WITS; ``None`` si no hay registros (404 NoRecordsFound).

    Raises:
        RuntimeError: ante cualquier otro status HTTP.
    """
    response = requests.get(url, timeout=_TIMEOUT_S)
    if response.status_code == 404 and "NoRecordsFound" in response.text:
        return None
    if response.status_code != 200:
        raise RuntimeError(
            f"WITS respondió HTTP {response.status_code} para {url}: {response.text[:300]}"
        )
    return response.text


def fetch_wits_tariffs(hs: str) -> dict[str, Any]:
    """Descarga los aranceles MFN y preferenciales (origen) del producto ``hs``.

    Un par de requests (MFN + preferencial) por reporter único de
    ``config.WITS_REPORTER_CODES`` — la UE (918) se consulta una sola vez —
    con todas las subpartidas HS6 de la partida unidas con ``+``.

    Args:
        hs: partida HS normalizada (2, 4 o 6 dígitos).

    Returns:
        Payload serializable con los XML crudos por reporter:
        ``{"hs": ..., "products": ..., "responses": {"918": {"mfn": xml|None,
        "pref": xml|None}, ...}}``.

    Raises:
        RuntimeError: si la API responde un error HTTP distinto de
            "sin registros".
        ValueError: si la partida no tiene subpartidas HS6 en el catálogo.
    """
    products = "+".join(hs_codes.hs6_children(hs))
    start, end = config.WITS_YEARS
    responses: dict[str, dict[str, str | None]] = {}
    for reporter_code in sorted(set(config.WITS_REPORTER_CODES.values())):
        # WITS exige el código de país a 3 dígitos (Australia = "036", no "36").
        reporter = f"{reporter_code:03d}"
        pair: dict[str, str | None] = {}
        for kind, partner in (
            ("mfn", config.WITS_PARTNER_WORLD),
            ("pref", str(config.ORIGIN_WITS_CODE)),
        ):
            url = config.WITS_URL.format(
                reporter=reporter, partner=partner, products=products, start=start, end=end
            )
            pair[kind] = _fetch_xml(url)
            logger.info(
                "WITS %s reporter=%s: %s",
                kind,
                reporter,
                "sin registros" if pair[kind] is None else f"{len(pair[kind] or '')} bytes",
            )
        responses[str(reporter)] = pair
    return {"hs": hs, "products": products, "responses": responses}


def _parse_generic_data(xml_text: str, destinations: list[str]) -> list[dict[str, object]]:
    """Extrae filas (país, HS6, tipo, año, tasa) de un XML SDMX GenericData.

    Cada ``Series`` trae la subpartida en su ``SeriesKey``; cada ``Obs`` trae
    el año, la tasa (% promedio simple de líneas ad-valorem) y el atributo
    ``TARIFFTYPE``. El reporter se expande a los destinos que representa
    (la UE cubre 11 países del MVP).

    Raises:
        RuntimeError: si el XML no tiene la estructura esperada o trae un
            tipo de arancel desconocido.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise RuntimeError(f"Respuesta de WITS no es XML válido: {xml_text[:200]}") from exc

    rows: list[dict[str, object]] = []
    for series in root.iter(f"{{{_NS['generic']}}}Series"):
        key = {
            value.get("id"): value.get("value")
            for value in series.findall("generic:SeriesKey/generic:Value", _NS)
        }
        product = key.get("PRODUCTCODE")
        if product is None:
            raise RuntimeError(f"Serie de WITS sin PRODUCTCODE; clave: {key}")
        for obs in series.findall("generic:Obs", _NS):
            dimension = obs.find("generic:ObsDimension", _NS)
            value = obs.find("generic:ObsValue", _NS)
            attributes = {
                attr.get("id"): attr.get("value")
                for attr in obs.findall("generic:Attributes/generic:Value", _NS)
            }
            tariff_type = attributes.get("TARIFFTYPE")
            if dimension is None or value is None or tariff_type is None:
                raise RuntimeError(f"Observación de WITS sin año, valor o TARIFFTYPE: {key}")
            if tariff_type not in ("MFN", "PREF"):
                raise RuntimeError(f"Tipo de arancel desconocido en WITS: {tariff_type!r}")
            rate = float(str(value.get("value")))
            if not math.isfinite(rate):
                # Líneas no ad-valorem sin equivalente AVE (p. ej. aranceles
                # específicos del azúcar): WITS reporta ObsValue "NaN" — la
                # observación no aporta dato.
                logger.debug("Observación sin AVE (%s, %s): descartada", product, tariff_type)
                continue
            for iso3 in destinations:
                rows.append(
                    {
                        config.COL_COUNTRY: iso3,
                        config.COL_CMD: product,
                        config.COL_TARIFF_TYPE: tariff_type,
                        config.COL_YEAR: int(str(dimension.get("value"))),
                        config.COL_RATE_PCT: rate,
                    }
                )
    return rows


def parse_wits_response(payload: dict[str, Any]) -> pd.DataFrame:
    """Normaliza el payload crudo de WITS al contrato ``tariffs_schema``.

    Función sin red: testeable con respuestas guardadas. Un reporter sin
    registros MFN genera un warning (el arancel del destino queda sin dato y
    domain lo trata como NaN); sin preferencial es lo esperado cuando no hay
    acuerdo con el origen.

    Args:
        payload: dict con ``responses`` (XML crudo por reporter, ver
            :func:`fetch_wits_tariffs`).

    Returns:
        DataFrame validado contra ``tariffs_schema`` (puede ser vacío si la
        partida no existe en TRAINS), ordenado y sin duplicados.

    Raises:
        RuntimeError: si el payload no tiene ``responses`` o un XML cambió de
            estructura.
    """
    responses = payload.get("responses")
    if responses is None:
        raise RuntimeError(f"Payload de WITS sin clave 'responses'; claves: {sorted(payload)}")

    by_reporter: dict[str, list[str]] = {}
    for iso3, code in config.WITS_REPORTER_CODES.items():
        by_reporter.setdefault(f"{code:03d}", []).append(iso3)

    rows: list[dict[str, object]] = []
    for reporter, pair in responses.items():
        destinations = by_reporter.get(reporter)
        if destinations is None:
            logger.warning("Reporter %s del caché no corresponde a ningún destino", reporter)
            continue
        if pair.get("mfn") is None:
            logger.warning("Sin arancel MFN en WITS para %s (quedará sin dato)", destinations)
        for kind in ("mfn", "pref"):
            xml_text = pair.get(kind)
            if xml_text is not None:
                rows.extend(_parse_generic_data(xml_text, destinations))

    columns = [
        config.COL_COUNTRY,
        config.COL_CMD,
        config.COL_TARIFF_TYPE,
        config.COL_YEAR,
        config.COL_RATE_PCT,
    ]
    df = pd.DataFrame(rows, columns=columns)
    df = df.drop_duplicates(subset=columns[:4]).sort_values(columns[:4], ignore_index=True)
    validated: pd.DataFrame = tariffs_schema.validate(df)
    return validated


def load_wits_tariffs(hs: str, cache_file: Path | None = None, force: bool = False) -> pd.DataFrame:
    """Carga los aranceles del producto, descargando solo si no hay caché.

    Args:
        hs: partida HS normalizada (2, 4 o 6 dígitos).
        cache_file: ruta del JSON crudo cacheado (default:
            ``config.wits_tariffs_cache(hs)``).
        force: si es True, re-descarga aunque exista caché.

    Returns:
        DataFrame validado contra ``tariffs_schema``.
    """
    if cache_file is None:
        cache_file = config.wits_tariffs_cache(hs)
    if force or not cache_file.exists():
        payload = fetch_wits_tariffs(hs)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        logger.info("Respuesta cruda de WITS cacheada en %s", cache_file)
    else:
        logger.info("Usando caché de WITS: %s", cache_file)
    cached: dict[str, Any] = json.loads(cache_file.read_text(encoding="utf-8"))
    return parse_wits_response(cached)
