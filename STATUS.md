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

- **Última fase completada:** F2 — ingesta real Comtrade (2026-07-05).
- **En curso:** F3 — motor de oportunidad completo (4 métricas + scoring).
- **Métricas vivas:** `market_size` (promedio de importaciones, 3 años).
- **Datos:** reales, cacheados en `data/raw/comtrade_0901_imports.json`
  (2022–2024, 18 mercados). Sin `COMTRADE_API_KEY` en `.env`: usa el preview
  público (tope 500 registros, **1 período por request**, rate-limit 429 →
  retry integrado).

## Cómo correr (Windows)

```powershell
.venv\Scripts\Activate.ps1                      # activar entorno
python -m tradefit.pipeline.build_snapshot      # snapshot (--source stub como fallback)
streamlit run src/tradefit/app/main.py          # app
pytest ; ruff check . ; mypy src                # puerta de calidad
```

## Decisiones no obvias (log)

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
- F3 amplía la ingesta: flujos bilaterales Colombia→destino, canasta
  exportadora de Colombia, totales mundiales (para RCA y complementariedad).
