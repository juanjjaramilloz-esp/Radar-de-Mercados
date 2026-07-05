# Radar de Mercados (`tradefit`)

Screener de mercados de exportación: dado un producto (código HS) y un país de
origen, rankea mercados destino combinando métricas de oportunidad comercial
con un filtro de estabilidad macro del destino.

- Arquitectura y convenciones: [CLAUDE.md](CLAUDE.md) (fuente de verdad).
- Plan por fases y estado: [PLAN.md](PLAN.md).

MVP actual: producto fijo **café (HS 0901)**, origen **Colombia**, 15 mercados
destino con datos stub (Fase 1; ver PLAN.md).

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
