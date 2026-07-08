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

- **Última fase completada:** F6 — export PDF/Excel (2026-07-05). **MVP completo.**
- **Post-MVP hecho:** metodología visible en la app (expander con fórmulas y
  citas) + **multi-producto**: snapshots por HS en `data/processed/<hs>/`
  (café 0901, flores 0603, banano 0803; `--hs` en el pipeline, selector en la
  app). RCA reales: flores 96.8, banano 40.8, café 35.7. Cuota de flores
  COL→USA: 59 % (cuadra con la realidad, ~60 %).
- **Buscador avanzado (2026-07-07):** la app analiza CUALQUIER partida HS
  (2/4/6 dígitos) — búsqueda por código o descripción (catálogo versionado
  `data/sample/hs_reference.csv.gz`, 8261 códigos H6, módulo `hs_codes.py`
  sin red) → `pipeline.ensure_snapshot(hs)` construye on-demand con caché
  (excepción sancionada en CLAUDE.md). Tolerancias para partidas arbitrarias:
  bilateral vacío = cuota 0 (no error) y origen sin exportaciones del
  producto = RCA 0. En el cloud la key llega por `st.secrets` (puente en la
  app hacia la variable de entorno).
- **Aranceles WITS (2026-07-07):** métrica `tariff_faced` — arancel
  efectivamente aplicado a Colombia (AHS: mín(MFN, preferencial) por HS6,
  promedio simple), invertida en el scoring (menos = mejor), peso 0.10 en
  `WEIGHTS` rebalanceados. Sin dato de WITS → aporte neutro 0.5 (mismo
  criterio que el macro). Con datos reales: el café entra libre en 17
  destinos y Japón cobra 6 % (sin acuerdo → MFN); banano: Japón 12,75 %.
- **Narrativa bilingüe (2026-07-07):** `narrative.json` trae `{"es", "en"}`
  (generadas por `domain/narrative.py` con plantillas y formato numérico por
  idioma); la app muestra la del idioma activo y los exports Excel/PDF van
  completos en ese idioma (etiquetas, números y narrativa). Snapshots con el
  formato plano viejo degradan a español.
- **En curso:** backlog (IMF SDMX como macro complementaria) + mejoras de
  buen costo/beneficio sin preguntar.
- **Web:** repo público https://github.com/juanjjaramilloz-esp/Radar-de-Mercados;
  deploy en Streamlit Community Cloud (entry point `streamlit_app.py`, snapshot
  de ejemplo versionado). `git push` está denegado para Claude Code: los push
  los hace el usuario.
- **Export:** `app/export.py` — Excel (openpyxl: hojas Ranking + Narrativa,
  formatos numéricos) y PDF (reportlab: top-3, tabla, lectura por mercado),
  funciones puras (ranking, meta, narrative) → bytes, testeadas sin Streamlit.
- **Narrativa:** `domain/narrative.py` (puro) → `data/processed/narrative.json`;
  cada frase cita su número (test lo verifica con regex); top-3 con porqué =
  las 2 métricas de mayor contribución peso×norm, con valor crudo y posición.
- **Modo de trabajo:** libertades creativas post-MVP acordadas — mejoras de
  buen costo/beneficio se implementan sin preguntar (ver CLAUDE.md).
- **Filtro macro:** WDI (inflación, PIB, cuenta corriente) → rampas lineales
  (`config.MACRO_BOUNDS`) → `final_score = score × (0.5 + 0.5·estabilidad)`.
  Con datos reales: USA pierde ventaja (estabilidad 0.66) y ESP/KOR/ITA casi
  lo alcanzan en score final.
- **`COMTRADE_API_KEY` ya configurada en `.env`:** endpoint autenticado
  activo, cachés re-descargados completos (canastas: 1841 filas).
- **Métricas vivas:** `market_size`, `import_growth` (CAGR), `market_share`,
  `share_trend`, `complementarity` (Michaely), `tariff_faced` (AHS de WITS,
  invertida); RCA de Balassa como columna de contexto (constante entre
  destinos, no pondera). Pesos en `config.WEIGHTS`.
- **Datos:** reales, cacheados en `data/raw/` (por producto: imports,
  bilateral COL, totales de exportación y aranceles WITS; compartidos:
  canastas HS2 y macro WDI; 2022–2024, 18 mercados). Snapshot real: RCA de
  Colombia en café = 35.66 (2024).

## Cómo correr (Windows)

```powershell
.venv\Scripts\Activate.ps1                      # activar entorno
python -m tradefit.pipeline.build_snapshot      # snapshot (--source stub como fallback)
streamlit run src/tradefit/app/main.py          # app
pytest ; ruff check . ; mypy src                # puerta de calidad
```

## Decisiones no obvias (log)

- 2026-07-05 · F4: destino sin datos WDI = **warning + estabilidad neutra
  (0.5)**, no error — la ausencia en WDI es hueco de fuente, no evidencia de
  inestabilidad. El piso 0.5 de la penalización evita que el filtro macro
  anule la oportunidad comercial (destinos MVP = economías desarrolladas).
  El API de WDI a veces da timeout en frío: reintentar el build.
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
- 2026-07-07 · WITS TRAINS: el endpoint SDMX solo acepta subpartidas **HS6**
  (una partida se expande con `hs_codes.hs6_children`), los códigos de país
  van a **3 dígitos** ("036") y son ISO numéricos (Suiza 756, no el 757 de
  Comtrade); la UE reporta como bloque (**918**) — una consulta cubre a los
  11 destinos comunitarios. `format=JSON` se ignora: la respuesta es XML
  SDMX GenericData. Aranceles específicos sin equivalente ad-valorem llegan
  como ObsValue `"NaN"` (azúcar en Canadá) → observación descartada.
- 2026-07-07 · Arancel sin dato = **NaN → aporte neutro 0.5** en el scoring
  (no 0): que WITS no publique el arancel no es evidencia de arancel alto —
  mismo criterio que la estabilidad macro neutra.

## Pendientes conocidos

- `git push` pendiente del usuario (regla de permisos): narrativa bilingüe
  (4 commits) + enlace del repo nuevo en la app. El remoto nuevo
  (`juanjjaramilloz-esp/Radar-de-Mercados`) ya tiene todo hasta aranceles WITS.
- Backlog: IMF SDMX como macro complementaria.
