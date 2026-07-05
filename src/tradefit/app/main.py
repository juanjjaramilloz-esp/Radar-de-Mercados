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


def _load_snapshot() -> tuple[pd.DataFrame, dict[str, object], dict[str, object]]:
    """Lee ranking, metadatos y narrativa del snapshot.

    Returns:
        Tupla (ranking, meta, narrative) leída de ``data/processed/``. Si el
        snapshot es viejo y no trae narrativa, ``narrative`` queda vacío y la
        app omite esa sección (degradar con gracia).

    Raises:
        FileNotFoundError: si el snapshot todavía no fue construido.
    """
    ranking = pd.read_parquet(config.RANKING_PARQUET)
    meta: dict[str, object] = json.loads(config.SNAPSHOT_META_JSON.read_text(encoding="utf-8"))
    narrative: dict[str, object] = {}
    if config.NARRATIVE_JSON.exists():
        narrative = json.loads(config.NARRATIVE_JSON.read_text(encoding="utf-8"))
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

    try:
        ranking, meta, narrative = _load_snapshot()
    except FileNotFoundError:
        st.error(
            "No hay snapshot en `data/processed/`. Genera uno con:\n\n"
            "```\npython -m tradefit.pipeline.build_snapshot\n```"
        )
        return

    rca = meta.get("rca_balassa")
    rca_text = f" · RCA del origen en el producto: **{rca}**" if rca is not None else ""
    st.caption(
        f"Producto: **{meta['hs_label']}** · Origen: **{meta['origin_iso3']}** · "
        f"Fuente: {meta['source']} · Datos {meta['data_year_min']}–{meta['data_year_max']} · "
        f"{meta['n_markets']} mercados{rca_text}"
    )

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
