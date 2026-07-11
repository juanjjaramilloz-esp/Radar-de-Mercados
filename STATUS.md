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

## ✅ Última tanda — seguridad, integridad y refresh automático (2026-07-11)

1. CORS y XSRF vuelven a estar activos; el dominio de un proxy propio se
   configura con `STREAMLIT_BROWSER_SERVER_ADDRESS`.
2. Los cachés crudos llevan sidecars con parámetros, vintage y SHA-256;
   cambiar años invalida el caché. Los snapshots se preparan completos en
   staging, llevan `manifest.json`, se publican por swap con lock y la app
   verifica contrato + hashes. El stub no sobrescribe el macro compartido.
3. `.github/workflows/data-refresh.yml` revisa mensualmente TTL por fuente
   (Comtrade 60 días, WDI 90, WITS 180), reconstruye y abre una PR de datos
   después de pasar la puerta completa. No empuja directamente a `main`.

## ✅ Última tanda — margen de preferencia + backtest (2026-07-09, COMPLETA)

Tanda "1 y 3" aprobada por el usuario (las dos mejoras de comercio
internacional priorizadas): margen de preferencia relativo y validación
predictiva. La automatización del refresh que era el siguiente paso quedó
completada el 2026-07-11 (ver tanda superior).

1. **Margen de preferencia relativo** (`preference_margin`, pondera 0.05):
   arancel AHS promedio de los top-3 proveedores rivales de cada destino −
   arancel de Colombia (cf. Fugazza & Nicita 2013, *JIE* 89(2)). Corrige el
   sesgo "0 % parece ventaja aunque todos paguen 0 %". El bloque arancelario
   0.10 se partió en tariff_faced 0.05 + margen 0.05. Ingest nuevo:
   `wits.load_competitor_tariffs` — 1 consulta PREF por reporter con los
   partners unidos con `+` (multi-partner verificado contra el endpoint;
   PARTNER llega en la SeriesKey), caché por producto que se invalida solo
   si el top de competidores cambia. Traducción de códigos Comtrade→WITS en
   `_competitor_partner_plan` (pipeline): UE como bloque 918, intra-UE = 0
   por unión aduanera, excepciones M49 (757→756 etc.), agregados
   estadísticos fuera. Dominio puro `indices.competitor_tariff_faced`
   (3 tests a mano) + columnas `competitor_tariff` (contexto) y
   `preference_margin` en el ranking; narrativa con frase propia
   (ventaja/desventaja/empate), ficha con línea ⚖️, metodología, exports.
   Sanity real (café): Japón **−2 pp** (COL paga 6 % MFN, Vietnam 4 %),
   Brasil **+10 pp**, USA/CAN 0 (el fix del sesgo, exacto).
2. **Backtest del score** (`pipeline/backtest.py` → `backtest.json`
   versionado): las 4 métricas de comercio se recalculan as-of 2020–2022
   (cachés históricos nuevos de Comtrade) y el score re-scoreado
   (`rescore_ranking`, cero fórmulas nuevas) se contrasta con el
   crecimiento realizado del flujo COL→destino 2023–2025 (tasa simétrica
   DHS — Davis-Haltiwanger-Schuh 1996, robusta a flujos cero). Métricas:
   Spearman por producto, agregado con rangos intra-producto, hit-rate
   top-5, y baseline "solo tamaño de mercado" para mostrar skill.
   `domain/backtest.py` puro con 9 tests a mano. La app lo muestra en
   metodología («🧪 Validación») con guía de lectura y limitaciones.
   **Resultado honesto**: agregado ρ score = −0.04 vs. baseline = 0.01
   (343 pares) — ni el score ni el baseline anticipan el crecimiento
   bilateral de corto plazo. Se publica igual (espíritu glass-box): el
   score se defiende como medida de atractivo del mercado, no como
   pronóstico; causas plausibles documentadas en la app (estructurales
   congeladas, ventana 2020–2022 distorsionada por pandemia, DHS ruidoso
   en flujos chicos, mean reversion). Es un talking point de entrevista,
   no un defecto escondido.
3. Los 15 snapshots reconstruidos con las columnas nuevas (WITS de
   competidores descargado y cacheado). El buscador on-demand también
   calcula el margen (algunas consultas WITS extra por partida nueva).

## ✅ Tanda anterior — cobertura de datos del score (2026-07-08, COMPLETA)

Mejora única elegida por criticidad (pedido del usuario: "lo más crucial"):
el score podía apoyarse en rellenos silenciosos (arancel/accesibilidad sin
dato → neutro 0.5; complementariedad/CAGR sin dato → 0; macro → 0.5) y en la
app era indistinguible de un score 100 % respaldado por datos — hueco de
defendibilidad del pitch glass-box.

1. **`data_coverage`** — nueva columna del ranking [0,1]: fracción del peso
   del score respaldada por dato observado (NaN crudo **antes** del relleno
   = no observado), calculada en `domain/scoring.data_coverage` (pura, 3
   tests a mano). Excepción documentada: cuota/Δ cuota ausentes del
   bilateral son **cero observado por diseño** (decisión 2026-07-05), no
   hueco de fuente. No pondera en el score; es transparencia del insumo.
   Contrato `required=False` (snapshots viejos siguen válidos, la app
   degrada con gracia).
2. **App**: columna opcional en «⚙️ Columnas» (formato %), tooltip con la
   definición, y línea 🧭 en la ficha del destino con el % y las métricas
   sin dato nombradas (las que el snapshot deja visibles como NaN: arancel,
   accesibilidad, CAGR; la complementariedad ausente descuenta el % aunque
   no se nombre — llega rellenada a 0). Exports Excel con la columna.
   Verificado con AppTest en ES/EN, casos parcial (DOM banano 82 %, nombra
   «Crecimiento») y 100 % (USA café).
3. **Rebuild de los 15 snapshots** con la columna. En el catálogo curado la
   cobertura es ~100 % (solo DOM en banano 0803 = 82 %, sin CAGR); el valor
   real de la columna está en el buscador avanzado (partidas arbitrarias con
   huecos de WITS/canastas frecuentes).
4. Hallazgo colateral (preexistente, NO de esta tanda, queda como chip de
   tarea): al cambiar de idioma se pierde el foco y el producto vuelve al
   default (estado de widgets con label traducido).

## ✅ Tanda anterior — accesibilidad logística + perfil arancelario HS6 (2026-07-08, COMPLETA)

1. **Accesibilidad logística** (`f891b3f`): nueva métrica `accessibility`
   [0,1] que pondera **0.10** en el score — promedio de (a) rampa lineal en
   **log-distancia** bilateral (CEPII GeoDist `distw` con fallback a `dist`;
   modelo gravitacional — Tinbergen 1962; elasticidad ≈ −0.9 cf. Disdier &
   Head 2008) entre extremos físicos (100 km ↔ 20 015 km = media
   circunferencia) y (b) rampa del LPI sobre su escala completa 1–5 (sin
   dato = neutro 0.5, mismo criterio que el arancel). Sin distancia →
   NaN → aporte neutro en el scoring. El extracto CEPII del origen vive
   **versionado** en `data/sample/geodist_col.csv.gz` (la fuente es final y
   la geografía no caduca; se regenera con `python -m
   tradefit.ingest.geodist`). Los demás pesos cedieron 10 pp en total
   (market_size 0.22, growth 0.18, share 0.14, trend 0.08, compl. 0.18).
   Columnas nuevas `distance_km` (contexto) y `accessibility` en el ranking
   (`required=False`: snapshots viejos siguen válidos y la narrativa/app
   degradan con gracia).
2. **Perfil arancelario intra-partida** (`e1f97eb`): nueva función pura
   `tariff_profile` — el AHS por (destino, subpartida HS6) con el tipo que
   aplica (PREF en empate: documenta el acuerdo) y su año; `tariff_faced`
   ahora ES su promedio simple (coherencia testeada). El pipeline conserva
   el detalle en `tariff_profile.parquet` y la ficha del destino lo grafica
   (barras por subpartida, verde = preferencial / gris = MFN, etiquetas del
   catálogo HS). Sin dispersión (p. ej. café: todo 0 % por TLC) el bloque
   muestra una frase en lugar de barras invisibles. Ejemplo real: 8504 en
   Ecuador esconde **18 pp** de dispersión entre subpartidas.
3. **Recencia de datos**: el comercio (Comtrade) llega a 2025 en los
   snapshots reconstruidos (`03f0b61`); los aranceles WITS traen el rezago
   propio de la fuente (2021–2023 según destino, se cita el año por línea);
   CEPII es estático por naturaleza (documentado en `ingest/geodist.py`).

## ✅ Tanda anterior — comparador global de mercados (2026-07-08, COMPLETA)

1. **Comparador global** (`9d1c573`): multiselect «🔍 Mercados a comparar
   (máx. 3)» encima de las pestañas (opciones por ISO3 → sobreviven al
   toggle de idioma; el estado se depura al cambiar de producto, p. ej.
   banano sin ECU/MEX). Con selección activa, TODAS las gráficas (mapa,
   desglose, radar, scores, tamaño, valor unitario, evolución) muestran
   solo esos mercados. El radar perdió su selector interno y usa este
   (top-3 sin selección, con hint); la evolución oculta el suyo en modo
   comparación. Las normalizaciones min-max (desglose/radar) se calculan
   SIEMPRE sobre el ranking completo: comparar no cambia los valores
   (`_compare_view` solo filtra presentación).
2. **Chips con color de bandera** (`ff6cc87`): `FLAG_COLORS` + `flag_color`
   en `app/flags.py` (tono representativo del pabellón por ISO3, curado a
   mano). CSS `.st-key-compare_markets [data-baseweb=tag]:nth-of-type(n)`
   — el orden del DOM es el orden de selección, el mismo de las trazas —
   con texto blanco/negro por luminancia. Radar y evolución (en modo
   comparación) usan el MISMO color por país: la chip hace de leyenda y la
   leyenda del radar se apaga (`showlegend=not compare`; vuelve con el
   top-3 default). Verificado en preview (excepción visual justificada):
   colores computados chip↔traza idénticos.

## ✅ Tanda anterior — valores unitarios + tooltips + piso macro (2026-07-08, COMPLETA)

1. **Valores unitarios (USD/kg) por destino** (`30f9d2d`): nueva señal de
   posicionamiento precio/calidad, exclusiva del catálogo curado. UV =
   valor ÷ peso neto (UN IMTS 2010) agregado como **cociente de sumas**
   sobre la ventana de `MARKET_SIZE_YEARS`; premium = UV_origen/UV_destino
   − 1 (cf. Hummels & Klenow 2005). Todo sale del `netWgt` de los cachés
   crudos ya descargados (cero red nueva). Piezas: `parse_flow_weights` +
   `load_import_weights`/`load_bilateral_weights` (ingest),
   `aggregate_unit_value`/`unit_value_premium` (domain, testeadas a mano),
   `flow_weights_schema`/`unit_values_schema` (contratos),
   `_unit_values_table` + `refresh_unit_values` (pipeline), pestaña
   «💲 Valor unitario» (barras del promedio + rombo ámbar del origen) y
   bloque en la ficha de foco con el premium como delta. Los 15
   `unit_values.parquet` versionados para el demo (ya generados con
   `refresh_unit_values`, sin rebuild).
2. **Tooltip (i) en todas las columnas del ranking y en los 5 KPIs**
   (`e2ef9cd`): cada header lleva `help=` con la definición de una frase
   (fórmula/fuente donde aplica); antes solo lo tenían 3 columnas y 2 KPIs
   — incluida la petición directa del KPI «cuota agregada del origen».
3. **Piso de la penalización macro ajustable en el simulador** (`386bf63`):
   slider 0–100 % (paso 5, oficial 50 %) junto a los pesos.
   `rescore_ranking` ya aceptaba `macro_floor` validado — la app solo
   recoge el valor; el piso simulado se propaga a toda la página con los
   pesos, entra al gate del CSV simulado y «↺ Valores oficiales» también
   lo resetea. Test nuevo a mano: piso 1.0 apaga el filtro, piso 0.0
   multiplica por la estabilidad completa. Verificado además con AppTest
   (slider → nota de simulador activo → reset).

## ✅ Tanda anterior — ronda de pulido (2026-07-08, COMPLETA)

Quick wins acordados (40% UI, 40% exports, 20% rendimiento; enfoque demo):

1. **Caché de lecturas del snapshot** (`_read_parquet`/`_read_json` sobre
   `st.cache_data`): el `mtime_ns` del archivo forma parte de la clave, así
   que `ensure_snapshot` invalida solo (resuelto el riesgo que tenía este
   ítem en el backlog). Cada tick de slider ya no relee parquet del disco.
2. **CSV del ranking simulado** dentro del simulador (solo cuando los pesos
   difieren de los oficiales) + nota de que CSV/Excel/PDF de arriba siguen
   exportando el oficial.
3. **Δ posición coloreada** en la tabla del simulador (Styler: verde/rojo).
4. **Radar con paleta propia** (azul/ámbar/verde + relleno translúcido).
5. (Commit anterior de la misma sesión) margen superior en las tres
   gráficas de barras: la leyenda ya no tapa la primera barra.

## ✅ Tanda anterior — simulador propagado a toda la página (2026-07-08, COMPLETA)

Tres peticiones directas sobre el 🎯 Simulador de prioridades (solo `app/`):

1. **Los pesos del simulador ahora se propagan**: si el usuario mueve
   algún deslizador respecto a los pesos oficiales, `_weight_lab_section`
   devuelve `(rescored, weights)` y `main()` pinta TODO lo que queda de
   página (mapa, desglose, radar, scores, tamaño, evolución y ficha de
   foco) con ese ranking re-calculado y un meta con los pesos simulados
   (`view_ranking` / `view_meta`); un `st.info` avisa que los pesos del
   simulador están activos. Con los pesos oficiales intactos devuelve
   `None` y nada cambia. La tabla oficial del ranking, KPIs y narrativa
   (arriba del simulador) siguen siendo siempre las oficiales, a
   propósito. El clic en el mapa es seguro con el reorden (identifica por
   ISO3 en customdata, no por índice de fila).
2. **Paso fino**: sliders de 5% → 1%.
3. **Suma ≠ 100%**: es válido por diseño (pesos relativos, se normalizan
   a suma 1 en `domain/scoring`); ahora un caption lo dice explícitamente
   mostrando el total cuando difiere de 100.

## ✅ Tanda anterior — hero + selector de producto (2026-07-08, COMPLETA)

Dos correcciones de feedback visual, sobre la tanda de pulidos de abajo:

1. El hero decía «un país de origen» como si fuera elegible: ahora nombra
   a Colombia directamente (`config.ORIGIN_NAME` + su bandera 🇨🇴),
   coherente con la decisión de origen fijo (ver CLAUDE.md).
2. El selector de producto (acción primordial de la app) gana un
   contenedor con fondo/borde azul translúcido y label en negrita, vía
   la clase `st-key-<key>` que Streamlit asigna a `st.container(key=…)`
   — confirmado en el bundle del frontend (`convertKeyToClassName`) y
   verificado con `preview_inspect` (no por script, es CSS puro). El
   estilo queda acotado a este selector, no toca los demás de la página.

## ✅ Tanda anterior — pulidos de UI (2026-07-08, COMPLETA)

Cuatro pulidos de presentación (solo `app/`; verificados con scripts
`AppTest` desechables, sin tests permanentes nuevos):

1. «Laboratorio de pesos» → **«🎯 Simulador de prioridades»** (petición
   directa; solo texto i18n, los keys `lab_*` no cambian).
2. **Selector de columnas del ranking**: por defecto 8 columnas compactas
   (#, mercado, importaciones, crecimiento, cuota, arancel, estabilidad,
   score final); el resto (ISO3, Δ cuota, % export. COL,
   complementariedad, acuerdo, LPI, score bruto) se activa desde el
   popover «⚙️ Columnas» sobre la tabla. Tras feedback del usuario
   (multiselect dentro del popover = menú anidado poco intuitivo), el
   panel es **un checkbox por columna** en dos columnas. El estado vive
   en claves propias `ranking_col_store_<config.COL_*>` (no en el
   widget: la etiqueta traducida cambia su identidad y Streamlit
   descartaría el valor al cambiar de idioma) → sobrevive al toggle
   ES/EN y al cambio de producto. El resaltado de la fila en foco lee
   ISO3 de `ranking` (en `display` puede estar oculta). Exports
   CSV/Excel/PDF siguen con todas las columnas. La selección por fila se
   quitó y **se restauró** en la misma tanda (el usuario confirmó que el
   clic en la fila sí era útil); la columna «#» quedó en
   `width="small"` — el ancho en píxeles (int) se ignora en silencio en
   Streamlit 1.49, se añadió después.
5. **Score final como barra de progreso** (pedido del usuario): vuelve la
   `ProgressColumn` perdida en `debf131` al pasar la tabla a Styler. La
   columna necesita el valor numérico crudo → queda fuera del dict de
   formatos del Styler; trade-off asumido y comentado: su texto usa
   `"%.3f"` (punto fijo) también en español.
3. Nomenclatura: pestañas «🕸️ Perfil comparado» (antes colisionaba con el
   nombre de la app) y «Score bruto vs. final» (mismo término que las
   columnas); tooltips `help=` con definición de una frase en KPIs
   HHI/RCA y columnas cuota del origen / % export. COL / LPI.
4. UX: caption que anuncia el comparador cuando hay < 2 partidas (antes
   `return` silencioso), `focus_hint` con las 3 vías de foco (selector,
   mapa, fila de la tabla) y 💡, tooltips en el selector de foco y los
   sliders del simulador.

## ✅ Tanda anterior — «Profundidad Colombia» (2026-07-08, COMPLETA)

Tanda **"Profundidad Colombia"** (plan aprobado, 2 partes; contexto: con el
catálogo top-15, agregar info específica Colombia × producto × destino y
diferenciarse del ITC Export Potential Map — EPM predice USD con modelo
opaco para 222 países; el Radar es glass-box con filtro macro y 1 origen a
fondo). **Las dos partes quedaron completas y commiteadas**; falta el push
del usuario y el checklist manual de abajo.

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

**Parte 2 — completa (2026-07-08):**

- P2.1/P2.2 ✅ Focus por destino (commit `e12c305`): clic en el mapa
  (`on_select="rerun"`, customdata ISO3, guard anti-reimposición) o
  selector → **ficha del destino**: score+rank, arancel AHS con el acuerdo
  vigente, cuota COL y Δ, % export. COL, top-2 drivers
  (`score_contributions`), macro con año del dato
  (`macro_context.parquet` + `latest_indicator_value`) + LPI +
  estabilidad, top-5 proveedores con Colombia resaltada y su posición,
  mini-evolución y narrativa. Fila resaltada en la tabla y borde ámbar en
  el mapa. Reemplaza la vieja sección «Lectura por mercado». Verificado
  headless con `streamlit.testing.v1.AppTest`.
- P2.3 ✅ Competidores (commit `74babf2`): `ingest/competitors.py` (una
  consulta por producto: 26 reporters × todos los partners × 3 años,
  `includeDesc=true` para nombres) + `domain/indices.supplier_shares`
  (partner share cf. WITS; denominador = World del propio destino o suma;
  último año con dato por destino; testeado a mano) →
  `competitors.parquet` por producto + `macro_context.parquet` compartido
  (WDI crudo para la ficha). Versionados para el demo (commit `8dcfd60`,
  ~20-40 KB c/u). Sanity check real: Colombia = proveedor #1 de café en
  USA con 21,5 % (2025).
- P2.4 ✅ Diferenciación vs. ITC Export Potential Map: tabla honesta en el
  README + pitch corto en el sidebar (es/en).

**Siguiente tanda (pedida por el usuario, 2026-07-08):** investigar la
frecuencia/calendario de publicación de cada fuente (Comtrade, WDI, WITS,
LPI) y automatizar la recolección ~1 día después de cada publicación
oficial (probable GitHub Action que abre PR; requiere resolver token de
GitHub en CI — el push sigue siendo del usuario).

## Checklist manual — tanda «Profundidad Colombia» (revisar tras el push)

1. Selector de los 15 productos: cada uno carga sin error; banano (0803)
   muestra 24 mercados (no 26) — es correcto, no un bug (ECU/MEX no
   reportaron ese producto).
2. Tabla: columnas «Acuerdo comercial», «% export. de Colombia», «LPI
   logístico (1–5)» visibles, con datos, y respetando el toggle ES/EN.
3. Los 8 destinos LATAM (MEX/BRA/CHL/PER/ECU/CRI/PAN/DOM) con nombre y
   bandera correctos en tabla, mapa y radar.
4. KPI de concentración (HHI) + frase de la narrativa sobre dependencia.
5. **Focus mode**: clic en un país del mapa → la ficha aparece abajo, la
   fila del ranking queda resaltada en ámbar y el país con borde ámbar;
   «✕ Quitar foco» limpia todo; el selector de la ficha es equivalente.
6. **Ficha del destino** (probar café 0901 + USA): 4 métricas arriba
   (score #rank, arancel con TLC, cuota+Δ, % export COL), línea de
   drivers, contexto macro con años, top-5 proveedores con Colombia en
   ámbar («Colombia es el proveedor #1 con 21,5 %»), mini-evolución y
   frases de narrativa. Cambiar idioma y verificar que todo se traduce.
7. Ficha con un destino sin competidores (banano → probar; o partida del
   buscador con snapshot viejo): mensaje de degradación, no error.
8. Laboratorio de pesos: sigue reproduciendo el ranking oficial.
9. Export Excel: trae Acuerdo/LPI/% export.
10. Sidebar: pitch «¿En qué se diferencia del ITC EPM?» en ambos idiomas;
    README con la tabla de diferenciación bien renderizada en GitHub.
11. Buscador avanzado: partida nueva construye on-demand (ahora descarga
    también competidores; algo más lento pero con ficha completa).

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

- ~~`git push` pendiente del usuario~~ HECHO 2026-07-08: el remoto
  (`juanjjaramilloz-esp/Radar-de-Mercados`) está al día hasta la tanda de
  accesibilidad + perfil arancelario HS6 (`e9734d2`). El push sigue siendo
  del usuario (regla de permisos) tras cada tanda nueva.
- Screenshots del README (los toma el usuario, antes del push):
  `docs/img/app-overview.png` y `docs/img/weight-lab.png`.
- `gh` CLI local sin cuenta logueada (2026-07-08): la credencial vieja
  suspendida se limpió (`gh auth logout`) porque causaba 403 confusos; si se
  necesita `gh` autenticado, correr `gh auth login` con la cuenta nueva
  (`juanjjaramilloz-esp`) — flujo OAuth interactivo, requiere el usuario.
- Backlog: IMF SDMX como macro complementaria. La automatización del refresh
  quedó hecha el 2026-07-11 (workflow mensual + TTL por fuente + PR revisable).
- ~~Backlog: `st.cache_data` en los loaders~~ HECHO 2026-07-08 con clave por mtime (ver última tanda). Detalle histórico: (`_load_snapshot`,
  `_load_imports_timeseries`, `_load_competitors`, `_load_macro_context`)
  — beneficio real (no releer parquet en cada rerun/slider) pero riesgo
  alto: esos archivos los escribe `ensure_snapshot` en caliente y una
  caché mal invalidada serviría un snapshot viejo recién construido.
  Cambio propio con pruebas de invalidación.
