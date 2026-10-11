# Trader-IA — Fase 1.4: auditoría integral y hardening del sistema (excluye la estrategia cuantitativa)

Informe de cierre. Sin commits, sin push, sin despliegues, sin reinicios de servicios, contenedores,
procesos ni VPS, sin órdenes reales ni acceso a Binance, sin credenciales leídas, impresas, copiadas ni
guardadas, sin cambios en la estrategia de trading ni en ningún umbral, sin acceso al holdout. Todo lo que
se afirma sobre pruebas tiene un comando y un resultado en §6; lo no reproducido está en §7 con su motivo.
**Nada de lo descrito está desplegado**: el working tree local no es el código que corre en el VPS y no se
afirma nada sobre ese código (§13).

Convención: cada sección separa **hechos** (código, comando o prueba), **inferencias** y
**recomendaciones**. Severidades: **P0** (puede perder dinero o estado sin aviso; bloquea cualquier
validación), **P1** (corrupción o pérdida de registro, estado imposible, carrera reproducible),
**P2** (degradación observable sin aviso, contrato incumplido), **P3** (documentación, consistencia,
mejora). Un hallazgo "corregido" tiene una prueba que falla en el árbol previo a la fase y pasa en el actual.

---

## 1. Estado inicial y preservación

**Hechos.** La fase arrancó sobre el working tree que dejó la Fase 1.3 (dos bloques, informes
`docs/PHASE_1_3_HARDENING_REPORT.md` y `docs/PHASE_1_3_COSTS_RISK_PARITY_REPORT.md`), sin commit. Antes de
tocar nada se capturó `git status`, el `git diff` completo y una copia byte a byte de los 82 archivos
modificados o no rastreados (`scratchpad/phase14/tree_start`), y al final se comprobó que ninguno cambió
salvo los tres que esta fase declara propios (§14).

| | Inicio (2026-10-11T11:26:18Z) |
|---|---|
| Rama / HEAD | `claude/algo-trading-simulation-platform-ngf7xo` / `ab68d1c128a7181f54e1e79d3d7f37261365d821` |
| `git status --porcelain` | 82 líneas: 25 M + 57 ?? |
| Huella del `git diff` (sha256/16) | `aa7dce3039a38ec2` |
| Huella del conjunto de no rastreados | `e6fd81fb52093f1f` |
| `git diff --stat` | 25 files changed, 3667 insertions(+), 335 deletions(-) |
| Suites al inicio (cierre de 1.3) | lint limpio; unit 1403; integration 302; property 31; failure 12; adversarial 16; e2e 8 — verdes |

Alcance inspeccionado (lectura completa o dirigida): `api/state.py` (ciclo de vida, persistencia,
salud, métricas), `api/app.py` (rutas, autenticación, mapeo de errores, límites de tasa), `runtime/engine.py`
(motor de escenarios), `runtime/live.py` (sesión 24/7; ya auditada en 1.3), `persistence/database.py` y
`persistence/repositories.py`, `core/config.py` (secretos), `data/providers/binance_public.py` y
`binance_stream.py`, `Dockerfile`, `docker-compose*.yml`, `infra/Caddyfile`, `scripts/backup.sh`,
`scripts/deploy.sh`, `scripts/post_reboot_check.sh`, `docs/DEPLOYMENT.md`, `docs/LIVE_RUNBOOK.md`,
`SYSTEM_STATUS.md`, `.env.production.example` (solo nombres de variables y longitud de valores; ningún valor
se leyó como texto), y el frontend por búsqueda de símbolos.

---

## 2. Resumen de riesgos

| Severidad | Hallazgos | Estado |
|---|---|---|
| **P0** | ninguno encontrado en el alcance | — |
| **P1** | H1 escritura de persistencia del motor de escenarios sin orden ni vaciado al detener; H2 arranque de run sin candado y con referencia instalada antes de la fila | **corregidos** con pruebas (§3, §5) |
| **P2** | H3 `stop()` del motor dejaba RUNNING sin tarea tras un timeout; H4 fallos de persistencia absorbidos sin contador ni señal en salud; H5 `stop` de la sesión 24/7 fuera del candado de sesión | **corregidos** con pruebas |
| **P3** | H6 la URL del webhook de alertas no se enmascaraba en `Settings.redacted()`; H7 `/api/health` sin autenticación expone el motivo libre del último estado; H8 código 400 vs 409 para "run ya activo"; H9 comentarios "nunca ejecutado" en los compose contradicen el despliegue registrado; H10 el frontend no muestra `entry_blocks` ni el lease; H11 F5 entre procesos sigue siendo detección, no exclusión; H12 sin segundo factor | H6 corregido; H7–H12 documentados |

**Inferencia.** El sistema no tiene, en el alcance auditado, un camino que pierda dinero o estado sin dejar
rastro: la sesión 24/7 ya secuenciaba y vaciaba sus escrituras (1.3), y el motor de escenarios ahora hace lo
mismo. Lo que había era pérdida de **registro** silenciosa (H1, H4) y estados de API que no correspondían al
proceso (H2, H3, H5). Lo que sigue abierto es externo al código local (venue, réplicas, 2FA) o es
documentación.

---

## 3. Hallazgos por severidad

### P1

**H1 — El motor de escenarios escribía fire-and-forget y `stop()` volvía con escrituras en vuelo**
(`runtime/engine.py`). Hechos: `_save` creaba una tarea por escritura (`asyncio.create_task`) sin orden
entre ellas y sin seguimiento; `stop()` esperaba al loop y volvía. Una fila de fill referencia su fila de
orden (clave foránea); dos escrituras en sesiones distintas pueden intercalarse y el fill llega antes que la
orden y es rechazado — un round trip que la reconstrucción del reinicio no puede recomponer. Esta es la causa
raíz del flake de `tests/integration/test_restart_recovery.py` registrado en 1.3 (el test dormía 0,5 s para
"dejar drenar"). La sesión 24/7 tenía desde 1.3 un candado de secuencia y `flush_persistence()`; el motor de
escenarios no. Corrección: `_persist_lock` + `_sequenced`, conjunto de tareas en vuelo,
`flush_persistence(timeout)` llamado al final de `stop()`, `persistence_flushed` y `last_error` cuando no
se completó, contador `Counters.persist_failures`. Pruebas: `test_scenario_engine_persistence.py` (6; 5
fallan en el árbol previo). `AppState.stop_run` sella la fila **después** de `stop()`, es decir, después del
vaciado.

**H2 — `start_run` sin candado e instalaba el motor antes de que existiera su fila** (`api/state.py`).
Hechos: `start_run` no tomaba `_session_lock` (la ruta paper-live sí, desde 1.2/F5); `self.runtime = engine`
se asignaba antes de `RunRepository.create` y de `engine.start()`. Consecuencias reproducidas: (a) si la fila
no podía escribirse, la API reportaba un run con `run_id` que la base no conocía y `stop_run` sellaba una
fila inexistente; (b) si `engine.start()` fallaba, el motor quedaba instalado y la fila sin sellar; (c) dos
arranques concurrentes pasaban ambos la comprobación "ya activo" (`is_running` es falso hasta `start()`),
escribían dos filas y arrancaban dos motores sobre una cuenta — el primero huérfano pero vivo, y sus puntos
de equity se escribían bajo el `run_id` del segundo (`_persist("equity")` lee `self.runtime.run_id`).
Corrección: `start_run` bajo `_session_lock`; fila → `engine.start()` → referencia, en ese orden; un
`start()` que falla sella la fila y la anota (`start_failed: …`) y no instala nada. Pruebas:
`test_run_lifecycle.py` (fila rechazada, arranque fallido, dos arranques con barrera, stop idempotente; las
cuatro fallan en el árbol previo).

### P2

**H3 — Timeout de `RuntimeEngine.stop()` escapaba y dejaba RUNNING sin tarea.** Hechos: `wait_for(task, 10)`
dentro de `suppress(CancelledError)`; al vencer, `wait_for` cancela la tarea y lanza `TimeoutError`, que no
se suprimía: `stop()` lanzaba, `state` quedaba RUNNING y `_task` apuntaba a una tarea cancelada
(`is_running` verdadero sin loop). Corrección: el timeout se captura, cuenta un error, deja constancia en
`last_error` y el motor aterriza en STOPPED. Prueba: `test_a_loop_that_will_not_stop_is_cancelled...`
(falla en el árbol previo con `TimeoutError`).

**H4 — Fallos de persistencia absorbidos sin señal.** Hechos: `AppState._persist` captura toda excepción y
la registra en el log; ni la salud, ni el estado del sistema, ni las métricas sabían que el registro iba
quedando corto; el motor seguía (correcto por diseño) y nadie se enteraba (incorrecto). Corrección:
`_persist_writes`, `_persist_failures`, último error (tipo y mensaje truncado, **nunca** el payload) y hora;
`health()` añade el componente `persistence` ("degraded" si hubo un fallo en los últimos 10 minutos y, con
él, `status: degraded`); `system_status()` expone `persistence`; `/api/metrics` añade
`tia_persist_writes_total` y `tia_persist_failures_total`. Prueba:
`test_a_write_the_store_refuses_is_counted_and_degrades_health` (falla en el árbol previo).

**H5 — `stop_realtime_session` fuera del candado de sesión.** Hechos: el arranque de la sesión 24/7 corre bajo
`_session_lock` y asigna `self.live_runtime` al final; un stop que llega durante el arranque veía
`live_runtime is None`, respondía `{"active": False, "state": "disarmed"}` y la sesión que no vio seguía
corriendo. Corrección: el stop toma el candado; un stop durante un arranque espera y luego detiene (la
intención del operador prevalece). Sin reentrancia: el único llamador es la ruta `/api/live/stop`; `shutdown`
detiene el runtime directamente. Prueba: `test_a_stop_that_arrives_during_a_start_waits_and_then_stops_the_session`
(barrera sobre `_foreign_session_lease`; falla en el árbol previo).

### P3

**H6 — `Settings.redacted()` no enmascaraba `observability.alert_webhook_url`.** Un webhook de Discord o
Slack lleva su token en la ruta. `redacted()` no tiene hoy ningún llamador en el paquete (latente), pero es
la función que la documentación presenta como "segura para registrar". Corrección: se conserva el esquema y
el host (`https://discord.com/***`) y se retira el resto. Pruebas: `test_config_redaction.py` (3; 2 fallan en
el árbol previo). `settings_view()` (la ruta `/api/settings`) no incluía ni incluye la URL.

**H7 — `/api/health` sin autenticación expone `live_runtime.state_reason`** (texto libre del último cambio de
estado, p. ej. "provider unreachable (attempt 3): <mensaje de excepción>"). El docstring promete "solo
estados de componentes". No cambiado: `scripts/post_reboot_check.sh` y los monitores externos leen `mode` y
`heartbeat_age_seconds` de este endpoint sin sesión. Recomendación: sustituir `state_reason` por un
vocabulario fijo o moverlo a `/api/system/status` (autenticado), y actualizar el script.

**H8 — Contrato HTTP inconsistente para "ya activo":** `/api/runtime/start` → 400 (`ValueError`);
`/api/live/paper-start` → 409 (`LiveActivationError`). Mismo hecho, dos códigos. No cambiado (el frontend
puede depender del código). Recomendación: 409 en ambos.

**H9 — Documentación de infraestructura desactualizada.** `docker-compose.yml` y `docker-compose.prod.yml`
abren con "STATUS: REQUIRES VALIDATION … has never been executed", mientras `infra/Caddyfile` ("found on the
first real deployment") y `SYSTEM_STATUS.md` (pase de despliegue 24/7 del 2026-08-14, validación contra
mainnet desde un VPS el 2026-08-18) registran despliegues reales. No se tocaron archivos de infraestructura.
Recomendación: actualizar los dos encabezados con la fecha y el resultado del `make production-readiness`.

**H10 — El frontend no muestra `entry_blocks` ni el lease** (búsqueda en `frontend/src`: solo
`heartbeat_age_seconds`). Un operador no ve por qué la sesión rehúsa entradas (`position_unverified`,
restauración incompleta) salvo en la API. Recomendación de UI; fuera del alcance de esta fase.

**H11 — F5 entre procesos** (de 1.3): el lease por heartbeat (120 s) detecta otro proceso vivo pero no
excluye dos arranques dentro de la misma ventana sin heartbeat previo. Sin Redis ni candado distribuido por
mandato. Operar con una réplica por cuenta: la regla **no** figura como tal en `docs/DEPLOYMENT.md` ni en
`docs/LIVE_RUNBOOK.md` (búsqueda de "replica"/"réplica"/"scale": sin resultados) — ver §12.

**H12 — Sin segundo factor** para la cuenta del operador (ya declarado en `/api/security/posture`).

### 3.1 Matriz de fallos (16 casos)

Campos: fallo · cómo se detecta · respuesta del sistema · estado resultante · recuperación · evidencia.

| # | Fallo | Detección | Respuesta | Estado resultante | Recuperación | Evidencia |
|---|---|---|---|---|---|---|
| 1 | base de datos ausente o con otra versión de esquema al arrancar | `ensure_schema` / `alembic upgrade` fallan | la aplicación no sirve (lifespan falla; el contenedor reinicia visiblemente) | sin API | corregir la base; nada se opera a ciegas | `test_a_schema_from_another_version_is_refused` |
| 2 | escritura rechazada por la base durante la operación | `_persist` captura; contador y hora | el loop sigue; `health.persistence = degraded` 10 min; métricas | operando con registro corto | el próximo arranque reconstruye y **bloquea entradas** si la cuenta no cierra | H4 (nueva); `test_the_database_being_unavailable_does_not_stop_trading`; `test_a_lost_journal_write…` |
| 3 | fill escrito antes que su orden | clave foránea | **ya no ocurre**: escrituras secuenciadas en ambos motores | — | — | H1 (nueva, falla en el árbol previo) |
| 4 | proceso muerto con escrituras en vuelo | el arranque siguiente: fila sin `stopped_at`; cross-check fills ↔ eventos | la sesión 24/7 se reanuda bajo el mismo deadline; una cuenta que no reconcilia bloquea entradas | reanudada o bloqueada, nunca a ciegas | `reconcile_session_state` por el operador | `test_session_deadline.py`, `test_account_restore.py` |
| 5 | stop con escrituras pendientes | `flush_persistence` con timeout | espera hasta 10 s; si no, `persistence_flushed=False` y `last_error` lo dicen | detenido, registro posiblemente corto y dicho | reconstrucción en el arranque | H1 (nueva); `test_a_clean_stop_reports_the_record_flushed` |
| 6 | la fila del run no puede escribirse | excepción en `RunRepository.create` | nada arranca ni se instala | sin run | reintentar el arranque | H2 (nueva); `test_a_failed_run_row_write_starts_nothing` |
| 7 | el motor falla al arrancar | excepción en `start()` | fila sellada y anotada `start_failed`; nada instalado | sin run; fila cerrada | reintentar | H2 (nueva); `test_a_runtime_that_fails_to_start_leaves_a_stamped_row_and_no_session` |
| 8 | dos arranques concurrentes | candado de sesión | el segundo espera y es rechazado ("already active") | un run, una fila | — | H2 (nueva); `test_session_start_atomicity.py` |
| 9 | stop durante un arranque | candado de sesión | el stop espera y luego detiene | sesión detenida, fila sellada | — | H5 (nueva) |
| 10 | el loop no se detiene | timeout de `stop()` | tarea cancelada; error contado y dicho | STOPPED (nunca RUNNING sin tarea) | nuevo motor | H3 (nueva) |
| 11 | velas que dejan de llegar (feed estancado) | watchdog por TTL (300 s) | HALT_NEW_ORDERS; la posición sigue gestionada | halt sanable | se levanta solo al volver los datos; nunca si el deadline pasó | `test_stale_market_data_halts_and_recovery_is_earned`; `test_a_deadline_during_a_watchdog_halt_is_not_lifted…` |
| 12 | proveedor inalcanzable repetidamente | contador de fallos del loop | halt; SAFE_MODE al décimo fallo con incidente | SAFE_MODE pegajoso | operador nombrado | `test_transient_provider_failure_halts_then_escalates_only_if_persistent` |
| 13 | datos corruptos, duplicados, futuros o congelados | `DataQualityEngine` hard-fail | sin decisión en esa vela | operando sin decidir | datos limpios | `test_data_quality.py` (19), `test_a_corrupted_feed_produces_refusals_not_trades` |
| 14 | estado de una orden desconocido (timeout del venue) | `ReconciliationError` | halt de entradas; resolución por `client_order_id`; nunca reenvío a ciegas | adoptada o descartada | reconciliación | `test_timeout_does_not_duplicate_order`, `test_a_resolved_present_order_is_adopted_not_retried` |
| 15 | posición del venue ≠ round trip rastreado | `_manage_position` / `_reconcile` (F16) | entradas bloqueadas `position_unverified`; divergencia registrada | HALT_NEW_ORDERS con bloqueo | `reconcile_session_state` | `test_runtime_invariants.py` (G13), `test_phase13_audit_regressions.py` (F16) |
| 16 | otro proceso corre la misma sesión (heartbeat fresco) | lease en `runs.notes` | arranque rehusado; el run no se reanuda ni se sella | una sola sesión | esperar el lease o detener el otro proceso | `test_session_lease.py` |

Fuera de la tabla pero cubiertos: desvío de reloj (`test_clock_skew_monitor`), deadline con feed muerto y
cierre no ejecutado (F9), caída del contexto LLM (`test_the_llm_being_unavailable_never_stops_the_pipeline`),
rechazos y parciales del venue durante 500 velas (`test_adverse_recovery.py`).

---

## 4. Cambios y archivos

| Archivo | Δ fase | Cambio |
|---|---|---|
| `packages/tia/src/tia/runtime/engine.py` | +93 / −15 | H1, H3: `_persist_lock`, `_sequenced`, `_persist_tasks`, `flush_persistence`, `persistence_flushed`, `_on_persist_done`, `Counters.persist_failures`, `stop()` con timeout capturado y vaciado; se retira `_swallow_task_error`. |
| `packages/tia/src/tia/api/state.py` | +73 / −3 | H2: `start_run` bajo candado y `_start_run_locked` (fila → start → referencia; fallo sella y anota). H4: contadores de persistencia, `persistence_status()`, componente `persistence` en `health()`, `persistence` en `system_status()`, dos series en `prometheus_metrics()`. H5: `stop_realtime_session` bajo candado (`_stop_realtime_session_locked`). |
| `packages/tia/src/tia/core/config.py` | +7 / −0 | H6: enmascarado de `observability.alert_webhook_url` en `redacted()`. |

Pruebas nuevas (no rastreadas; ninguna prueba existente modificada):

| Archivo | Pruebas | Cubre |
|---|---|---|
| `tests/integration/test_scenario_engine_persistence.py` | 6 | orden fill/orden, stop espera escrituras (y lo dice cuando no puede), stop limpio, fallos contados sin detener el loop (sync y async), timeout del loop, stop idempotente |
| `tests/integration/test_run_lifecycle.py` | 6 | fila rechazada, start fallido sella la fila, dos arranques concurrentes (barrera), stop idempotente, fallo de persistencia → salud degradada/métricas, stop durante arranque (barrera) |
| `tests/unit/test_config_redaction.py` | 3 | token del webhook retirado, ningún secreto en el documento, URL vacía intacta |

Total: **15 pruebas nuevas en 3 archivos**; 13 fallan en el árbol de inicio de la fase
(`scratchpad/phase14/prefix_results_detail.txt`); las 2 restantes son controles que pasan en ambos.

---

## 5. Pruebas agregadas frente a lo que el mandato exigía

### 5.1 Persistencia y recuperación (ocho casos obligatorios)

| Caso | Prueba | Estado |
|---|---|---|
| 1. fallo entre escrituras relacionadas (orden y fill) | `test_a_fill_is_never_written_before_the_order_it_references` (motor de escenarios, nueva); `test_account_restore.py::test_a_lost_journal_write_makes_the_rebuild_incomplete_and_the_next_session_blocked` (sesión 24/7, 1.2) | cubierto |
| 2. reintento de un evento ya procesado | `test_failure_modes.py::test_a_redelivered_event_is_rejected_by_the_database` (índice único en `idempotency_key`); `FillRepository.append` y `OrderRepository.upsert` son upserts por id; `test_account_restore.py::test_partial_fills_and_fees_rebuild_identically_however_often` | cubierto |
| 3. restauración de un estado válido | `test_account_restore.py` (12), `test_risk_state_persistence.py`, `test_restart_recovery.py::test_restart_recovery` | cubierto |
| 4. estado incompleto o corrupto | `test_an_incomplete_rebuild_is_refused_by_the_engine`, `test_risk_restore_future_rows.py` (6), `test_an_unreadable_store_at_start_blocks_entries_and_never_substitutes_base_capital`, `test_failure_modes.py::test_a_schema_from_another_version_is_refused` | cubierto |
| 5. error de base durante una transición | `test_a_write_the_store_refuses_is_counted_and_degrades_health` (nueva); `test_persistence_failures_are_counted_and_never_stop_the_loop` (nueva); `test_failure_modes.py::test_the_database_being_unavailable_does_not_stop_trading` | cubierto |
| 6. reinicio con run activo | `test_session_deadline.py` (resume bajo el mismo deadline / no resume vencido), `test_session_lease.py`, `test_account_restore.py::test_an_open_position_is_restored_protected_scorable_and_closable_after_a_restart` | cubierto |
| 7. stop ordenado con escrituras pendientes | `test_stop_waits_for_the_writes_in_flight_and_says_when_it_could_not` (nueva); `test_runtime_invariants.py::test_a_clean_stop_reports_the_record_flushed` / `test_a_stop_that_cannot_drain_the_persistence_queue_says_so` (1.3) | cubierto |
| 8. reconciliación base ↔ memoria | `reconcile_session_state` en `test_account_restore.py` / `test_live_api.py`; `test_phase13_audit_regressions.py` (F16, posición del venue vs round trip) | cubierto |

### 5.2 Concurrencia (barreras y eventos, nunca probabilístico)

`test_two_concurrent_starts_yield_exactly_one_run` (nueva: el primer arranque se retiene dentro de la
escritura de la fila; el segundo llega mientras), `test_a_stop_that_arrives_during_a_start_waits_and_then_stops_the_session`
(nueva: el arranque se retiene en la comprobación del lease), `test_session_start_atomicity.py` (6, de
1.2: dos arranques simultáneos de la sesión 24/7 y la variante sin candado que construye dos runtimes),
`test_exit_guard.py::test_two_concurrent_close_callbacks_send_one_exit` (1.2), `test_session_lease.py`
(otro proceso). **Hecho:** el candado es `asyncio.Lock`, local al proceso; entre procesos solo el lease por
heartbeat (detección). **Límite de una réplica:** el despliegue debe correr un solo backend por base.

### 5.3 Ciclo de vida

Idempotencia de `start`/`stop`: `test_stop_is_idempotent` (motor), `test_stop_is_idempotent_and_stamps_the_row_once`
(aplicación), `LiveRuntime.stop` idempotente por `is_terminal` (1.3). Arranque parcial: `test_a_run_whose_row_cannot_be_written_is_not_installed`,
`test_a_start_that_fails_stamps_its_row_and_installs_nothing`, `test_session_start_atomicity.py::test_a_failed_run_row_write_starts_nothing`
/ `test_a_runtime_that_fails_to_start_leaves_a_stamped_row_and_no_session`. Stop durante operación pendiente:
`test_deadline_hardening.py::test_a_pending_exit_at_the_deadline_is_not_doubled`,
`test_exit_guard.py::test_a_partially_filled_exit_keeps_the_pending_state_until_it_completes`. Estado de la
API vs estado real: H2/H3/H5 (nuevas). Estados imposibles: H3 (RUNNING sin tarea) cerrado; la máquina de
13 estados de la sesión rechaza transiciones ilegales (`test_the_state_machine_refuses_illegal_transitions`).

---

## 6. Comandos y resultados

Entorno: `.venv/bin/python` con `PYTHONPATH=packages/tia/src`, `-p no:cacheprovider -o
addopts="--strict-markers --strict-config" -q`; lint `.venv/bin/ruff check packages tests scripts`.
Registros en `scratchpad/phase14/`.

| Comando (resumen) | Resultado |
|---|---|
| pruebas nuevas (3 archivos) | 15 passed (3,9 s) |
| las mismas contra el árbol de inicio (`-o pythonpath=scratchpad/phase14/prefix_full/packages/tia/src`) | motor: 5 failed, 1 passed; ciclo de vida: 6 failed; redacción: 2 failed, 1 passed |
| suites existentes afectadas (`test_restart_recovery`, `test_paper_session_api`, `test_live_api`, `test_session_lease`, `test_session_deadline`, `test_session_start_atomicity`, `test_account_restore`, `test_adverse_recovery`, `test_core_kernel`, `tests/e2e`) | 143 passed in 129.68s (0:02:09) (131 s) |

### Corrida completa definitiva (`scratchpad/phase14/run_final.sh`)

| Paso | Estado | Duración | Resultado |
|---|---|---|---|
| lint | OK (0) | — | All checks passed! |
| `pytest tests/unit` | OK (0) | 87 s | 1406 passed, 6 warnings in 84.79s (0:01:24) |
| `pytest tests/integration` | OK (0) | 247 s | 314 passed in 245.81s (0:04:05) |
| `pytest tests/property` | OK (0) | 27 s | 31 passed in 25.58s |
| `pytest tests/failure` | OK (0) | 5 s | 12 passed in 3.38s |
| `pytest tests/adversarial` | OK (0) | 8 s | 16 passed in 7.30s |
| `pytest tests/e2e` | OK (0) | 30 s | 8 passed in 28.86s |

Una sola corrida, sin fallos, sin reintentos y sin pruebas desactivadas o marcadas. Comparación con el cierre de 1.3: unit 1403 → 1406 (+3),
integration 302 → 314 (+12); el resto sin cambios.

---

## 7. Casos no reproducidos o bloqueados

| Caso | Motivo |
|---|---|
| Comportamiento de los contenedores, healthchecks, red interna, Caddy, backup y restore | no hay daemon Docker en este entorno; se auditó la definición (§12) y no se ejecutó nada |
| Entrega real del webhook de alertas | sin red saliente; `_dispatch_alert` tiene timeout de 5 s, fire-and-forget y registro del fallo (hecho, por lectura) |
| Reconexión del stream de Binance contra el endpoint real | sin red; cubierto contra mocks (`test_binance_stream.py`: `test_a_dropped_socket_reconnects_with_backoff`, `test_a_stale_or_dead_stream_falls_back_to_rest_and_says_so`) |
| Postgres (producción) | las pruebas corren sobre SQLite; los upserts usan `on_conflict` del dialecto (ambos soportados); el restore drill documentado no se ejecutó |
| Dos **procesos** sobre la misma base arrancando dentro de la ventana del lease | reproducir exige dos procesos y una base compartida; el límite está documentado (H11) y el caso dentro de un proceso está probado |
| Pérdida dura entre un fill y su evento de cuenta | cubierto por diseño como bloqueo (1.2, `test_a_lost_journal_write...`); no se simuló matar el proceso |

---

## 8. Riesgos restantes (ordenados)

1. **Venue real no validado** (F6/1.3): adaptador Spot sin `reduceOnly`; nada de la ruta live ha tocado un
   venue. Bloqueado hasta testnet. **No habilitar dinero real.**
2. **Una réplica por cuenta** (H11): el lease detecta, no excluye.
3. **Comisiones no verificadas en origen** (`verified_at_source=False`; el gate live rehúsa armar).
4. **`/api/health` sin autenticación** expone texto libre (H7).
5. **Decisiones de 1.3 pendientes del usuario**: doble cuenta parcial de ejecución en el EV, carry sin
   lectura, spread sin cotización (informe 1.3 §8).
6. **Documentación de infraestructura** desalineada con el despliegue real (H9) y restore drill sin
   ejecutar registrado.
7. **Frontend** sin `entry_blocks`/lease (H10).
8. **Dependencias**: no se auditaron versiones ni CVEs (sin red; fuera del alcance declarado).

---

## 9. Seguridad

**Hechos.** Secretos tipados `SecretStr` (`jwt_secret`, `webhook_secret`, `binance_api_key/secret`,
`anthropic_api_key`); nunca aceptados por la API ni enviados al frontend (`settings_view` devuelve solo
booleanos `credentials_configured` / `api_key_configured`); `Database.url` enmascara la contraseña;
`redacted()` enmascara ahora también el webhook (H6). `.env` no existe en el working tree y está en
`.gitignore`; `.env.production.example` tiene todos los valores sensibles vacíos (comprobado por longitud,
sin leer valores). Rutas: todas requieren sesión salvo `/api/auth/login`, `/api/auth/logout`, `/api/health`
y el frontend estático (comprobado por búsqueda de `Depends` en cada ruta); las de control exigen rol
operador (`require_operator`). Límites de tasa: login 8/5 min por dirección y 12/10 min por cuenta; API 600/min.
Cabeceras CSP/no-sniff/no-frame y HSTS en el proxy. Contenedores sin privilegios nuevos, backend no root,
solo el proxy publicado, Postgres sin puertos. Sin segundo factor (H12). Ninguna credencial fue leída,
impresa ni almacenada durante la fase; ningún test imprime secretos (el marcador de `test_config_redaction.py`
es una cadena inventada).

**Inferencia.** La superficie no autenticada es pequeña y conocida; el único dato que fuga sin sesión es el
motivo libre de estado en `/api/health` (H7).

---

## 10. Persistencia y recuperación

**Hechos.** Una sesión SQLAlchemy por escritura (`AppState._persist`), sin transacción que agrupe orden y
fill: la coherencia entre ambas depende del **orden** (ahora garantizado en los dos motores) y de la clave
foránea (que rechaza el fill huérfano, nunca lo acepta). Idempotencia: eventos por índice único en
`idempotency_key`, fills y órdenes por upsert sobre su id, reconciliaciones e incidentes por id
determinista. SQLite con WAL, `foreign_keys=ON`, `busy_timeout=5000`; Postgres con `pool_pre_ping`.
Migraciones Alembic antes de servir en producción; `ensure_schema` rechaza una versión distinta
(`test_a_schema_from_another_version_is_refused`). Recuperación: la sesión 24/7 reconstruye cuenta, riesgo y
evidencia desde la base y **bloquea entradas** si algo no cierra (1.2/1.3); el motor de escenarios no se
reanuda (por diseño: un escenario es desechable). Vaciado al detener en ambos motores (H1), con `False` dicho
cuando no se logró. Fallos absorbidos ahora contados y visibles (H4).

**Recomendaciones.** Agrupar orden y sus fills en una transacción cuando lleguen juntos (hoy el orden basta,
pero una transacción cerraría también el caso de muerte del proceso entre ambas); ejecutar el restore drill
documentado y registrar su fecha.

---

## 11. Concurrencia

**Hechos.** Candado `asyncio.Lock` de sesión para arrancar la sesión 24/7, armar live y — desde esta fase —
arrancar un run de escenario y detener la sesión 24/7. Escrituras de persistencia secuenciadas por motor.
Difusión SSE sin bloqueo (cola por suscriptor, descarte del más antiguo, contador `dropped_events`). Sin
hilos: todo en el event loop; las operaciones de red del webhook y del stream son tareas con timeout. Entre
procesos: lease por heartbeat (120 s) — detección, no exclusión (H11).

---

## 12. API, observabilidad e infraestructura

**API.** Validación de cuerpos con Pydantic (`StartRequest` con rangos); errores mapeados a 400/401/403/
404/409/429/502/503 según la ruta; inconsistencia 400/409 en "ya activo" (H8). `/api/health` devuelve
componentes (`database`, `persistence` nuevo, `market_data`, `trading_engine` por edad del heartbeat,
`market_data_feed` por TTL) y `status` agregado; `/api/system/status` añade suscriptores, eventos
descartados, persistencia y el run; `/api/metrics` en formato Prometheus (ahora con escrituras y fallos de
persistencia). Logs estructurados (structlog) con `error=str(exc)[:N]` — un mensaje de excepción de httpx
podría incluir una URL; el webhook no se registra, pero es un punto a vigilar.

**Infraestructura (solo definición; nada ejecutado).** `Dockerfile` multi-etapa, usuario no root, `curl` solo
para el healthcheck, healthcheck a `/api/health` cada 20 s. `docker-compose.prod.yml`: proxy Caddy con TLS
automático, backend con `alembic upgrade head` antes de servir, Postgres sin puertos, servicio de backup
diario (`pg_dump | gzip`, retención 14) en un volumen del mismo host — los comentarios y `DEPLOYMENT.md`
§10 dicen copiarlo fuera. `scripts/backup.sh` cubre los tres casos (stack, Postgres directo, SQLite con
`.backup` consistente). `scripts/deploy.sh`: preflight → backup → build → `up -d --wait` → verificación →
rollback a la imagen anterior. `scripts/post_reboot_check.sh`: servicios sanos, salud por el proxy, sesión
resumida, cero `client_order_id` duplicados, heartbeat en movimiento. Documentación operativa:
`docs/DEPLOYMENT.md` (12 secciones, restore drill documentado, monitorización, rollback) y
`docs/LIVE_RUNBOOK.md` (16 secciones: pausa, kill switch, emergencias, reconciliación, reinicio, apagado).
Faltan: un procedimiento de **restore ejecutado y fechado**, la regla explícita "una réplica por base", y
los encabezados de los compose (H9).

---

## 13. Diferencias local / desplegado no verificables

El working tree local lleva 82 archivos modificados o nuevos sin commit (Fases 1, 1.1, 1.2, 1.3 y 1.4). El
código desplegado en el VPS es, como mínimo, HEAD `ab68d1c` o anterior, y no se accedió al VPS. Todo lo que
este informe y los de 1.3 corrigen **no está desplegado** hasta que el usuario revise, haga commit, despliegue
(`scripts/deploy.sh`) y ejecute `scripts/post_reboot_check.sh`. `SYSTEM_STATUS.md` (2026-08-14) describe un
estado anterior a todas las fases 1.x y no fue actualizado por esta fase.

---

## 14. Archivos tocados, estado Git final y preservación

Modificados por esta fase: `packages/tia/src/tia/runtime/engine.py`, `packages/tia/src/tia/api/state.py`,
`packages/tia/src/tia/core/config.py`. Nuevos: `tests/integration/test_scenario_engine_persistence.py`,
`tests/integration/test_run_lifecycle.py`, `tests/unit/test_config_redaction.py`, este informe.

| | Final (2026-10-11T11:41:12Z) |
|---|---|
| Rama / HEAD | `claude/algo-trading-simulation-platform-ngf7xo` / `ab68d1c128a7181f54e1e79d3d7f37261365d821` (sin commits) |
| `git status --porcelain` | 86 (25 M, 61 ??) (los 82 del inicio + 3 archivos de prueba + este informe) |
| Huella del `git diff` (sha256/16) | `d0fdb4c13f60db6f` |
| Huella del conjunto de no rastreados (excluido este informe) | `f48495d8aa491ecd` |
| `git diff --stat` | 25 files changed, 3840 insertions(+), 353 deletions(-) |
| `git stash list` | vacío |

Preservación (`scratchpad/phase14/preservation_check.sh`): de los 82 archivos capturados al inicio,
79 son idénticos y 3 cambiaron, los tres propios de esta fase; **0** cambios en
archivos ajenos; ningún archivo rastreado que estuviera limpio al inicio difiere ahora de HEAD.

---

## 15. Confirmaciones

**No** se hizo commit ni push. **No** se desplegó, reinició ni detuvo ningún servicio, contenedor, proceso ni
el VPS. **No** se ejecutó ninguna operación en Binance ni se envió orden real alguna; **no** se habilitó
trading con dinero real. **No** se leyó, solicitó, imprimió, copió ni guardó credencial, token, clave ni
contraseña. **No** se accedió al holdout ni a su libro. **No** se cambiaron configuraciones desplegadas ni
archivos de infraestructura. **No** se modificó la estrategia de trading ni umbral alguno. **No** se desactivó,
marcó ni debilitó ninguna prueba existente, ni se añadieron excepciones amplias (las dos capturas amplias
tocadas, `RuntimeEngine._save` y `AppState._persist`, ya existían y ahora cuentan además de registrar; la
nueva `_on_persist_done` cuenta la excepción de la tarea, no la silencia). **No** se usó `git reset --hard`, `git clean`,
checkout destructivo ni stash. **No** se instaló ni descargó nada. **No** se presenta como verificado nada que
solo esté documentado: lo que no se ejecutó está en §7.

---

## 16. Recomendación previa a una validación paper prolongada

**Hechos reunidos.** Las suites completas están en verde (lint limpio; unit 1406 passed, 6 warnings; integration 314 passed; property 31 passed; failure 12 passed; adversarial 16 passed; e2e 8 passed); los defectos de ciclo de
vida y persistencia encontrados en 1.2, 1.3 y 1.4 tienen corrección y prueba; el camino de dinero real sigue
sin validar contra un venue.

**Recomendación (orden).** (1) Revisar y hacer commit del working tree completo (82+ archivos) tras una
lectura independiente de los tres informes; (2) desplegar con `scripts/deploy.sh` y ejecutar
`scripts/post_reboot_check.sh`; (3) ejecutar el restore drill y registrar la fecha; (4) corregir H7 y H9 y
decidir las tres políticas abiertas de 1.3; (5) solo entonces arrancar la validación paper prolongada con
`max_hours` explícito, una réplica, alertas por webhook configuradas y vigilancia del nuevo componente
`persistence` en `/api/health`; (6) mantener el trading real deshabilitado hasta validar el adaptador en
testnet con `reduceOnly` resuelto. Nada de lo anterior constituye evidencia de ventaja de la estrategia.
