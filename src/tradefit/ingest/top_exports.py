"""Top de exportaciones del origen por partida HS4 (UN Comtrade).

Deriva la lista curada de productos del desplegable de la app
(``config.PRODUCTS``): exportaciones anuales del origen a nivel de partida
HS4 (``cmdCode=AG4``, flujo X, partner World) del año ``config.BASKET_YEAR``,
excluyendo los capítulos minero-energéticos
(``config.NON_MINING_EXCLUDED_CHAPTERS``). No es parte del pipeline: se corre
a mano para regenerar/verificar la lista cuando cambie el año de referencia:

    python -m tradefit.ingest.top_exports
"""

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from tradefit import config, hs_codes
from tradefit.hs_codes import COL_DESC, COL_HS

# Reuso intra-capa: el request con retry/caché es idéntico al del resto de
# consultas Comtrade; no se duplica la lógica de red.
from tradefit.ingest.comtrade import _BASE_PARAMS, _fetch_records, _load_cached

logger = logging.getLogger(__name__)

#: Columna del valor exportado anual en USD.
COL_EXPORTS: str = "exports_usd"


def fetch_top_exports() -> dict[str, Any]:
    """Descarga las exportaciones del origen por partida HS4, en un request.

    Consulta: reporter = ``config.ORIGIN_COMTRADE_CODE``, flujo X, partner
    World, ``cmdCode=AG4`` (todas las partidas de 4 dígitos), año
    ``config.BASKET_YEAR``. Con key autenticada la respuesta (~1 200 filas)
    entra en un request; sin key el preview truncaría y ``_fetch_records``
    falla ruidosamente.

    Returns:
        Payload JSON con la clave ``data``.

    Raises:
        RuntimeError: si la API responde con error o truncamiento.
    """
    params = _BASE_PARAMS | {
        "reporterCode": str(config.ORIGIN_COMTRADE_CODE),
        "period": str(config.BASKET_YEAR),
        "cmdCode": config.COMTRADE_CMD_ALL_HS4,
        "flowCode": "X",
    }
    label = f"exportaciones HS4 del origen {config.BASKET_YEAR}"
    return {"data": _fetch_records(params, label)}


def parse_top_exports(
    payload: dict[str, Any],
    exclude_chapters: frozenset[str] = config.NON_MINING_EXCLUDED_CHAPTERS,
) -> pd.DataFrame:
    """Normaliza el payload al ranking de partidas HS4 por valor exportado.

    Conserva solo códigos numéricos de 4 dígitos (descarta agregados como
    ``TOTAL``), suma ``primaryValue`` por partida (por si la fuente parte una
    partida en varios registros) y descarta los capítulos de
    ``exclude_chapters``. Orden: valor descendente, código como desempate
    (determinístico).

    Args:
        payload: JSON crudo de Comtrade con la clave ``data``.
        exclude_chapters: capítulos HS2 a excluir (default: minero-energéticos,
            ver ``config.NON_MINING_EXCLUDED_CHAPTERS``).

    Returns:
        DataFrame con columnas ``hs_code`` y ``exports_usd``, ordenado desc.

    Raises:
        RuntimeError: si el payload no trae ``data`` o no queda ninguna
            partida HS4 tras filtrar.
    """
    records = payload.get("data")
    if records is None:
        raise RuntimeError(f"Payload de Comtrade sin clave 'data'; claves: {sorted(payload)}")
    rows: list[dict[str, object]] = []
    for record in records:
        code = str(record.get("cmdCode", ""))
        if len(code) != 4 or not code.isdigit() or code[:2] in exclude_chapters:
            continue
        rows.append({COL_HS: code, COL_EXPORTS: float(record.get("primaryValue") or 0.0)})
    if not rows:
        raise RuntimeError("Comtrade no trajo partidas HS4 de exportación del origen")
    totals = pd.DataFrame(rows).groupby(COL_HS)[COL_EXPORTS].sum().reset_index()
    return totals.sort_values([COL_EXPORTS, COL_HS], ascending=[False, True], ignore_index=True)


def load_top_exports(cache_file: Path | None = None, force: bool = False) -> pd.DataFrame:
    """Carga el top de exportaciones HS4, descargando solo si no hay caché.

    Args:
        cache_file: ruta del JSON crudo; default:
            ``config.comtrade_top_exports_cache()``.
        force: si es True, re-descarga aunque exista caché.

    Returns:
        DataFrame de :func:`parse_top_exports`.
    """
    cache = cache_file or config.comtrade_top_exports_cache()
    return _load_cached(
        cache,
        fetch_top_exports,
        parse_top_exports,
        force,
        source="un_comtrade_top_exports_hs4",
        parameters={"origin": config.ORIGIN_ISO3, "year": config.BASKET_YEAR},
    )


def _print_top(n: int = 20) -> None:
    """Imprime el top-N con descripción del catálogo local (para curar PRODUCTS)."""
    top = load_top_exports().head(n)
    try:
        catalog = hs_codes.load_hs_reference().set_index(COL_HS)[COL_DESC]
    except FileNotFoundError:
        catalog = pd.Series(dtype=str)
    for position, row in enumerate(top.itertuples(index=False), start=1):
        hs = str(getattr(row, COL_HS))
        value = float(getattr(row, COL_EXPORTS))
        description = str(catalog.get(hs, "—"))
        print(f"{position:2d}. {hs}  {value / 1e6:10,.1f} MUSD  {description}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    _print_top()
