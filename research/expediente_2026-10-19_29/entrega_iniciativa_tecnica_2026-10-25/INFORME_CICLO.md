# Informe del ciclo de iniciativa técnica · Trader-IA · 2026-10-25

**Estado de autorización: NO AUTORIZADO PARA OPERAR CON DINERO REAL.** `validada_para_operar` no existe en el repositorio y no se creó ni se tocó. No hubo commits, push, PR, merge, deploy, conexión a exchanges ni uso de credenciales.

| | |
|---|---|
| Base | commit `72ffae5` + parches 01–15 de la entrega anterior = árbol T15 `17332e1c…` |
| Resultado | parches 16–22 = árbol T22 `87af7a45…` (`parches/CADENA_TI.txt`). T21 `bcfa4008…` es el último árbol con cambios de código; 22 solo corrige documentación |
| Repositorio protegido | sin cambios: índice `37490035…`, HEAD `72ffae5`, 0 cambios (`VERIFICACION_FINAL.txt`) |
| Registro de propuestas | `PROPUESTAS_TECNICAS.md` (P01–P25) |

## Resumen

- Encontré y corregí **10 defectos**: 9 de código, cada uno con una prueba que falla sin el arreglo y pasa con él, y 1 de documentación operativa. Los tres más graves: el kill switch dejaba la posición **sin stop** por tiempo indefinido (P01); mi propio arreglo de R19 del ciclo anterior **no tenía efecto en producción** (P04, errata); y, en el experimento de mutación, quitar la detención de entradas ante una orden de estado desconocido dejaba a la sesión mandar **6 entradas encima de una que podía estar ejecutada** sin que ninguna prueba fallara (M18).
- El experimento de mutación sobre la lógica que protege el capital: T15 detectaba **16 de 22** defectos sembrados; los 6 sobrevivientes tienen ahora prueba nueva. Como esas pruebas se escribieron conociendo los mutantes, medí aparte un **lote 2 no contaminado** (11 mutantes fijados antes, en lógica que no toqué): la suite detecta **11 de 11**. Los huecos estaban en los caminos de integración del vivo, no en las reglas unitarias.
- Encontré además que **dos pruebas de *funding* fallan siempre en una ventana de ~6 min cada 8 h** (05:40, 13:40 y 21:40 UTC), desde la base `72ffae5`. Esa falla contaminó mi propia medición y la corregí (P25).
- Dos hipótesis mías se **refutaron** con experimentos (la regla de EV aprueba ruido por comparaciones múltiples; los trades sintéticos fabrican ventaja) y no cambié nada por ellas.
- Mi posición sobre el próximo paso: **integrar 16–22 y dejar de ampliar la infraestructura del vivo**. El cuello de botella del proyecto es la información (0 de 18 hipótesis respaldadas), no la ejecución.

---

## 1. Defectos corregidos

| Id | Defecto | Severidad | Demostración (sin → con arreglo) | Parche |
|---|---|---|---|---|
| P01 | `kill_switch()` cancelaba el stop protector y dejaba `SAFE_MODE`, donde nada lo repone: posición abierta y sin stop hasta que volviera el operador; ni siquiera se contaba como desprotegida | **Alta** | `exp_kill_antes.json`: 0 stops, el precio cruza el nivel y la posición sigue. Las 6 pruebas de `test_emergency_controls_protection.py` (cubren P01–P03) fallan sin el arreglo (`A1_SIN_correccion_razones.txt`) | 16 |
| P02 | `emergency_flatten()` con el cierre rechazado: una barra emparejada sin stop | Alta | `exp_flatten_rechazado_antes.json` | 16 |
| P03 | El venue de papel no emparejaba en `PAUSED` / `SAFE_MODE`: un stop en reposo nunca se ejecutaba | Media | 2 pruebas | 16 |
| P04 | **R19 sin efecto en producción.** El despachador de la aplicación absorbía toda falla, así que la sesión contaba las escrituras rechazadas como confirmadas y el *flush* decía «completo» | **Alta** (pérdida silenciosa) | `A4_SIN_correccion_con_el_despachador_de_produccion.txt` | 19 |
| P05 | Las alertas salían desde dentro de la escritura de la incidencia (con la base caída, ninguna alerta) y un HTTP 500 contaba como entregado | Alta | 2 pruebas (`A6_SIN_correccion.txt`) | 19 |
| P06 | `/api/metrics` no describía la sesión 24/7 que tiene las posiciones | Media-alta | prueba de la serie | 18 |
| P07 | La compuerta `EDGE_EVIDENCE` leía el motor de escenarios y contaba trades sintéticos | Media | 3 pruebas | 17 |
| P08 | N3: el motor de escenarios decía «completo» con escrituras fallidas | Baja-media | `A5_SIN_correccion.txt` | 19 |
| P01-doc | `LIVE_RUNBOOK.md` y `DEPLOYMENT.md` describían el kill switch como «cancela las órdenes en reposo» y «sigue gestionando las salidas»; ninguna de las dos cosas era cierta tras P01 (y la segunda tampoco antes) | Media (un operador decide sobre la base del runbook) | revisión del texto contra el código | 22 |
| P22 | Al reanudar tras una pausa > TTL, el *watchdog* detenía la sesión por «datos viejos» con velas llegando. **P03 lo agravaba:** la detención duraba hasta la vela siguiente | Media | falla en T15 y en T20 (`A7_SIN_correccion_*.txt`) | 21 |

Además, en el parche 20 hay **6 funciones de prueba nuevas** (8 casos con la parametrización) que cierran los 6 huecos de detección del experimento de mutación. Cada una se verificó contra su mutante: falla con él y pasa con el código real (`logs/sin_y_con_correccion/M*_mutante_con_prueba_nueva.*`).

### Errata respecto de entregas anteriores

1. **R19** figuraba como «CORREGIDO_Y_VERIFICADO» en la entrega de integración controlada. Las pruebas usaban un doble que lanza; producción usaba un despachador que absorbe. Recién queda corregido con el parche 19 (P04).
2. En la primera versión de `PROPUESTAS_TECNICAS.md` de este ciclo anoté el *watchdog* al reanudar como «riesgo residual que no cambié». Al revisarlo era un defecto real, y mi P03 lo empeoraba (P22).
3. La medición de mutación «después» sobre los mismos 22 mutantes **no es una medida independiente** de la calidad de las pruebas (P09). Por eso existe el lote 2.
4. **Dos errores de procedimiento míos en la corrida de mutación de T21**, detectados y corregidos antes de cerrar:
   - la lista de pruebas omitía un archivo nuevo, y M18 salió vivo;
   - cinco «muertes» las produjo una prueba que falla por la hora, no el mutante (P25).
   Los JSON consolidados dicen, mutante por mutante, de qué corrida sale cada resultado.
5. En una versión intermedia de este informe escribí que el comportamiento del kill switch «no estaba documentado». Era inexacto: estaba documentado a medias y de forma engañosa (P01, parche 22).

## 2. Mejoras por iniciativa propia

- **Instrumento de poder de detección** (`herramientas/exp_mutacion.py`, lote 2 en `exp_mutacion_lote2.py`): mutantes fijados antes de correr, restauración verificada por sha256. Midió por primera vez qué defectos de protección de capital detecta la suite, en lugar de cuántas líneas cubre.
- **Contrato de persistencia en producción** (P04): ahora una prueba recorre el despachador real de la aplicación, no un doble.
- **Observabilidad de la sesión 24/7** (P06): estado, posición desprotegida, bloqueos, antigüedad del latido y de los datos, y completitud de la persistencia. Antes, un *scrape* veía `tia_up 1` y nada más.
- **Reproducibilidad del paquete** (`reproducir_TI.sh`): reconstruye T22 desde el repositorio de origen y los parches del paquete, compara cada árbol intermedio y comprueba que el índice del origen no cambie.

## 3. Experimentos y qué mostraron

| Experimento | Pregunta | Resultado | Consecuencia |
|---|---|---|---|
| Kill switch antes/después (`exp_kill_switch.py`) | ¿Queda protegida la posición? | Antes: 0 stops y la barra cruza el nivel. Después: el stop queda y se ejecuta | P01 implementado |
| Falsos positivos de la regla de EV (`exp_ev_falsos_positivos.py`, 5.000 réplicas por celda) | ¿Aprueba ruido por comparaciones múltiples? | Con c = 20 bps: ≤ 0,3 % (σ = 100) y 2,9 % (σ = 200) por bucket; 0,5 % de historias operan, con una pérdida media de −0,76 bps | **Hipótesis refutada**; Bonferroni descartado (bajaba la potencia de 18 % a 1 %) |
| Razón de costos (`exp_ev_razon_costos.py`) | ¿Qué limita la potencia? | Con la razón 0,6 la potencia ante +15 bps **no crece** con n (19 % → 20 % de n = 30 a 120); con 1,0 sube a 54 % | Hallazgo validado; **no** cambiar la regla hasta medir costos reales (P11) |
| Contaminación sintética (`exp_contaminacion_sintetica.py`, 12 corridas) | ¿La deriva de los escenarios fabrica un bucket operable? | 26 trades, ningún bucket llega a 30, media bruta −0,99 bps | **No confirmado en lo medido**; igual se cerró la puerta en la compuerta (P07) |
| Mutación, lote 1 (22 mutantes) | ¿Qué defectos de protección pasan la suite? | T15: **16/22** muertos (vivos: M04, M09, M10, M12, M14, M18). T21: **22/22**, después de corregir dos errores de procedimiento míos (P09) | 6 pruebas nuevas (parche 20); medida «después» no independiente |
| Mutación, lote 2 (11 mutantes, suite completa, fijados antes) | ¿Qué detecta la suite en lógica que no miré? | **11/11** aplicables (frenos de drawdown y de pérdida diaria, reglas de salida, encogimiento y costos del EV, permisos de `HALT_NEW_ORDERS`). M32 no aplicó; M32b la corrige después de correr, declarado | P24; muestra chica, no es cobertura |
| Muertes sospechosas en la corrida de T21 | ¿Una prueba de *funding* mata a M07, M09, M10 y M11? | No: aislados, 0/4 (dos veces). Con el reloj desplazado, dos pruebas fallan **sin mutante** a las 05:40, 13:40 y 21:40 UTC (±3 min) y pasan fuera de esas ventanas; igual en la base `72ffae5` | P25; los 5 mutantes afectados se repitieron fuera de la ventana |
| Simulación integral E01–E14 (semillas 7 y 8) | ¿Regresiones de extremo a extremo? | T21: **30/30 CUMPLE** (igual que T15) | sin regresiones |
| Diferencia de E12 entre T15 y T21 | ¿Lo causó algún parche? | No: el **mismo** T15 dio 2.534 escrituras a las 20:04 y 73 a las 21:35. La serie se ancla a `datetime.now()` | P23 (reproducibilidad) |
| CI local en T21 | ¿Suite, compuerta y migraciones? | Job principal 2.053 pasan + 10 salteadas (PG); job PG **2.063/2.063**; compuerta `pass`; Alembic ida, vuelta e ida OK | — |

## 4. Decisiones y fundamentos

### D1 · Kill switch (P01)
- **Hechos:** el stop se cancelaba y `SAFE_MODE` no gestiona posiciones (`exp_kill_antes.json`).
- **¿Era deliberado?** La documentación dice «cancela las órdenes en reposo» y «no cierra posiciones», pero ninguna fuente dice que esa combinación deja la posición sin stop. `docs/DEPLOYMENT.md` lo presentaba incluso como «detener entradas, **seguir gestionando las salidas**», lo que el código no hacía. Y la regla de R18 exige lo contrario: «toda barra encuentra la posición protegida». Lo leo como una consecuencia no prevista, no como una decisión.
- **Alternativas:** conservar las órdenes que solo reducen · cancelar todo y re-proteger · solo avisar · convertir el kill switch en cierre.
- **Criterio:** no enviar órdenes nuevas en plena emergencia y no aumentar la exposición.
- **Decisión:** conservar las reducing-only (stop y cierre en curso).
- **Validación:** las pruebas de `test_emergency_controls_protection.py` y el experimento después.
- **Riesgo residual:** si el operador acciona el kill switch **porque** el stop está mal, el stop sigue ahí.

### D2 · Despachador de sesión (P04)
- **Hechos:** `_persist` absorbe; los servicios de *market making* lo esperan en línea y dependen de que no lance.
- **Alternativas:** que `_persist` lance siempre (rompe *market making*) · un despachador para las sesiones que cuenta igual y vuelve a lanzar.
- **Decisión:** `session_persist` para la sesión viva y el motor de escenarios.
- **Validación:** prueba con el despachador real; los contadores de la aplicación y de la sesión coinciden.
- **Riesgo residual:** las fábricas reales de sesiones (proveedores de Binance) se verificaron por inspección, no por prueba.

### D3 · Watchdog al reanudar (P22)
- **Alternativas:** reiniciar el reloj al reanudar · registrar la hora de las velas que ya ve el emparejador en pausa.
- **Criterio:** que la métrica de antigüedad de datos no mienta y que un feed cortado siga detectándose en el primer ciclo.
- **Decisión:** la segunda.
- **Validación:** la prueba 2 **falla con la alternativa descartada**.
- **Riesgo residual:** con venue real queda una detención espuria que se cura en el mismo ciclo (comportamiento de T15).

### D4 · No cambiar la regla de EV (P10, P11)
- **Hechos:** sin ventaja, los falsos positivos son bajos con los costos actuales; la razón 0,6 limita la potencia.
- **Criterio:** no relajar un control de riesgo mientras el modelo de costos que lo justifica siga sin verificar (`FEES_VERIFIED_AT_SOURCE` falla).
- **Decisión:** no tocarla ahora. Revisarla con costos medidos sobre fills reales, y con un experimento prerregistrado sobre esos costos.

### D5 · No migrar `pytest.approx` ni partir `live.py` en este ciclo (P13, P15)
- **Criterio:** son 49 aserciones de pruebas ajenas y un refactor grande.
- **Decisión:** ninguno de los dos sin revisión humana. El refactor, además, recién cuando la detección esté medida: el criterio de aceptación es que la tasa de mutantes muertos no baje.

## 5. Propuestas descartadas

| Propuesta | Por qué |
|---|---|
| Corrección de Bonferroni en la regla de EV | Refutada por experimento: costo alto en potencia, beneficio irrelevante con los costos actuales (P10) |
| Kill switch = cierre de emergencia | Borra la separación deliberada entre «el software duda» y «quiero salir» (P01 d) |
| `_persist` que lance siempre | Rompe a los servicios de *market making* que lo esperan en línea (P04 a) |
| Reiniciar el reloj del *watchdog* al reanudar | Hace mentir a la métrica y demora un TTL la detección de un feed cortado; la prueba 2 lo detecta (P22 a) |
| Unificar `RuntimeEngine` y `LiveRuntime` de una vez | Riesgo alto sobre una suite cuya detección recién se empezó a medir (P14 a) |

## 6. Nuevas oportunidades

Ordenadas por beneficio sobre costo, según mi criterio:

1. **P20:** mutación dirigida como chequeo periódico (manual o nocturno, no en cada push), con este ciclo como línea base.
2. **P13:** `approx_price(x, tick)` y migrar las 49 comparaciones de precio.
3. **P23:** `start` fijo en la simulación y en las pruebas que comparan conteos.
4. **P14 (c):** declarar el motor de escenarios «solo demo»; luego (b), extraer el libro de escrituras compartido.
5. **P05:** una cola de alertas con reintento acotado, y reglas de Alertmanager (mínimo: `tia_live_position_unprotected == 1` durante más de 1 min).
6. **P22:** leer el feed durante la pausa también con venue real.
7. **P19:** H-XS-REV-1, especificación completa. **No correr antes de E3-H1.**
8. **P25:** anclar los *builders* de prueba dentro del período de *funding* en curso. Elimina por construcción la ventana horaria, y conviene verificarlo con la suite completa a varias horas desplazadas.
9. **P24 + P20:** los dos lotes de mutación como línea base del chequeo periódico, con control sin mutante.

## 7. Riesgos abiertos

- **R17**, de siempre: mientras un cierre trabaja, la posición no tiene stop propio (decisión T8).
- **P16 (hipótesis, no verificada):** en spot, Binance cobra la comisión de compra en el activo base, así que un `STOP_LOSS` por la cantidad del fill podría pedir más de lo que hay. Necesita testnet.
- **Kill switch:** si el stop es el problema, sigue en reposo (D1).
- **Alertas:** sin reintento; una alerta fallida se cuenta pero no se reenvía.
- **Fábricas de sesión con Binance:** que pasen `session_persist` está verificado por inspección, no por prueba.
- **Valor por defecto `legacy`** de `ev_evidence_policy` en `docker-compose.prod.yml` (P12). La compuerta ya no aprueba con él, pero el motor de EV del vivo sigue aprendiendo de lo que esa política admite.
- **Venue real al reanudar:** detención espuria con incidencia y alerta, curada en el mismo ciclo (P22).
- **Reproducibilidad:** los conteos de la simulación dependen de la hora de pared (P23).
- **La sesión de papel no puede demostrar ventaja** (P17). Una compuerta aprobada por historial de papel no es evidencia de ventaja.
- **CI en ventana horaria (P25):** una corrida que pase por 05:37–05:43, 13:37–13:43 o 21:37–21:43 UTC puede fallar sin ningún defecto. La CI local de T21 pasó (21:31–21:37 UTC, en el borde de la ventana), y eso no es garantía de la próxima.
- **Lote 2:** en 4 de 11 mutantes no verifiqué que la prueba falle por la razón correcta (P24).

## 8. Recomendación técnica independiente

1. **Integrar 16–22**, previa revisión humana de los diffs (código: 4 archivos, +205 / −27 líneas; pruebas: 11 archivos, +790 / −3). Cierran tres caminos a una posición desprotegida o a escrituras perdidas en silencio, y valen también para papel.
2. **No seguir ampliando la infraestructura del vivo.** Dos ciclos endurecieron la ejecución. Con 0 de 18 hipótesis respaldadas, cada hora más de plomería vale menos que una hora de información.
3. **Destrabar E3-H1.** Es tu decisión: el dato es la lista de exclusiones de pares, y hace falta una reapertura acotada. Es la única prueba pendiente con valor informativo y su protocolo ya está congelado.
4. Para no perder lo ganado en detección: **P20 y P13** antes de cualquier refactor (P14, P15).

## 9. Acciones que requieren tu autorización explícita (categoría C)

Ninguna de estas se hizo. **Cada una es una autorización separada.**

| Acción | Para qué |
|---|---|
| Commit, push y PR de los parches 16–22 (y de 01–15, si no se integraron) | Integrar las correcciones |
| Cambiar `ev_evidence_policy` a `real_only` en `docker-compose.prod.yml` | P12; decidirlo junto con el presupuesto de exploración, porque una sesión nueva sin evidencia real no opera |
| Testnet de Binance para R25 (stop aceptado) y P16 (comisión en el activo base) | Verificar dos hipótesis que no se pueden probar en papel |
| Workflow de CI para la mutación periódica | P20 |
| Reabrir E3-H1 y obtener la lista de exclusiones | P18; las restricciones vigentes me impiden tocarlo |
| Cualquier operación con dinero real | **No se recomienda ni se solicita.** `validada_para_operar` no se tocó |
