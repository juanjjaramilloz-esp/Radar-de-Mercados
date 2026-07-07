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

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from tradefit import config, hs_codes
from tradefit.app.export import ranking_to_excel, ranking_to_pdf
from tradefit.pipeline.build_snapshot import ensure_snapshot

_PRODUCT_SELECT_KEY = "product_select"
_TOUR_SEEN_KEY = "tour_seen"


def _hero_section() -> None:
    """Propuesta de valor y mini-tour: el usuario aterriza sin contexto.

    El expander del tour llega abierto solo en la primera carga de la sesión
    (``st.session_state``); después queda plegado y disponible.
    """
    st.markdown(
        "Dado un **producto** (partida arancelaria HS) y un **país de origen**, "
        "esta herramienta rankea mercados destino combinando la **oportunidad "
        "comercial** (tamaño, crecimiento, cuota, complementariedad) con un "
        "**filtro de estabilidad macroeconómica** del destino."
    )
    first_load = _TOUR_SEEN_KEY not in st.session_state
    st.session_state[_TOUR_SEEN_KEY] = True
    with st.expander("🧭 ¿Cómo leo esto? — tour de 30 segundos", expanded=first_load):
        st.markdown(
            "- **Podio y ranking**: los mercados destino ordenados por **score "
            "final** (0–1) = oportunidad comercial × estabilidad macro.\n"
            "- **Recomendación**: el porqué de cada top, con sus números "
            "(crecimiento de la demanda, cuota ya ganada, complementariedad).\n"
            "- **🔎 Buscador avanzado**: escribe cualquier partida (p. ej. "
            "`1701` o «coffee») y la app descarga los datos de UN Comtrade y "
            "construye el análisis al momento.\n"
            "- **📖 Metodología**: la fórmula y la cita académica de cada "
            "métrica; el ranking se exporta a CSV, Excel o PDF."
        )


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
            products[hs] = str(meta.get("hs_label", hs))
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
        st.warning(
            "Sin `COMTRADE_API_KEY` configurada el análisis usa el preview "
            "público de Comtrade y puede fallar por su tope de registros."
        )
    try:
        with st.spinner(
            f"Descargando datos de UN Comtrade para la partida {hs} "
            "(≈12 consultas; puede tardar un minuto)…"
        ):
            ensure_snapshot(hs)
    except ValueError as exc:
        st.error(f"Partida inválida: {exc}")
        return False
    except Exception as exc:  # noqa: BLE001 — presentación: degradar con gracia
        st.error(
            f"No se pudo construir el análisis de la partida {hs}. "
            f"Puede que no exista en la nomenclatura o que la fuente no tenga "
            f"datos para el periodo. Detalle: {exc}"
        )
        return False
    return True


def _advanced_search_section(products: dict[str, str]) -> None:
    """Buscador avanzado: cualquier partida HS → snapshot on-demand → análisis.

    El usuario escribe un código (2/4/6 dígitos) o palabras de la descripción
    (en inglés, idioma del catálogo de Comtrade); al confirmar, se descargan
    los datos de esa partida, se construye el snapshot y la app entera (ranking,
    gráficas, narrativa, export) pasa a mostrarla. Con caché: repetir una
    partida ya analizada es instantáneo.
    """
    with st.expander("🔎 Buscador avanzado: analiza cualquier partida arancelaria"):
        query = st.text_input(
            "Partida HS o palabras de la descripción (catálogo en inglés)",
            placeholder="p. ej. 1701, 09.01 o «sugar cane»",
            help="Niveles soportados: capítulo (2 dígitos), partida (4) y subpartida (6).",
        )
        if not query.strip():
            return
        selected: str | None = None
        try:
            matches = hs_codes.search_hs(query, _hs_catalog())
        except FileNotFoundError:
            matches = None  # sin catálogo local: se acepta el código a ciegas
        normalized = hs_codes.normalize_hs(query)
        if matches is not None and not matches.empty:
            labels = dict(zip(matches[hs_codes.COL_HS], matches[hs_codes.COL_DESC], strict=True))
            selected = st.selectbox(
                "Coincidencias",
                options=list(labels),
                format_func=lambda code: f"{code} — {labels[code]}",
            )
        elif hs_codes.is_valid_hs(normalized):
            selected = normalized
            st.caption(
                f"La partida {normalized} no aparece en el catálogo local; "
                "se intentará consultar igual."
            )
        else:
            st.info("Sin coincidencias: prueba con el código HS o términos en inglés.")
            return
        if selected is None:
            return
        already_built = selected in products
        action = "Ver análisis" if already_built else "Descargar datos y analizar"
        go = st.button(action, type="primary", key="advanced_search_go")
        if go and (already_built or _build_on_demand(selected)):
            st.session_state[_PRODUCT_SELECT_KEY] = selected
            st.rerun()


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
    st.subheader("Recomendación: dónde enfocarse")
    for i, rec in enumerate(recommendations, start=1):
        reasons = " · ".join(rec["reasons"]) if rec["reasons"] else ""
        st.markdown(f"**{i}. {rec['name']}** (score final {rec['final_score']:.3f}) — {reasons}")


def _market_detail_section(ranking: pd.DataFrame, narrative: dict[str, object]) -> None:
    """Ficha narrativa por mercado: frases por reglas, cada una con su número."""
    markets = narrative.get("markets")
    if not isinstance(markets, dict) or not markets:
        return
    st.subheader("Lectura por mercado")
    names = ranking.set_index(config.COL_COUNTRY)[config.COL_COUNTRY_NAME]
    selected = st.selectbox(
        "Mercado",
        options=list(ranking[config.COL_COUNTRY]),
        format_func=lambda iso3: f"{names.get(iso3, iso3)} ({iso3})",
    )
    for sentence in markets.get(selected, []):
        st.markdown(f"- {sentence}")


def _methodology_section(meta: dict[str, object]) -> None:
    """Metodología: fórmula y cita de cada métrica, y cómo se combinan."""
    weights_obj = meta.get("weights")
    weights: dict[str, object] = weights_obj if isinstance(weights_obj, dict) else {}
    bounds_obj = meta.get("macro_bounds")
    bounds: dict[str, object] = bounds_obj if isinstance(bounds_obj, dict) else {}
    definitions = [
        (
            "Tamaño de mercado",
            f"Promedio de importaciones del producto en el destino, últimos "
            f"{meta.get('market_size_years')} años (cf. ITC Export Potential "
            "Indicator, Decreux & Spies 2016)",
            "market_size",
        ),
        (
            "Crecimiento",
            "CAGR de esas importaciones en la ventana: (V_final/V_inicial)^(1/n) − 1",
            "import_growth",
        ),
        (
            "Cuota del origen",
            "Participación del origen en las importaciones del destino, "
            "M_d←o / M_d (cf. WITS *partner share*)",
            "market_share",
        ),
        (
            "Momentum de cuota",
            "Δ de esa cuota entre el primer y el último año de la ventana",
            "share_trend",
        ),
        (
            "Complementariedad",
            "Índice de Michaely (1996): C = 1 − Σ\\|m_dk − x_ok\\|/2 sobre "
            "capítulos HS2 (usado por el Banco Mundial en WITS)",
            "complementarity",
        ),
    ]
    table = "\n".join(
        f"| {name} | {definition} | {weights.get(key, '—')} |"
        for name, definition, key in definitions
    )
    with st.expander("📖 Metodología: de dónde sale cada número"):
        st.markdown(
            f"""
**Métricas de oportunidad** (min-max normalizadas y combinadas con los pesos
documentados en `config.py`; suman 1.0):

| Métrica | Definición | Peso |
|---|---|---|
{table}

**RCA de Balassa (1965)** — (X_ok/X_o)/(X_wk/X_w) — se reporta como contexto:
es constante entre destinos, así que no pondera en el ranking.

**Filtro macro de estabilidad** (World Bank WDI, promedio de los últimos
{meta.get("macro_years")} años con dato): cada indicador se normaliza con una
rampa lineal entre umbrales fijos (normalización min-max con umbrales, cf.
OECD/JRC *Handbook on Constructing Composite Indicators*, 2008):
inflación {bounds.get("inflation", "—")}, crecimiento del PIB
{bounds.get("gdp_growth", "—")}, cuenta corriente {bounds.get("current_account", "—")}
(formato [peor, mejor], en %).

**Score final** = score de oportunidad × ({meta.get("macro_floor")} +
{round(1 - float(str(meta.get("macro_floor") or 0.5)), 2)} × estabilidad): un
destino totalmente inestable conserva el piso, no se anula.

Cada métrica tiene su test con un valor calculado a mano; los datos crudos se
cachean en `data/raw/` y el snapshot es reproducible (mismo input → mismo output).
"""
        )


def _top3_cards(ranking: pd.DataFrame) -> None:
    """Tarjetas del podio: los 3 mercados con mejor score final."""
    top3 = ranking.nsmallest(3, config.COL_RANK)
    medals = ["🥇", "🥈", "🥉"]
    for column, (_, row), medal in zip(st.columns(3), top3.iterrows(), medals, strict=False):
        with column:
            st.metric(
                label=f"{medal} {row[config.COL_COUNTRY_NAME]}",
                value=f"{row[config.COL_FINAL_SCORE]:.3f}",
                delta=f"estabilidad {row[config.COL_STABILITY]:.2f}",
                delta_color="off",
            )


def main() -> None:
    """Renderiza la página principal: ranking de mercados destino."""
    st.set_page_config(page_title="Radar de Mercados", page_icon="📡", layout="wide")
    st.title("📡 Radar de Mercados")
    _hero_section()

    products = _available_products()
    _advanced_search_section(products)
    if not products:
        st.error(
            "No hay snapshots en `data/processed/`. Usa el buscador avanzado "
            "de arriba o genera uno con:\n\n"
            "```\npython -m tradefit.pipeline.build_snapshot\n```"
        )
        return
    hs = st.selectbox(
        "Producto",
        options=list(products),
        format_func=lambda code: products[code],
        key=_PRODUCT_SELECT_KEY,
    )
    ranking, meta, narrative = _load_snapshot(hs)

    rca = meta.get("rca_balassa")
    rca_text = f" · RCA del origen en el producto: **{rca}**" if rca is not None else ""
    st.caption(
        f"Producto: **{meta['hs_label']}** · Origen: **{meta['origin_iso3']}** · "
        f"Fuente: {meta['source']} · Datos {meta['data_year_min']}–{meta['data_year_max']} · "
        f"{meta['n_markets']} mercados{rca_text}"
    )

    _methodology_section(meta)
    _top3_cards(ranking)
    _recommendations_section(narrative)

    st.subheader("Ranking de mercados destino")
    st.caption(
        "Score final = oportunidad comercial × penalización por estabilidad macro "
        f"(piso {meta.get('macro_floor', '—')}; indicadores WDI: inflación, "
        "crecimiento del PIB y cuenta corriente)."
    )
    display = ranking.drop(columns=[config.COL_RCA]).assign(
        **{config.COL_MARKET_SIZE: ranking[config.COL_MARKET_SIZE].round().astype("int64")}
    )
    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        column_config={
            config.COL_RANK: st.column_config.NumberColumn("#"),
            config.COL_COUNTRY: st.column_config.TextColumn("ISO3"),
            config.COL_COUNTRY_NAME: st.column_config.TextColumn("Mercado"),
            config.COL_MARKET_SIZE: st.column_config.NumberColumn(
                f"Importaciones prom. {meta['market_size_years']} años (USD)",
                format="localized",
            ),
            config.COL_GROWTH: st.column_config.NumberColumn(
                "Crecimiento (CAGR)", format="percent"
            ),
            config.COL_SHARE: st.column_config.NumberColumn("Cuota del origen", format="percent"),
            config.COL_SHARE_TREND: st.column_config.NumberColumn(
                "Δ cuota (ventana)", format="percent"
            ),
            config.COL_COMPLEMENTARITY: st.column_config.NumberColumn(
                "Complementariedad", format="%.2f"
            ),
            config.COL_STABILITY: st.column_config.NumberColumn("Estabilidad macro", format="%.2f"),
            config.COL_SCORE: st.column_config.NumberColumn("Score bruto", format="%.3f"),
            config.COL_FINAL_SCORE: st.column_config.ProgressColumn(
                "Score final", min_value=0.0, max_value=1.0, format="%.3f"
            ),
        },
    )
    base_name = f"radar_{meta['hs_code']}_{meta['origin_iso3']}"
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
            data=ranking_to_excel(ranking, meta, narrative),
            file_name=f"{base_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with col_pdf:
        st.download_button(
            "⬇️ PDF",
            data=ranking_to_pdf(ranking, meta, narrative),
            file_name=f"{base_name}.pdf",
            mime="application/pdf",
        )

    timeseries = _load_imports_timeseries(hs)
    tab_labels = ["Oportunidad vs. score final", "Tamaño de mercado"]
    if timeseries is not None:
        tab_labels.append("Evolución del mercado")
    tabs = st.tabs(tab_labels)
    tab_scores, tab_size = tabs[0], tabs[1]
    with tab_scores:
        st.caption(
            "La distancia entre las barras es la penalización macro: donde el score "
            "final se acerca al bruto, el destino es estable."
        )
        scores = ranking.set_index(config.COL_COUNTRY_NAME)[
            [config.COL_SCORE, config.COL_FINAL_SCORE]
        ].rename(columns={config.COL_SCORE: "Score bruto", config.COL_FINAL_SCORE: "Score final"})
        st.bar_chart(scores, horizontal=True)
    with tab_size:
        st.caption(
            f"La porción clara es lo que ya vende {meta['origin_iso3']} en cada mercado "
            "(cuota del último año × tamaño promedio); la oscura, el resto del mercado."
        )
        by_market = ranking.set_index(config.COL_COUNTRY_NAME)
        from_origin = by_market[config.COL_MARKET_SIZE] * by_market[config.COL_SHARE]
        size_chart = pd.DataFrame(
            {
                f"Desde {meta['origin_iso3']}": from_origin,
                "Resto del mercado": by_market[config.COL_MARKET_SIZE] - from_origin,
            }
        )
        st.bar_chart(size_chart, horizontal=True, color=["#93C5FD", "#1D4ED8"])

    if timeseries is not None:
        with tabs[2]:
            names = ranking.set_index(config.COL_COUNTRY)[config.COL_COUNTRY_NAME]
            default_markets = list(ranking.nsmallest(5, config.COL_RANK)[config.COL_COUNTRY_NAME])
            selected_names = st.multiselect(
                "Mercados a mostrar",
                options=list(names.sort_values()),
                default=default_markets,
            )
            view = st.radio(
                "Vista",
                options=["Variación (año base = 100)", "Valor absoluto (USD)"],
                horizontal=True,
                help=(
                    "En valor absoluto, un mercado grande (p. ej. Estados Unidos) "
                    "aplasta en el eje a los mercados chicos aunque estos crezcan más "
                    "rápido; la variación indexada pone a todos en la misma escala."
                ),
            )
            selected_iso3 = [iso3 for iso3, name in names.items() if name in selected_names]
            if selected_iso3:
                by_year = (
                    timeseries[timeseries[config.COL_COUNTRY].isin(selected_iso3)]
                    .assign(**{config.COL_COUNTRY_NAME: lambda d: d[config.COL_COUNTRY].map(names)})
                    .pivot(
                        index=config.COL_YEAR,
                        columns=config.COL_COUNTRY_NAME,
                        values=config.COL_IMPORTS_USD,
                    )
                )
                if view == "Variación (año base = 100)":
                    st.caption(
                        f"Importaciones anuales del producto, indexadas a "
                        f"{meta['data_year_min']} = 100 (periodo disponible: "
                        f"{meta['data_year_min']}–{meta['data_year_max']})."
                    )
                    st.line_chart(by_year.div(by_year.iloc[0]).mul(100.0))
                else:
                    st.caption(
                        "Importaciones anuales del producto por destino (USD); "
                        f"periodo disponible: {meta['data_year_min']}–{meta['data_year_max']}."
                    )
                    st.line_chart(by_year)
            else:
                st.info("Selecciona al menos un mercado para ver su evolución.")

    _market_detail_section(ranking, narrative)


if __name__ == "__main__":
    main()
