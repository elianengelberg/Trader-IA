# Simulación integral de extremo a extremo (Fase K)

**Entorno:** papel. No hay red, ni venue real, ni testnet, ni credenciales.
- **Candidato:** `17332e1c510d0004f7744bde0a68f008f01652b7` (clon `gate_pg`).
- **Base de comparación:** A+B+03 (`84f9e349526d061771de74ae799d4ecd6e3732ce`, clon `ABC`).
- **Semillas:** 7 y 8. **Script:** `herramientas/simulacion_integral.py`. **Salida:** `logs/K_sim_T15/*.json`; los registros completos están en `*.txt.gz`.

## 1. Método

- **Componentes reales del repositorio:**
  - `LiveRuntime` (la sesión viva, en modo papel);
  - `PaperExecutionProvider`, que empareja las órdenes en reposo al comienzo de cada barra;
  - persistencia real en SQLite, con los mismos repositorios que `AppState`;
  - reinicio por reconstrucción del diario (`rebuild`).
- **Mercado:** `FakeMarketData` de las pruebas, con serie `trend_up` y semilla fija.
- **Fallas inyectadas, deterministas:**
  - un venue que rechaza los stops (como Binance antes de R25);
  - el rechazo del primer cierre;
  - una respuesta perdida tras una orden aceptada;
  - llenados parciales;
  - caídas del feed y del venue;
  - una escritura que se pierde a propósito;
  - un apagado con la posición abierta;
  - una orden ajena puesta a mano.
- **Medición de la protección:** un observador mira el venue **en cada emparejamiento** (`on_bar`) y después de cada llamada que cambia órdenes. Una barra con posición y sin stop (ni cierre en curso) cuenta como «sin protección». Tolerancia 0.
- **Esperado:** el comportamiento seguro de cada escenario se fijó **antes** de correr y es el mismo para los dos árboles.
- **E15** (reversión de versión) corre aparte, porque necesita dos árboles sobre la misma base (`herramientas/reversion_version.sh`).

## 2. Escenarios

| # | Qué se ejercita |
|---|---|
| E01 | Arranque en papel: DISARMED → RUNNING → STOPPED, con registro completo |
| E02 | Mercado y señales: 60 barras evaluadas, sin error |
| E03 | Apertura: posición abierta; orden y fill guardados |
| E04 | Protección colocada y confirmada: exactamente un stop trabajando en cada barra |
| E04b | Venue que rechaza stops (R25): la sesión tiene que **darse cuenta** |
| E05 | Gestión normal: nunca dos stops, ninguna barra sin protección |
| E06 | Cierre por stop (el mercado cruza el nivel): plana, sin órdenes colgadas |
| E07 | Cierre por reversión: cierre enviado, plana, ninguna barra sin protección |
| E08 | Cierre rechazado y reintento (R18): protegida en la misma llamada |
| E09 | Cierre con respuesta perdida (estado desconocido) y llenados parciales: sin cierre duplicado |
| E10 | Pérdida de conexión: 3 caídas del feed y 2 del venue; la posición sigue protegida |
| E11 | Escrituras concurrentes del mismo backtest: ningún escritor descartado recibe éxito. En SQLite; la carrera real se midió en PostgreSQL (`registro/F1_r15.txt`) |
| E12 | Persistencia incompleta (R19): una escritura de fill se pierde |
| E13 | Apagado con la posición abierta y recuperación: reconstrucción, re-protección **antes** de la primera barra, cierre |
| E14 | Reconciliación con una orden ajena en el venue: la operatoria se detiene |
| E15 | Reversión de versión: código anterior frente a esquema nuevo |

## Resumen por escenario, árbol y semilla

| Escenario | Candidato s7 | Candidato s8 | Base s7 | Base s8 | Esperado incumplido en la base |
|---|---|---|---|---|---|
| E01_arranque_en_papel | CUMPLE | CUMPLE | CUMPLE | CUMPLE | — |
| E02_mercado_y_senales | CUMPLE | CUMPLE | CUMPLE | CUMPLE | — |
| E03_apertura | CUMPLE | CUMPLE | CUMPLE | CUMPLE | — |
| E04_proteccion_colocada_y_confirmada | CUMPLE | CUMPLE | CUMPLE | CUMPLE | — |
| E04b_venue_que_rechaza_stops_R25 | CUMPLE | CUMPLE | NO CUMPLE | NO CUMPLE | entradas bloqueadas; incidente guardado; posición contada como desprotegida; sesión en alto de órdenes nuevas |
| E05_gestion_normal | CUMPLE | CUMPLE | CUMPLE | CUMPLE | — |
| E06_cierre_por_stop | CUMPLE | CUMPLE | CUMPLE | CUMPLE | — |
| E07_cierre_por_reversion | CUMPLE | CUMPLE | CUMPLE | CUMPLE | — |
| E08_cierre_rechazado_y_reintento | CUMPLE | CUMPLE | NO CUMPLE | NO CUMPLE | ninguna barra sin protección; protegida en la misma llamada |
| E09_parcial_y_timeout | CUMPLE | CUMPLE | CUMPLE | CUMPLE | — |
| E10_perdida_de_conexion | CUMPLE | CUMPLE | CUMPLE | CUMPLE | — |
| E11_escrituras_concurrentes | CUMPLE | CUMPLE | NO CUMPLE | NO CUMPLE | ningún escritor descartado recibe éxito |
| E12_persistencia_incompleta | CUMPLE | CUMPLE | NO CUMPLE | NO CUMPLE | cierre no limpio; flush NO dice completo |
| E13_apagado_y_recuperacion | CUMPLE | CUMPLE | NO CUMPLE | NO CUMPLE | protegida antes de su primera barra |
| E14_reconciliacion | CUMPLE | CUMPLE | CUMPLE | CUMPLE | — |

Totales CUMPLE: candidato 15/15 y 15/15; base 10/15 y 10/15. Clones: candidato `gate_pg`, base `ABC`.

## Detalle por escenario (candidato, semilla 7; la base se indica donde difiere)

### E01_arranque_en_papel

- **Esperado (fijado antes de correr):** arranca en RUNNING; cierra en STOPPED; registro completo al cerrar.
- **Estado inicial:** `armed`, posición 0.0, órdenes abiertas ninguna.
- **Transiciones (hasta el cierre del escenario):** disarmed->arming → arming->armed → armed->starting → starting->running → running->stopping → stopping->stopped.
- **Estado final:** `stopped`, posición 0.0, órdenes abiertas ninguna, bloqueos ninguno.
- **Órdenes y contadores:** sin actividad.
- **Escrituras:** programadas 1, confirmadas 1, fallidas 0, en vuelo 0, completo=True; `persistence_flushed`=True.
- **Filas en la base:** órdenes 0, fills 0, incidentes 0 (ninguno), corridas 1.
- **Errores:** ninguno.
- **Inconsistencias (esperado no cumplido):** ninguna. **Veredicto: CUMPLE.**

### E02_mercado_y_senales

- **Esperado (fijado antes de correr):** evalúa señales; sin error.
- **Estado final:** `running`, posición 0.0, órdenes abiertas ninguna, bloqueos ninguno.
- **Órdenes y contadores:** orders=1, round_trips=1, stops_placed=4, exits_stop=1.
- **Otros observables:** `{"senales": 60}`.
- **Errores:** ninguno.
- **Inconsistencias (esperado no cumplido):** ninguna. **Veredicto: CUMPLE.**

### E03_apertura

- **Esperado (fijado antes de correr):** posición abierta; orden y fill guardados.
- **Estado final:** `running`, posición 0.080117, órdenes abiertas ['stop/ro'], bloqueos ninguno.
- **Órdenes y contadores:** orders=1, stops_placed=1.
- **Protección medida en cada emparejamiento:** barras con posición 0, barras sin protección **0**, máximo de stops simultáneos 1.
- **Filas en la base:** órdenes 2, fills 1, incidentes 0 (ninguno), corridas 1.
- **Errores:** ninguno.
- **Inconsistencias (esperado no cumplido):** ninguna. **Veredicto: CUMPLE.**

### E04_proteccion_colocada_y_confirmada

- **Esperado (fijado antes de correr):** un stop trabajando; ninguna barra sin protección; snapshot dice protegida.
- **Transiciones (hasta el cierre del escenario):** disarmed->arming → arming->armed → armed->starting → starting->running → running->stopping → stopping->stopped.
- **Estado final:** `running`, posición 0.080117, órdenes abiertas ['stop/ro'], bloqueos ninguno.
- **Órdenes y contadores:** orders=1, stops_placed=2.
- **Protección medida en cada emparejamiento:** barras con posición 3, barras sin protección **0**, máximo de stops simultáneos 1.
- **Filas en la base:** órdenes 3, fills 1, incidentes 0 (ninguno), corridas 1.
- **Otros observables:** `{"snapshot_protected": true}`.
- **Errores:** ninguno.
- **Inconsistencias (esperado no cumplido):** ninguna. **Veredicto: CUMPLE.**

### E04b_venue_que_rechaza_stops_R25

- **Esperado (fijado antes de correr):** posición contada como desprotegida; entradas bloqueadas; sesión en alto de órdenes nuevas; incidente guardado; snapshot no dice protegida.
- **Transiciones (hasta el cierre del escenario):** disarmed->arming → arming->armed → armed->starting → starting->running → running->halt_new_orders → halt_new_orders->stopping → stopping->stopped.
- **Estado final:** `halt_new_orders`, posición 0.080117, órdenes abiertas ninguna, bloqueos ['position_unprotected'], last_error: «position unprotected: protective stop refused: [EXECUTION_ERROR] order type stop is not supported by this adapter (inyectado, como Binance antes de R25)».
- **Órdenes y contadores:** orders=1, unprotected_positions=1, protective_stop_failures=4.
- **Protección medida en cada emparejamiento:** barras con posición 3, barras sin protección **3**, máximo de stops simultáneos 0.
- **Filas en la base:** órdenes 1, fills 1, incidentes 6 (entries_blocked:position_unprotected, halt_new_orders, protective_stop_failed), corridas 1.
- **Otros observables:** `{"snapshot_protected": false}`.
- **Errores:** ninguno.
- **Inconsistencias (esperado no cumplido):** ninguna. **Veredicto: CUMPLE.**
- **Base (A+B+03):** NO CUMPLE, incumple: posición contada como desprotegida, entradas bloqueadas, sesión en alto de órdenes nuevas, incidente guardado. Estado final `running`, bloqueos ninguno, protección: {"barras_con_posicion": 3, "barras_sin_proteccion": 3, "max_stops_simultaneos": 0, "racha_max_llamadas_sin_proteccion": 0}.

### E05_gestion_normal

- **Esperado (fijado antes de correr):** nunca dos stops; ninguna barra sin protección.
- **Estado final:** `running`, posición 0.0, órdenes abiertas ninguna, bloqueos ninguno.
- **Órdenes y contadores:** orders=1, round_trips=1, stops_placed=4, exits_stop=1.
- **Protección medida en cada emparejamiento:** barras con posición 9, barras sin protección **0**, máximo de stops simultáneos 1.
- **Errores:** ninguno.
- **Inconsistencias (esperado no cumplido):** ninguna. **Veredicto: CUMPLE.**

### E06_cierre_por_stop

- **Esperado (fijado antes de correr):** cerrada por stop; plana; ida y vuelta puntuada; sin órdenes colgadas.
- **Estado final:** `running`, posición 0.0, órdenes abiertas ninguna, bloqueos ninguno.
- **Órdenes y contadores:** orders=1, round_trips=1, stops_placed=3, exits_stop=1.
- **Protección medida en cada emparejamiento:** barras con posición 3, barras sin protección **0**, máximo de stops simultáneos 1.
- **Errores:** ninguno.
- **Inconsistencias (esperado no cumplido):** ninguna. **Veredicto: CUMPLE.**

### E07_cierre_por_reversion

- **Esperado (fijado antes de correr):** cierre enviado; plana; ninguna barra sin protección.
- **Estado final:** `running`, posición 0.0, órdenes abiertas ninguna, bloqueos ninguno.
- **Órdenes y contadores:** orders=2, round_trips=1, stops_placed=2, exits_reversal=1.
- **Protección medida en cada emparejamiento:** barras con posición 2, barras sin protección **0**, máximo de stops simultáneos 1.
- **Otros observables:** `{"enviado": true}`.
- **Errores:** ninguno.
- **Inconsistencias (esperado no cumplido):** ninguna. **Veredicto: CUMPLE.**

### E08_cierre_rechazado_y_reintento

- **Esperado (fijado antes de correr):** rechazo registrado; protegida en la misma llamada; ninguna barra sin protección; reintento cierra.
- **Estado final:** `running`, posición 0.0, órdenes abiertas ninguna, bloqueos ninguno.
- **Órdenes y contadores:** orders=3, round_trips=1, stops_placed=3, exits_rejected=1, exits_time=2.
- **Protección medida en cada emparejamiento:** barras con posición 3, barras sin protección **0**, máximo de stops simultáneos 1.
- **tras el rechazo:** `{"held": 0.080117, "protegida": true, "stops": 1}`.
- **Filas en la base:** órdenes 6, fills 2, incidentes 1 (exit_rejected), corridas 1.
- **Errores:** ninguno.
- **Inconsistencias (esperado no cumplido):** ninguna. **Veredicto: CUMPLE.**
- **Base (A+B+03):** NO CUMPLE, incumple: protegida en la misma llamada, ninguna barra sin protección. Estado final `running`, bloqueos ninguno, protección: {"barras_con_posicion": 3, "barras_sin_proteccion": 1, "max_stops_simultaneos": 1, "racha_max_llamadas_sin_proteccion": 2}, {"tras_el_rechazo": {"held": 0.080117, "protegida": false, "stops": 0}}.

### E09_parcial_y_timeout

- **Esperado (fijado antes de correr):** estado desconocido resuelto; sin cierre duplicado por el timeout; plana al final; ninguna barra sin protección.
- **Estado final:** `running`, posición 0.0, órdenes abiertas ninguna, bloqueos ninguno.
- **Órdenes y contadores:** orders=2, round_trips=1, stops_placed=2, exits_time=1, unknown_order_states=1.
- **Protección medida en cada emparejamiento:** barras con posición 4, barras sin protección **0**, máximo de stops simultáneos 1.
- **Otros observables:** `{"cierres_enviados": 1}`.
- **Errores:** ninguno.
- **Inconsistencias (esperado no cumplido):** ninguna. **Veredicto: CUMPLE.**

### E10_perdida_de_conexion

- **Esperado (fijado antes de correr):** posición sigue protegida en el venue; ninguna barra sin protección.
- **Transiciones (hasta el cierre del escenario):** disarmed->arming → arming->armed → armed->starting → starting->running → running->stopping → stopping->stopped.
- **Estado final:** `running`, posición 0.0, órdenes abiertas ninguna, bloqueos ninguno.
- **Órdenes y contadores:** orders=1, round_trips=1, stops_placed=4, exits_stop=1.
- **Protección medida en cada emparejamiento:** barras con posición 6, barras sin protección **0**, máximo de stops simultáneos 1.
- **Otros observables:** `{"excepciones_al_bucle": 3}`.
- **Errores:** ninguno.
- **Inconsistencias (esperado no cumplido):** ninguna. **Veredicto: CUMPLE.**

### E11_escrituras_concurrentes

- **Esperado (fijado antes de correr):** ningún escritor descartado recibe éxito.
- **Otros observables:** `{"intentos": 20, "ambos_aceptados": 0, "exito_descartado": 0, "nota": "SQLite serializa escritores; la carrera real está medida en PostgreSQL (F1)"}`.
- **Errores:** ninguno.
- **Inconsistencias (esperado no cumplido):** ninguna. **Veredicto: CUMPLE.**
- **Base (A+B+03):** NO CUMPLE, incumple: ningún escritor descartado recibe éxito. Estado final `None`, bloqueos ninguno, {"ambos_aceptados": 19, "exito_descartado": 19}.

### E12_persistencia_incompleta

- **Esperado (fijado antes de correr):** flush NO dice completo; cierre no limpio; la siguiente sesión no opera sobre un registro corto.
- **Escrituras:** programadas 2534, confirmadas 2533, fallidas 1, en vuelo 0, completo=False; `persistence_flushed`=False.
- **Otros observables:** `{"flush_dijo": false, "last_error": "1 persistence write(s) failed during the session; the record is incomplete", "reconstruccion_completa": false, "siguiente_sesion_bloqueada": true}`.
- **Errores:** ninguno.
- **Inconsistencias (esperado no cumplido):** ninguna. **Veredicto: CUMPLE.**
- **Base (A+B+03):** NO CUMPLE, incumple: flush NO dice completo, cierre no limpio. Estado final `None`, bloqueos ninguno, {"flush_dijo": true, "escrituras": {"sin_informe": "esta versión no lleva la cuenta de sus escrituras"}}.

### E13_apagado_y_recuperacion

- **Esperado (fijado antes de correr):** la reconstrucción ve la posición; la sesión nueva la protege; protegida antes de su primera barra; se cierra y el registro queda completo y plano.
- **Estado final:** `running`, posición 0.0, órdenes abiertas ninguna, bloqueos ninguno.
- **Órdenes y contadores:** orders=1, round_trips=1, stops_placed=1, exits_time=1.
- **al arrancar:** `{"held": 0.080117, "protegida": true, "stops": 1}`.
- **reconstruccion:** `{"completa": true, "posicion": 0.080117}`.
- **final reconstruido:** `{"completo": true, "posicion": false}`.
- **proteccion sesion b:** `{"barras_con_posicion": 2, "barras_sin_proteccion": 0, "max_stops_simultaneos": 1, "racha_max_llamadas_sin_proteccion": 1}`.
- **Otros observables:** `{"posicion_al_apagar": 0.080117, "reprotegida": true}`.
- **Errores:** ninguno.
- **Inconsistencias (esperado no cumplido):** ninguna. **Veredicto: CUMPLE.**
- **Base (A+B+03):** NO CUMPLE, incumple: protegida antes de su primera barra. Estado final `running`, bloqueos ninguno, {"al_arrancar": {"held": 0.080117, "protegida": false, "stops": 0}}.

### E14_reconciliacion

- **Esperado (fijado antes de correr):** la orden ajena detiene la operatoria.
- **Transiciones (hasta el cierre del escenario):** disarmed->arming → arming->armed → armed->starting → starting->running → running->safe_mode → safe_mode->stopping → stopping->stopped.
- **Estado final:** `safe_mode`, posición 0.080117, órdenes abiertas ['limit', 'stop/ro'], bloqueos ninguno.
- **Órdenes y contadores:** orders=1, stops_placed=2.
- **Filas en la base:** órdenes 3, fills 1, incidentes 1 (safe_mode), corridas 1.
- **Otros observables:** `{"estado_tras_conciliar": "safe_mode"}`.
- **Errores:** ninguno.
- **Inconsistencias (esperado no cumplido):** ninguna. **Veredicto: CUMPLE.**

## E15: reversión de versión (`logs/K_E15.txt`, `logs/K_E15/`)

Una base SQLite compartida entre árboles: el candidato con esquema v8 y el anterior, A+B+03, con esquema v7.

| Paso | Resultado |
|---|---|
| El candidato aplica las migraciones y escribe un backtest (motor 1.2.0) y dos incidentes, uno con `kind` de 34 caracteres | `alembic upgrade head` rc=0; guardado `created` |
| El código anterior lee la base sin revertir | Lee el backtest y los incidentes, pero `ensure_schema()` **RECHAZA** (`ConfigurationError`: la versión de esquema no coincide). Falla cerrado; no opera sobre un esquema que no conoce |
| `alembic downgrade 0007` con el incidente largo presente | **Se niega** (rc=1): «1 incident(s) have a kind longer than 32 characters; narrowing incidents.kind would cut them. Export or re-file them before downgrading» |
| Exportar los incidentes largos a JSON y borrarlos | 1 exportado (`K_E15/*.incidentes_exportados.json`) |
| `alembic downgrade 0007` | rc=0 |
| El código anterior lee la base revertida | `ensure_schema()` = 7; lee el backtest y el incidente corto |
| El candidato vuelve a subir (`upgrade head`) y lee | `ensure_schema()` = 8; datos intactos. El incidente exportado **no** se reimporta solo: queda en el JSON |

## 3. Lectura

- **Candidato:** 15 de 15 en las dos semillas.
- **Base:** 10 de 15 en las dos semillas. Falla exactamente en lo que corrigen los parches:
  - **E04b** (R25): con un venue que rechaza stops, la base sigue `running` sin bloqueo ni incidente.
  - **E08** (R18): tras el cierre rechazado, la base queda sin stop, con una barra emparejada sin protección.
  - **E11** (R15): la base da éxito a un escritor descartado.
  - **E12** (R19): la base dice «completo» con una escritura perdida.
  - **E13** (N5): la posición restaurada no tiene stop al arrancar.
- **Determinismo:** con la misma semilla, la base dio JSON idénticos en tres corridas (`K_sim`, `K_sim_final` y `K_sim_T15`).
  - En el candidato, lo único que varía entre corridas es el número de escrituras programadas en E12: depende del tiempo de pared que tarda el bucle (entre 2534 y 3777 en seis corridas).
  - El invariante se mantiene en las seis: confirmadas = programadas − 1, fallidas 1, `complete=false`.
  - Los veredictos son idénticos en todas las corridas de los tres árboles candidatos sucesivos (`85d973ee`, `c7688384`, `17332e1c`).

## 4. Límites

- Es **papel**. El adaptador de Binance no participa: el rechazo de stops de E04b se inyecta. Lo que Binance haga con un `STOP_LOSS` real solo lo dirá la testnet (R25, T10).
- La persistencia es SQLite, que serializa a los escritores. Las carreras reales de R15 y la columna de R24-H1 se midieron en PostgreSQL 16.15 (`registro/F1_r15.txt`, `logs/H1_*`).
- Se excluyen el reloj real, la latencia de red y los tiempos de un venue real.
