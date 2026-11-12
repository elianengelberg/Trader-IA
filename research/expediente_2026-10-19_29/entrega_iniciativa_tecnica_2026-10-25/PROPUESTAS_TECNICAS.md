# Registro de iniciativa técnica (ciclo 1, 2026-10-25)

**Base:** candidato de la integración controlada, árbol `17332e1c…` (parches 01–15).
**Resultado de este ciclo:** parches 16–22, árbol `T22` = `87af7a45…` (ver `parches/CADENA_TI.txt`). T21 = `bcfa4008…` es el último árbol con cambios de código; el 22 solo corrige documentación.
**Estado de autorización:** NO AUTORIZADO PARA OPERAR CON DINERO REAL. Nada de esto se commiteó, se publicó ni se conectó a un exchange.

## Convenciones

- **Categorías:**
  - **A**: decidir e implementar.
  - **B**: investigar, experimentar y recomendar.
  - **C**: requiere tu autorización.
- **Estados:** propuesta · investigando · validada · implementada · descartada · pendiente de autorización.
- **Hechos, hipótesis y riesgos:** cada entrada separa lo observado (con la ruta de la evidencia) de lo que sigue siendo hipótesis. Ninguna cifra de mejora está estimada a ojo: cada número sale de un experimento citado o se declara como faltante.

## Índice

| Id | Título | Cat. | Severidad / beneficio | Estado |
|---|---|---|---|---|
| P01 | El kill switch dejaba la posición sin stop por tiempo indefinido | A | **Alta** (posición sin protección) | **implementada** (16; documentación en 22) |
| P02 | Un cierre de emergencia rechazado dejaba una barra sin protección | A | Alta | **implementada** (16) |
| P03 | El venue simulado se detenía con la sesión (PAUSED / SAFE_MODE) | A | Media (papel no fiel; el arreglo P01 no surtía efecto en papel) | **implementada** (16) |
| P04 | **El arreglo de R19 no tenía efecto en producción:** el despachador absorbía las fallas | A | **Alta** (pérdida silenciosa de datos) | **implementada** (19) |
| P05 | Las alertas dependían de la base de datos; un 500 contaba como entregado | A | Alta (operación sin aviso) | **implementada** (19) |
| P06 | `/api/metrics` no describía la sesión que tiene las posiciones | A | Media-alta (monitoreo ciego) | **implementada** (18) |
| P07 | La compuerta `EDGE_EVIDENCE` leía el motor equivocado y contaba trades sintéticos | A | Media (compuerta de dinero real) | **implementada** (17) |
| P08 | N3: el motor de escenarios decía «registro completo» con escrituras fallidas | A | Baja-media | **implementada** (19) |
| P09 | Huecos de detección de las pruebas (experimento de mutación) | A | Media-alta (pruebas verdes que no protegen; M18 = órdenes duplicadas) | **implementada** (20): los 6 sobrevivientes cubiertos; medida independiente en P24 |
| P10 | Hipótesis: la regla de EV aprueba ruido por comparaciones múltiples | B | — | **descartada** (refutada por experimento) |
| P11 | La razón de costos 0,6 es la que limita la potencia de la regla de EV | B | Beneficio potencial alto, riesgo alto | **validada como hallazgo**; cambio **no** recomendado todavía |
| P12 | Contaminación del estimador de EV con trades sintéticos (`legacy`) | B / C | Media | **investigada**; no fabricó ventaja en lo medido. Cambio del valor por defecto en producción: **pendiente de autorización** |
| P13 | `pytest.approx` sin tolerancia absoluta en 49 comparaciones de precios | B | Media (pruebas que no discriminan un tick) | propuesta |
| P14 | Dos motores de sesión duplicados (`RuntimeEngine` y `LiveRuntime`) | B | Alta para la mantenibilidad | propuesta (sin cambio estructural) |
| P15 | `runtime/live.py` tiene 5.000 líneas | B | Media | propuesta, **después** de P09/P13 |
| P16 | Hipótesis: Binance cobra la comisión de compra en el activo base y el stop pide más de lo que hay | C (testnet) | Alta si se confirma | propuesta (necesita testnet) |
| P17 | La sesión de papel no puede demostrar ventaja | B | Estratégico | validada (cálculo y experimento) |
| P18 | Prioridad cuantitativa: información antes que infraestructura | B / C | Estratégico | recomendación |
| P19 | Hipótesis nueva H-XS-REV-1 (reversión transversal de corto plazo), con especificación completa | B | — | propuesta; **no ejecutar antes de E3-H1** |
| P20 | Mutación dirigida como chequeo periódico (no en cada push) | B | Media | propuesta |
| P21 | N4: ids del stop por barra en el motor de escenarios | A | Baja | pendiente (no reproducido) |
| P22 | Al reanudar tras una pausa larga, el *watchdog* detenía la sesión por «datos viejos» con velas llegando | A | Media (alerta falsa; con P03, entradas detenidas una vela) | **implementada** (21) para papel; venue real: riesgo residual |
| P23 | La simulación y los *fixtures* dependen del reloj de pared | B | Media (resultados no comparables entre corridas) | **validada como hallazgo**; propuesta |
| P24 | Lote 2 de mutación: medida no contaminada de la suite | B | Media | **validada** (ver §P24) |
| P25 | Dos pruebas de *funding* fallan siempre en una ventana de ~6 min cada 8 h (05:40, 13:40 y 21:40 UTC) | B | Media (CI roja sin defecto; contaminó mi instrumento) | **validada** (reproducción determinista); corrección propuesta |

---

## P01 · El kill switch dejaba la posición sin stop por tiempo indefinido

- **Problema:** `kill_switch()` cancelaba **todas** las órdenes, incluido el stop protector, no cerraba la posición (por diseño) y dejaba la sesión en `SAFE_MODE`. En ese estado el ciclo no gestiona posiciones, así que nada repone el stop.
- **Evidencia (hecho):**
  - `logs/experimentos/exp_kill_antes.json`: después del kill switch, posición 0,080117 BTC, 0 stops en reposo, `SAFE_MODE`.
  - En la barra siguiente el precio cruzó el nivel del stop anterior y la posición siguió abierta.
  - `unprotected_positions = 0`: el sistema ni siquiera la contaba como desprotegida.
- **Alternativas:**
  - (a) conservar las órdenes que solo reducen la posición (su stop y un cierre en curso);
  - (b) cancelar todo y volver a poner un stop (más órdenes en plena emergencia);
  - (c) dejarlo así y solo avisar;
  - (d) convertir el kill switch en un cierre de emergencia (contradice la separación deliberada entre «el software duda» y «quiero salir»).
- **Decisión: (a).** No envía ninguna orden nueva y no aumenta la exposición, porque un stop reduce-only en spot no puede abrir una posición. Si no queda nada que proteja la posición, se cuenta como desprotegida y se dice (incidente, bloqueo, `last_error`), sin sacar a la sesión de `SAFE_MODE`.
- **Validación:**
  - `tests/integration/test_emergency_controls_protection.py`: 6 pruebas, **6 de 6 fallan sin el arreglo por la razón esencial** (`logs/sin_y_con_correccion/A1_SIN_correccion_razones.txt`) y pasan con él.
  - El experimento repetido (`logs/experimentos/exp_kill_despues.json`): el stop queda.
- **Prueba existente adaptada:** `test_order_integrity.py::test_the_kill_switch_keeps_tracking…` usaba el stop como ejemplo de cancelación no confirmada. Ahora el stop no se cancela, y la propiedad original se verifica sobre `_cancel_all_open()`, que es lo que usa el cierre de emergencia. No se debilitó.
- **Documentación (parche 22):** `docs/LIVE_RUNBOOK.md` §12 decía «cancela las órdenes en reposo» y `docs/DEPLOYMENT.md` §13 lo presentaba como «detener entradas, **seguir gestionando las salidas**». Lo segundo no era cierto ni antes ni después de P01: `SAFE_MODE` no gestiona la posición, sin *trailing*, *break-even* ni salida por tiempo. Los dos textos describen ahora lo que hace el código: conserva el stop y la salida en curso, no gestiona nada más, y avisa si no queda nada en el venue. En la primera versión de este registro escribí que el comportamiento «no estaba documentado»; era inexacto: estaba documentado a medias y de forma engañosa.
- **Riesgo residual:** si el operador acciona el kill switch **porque** el stop está mal (nivel absurdo), ahora el stop sigue ahí. Tiene que usar el cierre de emergencia (lo dice el runbook corregido). Me parece un precio menor que una posición desnuda.

## P02 · Un cierre de emergencia rechazado dejaba una barra sin protección

- **Problema:** `emergency_flatten()` cancela el stop y cierra a mercado. Si el venue rechazaba el cierre, la posición quedaba sin stop hasta el ciclo siguiente: la misma ventana de R18, por otra puerta (no pasaba por `_reprotect`).
- **Evidencia:** `logs/experimentos/exp_flatten_rechazado_antes.json`: la barra 0 se emparejó sin stop.
- **Decisión:** si no queda ningún cierre trabajando, `_reprotect()` en la misma llamada (la regla de R18).
- **Validación:** la prueba correspondiente de `test_emergency_controls_protection.py` falla sin el arreglo y pasa con él.
- **Riesgo residual:** el R17 de siempre: mientras un cierre trabaja, la posición no tiene stop propio (decisión T8).

## P03 · El venue simulado se detenía con la sesión

- **Problema:** el venue de papel empareja solo las barras que el ciclo le pasa (`on_bar`). En `PAUSED` y `SAFE_MODE` el ciclo salía antes de leer velas, así que un stop en reposo nunca se ejecutaba en papel. Contradice el comentario del propio código: «el venue no se pausa» (G7).
- **Evidencia:** con P01 aplicado, el stop conservado no se ejecutaba aunque el precio cruzara el nivel (`logs/experimentos/exp_kill_despues.json`, primera versión).
- **Decisión:** en esos estados, cada barra nueva se empareja contra las órdenes en reposo y nada más: no hay decisión ni orden, y la barra no se cuenta. Un venue real (sin `on_bar`) no se toca.
- **Validación:** dos pruebas (kill switch y pausa), con el stop ejecutándose en la barra que cruza. Fallan sin el arreglo.
- **Riesgo residual (corregido después, P22):** el *watchdog* de datos usaba `_last_bar_wall`, que no se actualizaba en esos estados. Lo había anotado como riesgo «que no cambié»; al revisarlo resultó un defecto real, y P03 lo empeoraba. Ver P22.

## P04 · El arreglo de R19 no tenía efecto en producción

- **Problema:** el libro de escrituras de la sesión (R19) cuenta una escritura como fallida solo si su corrutina **lanza**. La aplicación le pasa `AppState._persist`, que **atrapa toda excepción y retorna normalmente**. En producción, toda escritura rechazada figuraba como confirmada, el *flush* decía «completo» y nunca aparecía el aviso «the record is incomplete».
- **Corrección de una afirmación mía:**
  - En la entrega anterior declaré R19 «CORREGIDO_Y_VERIFICADO».
  - Las pruebas y la simulación E12 usaron dobles de prueba que lanzan, un contrato distinto del de producción. Era una prueba aprobada sin garantía real.
  - **R19 solo queda corregido con este parche.**
- **Evidencia:** `tests/integration/test_session_persistence_contract.py`, corrida en el árbol anterior con el despachador de producción: la sesión **no sabe** que perdió la escritura (`logs/sin_y_con_correccion/A4_SIN_correccion_con_el_despachador_de_produccion.txt`).
- **Alternativas:**
  - (a) que `_persist` lance siempre (rompería a los servicios de *market making*, que lo esperan en línea);
  - (b) un despachador para las sesiones que cuenta igual y vuelve a lanzar (`session_persist`).
- **Decisión: (b).** Lo reciben la sesión viva y el motor de escenarios, que ya estaban escritos para un despachador que lanza. `_persist` sigue absorbiendo para los demás.
- **Validación:**
  - Prueba nueva: falla sin el arreglo y pasa con él.
  - Los dos contadores (el de la aplicación y el de la sesión) coinciden.
- **Riesgo residual:** las fábricas reales de sesiones construyen proveedores de Binance y no se instancian en pruebas. Que pasen `session_persist` está verificado por inspección, no por una prueba.

## P05 · Las alertas dependían de la base de datos

- **Problema:**
  - El webhook se llamaba desde **dentro** de la escritura de la incidencia, después de guardarla. Con la base caída, que es cuando más importa avisar, no salía ninguna alerta.
  - Además no se miraba la respuesta: un 500 contaba como entregado.
- **Decisión:**
  - la alerta se despacha antes de la escritura;
  - una respuesta fuera de 2xx es una falla;
  - nuevo contador `tia_alert_failures_total`.
- **Validación:** `tests/integration/test_alert_delivery.py`, 2 pruebas que fallan sin el arreglo (`logs/sin_y_con_correccion/A6_SIN_correccion.txt`).
- **Riesgo residual:** sigue siendo *fire-and-forget*, sin reintentos. Una alerta que falla se cuenta y se registra, pero no se reenvía (propuesta abierta: una cola con reintento acotado).

## P06 · `/api/metrics` no describía la sesión que tiene las posiciones

- **Problema:** la exposición Prometheus leía solo el motor de escenarios. Con solo la sesión 24/7 corriendo, un *scrape* veía `tia_up 1` y contadores vacíos. Para colmo, la compuerta `OBSERVABILITY` aprueba con solo mirar que las métricas estén habilitadas.
- **Decisión:** series nuevas de la sesión:
  - `tia_live_session` y `tia_live_state{state=…}`;
  - `tia_live_position_open` y `tia_live_position_unprotected`;
  - `tia_live_entry_blocks`;
  - las antigüedades del latido y de los datos;
  - la completitud de la persistencia y todos sus contadores.
- **Validación:** `tests/integration/test_live_metrics.py` falla sin el arreglo (no existe la serie) y pasa con él.
- **Riesgo residual:** no hay reglas de alerta escritas (Alertmanager). Falta definir umbrales; sugerencia mínima: `tia_live_position_unprotected == 1` durante más de 1 min.

## P07 · La compuerta `EDGE_EVIDENCE`

- **Problema:**
  - Leía el estimador del motor de **escenarios**, alimentado por mercados generados.
  - Aprobaba cuando **algún** bucket llegaba a 30 trades, sin mirar la política de admisión del vivo.
  - El valor por defecto (`legacy`, también en `docker-compose.prod.yml`) deja que el motor de EV del vivo aprenda de trades sintéticos.
  - Los otros chequeos de la compuerta ya preferían la sesión paper-live; este no.
- **Decisión:**
  - fallar si `ev_evidence_policy != "real_only"`;
  - leer el estimador de la sesión paper-live en curso;
  - contar solo lo que esa sesión admitió.
  - Es una compuerta **más estricta**: no habilita nada.
- **Validación:** `tests/integration/test_edge_evidence_gate.py`, 3 pruebas que fallan sin el arreglo y pasan con él.
- **Riesgo residual:** la compuerta sigue exigiendo un tamaño de muestra, no una ventaja demostrada. La ventaja la juzga el motor de EV trade por trade (P11), y su demostración estadística no puede venir de la sesión de papel (P17).

## P08 · N3: el motor de escenarios decía «completo» con escrituras fallidas

- **Decisión:** el *flush* da `True` solo si ninguna escritura falló (la regla de R19), y `last_error` distingue «en vuelo» de «fallida».
- **Prueba existente modificada a propósito:** `test_persistence_failures_are_counted_and_never_stop_the_loop` afirmaba «failed writes are finished writes». Es exactamente la semántica que el proyecto rechazó en R19. Se mantienen sus otras aserciones (el bucle sigue, las fallas se cuentan, no hay error de bucle).
- **Validación:** prueba nueva que falla sin el arreglo (`assert True is False`, `logs/sin_y_con_correccion/A5_SIN_correccion.txt`).

## P09 · Huecos de detección: experimento de mutación

- **Diseño** (`herramientas/exp_mutacion.py`, fijado antes de correr):
  - 22 mutantes que representan defectos plausibles de la lógica que protege el capital, algunos idénticos a defectos ya encontrados (R25, R18, R19, N1);
  - cada mutante reemplaza **una** cadena que aparece exactamente una vez; se corre con `-x` y el archivo se restaura verificando su sha256.
  - Lista de pruebas: T15, los 36 archivos que tocan el vivo, el adaptador y la compuerta; T21, esos 36 más los 8 archivos nuevos de este ciclo (44).
- **Resultado** (generado por `herramientas/tabla_mutacion.py` desde `exp_mutacion_T15.json` y `exp_mutacion_T21_consolidado.json`):

| Id | Defecto simulado | T15 (36 archivos) | T21 (44 archivos) | Prueba que lo detecta en T21 |
|---|---|---|---|---|
| M01 | dos stops si la cancelación no se confirma | MUERTO | MUERTO | `test_partial_fills_and_fees_rebuild_identically_however_often` |
| M02 | segundo stop cuando el venue no sabe del primero | MUERTO | MUERTO | `test_a_venue_that_cannot_be_read_keeps_the_stop_tracked_and_places_not` |
| M03 | no esperar al stop de respuesta perdida | MUERTO | MUERTO | `test_no_second_stop_while_the_venue_cannot_say_whether_the_first_arriv` |
| M04 | ignorar el cambio de cantidad (stop más chico que la posición) | VIVO | MUERTO | `test_a_stop_is_resized_when_the_position_it_covers_changes_size[0.5]` |
| M05 | rechazo del stop en silencio (R25 original) | MUERTO | MUERTO | `test_a_venue_that_refuses_every_stop_blocks_entries_halts_and_keeps_as` |
| M06 | stop rechazado tomado como protección | MUERTO | MUERTO | `test_a_stop_rejected_as_an_order_is_handled_like_a_refused_one` |
| M07 | stop protector sin reduce_only | MUERTO | MUERTO | `test_a_venue_flat_behind_a_tracked_round_trip_blocks_entries_and_score` |
| M08 | stop del lado equivocado | MUERTO | MUERTO | `test_an_open_position_is_restored_protected_scorable_and_closable_afte` |
| M09 | redondeo del nivel hacia el lado que agranda la pérdida | VIVO | MUERTO | `test_the_stop_level_is_rounded_toward_the_position_on_the_venue_grid[T` |
| M10 | re-protección sin mirar si el estado admite órdenes reductoras | VIVO | MUERTO | `test_a_session_that_may_not_send_orders_does_not_reprotect_but_says_so` |
| M11 | sin re-protección tras un cierre que no trabaja (R18) | MUERTO | MUERTO | `test_every_bar_boundary_finds_the_position_protected_while_closes_are_` |
| M12 | sin re-protección tras un cierre no enviado (R18) | VIVO | MUERTO | `test_a_close_that_is_not_sent_puts_the_stop_back_in_the_same_call` |
| M13 | sin re-protección de la posición restaurada al arrancar (N5) | MUERTO | MUERTO | `test_a_position_restored_after_a_restart_is_protected_before_its_first` |
| M14 | más de un stop en reposo al reiniciar sin bloquear | VIVO | MUERTO | `test_two_stops_resting_against_a_restored_position_halt_the_session` |
| M15 | flush «completo» con escrituras fallidas (R19) | MUERTO | MUERTO | `test_a_lost_journal_write_makes_the_rebuild_incomplete_and_the_next_se` |
| M16 | cierre de emergencia a mercado encima de un stop que puede seguir en reposo | MUERTO | MUERTO | `test_a_flatten_whose_cancels_fail_keeps_the_stop_tracked_and_sends_no_` |
| M17 | cancelar todo olvida órdenes cuya cancelación no se confirmó | MUERTO | MUERTO | `test_a_flatten_whose_cancels_fail_keeps_the_stop_tracked_and_sends_no_` |
| M18 | estado desconocido sin detener las entradas | VIVO | MUERTO | `test_an_entry_the_venue_cannot_resolve_halts_entries_and_none_follows` |
| M19 | error de transporte después de enviar tomado como no enviado (N1) | MUERTO | MUERTO | `test_an_order_that_may_have_reached_the_venue_is_unknown_not_unsent[Re` |
| M20 | timeInForce enviado con STOP_LOSS | MUERTO | MUERTO | `test_a_stop_is_sent_as_stop_loss_with_a_stop_price_and_nothing_else` |
| M21 | la compuerta no exige el stop aceptado en testnet (R25) | MUERTO | MUERTO | `test_live_activation_needs_a_venue_that_accepted_the_protective_stop` |
| M22 | posición desprotegida sin detener órdenes nuevas | MUERTO | MUERTO | `test_a_venue_that_refuses_every_stop_blocks_entries_halts_and_keeps_as` |

**Muertos:** T15 16 de 22 · T21 22 de 22.

- **Los 6 sobrevivientes de T15 y su prueba nueva** (cada una verificada contra su mutante: falla con él y pasa con el código real, `logs/sin_y_con_correccion/M*_mutante_con_prueba_nueva.*`):
  - **M04**, el stop no se redimensiona cuando cambia la posición. Mi primera versión de la prueba falló también con el código real, porque pedía una cantidad fuera de la grilla de lotes; no era un defecto del código.
  - **M09**, el redondeo del nivel hacia el lado de la pérdida. Ninguna prueba cargaba un `tick_size`, y mi primera prueba, con `pytest.approx` relativo, no discriminaba (de ahí P13).
  - **M10**, re-proteger desde un estado que no admite órdenes.
  - **M12**, ninguna re-protección cuando el cierre ni siquiera se envía.
  - **M14**, dos stops en reposo contra una posición restaurada: se adoptaba uno en lugar de detener la sesión.
  - **M18**, una entrada de estado desconocido que el venue no puede resolver no detenía las entradas. **Con el mutante, la sesión mandó 6 entradas más encima de una que podía estar ejecutada** (`M18_consecuencia_del_mutante.txt`). Las pruebas existentes manejaban `_cycle_once` directamente y aceptaban `RUNNING` como resultado; la nueva pasa por el bucle real.
- **Advertencias sobre la medición «después»:**
  - **No es independiente:** las pruebas nuevas se escribieron conociendo los mutantes. 22 de 22 muestra que los huecos se cerraron, no que la suite sea buena en general. Para eso está el lote 2 (P24).
  - **Dos errores míos en la corrida de T21, corregidos y documentados en el JSON consolidado:**
    1. la lista omitía `test_unknown_entry_halts_entries.py`, escrita después de armarla, así que M18 salió vivo; se repitió con la lista de 44;
    2. M07, M09, M10 y M11 corrieron dentro de la ventana horaria de P25, y los «mató» una prueba de *funding* que falla sin mutante; se repitieron fuera de la ventana. Ahora cada uno muere por la prueba que corresponde.

## P10 · Hipótesis descartada: la regla de EV aprueba ruido por comparaciones múltiples

- **Hipótesis inicial (mía):** con unos 10 buckets de 30 muestras y un encogimiento de solo 1 EE, algún bucket sin ventaja sería aprobado a menudo.
- **Experimento** (`herramientas/exp_ev_falsos_positivos.py`):
  - clases reales del repositorio, retornos sintéticos declarados (normales y t3);
  - 5.000 réplicas por celda y 1.000 historias secuenciales.
- **Resultado:**
  - Con costos realistas (c = 20 bps), P(aprobado | sin ventaja) ≤ 0,3 % para σ = 100 y 2,9 % para σ = 200.
  - En la simulación secuencial (σ = 100, c = 20), el 0,5 % de las historias llega a operar, con una pérdida media de −0,76 bps.
  - Solo con costos bajos y volatilidad alta (c = 10, σ = 200) sube al 7 % por bucket (52 % de que al menos 1 de 10 sea aprobado).
- **Decisión:** **descartar** agregar una corrección por comparaciones múltiples (Bonferroni): en el experimento redujo la potencia ante una ventaja real de 18 % a 1 % sin un beneficio relevante.
- **Riesgo residual:** con entradas *maker* (costos bajos) y alta volatilidad, el riesgo existe (7 % por bucket); revisarlo si se cambia a entradas límite.

## P11 · La razón de costos limita la potencia

- **Experimento** (`herramientas/exp_ev_razon_costos.py`): con σ = 100 y c = 20, la potencia ante una ventaja neta de +15 bps es:

  | n | Razón 0,6 (actual) | Razón 1,0 |
  |---|---|---|
  | 30 | 19 % | 31 % |
  | 120 | **20 %** | **54 %** |

  Falsos positivos: 0,4 % → 0,9 % con n = 30, y 0 % → 0 % con n = 120.
- **Lectura:** con la regla actual, la potencia **no crece con más evidencia**. La regla exige una estimación ajustada ≥ c/0,6, que para esa ventaja requiere miles de muestras.
- **Recomendación: no cambiarla todavía.** Existe para no depender de un modelo de costos que hoy no está verificado (la comisión es configurada; `FEES_VERIFIED_AT_SOURCE` falla). Revisarla cuando haya costos medidos con fills reales, y entonces con un experimento sobre esos costos.

## P12 · Contaminación del estimador de EV con trades sintéticos

- **Hipótesis:** la deriva de los escenarios (por ejemplo, `trend_up`: deriva/volatilidad ≈ 0,25 por barra) haría «operable» un bucket.
- **Experimento** (`herramientas/exp_contaminacion_sintetica.py`): 12 corridas completas del motor de escenarios.
- **Resultado:**
  - Solo 26 trades.
  - `trending_up/long` dio una media bruta de −0,99 bps.
  - Ningún bucket llega a 30; ninguno es operable bajo `legacy` ni bajo `real_only`.
  - **La hipótesis no se confirma en lo medido.**
- **Lo que sí queda:** mezclar poblaciones de mercados reales y generados en un mismo estimador es metodológicamente inválido. P07 cierra la puerta en la compuerta.
- **Recomendación (C, toca producción):** cambiar a `real_only` en `docker-compose.prod.yml`. Con `real_only` y sin exploración, una sesión nueva no opera (no tiene evidencia real). Es el comportamiento honesto, pero conviene decidirlo junto con el presupuesto de exploración.

## P13 · `pytest.approx` sin tolerancia absoluta en precios

- **Evidencia:**
  - 49 comparaciones de valores tipo precio usan `pytest.approx(x)` sin `abs=`.
  - A ~50.000, la tolerancia relativa por defecto (1e-6) es 0,05: deja pasar hasta cinco ticks de 0,01.
  - M09 sobrevivió por esto en mi propia prueba.
- **Propuesta:** un ayudante `approx_price(x, tick)` con `abs = tick/2`, y migrar esas 49 comparaciones.
  - Costo: bajo.
  - Riesgo: algunas pruebas pueden fallar si dependen de una aritmética flotante que hoy queda tapada; eso también es información.
  - **No lo hice en este ciclo** porque toca 49 aserciones de pruebas ajenas y merece revisión.

## P14 · Dos motores de sesión duplicados

- **Hechos:**
  - `runtime/engine.py` (1.824 líneas) y `runtime/live.py` (4.988) implementan por separado:
    - el ciclo de órdenes;
    - el stop protector (con ids distintos: N4);
    - la persistencia (con semánticas opuestas del *flush* hasta P08).
  - Los defectos N3 y N4 existen porque los arreglos de uno no llegaron al otro.
- **Alternativas:**
  - (a) unificar en una sesión con proveedores intercambiables (*big bang*, riesgo alto);
  - (b) extraer piezas compartidas pequeñas: el libro de escrituras, la regla del stop protector;
  - (c) declarar el motor de escenarios **solo demo**, sin camino de evidencia hacia el vivo.
- **Recomendación:** (c) ya, que con P07 y P12 es casi gratis. Después (b), empezando por el libro de escrituras. **No** (a) sin antes subir la detección de las pruebas (P09, P13): un refactor grande sobre pruebas que no detectan M04 o M09 es una apuesta.

## P15 · `runtime/live.py` de 5.000 líneas

- **Propuesta:** dividir por responsabilidad (protección, persistencia, reconciliación, salidas), pero **después** de P09 y P13.
- **Validación:** la tasa de mutantes muertos no puede bajar.
- **No hacerlo ahora:** el beneficio no está demostrado, y el riesgo de regresión con la detección actual sí.

## P16 · Hipótesis: comisión en el activo base y cantidad del stop (Binance)

- **Mecanismo plausible:** en spot, Binance cobra la comisión de una compra en el activo comprado, salvo que se pague con BNB. El saldo libre queda por debajo de la cantidad del fill. Un `STOP_LOSS` por la cantidad del fill podría:
  - ser rechazado (saldo insuficiente o grilla de lotes);
  - o fallar al dispararse.
- **Evidencia:** solo de mecanismo, por inspección. El adaptador y el vivo usan la cantidad de la posición (de los fills); el papel cobra la comisión en la moneda de cotización. **No verificado.**
- **Validación:** en testnet, comprar a mercado y pedir el stop por la cantidad del fill.
- **Estado:** pendiente de autorización (C), junto con R25.

## P17 · La sesión de papel no puede demostrar ventaja

- **Hechos:**
  - La compuerta pide 30 trades en 7 días (`min_paper_trades`, `min_paper_days`).
  - Con la regla de EV actual, una ventaja real de +15 bps netos se aprueba en el 18–20 % de las evaluaciones (P11).
  - Un error estándar razonable con 30 trades (σ = 100 bps) es de 18 bps: del orden de la ventaja buscada.
- **Lectura:**
  - El historial de papel prueba **la plomería** (reconexiones, persistencia, reconciliación). Eso vale, pero no es evidencia de ventaja.
  - La evidencia de ventaja tiene que venir de pruebas prerregistradas sobre datos auténticos, con potencia calculada antes (como hizo la hoja de ruta del 2026-10-21).
- **Recomendación:** que la documentación de la compuerta lo diga explícitamente, y que nadie lea un historial de papel aprobado como ventaja.

## P18 · Prioridad cuantitativa: información antes que infraestructura

- **Hechos del propio proyecto** (hoja de ruta 2026-10-21):
  - 0 hipótesis respaldadas de 18 con resultado;
  - con un IR neto plausible de 0,3–0,5, la potencia de una confirmación prospectiva es del 9–20 %;
  - la única prueba pendiente con valor informativo es **E3-H1** (momentum transversal), con su protocolo congelado y bloqueada por un dato (la lista de exclusiones de pares).
- **Mi posición:** el cuello de botella es la información por unidad de tiempo, no la ejecución. Este ciclo y el anterior endurecieron mucho la ejecución en vivo, y eso tiene un valor decreciente mientras no haya una sola hipótesis respaldada.
- **Recomendación:**
  - integrar las correcciones de seguridad (son baratas y valen también para papel);
  - **no** seguir ampliando la infraestructura del vivo;
  - destrabar E3-H1, que es decisión tuya (dato y reapertura acotada), y que yo no puedo tocar según las restricciones vigentes.

## P19 · Hipótesis nueva H-XS-REV-1: reversión transversal de corto plazo

Propuesta, **no ejecutada**. No debe correrse antes de que E3-H1 consuma su prueba única, porque usaría el mismo universo y contaminaría su fuera de muestra.

| Aspecto | Especificación |
|---|---|
| **Fundamento económico** | Provisión de liquidez: la presión de órdenes no informadas aleja los precios en el corto plazo y quien provee liquidez cobra la reversión. Documentado en acciones (Lehmann 1990; Jegadeesh 1990; Nagel 2012). En cripto la evidencia a horizonte diario es mixta y el signo no está establecido: por eso es una pregunta, no una apuesta |
| **Hipótesis falsable** | En el universo líquido USDT (top N por volumen, **sin sesgo de supervivencia**), una cartera neutral, larga en el quintil de peores retornos del día anterior y corta en el de mejores, rebalanceada a diario a una hora UTC fija con una barra de retraso, tiene un retorno diario medio **neto de costos** > 0. H0: ≤ 0 |
| **Datos** | OHLCV diario u horario del universo **con los pares excluidos** (el mismo bloqueo que E3-H1), tasas de funding si las ventas usan perpetuos, y spreads o profundidad para los costos |
| **Qué la invalida** | Media neta ≤ 0; bruta positiva pero comida por los costos; efecto concentrado en nombres ilíquidos (capacidad menor que la necesaria); resultado explicado por pocos días extremos |
| **Contra el sobreajuste** | Una sola especificación fijada antes (retrospectiva 1 día, quintiles, pesos iguales, rebalanceo diario). Sin búsqueda de parámetros. Las variantes de robustez se declaran antes y no sirven para elegir |
| **Separación** | Cronológica: desarrollo, validación y prueba con *embargo*. Ventanas sin superposición con las reservadas de E3-H1, o ejecución recién después de E3-H1. Prueba mirada **una sola vez** |
| **Costos a modelar** | Comisión taker por lado (7,5 bps spot por defecto, verificar en la cuenta), medio spread medido, deslizamiento por participación, funding de las ventas en perpetuos y latencia de una barra. La rotación diaria alta hace que los costos sean el obstáculo principal |
| **Métrica principal** | Retorno diario neto medio de la cartera larga-corta, con estadístico t robusto (Newey-West) |
| **Descarte rápido (antes de validar)** | En desarrollo, estimar el diferencial **bruto** medio. Si es menor que 2× los costos de ida y vuelta estimados, **descartar sin pasar a validación** |
| **Continuar si** | Neto medio > 0 con t > 2 en desarrollo **y** razón bruto/costo > 1,5; después, validación con el umbral prerregistrado |
| **Descartar si** | Cualquiera de las anteriores falla. Sin reformulaciones dentro del mismo período |
| **Potencia esperable** | Con observaciones diarias, t ≈ IR anual × √años: dos años de desarrollo necesitan un IR neto ≥ 1,4 para t ≥ 2. Es exigente, y lo honesto es esperar un descarte |

## P20 · Mutación dirigida como chequeo periódico

- **Propuesta:** convertir `exp_mutacion.py` y `exp_mutacion_lote2.py` en un *workflow* manual o nocturno. No en cada push: en esta máquina, con carga compartida, el lote 1 tardó 35–43 min y el lote 2, 38 min (suma de `segundos` en los JSON).
- **Criterio:** la tasa de mutantes muertos sobre las listas fijadas no puede bajar. Línea base: lote 1 22/22 en T21, lote 2 11/11 aplicables.
- **Control obligatorio (lección de P25):** correr el código sin mutar al principio y al final, fuera de las ventanas horarias conocidas, y repetir toda «muerte» cuya prueba falle también sin mutante.
- **Requiere:** autorización para tocar la CI (C).

## P21 · N4: ids del stop por barra en el motor de escenarios

- **Hecho:** `protective:{symbol}:{bars}`, el análogo de N2 que se arregló en el vivo.
- **No reproducido;** baja severidad (solo demo). Si se aplica P14 (c), pierde relevancia.

## P22 · Al reanudar tras una pausa larga, el *watchdog* detenía la sesión con velas llegando

- **Problema:** el *watchdog* de datos mide el tiempo de pared desde la última vela nueva que vio la sesión, y solo el ciclo en `RUNNING` miraba velas. Una sesión pausada más que el TTL (300 s) volvía a `RUNNING` y en el ciclo siguiente pasaba a `HALT_NEW_ORDERS` por «market data stale», con incidencia y alerta, aunque el feed nunca se hubiera cortado.
- **Agravante que introduje yo (P03):** el emparejador en pausa marca la vela como ya emparejada, para no emparejarla dos veces. Por eso, al reanudar, la vela no es «nueva» y la autocuración del *watchdog* esperaba a la vela siguiente (hasta un *timeframe* entero con entradas detenidas). En T15 la detención era espuria pero se curaba en el mismo ciclo.
- **Evidencia (hecho):**
  - `tests/integration/test_watchdog_after_standing.py`, primera prueba: falla en **T15** y en **T20** con `market data stale: no new bar for 660s (TTL 300s)` (`logs/sin_y_con_correccion/A7_SIN_correccion_T15.txt`, `A7_SIN_correccion_T20.txt`).
- **Alternativas:**
  - (a) reiniciar el reloj del *watchdog* al reanudar: descartada; haría mentir a la métrica `tia_live_market_data_age_seconds` y demoraría un TTL la detección de un feed que sí se cortó durante la pausa;
  - (b) que el emparejador en pausa, que ya lee cada vela nueva, registre su hora para el *watchdog*: es un hecho verdadero (el feed produjo esa vela).
- **Decisión: (b)**, una línea en `_match_simulated_venue_while_standing`.
- **Validación:**
  - la prueba 1 pasa con el arreglo;
  - la prueba 2 (un feed que **sí** se cortó durante la pausa se detecta en el primer ciclo después de reanudar) pasa con y sin el arreglo, y **falla con el arreglo demasiado amplio (a)** (`logs/sin_y_con_correccion/A7_mutante_reinicio_en_resume.txt`): protege contra la corrección equivocada.
- **Riesgo residual:** con un venue real (sin `on_bar`) el ciclo en pausa no lee velas. Al reanudar tras una pausa larga sigue habiendo una detención espuria, con incidencia y alerta, que se cura en el mismo ciclo (comportamiento de T15, no empeorado). Corregirlo exige leer el feed durante la pausa también con venue real (una llamada por ciclo); lo dejo como propuesta porque cambia el uso de la API del exchange.

## P23 · La simulación y los *fixtures* dependen del reloj de pared

- **Hecho:** `tests/integration/test_account_restore.py::build()` ancla la serie de velas a `datetime.now(UTC)`. La simulación integral usa ese `build()`.
- **Evidencia:** el **mismo** árbol (T15) con el **mismo** script dio en E12 2.534 escrituras programadas a las 20:04 UTC y 73 a las 21:35 UTC (`logs/K_sim_T15/sim_cand_7.json` de la entrega de integración controlada, idéntico al de este entorno, contra `logs/simulacion/K_sim_T15_recorrida/sim_T15_7.json` de este paquete). Los veredictos no cambiaron (15/15 CUMPLE en las dos), pero los conteos observados no son comparables entre corridas.
- **Cómo lo encontré:** al comparar T15 contra T21, E12 difería (2.534 contra 41). Antes de atribuirlo a mis parches, una sonda mostró el mismo comportamiento en los dos árboles (13 barras hasta abrir posición), y la re-corrida de T15 confirmó que la variación es por la hora.
- **Propuesta:** que la simulación pase un `start` fijo a `build()` (el parámetro ya existe), y que las pruebas que comparan conteos lo hagan también. La dependencia horaria de la suite ya se había medido en la Fase J del ciclo anterior; esto la extiende a la simulación.
- **Por qué no lo cambié:** la simulación es una herramienta de la entrega anterior, que no se modifica; y en el repositorio el cambio toca decenas de pruebas. Es barato, pero merece su propio parche revisado.

## P24 · Lote 2 de mutación: medida no contaminada

- **Por qué:** después de escribir pruebas para los sobrevivientes del lote 1, ese lote dejó de medir la suite (P09). El lote 2 son 11 mutantes **fijados antes de correr** (sha256 en `herramientas/listas/exp_mutacion_lote2_fijado.sha256`), sobre lógica que protege el capital y que este ciclo no tocó ni miró al escribir pruebas: frenos de riesgo, reglas de salida, regla de EV y permisos de estado. Corren contra la **suite completa**.
- **Resultado** (`exp_mutacion_lote2_T21_consolidado.json`):

| Id | Defecto simulado (lote 2, suite completa) | T21 | Primera prueba que falla | Segundos |
|---|---|---|---|---|
| M23 | el freno de drawdown nunca salta | MUERTO | `test_a_drawdown_past_the_breaker_survives_a_restart` | 39.7 |
| M24 | el freno de drawdown rechaza la señal pero no pone el sistema en modo seguro | MUERTO | `test_drawdown_breach_halts_the_system_not_just_the_signal` | 409.7 |
| M25 | el límite de pérdida diaria nunca bloquea | MUERTO | `test_a_day_that_hit_the_loss_limit_still_refuses_entries_after_a_resta` | 32.4 |
| M26 | la regla de salida puede aflojar el stop (falta «solo más ajustado») | MUERTO | `test_rejects_and_partials_over_hundreds_of_bars_keep_the_invariants_an` | 54.6 |
| M27 | el stop puede quedar del otro lado del último cierre | MUERTO | `test_a_stop_stays_a_stop_never_through_the_last_close` | 376.8 |
| M28 | se elige el candidato más flojo en vez del más ajustado | MUERTO | `test_the_tightest_candidate_wins - Assertion...` | 387.8 |
| M29 | sin encogimiento por error estándar | MUERTO | `test_exploration_buys_lessons_in_unproven_buckets_but_never_in_disprov` | 205.6 |
| M30 | un costo desconocido no impide operar | MUERTO | `test_an_incomplete_estimate_never_makes_a_trade_tradeable` | 413.8 |
| M31 | se ignora el techo de la razón de costos | MUERTO | `test_the_cost_ratio_ceiling_refuses_a_trade_that_depends_on_the_cost_m` | 397.9 |
| M32 | HALT_NEW_ORDERS no admite órdenes que reducen (no se puede cerrar ni proteger) | NO_APLICA (aparece 2 veces) | `` | — |
| M32b | HALT_NEW_ORDERS no admite órdenes que reducen (corregido: cadena única) | MUERTO | `test_deadline_and_time_stop_in_the_same_cycle_send_one_exit_and_the_bo` | 111.2 |
| M33 | muestra mínima de 3 en vez de 30 | MUERTO | `test_an_unfilled_limit_entry_expires_and_frees_the_session` | 203.8 |

**Lote 2:** 11 muertos de 12.

- **Lectura:**
  - **11 de 11 aplicables detectados.** En este instrumento, los huecos estaban en los caminos de integración del vivo (stop protector y re-protección: 6 de 22 sobrevivían en T15), no en las reglas unitarias de riesgo, salidas y EV (0 de 11).
  - Es una muestra chica: no es una estimación de cobertura ni garantiza la ausencia de otros huecos.
- **Correcciones de procedimiento, declaradas:**
  - M32 no se aplicó, porque su cadena aparece dos veces en `states.py`. M32b es la misma hipótesis con contexto único, agregada **después** de la primera corrida (`exp_mutacion_lote2_b.py`).
  - M24 corrió dentro de la ventana de P25 y se repitió fuera de ella; ahora lo detecta `test_risk_engine.py::test_drawdown_breach_halts_the_system_not_just_the_signal`.
- **Limitación:** en el lote 2 «muerto» significa que alguna prueba falló. Para 7 de 11 la prueba que falla nombra la propiedad mutada; para M26, M29, M32b y M33 la detecta una prueba más amplia. No verifiqué que cada falla sea «por la razón correcta», como sí hice en el lote 1.
- **Recomendación:** P20 (mutación periódica) con los **dos** lotes, más un control obligatorio: correr el código sin mutar al principio y al final, y repetir toda «muerte» cuya prueba falle también sin mutante (P25).

## P25 · Dos pruebas de *funding* fallan siempre en una ventana horaria (cada 8 h)

- **Cómo apareció:** en la corrida de mutación sobre T21, M07, M09, M10 y M11 (y M24 del lote 2) quedaron «muertos» por dos pruebas de *funding*, que con esos mismos mutantes pasaban en T15. Repetidos solo contra los archivos de *funding*, **ninguno de los cuatro murió** (dos corridas, `logs/experimentos/ventana_horaria/sonda_funding_M09_M10_*.json`).
- **Hechos** (`logs/experimentos/ventana_horaria/funding_ventana_horaria.txt`, reloj de pared desplazado con `time-machine`, la herramienta de la Fase J):
  - `test_funding_restore.py::test_a_restart_inside_the_period_already_paid_charges_nothing_again` falla a las 13:38, 21:38, 21:40 y 05:38 UTC;
  - `test_funding_settlement.py::test_a_missing_mark_at_the_settlement_leaves_the_period_unreconciled` falla a las 13:42, 21:42 y 05:42;
  - las dos pasan a las 21:30, 21:34, 21:36, 21:44, 21:46, 22:00, 17:40 y 01:40.
  - La ventana mide unos 6 minutos y **se repite cada 8 horas**, el período del *funding*.
  - **Preexistente:** falla igual en la base `72ffae5` y en T15.
- **Mecanismo:** las dos usan *builders* anclados a `datetime.now()` (`build()` y `build_runtime_paper_with()`). `_settle_once` fuerza «un límite cruzado», y la prueba supone que las barras siguientes no cruzan **otro** límite real (00/08/16 UTC). En esa ventana, la serie simulada sí lo cruza.
- **Impacto:**
  - una CI que corra la suite en esa ventana (≈18 min por día) falla sin que haya ningún defecto;
  - en mi experimento, la falla se contó como «muerte» de los mutantes que corrían en ese momento.
- **Lo que hice con mis mediciones:** repetí fuera de la ventana los 5 mutantes afectados y la tabla de P09/P24 usa esas repeticiones (`exp_mutacion_T21_repeticion_fuera_de_ventana.json`, `exp_mutacion_lote2_T21_repeticion.json`). **Lección para el instrumento:** una muerte cuenta solo si la prueba que mata no falla sin el mutante. El experimento debe correr además el código sin mutar como control, al principio y al final.
- **Alternativas de corrección:**
  - (a) anclar los *builders* compartidos a un punto fijo **dentro** del período de *funding* en curso (`floor_8h(now) − desplazamiento`): la línea de tiempo simulada relativa a los cortes queda idéntica a cualquier hora, por construcción;
  - (b) un `start` fijo solo en estas dos pruebas;
  - (c) marcarlas como dependientes de la hora y saltearlas en la ventana (esconde el problema).
- **Recomendación:** (a), en un parche propio, verificado con la suite completa a varias horas desplazadas, entre ellas las tres ventanas.
- **Por qué no lo implementé:** los dos *builders* los usan cientos de pruebas, algunas comparan contra el reloj real (`feed_at_end`, `rebuild(now=datetime.now)`), y un cambio de ancla puede mover el problema en lugar de resolverlo. Tiene una verificación clara, pero cuesta más de lo que quedaba en el ciclo. La Fase J del ciclo anterior no lo vio porque no muestreó esas horas: su conclusión sigue en pie para las horas que midió, pero no cubre toda la suite.
