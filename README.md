# Radar de Mercados (`tradefit`)

**Demo en vivo: <https://radar-de-mercados.streamlit.app/>**

Screener de mercados de exportación: dado un producto (código HS) y un país de
origen, rankea mercados destino combinando métricas de oportunidad comercial
con un filtro de estabilidad macro del destino.

- Arquitectura y convenciones: [CLAUDE.md](CLAUDE.md) (fuente de verdad).
- Plan por fases y estado: [PLAN.md](PLAN.md).

Estado actual: producto fijo **café (HS 0901)**, origen **Colombia**, 18
mercados destino con **datos reales** (UN Comtrade Plus + World Bank WDI):
5 métricas de oportunidad + filtro macro de estabilidad + narrativa por
reglas donde cada frase cita su número (Fases 1–5 completas; ver PLAN.md).

El repo incluye un snapshot pequeño de ejemplo en `data/processed/` para que
la demo funcione sin descargar datos; para regenerarlo con datos frescos se
necesita una key gratuita de Comtrade en `.env` (ver `.env.example`).

## Instalar (Windows)

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\Activate.ps1
```

## Usar

```powershell
# 1) Construir el snapshot (Fase 1: datos stub locales, sin red)
python -m tradefit.pipeline.build_snapshot

# 2) Levantar la app (solo lee data/processed/, nunca llama APIs)
streamlit run src/tradefit/app/main.py
```

## Calidad

```powershell
pytest                      # tests (sin red)
ruff check . ; mypy src     # lint + tipos
pre-commit install          # hooks: ruff + mypy + pytest antes de cada commit
```
