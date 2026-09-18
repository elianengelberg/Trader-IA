# Market maker profesional — Fase 3, Etapa 1: auditoría y diseño técnico

**PHASE3_STATUS = IMPLEMENTATION** (desde el 2026-09-18, con las cuatro decisiones de §17 confirmadas por el operador; D1 con la arquitectura de una sola autoridad global de solo lectura).
Fecha: 2026-09-18. Base: commit `9362dfa` (Fase 2 cerrada con PASS sobre Binance real,
según la evidencia del operador transcrita en `docs/MARKET_MAKING_PHASE2_REPORT.md`).

Principio rector: **DATA INTEGRITY > EXECUTION INTEGRITY > STATISTICAL INTEGRITY > RISK >
PnL.** Ningún fill inventado, ninguna información futura, ningún resultado que modifique
retroactivamente la señal que lo originó. La máquina que se diseña responde una sola
pregunta: *"si hubiera colocado estas órdenes en Binance en ese momento, con esta
información disponible, estas latencias y estos costos, ¿habría tenido expectativa neta
positiva?"*.

Hay **una inconsistencia arquitectónica importante** (§17, D1: cómo ejerce autoridad el
`RiskEngine` existente sobre un proceso de cotización continua) y **tres decisiones** que
requieren confirmación antes de implementar lógica de rentabilidad. Por eso este
documento se entrega solo, sin código de Fase 3.

---

## 1. Datos disponibles actualmente

| Fuente | Módulo | Contenido | Estado |
|---|---|---|---|
| `btcusdt@depth@100ms` (WS) | `tia/mm/streams.py` → `LocalOrderBook` | diffs absolutos por nivel (`U`, `u`, `b`, `a`), libro local sincronizado por el procedimiento oficial | validado en el VPS (Fase 2) |
| `btcusdt@trade` (WS) | `tia/mm/streams.py` | cada trade: `t` (id secuencial), `p`, `q`, `m` (buyer is maker), `T`, `E` | validado |
| `btcusdt@bookTicker` (WS) | `tia/mm/streams.py` | mejor bid/ask y tamaños, `u`; **sin timestamp del exchange** en Spot | validado; sólo comparación |
| `GET /api/v3/depth` (REST) | `binance_public.depth_snapshot` | hasta 5000 niveles con `lastUpdateId` | validado |
| Grabación | `tia/mm/recorder.py` | segmentos horarios `jsonl.gz` con snapshot, checkpoints, depth, trade, book; manifiesto con sha256, `format=2`, `replayable` | validado (replay OK, checksum OK, digest OK) |
| Replay del libro | `tia/mm/replay.py` | reconstrucción determinista desde un segmento | validado |
| Latencias | `tia/mm/latency.py`, `MarketDataService.processing_us` | exchange→local p50/p95/p99/min/max por stream; procesamiento local en µs | medidas en el VPS; **las cifras deben transcribirse** (ver §12) |
| Velas 1m, bookTicker de la sesión 24/7 | `data/providers/binance_stream.py` | feed de la sesión existente | no se toca ni se comparte estado |
| Historial grabado | `/app/data/runtime/ticks-*` en el VPS | del orden de **decenas de minutos** reales (corridas de 5 y 2 minutos del 2026-09-18) | **insuficiente** para train/validation/OOS (§15) |

Lo que **no** existe: L3 (órdenes individuales) de Binance, nuestra posición real en la
cola, históricos de profundidad del venue (Binance no los publica), fills reales.

## 2. Timestamp de cada fuente

| Evento | `R` (recepción local, ms, reloj inyectado) | `E` (event time del exchange) | `T` (trade time) | Id de secuencia |
|---|---|---|---|---|
| depth | sí | sí | — | `U`..`u` |
| trade | sí | sí | sí | `t` |
| bookTicker | sí | **no** (Spot) | — | `u` |
| snapshot REST | sí (momento de aplicación) | — | — | `lastUpdateId` |
| checkpoint | sí | — | — | `update_id` |

Regla: **el único "ahora" del sistema es `R`**. `E` y `T` sirven para medir latencia y para
describir; nunca ordenan el procesamiento ni deciden un fill. La grabación preserva el
orden de llegada, así que el replay reproduce exactamente la secuencia que el proceso vio.

## 3. Información disponible en `t`

En el instante `t` (un `R`), el sistema conoce: el libro local hasta el último depth con
`R ≤ t`; los trades con `R ≤ t`; el bookTicker con `R ≤ t`; los features derivados de lo
anterior; las cotizaciones propias emitidas antes de `t`; los fills simulados ya
**resueltos** antes de `t`; el inventario y el PnL realizado hasta `t`; los markouts ya
resueltos (horizonte vencido antes de `t`) y la toxicidad derivada de ellos; el reloj de
latencia (ver §12).

## 4. Información que sólo se conoce después

- Si una orden colocada en `t` **habría sido llenada**: sólo los trades y diffs con
  `R > t + latencia_de_orden` lo dicen.
- El **markout** de un fill (mid a +100 ms … +5 s): sólo tras el horizonte.
- Si una cotización habría sido cancelada a tiempo: sólo tras `t + latencia_de_cancel`.
- La volatilidad "del momento" completa: sólo la ventana pasada está disponible; la
  ventana centrada en `t` no.
- El régimen de un intervalo (spread, flujo) medido con el intervalo completo.

## 5. Cómo se evita el look-ahead

1. **Procesamiento de una sola pasada, ordenado por `R`.** Un solo bucle de eventos
   alimenta features, fair value, cotización, simulador de fills, inventario y PnL.
   Ninguna función recibe la lista completa del tape.
2. **Fills resueltos por eventos posteriores a la llegada.** Una orden decidida en `t`
   "llega" al venue en `t + L_order`; sólo los trades/diffs con `R ≥ t + L_order` cuentan
   para la cola y el fill. El simulador no lee eventos futuros: los recibe cuando llegan.
3. **Markouts en un tracker separado.** Un fill emite una observación pendiente; el
   tracker la resuelve cuando pasan los horizontes. La cotización sólo lee la toxicidad
   agregada de observaciones **ya resueltas**, con retardo por construcción.
4. **Sin retroalimentación del resultado a la señal.** El journal graba la decisión con
   sus features en `t`; el resultado se anexa después como fila separada referida por id.
   Nada reescribe la decisión.
5. **Prueba de prefijo** (misma idea que `tests/property/test_no_lookahead.py`): correr
   la máquina sobre un tape y sobre un prefijo de ese tape; el journal del prefijo debe
   ser prefijo byte a byte del journal completo. Cualquier lectura del futuro rompe esta
   propiedad.
6. **Determinismo**: mismo tape + misma configuración + misma semilla ⇒ mismo hash del
   journal. Sin reloj de pared en `tia/mm` (regla ya vigente en
   `tests/unit/test_scope_boundary.py`).

## 6. Componentes de microestructura que ya existen

En `tia/mm/order_book.py`: `imbalance(n)` = (bid − ask)/(bid + ask) sobre `n` niveles;
`microprice(n)` = (ask·bid_size + bid·ask_size)/(bid_size + ask_size); `mid`, `spread`,
`spread_bps`; `depth(n)`, `depth_notional(n)`, `cumulative_depth(n)`; `weighted_mid(n)`;
`price_impact(qty, side)` (None si el libro visible no absorbe); `liquidity_concentration`.
En `tia/mm/streams.py`: `TradeEvent.aggressor` a partir de `m` (clasificación exacta del
venue, sin inferencia). En `tia/mm/latency.py`: percentiles nearest-rank. En `tia/mm/replay.py`:
reconstrucción determinista. En `tia/economics/costs.py`: `FeeSchedule`, `CostModel`
(round trip, `requires_verification`). En `tia/economics/expected_value.py`: `EdgeEstimator`
(buckets, piso de muestras, pooled backoff, guardia de decaimiento). En
`tia/risk/engine.py`: kill switch, safe mode, breakers diarios/drawdown, `RiskLimits`
congelados. En `tia/portfolio/capital.py`: `CapitalLedger` (halts por pérdida).

## 7. Qué falta

Order Flow Imbalance desde diffs; flujo de trades por ventanas; volatilidad de corto plazo
por tiempo; percentil y régimen de spread; fair value explícito con contribuciones;
adverse selection/markouts; toxicidad; inventario; cotización adaptativa; simulador de
fills con cola estimada y estado UNRESOLVED; modelo de latencia por escenarios; modelo de
costos del maker con descomposición; cuenta paper propia con ledger; guardia de riesgo
del market maker; métricas; replay end-to-end; persistencia propia (tablas `mm_*`); API y
página `/market-maker`; journal explicable; tests (23 obligatorios) y la propiedad de
prefijo sobre el tape.

## 8. Cómo se calculará cada feature (todos sólo con eventos `R ≤ t`)

| Feature | Definición | Registro |
|---|---|---|
| Imbalance | `imbalance(n)` de `LocalOrderBook` para n = 1, 5, 10, 20 | `imbalance_t1/t5/t10/t20` |
| Microprice | fórmula de §6 con n=1 | `mid_price`, `microprice`, `microprice_minus_mid`, `microprice_delta_bps = (microprice − mid)/mid·1e4` |
| OFI | por cada diff, fórmula de Cont–Kukanov–Stoikov sobre el mejor nivel: `e = 1{Pb ≥ Pb'}·qb − 1{Pb ≤ Pb'}·qb' − 1{Pa ≤ Pa'}·qa + 1{Pa ≥ Pa'}·qa'`; además, sobre los `N` mejores niveles, separación de **additions** (Δq > 0) y **cancellations** (Δq < 0 no explicado por trades al mismo precio en el mismo intervalo) por lado; OFI normalizado por la profundidad media de la ventana | `ofi_raw`, `ofi_norm`, `bid_additions`, `bid_cancellations`, `ask_additions`, `ask_cancellations` |
| Trade flow | por ventanas de 1/5/15/30/60 s: `buy_volume`, `sell_volume` (aggressor por `m`), `net_aggressive_volume`, `trade_count`, `avg_trade_size`, `flow_norm = net/(buy+sell)` | por ventana |
| Volatilidad corta | desviación de log-retornos del mid muestreado en cada cambio, por ventana temporal 1/5/15/30/60 s, sólo pasado; anualización no aplica, se reporta en bps por ventana | `vol_1s … vol_60s` |
| Spread | `spread`, `spread_bps`, percentil sobre ventana rodante (30 min), régimen `tight/normal/wide` por percentiles configurables (p25/p75) | `spread_abs`, `spread_bps`, `spread_pct`, `spread_regime` |
| Movimiento reciente | retorno del mid en 1/5/30 s | `ret_1s`, `ret_5s`, `ret_30s` |

Cada feature es una **descripción**, no una señal. Que prediga algo se mide después
(§15) y no se asume.

## 9. Cómo se construirá el fair value

Modelo explícito, lineal en contribuciones, con **pesos configurables** y por defecto
conservadores; nunca un ajuste automático sobre los mismos datos que luego se evalúan:

```
fv = mid
   + w_micro · (microprice − mid)
   + w_imb   · imbalance_t5 · half_spread
   + w_ofi   · ofi_norm      · half_spread
   + w_flow  · flow_norm_5s  · half_spread
   + w_mom   · ret_5s        · mid
fair_value_offset_bps = (fv − mid)/mid · 1e4
```

`fair_value_confidence ∈ [0, 1]` decrece con: edad del dato, régimen de spread `wide`,
`vol_5s` alta, libro no usable, desacuerdo entre componentes (signos opuestos). Se registra
`components = {micro, imb, ofi, flow, mom}` con la contribución de cada uno en bps. Los
pesos por defecto: `w_micro = 1.0`, el resto `0.0` (fair value = microprice), porque es el
único componente con respaldo empírico general; los demás son **hipótesis** que se activan
por configuración y se evalúan por su markout (§15). Fair value es una estimación
condicionada; el código lo llama `estimate` y nunca `prediction`.

## 10. Cómo se simularán los fills

Sin L3 no hay posición de cola exacta; el simulador es **de cotas**, no de puntos:

1. Una cotización decidida en `t` se convierte en orden simulada que **llega** en
   `t_arr = t + L_order`. El estado del libro que la recibe es el de `t_arr` (eventos
   posteriores a la decisión, sin mirar más allá).
2. Al llegar a precio `p`: `queue_ahead_conservative = qty visible en p` (todo lo que había
   está delante); `queue_ahead_optimistic = qty visible en p` también al inicio.
3. Después, por cada evento con `R ≥ t_arr`:
   - **Trade** a `p` en el lado correcto (para nuestro bid: aggressor `sell` a precio
     `≤ p`): consume cola por delante en ambas cotas; el exceso sobre la cola llena
     nuestra orden (parciales por volumen real).
   - **Trade a precio peor que `p` para el agresor** (el precio atraviesa nuestro nivel):
     todo lo que había en `p` fue tomado ⇒ fill de lo que reste, confirmado.
   - **Diff que reduce `p` sin trades equivalentes** (cancelaciones): la cota optimista
     asume que estaban delante (cola baja); la conservadora asume que estaban detrás
     (cola igual).
   - **Diff que aumenta `p`**: llegan detrás de nosotros; no cambia la cola.
4. Clasificación: **FILLED** si el volumen agredido a través de `p` supera la cola
   conservadora; **UNRESOLVED** si supera sólo la optimista; **NONE** si ninguna. Los
   UNRESOLVED **se contabilizan aparte y se excluyen del PnL**; se reporta su número y el
   PnL que tendrían bajo cada cota, para que la incertidumbre sea visible y no favorable.
5. Nunca por `high ≥ price` ni `low ≤ price`; nunca por velas; nunca por bookTicker.
6. Cada fill lleva `venue_trade_ids` (los trades reales que lo produjeron),
   `queue_ahead_at_arrival`, `estimated_queue_position` (cota conservadora) y
   `resolution ∈ {filled, partial, unresolved, none, cancelled}`.
7. Cancelaciones propias: efectivas en `t + L_cancel`; un trade que llega antes de esa
   efectividad puede llenar la orden (riesgo real de cancel tardío).
8. El simulador **no** mueve el mercado (nuestras órdenes no cambian el libro real
   grabado). Se documenta como límite; el sizing se acota a una fracción del volumen al
   nivel para no depender de ello.

## 11. Cómo se modelarán los fees

`maker_fee_bps = 10.0` (PROVISIONAL_COST_ASSUMPTION, `TIA_MM__MAKER_FEE_BPS`), evaluado
en paralelo con el escenario adverso (15 bps) y el verificado (None hasta leerlo de la
cuenta). No se asume ninguna comisión menor. Cada fill simulado paga `fee = notional ·
maker_fee_bps/1e4`; un unwind de inventario por market order simulada paga taker (se
configura, default 10 bps) más impacto por `price_impact(qty)` del libro real. Descomposición
por fill y agregada: `gross_pnl`, `fees`, `adverse_selection_cost` (markout adverso
realizado a 1 s, atribuible al fill), `slippage_cost` (unwinds), `net_pnl`. Ninguna cifra
neta se muestra sin su bruto y sus costos al lado.

## 12. Cómo se modelará la latencia

Un `LatencyProfile` con cinco componentes, en ms, **derivado de las mediciones reales de
la Fase 2**: `data_latency` (exchange→local, medido), `processing_latency` (medido en µs),
`decision_latency` (medido en el motor por evento), `simulated_order_latency` y
`cancel_latency` (no medibles sin enviar órdenes: se estiman como el mismo camino de red
que la data, usando los percentiles observados). Escenarios:

| Escenario | order/cancel latency | data latency usada |
|---|---|---|
| optimistic | `p50` observado de depth | p50 |
| baseline (default) | `p95` observado de depth | p95 |
| conservative | `p99` observado de depth × 2 | p99 |

Piso absoluto de 5 ms en todo escenario: **latencia cero está prohibida** y el test lo
verifica. Las cifras se cargan de `data/mm/latency_profile.json`, que
`scripts/mm_market_data_check.py` escribirá con `--write-latency-profile` a partir de una
corrida real; hasta que ese archivo exista con cifras del VPS, el motor de replay **se
niega a correr** con un perfil por defecto. Cada fill registra las latencias aplicadas.

## 13. Cómo se modelará la adverse selection

`AdverseSelectionEngine`: por cada fill resuelto, markout a +100, +250, +500 ms, +1, +2,
+5 s: `markout_h = side · (mid(t_fill + h) − fill_price)/fill_price · 1e4` (bps). Adverso si
< 0. Se registra `post_fill_markout`, `adverse_markout`, `favorable_markout`,
`fill_to_mid_movement`. `ToxicityEngine`: agregado rodante (ventana y decaimiento
configurables) del markout adverso a 1 s por bucket `{side, spread_regime,
imbalance_regime, vol_regime, flow_regime}` ⇒ `toxicity_score ∈ [0, 1]`. Sólo usa
observaciones **resueltas**; sólo puede **ampliar** el spread objetivo, reducir tamaño o
pausar; nunca estrecha ni aumenta tamaño. Nunca se usa para decidir si el fill original
habría ocurrido.

## 14. Cómo se medirá el PnL

Cuenta paper propia (`MM_PAPER_EQUITY = 10.000`, alias de `TIA_MM__PAPER_CAPITAL`),
`CapitalLedger` propio, `PaperExecutionProvider` **no** reutilizado (su modelo es por
velas; el simulador de §10 es por tape). Contabilidad: inventario en BTC con costo
promedio; realizado al reducir inventario (FIFO por costo promedio); no realizado
marcado al **mid** (y también al lado conservador: bid para long, ask para short,
reportado aparte). Equity = cash + inventario·mark. Series: por fill, por cotización, por
minuto, por régimen. Drawdown sobre equity marcada al conservador. Persistencia en
tablas nuevas `mm_quotes`, `mm_fills`, `mm_markouts`, `mm_ledger`, `mm_journal`
(migración 0006). **Nunca** en `edge_outcomes`, así `track_record()` y las 27
verificaciones no ven nada del market maker.

## 15. Cómo se determinará si existe edge

Nunca por `paper_pnl > 0`. Se declara **edge encontrado** sólo si, en datos que **no** se
usaron para elegir parámetros (OOS por tiempo: días distintos, con el orden
TRAIN → VALIDATION → OOS fijado antes de correr):

1. `n_fills_confirmed ≥ 300` y presencia en ≥ 3 regímenes de spread y ≥ 3 de volatilidad;
2. `net_pnl_per_fill` con intervalo de confianza 95 % (bootstrap por bloques de tiempo)
   **enteramente positivo** bajo escenario `baseline` y fees asumidos;
3. `net_pnl` no negativo bajo el escenario `conservative` **y** bajo fees adversos;
4. markout adverso a 1 s no dominante (adverse_selection_cost < gross spread capture);
5. resultado estable: ningún régimen con contribución > 60 % del neto;
6. UNRESOLVED ≤ 10 % de los fills candidatos; si son más, el resultado es "no
   determinable", no "positivo".

Si falla cualquiera: **"edge no encontrado bajo estas condiciones"**, sin ajustar
parámetros para volver a correr sobre los mismos datos. Un cambio de parámetros abre una
nueva partición temporal.

Historial disponible hoy: decenas de minutos. **No hay muestra para OOS.** Se dice
explícitamente y se propone la decisión D2 (§17): grabar ticks de forma continua desde ya.

## 16. Métricas para aceptar o rechazar

`total_quotes`, `fills`, `partial_fills`, `rejected_fills`, `unresolved_fills`,
`gross_spread_capture`, `gross_pnl`, `fees`, `adverse_selection`, `slippage`, `net_pnl`,
`pnl_per_fill`, `pnl_per_quote`, `fill_ratio`, `cancel_ratio`, `inventory_utilization`,
`inventory_duration`, `max_inventory`, `drawdown`, `sharpe`/`sortino` sólo si `n ≥ 300` y
se reporta el error estándar, `markout_100ms … markout_5s`; todo separado por
`vol_regime`, `spread_regime`, `imbalance_regime`, `flow_regime`, `inventory_bucket`,
`side`, y por escenario de latencia y de fees.

---

## 17. Inconsistencia arquitectónica y decisiones que requieren confirmación

### D1 — Autoridad del `RiskEngine` existente sobre un proceso de cotización continua (RESUELTA)

`RiskEngine.evaluate(signal: SignalCandidate, portfolio, …)` está diseñado para una
decisión direccional por vela de 1 minuto: exige un `SignalCandidate`, aplica
`trade_cooldown_seconds = 300`, `max_trades_per_day = 20` y `max_trades_per_symbol_per_day
= 5`. Un market maker emite cientos de cotizaciones por hora y mantiene inventario, no
"trades". Pasar cada cotización por `evaluate` la rechazaría por frecuencia; cambiar esos
límites para el market maker sería exactamente lo prohibido.

**Arquitectura confirmada por el operador** (sin segundo `RiskEngine`, sin autoridades
paralelas):

1. `tia/risk/engine.py` **no se modifica**. El `RiskEngine` existente sigue siendo la
   autoridad de riesgo del sistema existente.
2. `tia/mm/safety.py::GlobalTradingSafetyGate`: **solo lectura**. Expone un estado
   `SAFE | SAFE_MODE | HALTED | DATA_INVALID | SYSTEM_UNSAFE` a partir del estado del
   `RiskEngine` de la sesión (kill switch, safe mode, halted), de la validez de los datos
   (`MarketDataService.usable`) y de la salud del sistema. No escribe nada en ningún
   motor. Si el estado no es `SAFE`: se cancelan las cotizaciones paper activas, no se
   generan nuevas, se registra el motivo y se espera la recuperación.
3. `tia/mm/risk.py::MarketMakerRiskController`: límites propios de la cuenta paper de
   $10.000 (inventario, notional, tamaño de cotización, pérdida diaria, drawdown,
   frecuencia de cotización, kill switch propio). **Solo puede restringir**; no tiene
   ninguna API para relajar un límite global ni para resumir nada del sistema existente.
4. Jerarquía, en este orden y nunca al revés, codificada en `MarketMakerEngine`:

```
DATA VALIDITY  →  GLOBAL SAFETY GATE  →  MARKET MAKER RISK CONTROLLER  →  QUOTING ENGINE  →  PAPER EXECUTION
```

   No existe camino en el que "el controller dice OK" pueda ignorar una condición de
   seguridad global: el motor consulta el gate antes que el controller y el controller no
   recibe el resultado del gate como entrada que pueda anular.

### D2 — Grabación continua desde hoy (datos para replay/OOS)

Sin días de ticks no hay TRAIN/VALIDATION/OOS. Propuesta: poner `TIA_MM__ENABLED=true`
en el `.env` del VPS **ahora** (sólo arranca el servicio de datos de la Fase 2 y graba a
`/app/data/runtime/ticks`; no cotiza nada), subir `TIA_MM__TICKS_MAX_GB` según el
crecimiento medido en el VPS (`ticks_dir_growth_mb_per_hour` del reporte de Fase 2) y
`TIA_MM__TICKS_RETENTION_DAYS` a 30. Cada día grabado es un día de evidencia potencial.

### D3 — Perfil de latencia real

El motor exige `data/mm/latency_profile.json` con las cifras del VPS. Propuesta: agregar
`--write-latency-profile` al script de la Fase 2, correrlo 5 minutos en el VPS y **subir el
archivo al repositorio** (es un dato, no un secreto). Sin ese archivo, el replay no corre
con supuestos por defecto.

### D4 — Banderas

`TIA_MM__ENABLED` = datos de mercado + grabación (ya existe). Nueva
`TIA_MM__ADAPTIVE_ENABLED` (= `ADAPTIVE_MARKET_MAKER_ENABLED`, default `false`) = cotización
**paper**. `TIA_MM__REAL_MONEY` (= `ADAPTIVE_MARKET_MAKER_REAL_MONEY`) sigue sin efecto en
ningún camino de código; el runtime del market maker acepta únicamente su simulador
interno y lanza si recibe un `ExecutionProvider` con `is_live`. Los nombres largos se
aceptan como alias en compose.

---

## 18. Diseño técnico (módulos, todos en `tia/mm/`, camino de decisión, sin reloj de pared)

| Módulo | Entrada | Salida | Tests obligatorios cubiertos |
|---|---|---|---|
| `features.py` | `LocalOrderBook`, `DepthUpdate`, `TradeEvent`, `t` | `FeatureVector` (§8) | 1 imbalance, 2 microprice, 3 OFI, 4 clasificación de trades |
| `fair_value.py` | `FeatureVector`, `FairValueConfig` | `FairValueEstimate(fv, confidence, offset_bps, components)` | 5 |
| `adverse_selection.py` | fills resueltos + stream de mid | `Markout` por horizonte, pendientes/resueltos | 9 |
| `toxicity.py` | markouts resueltos | `toxicity_score` por bucket | 8 |
| `inventory.py` | inventario, límites | `inventory_ratio`, `pressure`, `adjustment_bps` | 6, 16 |
| `spread.py` | vol, spread, toxicidad, costos | `spread_target_bps` | 7 |
| `quoting.py` | fv, features, inventario, toxicidad, latencia, costos, guardia | `QuoteDecision(bid, ask, size, spread_target, confidence, reason)` o `NO_QUOTE(reason)` | 5–8, 17 |
| `latency_model.py` | `latency_profile.json`, escenario | `LatencyProfile` | 11 |
| `costs.py` (mm) | fee scenarios, impacto | descomposición §11 | 12 |
| `queue.py` | libro en `t_arr`, trades, diffs | cotas de cola, resolución | 10 |
| `sim.py` | `QuoteDecision`, tape | `SimulatedOrder`, `SimulatedFill(resolution, venue_trade_ids)` | 13, 14, 15 |
| `ledger.py` | fills, marks | inventario, PnL bruto/neto, drawdown | 6, 16, 22 |
| `safety.py` | estado del `RiskEngine` de sesión (lectura), validez de datos, salud | `SafetyStatus(SAFE/SAFE_MODE/HALTED/DATA_INVALID/SYSTEM_UNSAFE, reason)` | 17, 23 |
| `risk.py` | `MarketMakerRiskLimits`, estado del ledger propio | `allow/deny(reason)`, tamaño acotado, kill switch propio; sólo restringe | 16, 17, 23 |
| `engine.py` | eventos en orden `R` | journal, métricas, snapshot | 18, 19, 20, 21 |
| `mm_replay.py` | segmentos + config + semilla | resultado determinista, hash del journal | 18, 19 |
| `metrics.py` | journal | §16 por régimen/escenario | — |
| `persistence` | migración 0006, tablas `mm_*`, `MarketMakerRepository` | reinicio con estado | 22 |
| `api`/`frontend` | `/api/mm/state`, `/api/mm/journal`, eventos `mm.*`; vista `MarketMaker.tsx` (`/market-maker`) | observabilidad | — |

Seguridad estructural (tests 20 y 21): `tia/mm` no importa `tia/execution/binance*` ni
ningún proveedor con `is_live`; el `MarketMakerEngine` lanza si `settings.mm.real_money`
cambia algo (no cambia nada); `test_scope_boundary` extiende la lista de importaciones
prohibidas al paquete `mm`; ningún módulo de `mm` recibe `LiveActivationToken`.

## 19. Orden de implementación (un commit auditable por etapa, con tests y reporte)

1. Audit (este documento). 2. Confirmación de D1–D4. 3. Tests de datos: propiedad de
prefijo sobre el tape y determinismo del replay del libro. 4. `features.py`. 5.
`fair_value.py`. 6. `adverse_selection.py` + `toxicity.py`. 7. `inventory.py` + `spread.py`.
8. `quoting.py` + `risk.py`. 9. `latency_model.py` + `queue.py` + `sim.py` + `costs.py` +
`ledger.py`. 10. `engine.py` + `mm_replay.py`. 11. `metrics.py` + persistencia. 12. API +
`/market-maker`. 13. Live paper mode (`TIA_MM__ADAPTIVE_ENABLED=true`, sólo paper). 14.
Evaluación estadística sobre los ticks grabados, con la regla de §15.

## 20. Confirmaciones

No se modificó ningún archivo de código en esta etapa. Las 27 verificaciones, el
`RiskEngine`, las estrategias, la cuenta paper existente, la sesión 24/7, la ejecución real
y el `LiveActivationToken` no se tocan en el diseño. `TIA_MM__ENABLED=false` y
`TIA_MM__REAL_MONEY=false` siguen siendo los valores por defecto del repositorio.

---

## 21. Estado de implementación (2026-09-18) — PHASE3_STATUS = IMPLEMENTATION

Doce etapas, un commit auditable cada una, en el orden del §19. Ningún commit toca
`tia/risk/engine.py`, `tia/live/gate.py`, las estrategias, la cuenta paper existente ni la
sesión 24/7.

| Etapa | Commit | Qué | Tests |
|---|---|---|---|
| 1 Decisiones | `23262d0` | Banderas separadas con alias; perfil de latencia medido (`--write-latency-profile`), cargador que se niega sin medición; la imagen conoce su commit | 4 |
| 2 Tests de datos | `36208b4` | Determinismo, invariancia de prefijo, suficiencia de checkpoints; orden de llegada verificado en el replay | 4 propiedad |
| 3 Features | `8bf98f2` | Imbalance 1/5/10/20, microprice, OFI con adiciones/cancelaciones separadas de trades, flujo por ventanas, volatilidad corta, spread con percentil y régimen, retornos | 8 |
| 4 Fair value | `1e8cb8c` | Estimación explícita con contribuciones nombradas, confianza que sólo baja, sin ajuste | 5 |
| 5 Adverse selection | `9e4c2a8` | Markouts resueltos sólo por mids posteriores (tolerancia, vencidos = no resueltos); toxicidad que sólo amplía o reduce tamaño | 6 |
| 6 Inventario y spread | `a31b40d` | Skew contra la posición, tamaño del mismo lado a cero en el límite; spread = piso de costos / volatilidad / mercado + toxicidad | 5 |
| 7 Gate, controller, quoting | `240a6d5` | Gate global de solo lectura; controller propio que sólo restringe (kill switch propio); cotización en grilla de tick, nunca cruzada | 7 |
| 8 Ejecución paper | `7582ad0` | Cola por cotas (conservadora/optimista), fills sólo por prints reales, UNRESOLVED nunca contabilizado, latencias de orden y cancel, taker rechazado; costos itemizados; ledger propio | 9 |
| 9 Motor y replay | `0d5e405` | Jerarquía DATA → GATE → CONTROLLER → QUOTING → EXECUTION en código; journal con hash; replay determinista que nombra su perfil | 7 |
| 10 Métricas y persistencia | `ecb2c89` | Métricas §16 por régimen/escenario, bootstrap por bloques, veredicto que por defecto es NO EDGE DETECTED; tablas `mm_journal`, `mm_fills`, `mm_ledger` (migración 0006) | 3 |
| 11 API y página | `016e26f` | `/api/mm/state`, `/api/mm/journal`, `/api/mm/metrics` (solo lectura); página `/market-maker` | 1 + smoke |
| 12 Live paper mode | este commit | `MarketMakerService` sobre el feed real; el consumidor recibe el libro actual al suscribirse; persistencia propia, reanudación del ledger, pushes `mm.state`/`mm.journal`; arranque sólo con datos de mercado **y** perfil medido | 3 |

Verificación completa del repositorio tras la etapa 12: **9/9**.

### 21.1 Cómo se activa el paper real en el VPS (nada de esto envía órdenes)

```
cd /home/tia/Trader-IA
git pull origin claude/algo-trading-simulation-platform-ngf7xo

# D2: grabación continua (datos de mercado; no cotiza)
#   en .env:  TIA_MM__ENABLED=true   TIA_MM__ADAPTIVE_ENABLED=false
GIT_COMMIT=$(git rev-parse --short HEAD) docker compose -f docker-compose.prod.yml up -d --build backend

# D3: perfil de latencia medido en este host, 5 minutos, escrito al volumen
docker compose -f docker-compose.prod.yml exec backend python scripts/mm_market_data_check.py --minutes 5 --ticks-dir /app/data/runtime/ticks-profile --write-latency-profile /app/data/runtime/mm/latency_profile.json
docker compose -f docker-compose.prod.yml cp backend:/app/data/runtime/mm/latency_profile.json data/mm/latency_profile.json
git add data/mm/latency_profile.json && git commit -m "Latency profile measured on the VPS" && git push origin claude/algo-trading-simulation-platform-ngf7xo

# Paper quoting (simulado): sólo cuando lo anterior existe
#   en .env:  TIA_MM__ADAPTIVE_ENABLED=true   (TIA_MM__REAL_MONEY queda fijado en "false" en compose y no tiene efecto)
docker compose -f docker-compose.prod.yml up -d backend
docker compose -f docker-compose.prod.yml logs backend | grep -E "mm_paper_running|mm_paper_not_started"
```

Sin `TIA_MM__ENABLED=true` o sin el perfil, el servicio **no arranca** y `/api/mm/state`
dice por qué. Con ambos, `/market-maker` muestra `PAPER_RUNNING` y
`EVIDENCE_PENDING`. El ledger del maker se guarda cada 10 s y al cierre en `mm_ledger`
y se reanuda al reiniciar si la configuración (`config_id`) no cambió.

### 21.2 Límites conocidos de esta implementación

- Las órdenes simuladas no mueven el libro real ni consumen liquidez del libro grabado;
  el tamaño base (0,005 BTC) se eligió para que esa aproximación sea defendible.
- La cola se modela por cotas; el informe muestra `unresolved` aparte y el veredicto
  exige que sea ≤ 10 %.
- La latencia de orden y cancel se deriva del camino de red medido para los datos
  (nunca cero); las dos latencias del pipeline se miden desde ahora en el motor
  (`processing_us`) y se incorporarán al perfil cuando existan corridas reales.
- No hay historial suficiente para TRAIN/VALIDATION/OOS; el veredicto seguirá siendo
  NO EDGE DETECTED hasta que lo haya, y no se ajustará ningún parámetro para cambiarlo.
- El estado pasa a PAPER_RUNNING cuando el operador activa la bandera en el VPS; hasta
  entonces es IMPLEMENTATION. PROFITABLE no es un estado de este sistema.

---

## 22. Objetivo final del proyecto y límites (fijado por el operador, 2026-09-18)

**Durante toda la Fase 3 el market maker opera exclusivamente en simulación**, 24/7,
sobre datos reales de Binance, con una cuenta paper propia de **$10.000 USD**, y todo el
proceso simulado de la forma más realista posible: órdenes simuladas, fills simulados
sólo por trades reales, cola estimada, latencia medida, fees, spread, slippage, adverse
selection, inventario, drawdown, PnL, riesgo y todas las métricas necesarias. Debe
comportarse como si administrara $10.000 reales, **sin usar dinero real**.

**Ahora**: `TIA_MM__REAL_MONEY=false`; sin colocación de órdenes en Binance; sin
permisos de trading en la API; sin órdenes reales; sin workaround; sin endpoint
alternativo; sin código que pueda mandar una orden real. "Querer dinero real en el
futuro" **no** es permiso para implementar ejecución real ahora.

**Fase 4 (futura, independiente, no autorizada todavía)**: si tras suficiente tiempo y
con evaluación TRAIN / VALIDATION / OOS el sistema demuestra una ventaja estadística
consistente, la arquitectura debe permitir pasar de
`DATA → QUOTING → PAPER EXECUTION` a `DATA → QUOTING → REAL EXECUTION` sin reconstruir
el market maker, y **solamente** después de una auditoría específica de ejecución real:
permisos, límites, reconciliación de órdenes, fills, cancelaciones, fallos de red,
duplicados, posiciones reales, balances y kill switch.

### 22.1 Qué significa "funciona"

No funciona porque el PnL paper sea positivo, porque hubo unas pocas operaciones
ganadoras, porque una semana fue positiva ni porque el backtest dio ganancias. Se exige
evidencia de que el resultado sobre los $10.000 simulados **no proviene de** lookahead,
fills demasiado optimistas, cola instantánea, latencia cero, UNRESOLVED
convenientemente excluidos, fees incorrectas, slippage inexistente, parámetros
sobreoptimizados, un único régimen de mercado ni sobreajuste al histórico. Cómo lo
cubre la implementación actual, y dónde no llega:

| Riesgo | Mecanismo |
|---|---|
| lookahead | una sola pasada por tiempo de recepción; fills resueltos por eventos posteriores a la llegada; markouts en tracker separado; propiedad de prefijo y determinismo por hash (tests) |
| fills optimistas | fill sólo cuando prints reales superan la cota **conservadora** de cola; nunca por vela, tope de libro ni "tocó el precio" |
| cola instantánea | la cola al llegar es la cantidad visible al precio en ese instante; se registra por fill (`queue_ahead_at_arrival`) |
| latencia cero | perfil medido en el VPS y versionado; piso de 5 ms; el replay y el paper se niegan sin perfil |
| UNRESOLVED excluidos | se contabilizan aparte, se journalizan con contexto y reciben markout sombra; la auditoría compara su distribución con la de los fills confirmados; 10 % es cobertura, no realismo |
| fees | 10 bps maker como supuesto provisional, escenario adverso 15 bps, tasa verificada sólo cuando se lea de la cuenta |
| slippage | **sólo** modelado para unwinds por taker; hoy el maker no fuerza unwinds, así que el slippage registrado es cero por construcción, no por supuesto favorable: queda declarado como límite |
| liquidación | la cuenta del maker es de contado, sin apalancamiento: la liquidación **no puede ocurrir por construcción**; los límites del controller (inventario 0,05 BTC, notional $6.000, pérdida diaria $100, drawdown 3 %) acotan la exposición muy por debajo del capital; si se quisiera una cuenta apalancada con liquidación, es una decisión de diseño separada |
| sobreoptimización | ningún parámetro se ajusta al resultado; un cambio de parámetros abre una partición temporal nueva |
| único régimen | regla de concentración por régimen en el veredicto |
| sobreajuste | veredicto sólo fuera de muestra por tiempo, con intervalo bootstrap |

### 22.2 Estados

El sistema conserva **PAPER_RUNNING + EVIDENCE_PENDING + NO EDGE DETECTED** hasta que
exista evidencia suficiente. `PROFITABLE` no es un estado del sistema. Resultados
negativos, estables o ambiguos se reportan exactamente así; un resultado positivo debe
demostrar primero que sobrevive a fees, latencia, adverse selection, fills realistas y
OOS.

### 22.3 La costura para la Fase 4 (sin implementarla)

La etapa de ejecución del motor es un objeto con una superficie estrecha:
`place(decision, t)`, `cancel(order_id, t, reason)`, `cancel_all(t, reason)`,
`on_event(kind, event, book, t)`, `open_orders()`, `orders`, `last_unresolved`,
`stats()`. Hoy sólo existe la implementación paper (`tia/mm/sim.py`) y el motor no
acepta otra. Una Fase 4 definiría un protocolo en esa costura, con su propia auditoría
(§22) y su propio gate, sin tocar las etapas de datos, features, fair value, riesgo ni
cotización. Nada de eso se implementa en la Fase 3.

### 22.4 Regla HOLD (decisión del operador, 2026-09-18)

Cuando el controller niega **únicamente** por tasa máxima de cotización o por intervalo
mínimo entre cotizaciones (`RiskAllowance.hold_only`), una cotización que ya descansa en
el libro paper **no se cancela automáticamente**: el motor recalcula la cotización
deseada como si el ritmo lo permitiera y, si sigue dentro del umbral de recotización
(0,5 bps), la mantiene (`decision = hold`, con el motivo en el journal). Si el fair value,
el inventario, la toxicidad, el spread requerido o los permisos por lado la obligan a
moverse, se cancela normalmente y **no se reemplaza** hasta que el ritmo lo permita. El
gate global y toda negativa dura (kill switch, pérdida diaria, drawdown, inventario,
notional) siguen cancelando. El TTL de la cotización (1 s) y la reevaluación cada 500 ms
no cambian; un HOLD nunca extiende una orden más allá de su TTL. Ningún límite de ritmo
se aumentó ni se redujo ninguna protección. Tests en `tests/unit/mm/test_hold.py`.

### 22.5 Modelo de tiempo del tape y perfil de latencia del VPS (2026-09-18)

**Tres tiempos, nunca confundidos.** `R` es el tiempo de recepción local (el único "ahora"
del sistema); `E` es el event time del exchange (sólo en depth y trade; el `bookTicker` de
Spot no lo trae y no se le inventa); `T` es el trade time del venue. El orden de
procesamiento es el **orden físico de llegada**, que el recorder preserva por construcción
(un solo hilo, despacho síncrono, líneas anexadas en orden de llamada). `R` es un atributo
de cada línea, no la clave de orden.

**Regla determinista para `R`.** (1) Los eventos se estampan con un reloj de recepción
anclado una sola vez al reloj monotónico (`ReceiveClock`): dos estampas consecutivas del
mismo proceso nunca retroceden, aunque el reloj de pared salte por NTP; el costo, que se
declara y no se corrige en silencio, es que tras un salto `R` y la latencia exchange→local
quedan desplazadas por ese salto. (2) Las líneas sintéticas (snapshot REST, checkpoints)
no "llegan": llevan el `R` de su lugar en la cinta — el checkpoint de cierre el del último
evento, el de apertura el del evento que provocó el cambio de hora — y se estampan con el
mismo reloj que los eventos. (3) Los empates de `R` se resuelven por orden de archivo. (4)
El replay exige `R` no decreciente; cualquier regresión falla el replay y se clasifica
(secuencia del venue avanza: artefacto de estampa; retrocede: cinta desordenada), con las
dos líneas involucradas en el reporte. Nada de esto introduce lookahead: ningún dato
posterior decide el orden.

**Causa de la regresión del segmento `20260918-22`.** El checkpoint que abre cada archivo
horario se estampaba con el reloj de pared al momento de escribirse, mientras que el
evento que provocó el cambio de hora llevaba su `R` de llegada, anterior en ≥ 1 ms. Una
inversión por archivo de cambio de hora, en su primera línea; corregida por la regla (2).
Los 12 eventos de diferencia entre `events_written` (21.880) y las líneas de los
manifiestos (21.892) son el buffer aún no volcado en el instante en que el reporte tomó el
estado (≤ 1 s de eventos) más el checkpoint de cierre escrito al cerrar; sin pérdida ni
duplicación (los manifiestos y el checksum describen el archivo completo). El reporte
ahora toma el estado final del recorder y muestra la conciliación explícita.

**Perfil de latencia del VPS (provisional, utilizable).** exchange→local depth p50 117 /
p95 118 / p99 120 ms; trade p50 121 / p95 136 / p99 163 ms; procesamiento local p99 1,405 ms
con **máximo 161,902 ms identificado como outlier** (no es latencia típica y no se usa como
tal). `bookTicker` no se usa como fuente de latencia exchange→local. Los escenarios derivan
la latencia de orden y cancelación del camino depth (p50 / p95 / 2×p99).
