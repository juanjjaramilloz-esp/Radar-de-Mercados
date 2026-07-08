"""Internacionalización de la app (español/inglés).

Módulo de presentación pura: guarda el idioma activo en la sesión y traduce
los textos propios de ``app/`` (chrome estático, metodología, mapa,
comparador, nombres de los productos/países curados). La narrativa
(recomendaciones, lectura por mercado) la genera ``domain/narrative.py`` en
ambos idiomas dentro de ``narrative.json``; la app solo elige la del idioma
activo (``main._narrative_in_language``).
"""

from typing import Final

import streamlit as st

from tradefit import config
from tradefit.app.format import Lang, format_number, format_pct, plotly_separators

_LANG_KEY: Final = "app_lang"
_DEFAULT_LANG: Final[Lang] = "es"


def get_language() -> Lang:
    """Idioma activo de la sesión (``"es"`` por defecto)."""
    lang = st.session_state.get(_LANG_KEY, _DEFAULT_LANG)
    return "en" if lang == "en" else "es"


def language_toggle() -> None:
    """Selector de idioma en la sidebar; guarda la elección en la sesión."""
    with st.sidebar:
        st.selectbox(
            "🌐 Idioma / Language",
            options=["es", "en"],
            format_func=lambda code: {"es": "🇪🇸 Español", "en": "🇬🇧 English"}[code],
            key=_LANG_KEY,
        )


def t(key: str, **kwargs: object) -> str:
    """Texto de ``key`` en el idioma activo; formatea con ``kwargs`` si se pasan."""
    text = _STRINGS[key][get_language()]
    return text.format(**kwargs) if kwargs else text


def fmt_number(value: float, decimals: int = 0, signed: bool = False) -> str:
    """Número formateado en el idioma activo (es → ``1.234,5``; en → ``1,234.5``)."""
    return format_number(value, decimals, get_language(), signed)


def fmt_pct(fraction: float, decimals: int = 1, signed: bool = False) -> str:
    """Fracción como porcentaje en el idioma activo (``0.202 → "20,2 %"`` en español)."""
    return format_pct(fraction, decimals, get_language(), signed)


def fmt_usd_compact(value: float) -> str:
    """Monto USD legible en el idioma activo: millones o miles de millones."""
    if value >= 1e9:
        return t("usd_billion", value=fmt_number(value / 1e9, 1))
    return t("usd_million", value=fmt_number(value / 1e6, 0))


def active_plotly_separators() -> str:
    """Cadena ``separators`` de Plotly (decimal + miles) para el idioma activo."""
    return plotly_separators(get_language())


def product_label(hs: str, fallback: str) -> str:
    """Etiqueta del producto en el idioma activo.

    Solo los productos curados (:data:`config.PRODUCTS_EN`) tienen versión
    en inglés; una partida construida on-demand ya trae su descripción del
    catálogo en inglés como ``fallback`` y no necesita traducción.
    """
    if get_language() == "en":
        return config.PRODUCTS_EN.get(hs, fallback)
    return fallback


def country_name(iso3: str, fallback: str) -> str:
    """Nombre del país en el idioma activo (los 18 destinos del MVP tienen inglés)."""
    if get_language() == "en":
        return config.DESTINATIONS_EN.get(iso3, fallback)
    return fallback


#: Etapas que emite ``pipeline.build_snapshot`` vía ``on_stage``; se traducen
#: solo para mostrarlas — el pipeline sigue emitiendo español (no conoce la
#: app ni su idioma).
_STAGE_TRANSLATIONS: Final[dict[str, str]] = {
    "Importaciones del producto por destino (UN Comtrade)": (
        "Product imports by destination (UN Comtrade)"
    ),
    "Flujo bilateral desde el origen": "Bilateral flow from the origin",
    "Canastas exportadora e importadora (complementariedad)": (
        "Export and import baskets (complementarity)"
    ),
    "Totales de exportación para el RCA": "Export totals for the RCA",
    "Indicadores macro (World Bank WDI)": "Macro indicators (World Bank WDI)",
    "Insumos locales de ejemplo (stub, sin red)": "Local sample inputs (stub, no network)",
    "Calculando índices, estabilidad macro y ranking": (
        "Computing indices, macro stability and ranking"
    ),
    "Escribiendo el snapshot": "Writing the snapshot",
}


def translate_stage(stage: str) -> str:
    """Traduce una etapa del pipeline al inglés si ese es el idioma activo."""
    if get_language() == "en":
        return _STAGE_TRANSLATIONS.get(stage, stage)
    return stage


_STRINGS: Final[dict[str, dict[Lang, str]]] = {
    "page_title": {"es": "Radar de Mercados", "en": "Market Radar"},
    "app_title": {"es": "📡 Radar de Mercados", "en": "📡 Market Radar"},
    "about_header": {"es": "Sobre el proyecto", "en": "About this project"},
    "about_body": {
        "es": (
            "Screener de mercados de exportación con un motor económico "
            "defendible: **cada métrica cita su definición académica y "
            "tiene test con un valor calculado a mano**.\n\n"
            "**Stack** · Python · Streamlit · pandas\n\n"
            "**Datos** · UN Comtrade Plus · World Bank WDI\n\n"
            "**Código** · [GitHub: radar-de-mercados]"
            "(https://github.com/juanjjaramilloz-esp/Radar-de-Mercados)"
        ),
        "en": (
            "Export market screener built on a defensible economic engine: "
            "**every metric cites its academic definition and has a test "
            "with a hand-calculated value**.\n\n"
            "**Stack** · Python · Streamlit · pandas\n\n"
            "**Data** · UN Comtrade Plus · World Bank WDI\n\n"
            "**Code** · [GitHub: radar-de-mercados]"
            "(https://github.com/juanjjaramilloz-esp/Radar-de-Mercados)"
        ),
    },
    "about_caption": {
        "es": (
            "Arquitectura en capas con dependencias en una sola dirección: "
            "`ingest` (red) → `domain` (cálculo puro y testeado) → `app` "
            "(solo presentación)."
        ),
        "en": (
            "Layered architecture with one-way dependencies: `ingest` "
            "(network) → `domain` (pure, tested calculation) → `app` "
            "(presentation only)."
        ),
    },
    "hero_value_prop": {
        "es": (
            "Dado un **producto** (partida arancelaria HS) y un **país de "
            "origen**, esta herramienta rankea mercados destino combinando "
            "la **oportunidad comercial** (tamaño, crecimiento, cuota, "
            "complementariedad) con un **filtro de estabilidad "
            "macroeconómica** del destino."
        ),
        "en": (
            "Given a **product** (HS tariff line) and an **origin country**, "
            "this tool ranks destination markets by combining **commercial "
            "opportunity** (size, growth, share, complementarity) with a "
            "**macroeconomic stability filter** on the destination."
        ),
    },
    "hero_tour_title": {
        "es": "🧭 ¿Cómo leo esto? — tour de 30 segundos",
        "en": "🧭 How do I read this? — 30-second tour",
    },
    "hero_tour_body": {
        "es": (
            "- **Podio y ranking**: los mercados destino ordenados por "
            "**score final** (0–1) = oportunidad comercial × estabilidad "
            "macro.\n"
            "- **Recomendación**: el porqué de cada top, con sus números "
            "(crecimiento de la demanda, cuota ya ganada, "
            "complementariedad).\n"
            "- **🔎 Buscador avanzado**: escribe cualquier partida (p. ej. "
            "`1701` o «café») y la app descarga los datos de UN Comtrade y "
            "construye el análisis al momento.\n"
            "- **📖 Metodología**: la fórmula y la cita académica de cada "
            "métrica; el ranking se exporta a CSV, Excel o PDF."
        ),
        "en": (
            "- **Podium and ranking**: destination markets ordered by "
            "**final score** (0–1) = commercial opportunity × macro "
            "stability.\n"
            "- **Recommendation**: the why behind each top pick, with the "
            "numbers (demand growth, share already won, complementarity).\n"
            "- **🔎 Advanced search**: type any tariff line (e.g. `1701` or "
            "«coffee») and the app downloads UN Comtrade data and builds "
            "the analysis on the spot.\n"
            "- **📖 Methodology**: the formula and academic citation behind "
            "every metric; export the ranking to CSV, Excel or PDF."
        ),
    },
    "search_expander_title": {
        "es": "🔎 Buscador avanzado: analiza cualquier partida arancelaria",
        "en": "🔎 Advanced search: analyze any tariff line",
    },
    "search_input_label": {
        "es": "Partida HS o nombre del producto (español o inglés)",
        "en": "HS code or product name (English)",
    },
    "search_input_placeholder": {
        "es": "p. ej. 1701, 09.01, «café» o «sugar cane»",
        "en": "e.g. 1701, 09.01 or «sugar cane»",
    },
    "search_input_help": {
        "es": "Niveles soportados: capítulo (2 dígitos), partida (4) y subpartida (6).",
        "en": "Supported levels: chapter (2 digits), heading (4) and subheading (6).",
    },
    "search_matches_label": {"es": "Coincidencias", "en": "Matches"},
    "search_hs_not_in_catalog": {
        "es": ("La partida {hs} no aparece en el catálogo local; se intentará consultar igual."),
        "en": "{hs} doesn't appear in the local catalog; it will be queried anyway.",
    },
    "search_no_matches_info": {
        "es": (
            "Sin coincidencias: prueba con el código HS o el nombre del "
            "producto (español o inglés)."
        ),
        "en": "No matches: try the HS code or the product name in English.",
    },
    "search_button_view": {"es": "Ver análisis", "en": "View analysis"},
    "search_button_download": {
        "es": "Descargar datos y analizar",
        "en": "Download data and analyze",
    },
    "search_api_key_warning": {
        "es": (
            "Sin `COMTRADE_API_KEY` configurada el análisis usa el preview "
            "público de Comtrade y puede fallar por su tope de registros."
        ),
        "en": (
            "Without `COMTRADE_API_KEY` set, the analysis uses Comtrade's "
            "public preview and may fail due to its record cap."
        ),
    },
    "search_status_building": {
        "es": "Construyendo el análisis de la partida {hs} (puede tardar un minuto)…",
        "en": "Building the analysis for {hs} (may take a minute)…",
    },
    "search_status_invalid": {
        "es": "Partida inválida: {error}",
        "en": "Invalid tariff line: {error}",
    },
    "search_status_failed": {
        "es": "No se pudo construir el análisis de {hs}",
        "en": "Could not build the analysis for {hs}",
    },
    "search_error_body": {
        "es": (
            "No se pudo construir el análisis de la partida {hs}. "
            "Puede que no exista en la nomenclatura o que la fuente no "
            "tenga datos para el periodo. Detalle: {error}"
        ),
        "en": (
            "Could not build the analysis for {hs}. It may not exist in "
            "the nomenclature, or the source may have no data for the "
            "period. Detail: {error}"
        ),
    },
    "search_status_done": {
        "es": "Análisis de la partida {hs} listo ✅",
        "en": "Analysis for {hs} ready ✅",
    },
    "recommendations_subheader": {
        "es": "Recomendación: dónde enfocarse",
        "en": "Recommendation: where to focus",
    },
    "market_detail_subheader": {"es": "Lectura por mercado", "en": "Market notes"},
    "market_detail_select_label": {"es": "Mercado", "en": "Market"},
    "comparator_subheader": {
        "es": "⚖️ Comparador de productos",
        "en": "⚖️ Product comparator",
    },
    "comparator_caption": {
        "es": (
            "Elige dos o tres partidas ya analizadas y compara sus mejores "
            "mercados; construye más partidas con el buscador avanzado."
        ),
        "en": (
            "Pick two or three already-analyzed tariff lines and compare "
            "their best markets; build more with the advanced search."
        ),
    },
    "comparator_select_label": {
        "es": "Productos a comparar",
        "en": "Products to compare",
    },
    "comparator_select_info": {
        "es": "Selecciona al menos dos productos para comparar.",
        "en": "Select at least two products to compare.",
    },
    "comparator_missing_warning": {
        "es": "El snapshot de {code} ya no está disponible.",
        "en": "The snapshot for {code} is no longer available.",
    },
    "comparator_rca_demand": {
        "es": "RCA del origen: {rca} · demanda {demand}",
        "en": "Origin's RCA: {rca} · demand {demand}",
    },
    "methodology_expander_title": {
        "es": "📖 Metodología: de dónde sale cada número",
        "en": "📖 Methodology: where every number comes from",
    },
    "methodology_intro": {
        "es": (
            "**Métricas de oportunidad** (min-max normalizadas y "
            "combinadas con los pesos documentados en `config.py`; suman "
            "1.0):"
        ),
        "en": (
            "**Opportunity metrics** (min-max normalized and combined "
            "with the weights documented in `config.py`; they sum to 1.0):"
        ),
    },
    "methodology_col_metric": {"es": "Métrica", "en": "Metric"},
    "methodology_col_definition": {"es": "Definición", "en": "Definition"},
    "methodology_col_weight": {"es": "Peso", "en": "Weight"},
    "methodology_metric_market_size": {"es": "Tamaño de mercado", "en": "Market size"},
    "methodology_def_market_size": {
        "es": (
            "Promedio de importaciones del producto en el destino, "
            "últimos {years} años (cf. ITC Export Potential Indicator, "
            "Decreux & Spies 2016)"
        ),
        "en": (
            "Average product imports into the destination, last {years} "
            "years (cf. ITC Export Potential Indicator, Decreux & Spies 2016)"
        ),
    },
    "methodology_metric_growth": {"es": "Crecimiento", "en": "Growth"},
    "methodology_def_growth": {
        "es": "CAGR de esas importaciones en la ventana: (V_final/V_inicial)^(1/n) − 1",
        "en": "CAGR of those imports over the window: (V_final/V_initial)^(1/n) − 1",
    },
    "methodology_metric_share": {"es": "Cuota del origen", "en": "Origin's share"},
    "methodology_def_share": {
        "es": (
            "Participación del origen en las importaciones del destino, "
            "M_d←o / M_d (cf. WITS *partner share*)"
        ),
        "en": (
            "Origin's share of the destination's imports, M_d←o / M_d (cf. WITS *partner share*)"
        ),
    },
    "methodology_metric_share_trend": {
        "es": "Momentum de cuota",
        "en": "Share momentum",
    },
    "methodology_def_share_trend": {
        "es": "Δ de esa cuota entre el primer y el último año de la ventana",
        "en": "Δ of that share between the first and last year of the window",
    },
    "methodology_metric_complementarity": {
        "es": "Complementariedad",
        "en": "Complementarity",
    },
    "methodology_def_complementarity": {
        "es": (
            "Índice de Michaely (1996): C = 1 − Σ|m_dk − x_ok|/2 sobre "
            "capítulos HS2 (usado por el Banco Mundial en WITS)"
        ),
        "en": (
            "Michaely index (1996): C = 1 − Σ|m_dk − x_ok|/2 over HS2 "
            "chapters (used by the World Bank in WITS)"
        ),
    },
    "methodology_metric_tariff": {
        "es": "Arancel enfrentado",
        "en": "Tariff faced",
    },
    "methodology_def_tariff": {
        "es": (
            "Arancel efectivamente aplicado al origen: mín(MFN, "
            "preferencial), promedio simple de las subpartidas HS6 "
            "(cf. WITS *effectively applied — AHS*; invertido: menos "
            "arancel = mejor)"
        ),
        "en": (
            "Tariff effectively applied to the origin: min(MFN, "
            "preferential), simple average over HS6 subheadings "
            "(cf. WITS *effectively applied — AHS*; inverted: lower "
            "tariff = better)"
        ),
    },
    "methodology_rca_note": {
        "es": (
            "**RCA de Balassa (1965)** — (X_ok/X_o)/(X_wk/X_w) — se reporta "
            "como contexto: es constante entre destinos, así que no "
            "pondera en el ranking."
        ),
        "en": (
            "**Balassa's RCA (1965)** — (X_ok/X_o)/(X_wk/X_w) — reported "
            "as context: it's constant across destinations, so it doesn't "
            "weigh into the ranking."
        ),
    },
    "methodology_macro_filter": {
        "es": (
            "**Filtro macro de estabilidad** (World Bank WDI, promedio de "
            "los últimos {years} años con dato): cada indicador se "
            "normaliza con una rampa lineal entre umbrales fijos "
            "(normalización min-max con umbrales, cf. OECD/JRC *Handbook "
            "on Constructing Composite Indicators*, 2008): inflación "
            "{inflation}, crecimiento del PIB {gdp}, cuenta corriente "
            "{current_account} (formato [peor, mejor], en %)."
        ),
        "en": (
            "**Macro stability filter** (World Bank WDI, average of the "
            "last {years} years with data): each indicator is normalized "
            "with a linear ramp between fixed thresholds (min-max "
            "normalization with thresholds, cf. OECD/JRC *Handbook on "
            "Constructing Composite Indicators*, 2008): inflation "
            "{inflation}, GDP growth {gdp}, current account "
            "{current_account} (format [worst, best], in %)."
        ),
    },
    "methodology_final_score": {
        "es": (
            "**Score final** = score de oportunidad × ({floor} + "
            "{floor_complement} × estabilidad): un destino totalmente "
            "inestable conserva el piso, no se anula."
        ),
        "en": (
            "**Final score** = opportunity score × ({floor} + "
            "{floor_complement} × stability): a fully unstable destination "
            "keeps the floor, it isn't zeroed out."
        ),
    },
    "methodology_footer": {
        "es": (
            "Cada métrica tiene su test con un valor calculado a mano; los "
            "datos crudos se cachean en `data/raw/` y el snapshot es "
            "reproducible (mismo input → mismo output)."
        ),
        "en": (
            "Every metric has a test with a hand-calculated value; raw "
            "data is cached in `data/raw/` and the snapshot is "
            "reproducible (same input → same output)."
        ),
    },
    "map_caption": {
        "es": (
            "Score final por mercado destino: más oscuro = mejor "
            "oportunidad ajustada por estabilidad. Pasa el cursor para "
            "ver las métricas."
        ),
        "en": (
            "Final score by destination market: darker = better "
            "stability-adjusted opportunity. Hover to see the metrics."
        ),
    },
    "map_label_final_score": {"es": "Score final", "en": "Final score"},
    "map_label_imports": {
        "es": "Importaciones (USD/año)",
        "en": "Imports (USD/year)",
    },
    "map_label_growth": {"es": "Crecimiento (CAGR)", "en": "Growth (CAGR)"},
    "map_label_share": {"es": "Cuota del origen", "en": "Origin's share"},
    "map_label_stability": {"es": "Estabilidad macro", "en": "Macro stability"},
    "usd_billion": {"es": "USD {value} B/año", "en": "USD {value} B/year"},
    "usd_million": {"es": "USD {value} M/año", "en": "USD {value} M/year"},
    "kpi_demand_label": {"es": "Demanda analizada", "en": "Demand analyzed"},
    "kpi_demand_delta": {
        "es": "{n} mercados destino",
        "en": "{n} destination markets",
    },
    "kpi_growth_label": {
        "es": "Crecimiento de la demanda",
        "en": "Demand growth",
    },
    "kpi_growth_delta": {
        "es": "CAGR ponderado por tamaño",
        "en": "Size-weighted CAGR",
    },
    "kpi_share_label": {
        "es": "Cuota agregada del origen",
        "en": "Origin's aggregate share",
    },
    "kpi_share_delta": {"es": "de la demanda analizada", "en": "of demand analyzed"},
    "kpi_rca_label": {"es": "RCA del origen", "en": "Origin's RCA"},
    "kpi_rca_delta_yes": {"es": "ventaja revelada", "en": "revealed advantage"},
    "kpi_rca_delta_no": {
        "es": "sin ventaja revelada",
        "en": "no revealed advantage",
    },
    "top3_stability_delta": {"es": "estabilidad {value}", "en": "stability {value}"},
    "no_snapshots_error": {
        "es": (
            "No hay snapshots en `data/processed/`. Usa el buscador "
            "avanzado de arriba o genera uno con:\n\n"
            "```\npython -m tradefit.pipeline.build_snapshot\n```"
        ),
        "en": (
            "No snapshots in `data/processed/`. Use the advanced search "
            "above or generate one with:\n\n"
            "```\npython -m tradefit.pipeline.build_snapshot\n```"
        ),
    },
    "product_select_label": {"es": "Producto", "en": "Product"},
    "caption_line": {
        "es": (
            "Producto: **{label}** · Origen: **{origin_flag} {origin}** · "
            "Fuente: {source} · Datos {min_year}–{max_year} · "
            "{n_markets} mercados{rca_text}"
        ),
        "en": (
            "Product: **{label}** · Origin: **{origin_flag} {origin}** · "
            "Source: {source} · Data {min_year}–{max_year} · "
            "{n_markets} markets{rca_text}"
        ),
    },
    "caption_rca_suffix": {
        "es": " · RCA del origen en el producto: **{rca}**",
        "en": " · Origin's RCA for the product: **{rca}**",
    },
    "ranking_subheader": {
        "es": "Ranking de mercados destino",
        "en": "Destination market ranking",
    },
    "ranking_caption": {
        "es": (
            "Score final = oportunidad comercial × penalización por "
            "estabilidad macro (piso {floor}; indicadores WDI: inflación, "
            "crecimiento del PIB y cuenta corriente)."
        ),
        "en": (
            "Final score = commercial opportunity × macro stability "
            "penalty (floor {floor}; WDI indicators: inflation, GDP "
            "growth and current account)."
        ),
    },
    "col_market": {"es": "Mercado", "en": "Market"},
    "col_market_size": {
        "es": "Importaciones prom. {years} años (USD)",
        "en": "Avg. imports, {years}y (USD)",
    },
    "col_growth": {"es": "Crecimiento (CAGR)", "en": "Growth (CAGR)"},
    "col_share": {"es": "Cuota del origen", "en": "Origin's share"},
    "col_share_trend": {"es": "Δ cuota (ventana)", "en": "Δ share (window)"},
    "col_complementarity": {"es": "Complementariedad", "en": "Complementarity"},
    "col_tariff": {"es": "Arancel enfrentado", "en": "Tariff faced"},
    "col_stability": {"es": "Estabilidad macro", "en": "Macro stability"},
    "col_score_raw": {"es": "Score bruto", "en": "Raw score"},
    "col_score_final": {"es": "Score final", "en": "Final score"},
    "tab_map": {"es": "🗺️ Mapa", "en": "🗺️ Map"},
    "tab_scores": {
        "es": "Oportunidad vs. score final",
        "en": "Opportunity vs. final score",
    },
    "tab_size": {"es": "Tamaño de mercado", "en": "Market size"},
    "tab_evolution": {"es": "Evolución del mercado", "en": "Market evolution"},
    "tab_scores_caption": {
        "es": (
            "La distancia entre las barras es la penalización macro: "
            "donde el score final se acerca al bruto, el destino es "
            "estable."
        ),
        "en": (
            "The gap between the bars is the macro penalty: where the "
            "final score is close to the raw one, the destination is "
            "stable."
        ),
    },
    "tab_size_caption": {
        "es": (
            "La porción clara es lo que ya vende {origin} en cada mercado "
            "(cuota del último año × tamaño promedio); la oscura, el "
            "resto del mercado."
        ),
        "en": (
            "The light portion is what {origin} already sells in each "
            "market (last year's share × average size); the dark one is "
            "the rest of the market."
        ),
    },
    "legend_from_origin": {"es": "Desde {origin}", "en": "From {origin}"},
    "legend_rest": {"es": "Resto del mercado", "en": "Rest of the market"},
    "size_xaxis_usd_m": {
        "es": "Importaciones promedio (USD M)",
        "en": "Average imports (USD M)",
    },
    "evolution_select_markets_label": {
        "es": "Mercados a mostrar",
        "en": "Markets to show",
    },
    "evolution_view_label": {"es": "Vista", "en": "View"},
    "evolution_view_index": {
        "es": "Variación (año base = 100)",
        "en": "Change (base year = 100)",
    },
    "evolution_view_absolute": {
        "es": "Valor absoluto (USD)",
        "en": "Absolute value (USD)",
    },
    "evolution_view_help": {
        "es": (
            "En valor absoluto, un mercado grande (p. ej. Estados Unidos) "
            "aplasta en el eje a los mercados chicos aunque estos crezcan "
            "más rápido; la variación indexada pone a todos en la misma "
            "escala."
        ),
        "en": (
            "In absolute value, a large market (e.g. the United States) "
            "flattens the axis for small markets even if they grow "
            "faster; the indexed view puts everyone on the same scale."
        ),
    },
    "evolution_caption_index": {
        "es": (
            "Importaciones anuales del producto, indexadas a "
            "{min_year} = 100 (periodo disponible: {min_year}–{max_year})."
        ),
        "en": (
            "Annual product imports, indexed to {min_year} = 100 "
            "(period available: {min_year}–{max_year})."
        ),
    },
    "evolution_caption_absolute": {
        "es": (
            "Importaciones anuales del producto por destino, en millones de "
            "USD (periodo disponible: {min_year}–{max_year})."
        ),
        "en": (
            "Annual product imports by destination, USD million "
            "(period available: {min_year}–{max_year})."
        ),
    },
    "evolution_yaxis_index": {
        "es": "Índice (año base = 100)",
        "en": "Index (base year = 100)",
    },
    "evolution_yaxis_usd_m": {
        "es": "Importaciones (USD M)",
        "en": "Imports (USD M)",
    },
    "evolution_select_info": {
        "es": "Selecciona al menos un mercado para ver su evolución.",
        "en": "Select at least one market to see its evolution.",
    },
}
