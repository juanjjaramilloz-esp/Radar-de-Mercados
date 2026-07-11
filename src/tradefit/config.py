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
# Catálogo HS versionado (código → descripción, niveles 2/4/6 dígitos) para el
# buscador de partidas de la app; se regenera con ingest/hs_reference.py.
HS_REFERENCE_CSV: Final = SAMPLE_DIR / "hs_reference.csv.gz"
# Distancias bilaterales desde el origen (CEPII GeoDist), versionadas: la
# geografía no cambia y la fuente dejó de actualizarse (dataset final).
# Se regenera con ingest/geodist.py si hiciera falta.
GEODIST_CSV: Final = SAMPLE_DIR / "geodist_col.csv.gz"
STUB_BILATERAL_CSV: Final = SAMPLE_DIR / "stub_bilateral.csv"
STUB_BASKETS_CSV: Final = SAMPLE_DIR / "stub_baskets.csv"
STUB_EXPORT_TOTALS_CSV: Final = SAMPLE_DIR / "stub_export_totals.csv"
STUB_TARIFFS_CSV: Final = SAMPLE_DIR / "stub_tariffs.csv"

# Cantidad de mercados recomendados en la narrativa (top-N del ranking).
TOP_RECOMMENDATIONS: Final = 3

# --- Productos y origen ---
# Canasta curada del desplegable de la app: el top 15 de exportaciones de
# Colombia por partida HS4, EXCLUYENDO los capítulos minero-energéticos
# (NON_MINING_EXCLUDED_CHAPTERS: 27 combustibles y 71 oro/piedras).
# Fuente: UN Comtrade, exportaciones de Colombia año BASKET_YEAR (2024),
# nivel AG4, consultado 2026-07-08; en ORDEN de valor exportado descendente
# (café USD 3 545 M … polipropileno USD 290 M). La lista se regenera o
# verifica con: python -m tradefit.ingest.top_exports
# Las etiquetas son curadas a mano (presentación); el origen sigue fijo.
PRODUCTS: Final[dict[str, str]] = {
    "0901": "Café (HS 0901)",
    "0603": "Flores cortadas (HS 0603)",
    "0803": "Bananos y plátanos (HS 0803)",
    "7610": "Estructuras de aluminio (HS 7610)",
    "7202": "Ferroaleaciones — ferroníquel (HS 7202)",
    "3808": "Insecticidas y plaguicidas (HS 3808)",
    "1511": "Aceite de palma (HS 1511)",
    "1701": "Azúcar de caña (HS 1701)",
    "8504": "Transformadores eléctricos (HS 8504)",
    "7404": "Chatarra de cobre (HS 7404)",
    "3004": "Medicamentos (HS 3004)",
    "2101": "Extractos de café (HS 2101)",
    "3904": "PVC en formas primarias (HS 3904)",
    "0804": "Aguacates, piñas y mangos (HS 0804)",
    "3902": "Polipropileno (HS 3902)",
}
# Etiquetas en inglés de los mismos 15 productos curados, para el toggle de
# idioma de la app (presentación pura; las partidas construidas on-demand
# usan la descripción del catálogo, que ya está en inglés).
PRODUCTS_EN: Final[dict[str, str]] = {
    "0901": "Coffee (HS 0901)",
    "0603": "Cut flowers (HS 0603)",
    "0803": "Bananas and plantains (HS 0803)",
    "7610": "Aluminium structures (HS 7610)",
    "7202": "Ferro-alloys — ferronickel (HS 7202)",
    "3808": "Insecticides and pesticides (HS 3808)",
    "1511": "Palm oil (HS 1511)",
    "1701": "Cane sugar (HS 1701)",
    "8504": "Electric transformers (HS 8504)",
    "7404": "Copper waste and scrap (HS 7404)",
    "3004": "Medicaments (HS 3004)",
    "2101": "Coffee extracts (HS 2101)",
    "3904": "PVC in primary forms (HS 3904)",
    "0804": "Avocados, pineapples and mangoes (HS 0804)",
    "3902": "Polypropylene (HS 3902)",
}
HS_CODE: Final = "0901"  # producto por defecto (pipeline sin --hs, stub, tests)
HS_LABEL: Final = PRODUCTS[HS_CODE]
ORIGIN_ISO3: Final = "COL"
ORIGIN_NAME: Final = "Colombia"  # nombre legible del origen (narrativa y app)


def processed_dir(hs: str) -> Path:
    """Directorio del snapshot de un producto: ``data/processed/<hs>/``."""
    return PROCESSED_DIR / hs


def ranking_parquet(hs: str) -> Path:
    """Ruta del ranking parquet del producto ``hs``."""
    return processed_dir(hs) / "ranking.parquet"


def snapshot_meta_json(hs: str) -> Path:
    """Ruta del meta.json del producto ``hs``."""
    return processed_dir(hs) / "meta.json"


def narrative_json(hs: str) -> Path:
    """Ruta del narrative.json del producto ``hs``."""
    return processed_dir(hs) / "narrative.json"


def snapshot_manifest_json(hs: str) -> Path:
    """Manifiesto de hashes y procedencia del snapshot de ``hs``."""
    return processed_dir(hs) / "manifest.json"


def imports_timeseries_parquet(hs: str) -> Path:
    """Ruta de la serie anual de importaciones (por destino y año) de ``hs``."""
    return processed_dir(hs) / "imports_timeseries.parquet"


def competitors_parquet(hs: str) -> Path:
    """Ruta de las cuotas de proveedores por destino (competidores) de ``hs``."""
    return processed_dir(hs) / "competitors.parquet"


def unit_values_parquet(hs: str) -> Path:
    """Ruta de los valores unitarios (USD/kg) por destino de ``hs``.

    Artefacto exclusivo del catálogo curado (``PRODUCTS``): el pipeline solo
    lo construye para esos productos — es el diferencial "análisis avanzado"
    frente a las partidas del buscador on-demand. La app degrada con gracia
    si no existe.
    """
    return processed_dir(hs) / "unit_values.parquet"


def tariff_profile_parquet(hs: str) -> Path:
    """Ruta del perfil arancelario por subpartida HS6 de ``hs``.

    Desglose del arancel efectivamente aplicado que ``tariff_faced`` promedia
    para el ranking: revela la dispersión intra-partida en la ficha del
    destino. La app degrada con gracia si no existe (snapshots viejos o sin
    datos de WITS).
    """
    return processed_dir(hs) / "tariff_profile.parquet"


def macro_context_parquet() -> Path:
    """Ruta del macro crudo compartido (indicadores por país y año, para la ficha).

    Es independiente del producto: un solo artefacto en la raíz de
    ``data/processed/`` que la app usa para mostrar el contexto macro del
    destino (inflación, PIB, cuenta corriente, LPI) con su año.
    """
    return PROCESSED_DIR / "macro_context.parquet"


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
    # Destinos LATAM (2026-07-08): socios regionales relevantes de Colombia
    # con buen reporte a Comtrade; ojo con reporters rezagados (se anota en
    # STATUS si alguno queda corto en la ventana de años).
    "MEX": "México",
    "BRA": "Brasil",
    "CHL": "Chile",
    "PER": "Perú",
    "ECU": "Ecuador",
    "CRI": "Costa Rica",
    "PAN": "Panamá",
    "DOM": "República Dominicana",
}

# Nombres en inglés de los mismos destinos, para el toggle de idioma de la app.
DESTINATIONS_EN: Final[dict[str, str]] = {
    "USA": "United States",
    "DEU": "Germany",
    "ITA": "Italy",
    "FRA": "France",
    "JPN": "Japan",
    "CAN": "Canada",
    "BEL": "Belgium",
    "NLD": "Netherlands",
    "ESP": "Spain",
    "GBR": "United Kingdom",
    "KOR": "South Korea",
    "CHE": "Switzerland",
    "POL": "Poland",
    "SWE": "Sweden",
    "AUS": "Australia",
    "PRT": "Portugal",
    "FIN": "Finland",
    "AUT": "Austria",
    "MEX": "Mexico",
    "BRA": "Brazil",
    "CHL": "Chile",
    "PER": "Peru",
    "ECU": "Ecuador",
    "CRI": "Costa Rica",
    "PAN": "Panama",
    "DOM": "Dominican Republic",
}

# --- Acuerdos comerciales de Colombia por destino (contexto, NO pondera) ---
# Acuerdo vigente que cubre el comercio de bienes con cada destino y su año
# de entrada en vigor. Fuente: MinCIT / tlc.gov.co, acuerdos comerciales
# vigentes (consultado 2026-07-08). El efecto arancelario ya lo captura la
# métrica tariff_faced (AHS = mín(MFN, preferencial)); esto es contexto
# legible en la app. Destinos sin acuerdo vigente (JPN, AUS, DOM) no
# aparecen en el dict.
TRADE_AGREEMENTS: Final[dict[str, str]] = {
    "USA": "TLC EE. UU. (2012)",
    "DEU": "Acuerdo UE (2013)",
    "ITA": "Acuerdo UE (2013)",
    "FRA": "Acuerdo UE (2013)",
    "BEL": "Acuerdo UE (2013)",
    "NLD": "Acuerdo UE (2013)",
    "ESP": "Acuerdo UE (2013)",
    "POL": "Acuerdo UE (2013)",
    "SWE": "Acuerdo UE (2013)",
    "PRT": "Acuerdo UE (2013)",
    "FIN": "Acuerdo UE (2013)",
    "AUT": "Acuerdo UE (2013)",
    "GBR": "Acuerdo Reino Unido (2021)",
    "CAN": "TLC Canadá (2011)",
    "KOR": "TLC Corea del Sur (2016)",
    "CHE": "AELC–EFTA (2011)",
    "MEX": "TLC México (1995) · Alianza del Pacífico",
    "CHL": "TLC Chile (2009) · Alianza del Pacífico",
    "PER": "CAN (1973) · Alianza del Pacífico",
    "ECU": "CAN (1973)",
    "BRA": "ACE-72 Mercosur (2017)",
    "CRI": "TLC Costa Rica (2016)",
    "PAN": "AAP N.º 29 (1994)",
}
# Versión en inglés de los mismos acuerdos (toggle de idioma).
TRADE_AGREEMENTS_EN: Final[dict[str, str]] = {
    "USA": "US FTA (2012)",
    "DEU": "EU Agreement (2013)",
    "ITA": "EU Agreement (2013)",
    "FRA": "EU Agreement (2013)",
    "BEL": "EU Agreement (2013)",
    "NLD": "EU Agreement (2013)",
    "ESP": "EU Agreement (2013)",
    "POL": "EU Agreement (2013)",
    "SWE": "EU Agreement (2013)",
    "PRT": "EU Agreement (2013)",
    "FIN": "EU Agreement (2013)",
    "AUT": "EU Agreement (2013)",
    "GBR": "UK Agreement (2021)",
    "CAN": "Canada FTA (2011)",
    "KOR": "South Korea FTA (2016)",
    "CHE": "EFTA (2011)",
    "MEX": "Mexico FTA (1995) · Pacific Alliance",
    "CHL": "Chile FTA (2009) · Pacific Alliance",
    "PER": "Andean Community (1973) · Pacific Alliance",
    "ECU": "Andean Community (1973)",
    "BRA": "ACE-72 Mercosur (2017)",
    "CRI": "Costa Rica FTA (2016)",
    "PAN": "Partial-scope AAP No. 29 (1994)",
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
    "MEX": 484,
    "BRA": 76,
    "CHL": 152,
    "PER": 604,
    "ECU": 218,
    "CRI": 188,
    "PAN": 591,
    "DOM": 214,
}

# Años de importaciones a descargar (fijos para que el snapshot sea reproducible).
IMPORT_YEARS: Final[tuple[int, ...]] = (2023, 2024, 2025)

# --- UN Comtrade Plus ---
ENV_COMTRADE_KEY: Final = "COMTRADE_API_KEY"
COMTRADE_URL_AUTH: Final = "https://comtradeapi.un.org/data/v1/get/C/A/HS"
COMTRADE_URL_PREVIEW: Final = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
COMTRADE_BASKETS_CACHE: Final = RAW_DIR / "comtrade_baskets_hs2.json"
# Codebook oficial de códigos HS (H6) de Comtrade; alimenta HS_REFERENCE_CSV.
COMTRADE_HS_REFERENCE_URL: Final = "https://comtradeapi.un.org/files/v1/app/reference/HS.json"


def comtrade_imports_cache(hs: str) -> Path:
    """Caché crudo de importaciones (destinos ← mundo) del producto ``hs``."""
    return RAW_DIR / f"comtrade_{hs}_imports.json"


def comtrade_bilateral_cache(hs: str) -> Path:
    """Caché crudo de importaciones desde el origen del producto ``hs``."""
    return RAW_DIR / f"comtrade_{hs}_bilateral_{ORIGIN_ISO3}.json"


def comtrade_imports_hist_cache(hs: str, years: tuple[int, ...]) -> Path:
    """Caché crudo de importaciones de una ventana histórica (backtest)."""
    return RAW_DIR / f"comtrade_{hs}_imports_hist_{years[0]}_{years[-1]}.json"


def comtrade_bilateral_hist_cache(hs: str, years: tuple[int, ...]) -> Path:
    """Caché crudo del flujo bilateral de una ventana histórica (backtest)."""
    return RAW_DIR / f"comtrade_{hs}_bilateral_hist_{years[0]}_{years[-1]}.json"


def comtrade_exports_cache(hs: str) -> Path:
    """Caché crudo de totales de exportación (RCA) del producto ``hs``."""
    return RAW_DIR / f"comtrade_{hs}_export_totals.json"


def comtrade_destinations_cache(hs: str) -> Path:
    """Caché crudo de exportaciones del origen por destino (todos los partners)."""
    return RAW_DIR / f"comtrade_{hs}_destinos_{ORIGIN_ISO3}.json"


def comtrade_competitors_cache(hs: str) -> Path:
    """Caché crudo de importaciones de cada destino por proveedor (competidores)."""
    return RAW_DIR / f"comtrade_{hs}_competidores.json"


# Código de reporter/partner de Comtrade para el país de origen (Colombia).
ORIGIN_COMTRADE_CODE: Final = 170
# Códigos de commodity especiales de Comtrade.
COMTRADE_CMD_TOTAL: Final = "TOTAL"  # comercio total del reporter
COMTRADE_CMD_ALL_HS2: Final = "AG2"  # todos los capítulos HS a 2 dígitos
COMTRADE_CMD_ALL_HS4: Final = "AG4"  # todas las partidas HS a 4 dígitos

# Capítulos HS excluidos del top de exportaciones que alimenta PRODUCTS:
# 27 (combustibles minerales) y 71 (oro/piedras preciosas) — criterio de
# canasta "no minero-energética" usado por MinCIT/Procolombia para medir la
# diversificación exportadora; esos flujos van a mercados concentrados y con
# logística atípica, poco útiles en un screener de dónde exportar.
NON_MINING_EXCLUDED_CHAPTERS: Final[frozenset[str]] = frozenset({"27", "71"})


# Caché crudo de exportaciones del origen por partida HS4 (top de PRODUCTS);
# el año en el nombre invalida el caché cuando BASKET_YEAR avance.
def comtrade_top_exports_cache() -> Path:
    """Caché crudo del top de exportaciones HS4 del origen (año BASKET_YEAR)."""
    return RAW_DIR / f"comtrade_{ORIGIN_ISO3}_exports_hs4_{BASKET_YEAR}.json"


# Año de las canastas comerciales para complementariedad. Colombia (origen)
# reporta a Comtrade con más rezago que la mayoría de los destinos del MVP:
# no necesariamente el último año de IMPORT_YEARS tiene ya la canasta
# exportadora de Colombia disponible, así que este año se fija por separado
# (verificar disponibilidad del origen antes de adelantarlo).
BASKET_YEAR: Final = 2024

# --- Backtest del score (validación predictiva fuera de muestra) ---
# Ventana de entrenamiento: las métricas de comercio del score se recalculan
# con estos años (as-of 2022) y el score resultante se contrasta con el
# crecimiento bilateral realizado en IMPORT_YEARS (2023–2025). La ventana
# tiene el mismo ancho que MARKET_SIZE_YEARS para que el score histórico use
# la definición oficial.
BACKTEST_TRAIN_YEARS: Final[tuple[int, ...]] = (2020, 2021, 2022)
#: Artefacto del backtest que lee la app (independiente del producto).
BACKTEST_JSON: Final = PROCESSED_DIR / "backtest.json"

# --- World Bank WITS (aranceles TRAINS; sin API key) ---
# Endpoint SDMX REST del dataflow TRAINS. La clave es
# ``A.{reporter}.{partner}.{productos}.reported``: frecuencia anual, códigos
# numéricos de país, subpartidas HS6 unidas con "+" (verificado 2026-07: el
# dataflow NO acepta partidas de 2/4 dígitos ni el parámetro format=JSON —
# responde XML SDMX GenericData). ObsValue = promedio simple de las líneas
# ad-valorem, en % (atributo TARIFFTYPE: MFN o PREF).
WITS_URL: Final = (
    "https://wits.worldbank.org/API/V1/SDMX/V21/rest/data/DF_WITS_Tariff_TRAINS/"
    "A.{reporter}.{partner}.{products}.reported/"
    "?startperiod={start}&endperiod={end}"
)
# Rango de años a pedir: los aranceles llegan con rezago y las preferencias
# suelen publicarse más tarde que el MFN; una ventana ancha permite tomar el
# último año disponible de cada serie.
WITS_YEARS: Final[tuple[int, int]] = (2018, 2025)
# Partner "000" = mundo → arancel MFN del reporter.
WITS_PARTNER_WORLD: Final = "000"
# Código WITS del origen (Colombia) como partner → arancel preferencial.
ORIGIN_WITS_CODE: Final = 170

# Códigos de reporter de WITS por destino. WITS usa códigos ISO numéricos
# (Suiza=756, a diferencia del 757 de Comtrade) y los miembros de la UE no
# tienen arancel propio: reportan como el bloque 918 (European Union), así
# que una sola consulta a 918 cubre a los 11 destinos comunitarios del MVP.
WITS_EU_CODE: Final = 918
WITS_REPORTER_CODES: Final[dict[str, int]] = {
    "USA": 840,
    "DEU": WITS_EU_CODE,
    "ITA": WITS_EU_CODE,
    "FRA": WITS_EU_CODE,
    "JPN": 392,
    "CAN": 124,
    "BEL": WITS_EU_CODE,
    "NLD": WITS_EU_CODE,
    "ESP": WITS_EU_CODE,
    "GBR": 826,
    "KOR": 410,
    "CHE": 756,
    "POL": WITS_EU_CODE,
    "SWE": WITS_EU_CODE,
    "AUS": 36,
    "PRT": WITS_EU_CODE,
    "FIN": WITS_EU_CODE,
    "AUT": WITS_EU_CODE,
    # LATAM: ISO numérico coincide con el M49 de Comtrade en estos 8.
    "MEX": 484,
    "BRA": 76,
    "CHL": 152,
    "PER": 604,
    "ECU": 218,
    "CRI": 188,
    "PAN": 591,
    "DOM": 214,
}


def wits_tariffs_cache(hs: str) -> Path:
    """Caché crudo de aranceles WITS (MFN + preferencial COL) del producto ``hs``."""
    return RAW_DIR / f"wits_{hs}_tariffs_{ORIGIN_ISO3}.json"


def wits_competitor_tariffs_cache(hs: str) -> Path:
    """Caché crudo de aranceles preferenciales hacia los competidores (WITS)."""
    return RAW_DIR / f"wits_{hs}_tariffs_competidores.json"


# --- Margen de preferencia (aranceles que enfrentan los competidores) ---
# Nº de mayores proveedores del destino (excluido el origen) contra los que
# se mide el margen: 3 captura el grueso de la competencia sin disparar las
# consultas a WITS (una por reporter con los partners unidos con "+").
PREF_MARGIN_TOP_COMPETITORS: Final = 3
# Comtrade usa códigos M49 extendidos para algunos países; WITS exige el ISO
# numérico puro. Solo difieren estos (verificado contra los proveedores
# presentes en los 15 productos del catálogo, 2026-07).
COMTRADE_TO_WITS_PARTNER: Final[dict[str, str]] = {
    "251": "250",  # Francia
    "381": "380",  # Italia (código legacy)
    "579": "578",  # Noruega
    "699": "356",  # India
    "757": "756",  # Suiza
    "842": "840",  # EE. UU.
}
# Agregados estadísticos de Comtrade sin país equivalente en WITS: se omiten
# del margen (no son competidores identificables).
COMTRADE_AGGREGATE_PARTNERS: Final[frozenset[str]] = frozenset({"490", "568", "838", "899"})
# Miembros de la UE por código Comtrade: la unión aduanera implica arancel 0
# entre miembros, y las preferencias de terceros hacia cualquier miembro se
# registran en TRAINS bajo el bloque 918.
EU_MEMBER_COMTRADE_CODES: Final[frozenset[str]] = frozenset(
    {
        "40",  # Austria
        "56",  # Bélgica
        "100",  # Bulgaria
        "191",  # Croacia
        "196",  # Chipre
        "203",  # Chequia
        "208",  # Dinamarca
        "233",  # Estonia
        "246",  # Finlandia
        "251",  # Francia
        "276",  # Alemania
        "300",  # Grecia
        "348",  # Hungría
        "372",  # Irlanda
        "380",  # Italia
        "381",  # Italia (legacy)
        "428",  # Letonia
        "440",  # Lituania
        "442",  # Luxemburgo
        "470",  # Malta
        "528",  # Países Bajos
        "616",  # Polonia
        "620",  # Portugal
        "642",  # Rumania
        "703",  # Eslovaquia
        "705",  # Eslovenia
        "724",  # España
        "752",  # Suecia
    }
)


# --- CEPII GeoDist (distancias bilaterales; archivo estático, sin API) ---
# Dataset dyádico dist_cepii de Mayer & Zignago (2011), CEPII WP 2011-25:
# distancias en km entre pares de países (dist = entre las ciudades más
# pobladas; distw = promedio ponderado por población de las ciudades
# principales, la medida recomendada para ecuaciones de gravedad). El archivo
# es final (CEPII no lo actualiza más) y la geografía no caduca: se versiona
# el extracto del origen en GEODIST_CSV y solo se regenera si cambia la lista
# de destinos posibles.
CEPII_DIST_URL: Final = "https://www.cepii.fr/distance/dist_cepii.dta"
CEPII_DIST_CACHE: Final = RAW_DIR / "dist_cepii.dta"

# Rampa log-lineal de la accesibilidad por distancia (peor, mejor) en km.
# Extremos físicos, no muestrales: 20 015 km es la máxima distancia geodésica
# posible (media circunferencia terrestre, π·6371 km) y 100 km una frontera
# contigua efectiva. La rampa es lineal en log-distancia porque el efecto de
# la distancia sobre el comercio es aproximadamente log-lineal (elasticidad
# ≈ −0.9; Disdier & Head 2008, meta-análisis del modelo gravitacional).
ACCESSIBILITY_DISTANCE_BOUNDS_KM: Final[tuple[float, float]] = (20015.0, 100.0)
# Rampa del componente logístico: la escala completa del LPI (World Bank,
# Logistics Performance Index, 1–5). Sin dato de LPI el componente es neutro
# (0.5): la ausencia en la fuente no es evidencia de mala logística.
ACCESSIBILITY_LPI_BOUNDS: Final[tuple[float, float]] = (1.0, 5.0)

# --- World Bank WDI (filtro macro de estabilidad; sin API key) ---
WDI_URL: Final = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"
WDI_CACHE_FILE: Final = RAW_DIR / "wdi_macro.json"
STUB_MACRO_CSV: Final = SAMPLE_DIR / "stub_macro.csv"
# Rango de años a descargar; el score usa los últimos MACRO_YEARS con dato.
WDI_DATE_RANGE: Final = "2021:2025"
MACRO_YEARS: Final = 3

# Indicadores WDI del filtro (código → nombre corto usado en el contrato).
WDI_INDICATORS: Final[dict[str, str]] = {
    "FP.CPI.TOTL.ZG": "inflation",  # inflación anual, precios al consumidor (%)
    "NY.GDP.MKTP.KD.ZG": "gdp_growth",  # crecimiento real del PIB (%)
    "BN.CAB.XOKA.GD.ZS": "current_account",  # cuenta corriente (% del PIB)
}

# Indicadores WDI de CONTEXTO: se descargan y viajan en el mismo caché/
# contrato macro pero NO entran al filtro de estabilidad ni al score.
# LPI = Logistics Performance Index (World Bank, escala 1–5; publicación
# esparsa, ~cada 4-5 años — se toma el último año con dato por país).
WDI_CONTEXT_INDICATORS: Final[dict[str, str]] = {
    "LP.LPI.OVRL.XQ": "lpi",
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
COL_TARIFF: Final = "tariff_faced"
COL_TARIFF_TYPE: Final = "tariff_type"
COL_RATE_PCT: Final = "rate_pct"
COL_RCA: Final = "rca_balassa"
COL_INDICATOR: Final = "indicator"
COL_MACRO_VALUE: Final = "value"  # % u otras unidades según el indicador (no USD)
COL_AGREEMENT: Final = "trade_agreement"  # presentación (app, desde TRADE_AGREEMENTS)
COL_ORIGIN_EXPORT_SHARE: Final = "share_of_origin_exports"
COL_PARTNER_CODE: Final = "partner_code"  # código M49 del proveedor (texto)
COL_PARTNER_NAME: Final = "partner_name"  # nombre del proveedor (catálogo Comtrade, EN)
COL_SUPPLIER_SHARE: Final = "supplier_share"  # cuota del proveedor en las imports del destino
COL_SUPPLIER_RANK: Final = "supplier_rank"  # posición del proveedor en el destino (1 = mayor)
COL_LPI: Final = "lpi"  # Logistics Performance Index del destino (contexto)
COL_DISTANCE_KM: Final = "distance_km"  # distancia bilateral origen→destino (CEPII, km)
COL_ACCESSIBILITY: Final = "accessibility"  # accesibilidad logística [0,1] (pondera)
COL_NET_WGT: Final = "net_weight_kg"  # peso neto del flujo (Comtrade netWgt)
COL_UV_MARKET: Final = "uv_market_usd_kg"  # valor unitario de las imports del destino
COL_UV_ORIGIN: Final = "uv_origin_usd_kg"  # valor unitario del flujo origen→destino
COL_UV_PREMIUM: Final = "uv_premium"  # UV origen / UV destino − 1 (fracción)
COL_COMPETITOR_TARIFF: Final = "competitor_tariff"  # AHS promedio de los top competidores
COL_PREF_MARGIN: Final = "preference_margin"  # margen de preferencia relativo (pondera)
COL_COVERAGE: Final = "data_coverage"  # % del peso del score con dato observado (transparencia)
COL_STABILITY: Final = "stability_score"
COL_SCORE: Final = "opportunity_score"
COL_FINAL_SCORE: Final = "final_score"
COL_RANK: Final = "rank"

# Umbrales de lectura del HHI de concentración de destinos (guías de fusión
# DOJ/FTC 2010, en fracción: <0.15 desconcentrado, 0.15–0.25 moderado,
# >0.25 altamente concentrado). Solo para la etiqueta cualitativa de la app;
# el HHI se reporta como contexto y no pondera en el score.
HHI_MODERATE: Final = 0.15
HHI_HIGH: Final = 0.25

# --- Parámetros de métricas ---
# Ventana de años recientes para promediar importaciones (ver indices.market_size):
# 3 años suaviza shocks puntuales sin diluir la señal reciente.
MARKET_SIZE_YEARS: Final = 3

# --- Pesos del scoring (consumidos por domain/scoring.rank_markets) ---
# Score = promedio ponderado de métricas min-max normalizadas. Justificación:
# la demanda existente (nivel + dinámica) pesa casi la mitad porque sin
# demanda no hay mercado; la posición ya ganada por el origen (cuota +
# momentum) y el encaje estructural oferta-demanda reparten el grueso del
# resto; las dos fricciones de acceso — arancel enfrentado y accesibilidad
# logística (distancia gravitacional + LPI) — entran con peso moderado (0.10
# cada una) porque condicionan el costo de llegar pero no crean demanda.
# Para dar cabida a la accesibilidad (2026-07-08) ceden 3 pp el tamaño de
# mercado, 2 pp el crecimiento, 2 pp la complementariedad, 1 pp la cuota y
# 2 pp el momentum (la métrica más ruidosa de la ventana). El bloque
# arancelario (0.10) se reparte desde 2026-07-09 entre el nivel absoluto del
# arancel (0.05: costo real de entrada) y el margen de preferencia relativo
# (0.05: la ventaja/desventaja frente a los competidores — un arancel de 0 %
# no es ventaja si los rivales también pagan 0 %). Suman 1.0.
WEIGHTS: Final[dict[str, float]] = {
    "market_size": 0.22,  # demanda actual del destino (nivel)
    "import_growth": 0.18,  # dinámica de la demanda (CAGR de la ventana)
    "market_share": 0.14,  # cuota ya ganada por el origen (último año)
    "share_trend": 0.08,  # momentum de esa cuota (Δ en la ventana)
    "complementarity": 0.18,  # encaje canasta origen ↔ demanda destino
    "tariff_faced": 0.05,  # arancel efectivamente aplicado (menos = mejor)
    "preference_margin": 0.05,  # ventaja arancelaria vs. competidores (más = mejor)
    "accessibility": 0.10,  # accesibilidad logística: distancia (gravedad) + LPI
}
# El RCA de Balassa del origen es constante entre destinos: se reporta como
# contexto en el snapshot (columna rca_balassa) pero NO pondera en el ranking.
