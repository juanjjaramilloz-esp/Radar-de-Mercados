# CLAUDE.md — TradeFit (Screener de Mercados de Exportación)

> Este archivo es la fuente de verdad para convenciones, arquitectura e higiene.
> Léelo antes de escribir código y no lo contradigas. Si algo aquí choca con una
> petición puntual, señálalo antes de proceder.

## Propósito

Herramienta que, dado un producto (código HS) y un país de origen, rankea mercados
destino combinando **métricas de oportunidad comercial** (cuota de mercado, RCA de
Balassa, complementariedad, arancel) con un **filtro de estabilidad macro** del
destino. Entrega: ranking + narrativa interpretada + export (PDF/Excel).

Dos objetivos de calidad que mandan sobre todo lo demás:

1. **Motor defendible**: cada métrica económica está documentada (cita su definición)
   y testeada con un valor conocido. Nada de números que "salen" sin poder explicar
   de dónde.
2. **Arquitectura cambiable**: se debe poder cambiar una fuente de datos, agregar un
   índice o reemplazar la capa de presentación **sin reescribir el resto**.

## Principio arquitectónico central: separación en capas

Tres capas, con dependencias en **una sola dirección**. Nunca al revés.

```
ingest/  (única capa que toca la red)
   │        descarga datos crudos de APIs externas
   ▼
pipeline/  orquesta: ingest → domain → escribe snapshot
   │
   ▼
domain/  (lógica económica PURA: sin red, sin I/O)
   │        calcula índices y scoring; determinística; testeable
   ▼
data/processed/  (snapshot: el contrato entre pipeline y app)
   │
   ▼
app/  (solo LEE el snapshot; nunca llama APIs, nunca importa ingest)
```

Reglas de oro:

- ¿Tocas una API o la red? → va en `ingest/`.
- ¿Haces un cálculo económico? → va en `domain/`, es una función pura y **lleva test**.
- `domain/` no importa `ingest/` ni `app/`. `app/` no importa `ingest/`.
- La app no calcula ni descarga: solo lee `data/processed/` y muestra.
- **Excepción sancionada (buscador avanzado):** la app puede invocar
  `pipeline.ensure_snapshot(hs)` como único punto de entrada para construir
  on-demand el snapshot de una partida que el usuario pide y aún no existe.
  La red sigue en `ingest/`, el cálculo en `domain/` y la app luego lee el
  snapshot como siempre; la app jamás importa `ingest/` directamente ni
  contiene lógica de red o de cálculo.

Esto es lo que hace el proyecto fácil de mejorar después: la lógica económica queda
aislada de dónde vienen los datos y de cómo se ven.

## Estructura de directorios

```
tradefit/
├── CLAUDE.md
├── README.md
├── PLAN.md                     # plan por fases (lo escribe y mantiene Claude Code)
├── pyproject.toml              # deps fijadas + config de tooling
├── .env.example                # nombres de variables, SIN valores
├── .gitignore
├── .pre-commit-config.yaml
├── data/
│   ├── raw/                    # descargas crudas          (gitignored)
│   ├── interim/               # intermedios               (gitignored)
│   └── processed/             # snapshot que consume la app (gitignored)
├── src/
│   └── tradefit/
│       ├── __init__.py
│       ├── config.py          # paths, constantes, nombres de columnas, PESOS
│       ├── contracts.py       # esquemas de validación (pandera) de los DataFrames
│       ├── hs_codes.py        # catálogo HS local: validar/buscar/etiquetar (SIN red)
│       ├── ingest/            # CAPA 1 — red
│       │   ├── worldbank.py
│       │   ├── comtrade.py
│       │   ├── hs_reference.py  # regenera el catálogo HS versionado
│       │   └── wits.py
│       ├── domain/            # CAPA 2 — puro
│       │   ├── indices.py     # RCA, complementariedad, cuota...
│       │   ├── macro_filter.py
│       │   └── scoring.py     # combinación y ranking
│       ├── pipeline/
│       │   └── build_snapshot.py
│       └── app/               # CAPA 3 — presentación
│           └── main.py        # Streamlit
├── tests/
│   ├── conftest.py
│   ├── fixtures/              # datos pequeños de prueba (nunca red en tests)
│   ├── test_indices.py
│   └── test_scoring.py
└── notebooks/                # exploración; NO es producción
```

> El nombre `tradefit` es provisional; si se renombra, se cambia en un solo lugar.

## Reglas de higiene (obligatorias)

- **Python ≥ 3.11.** Type hints en toda firma pública. `mypy` debe pasar.
- **Funciones pequeñas**, una sola responsabilidad. En `domain/`, preferir funciones
  puras y determinísticas.
- **Docstrings** en toda función pública (qué hace, parámetros, retorno). En
  `domain/indices.py`, cada índice **cita su definición/fórmula** (p. ej. RCA → Balassa 1965).
- **Sin secretos en el repo.** Las API keys se leen de variables de entorno (`.env`,
  cargado con `python-dotenv`). `.env` va en `.gitignore`. Mantener `.env.example`
  con los nombres pero sin valores.
- **Red solo en `ingest/`.** `domain/` y `app/` nunca acceden a internet.
- **Contratos de datos explícitos.** Todo DataFrame que cruza capas se valida contra
  un esquema en `contracts.py` (pandera). Falla temprano si el esquema cambió.
- **Configuración centralizada** en `config.py`: paths, constantes, nombres de columnas.
  Cero rutas o "números mágicos" dispersos.
- **Los pesos del scoring viven en un solo lugar** (`config.py` o un YAML),
  documentados y justificados. Jamás hardcodeados dentro de la lógica.
- **Logging** con el módulo `logging`, no `print`.
- **Errores:** en `ingest`/`pipeline` fallar ruidosamente (que se note si una fuente
  cambió); en `app` degradar con gracia (mensaje claro al usuario).
- **Reproducibilidad:** deps fijadas en `pyproject.toml`. El pipeline es idempotente:
  correrlo dos veces produce el mismo snapshot.

## Testing

- `pytest`. **Los tests no tocan la red** (usan fixtures pequeños en `tests/fixtures/`).
- **Todo índice económico en `domain/` tiene al menos un test** con un ejemplo de valor
  conocido (input → output calculado a mano). Esto es lo que hace la metodología
  defendible en una entrevista.
- El scoring/ranking se prueba con un caso sintético donde el orden esperado es obvio.
- Prioridad de cobertura: `domain/` por encima de todo. `ingest/` se prueba con
  respuestas mockeadas o guardadas.

## Git

- Commits pequeños y atómicos. **Conventional Commits** (`feat:`, `fix:`, `refactor:`,
  `test:`, `docs:`, `chore:`).
- `.gitignore` incluye: `.env`, `data/raw/`, `data/interim/`, `data/processed/`.
  Los snapshots no se versionan (si se necesita uno de ejemplo, que sea pequeño y explícito).
- Nunca commitear datasets grandes ni credenciales.

## Tooling

- `ruff` (lint + format), `mypy` (tipos), `pytest`.
- `pre-commit` corre ruff + mypy + pytest antes de cada commit.

## Comandos

> Claude Code ajusta/confirma estos al implementar.

- Instalar: `pip install -e ".[dev]"`
- Construir snapshot: `python -m tradefit.pipeline.build_snapshot`
- Levantar app: `streamlit run src/tradefit/app/main.py`
- Tests: `pytest`
- Lint + tipos: `ruff check . && mypy src`

## Fuentes de datos (estado real — respetar)

- **World Bank WDI** — columna vertebral macro. **Sin API key.** Estable. Base por defecto.
- **UN Comtrade Plus** — datos comercio producto-nivel. Requiere **key gratuita** (registro)
  leída de `COMTRADE_API_KEY`. Sin key, el preview topa en 500 registros → insuficiente.
  **No llamar en vivo desde la app:** descargar en `ingest/`, cachear en `data/`.
- **World Bank WITS** — aranceles y acuerdos comerciales.
- **IMF (data.imf.org, SDMX 3.0)** — opcional y frágil (migración reciente rompió librerías
  viejas). No es dependencia crítica del MVP; usar solo si WDI no cubre algo.

## Libertades creativas (post-MVP, desde F4)

Regla acordada: cuando Claude Code detecte una mejora a la app con **buen
costo/beneficio**, la implementa **sin preguntar**. Ya no estamos atados al
MVP mínimo. Límites que siguen vigentes:

- Las reglas de higiene y la separación en capas no se negocian.
- Toda mejora se commitea aparte (atómica) para poder revertirla sola.
- Si una mejora es cara o irreversible (cambiar de framework, borrar datos,
  servicios pagos), eso sí se consulta antes.

## Qué NO hacer

- No llamar APIs desde `app/` ni desde `domain/`.
- No hardcodear keys, pesos ni rutas.
- No mezclar cálculo económico con I/O.
- No versionar datos ni secretos.
- No introducir un índice sin docstring que cite su definición y sin test.
