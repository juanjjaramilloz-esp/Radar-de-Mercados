# PLAN — Radar de Mercados

> Mantenido por Claude Code. Fases incrementales tipo "corte vertical": cada
> fase queda corriendo, testeada (pytest + ruff + mypy en verde) y commiteada
> (Conventional Commits) por sí sola.
> MVP: producto fijo (café, HS 0901) + origen Colombia, 15–20 mercados destino.

## Estado

- [x] **Fase 1 — Esqueleto caminante** (completada 2026-07-05)
- [x] **Fase 2 — Ingesta real (Comtrade)** (completada 2026-07-05)
- [x] **Fase 3 — Motor de oportunidad completo** (completada 2026-07-05)
- [x] **Fase 4 — Filtro macro de estabilidad** (completada 2026-07-05)
- [x] **Fase 5 — Narrativa por reglas + recomendaciones** (completada 2026-07-05)
- [x] **Fase 6 — Export PDF/Excel + pulido** (completada 2026-07-05)

**MVP completo.** Lo que sigue vive en el Backlog (y en las libertades
creativas post-MVP acordadas en CLAUDE.md).

## Fase 1 — Esqueleto caminante (end-to-end mínimo)

**Entrega:** estructura completa del repo + tooling (ruff, mypy, pytest,
pre-commit) + el flujo entero funcionando con UNA métrica y datos stub:
`ingest/stub.py` (CSV pequeño y explícito versionado en `data/sample/`, cero
red) → `domain/indices.market_size` (promedio de importaciones del destino en
los últimos 3 años) → `domain/scoring.rank_markets` (normalización min-max +
pesos desde `config.py`) → `pipeline/build_snapshot` (escribe
`data/processed/ranking.parquet` + `meta.json`) → app Streamlit que lee SOLO
el snapshot y muestra el ranking.

**Hecho cuando:**

- `python -m tradefit.pipeline.build_snapshot` produce el snapshot y es
  idempotente (dos corridas → mismo resultado).
- La app muestra el ranking leyendo solo `data/processed/`; sin snapshot,
  degrada con un mensaje claro.
- `market_size` tiene test con valor calculado a mano; el ranking tiene test
  sintético con orden obvio. pytest + ruff + mypy en verde.
- Commits Conventional Commits.

## Fase 2 — Ingesta real (Comtrade)

**Entrega:** `ingest/comtrade.py` (importaciones HS 0901 por destino; key
gratuita leída de `COMTRADE_API_KEY`, con fallback al preview público de
máx. 500 registros y 1 período por request); descarga cruda cacheada en
`data/raw/`; 18 mercados reales. El contrato del snapshot NO cambia:
`domain/` y `app/` no se tocan. El pipeline acepta `--source comtrade|stub`.

> Nota de re-alcance: `ingest/worldbank.py` (WDI) se movió a la Fase 4, que es
> donde el filtro macro lo consume — las fases son cortes verticales y no se
> construye ingesta sin consumidor.

**Hecho cuando:** el pipeline construye el snapshot con datos reales cacheados;
ingest testeado con respuestas guardadas/mockeadas (tests sin red); fallo
ruidoso si una fuente cambia de formato; verde + commit.

## Fase 3 — Motor de oportunidad completo

**Entrega:** las 4 métricas del MVP en `domain/indices.py`, cada una con
docstring que cita su definición y test con valor calculado a mano:

1. Tamaño **y crecimiento** de importaciones del destino (nivel + CAGR).
2. Cuota de mercado del origen en el destino y su tendencia.
3. RCA de Balassa (1965) del origen en el producto.
4. Complementariedad comercial origen–destino.

`scoring.py` combina las métricas con pesos documentados y justificados en
`config.py`.

**Hecho cuando:** cada índice tiene test a mano; el ranking combinado se prueba
con un caso sintético de orden obvio; la app muestra las métricas; verde + commit.

## Fase 4 — Filtro macro de estabilidad

**Entrega:** `ingest/worldbank.py` (WDI, sin key, caché en `data/raw/`) +
`domain/macro_filter.py`: score de estabilidad del destino con indicadores WDI
(p. ej. inflación, crecimiento del PIB, balanza por cuenta corriente),
aplicado como **penalización multiplicativa** sobre el score de oportunidad;
umbrales/parámetros documentados en `config.py`.

**Hecho cuando:** filtro testeado con caso a mano (país estable vs. inestable,
orden esperado); el snapshot incluye score bruto y penalizado; la app los
distingue; verde + commit.

## Fase 5 — Narrativa por reglas + recomendaciones

**Entrega:** generador de narrativa en `domain/` (puro): reglas transparentes
donde **cada frase incluye el número que la respalda**; top-3 recomendaciones
de mercados con su porqué. La app la muestra por mercado.

**Hecho cuando:** narrativa testeada (input sintético → frases esperadas);
ninguna afirmación sin número; verde + commit.

## Fase 6 — Export PDF/Excel + pulido

**Entrega:** export del ranking + narrativa a Excel (openpyxl) y PDF
(reportlab) desde la app, leyendo solo el snapshot; pulido de UX.

**Hecho cuando:** ambos archivos se generan y abren correctamente; verde + commit.

## Backlog (fuera del MVP)

- Aranceles (WITS) como métrica adicional del motor de oportunidad.
- Selección libre de producto HS y país de origen en la app.
- IMF SDMX como fuente macro complementaria (frágil; solo si WDI no cubre algo).
