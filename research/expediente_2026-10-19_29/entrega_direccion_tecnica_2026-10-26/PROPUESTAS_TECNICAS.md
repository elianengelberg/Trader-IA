# Registro de iniciativa técnica (ciclo 2, 2026-10-26: misión de dirección técnica y cuantitativa)

> Versión nueva. La del ciclo 1 (`entrega_iniciativa_tecnica_2026-10-25/PROPUESTAS_TECNICAS.md`) se conserva sin cambios. Esta versión agrega P26–P35, cambia el estado de P16, P18, P19 y P25 (marcado «ciclo 2») y no borra nada.

**Base:** candidato de la integración controlada, árbol `17332e1c…` (parches 01–15).
**Resultado del ciclo 1:** parches 16–22, árbol `T22` = `87af7a45…`. T21 = `bcfa4008…` es el último árbol con cambios de código; el 22 solo corrige documentación.
**Resultado del ciclo 2:** parches 23–25 sobre T22, árbol `T25` = `11f9ccca…` (ver `parches/CADENA_DT.txt`). Además, el expediente E3R (desbloqueo de E3-H1, preparado y **no ejecutado**).
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
| P16 | Hipótesis: Binance cobra la comisión de compra en el activo base y el stop pide más de lo que hay | C (testnet) | Alta si se confirma | **ciclo 2: refutada en su forma original; el mecanismo real es otro (P28, P29)** |
| P17 | La sesión de papel no puede demostrar ventaja | B | Estratégico | validada (cálculo y experimento) |
| P18 | Prioridad cuantitativa: información antes que infraestructura | B / C | Estratégico | recomendación; **ciclo 2: sostenida y aplicada (P31)** |
| P19 | Hipótesis nueva H-XS-REV-1 (reversión transversal de corto plazo), con especificación completa | B | — | propuesta; **no ejecutar antes de E3-H1**; ciclo 2: errata del bloqueo (ver P31) |
| P20 | Mutación dirigida como chequeo periódico (no en cada push) | B | Media | propuesta |
| P21 | N4: ids del stop por barra en el motor de escenarios | A | Baja | pendiente (no reproducido) |
| P22 | Al reanudar tras una pausa larga, el *watchdog* detenía la sesión por «datos viejos» con velas llegando | A | Media (alerta falsa; con P03, entradas detenidas una vela) | **implementada** (21) para papel; venue real: riesgo residual |
| P23 | La simulación y los *fixtures* dependen del reloj de pared | B | Media (resultados no comparables entre corridas) | **validada como hallazgo**; propuesta |
| P24 | Lote 2 de mutación: medida no contaminada de la suite | B | Media | **validada** (ver §P24) |
| P25 | Dos pruebas de *funding* fallan siempre en una ventana de ~6 min cada 8 h (05:40, 13:40 y 21:40 UTC) | B | Media (CI roja sin defecto; contaminó mi instrumento) | **validada** (reproducción determinista); corrección propuesta; **ciclo 2: diferida a propósito** (ver P34) |
| P26 | Dos procesos podían armar dos sesiones **vivas** sobre la misma cuenta, y una base ilegible se tomaba como «no hay otro» | A | **Alta** (órdenes y stops duplicados en una cuenta real) | **implementada** (23) |
| P27 | Un resto menor que un lote (polvo) se trataba como posición: bloqueaba entradas, frenaba la sesión y el plazo nunca la encontraba plana | A | Media-alta (sesión inutilizada tras un cierre normal) | **implementada** (24) |
| P28 | El stop protector no se redondeaba al lote: con la comisión en el activo base el exchange lo rechaza y la posición queda **sin stop** tras cada entrada | A | **Alta** (posición sin protección en el vivo real) | **implementada** (25) |
| P29 | El vivo direccional supone la comisión en la moneda de cotización; con comisión en el activo base se frena tras cada compra, no cierra viajes y registra mal las comisiones | B (+C para validar) | **Alta para el vivo** (inoperable; falla cerrado) | **validada** por prueba; corrección propuesta; **bloquea el vivo** |
| P30 | Carrera residual entre la verificación del *lease* vivo y su registro (dos arranques en el mismo instante) | B (+C: migración) | Media (ventana de milisegundos; requiere dos operadores) | propuesta |
| P31 | E3R: desbloquear E3-H1 con evidencia interna del venue (Adenda R, R1′, R2) y orquestador congelado | B | Estratégico (la única prueba que cambia decisiones) | **preparada; ejecución pendiente de tu autorización** |
| P32 | Clasificación de las 18 hipótesis con resultado | B | Estratégico | **hecha** |
| P33 | Requisitos mínimos antes de cualquier dinero real o Testnet | B / C | Alta | propuesta (lista cerrada) |
| P34 | Lo que **no** conviene hacer ahora (y por qué) | B | — | decisión |
| P35 | Ejecutor en papel para la cartera transversal, **solo si** E3R da RESPALDADA | B | Condicional | propuesta condicionada |

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

---

# Ciclo 2 (2026-10-26)

## Cambios de estado de entradas del ciclo 1

### P16 · refutada en su forma original; el mecanismo real es otro
- **Lo que decía P16:** el stop se pedía por la cantidad del fill, y con la comisión cobrada en el activo base esa cantidad supera lo que hay.
- **Lo que muestra el código** (`runtime/live.py`, `data/providers/binance_live.py`):
  - el stop **no** se pide por la cantidad del fill;
  - `_sync_protective_stop` recibe la posición de `get_portfolio()`, y el adaptador de Binance arma esa posición con el saldo (`free + locked`), que ya viene **neto** de la comisión.
  - La forma original de P16 no ocurre.
- **El defecto real es otro:** ese saldo neto queda **fuera de la grilla de lotes** (0,999 del fill con una comisión de 0,1 %). El stop se enviaba sin redondear, y el exchange lo rechaza por `LOT_SIZE`.
  - Corregido en P28.
  - Lo que sigue roto con la comisión en el activo base está en P29.
- **Lección:** una hipótesis de mecanismo plausible puede apuntar a la pieza equivocada. Esta vez la lectura del código la corrigió **antes** de gastar una prueba en Testnet en la pregunta equivocada.

### P18 · sostenida y aplicada
- El diagnóstico del ciclo 2 coincide: el cuello de botella es la información, no la infraestructura.
- Este ciclo sí destrabó E3-H1 (P31), con la ejecución pendiente de tu autorización.
- En seguridad solo hice tres correcciones acotadas (P26–P28). Son baratas, valen para papel y para vivo, y una de ellas (P28) era una posición sin stop.

### P19 · errata del bloqueo
- P18 y P19 decían que E3-H1 estaba bloqueada por «un dato (la lista de exclusiones de pares)». **No es exacto.**
- El bloqueo era la regla de inicio de H de la v3, §4.11 (iv): exige que en todos los años las salidas sin anuncio sean ≤ 10 % de las observadas. El archivo web (Common Crawl) no alcanzaba para cumplirla.
- P31 lo resuelve con evidencia **interna** del venue, sin el archivo.
- La advertencia de P19 sigue en pie: H-XS-REV-1 usa el mismo universo, así que **no** se corre antes de que E3-H1 consuma su prueba única.

### P25 · diferida a propósito
- La corrección buena, la (a), toca *builders* compartidos: `test_account_restore.build`, `test_session_deadline.build`, `build_runtime_paper_with` y otros.
- Su efecto es una CI roja sin defecto durante ~18 min por día. No hay riesgo de seguridad.
- **Mitigación operativa, sin código:** no correr la suite entre hh:36 y hh:46 de las 05, 13 y 21 UTC, o repetir una falla de esas dos pruebas fuera de la ventana.
- Queda como propuesta. Conviene hacerla cuando se toquen esos *builders* por otro motivo (P14 b).

## P26 · Una sola sesión **viva** por cuenta entre procesos (parche 23)

- **Hechos** (prueba `tests/integration/test_live_session_lease.py`; registros `evidencia/B1_SIN_correccion_lease_vivo.txt` y `B1_CON_correccion.txt`):
  - la verificación de que ningún otro proceso latía una sesión sobre la misma base existía para papel (G9), pero `_arm_live_locked` **no** la hacía;
  - un segundo contenedor sobre la misma base y la misma cuenta podía armar una segunda sesión viva: entradas y stops por duplicado en una cuenta real;
  - además, `_foreign_session_lease` devolvía «nadie» si la base no se podía leer (falla **abierta**).
- **Corrección:**
  - armar una sesión viva consulta el *lease* (latido de menos de 120 s) y se niega con 409 si otro proceso lo tiene;
  - una base ilegible **niega** el arranque: «no hay otro proceso» no se puede deducir del silencio. Vale también para paper-live, cuyo llamador ya mapea el error a 409.
- **Pruebas** (3; antes de la corrección fallan las dos esenciales, después pasan):
  - un latido vivo ajeno niega el armado;
  - un latido viejo no lo niega;
  - una base ilegible niega.
- **Riesgo residual:** P30.

## P27 · Un resto menor que un lote no es una posición (parche 24)

- **Hechos** (prueba `tests/integration/test_dust_is_not_a_position.py`; registros `B2_SIN_*` y `B2_CON_*`; sonda `sonda_dust.py`):
  - con 4e-07 BTC en la cuenta (menos de un lote de 1e-06), la sesión bloqueaba entradas por `position_unverified`, se frenaba, suprimía una entrada aprobada como «posición ya abierta», y el plazo de la sesión nunca la encontraba plana;
  - ninguna orden puede vender, proteger ni cerrar menos de un lote, así que nada lo destrababa;
  - un exchange que cobra la comisión en el activo base deja ese resto casi en cada viaje de ida y vuelta.
- **Corrección:** `_holds(position)` = al menos un lote. Se usa en todos los puntos de decisión:
  - protección de una posición restaurada;
  - plazo;
  - cierre de emergencia;
  - `_held_quantity`;
  - entrada;
  - `_manage_position`;
  - `_close_position`;
  - `_reprotect`.
- **No cambiado a propósito:**
  - la verificación de «cuenta limpia» al arrancar compara el diario con el exchange y debe ver todo;
  - el *funding* sobre un resto es despreciable.
- **Lo que no se relajó:** una tenencia ajena de un lote o más **sigue** bloqueando y frenando (la tercera prueba lo fija; la sonda `sonda_saldo_ajeno.py` con 0,5 BTC da freno y 0 órdenes).

## P28 · El stop cubre los lotes enteros que hay en la cuenta (parche 25)

- **Hechos** (prueba `tests/integration/test_stop_quantity_on_the_lot_grid.py`; registros `B3_SIN_correccion_lote_del_stop.txt` y `B3_CON_*`):
  - un venue de prueba cobra la comisión de compra en el activo base y rechaza, como Binance, una cantidad fuera de la grilla de lotes;
  - antes de la corrección, después de una compra se registraron `protective_stop_rejected reason='Filter failure: LOT_SIZE'` y `entries_blocked cause=position_unprotected`. La posición quedó **sin stop**.
  - Las salidas, incluido el cierre de emergencia, ya pasaban por `_build_intent`, que redondea hacia abajo. **Solo el stop** se armaba con la cantidad cruda.
- **Corrección:**
  - `quantity = filters_for(...).quantize(abs(position_quantity))`: hacia abajo, nunca por encima de lo que hay;
  - si el redondeo da 0 (polvo), no se envía nada.
- **Validez de la prueba:** la primera versión **no probaba nada**, porque la sesión abrió un corto y la precondición «saldo fuera de la grilla» falló. Se corrigió para abrir un largo antes de aceptar el resultado. La precondición queda como aserción explícita.
- **Lo que no prueba:**
  - que Binance rechace exactamente así: es su regla `LOT_SIZE` documentada, pero no se verificó contra Testnet (C);
  - lo que pasa después: P29.

## P29 · El vivo direccional supone la comisión en la moneda de cotización

- **Hechos** (la misma prueba de P28, en el registro de antes y de después): con la comisión en el activo base, después de cada compra:
  1. **Tamaño:** `_manage_position` compara el saldo (0,007921071) con el viaje registrado (0,007929, la cantidad del fill). La diferencia son 7,9 lotes, mayor que la tolerancia de un lote: bloquea `position_unverified` y frena la sesión.
  2. **Cierre del viaje:** la salida vende el saldo redondeado hacia abajo, que es menos que la cantidad registrada. `exit_quantity` nunca alcanza `quantity` y el viaje no se puntúa (inferido del código, no ejecutado).
  3. **Comisiones:** `_ledger.record_fee(fill.fee)` registra una comisión en BTC como si fueran dólares (inferido del código; el módulo `mm` sí convierte, `converted_from_base`).
- **Severidad:** el vivo real de Binance spot queda **inoperable**, salvo que las comisiones se paguen en BNB. Falla **cerrado**: frena, no envía nada indebido, y con P28 la posición queda con stop.
- **Alternativas:**
  - (a) exigir el pago de comisiones en BNB y verificarlo al armar: si un fill trae `fee_asset` igual al activo base, se frena. Es una política de producción (C). Por sí sola es frágil: sin saldo de BNB, la comisión vuelve al activo base;
  - (b) registrar el viaje neto de la comisión cobrada en el activo base y convertir la comisión a la moneda de cotización al precio del fill. Es código (A/B) y se valida en Testnet (C);
  - (c) no hacer nada mientras el vivo siga bloqueado.
- **Recomendación:**
  - (c) **ahora**: el vivo no es el cuello de botella (P18);
  - (b), con (a) como resguardo, **antes** de cualquier Testnet o dinero real.
  - Sin esto, una corrida en Testnet solo mostraría el freno.

## P30 · Carrera residual del *lease* vivo

- **Hecho:** P26 verifica primero y registra después. Dos procesos que arman en el mismo instante pueden pasar los dos la verificación. Ventana de milisegundos; requiere dos operadores, o un orquestador que reinicie dos veces.
- **Alternativas:**
  - un índice único parcial: a lo sumo una corrida viva abierta por cuenta;
  - un *advisory lock* de PostgreSQL por cuenta;
  - en SQLite, `BEGIN IMMEDIATE`.
- **Costo:** una migración, que en producción es C.
- **Recomendación:** hacerlo junto con P29 b, antes de Testnet. **No** ahora.

## P31 · E3R: desbloquear E3-H1 (preparada; ejecución pendiente de tu autorización)

- **Bloqueo real:** la regla §4.11 (iv) dependía de la cobertura del archivo web (ver la errata de P19).
- **Reformulación sin contaminar.** Cada documento se congeló con hash y hora, **antes** de calcular cualquier retorno:
  - Adenda R (`87f60413…`): auditoría de supervivencia con evidencia interna del venue (filas de suspensión a las 03:00 UTC, colas de velas con 0 operaciones, anuncios). P0 da VÁLIDO: 160 semanas desde 2023-05-01;
  - corrección opcional R1′ (`86c8fd0b…`): alcance por clase. P0 da VÁLIDO: 274 semanas desde 2021-02-22;
  - Adenda R2 (`6905afd4…`): los cortes con salto de precio ×10 o más, sin mapeo, se tratan como listado nuevo.
- **Orquestador** `ejecutar_E3R.py` (`3b64a04d…`): importa sin cambios el código congelado de E3 (verifica los hashes) y fija las operacionalizaciones que la v3 no fijaba.
  - **Probado solo con datos sintéticos.**
  - Bajo el nulo: IC̄ = −0,0015 → INSUFICIENTE; el diagnóstico de §5.4 rechaza el 5,05 %.
  - Con momentum plantado: RESPALDADA.
  - Las guardas del modo real rechazan 5 de 5, sin leer precios.
- **Errores míos detectados y corregidos antes de congelar:**
  - el intervalo de H2 usaba la regla «método de mayor amplitud», que la Enmienda 2 reemplazó por la envolvente;
  - la semilla del diagnóstico de §5.4 no era la de N13;
  - faltaba la validez previa de §10 sobre datos reales.
- **Plan completo y autorización exacta:** `E3R/PLAN_EJECUCION_UNICA_E3R.md`.

## P32 · Clasificación de las 18 hipótesis con resultado

| Clase | Hipótesis | Por qué |
|---|---|---|
| **Refutadas** (7) | E1-P1, E1-P2, E1-P3, E1-S1, E1-S5, E1-CONF, E2-C | IC90 enteramente negativos, o en contra con datos nuevos (E2-C). E1-P3 está al límite (extremo superior −0,017) |
| **Sin ventaja demostrada** (8) | H-CARRY, T, T-MULTI, E2-A, E2-B, F3-V, F3-R, E1-MR-retraso | Probadas sin conclusión, o sin base. T-MULTI excluye una ventaja ≥ 0,65 %/año (en sustancia, en contra). H-CARRY quedó por debajo de su comparador |
| **No evaluables** (3) | E3-H1, E3-H2, E3-H3 | Nunca se probaron: el protocolo no pudo fijar la ventana |
| **Prometedora, a confirmar** | T, por la vía prospectiva (T-papel) | +7 %/año fuera de muestra con un IC90 de −8,8 a +22,9. No hay nada que hacer hasta su revisión del 2027-04-18 |
| **Merece una prueba nueva e independiente** | E3-H1/H2 (P31) | La única con fundamento publicado, datos verificados y protocolo congelado, que nunca consumió su prueba |

- **Lectura:** «0/18» exagera la evidencia negativa. Solo 7 están refutadas y 3 nunca se probaron.
- **También es cierto:** de las 15 probadas, **ninguna** mostró ventaja, y no hay ninguna que merezca seguir **solo** por el tiempo invertido.
- Si E3R no da RESPALDADA, el programa histórico se queda sin candidatas con datos disponibles.

## P33 · Requisitos mínimos antes de cualquier Testnet o dinero real (lista cerrada)

1. P29 (b), con P29 (a) como resguardo, y una prueba de ciclo completo con comisión en el activo base: entrada, stop válido, disparo del stop, cierre y viaje puntuado.
2. P30 (unicidad del *lease* a nivel de base).
3. **Subcuenta dedicada y plana:**
   - las tenencias ajenas fallan cerradas (P27), así que una cuenta compartida con otras tenencias no arranca;
   - una cuenta plana evita además que un saldo ajeno se confunda con la posición.
4. Testnet (C): el ciclo completo de (1); un rechazo `LOT_SIZE` real; un reinicio con posición abierta; y el `CANCEL_ONLY` del kill switch conservando el stop (P01).
5. Entrega de alertas por un canal real, verificada de punta a punta (P05).
6. Una hipótesis **respaldada**. Sin ella no hay razón económica para operar, por más sólida que sea la plomería (P17).

## P34 · Lo que no conviene hacer ahora (y por qué)

- **Seguir ampliando la infraestructura del vivo:** tiene valor decreciente sin ninguna hipótesis respaldada. Las correcciones P26–P28 eran baratas y cerraban riesgos concretos; P29 y P30 esperan.
- **P15** (dividir `live.py`) y **P14 (a)** (unificar motores): el riesgo de regresión está demostrado y el beneficio no.
- **P25:** ver arriba.
- **P20** (mutación periódica): útil, pero requiere tocar la CI (C) y no cambia ninguna decisión pendiente.
- **Nuevas hipótesis sobre los mismos datos** (variantes de E2, de T o de E1): prohibidas por el registro. Además, el único lugar con potencia razonable es E3R.
- **Correr H-XS-REV-1 (P19)** antes de E3-H1: contaminaría su fuera de muestra.

## P35 · Ejecutor en papel para la cartera transversal (condicionado)

- **Solo si** E3R da RESPALDADA, y como paso P de la v3. La ventana C ciega exige además A4.
- **Qué es:** una cartera semanal de 6 monedas sobre U30, en papel, con la misma mecánica que el motor congelado, para medir la ejecución prospectiva: aperturas, costos, aperturas faltantes.
- **Por qué no antes:** construirlo sin evidencia histórica es exactamente la inercia que señala P18.
