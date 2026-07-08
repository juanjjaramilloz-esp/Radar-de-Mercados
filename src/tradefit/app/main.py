"""App Streamlit del Radar de Mercados.

Capa de presentación: lee los snapshots de ``data/processed/`` y no calcula
índices ni llama APIs directamente. La única excepción sancionada es el
buscador avanzado, que invoca ``pipeline.ensure_snapshot`` para construir
on-demand el snapshot de una partida nueva (la red sigue viviendo en
``ingest/`` y el cálculo en ``domain/``; la app solo dispara la orquestación
y luego lee el resultado). Si algo falla, degrada con gracia.
"""

import json
import os
from collections.abc import Callable
from typing import cast

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
from tradefit.pipeline.build_snapshot import ensure_snapshot

_PRODUCT_SELECT_KEY = "product_select"
_TOUR_SEEN_KEY = "tour_seen"


def _hero_section() -> None:
    """Propuesta de valor y mini-tour: el usuario aterriza sin contexto.

    El expander del tour llega abierto solo en la primera carga de la sesión
    (``st.session_state``); después queda plegado y disponible.
    """
    st.markdown(t("hero_value_prop"))
    first_load = _TOUR_SEEN_KEY not in st.session_state
    st.session_state[_TOUR_SEEN_KEY] = True
    with st.expander(t("hero_tour_title"), expanded=first_load):
        st.markdown(t("hero_tour_body"))


def _about_sidebar() -> None:
    """Tarjeta de credibilidad: qué es el proyecto, con qué está hecho y dónde vive."""
    i18n.language_toggle()
    with st.sidebar:
        st.header(t("about_header"))
        st.markdown(t("about_body"))
        st.caption(t("about_caption"))


def _available_products() -> dict[str, str]:
    """Productos con snapshot construido: ``{hs: etiqueta}`` desde meta.json.

    Escanea ``data/processed/`` completo: incluye tanto los productos curados
    como las partidas construidas on-demand por el buscador.
    """
    products: dict[str, str] = {}
    if not config.PROCESSED_DIR.exists():
        return products
    for meta_path in sorted(config.PROCESSED_DIR.glob("*/meta.json")):
        hs = meta_path.parent.name
        if config.ranking_parquet(hs).exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            label = str(meta.get("hs_label", hs))
            products[hs] = i18n.product_label(hs, label)
    return products


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


def _advanced_search_section(products: dict[str, str]) -> None:
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
        already_built = selected in products
        action = t("search_button_view") if already_built else t("search_button_download")
        go = st.button(action, type="primary", key="advanced_search_go")
        if go and (already_built or _build_on_demand(selected)):
            st.session_state[_PRODUCT_SELECT_KEY] = selected
            st.rerun()


def _sync_product_from_url(products: dict[str, str]) -> None:
    """Deep link: ``?hs=0901`` en la URL selecciona ese producto al cargar.

    Solo actúa en la primera carga de la sesión (después manda el selector) y
    solo si el snapshot de la partida existe; un ``hs`` desconocido se ignora
    en silencio (degradar con gracia).
    """
    if _PRODUCT_SELECT_KEY in st.session_state:
        return
    url_hs = st.query_params.get("hs")
    if not url_hs:
        return
    normalized = hs_codes.normalize_hs(url_hs)
    if normalized in products:
        st.session_state[_PRODUCT_SELECT_KEY] = normalized


def _load_snapshot(hs: str) -> tuple[pd.DataFrame, dict[str, object], dict[str, object]]:
    """Lee ranking, metadatos y narrativa del snapshot de un producto.

    Returns:
        Tupla (ranking, meta, narrative) leída de ``data/processed/<hs>/``.
        Si el snapshot no trae narrativa, ``narrative`` queda vacío y la app
        omite esa sección (degradar con gracia).

    Raises:
        FileNotFoundError: si el snapshot todavía no fue construido.
    """
    ranking = pd.read_parquet(config.ranking_parquet(hs))
    meta: dict[str, object] = json.loads(config.snapshot_meta_json(hs).read_text(encoding="utf-8"))
    narrative: dict[str, object] = {}
    if config.narrative_json(hs).exists():
        narrative = json.loads(config.narrative_json(hs).read_text(encoding="utf-8"))
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
    return pd.read_parquet(path)


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


def _market_detail_section(ranking: pd.DataFrame, narrative: dict[str, object]) -> None:
    """Ficha narrativa por mercado: frases por reglas, cada una con su número."""
    markets = narrative.get("markets")
    if not isinstance(markets, dict) or not markets:
        return
    st.subheader(t("market_detail_subheader"))
    names = ranking.set_index(config.COL_COUNTRY)[config.COL_COUNTRY_NAME]
    selected = st.selectbox(
        t("market_detail_select_label"),
        options=list(ranking[config.COL_COUNTRY]),
        format_func=lambda iso3: f"{flag_emoji(iso3)} {names.get(iso3, iso3)} ({iso3})".strip(),
    )
    for sentence in markets.get(selected, []):
        st.markdown(f"- {sentence}")


def _comparator_section(products: dict[str, str]) -> None:
    """Comparador: los mejores mercados de 2–3 partidas, lado a lado.

    Solo lee snapshots ya construidos (nada de red ni cálculo): responde
    «¿a qué mercado le apuesto con cuál producto?» de una mirada.
    """
    if len(products) < 2:
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

{macro_filter_text}

{final_score_text}

{t("methodology_footer")}
"""
        )


def _map_tab(ranking: pd.DataFrame) -> None:
    """Choropleth del score final por destino (plotly acepta ISO3 directo).

    Presentación pura: pinta columnas ya presentes en el ranking; el color es
    el score final y el hover trae las métricas que lo explican.
    """
    st.caption(t("map_caption"))
    fig = px.choropleth(
        ranking,
        locations=config.COL_COUNTRY,
        color=config.COL_FINAL_SCORE,
        hover_name=config.COL_COUNTRY_NAME,
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
    fig.update_traces(marker_line_color="#FFFFFF", marker_line_width=0.6)
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
    st.plotly_chart(fig, use_container_width=True)


def _evolution_tab(
    ranking: pd.DataFrame, meta: dict[str, object], timeseries: pd.DataFrame
) -> None:
    """Evolución anual de las importaciones por destino (indexada o absoluta).

    Presentación pura sobre la serie que el pipeline dejó en el snapshot.
    Vista indexada (default): todos los mercados en la misma escala para
    comparar ritmos; vista absoluta en millones de USD.
    """
    names = ranking.set_index(config.COL_COUNTRY)[config.COL_COUNTRY_NAME]
    default_markets = list(ranking.nsmallest(5, config.COL_RANK)[config.COL_COUNTRY_NAME])
    selected_names = st.multiselect(
        t("evolution_select_markets_label"),
        options=list(names.sort_values()),
        default=default_markets,
    )
    view_index, view_absolute = t("evolution_view_index"), t("evolution_view_absolute")
    view = st.radio(
        t("evolution_view_label"),
        options=[view_index, view_absolute],
        horizontal=True,
        help=t("evolution_view_help"),
    )
    selected_iso3 = [iso3 for iso3, name in names.items() if name in selected_names]
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


def _ranking_table(ranking: pd.DataFrame, meta: dict[str, object]) -> None:
    """Tabla del ranking con los números formateados en el idioma activo.

    Los formatos de ``st.column_config`` no sirven aquí: los printf usan
    siempre punto decimal y ``"localized"`` sigue el locale del navegador,
    no el toggle de idioma de la app. Por eso los valores se formatean con
    ``pandas.Styler`` usando las mismas funciones de ``app/format.py`` que
    el resto de la app; los datos siguen siendo numéricos, así que la
    alineación a la derecha se conserva.
    """
    flagged_names = (
        ranking[config.COL_COUNTRY].map(flag_emoji) + " " + ranking[config.COL_COUNTRY_NAME]
    ).str.strip()
    display = ranking.drop(columns=[config.COL_RCA]).assign(
        **{config.COL_COUNTRY_NAME: flagged_names}
    )
    formats: dict[str, Callable[[float], str]] = {
        config.COL_MARKET_SIZE: lambda v: i18n.fmt_number(v),
        config.COL_GROWTH: lambda v: i18n.fmt_pct(v, signed=True),
        config.COL_SHARE: lambda v: i18n.fmt_pct(v),
        config.COL_SHARE_TREND: lambda v: i18n.fmt_pct(v, signed=True),
        config.COL_COMPLEMENTARITY: lambda v: i18n.fmt_number(v, 2),
        config.COL_TARIFF: lambda v: i18n.fmt_pct(v),
        config.COL_STABILITY: lambda v: i18n.fmt_number(v, 2),
        config.COL_SCORE: lambda v: i18n.fmt_number(v, 3),
        config.COL_FINAL_SCORE: lambda v: i18n.fmt_number(v, 3),
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
    st.dataframe(
        styler,
        hide_index=True,
        width="stretch",
        column_config={
            config.COL_RANK: st.column_config.Column("#"),
            config.COL_COUNTRY: st.column_config.Column("ISO3"),
            config.COL_COUNTRY_NAME: st.column_config.Column(t("col_market")),
            config.COL_MARKET_SIZE: st.column_config.Column(
                t("col_market_size", years=meta["market_size_years"])
            ),
            config.COL_GROWTH: st.column_config.Column(t("col_growth")),
            config.COL_SHARE: st.column_config.Column(t("col_share")),
            config.COL_SHARE_TREND: st.column_config.Column(t("col_share_trend")),
            config.COL_COMPLEMENTARITY: st.column_config.Column(t("col_complementarity")),
            config.COL_TARIFF: st.column_config.Column(t("col_tariff")),
            config.COL_STABILITY: st.column_config.Column(t("col_stability")),
            config.COL_SCORE: st.column_config.Column(t("col_score_raw")),
            config.COL_FINAL_SCORE: st.column_config.Column(t("col_score_final")),
        },
    )


def _weight_lab_section(ranking: pd.DataFrame, meta: dict[str, object]) -> None:
    """Laboratorio de pesos: sliders → re-ranking en vivo (what-if).

    Las fórmulas viven en ``domain/scoring`` (funciones puras, testeadas);
    la app solo recoge los pesos del usuario, invoca al dominio y compara el
    resultado contra el ranking oficial del snapshot.
    """
    available = [name for name, col in scoring.METRIC_COLUMNS.items() if col in ranking.columns]
    if not available or config.COL_STABILITY not in ranking.columns:
        return
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
        slider_columns = st.columns(3)
        raw_weights: dict[str, int] = {}
        for i, name in enumerate(available):
            default = official_weights.get(name, config.WEIGHTS.get(name, 0.0))
            with slider_columns[i % 3]:
                raw_weights[name] = st.slider(
                    i18n.metric_label(name),
                    min_value=0,
                    max_value=100,
                    value=int(round(default * 100)),
                    step=5,
                    format="%d%%",
                    key=f"lab_w_{name}",
                )
        total = sum(raw_weights.values())
        if total == 0:
            st.info(t("lab_zero_info"))
            return
        weights = {name: value / total for name, value in raw_weights.items()}
        effective = " · ".join(
            f"{i18n.metric_label(name)} {i18n.fmt_pct(weight, 0)}"
            for name, weight in weights.items()
            if weight > 0
        )
        st.caption(t("lab_effective_weights", weights=effective))
        floor = float(str(meta.get("macro_floor") or config.MACRO_FLOOR))
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
        st.dataframe(display, hide_index=True, width="stretch")


def _scores_tab(ranking: pd.DataFrame) -> None:
    """Score bruto vs. final por mercado: la brecha es la penalización macro.

    Plotly en lugar de ``st.bar_chart`` para que ejes y hover respeten los
    separadores del idioma activo (``separators``), igual que el mapa y la
    evolución.
    """
    st.caption(t("tab_scores_caption"))
    ordered = ranking.sort_values(config.COL_FINAL_SCORE, ascending=True)
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
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "title": None},
        xaxis={"title": None},
        yaxis={"title": None},
        hovermode="y unified",
    )
    st.plotly_chart(fig, use_container_width=True)


def _size_tab(ranking: pd.DataFrame, meta: dict[str, object]) -> None:
    """Tamaño de cada mercado partido en «ya lo vende el origen» vs. resto."""
    st.caption(t("tab_size_caption", origin=meta["origin_iso3"]))
    ordered = ranking.sort_values(config.COL_MARKET_SIZE, ascending=True)
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
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
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
    col_demand, col_growth, col_share, col_rca = st.columns(4)
    col_demand.metric(
        t("kpi_demand_label"),
        i18n.fmt_usd_compact(total),
        delta=t("kpi_demand_delta", n=len(ranking)),
        delta_color="off",
    )
    col_growth.metric(
        t("kpi_growth_label"),
        i18n.fmt_pct(growth, signed=True),
        delta=t("kpi_growth_delta"),
        delta_color="off",
    )
    col_share.metric(
        t("kpi_share_label"),
        i18n.fmt_pct(share),
        delta=t("kpi_share_delta"),
        delta_color="off",
    )
    rca = meta.get("rca_balassa")
    if rca is not None:
        rca_value = float(str(rca))
        col_rca.metric(
            t("kpi_rca_label"),
            i18n.fmt_number(rca_value, 1),
            delta=t("kpi_rca_delta_yes") if rca_value > 1 else t("kpi_rca_delta_no"),
            delta_color="off",
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

    products = _available_products()
    _advanced_search_section(products)
    if not products:
        st.error(t("no_snapshots_error"))
        return
    _sync_product_from_url(products)
    hs = st.selectbox(
        t("product_select_label"),
        options=list(products),
        format_func=lambda code: products[code],
        key=_PRODUCT_SELECT_KEY,
    )
    st.query_params["hs"] = hs  # URL compartible: ?hs=<partida>
    ranking, meta, narrative = _load_snapshot(hs)
    narrative = _narrative_in_language(narrative)
    ranking = _localize_country_names(ranking)
    product_label = i18n.product_label(hs, str(meta["hs_label"]))

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
    _ranking_table(ranking, meta)
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

    _weight_lab_section(ranking, meta)

    timeseries = _load_imports_timeseries(hs)
    tab_labels = [t("tab_map"), t("tab_scores"), t("tab_size")]
    if timeseries is not None:
        tab_labels.append(t("tab_evolution"))
    tabs = st.tabs(tab_labels)
    tab_map, tab_scores, tab_size = tabs[0], tabs[1], tabs[2]
    with tab_map:
        _map_tab(ranking)
    with tab_scores:
        _scores_tab(ranking)
    with tab_size:
        _size_tab(ranking, meta)

    if timeseries is not None:
        with tabs[3]:
            _evolution_tab(ranking, meta, timeseries)

    _market_detail_section(ranking, narrative)
    _comparator_section(products)


if __name__ == "__main__":
    main()
