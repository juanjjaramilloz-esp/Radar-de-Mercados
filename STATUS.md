# STATUS — Radar de Mercados

> **Propósito:** contexto mínimo para retomar el proyecto en un chat nuevo sin
> releer todo. Se actualiza al cierre de cada fase o cambio relevante.
> No duplica: arquitectura y reglas → [CLAUDE.md](CLAUDE.md); fases y criterios
> → [PLAN.md](PLAN.md). Aquí solo: estado, decisiones no obvias y pendientes.

## Qué es (1 línea)

Screener de mercados de exportación: café (HS 0901) desde Colombia → ranking
de 18 destinos. Motor económico puro en `domain/`, snapshot Parquet como
contrato, app Streamlit que solo lee el snapshot.

## Estado actual

- **Última fase completada:** F3 — motor de oportunidad completo (2026-07-05).
- **En curso:** F4 — filtro macro de estabilidad (WDI).
- **Métricas vivas:** `market_size`, `import_growth` (CAGR), `market_share`,
  `share_trend`, `complementarity` (Michaely); RCA de Balassa como columna de
  contexto (constante entre destinos, no pondera). Pesos en `config.WEIGHTS`.
- **Datos:** reales, cacheados en `data/raw/` (4 JSONs: imports, bilateral
  COL, canastas HS2, totales de exportación; 2022–2024, 18 mercados). Sin
  `COMTRADE_API_KEY` en `.env`: usa el preview público (tope 500 registros,
  **1 período por request**, rate-limit 429 → retry integrado). Snapshot real:
  RCA de Colombia en café = 35.66 (2024); USA lidera el ranking.

## Cómo correr (Windows)

```powershell
.venv\Scripts\Activate.ps1                      # activar entorno
python -m tradefit.pipeline.build_snapshot      # snapshot (--source stub como fallback)
streamlit run src/tradefit/app/main.py          # app
pytest ; ruff check . ; mypy src                # puerta de calidad
```

## Decisiones no obvias (log)

- 2026-07-05 · F3: el RCA es constante entre destinos → columna de contexto,
  NO pondera en el score. El "mundo" de exportaciones = suma de lo que
  reportan los países (consulta sin `reporterCode`); las canastas HS2 se
  piden en trozos de 4 reporters para no rozar el tope de 500 del preview.
- 2026-07-05 · F3: (país, año) ausente en el flujo bilateral = cuota 0;
  destino sin canasta = complementariedad NaN → aporta 0 al score. Ojo:
  `pow(1.0, NaN) = 1.0` (IEEE 754) — el CAGR enmascara explícitamente las
  ventanas inválidas para que queden en NaN.
- 2026-07-05 · Comtrade Plus: Italia es reporter **380** (no 381 legacy);
  `reporterISO` llega **null** en el preview → los países se identifican por
  `reporterCode` numérico mapeado en `config.COMTRADE_REPORTER_CODES`.
- 2026-07-05 · `ingest/worldbank.py` (WDI) movido de F2 a F4: las fases son
  cortes verticales y el filtro macro es su único consumidor.
- 2026-07-05 · mypy con `python_version = "3.12"` (los stubs de numpy 2.x usan
  sintaxis PEP 695); el proyecto sigue soportando ≥3.11 en runtime.
- Entorno local: no existe alias `python` fuera del venv (stub de MS Store);
  usar `py` o activar `.venv`. Los hooks de pre-commit son `language: system`
  → necesitan `.venv\Scripts` en el PATH al commitear.
- El snapshot es idempotente a propósito: `meta.json` no lleva timestamps.

## Pendientes conocidos

- Registrar key gratuita de Comtrade (https://comtradeplus.un.org/) y ponerla
  en `.env` como `COMTRADE_API_KEY=` (el código ya la usa si existe).
- F4: `ingest/worldbank.py` (WDI, sin key) + `domain/macro_filter.py` con
  penalización multiplicativa sobre el score de oportunidad.
