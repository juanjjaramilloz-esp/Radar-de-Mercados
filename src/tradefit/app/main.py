"""App Streamlit del Radar de Mercados.

Capa de presentación: SOLO lee el snapshot de ``data/processed/``. No llama
APIs, no importa ``ingest`` y no calcula índices. Si el snapshot no existe,
degrada con gracia mostrando cómo generarlo.
"""

import json

import pandas as pd
import streamlit as st

from tradefit import config
from tradefit.app.export import ranking_to_excel, ranking_to_pdf


def _available_products() -> dict[str, str]:
    """Productos con snapshot construido: ``{hs: etiqueta}`` desde meta.json."""
    products: dict[str, str] = {}
    for hs in sorted(config.PRODUCTS):
        meta_path = config.snapshot_meta_json(hs)
        if meta_path.exists() and config.ranking_parquet(hs).exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            products[hs] = str(meta.get("hs_label", hs))
    return products


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

    products = _available_products()
    if not products:
        st.error(
            "No hay snapshots en `data/processed/`. Genera uno con:\n\n"
            "```\npython -m tradefit.pipeline.build_snapshot\n```"
        )
        return
    hs = st.selectbox(
        "Producto",
        options=list(products),
        format_func=lambda code: products[code],
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
    st.dataframe(
        ranking.drop(columns=[config.COL_RCA]),
        hide_index=True,
        width="stretch",
        column_config={
            config.COL_RANK: st.column_config.NumberColumn("#"),
            config.COL_COUNTRY: st.column_config.TextColumn("ISO3"),
            config.COL_COUNTRY_NAME: st.column_config.TextColumn("Mercado"),
            config.COL_MARKET_SIZE: st.column_config.NumberColumn(
                f"Importaciones prom. {meta['market_size_years']} años (USD)",
                format="%.0f",
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

    tab_scores, tab_size = st.tabs(["Oportunidad vs. score final", "Tamaño de mercado"])
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
        st.bar_chart(
            ranking.set_index(config.COL_COUNTRY_NAME)[config.COL_MARKET_SIZE],
            horizontal=True,
        )

    _market_detail_section(ranking, narrative)


if __name__ == "__main__":
    main()
