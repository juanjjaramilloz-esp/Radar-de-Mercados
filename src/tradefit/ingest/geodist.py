"""Ingesta de distancias bilaterales desde CEPII GeoDist (archivo estático).

Descarga el dataset dyádico ``dist_cepii`` (Mayer & Zignago 2011, "Notes on
CEPII's distances measures: The GeoDist database", CEPII Working Paper
2011-25), filtra los pares cuyo origen es el del proyecto y versiona el
extracto en ``data/sample/geodist_col.csv.gz`` — como el catálogo HS: la app
y el pipeline leen el CSV versionado SIN red, y este módulo solo se corre
para regenerarlo.

La fuente es final (CEPII no la actualiza más) y la geografía no caduca, así
que la "recencia" no aplica a este dato: las distancias de 2011 son las
distancias de hoy.

Regenerar: ``python -m tradefit.ingest.geodist``
"""

import logging

import pandas as pd
import requests

from tradefit import config
from tradefit.contracts import geodist_schema

logger = logging.getLogger(__name__)

_TIMEOUT_S = 120

#: Columnas del dataset CEPII que conservamos, renombradas al contrato local.
_CEPII_COLUMNS = {
    "iso_d": config.COL_COUNTRY,
    "dist": "dist_km",
    "distw": "distw_km",
    "contig": "contig",
}


def fetch_cepii_distances(force: bool = False) -> pd.DataFrame:
    """Descarga (con caché en ``data/raw/``) el dist_cepii completo de CEPII.

    Args:
        force: si es True, re-descarga aunque exista el caché crudo.

    Returns:
        DataFrame crudo con todas las columnas y pares origen-destino del
        dataset (formato Stata leído con pandas).

    Raises:
        RuntimeError: si la descarga responde un error HTTP.
    """
    cache = config.CEPII_DIST_CACHE
    if force or not cache.exists():
        logger.info("Descargando dist_cepii desde %s", config.CEPII_DIST_URL)
        response = requests.get(config.CEPII_DIST_URL, timeout=_TIMEOUT_S)
        if response.status_code != 200:
            raise RuntimeError(
                f"CEPII respondió HTTP {response.status_code} para {config.CEPII_DIST_URL}"
            )
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(response.content)
        logger.info("dist_cepii cacheado en %s (%d bytes)", cache, len(response.content))
    else:
        logger.info("Usando caché de CEPII: %s", cache)
    return pd.read_stata(cache)


def extract_origin_distances(raw: pd.DataFrame) -> pd.DataFrame:
    """Extrae y normaliza los pares con origen en ``config.ORIGIN_ISO3``.

    Función sin red (testeable con un DataFrame pequeño): filtra
    ``iso_o == ORIGIN_ISO3``, renombra al contrato local y valida contra
    ``geodist_schema``. Un ``distw`` ausente (CEPII no lo calcula para
    algunos microestados) queda en NaN — quien consuma decide el fallback.

    Args:
        raw: dist_cepii completo (columnas ``iso_o``, ``iso_d``, ``dist``,
            ``distw``, ``contig``...).

    Returns:
        DataFrame validado contra ``geodist_schema``, ordenado por destino.

    Raises:
        RuntimeError: si el origen no aparece en el dataset (cambio de
            formato o de códigos de la fuente).
    """
    origin_rows = raw[raw["iso_o"] == config.ORIGIN_ISO3]
    if origin_rows.empty:
        raise RuntimeError(
            f"El origen {config.ORIGIN_ISO3} no aparece en dist_cepii; "
            f"¿cambió el formato de la fuente?"
        )
    subset = (
        origin_rows[list(_CEPII_COLUMNS)]
        .rename(columns=_CEPII_COLUMNS)
        .sort_values(config.COL_COUNTRY, ignore_index=True)
    )
    # El propio origen aparece como par (COL, COL) con la distancia interna:
    # no es un destino, fuera.
    subset = subset[subset[config.COL_COUNTRY] != config.ORIGIN_ISO3].reset_index(drop=True)
    validated: pd.DataFrame = geodist_schema.validate(subset)
    return validated


def regenerate_geodist_csv(force: bool = False) -> pd.DataFrame:
    """Reconstruye el CSV versionado de distancias del origen.

    Args:
        force: re-descarga el crudo de CEPII aunque haya caché.

    Returns:
        El DataFrame validado que quedó escrito en ``config.GEODIST_CSV``.
    """
    distances = extract_origin_distances(fetch_cepii_distances(force=force))
    config.GEODIST_CSV.parent.mkdir(parents=True, exist_ok=True)
    distances.to_csv(config.GEODIST_CSV, index=False, compression="gzip")
    logger.info(
        "Distancias de %s escritas en %s (%d destinos)",
        config.ORIGIN_ISO3,
        config.GEODIST_CSV,
        len(distances),
    )
    return distances


def load_distances() -> "pd.Series[float]":
    """Distancia origen→destino en km desde el CSV versionado (SIN red).

    Usa ``distw`` (promedio ponderado por población, la medida recomendada
    para gravedad por Mayer & Zignago 2011) con fallback a ``dist`` (entre
    ciudades principales) donde CEPII no calcula la ponderada.

    Returns:
        Series indexada por ISO3 del destino con la distancia en km,
        nombrada ``config.COL_DISTANCE_KM``.

    Raises:
        FileNotFoundError: si el CSV versionado no existe (regenerar con
            ``python -m tradefit.ingest.geodist``).
    """
    frame = geodist_schema.validate(pd.read_csv(config.GEODIST_CSV))
    indexed = frame.set_index(config.COL_COUNTRY)
    distances = indexed["distw_km"].fillna(indexed["dist_km"])
    return distances.rename(config.COL_DISTANCE_KM)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    regenerate_geodist_csv()
