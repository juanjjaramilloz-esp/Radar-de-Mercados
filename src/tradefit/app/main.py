"""App Streamlit del Radar de Mercados.

Capa de presentación: SOLO lee el snapshot de ``data/processed/``. No llama
APIs, no importa ``ingest`` y no calcula índices. Si el snapshot no existe,
degrada con gracia mostrando cómo generarlo.
"""

import json

import pandas as pd
import streamlit as st

from tradefit import config


def _load_snapshot() -> tuple[pd.DataFrame, dict[str, object]]:
    """Lee ranking y metadatos del snapshot.

    Returns:
        Tupla (ranking, meta) leída de ``data/processed/``.

    Raises:
        FileNotFoundError: si el snapshot todavía no fue construido.
    """
    ranking = pd.read_parquet(config.RANKING_PARQUET)
    meta: dict[str, object] = json.loads(config.SNAPSHOT_META_JSON.read_text(encoding="utf-8"))
    return ranking, meta


def main() -> None:
    """Renderiza la página principal: ranking de mercados destino."""
    st.set_page_config(page_title="Radar de Mercados", page_icon="📡", layout="wide")
    st.title("📡 Radar de Mercados")

    try:
        ranking, meta = _load_snapshot()
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

    st.subheader("Ranking de mercados destino")
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
            config.COL_SCORE: st.column_config.ProgressColumn(
                "Score de oportunidad", min_value=0.0, max_value=1.0, format="%.3f"
            ),
        },
    )

    st.subheader("Tamaño de mercado (USD)")
    st.bar_chart(
        ranking.set_index(config.COL_COUNTRY_NAME)[config.COL_MARKET_SIZE],
        horizontal=True,
    )


if __name__ == "__main__":
    main()
