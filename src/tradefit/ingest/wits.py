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

import logging
import math
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from tradefit import config, hs_codes
from tradefit.contracts import competitor_tariffs_schema, tariffs_schema
from tradefit.ingest.cache import load_json_cache, metadata_path, read_json, write_json_cache

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


def _parse_generic_data(
    xml_text: str, destinations: list[str], include_partner: bool = False
) -> list[dict[str, object]]:
    """Extrae filas (país, HS6, tipo, año, tasa) de un XML SDMX GenericData.

    Cada ``Series`` trae la subpartida en su ``SeriesKey``; cada ``Obs`` trae
    el año, la tasa (% promedio simple de líneas ad-valorem) y el atributo
    ``TARIFFTYPE``. El reporter se expande a los destinos que representa
    (la UE cubre 11 países del MVP). Con ``include_partner`` cada fila lleva
    además el código del partner de la serie (consultas multi-partner del
    margen de preferencia).

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
        partner = key.get("PARTNER")
        if include_partner and partner is None:
            raise RuntimeError(f"Serie de WITS sin PARTNER; clave: {key}")
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
                row: dict[str, object] = {
                    config.COL_COUNTRY: iso3,
                    config.COL_CMD: product,
                    config.COL_TARIFF_TYPE: tariff_type,
                    config.COL_YEAR: int(str(dimension.get("value"))),
                    config.COL_RATE_PCT: rate,
                }
                if include_partner:
                    row[config.COL_PARTNER_CODE] = str(partner)
                rows.append(row)
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
    cached, fetched = load_json_cache(
        cache_file,
        lambda: fetch_wits_tariffs(hs),
        source="world_bank_wits_tariffs",
        parameters={
            "hs": hs,
            "origin": config.ORIGIN_ISO3,
            "years": list(config.WITS_YEARS),
        },
        force=force,
    )
    if fetched:
        logger.info("Respuesta cruda de WITS cacheada en %s", cache_file)
    else:
        logger.info("Usando caché de WITS: %s", cache_file)
    return parse_wits_response(cached)


def fetch_competitor_tariffs(
    hs: str, partners_by_reporter: Mapping[str, Sequence[str]]
) -> dict[str, Any]:
    """Descarga el arancel preferencial que cada reporter aplica a competidores.

    Una consulta por reporter con los partners unidos con ``+`` (el dataflow
    TRAINS acepta multi-partner y devuelve el PARTNER en cada SeriesKey;
    verificado 2026-07). El MFN no se re-descarga: es erga omnes y ya vive en
    el caché de :func:`fetch_wits_tariffs`. Un 404 "NoRecordsFound" es normal
    (competidor sin esquema preferencial → paga MFN).

    Args:
        hs: partida HS normalizada (2, 4 o 6 dígitos).
        partners_by_reporter: códigos WITS de los competidores a consultar,
            por código de reporter a 3 dígitos (p. ej. ``{"918": ["076",
            "704"]}``).

    Returns:
        Payload serializable ``{"hs", "products", "responses": {reporter:
        {"partners": [...], "xml": xml|None}}}``.

    Raises:
        RuntimeError: si la API responde un error HTTP distinto de
            "sin registros".
        ValueError: si la partida no tiene subpartidas HS6 en el catálogo.
    """
    products = "+".join(hs_codes.hs6_children(hs))
    start, end = config.WITS_YEARS
    responses: dict[str, dict[str, Any]] = {}
    for reporter, partners in sorted(partners_by_reporter.items()):
        unique = sorted(set(partners))
        if not unique:
            continue
        url = config.WITS_URL.format(
            reporter=reporter, partner="+".join(unique), products=products, start=start, end=end
        )
        xml_text = _fetch_xml(url)
        logger.info(
            "WITS pref competidores reporter=%s partners=%s: %s",
            reporter,
            unique,
            "sin registros" if xml_text is None else f"{len(xml_text)} bytes",
        )
        responses[reporter] = {"partners": unique, "xml": xml_text}
    return {"hs": hs, "products": products, "responses": responses}


def parse_competitor_response(payload: dict[str, Any]) -> pd.DataFrame:
    """Normaliza el payload de competidores al contrato ``competitor_tariffs_schema``.

    Función sin red. Cada reporter se expande a los destinos que representa
    (mismo criterio que :func:`parse_wits_response`); cada fila conserva el
    código WITS del partner competidor.

    Raises:
        RuntimeError: si el payload no tiene ``responses`` o un XML cambió
            de estructura.
    """
    responses = payload.get("responses")
    if responses is None:
        raise RuntimeError(f"Payload de WITS sin clave 'responses'; claves: {sorted(payload)}")

    by_reporter: dict[str, list[str]] = {}
    for iso3, code in config.WITS_REPORTER_CODES.items():
        by_reporter.setdefault(f"{code:03d}", []).append(iso3)

    rows: list[dict[str, object]] = []
    for reporter, entry in responses.items():
        destinations = by_reporter.get(reporter)
        if destinations is None:
            logger.warning("Reporter %s del caché no corresponde a ningún destino", reporter)
            continue
        xml_text = entry.get("xml")
        if xml_text is not None:
            rows.extend(_parse_generic_data(xml_text, destinations, include_partner=True))

    columns = [
        config.COL_COUNTRY,
        config.COL_PARTNER_CODE,
        config.COL_CMD,
        config.COL_TARIFF_TYPE,
        config.COL_YEAR,
        config.COL_RATE_PCT,
    ]
    df = pd.DataFrame(rows, columns=columns)
    df = df.drop_duplicates(subset=columns[:5]).sort_values(columns[:5], ignore_index=True)
    validated: pd.DataFrame = competitor_tariffs_schema.validate(df)
    return validated


def load_competitor_tariffs(
    hs: str,
    partners_by_reporter: Mapping[str, Sequence[str]],
    cache_file: Path | None = None,
    force: bool = False,
) -> pd.DataFrame:
    """Carga los aranceles a competidores, descargando solo si falta caché.

    El caché se invalida solo si pide partners que no estaban cacheados (el
    top de competidores puede cambiar al refrescar el comercio); pedir un
    subconjunto reutiliza el caché.

    Args:
        hs: partida HS normalizada.
        partners_by_reporter: códigos WITS de competidores por reporter.
        cache_file: ruta del JSON crudo (default:
            ``config.wits_competitor_tariffs_cache(hs)``).
        force: si es True, re-descarga aunque exista caché.

    Returns:
        DataFrame validado contra ``competitor_tariffs_schema``.
    """
    if cache_file is None:
        cache_file = config.wits_competitor_tariffs_cache(hs)
    stale = force or not cache_file.exists()
    cached_payload: dict[str, Any] | None = None
    cached_partners: dict[str, set[str]] = {}
    if not stale:
        cached_payload = read_json(cache_file)
        cached_partners = {
            reporter: set(entry.get("partners", []))
            for reporter, entry in cached_payload.get("responses", {}).items()
        }
        stale = any(
            set(partners) - cached_partners.get(reporter, set())
            for reporter, partners in partners_by_reporter.items()
        )
        sidecar = metadata_path(cache_file)
        if sidecar.exists():
            cached_parameters = read_json(sidecar).get("parameters", {})
            stale = stale or cached_parameters.get("years") != list(config.WITS_YEARS)
    if stale:
        payload = fetch_competitor_tariffs(hs, partners_by_reporter)
        write_json_cache(
            cache_file,
            payload,
            source="world_bank_wits_competitor_tariffs",
            parameters={
                "hs": hs,
                "partners_by_reporter": {
                    reporter: sorted(set(partners))
                    for reporter, partners in sorted(partners_by_reporter.items())
                },
                "years": list(config.WITS_YEARS),
            },
        )
        logger.info("Aranceles a competidores cacheados en %s", cache_file)
    else:
        if cached_payload is not None and not metadata_path(cache_file).exists():
            write_json_cache(
                cache_file,
                cached_payload,
                source="world_bank_wits_competitor_tariffs",
                parameters={
                    "hs": hs,
                    "partners_by_reporter": {
                        reporter: sorted(partners)
                        for reporter, partners in sorted(cached_partners.items())
                    },
                    "years": list(config.WITS_YEARS),
                },
                retrieved_at=None,
            )
        logger.info("Usando caché de WITS (competidores): %s", cache_file)
    cached = read_json(cache_file)
    return parse_competitor_response(cached)
