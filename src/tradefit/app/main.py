"""App Streamlit del Radar de Mercados.

Capa de presentación: lee los snapshots de ``data/processed/`` y muestra;
nunca llama APIs ni importa ``ingest/``. Para las funciones interactivas
(simulador de prioridades, desglose, radar) invoca funciones **puras** de
``domain/`` sobre el snapshot ya leído (regla relajada 2026-07-07, ver
CLAUDE.md): toda fórmula vive y se testea en ``domain/``, la app no la
reimplementa. La única vía para construir datos nuevos sigue siendo
``pipeline.ensure_snapshot`` (buscador avanzado; la red vive en
``ingest/``). Si algo falla, degrada con gracia.
"""

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Final, cast

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from tradefit import config, hs_codes
from tradefit.app import i18n
from tradefit.app.export import ranking_to_excel, ranking_to_pdf
from tradefit.app.flags import flag_emoji
from tradefit.app.i18n import t
from tradefit.domain import scoring
from tradefit.domain.macro_filter import latest_indicator_value
from tradefit.pipeline.build_snapshot import ensure_snapshot

_PRODUCT_SELECT_KEY = "product_select"
#: Contenedor del selector de producto: la clave le da a Streamlit una clase
#: CSS propia (``st-key-<key>``) para resaltarlo sin afectar otros
#: selectbox de la app (buscador avanzado, foco, idioma).
_PRODUCT_SELECT_CONTAINER_KEY = "product_select_container"
_TOUR_SEEN_KEY = "tour_seen"
#: Estado del focus mode: el selectbox de la ficha es la fuente de verdad;
#: el mapa escribe en él (antes de instanciarlo) y un guard evita que la
#: selección vieja del mapa reimponga el foco tras «quitar foco».
_FOCUS_SELECT_KEY = "focus_market_select"
_MAP_KEY = "map_select"
_MAP_PROCESSED_KEY = "map_selection_processed"
_TABLE_KEY = "ranking_table_select"
_COMPARE_KEY = "compare_markets"
_TABLE_PROCESSED_KEY = "ranking_table_selection_processed"
#: Prefijos del panel «⚙️ Columnas»: cada columna tiene un checkbox
#: (``ranking_col_<nombre>``) y una clave de estado PROPIA
#: (``ranking_col_store_<nombre>``). El estado no puede vivir en el widget:
#: su etiqueta cambia con el idioma, eso recrea el widget y Streamlit
#: descartaría el valor — la clave propia sobrevive.
_COLUMN_TOGGLE_KEY_PREFIX = "ranking_col_"
_COLUMN_STORE_KEY_PREFIX = "ranking_col_store_"

#: Columnas del ranking visibles por defecto: un set compacto que cabe en
#: pantalla. El resto (ISO3, Δ cuota, acuerdo comercial, LPI, score bruto…)
#: se activa desde el popover «⚙️ Columnas»; ocultar es solo presentación —
#: los exports CSV/Excel/PDF llevan todas las columnas.
_DEFAULT_VISIBLE_COLUMNS: Final[tuple[str, ...]] = (
    config.COL_MARKET_SIZE,
    config.COL_GROWTH,
    config.COL_SHARE,
    config.COL_TARIFF,
    config.COL_STABILITY,
    config.COL_FINAL_SCORE,
)

#: Clave i18n de cada columna elegible del selector (las fijas — ranking y
#: mercado — no aparecen; ISO3 y tamaño de mercado se resuelven aparte en
#: ``_ranking_column_label``).
_RANKING_COLUMN_LABEL_KEYS: Final[dict[str, str]] = {
    config.COL_GROWTH: "col_growth",
    config.COL_SHARE: "col_share",
    config.COL_SHARE_TREND: "col_share_trend",
    config.COL_ORIGIN_EXPORT_SHARE: "col_origin_export_share",
    config.COL_COMPLEMENTARITY: "col_complementarity",
    config.COL_TARIFF: "col_tariff",
    config.COL_AGREEMENT: "col_agreement",
    config.COL_LPI: "col_lpi",
    config.COL_STABILITY: "col_stability",
    config.COL_SCORE: "col_score_raw",
    config.COL_FINAL_SCORE: "col_score_final",
}

#: Color de cada métrica en las gráficas de desglose (azules = demanda,
#: ámbar = posición del origen, verde = encaje, gris = fricción arancelaria).
_METRIC_COLORS: Final[dict[str, str]] = {
    "market_size": "#1D4ED8",
    "import_growth": "#60A5FA",
    "market_share": "#F59E0B",
    "share_trend": "#FCD34D",
    "complementarity": "#10B981",
    "tariff_faced": "#94A3B8",
}

#: Colores de los hasta 3 mercados del radar: misma familia cromática que el
#: resto de la app (azul/ámbar/verde) en lugar de la paleta default de plotly.
_RADAR_COLORS: Final[tuple[str, str, str]] = ("#1D4ED8", "#F59E0B", "#10B981")


def _radar_fill(hex_color: str) -> str:
    """Versión translúcida (rgba) de un color hex para el relleno del radar."""
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},0.18)"


def _hero_section() -> None:
    """Propuesta de valor y mini-tour: el usuario aterriza sin contexto.

    El expander del tour llega abierto solo en la primera carga de la sesión
    (``st.session_state``); después queda plegado y disponible.
    """
    st.markdown(
        t(
            "hero_value_prop",
            flag=flag_emoji(config.ORIGIN_ISO3),
            origin=config.ORIGIN_NAME,
        )
    )
    first_load = _TOUR_SEEN_KEY not in st.session_state
    st.session_state[_TOUR_SEEN_KEY] = True
    with st.expander(t("hero_tour_title"), expanded=first_load):
        st.markdown(t("hero_tour_body"))


def _product_select_css() -> None:
    """Resalta el selector de producto: es la acción primordial de la app.

    Streamlit da a ``st.container(key=...)`` una clase CSS propia
    (``st-key-<key>``, ver ``convertKeyToClassName`` en el frontend): el
    estilo queda acotado a este contenedor y no toca los demás selectbox
    de la página. Colores en rgba (no hex sólido) para funcionar igual en
    tema claro y oscuro, igual que el resaltado de foco de la tabla.
    """
    st.markdown(
        f"""
        <style>
        .st-key-{_PRODUCT_SELECT_CONTAINER_KEY} {{
            background-color: rgba(29, 78, 216, 0.12);
            border: 1px solid rgba(29, 78, 216, 0.4) !important;
            border-radius: 0.75rem;
            padding: 0.25rem 1rem 1rem 1rem;
        }}
        .st-key-{_PRODUCT_SELECT_CONTAINER_KEY} [data-testid="stWidgetLabel"] p {{
            font-size: 1.05rem;
            font-weight: 700;
        }}
        .st-key-{_PRODUCT_SELECT_CONTAINER_KEY} [data-baseweb="select"] > div {{
            background-color: rgba(29, 78, 216, 0.08);
            border-color: rgba(29, 78, 216, 0.55);
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _about_sidebar() -> None:
    """Tarjeta de credibilidad: qué es el proyecto, con qué está hecho y dónde vive."""
    i18n.language_toggle()
    with st.sidebar:
        st.header(t("about_header"))
        st.markdown(t("about_body"))
        st.caption(t("about_caption"))
        st.caption(t("about_epm_pitch"))


def _catalog_products() -> dict[str, str]:
    """Catálogo del desplegable: los 15 curados de ``config.PRODUCTS``.

    En el orden de ``config`` (valor exportado descendente) y con etiqueta
    en el idioma activo, tengan o no snapshot construido (si falta, se
    construye al seleccionarlo). El desplegable ya NO lista cualquier
    snapshot del disco: las partidas no curadas que construyó el buscador
    solo entran mientras sean la selección activa (``_selector_options``).
    """
    return {hs: i18n.product_label(hs, label) for hs, label in config.PRODUCTS.items()}


def _selector_options(catalog: dict[str, str]) -> dict[str, str]:
    """Opciones del selector: catálogo curado + la partida activa no curada.

    Una partida construida por el buscador (o llegada por ``?hs=``) no es
    parte del catálogo: entra al selector solo mientras sea la selección
    activa, con la etiqueta de su ``meta.json``.
    """
    options = dict(catalog)
    active = str(st.session_state.get(_PRODUCT_SELECT_KEY, ""))
    if active and active not in options:
        meta_path = config.snapshot_meta_json(active)
        if meta_path.exists():
            meta = _read_json(meta_path)
            options[active] = i18n.product_label(active, str(meta.get("hs_label", active)))
    return options


def _bridge_comtrade_key() -> None:
    """Copia ``COMTRADE_API_KEY`` de ``st.secrets`` al entorno si hace falta.

    En Streamlit Community Cloud los secretos llegan por ``st.secrets``, pero
    ``ingest/`` (capa de red) lee variables de entorno: este puente evita que
    la capa de datos conozca Streamlit. Sin secreto configurado, no hace nada.
    """
    load_dotenv()  # en local la key vive en .env; cargarla antes de chequear
    if os.environ.get(config.ENV_COMTRADE_KEY):
        return
    try:
        key = st.secrets[config.ENV_COMTRADE_KEY]
    except Exception:  # noqa: BLE001 — sin secrets.toml st.secrets lanza; es opcional
        return
    os.environ[config.ENV_COMTRADE_KEY] = str(key)


@st.cache_data
def _hs_catalog() -> pd.DataFrame:
    """Catálogo HS versionado, cacheado por sesión de la app."""
    return hs_codes.load_hs_reference()


def _build_on_demand(hs: str) -> bool:
    """Construye el snapshot de una partida nueva con feedback en pantalla.

    Returns:
        True si el snapshot quedó disponible; False si falló (el error ya se
        mostró al usuario — degradar con gracia, la app sigue viva).
    """
    _bridge_comtrade_key()
    if not os.environ.get(config.ENV_COMTRADE_KEY):
        st.warning(t("search_api_key_warning"))
    status = st.status(t("search_status_building", hs=hs), expanded=True)
    try:
        ensure_snapshot(
            hs, on_stage=lambda stage: status.write(f"▸ {i18n.translate_stage(stage)}…")
        )
    except ValueError as exc:
        status.update(label=t("search_status_invalid", error=exc), state="error")
        return False
    except Exception as exc:  # noqa: BLE001 — presentación: degradar con gracia
        status.update(label=t("search_status_failed", hs=hs), state="error")
        st.error(t("search_error_body", hs=hs, error=exc))
        return False
    status.update(label=t("search_status_done", hs=hs), state="complete", expanded=False)
    return True


def _advanced_search_section() -> None:
    """Buscador avanzado: cualquier partida HS → snapshot on-demand → análisis.

    El usuario escribe un código (2/4/6 dígitos) o palabras de la descripción
    (en inglés, idioma del catálogo de Comtrade); al confirmar, se descargan
    los datos de esa partida, se construye el snapshot y la app entera (ranking,
    gráficas, narrativa, export) pasa a mostrarla. Con caché: repetir una
    partida ya analizada es instantáneo.
    """
    with st.expander(t("search_expander_title")):
        query = st.text_input(
            t("search_input_label"),
            placeholder=t("search_input_placeholder"),
            help=t("search_input_help"),
        )
        if not query.strip():
            return
        selected: str | None = None
        try:
            matches = hs_codes.search_hs(query, _hs_catalog(), lang=i18n.get_language())
        except FileNotFoundError:
            matches = None  # sin catálogo local: se acepta el código a ciegas
        normalized = hs_codes.normalize_hs(query)
        if matches is not None and not matches.empty:
            labels = dict(zip(matches[hs_codes.COL_HS], matches[hs_codes.COL_DESC], strict=True))
            selected = st.selectbox(
                t("search_matches_label"),
                options=list(labels),
                format_func=lambda code: f"{code} — {labels[code]}",
            )
        elif hs_codes.is_valid_hs(normalized):
            selected = normalized
            st.caption(t("search_hs_not_in_catalog", hs=normalized))
        else:
            st.info(t("search_no_matches_info"))
            return
        if selected is None:
            return
        already_built = config.ranking_parquet(selected).exists()
        action = t("search_button_view") if already_built else t("search_button_download")
        go = st.button(action, type="primary", key="advanced_search_go")
        if go and (already_built or _build_on_demand(selected)):
            st.session_state[_PRODUCT_SELECT_KEY] = selected
            st.rerun()


def _sync_product_from_url() -> None:
    """Deep link: ``?hs=0901`` en la URL selecciona ese producto al cargar.

    Solo actúa en la primera carga de la sesión (después manda el selector) y
    solo si la partida es curada o ya tiene snapshot en disco; un ``hs``
    desconocido se ignora en silencio (degradar con gracia).
    """
    if _PRODUCT_SELECT_KEY in st.session_state:
        return
    url_hs = st.query_params.get("hs")
    if not url_hs:
        return
    normalized = hs_codes.normalize_hs(url_hs)
    if normalized in config.PRODUCTS or config.ranking_parquet(normalized).exists():
        st.session_state[_PRODUCT_SELECT_KEY] = normalized


@st.cache_data(show_spinner=False)
def _cached_parquet(path_str: str, mtime_ns: int) -> pd.DataFrame:
    """Lectura de parquet cacheada entre reruns (cada slider dispara uno).

    El ``mtime_ns`` del archivo forma parte de la clave de la caché: si
    ``ensure_snapshot`` reescribe el artefacto, el mtime cambia y la caché
    se invalida sola — no hay riesgo de servir un snapshot viejo.
    """
    return pd.read_parquet(path_str)


@st.cache_data(show_spinner=False)
def _cached_json(path_str: str, mtime_ns: int) -> dict[str, object]:
    """Lectura de JSON cacheada; misma invalidación por mtime que el parquet."""
    result: dict[str, object] = json.loads(Path(path_str).read_text(encoding="utf-8"))
    return result


def _read_parquet(path: Path) -> pd.DataFrame:
    """Parquet vía caché, con el mtime actual del archivo como clave."""
    return _cached_parquet(str(path), path.stat().st_mtime_ns)


def _read_json(path: Path) -> dict[str, object]:
    """JSON vía caché, con el mtime actual del archivo como clave."""
    return _cached_json(str(path), path.stat().st_mtime_ns)


def _load_snapshot(hs: str) -> tuple[pd.DataFrame, dict[str, object], dict[str, object]]:
    """Lee ranking, metadatos y narrativa del snapshot de un producto.

    Returns:
        Tupla (ranking, meta, narrative) leída de ``data/processed/<hs>/``.
        Si el snapshot no trae narrativa, ``narrative`` queda vacío y la app
        omite esa sección (degradar con gracia).

    Raises:
        FileNotFoundError: si el snapshot todavía no fue construido.
    """
    ranking = _read_parquet(config.ranking_parquet(hs))
    meta = _read_json(config.snapshot_meta_json(hs))
    narrative: dict[str, object] = {}
    if config.narrative_json(hs).exists():
        narrative = _read_json(config.narrative_json(hs))
    return ranking, meta, narrative


def _narrative_in_language(narrative: dict[str, object]) -> dict[str, object]:
    """Narrativa del idioma activo desde el ``narrative.json`` bilingüe.

    Snapshots anteriores al formato bilingüe traen las claves
    ``recommendations``/``markets`` en la raíz (solo español): se devuelven
    tal cual (degradar con gracia). Si falta el idioma pedido, cae al español.
    """
    if "recommendations" in narrative or "markets" in narrative:
        return narrative
    selected = narrative.get(i18n.get_language()) or narrative.get("es")
    return selected if isinstance(selected, dict) else {}


def _localize_country_names(ranking: pd.DataFrame) -> pd.DataFrame:
    """Reemplaza ``country_name`` por su versión en inglés si ese es el idioma activo.

    Los 18 destinos del MVP tienen nombre en inglés en
    ``config.DESTINATIONS_EN``; el resto de países (poco probable, pero
    posible si el catálogo crece) conserva el nombre ya presente.
    """
    if i18n.get_language() != "en":
        return ranking
    localized = ranking[config.COL_COUNTRY].combine(
        ranking[config.COL_COUNTRY_NAME],
        lambda iso3, name: i18n.country_name(iso3, name),
    )
    return ranking.assign(**{config.COL_COUNTRY_NAME: localized})


def _load_imports_timeseries(hs: str) -> pd.DataFrame | None:
    """Lee la serie anual de importaciones del producto, si el snapshot la trae.

    Snapshots generados antes de que este artefacto existiera no lo tienen:
    la app degrada con gracia omitiendo la pestaña de evolución.
    """
    path = config.imports_timeseries_parquet(hs)
    if not path.exists():
        return None
    return _read_parquet(path)


def _recommendations_section(narrative: dict[str, object]) -> None:
    """Top-N recomendado con el porqué (drivers del score, con números)."""
    recommendations = narrative.get("recommendations")
    if not isinstance(recommendations, list) or not recommendations:
        return
    st.subheader(t("recommendations_subheader"))
    for i, rec in enumerate(recommendations, start=1):
        reasons = " · ".join(rec["reasons"]) if rec["reasons"] else ""
        name = i18n.country_name(str(rec["iso3"]), str(rec["name"]))
        score_label = t("col_score_final").lower()
        score = i18n.fmt_number(float(rec["final_score"]), 3)
        st.markdown(f"**{i}. {name}** ({score_label} {score}) — {reasons}")


def _focus_header_metrics(ranking: pd.DataFrame, row: pd.Series, iso3: str) -> None:
    """Fila de métricas rápidas de la ficha (score, arancel+TLC, cuotas)."""
    col_score, col_tariff, col_share, col_origin = st.columns(4)
    col_score.metric(
        t("col_score_final"),
        i18n.fmt_number(float(row[config.COL_FINAL_SCORE]), 3),
        delta=t("focus_header_rank", rank=int(row[config.COL_RANK]), n=len(ranking)),
        delta_color="off",
    )
    tariff = row.get(config.COL_TARIFF)
    col_tariff.metric(
        t("col_tariff"),
        i18n.fmt_pct(float(tariff)) if pd.notna(tariff) else "—",
        delta=i18n.trade_agreement(iso3) or t("focus_no_agreement"),
        delta_color="off",
    )
    col_share.metric(
        t("col_share"),
        i18n.fmt_pct(float(row[config.COL_SHARE])),
        delta=(
            f"{i18n.fmt_pct(float(row[config.COL_SHARE_TREND]), signed=True)} "
            f"{t('focus_share_window')}"
        ),
        delta_color="off",
    )
    origin_share = row.get(config.COL_ORIGIN_EXPORT_SHARE)
    col_origin.metric(
        t("col_origin_export_share"),
        i18n.fmt_pct(float(origin_share)) if pd.notna(origin_share) else "—",
        delta=t("focus_origin_share_delta"),
        delta_color="off",
    )


def _focus_drivers_line(ranking: pd.DataFrame, meta: dict[str, object], iso3: str) -> None:
    """Los 2 mayores aportes peso×norm al score del mercado (domain puro)."""
    weights_obj = meta.get("weights")
    if not isinstance(weights_obj, dict):
        return
    weights = {
        name: float(str(value))
        for name, value in weights_obj.items()
        if scoring.METRIC_COLUMNS.get(str(name)) in ranking.columns
    }
    positive = {name: w for name, w in weights.items() if w > 0}
    if not positive:
        return
    contributions = scoring.score_contributions(ranking, positive)
    # cast: .loc con un solo índice devuelve la fila como Series (los stubs
    # de pandas no logran inferirlo).
    market_row = cast("pd.Series[float]", contributions.loc[iso3])
    top = market_row.nlargest(2)
    drivers = " · ".join(
        f"**{i18n.metric_label(str(name))}** ({i18n.fmt_number(float(value), 3)})"
        for name, value in top.items()
    )
    st.markdown(t("focus_drivers", drivers=drivers))


def _focus_macro_block(row: pd.Series, iso3: str) -> None:
    """Contexto macro del destino: último dato por indicador + LPI + estabilidad.

    Los valores salen del ``macro_context.parquet`` compartido; el «último
    año con dato» lo decide ``domain.macro_filter.latest_indicator_value``
    (puro, testeado) — la app solo formatea.
    """
    st.markdown(f"**{t('focus_macro_header')}**")
    lines: list[str] = []
    macro = _load_macro_context()
    if macro is not None:
        country_macro = macro[macro[config.COL_COUNTRY] == iso3]
        for indicator, label_key in (
            ("inflation", "macro_inflation"),
            ("gdp_growth", "macro_gdp_growth"),
            ("current_account", "macro_current_account"),
        ):
            values = latest_indicator_value(country_macro, indicator)
            if iso3 in values.index:
                year = int(
                    country_macro.loc[
                        country_macro[config.COL_INDICATOR] == indicator, config.COL_YEAR
                    ].max()
                )
                lines.append(
                    f"- {t(label_key)} ({year}): **{i18n.fmt_number(float(values[iso3]), 1)} %**"
                )
    lpi = row.get(config.COL_LPI)
    if pd.notna(lpi):
        lines.append(f"- {t('col_lpi')}: **{i18n.fmt_number(float(lpi), 1)}**")
    lines.append(
        f"- {t('col_stability')}: **{i18n.fmt_number(float(row[config.COL_STABILITY]), 2)}**"
    )
    st.markdown("\n".join(lines))


def _focus_competitors_block(hs: str, iso3: str, product_label: str) -> None:
    """Top proveedores del producto en el destino, con Colombia resaltada."""
    st.markdown(f"**{t('focus_competitors_header', product=product_label)}**")
    suppliers = _load_competitors(hs)
    destination = (
        suppliers[suppliers[config.COL_COUNTRY] == iso3] if suppliers is not None else None
    )
    if destination is None or destination.empty:
        st.info(t("focus_competitors_missing"))
        return
    origin_code = str(config.ORIGIN_COMTRADE_CODE)
    top = destination[destination[config.COL_SUPPLIER_RANK] <= 5]
    colombia = destination[destination[config.COL_PARTNER_CODE] == origin_code]
    chart_rows = (
        pd.concat([top, colombia])
        .drop_duplicates(subset=config.COL_PARTNER_CODE)
        .sort_values(config.COL_SUPPLIER_RANK)
    )
    labels = [
        f"#{int(rank)} " + (config.ORIGIN_NAME if code == origin_code else str(name))
        for rank, code, name in zip(
            chart_rows[config.COL_SUPPLIER_RANK],
            chart_rows[config.COL_PARTNER_CODE],
            chart_rows[config.COL_PARTNER_NAME],
            strict=True,
        )
    ]
    colors = [
        "#F59E0B" if code == origin_code else "#1D4ED8"
        for code in chart_rows[config.COL_PARTNER_CODE]
    ]
    fig = go.Figure(
        go.Bar(
            x=chart_rows[config.COL_SUPPLIER_SHARE] * 100.0,
            y=labels,
            orientation="h",
            marker_color=colors,
            hovertemplate="%{x:.1f} %<extra></extra>",
        )
    )
    fig.update_layout(
        separators=i18n.active_plotly_separators(),
        height=60 + 36 * len(chart_rows),
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        xaxis={"title": t("focus_competitors_xaxis")},
        yaxis={"title": None, "autorange": "reversed"},
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)
    year = int(destination[config.COL_YEAR].max())
    if not colombia.empty:
        st.caption(
            t(
                "focus_colombia_position",
                rank=int(colombia[config.COL_SUPPLIER_RANK].iloc[0]),
                share=i18n.fmt_pct(float(colombia[config.COL_SUPPLIER_SHARE].iloc[0])),
                year=year,
            )
        )
    else:
        st.caption(t("focus_colombia_absent", year=year))


def _focus_evolution_block(timeseries: pd.DataFrame | None, iso3: str) -> None:
    """Mini-gráfica: importaciones anuales del producto en el destino."""
    if timeseries is None:
        return
    series = timeseries[timeseries[config.COL_COUNTRY] == iso3]
    if series.empty:
        return
    st.markdown(f"**{t('focus_evolution_header')}**")
    data = series.assign(musd=series[config.COL_IMPORTS_USD] / 1e6)
    fig = px.line(data, x=config.COL_YEAR, y="musd", markers=True)
    fig.update_traces(
        line={"width": 2.5, "color": "#1D4ED8"},
        marker={"size": 7},
        hovertemplate="%{y:,.1f}<extra></extra>",
    )
    fig.update_layout(
        separators=i18n.active_plotly_separators(),
        height=240,
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
        xaxis={"title": None, "dtick": 1, "tickformat": "d"},
        yaxis={"title": None},
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)


def _focus_section(
    ranking: pd.DataFrame,
    meta: dict[str, object],
    narrative: dict[str, object],
    timeseries: pd.DataFrame | None,
    hs: str,
    product_label: str,
) -> None:
    """Ficha del destino: todo lo que el Radar sabe del mercado en foco.

    El foco se fija clicando el mapa (``_apply_map_selection``) o con el
    selector de esta sección; «quitar foco» lo limpia. Presentación pura:
    lee columnas del snapshot y llama funciones puras de ``domain/``
    (contribuciones, último dato macro) — ninguna fórmula vive aquí.
    """
    st.divider()
    st.subheader(t("focus_subheader"))
    st.caption(t("focus_caption"))
    names = ranking.set_index(config.COL_COUNTRY)[config.COL_COUNTRY_NAME]
    options = ["", *ranking[config.COL_COUNTRY].tolist()]
    # Un foco heredado (p. ej. de otro producto) que no existe en este
    # ranking rompería el selectbox: se limpia antes de instanciarlo.
    if st.session_state.get(_FOCUS_SELECT_KEY) not in options:
        st.session_state[_FOCUS_SELECT_KEY] = ""
    col_select, col_clear = st.columns([3, 1], vertical_alignment="bottom")
    with col_select:
        selected = st.selectbox(
            t("focus_select_label"),
            options=options,
            format_func=lambda iso3: (
                t("focus_select_placeholder")
                if not iso3
                else f"{flag_emoji(iso3)} {names.get(iso3, iso3)} ({iso3})".strip()
            ),
            key=_FOCUS_SELECT_KEY,
            help=t("focus_select_help"),
        )
    if selected:
        with col_clear:
            st.button(t("focus_clear"), on_click=_clear_focus)
    if not selected:
        st.info(t("focus_hint"))
        return
    row = ranking.set_index(config.COL_COUNTRY).loc[selected]
    flag = flag_emoji(selected)
    st.markdown(f"### {flag} {names[selected]}".replace("  ", " "))
    _focus_header_metrics(ranking, row, selected)
    _focus_drivers_line(ranking, meta, selected)
    _focus_unit_values_block(hs, selected)
    col_left, col_right = st.columns([2, 3])
    with col_left:
        _focus_macro_block(row, selected)
    with col_right:
        _focus_competitors_block(hs, selected, product_label)
    _focus_evolution_block(timeseries, selected)
    markets = narrative.get("markets")
    if isinstance(markets, dict) and markets.get(selected):
        st.markdown(f"**{t('focus_narrative_header')}**")
        for sentence in markets[selected]:
            st.markdown(f"- {sentence}")


def _focus_unit_values_block(hs: str, iso3: str) -> None:
    """Valor unitario del destino y del origen allí (USD/kg), con el premium.

    Presentación pura del artefacto ``unit_values.parquet`` (los cálculos
    viven en ``domain/indices``: ``aggregate_unit_value`` y
    ``unit_value_premium``). Solo catálogo curado; sin artefacto o sin dato
    para el destino, el bloque no aparece.
    """
    unit_values = _load_unit_values(hs)
    if unit_values is None:
        return
    match = unit_values[unit_values[config.COL_COUNTRY] == iso3]
    if match.empty:
        return
    row = match.iloc[0]
    uv_market = row[config.COL_UV_MARKET]
    uv_origin = row[config.COL_UV_ORIGIN]
    premium = row[config.COL_UV_PREMIUM]
    if pd.isna(uv_market) and pd.isna(uv_origin):
        return
    col_market, col_origin, _ = st.columns(3)
    if not pd.isna(uv_market):
        col_market.metric(
            t("uv_focus_market_label"),
            f"{i18n.fmt_number(float(uv_market), 2)} USD/kg",
            help=t("uv_focus_help"),
        )
    if not pd.isna(uv_origin):
        col_origin.metric(
            t("uv_focus_origin_label", origin=config.ORIGIN_NAME),
            f"{i18n.fmt_number(float(uv_origin), 2)} USD/kg",
            delta=(
                t("uv_focus_premium_delta", pct=i18n.fmt_pct(float(premium), 0, signed=True))
                if not pd.isna(premium)
                else None
            ),
            delta_color="off",
            help=t("uv_focus_help"),
        )


def _comparator_section(products: dict[str, str]) -> None:
    """Comparador: los mejores mercados de 2–3 partidas, lado a lado.

    Solo lee snapshots ya construidos (nada de red ni cálculo): responde
    «¿a qué mercado le apuesto con cuál producto?» de una mirada. Con un
    solo producto analizado, un caption anuncia la función (que exista se
    descubra, no que aparezca de la nada al construir la segunda partida).
    """
    if len(products) < 2:
        st.caption(t("comparator_needs_more_info"))
        return
    st.divider()
    st.subheader(t("comparator_subheader"))
    st.caption(t("comparator_caption"))
    selected = st.multiselect(
        t("comparator_select_label"),
        options=list(products),
        format_func=lambda code: products[code],
        max_selections=3,
        key="comparator_products",
    )
    if len(selected) == 1:
        st.info(t("comparator_select_info"))
        return
    if len(selected) < 2:
        return
    for column, code in zip(st.columns(len(selected)), selected, strict=True):
        with column:
            try:
                ranking, meta, _ = _load_snapshot(code)
            except FileNotFoundError:
                st.warning(t("comparator_missing_warning", code=code))
                continue
            ranking = _localize_country_names(ranking)
            label = i18n.product_label(code, str(meta["hs_label"]))
            st.markdown(f"**{label}**")
            demand = float(ranking[config.COL_MARKET_SIZE].sum())
            rca = meta.get("rca_balassa")
            st.caption(
                t(
                    "comparator_rca_demand",
                    rca=i18n.fmt_number(float(str(rca)), 1) if rca is not None else "—",
                    demand=i18n.fmt_usd_compact(demand),
                )
            )
            top5 = ranking.nsmallest(5, config.COL_RANK)
            for _, row in top5.iterrows():
                st.markdown(
                    f"{int(row[config.COL_RANK])}. "
                    f"{flag_emoji(row[config.COL_COUNTRY])} "
                    f"{row[config.COL_COUNTRY_NAME]} — "
                    f"**{i18n.fmt_number(row[config.COL_FINAL_SCORE], 3)}**"
                )


def _methodology_section(meta: dict[str, object]) -> None:
    """Metodología: fórmula y cita de cada métrica, y cómo se combinan."""
    weights_obj = meta.get("weights")
    weights: dict[str, object] = weights_obj if isinstance(weights_obj, dict) else {}
    bounds_obj = meta.get("macro_bounds")
    bounds: dict[str, object] = bounds_obj if isinstance(bounds_obj, dict) else {}
    definitions = [
        (
            t("methodology_metric_market_size"),
            t("methodology_def_market_size", years=meta.get("market_size_years")),
            "market_size",
        ),
        (
            t("methodology_metric_growth"),
            t("methodology_def_growth"),
            "import_growth",
        ),
        (
            t("methodology_metric_share"),
            t("methodology_def_share"),
            "market_share",
        ),
        (
            t("methodology_metric_share_trend"),
            t("methodology_def_share_trend"),
            "share_trend",
        ),
        (
            t("methodology_metric_complementarity"),
            t("methodology_def_complementarity"),
            "complementarity",
        ),
        (
            t("methodology_metric_tariff"),
            t("methodology_def_tariff"),
            "tariff_faced",
        ),
    ]
    header = (
        f"| {t('methodology_col_metric')} | {t('methodology_col_definition')} | "
        f"{t('methodology_col_weight')} |\n|---|---|---|"
    )
    table = "\n".join(
        f"| {name} | {definition} | {weights.get(key, '—')} |"
        for name, definition, key in definitions
    )
    floor = float(str(meta.get("macro_floor") or 0.5))
    macro_filter_text = t(
        "methodology_macro_filter",
        years=meta.get("macro_years"),
        inflation=bounds.get("inflation", "—"),
        gdp=bounds.get("gdp_growth", "—"),
        current_account=bounds.get("current_account", "—"),
    )
    final_score_text = t(
        "methodology_final_score",
        floor=meta.get("macro_floor"),
        floor_complement=round(1 - floor, 2),
    )
    with st.expander(t("methodology_expander_title")):
        st.markdown(
            f"""
{t("methodology_intro")}

{header}
{table}

{t("methodology_rca_note")}

{t("methodology_agreement_note")}

{t("methodology_hhi_note")}

{t("methodology_lpi_note")}

{macro_filter_text}

{final_score_text}

{t("methodology_footer")}
"""
        )


def _compare_selector(ranking: pd.DataFrame) -> list[str]:
    """Selector global de comparación: hasta 3 mercados para TODAS las gráficas.

    Devuelve los ISO3 elegidos; lista vacía = sin comparación (las pestañas
    muestran todos los mercados). Las opciones son códigos ISO3 — estables
    ante el toggle de idioma — y la etiqueta visible se arma con
    ``format_func``. El estado se depura antes de instanciar el widget: al
    cambiar de producto un destino puede desaparecer (p. ej. banano sin
    ECU/MEX) y una selección inválida rompería el multiselect.
    """
    names = ranking.set_index(config.COL_COUNTRY)[config.COL_COUNTRY_NAME]
    options = list(ranking[config.COL_COUNTRY])
    stored = st.session_state.get(_COMPARE_KEY)
    if isinstance(stored, list):
        valid = [iso3 for iso3 in stored if iso3 in options]
        if valid != stored:
            st.session_state[_COMPARE_KEY] = valid
    selected: list[str] = st.multiselect(
        t("compare_select_label"),
        options=options,
        max_selections=3,
        format_func=lambda iso3: f"{flag_emoji(iso3)} {names.get(iso3, iso3)}".strip(),
        key=_COMPARE_KEY,
        help=t("compare_select_help"),
    )
    if selected:
        st.caption(t("compare_active_note"))
    return selected


def _compare_view(ranking: pd.DataFrame, compare: list[str]) -> pd.DataFrame:
    """Filas de los mercados comparados, o el ranking completo sin selección.

    Solo filtra la PRESENTACIÓN: toda normalización (min-max del desglose y
    del radar) se calcula antes, sobre el ranking completo, para que
    comparar 3 mercados no cambie sus valores.
    """
    if not compare:
        return ranking
    return ranking[ranking[config.COL_COUNTRY].isin(compare)]


def _map_tab(ranking: pd.DataFrame, focus_iso3: str = "", compare: list[str] | None = None) -> None:
    """Choropleth del score final por destino (plotly acepta ISO3 directo).

    Presentación pura: pinta columnas ya presentes en el ranking; el color es
    el score final y el hover trae las métricas que lo explican. Con
    ``on_select="rerun"``, el clic en un país fija el foco (lo procesa
    ``_apply_map_selection`` al inicio del run siguiente) y el país en foco
    se dibuja con borde ámbar.
    """
    st.caption(t("map_caption"))
    st.caption(t("map_focus_hint"))
    data = _compare_view(ranking, compare or [])
    fig = px.choropleth(
        data,
        locations=config.COL_COUNTRY,
        color=config.COL_FINAL_SCORE,
        hover_name=config.COL_COUNTRY_NAME,
        custom_data=[config.COL_COUNTRY],
        hover_data={
            config.COL_COUNTRY: False,
            config.COL_FINAL_SCORE: ":.3f",
            config.COL_MARKET_SIZE: ":,.0f",
            config.COL_GROWTH: ":.1%",
            config.COL_SHARE: ":.1%",
            config.COL_STABILITY: ":.2f",
        },
        labels={
            config.COL_FINAL_SCORE: t("map_label_final_score"),
            config.COL_MARKET_SIZE: t("map_label_imports"),
            config.COL_GROWTH: t("map_label_growth"),
            config.COL_SHARE: t("map_label_share"),
            config.COL_STABILITY: t("map_label_stability"),
        },
        color_continuous_scale="Blues",
        projection="natural earth",
    )
    line_colors = [
        "#F59E0B" if iso == focus_iso3 else "#FFFFFF" for iso in data[config.COL_COUNTRY]
    ]
    line_widths = [2.5 if iso == focus_iso3 else 0.6 for iso in data[config.COL_COUNTRY]]
    fig.update_traces(marker_line_color=line_colors, marker_line_width=line_widths)
    fig.update_layout(
        separators=i18n.active_plotly_separators(),
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        height=480,
        coloraxis_colorbar={"title": t("map_label_final_score")},
        geo={
            "bgcolor": "rgba(0,0,0,0)",
            "showframe": False,
            "showland": True,
            "landcolor": "#E2E8F0",
            "showcountries": True,
            "countrycolor": "#FFFFFF",
            "coastlinecolor": "#CBD5E1",
        },
    )
    st.plotly_chart(fig, use_container_width=True, on_select="rerun", key=_MAP_KEY)


def _evolution_tab(
    ranking: pd.DataFrame,
    meta: dict[str, object],
    timeseries: pd.DataFrame,
    compare: list[str] | None = None,
) -> None:
    """Evolución anual de las importaciones por destino (indexada o absoluta).

    Presentación pura sobre la serie que el pipeline dejó en el snapshot.
    Vista indexada (default): todos los mercados en la misma escala para
    comparar ritmos; vista absoluta en millones de USD. Con el comparador
    global activo, las líneas son esos mercados y el selector propio se
    oculta (una sola fuente de verdad).
    """
    names = ranking.set_index(config.COL_COUNTRY)[config.COL_COUNTRY_NAME]
    if compare:
        selected_iso3 = [iso3 for iso3 in compare if iso3 in names.index]
    else:
        default_markets = list(ranking.nsmallest(5, config.COL_RANK)[config.COL_COUNTRY_NAME])
        selected_names = st.multiselect(
            t("evolution_select_markets_label"),
            options=list(names.sort_values()),
            default=default_markets,
        )
        selected_iso3 = [str(iso3) for iso3, name in names.items() if name in selected_names]
    view_index, view_absolute = t("evolution_view_index"), t("evolution_view_absolute")
    view = st.radio(
        t("evolution_view_label"),
        options=[view_index, view_absolute],
        horizontal=True,
        help=t("evolution_view_help"),
    )
    if not selected_iso3:
        st.info(t("evolution_select_info"))
        return
    by_year = (
        timeseries[timeseries[config.COL_COUNTRY].isin(selected_iso3)]
        .assign(**{config.COL_COUNTRY_NAME: lambda d: d[config.COL_COUNTRY].map(names)})
        .pivot(
            index=config.COL_YEAR,
            columns=config.COL_COUNTRY_NAME,
            values=config.COL_IMPORTS_USD,
        )
    )
    indexed = view == view_index
    caption_key = "evolution_caption_index" if indexed else "evolution_caption_absolute"
    st.caption(t(caption_key, min_year=meta["data_year_min"], max_year=meta["data_year_max"]))
    data = by_year.div(by_year.iloc[0]).mul(100.0) if indexed else by_year / 1e6
    fig = px.line(data, markers=True)
    fig.update_traces(line={"width": 2.5}, marker={"size": 7}, hovertemplate="%{y:,.1f}")
    if indexed:
        fig.add_hline(y=100.0, line_dash="dot", line_color="#94A3B8", opacity=0.8)
    fig.update_layout(
        separators=i18n.active_plotly_separators(),
        hovermode="x unified",
        height=440,
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
        legend={"orientation": "h", "yanchor": "bottom", "y": -0.35, "title": None},
        xaxis={"title": None, "dtick": 1, "tickformat": "d"},
        yaxis={"title": t("evolution_yaxis_index") if indexed else t("evolution_yaxis_usd_m")},
    )
    st.plotly_chart(fig, use_container_width=True)


def _load_competitors(hs: str) -> pd.DataFrame | None:
    """Lee las cuotas de proveedores por destino, si el snapshot las trae.

    Snapshots anteriores a 2026-07-08 (o construidos con el stub) no tienen
    este artefacto: la ficha degrada con gracia omitiendo la sección.
    """
    path = config.competitors_parquet(hs)
    if not path.exists():
        return None
    return _read_parquet(path)


def _load_unit_values(hs: str) -> pd.DataFrame | None:
    """Lee los valores unitarios (USD/kg) por destino, si el snapshot los trae.

    Artefacto exclusivo del catálogo curado: las partidas del buscador
    on-demand no lo tienen y la app degrada con gracia omitiendo la pestaña
    y el bloque de la ficha.
    """
    path = config.unit_values_parquet(hs)
    if not path.exists():
        return None
    return _read_parquet(path)


def _load_macro_context() -> pd.DataFrame | None:
    """Lee el macro crudo compartido (país × indicador × año), si existe."""
    path = config.macro_context_parquet()
    if not path.exists():
        return None
    return _read_parquet(path)


def _selected_map_iso3() -> str | None:
    """ISO3 del país clicado en el mapa, leyendo el estado del widget.

    Se lee de ``st.session_state`` (no del retorno de ``st.plotly_chart``)
    para poder aplicar el foco ANTES de renderizar la tabla y el selector,
    sin un rerun extra. Tolerante al formato del punto (``customdata`` o
    ``location``): si algo no está, devuelve None.
    """
    state = st.session_state.get(_MAP_KEY)
    if not state:
        return None
    try:
        points = state["selection"]["points"]
    except (KeyError, TypeError, IndexError):
        return None
    if not points:
        return None
    point = points[0]
    customdata = point.get("customdata")
    if isinstance(customdata, list | tuple) and customdata:
        return str(customdata[0])
    location = point.get("location")
    return str(location) if location else None


def _apply_map_selection(ranking: pd.DataFrame) -> None:
    """Clic en el mapa → foco. Debe correr antes de instanciar el selector.

    El guard ``_MAP_PROCESSED_KEY`` asegura que cada clic se aplique una sola
    vez: sin él, la selección persistente del widget reimpondría el foco en
    cada rerun y el botón «quitar foco» parecería roto.
    """
    iso3 = _selected_map_iso3()
    if not iso3 or iso3 not in set(ranking[config.COL_COUNTRY]):
        return
    if st.session_state.get(_MAP_PROCESSED_KEY) == iso3:
        return
    st.session_state[_MAP_PROCESSED_KEY] = iso3
    st.session_state[_FOCUS_SELECT_KEY] = iso3


def _selected_table_iso3(ranking: pd.DataFrame) -> str | None:
    """ISO3 de la fila clicada en la tabla del ranking, si hay alguna.

    Igual que ``_selected_map_iso3``: lee ``st.session_state`` (no el retorno
    de ``st.dataframe``) para poder aplicar el foco antes de renderizar la
    tabla. El índice de fila seleccionado corresponde 1:1 con ``ranking``
    porque la tabla se dibuja en el mismo orden, solo con columnas
    formateadas/insertadas/ocultadas para presentación.
    """
    state = st.session_state.get(_TABLE_KEY)
    if not state:
        return None
    try:
        rows = state["selection"]["rows"]
    except (KeyError, TypeError):
        return None
    if not rows:
        return None
    row_index = rows[0]
    if row_index < 0 or row_index >= len(ranking):
        return None
    return str(ranking.iloc[row_index][config.COL_COUNTRY])


def _apply_table_selection(ranking: pd.DataFrame) -> None:
    """Clic en una fila de la tabla → foco. Debe correr antes de dibujarla.

    Guard análogo a ``_apply_map_selection`` (``_TABLE_PROCESSED_KEY``): sin
    él, la selección persistente del widget reimpondría el foco en cada
    rerun y «quitar foco» parecería roto.
    """
    iso3 = _selected_table_iso3(ranking)
    if not iso3 or iso3 not in set(ranking[config.COL_COUNTRY]):
        return
    if st.session_state.get(_TABLE_PROCESSED_KEY) == iso3:
        return
    st.session_state[_TABLE_PROCESSED_KEY] = iso3
    st.session_state[_FOCUS_SELECT_KEY] = iso3


def _clear_focus() -> None:
    """Callback del botón «quitar foco» (corre antes del rerun)."""
    st.session_state[_FOCUS_SELECT_KEY] = ""


def _current_focus() -> str:
    """ISO3 del mercado en foco, o cadena vacía si no hay foco."""
    return str(st.session_state.get(_FOCUS_SELECT_KEY, "") or "")


def _ranking_column_label(column: str, meta: dict[str, object]) -> str:
    """Etiqueta de una columna del ranking en el idioma activo (selector de columnas)."""
    if column == config.COL_COUNTRY:
        return "ISO3"
    if column == config.COL_MARKET_SIZE:
        return t("col_market_size", years=meta["market_size_years"])
    return t(_RANKING_COLUMN_LABEL_KEYS[column])


def _column_toggle_changed(widget_key: str, store_key: str) -> None:
    """Callback de un checkbox de columna: copia su valor a la clave propia."""
    st.session_state[store_key] = bool(st.session_state[widget_key])


def _ranking_visible_columns(display: pd.DataFrame, meta: dict[str, object]) -> list[str]:
    """Columnas a mostrar en la tabla: fijas + las marcadas en «⚙️ Columnas».

    Un checkbox por columna dentro del popover — un clic activa/desactiva,
    sin menús anidados (el multiselect dentro del popover era un desplegable
    tras otro). El estado vive por columna en claves propias
    (``ranking_col_store_<nombre interno>``), así la elección sobrevive al
    toggle ES/EN y al cambio de producto. Se devuelven en el orden original
    de ``display.columns``.
    """
    fixed = [config.COL_RANK, config.COL_COUNTRY_NAME]
    optional = [col for col in display.columns if col not in fixed]
    selected: list[str] = []
    with st.popover(t("columns_popover_label")):
        st.markdown(f"**{t('columns_select_label')}**")
        st.caption(t("columns_select_help"))
        grid = st.columns(2)
        for i, column in enumerate(optional):
            widget_key = f"{_COLUMN_TOGGLE_KEY_PREFIX}{column}"
            store_key = f"{_COLUMN_STORE_KEY_PREFIX}{column}"
            if store_key not in st.session_state:
                st.session_state[store_key] = column in _DEFAULT_VISIBLE_COLUMNS
            with grid[i % 2]:
                if st.checkbox(
                    _ranking_column_label(column, meta),
                    value=bool(st.session_state[store_key]),
                    key=widget_key,
                    on_change=_column_toggle_changed,
                    args=(widget_key, store_key),
                ):
                    selected.append(column)
    return [col for col in display.columns if col in fixed or col in selected]


def _ranking_table(ranking: pd.DataFrame, meta: dict[str, object], focus_iso3: str = "") -> None:
    """Tabla del ranking con los números formateados en el idioma activo.

    Los formatos de ``st.column_config`` no sirven aquí: los printf usan
    siempre punto decimal y ``"localized"`` sigue el locale del navegador,
    no el toggle de idioma de la app. Por eso los valores se formatean con
    ``pandas.Styler`` usando las mismas funciones de ``app/format.py`` que
    el resto de la app; los datos siguen siendo numéricos, así que la
    alineación a la derecha se conserva.

    Solo se dibujan las columnas elegidas en el popover «⚙️ Columnas»
    (``_ranking_visible_columns``); los exports llevan todas.
    """
    flagged_names = (
        ranking[config.COL_COUNTRY].map(flag_emoji) + " " + ranking[config.COL_COUNTRY_NAME]
    ).str.strip()
    display = ranking.drop(columns=[config.COL_RCA]).assign(
        **{config.COL_COUNTRY_NAME: flagged_names}
    )
    # Acuerdo comercial COL–destino: contexto de presentación (config), se
    # inserta junto al arancel, cuyo valor ya refleja el acuerdo (AHS).
    agreement = ranking[config.COL_COUNTRY].map(lambda iso3: i18n.trade_agreement(iso3) or "—")
    position = (
        int(display.columns.get_indexer([config.COL_TARIFF])[0]) + 1
        if config.COL_TARIFF in display.columns
        else len(display.columns)
    )
    display.insert(position, config.COL_AGREEMENT, agreement)
    display = display[_ranking_visible_columns(display, meta)]
    formats: dict[str, Callable[[float], str]] = {
        config.COL_MARKET_SIZE: lambda v: i18n.fmt_number(v),
        config.COL_GROWTH: lambda v: i18n.fmt_pct(v, signed=True),
        config.COL_SHARE: lambda v: i18n.fmt_pct(v),
        config.COL_SHARE_TREND: lambda v: i18n.fmt_pct(v, signed=True),
        config.COL_ORIGIN_EXPORT_SHARE: lambda v: i18n.fmt_pct(v),
        config.COL_COMPLEMENTARITY: lambda v: i18n.fmt_number(v, 2),
        config.COL_TARIFF: lambda v: i18n.fmt_pct(v),
        config.COL_LPI: lambda v: i18n.fmt_number(v, 1),
        config.COL_STABILITY: lambda v: i18n.fmt_number(v, 2),
        config.COL_SCORE: lambda v: i18n.fmt_number(v, 3),
        # COL_FINAL_SCORE queda fuera a propósito: se dibuja como
        # ProgressColumn (barra 0–1) y esa columna necesita el valor
        # numérico crudo, no el string del Styler. Trade-off asumido: su
        # texto usa "%.3f" (punto decimal fijo) también en español.
    }
    # cast: Styler.format tipa el formatter como Callable[[object], str], pero
    # estas columnas son numéricas — solo recibirán floats.
    styler = display.style.format(
        {
            col: cast("Callable[[object], str]", fmt)
            for col, fmt in formats.items()
            if col in display.columns
        },
        na_rep="—",
    )
    if focus_iso3:
        # Fila del mercado en foco resaltada (ámbar translúcido: funciona en
        # tema claro y oscuro sin forzar el color del texto). Se lee de
        # ``ranking`` (mismo orden de filas): la columna ISO3 puede estar
        # oculta en ``display``.
        row_styles = [
            "background-color: rgba(245, 158, 11, 0.22)" if iso == focus_iso3 else ""
            for iso in ranking[config.COL_COUNTRY]
        ]
        styler = styler.apply(lambda column: row_styles, axis=0)
    st.dataframe(
        styler,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key=_TABLE_KEY,
        column_config={
            # width acepta píxeles (int) solo desde Streamlit > 1.49: aquí
            # se usa "small" para que el "#" no se estire con la tabla.
            config.COL_RANK: st.column_config.Column("#", width="small", help=t("col_rank_help")),
            config.COL_COUNTRY: st.column_config.Column("ISO3", help=t("col_iso3_help")),
            config.COL_COUNTRY_NAME: st.column_config.Column(
                t("col_market"), help=t("col_market_help")
            ),
            config.COL_MARKET_SIZE: st.column_config.Column(
                t("col_market_size", years=meta["market_size_years"]),
                help=t("col_market_size_help", years=meta["market_size_years"]),
            ),
            config.COL_GROWTH: st.column_config.Column(t("col_growth"), help=t("col_growth_help")),
            config.COL_SHARE: st.column_config.Column(t("col_share"), help=t("col_share_help")),
            config.COL_SHARE_TREND: st.column_config.Column(
                t("col_share_trend"), help=t("col_share_trend_help")
            ),
            config.COL_ORIGIN_EXPORT_SHARE: st.column_config.Column(
                t("col_origin_export_share"), help=t("col_origin_export_share_help")
            ),
            config.COL_COMPLEMENTARITY: st.column_config.Column(
                t("col_complementarity"), help=t("col_complementarity_help")
            ),
            config.COL_TARIFF: st.column_config.Column(t("col_tariff"), help=t("col_tariff_help")),
            config.COL_AGREEMENT: st.column_config.Column(
                t("col_agreement"), help=t("col_agreement_help")
            ),
            config.COL_LPI: st.column_config.Column(t("col_lpi"), help=t("col_lpi_help")),
            config.COL_STABILITY: st.column_config.Column(
                t("col_stability"), help=t("col_stability_help")
            ),
            config.COL_SCORE: st.column_config.Column(
                t("col_score_raw"), help=t("col_score_raw_help")
            ),
            config.COL_FINAL_SCORE: st.column_config.ProgressColumn(
                t("col_score_final"),
                min_value=0.0,
                max_value=1.0,
                format="%.3f",
                help=t("col_score_final_help"),
            ),
        },
    )


def _delta_color(value: object) -> str:
    """CSS de la celda Δ posición del simulador: sube verde, baja rojo."""
    text = str(value)
    if text.startswith("▲"):
        return "color: #16A34A; font-weight: 600"
    if text.startswith("▼"):
        return "color: #DC2626; font-weight: 600"
    return "color: #94A3B8"


def _weight_lab_section(
    ranking: pd.DataFrame, meta: dict[str, object]
) -> tuple[pd.DataFrame, dict[str, float], float] | None:
    """Simulador de prioridades: sliders → re-ranking en vivo (what-if).

    Las fórmulas viven en ``domain/scoring`` (funciones puras, testeadas);
    la app solo recoge los pesos y el piso de la penalización macro del
    usuario, invoca al dominio y compara el resultado contra el ranking
    oficial del snapshot.

    Returns:
        ``(rescored, weights, macro_floor)`` — el ranking re-calculado, los
        pesos efectivos (normalizados) y el piso macro simulado — solo
        cuando el usuario movió algún deslizador respecto a los valores
        oficiales, para que el resto de la página (mapa, pestañas, ficha de
        foco) se propague en vivo. ``None`` si los valores siguen siendo los
        oficiales, si el laboratorio no se puede mostrar (faltan columnas) o
        si todos los pesos quedaron en cero: en esos casos el llamador sigue
        usando el ranking oficial del snapshot.
    """
    available = [name for name, col in scoring.METRIC_COLUMNS.items() if col in ranking.columns]
    if not available or config.COL_STABILITY not in ranking.columns:
        return None
    weights_obj = meta.get("weights")
    official_weights: dict[str, float] = (
        {name: float(str(value)) for name, value in weights_obj.items() if name in available}
        if isinstance(weights_obj, dict)
        else {}
    )
    with st.expander(t("lab_expander_title")):
        st.caption(t("lab_caption"))
        # El reset borra el estado ANTES de instanciar los sliders: al
        # recrearse toman su valor por defecto (los pesos oficiales).
        if st.button(t("lab_reset"), key="lab_reset"):
            for name in available:
                st.session_state.pop(f"lab_w_{name}", None)
            st.session_state.pop("lab_floor", None)
        slider_columns = st.columns(3)
        raw_weights: dict[str, int] = {}
        default_ints: dict[str, int] = {}
        for i, name in enumerate(available):
            default = official_weights.get(name, config.WEIGHTS.get(name, 0.0))
            default_ints[name] = int(round(default * 100))
            with slider_columns[i % 3]:
                raw_weights[name] = st.slider(
                    i18n.metric_label(name),
                    min_value=0,
                    max_value=100,
                    value=default_ints[name],
                    step=1,
                    format="%d%%",
                    key=f"lab_w_{name}",
                    help=t("lab_slider_help"),
                )
        official_floor = float(str(meta.get("macro_floor") or config.MACRO_FLOOR))
        default_floor_int = int(round(official_floor * 100))
        floor_column, _ = st.columns([1, 2])
        with floor_column:
            floor_int = st.slider(
                t("lab_floor_label"),
                min_value=0,
                max_value=100,
                value=default_floor_int,
                step=5,
                format="%d%%",
                key="lab_floor",
                help=t("lab_floor_help", official=default_floor_int),
            )
        total = sum(raw_weights.values())
        if total == 0:
            st.info(t("lab_zero_info"))
            return None
        weights = {name: value / total for name, value in raw_weights.items()}
        effective = " · ".join(
            f"{i18n.metric_label(name)} {i18n.fmt_pct(weight, 0)}"
            for name, weight in weights.items()
            if weight > 0
        )
        st.caption(t("lab_effective_weights", weights=effective))
        if total != 100:
            st.caption(t("lab_total_note", total=total))
        floor = floor_int / 100.0
        rescored = scoring.rescore_ranking(ranking, weights, macro_floor=floor)
        official_rank = ranking.set_index(config.COL_COUNTRY)[config.COL_RANK]
        moves = (
            official_rank.reindex(rescored[config.COL_COUNTRY]).to_numpy()
            - rescored[config.COL_RANK].to_numpy()
        )
        flagged = (
            rescored[config.COL_COUNTRY].map(flag_emoji) + " " + rescored[config.COL_COUNTRY_NAME]
        ).str.strip()
        display = pd.DataFrame(
            {
                "#": rescored[config.COL_RANK],
                t("col_market"): flagged,
                t("col_score_final"): rescored[config.COL_FINAL_SCORE].map(
                    lambda v: i18n.fmt_number(v, 3)
                ),
                t("lab_col_delta"): [
                    f"▲ {move}" if move > 0 else f"▼ {-move}" if move < 0 else "=" for move in moves
                ],
            }
        )
        styled = display.style.map(_delta_color, subset=[t("lab_col_delta")])
        st.dataframe(styled, hide_index=True, width="stretch")
        simulated = raw_weights != default_ints or floor_int != default_floor_int
        if simulated:
            st.download_button(
                t("lab_download_csv"),
                data=rescored.to_csv(index=False).encode("utf-8"),
                file_name=f"radar_{meta['hs_code']}_{meta['origin_iso3']}_simulado.csv",
                mime="text/csv",
            )
            st.caption(t("lab_export_note"))
    if not simulated:
        return None  # valores oficiales intactos: la página sigue con el snapshot
    return rescored, weights, floor


def _scores_tab(ranking: pd.DataFrame, compare: list[str] | None = None) -> None:
    """Score bruto vs. final por mercado: la brecha es la penalización macro.

    Plotly en lugar de ``st.bar_chart`` para que ejes y hover respeten los
    separadores del idioma activo (``separators``), igual que el mapa y la
    evolución.
    """
    st.caption(t("tab_scores_caption"))
    ordered = _compare_view(ranking, compare or []).sort_values(
        config.COL_FINAL_SCORE, ascending=True
    )
    fig = go.Figure()
    for column, label, color in (
        (config.COL_SCORE, t("col_score_raw"), "#93C5FD"),
        (config.COL_FINAL_SCORE, t("col_score_final"), "#1D4ED8"),
    ):
        fig.add_bar(
            x=ordered[column],
            y=ordered[config.COL_COUNTRY_NAME],
            orientation="h",
            name=label,
            marker_color=color,
            hovertemplate="%{x:.3f}<extra>" + label + "</extra>",
        )
    fig.update_layout(
        separators=i18n.active_plotly_separators(),
        barmode="group",
        height=max(360, 30 * len(ordered) + 80),
        # t=60: hueco para la leyenda horizontal (si no, tapa la 1.ª barra)
        margin={"l": 0, "r": 0, "t": 60, "b": 0},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "title": None},
        xaxis={"title": None},
        yaxis={"title": None},
        hovermode="y unified",
    )
    st.plotly_chart(fig, use_container_width=True)


def _breakdown_tab(
    ranking: pd.DataFrame, meta: dict[str, object], compare: list[str] | None = None
) -> None:
    """Desglose del score de oportunidad: contribución de cada métrica.

    Barra apilada por mercado con los sumandos ``w·norm/Σw`` que calcula
    ``domain/scoring.score_contributions`` (puro, testeado): hace visible por
    qué cada mercado puntúa lo que puntúa. La penalización macro no aparece
    aquí — la muestra la pestaña de scores. Las contribuciones se calculan
    sobre el ranking COMPLETO (la normalización min-max no cambia al
    comparar); el comparador solo filtra qué barras se dibujan.
    """
    weights_obj = meta.get("weights")
    weights: dict[str, float] = (
        {name: float(str(value)) for name, value in weights_obj.items()}
        if isinstance(weights_obj, dict)
        else dict(config.WEIGHTS)
    )
    available = {
        name: weight
        for name, weight in weights.items()
        if scoring.METRIC_COLUMNS.get(name) in ranking.columns and weight > 0
    }
    if not available:
        return
    st.caption(t("breakdown_caption"))
    contributions = scoring.score_contributions(ranking, available)
    ordered = _compare_view(ranking, compare or []).sort_values(config.COL_SCORE, ascending=True)
    fig = go.Figure()
    for name in available:
        label = i18n.metric_label(name)
        fig.add_bar(
            x=contributions[name].reindex(ordered[config.COL_COUNTRY]),
            y=ordered[config.COL_COUNTRY_NAME],
            orientation="h",
            name=label,
            marker_color=_METRIC_COLORS.get(name, "#CBD5E1"),
            hovertemplate="%{x:.3f}<extra>" + label + "</extra>",
        )
    fig.update_layout(
        separators=i18n.active_plotly_separators(),
        barmode="stack",
        height=max(360, 30 * len(ordered) + 80),
        # margen superior amplio: la leyenda horizontal vive ahí (y=1.0);
        # con t pequeño se dibuja ENCIMA de la primera barra del ranking.
        margin={"l": 0, "r": 0, "t": 70, "b": 0},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "title": None},
        xaxis={"title": t("col_score_raw")},
        yaxis={"title": None},
        hovermode="y unified",
    )
    st.plotly_chart(fig, use_container_width=True)


def _radar_tab(ranking: pd.DataFrame, compare: list[str] | None = None) -> None:
    """Radar de métricas normalizadas: perfil comparado de hasta 3 mercados.

    Cada eje es una métrica del scoring normalizada con
    ``domain/scoring.normalized_metric`` sobre TODOS los mercados del
    ranking (mismas direcciones que el motor: el arancel llega invertido).
    Los mercados los define el comparador global («🔍 Mercados a
    comparar», encima de las pestañas); sin selección, el top-3 del ranking.
    """
    available = [name for name, col in scoring.METRIC_COLUMNS.items() if col in ranking.columns]
    if len(available) < 3:  # un radar con menos de 3 ejes no dice nada
        return
    st.caption(t("radar_caption"))
    if not compare:
        st.caption(t("radar_compare_hint"))
    names = ranking.set_index(config.COL_COUNTRY)[config.COL_COUNTRY_NAME]
    selected = compare or list(ranking.nsmallest(3, config.COL_RANK)[config.COL_COUNTRY])
    indexed = ranking.set_index(config.COL_COUNTRY)
    normalized = {
        name: scoring.normalized_metric(name, indexed[scoring.METRIC_COLUMNS[name]])
        for name in available
    }
    axes = [i18n.metric_label(name) for name in available]
    fig = go.Figure()
    for iso3, color in zip(selected, _RADAR_COLORS, strict=False):
        values = [float(normalized[name][iso3]) for name in available]
        fig.add_trace(
            go.Scatterpolar(
                # se repite el primer punto para cerrar el polígono
                r=[*values, values[0]],
                theta=[*axes, axes[0]],
                fill="toself",
                name=f"{flag_emoji(iso3)} {names.get(iso3, iso3)}".strip(),
                line={"color": color, "width": 2.5},
                fillcolor=_radar_fill(color),
                hovertemplate="%{theta}: %{r:.2f}<extra>%{fullData.name}</extra>",
            )
        )
    fig.update_layout(
        separators=i18n.active_plotly_separators(),
        polar={
            "radialaxis": {"range": [0, 1], "tickvals": [0.25, 0.5, 0.75, 1.0]},
            "bgcolor": "rgba(0,0,0,0)",
        },
        height=480,
        margin={"l": 60, "r": 60, "t": 30, "b": 30},
        legend={"orientation": "h", "yanchor": "bottom", "y": -0.2},
    )
    st.plotly_chart(fig, use_container_width=True)


def _unit_value_tab(
    ranking: pd.DataFrame,
    unit_values: pd.DataFrame,
    meta: dict[str, object],
    compare: list[str] | None = None,
) -> None:
    """Valor unitario por destino: barras (promedio) + rombo (el del origen).

    Presentación pura del artefacto ``unit_values.parquet``: la barra es el
    precio implícito promedio de las importaciones del destino y el rombo el
    del flujo desde el origen — la distancia entre ambos es el premium.
    Destinos sin UV promedio se omiten de la gráfica.
    """
    st.caption(
        t(
            "uv_tab_caption",
            years=meta.get("market_size_years", config.MARKET_SIZE_YEARS),
            origin=config.ORIGIN_NAME,
        )
    )
    names = ranking.set_index(config.COL_COUNTRY)[config.COL_COUNTRY_NAME]
    data = unit_values[unit_values[config.COL_UV_MARKET].notna()].assign(
        **{config.COL_COUNTRY_NAME: lambda d: d[config.COL_COUNTRY].map(names)}
    )
    data = _compare_view(data[data[config.COL_COUNTRY_NAME].notna()], compare or []).sort_values(
        config.COL_UV_MARKET
    )
    if data.empty:
        return
    fig = go.Figure()
    fig.add_bar(
        x=data[config.COL_UV_MARKET],
        y=data[config.COL_COUNTRY_NAME],
        orientation="h",
        name=t("uv_legend_market"),
        marker_color="#93C5FD",
        hovertemplate="%{x:.2f} USD/kg<extra>" + t("uv_legend_market") + "</extra>",
    )
    with_origin = data[data[config.COL_UV_ORIGIN].notna()]
    if not with_origin.empty:
        origin_label = t("uv_legend_origin", origin=config.ORIGIN_NAME)
        fig.add_scatter(
            x=with_origin[config.COL_UV_ORIGIN],
            y=with_origin[config.COL_COUNTRY_NAME],
            mode="markers",
            name=origin_label,
            marker={"symbol": "diamond", "size": 11, "color": "#F59E0B"},
            hovertemplate="%{x:.2f} USD/kg<extra>" + origin_label + "</extra>",
        )
    fig.update_layout(
        separators=i18n.active_plotly_separators(),
        height=max(360, 30 * len(data) + 80),
        # t=60: hueco para la leyenda horizontal (si no, tapa la 1.ª barra)
        margin={"l": 0, "r": 0, "t": 60, "b": 0},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "title": None},
        xaxis={"title": t("uv_xaxis")},
        yaxis={"title": None},
        hovermode="y unified",
    )
    st.plotly_chart(fig, use_container_width=True)


def _size_tab(
    ranking: pd.DataFrame, meta: dict[str, object], compare: list[str] | None = None
) -> None:
    """Tamaño de cada mercado partido en «ya lo vende el origen» vs. resto."""
    st.caption(t("tab_size_caption", origin=meta["origin_iso3"]))
    ordered = _compare_view(ranking, compare or []).sort_values(
        config.COL_MARKET_SIZE, ascending=True
    )
    from_origin = ordered[config.COL_MARKET_SIZE] * ordered[config.COL_SHARE] / 1e6
    rest = ordered[config.COL_MARKET_SIZE] / 1e6 - from_origin
    fig = go.Figure()
    for values, label, color in (
        (from_origin, t("legend_from_origin", origin=meta["origin_iso3"]), "#93C5FD"),
        (rest, t("legend_rest"), "#1D4ED8"),
    ):
        fig.add_bar(
            x=values,
            y=ordered[config.COL_COUNTRY_NAME],
            orientation="h",
            name=label,
            marker_color=color,
            hovertemplate="%{x:,.1f}<extra>" + label + "</extra>",
        )
    fig.update_layout(
        separators=i18n.active_plotly_separators(),
        barmode="stack",
        height=max(360, 30 * len(ordered) + 80),
        # t=60: hueco para la leyenda horizontal (si no, tapa la 1.ª barra)
        margin={"l": 0, "r": 0, "t": 60, "b": 0},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "title": None},
        xaxis={"title": t("size_xaxis_usd_m")},
        yaxis={"title": None},
        hovermode="y unified",
    )
    st.plotly_chart(fig, use_container_width=True)


def _kpi_row(ranking: pd.DataFrame, meta: dict[str, object]) -> None:
    """Resumen ejecutivo de una mirada: agregaciones del ranking ya calculado.

    Solo agrega columnas presentes en el snapshot (presentación, no cálculo
    económico nuevo): demanda total, CAGR y cuota ponderados por tamaño de
    mercado, y el RCA que el pipeline dejó en ``meta``.
    """
    total = float(ranking[config.COL_MARKET_SIZE].sum())
    if total <= 0:
        return
    weights = ranking[config.COL_MARKET_SIZE] / total
    growth = float((ranking[config.COL_GROWTH] * weights).sum())
    share = float((ranking[config.COL_SHARE] * weights).sum())
    col_demand, col_growth, col_share, col_hhi, col_rca = st.columns(5)
    col_demand.metric(
        t("kpi_demand_label"),
        i18n.fmt_usd_compact(total),
        delta=t("kpi_demand_delta", n=len(ranking)),
        delta_color="off",
        help=t("kpi_demand_help"),
    )
    col_growth.metric(
        t("kpi_growth_label"),
        i18n.fmt_pct(growth, signed=True),
        delta=t("kpi_growth_delta"),
        delta_color="off",
        help=t("kpi_growth_help"),
    )
    col_share.metric(
        t("kpi_share_label"),
        i18n.fmt_pct(share),
        delta=t("kpi_share_delta"),
        delta_color="off",
        help=t("kpi_share_help"),
    )
    hhi = meta.get("destination_hhi")
    if hhi is not None:
        hhi_value = float(str(hhi))
        if hhi_value > config.HHI_HIGH:
            hhi_reading = t("kpi_hhi_high")
        elif hhi_value >= config.HHI_MODERATE:
            hhi_reading = t("kpi_hhi_moderate")
        else:
            hhi_reading = t("kpi_hhi_low")
        col_hhi.metric(
            t("kpi_hhi_label"),
            i18n.fmt_number(hhi_value, 2),
            delta=hhi_reading,
            delta_color="off",
            help=t("kpi_hhi_help"),
        )
    rca = meta.get("rca_balassa")
    if rca is not None:
        rca_value = float(str(rca))
        col_rca.metric(
            t("kpi_rca_label"),
            i18n.fmt_number(rca_value, 1),
            delta=t("kpi_rca_delta_yes") if rca_value > 1 else t("kpi_rca_delta_no"),
            delta_color="off",
            help=t("kpi_rca_help"),
        )


def _top3_cards(ranking: pd.DataFrame) -> None:
    """Tarjetas del podio: los 3 mercados con mejor score final."""
    top3 = ranking.nsmallest(3, config.COL_RANK)
    medals = ["🥇", "🥈", "🥉"]
    for column, (_, row), medal in zip(st.columns(3), top3.iterrows(), medals, strict=False):
        with column:
            flag = flag_emoji(row[config.COL_COUNTRY])
            st.metric(
                label=f"{medal} {flag} {row[config.COL_COUNTRY_NAME]}".replace("  ", " "),
                value=i18n.fmt_number(row[config.COL_FINAL_SCORE], 3),
                delta=t(
                    "top3_stability_delta",
                    value=i18n.fmt_number(row[config.COL_STABILITY], 2),
                ),
                delta_color="off",
            )


def main() -> None:
    """Renderiza la página principal: ranking de mercados destino."""
    st.set_page_config(page_title=t("page_title"), page_icon="📡", layout="wide")
    st.title(t("app_title"))
    _about_sidebar()
    _hero_section()

    _advanced_search_section()
    _sync_product_from_url()
    options = _selector_options(_catalog_products())
    _product_select_css()
    with st.container(key=_PRODUCT_SELECT_CONTAINER_KEY, border=True):
        hs = st.selectbox(
            t("product_select_label"),
            options=list(options),
            format_func=lambda code: options[code],
            key=_PRODUCT_SELECT_KEY,
            help=t("product_select_help"),
        )
    st.query_params["hs"] = hs  # URL compartible: ?hs=<partida>
    # Los curados se listan aunque no tengan snapshot: se construye al
    # seleccionarlos (en el demo cloud vienen versionados → instantáneo).
    if not config.ranking_parquet(hs).exists() and not _build_on_demand(hs):
        return
    ranking, meta, narrative = _load_snapshot(hs)
    narrative = _narrative_in_language(narrative)
    ranking = _localize_country_names(ranking)
    product_label = i18n.product_label(hs, str(meta["hs_label"]))
    # El clic en el mapa se aplica AHORA (antes de tabla, mapa y selector):
    # así el resaltado y la ficha reflejan la selección en este mismo run.
    _apply_map_selection(ranking)
    _apply_table_selection(ranking)
    focus_iso3 = _current_focus()

    rca = meta.get("rca_balassa")
    rca_text = t("caption_rca_suffix", rca=rca) if rca is not None else ""
    origin_flag = flag_emoji(str(meta["origin_iso3"]))
    st.caption(
        t(
            "caption_line",
            label=product_label,
            origin_flag=origin_flag,
            origin=meta["origin_iso3"],
            source=meta["source"],
            min_year=meta["data_year_min"],
            max_year=meta["data_year_max"],
            n_markets=meta["n_markets"],
            rca_text=rca_text,
        )
    )

    _kpi_row(ranking, meta)
    _methodology_section(meta)
    _top3_cards(ranking)
    _recommendations_section(narrative)

    st.subheader(t("ranking_subheader"))
    st.caption(t("ranking_caption", floor=meta.get("macro_floor", "—")))
    st.caption(t("table_focus_hint"))
    _ranking_table(ranking, meta, focus_iso3)
    base_name = f"radar_{meta['hs_code']}_{meta['origin_iso3']}"
    # Los exports llevan el idioma activo: etiquetas, números y la narrativa
    # ya seleccionada arriba; la etiqueta del producto también se localiza.
    export_lang = i18n.get_language()
    export_meta = {**meta, "hs_label": product_label}
    col_csv, col_xlsx, col_pdf, _ = st.columns([1, 1, 1, 3])
    with col_csv:
        st.download_button(
            "⬇️ CSV",
            data=ranking.to_csv(index=False).encode("utf-8"),
            file_name=f"{base_name}.csv",
            mime="text/csv",
        )
    with col_xlsx:
        st.download_button(
            "⬇️ Excel",
            data=ranking_to_excel(ranking, export_meta, narrative, export_lang),
            file_name=f"{base_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with col_pdf:
        st.download_button(
            "⬇️ PDF",
            data=ranking_to_pdf(ranking, export_meta, narrative, export_lang),
            file_name=f"{base_name}.pdf",
            mime="application/pdf",
        )

    lab_result = _weight_lab_section(ranking, meta)
    # Si el usuario movió los pesos del simulador, TODO lo de aquí hacia
    # abajo (mapa, gráficas, ficha de foco) se pinta con el ranking
    # re-calculado y sus pesos; el ranking oficial de arriba no se toca.
    view_ranking, view_meta = ranking, meta
    if lab_result is not None:
        sim_ranking, sim_weights, sim_floor = lab_result
        view_ranking = sim_ranking
        view_meta = {**meta, "weights": sim_weights, "macro_floor": sim_floor}
        st.info(t("lab_live_note"))

    compare = _compare_selector(view_ranking)
    timeseries = _load_imports_timeseries(hs)
    unit_values = _load_unit_values(hs)
    tab_labels = [
        t("tab_map"),
        t("tab_breakdown"),
        t("tab_radar"),
        t("tab_scores"),
        t("tab_size"),
    ]
    if unit_values is not None:
        tab_labels.append(t("tab_unit_value"))
    if timeseries is not None:
        tab_labels.append(t("tab_evolution"))
    tabs = st.tabs(tab_labels)
    with tabs[0]:
        _map_tab(view_ranking, focus_iso3, compare)
    with tabs[1]:
        _breakdown_tab(view_ranking, view_meta, compare)
    with tabs[2]:
        _radar_tab(view_ranking, compare)
    with tabs[3]:
        _scores_tab(view_ranking, compare)
    with tabs[4]:
        _size_tab(view_ranking, view_meta, compare)

    next_tab = 5
    if unit_values is not None:
        with tabs[next_tab]:
            _unit_value_tab(view_ranking, unit_values, view_meta, compare)
        next_tab += 1
    if timeseries is not None:
        with tabs[next_tab]:
            _evolution_tab(view_ranking, view_meta, timeseries, compare)

    _focus_section(view_ranking, view_meta, narrative, timeseries, hs, product_label)
    built = {
        code: label for code, label in options.items() if config.ranking_parquet(code).exists()
    }
    _comparator_section(built)


if __name__ == "__main__":
    main()
