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


#: Clave de texto de la etiqueta corta de cada métrica del scoring
#: (nombres = claves de ``config.WEIGHTS``).
_METRIC_LABEL_KEYS: Final[dict[str, str]] = {
    "market_size": "methodology_metric_market_size",
    "import_growth": "methodology_metric_growth",
    "market_share": "methodology_metric_share",
    "share_trend": "methodology_metric_share_trend",
    "complementarity": "methodology_metric_complementarity",
    "tariff_faced": "methodology_metric_tariff",
}


def metric_label(name: str) -> str:
    """Etiqueta corta de una métrica del scoring en el idioma activo."""
    return t(_METRIC_LABEL_KEYS[name])


def trade_agreement(iso3: str) -> str | None:
    """Acuerdo comercial vigente Colombia–destino en el idioma activo.

    Returns:
        La etiqueta del acuerdo (``config.TRADE_AGREEMENTS``/``_EN``), o
        ``None`` si el destino no tiene acuerdo vigente con Colombia.
    """
    source = config.TRADE_AGREEMENTS_EN if get_language() == "en" else config.TRADE_AGREEMENTS
    return source.get(iso3)


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
    "Destinos de exportación del origen (concentración)": (
        "Origin's export destinations (concentration)"
    ),
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
    "about_epm_pitch": {
        "es": (
            "**¿En qué se diferencia del ITC Export Potential Map?** El EPM "
            "predice un potencial en USD con un modelo econométrico cerrado "
            "para 222 países; el Radar es **glass-box** — fórmulas citadas, "
            "pesos ajustables en vivo, filtro de riesgo macro — y profundiza "
            "en **un** origen: TLC, competidores y concentración de destinos "
            "de Colombia. Detalle en el README."
        ),
        "en": (
            "**How is this different from the ITC Export Potential Map?** "
            "EPM predicts a USD potential with a closed econometric model "
            "for 222 countries; the Radar is **glass-box** — cited formulas, "
            "live-adjustable weights, a macro-risk filter — and goes deep on "
            "**one** origin: Colombia's FTAs, competitors and destination "
            "concentration. Details in the README."
        ),
    },
    "hero_value_prop": {
        "es": (
            "Dado un **producto** (partida arancelaria HS), esta herramienta "
            "rankea mercados destino para las exportaciones de **{flag} "
            "{origin}** combinando la **oportunidad comercial** (tamaño, "
            "crecimiento, cuota, complementariedad) con un **filtro de "
            "estabilidad macroeconómica** del destino."
        ),
        "en": (
            "Given a **product** (HS tariff line), this tool ranks "
            "destination markets for **{flag} {origin}'s** exports by "
            "combining **commercial opportunity** (size, growth, share, "
            "complementarity) with a **macroeconomic stability filter** on "
            "the destination."
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
            "- **Producto**: el desplegable trae los 15 productos más "
            "exportados por Colombia (canasta no minero-energética, "
            "UN Comtrade 2024); ¿otro producto? el **🔎 buscador avanzado** "
            "analiza cualquier partida al momento.\n"
            "- **📖 Metodología**: la fórmula y la cita académica de cada "
            "métrica; el ranking se exporta a CSV, Excel o PDF."
        ),
        "en": (
            "- **Podium and ranking**: destination markets ordered by "
            "**final score** (0–1) = commercial opportunity × macro "
            "stability.\n"
            "- **Recommendation**: the why behind each top pick, with the "
            "numbers (demand growth, share already won, complementarity).\n"
            "- **Product**: the dropdown lists Colombia's 15 top exports "
            "(non-mining basket, UN Comtrade 2024); after something else? "
            "the **🔎 advanced search** analyzes any tariff line on the "
            "spot.\n"
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
    "focus_subheader": {"es": "🔎 Ficha del destino", "en": "🔎 Destination profile"},
    "focus_caption": {
        "es": (
            "Haz clic en un país del mapa (pestaña 🗺️) o elígelo aquí: la "
            "ficha reúne todo lo que el Radar sabe de ese mercado para este "
            "producto."
        ),
        "en": (
            "Click a country on the map (🗺️ tab) or pick one here: the "
            "profile gathers everything the Radar knows about that market "
            "for this product."
        ),
    },
    "focus_select_label": {"es": "Mercado en foco", "en": "Focused market"},
    "focus_select_placeholder": {"es": "— sin foco —", "en": "— no focus —"},
    "focus_clear": {"es": "✕ Quitar foco", "en": "✕ Clear focus"},
    "focus_hint": {
        "es": (
            "💡 Elige un mercado arriba, haz clic en el mapa (🗺️ Mapa) o en "
            "una fila de la tabla para ver su ficha."
        ),
        "en": ("💡 Pick a market above, click the map (🗺️ Map) or a table row to see its profile."),
    },
    "focus_select_help": {
        "es": (
            "Fija el mercado cuya ficha quieres ver; también puedes hacer "
            "clic en el mapa o en una fila de la tabla del ranking."
        ),
        "en": (
            "Sets the market whose profile you want to see; you can also "
            "click the map or a row in the ranking table."
        ),
    },
    "focus_header_rank": {
        "es": "#{rank} de {n} mercados",
        "en": "#{rank} of {n} markets",
    },
    "focus_no_agreement": {"es": "sin acuerdo vigente", "en": "no agreement in force"},
    "focus_share_window": {"es": "en la ventana", "en": "over the window"},
    "focus_origin_share_delta": {
        "es": "de las export. COL del producto",
        "en": "of COL's exports of the product",
    },
    "focus_drivers": {
        "es": "**Qué empuja su score:** {drivers} — contribución peso×norm al score bruto.",
        "en": "**What drives its score:** {drivers} — weight×norm contribution to the raw score.",
    },
    "focus_macro_header": {
        "es": "Contexto macro y logístico",
        "en": "Macro & logistics context",
    },
    "macro_inflation": {"es": "Inflación", "en": "Inflation"},
    "macro_gdp_growth": {"es": "Crecimiento del PIB", "en": "GDP growth"},
    "macro_current_account": {
        "es": "Cuenta corriente (% PIB)",
        "en": "Current account (% GDP)",
    },
    "focus_competitors_header": {
        "es": "Quién le vende {product} a este mercado",
        "en": "Who sells {product} to this market",
    },
    "focus_competitors_caption": {
        "es": "Top proveedores por cuota (UN Comtrade, {year}); Colombia resaltada.",
        "en": "Top suppliers by share (UN Comtrade, {year}); Colombia highlighted.",
    },
    "focus_colombia_position": {
        "es": "**Colombia es el proveedor #{rank}** con el {share} de las importaciones ({year}).",
        "en": "**Colombia is supplier #{rank}** with {share} of imports ({year}).",
    },
    "focus_colombia_absent": {
        "es": "Colombia no aparece entre los proveedores registrados ({year}).",
        "en": "Colombia does not appear among the recorded suppliers ({year}).",
    },
    "focus_competitors_missing": {
        "es": "Sin datos de competidores para este destino (el país no reportó el producto).",
        "en": "No competitor data for this destination (the country did not report the product).",
    },
    "focus_competitors_xaxis": {
        "es": "% de las importaciones del destino",
        "en": "% of the destination's imports",
    },
    "focus_evolution_header": {
        "es": "Evolución de sus importaciones (USD M)",
        "en": "Its imports over time (USD M)",
    },
    "focus_narrative_header": {"es": "Lectura del mercado", "en": "Market notes"},
    "map_focus_hint": {
        "es": "💡 Haz clic en un país para fijar el foco y abrir su ficha (abajo).",
        "en": "💡 Click a country to set focus and open its profile (below).",
    },
    "table_focus_hint": {
        "es": "💡 Haz clic en una fila para fijar el foco y abrir su ficha (abajo).",
        "en": "💡 Click a row to set focus and open its profile (below).",
    },
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
    "comparator_needs_more_info": {
        "es": (
            "⚖️ Comparador de productos: analiza al menos 2 partidas HS "
            "para comparar sus mejores mercados lado a lado."
        ),
        "en": (
            "⚖️ Product comparator: analyze at least 2 HS tariff lines to "
            "compare their best markets side by side."
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
    "methodology_hhi_note": {
        "es": (
            "**Concentración de destinos** — HHI de Herfindahl–Hirschman "
            "(Hirschman 1964): Σ cuotas² de los destinos de exportación "
            "colombianos del producto (todos los socios, no solo los del "
            "radar). Lectura: > 0,25 alta, 0,15–0,25 moderada (umbrales de "
            "las guías DOJ/FTC 2010). Contexto: no pondera en el score."
        ),
        "en": (
            "**Destination concentration** — Herfindahl–Hirschman index "
            "(Hirschman 1964): Σ squared shares of Colombia's export "
            "destinations for the product (all partners, not just the "
            "radar's). Reading: > 0.25 high, 0.15–0.25 moderate (DOJ/FTC "
            "2010 merger guidelines). Context: it does not weigh in the "
            "score."
        ),
    },
    "methodology_lpi_note": {
        "es": (
            "**LPI del destino** — Logistics Performance Index del Banco "
            "Mundial (*Connecting to Compete*; escala 1–5, más es mejor): "
            "desempeño logístico del destino (aduanas, infraestructura, "
            "envíos internacionales). Publicación esparsa (~cada 4–5 años): "
            "se toma el último año con dato por país. Contexto: no pondera "
            "en el score."
        ),
        "en": (
            "**Destination LPI** — World Bank Logistics Performance Index "
            "(*Connecting to Compete*; 1–5 scale, higher is better): the "
            "destination's logistics performance (customs, infrastructure, "
            "international shipments). Published sparsely (~every 4–5 "
            "years): the latest year with data per country is used. "
            "Context: it does not weigh in the score."
        ),
    },
    "methodology_agreement_note": {
        "es": (
            "**Acuerdos comerciales** — la columna «Acuerdo comercial» es "
            "contexto (fuente: MinCIT, acuerdos vigentes): su efecto sobre "
            "el acceso ya está capturado por el arancel efectivamente "
            "aplicado (AHS), así que no pondera aparte en el score."
        ),
        "en": (
            "**Trade agreements** — the «Trade agreement» column is context "
            "(source: MinCIT, agreements in force): its effect on access is "
            "already captured by the effectively applied tariff (AHS), so "
            "it does not weigh separately in the score."
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
    "kpi_demand_help": {
        "es": (
            "Suma de las importaciones promedio del producto en los "
            "mercados analizados (Comtrade, USD/año)."
        ),
        "en": (
            "Sum of the product's average imports across the analyzed markets (Comtrade, USD/year)."
        ),
    },
    "kpi_growth_label": {
        "es": "Crecimiento de la demanda",
        "en": "Demand growth",
    },
    "kpi_growth_delta": {
        "es": "CAGR ponderado por tamaño",
        "en": "Size-weighted CAGR",
    },
    "kpi_growth_help": {
        "es": (
            "CAGR de las importaciones de cada destino, promediado "
            "ponderando por el tamaño de cada mercado."
        ),
        "en": ("CAGR of each destination's imports, averaged weighted by each market's size."),
    },
    "kpi_share_label": {
        "es": "Cuota agregada del origen",
        "en": "Origin's aggregate share",
    },
    "kpi_share_delta": {"es": "de la demanda analizada", "en": "of demand analyzed"},
    "kpi_share_help": {
        "es": (
            "Cuota de Colombia en las importaciones del producto, agregada "
            "sobre los mercados analizados: promedio de la cuota por "
            "destino ponderado por el tamaño de cada mercado."
        ),
        "en": (
            "Colombia's share of the product's imports, aggregated across "
            "the analyzed markets: the per-destination share averaged "
            "weighted by each market's size."
        ),
    },
    "kpi_hhi_label": {
        "es": "Concentración de destinos (HHI)",
        "en": "Destination concentration (HHI)",
    },
    "kpi_hhi_high": {"es": "alta (HHI > 0,25)", "en": "high (HHI > 0.25)"},
    "kpi_hhi_moderate": {
        "es": "moderada (HHI 0,15–0,25)",
        "en": "moderate (HHI 0.15–0.25)",
    },
    "kpi_hhi_low": {"es": "baja (HHI < 0,15)", "en": "low (HHI < 0.15)"},
    "kpi_hhi_help": {
        "es": (
            "HHI = índice de Herfindahl–Hirschman: Σ cuotas² de los "
            "destinos de exportación colombianos del producto. 0 = "
            "repartido entre muchos destinos, 1 = un solo destino."
        ),
        "en": (
            "HHI = Herfindahl–Hirschman index: Σ squared shares of "
            "Colombia's export destinations for the product. 0 = spread "
            "across many destinations, 1 = a single destination."
        ),
    },
    "kpi_rca_help": {
        "es": (
            "RCA = Ventaja Comparativa Revelada (Balassa 1965): peso del "
            "producto en la canasta exportadora de Colombia frente a su "
            "peso en el comercio mundial. > 1 = ventaja revelada."
        ),
        "en": (
            "RCA = Revealed Comparative Advantage (Balassa 1965): the "
            "product's weight in Colombia's export basket vs. its weight "
            "in world trade. > 1 = revealed advantage."
        ),
    },
    "kpi_rca_label": {"es": "RCA del origen", "en": "Origin's RCA"},
    "kpi_rca_delta_yes": {"es": "ventaja revelada", "en": "revealed advantage"},
    "kpi_rca_delta_no": {
        "es": "sin ventaja revelada",
        "en": "no revealed advantage",
    },
    "top3_stability_delta": {"es": "estabilidad {value}", "en": "stability {value}"},
    "product_select_label": {"es": "📦 Elige el producto", "en": "📦 Choose the product"},
    "product_select_help": {
        "es": (
            "Top 15 de exportaciones de Colombia por partida HS4 "
            "(UN Comtrade 2024), excluyendo minero-energéticos (capítulos "
            "27 y 71), en orden de valor exportado. ¿Otro producto? Usa el "
            "buscador avanzado."
        ),
        "en": (
            "Colombia's top 15 exports by HS4 heading (UN Comtrade 2024), "
            "excluding mining and energy (chapters 27 and 71), ordered by "
            "export value. Looking for something else? Use the advanced "
            "search."
        ),
    },
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
    "col_rank_help": {
        "es": "Posición en el ranking por score final (1 = mejor oportunidad).",
        "en": "Rank by final score (1 = best opportunity).",
    },
    "col_iso3_help": {
        "es": "Código ISO 3166-1 alfa-3 del mercado destino.",
        "en": "ISO 3166-1 alpha-3 code of the destination market.",
    },
    "col_market": {"es": "Mercado", "en": "Market"},
    "col_market_help": {
        "es": "Mercado destino analizado; clic en la fila para abrir su ficha.",
        "en": "Destination market analyzed; click the row to open its profile.",
    },
    "col_market_size": {
        "es": "Importaciones prom. {years} años (USD)",
        "en": "Avg. imports, {years}y (USD)",
    },
    "col_market_size_help": {
        "es": (
            "Tamaño del mercado: importaciones del producto promediadas "
            "sobre los últimos {years} años con dato (Comtrade, USD)."
        ),
        "en": (
            "Market size: the destination's imports of the product "
            "averaged over the last {years} years with data (Comtrade, USD)."
        ),
    },
    "col_growth": {"es": "Crecimiento (CAGR)", "en": "Growth (CAGR)"},
    "col_growth_help": {
        "es": (
            "Crecimiento anual compuesto (CAGR) de las importaciones del "
            "destino entre el primer y el último año de la ventana."
        ),
        "en": (
            "Compound annual growth rate (CAGR) of the destination's "
            "imports between the first and last year of the window."
        ),
    },
    "col_share": {"es": "Cuota del origen", "en": "Origin's share"},
    "col_share_help": {
        "es": "% de las importaciones del destino que ya cubre Colombia.",
        "en": "% of the destination's imports already covered by Colombia.",
    },
    "col_share_trend": {"es": "Δ cuota (ventana)", "en": "Δ share (window)"},
    "col_share_trend_help": {
        "es": (
            "Cambio de la cuota de Colombia entre el primer y el último "
            "año de la ventana (puntos porcentuales): ¿está ganando o "
            "perdiendo terreno?"
        ),
        "en": (
            "Change in Colombia's share between the first and last year "
            "of the window (percentage points): is it gaining or losing "
            "ground?"
        ),
    },
    "col_origin_export_share": {
        "es": "% export. de Colombia",
        "en": "% of Colombia's exports",
    },
    "col_origin_export_share_help": {
        "es": (
            "% de las exportaciones colombianas del producto que van a ese "
            "destino (no confundir con la cuota del origen, que mira las "
            "importaciones del destino)."
        ),
        "en": (
            "% of Colombia's exports of the product that go to that "
            "destination (not the origin's share, which looks at the "
            "destination's imports)."
        ),
    },
    "col_complementarity": {"es": "Complementariedad", "en": "Complementarity"},
    "col_complementarity_help": {
        "es": (
            "Índice de Michaely (0–1): qué tanto encaja la canasta "
            "exportadora de Colombia con la canasta importadora del "
            "destino. Más alto = mejor encaje comercial."
        ),
        "en": (
            "Michaely index (0–1): how well Colombia's export basket "
            "matches the destination's import basket. Higher = better "
            "trade fit."
        ),
    },
    "col_tariff": {"es": "Arancel enfrentado", "en": "Tariff faced"},
    "col_tariff_help": {
        "es": (
            "Arancel efectivamente aplicado a Colombia (AHS de WITS: "
            "mínimo entre MFN y preferencial, promedio simple de las "
            "subpartidas HS6). Menos = mejor; en el score entra invertido."
        ),
        "en": (
            "Tariff effectively applied to Colombia (WITS AHS: minimum of "
            "MFN and preferential, simple average across HS6 subheadings). "
            "Lower = better; it enters the score inverted."
        ),
    },
    "col_agreement": {"es": "Acuerdo comercial", "en": "Trade agreement"},
    "col_agreement_help": {
        "es": (
            "Acuerdo comercial vigente entre Colombia y el destino "
            "(fuente MinCIT). El arancel enfrentado ya refleja sus "
            "preferencias."
        ),
        "en": (
            "Trade agreement in force between Colombia and the "
            "destination (source: MinCIT). The tariff faced already "
            "reflects its preferences."
        ),
    },
    "col_lpi": {"es": "LPI logístico (1–5)", "en": "Logistics LPI (1–5)"},
    "col_lpi_help": {
        "es": (
            "LPI = Índice de Desempeño Logístico del Banco Mundial "
            "(aduanas, infraestructura, envíos); escala 1–5, más es mejor."
        ),
        "en": (
            "LPI = World Bank Logistics Performance Index (customs, "
            "infrastructure, shipments); 1–5 scale, higher is better."
        ),
    },
    "col_stability": {"es": "Estabilidad macro", "en": "Macro stability"},
    "col_stability_help": {
        "es": (
            "Filtro macro del destino (0–1) con indicadores WDI: "
            "inflación, crecimiento del PIB y cuenta corriente, vía "
            "rampas lineales. Sin dato = 0,5 neutro."
        ),
        "en": (
            "Destination macro filter (0–1) from WDI indicators: "
            "inflation, GDP growth and current account, via linear "
            "ramps. Missing data = neutral 0.5."
        ),
    },
    "col_score_raw": {"es": "Score bruto", "en": "Raw score"},
    "col_score_raw_help": {
        "es": (
            "Oportunidad comercial: suma ponderada de las métricas "
            "normalizadas (pesos en el panel de metodología), ANTES del "
            "filtro de estabilidad macro."
        ),
        "en": (
            "Commercial opportunity: weighted sum of the normalized "
            "metrics (weights in the methodology panel), BEFORE the "
            "macro stability filter."
        ),
    },
    "col_score_final": {"es": "Score final", "en": "Final score"},
    "col_score_final_help": {
        "es": (
            "Score bruto × penalización macro: bruto × (piso + "
            "(1 − piso) × estabilidad). Es el orden del ranking."
        ),
        "en": (
            "Raw score × macro penalty: raw × (floor + (1 − floor) × "
            "stability). This is the ranking order."
        ),
    },
    "columns_popover_label": {"es": "⚙️ Columnas", "en": "⚙️ Columns"},
    "columns_select_label": {
        "es": "Columnas visibles en la tabla",
        "en": "Columns shown in the table",
    },
    "columns_select_help": {
        "es": (
            "El ranking (#) y el mercado siempre se muestran. Los exports "
            "CSV/Excel/PDF llevan todas las columnas."
        ),
        "en": ("Rank (#) and market are always shown. CSV/Excel/PDF exports include every column."),
    },
    "tab_map": {"es": "🗺️ Mapa", "en": "🗺️ Map"},
    "tab_breakdown": {"es": "¿Por qué este score?", "en": "Why this score?"},
    "tab_radar": {"es": "🕸️ Perfil comparado", "en": "🕸️ Compared profile"},
    "radar_caption": {
        "es": (
            "Perfil de cada mercado en las métricas del scoring, "
            "normalizadas a [0, 1] sobre los mercados analizados (min-max, "
            "las mismas del motor). Más área = mejor perfil; el arancel va "
            "invertido (más lejos del centro = menos arancel)."
        ),
        "en": (
            "Each market's profile across the scoring metrics, normalized "
            "to [0, 1] over the analyzed markets (min-max, same as the "
            "engine). More area = better profile; the tariff is inverted "
            "(farther from the center = lower tariff)."
        ),
    },
    "compare_select_label": {
        "es": "🔍 Mercados a comparar (máx. 3)",
        "en": "🔍 Markets to compare (max 3)",
    },
    "compare_select_help": {
        "es": (
            "Elige 2–3 mercados y TODAS las gráficas de abajo (mapa, "
            "desglose, radar, scores, tamaño, valor unitario, evolución) "
            "muestran solo esos. Vacío = todos los mercados."
        ),
        "en": (
            "Pick 2–3 markets and ALL the charts below (map, breakdown, "
            "radar, scores, size, unit value, evolution) show only those. "
            "Empty = every market."
        ),
    },
    "compare_active_note": {
        "es": (
            "Comparación activa: las gráficas muestran solo los mercados "
            "seleccionados. Vacía la selección para volver a todos."
        ),
        "en": (
            "Comparison active: the charts show only the selected "
            "markets. Clear the selection to get every market back."
        ),
    },
    "radar_compare_hint": {
        "es": (
            "Mostrando el top-3 del ranking; elige otros mercados en "
            "«🔍 Mercados a comparar», encima de las pestañas."
        ),
        "en": (
            "Showing the ranking's top 3; pick other markets in "
            "“🔍 Markets to compare”, above the tabs."
        ),
    },
    "breakdown_caption": {
        "es": (
            "Cada barra suma el score de oportunidad (antes de la "
            "penalización macro): contribución = peso × métrica normalizada "
            "(min-max sobre los mercados analizados)."
        ),
        "en": (
            "Each bar adds up to the opportunity score (before the macro "
            "penalty): contribution = weight × normalized metric (min-max "
            "over the analyzed markets)."
        ),
    },
    "tab_scores": {
        "es": "Score bruto vs. final",
        "en": "Raw vs. final score",
    },
    "tab_size": {"es": "Tamaño de mercado", "en": "Market size"},
    "tab_evolution": {"es": "Evolución del mercado", "en": "Market evolution"},
    "tab_unit_value": {"es": "💲 Valor unitario", "en": "💲 Unit value"},
    "uv_tab_caption": {
        "es": (
            "Valor unitario = valor importado ÷ peso neto (USD/kg, "
            "últimos {years} años con dato): el precio implícito del "
            "producto en cada destino. El rombo ámbar es el valor unitario "
            "de {origin} en ese destino — por encima de la barra sugiere "
            "posicionamiento premium; por debajo, competencia por precio. "
            "Ojo experto: dentro de una partida HS4 conviven calidades y "
            "grados de procesamiento distintos, así que el premium mezcla "
            "precio con composición."
        ),
        "en": (
            "Unit value = import value ÷ net weight (USD/kg, last {years} "
            "years with data): the product's implicit price in each "
            "destination. The amber diamond is {origin}'s unit value in "
            "that destination — above the bar suggests premium "
            "positioning; below it, price competition. Expert caveat: an "
            "HS4 heading mixes qualities and processing grades, so the "
            "premium blends price with composition."
        ),
    },
    "uv_legend_market": {
        "es": "Promedio del destino (todos los proveedores)",
        "en": "Destination average (all suppliers)",
    },
    "uv_legend_origin": {"es": "{origin} en ese destino", "en": "{origin} in that destination"},
    "uv_xaxis": {"es": "USD por kg", "en": "USD per kg"},
    "uv_focus_market_label": {
        "es": "Valor unitario del destino",
        "en": "Destination unit value",
    },
    "uv_focus_origin_label": {
        "es": "Valor unitario de {origin} aquí",
        "en": "{origin}'s unit value here",
    },
    "uv_focus_premium_delta": {
        "es": "{pct} vs. promedio del destino",
        "en": "{pct} vs. destination average",
    },
    "uv_focus_help": {
        "es": (
            "USD/kg = valor ÷ peso neto (Comtrade), agregado sobre los "
            "últimos años con dato. Premium > 0: el origen vende por "
            "encima del precio implícito promedio del destino."
        ),
        "en": (
            "USD/kg = value ÷ net weight (Comtrade), aggregated over the "
            "last years with data. Premium > 0: the origin sells above "
            "the destination's average implicit price."
        ),
    },
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
    "lab_expander_title": {
        "es": "🎯 Simulador de prioridades: ¿y si priorizas otra cosa?",
        "en": "🎯 Priority simulator: what if your priorities differ?",
    },
    "lab_caption": {
        "es": (
            "Mueve los pesos —o el piso de la penalización macro— y el "
            "ranking se recalcula en vivo con las mismas fórmulas del motor "
            "(`domain/`, puras y testeadas). Los pesos se normalizan a suma "
            "1. El ranking oficial de arriba usa los valores documentados y "
            "justificados en `config.py`."
        ),
        "en": (
            "Move the weights — or the macro penalty floor — and the "
            "ranking is recomputed live with the engine's own formulas "
            "(`domain/`, pure and tested). Weights are normalized to sum "
            "1. The official ranking above uses the values documented and "
            "justified in `config.py`."
        ),
    },
    "lab_reset": {"es": "↺ Valores oficiales", "en": "↺ Official values"},
    "lab_slider_help": {
        "es": (
            "Peso relativo de esta métrica en el score: los pesos se "
            "normalizan a suma 1 y el ranking se recalcula en vivo."
        ),
        "en": (
            "This metric's relative weight in the score: weights are "
            "normalized to sum 1 and the ranking is recomputed live."
        ),
    },
    "lab_floor_label": {
        "es": "🛡️ Penalización por estabilidad macro (piso)",
        "en": "🛡️ Macro stability penalty (floor)",
    },
    "lab_floor_help": {
        "es": (
            "Piso de la penalización: score final = score bruto × (piso + "
            "(1 − piso) × estabilidad). Con 100 % el filtro macro se apaga "
            "(final = bruto); con 0 % la estabilidad multiplica el score "
            "completo. El oficial es {official} %."
        ),
        "en": (
            "Penalty floor: final score = raw score × (floor + (1 − floor) "
            "× stability). At 100% the macro filter is off (final = raw); "
            "at 0% stability multiplies the whole score. The official "
            "value is {official}%."
        ),
    },
    "lab_zero_info": {
        "es": "Sube al menos un peso para recalcular el ranking.",
        "en": "Raise at least one weight to recompute the ranking.",
    },
    "lab_effective_weights": {
        "es": "Pesos efectivos: {weights}",
        "en": "Effective weights: {weights}",
    },
    "lab_col_delta": {"es": "Δ posición", "en": "Δ position"},
    "lab_total_note": {
        "es": (
            "La suma de los deslizadores es {total}%: no pasa nada, los "
            "pesos son relativos y se normalizan a 100% antes de calcular."
        ),
        "en": (
            "The sliders add up to {total}%: that's fine — weights are "
            "relative and get normalized to 100% before computing."
        ),
    },
    "lab_download_csv": {
        "es": "⬇️ CSV (ranking simulado)",
        "en": "⬇️ CSV (simulated ranking)",
    },
    "lab_export_note": {
        "es": (
            "Los botones CSV/Excel/PDF de arriba exportan siempre el "
            "ranking oficial; este CSV lleva el ranking con tus pesos."
        ),
        "en": (
            "The CSV/Excel/PDF buttons above always export the official "
            "ranking; this CSV carries the ranking with your weights."
        ),
    },
    "lab_live_note": {
        "es": (
            "🎯 Simulador activo: el mapa, las gráficas y la ficha de "
            "destino de abajo reflejan tus prioridades (pesos y/o "
            "penalización macro), no las oficiales. Usa «↺ Valores "
            "oficiales» en el simulador para volver."
        ),
        "en": (
            "🎯 Simulator active: the map, the charts and the market "
            "sheet below reflect your priorities (weights and/or macro "
            "penalty), not the official ones. Use “↺ Official values” in "
            "the simulator to go back."
        ),
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
