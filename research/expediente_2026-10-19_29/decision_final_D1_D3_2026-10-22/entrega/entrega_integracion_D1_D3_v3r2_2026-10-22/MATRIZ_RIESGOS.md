# Matriz de riesgos: resueltos y pendientes (v3)

**Estados:**
- **Resuelto:** cerrado por un parche de esta entrega, con evidencia. Solo vale si ese parche se integra.
- **Pendiente:** sigue abierto; se documenta y no se presenta como resuelto.
- **Aceptado:** comportamiento intencional o de impacto despreciable, con su motivo.

| # | Riesgo | Severidad | Estado | Evidencia / condición |
|---|---|---|---|---|
| R1 | Los resultados de backtest cambian al integrar 01 (es el arreglo) | Media | **Aceptado** | Con la API real, el mismo pedido da 13 operaciones con 72ffae5 y 12 con 01. Con 02v3 ambos quedan distinguidos por `run_id` y `engine_version` (`R5_*`) |
| R2 | La advertencia «no stop level» vuelve no confiables las corridas con piernas sin stop | Baja | **Aceptado** | Falla segura buscada |
| R3 | Las capas 2 y 3 de D3 son propias del backtest; `tia.runtime.live` no las tiene igual | Baja | **Pendiente** (fuera de alcance) | No se afirma equivalencia con el vivo |
| R4 | `run_id` sin motor ni datos, con upsert ciego | Media | **Resuelto por 02v3** | Reaparece si se integra 01 sin 02v3 (`C_run_id_*` de v2) |
| R4b | **Nuevo:** misma procedencia registrada y otros números → sobrescritura silenciosa en el **02 original** | Media | **Resuelto por 02v3** | `R1_*` (defecto), `R3_*` (corregido), `R2_*` (la prueba nueva falla con el 02 original), T13 |
| R5 | Con cierres IOC adversos cada reintento tarda 2 barras | Baja | **Aceptado** | Correcto pero lento |
| R6 | Tolerancia del nivel de stop: relativa en el backtest, absoluta en el vivo | Muy baja | **Aceptado** | Por debajo del tick |
| R7 | `ci.yml` de GitHub nunca corrió | Media | **Pendiente** | Ver informe §4: qué se reprodujo localmente y qué exige una corrida real |
| R8 | Sin firma digital ni ancla externa | Media | **Pendiente** (decisión del propietario) | Los hashes prueban integridad, no autoría |
| R9 | Frontend, migraciones, venue real | — | **Frontend y migraciones: verificados localmente** (`CI_frontend.txt`, `CI_alembic.txt`). **Venue real: pendiente, no verificado** | Los parches no tocan `frontend/` ni las migraciones |
| R11 | Dos pruebas de reloj fallan u omiten entre 00:00 y 05:55 UTC | Media | **Resuelto por 03** (si se integra) | `R9_*`; v2 `B3_*` |
| R12 | CI sin versiones fijadas: hoy resuelve `alembic` 1.20.1, `coverage` 7.17.0 y `python-dateutil` 3.0.0 en lugar de las fijadas | Media | **Pendiente**; el parche 04 (opcional) lo resuelve | `entorno/deriva_CI_libre_vs_restricciones.diff`. Con esas versiones, las suites pasan igual (`S_suite_*_CI_libre`) |
| R13 | Prueba de persistencia con límite de 10 s (carrera con el bucle de fondo) | Media | **Resuelto por 03** (si se integra) | v2 `B3_*`; `R10_*` |
| R14 | Huella del motor conservadora: un comentario cambia el `run_id` | Baja | **Aceptado** | Un id nuevo no borra nada; nunca mezcla motores |
| R15 | El guardado lee y después hace upsert, sin atomicidad: dos guardados simultáneos con el mismo `run_id` podrían cruzarse (ahora también vale para el control de números) | Muy baja | **Pendiente (no resuelto)** | Exige dos backtests simultáneos con el mismo id y distinto resultado. Arreglarlo requiere una transacción con bloqueo, fuera de lo mínimo |
| R16 | Filas viejas con motor desconocido | — | **Tratado** | Intactas, `engine_version` = null, legibles por la API vieja y la nueva (`R5_*`). No comparables sin procedencia externa |
| R17 | Mientras un cierre trabaja por llenados parciales, el resto de la posición no tiene stop | Baja | **Pendiente (no resuelto)** | Es la regla de la sesión (ningún stop sobre un cierre en curso). En el escenario de estrés se observaron más de 7 barras |
| R18 | Un cierre por señal invertida que se rechaza no se reintenta si la señal no vuelve | Baja | **Pendiente (no resuelto)** | La pierna queda protegida por su stop (`d1_stop`). Por inspección el vivo sigue el mismo patrón (`live.py:2064`), **sin prueba de equivalencia** |
| R19 | Otras pruebas llaman a `start()` y hacen ciclos a mano con el bucle de fondo girando (34 llamadas en 4 módulos) | **Media (subió)** | **Pendiente (no resuelto)** | **Se materializó hoy:** con carga de CPU ≈5, `test_partial_fills_and_fees_rebuild_identically_however_often` falló en la base (2 de 4) y en la integración (1 de 4); con carga ≤2,5 pasó siempre (`R10_*`). Es preexistente, no lo introduce ningún parche. Seguimiento: el mismo `_drive_by_hand` en esas pruebas |
| R20 | Un conflicto de guardado sale como HTTP 400, no 409 | Muy baja | **Aceptado** | Mapeo existente de `ValueError` |
| R21 | **Nuevo (efecto de 02v3):** una re-corrida legítima después de un cambio de entorno que cambie números se rechaza hasta borrar o renombrar a mano | Baja | **Aceptado** | Falla ruidosa en lugar de sobrescritura silenciosa |
| R22 | **Nuevo:** la huella se calcula sobre los archivos en disco al primer uso; con un despliegue en caliente sin reinicio podría no corresponder al código cargado | Muy baja | **Pendiente (aceptado)** | Mitigado por el control de números de 02v3 |
| R23 | **Nuevo:** CRLF (Windows) cambia la huella y da otro `run_id` para el mismo código | Muy baja | **Aceptado** | Conservador: nunca mezcla |
| R24 | **Nuevo:** el guardado se probó solo contra SQLite, no contra PostgreSQL | Baja | **Pendiente** | El código no depende del dialecto (`session.get` y el upsert existente), pero no se ejecutó contra PostgreSQL |
| R-M10 | `reduce_only` del cierre no se distingue por comportamiento en los escenarios | Muy baja | **Aceptado** | M10 se detecta solo por la cobertura de los escenarios |
| Obs. | Los stops protectores no son reduce-only (desde la base) | — | **Fuera de alcance** | No alcanzable con el motor actual: el stop se cancela antes del cierre |
