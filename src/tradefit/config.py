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
RANKING_PARQUET: Final = PROCESSED_DIR / "ranking.parquet"
SNAPSHOT_META_JSON: Final = PROCESSED_DIR / "meta.json"

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

# --- Nombres de columnas (contrato entre capas; esquemas en contracts.py) ---
COL_COUNTRY: Final = "country_iso3"
COL_COUNTRY_NAME: Final = "country_name"
COL_YEAR: Final = "year"
COL_IMPORTS_USD: Final = "imports_usd"
COL_MARKET_SIZE: Final = "market_size_usd"
COL_SCORE: Final = "opportunity_score"
COL_RANK: Final = "rank"

# --- Parámetros de métricas ---
# Ventana de años recientes para promediar importaciones (ver indices.market_size):
# 3 años suaviza shocks puntuales sin diluir la señal reciente.
MARKET_SIZE_YEARS: Final = 3

# --- Pesos del scoring (consumidos por domain/scoring.rank_markets) ---
# Fase 1: una sola métrica, peso 1.0 (trivialmente el 100% del score).
# Al agregar métricas (Fase 3), los pesos se documentan y justifican AQUÍ,
# nunca dentro de la lógica.
WEIGHTS: Final[dict[str, float]] = {"market_size": 1.0}
