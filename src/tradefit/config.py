"""Configuración centralizada: paths, constantes, nombres de columnas y pesos.

Único lugar del código donde viven rutas, nombres de columnas y parámetros del
scoring. El resto del código importa de aquí; cero números mágicos dispersos.
"""

from pathlib import Path
from typing import Final

# --- Paths (todos relativos a la raíz del repo) ---
ROOT_DIR: Final = Path(__file__).resolve().parents[2]
DATA_DIR: Final = ROOT_DIR / "data"
RAW_DIR: Final = DATA_DIR / "raw"
INTERIM_DIR: Final = DATA_DIR / "interim"
PROCESSED_DIR: Final = DATA_DIR / "processed"
SAMPLE_DIR: Final = DATA_DIR / "sample"

STUB_IMPORTS_CSV: Final = SAMPLE_DIR / "stub_imports.csv"
STUB_BILATERAL_CSV: Final = SAMPLE_DIR / "stub_bilateral.csv"
STUB_BASKETS_CSV: Final = SAMPLE_DIR / "stub_baskets.csv"
STUB_EXPORT_TOTALS_CSV: Final = SAMPLE_DIR / "stub_export_totals.csv"
RANKING_PARQUET: Final = PROCESSED_DIR / "ranking.parquet"
SNAPSHOT_META_JSON: Final = PROCESSED_DIR / "meta.json"
NARRATIVE_JSON: Final = PROCESSED_DIR / "narrative.json"

# Cantidad de mercados recomendados en la narrativa (top-N del ranking).
TOP_RECOMMENDATIONS: Final = 3

# --- Producto y origen del MVP (fijos hasta el backlog "selección libre") ---
HS_CODE: Final = "0901"
HS_LABEL: Final = "Café (HS 0901)"
ORIGIN_ISO3: Final = "COL"

# --- Mercados destino del MVP (ISO3 → nombre en español) ---
DESTINATIONS: Final[dict[str, str]] = {
    "USA": "Estados Unidos",
    "DEU": "Alemania",
    "ITA": "Italia",
    "FRA": "Francia",
    "JPN": "Japón",
    "CAN": "Canadá",
    "BEL": "Bélgica",
    "NLD": "Países Bajos",
    "ESP": "España",
    "GBR": "Reino Unido",
    "KOR": "Corea del Sur",
    "CHE": "Suiza",
    "POL": "Polonia",
    "SWE": "Suecia",
    "AUS": "Australia",
    "PRT": "Portugal",
    "FIN": "Finlandia",
    "AUT": "Austria",
}

# Códigos de reporter de UN Comtrade (basados en M49; ojo con los códigos
# especiales de Comtrade: USA=842, Francia=251, Suiza=757; Italia es 380
# en Comtrade Plus, no el 381 del legacy).
COMTRADE_REPORTER_CODES: Final[dict[str, int]] = {
    "USA": 842,
    "DEU": 276,
    "ITA": 380,
    "FRA": 251,
    "JPN": 392,
    "CAN": 124,
    "BEL": 56,
    "NLD": 528,
    "ESP": 724,
    "GBR": 826,
    "KOR": 410,
    "CHE": 757,
    "POL": 616,
    "SWE": 752,
    "AUS": 36,
    "PRT": 620,
    "FIN": 246,
    "AUT": 40,
}

# Años de importaciones a descargar (fijos para que el snapshot sea reproducible).
IMPORT_YEARS: Final[tuple[int, ...]] = (2022, 2023, 2024)

# --- UN Comtrade Plus ---
ENV_COMTRADE_KEY: Final = "COMTRADE_API_KEY"
COMTRADE_URL_AUTH: Final = "https://comtradeapi.un.org/data/v1/get/C/A/HS"
COMTRADE_URL_PREVIEW: Final = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
COMTRADE_CACHE_FILE: Final = RAW_DIR / f"comtrade_{HS_CODE}_imports.json"
COMTRADE_BILATERAL_CACHE: Final = RAW_DIR / f"comtrade_{HS_CODE}_bilateral_{ORIGIN_ISO3}.json"
COMTRADE_EXPORTS_CACHE: Final = RAW_DIR / f"comtrade_{HS_CODE}_export_totals.json"
COMTRADE_BASKETS_CACHE: Final = RAW_DIR / "comtrade_baskets_hs2.json"

# Código de reporter/partner de Comtrade para el país de origen (Colombia).
ORIGIN_COMTRADE_CODE: Final = 170
# Códigos de commodity especiales de Comtrade.
COMTRADE_CMD_TOTAL: Final = "TOTAL"  # comercio total del reporter
COMTRADE_CMD_ALL_HS2: Final = "AG2"  # todos los capítulos HS a 2 dígitos
# Año de las canastas comerciales para complementariedad (el más reciente).
BASKET_YEAR: Final = max(IMPORT_YEARS)

# --- World Bank WDI (filtro macro de estabilidad; sin API key) ---
WDI_URL: Final = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"
WDI_CACHE_FILE: Final = RAW_DIR / "wdi_macro.json"
STUB_MACRO_CSV: Final = SAMPLE_DIR / "stub_macro.csv"
# Rango de años a descargar; el score usa los últimos MACRO_YEARS con dato.
WDI_DATE_RANGE: Final = "2020:2024"
MACRO_YEARS: Final = 3

# Indicadores WDI del filtro (código → nombre corto usado en el contrato).
WDI_INDICATORS: Final[dict[str, str]] = {
    "FP.CPI.TOTL.ZG": "inflation",  # inflación anual, precios al consumidor (%)
    "NY.GDP.MKTP.KD.ZG": "gdp_growth",  # crecimiento real del PIB (%)
    "BN.CAB.XOKA.GD.ZS": "current_account",  # cuenta corriente (% del PIB)
}

# Rampas de estabilidad por indicador: (peor, mejor) → score lineal en [0, 1].
# Valores en el peor extremo o más allá puntúan 0; en el mejor o más allá, 1.
# Justificación: inflación ≤2% es la meta típica de bancos centrales de la
# OCDE y ≥15% es estrés macro severo; crecimiento del PIB ≤−2% es recesión
# marcada y ≥3% expansión sólida; cuenta corriente ≤−5% del PIB es el umbral
# clásico de vulnerabilidad externa (cf. los "twin deficits") y ≥0% elimina
# esa vulnerabilidad. Rampas lineales: transparentes y defendibles.
MACRO_BOUNDS: Final[dict[str, tuple[float, float]]] = {
    "inflation": (15.0, 2.0),  # peor: 15% o más; mejor: 2% o menos
    "gdp_growth": (-2.0, 3.0),  # peor: −2% o menos; mejor: 3% o más
    "current_account": (-5.0, 0.0),  # peor: −5% del PIB o menos; mejor: ≥0%
}

# Piso de la penalización multiplicativa: score_final = score_oportunidad ×
# (MACRO_FLOOR + (1 − MACRO_FLOOR) × estabilidad). Con 0.5, un mercado
# totalmente inestable conserva la mitad de su score: el filtro macro modula
# la oportunidad comercial pero no la anula (los 18 destinos del MVP son
# economías desarrolladas; el filtro gana peso al abrir la selección de países).
MACRO_FLOOR: Final = 0.5

# --- Nombres de columnas (contrato entre capas; esquemas en contracts.py) ---
COL_COUNTRY: Final = "country_iso3"
COL_COUNTRY_NAME: Final = "country_name"
COL_YEAR: Final = "year"
COL_IMPORTS_USD: Final = "imports_usd"
COL_IMPORTS_FROM_ORIGIN: Final = "imports_from_origin_usd"
COL_CMD: Final = "cmd_code"
COL_VALUE: Final = "value_usd"
COL_SCOPE: Final = "scope"
COL_MARKET_SIZE: Final = "market_size_usd"
COL_GROWTH: Final = "import_growth"
COL_SHARE: Final = "market_share"
COL_SHARE_TREND: Final = "share_trend"
COL_COMPLEMENTARITY: Final = "complementarity"
COL_RCA: Final = "rca_balassa"
COL_INDICATOR: Final = "indicator"
COL_MACRO_VALUE: Final = "value"  # % u otras unidades según el indicador (no USD)
COL_STABILITY: Final = "stability_score"
COL_SCORE: Final = "opportunity_score"
COL_FINAL_SCORE: Final = "final_score"
COL_RANK: Final = "rank"

# --- Parámetros de métricas ---
# Ventana de años recientes para promediar importaciones (ver indices.market_size):
# 3 años suaviza shocks puntuales sin diluir la señal reciente.
MARKET_SIZE_YEARS: Final = 3

# --- Pesos del scoring (consumidos por domain/scoring.rank_markets) ---
# Score = promedio ponderado de métricas min-max normalizadas. Justificación:
# la demanda existente (nivel + dinámica) pesa la mitad porque sin demanda no
# hay mercado; la posición ya ganada por el origen (cuota + momentum) y el
# encaje estructural oferta-demanda reparten la otra mitad. Suman 1.0.
WEIGHTS: Final[dict[str, float]] = {
    "market_size": 0.30,  # demanda actual del destino (nivel)
    "import_growth": 0.20,  # dinámica de la demanda (CAGR de la ventana)
    "market_share": 0.15,  # cuota ya ganada por el origen (último año)
    "share_trend": 0.15,  # momentum de esa cuota (Δ en la ventana)
    "complementarity": 0.20,  # encaje canasta origen ↔ demanda destino
}
# El RCA de Balassa del origen es constante entre destinos: se reporta como
# contexto en el snapshot (columna rca_balassa) pero NO pondera en el ranking.
