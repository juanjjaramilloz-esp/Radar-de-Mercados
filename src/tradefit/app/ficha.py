"""Página «Ficha de operación»: una exportación concreta, explicada con datos públicos.

La empresa elige producto, subpartida y destino, y si quiere escribe cantidad y
precio pactado. La página junta en bloques lo que Radar (Comtrade, WITS, Banco
Mundial) y el Observatorio (microdatos del DANE) saben de esa operación. Cada
bloque dice de dónde sale su dato, de qué período es y con qué versión.

Presentación pura: las cifras salen de ``domain/ficha.py`` y de las tablas ya
versionadas; lo que escribe la empresa vive solo en la sesión y no se guarda.
"""

import json
import math
from datetime import date
from typing import Final

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from tradefit import config, hs_codes
from tradefit.app import i18n, paises
from tradefit.app.flags import flag_emoji
from tradefit.app.i18n import t
from tradefit.app.main import (
    _about_sidebar,
    _hs_catalog,
    _load_competitors,
    _load_snapshot,
    _load_subsector_tables,
    _load_tariff_profile,
    _localize_country_names,
    _observatorio_meta,
    _partial_years,
    _read_parquet,
    _sidebar_toggle_css,
)
from tradefit.contracts import OBSERVATORIO_MIN_REGISTROS
from tradefit.domain import ficha, subsector

VUCE_URL: Final = "https://www.vuce.gov.co"
DIAN_ARANCEL_URL: Final = "https://muisca.dian.gov.co/WebArancel/DefMenuConsultas.faces"
INCOTERMS: Final = ("EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP")
_MESES_ES: Final = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)
_MESES_EN: Final = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def _ficha_tables() -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Tablas del Observatorio para la ficha, o ``None`` si el paquete no las trae."""
    anual, mensual = config.ficha_anual_parquet(), config.ficha_mensual_parquet()
    if not anual.exists() or not mensual.exists():
        return None
    return _read_parquet(anual), _read_parquet(mensual)


def _observatorio_commit() -> str:
    """Commit del Observatorio que produjo el paquete (siete caracteres), o «—»."""
    ruta = config.observatorio_manifest_json()
    if not ruta.exists():
        return "—"
    parametros = json.loads(ruta.read_text(encoding="utf-8")).get("parameters", {})
    commit = parametros.get("commit") if isinstance(parametros, dict) else None
    return str(commit)[:7] if commit else "—"


def _pais(iso3: str, nombres: dict[str, str]) -> str:
    """Bandera y nombre del país en el idioma activo; sirve para cualquier socio, no solo los 26."""
    respaldo = nombres.get(iso3) or paises.nombre(iso3, i18n.get_language()) or iso3
    nombre = i18n.country_name(iso3, respaldo) if iso3 in nombres else respaldo
    return f"{flag_emoji(iso3)} {nombre}".strip()


def _usd_kg(valor: float | None) -> str:
    return "—" if valor is None or pd.isna(valor) else i18n.fmt_number(float(valor), 2)


def _pie(texto: str) -> None:
    st.caption(f"`{texto}`")


def _hs6_label(hs6: str, catalogo: pd.DataFrame, valor: float) -> str:
    """«3808.92 · Fungicides (USD 42 M)»: código, descripción del catálogo y valor exportado."""
    desc = catalogo.loc[catalogo[hs_codes.COL_HS] == hs6, hs_codes.COL_DESC]
    nombre = str(desc.iloc[0]) if not desc.empty else ""
    corto = nombre if len(nombre) <= 60 else nombre[:57] + "…"
    return f"{hs6[:4]}.{hs6[4:]} · {corto} ({i18n.fmt_usd_compact(valor)})"


def _operacion(
    anual: pd.DataFrame, anio: int, ranking: pd.DataFrame, hs: str
) -> tuple[str, str, float, float] | None:
    """Formulario de la operación. Devuelve (hs6, destino, kg, precio) o ``None``."""
    catalogo = _hs_catalog()
    subpartidas = ficha.subpartidas_exportadas(anual, hs, anio)
    if subpartidas.empty:
        st.warning(t("ficha_no_hs6", hs=hs, year=anio))
        return None
    opciones_hs6 = dict(zip(subpartidas["hs6"], subpartidas["valor"], strict=True))
    pedido_hs6 = st.query_params.get("hs6")
    indice_hs6 = list(opciones_hs6).index(pedido_hs6) if pedido_hs6 in opciones_hs6 else 0

    nombres = dict(zip(ranking[config.COL_COUNTRY], ranking[config.COL_COUNTRY_NAME], strict=True))
    destinos = ranking.sort_values(config.COL_RANK)[config.COL_COUNTRY].tolist()
    pedido_pais = st.query_params.get("pais")
    indice_pais = destinos.index(pedido_pais) if pedido_pais in destinos else 0

    with st.container(border=True):
        col_hs6, col_pais = st.columns([3, 2])
        hs6 = col_hs6.selectbox(
            t("ficha_hs6_label"),
            options=list(opciones_hs6),
            index=indice_hs6,
            format_func=lambda c: _hs6_label(c, catalogo, opciones_hs6[c]),
            help=t("ficha_hs6_help", year=anio),
        )
        destino = col_pais.selectbox(
            t("ficha_destination_label"),
            options=destinos,
            index=indice_pais,
            format_func=lambda c: _pais(c, nombres),
        )
        col_kg, col_precio, col_inco, col_fecha, col_total = st.columns(5)
        kg = col_kg.number_input(t("ficha_quantity_label"), min_value=0.0, value=0.0, step=1000.0)
        precio = col_precio.number_input(
            t("ficha_price_label"), min_value=0.0, value=0.0, step=0.1, format="%.2f"
        )
        col_inco.selectbox(t("ficha_incoterm_label"), options=INCOTERMS, index=1)
        col_fecha.date_input(t("ficha_date_label"), value=None, min_value=date.today())
        col_total.metric(
            t("ficha_total_label"),
            f"US$ {i18n.fmt_number(kg * precio, 0)}" if kg and precio else "—",
        )
        st.caption(t("ficha_privacy_note"))
    st.query_params.update({"hs": hs, "hs6": hs6, "pais": destino})
    return hs6, destino, float(kg), float(precio)


def _numeros(ranking: pd.DataFrame, destino: str) -> dict[str, float | None]:
    """Fila del destino en el ranking como números de Python; ``None`` donde no hay dato."""
    fila = ranking[ranking[config.COL_COUNTRY] == destino].iloc[0].to_dict()
    numeros = {
        str(col): float(v)
        for col, v in fila.items()
        if isinstance(v, int | float | np.integer | np.floating) and not isinstance(v, bool)
    }
    return {col: (None if math.isnan(v) else v) for col, v in numeros.items()}


def _bloque_mercado(
    ranking: pd.DataFrame, meta: dict[str, object], hs: str, destino: str, nombres: dict[str, str]
) -> None:
    fila = _numeros(ranking, destino)
    rank, share = fila[config.COL_RANK] or 0.0, fila[config.COL_SHARE] or 0.0
    st.markdown(f"#### {t('ficha_market_header')}")
    st.markdown(
        t(
            "ficha_market_headline",
            country=_pais(destino, nombres),
            rank=int(rank),
            n=len(ranking),
            share=i18n.fmt_pct(share),
        )
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("ficha_market_size"), i18n.fmt_usd_compact(fila[config.COL_MARKET_SIZE] or 0.0))
    c2.metric(t("ficha_market_growth"), i18n.fmt_pct(fila[config.COL_GROWTH] or 0.0, signed=True))
    tendencia = fila.get(config.COL_SHARE_TREND)
    c3.metric(
        t("ficha_market_share"),
        i18n.fmt_pct(share),
        delta=None
        if tendencia is None
        else t("ficha_pp", value=i18n.fmt_number(tendencia * 100, 1, signed=True)),
    )
    c4.metric(t("ficha_market_stability"), i18n.fmt_number(fila[config.COL_STABILITY] or 0.0, 2))
    competidores = _load_competitors(hs)
    if competidores is not None:
        prov = ficha.proveedores_destino(competidores, destino)
        if not prov.empty:
            anio = int(prov["year"].iloc[0])
            st.caption(t("ficha_market_suppliers", year=anio))
            for _, p in prov.iterrows():
                nombre = f"**{p['partner_name']}**" if p["es_colombia"] else str(p["partner_name"])
                cuota = float(p["supplier_share"])
                st.progress(
                    min(cuota, 1.0),
                    text=f"{int(p['supplier_rank'])}. {nombre} · {i18n.fmt_pct(cuota)}",
                )
    st.caption(t("ficha_market_note"))
    _pie(
        t(
            "ficha_market_source",
            hs=hs,
            min_year=meta["data_year_min"],
            max_year=meta["data_year_max"],
        )
    )


def _bloque_acceso(ranking: pd.DataFrame, hs: str, hs6: str, destino: str) -> None:
    fila = _numeros(ranking, destino)
    st.markdown(f"#### {t('ficha_access_header')}")
    acuerdo = i18n.trade_agreement(destino)
    st.markdown(
        t("ficha_access_agreement", agreement=acuerdo)
        if acuerdo
        else t("ficha_access_no_agreement")
    )
    perfil = _load_tariff_profile(hs)
    arancel = ficha.arancel_subpartida(perfil, destino, hs6) if perfil is not None else None
    c1, c2, c3 = st.columns(3)
    if arancel is not None:
        tipo = t("ficha_tariff_pref") if arancel.tipo == "PREF" else t("ficha_tariff_mfn")
        c1.metric(
            t("ficha_tariff_hs6", hs6=f"{hs6[:4]}.{hs6[4:]}"),
            i18n.fmt_pct(arancel.arancel, 2),
            delta=f"{tipo}, {arancel.anio}",
            delta_color="off",
        )
    else:
        c1.metric(t("ficha_tariff_hs6", hs6=f"{hs6[:4]}.{hs6[4:]}"), "—")
    tarifa = fila.get(config.COL_TARIFF)
    c2.metric(t("ficha_tariff_avg"), "—" if tarifa is None else i18n.fmt_pct(tarifa, 2))
    margen = fila.get(config.COL_PREF_MARGIN)
    # + 0.0 convierte el −0,00 de un margen diminuto negativo en 0,00.
    puntos = None if margen is None else round(margen * 100, 2) + 0.0
    c3.metric(
        t("ficha_pref_margin"),
        "—" if puntos is None else t("ficha_pp", value=i18n.fmt_number(puntos, 2)),
    )
    if arancel is not None:
        st.warning(t("ficha_tariff_warning", year=arancel.anio))
    distancia = fila.get(config.COL_DISTANCE_KM)
    if distancia is not None:
        st.caption(t("ficha_distance", km=i18n.fmt_number(distancia, 0)))
    _pie(t("ficha_access_source"))


def _grafico_precio(precio_ref: ficha.PrecioReferencia, precio: float) -> None:
    meses = _MESES_EN if i18n.get_language() == "en" else _MESES_ES
    m = precio_ref.meses
    fig = go.Figure()
    if precio_ref.p25 is not None and precio_ref.p75 is not None:
        fig.add_hrect(
            y0=precio_ref.p25,
            y1=precio_ref.p75,
            fillcolor="#6494ff",
            opacity=0.18,
            line_width=0,
            annotation_text=t("ficha_price_band"),
            annotation_position="top left",
        )
        fig.add_hline(y=precio_ref.mediana, line_dash="dot", line_color="#1a56db", line_width=1)
    fig.add_trace(
        go.Scatter(
            x=[meses[int(i) - 1] for i in m["mes"]],
            y=m["valor_unitario"],
            mode="markers+lines",
            line={"color": "#6494ff", "width": 1},
            marker={"size": 9, "color": "#1a56db"},
            customdata=m["registros"],
            hovertemplate="%{x}: %{y:.2f} USD/kg · %{customdata} "
            + t("ficha_records")
            + "<extra></extra>",
            name=t("ficha_price_monthly"),
        )
    )
    if precio > 0:
        fig.add_hline(
            y=precio,
            line_color="#a4560a",
            line_width=3,
            annotation_text=t("ficha_price_yours", price=i18n.fmt_number(precio, 2)),
            annotation_position="bottom right",
        )
    fig.update_layout(
        height=300,
        margin={"l": 10, "r": 10, "t": 20, "b": 10},
        yaxis_title="USD/kg",
        showlegend=False,
        separators=i18n.active_plotly_separators(),
        xaxis={"categoryorder": "array", "categoryarray": list(meses)},
    )
    st.plotly_chart(fig, use_container_width=True)


def _bloque_precio(
    anual: pd.DataFrame,
    mensual: pd.DataFrame,
    hs6: str,
    destino: str,
    anio: int,
    precio: float,
    nombres: dict[str, str],
) -> None:
    st.markdown(f"#### {t('ficha_price_header')}")
    ref = ficha.precio_referencia(anual, mensual, hs6, destino, anio)
    pais = _pais(destino, nombres)
    if ref.promedio is None:
        st.info(t("ficha_price_hidden", country=pais, year=anio, n=OBSERVATORIO_MIN_REGISTROS))
        _pie(t("ficha_price_source", hs6=hs6, year=anio, commit=_observatorio_commit()))
        return
    posicion = ficha.posicion_precio(precio, ref.p25, ref.p75)
    if precio <= 0:
        st.markdown(t("ficha_price_prompt", country=pais, year=anio))
    elif posicion is None:
        st.markdown(t("ficha_price_no_band", price=i18n.fmt_number(precio, 2)))
    else:
        diferencia = precio / ref.promedio - 1
        texto = t(f"ficha_price_{posicion}")
        st.markdown(
            t(
                "ficha_price_headline",
                price=i18n.fmt_number(precio, 2),
                position=f":{'green' if posicion == 'dentro' else 'orange'}-background[{texto}]",
                country=pais,
                year=anio,
                diff=i18n.fmt_pct(diferencia, 1, signed=True),
            )
        )
    if ref.meses.empty:
        st.caption(t("ficha_price_no_months"))
    else:
        _grafico_precio(ref, precio)
    c1, c2, c3 = st.columns(3)
    c1.metric(
        t("ficha_price_avg", year=anio),
        f"{_usd_kg(ref.promedio)} USD/kg",
        delta=t("ficha_price_records", n=i18n.fmt_number(ref.registros, 0)),
        delta_color="off",
    )
    serie = " → ".join(_usd_kg(v) for v in ref.serie["valor_unitario"])
    c2.metric(
        t("ficha_price_trend", years="–".join(str(a) for a in ref.serie["anio"])),
        serie or "—",
    )
    otros = " · ".join(
        f"{_pais(p, nombres)} {_usd_kg(v)}"
        for p, v in zip(
            ref.otros_destinos["pais"], ref.otros_destinos["valor_unitario"], strict=True
        )
    )
    c3.markdown(f"**{t('ficha_price_others')}**  \n{otros or '—'}")
    st.caption(t("ficha_price_note", n=OBSERVATORIO_MIN_REGISTROS))
    _pie(t("ficha_price_source", hs6=hs6, year=anio, commit=_observatorio_commit()))


def _bloque_subsector(hs: str, destino: str, anio: int, nombres: dict[str, str]) -> None:
    st.markdown(f"#### {t('ficha_subsector_header')}")
    tablas = _load_subsector_tables()
    if tablas is None:
        st.caption(t("ficha_subsector_missing"))
        return
    grupos = subsector.groups_for_product(tablas["hs4"], hs)
    if grupos.empty:
        st.caption(t("subsector_no_match"))
        return
    grupo = str(grupos[subsector.COL_GROUP].iloc[0])
    serie = subsector.series_for_group(tablas["indicadores"], grupo)
    fila = serie[serie[subsector.COL_YEAR] == anio]
    nombre = subsector.group_name(tablas["indicadores"], grupo)
    st.markdown(t("ficha_subsector_headline", group=grupo, name=nombre))
    if not fila.empty:
        f = fila.iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric(t("subsector_kpi_x"), i18n.fmt_usd_compact(float(f["X"])))
        c2.metric(t("subsector_kpi_m"), i18n.fmt_usd_compact(float(f["M"])))
        c3.metric(
            t("subsector_kpi_balance"),
            i18n.fmt_usd_compact(abs(float(f["balanza"]))),
            delta=t("subsector_surplus") if float(f["balanza"]) >= 0 else t("subsector_deficit"),
            delta_color="normal" if float(f["balanza"]) >= 0 else "inverse",
        )
    socio = ficha.destino_en_subsector(tablas["socios"], grupo, destino, anio)
    pais = _pais(destino, nombres)
    if socio is None:
        st.caption(t("ficha_subsector_not_top", country=pais))
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric(
            t("ficha_subsector_to", country=pais),
            i18n.fmt_usd_compact(socio["X"]),
            delta=t("ficha_subsector_share", share=i18n.fmt_pct(socio["cuota_x"])),
            delta_color="off",
        )
        c2.metric(t("ficha_subsector_from", country=pais), i18n.fmt_usd_compact(socio["M"]))
        c3.metric(t("ficha_subsector_gl"), i18n.fmt_number(socio["gl_partida"], 3))
    _pie(t("ficha_subsector_source", year=anio))


def _bloque_importacion(anual: pd.DataFrame, hs6: str, anio: int, nombres: dict[str, str]) -> None:
    st.markdown(f"#### {t('ficha_import_header')}")
    prov = ficha.proveedores_colombia(anual, hs6, anio)
    if prov.total <= 0:
        st.caption(t("ficha_import_none", hs6=hs6, year=anio))
        return
    hhi = prov.hhi if prov.hhi is not None else 0.0
    concentracion = t("ficha_import_concentrated") if hhi > 0.25 else t("ficha_import_diversified")
    st.markdown(
        t(
            "ficha_import_headline",
            total=i18n.fmt_usd_compact(prov.total),
            year=anio,
            concentration=concentracion,
            hhi=i18n.fmt_number(hhi, 3),
        )
    )
    for _, p in prov.tabla.iterrows():
        vu = _usd_kg(p["valor_unitario"])
        cuota = float(p["cuota"])
        st.progress(
            min(cuota, 1.0),
            text=f"{_pais(str(p['pais']), nombres)} · {i18n.fmt_pct(cuota)} · {vu} USD/kg",
        )
    st.caption(t("ficha_import_note", n=OBSERVATORIO_MIN_REGISTROS))
    _pie(t("ficha_import_source", hs6=hs6, year=anio))


def _bloque_documentos(destino: str) -> None:
    st.markdown(f"#### {t('ficha_docs_header')}")
    acuerdo = i18n.trade_agreement(destino)
    documentos = [
        ("ficha_doc_invoice", "ficha_doc_always", "ficha_doc_company"),
        ("ficha_doc_packing", "ficha_doc_always", "ficha_doc_company"),
        ("ficha_doc_dex", "ficha_doc_always", "ficha_doc_broker"),
        ("ficha_doc_product", "ficha_doc_vuce", "ficha_doc_company"),
        ("ficha_doc_destination", "ficha_doc_destination_why", "ficha_doc_importer"),
    ]
    if acuerdo:
        documentos.insert(3, ("ficha_doc_origin", "ficha_doc_origin_why", "ficha_doc_company"))
    listos = 0
    for clave, por_que, responsable in documentos:
        col_doc, col_por_que, col_quien = st.columns([2, 3, 2])
        marcado = col_doc.checkbox(t(clave), key=f"ficha_doc_{clave}")
        listos += int(marcado)
        col_por_que.caption(t(por_que, agreement=acuerdo or ""))
        col_quien.caption(t(responsable))
    st.markdown(t("ficha_docs_progress", done=listos, total=len(documentos)))
    st.caption(t("ficha_docs_note", vuce=VUCE_URL, dian=DIAN_ARANCEL_URL))


def page() -> None:
    """Renderiza la ficha de operación."""
    st.set_page_config(page_title=t("ficha_page_title"), page_icon="🧾", layout="wide")
    _sidebar_toggle_css()
    _about_sidebar()
    st.title(t("ficha_title"))
    st.caption(t("ficha_intro"))

    tablas = _ficha_tables()
    if tablas is None:
        st.warning(t("ficha_missing_package"))
        return
    anual, mensual = tablas
    parciales = _partial_years(_observatorio_meta())
    anios = sorted(set(anual["anio"].astype(int)) - parciales)
    if not anios:
        st.warning(t("ficha_missing_package"))
        return
    anio = anios[-1]

    productos = {
        hs: i18n.product_label(hs, label)
        for hs, label in config.PRODUCTS.items()
        if config.ranking_parquet(hs).exists()
    }
    pedido = st.query_params.get("hs")
    hs = st.selectbox(
        t("product_select_label"),
        options=list(productos),
        index=list(productos).index(pedido) if pedido in productos else 0,
        format_func=lambda c: productos[c],
    )
    try:
        ranking, meta, _ = _load_snapshot(hs)
    except Exception as exc:  # noqa: BLE001 — presentación: degradar con gracia
        st.error(t("snapshot_invalid_error", hs=hs, error=exc))
        return
    ranking = _localize_country_names(ranking)
    nombres = dict(zip(ranking[config.COL_COUNTRY], ranking[config.COL_COUNTRY_NAME], strict=True))

    operacion = _operacion(anual, anio, ranking, hs)
    if operacion is None:
        return
    hs6, destino, _kg, precio = operacion

    col_izq, col_der = st.columns(2, gap="large")
    with col_izq, st.container(border=True):
        _bloque_mercado(ranking, meta, hs, destino, nombres)
    with col_der, st.container(border=True):
        _bloque_acceso(ranking, hs, hs6, destino)
    with st.container(border=True):
        _bloque_precio(anual, mensual, hs6, destino, anio, precio, nombres)
    col_izq, col_der = st.columns(2, gap="large")
    with col_izq, st.container(border=True):
        _bloque_subsector(hs, destino, anio, nombres)
    with col_der, st.container(border=True):
        _bloque_importacion(anual, hs6, anio, nombres)
    with st.container(border=True):
        _bloque_documentos(destino)
    st.caption(t("ficha_footer", commit=_observatorio_commit(), hs=hs))
