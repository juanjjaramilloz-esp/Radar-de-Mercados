# STATUS — Radar de Mercados

> **Propósito:** contexto mínimo para retomar el proyecto en un chat nuevo sin
> releer todo. Se actualiza al cierre de cada fase o cambio relevante.
> No duplica: arquitectura y reglas → [CLAUDE.md](CLAUDE.md); fases y criterios
> → [PLAN.md](PLAN.md). Aquí solo: estado, decisiones no obvias y pendientes.

## Qué es (1 línea)

Screener de mercados de exportación: dado un producto (HS) desde Colombia →
ranking de 26 destinos (18 OCDE/Asia + 8 LATAM). Motor económico puro en
`domain/`, snapshot Parquet como contrato, app Streamlit que solo lee el
snapshot.

## ⏸️ Trabajo en curso — retomar aquí (2026-07-08)

Tanda **"Profundidad Colombia"** (plan aprobado, 2 partes; contexto: con el
catálogo top-15, agregar info específica Colombia × producto × destino y
diferenciarse del ITC Export Potential Map — EPM predice USD con modelo
opaco para 222 países; el Radar es glass-box con filtro macro y 1 origen a
fondo).

**Parte 1 — completa (2026-07-08):**

- P1.1 ✅ 8 destinos LATAM en config (MEX/BRA/CHL/PER/ECU/CRI/PAN/DOM → 26
  mercados; commit `336c13a`).
- P1.2 ✅ `config.TRADE_AGREEMENTS(_EN)` (fuente MinCIT) + columna «Acuerdo
  comercial» + nota metodológica (commit `ce2f16b`).
- P1.3 ✅ HHI de concentración de destinos + `share_of_origin_exports`
  (ingest/domain/pipeline/app/narrativa; commit `34f4ac8`).
- P1.4 ✅ LPI del destino: `latest_indicator_value` en
  `domain/macro_filter.py` (último año con dato por país, indicador
  esparso; 2 tests a mano), columna `lpi` en el snapshot (antes de
  `stability_score`, NaN si falta), formato/i18n/nota metodológica en la
  app, columna en el Excel exportado (commit `8110404`).
- P1.5 ✅ **rebuild forzado** de los 15 productos × 26 mercados: cachés de
  `data/raw/` dependientes de la lista de reporters movidos a un backup
  fuera del repo (importaciones, bilateral, canastas HS2, WDI, WITS —
  `export_totals` y el top-15 no dependen de reporters, no se tocaron) +
  `python -m tradefit.pipeline.build_snapshot` completo. Verificado: los 15
  `ranking.parquet` pasan `ranking_schema`, LPI y
  `share_of_origin_exports` pobladas, `rescore_ranking` reproduce el
  ranking oficial en los 15 (commit `ad0e667`). 14/15 con 26 mercados;
  **banano (0803) queda en 24** — ECU y MEX no reportaron ese producto en
  Comtrade (riesgo ya documentado en el plan, no es un bug). README/PLAN
  actualizados a "26 mercados".

**Parte 2 — planificada (siguiente sesión):** mapa interactivo con focus
por destino (`st.plotly_chart(on_select="rerun")`), ficha del destino
(drivers + TLC + LPI + macro + evolución), `ingest/competitors.py` (top-5
proveedores por destino, Colombia resaltada) y sección README de
diferenciación vs. EPM. Detalle completo en el plan aprobado
(`~/.claude/plans/lee-el-proyecto-vamos-federated-crane.md`).

## Checklist manual — Parte 1 (revisar en Streamlit tras el push)

1. Selector de los 15 productos: cada uno carga sin error; banano (0803)
   muestra 24 mercados (no 26) — es correcto, no un bug.
2. Tabla: columnas nuevas «Acuerdo comercial», «% export. de Colombia»,
   «LPI logístico (1–5)» visibles, con datos (no todo `—`), y que cambien
   de idioma/formato con el toggle ES/EN.
3. Los 8 destinos LATAM (MEX/BRA/CHL/PER/ECU/CRI/PAN/DOM) aparecen con
   nombre y bandera correctos en tabla, mapa y radar de métricas.
4. KPI de concentración de destinos (HHI) + frase de la narrativa sobre
   dependencia de un destino.
5. Mapa choropleth pinta los países LATAM nuevos.
6. Laboratorio de pesos: sigue reproduciendo el ranking oficial (las
   columnas nuevas son contexto, no ponderan).
7. Export Excel: abre y trae Acuerdo/LPI/% export con formato correcto.
8. Expander de Metodología: nota nueva del LPI en ambos idiomas.
9. Buscador avanzado (cualquier HS): sigue funcionando on-demand con 26
   mercados (más lento; vigilar que no dé timeout visible).

## Estado actual

- **Última fase completada:** F6 — export PDF/Excel (2026-07-05). **MVP completo.**
- **Post-MVP hecho:** metodología visible en la app (expander con fórmulas y
  citas) + **multi-producto**: snapshots por HS en `data/processed/<hs>/`
  (café 0901, flores 0603, banano 0803; `--hs` en el pipeline, selector en la
  app). RCA reales: flores 96.8, banano 40.8, café 35.7. Cuota de flores
  COL→USA: 59 % (cuadra con la realidad, ~60 %).
- **Multi-producto:** ahora son los 15 curados (ver arriba); los 3
  originales (café/flores/banano) siguen dentro.
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
- **26 mercados destino (2026-07-08):** los 18 originales (OCDE/Asia) + 8
  LATAM (México, Brasil, Chile, Perú, Ecuador, Costa Rica, Panamá, Rep.
  Dominicana; commit `336c13a`) — los 15 snapshots curados reconstruidos con
  todos (banano queda en 24: ECU/MEX no reportan ese producto en Comtrade).
- **Catálogo curado top-15 (2026-07-08):** el desplegable ofrece las 15
  partidas HS4 más exportadas por Colombia **sin minero-energéticos**
  (cap. 27/71 fuera; fuente Comtrade 2024, `ingest/top_exports.py`,
  regenerable con `python -m tradefit.ingest.top_exports`). La app ya no
  lista cualquier snapshot del disco (los visitantes del demo construían
  partidas como 8802 aviones y quedaban en el selector de todos): curados
  siempre visibles (build on-demand si falta), partida no curada solo
  mientras esté activa. 0902/1704/8802 retirados del repo; los 15 snapshots
  del demo, versionados.
- **Tanda "cara al reclutador" (2026-07-07):** fix de separadores por idioma
  en tabla/barras (Styler + Plotly), CI GitHub Actions + badges, README
  renovado (mermaid, English summary), **laboratorio de pesos what-if**
  (sliders → `domain/scoring.rescore_ranking`, reproduce el oficial con los
  pesos de config), pestañas «¿Por qué este score?» (desglose w·norm) y
  «📡 Radar de métricas» (Scatterpolar top-3). Pendiente del usuario:
  screenshots `docs/img/app-overview.png` y `docs/img/weight-lab.png`
  referenciados por el README.
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
- 2026-07-07 · Regla "la app no calcula" **relajada por decisión del
  usuario** para funciones interactivas: la app puede invocar funciones
  puras de `domain/` sobre el snapshot ya leído (laboratorio de pesos,
  desglose, radar). Sin red, sin I/O; las fórmulas se testean en `domain/`.
- 2026-07-07 · Los formatos de `st.column_config` no siguen el toggle de
  idioma (printf = punto decimal fijo; `"localized"` = locale del navegador):
  todo número visible se formatea con `app/format.py` (tabla vía Styler,
  gráficas vía Plotly `separators`).

## Pendientes conocidos

- `git push` pendiente del usuario (regla de permisos): narrativa bilingüe +
  tanda "cara al reclutador" + tanda "Profundidad Colombia" Parte 1 completa
  (LATAM, TLC, HHI, LPI, rebuild 26 mercados). El remoto nuevo
  (`juanjjaramilloz-esp/Radar-de-Mercados`) solo tiene hasta aranceles WITS.
- Screenshots del README (los toma el usuario, antes del push):
  `docs/img/app-overview.png` y `docs/img/weight-lab.png`.
- `gh` CLI local sin cuenta logueada (2026-07-08): la credencial vieja
  suspendida se limpió (`gh auth logout`) porque causaba 403 confusos; si se
  necesita `gh` autenticado, correr `gh auth login` con la cuenta nueva
  (`juanjjaramilloz-esp`) — flujo OAuth interactivo, requiere el usuario.
- Backlog: IMF SDMX como macro complementaria; Parte 2 de "Profundidad
  Colombia" (mapa con focus, ficha del destino, competidores, diferenciación
  vs. EPM en el README).
