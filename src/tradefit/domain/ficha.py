"""Ficha de operación: lo que Radar y el Observatorio saben de una exportación concreta.

Una operación es un producto a seis dígitos (HS6), un destino y, si la empresa
lo escribe, un precio pactado. La ficha junta cinco miradas que hoy viven en
fuentes separadas: el mercado de destino (ranking y proveedores, de Comtrade),
el acceso (arancel y acuerdo), el precio de referencia (lo que Colombia declaró
al exportar ese HS6 a ese destino, del DANE), el subsector y el lado importador.

Funciones puras sobre DataFrames ya leídos: sin I/O ni red, como el resto de
``domain/``. La app las llama y solo presenta.

**Confidencialidad.** La mediana de una celda mes × partida × país en los
microdatos es un solo registro, y un valor unitario calculado con un registro
es el precio de una empresa. Ningún valor unitario se publica con menos de
``OBSERVATORIO_MIN_REGISTROS`` registros: el Observatorio ya no entrega esos
meses y aquí se aplica el mismo umbral al año y a cada país.
"""

from dataclasses import dataclass
from typing import Final, Literal

import numpy as np
import pandas as pd

from tradefit.contracts import OBSERVATORIO_MIN_REGISTROS

#: Meses publicables necesarios para dibujar el rango habitual (percentiles).
MESES_MINIMOS_RANGO: Final = 4
#: Código Comtrade de Colombia en la tabla de competidores.
CODIGO_COLOMBIA: Final = "170"

Posicion = Literal["debajo", "dentro", "encima"]


def valor_unitario(
    valor: float, kg: float, registros: int, minimo: int = OBSERVATORIO_MIN_REGISTROS
) -> float | None:
    """US$ por kg, o ``None`` si no hay peso o hay muy pocos registros para publicarlo."""
    if registros < minimo or not kg or kg <= 0:
        return None
    return float(valor) / float(kg)


@dataclass(frozen=True)
class PrecioReferencia:
    """Precio de referencia de un HS6 hacia un destino en un año.

    Attributes:
        anio: año de referencia (el último completo).
        meses: meses publicables del año, con ``mes``, ``valor_unitario`` y
            ``registros``.
        p25, mediana, p75: percentiles de los valores unitarios mensuales;
            ``None`` si hay menos de ``MESES_MINIMOS_RANGO`` meses publicables.
        promedio: valor unitario del año completo (valor total / kg total), o
            ``None`` si no es publicable.
        registros: registros del año hacia ese destino.
        valor: valor FOB exportado en el año hacia ese destino.
        serie: valor unitario publicable de los tres años hasta ``anio``.
        otros_destinos: destinos que más compran ese HS6 en el año, con su
            valor unitario cuando es publicable.
    """

    anio: int
    meses: pd.DataFrame
    p25: float | None
    mediana: float | None
    p75: float | None
    promedio: float | None
    registros: int
    valor: float
    serie: pd.DataFrame
    otros_destinos: pd.DataFrame


def _exportaciones(anual: pd.DataFrame, hs6: str) -> pd.DataFrame:
    return anual[(anual["flujo"] == "X") & (anual["hs6"] == hs6)]


def precio_referencia(
    anual: pd.DataFrame,
    mensual: pd.DataFrame,
    hs6: str,
    pais: str,
    anio: int,
    top_otros: int = 4,
    minimo: int = OBSERVATORIO_MIN_REGISTROS,
) -> PrecioReferencia:
    """Arma el precio de referencia de ``hs6`` hacia ``pais`` en ``anio``."""
    meses = (
        mensual[
            (mensual["hs6"] == hs6)
            & (mensual["pais"] == pais)
            & (mensual["anio"] == anio)
            & (mensual["registros"] >= minimo)
        ][["mes", "valor_unitario", "registros"]]
        .sort_values("mes")
        .reset_index(drop=True)
    )
    p25 = mediana = p75 = None
    if len(meses) >= MESES_MINIMOS_RANGO:
        p25, mediana, p75 = (float(v) for v in np.percentile(meses["valor_unitario"], [25, 50, 75]))

    x = _exportaciones(anual, hs6)
    destino = x[x["pais"] == pais]
    fila = destino[destino["anio"] == anio]
    valor = float(fila["valor"].sum())
    registros = int(fila["registros"].sum())
    promedio = valor_unitario(valor, float(fila["kg"].sum()), registros, minimo)

    serie = destino[destino["anio"].between(anio - 2, anio)].sort_values("anio")
    serie = pd.DataFrame(
        {
            "anio": serie["anio"].astype(int).to_numpy(),
            "valor_unitario": [
                valor_unitario(v, k, r, minimo)
                for v, k, r in zip(serie["valor"], serie["kg"], serie["registros"], strict=True)
            ],
        }
    )

    otros = x[(x["anio"] == anio) & (x["pais"] != pais)].nlargest(top_otros, "valor")
    otros_destinos = pd.DataFrame(
        {
            "pais": otros["pais"].to_numpy(),
            "valor": otros["valor"].to_numpy(),
            "registros": otros["registros"].to_numpy(),
            "valor_unitario": [
                valor_unitario(v, k, r, minimo)
                for v, k, r in zip(otros["valor"], otros["kg"], otros["registros"], strict=True)
            ],
        }
    )
    return PrecioReferencia(
        anio=anio,
        meses=meses,
        p25=p25,
        mediana=mediana,
        p75=p75,
        promedio=promedio,
        registros=registros,
        valor=valor,
        serie=serie,
        otros_destinos=otros_destinos,
    )


def posicion_precio(precio: float | None, p25: float | None, p75: float | None) -> Posicion | None:
    """Dónde cae el precio pactado frente al rango habitual (percentiles 25 a 75)."""
    if precio is None or precio <= 0 or p25 is None or p75 is None:
        return None
    if precio < p25:
        return "debajo"
    if precio > p75:
        return "encima"
    return "dentro"


@dataclass(frozen=True)
class Proveedores:
    """De dónde importa Colombia un HS6: total, principales orígenes y concentración."""

    total: float
    tabla: pd.DataFrame
    hhi: float | None


def proveedores_colombia(
    anual: pd.DataFrame,
    hs6: str,
    anio: int,
    top: int = 5,
    minimo: int = OBSERVATORIO_MIN_REGISTROS,
) -> Proveedores:
    """Importaciones colombianas del HS6 en el año por país de origen.

    El HHI se calcula sobre todos los orígenes, no solo los que se muestran.
    """
    m = anual[(anual["flujo"] == "M") & (anual["hs6"] == hs6) & (anual["anio"] == anio)]
    total = float(m["valor"].sum())
    if total <= 0:
        vacia = pd.DataFrame(columns=["pais", "valor", "cuota", "valor_unitario", "registros"])
        return Proveedores(total=0.0, tabla=vacia, hhi=None)
    cuotas = m["valor"] / total
    hhi = float((cuotas**2).sum())
    top_m = m.nlargest(top, "valor")
    tabla = pd.DataFrame(
        {
            "pais": top_m["pais"].to_numpy(),
            "valor": top_m["valor"].to_numpy(),
            "cuota": (top_m["valor"] / total).to_numpy(),
            "registros": top_m["registros"].to_numpy(),
            "valor_unitario": [
                valor_unitario(v, k, r, minimo)
                for v, k, r in zip(top_m["valor"], top_m["kg"], top_m["registros"], strict=True)
            ],
        }
    )
    return Proveedores(total=total, tabla=tabla, hhi=hhi)


def proveedores_destino(competitors: pd.DataFrame, iso3: str, top: int = 5) -> pd.DataFrame:
    """Principales proveedores del destino en el último año, con Colombia siempre visible.

    Si Colombia no está entre los ``top``, se agrega al final con su posición
    real, para que la ficha diga dónde está aunque no sea de los primeros.
    """
    c = competitors[competitors["country_iso3"] == iso3]
    if c.empty:
        return c.assign(es_colombia=pd.Series(dtype=bool))
    c = c[c["year"] == c["year"].max()].sort_values("supplier_rank")
    c = c.assign(es_colombia=c["partner_code"].astype(str) == CODIGO_COLOMBIA)
    primeros = c.head(top)
    if not primeros["es_colombia"].any():
        primeros = pd.concat([primeros, c[c["es_colombia"]]])
    return pd.DataFrame(primeros.reset_index(drop=True))


@dataclass(frozen=True)
class Arancel:
    """Arancel que enfrenta Colombia en una subpartida: tasa (fracción), tipo y año del dato."""

    arancel: float
    tipo: Literal["PREF", "MFN"]
    anio: int


def arancel_subpartida(tariff_profile: pd.DataFrame, iso3: str, hs6: str) -> Arancel | None:
    """Arancel que enfrenta Colombia en ``hs6`` en el destino: preferencial si hay, si no NMF.

    Returns:
        El dato más reciente del tipo elegido, o ``None`` si WITS no reporta
        esa subpartida para el destino.
    """
    t = tariff_profile[
        (tariff_profile["country_iso3"] == iso3) & (tariff_profile["cmd_code"].astype(str) == hs6)
    ]
    if t.empty:
        return None
    tipo: Literal["PREF", "MFN"] = "PREF" if (t["tariff_type"] == "PREF").any() else "MFN"
    fila = t[t["tariff_type"] == tipo].sort_values("year").iloc[-1]
    return Arancel(arancel=float(fila["tariff_faced"]), tipo=tipo, anio=int(fila["year"]))


def subpartidas_exportadas(anual: pd.DataFrame, hs4: str, anio: int) -> pd.DataFrame:
    """HS6 del HS4 que Colombia exportó en el año, de mayor a menor valor."""
    x = anual[(anual["flujo"] == "X") & (anual["hs6"].str[:4] == hs4) & (anual["anio"] == anio)]
    return x.groupby("hs6")["valor"].sum().sort_values(ascending=False).reset_index()


def destino_en_subsector(
    socios: pd.DataFrame, grupo: str, pais: str, anio: int
) -> dict[str, float] | None:
    """Comercio del subsector con el destino: exportaciones, importaciones, cuota y GL.

    La tabla de socios del Observatorio trae los principales socios de cada
    subsector; si el destino no está entre ellos devuelve ``None`` en lugar de
    inventar un cero.
    """
    s = socios[
        (socios["ciiu4_grupo"] == grupo) & (socios["anio"] == anio) & (socios["pais"] == pais)
    ]
    if s.empty:
        return None
    fila = s.iloc[0]
    return {
        "X": float(fila["X"]),
        "M": float(fila["M"]),
        "cuota_x": float(fila["cuota_x"]),
        "gl_partida": float(fila["gl_partida"]),
    }
