# Trader-IA — Fase 1.3 (bloque 2): hardening técnico, costos, risk sizing y paridad del backtester

Informe de cierre del segundo bloque de la Fase 1.3. Sin commits, sin push, sin despliegues, sin reinicios
de servicios, contenedores, procesos ni VPS, sin órdenes a ningún exchange, sin credenciales leídas,
mostradas ni almacenadas, sin acceso al holdout reservado ni a su libro, sin simulaciones extensas ni
paper runs prolongados. Todo lo afirmado sobre pruebas tiene un comando y un resultado en §7; lo no
ejecutado está en §8 con su motivo. **Nada de lo descrito aquí está desplegado**: el código corregido vive
únicamente en el working tree local de la rama `claude/algo-trading-simulation-platform-ngf7xo`, y no se
afirma nada sobre el código que corre en el VPS.

Convención de lectura. Cada sección separa **hechos** (lo que el código, un comando o una prueba muestran),
**inferencias** (lo que se deduce de esos hechos) y **recomendaciones** (decisiones que corresponden al
usuario). Estados usados en §3: **Confirmado y corregido**, **Confirmado y pendiente**, **No
reproducible**, **No aplicable**, **Bloqueado por falta de evidencia**. Un estado "corregido" exige una
prueba de regresión que falla en el árbol previo al bloque y pasa en el actual; la existencia de una
función, un comentario o una configuración no cuenta como corrección.

---

## 1. Estado inicial

**Hechos.** El bloque arrancó sobre el working tree que dejó el bloque anterior de la Fase 1.3 (informe
`docs/PHASE_1_3_HARDENING_REPORT.md`), preservado íntegro: antes de tocar nada se capturó `git status`,
el `git diff` completo y una copia byte a byte de los 70 archivos modificados o no rastreados
(`scratchpad/phase13b/tree_start`, 70 archivos), y al final se comprobó que ninguno de ellos cambió salvo
los que este bloque declara propios (§9).

| | Inicio del bloque (2026-10-11T10:33:28Z) |
|---|---|
| Rama | `claude/algo-trading-simulation-platform-ngf7xo` |
| HEAD | `ab68d1c128a7181f54e1e79d3d7f37261365d821` |
| `git status --porcelain` | 70 líneas: 21 M + 49 ?? (Fases 1, 1.1, 1.2 y el bloque anterior de 1.3, sin commit) |
| Huella del `git diff` (sha256/16) | `30aaf2f001e4baca` |
| Huella del conjunto de no rastreados | `3ecafc502ce9d7d7` |
| `git diff --stat` | 21 files changed, 2711 insertions(+), 272 deletions(-) |
| `git stash list` | vacío |
| Suites al inicio (cierre del bloque anterior) | lint limpio; unit 1346; integration 274; property 31; failure 12; adversarial 16; e2e 8 — todas en verde |

El estado de los hallazgos F1–F16 al inicio era el que dejó la Fase 1.2: F1–F5, F7 y F8 **RESUELTOS**
(F5 solo dentro de un proceso), F6 **NO ABORDADO** por mandato, F9–F16 **abiertos** (el informe de 1.2,
§6, los lista como no abordados por prioridad). El bloque anterior de 1.3 cerró además G1–G13 y dejó
tres pendientes explícitos que este bloque toma: los multiplicadores del presupuesto de riesgo eran
**inertes** para el tamaño, la paridad backtester–sesión en salidas no se había abordado, y F6/G10 en
live seguía PARCIAL.

---

## 2. Cambios, archivo por archivo

Las cifras son la diferencia de líneas de **este bloque** (contra la copia de inicio o contra HEAD cuando el
archivo estaba limpio al inicio), no la diferencia acumulada contra HEAD.

| Archivo | Δ bloque | Qué cambió |
|---|---|---|
| `packages/tia/src/tia/risk/sizing.py` | +211 / −1 | **Contrato único de sizing** `apply_risk_budget` → `BudgetedSize` (§5): riesgo permitido, cantidad, redondeo hacia abajo, rechazos con motivo, guarda interna que lanza `RiskError` si el efectivo supera el permitido. |
| `packages/tia/src/tia/runtime/live.py` | +155 / −23 | Sizing vía el contrato (antes el presupuesto solo se leía como permitir/no permitir); F9 detección de cierre por deadline no ejecutado en tiempo de pared; F14 rechazo del venue no consume presupuesto diario (`orders_rejected`); F16 comparación de posición en `_reconcile`; G15 nada se coloca sobre un cierre en vuelo; EV con `direction`, `funding_rate`/`funding_periods` (carry) y contador `funding.ev_carry_unpriced`. |
| `packages/tia/src/tia/runtime/engine.py` | +39 / −0 | El motor de escenarios aplica el mismo contrato de sizing antes de enviar (`Counters.sized_down`, rechazos a `budget_rejected`). |
| `packages/tia/src/tia/backtest/engine.py` | +417 / −30 | **Paridad con la sesión** (§6): presupuesto de riesgo, EV (observa por defecto), convicción, contrato de sizing, salidas por objetivo/time stop/reversión vía una sola ruta (`_request_exit`: stop cancelado primero, un cierre reduce-only, nada más mientras trabaja), break-even y trailing con `execution/exits.tighten_stop`, entradas limit con regla de "atraviesa el límite" y timeout, estimador alimentado con round trips cerrados (bruto + fees), funnel por etapa en el log de decisiones, spread del EV como el que el simulador realiza. Campos de `BacktestConfig` con los mismos nombres y valores por defecto que `LiveConfig`. |
| `packages/tia/src/tia/backtest/result.py` | +21 / −0 | `DecisionRecord`: `stage`, `reason`, `ev_net_bps`, `ev_tradeable`, `budget_multiplier`, `sized_quantity`. `DecisionCounts`: `budget_rejected`, `ev_would_reject`, `ev_no_evidence`, `ev_rejected`, `filter_rejected`, `sized_down`, `entries_skipped_resting`, `stops_tightened`, `exits_requested`. |
| `packages/tia/src/tia/economics/costs.py` | +91 / −7 | **Una semántica de costos** (§4): `TradeCosts` itemiza fee de entrada y de salida con su liquidez, `funding_bps`, `borrow_bps`, `funding_known`; propiedades `execution_bps`, `carry_bps`, `complete`; `CostModel.estimate` acepta `direction`, `funding_rate`, `funding_periods`, `borrow_rate_bps_per_day`, `holding_days`; `FUNDING_PERIOD_SECONDS`. |
| `packages/tia/src/tia/economics/expected_value.py` | +13 / −3 | `is_tradeable` exige `costs.complete`; `explain()` dice cuando la estimación está incompleta. |
| `packages/tia/src/tia/risk/restore.py` | +28 / −1 | F10: filas fechadas después de `now` (más de 60 s) dejan la reconstrucción **incompleta** en vez de descartarse en silencio. |
| `packages/tia/src/tia/api/state.py` | +13 / −4 | F10: la lectura de restauración cubre `max(2 días, 2 × trade_cooldown_seconds)`; docstring F15. |
| `packages/tia/src/tia/api/app.py` | +3 / −2 | F15: la descripción del parámetro `max_hours` dice que `0` es "sin deadline" y prevalece sobre el configurado. |
| `packages/tia/src/tia/backtest/holdout.py` | +62 / −5 | F11: hash de código congelado cubre estrategia, backtester, ejecución, riesgo, quant, régimen, costos, EV e instrumentos; huella del árbol sucio; bloqueo `fcntl.flock` al escribir el libro. F13: — (ver script). |
| `scripts/strategy_experiment.py` | +43 / −5 | F11: usa `frozen_code_paths` y `dirty_tree_digest`; F13: `resamples_adjusted = max(resamples, ⌈TAIL_MEANS/α_adj⌉)` para el intervalo ajustado por multiplicidad, registrado en el output; el bloque `simulator` del output registra las reglas de paridad reales del backtester (tipo de entrada, salidas, perfil, EV) en vez del literal `"market (backtester)"`. |

Archivos de prueba nuevos (todos no rastreados; ninguno modifica pruebas ajenas):

| Archivo | Pruebas | Cubre |
|---|---|---|
| `tests/unit/test_risk_sizing_contract.py` | 21 | los 16 escenarios de sizing de §5 + invariante por propiedades (Hypothesis) |
| `tests/unit/test_cost_semantics.py` | 30 | la semántica de costos de §4 con números de referencia a mano |
| `tests/unit/test_risk_restore_future_rows.py` | 6 | F10 (filas futuras → incompleta; tolerancia 60 s; el motor rechaza) |
| `tests/integration/test_backtest_parity.py` | 14 | §6: módulos compartidos, mismos argumentos del contrato en ambos motores, EV en frío, gate forzado, salidas nombradas, time stop acota la tenencia, limit vs market, perfiles, etapas, coherencia EV–simulador |
| `tests/integration/test_phase13_audit_regressions.py` | 7 | F9, F14, F16, G15 sobre el motor paper real |
| `tests/integration/test_risk_restore_lookback.py` | 3 | F10 (lookback ≥ 2 × cooldown) |
| `tests/integration/test_runtime_carry_pricing.py` | 4 | cómo la sesión pasa el carry al EV (con lectura, sin lectura, sin time stop, lectura no finita) |

Total: **85 pruebas nuevas en 7 archivos**. Ninguna prueba existente fue modificada en este bloque.

---

## 3. Auditoría F1–F16 contra el código actual

Método: para cada hallazgo se buscó el camino de código en el working tree actual, se ejecutó la prueba que
lo cubre y, donde el defecto podía reproducirse, se corrió la prueba nueva contra el árbol de inicio del
bloque (`scratchpad/phase13b/prefix_full`: HEAD más los archivos capturados en `tree_start`) para ver que
falla allí (`scratchpad/phase13b/prefix_results_detail.txt`).

| # | Hallazgo (resumen) | Estado | Evidencia |
|---|---|---|---|
| F1 | el proveedor paper solo cancelaba por `order_id`; el error se tragaba y el stop "cancelado" seguía vivo | **Confirmado y corregido** (Fase 1.2) | `tests/integration/test_paper_cancellations.py` (7) pasa; en este bloque se re-ejecutó y se leyó `cancel_order` (resuelve ambos ids, lanza `DuplicateOrderError` si no existe). Nada nuevo que corregir. |
| F2 | deadline y time stop en el mismo ciclo enviaban dos salidas | **Confirmado y corregido** (1.2; reforzado en 1.3 por G15) | `test_exit_guard.py` (8) pasa; G15 cierra la variante "stop recolocado sobre el cierre en vuelo" (§3, G15). |
| F3 | pérdida diaria, drawdown y pico se reiniciaban en cada arranque | **Confirmado y corregido** (1.2; cuenta paper) | `test_account_restore.py` (12) pasa. Límite documentado en 1.2: muerte dura entre fill y evento → bloqueo, no pérdida silenciosa. |
| F4 | el P&L caía a 0.0 ante error de base y la reconciliación levantaba el bloqueo | **Confirmado y corregido** (1.2) | `test_account_restore.py::test_an_unreadable_store_at_start_blocks_entries_and_never_substitutes_base_capital` pasa; `reconcile_session_state` exige riesgo + cuenta + posición del venue (leído en `api/state.py`). |
| F5 | dos arranques concurrentes construían dos runtimes | **Confirmado y corregido dentro de un proceso; Confirmado y pendiente entre procesos** | Dentro de un proceso: `asyncio.Lock` en `AppState._session_lock` (`test_session_start_atomicity.py`). Entre procesos: el bloque anterior añadió el **lease por heartbeat** en `runs.notes` (120 s; `test_session_lease.py`), que detecta a otro proceso vivo sobre la misma base **pero no es un candado distribuido**: dos procesos que arrancan dentro de la misma ventana de 120 s sin heartbeat previo pueden ambos pasar. No se introduce Redis ni otro servicio (mandato). Recomendación: una réplica por cuenta, documentada en operación. |
| F6 | el runtime live (dinero real) no recibe restauración ni deadline | **Confirmado y pendiente (PARCIAL)** | Auditado **sin activar trading real**: `_arm_live_locked` comparte el contrato "fila antes del loop" (G10, bloque anterior) y la restauración de riesgo se carga por el mismo `_load_risk_restore`; `restore_risk_state` falla cerrado (bloquea entradas si la reconstrucción es incompleta) — comprobado leyendo el código y con `test_live_path_parity.py`. **No verificado contra un venue**: no hay testnet accesible y el mandato prohíbe mainnet. El adaptador apunta a Binance **Spot** (`/api/v3/order`), sin `reduceOnly`: una salida live no tiene la protección G5 del motor paper. Sigue PARCIAL hasta validarse en testnet. |
| F7 | `resume` y el watchdog podían levantar el halt del deadline | **Confirmado y corregido** (1.2) | `test_deadline_hardening.py` (5) pasa. |
| F8 | la fila del run se escribía después de arrancar el loop | **Confirmado y corregido** (1.2) | `test_session_start_atomicity.py` pasa; G10 lo extiende a la ruta live. |
| F9 | feed caído tras el deadline: la detección de "cierre no ejecutado" contaba solo velas y nunca disparaba; el filtro de datos erraba en el cierre | **Confirmado y corregido** | `_check_deadline` cuenta también tiempo de pared: `3 × _bar_seconds()` desde `_deadline_close_at` (F9). `test_phase13_audit_regressions.py::test_a_deadline_close_no_bar_can_fill_is_reported_stuck_in_wall_time` **falla en el árbol previo** y pasa ahora; una prueba de control muestra que no dispara antes de los tres compases. |
| F10 | la restauración de riesgo leía un horizonte fijo de 2 días y descartaba filas futuras en silencio | **Confirmado y corregido** | `rebuild_risk_state` devuelve `complete=False` con el motivo si hay filas > 60 s después de `now`; `_load_risk_restore` lee `max(2 d, 2 × cooldown)`. `test_risk_restore_future_rows.py` (6; no importa en el árbol previo: la constante no existía) y `test_risk_restore_lookback.py::test_a_long_cooldown_widens_the_read_to_twice_its_span` (**falla en el árbol previo**). |
| F11 | el hash del holdout cubría solo el código de estrategia; sin bloqueo de archivo; sin huella del árbol sucio | **Confirmado y corregido** | `frozen_code_paths` (estrategia, backtest, ejecución, riesgo, quant, régimen, `domain/instruments.py`, `economics/costs.py`, `economics/expected_value.py`), `dirty_tree_digest`, `fcntl.flock` exclusivo en `HoldoutLedger.record`; el script registra `frozen_code_files` y `tree_digest`. Pruebas: `test_holdout*.py`, `test_experiment_integrity.py`, `test_strategy_experiment_script.py` (pasan). |
| F12 | multiplicidad contada por corrida y no acumulada | **Confirmado y corregido** (bloque anterior, S3) | familia de Bonferroni acumulativa sobre `research_runs.jsonl`; verificado en `test_experiment_integrity.py`. |
| F13 | precisión del intervalo ajustado: pocas remuestras para el α ajustado | **Confirmado y corregido** | `resamples_adjusted = max(resamples, ⌈20/α_adj⌉)` (`TAIL_MEANS = 20` medias más allá de cada cota); registrado en el output (`resamples_adjusted`, `tail_means`, `validity`). Cubierto por `test_strategy_experiment_script.py`. |
| F14 | una orden rechazada por el venue incrementaba contadores y presupuesto como si se hubiera operado | **Confirmado y corregido** | en `_submit`: terminal sin fills → `orders_rejected += 1`, `_trades_today` no cambia. `test_a_venue_rejection_is_counted_and_spends_nothing_from_the_days_budget` (**falla en el árbol previo**; venue con `reject_probability=1.0`). La prueba de control (`test_a_filled_entry_still_counts_as_a_trade_of_the_day`) falla en el árbol previo solo porque el contador `orders_rejected` no existía. |
| F15 | `max_hours=0` anula el span configurado sin documentarlo | **Confirmado y corregido (documentación)** | la descripción del parámetro en `api/app.py` y el docstring de `api/state.py` lo dicen; el comportamiento no se cambió (es el deseado: el operador decide explícitamente). Sin prueba nueva: es texto. |
| F16 | el docstring de `_reconcile` prometía comparar posiciones y no lo hacía | **Confirmado y corregido** | comparación venue ↔ round trip rastreado ("posición sin round trip", "round trip sin posición", "lado opuesto") registrada en el récord de reconciliación y en `reconciliation_breaks`; **no** lleva a SAFE_MODE (es la ruta de posición de `_manage_position` la que bloquea entradas, G13). Dos pruebas nuevas (**fallan en el árbol previo**). |
| G15 | con un cierre en vuelo y una vela que no lo ejecuta, la gestión de posición recolocaba un stop sobre el cierre | **Confirmado y corregido** | `_manage_position` retorna mientras `_pending_exit` no sea `None` (los disparadores que ocurren mientras tanto se cuentan en `exits_skipped_pending`, como antes). `test_a_bar_that_cannot_fill_the_close_leaves_no_stop_placed_over_it` (**falla en el árbol previo**). |

Hechos adicionales de la auditoría sin cambio de código: ningún hallazgo resultó **No reproducible** ni
**No aplicable**; el único **Bloqueado por falta de evidencia** es la parte de F6 que exige un venue
(testnet) para verificarse.

---

## 4. Costos

### 4.1 Inventario de lo que había

**Hechos.** Tres lugares calculaban costos con semánticas distintas:

* `ExecutionSimConfig` (simulador paper y backtester): `maker_fee_bps=2.5`, `taker_fee_bps=7.5`,
  `base_slippage_bps=2.0` aplicado **adversamente en cada pata** sobre el open de la vela, impacto
  `0.35 × √participación × 100` bps por pata, componente de rango `min(5 % del rango de la vela en bps, 25)`
  por pata, latencia modelada como desplazamiento de timestamps (no de precio), `reject_probability=0.01`,
  `partial_fill_probability=0.15`.
* `FeeSchedule` (modelo de costos del EV): `maker_bps=10`, `taker_bps=10` por defecto, marcado "configured
  default — NOT read from a live account"; la sesión, el motor de escenarios y el backtester construyen
  `CostModel(FeeSchedule(maker=execution.maker_fee_bps, taker=execution.taker_fee_bps))`, así que en los
  tres caminos los fees del EV son los del simulador (2.5/7.5) y no los 10/10 del default.
* `CostModel.estimate`: fees de ambas patas; spread "la mitad por cruce" (`spread_bps × 0.5 × cruces`, un
  cruce por pata taker); slippage más allá del tope de libro (`0.5 × √(exceso/tope) × max(spread, 1)` por
  cruce; sin libro, `max(½ volatilidad por vela, ½ spread)`); impacto `0.35 × √participación × 100` por
  cruce; latencia `σ_vela × √(latencia/duración de vela)` una vez. **No existía** funding, borrow ni la
  noción de estimación incompleta.

**Inferencias.** (i) El EV y el simulador compartían fees e impacto pero **no** el spread: el backtester
pasaba `spread_bps = base_slippage_bps` y el modelo cobraba la mitad por cruce, es decir **la mitad** de lo
que el simulador realizaba por pata. (ii) El carry no estaba en el EV mientras la sesión paper sí lo cobra
cada 8 h al tipo vivo (`_charge_funding`): un costo real ausente del gate. (iii) Un tipo de funding ausente
no tenía representación: nada distinguía "no aplica" de "no se pudo valorar".

### 4.2 La semántica unificada

**Hechos (código actual).** Para una operación de ida y vuelta, en puntos básicos del notional de entrada:

```
total_bps = fee_bps + execution_bps + carry_bps

fee_bps       = fee_entrada(maker|taker) + fee_salida(maker|taker)       # itemizadas: entry_fee_bps, exit_fee_bps
execution_bps = spread_bps + slippage_bps + latency_bps + impact_bps
  spread_bps   = spread_del_libro × ½ × cruces        cruces = (0 si entrada maker, si no 1) + (0 si salida maker, si no 1)
  slippage_bps = f(tamaño más allá del tope) × cruces  (0 si el tamaño cabe en el tope)
  impact_bps   = 0.35 × √(tamaño / volumen_vela) × 100 × cruces
  latency_bps  = σ_vela × √(latencia / duración_vela) / 1e-4            una sola vez
carry_bps     = funding_bps + borrow_bps
  funding_bps  = max(0, signo × tasa × períodos) / 1e-4   signo = +1 long, −1 short; lo que se cobraría se paga, lo que se recibiría NO se acredita
  borrow_bps   = tasa_diaria_bps × días  solo en short y solo si el venue presta (perpetuo: 0)
complete      = funding_known   (False si se pidió un horizonte > 0 sin tasa finita → la operación NUNCA es tradeable)
total_currency = notional × total_bps × 1e-4
```

Conversiones: `notional = |cantidad| × precio`; bps ↔ moneda por `× notional × 1e-4`; un cambio de nivel
de precio con el mismo notional no cambia ni los bps ni la moneda (probado). Long y short pagan los mismos
costos de ejecución; difieren solo en el signo del carry (probado).

**Qué es medido, estimado o asumido** (hecho: ningún componente es medido en el sentido de leído de la
cuenta; `FeeSchedule.verified_at_source` sigue `False` y el Live Activation Gate rehúsa armar mientras lo
esté):

| Componente | Origen | Carácter |
|---|---|---|
| fees | `ExecutionSimConfig` (2.5/7.5) | **asumido**, no verificado en origen |
| spread | sesión: cotización viva (`bookTicker`) cuando el feed la muestra; sin cotización, `base_slippage_bps` configurado; backtester: `2 × base_slippage_bps` (la lectura del simulador, §4.4) | **estimado** (sesión con quote) / **asumido** (resto) |
| slippage más allá del tope | sesión: `min(bid_size, ask_size)` del quote (0 = ignorancia, valorada como ½ σ); backtester: `volumen típico × max_participation_rate` | estimado / asumido |
| impacto | √participación en el volumen de la vela, coeficiente 0.35 | **asumido** (modelo convencional) |
| latencia | sesión: EMA de la latencia **medida** decisión→fill; backtester: `submit + ack` configurados (180 ms) | medido (sesión) / asumido (backtester) |
| funding | sesión: tipo vivo del monitor cuando hay time stop y lectura; backtester: no valorado (0 períodos) | estimado / no valorado (dicho en el registro) |
| borrow | 0 (perpetuo) | asumido |

### 4.3 Ejemplo numérico paso a paso (`test_the_worked_example`)

0,01 BTC a 100.000 → notional 1.000. Entrada maker, salida taker; libro de 2 bps; sin profundidad excedida,
sin impacto (volumen de vela desconocido = 0), sin latencia; long con time stop que cruza 3 liquidaciones
a +0,0001.

| Paso | Cálculo | bps | moneda |
|---|---|---|---|
| fee entrada (maker) | 2,5 | 2,5 | 0,25 |
| fee salida (taker) | 7,5 | 7,5 | 0,75 |
| spread | 2,0 × ½ × 1 cruce | 1,0 | 0,10 |
| slippage / impacto / latencia | 0 | 0 | 0 |
| funding | +1 × 0,0001 × 3 / 1e-4 | 3,0 | 0,30 |
| **total** | | **14,0** | **1,40** |
| edge bruto del estimador | 30 | 30,0 | 3,00 |
| **neto** | 30 − 14 | **16,0** | **1,60** |
| umbral | 5 | ≥ 5 → TRADE | |
| cost ratio | 14/30 = 0,467 | < 0,6 → pasa | |

El mismo ejemplo en short: funding 0 (lo recibiría; no se acredita), total 11, neto 19. Con el tipo ausente
(`funding_rate=None`, 3 períodos): `funding_bps = 0`, `complete = False`, `is_tradeable = False` aunque el
neto valorado sea 19 — "una estimación incompleta no es un costo más pequeño, es un costo desconocido".

Otros números de referencia probados (`tests/unit/test_cost_semantics.py`): taker+taker 15 + 2 = 17;
maker+maker 5 + 0 = 5; ganador antes de costos (+8) y perdedor después (−3) rechazado a cualquier umbral
≥ 0; perdedor en ambos (−5 → recortado a 0 − 11 = −11); slippage con 4 unidades contra 1 en el tope =
0,5 × √3 × 2 = 1,732 por cruce; impacto con ¼ del volumen = 17,5 por cruce; latencia 6 s de 60 =
√0,1 × 10 = 3,162 una vez; borrow short 5 bps/día × 2 días = 10, long 0; cost ratio 17/25 = 68 % > 60 %
rechaza con neto +8.

### 4.4 No doble contabilización

**Hechos.** (a) El estimador recibe el **retorno bruto** de cada round trip (`Outcome.gross_return_bps`)
con los fees pagados al lado; el motor del EV resta **una vez** los costos de la operación en evaluación
(`net = gross_edge − costs.total_bps`): probado con 30 bruto / 10 pagados / 11 hoy → 19, no 9. El
backtester alimenta su estimador con esa misma convención (`market_data="backtest"`). (b) Dentro de
`TradeCosts` cada componente se suma exactamente una vez; la itemización cierra con el total (probado).
(c) El spread se cobra por **cruce**, no por pata y además por round trip.

**Inferencia que queda como decisión documentada (no cambiada).** La muestra del estimador es el retorno
"fill a fill", y los fills del simulador ya incorporan el slippage/impacto/rango **realizados**; el EV
resta además el spread/slippage/impacto **modelados**. Sobre los costos de ejecución hay, por tanto, una
doble cuenta parcial de ≈ 2–5 bps por round trip en el peor caso (fees no: están separados). Es
**conservadora** (eleva la barra) y revertirla exigiría guardar el slippage realizado por round trip
(`edge_outcomes` no tiene esa columna) y mezclar semánticas en el histórico. **Dos soluciones plausibles,
riesgos distintos**: (1) dejarla, con la barra efectiva algo más alta que la configurada (elegida aquí por
no tocar el histórico ni la semántica de la evidencia); (2) persistir el slippage realizado y descontarlo de
la muestra, lo que afloja el gate en esos bps. Corresponde al usuario.

### 4.5 Coherencia EV ↔ simulador

**Hechos.** `test_the_expected_value_prices_the_spread_and_impact_the_simulator_realises`: con las
condiciones que el backtester construye (spread `2 × base`, tope `volumen típico × participación`, volumen
de vela, latencia y σ a cero para aislar), el modelo cobra **exactamente** el `base_slippage_bps` del
simulador por pata y el **mismo impacto** por pata (6,5 realizado vs 5,5 modelado por pata en el ejemplo;
la diferencia es el componente de rango del simulador, 1,0 por pata, que el modelo no tiene). El simulador
realiza siempre **≥** lo que el EV modela: el gate es el lado optimista por exactamente ese componente.

**Cambio aplicado (backtester, no sesión):** `spread_bps = 2 × base_slippage_bps` en las condiciones del EV
del backtester. Justificación en el código: el simulador toma `base` adversamente **en cada pata** contra el
open; como libro, eso es un spread de `2 × base` del que cada cruce paga la mitad. Antes el EV del backtester
cobraba la mitad de lo que el simulador realizaba por este componente. **No se cambió** el fallback de la
sesión sin cotización (`spread = base_slippage_bps`): es comportamiento de producción y la sesión normalmente
tiene quote; queda como decisión (§8) con las dos opciones.

### 4.6 El carry en la sesión: dos políticas, una elegida y la otra documentada

**Hechos.** Al cablear el funding al EV, la primera versión declaraba el horizonte (time stop > 0) y, sin
lectura del monitor, marcaba la estimación incompleta → **ninguna entrada** en una sesión paper con time stop
y sin monitor de funding (dos pruebas existentes lo mostraron: `test_exit_guard.py` y
`test_adverse_recovery.py` dejaron de operar). La versión final valora el carry **solo cuando hay una
lectura finita**; sin lectura no declara horizonte, el EV queda completo y la omisión se **cuenta**
(`funding.ev_carry_unpriced`), igual que el acumulador de la sesión no cobra y cuenta (`skipped_no_rate`).
Así el costo que el gate resta es el costo que el simulador cobrará. Probado en
`test_runtime_carry_pricing.py` (4).

**Las dos opciones.** (1) **Elegida**: coherente con el simulador; preserva el comportamiento de producción
(un feed de funding caído no detiene la sesión paper); riesgo: subvalora el carry mientras no hay lectura, y
lo dice. (2) **Estricta (fail-closed)**: horizonte sin tasa → incompleta → sin entradas; riesgo: la sesión
deja de operar en cada caída del feed de funding (desde este entorno, Binance responde 403; en el VPS no se
verificó). La opción 2 es un cambio de una línea (`funding_periods` siempre que `max_holding_bars > 0`) y
queda como recomendación a decidir, no como código.

Con `max_holding_bars = 0` (el valor por defecto) no se declara horizonte: la tenencia es ilimitada y el
carry se cobra cuando ocurre; el registro lo dice (`funding_periods = 0`).

---

## 5. Risk sizing

### 5.1 El contrato (`tia.risk.sizing.apply_risk_budget`)

```
allowed  = min(limit_risk, budget_risk) × conviction                      # moneda que el stop puede realizar
quantity = min(approved, min(limit_risk, budget_risk) / |entry − stop|) × conviction
quantity = redondeo HACIA ABAJO al step del instrumento
rechazar si quantity ≤ 0 (below_lot_step) o quantity × entry < min_notional (below_min_notional)   # nunca se eleva
garantía: quantity × |entry − stop| ≤ allowed   (si no, RiskError: el contrato se rompió)
```

donde `limit_risk = equity × RiskLimits.max_risk_per_trade_pct / 100` (0,5 % por defecto: el techo duro del
motor de riesgo), `budget_risk = equity × risk_per_trade_pct(perfil) × m_drawdown × m_volatilidad × m_racha`
(`RiskBudgetEngine`), `approved` la cantidad que el `RiskEngine` aprobó tras sus límites de exposición
(notional por posición, bruta, neta, clúster, apalancamiento/margen, filtros) y `conviction ∈ (0, 1]` la
fracción por convicción (solo si está definida; `1.0` si no). Un presupuesto que no permite operar, un
presupuesto nulo o no finito, un stop ausente/inválido, una convicción no finita o ≤ 0, un precio de entrada
inválido o una aprobación nula **rechazan** con motivo (`budget_blocks_new_trades`, `zero_risk_budget`,
`invalid_risk_budget`, `no_stop_defined`, `invalid_stop`, `invalid_conviction`, `invalid_entry_price`,
`nothing_approved`). El límite que mandó queda nombrado (`risk_engine`, `risk_budget`, `risk_limit`, con
sufijo ` x conviction`).

**Hechos.** El contrato lo llaman los tres motores con los mismos nueve argumentos (probado en
`test_backtest_parity.py` para sesión y backtester): la sesión en `_process_bar` (los rechazos
`below_*` van a la etapa `filters`, el resto a `budget`; `sized_down` cuando la cantidad baja de la
aprobada), el backtester en el paso de decisión, y el motor de escenarios antes de `_submit`. La semántica de
la convicción cambió de "fracción del riesgo permitido" a "fracción del tamaño completo" para respetar su
contrato documentado ("fraction of the risk-approved size"); con ello `quantity ≤ approved × conviction` y
la pérdida en el stop ≤ `min(limit, budget) × conviction` a la vez.

### 5.2 Multiplicadores (hechos, `tia/risk/budget.py`)

| Multiplicador | Regla | Perfil conservador / equilibrado / agresivo |
|---|---|---|
| drawdown | NORMAL: lineal de 1,0 a `defensive_multiplier` en `[0, defensive]`; DEFENSIVE: lineal de `defensive_multiplier` a 0 en `[defensive, emergency]`; EMERGENCY: 0 y **no permite operar** | defensive 3/5/8 %, emergency 6/10/15 %, defensive_multiplier 0,4/0,5/0,6 |
| volatilidad | `min(1, target_annual_vol / realizada)`; **nunca > 1** | target 0,10/0,20/0,35 |
| racha | `0.5^(pérdidas − dampener + 1)` desde `dampener` pérdidas seguidas, piso 0,05 | dampener 3/4/5 |
| riesgo por trade | `risk_per_trade_pct` | 0,25 / 0,50 / 1,00 % |

### 5.3 Los 16 escenarios (equity 10.000; entrada 100.000; stop 99.000 → 1.000 por unidad al stop; límite 0,5 % = 50; step 1e-6; min notional 10)

| # | Escenario | Riesgo permitido | Cantidad | Riesgo efectivo | Resultado |
|---|---|---|---|---|---|
| 1 | base 0,5 % (equilibrado) con stop conocido | 50 | 0,05 | 50 | aceptado; manda `risk_engine` |
| 2 | perfil conservador 0,25 % | 25 | 0,025 | 25 | manda `risk_budget` |
| 3 | perfil agresivo 1 % contra el límite 0,5 % | 50 (de 100) | 0,05 | 50 | manda `risk_limit`: el límite es techo |
| 4 | multiplicador 1,0 | 50 | 0,05 | 50 | nada cambia |
| 5 | multiplicador 0,5 | 25 | 0,025 | 25 | la mitad del dinero en el stop |
| 6 | multiplicador 0 | 0 | — | — | **rechazado** `zero_risk_budget` |
| 7 | drawdown: a mitad de la zona normal 0,75×; en el umbral defensivo 0,25×... (0,5 × 0,5); emergencia | 37,5 / 12,5 / 0 | — | 0,75× / 0,25× | emergencia **rechazado** `budget_blocks_new_trades` |
| 8 | racha: al dampener ½, una más ¼ | 25 / 12,5 | | 0,5× / 0,25× | el tamaño sigue al presupuesto |
| 9 | volatilidad: realizada = target 1×; 4× el target 0,25×; baja volatilidad **no** crece | 50 / 12,5 / 50 | | 50 / 12,5 / 50 | nunca > 1 |
| 10 | stop ausente / negativo / igual a la entrada / NaN | — | — | — | **rechazado** `no_stop_defined` / `invalid_stop` / `invalid_stop` / `no_stop_defined` |
| 11 | equity 0 / negativa / NaN / inf | — | — | — | **rechazado** `zero_risk_budget` o `invalid_risk_budget` |
| 12 | step y min notional: 25,0000004 → 0,025000; presupuesto 0,05 con min notional 10 | 25 / 0,05 | 0,025 / — | 25 / — | redondeo hacia abajo; **rechazado** `below_min_notional` (no se eleva a 0,0001) |
| 13 | la aprobación del motor (0,002, 2 de riesgo) es techo | 50 | 0,002 | 2 | manda `risk_engine` |
| 14 | long y short con la misma distancia de stop | 50 | 0,05 / 0,05 | 50 / 50 | mismo dinero |
| 15 | los tres perfiles ordenan el dinero hasta el límite | 25 / 50 / 50 | | | agresivo capado por `RiskLimits`, no 100 |
| 16 | convicción 0,25 → 0,0125 (12,5); 1,5 → clampeada a 1; 0 / NaN rechazadas; 0,3 × 0,25 → `below_min_notional` | 12,5 | 0,0125 | 12,5 | nunca crece |
| + | racha restaurada tras reinicio (`restore_risk_state`) reduce el primer presupuesto del nuevo proceso | | | | probado |
| + | **invariante (Hypothesis)**: para presupuestos aleatorios, un multiplicador menor nunca permite una pérdida mayor; `efectivo ≤ permitido`; `cantidad ≤ aprobada`; `notional ≥ min_notional` si aceptado | | | | 100 ejemplos |

### 5.4 Casos rechazados en los motores (hechos)

En la sesión, `below_min_notional`/`below_lot_step` se cuentan en `filter_rejected` y se rehúsan en la
etapa `filters` con el texto "not raised to reach it"; los demás rechazos del contrato van a
`budget_rejected`/etapa `budget`. El backtester usa las mismas etapas y contadores. Ningún camino eleva la
cantidad al mínimo del venue.

---

## 6. Paridad backtester ↔ sesión paper-live

Clasificación: **CE** compartido y equivalente (mismo módulo, misma regla); **CD** compartido con diferencias
justificadas; **SR** solo runtime; **SB** solo backtester; **NI** no implementado; **NV** no verificable.

| Componente | Sesión (`runtime/live.py`) | Backtester (`backtest/engine.py`) | Clase | Nota |
|---|---|---|---|---|
| Datos | feed Binance (WS kline + REST) | serie histórica/CSV, buffer acotado `lookback_bars` | CD | la sesión ve velas en formación; el backtester decide al cierre y ejecuta en la siguiente (ambos) |
| Features | `FeatureBuilder` | `FeatureBuilder` | CE | |
| Régimen e histéresis | `RegimeClassifier.classify(now)` | idem | CE | |
| Fusión de estrategias | `StrategyEngine.evaluate` | idem | CE | |
| Gate HTF ("tide") | sí (`tide`, lectura horaria) | no | SR | el backtester no tiene serie horaria paralela; **NI** en backtest |
| Calidad de datos | `DataQualityEngine` + watchdog de frescura | `DataQualityEngine` (hard fail salta la vela) | CD | el watchdog (TTL, halts) es solo runtime |
| RiskEngine | `RiskEngine.evaluate` | idem | CE | |
| Presupuesto de riesgo | `RiskBudgetEngine(profile)` con drawdown/volatilidad/racha/trades del día/exposición | idem | CE | ambos con `trades_today` armado al fill de entrada |
| Contrato de sizing | `apply_risk_budget` | idem, mismos 9 argumentos | CE | probado |
| Convicción | `conviction_fraction` (exploración incluida) | `conviction_fraction` (`exploring=False`) | CD | sin exploración en backtest |
| EV + costos | `ExpectedValueEngine` **forzado**; `CostModel` con quote vivo, latencia medida, carry si time stop + lectura | mismo motor y modelo, **observa por defecto** (`enforce_expected_value=False`), spread `2 × base`, latencia configurada, sin carry | CD | justificado: un backtest frío no tiene evidencia; forzado se prueba que opera 0 |
| Evidencia | absorbida al arranque + propia; política de procedencia | solo la propia de la corrida (`market_data="backtest"`) | CD | no se inventa evidencia artificial para el EV |
| Exploración | paper, acotada por día, explícita | ninguna | SR | |
| Scoreboard / mute, guardrail retrospectivo | sí | no | SR | |
| Filtro de spread | gate `max_spread_bps` sobre el quote | no hay quote | SR | |
| Entrada market vs limit | `entry_order_type`; limit a ½ `base_slippage_bps` de nuestro lado, cuantizada al tick del venue de forma pasiva (`core/money.quantize_price_passive`: compra hacia abajo, venta hacia arriba; sin tick conocido, precio crudo) | idem (`_limit_price_for`), con el tick del universo de instrumentos, la misma regla local que juzga las órdenes paper-live sin filtros del venue (Fase 1.6) | CE | la cuantización nunca hace la orden más agresiva; probado en `tests/unit/test_limit_price_ticks.py` |
| Timeout / expiración / cancel de la limit | `entry_limit_timeout_bars` | idem (`orders_expired`) | CE | |
| Política de fill de la limit | motor paper: solo si la vela **atraviesa** el límite | mismo motor | CE | conservadora: tocar no es llenar |
| Stop protector | uno por posición, redimensionado en parciales | idem (`_sync_protective_stop`) | CE | |
| Break-even + fees | `tighten_stop(fee_buffer)` | idem | CE | mismo `fee_buffer_bps` del `FeeSchedule` |
| Trailing (ATR) | `tighten_stop(trail_atr_multiple)` | idem | CE | ATR de la vela anterior en ambos |
| Objetivo | `use_target`, cierre market | idem (`_request_exit("target reached")`) | CE | |
| Salida por señal opuesta | `exit_on_signal_reversal` → cierre sin pasar por el EV | idem | CE | |
| Time stop | `max_holding_bars` (0 = off) | idem | CE | probado: tenencia ≤ `max_holding_bars + 1` |
| Una sola salida en vuelo | `_pending_exit` (G15) | `leg.exit_pending` | CE | |
| Funding / borrow | acumulación cada 8 h al tipo vivo; EV con carry si time stop | no se acumula; EV sin carry | SR | **NI** en backtest; dicho en el output del script |
| Apalancamiento / liquidación | `leverage` escala límites; liquidación por mantenimiento | 1× | SR | |
| Redondeo y filtros del venue | `filters_for`/`validate_quantity` al construir y en el motor | contrato + motor paper | CE | mismo `execution/filters.py` |
| Rechazos y parciales del venue | motor paper (`reject_probability`, `partial_fill_probability`) | mismo motor | CE | deterministas por semilla |
| Cierre fin de período | deadline de sesión: halt, cancel de la limit, cierre con gracia, detección de no ejecutado (F9) | `liquidate_at_end` al close de la última vela con taker + base slippage | CD | el backtester marca la salida como forzada |
| Registro de decisiones | `_refuse(stage, reason)` → funnel y eventos | `DecisionRecord.stage/reason` + `DecisionCounts` | CE | mismo vocabulario de etapas |
| Persistencia, reconciliación, lease, kill switch | sí | no | SR | |
| Consistencia con el VPS | — | — | **NV** | el working tree no es el código desplegado |

**Hechos sobre las pruebas de paridad** (`tests/integration/test_backtest_parity.py`, 14): los mismos
objetos importados (`apply_risk_budget`, `tighten_stop`, `conviction_fraction`, `CostModel`,
`RiskBudgetEngine`, `ExpectedValueEngine`); el backtester llama al contrato por cada entrada enviada con las
mismas nueve claves que la sesión; en frío cada entrada vale `0 − costos` (< 0, no tradeable) y se envía
igual (observa); con `enforce_expected_value=True` opera **cero** veces y cada registro de la etapa
`expected_value` dice NO_TRADE; toda salida tiene un nombre del vocabulario de la sesión (`protective
stop`, `break-even stop`, `trailing stop`, `target reached`, `time stop`, `signal reversed`) o
`forced liquidation at end of sample`; con `max_holding_bars=5` ninguna tenencia elegida supera 6 velas;
el conservador toma menos que el agresivo en la **misma** primera decisión y `sized_down ≥ 1`; un perfil
desconocido es rechazado antes de leer una vela; todas las etapas pertenecen al conjunto conocido.

**Inferencia.** El backtester juega ahora el mismo juego que la sesión en todo lo que depende de módulos
compartidos; las diferencias restantes son de **información** (quote, latencia medida, funding, tide,
exploración, evidencia absorbida), no de reglas, y están listadas. Esto **no** prueba que ambos produzcan
los mismos trades sobre los mismos datos, ni que la estrategia tenga ventaja.

---

## 7. Pruebas ejecutadas

Entorno: `.venv/bin/python` con `PYTHONPATH=packages/tia/src`, opciones `-p no:cacheprovider -o
addopts="--strict-markers --strict-config" -q`; lint `.venv/bin/ruff check packages tests scripts`.
Registros en `scratchpad/phase13b/` (`affected_suites.log`, `final_*.log`, `prefix_results*.txt`).

### 7.1 Pruebas focalizadas (durante el bloque)

| Comando (resumen) | Resultado |
|---|---|
| `pytest tests/unit/test_cost_semantics.py` | 30 passed (0,2 s) |
| `pytest tests/unit/test_risk_sizing_contract.py` | 21 passed |
| `pytest tests/unit/test_risk_restore_future_rows.py tests/unit/test_risk_restore.py` | 18 passed |
| `pytest tests/integration/test_backtest_parity.py` | 14 passed (29 s) |
| `pytest tests/integration/test_phase13_audit_regressions.py` | 7 passed |
| `pytest tests/integration/test_risk_restore_lookback.py` | 3 passed |
| `pytest tests/integration/test_runtime_carry_pricing.py` | 4 passed |
| `pytest tests/integration/test_experiment_integrity.py tests/integration/test_strategy_experiment_script.py` | 4 passed (44 s) |
| suites afectadas (runtime, deadline, invariantes, exit guard, integridad de órdenes, cancelaciones, economía del runtime, recuperación adversa, paridad live, backtest unit, no-lookahead, holdout, experimento, sizing, economía, EV, convicción, restore, budget, risk engine) | **primera corrida: 2 failed, 414 passed (125 s)** — las dos fallas (`test_exit_guard.py::test_deadline_and_time_stop_in_the_same_cycle...` y `test_adverse_recovery.py::test_rejects_and_partials...`) eran la política de carry estricta (§4.6: con time stop y sin monitor, ninguna entrada); corregida la política, las dos pasan y la selección `-k "exit_guard or adverse or audit_regressions or funding or time_stop or conviction"` da 21 passed |

Las 38 pruebas de regresión de la Fase 1.2 (`test_paper_cancellations.py` 7, `test_exit_guard.py` 8,
`test_deadline_hardening.py` 5, `test_account_restore.py` 12, `test_session_start_atomicity.py` 6) están
incluidas en la corrida completa de §7.3.

### 7.2 Evidencia previa a la corrección (árbol de inicio del bloque, `-o pythonpath=scratchpad/phase13b/prefix_full/packages/tia/src`)

| Archivo | En el árbol previo |
|---|---|
| `test_cost_semantics.py` | no importa: `FUNDING_PERIOD_SECONDS` no existía |
| `test_risk_sizing_contract.py`, `test_backtest_parity.py` | no importan: `apply_risk_budget` no existía |
| `test_risk_restore_future_rows.py` | no importa: `FUTURE_ROW_TOLERANCE_SECONDS` no existía |
| `test_phase13_audit_regressions.py` | **6 failed, 1 passed**: fallan F9 (cierre no ejecutado nunca detectado sin velas), F14 (y su control: el contador no existía), F16 ×2 (ninguna divergencia de posición), G15 (stop recolocado sobre el cierre: `"no stop re-placed over the working close"`); pasa el control de "no dispara antes de tres compases" |
| `test_risk_restore_lookback.py` | **1 failed, 2 passed**: falla el cooldown largo (lookback fijo de 2 días); pasan los dos casos cuyo resultado no cambió |
| `test_runtime_carry_pricing.py` | 4 failed (`KeyError`: el contador `ev_carry_unpriced` y los argumentos de carry no existían) |

### 7.3 Corrida completa definitiva (`scratchpad/phase13b/run_final.sh`)

| Paso | Estado | Duración | Resultado |
|---|---|---|---|
| lint | OK (0) | — | All checks passed! |
| `pytest tests/unit` | OK (0) | 86 s | 1403 passed, 6 warnings in 84.48s (0:01:24) |
| `pytest tests/integration` | OK (0) | 251 s | 302 passed in 248.64s (0:04:08) |
| `pytest tests/property` | OK (0) | 24 s | 31 passed in 23.56s |
| `pytest tests/failure` | OK (0) | 5 s | 12 passed in 3.24s |
| `pytest tests/adversarial` | OK (0) | 7 s | 16 passed in 7.15s |
| `pytest tests/e2e` | OK (0) | 64 s | 8 passed in 61.98s (0:01:01) |

Una sola corrida, sin fallos, sin reintentos y sin pruebas desactivadas o marcadas.

Comparación con el cierre del bloque anterior: unit 1346 → 1403 (+57), integration
274 → 302 (+28); el resto sin cambios.

---

## 8. Riesgos pendientes y decisiones del usuario

1. **Doble cuenta parcial de los costos de ejecución en el EV** (§4.4): la muestra bruta del estimador ya
   incorpora el slippage realizado y el EV resta el modelado. Conservador; revertirlo exige persistir el
   slippage realizado por round trip. Decisión del usuario.
2. **Carry sin lectura de funding** (§4.6): elegida la política coherente con el simulador (no valorar,
   contar). La alternativa fail-closed está descrita y es un cambio de una línea; afecta a la sesión
   desplegada cuando el feed de funding falla. Decisión del usuario.
3. **Spread sin cotización en la sesión** (§4.5): el fallback sigue siendo `base_slippage_bps` (la mitad
   de lo que el simulador paper realiza por pata). Opciones: (a) `2 × base` como el backtester (más
   conservador, cambia producción en el caso sin quote); (b) dejarlo y aceptar el sesgo cuando el feed de
   quotes falla. No se cambió. Decisión del usuario.
4. **F6 / adaptador Spot**: la ruta live no está validada contra ningún venue; el adaptador no mapea
   `reduceOnly`. **Bloqueado** hasta disponer de testnet. No habilitar dinero real antes.
5. **F5 entre procesos**: el lease por heartbeat detecta, no excluye; una ventana de 120 s sin heartbeat
   previo admite dos arranques. Operar con una réplica por cuenta.
6. **Fees no verificados en origen**: `verified_at_source=False`; el gate live rehúsa armar mientras lo
   esté. Sin cambios posibles sin cuenta.
7. **Funding, tide y exploración no existen en el backtester** (§6): la evidencia que produce un backtest
   es la de un juego sin esas tres cosas; el output del script lo registra.
8. **Flake conocido** (bloque anterior): `tests/integration/test_restart_recovery.py` tiene una carrera de
   persistencia fire-and-forget en el motor de escenarios (`runtime/engine.py`, `asyncio.create_task` en
   `_persist`); pasó en la corrida definitiva anterior y pasó también en la corrida definitiva de este bloque (sin reintento). Pendiente para la
   Fase 1.4.
9. **Ninguna afirmación sobre ventaja**: la evidencia real sigue siendo la del bloque anterior (2 round
   trips). Nada en este bloque mejora, valida ni promete rentabilidad; los umbrales (`ev_threshold_bps=5`,
   `max_cost_ratio=0.6`, perfiles, límites) no se tocaron.

---

## 9. Estado de Git al final y confirmaciones

| | Final (2026-10-11T11:25:02Z) |
|---|---|
| Rama | `claude/algo-trading-simulation-platform-ngf7xo` |
| HEAD | `ab68d1c128a7181f54e1e79d3d7f37261365d821` (sin commits) |
| `git status --porcelain` | 82 (25 M, 57 ??) (los 70 del inicio + 7 archivos de prueba + este informe) |
| Huella del `git diff` (sha256/16) | `aa7dce3039a38ec2` |
| Huella del conjunto de no rastreados (excluido este informe) | `e58433f066dfe06b` |
| `git diff --stat` | 25 files changed, 3667 insertions(+), 335 deletions(-) |
| `git stash list` | vacío |

Preservación (`scratchpad/phase13b/preservation_check.sh`): de los 70 archivos capturados al inicio,
62 son byte a byte idénticos y 8 cambiaron, **todos** en la lista de archivos
propios de este bloque; **0** cambios en archivos ajenos. Los cuatro archivos rastreados que estaban
limpios al inicio y ahora difieren de HEAD (`backtest/engine.py`, `backtest/result.py`, `economics/costs.py`,
`risk/sizing.py`) son propios. Los nuevos no rastreados son los 7 archivos de prueba de §2 y este informe.

Confirmaciones: **no** se hizo commit ni push; **no** se desplegó ni reinició ningún servicio, contenedor,
proceso ni el VPS; **no** se ejecutó ninguna operación en Binance (mainnet ni testnet) ni se envió orden
alguna; **no** se leyó, mostró, copió ni almacenó credencial, token, clave ni contraseña; **no** se accedió
al holdout, no se desbloqueó ni se modificó su libro (el script de experimentos no se ejecutó fuera de sus
pruebas, que usan datos sintéticos y un libro temporal); **no** se corrió ninguna simulación extensa ni
paper run prolongado; **no** se instaló ni descargó dependencia alguna; **no** se usó `git reset --hard`,
`git clean`, checkout destructivo ni stash; **no** se alteró ningún umbral ni parámetro para mejorar
resultados; **no** se modificó ninguna prueba ajena al alcance; **no** se afirma que el código desplegado
haya cambiado.

---

## 10. Conclusión

**Hechos.** Los tres pendientes que dejó el bloque anterior están cerrados en el working tree: (1) los
multiplicadores del presupuesto de riesgo **reducen el dinero en el stop**, no solo un número en el informe,
a través de un contrato único que los tres motores comparten y que 21 pruebas con números a mano y un
invariante por propiedades verifican; (2) los costos tienen **una** semántica itemizada (fees por pata y
liquidez, spread por cruce, slippage, impacto, latencia, funding pagado y nunca acreditado, borrow,
estimación incompleta que nunca es tradeable), con 30 pruebas de referencia y un ejemplo paso a paso; (3) el
backtester reproduce las reglas de la sesión (presupuesto, EV observado, convicción, sizing, salidas con una
sola ruta, break-even/trailing, limit con timeout, funnel por etapa) y la tabla de §6 dice qué sigue siendo
distinto y por qué. De F1–F16, catorce están **Confirmado y corregido** (ocho de ellos con la prueba nueva
fallando en el árbol previo o sin poder importarse allí), F5 lo está dentro de un proceso y pendiente entre
procesos, y F6 sigue **PARCIAL/Bloqueado** por falta de un venue. Las suites completas: lint limpio; unit 1403 passed, 6 warnings; integration 302 passed; property 31 passed; failure 12 passed; adversarial 16 passed; e2e 8 passed.

**Inferencias.** El gate del EV es ahora, en el backtester, al menos tan estricto como el costo que el
simulador realiza salvo el componente de rango (medido: 1 bps por pata en el ejemplo); en la sesión, con
quote vivo, cobra el spread real. La doble cuenta parcial de ejecución eleva la barra efectiva algunos bps y
está documentada, no escondida. Nada de esto es evidencia de ventaja: solo garantiza que el instrumento de
medición no miente a favor.

**Recomendaciones (decisiones del usuario, en orden).** (1) Revisar este diff y los dos informes de la
Fase 1.3 antes de cualquier commit; (2) decidir las tres políticas abiertas de §8 (doble cuenta, carry sin
lectura, spread sin quote); (3) no habilitar la ruta live hasta validar el adaptador en testnet con
`reduceOnly` resuelto; (4) una réplica por cuenta mientras el lease sea detección y no exclusión; (5) la
Fase 1.4 (auditoría integral del sistema, sin tocar la estrategia) es el siguiente paso y hereda como
entradas conocidas la carrera de persistencia del motor de escenarios, el adaptador Spot y la falta de
`entry_blocks`/lease en el frontend.
