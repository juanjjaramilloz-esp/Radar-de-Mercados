"""Lectura del Observatorio de subsectores: qué subsector es un producto y
cómo le va a Colombia en él.

Funciones puras sobre las tablas del Observatorio (construidas con los
microdatos del DANE y la correlativa partida → CIIU Rev. 4 A.C.): no hacen
I/O ni tocan la red. La app las llama con los DataFrames ya leídos.

Sobre el índice de Grubel-Lloyd: las tablas traen tres versiones porque
responden preguntas distintas. ``gl_partida_socio`` (pares partida × país) es
la exigente: mide comercio en los dos sentidos del mismo producto con el mismo
socio. ``gl_partida`` compara cada partida contra el mundo. ``gl_totales``, en
cambio, se calcula sobre los totales del subsector y **sesga al alza** —una
partida que solo se exporta compensa otra que solo se importa—, así que aquí
nunca se usa como resultado.
"""

from typing import Final

import pandas as pd

#: Columnas de las tablas del Observatorio (nombres en español: vienen así
#: desde el repositorio que las construye y no se renombran al leerlas).
COL_GROUP: Final = "ciiu4_grupo"
COL_HS4: Final = "hs4"
COL_YEAR: Final = "anio"
COL_SHARE: Final = "participacion"
COL_COUNTRY: Final = "pais"


def groups_for_product(hs4_map: pd.DataFrame, hs: str, min_share: float = 0.0) -> pd.DataFrame:
    """Grupos CIIU a los que pertenece un producto HS4, del que más pesa al que menos.

    Args:
        hs4_map: tabla larga HS4 × grupo con ``participacion`` (0 a 1).
        hs: código de producto; se usan sus primeros cuatro dígitos.
        min_share: participación mínima para incluir un grupo; 0 los incluye todos.

    Returns:
        DataFrame con una fila por grupo, ordenado por participación
        descendente. Vacío si el producto no está en la tabla.
    """
    hs4 = str(hs)[:4]
    filas = hs4_map[(hs4_map[COL_HS4] == hs4) & (hs4_map[COL_SHARE] >= min_share)]
    return filas.sort_values(COL_SHARE, ascending=False).reset_index(drop=True)


def series_for_group(indicadores: pd.DataFrame, group: str) -> pd.DataFrame:
    """Serie anual de un subsector, ordenada por año.

    Args:
        indicadores: tabla de indicadores por año y grupo CIIU.
        group: código del grupo (tres dígitos).

    Returns:
        DataFrame indexado por posición con los años en orden ascendente.
        Vacío si el grupo no aparece.
    """
    filas = indicadores[indicadores[COL_GROUP] == group]
    return filas.sort_values(COL_YEAR).reset_index(drop=True)


def partners_for_group(socios: pd.DataFrame, group: str, year: int, top: int = 8) -> pd.DataFrame:
    """Principales socios del subsector en un año, por comercio total.

    Args:
        socios: tabla de socios por año, grupo y país.
        group: código del grupo CIIU.
        year: año a mostrar.
        top: cuántos socios devolver.

    Returns:
        DataFrame con los ``top`` socios ordenados por comercio total
        descendente. Vacío si no hay datos de ese grupo y año.
    """
    filas = socios[(socios[COL_GROUP] == group) & (socios[COL_YEAR] == year)]
    return filas.nlargest(top, "total").reset_index(drop=True)


def highlights_for_group(partidas: pd.DataFrame, group: str, top: int = 5) -> pd.DataFrame:
    """Partidas que más pesan en el subsector, de mayor a menor.

    Args:
        partidas: tabla de partidas destacadas por grupo, con ``descripcion``.
        group: código del grupo CIIU.
        top: cuántas partidas devolver.

    Returns:
        DataFrame ordenado por comercio total descendente; vacío si el grupo
        no aparece.
    """
    filas = partidas[partidas[COL_GROUP] == group]
    return filas.nlargest(top, "total").reset_index(drop=True)


def latest_full_year(indicadores: pd.DataFrame, partial_years: set[int]) -> int | None:
    """Último año de la serie que no sea parcial.

    Un año en curso solo tiene algunos meses y no se compara con un año
    completo; la app lo marca en vez de esconderlo, pero los rankings de socios
    se muestran del último año completo.

    Args:
        indicadores: tabla de indicadores por año y grupo.
        partial_years: años que el Observatorio declara incompletos.

    Returns:
        El año más reciente disponible que no esté en ``partial_years``, o
        ``None`` si la tabla está vacía o todos los años son parciales.
    """
    anios = sorted(set(indicadores[COL_YEAR].astype(int)) - set(partial_years))
    return anios[-1] if anios else None
