# Trader-IA — Fase 1.1: endurecimiento operativo y estadístico

Entorno de trabajo: checkout de esta sesión en `/home/user/Trader-IA` (mismo repositorio y rama que
`/home/tia/Trader-IA` en el VPS; el VPS no se tocó). Todo es simulación en papel; nada de esta fase
toca dinero real, credenciales, activación ni despliegue. Sin commits ni push.

## Estado por tarea (implementado / probado / probado parcialmente / pendiente)

| # | Tarea | Estado | Nota |
|---|---|---|---|
| 1 | Persistencia y restauración de límites de riesgo | **implementado y probado** para entradas/día, por símbolo, cooldown, presupuesto diario y exploración; **pendiente** para pérdida diaria y pico de equity (§3) | la ruta real (runtime → SQLite → repositorio → runtime) está cubierta por tests |
| 2 | Filtros de instrumento y `min_notional` | **implementado y probado** (constructor de intención y proveedor paper) | hallazgo: el motor de riesgo ya comprobaba el mínimo al dimensionar; la brecha real era el escalado posterior |
| 3 | Corte y supervisión de sesión | **implementado y probado** (reloj inyectable) con una política de wind-down; **probado parcialmente** el reinicio (decisión de arranque y API); caída del supervisor documentada, no ejecutable aquí | sin corrida real de 8 h, por mandato |
| 4 | Criterio `PROMISING_ON_VALIDATION` | **implementado y probado** | límite inferior ajustado > 0 estricto; sin estrés de costos no hay `PROMISING` |
| 5 | Dependencia temporal y multiplicidad | **implementado y probado** (block bootstrap circular, Bonferroni) | no equivale a un análisis completo de sobreajuste (§7) |
| 6 | Protección del holdout | **implementado y probado** (libro de accesos, hash de dataset/configuración/código, rechazo de repetición) | es procedimiento, no caja fuerte; el holdout no se desbloqueó ni calculó |

---

## 1. Estado inicial y final de Git

| | Inicio de la fase (2026-10-10T15:12:53Z) | Final |
|---|---|---|
| Rama | `claude/algo-trading-simulation-platform-ngf7xo` | igual |
| HEAD | `ab68d1c128a7181f54e1e79d3d7f37261365d821` | igual (sin commits) |
| `git status --short` | 15 M + 10 ?? (Fase 1 + informe de la Fase 2) | 20 M + 28 ?? (incluido este informe) |
| Huella del `git diff` (sha256/16) | `d98ab6359eb3edfe` (idéntica a la del paquete de revisión) | `0278e0e556ecd44d` |
| `git diff --stat` | 15 archivos, +607/−48 | 20 files changed, 1227 insertions(+), 93 deletions(-) |

**Prueba de que la Fase 1 no se perdió.** Se guardó el diff de la Fase 1 al inicio
(`phase1_diff_start.patch`, 1.109 líneas) y se reconstruyó cada archivo tal como quedó en la Fase 1
(snapshot de HEAD + ese parche; el parche aplica limpio). Comparando esas versiones con el árbol final:

- Archivos de la Fase 1 **intactos** (hash idéntico): `.env.example`, `docker-compose.prod.yml`,
  `domain/signals.py`, `economics/expected_value.py`, `learning/scoreboard.py`, `runtime/engine.py`,
  `strategy/engine.py`, `strategy/fusion.py`, `tests/unit/test_paper_execution.py`,
  `tests/unit/test_scoreboard.py`, y los nuevos de la Fase 1 `backtest/resample.py` y los cuatro tests
  unitarios, más los tres informes previos.
- Archivos de la Fase 1 **ampliados** en 1.1: `api/state.py`, `core/config.py`, `execution/paper.py`,
  `runtime/live.py`, `tests/integration/test_live_runtime.py`, `docs/STRATEGY_IMPROVEMENT_PHASE.md`
  (solo se **añadió** §7.1) y `scripts/strategy_experiment.py` (reescrito para los ítems 4–6; la versión
  de la Fase 1 se conservó en el scratchpad de la sesión).
- Líneas de la Fase 1 **sustituidas** (54 en total, listadas en `removed_from_phase1_versions.txt`):
  en `live.py` el bloque de cuantización/`min_notional` de `_build_intent` (reemplazado por el módulo
  de filtros, que conserva la cuantización hacia abajo al lote del instrumento y la prueba de Fase 1
  que lo cubre sigue pasando), el cuerpo de `stop()` (reestructurado en `stop()` + `_finalize_stop()`,
  idempotente) y dos imports; en `state.py` la firma de `start_paper_realtime`, la consulta de
  reanudación (ahora lee también `notes`) y el bloque `if halts` (reemplazado por `resume_decision`);
  en `app.py` la firma de la ruta `paper-start`; en `test_live_runtime.py` dos llamadas directas a
  `_build_intent` que ahora pasan `reference_price` (las entradas se juzgan contra el notional mínimo).
  Ninguna corrección de la Fase 1 se revirtió; las 1.232 + 163 pruebas previas siguen pasando.

## 2. Archivos modificados y motivo

Nuevos (fuente, 970 líneas):

| Archivo | Motivo |
|---|---|
| `packages/tia/src/tia/risk/restore.py` | reconstrucción pura del estado de frecuencia desde órdenes/fills persistidos (`RiskRestore`, `rebuild_risk_state`) |
| `packages/tia/src/tia/execution/filters.py` | única fuente de reglas de cantidad/notional (`InstrumentFilters`, `filters_for`, `validate_quantity`, `OrderFilterError`) |
| `packages/tia/src/tia/runtime/session_limits.py` | deadline en la fila de run y decisión de reanudación (`encode_session_notes`, `decode_session_deadline`, `resume_decision`) |
| `packages/tia/src/tia/backtest/inference.py` | `CRITERIA`, block bootstrap, i.i.d. de comparación, nivel Bonferroni, `verdict` con motivo |
| `packages/tia/src/tia/backtest/partitions.py` | particiones cronológicas con purga/embargo y ventana de calentamiento |
| `packages/tia/src/tia/backtest/holdout.py` | libro de accesos al holdout, hash de configuración+código, estado git |

Modificados:

| Archivo | Cambio |
|---|---|
| `risk/engine.py` | `RiskEngine.restore(RiskRestore)` (rechaza reconstrucciones incompletas) |
| `risk/__init__.py`, `persistence/__init__.py` | exportaciones |
| `persistence/repositories.py` | `RiskStateRepository.rebuild(now)` (solo lectura; runs `paper-live`/`live`); `RunRepository.create(notes=)` |
| `runtime/live.py` | restauración y fail-safe del estado de riesgo; filtros en `_build_intent` y etapa `filters` del embudo; deadline de sesión con wind-down; `stop()` idempotente; escrituras de persistencia **secuenciadas** y orden guardada antes que sus fills; `snapshot()` con `risk_state` y `session` |
| `execution/paper.py` | validación de filtros en `submit_order` (REJECTED determinista, sin fills) |
| `api/state.py` | `_load_risk_restore`, `reconcile_risk_state`, `max_duration_hours`/`session_deadline` en `start_paper_realtime`, `notes` del run, reanudación por `resume_decision`, kind `run_stop` en `_persist` |
| `api/app.py` | `POST /api/live/paper-start?max_hours=`; `POST /api/live/risk-state/reconcile` |
| `core/config.py` | `live.session_max_hours` (0 = sin límite), `live.session_wind_down_bars` (30) |
| `scripts/strategy_experiment.py` | usa `inference`/`partitions`/`holdout`; CI ajustado, veredictos con motivo, libro del holdout, `--resamples`, `--holdout-log`, `--holdout-reopen-reason` |
| `docs/STRATEGY_IMPROVEMENT_PHASE.md` | §7.1 añadido (criterio nuevo, inferencia, protocolo del holdout) |
| `tests/integration/test_live_runtime.py` | tres llamadas directas al constructor de intenciones pasan `reference_price`; un envío manual siembra una vela en el buffer; helper `_market_candles` |

Pruebas nuevas (112 funciones, 116 casos con parametrizaciones): `test_risk_restore` (12), `test_risk_state_persistence` (9), `test_order_filters`
(19), `test_live_filters` (6), `test_session_limits` (8), `test_session_deadline` (15),
`test_paper_session_api` (5), `test_inference` (22), `test_partitions` (7), `test_holdout_ledger` (7),
`test_strategy_experiment_script` (2).

## 3. Diseño adoptado para persistencia y recuperación del riesgo

**Fuentes de estado inspeccionadas y qué les pasa en un reinicio (antes de 1.1).**

| Estado | Dónde vive | Efecto en decisiones | Antes | Ahora |
|---|---|---|---|---|
| `trades_today`, `trades_today_by_symbol` | `RiskState` (memoria) | tope 20/día y 5/símbolo/día | a cero | restaurado |
| `last_trade_at[symbol]` | `RiskState` | cooldown 300 s | perdido | restaurado |
| `_trades_today` (órdenes enviadas hoy) | `LiveRuntime` | tope diario del perfil de presupuesto | a cero | restaurado |
| `_exploration_used` | `LiveRuntime` | presupuesto de exploración/día | a cero | restaurado como **cota inferior** (exploratorios **cerrados** hoy) |
| `_consecutive_losses` | `LiveRuntime` | multiplicador de racha del presupuesto | ya se sembraba desde `edge_outcomes` admitidos | sin cambio (bajo `legacy` puede sembrarse con filas sintéticas) |
| `day_pnl_pct`, `drawdown_pct` del breaker | `PortfolioState` del proveedor paper | límite de pérdida diaria 2 %, drawdown 10 % | el portafolio paper arranca fresco: día y pico se reinician | **pendiente** (§10) |
| `_peak_equity` del presupuesto | `LiveRuntime` | estado de drawdown del presupuesto | = equity inicial | **pendiente** (§10) |

**Una sola fuente de verdad.** No se añadió ninguna tabla ni columna: el estado se reconstruye de
las tablas `orders` y `fills` que la sesión ya persiste, más `edge_outcomes` para la exploración.
`RiskStateRepository.rebuild(now)` lee órdenes y fills de los runs `paper-live`/`live` de los últimos
2 días (cubre cualquier cooldown configurable hoy) y entrega las filas a la función pura
`rebuild_risk_state`.

**Reglas de reconstrucción**, idénticas a las del motor en marcha:
- una **entrada** es una orden cuyo `signal_id` no empieza por `exit:`, `protective:` ni `flatten:`
  (convención que el runtime usa para nombrar sus órdenes; declarada y probada, no garantía de esquema);
- `entries_today` cuenta órdenes de entrada con ≥ 1 fill cuyo **primer** fill cayó hoy (UTC), una por
  orden aunque haya parciales (el runtime arma el motor una vez por round trip abierto);
- `last_entry_at` es la hora del primer fill de la última entrada con fill por símbolo, de cualquier
  día (el cooldown cruza la medianoche);
- `entry_orders_today` cuenta entradas **creadas** hoy, con o sin fill (el presupuesto cuenta envíos);
- duplicados por `order_id`/`fill_id` cuentan una vez; reconstruir dos veces da lo mismo (probado);
- filas con `filled_at` posterior a `now` se ignoran (reloj que retrocede);
- SQLite devuelve timestamps naive: se leen como UTC (todo escritor del sistema escribe UTC).

**Fail-safe.** `AppState._load_risk_restore` devuelve `RiskRestore.failed(error)` si la base no se
puede leer. El runtime, con una reconstrucción incompleta, **rechaza toda entrada** en la etapa `risk`
con el motivo ("risk state unverified — …") antes de evaluar riesgo; las salidas, stops y
reconciliación no se ven afectadas; `snapshot()["risk_state"]["verified"]` lo expone;
`POST /api/live/risk-state/reconcile` relee el almacén y levanta el bloqueo solo si la reconstrucción
es completa. Un runtime sin almacén (`persist=None`) no tiene nada que restaurar y es completo por
construcción.

**Hallazgo colateral corregido.** Las escrituras de persistencia se lanzaban como tareas
independientes; una orden y su fill, programados seguidos, podían intercalarse en la base y el fill
llegar antes que su orden (clave foránea) y perderse — exactamente lo que la reconstrucción necesita.
Ahora `_save` serializa las escrituras en orden de programación (`_sequenced`, un lock) y la fila de
la orden se escribe **antes** de enrutar fills que llegaron con el acuse (venue que ejecuta al
acusar, stop ya atravesado al colocarse, cierre inmediato). Con el proveedor paper los fills llegan en
la vela siguiente, por lo que en la corrida de 12 h los fills sí se persistieron; el defecto era
latente para fills inmediatos.

## 4. Diseño de validación de filtros del instrumento

**Fuente de verdad.** `InstrumentFilters` (`step_size`, `min_quantity`, `min_notional`, `tick_size`,
`source`): de los filtros del venue cuando una sesión real los cargó (`exchangeInfo`), rellenando con
el instrumento lo que falte; del `Instrument` de `DEFAULT_UNIVERSE` cuando no hay filtros (paper-live,
motor de escenarios, backtester), **etiquetado como regla local**. Nunca se inventan filtros
dinámicos del venue.

**Reglas, en orden:** instrumento conocido; cantidad ≥ 1 lote y múltiplo entero del lote (tolerancia
de redondeo de float, no de un lote); para órdenes que **abren o aumentan** exposición, notional ≥
mínimo juzgado al precio límite (si descansa) o al precio de referencia (último cierre) si cruza; sin
precio de referencia una entrada se **rechaza**, no se asume. Las órdenes que **reducen**
(`reduce_only`, o — en el proveedor — contrarias a la posición mantenida) quedan exentas del mínimo
notional: una posición siempre debe poder cerrarse.

**Dónde se aplica.** (a) `LiveRuntime._build_intent`: cuantiza hacia abajo y **juzga la cantidad ya
cuantizada**; un rechazo es `OrderFilterError` (también `ValueError`, para los llamadores existentes),
que `_submit` convierte en una refusal de la etapa nueva `filters` del embudo (contador
`filter_rejected`, `live.no_trade` con estrategia) — **no** en SAFE_MODE, como ocurría con el
`ValueError` de la Fase 1. (b) `PaperExecutionProvider.submit_order`: misma validación; rechazo
determinista `REJECTED` con el motivo, sin fill, posición ni P&L (probado con velas posteriores). Si
el simulador aún no vio ninguna vela no puede juzgar el notional y lo deja al constructor (documentado
en código y probado).

**Corrección de un diagnóstico de la Fase 1.** `risk/sizing.py` ya rechazaba al dimensionar un tamaño
por debajo de `instrument.min_notional` (`below_min_notional`). La brecha real era el **escalado
posterior** al riesgo (conviction sizing, fracción de exploración, mitad por marea), que podía dejar el
tamaño aprobado bajo el mínimo sin que nadie lo comprobara; la prueba de integración reproduce
exactamente eso (exploración al 5 % del tamaño aprobado) y verifica refusal, sin envío y sesión
RUNNING. No se relajó ningún filtro.

## 5. Diseño y garantías del corte de sesión

**Mecanismo.** `LiveRuntime` acepta `session_deadline` (explícito) o lo calcula al arrancar desde
`live.session_max_hours` (0 = sin límite, el valor por defecto: la sesión 24/7 no cambia).
`POST /api/live/paper-start?max_hours=8` lo fija por sesión sin tocar configuración (validado 0–720).
El deadline se **comprueba dentro del loop** (`_check_deadline`, al principio de cada ciclo, en
cualquier estado, también PAUSED/SAFE_MODE) y se **persiste** en `runs.notes` (JSON) con el run, sin
migración; `snapshot()["session"]` lo expone con el tiempo restante.

**Política al vencer** (probada con reloj inyectable):
1. `HALT_NEW_ORDERS` con actor `session-deadline` (halt de nivel operador: el watchdog no lo levanta);
   la entrada **resting** sin ejecutar se cancela (`deadline_cancelled`); incidente `session_deadline`.
2. Si está plano: reconciliación final, incidente `session_completed`, `STOPPING` → el loop sale y
   finaliza (`STOPPED`), sella la fila del run (`run_stop`) para que el próximo arranque no la reanude.
3. Si hay posición: **no se cancela su stop**; se sigue gestionando (stop, trailing, objetivo, time
   stop) durante `session_wind_down_bars` barras (30 por defecto); vencida la gracia se cierra por el
   mismo camino que un time stop (`_close_position("session deadline")`: stop cancelado primero,
   orden reduce-only a mercado, round trip puntuado como evidencia, `exits_deadline`), **una sola vez**;
   si tras 3 barras la posición sigue abierta se registra `session_deadline_close_unfilled` y el halt
   se mantiene sin reintentos: lo resuelve un operador.
4. En **SAFE_MODE** no se toca nada (ni stop ni cierre); vencida la gracia (medida en tiempo de pared
   cuando no fluyen barras) se para con `session_deadline_in_safe_mode` y la posición queda para el
   operador.
5. `stop()` es idempotente (parar dos veces, parar tras el corte) y seguro desde dentro del loop; el
   corte nunca arranca otra sesión (`start()` tras `STOPPED` falla por máquina de estados).

**Comportamiento por escenario**

| Escenario | Comportamiento | Prueba |
|---|---|---|
| Vencimiento normal, plano | halt → reconcile → STOPPED, run sellado | `test_the_configured_span_becomes_a_deadline…` |
| Posición abierta | gestionada durante la gracia, cerrada después, puntuada, STOPPED | `…managed_through_the_grace_then_closed…` |
| Entrada resting | cancelada; STOPPED | `…resting_entry_is_cancelled_at_the_deadline…` |
| Desconexión del feed | el manejo existente halta entradas; al vencer, para si está plano; con posición **no visible** no envía nada y el halt se mantiene (loop vivo hasta que vuelva el feed o pare un operador) | `…feed_is_down…` (plano) |
| Datos obsoletos | watchdog halta; el corte termina la sesión | `…stale_data…` |
| Excepción inesperada | SAFE_MODE (existente); el corte para con incidente | `…unexpected_exception…` |
| Caída del supervisor | el supervisor **es** el proceso; con `restart: unless-stopped` el contenedor rearranca y `_maybe_resume_paper_realtime` lee `notes`: deadline vencido ⇒ no reanuda y sella; vigente ⇒ reanuda **bajo el mismo deadline**; halt de operador ⇒ no reanuda | `test_session_limits` (decisión pura), `test_paper_session_api` (API+DB) |
| Reinicio del runtime | mismo deadline; vencido ⇒ termina en el primer ciclo sin entradas | `…restart_under_…` |
| Fallo de la base | `_save` traga errores; la sesión termina igual; el sello puede no escribirse (§10) | `…persistence_failing…` |
| Posición y stops al parar | arriba (3–4) | arriba |

**Lo que el código no puede garantizar** (y se dice): si el proceso muere nadie ejecuta el corte
hasta el próximo arranque; una posición paper abierta al morir el proceso no se marca ni se cierra (el
nuevo `PaperExecutionProvider` arranca plano; su P&L no realizado se pierde del registro —
propiedad preexistente de los reinicios); el apagado por `SIGTERM` **no** sella el run (es el contrato
de reanudación tras caída, probado por la API); no se ejecutó ninguna corrida de 8 h.

## 6. Nuevo criterio estadístico de aprobación

Los veredictos viven en `tia.backtest.inference.verdict`, en este orden fijo:

1. `INSUFFICIENT`: trades < 30, sin intervalo, o intervalo no finito (NaN/∞; una guarda explícita
   porque NaN compara falso con todo y se colaba hasta `PROMISING`).
2. `UNFAVOURABLE`: intervalo ajustado enteramente < 0 (superior = 0 exacto ⇒ `INCONCLUSIVE`).
3. `INCONCLUSIVE`: límite inferior ajustado ≤ 0 (**0 exacto no cuenta**), o PF ≤ 1,2 (o NaN/`None`), o
   maxDD ≥ 1 % (o no finito), o **estrés de costos no ejecutado**.
4. `FRAGILE`: media neta ≤ 0 (o NaN) con comisiones ×1,5.
5. `PROMISING_ON_VALIDATION`: lo demás; su motivo dice explícitamente "merece una evaluación posterior
   fuera de muestra; no es una afirmación de rentabilidad".

Nivel: 90 % bilateral, **pre-registrado en la Fase 1 y mantenido**; la regla lee solo el límite
inferior (error unilateral 5 %). No se ajustó ningún umbral a resultado alguno: la corrida sobre las
fixtures sintéticas siguió dando `INSUFFICIENT` en las seis celdas (0–4 trades), como en la Fase 1.

## 7. Tratamiento de dependencia temporal y multiplicidad

**Trades.** El backtester lleva **una pierna a la vez** (`_OpenLeg`): los round trips no se solapan
en el tiempo, pero sí dependen (regímenes persistentes, volatilidad agrupada, rachas). Por eso no se
añadió una prueba de solapamiento: el motor no puede generarlo.

**Block bootstrap circular** (Politis–Romano) de la media neta por trade: bloques de longitud
`round(n^(1/3))` (tasa de Hall–Horowitz–Jing; un valor por defecto defendible, **no** una selección
óptima por serie), inicio uniforme sobre la serie envuelta, 2.000 remuestreos, percentiles, semilla
fija (reproducible y probado). El intervalo i.i.d. se calcula al lado **solo para comparar**. Pruebas:
serie independiente (ambos intervalos contienen la media verdadera, anchuras comparables), serie
AR(1) con φ = 0,7 (el intervalo por bloques es en promedio > 25 % más ancho sobre 8 semillas), serie
constante, serie con mitades opuestas, n < 2 ⇒ sin intervalo.

**Multiplicidad.** La familia son los candidatos (estrategia × horizonte) juzgados sobre la misma
validación; el veredicto lee el intervalo al nivel **Bonferroni** `1 − 0,10/k` (válido bajo cualquier
dependencia; conservador). Las variantes de costos de un candidato son chequeos de robustez, no
candidatos. El registro guarda `family_size`, `adjusted_level`, los dos intervalos por celda y el
número de variantes probadas. Con k = 6 (tres estrategias × dos horizontes con celdas válidas), el
nivel ajustado es 0,9833.

**Lo que esto no hace** (bloqueos declarados para el uso inferencial del harness): no elimina el
sesgo de selección de elegir el mejor de k (acota la tasa de falsos positivos de la etiqueta); no
estima la probabilidad de sobreajuste (PBO) ni el Sharpe deflactado; con < 30 trades por celda
devuelve `INSUFFICIENT`, con lo que **en las fixtures no hay inferencia alguna**; el block bootstrap no
corrige un sesgo de muestreo de los datos ni la no estacionariedad entre particiones.

## 8. Protección del holdout y limitaciones restantes

`--unlock-holdout` era una bandera. Ahora: cada cómputo del holdout pasa por `HoldoutLedger.check`
(dataset por hash de contenido, configuración congelada por hash de criterios + estrategias +
horizontes + particiones + semilla + simulador + **código fuente de `tia/strategy`**) y, si procede,
se registra en un JSONL append-only (`--holdout-log`, por defecto `data/runtime/holdout_access.jsonl`)
con variantes probadas, veredictos, commit y limpieza del árbol. Una repetición bajo la **misma**
configuración se rechaza siempre (código de salida 2, nada computado); una reapertura bajo
configuración distinta exige `--holdout-reopen-reason`, que queda escrito. Protocolo documentado en
§7.1 del documento de la Fase 1: congelar todo, abrir una vez, y cualquier cambio motivado por el
resultado exige un nuevo período fuera de muestra.

Limitaciones: el libro es un archivo borrable; el hash del dataset no impide evaluar un recorte
distinto de los mismos datos; nada detecta un holdout calculado por otros medios. En esta fase **no se
desbloqueó ni calculó** ningún holdout (ni siquiera sobre las fixtures; la prueba de integración solo
ejercita el rechazo). El libro real de `data/runtime` no existe.

## 9. Pruebas ejecutadas, comandos y resultados exactos

Entorno: Python 3.11.15, pytest 9.1.1, `PYTHONPATH=packages/tia/src`, sin red, bases SQLite temporales.
`scripts/verify.sh` **no** se ejecutó (levanta el servidor para el smoke); se ejecutaron sus pasos
equivalentes de lint y pruebas.

| Comando | Resultado |
|---|---|
| `.venv/bin/ruff check packages tests scripts` | All checks passed (alcance del proyecto; `ruff check .` conserva 6 avisos preexistentes en `infra/migrations/`) |
| `pytest tests/unit` | 1311 recogidos, exit 0, 78 s (1232 de la Fase 1 + 79 nuevos); 6 warnings preexistentes de pyjwt. Una primera pasada falló `test_scope_boundary::test_the_decision_path_never_reads_the_wall_clock` por un `datetime.now()` en `backtest/holdout.py`; se movió la lectura de reloj al script y la suite volvió a pasar completa |
| `pytest tests/integration` | 200 recogidos, exit 0, 126 s (163 + 37 nuevos) |
| `pytest tests/property` | 31 recogidos, exit 0, 28 s |
| `pytest tests/failure` | 12 recogidos, exit 0, 5 s |
| `pytest tests/adversarial` | 16 recogidos, exit 0, 8 s |
| `pytest tests/e2e` | 8 recogidos, exit 0, 83 s |
| `python scripts/strategy_experiment.py --fixtures data/fixtures --symbol BTC-USD --timeframes 1m,5m,15m --fee-multipliers 1.0,1.5 --extra-slippage-bps 0 --holdout-log <scratchpad> --json <scratchpad>` | exit 0 en 87 s; 12 variantes; 6 veredictos `INSUFFICIENT` (0–4 trades); holdout SEALED; libro no creado |

Regresión específica (dentro de las suites): EV (`test_expected_value_convention`, 13), procedencia
(`test_evidence_policy_config`, `test_scoreboard`, política en `test_live_runtime`), simulador
(`test_paper_execution`, `test_order_filters`), scoreboard, riesgo (`test_risk_engine`,
`test_risk_restore`, `test_risk_state_persistence`), harness (`test_inference`, `test_partitions`,
`test_holdout_ledger`, `test_strategy_experiment_script`, `test_resample`).

Verificaciones de seguridad: `Settings()` por defecto sigue en `mode=paper`, `is_simulation_only=True`,
`live.enabled=False`, `use_testnet=True`, `max_live_capital=0.0`, `mm.real_money=False`; el diff de
`core/config.py` añade solo `session_max_hours` y `session_wind_down_bars` (y el `ev_evidence_policy`
de la Fase 1); `.env` no existe en este entorno y no se leyó ni escribió ningún archivo de entorno;
barrido de patrones de secretos sobre todo el diff y los archivos nuevos: sin aciertos; ningún endpoint
privado ni credencial en ninguna ruta de código nueva.

## 10. Fallos encontrados y pendientes

Encontrados y corregidos en esta fase:
- Carrera orden/fill en la persistencia (§3). Corregido con escrituras secuenciadas y orden antes que
  fill.
- Un `ValueError` del constructor de intenciones (cuantización a cero, mínimo del venue) ponía la
  sesión en SAFE_MODE; ahora es una refusal contada.
- NaN en el veredicto se colaba hasta `PROMISING`; guardado.
- El diagnóstico de la Fase 1 sobre `min_notional` era incompleto (el motor de riesgo sí lo comprobaba
  al dimensionar); corregido aquí y en el diseño.

Pendientes (no resueltos, documentados, sin solución improvisada):
- **Pérdida diaria y drawdown no sobreviven al reinicio.** Los breakers del motor leen
  `PortfolioState` del proveedor paper, que arranca fresco (día y pico = equity inicial); el pico del
  presupuesto también. Restaurarlos exige sembrar `day_start_equity`/`peak_equity` desde el registro de
  P&L intradía (o persistir puntos de equity de la sesión), una decisión de diseño sobre qué
  "día" y qué "pico" cuentan tras un reinicio que no se tomó aquí. Hasta entonces, tras un reinicio el
  límite de pérdida diaria se mide desde la equity de arranque.
- **Exploración restaurada como cota inferior**: una entrada exploratoria abierta al reiniciar no
  cuenta hasta cerrarse (no hay persistencia de la decisión de exploración; añadirla sería una
  segunda fuente de verdad).
- **Sello del run si la base falla justo al terminar**: `run_stop` se pierde y el próximo arranque
  vería el run como interrumpido; con deadline vencido no lo reanuda (decisión por `notes`), con
  deadline vigente lo reanudaría. Pre-existente y acotado.
- **Posición abierta con feed caído al vencer**: la sesión queda en HALT con el loop vivo, sin cierre
  (no se envía nada a un venue que no se ve); requiere operador. Diseñado, no probado.
- **`_trades_today` cuenta órdenes enviadas** (semántica preexistente del presupuesto) y el motor
  cuenta round trips abiertos; dos contadores con dos semánticas, ambos restaurados con la suya.
- **Frontend** no muestra los campos nuevos (`risk_state`, `session`, etapa `filters`); la API es
  compatible hacia atrás (claves añadidas).
- **Lint fuera del alcance del proyecto**: 6 avisos preexistentes de orden de imports en
  `infra/migrations/` (no tocados).
- **El VPS** sigue con la imagen anterior a la Fase 1; nada de 1.1 está desplegado.

## 11. Riesgos residuales por severidad

| Severidad | Riesgo |
|---|---|
| Alta | Un reinicio sigue reabriendo el límite de pérdida diaria y el drawdown (§10); con un día ya perdido al 2 %, tras reiniciar el breaker no actúa hasta volver a perder 2 % desde la equity de arranque. |
| Alta | Nada de 1.1 corre en el VPS; la próxima validación con la imagen actual no tendrá ni restauración ni corte. |
| Media | La clasificación entrada/salida por prefijo de `signal_id` es una convención; una orden nombrada fuera de ella contaría mal. Probada, no garantizada por esquema. |
| Media | El corte depende de que el proceso viva; la supervisión externa (restart de Docker + decisión al arrancar) no se ejercitó aquí. |
| Media | Bajo `ev_evidence_policy=legacy` la racha de pérdidas inicial puede sembrarse con filas sintéticas (preexistente). |
| Baja | El libro del holdout es borrable; el candado es procedimental. |
| Baja | Bonferroni es conservador: con muchas celdas el intervalo ajustado rara vez excluirá cero; es el coste elegido frente a inflar falsos positivos. |
| Baja | El proveedor paper omite el chequeo de notional antes de la primera vela (documentado); el constructor de intenciones lo cubre. |

## 12. Qué no puede concluirse sobre rentabilidad

Nada. Esta fase no evaluó ninguna estrategia: el único dato que pasó por el harness son fixtures
sintéticas y todas las celdas quedaron `INSUFFICIENT`. Las pruebas verifican aritmética, políticas,
máquinas de estado, persistencia y el simulador; que pasen no dice nada sobre ventaja de mercado.
Que el corte, los filtros y la restauración funcionen hace la próxima simulación más segura y más
interpretable; no la hace rentable. `PROMISING_ON_VALIDATION` no significa rentable ni autoriza
dinero real, y ninguna celda lo ha obtenido.

## 13. Pasos necesarios para una posterior autorización de despliegue

No se solicita aquí; son los pasos que harían falta, en orden:
1. Revisión independiente del diff de 1.1 (este informe + `git diff`), en especial `runtime/live.py`.
2. Decidir el diseño pendiente de pérdida diaria/pico tras reinicio (§10) o aceptar explícitamente la
   limitación para la siguiente validación.
3. Commit y push por el usuario (separando Fase 1 y Fase 1.1), construcción de imagen y despliegue con
   `scripts/deploy.sh` en el VPS **con autorización explícita**; no requiere migración de base.
4. Verificar en el VPS, sin secretos: configuración efectiva, `session_max_hours=0` salvo decisión,
   `/api/live` con `risk_state.verified=true` tras arrancar, y la decisión de `ev_evidence_policy`.
5. Ejecutar entonces la validación de 8 h con `?max_hours=8`, con el protocolo de la Fase 2 (datos
   reales, supervisión, chequeos periódicos) y el informe de 15 secciones.
