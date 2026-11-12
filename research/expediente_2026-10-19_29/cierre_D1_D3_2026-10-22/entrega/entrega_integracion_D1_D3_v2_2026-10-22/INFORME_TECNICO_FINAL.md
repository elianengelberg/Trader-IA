# Informe técnico final — cierre D1–D3: reproducibilidad, trazabilidad e integración controlada (v2)

**Fecha:** 2026-10-22. **Base:** `72ffae5d2698440c8f1afaff12e07bd8adde66fb`.
**Alcance:** revisión técnica del motor de backtest y de sus pruebas. **No es** una validación de rentabilidad. Ningún número de este informe dice nada sobre resultados futuros.
**Nada se publicó ni se operó:**
- sin commits ni push;
- sin ramas remotas ni PR;
- sin despliegue;
- sin cambios en el repositorio original;
- sin dinero real.

## 1. Identidad de lo entregado
| Elemento | Valor |
|---|---|
| Base | `72ffae5d2698440c8f1afaff12e07bd8adde66fb`; `engine.py` `547109460bb5…`, `paper.py` `f5e0cb87a98d…` |
| Parche 01 (obligatorio) | D1–D3 en `engine.py` y `paper.py`, idénticos a la entrega anterior (`85965ec5…`, `05569d16…`), más las pruebas definitivas v3 (`3900d626…`, 8 pruebas) |
| Parche 02 (obligatorio, sobre 01) | Trazabilidad: `engine.py`, `result.py`, `repositories.py`, `api/state.py`, `docs/ARCHITECTURE.md`, prueba nueva `test_backtest_provenance.py` (`e07e701f…`, 12 pruebas) |
| Parche 03 (opcional) | Solo pruebas: `test_account_restore.py`, `test_risk_state_persistence.py`, `test_adverse_recovery.py` |
| Árbol obligatorio (01+02) | `engine.py` `47ec09060a69…`; ver `parches/SHA256_archivos_resultantes_obligatoria.txt` |
| Entrega anterior | `entrega_integracion_D1_D3_2026-10-22.zip` `f9495ad8…`: **no se modificó ni se reutilizó su hash** |

Los tres parches aplican limpio, en cadena, sobre una copia nueva de `72ffae5`. El resultado es idéntico byte a byte al árbol verificado (`evidencia/F_parches_aplicacion.txt`).

## 2. Fase A — integridad de la entrega anterior (`registro/01`–`03`)
- **ZIP:** `f9495ad8…`, 245.099 bytes, 63 entradas.
  - Las 62 sumas internas verifican.
  - Único contenido duplicado: `E17_ci` = `E17_e1`, esperado (misma salida en dos entornos).
- **Secretos:** no hay. Las rutas absolutas aparecen solo en registros históricos, no en herramientas ni en el parche.
- **Extracción en un directorio vacío:** correcta.
- **Parche:** coincide con los blobs de `72ffae5` y `git apply --check` sale limpio.
- **Defectos encontrados en la entrega anterior** (se corrigen en esta v2, sin tocar la anterior):
  - **dependencias sin fijar**: la CI resuelve versiones nuevas en cada instalación;
  - **`reproducir.sh` heredaba variables del entorno**: no limpiaba `PYTHONPATH` ni `PIP_CONSTRAINT`.

## 3. Fase B — reproducibilidad

### B1. Entorno
- **Restricciones:** `entorno/ci-py311.txt`, con 74 paquetes fijados (sha `b0f6791d…`).
  - Se aplicaron solo en copias aisladas; el repositorio no se tocó.
  - Uso: `pip install -c ci-py311.txt -e ".[api,db,postgres,redis,llm,dev]"`, el comando de `ci.yml`.
- **Dos entornos independientes** (`venv_A`, `venv_B`): `pip freeze` idéntico (`dd036ddd…`).
- **Un tercer entorno** con `time-machine 3.5.1`, solo para fijar el reloj de pared.
- **Inventario completo:** `registro/04_inventario_entorno.txt`.

### B2. Suites completas en entornos equivalentes (corridas simultáneas, 2026-10-22)
- **Corridas simultáneas:** comenzaron las tres a las 13:14:49Z. El comando es el de la CI (`pytest tests -q`), con un informe JUnit para contar resultados exactos (`herramientas/correr_suite_ci.sh`).
- **Entornos:** `venv_A` y `venv_B` tienen el mismo `pip freeze`.

| Árbol | Entorno | Pruebas | Pasan | Fallan | Errores (incl. colección) | Omitidas | Código de salida | Duración (JUnit) |
|---|---|---|---|---|---|---|---|---|
| Base `72ffae5` | venv_A | 1956 | 1956 | 0 | 0 | 0 | 0 | 321,7 s |
| Obligatoria (01+02) | venv_B | 1976 | 1976 | 0 | 0 | 0 | 0 | 365,8 s |
| Completa (01+02+03) | venv_A | 1976 | 1976 | 0 | 0 | 0 | 0 | 363,2 s |

- **Prueba a prueba** (`herramientas/comparar_suites_v2.py`; `evidencia/F_comparacion_*`):
  - no falta ninguna prueba de la base;
  - las **20 nuevas** (8 de D1–D3 y 12 de trazabilidad) pasan;
  - ninguna prueba de la base cambia de resultado;
  - en la completa, las 3 sensibles al entorno pasan.
  - Veredicto del comparador: «SIN REGRESIONES FRENTE A LA BASE» en ambos casos.
- **Fallas de infraestructura:** ninguna en esta corrida.
- **Fallas preexistentes:** son las 3 sensibles al entorno de B3. **En esta corrida pasaron en la base**, y eso no prueba que estén sanas:
  - las de reloj pasan después de las 05:55 UTC y la corrida fue a las 13:14Z;
  - la de persistencia ganó la carrera (4,48 s).
  - En otros contextos de hoy la misma prueba de la base falló (B3; `evidencia/B3_contexto_suite.txt`).
- **Corridas históricas** (entrega anterior, `E7`–`E9`, `E20`–`E25`):
  - base 1956/1956 e integración 1962/1962 fuera de la franja horaria y con la carrera a favor;
  - con las mismas 3 pruebas fallando u omitidas en otras horas o máquinas.
  - Las corridas de hoy son las más recientes y no reemplazan a las históricas: ambas constan.

### B3. Pruebas sensibles al entorno: causa, corrección y evidencia
Las hipótesis anteriores se trataron como no verificadas. Resultado:
- **la ventana horaria era aproximada**: el límite exacto es 05:55, no ≈05:45;
- **«contenedor lento» era falsa**: la causa es otra.

**1. Las dos pruebas de reloj**
- **Pruebas:**
  - `test_five_restored_entries_for_the_symbol_refuse_the_sixth_after_the_restart`;
  - `test_a_day_that_hit_the_loss_limit_still_refuses_entries_after_a_restart`.
- **Causa, verificada por código y aritmética:**
  - La serie de velas falsas empieza en `ahora − (500 + 5) min`.
  - El reloj simulado de la sesión abre en la vela 150, o sea en `ahora − 355 min` (≈ 5 h 55 m antes que el reloj de pared).
  - El día restaurado se toma del reloj de pared (`datetime.now(UTC).date()`).
  - Entre las 00:00 y las 05:55 UTC el día de la sesión es el de ayer: lo restaurado es «de mañana» para la sesión y el límite nunca habla.
  - En la otra prueba se omite por un `pytest.skip`.
- **Evidencia** (`evidencia/B3_verificacion_reloj_y_persistencia.txt`), con time-machine:

| Hora de pared fijada (UTC) | 00:30 | 02:30 | 05:30 | 05:50 | 05:56 | 12:00 | 18:00 | 23:59 | real |
|---|---|---|---|---|---|---|---|---|---|
| Base | 1 falla, 1 omitida | 1 falla, 1 omitida | 1 falla, 1 omitida | 1 falla, 1 omitida | 2 pasan | 2 pasan | 2 pasan | 2 pasan | 2 pasan |
| Con el parche 03 | 2 pasan | 2 pasan | 2 pasan | 2 pasan | 2 pasan | 2 pasan | 2 pasan | 2 pasan | 2 pasan |

- **Corrección mínima (solo pruebas):**
  - un parámetro opcional `start` en los ayudantes `build` y `build_runtime_paper_with` (por defecto, el comportamiento de siempre);
  - un ancla fija `SESSION_DAY_START = 2026-01-05 06:00 UTC`: la sesión abre a las 08:30:01 con el resto del día por delante;
  - el día restaurado y `now`/`t0` salen del reloj de la sesión.
- **Sin relajar nada:**
  - ningún tiempo límite cambió ni se relajó ninguna aserción;
  - los dos `pytest.skip` pasaron a ser aserciones;
  - se agregaron dos aserciones nuevas: «la sesión reiniciada lee el mismo reloj» y «el recorrido se quedó dentro del día restaurado»;
  - se quitó una aserción vacía (`… or True`).

**2. La prueba de persistencia con límite de 10 s** (`test_rejects_and_partials_over_hundreds_of_bars_keep_the_invariants_and_the_record_whole`)
- **Hipótesis descartadas por evidencia:**
  - *Disco:* en tmpfs también falla, 2 de 3 (`evidencia/B3_persistencia_disco_vs_tmpfs.txt`).
  - *Contenedor lento:* no explica 49.000 escrituras.
- **Causa, verificada con sondas que solo miden** (`herramientas/sonda_persistencia.py`, `sonda_ciclos.py`):
  - `runtime.start()` crea la tarea del bucle propio de la sesión (`live.py:1266`). La prueba hace además sus 500 ciclos a mano.
  - Con el intervalo de sondeo 0 de los ayudantes, ese bucle gira en paralelo: **462.525 ciclos de fondo frente a 500 manuales**.
  - Cada 12 ciclos, una escritura de reconciliación: **49.362 escrituras**.
  - Las escrituras reales (orden, llenado, evento) tardaban ≈115 ms de reloj cada una, porque el bucle acapara el event loop.
  - `flush_persistence` espera también las escrituras programadas mientras espera, y con un productor que no para no puede vaciarse a tiempo.
  - En la corrida instrumentada, la sexta espera entró con 63 pendientes y salió a los 10,007 s con **4.471** pendientes.
  - Pasar o fallar depende de cómo se intercalan el bucle y el hilo de escritura de aiosqlite. La competencia por el GIL es una hipótesis compatible con la evidencia, **no verificada**: sin el bucle, cada escritura tarda ≈2 ms; con él, ≈115 ms.
  - La magnitud varía por corrida y contexto; el mecanismo es siempre el mismo (`evidencia/B3_contexto_suite.txt`, `B3_verificacion_*`):

| Contexto (base) | Resultado | Duración | Ciclos de fondo | Espera máx. |
|---|---|---|---|---|
| Aislada (6 corridas alternadas) | 5 pasan, 1 falla | 25,8–31,2 s | — | — |
| Aislada, instrumentada | pasa | 24,1 s | 511.275 | 7,4 s |
| Su módulo (2 pruebas) | falla | 23,8 s | 597.066 | 10,0 s |
| `tests/integration` entera | falla | 17,7 s | 1.535.778 | 10,0 s |
| `tests/e2e` + la prueba (hipótesis «configuración global de e2e»: refutada) | pasa | 27,7 s | 571.923 | 9,4 s |
| Suite completa de hoy, en paralelo con otras dos | pasa | 4,5 s | — | — |

  - Esto explica las observaciones anteriores (4–7 s en algunas suites, 16–57 s en otras) sin recurrir a «un contenedor lento».
- **Alcance:**
  - Es un defecto **de la prueba**, no del producto. En producción `flush_persistence` se llama solo después de cancelar el bucle (`live.py:1288`, `engine.py:529`), y el intervalo de sondeo real es de 5 s.
- **Corrección mínima (solo la prueba):**
  - Después de `start()`, la prueba cancela el bucle de fondo con `_drive_by_hand`, porque ella misma conduce los ciclos.
  - Se agregó la aserción `runtime.counters["cycles"] == 500`, que detecta un segundo conductor.
- **Resultado** (`evidencia/B3_sonda_corregida.json`, `B3_ciclos_corregida.json`):

| | Base | Con el parche 03 |
|---|---|---|
| Ciclos de fondo | 462.525 | 0 |
| Escrituras | 49.496 | 188 |
| Espera de vaciado más larga | 10,007 s (timeout) | 0,104 s |
| Duración | 25–31 s | 3,2–3,8 s |
| Corridas alternadas | 5 de 6 pasan | 6 de 6 pasan |

- **Patrón latente** (riesgo R19): otras pruebas también llaman a `start()` y después hacen ciclos a mano con el bucle girando (`test_account_restore`, `test_funding_*`). En las corridas de hoy pasaron todas, pero no se midió su holgura una por una. No se tocaron: no fallaron, y cambiarlas excede el mínimo.

## 4. Fase C — trazabilidad (prioritaria)

### Defecto (R4), demostrado sobre el original (`evidencia/C_run_id_*.json`)
- **Fórmula:** `run_id = deterministic_id("bt", dataset, símbolo, cfg.digest())`. No incluye el motor ni los datos, y `BacktestRepository.save` hace upsert por `run_id`.
- **Caso medido (fixtures BTC-USD 1h):**
  - la base (8 operaciones, −0,1349 %) y el motor con D1–D3 (9 operaciones, −0,1161 %) dan **el mismo** `bt_DJZPATCEBZ0B0DP393XP3W1D`;
  - 400 y 350 barras del mismo dataset también lo comparten.
- **Consecuencia:** re-correr un backtest guardado reemplazaba en silencio el resultado viejo, y la API lo hacía con cualquier `bars`.

### Corrección (parche 02)
- **`ENGINE_VERSION = "1.1.0"`** en `backtest/engine.py`.
  - Se sube a mano ante cualquier cambio que altere resultados.
  - Su comentario dice que antes no se registraba ninguna versión.
- **`engine_fingerprint()`:** SHA-256 de todos los `.py` de los subpaquetes que deciden un backtest (`backtest, core, data, domain, economics, execution, quant, regime, risk, strategy`).
  - Es conservadora: un comentario editado también la cambia.
  - Si no hay fuentes legibles dice `unavailable`; no inventa un valor.
- **`data_fingerprint(bars)`:** SHA-256 de las velas consumidas.
- **`universe_digest`:** huella de los instrumentos.
- **Registro:** las cuatro van a `BacktestConditions` (campos nuevos con valor por defecto `""` = desconocido).
- **Nuevo `run_id`:** a las cuatro se suman el conjunto de estrategias, `liquidate_at_end` y `is_out_of_sample`. Antes, con otro conjunto de estrategias, el `run_id` coincidía.
- **`BacktestRepository.save`:**
  - Reemplaza una fila solo si tiene la **misma procedencia** (una re-corrida del mismo motor sobre los mismos datos).
  - Si no, levanta `ValueError` con la procedencia guardada; la API lo devuelve como 400.
  - Nunca sobrescribe una fila vieja ni de otro motor.
- **`GET /api/backtests`:** agrega `engine_version`, que vale `null` para las filas viejas.
- **Sin migración:** los campos viven en la columna JSON `conditions`, que ya existe. Sin cambio de esquema; reversible con `git revert`.
- **Los números no cambian:** la paridad con E1 (§6) da las mismas huellas de operaciones, equity, métricas y decisiones antes y después del parche 02. Solo cambia el `run_id`.

### Pruebas (`tests/integration/test_backtest_provenance.py`, 12)
- **Qué registran y qué cambia el id:**
  - el resultado registra motor, datos e instrumentos;
  - otra versión, una huella de código distinta, otros datos con el mismo nombre (menos barras o una vela tocada) y otro conjunto de estrategias dan otro `run_id`;
  - el mismo motor sobre los mismos datos da las mismas condiciones.
- **Huella del motor:** sigue al código del motor (cambia con un comentario en `execution/paper.py`, no con uno en `api/state.py`) y dice `unavailable` sin fuentes.
- **Base de datos (SQLite real):**
  - una fila **escrita exactamente como la escribía `72ffae5`** convive con la nueva y queda byte a byte igual, sin campos de procedencia;
  - el guardado rechaza reemplazar una fila de otra procedencia, en ambos sentidos;
  - una re-corrida idéntica se reemplaza solo a sí misma.
  - La fórmula vieja del `run_id` usada en la prueba coincide con la que produce el motor base real (`evidencia/C_run_id_base.json`).
- **API real (ASGI y base de datos):** lista `engine_version` = `null` para la fila vieja, con su número intacto, y `1.1.0` para la nueva.
- **Mutantes:** 12. Detectados 11 de 11 no equivalentes; 1 equivalente justificado (T10). Ver `MATRIZ_MUTANTES.md`.

### Registros históricos con versión desconocida
- No se les asigna versión, ni siquiera «1.0.0», porque nadie registró con qué código se calcularon.
- Quedan intactos y legibles.
- No son comparables con resultados versionados salvo que su procedencia se reconstruya por fuera, con fecha y commit desplegado.
- **E1 no se regeneró.**

## 5. Fase D — D1–D3

### Pruebas definitivas (`tests/unit/test_backtest_order_hygiene.py` v3, 8 pruebas)
- **Instrumentación:** un `_Instrumented(BacktestEngine)` verifica invariantes en cada barra:
  - `d1_stop`: más de 8 barras con pierna y sin stop vivo;
  - `d1_exit`: un cierre pedido que **no llegó a la venue** (suprimido como duplicado), cualquiera sea su razón; y un stop por tiempo que no cierra nada durante más de 8 barras (el progreso por llenados parciales cuenta);
  - `d2`: el stop del libro no está al nivel de la pierna;
  - `d2_churn` (nueva): un stop vivo reemplazado sin cambio de tamaño ni de nivel;
  - `d3`: la posición de la venue no es la pierna que sigue el motor;
  - `d3_flipped` (nueva): la venue en el lado contrario a la pierna;
  - `d3_stuck`: la pierna espera un cierre que ya terminó;
  - `d3_added`: algo se sumó a la posición después de pedir el cierre;
  - `d3_reopened`: una señal cerrada reaparece.
- **Escenarios:**
  - rechazos al 20 %;
  - el primer cierre de cada salida rechazado;
  - movimientos de break-even y trailing;
  - **sin recolocaciones innecesarias** (nueva, en calma y con rechazos y parciales);
  - parciales al 90 %;
  - cierres IOC con posición restante;
  - pierna sin nivel de stop;
  - **combinado** (nueva): cada cierre rechazado dos veces, 30 % de rechazos, 60 % de parciales y entradas límite que expiran, en dos corridas:
    - una con stops por tiempo;
    - otra con una estrategia de tendencia de stop amplio que produce cierres por **señal invertida**.
- **Resultados:** contra el motor de `72ffae5` fallan **8 de 8, todas por `AssertionError`**; contra el parche 01 y contra el árbol obligatorio pasan **8 de 8**.

### Dos hallazgos de esta fase, explicados y no ocultos
1. **Un cierre que trabaja por parciales puede tardar más de 8 barras sin estar trabado.**
   - Traza de `herramientas/sonda_salida_lenta.py`: el cierre por tiempo fue rechazado 4 veces y después se llenó en parciales decrecientes (0,112 → 0,000155) durante más de 7 barras.
   - La invariante original medía desde el primer pedido y lo marcaba como falla.
   - Se redefinió como «nada cerrado durante más de 8 barras». Con llenados enteros es idéntica a la anterior.
   - Mientras el cierre trabaja, el resto no tiene stop: es la regla de la sesión, «ningún stop sobre un cierre en curso» (riesgo R17).
2. **Un cierre por señal invertida que se rechaza no se reintenta si la señal no vuelve.**
   - La pierna sigue abierta y protegida por su stop: `d1_stop` lo verifica.
   - Es semántica, no D1–D3: la salida se pide solo en la barra en que aparece la señal opuesta aprobada.
   - Por inspección, la sesión en vivo sigue el mismo patrón (`live.py:2064`), pero **no hay prueba específica de equivalencia** (riesgo R18).
   - Por eso la vivacidad «con progreso» se exige solo al stop por tiempo, la única salida que persiste por construcción. La supresión por id duplicado se exige a todas.

### Mutantes con exactamente el archivo final (`MATRIZ_MUTANTES.md`)
- Son 10:
  - M1–M8, cada pieza del parche revertida;
  - M9, recolocar en cada barra;
  - M10, cierre sin `reduce_only`.
- **0 vivos.** Cada mutante lleva su defecto, las pruebas que lo detectan, la aserción responsable, el resultado con el motor original y el resultado con la integración.
- **M10 cae por las aserciones de cobertura de los escenarios**, no por una invariante de comportamiento: `reduce_only` es una defensa que estos escenarios no distinguen (R-M10).

### Garantías del backtest frente a `tia.runtime.live`
- **Probado aquí (por comportamiento):** solo el motor de backtest.
- **`tia.runtime.live`:** no se modificó y **no se afirma equivalencia**.
  - Los comentarios del motor dicen que D1 y D2 copian la regla de la sesión (`same_level`, un id por intento). Eso es inspección de código, no una prueba.
  - Las capas 2 y 3 de D3 son propias del backtest.

## 6. Fase E — paridad con E1 (`evidencia/E_paridad_clasificada.md`)
- **Cómo se corrió:**
  - el `BacktestEngine` integrado, **sin subclases**;
  - la configuración, el universo y el escenario de E1, construidos por **el mismo `e1_comun.py` de la corrida evaluada de E1** (`b61cab57…`, huella de su adenda 2);
  - las 58.402 velas BTCUSDT 1h de E1, leídas de sus 96 archivos verificados contra `.CHECKSUM`.
- **Dos entornos:** CI (pydantic 2.14.1) y E1 (pydantic 2.13.5, sus requisitos con hash).
- **No es un experimento:** no se calculó ninguna métrica de decisión nueva y E1 no se regeneró.

| Comparación (cada una para P1, P2, P3 y S1) | Resultado |
|---|---|
| Huella de los datos de entrada (lista de archivos `4931ee70…`, 58.402 velas, extremos, huecos, horas excluidas) | **Igualdad verificada** |
| Round trips completos: marcas de tiempo, dirección, nocional, neto, bruto, **comisiones**, barras, razón, confianza, régimen, piezas (629, 139, 185 y 795), en ambos entornos | **Igualdad verificada** (JSON idéntico) |
| Métricas de la curva **registradas por E1** (retorno total y anualizado, volatilidad, Sharpe, Sortino, drawdown máximo, exposición), en ambos entornos | **Igualdad verificada**: 7 de 7, igualdad exacta de float. **Nuevo:** la entrega anterior no lo había comparado |
| Contadores de decisiones y señales **registrados por E1** (señales, intenciones, llenados, rechazos, stops sin colocar, ajustes de stop, salidas pedidas, rechazos de presupuesto), en ambos entornos | **Igualdad verificada**: 8 de 8. **Nuevo** |
| Registro completo de decisiones por barra, curva punto a punto y detalle de cada operación frente a E1 | **Imposible de verificar por falta de referencia**: E1 no los registró |
| Esas salidas completas entre los dos entornos de hoy y frente a la integración anterior (E17, copiada en `evidencia/referencias_entrega_anterior/`) | **Igualdad verificada**: la trazabilidad no cambió ningún número |
| Parámetros efectivos | **Igualdad verificada** por identidad del código que los construye; ningún parche toca `BacktestConfig` |
| Huella del motor | **Diferencia explicada**: E1 usó `MotorE1`, una subclase con sus propias correcciones, sobre el `engine.py` de `72ffae5`; hoy corre el motor integrado sin subclases. E1 no registró una huella de motor |
| Versiones de dependencias | **Igualdad verificada** en el entorno E1; **diferencia explicada** en el de la CI (pydantic 2.14.1 frente a 2.13.5), con salidas idénticas |

**Totales:** 45 igualdades verificadas, 5 diferencias explicadas, 4 imposibles por falta de referencia, **0 diferencias no explicadas**.

## 7. Fase F — integración final aislada
- **Archivos modificados:** `parches/ARCHIVOS_MODIFICADOS.txt`.
  - Obligatorios: 5 de producción, 1 de documentación y 2 pruebas nuevas.
  - Opcional: 3 pruebas.
- **Diff revisable:** `parches/*.patch`.
- **Verificaciones (todas ejecutadas en esta sesión):**
  - `ruff check packages tests scripts` limpio en los árboles obligatorio y completo;
  - suites completas (§3, B2);
  - pruebas D1–D3 (8/8) y de trazabilidad (12/12);
  - mutantes, con 0 vivos;
  - persistencia y coexistencia (§4);
  - reproducción desde una extracción limpia del ZIP nuevo. Se hace **después** de cerrarlo, así que su resultado no puede estar dentro: queda en el registro externo `VERIFICACION_EXTRACCION_LIMPIA_v2.txt`, junto al ZIP;
  - archivos congelados sin cambios (`registro/99`);
  - repositorio original intacto (`registro/00` y `99`).
- **No se afirma que la CI de GitHub esté en verde:** nunca corrió.

## 8. Riesgos residuales
| # | Riesgo | Severidad | Estado |
|---|---|---|---|
| R1 | Los resultados de backtest cambian al integrar 01 (es el arreglo) | Media | Esperado. Con 02, quedan distinguidos por `engine_version` |
| R2 | La advertencia «no stop level» puede volver no confiables corridas con piernas realmente sin stop | Baja | Comportamiento buscado |
| R3 | Las capas 2 y 3 de D3 son propias del backtest | Baja | Probadas por comportamiento. El vivo no se tocó |
| R4 | `run_id` sin motor ni datos, con upsert ciego | — | **Resuelto por 02.** Reaparece si se integra 01 sin 02 |
| R5 | Con cierres IOC adversos cada reintento tarda 2 barras | Baja | Correcto pero lento |
| R6 | Tolerancia del nivel de stop: relativa en el backtest, absoluta en el vivo | Muy baja | Por debajo del tick |
| R7 | `ci.yml` de GitHub nunca corrió | Media | El primer PR es su primera corrida (A7) |
| R8 | Sin firma digital ni ancla externa: los hashes prueban integridad, no autoría | Media | Declarado (§10) |
| R9 | **No verificado:** frontend, migraciones `alembic`, sesión en vivo contra una venue real | — | Los parches no los tocan, pero no se ejecutaron |
| R11/R13 | Pruebas de reloj y de persistencia | — | **Resueltas por 03, opcional.** Sin 03 siguen intermitentes (§3, B3) |
| R12 | CI sin versiones fijadas | Media | Restricciones entregadas; aplicarlas a `ci.yml` es tu decisión |
| R14 | La huella del motor es conservadora: un comentario cambia el `run_id`. Una instalación sin `.py` da `unavailable` | Baja | Elegido: nunca confunde motores. Un id nuevo no borra nada |
| R15 | El guardado lee y después hace upsert, sin atomicidad: dos guardados simultáneos con el mismo `run_id` y distinta procedencia podrían cruzarse | Muy baja | Requiere colisión de hash o una inserción manual |
| R16 | Filas viejas con motor desconocido | — | Intactas, `engine_version` = `null`. No comparables sin procedencia externa |
| R17 | Mientras un cierre trabaja por parciales, el resto de la posición no tiene stop | Baja | Regla de la sesión (ningún stop sobre un cierre en curso). Observado durante más de 7 barras en el escenario de estrés |
| R18 | Un cierre por señal invertida que se rechaza no se reintenta si la señal no vuelve | Baja | La pierna queda protegida por su stop. El vivo, igual por inspección, sin prueba de equivalencia |
| R-M10 | `reduce_only` del cierre no es distinguible por comportamiento en estos escenarios | Muy baja | Mutante detectado solo por cobertura |
| R19 | Otras pruebas llaman a `start()` y después hacen ciclos a mano con el bucle de fondo girando: mismo mecanismo, con menos escrituras | Baja | Pasaron en todas las corridas de hoy, pero **no se midió su holgura una por una**. Seguimiento propuesto: el mismo `_drive_by_hand` |
| R20 | Un conflicto de procedencia sale como HTTP 400, no 409 | Muy baja | Mapeo existente de `ValueError` |

## 9. Seguridad
- No se operó con dinero real ni se habilitó operación real.
- No se desplegó ni se reinició nada; no se tocó infraestructura.
- Sin commits, push, ramas remotas ni PR.
- El repositorio original no se modificó: mismo HEAD, índice, refs, reflog, stash y árbol (`registro/00` y `99`).
- `validada_para_operar` y las condiciones de autorización no se tocaron.
- T-MULTI, T-papel, E3-H1 y E1 verifican contra sus manifiestos (`registro/99`).
- No se borró ni se sobrescribió ninguna entrega anterior, resultado fallido ni evidencia.
- Los datos de E1 se **leyeron** de su ubicación ignorada por git, sin copiarlos a la entrega.

## 10. Integridad y autenticidad
- `SHA256SUMS`, dentro del ZIP, cubre cada archivo de la entrega.
- El hash del ZIP va en un archivo externo, `entrega_integracion_D1_D3_v2_2026-10-22.zip.sha256`.
- **No hay firma digital.** Un hash prueba que los bytes no cambiaron respecto de un valor conocido, no quién los produjo. La autenticidad descansa en que recibas el hash por un canal en el que confíes.

## 11. Cómo repetir todo
Ver `COMANDOS_DE_VERIFICACION.md` y `reproducir.sh`.
