"""Regenera el catálogo HS versionado desde el codebook oficial de Comtrade.

Descarga la nomenclatura H6 (``config.COMTRADE_HS_REFERENCE_URL``, sin API
key), la reduce a (código, descripción) para los niveles 2/4/6 dígitos y la
escribe comprimida en ``config.HS_REFERENCE_CSV`` (data/sample/, versionado).
Se corre a mano cuando cambia la nomenclatura — no es parte del pipeline:

    python -m tradefit.ingest.hs_reference
"""

import gzip
import logging
from typing import Any

import pandas as pd
import requests

from tradefit import config
from tradefit.hs_codes import COL_DESC, COL_HS

logger = logging.getLogger(__name__)

_TIMEOUT_S = 60


def parse_hs_reference(payload: dict[str, Any]) -> pd.DataFrame:
    """Normaliza el codebook crudo al formato del catálogo local.

    Conserva solo códigos numéricos de 2/4/6 dígitos (descarta agregados como
    ``TOTAL``) y quita el prefijo ``"<código> - "`` de la descripción.

    Args:
        payload: JSON del codebook con la clave ``results``.

    Returns:
        DataFrame con columnas ``hs_code`` y ``description``, ordenado por código.

    Raises:
        RuntimeError: si el payload no trae ``results`` o queda vacío tras filtrar.
    """
    items = payload.get("results")
    if items is None:
        raise RuntimeError(f"Codebook HS sin clave 'results'; claves: {sorted(payload)}")
    rows: list[dict[str, str]] = []
    for item in items:
        code = str(item.get("id", ""))
        if not code.isdigit() or len(code) not in (2, 4, 6):
            continue
        text = str(item.get("text", ""))
        prefix = f"{code} - "
        rows.append(
            {
                COL_HS: code,
                COL_DESC: text.removeprefix(prefix) if text.startswith(prefix) else text,
            }
        )
    if not rows:
        raise RuntimeError("El codebook HS no trajo ningún código de 2/4/6 dígitos")
    return pd.DataFrame(rows).sort_values(COL_HS, ignore_index=True)


def fetch_hs_reference() -> dict[str, Any]:
    """Descarga el codebook HS oficial de Comtrade (sin API key).

    Raises:
        RuntimeError: si la respuesta no es HTTP 200.
    """
    response = requests.get(config.COMTRADE_HS_REFERENCE_URL, timeout=_TIMEOUT_S)
    if response.status_code != 200:
        raise RuntimeError(f"Codebook HS respondió HTTP {response.status_code}")
    payload: dict[str, Any] = response.json()
    return payload


def refresh_hs_reference() -> pd.DataFrame:
    """Descarga, normaliza y escribe el catálogo en ``config.HS_REFERENCE_CSV``."""
    catalog = parse_hs_reference(fetch_hs_reference())
    config.HS_REFERENCE_CSV.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(config.HS_REFERENCE_CSV, "wt", encoding="utf-8", newline="") as f:
        catalog.to_csv(f, index=False, lineterminator="\n")
    logger.info("Catálogo HS escrito en %s (%d códigos)", config.HS_REFERENCE_CSV, len(catalog))
    return catalog


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    refresh_hs_reference()
