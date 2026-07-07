"""Catálogo local de partidas arancelarias (HS): validación, búsqueda y etiquetas.

Lee el catálogo versionado ``data/sample/hs_reference.csv.gz`` (código HS →
descripción, niveles 2/4/6 dígitos, nomenclatura H6 de UN Comtrade). Módulo
SIN red: lo consumen tanto la app (buscador de partidas) como el pipeline
(etiqueta del snapshot). El catálogo se regenera con ``ingest/hs_reference.py``.
"""

import gzip
import logging
import re

import pandas as pd

from tradefit import config

logger = logging.getLogger(__name__)

#: Formato válido de una partida HS: 2 (capítulo), 4 (partida) o 6 (subpartida) dígitos.
_HS_RE = re.compile(r"^\d{2}(\d{2})?(\d{2})?$")

COL_HS: str = "hs_code"
COL_DESC: str = "description"


def normalize_hs(raw: str) -> str:
    """Normaliza la entrada del usuario a un código HS plano.

    Quita espacios y puntos (se acepta ``09.01`` o `` 0901 ``); NO valida el
    formato — para eso está :func:`is_valid_hs`.

    Args:
        raw: texto ingresado por el usuario.

    Returns:
        Código sin separadores (p. ej. ``"0901"``).
    """
    return raw.strip().replace(".", "").replace(" ", "")


def is_valid_hs(hs: str) -> bool:
    """True si ``hs`` tiene formato de partida HS (2, 4 o 6 dígitos)."""
    return bool(_HS_RE.fullmatch(hs))


def load_hs_reference() -> pd.DataFrame:
    """Carga el catálogo HS versionado.

    Returns:
        DataFrame con columnas ``hs_code`` (str) y ``description`` (str),
        una fila por código de 2/4/6 dígitos.

    Raises:
        FileNotFoundError: si el catálogo no está en ``data/sample/``.
    """
    with gzip.open(config.HS_REFERENCE_CSV, "rt", encoding="utf-8") as f:
        return pd.read_csv(f, dtype=str)


def search_hs(query: str, catalog: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    """Busca partidas por código (prefijo) o por descripción (todas las palabras).

    Args:
        query: código HS (o su prefijo) o términos en la descripción (en
            inglés, el idioma del catálogo de Comtrade).
        catalog: catálogo cargado con :func:`load_hs_reference`.
        limit: máximo de resultados.

    Returns:
        Subconjunto del catálogo (mismas columnas), a lo sumo ``limit`` filas.
        Vacío si la consulta es en blanco o nada coincide.
    """
    normalized = normalize_hs(query)
    if not normalized:
        return catalog.head(0)
    if normalized.isdigit():
        mask = catalog[COL_HS].str.startswith(normalized)
    else:
        terms = [t for t in query.casefold().split() if t]
        descriptions = catalog[COL_DESC].str.casefold()
        mask = pd.Series(True, index=catalog.index)
        for term in terms:
            mask &= descriptions.str.contains(re.escape(term), na=False)
    return catalog[mask].head(limit)


def hs_label(hs: str) -> str:
    """Etiqueta legible de una partida: curada > catálogo > genérica.

    Prioridad: etiqueta en español de ``config.PRODUCTS`` (productos curados),
    luego la descripción del catálogo versionado, y como último recurso
    ``"HS <código>"`` (el catálogo puede faltar o no traer el código).
    """
    curated = config.PRODUCTS.get(hs)
    if curated:
        return curated
    try:
        catalog = load_hs_reference()
    except FileNotFoundError:
        logger.warning("Catálogo HS no encontrado en %s", config.HS_REFERENCE_CSV)
        return f"HS {hs}"
    match = catalog.loc[catalog[COL_HS] == hs, COL_DESC]
    if match.empty:
        return f"HS {hs}"
    return f"{match.iloc[0]} (HS {hs})"
