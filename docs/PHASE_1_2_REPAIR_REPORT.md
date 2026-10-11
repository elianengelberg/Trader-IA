# Trader-IA — Fase 1.2: reparación de bloqueos críticos y pruebas adversariales

Entorno de trabajo: checkout de esta sesión en `/home/user/Trader-IA` (mismo repositorio y rama que el
VPS; el VPS no se tocó). Todo es simulación en papel: nada de esta fase toca dinero real, credenciales,
activación live ni despliegue. Sin commits ni push. Sin corrida prolongada ni prueba de 8 h.

Punto de partida: la auditoría adversarial independiente de las Fases 1 y 1.1 (entregada como texto,
sin documento), cuyos bloqueos críticos eran F1, F2, F3/F4, F5 y F8, más F7 como riesgo del corte.

## Estado por bloqueo (resumen; el detalle y el veredicto razonado están en §9)

| Bloqueo | Qué era | Veredicto |
|---|---|---|
| F1 | el proveedor paper solo cancelaba por `order_id`; el runtime cancelaba por `client_order_id`, el error se tragaba y el stop "cancelado" seguía vivo | **RESUELTO** |
| F2 | cierre por deadline y time stop en el mismo ciclo enviaban dos salidas; la posición quedaba del lado contrario | **RESUELTO** |
| F3 | pérdida diaria, drawdown y pico de equity se reiniciaban en cada arranque | **RESUELTO** (cuenta paper) |
| F4 | el P&L acumulado caía a 0.0 ante un error de base y la reconciliación levantaba el bloqueo sin mirar la cuenta | **RESUELTO** |
| F5 | dos arranques concurrentes construían dos runtimes sobre una cuenta | **RESUELTO** (dentro de un proceso; límite multiproceso documentado) |
| F8 | la fila del run se escribía después de arrancar el loop | **RESUELTO** |
| F7 | `resume` y el watchdog podían levantar el halt del deadline | **RESUELTO** |
| F6 | el runtime live (dinero real) no recibe restauración ni deadline | **NO ABORDADO** — fuera del alcance por mandato (sin cambios en activación live) |

---

## 1. Estado de Git al inicio y al final

| | Inicio de la fase (2026-10-10T17:58:56Z) | Final (2026-10-10T18:38:21Z) |
|---|---|---|
| Rama | `claude/algo-trading-simulation-platform-ngf7xo` | igual |
| HEAD | `ab68d1c128a7181f54e1e79d3d7f37261365d821` | igual (sin commits; `git stash list` vacío; reflog sin entradas nuevas) |
| `git status --short` | 48 líneas: 20 M + 28 ?? (Fases 1 y 1.1 + informes previos) | 56 líneas: 20 M + 36 ?? (los 28 anteriores + 7 archivos nuevos de 1.2 + este informe) |
| Huella del `git diff` (sha256/16) | `0278e0e556ecd44d` (idéntica a la final de la Fase 1.1) | `0513d698ab970a2b` |
| Huella del conjunto de no rastreados (sha256/16 de la lista de sha256 por archivo) | `2e6fae89d5e73d69` | `0ee6bbd8e809eba1 (excluido este informe, que no puede contener su propia huella)` |
| `git diff --stat` | 20 files changed, 1227 insertions(+), 93 deletions(-) | 20 files changed, 2072 insertions(+), 190 deletions(-) |

Fórmulas: `git diff | sha256sum | cut -c1-16` y
`git status --porcelain | grep '^??' | awk '{print $2}' | sort | xargs sha256sum | sha256sum | cut -c1-16`.

**Prueba de que las Fases 1 y 1.1 no se perdieron.** Al inicio se guardó en el scratchpad de la sesión
una copia de los 20 archivos rastreados modificados (`tracked_start/`), el parche completo
(`diff_start.patch`, cuyo sha256 coincide con la huella `0278e0e556ecd44d`) y los 28 no rastreados
(`untracked_start/`). Comparación byte a byte con el árbol final:

- **Los 28 archivos no rastreados de las Fases 1 y 1.1 son idénticos** (incluidos `risk/restore.py`,
  `execution/filters.py`, `runtime/session_limits.py`, `backtest/{holdout,inference,partitions,resample}.py`,
  `scripts/strategy_experiment.py`, los 17 archivos de prueba de 1 y 1.1 y los cinco informes previos, entre
  ellos `docs/PHASE_1_1_HARDENING_REPORT.md`).
- De los 20 rastreados, **14 son idénticos** a su versión de inicio (`.env.example`,
  `docker-compose.prod.yml`, `core/config.py`, `domain/signals.py`, `economics/expected_value.py`,
  `learning/scoreboard.py`, `risk/__init__.py`, `risk/engine.py`, `runtime/engine.py`, `strategy/engine.py`,
  `strategy/fusion.py`, `tests/integration/test_live_runtime.py`, `tests/unit/test_paper_execution.py`,
  `tests/unit/test_scoreboard.py`).
- **6 se ampliaron** en esta fase: `runtime/live.py`, `api/state.py`, `api/app.py`, `execution/paper.py`,
  `persistence/repositories.py`, `persistence/__init__.py` (delta 1.2 total +893/−145 líneas). Las líneas de 1/1.1
  sustituidas en ellos son las que esta fase tenía que corregir: en `live.py` el cuerpo de
  `_close_position` (ahora `_close_position` + `_submit_exit`), `emergency_flatten` y `_cancel_all_open`
  (pasan por `_submit_exit`/`_cancel`), el bloque de cancelación de `_check_deadline`, la compuerta de
  `_process_bar` (`risk_state_verified` → diccionario de bloqueos) y `_apply_risk_restore` (usa los
  bloqueos); en `state.py` `start_paper_realtime` (dividido en envoltorio con candado + cuerpo; la fila del
  run antes del arranque; la restauración de cuenta sustituye a `_carried_session_pnl`, eliminado),
  `reconcile_risk_state` (delega en `reconcile_session_state`); en `app.py` la ruta
  `risk-state/reconcile` (delega); en `paper.py` `cancel_order`/`get_order` (resuelven ambos ids).
  Ningún comportamiento de 1.1 se revirtió: **todas las pruebas de 1 y 1.1 siguen pasando sin cambios en sus
  archivos** (el único ajuste de texto fue mantener la palabra "unverified" en el mensaje de rechazo que
  `test_risk_state_persistence` espera).

## 2. Hallazgos: defecto, causa, corrección y prueba de que la prueba lo detecta

Para cada bloqueo se ejecutaron las pruebas nuevas **también contra el árbol previo a la fase** (una copia
del paquete `tia` con las seis versiones de inicio y sin `portfolio/account_journal.py`, seleccionada con
`-o pythonpath=<copia>`; salida completa en `prefix_results.txt` del scratchpad). Una prueba que no
falla sobre el código viejo no cuenta como evidencia; las que pasan en ambos árboles se señalan.

### F1 — cancelaciones que mentían (CRÍTICO)

- **Defecto.** `PaperExecutionProvider.cancel_order(order_id)` solo resolvía `order_id`; el runtime
  cancelaba por `client_order_id`; el `DuplicateOrderError("unknown order")` se tragaba y el runtime daba el
  stop (o la entrada en reposo) por cancelado. El stop seguía en el motor y podía ejecutarse después del
  cierre: doble fill y posición invertida. `FakeExecution` de `test_live_runtime.py` acepta ambos ids, por
  eso ninguna prueba de 1/1.1 lo vio.
- **Corrección.** Proveedor: `_resolve(order_ref)` acepta `order_id` o `client_order_id` en `get_order` y
  `cancel_order`, y la cancelación retira la orden de `_resting` por su `order_id` real. Runtime: un único
  `_cancel(order_ref, purpose)` que cree **solo la respuesta del venue** (estado terminal); si el venue
  falla o devuelve una orden aún viva: contador `cancel_failures`, bloqueo de entradas `orders_unverified`,
  `HALT_NEW_ORDERS`, incidente, y el runtime **sigue rastreando** la orden. `_cancel_protective()` devuelve
  `False` en ese caso y `_close_position` **no envía** un cierre a mercado sobre un stop vivo. Pasan por
  `_cancel`: expiración/polvo de la entrada en reposo (`_manage_resting`), el deadline, `_cancel_all_open`
  y `emergency_flatten`.
- **Pruebas** (`tests/integration/test_paper_cancellations.py`, 7, motor paper real): cancelar por
  cualquiera de los dos ids y que la orden no se ejecute después; el cierre cancela el stop en el motor y el
  stop viejo no puede dispararse; el trailing deja exactamente un stop; la entrada expirada queda
  `cancelled` en el motor y no se ejecuta después; el deadline cancela la entrada en reposo; el flatten de
  emergencia cancela el stop y cierra por el motor; un cancel que el venue no confirma bloquea entradas y
  mantiene el stop rastreado (único test que parchea el motor: `cancel_order` lanza).
- **Contra el árbol previo: 7 de 7 fallan**, con el síntoma original: "one stop resting, found 3"; la
  entrada expirada sigue `acknowledged` en vez de `cancelled`; "no close on top of a live stop"; `2 == 1`
  órdenes de salida.

### F2 — dos salidas en el mismo ciclo (CRÍTICO)

- **Defecto.** El cierre por deadline y el time stop (o el objetivo) del mismo ciclo enviaban cada uno
  una orden de mercado reduce-only; el motor paper ejecuta en la vela siguiente, la segunda no veía la
  primera y la posición quedaba abierta del lado contrario.
- **Corrección.** Un único camino de salida, `_submit_exit`, bajo `asyncio.Lock` con registro
  `_pending_exit`; `_poll_pending_exit` lee el estado de la salida en vuelo al inicio del ciclo, antes de
  gestionar la posición y antes de cualquier nueva salida. Mientras hay una salida pendiente no se envía
  otra (`exits_skipped_pending`). Resultados creídos solo como los reporta el venue: rechazo → incidente
  `exit_rejected` y la posición conserva su protección; parcial → sigue pendiente hasta estado terminal;
  cancelada/expirada con resto → incidente `exit_unfilled` y el siguiente disparador reintenta una vez;
  resultado desconocido (`ReconciliationError`) → `_resolve_unknown`; irresoluble → bloqueo
  `position_unverified` + halt. `_manage_position` bloquea y detiene entradas si el venue tiene una posición
  que el runtime no rastrea o del lado contrario, y levanta el bloqueo solo cuando el venue coincide.
- **Pruebas** (`tests/integration/test_exit_guard.py`, 8): deadline + time stop en el mismo ciclo envían
  una salida y el libro termina plano; deadline + objetivo; dos callbacks concurrentes; salida parcial;
  salida rechazada; salida desconocida e irresoluble bloquea hasta que el venue coincide; salida
  desconocida resuelta como presente se adopta y no se reenvía; posición no rastreada bloquea y no envía nada.
- **Contra el árbol previo: 8 de 8 fallan**; las dos primeras con la evidencia exacta del hallazgo:
  `['exit:session-deadline:13', 'exit:time-stop:14']` y `['exit:session-deadline:13', 'exit:target-reached:14']`.

### F3 / F4 — la cuenta no sobrevivía al reinicio (CRÍTICO)

- **Defecto.** El motor paper arrancaba fresco (`day_start_equity` y `peak_equity` = capital inicial), así
  que tras reiniciar en un día ya perdido al 2 % el breaker diario no actuaba hasta volver a perder 2 % desde
  la equity de arranque, y el drawdown se medía desde cero. El P&L acumulado se tomaba del registro de
  outcomes (`_carried_session_pnl`) y **caía a 0.0 ante un error de base**; la reconciliación del estado de
  riesgo levantaba el bloqueo contando órdenes, sin mirar la cuenta.
- **Corrección.** Diario de eventos de cuenta y reconstrucción pura (diseño en §3); el motor se siembra
  con `restore_portfolio` **antes** de construir el runtime; una reconstrucción incompleta no siembra nada
  **y bloquea entradas** (`account_state`) hasta que `POST /api/live/reconcile` (riesgo + cuenta + posición
  del venue) la verifique; `_carried_session_pnl` eliminado. Demostración ejecutable sin pytest
  (`f3_demo.py` del scratchpad, misma entrada en ambos árboles, un día con −2,65 %):

  | Árbol | Qué lee el motor al reiniciar | Breaker diario |
  |---|---|---|
  | previo | `+0.00 %` (día abre en 10 000,00; equity 10 000,00) | **permite** una entrada nueva |
  | reparado | `−2.65 %` (día abre en 10 000,00; equity 9 735,10) | **rechaza**: `daily loss -2.65% breached the 2.00% limit` |

- **Pruebas.** Unitarias (`tests/unit/test_account_journal.py`, 11): diario vacío, replay por el modelo del
  motor, pierna abierta con precio medio/comisiones/plan, pico y apertura del día UTC, reinicio al día
  siguiente, ajustes, idempotencia con duplicados, salida parcial, cross-check contra `fills`, restauraciones
  `failed`/`empty`, otros símbolos ignorados. Integración (`tests/integration/test_account_restore.py`, 12,
  SQLite temporal + runtime + motor paper real): pérdida diaria que sigue rechazando tras reiniciar (vía
  `RiskEngine` **y** vía runtime: 0 órdenes en 120 velas con el rechazo "daily loss"); drawdown que
  sobrevive; reinicio antes y después de medianoche UTC (pico conservado, día rodado); posición abierta
  restaurada, re-protegida, cerrable y puntuada; entrada en reposo de una sesión muerta marcada huérfana;
  salida pendiente al reiniciar; fills parciales idénticos en cada reconstrucción; base ilegible al
  arrancar bloquea y nunca sustituye capital base; escritura perdida del diario → incompleta y bloqueo;
  caída de base durante una escritura no finge haberla guardado; filas de fills sin eventos → cuenta
  inconsistente; lado de la posición en desacuerdo con el motor → bloqueo.
- **Contra el árbol previo:** los dos archivos no se recogen (`ModuleNotFoundError: tia.portfolio.account_journal`,
  `ImportError: AccountJournalRepository`): el mecanismo no existía. La evidencia del defecto es la tabla
  anterior.

### F5 — arranques concurrentes (CRÍTICO)

- **Defecto.** Dos `POST /api/live/paper-start` concurrentes pasaban ambos la comprobación "ya activa"
  (el cuerpo tiene esperas de base entre la comprobación y la asignación) y construían dos runtimes sobre
  una cuenta; la aplicación recordaba solo el último.
- **Corrección.** `AppState._session_lock` (`asyncio.Lock`) envuelve `start_paper_realtime` y `arm_live`;
  el segundo espera y es rechazado con "already active".
- **Pruebas** (`tests/integration/test_session_start_atomicity.py`, sobre `AppState` real con SQLite
  temporal): dos solicitudes simultáneas → una aceptada, una rechazada, un loop arrancado, una fila sin
  sello; **la carrera reproducida sin el candado** (`_start_paper_realtime_locked` dos veces): dos loops,
  dos filas, uno huérfano; un segundo arranque secuencial se rechaza y tras `stop` el siguiente crea un run
  nuevo con el anterior sellado.
- **Contra el árbol previo:** la simultánea falla con `assert 2 == 1` (ambas aceptadas; dos sesiones). La
  secuencial pasa también en el árbol previo (la comprobación secuencial ya existía): no es evidencia del
  defecto, solo de no regresión.

### F8 — la fila del run después del loop (CRÍTICO)

- **Defecto.** `runtime.start()` se ejecutaba antes de `RunRepository.create`; un fill del primer ciclo
  referenciaba un run que la base no conocía (la clave foránea lo rechaza) y un arranque fallido no dejaba
  rastro.
- **Corrección.** La fila (con el deadline en `notes`) y el marcado de órdenes huérfanas de sesiones
  anteriores se escriben **antes** de `start()`; si la escritura falla no arranca nada
  (`LiveActivationError: the session's run row could not be persisted; nothing was started`); si `start()`
  falla, la fila se sella (`stopped_at`) con `notes.note = "start_failed: …"` para que un arranque posterior
  ni la reanude ni reconstruya sobre ella; un reintento crea su propia fila.
- **Pruebas** (mismo archivo): fallo al crear la fila → nada arranca, 0 filas, reintento exitoso; fallo
  al arrancar el runtime → fila sellada con `start_failed`, sin sesión, reintento con fila nueva; la fila
  existe en el instante en que `start` es llamado y un fill persistido desde dentro de `start` (por el
  propio `_save` del runtime) llega a la tabla `fills` con ese `run_id`, mientras que el mismo fill para un
  run desconocido es rechazado por `IntegrityError`.
- **Contra el árbol previo:** "the row was there when the loop started" es `False`; el fallo de la fila
  se propaga como `RuntimeError` crudo con el loop ya arrancado; el fallo de `start` deja 0 filas.

### F7 / Fase E — el deadline no se deshace

- **Corrección.** `resume()` lanza `ValueError("… cannot be resumed")` durante el wind-down; la
  auto-curación del watchdog no vuelve a `RUNNING` si la sesión está venciendo; `_check_deadline` vuelve a
  poner `HALT_NEW_ORDERS` en cada ciclo si algo lo levantó y reintenta la cancelación de la entrada en reposo
  por `_cancel`; `_process_bar` rechaza entradas tras el deadline aunque la máquina esté en `RUNNING`; la
  sesión termina solo cuando está plana **y** no hay salida pendiente (`_poll_pending_exit` antes de
  decidir); con el feed caído y posición abierta no se envía nada y la posición se queda.
- **Pruebas** (`tests/integration/test_deadline_hardening.py`, 5). **Contra el árbol previo: 4 de 5
  fallan** (`DID NOT RAISE ValueError`; el watchdog deja la máquina en `RUNNING`; `2 == 1` salidas con el
  feed caído; la salida pendiente se duplica al vencer). La quinta
  (`test_no_entry_is_taken_after_the_deadline_even_if_the_machine_is_running`) es defensa en profundidad y
  pasa también en el árbol previo porque en ese escenario la sesión plana termina de inmediato.

### Encontrado durante la fase (no estaba en la auditoría)

- **Escrituras pendientes al parar.** Una prueba de reinicio falló porque el fill de salida estaba en la
  tabla `fills` y aún no en el diario: las escrituras se secuencian en tareas y `stop()` no las esperaba, así
  que un proceso que para justo después de un fill podía morir con el evento sin escribir (misma clase que
  F3/F4: el siguiente arranque vería la cuenta incompleta y bloquearía). Se añadió
  `LiveRuntime.flush_persistence(timeout_seconds=10)` (espera acotada de las escrituras en vuelo) y `stop()`
  lo llama tras `_finalize_stop()`. Las pruebas de reinicio esperan con él en vez de dormir.
- **Lectura de reloj de pared** en `account_journal.portfolio_state()` (`datetime.now()` como respaldo),
  detectada por `tests/unit/test_scope_boundary.py` en la primera pasada completa; se marca con el tiempo del
  último evento del diario o no se marca. Misma lección que en 1.1.

## 3. Decisiones de diseño de la restauración de cuenta

1. **Fuente de verdad: un diario de eventos de cuenta, no un saldo guardado.** Se reutiliza la tabla
   `events` (sin migración) con cuatro tipos: `account.fill` (cada fill, escrito desde `_on_fill` justo
   después de la fila de `fills`), `account.adjustment` (funding devengado, liquidación), `account.mark`
   (precio/cash/posición/equity: cada vela mientras hay posición, cada 15 velas en plano y en la primera vela
   de cada día UTC) y `account.plan` (stop, objetivo, tipo de stop y creencias de entrada cuando cambian).
   Idempotentes por `idempotency_key = tipo:clave` (índice único; un evento reentregado es un no-op);
   `event_id` determinista desde la clave.
2. **Reconstrucción = replay puro por el modelo del motor.** `fold_account_events` ordena por
   `occurred_at, sequence, event_id` y aplica los fills y marcas a un `PortfolioState` con
   `apply_fill`/`mark`, el mismo código que el motor usa en vivo: así el día UTC, la equity de apertura del
   día, el pico y el drawdown salen de la misma aritmética, no de una segunda implementación. Reglas: el día
   actual es el UTC de `now`; `day_start_equity` es la equity en la primera marca de ese día (o la equity
   arrastrada si el reinicio cae en un día nuevo: el día abre al reiniciar, en 0 %); el pico es el máximo
   de equity a lo largo del replay (los pisos anteriores al journal no se inventan).
3. **Cross-check contra la tabla `fills`.** Número de fills, cantidad neta y comisiones deben coincidir;
   si no, la reconstrucción es `complete=False` con el motivo. Una escritura perdida se vuelve visible en
   lugar de silenciosa.
4. **Nunca degradar a capital base en silencio.** Si la reconstrucción falla o es incompleta, el motor
   queda en capital base **y el runtime rechaza entradas** (bloqueo `account_state`, visible en
   `/api/live` → `entry_blocks` y `account_state`) hasta que un operador reconcilie
   (`POST /api/live/reconcile`), que exige: reconstrucción de riesgo completa, reconstrucción de cuenta
   completa y posición del venue igual a la del diario e igual a la pierna rastreada. Salidas, stops y
   reconciliación nunca se bloquean. El P&L realizado arrastrado sale de la reconstrucción
   (`realized_pnl`); no hay respaldo a 0.0.
5. **Posición abierta al reiniciar.** Se adopta como round trip rastreado (`restored: true`) con precio
   medio, comisiones de la pierna abierta, plan (stop/objetivo/tipo) y creencias de entrada; la lógica normal
   la vuelve a proteger con un stop y la puntúa al cerrar. El time stop no conoce la edad de la pierna
   (`position_opened_bar = None`), así que no la cierra por tiempo: decisión explícita frente a inventar una
   edad. Si el diario no trae creencias, la pierna es gestionable y cerrable pero las entradas nuevas esperan
   a una persona.
6. **Órdenes de sesiones muertas.** Al arrancar, toda orden no terminal de otro run de sesión se marca
   `cancelled` con motivo "orphaned": un proceso reiniciado tiene un motor nuevo y esa orden ya no existe en
   ningún sitio. Se hace en la misma transacción que la fila del run.
7. **Alcance.** Los runs `paper-live` y `live` comparten el diario de cuenta por diseño, pero el runtime
   live (dinero real) no fue tocado (F6 sigue abierto por mandato).

## 4. Archivos modificados y nuevos

Nuevos (fuente y pruebas):

| Archivo | Líneas | Motivo |
|---|---|---|
| `packages/tia/src/tia/portfolio/account_journal.py` | 403 | tipos de evento y payloads, `AccountRestore`, `fold_account_events` (replay puro), `cross_check` |
| `tests/unit/test_account_journal.py` | 191 | 11 pruebas de la reconstrucción |
| `tests/integration/test_paper_cancellations.py` | 261 | 7 pruebas F1 (motor paper real) |
| `tests/integration/test_exit_guard.py` | 273 | 8 pruebas F2 |
| `tests/integration/test_deadline_hardening.py` | 128 | 5 pruebas F7/E |
| `tests/integration/test_account_restore.py` | 605 | 12 pruebas F3/F4 (SQLite temporal) |
| `tests/integration/test_session_start_atomicity.py` | 281 | 6 pruebas F5/F8 (`AppState` real) |

Modificados en esta fase (delta respecto al inicio de la fase; el `git diff --stat` global incluye 1 y 1.1):

| Archivo | Delta 1.2 | Qué cambia |
|---|---|---|
| `packages/tia/src/tia/runtime/live.py` | +599 / −92 | `_cancel`/`_cancel_protective`; `_submit_exit`/`_poll_pending_exit`/`_close_position`; bloqueos de entrada (`_blocks`, `entry_blocks`, compuerta en `_process_bar`); diario de cuenta (`_journal*`), `_apply_account_restore`, `restore_account_state`, `account_state_report`; deadline (re-halt, `resume` rechazado, watchdog); `_manage_position` (posición no rastreada/opuesta); `flush_persistence` y `_persist_tasks`; contadores nuevos; claves `entry_blocks`, `pending_exit`, `account_state` en el snapshot |
| `packages/tia/src/tia/api/state.py` | +134 / −45 | `_session_lock`; `start_paper_realtime` → `_start_paper_realtime_locked` (restauración de cuenta, siembra del motor, fila del run + órdenes huérfanas antes de `start`, sello `start_failed`); `arm_live` bajo el candado; `_load_account_restore`; `reconcile_session_state`; `_persist` escribe `account_event`; `_carried_session_pnl` eliminado |
| `packages/tia/src/tia/api/app.py` | +11 / −4 | `POST /api/live/reconcile`; `risk-state/reconcile` delega en la reconciliación completa |
| `packages/tia/src/tia/execution/paper.py` | +40 / −4 | `_resolve` (ambos ids) en `get_order`/`cancel_order`; `restore_portfolio` |
| `packages/tia/src/tia/persistence/repositories.py` | +107 / −0 | `RunRepository.annotate`; `AccountJournalRepository.rebuild`/`orphan_open_orders` |
| `packages/tia/src/tia/persistence/__init__.py` | +2 / −0 | exporta `AccountJournalRepository` |

Sin cambios de configuración, umbrales estadísticos, esquema de base ni frontend. `Settings()` por
defecto sigue en `mode=paper`, `is_simulation_only=True`, `live.enabled=False`, `use_testnet=True`,
`max_live_capital=0.0`, `mm.real_money=False` (verificado al final de la fase).

## 5. Pruebas ejecutadas y resultados

Entorno: Python 3.11.15, pytest 9.1.1, `PYTHONPATH=packages/tia/src`, sin red, bases SQLite temporales,
`-p no:cacheprovider`. `scripts/verify.sh` **no** se ejecutó (levanta el servidor para el smoke y escribe
`data/runtime/verify_passed.json`); se ejecutaron sus pasos equivalentes. `data/runtime/verify_passed.json`
conserva su fecha anterior (2026-10-07).

Pruebas nuevas (código reparado):

| Archivo | Resultado |
|---|---|
| `tests/integration/test_paper_cancellations.py` | 7 passed (0,8 s) |
| `tests/integration/test_exit_guard.py` | 8 passed (0,7 s) |
| `tests/integration/test_deadline_hardening.py` | 5 passed (0,7 s) |
| `tests/unit/test_account_journal.py` | 11 passed (0,1 s) |
| `tests/integration/test_account_restore.py` | 12 passed (13,0 s) |
| `tests/integration/test_session_start_atomicity.py` | 6 passed (3,1 s) |

Las mismas 49 pruebas contra el árbol previo a la fase: 7 + 8 + 5 fallan en bloque (F1, F2, F7 con
una excepción explicada en §2), 5 de 6 fallan en atomicidad, y los 23 tests de cuenta no se recogen porque
el módulo no existía.

Suites completas sobre el código final (comando: `.venv/bin/python -m pytest tests/<suite> -q -p no:cacheprovider -o addopts="--strict-markers --strict-config"`):

| Comando | Resultado |
|---|---|
| `.venv/bin/ruff check packages tests scripts` | All checks passed |
| `pytest tests/unit` | 1322 passed, exit 0, 81 s (1311 de la Fase 1.1 + 11 nuevos); 6 warnings preexistentes de pyjwt |
| `pytest tests/integration` | 238 passed, exit 0, 125 s (200 + 38 nuevos) |
| `pytest tests/property` | 31 passed, exit 0, 22 s |
| `pytest tests/failure` | 12 passed, exit 0, 3 s |
| `pytest tests/adversarial` | 16 passed, exit 0, 7 s |
| `pytest tests/e2e` | 8 passed, exit 0, 63 s |

Una primera pasada completa (antes de la corrección del reloj de pared, §2) falló únicamente
`tests/unit/test_scope_boundary.py::test_the_decision_path_never_reads_the_wall_clock`; el resto de suites
pasó. Regresión específica dentro de las suites: `test_live_runtime` (FakeExecution, 1/1.1),
`test_session_deadline`, `test_live_filters`, `test_risk_state_persistence`, `test_risk_restore`,
`test_paper_session_api`, `test_live_api`, `test_paper_execution`, `test_order_filters`.

## 6. Casos no probados y limitaciones

- **Sin corrida prolongada ni venue real.** Todo se probó con feed sintético (Binance bloqueado en este
  entorno) y el motor paper; la validación de 8 h sigue pendiente y no se autoriza aquí.
- **Candado de sesión local al proceso.** `_session_lock` serializa arranques dentro de un proceso de API.
  Dos procesos (dos réplicas, o un reinicio que solapa con el anterior) no lo comparten; la fila del run
  antes del loop y el marcado de huérfanos acotan el daño pero no lo impiden. Un candado en base
  (fila `runs` activa única por modo) sería el siguiente paso; no se improvisó aquí.
- **Muerte dura del proceso.** `flush_persistence` espera hasta 10 s en un `stop` ordenado; un `kill -9`
  entre un fill y su evento deja el diario incompleto. Está cubierto por diseño (el cross-check lo detecta y
  el siguiente arranque bloquea entradas) y por prueba (escritura perdida), pero la recuperación es manual.
- **Pierna restaurada sin edad.** El time stop no cierra una posición restaurada (decisión en §3.5); el
  stop, el objetivo y el deadline sí la gobiernan.
- **Diario y `fills` en la misma base.** El cross-check detecta que una de las dos escrituras se perdió;
  no detecta que se perdieran las dos (la cuenta seguiría coherente pero corta). El sello de `run_stop`
  perdido sigue siendo el pendiente de 1.1.
- **Reconciliación del venue en paper.** "La posición del venue" es la del motor paper del mismo proceso;
  en un venue real sería una lectura de red con sus propios fallos, no cubierta.
- **F6 y F9–F16 de la auditoría** no se abordaron (F6 por mandato; el resto por prioridad); siguen abiertos.
- **Frontend** no muestra `entry_blocks`, `pending_exit` ni `account_state`; la API es compatible hacia
  atrás (claves añadidas).
- **Multiproceso de pruebas.** Las pruebas de atomicidad se apoyan en el entrelazado del event loop con
  I/O real de SQLite (aiosqlite); son deterministas en este entorno, pero la reproducción "sin candado"
  depende de que exista al menos una espera antes de asignar la sesión, que hoy existe.

## 7. Evidencia de que las pruebas usan el proveedor paper real

- Ningún archivo nuevo usa `FakeExecution` (`grep -c FakeExecution` = 0 en los seis). Los constructores
  `build()` de `test_paper_cancellations.py` (reutilizado por `test_exit_guard.py` y
  `test_deadline_hardening.py`) y `engine_for()` de `test_account_restore.py` instancian
  `PaperExecutionProvider(settings.execution.model_copy(update={"reject_probability": 0.0, "partial_fill_probability": 0.0}), DEFAULT_UNIVERSE, clock, RngRegistry(1), initial_capital=…)`
  y lo inyectan en `LiveRuntime` como `execution`. Los fills salen de `on_bar` del motor en la vela
  siguiente, con su latencia y slippage; las aserciones leen `get_orders(open_only=True)`,
  `get_positions()` y `get_portfolio()` del motor, no contadores del runtime.
- `test_session_start_atomicity.py` no construye el motor: pasa por `AppState.start_paper_realtime`, que
  construye el `PaperExecutionProvider` de producción; solo el feed público se sustituye por
  `_FakePublicFeed` (misma sustitución que las pruebas de API de 1.1).
- Único parcheo del motor: `cancel_order` que lanza, en el test de cancel no confirmado (F1), y el
  plantado directo de un fill en `_portfolio` para simular una posición que el runtime no vio (F2). Ambos
  están nombrados en el propio test.
- El motor sembrado se verifica contra el propio `RiskEngine` (rechazo "daily loss") y contra el runtime
  (0 órdenes en 120 velas con cubos sembrados), no contra un doble.

## 8. Confirmaciones

- No se hicieron commits, push, pull, stash, rebase ni cambios de rama; HEAD sigue en
  `ab68d1c128a7181f54e1e79d3d7f37261365d821`.
- No se desplegó nada, no se tocó el VPS, no se ejecutaron migraciones ni reinicios externos.
- No se ejecutó ninguna orden real ni se llamó a ningún endpoint privado; no hay egreso a Binance en este
  entorno y las pruebas no lo necesitan.
- No se solicitaron, leyeron, imprimieron ni modificaron credenciales o secretos; `.env` no existe en este
  checkout y no se leyó ni escribió ningún archivo de entorno; barrido de patrones de secretos sobre el delta
  de la fase y los archivos nuevos: sin aciertos.
- No se modificó la activación live ni nada que habilite dinero real (`core/config.py` intacto; valores por
  defecto verificados en §4).
- No se ejecutó ninguna prueba que acceda o desbloquee el holdout; `backtest/holdout.py` y sus pruebas
  están intactos (hash idéntico al inicio).
- No se alteró ningún umbral estadístico ni de riesgo (`risk/engine.py`, `backtest/inference.py` intactos).
- No se ejecutó `scripts/verify.sh` ni ninguna simulación prolongada.

## 9. Veredicto por bloqueo

| Bloqueo | Veredicto | Fundamento |
|---|---|---|
| F1 | **RESUELTO** | causa corregida en proveedor y runtime; 7 pruebas sobre el motor real que fallan en el árbol previo con el síntoma original; el fallo de cancel ahora bloquea y detiene en vez de mentir |
| F2 | **RESUELTO** | una salida en vuelo por posición, bajo candado, con resultados creídos solo del venue; 8 pruebas que fallan en el árbol previo mostrando las dos salidas |
| F3 | **RESUELTO** (cuenta paper) | pérdida diaria, drawdown, pico y día UTC se reconstruyen del diario por el modelo del motor; 23 pruebas; demostración previo/reparado en §2; límite: muerte dura entre fill y evento → bloqueo, no pérdida silenciosa |
| F4 | **RESUELTO** | el respaldo a 0.0 fue eliminado; una base ilegible bloquea entradas; la reconciliación exige riesgo + cuenta + posición del venue |
| F5 | **RESUELTO** dentro de un proceso | candado `asyncio` en arranque y armado; carrera reproducida sin él y cerrada con él; **PARCIAL** si se despliegan varias réplicas (documentado, no resuelto) |
| F8 | **RESUELTO** | fila antes del loop, nada arranca si la fila falla, arranque fallido sellado y anotado, reintento limpio; prueba de orden desde dentro de `start` con clave foránea |
| F7 | **RESUELTO** | `resume` rechazado, watchdog sin levantar, re-halt por ciclo, sin entradas tras el deadline aunque la máquina esté en RUNNING |
| F6 | **NO ABORDADO** | fuera del alcance por mandato (ninguna modificación de la activación live); sigue abierto |

Lo que esto **no** dice: nada sobre rentabilidad ni sobre el comportamiento con un venue real. Lo que sí
dice: los cinco bloqueos críticos que impedían una validación prolongada en papel tienen una corrección
con causa identificada y pruebas que detectan el defecto original. La validación de 8 h sigue necesitando
revisión independiente de este diff, commit y despliegue por el usuario, y la decisión sobre F6 y el
candado multiproceso.
