# Trader-IA — Fase 1.3: hardening técnico, validación de ejecución e investigación cuantitativa

Informe de cierre. Sin commits, sin push, sin despliegues, sin reinicios de servicios, sin órdenes a ningún
exchange, sin credenciales leídas ni almacenadas, sin acceso al holdout reservado. Todo lo afirmado sobre
pruebas tiene un comando y un resultado en §5; lo no ejecutado está en §6 con su motivo.

Estados usados: **RESUELTO** (causa corregida, prueba de regresión que falla en el árbol previo y pasa en el
actual), **PARCIAL** (corrección aplicada con un límite explícito), **PENDIENTE** (no abordado; decisión o
trabajo posterior), **NO REPRODUCIDO** (revisado; no es un defecto o no pudo reproducirse), **BLOQUEADO**
(requiere un recurso o permiso que este entorno/mandato no tiene).

---

## 1. Resumen ejecutivo

1. **Las correcciones de la Fase 1.2 son reales pero no eran suficientes.** La revisión adversarial de
   `runtime/live.py` sobre el motor paper real encontró trece defectos nuevos (G1–G13, §3) en los mismos
   caminos que 1.2 reparó: una sustitución de stop cuyo cancel falla colocaba un **segundo stop** y olvidaba
   el primero (G1); `_cancel_all_open` borraba sus registros **antes** de cancelar, y el flatten cerraba
   encima de un stop vivo (G2); cualquier excepción al leer una orden se trataba como "la orden no existe"
   (G3) y una salida desconocida bloqueaba **toda** salida posterior para siempre (G3); un cancel que
   encontraba el stop ya ejecutado contaba como "cancelado" sin contabilizar el fill, y el cierre salía sobre
   una posición ya plana (G4); el motor paper no aplicaba `reduce_only` y una salida sobre un libro plano
   abría la posición contraria (G5); los ids de cliente de stops y salidas se repetían entre sesiones (G6);
   una sesión en PAUSED/SAFE_MODE o sin vela nueva **no leía** sus órdenes y no se enteraba de un stop
   ejecutado (G7); la reconciliación comparaba al proveedor consigo mismo y nunca podía divergir (G8); dos
   procesos sobre la misma base arrancaban dos sesiones (G9, el límite multiproceso de F5); la ruta live no
   compartía el contrato "fila antes del loop" (G10/F6); eventos del diario fechados en el futuro y eventos de
   runs live se plegaban en la cuenta paper (G11); un `stop()` que no lograba vaciar la cola de persistencia
   callaba (G12); el tamaño de la posición del venue nunca se comparaba con el round trip rastreado (G13).
2. **Todos tienen corrección mínima y prueba que detecta el defecto original.** 60 pruebas nuevas en 12
   archivos; 36 de ellas fallan contra el árbol de inicio de la fase, 15 no pueden ni importarse allí (la
   función no existía), 4 no aplican a ese árbol (el guion vive en `scripts/`; las de invariantes adversos
   no prueban un defecto) y 5 son pruebas de preservación de comportamiento que pasan en ambos. Las suites
   completas quedan verdes: `lint limpio; unit 1346 passed, 6 warnings; integration 274 passed; property 31 passed; failure 12 passed; adversarial 16 passed; e2e 8 passed`.
3. **Estadística e integridad experimental.** El bootstrap truncaba el índice del percentil (sesgo hacia el
   centro de hasta un estadístico de orden; a 2.000 remuestras el extremo 5 % leía la media 100.ª en vez de
   la 99,95.ª): ahora interpola. Un dato no finito devolvía un intervalo; ahora no devuelve ninguno. El libro
   de accesos al holdout escribe la línea **al abrir** el acceso y otra al completarlo (un proceso que muere
   entre la verificación y el registro ya no borra el acceso). La familia de Bonferroni es ahora
   **acumulativa** sobre todas las corridas que leyeron la misma partición de validación (`research_runs.jsonl`),
   no la de la corrida que imprime. Se añade una lectura de estabilidad por mitades (informativa).
4. **Validación paper con datos reales: BLOQUEADO.** El egreso a Binance desde este entorno responde
   `CONNECT 403` (medido en la fase anterior; no se reintentó para no consumir un recurso prohibido), las
   comisiones siguen sin verificar en origen y el código corregido no está desplegado (el mandato prohíbe
   commit, push y despliegue). La lista de criterios de preparación (§8) tiene 11 de 15 cumplidos con
   evidencia; los 4 restantes son del operador. Se ejecutaron, en su lugar, **simulaciones adversas
   deterministas** sobre el motor real y la base real (rechazos y parciales durante 500 velas, pérdida de
   la tabla de fills, reinicio sobre una cuenta inconsistente).
5. **Investigación cuantitativa (§10–§11).** No hay evidencia de ventaja ni de su ausencia: la única
   evidencia real son 2 round trips. El problema dominante es geométrico (a 1 m el stop y el objetivo son del
   orden de los costos; tasa de acierto de equilibrio ≈ 0,88). Cinco hipótesis falsables quedan diseñadas con
   los once campos pedidos; ninguna mejora de estrategia se implementa ni se recomienda implementar hoy.
6. **Pendientes de decisión del usuario:** F6/G10 en live sigue **PARCIAL** (sin validación contra un venue;
   el adaptador apunta a Binance **Spot**, que no tiene `reduceOnly`); los multiplicadores del presupuesto de
   riesgo siguen **inertes** para el tamaño (PENDIENTE: es una decisión de diseño, no se cambió); la paridad
   backtester–sesión en salidas (C4) no se abordó.

---

## 2. Estado del repositorio al inicio y al final

| | Inicio de la fase (2026-10-10T19:13:39Z) | Final (2026-10-11T10:32:40Z) |
|---|---|---|
| Rama | `claude/algo-trading-simulation-platform-ngf7xo` | igual |
| HEAD | `ab68d1c128a7181f54e1e79d3d7f37261365d821` | igual (sin commits; `git stash list` vacío; reflog sin entradas nuevas) |
| `git status --porcelain` | 56 líneas: 20 M + 36 ?? (Fases 1, 1.1 y 1.2 e informes previos) | 70 líneas: 21 M + 49 ?? (los 56 anteriores + `domain/orders.py` + 12 archivos de prueba nuevos + este informe) |
| Huella del `git diff` (sha256/16) | `0513d698ab970a2b` (idéntica a la final de la Fase 1.2) | `30aaf2f001e4baca` |
| Huella del conjunto de no rastreados | `03141d5a520b5337` | `3ea057c95fa23a3c` (excluido este informe, que no puede contener su propia huella) |
| `git diff --stat` | 20 files changed, 2072 insertions(+), 190 deletions(-) | 21 files changed, 2711 insertions(+), 272 deletions(-) |

Fórmulas: `git diff | sha256sum | cut -c1-16` y
`git status --porcelain | grep '^??' | awk '{print $2}' | sort | xargs sha256sum | sha256sum | cut -c1-16`.

**Preservación de lo ajeno a esta fase.** Al inicio se copiaron al scratchpad de la sesión los 20 archivos
rastreados modificados (`tracked_start/`), el parche (`diff_start.patch`, sha256 = `0513d698ab970a2b`) y los
36 no rastreados (`untracked_start/`). Comparación byte a byte al final (`preservation_check.sh`):

- de los 20 rastreados modificados al inicio, **16 son idénticos**; 4 cambiaron, los cuatro por esta fase:
  `runtime/live.py`, `api/state.py`, `execution/paper.py`, `persistence/repositories.py`;
- de los 36 no rastreados al inicio, **31 son idénticos** (incluidos los 7 archivos de prueba y el informe de
  1.2, `risk/restore.py`, `execution/filters.py`, `backtest/partitions.py`, `backtest/resample.py`); 5 cambiaron,
  los cinco por esta fase: `backtest/holdout.py`, `backtest/inference.py`, `runtime/session_limits.py`,
  `portfolio/account_journal.py`, `scripts/strategy_experiment.py`;
- un archivo limpio al inicio fue modificado por esta fase: `domain/orders.py` (+4 líneas: `Order.reduce_only`);
- **ningún archivo de prueba existente fue tocado**; todas las pruebas de las Fases 1, 1.1 y 1.2 pasan sin
  cambios.

Modificaciones propias (líneas añadidas/eliminadas respecto de la versión de inicio):
`live.py` +367/−83 · `state.py` +233/−50 · `paper.py` +50/−0 · `repositories.py` +32/−0 ·
`session_limits.py` +96/−1 · `account_journal.py` +24/−3 · `inference.py` +24/−8 · `holdout.py` +25/−2 ·
`strategy_experiment.py` +96/−6 · `orders.py` +4/−0. Archivos nuevos: 12 de prueba (1.653 líneas) y este informe.

---

## 3. Defectos revisados, con evidencia

Identificadores: F1–F8 son los de la auditoría que la Fase 1.2 abordó; los **F9–F16** de esa auditoría no
figuran con texto en el repositorio (la Fase 1.2 solo los nombra como "siguen abiertos"), por lo que esta
fase cubrió las áreas que el mandato enumera (B1–B5) y numeró sus hallazgos como **G1–G13**. Donde un G
coincide con un F conocido se indica.

### 3.1 Verificación adversarial de la Fase 1.2 (¿son reales y fiables?)

| Punto del mandato | Resultado | Evidencia |
|---|---|---|
| Resolución `order_id`/`client_order_id` | **RESUELTO (1.2) y ampliado**: el motor resuelve ambos; el runtime lee por ambos y distingue "el venue falló" de "el venue no la conoce" (G3) | `test_paper_cancellations` (7), `test_order_integrity` (8) |
| Confirmación de cancelaciones | **RESUELTO (1.2)**; hueco encontrado y cerrado: la sustitución de stop ignoraba el resultado (G1), cancel-all olvidaba antes de confirmar (G2), un cancel que halla la orden ejecutada no contabilizaba (G4) | `test_a_stop_replacement_whose_cancel_fails_places_no_second_stop`, `test_a_flatten_whose_cancels_fail_...`, `test_a_close_whose_cancel_finds_the_stop_already_filled_sends_no_exit` |
| Salidas pendientes, candado, cierres concurrentes | **RESUELTO (1.2)**; hueco: salida desconocida ⇒ bloqueo permanente de toda salida (G3); la salida a mercado de una limit reductora expirada saltaba el candado (sin test propio; corregida: pasa por `_submit_exit`) | `test_an_exit_the_venue_never_accepted_is_given_up_and_the_position_can_be_closed_again` |
| Parciales, rechazos, timeouts, resultados desconocidos | **RESUELTO**; 500 velas con rechazos 20 % y parciales 40 % mantienen los invariantes | `test_adverse_recovery` (2), `test_exit_guard` (8) |
| Diario de eventos de cuenta | **RESUELTO (1.2)**; huecos: eventos futuros (G11) y eventos de runs `live` plegados en la cuenta paper (G11) | `test_account_journal_future` (3), `test_account_restore_scope` (2) |
| Restauración de cash/posición/equity/pico/pérdida diaria | **RESUELTO (1.2)**; re-verificado con parciales, reinicio y pérdida de la tabla de fills | `test_account_restore` (12), `test_adverse_recovery` |
| Reconciliación diario–fills–motor | **RESUELTO (1.2)**; hueco: la reconciliación órdenes-venue no comparaba con los registros del runtime (G8) | `test_an_open_order_at_the_venue_that_no_record_names_is_a_divergence` |
| Fila del run antes del loop | **RESUELTO (1.2)** en paper; **PARCIAL** en live (G10) | `test_session_start_atomicity` (6), `test_live_path_parity` (5) |
| Órdenes huérfanas / posiciones no rastreadas | **RESUELTO (1.2)**; hueco: posición del mismo lado pero distinto tamaño, o venue plano con round trip abierto, no se detectaban (G13) | `test_a_position_larger_at_the_venue_...`, `test_a_venue_flat_behind_a_tracked_round_trip_...` |
| Deadline, resume, watchdog | **RESUELTO (1.2)**; sin cambios; re-ejecutado | `test_deadline_hardening` (5), `test_session_deadline` (10) |
| Vaciado de escrituras pendientes al detener | **RESUELTO (1.2)**; hueco: el resultado se ignoraba (G12) | `test_a_stop_that_cannot_drain_the_persistence_queue_says_so` |

### 3.2 Defectos nuevos y pendientes (B1–B5 del mandato)

| Id | Área | Defecto (causa raíz) | Estado | Corrección mínima | Evidencia (falla en el árbol de inicio → pasa) |
|---|---|---|---|---|---|
| G1 | B3 | `_sync_protective_stop` llamaba `_cancel_protective()` sin mirar el resultado; con el cancel rechazado colocaba un segundo stop y sobrescribía el registro: dos stops vivos, uno sin rastrear | **RESUELTO** | si el cancel no se confirma, no se envía reemplazo; el stop viejo sigue rastreado; entradas bloqueadas por `_cancel` | `test_a_stop_replacement_whose_cancel_fails_places_no_second_stop` (reproducción manual previa: 2 stops en el motor, `stops_placed=3`) |
| G2 | B1/B3 | `_cancel_all_open` ponía `_protective=None`/`_resting=None` **antes** de cancelar; `emergency_flatten` enviaba la salida aunque el cancel del stop hubiera fallado | **RESUELTO** | los registros se olvidan solo tras un cancel confirmado (`_forget_tracked`); los ids no confirmados quedan en `_unconfirmed_cancels` y en el incidente; el flatten no cierra sobre un stop no confirmado y lo dice en `closing_orders` | `test_a_flatten_whose_cancels_fail_keeps_the_stop_tracked_and_sends_no_close`, `test_the_kill_switch_keeps_tracking_an_order_the_venue_did_not_cancel` |
| G3 | B1/B3 | los tres pollers usaban `contextlib.suppress(Exception)` y trataban `None` como "orden desaparecida": una caída transitoria del venue borraba el stop y el ciclo siguiente colocaba otro; una salida desconocida se quedaba pendiente para siempre y ninguna salida posterior podía enviarse | **RESUELTO** | `_read_tracked_order` distingue `found`/`unknown`/`error`; `error` mantiene el registro y no coloca nada; `unknown` bloquea entradas y se da por perdida tras `UNKNOWN_POLLS_BEFORE_LOST=3` lecturas consecutivas con incidente (`protective_stop_lost`, `resting_order_lost`, `exit_lost`); contadores `order_poll_failures`, `orders_lost` | `test_a_venue_that_cannot_be_read_keeps_the_stop_tracked_and_places_nothing`, `test_a_resting_entry_the_venue_does_not_know_...`, `test_an_exit_the_venue_never_accepted_...` |
| G4 | B3 | `_cancel` devolvía la orden terminal como éxito aunque fuera **FILLED** (el stop se ejecutó entre la decisión y el cancel) sin encaminar sus fills; `_close_position` dimensionaba el cierre con la lectura anterior | **RESUELTO** | `_cancel` encamina los fills de una orden terminal; `_close_position` relee la posición tras los cancels y no envía nada si está plana | `test_a_close_whose_cancel_finds_the_stop_already_filled_sends_no_exit` |
| G5 | B3 | el motor paper usaba `reduce_only` solo para eximir del mínimo nocional; `Order` no lo llevaba; una salida sobre un libro plano abría la posición contraria y un stop residual podía disparar sobre un libro plano | **RESUELTO** | `Order.reduce_only`; el motor rechaza una reduce-only que no reduce (como un venue de futuros), recorta el fill a lo que se tiene (con tolerancia a residuo flotante) y expira el resto; la orden ordinaria sigue pudiendo dar la vuelta | `test_paper_reduce_only` (6; 5 fallan en el árbol previo, 1 preserva comportamiento) |
| G6 | B4 | `client_order_id` de stops y salidas derivaba del contador de velas, que reinicia por sesión: la misma vela y tamaño en otra sesión re-apuntaba la fila de orden anterior (`orders.client_order_id` UNIQUE, `order_id` determinista) y sería un duplicado en un venue real | **RESUELTO** | el `run_id` entra en el id sintético; los prefijos `exit:`/`protective:` que clasifica `risk/restore.py` se conservan | `test_exit_and_stop_client_ids_differ_between_two_sessions_at_the_same_bar` |
| G7 | B3 | `_cycle_once` retornaba antes de leer orden alguna en PAUSED/SAFE_MODE, sin velas o sin vela nueva: un stop ejecutado durante una pausa no se contabilizaba hasta cambiar de estado | **RESUELTO** | `_poll_tracked_orders()` (solo lecturas) en los tres retornos tempranos; `_manage_resting` dividido en `_poll_resting` + gestión | `test_a_stop_that_fires_while_the_session_is_in_safe_mode_...`, `test_an_exit_that_fills_while_no_new_bar_closes_...`, `test_no_order_is_sent_from_a_paused_or_safe_moded_cycle` |
| G8 | B2 | `_reconcile` comparaba las órdenes abiertas del proveedor con las no terminales **del mismo proveedor**: nunca divergía; una orden huérfana en el venue no se reportaba | **RESUELTO** | compara el libro del venue (símbolo de la sesión) con los registros `_protective`/`_resting`/`_pending_exit`; "open at the venue but not tracked" ⇒ SAFE_MODE + incidente; para que una entrada a mercado pendiente de la vela siguiente no sea falso positivo, **toda** entrada no terminal se rastrea en `_resting` (`limit: bool`) | `test_an_open_order_at_the_venue_that_no_record_names_is_a_divergence`, `test_a_market_entry_is_tracked_while_it_works_...` |
| G9 (F5 multiproceso) | B1 | el candado de 1.2 es por proceso; un segundo contenedor o un despliegue viejo aún vivo pasaba como "run interrumpido" y el arranque lo sellaba y arrancaba otra sesión sobre la cuenta | **RESUELTO** | heartbeat en `runs.notes` (JSON, sin migración) cada 30 s de reloj de pared (`RunRepository.heartbeat`); lease de 120 s; el arranque rechaza si hay un lease ajeno fresco; el boot no sella ni reanuda un run con lease fresco: sondea 45 s en segundo plano y decide por si el heartbeat avanzó; un apagado limpio **libera** el lease (reanudación inmediata tras redeploy); `resume_decision.held_by_other` | `test_session_lease` (7 integración + 8 unitarias); `test_live_api::test_paper_session_resumes_after_a_crash_...` sigue pasando |
| G10 (F6) | B5 | la ruta live creaba la fila del run **después** de `start()`, sin restauración del estado de riesgo ni deadline | **PARCIAL** | `_start_session_with_run_row` compartido por paper y live (fila antes del loop; arranque fallido ⇒ fila sellada y anotada; sin sello de "huérfanas" para un venue real); `_build_live_runtime` recibe `prior_risk_state` y deadline por `session_max_hours`; la cuenta **no** se restaura del diario en live (el venue es la autoridad). Límite: no validado contra ningún venue; el adaptador es Binance **Spot** (`/api/v3/order`) y no mapea `reduceOnly` (en Spot no existe); nada se activó | `test_live_path_parity` (5), incl. la ruta de armado con gate y constructor sustituidos |
| G11 | B2/B4 | `fold_account_events` plegaba eventos fechados **después de ahora** (reloj adelantado) como si no lo fueran; la restauración paper plegaba eventos de runs `live` | **RESUELTO** | eventos > ahora + 60 s no se pliegan y hacen la restauración **incompleta** (bloquea entradas, con el motivo); `_load_account_restore` usa `modes=("paper-live",)` | `test_account_journal_future` (3), `test_account_restore_scope` (2) |
| G12 | B1 | `stop()` descartaba el booleano de `flush_persistence`; una cola que no vaciaba en 10 s salía sin decir nada | **RESUELTO** | `persistence_flushed` y `last_error` dicen cuántas escrituras quedaron; log de error | `test_a_stop_that_cannot_drain_the_persistence_queue_says_so`, `test_a_clean_stop_reports_the_record_flushed` |
| G13 | B2 | `_manage_position` comparaba solo el **lado** de la posición con el round trip; un fill no visto (tamaño distinto) o un venue plano con round trip abierto pasaban sin bloqueo | **RESUELTO** | tamaño comparado con tolerancia de un lote; venue plano con round trip abierto y sin salida en vuelo ⇒ bloqueo `position_unverified` + halt; nada se inventa para puntuar | `test_a_position_larger_at_the_venue_than_the_tracked_leg_blocks_entries`, `test_a_venue_flat_behind_a_tracked_round_trip_...` |
| G14 | B1 | (hallado al correr G8) `_poll_resting`/`_poll_protective` re-escribían la fila de una orden **parcialmente** llena en cada ciclo; con reloj simulado la cola de persistencia no vaciaba en 10 s | **RESUELTO** | `_save_order_if_changed` escribe solo cuando cambian estado, nº de fills o cantidad llena | `test_account_restore::test_partial_fills_and_fees_rebuild_identically_however_often` pasa en 8 s (58 s y fallo durante el desarrollo) |
| S1 | B4 | `_percentiles` truncaba el índice (`int(alpha*last)`): sesgo hacia el centro de hasta un estadístico de orden en ambos extremos | **RESUELTO** | interpolación lineal (Hyndman-Fan 7); la serie constante sigue degenerando a sí misma | `test_inference_quantiles` (4; 3 fallan en el árbol previo) |
| S2 | B4 | un valor NaN/inf en los retornos producía un intervalo (NaN ordena en cualquier sitio) | **RESUELTO** | `block_bootstrap_ci`/`iid_bootstrap_ci` devuelven `None` si algún valor no es finito; `verdict` ya trataba `None` como INSUFFICIENT | `test_non_finite_returns_give_no_interval_rather_than_a_bound` |
| S3 | B4 | la familia de Bonferroni era la de **una corrida**: tres corridas con un candidato cada una sobre la misma validación leían tres veces al nivel nominal | **RESUELTO** | `research_runs.jsonl` (junto al libro del holdout) registra cada corrida; la familia es la unión de candidatos (`estrategia@horizonte@hash-del-código`) que alguna vez se juzgaron sobre la misma partición (`dataset:split:purge:embargo`); el veredicto usa el nivel acumulativo | `test_experiment_integrity` (2) |
| S4 | B4 | TOCTOU del libro del holdout: `check` → cómputo → `record`; una muerte intermedia dejaba el acceso sin registrar | **RESUELTO** | `HoldoutLedger.open_access` escribe la línea `opened` antes de computar (fsync) y `completed` después; un repeat tras un `opened` sin completar se rechaza diciendo que el dato se leyó; las líneas antiguas leen como `completed` | `test_holdout_ledger_atomicity` (3) |
| S5 | B4 | estacionariedad: ninguna lectura de estabilidad temporal | **PARCIAL** | `half_split` por celda de validación (medias de cada mitad, mismo signo), **informativo**: ningún veredicto lo lee | `test_a_different_partition_is_its_own_family_and_the_record_carries_the_half_split` |
| S6 | B4 | tamaño de muestra / horizonte de restauración de riesgo (2 días) | **NO REPRODUCIDO** | `min_trades` ya gobierna el veredicto; el lookback de 2 días cubre el cooldown más largo configurable; sin cambios | revisión de `inference.verdict` y `RiskStateRepository.rebuild` |
| R1 | B2 | multiplicadores del presupuesto de riesgo (drawdown, volatilidad, racha) calculados pero inertes para el tamaño (`live.py` lee solo `allows_new_trades`; `runtime/engine.py` igual) | **PENDIENTE** | no se cambió: la documentación afirma "volatility targeting"; es una decisión de diseño del usuario (activar los multiplicadores sobre `approved_quantity` con test, o retirar la afirmación) | `grep` en `live.py:1838` y `risk/budget.py` |
| F6 | B5 | ver G10 | **PARCIAL** (era NO ABORDADO) | | |

### 3.3 Hallazgos de B5 documentados, sin cambio (nunca se activa trading real)

- El adaptador `data/providers/binance_live.py` usa **Spot** (`/api/v3/order`, `/api/v3/openOrders`): no existe
  `reduceOnly`; el flag `reduce_only` del runtime solo tiene efecto en el motor paper (G5). En Spot un
  cierre de más de lo que se tiene se rechaza por saldo; una "posición corta" no existe. Si el objetivo es
  perpetuos (el paper acumula funding y liquidación), la ruta live necesita el adaptador de futuros y el
  mapeo `reduceOnly`: **PENDIENTE** y previo a cualquier activación.
- La ruta live ahora recibe `prior_risk_state` y deadline, pero **no** restaura la cuenta del diario; la
  reconciliación clasifica el saldo del venue (ya existía). Lo que falta para que F6 sea RESUELTO es una
  prueba contra testnet/venue real, imposible desde aquí (egreso bloqueado) y fuera del mandato.
- Preparación segura de pruebas live: `test_live_path_parity::test_the_live_arming_path_goes_through_the_shared_helper`
  recorre `_arm_live_locked` con el gate y el constructor del venue sustituidos; no toca red ni credenciales.

---

## 4. Cambios realizados y razones

| Archivo | Cambio | Razón |
|---|---|---|
| `runtime/live.py` | `UNKNOWN_POLLS_BEFORE_LOST`; `_read_tracked_order`, `_count_unknown`, `_poll_resting`, `_poll_tracked_orders`, `_save_order_if_changed`, `_forget_tracked`, `_persist_heartbeat`; cambios en `_sync_protective_stop`, `_poll_protective`, `_poll_pending_exit`, `_manage_resting` (salida a mercado por `_submit_exit`), `_cancel` (fills), `_close_position` (relectura), `_cancel_all_open`, `emergency_flatten`, `_reconcile` (G8), `_submit` (toda entrada no terminal rastreada), `_manage_position` (G13), `_cycle_once` (G7, heartbeat), `stop()` (G12); ids sintéticos con `run_id`; contadores `order_poll_failures`, `orders_lost`; campos `_unconfirmed_cancels`, `_flush_timeout_seconds`, `persistence_flushed`, `_heartbeat_every_seconds` | G1–G4, G6–G8, G12–G14 |
| `execution/paper.py` | `reduce_only` en `Order`; rechazo en `submit_order` si no reduce; recorte y expiración en `_try_fill`; `_reduces` | G5 |
| `domain/orders.py` | `Order.reduce_only: bool = False` | G5 |
| `api/state.py` | `_start_session_with_run_row` (compartido), `_foreign_session_lease`, `_probe_lease_then_resume`, `LEASE_PROBE_SECONDS`; `_arm_live_locked` y `_build_live_runtime` por el helper con `prior_risk_state` y deadline; `_start_paper_realtime_locked` rechaza lease ajeno y usa el helper; `_maybe_resume_paper_realtime` decide antes de sellar; `shutdown` libera el lease; `_persist` acepta `run_heartbeat`; `_load_account_restore` con `modes=("paper-live",)` | G9, G10, G11 |
| `persistence/repositories.py` | `RunRepository.heartbeat`, `release_lease`, `open_sessions` | G9 |
| `runtime/session_limits.py` | `HEARTBEAT_KEY`, `LEASE_SECONDS`, `encode_heartbeat`, `clear_heartbeat`, `decode_heartbeat`, `lease_age_seconds`, `lease_is_held`; `ResumeDecision.held_by_other`; `resume_decision(lease_seconds=…)` | G9 |
| `portfolio/account_journal.py` | `FUTURE_EVENT_TOLERANCE_SECONDS`; eventos futuros no plegados ⇒ `complete=False` con motivo y `checks["future_events"]` | G11 |
| `backtest/inference.py` | `_quantile` interpolado; `_all_finite` en ambos bootstraps | S1, S2 |
| `backtest/holdout.py` | `HoldoutAccess.status`; `open_access`; mensaje de rechazo para `opened`; fsync al escribir | S4 |
| `scripts/strategy_experiment.py` | `--research-log`; `prior_candidates`/`append_research_log`; familia acumulativa; `opened`/`completed` en el libro; `half_split`; `percentile_method` en el registro | S3, S4, S5 |

Lo que **no** se cambió a propósito: ningún parámetro de estrategia, riesgo o costos; ningún test existente;
ningún controlador se debilitó (los bloqueos añadidos solo restringen); ninguna dependencia nueva; ninguna
migración (el heartbeat vive en `runs.notes` JSON como ya lo hacía el deadline).

Decisiones de diseño discutibles, para revisión:

- **Lease de 120 s y sonda de 45 s.** Un reinicio tras una **muerte dura** dentro del lease espera la sonda
  antes de reanudar (la API arranca igual); un redeploy limpio reanuda al instante porque `shutdown` libera el
  lease. La alternativa (reanudar siempre) es exactamente el defecto G9.
- **"Orden abierta no rastreada" ⇒ SAFE_MODE.** Conservador; en un venue compartido con órdenes manuales del
  mismo símbolo saltará. Es el comportamiento que el documento de arquitectura pide ("el venue gana").
- **Tres lecturas "unknown" antes de dar una orden por perdida.** Un venue que indexa con retraso justifica
  la tolerancia; tres respuestas negativas consecutivas con entradas ya bloqueadas es el límite elegido.
- **Familia acumulativa por hash del código de estrategia.** Más conservadora que la de una corrida; un
  cambio en `tia/strategy/*.py` cuenta como candidato nuevo (es lo que se quiere penalizar).

---

## 5. Pruebas ejecutadas: comandos y resultados

Entorno: `.venv/bin/python` (3.11), `PYTHONPATH=packages/tia/src`, opciones
`-p no:cacheprovider -o addopts="--strict-markers --strict-config" -q`.

### 5.1 Línea base al inicio (árbol de inicio de la fase, antes de cualquier cambio)

```
ruff check packages tests scripts          → All checks passed!
pytest tests/unit                          → 1322 passed, 6 warnings in 91.79s
pytest tests/integration                   → 238 passed in 147.64s
pytest tests/property                      → 31 passed in 23.78s
pytest tests/failure                       → 12 passed in 3.17s
pytest tests/adversarial                   → 16 passed in 7.12s
pytest tests/e2e                           → 8 passed in 96.50s
```

### 5.2 Suites completas al final (mismo comando, árbol final)

```
ruff check packages tests scripts          → All checks passed!
pytest tests/unit                          → 1346 passed, 6 warnings in 86.70s (0:01:26)
pytest tests/integration                   → 274 passed in 215.77s (0:03:35)
pytest tests/property                      → 31 passed in 24.20s
pytest tests/failure                       → 12 passed in 3.03s
pytest tests/adversarial                   → 16 passed in 7.16s
pytest tests/e2e                           → 8 passed in 86.80s (0:01:26)

Nota: una primera corrida completa sobre un árbol intermedio (antes del último ajuste de `state.py`) dio `integration: 4 failed, 270 passed`. Tres fallos eran interacciones reales con los cambios de esta fase y se corrigieron (el helper live leía `session_deadline` de un runtime falso que no lo tiene → `getattr`; el heartbeat quedaba en `notes` tras un stop de operador y `test_without_max_hours_the_session_has_no_deadline` esperaba la columna vacía → un run sellado libera el lease). El cuarto, `test_restart_recovery.py::test_restart_recovery` (0 de 2 `edge_outcomes` persistidos), pasa aislado y en dos corridas completas posteriores (274/274 ambas); su causa probable es preexistente y ajena a esta fase — el motor de escenarios persiste con tareas sin secuenciar y una espera fija de 0,5 s; el log de esa corrida muestra un `persist_failed ... FOREIGN KEY constraint failed` en `fills` del mismo test — y queda anotada como PENDIENTE para la Fase 1.4.
```

### 5.3 Pruebas nuevas (60) y su comportamiento contra el árbol de inicio

Las copias para el árbol previo están en el scratchpad (`prefix_tests/`, importaciones con `getattr` donde el
nombre no existía) y se corrieron con `-o pythonpath=<árbol de inicio reconstruido: git archive HEAD +
tracked_start + untracked_start>`.

| Archivo | Pruebas | En el árbol de inicio | En el árbol final |
|---|---|---|---|
| `tests/integration/test_order_integrity.py` (G1–G4, G6) | 8 | 8 fallan | 8 pasan |
| `tests/unit/test_paper_reduce_only.py` (G5) | 6 | 5 fallan, 1 pasa (preservación: la orden ordinaria sigue dando la vuelta) | 6 pasan |
| `tests/integration/test_runtime_invariants.py` (G7, G8, G12, G13) | 10 | 8 fallan, 2 pasan (preservación: nada se envía en PAUSED/SAFE_MODE) | 10 pasan |
| `tests/integration/test_session_lease.py` (G9) | 7 | no importa (la función no existía) | 7 pasan |
| `tests/unit/test_session_lease.py` (G9) | 8 | no importa | 8 pasan |
| `tests/integration/test_live_path_parity.py` (G10) | 5 | 5 fallan | 5 pasan |
| `tests/integration/test_account_restore_scope.py` (G11) | 2 | 1 falla (la aplicación), 1 pasa (el repositorio ya aceptaba `modes`) | 2 pasan |
| `tests/unit/test_account_journal_future.py` (G11) | 3 | 3 fallan | 3 pasan |
| `tests/unit/test_inference_quantiles.py` (S1, S2) | 4 | 3 fallan, 1 pasa (preservación: serie constante) | 4 pasan |
| `tests/unit/test_holdout_ledger_atomicity.py` (S4) | 3 | 3 fallan | 3 pasan |
| `tests/integration/test_experiment_integrity.py` (S3, S5) | 2 | no aplicable (el guion vive en `scripts/`, fuera del árbol sustituible) | 2 pasan |
| `tests/integration/test_adverse_recovery.py` (Etapa C) | 2 | no corrido en el árbol previo (prueba de invariantes, no de defecto) | 2 pasan |

Resultado agregado de las copias contra el árbol de inicio: `30 failed, 4 passed, 2 errors` (A/B) y
`6 failed, 1 passed` (C); registros en `prefix_results_stageAB.txt` y `prefix_results_stageC.txt`.

### 5.4 Corridas intermedias relevantes

- Reproducción manual de G1 antes de corregir (`repro/g1_repro.py`): `stops resting after failed cancel: 2`,
  el stop rastreado ≠ el primero, `stops_placed=3`; tras la corrección: `1`, el rastreado = el primero.
- Suites afectadas tras la Etapa A (1.2 + nuevas): `115 passed`; unitarias completas: `1322 passed`.
- Suites afectadas tras la Etapa B: `213 passed`; las 35 pruebas nuevas de B: `35 passed`.
- `test_strategy_experiment_script.py` (2) y `test_inference.py` + `test_holdout_ledger.py` (29) tras la Etapa C: pasan.

---

## 6. Pruebas no ejecutadas y por qué

| Qué | Por qué no |
|---|---|
| Validación paper con datos de mercado reales (ni corta ni prolongada) | **BLOQUEADO**: egreso a Binance `CONNECT 403` desde este entorno; el mandato prohíbe inventar precios; tres criterios de preparación del operador sin cumplir (§8) |
| Cualquier prueba contra testnet o venue real (F6/G10, `reduceOnly`, user stream) | **BLOQUEADO** por mandato (sin endpoints privados, sin credenciales) y por red |
| Verificación del estado del VPS / imagen desplegada | **BLOQUEADO** por mandato (sin despliegues ni acceso) |
| Cómputo del holdout (incluso sobre fixtures sintéticas) con `--unlock-holdout` | **no ejecutado a propósito**: el mandato prohíbe usar el holdout; la atomicidad del libro se probó a nivel unitario (`open_access`) |
| Prueba de regresión específica para la salida a mercado de una limit reductora expirada (ahora por `_submit_exit`) | requiere una secuencia señal-inversa con entradas limit difícil de forzar determinísticamente; el camino queda cubierto por los invariantes de `test_exit_guard` y `test_runtime_invariants`; **PENDIENTE** una prueba dedicada |
| Prueba de "muerte dura dentro del lease" con un runtime real en otro proceso | se simuló escribiendo el heartbeat ajeno a mano y avanzándolo en una tarea paralela; no se lanzó un segundo proceso Python |
| Paridad backtester–sesión (C4) y sus pruebas | **PENDIENTE**: no abordado por tiempo; es infraestructura experimental, no un defecto de ejecución |

---

## 7. Estado de persistencia y recuperación

| Aspecto | Estado | Evidencia |
|---|---|---|
| Fila del run antes del loop; arranque fallido sellado y anotado | **RESUELTO** paper y (helper) live | `test_session_start_atomicity` (6), `test_live_path_parity` (5) |
| Cuenta paper restaurada del diario (cash, posición, pico, día UTC, plan, creencias) | **RESUELTO** | `test_account_restore` (12), `test_account_journal` (11) |
| Diario inconsistente con la tabla de fills ⇒ restauración incompleta ⇒ entradas bloqueadas, posición gestionable | **RESUELTO** | `test_a_lost_journal_write_...`, `test_a_store_that_loses_the_fills_table_...` |
| Eventos futuros ⇒ incompleta; eventos de runs live excluidos de la cuenta paper | **RESUELTO** | `test_account_journal_future`, `test_account_restore_scope` |
| Órdenes de sesiones paper anteriores selladas como huérfanas al arrancar; las de runs live **no** | **RESUELTO** | `test_a_live_start_does_not_stamp_an_earlier_runs_open_orders_as_orphaned` |
| Estado de riesgo del día restaurado (entradas, cooldown) en paper y live | paper RESUELTO (1.1/1.2); live **PARCIAL** (sin venue) | `test_risk_restore`, `test_live_path_parity` |
| Escrituras pendientes vaciadas al detener; resultado reportado | **RESUELTO** | G12 |
| Reanudación tras reinicio: solo runs sin sello; halts pegajosos; deadline conservado; **lease multiproceso** | **RESUELTO** | `test_live_api` (resume), `test_session_lease` |
| Heartbeat cada 30 s de pared; liberado en apagado limpio | **RESUELTO** | `test_a_running_session_stamps_its_heartbeat_and_a_clean_shutdown_releases_it` |
| Órdenes abiertas en el venue vs registros de la sesión | **RESUELTO** | G8 |
| Posición del venue vs round trip (lado **y** tamaño; venue plano) | **RESUELTO** | G13 |
| Recuperación contra un venue real (saldo, posiciones, órdenes) | **BLOQUEADO** | — |

Límite conocido (sin cambio): una muerte dura entre un fill del motor y la escritura de su evento deja el
diario corto; la siguiente restauración lo detecta por la tabla de fills (incompleta ⇒ bloqueo), no lo
repara. Es la conducta deseada ("bloquear, no inventar").

---

## 8. Validaciones paper realmente ejecutadas y lista de preparación

### 8.1 Lista de criterios verificables (Etapa C)

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | Lint y las seis suites verdes sobre el árbol a validar | ✔ | §5.2 |
| 2 | Las cancelaciones se creen solo por respuesta del venue; un cancel fallido bloquea y mantiene el rastreo (F1, G1, G2) | ✔ | `test_paper_cancellations`, `test_order_integrity` |
| 3 | Una sola salida en vuelo por posición; nunca una salida sobre un stop no confirmado ni sobre una posición plana (F2, G4) | ✔ | `test_exit_guard`, G4 |
| 4 | Reduce-only aplicado por el venue simulado (G5) | ✔ | `test_paper_reduce_only` |
| 5 | Cuenta, pico, día UTC y plan sobreviven al reinicio; inconsistencias bloquean (F3/F4, G11) | ✔ | §7 |
| 6 | Una sesión por cuenta dentro del proceso **y** entre procesos (F5, G9) | ✔ | `test_session_start_atomicity`, `test_session_lease` |
| 7 | Fila del run antes del loop; arranque fallido no deja sesión (F8, G10) | ✔ | §7 |
| 8 | Órdenes leídas en todo estado y sin vela nueva (G7) | ✔ | `test_runtime_invariants` |
| 9 | Reconciliación compara el venue con los registros de la sesión (G8) | ✔ | idem |
| 10 | Tamaño de la posición del venue coherente con el round trip (G13) | ✔ | idem |
| 11 | El stop dice si la persistencia quedó corta (G12) | ✔ | idem |
| 12 | Datos de mercado reales accesibles desde el entorno de la corrida | ✘ **BLOQUEADO** (`CONNECT 403`) | fase anterior |
| 13 | Comisiones verificadas en origen (`FeeSchedule.verified_at_source`) | ✘ **PENDIENTE** (operador: `validate_binance.py` o asumir tier estándar) | `economics/costs.py:54` |
| 14 | La imagen desplegada es el árbol corregido (commit + despliegue por el usuario) | ✘ **BLOQUEADO** por mandato | — |
| 15 | Decisión sobre el dimensionamiento por presupuesto de riesgo (R1) | ✘ **PENDIENTE** | §3.2 |

Conclusión de la Etapa C: **11/15**; los cuatro restantes son del operador y ninguno se puede cumplir desde
aquí sin violar el mandato. Por tanto **no se ejecutó ninguna validación paper con datos reales**.

### 8.2 Simulaciones adversas deterministas ejecutadas (sustituto honesto)

| Escenario | Resultado |
|---|---|
| 500 velas con venue que rechaza 20 % y fuerza parciales 40 % (semilla fija), persistencia real en SQLite | ≤ 1 stop en todo momento, libro nunca contrario al round trip, ≤ 1 salida en vuelo; la reconstrucción del diario es **completa** e igual al motor (cash, fees, posición, nº de fills) — `test_rejects_and_partials_over_hundreds_of_bars_...` |
| La tabla `fills` pierde todas sus escrituras durante la sesión; el proceso muere con posición abierta | la reconstrucción es **incompleta** y nombra la discrepancia; la sesión siguiente no adopta la pierna, no envía entradas ni salidas sobre una posición que no rastrea, y lo dice (`account_state`, `position_unverified`) — `test_a_store_that_loses_the_fills_table_...` |
| Stop ejecutado en el venue durante SAFE_MODE; salida ejecutada sin vela nueva | contabilizados en el ciclo siguiente — G7 |
| Reinicio con salida pendiente, con entrada limit descansando, con posición abierta (1.2) | re-ejecutados — `test_account_restore` |
| Lease ajeno fresco; lease que avanza; lease que no avanza; sin lease; apagado limpio | arranque rechazado / no reanudado y sin sellar con alerta / reanudado tras la sonda / reanudado al instante — `test_session_lease` |

Nada de lo anterior es evidencia sobre un mercado: son pruebas de plomería con datos sintéticos.

---

## 9. Limitaciones de datos e inferencia

- **Datos.** No hay velas reales en el repositorio; las fixtures son sintéticas y el propio código lo dice en
  cada salida. Los 265.611 resultados de `edge_outcomes` provienen de un generador con deriva impuesta. La
  única evidencia real son 2 round trips exploratorios (12 h), ambos perdedores por stop.
- **Egreso.** Bloqueado (`403` del proxy) para Binance; cualquier dato real debe aportarlo el operador con
  hash y rango (BTCUSDT 1 m ≥ 180 días; 1 h ≥ 3 años).
- **Backtester ≠ sesión.** El harness opera entradas a mercado, stop fijo, sin EV, sin HTF, sin trailing ni
  objetivo (C4 pendiente): un veredicto del harness no transfiere a la sesión.
- **Comisiones** 2,5/7,5 bps configuradas, 10/10 estándar, sin verificar (`requires_verification=True`).
- **Confianza no calibrada**; cobertura exacta de buckets = 30 × 30 = 900 round trips reales; a la frecuencia
  medida, años.
- **Inferencia.** Intervalos por block bootstrap (ahora con percentiles interpolados y familia acumulativa);
  el veredicto exige ≥ `min_trades`; la lectura por mitades es informativa. Nada aquí mide rentabilidad.
- **Simulador sin libro.** Limit optimista (sin cola) y pesimista (trade-through); stop al peor de stop/open;
  ningún fill real para calibrarlo.

---

## 10. Oportunidades de estrategia (máximo cinco, ordenadas)

Criterios de orden: impacto potencial, calidad de la evidencia hoy, aislabilidad del efecto, costo, riesgo de
sobreajuste, dependencias. Ninguna se recomienda implementar hoy; todas requieren datos reales (C6) y las
correcciones C1–C4 del informe de investigación (consolidar/desplegar; comisiones; decisión de
dimensionamiento; paridad de salidas en el backtester).

| Rango | Id | Oportunidad | Impacto | Evidencia hoy | Aislabilidad | Costo | Sobreajuste | Depende de |
|---|---|---|---|---|---|---|---|---|
| 1 | A | **Horizonte**: a 15 m–4 h la relación objetivo/costos hace viable la misma regla (a 1 m p* ≈ 0,88 con costo 11 bps; > 1 con 16 bps) | alto | aritmética sobre σ medida en 12 h + 2 trades | alta (un parámetro) | bajo (harness existe) | medio (familia 12–16) | C2, C6 |
| 2 | B | **Estructura de salidas**: stop fijo vs BE vs trailing vs objetivo; cambia la distribución, no la expectativa | medio | literatura; 0 datos propios | alta (pareado por señal) | medio (C4) | bajo-medio | A, C4 |
| 3 | D | **Entrada limit con timeout vs market**: ahorro de costos vs selección adversa y fills perdidos | medio | 2 fills maker | alta (misma señal, dos ejecuciones) | medio (C4) | bajo | A, C4 |
| 4 | C | **Ablación de filtros de régimen y HTF**: ¿eliminan señales peores que las que conservan? | medio | 0 (HTF fue no-op en 12 h) | media | bajo | medio | A |
| 5 | E | **Calibración de la confianza / buckets del EV** (exploratoria, observacional) | bajo-medio | 0 | alta (medición) | bajo | bajo | A |

Descartadas razonadamente (no entran): más indicadores o una cuarta estrategia; pronosticadores ML; optimizar
parámetros a 1 m; stops más ajustados; aumentar exploración o bajar el piso de 30; usar evidencia sintética
para autorizar tamaño; el LLM en la ruta de decisión; multi-símbolo/carry/libro.

---

## 11. Experimentos propuestos (once campos cada uno)

Campos: (1) hipótesis, (2) mecanismo, (3) cambio mínimo, (4) métrica primaria, (5) métricas de protección,
(6) datos necesarios, (7) diseño y particiones, (8) costos modelados, (9) riesgos estadísticos
(multiplicidad, leakage, selección, dependencia), (10) criterio de rechazo, (11) dependencias y estado.

### A — Horizonte y geometría frente a costos

1. A 1 m la expectativa neta de las tres estrategias es negativa por geometría; a ≥ 15 m la misma regla puede
   tener expectativa neta no negativa. **[HIPÓTESIS]**
2. Costos de ida y vuelta fijos (≈ 11 bps maker-in, ≈ 16 taker-taker); la distancia capturada escala con
   √horizonte; `p* = (S + c)/(T + S)`: 1 m 0,88 / 5 m 0,61 / 15 m 0,52 / 1 h 0,46 / 4 h 0,43 (c = 11).
3. Ninguno en estrategia: `--timeframes 15m,1h,4h` en el harness; velas 1 h nativas para 1 h/4 h.
4. Media neta por trade (bps) con intervalo block-bootstrap al nivel Bonferroni **acumulativo**; veredicto
   pre-registrado de `tia.backtest.inference`.
5. Trades por celda ≥ 30; PF > 1,2; maxDD < 1 %; exposición y trades/1.000 velas; `random_entry` y
   `always_flat` emparejados; `half_split` con el mismo signo.
6. BTCUSDT 1 m ≥ 180 días (259 k velas), 1 h ≥ 3 años, 4 h ≥ 5 años, con hash. Faltan: no hay datos reales.
7. Particiones 50/30/20 cronológicas, purga 20 + embargo 30 velas del horizonte; cada estrategia sola;
   ensemble como candidato extra solo si alguna celda no es UNFAVOURABLE; holdout sellado.
8. Comisiones verificadas ×1, ×1,5, ×2; slippage +0/+2 bps; entradas market (y limit tras C4); sin funding.
9. Familia explícita 3 × 4 = 12 (16 con ensemble), acumulada en `research_runs.jsonl`; warm-up solo hacia
   atrás; ningún parámetro se mueve entre lecturas; block bootstrap; lectura por mitades.
10. Si todo horizonte ≤ 15 m es UNFAVOURABLE/FRAGILE/INSUFFICIENT con ≥ 30 trades, se abandona 1 m; si a 1 h/4 h
    el límite inferior ajustado ≤ 0 en todas las estrategias, la hipótesis se rechaza y el siguiente paso es la
    señal, no la geometría.
11. Depende de C2 (comisiones) y C6 (datos). Estado: **diseñado, no ejecutable aquí** (sin datos reales).

### B — Estructura de salidas

1. BE a 1R y trailing 2×ATR convierten ganadores en empates y recortan la cola derecha; efecto neto ≤ 0 a
   horizontes cortos aunque reduzcan la pérdida máxima; el objetivo a 3×ATR deja dinero en tendencia.
2. Un stop que se estrecha reduce varianza y drawdown pero sesga hacia pequeñas pérdidas/empates; su valor
   depende de la autocorrelación tras 1R, que se mide.
3. C4: `exit_variant ∈ {fixed_stop, be_only, trail_only, be+trail, be+trail+target}` en el backtester
   reutilizando `tia/execution/exits.py` y la regla de objetivo de la sesión.
4. Diferencia **pareada** por señal de la media neta (bps) frente a `fixed_stop`, bootstrap de las diferencias.
5. Payoff, p90 de ganadores, maxDD, duración media; nº de trades sin cambio.
6. Los de A en el horizonte superviviente.
7. Misma validación, mismas señales, cinco variantes; k = 5 por estrategia.
8. BE/trailing como stops (taker al peor de stop/open); objetivo taker al open siguiente.
9. Dependencia entre variantes (comparten entradas) ⇒ diferencias pareadas, no intervalos marginales; sin
   múltiplos de ATR nuevos.
10. Si el límite inferior de la diferencia pareada ≤ 0, se conserva el stop fijo; una variante que mejora DD
    > 20 % sin empeorar expectativa se marca "candidata de riesgo", no de rentabilidad.
11. Depende de A y C4. Estado: **diseñado**; C4 **PENDIENTE**.

### D — Entrada limit con timeout vs market

1. La entrada post-only ahorra ≈ 5 bps + spread pero se llena cuando el precio va contra la tesis y pierde los
   trades que arrancan sin volver; el ahorro por trade llenado no compensa el costo de oportunidad por señal.
2. Momentum: los mejores trades de tendencia/ruptura no retroceden; una limit al toque se queda fuera de ellos.
3. C4: `entry_order_type ∈ {market, limit}` con trade-through y timeout 3 velas; spread = `base_slippage_bps`
   declarado como supuesto.
4. P&L neto **por señal** (cero para las no llenadas); comparación pareada market vs limit.
5. Tasa de fill, tiempo a fill, media neta de las llenadas, P&L de señales perdidas bajo market.
6. Los de A; idealmente registro de bookTicker real para calibrar el spread (no existe).
7. Misma validación; dos variantes; tres supuestos de fill (estricto, ≥ 1 tick, toque) que acotan.
8. Maker vs taker verificados; spread supuesto y su sensibilidad.
9. El simulador sin cola sobreestima fills limit: reportar horquilla, no punto.
10. Si bajo el supuesto pesimista el P&L por señal con limit ≤ market, la limit no se justifica por costos.
11. Depende de A y C4. Estado: **diseñado**.

### C — Ablación de filtros de régimen y HTF

1. El gate de régimen y el HTF `hard` eliminan señales sin mejorar la expectativa de las que quedan a
   1 m–15 m; a 1 h+ la marea semanal sí aporta.
2. Un filtro ayuda si las señales que elimina tienen peor expectativa que las conservadas, neto de la pérdida
   de muestra; los umbrales se calibraron sobre un generador sintético.
3. Banderas de ablación: régimen siempre aplicable, `max_volatility_percentile=1.0`, HTF off/soft/hard.
4. Diferencia de media neta entre señales conservadas y eliminadas (mismo run sin filtro), con bootstrap;
   expectativa total con/sin filtro.
5. Trades conservados ≥ 50 % o expectativa claramente superior; maxDD; permanencia y parpadeo por régimen.
6. Los de A + velas 1 h para HTF.
7. Un filtro por vez; cada ablación es un candidato.
8. Idénticos entre variantes.
9. Cambiar un gate altera la secuencia posterior: comparar poblaciones de señales, no curvas de equity;
   umbrales **no** se re-ajustan.
10. Si las señales eliminadas no tienen peor expectativa (IC de la diferencia contiene 0), el filtro no se
    justifica como mejora y se conserva solo si reduce DD de forma clara.
11. Depende de A. Estado: **diseñado**.

### E — Calibración de la confianza y buckets del EV (exploratoria)

1. La "fuerza" fusionada no ordena el retorno bruto realizado; las bandas de confianza no aportan información
   y triplican el tiempo de llenado del estimador.
2. Un score heurístico sin calibración puede ser ruido ordinal.
3. Ninguno en producción: análisis sobre `DecisionRecord` + trades del harness.
4. Spearman y monotonicidad (media bruta por banda con IC) entre confianza y retorno bruto, por estrategia.
5. Tamaño por banda ≥ 30; repetición en research y validation.
6. Los de A.
7. Observacional; ninguna decisión de trading cambia hasta el resultado.
8. Bruto (la calibración es sobre la señal).
9. Confusión vía régimen: estratificar.
10. Si la monotonicidad se sostiene en ambas particiones, las bandas se quedan; si no, se propone (cambio
    separado con test) pooling estrategia × régimen × dirección.
11. Depende de A. Estado: **diseñado**.

Integridad experimental (Etapa F): particiones cronológicas con purga y embargo, warm-up solo hacia atrás,
holdout sellado con libro `opened`/`completed`, parámetros congelados y hasheados (config + código de
estrategia), familia acumulativa por partición en `research_runs.jsonl`, lectura por mitades, veredicto
pre-registrado que nunca dice "rentable".

---

## 12. Bloqueos pendientes

| Bloqueo | Tipo | Quién lo resuelve |
|---|---|---|
| Egreso a Binance (`403`) ⇒ sin datos reales ni validación paper | BLOQUEADO (entorno) | operador: aportar CSV con hash, o entorno con red |
| Commit, push y despliegue del árbol corregido (56 + 14 archivos sin commit) | BLOQUEADO (mandato) | usuario |
| Comisiones verificadas en origen (C2) | PENDIENTE | operador |
| Decisión sobre multiplicadores del presupuesto de riesgo (R1) | PENDIENTE (diseño) | usuario |
| F6/G10 en live: validación contra testnet; adaptador Spot sin `reduceOnly`; ¿Spot o perpetuos? | PARCIAL / PENDIENTE | usuario + entorno con red |
| Paridad backtester–sesión (C4) para B, D y C | PENDIENTE | trabajo posterior (≈ 1 día) |
| Persistir decisiones por señal, régimen por vela, MAE/MFE (C5) | PENDIENTE | trabajo posterior |
| Prueba dedicada de la salida a mercado tras una limit reductora expirada | PENDIENTE | trabajo posterior (pequeño) |
| Frontend: `entry_blocks`, `pending_exit`, `account_state`, lease, `orders_lost` no se muestran | PENDIENTE (API compatible) | trabajo posterior |

---

## 13. Siguiente paso recomendado

1. **Revisar este diff y decidir el commit/despliegue** (usuario). Hasta entonces ninguna corrida paper en el
   VPS es interpretable: la imagen desplegada tiene F1–F8 y G1–G13.
2. **Decidir R1** (dimensionamiento por presupuesto) y **verificar comisiones** (C2); ambos cambian lo que una
   corrida paper mide.
3. **Aportar datos reales** (C6) fuera de este entorno y correr el experimento **A** con el harness congelado
   (familia pre-registrada, holdout sellado, `research_runs.jsonl` como memoria de multiplicidad). Regla de
   decisión fijada ahora: si todo horizonte ≤ 15 m es UNFAVOURABLE/FRAGILE con n ≥ 30, el desarrollo a 1 m se
   detiene y la sesión 24/7 pasa a ser solo instrumento de medición; si algún horizonte logra límite inferior
   ajustado > 0, se abren B y D en ese horizonte (requieren C4).
4. Solo con 1–3 cumplidos: **validación paper limitada** (horas, con deadline, bajo la lista de §8.1 con 15/15),
   sin tocar parámetros durante la ventana, con el forense previo como protocolo de lectura.

Lo que este informe **no** dice: nada sobre rentabilidad ni sobre el comportamiento con un venue real. Lo que
sí dice: los caminos de ejecución, contabilidad y recuperación de la sesión paper tienen ahora, para cada
defecto conocido, una causa identificada, una corrección mínima y una prueba que falla sin ella.
