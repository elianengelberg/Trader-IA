# Matriz de riesgos: cierre integral (2026-10-22)

Parte de la matriz de v3r3 (`MATRIZ_RIESGOS.md` de `25902649…`), que **no se modifica**. Agrega lo que esta misión verificó y nada más.

**Estados:**
- **Resuelto**: un parche lo cierra con evidencia, y solo si ese parche se integra.
- **Verificado localmente**: ejecutado aquí, no en la CI real ni en producción.
- **Pendiente**: sigue abierto.
- **Aceptado**: intencional, o de impacto despreciable, con su motivo.

Ningún riesgo se declara resuelto por inferencia. Donde una afirmación sale de leer el código y no de una ejecución, se indica «por inspección».

**Tipo de evidencia:**
- **L**: local, en esta máquina.
- **CI**: GitHub Actions real. **Ninguna** fila tiene evidencia CI: la CI real no corrió.
- **X**: externa (venue, testnet o entorno objetivo). **Ninguna** fila la tiene.

## Riesgos que esta misión cambió o agregó
| # | Riesgo | Severidad | Estado | Evidencia | Qué falta |
|---|---|---|---|---|---|
| **R7 / A7** | `ci.yml` nunca corrió en GitHub Actions | Media | **Pendiente** | L: las suites como la CI (Fase E), ruff, alembic y el gate 06v3 con 11 casos de prueba (`evidence/E_*`). CI: ninguna | Push autorizado y una corrida real en verde sobre el árbol esperado (`PLAN_INTEGRACION.md` §0). Las pruebas locales no la sustituyen |
| **A8** | Revisión humana del diff | — | **Pendiente** | L: revisión línea a línea hecha por el agente (`evidence/F_diferencias/REVISION_DIFERENCIAS.md`) | Una revisión humana |
| **R4c** | 02v3 sin 01 (o reversión parcial de A) declara 1.1.0 en un motor sin D1–D3 | Media | **Detectable técnicamente si se integra B (05v2)**; sigue **pendiente** hasta que lo vigile la CI real | L: guarda 05v2 en rojo, por la razón correcta, en N1, N2, N3, E1, E2, C2, L4 y L6 (`evidence/C_guarda/MATRIZ_MUTANTES_GUARDA.md`); robustez de v2 sobre 02v3 sin 01 (`evidence/C_guarda/robustez/v2/`); simulación de reversiones (`evidence/F_simulacion/`) | Git sigue permitiendo la combinación. La detección exige que la guarda corra (CI real, A7). Con 06v3, el gate exige 7/7 de la guarda cuando el motor declara ≥ 1.1.0 (`evidence/E_gate/`). El procedimiento de un único commit sigue vigente |
| **Gate de CI 06 v1 y 06v2** | 06 v1: `ruff check packages tests scripts` (el lint de su propia CI) fallaba con 5 errores. 06v2: si no podía importar el motor, dejaba de exigir la guarda (fallaba abierto) | Media | **Reemplazados por 06v3** (no integrar v1 ni v2) | L: `logs/E/E2_final_suite_gate.log` (ruff, 5 errores); `evidence/E_gate/corrida2_06v2_ANTES/` (10/11: aprueba un JUnit con la guarda omitida si corre con otro intérprete); `evidence/E_gate/corrida3_06v3_DESPUES/` (11/11); suite final 1985/1985 y gate pass con 06v3 | Que el gate corra en la CI real (A7) |
| **Guarda 05 v1** | Omitía en vez de fallar sin versión (B sin A, 02v3 revertido solo), no reconocía «1.1» y daba un falso positivo con un cierre límite reduce-only válido | Media | **Reemplazada por 05v2** (no integrar v1) | L: v1 da lo esperado en 20 de 26 casos (N2, N3 y L6 vivos, L7 omitido, C1 falso positivo); v2 en 25 de 26 (M7 fuera de alcance). Robustez de v1 y v2 sobre las mismas semillas | M7 (aviso del informe de una pierna sin stop) no es una regla de venue: lo cubre la prueba de 01, no la guarda |
| **R19** | Falla intermitente «persistence writes still in flight» en `test_partial_fills_and_fees_rebuild_identically_however_often` | Media | **NO_REPRODUCIDO**; sigue **pendiente** como riesgo de intermitencia | L: 0 de 252 corridas con el instrumento válido; con el bucle activo y K0, el vaciado tarda en mediana unos 7 s, con un máximo de 9,0 s y un **margen mínimo de unos 1 s** frente al límite de 10 s. Cota superior del IC 95 %: 16,8 % por celda y 3,0 % juntando las celdas (`docs/RESULTADOS_R19.md`) | Las fallas de R10 siguen sin explicación. Un runner más lento podría pasar de 10 s (inferencia, no observado). Faltan controles de detección y comunicación de la persistencia incompleta (propuestos en `RESULTADOS_R19.md`, no implementados) |
| **R15** | Guardado sin atomicidad: dos guardados simultáneos con el mismo `run_id` | **Baja → Media** (confirmado) | **Pendiente, CONFIRMADO en PostgreSQL 16** | L: en 50 intentos concurrentes, **32 aceptaron los dos** guardados (gana el último) y 18 rechazaron uno (`evidence/G_R24/R15_sonda_pg.*`) | Exige dos backtests simultáneos con el mismo id y distinto resultado. Arreglarlo cambia 02v3, que está congelado. Diseño propuesto: `INSERT … ON CONFLICT DO NOTHING`, después `SELECT … FOR UPDATE` y comparar. No implementado |
| **R24** | El almacén de backtest solo se había probado con SQLite | Baja | **Verificado localmente contra PostgreSQL 16.15** (almacén de backtest) | L: migraciones desde cero; las **14** pruebas de trazabilidad existentes contra PostgreSQL; el módulo 07: **4/4** (lectura desde otra conexión, NaN, guardado revertido, guardado rechazado); sin la variable se omiten y nunca caen a SQLite (`evidence/G_R24/`) | No es la CI ni la versión o configuración de producción. Cierre definitivo: 07 corriendo en la CI con un servicio PostgreSQL, o en el entorno objetivo. No cubre el resto de la persistencia (vivo, cuentas) |
| **R25 (nuevo)** | **Adaptador de Binance:** el stop protector del vivo (`OrderType.STOP`) no tiene traducción; el adaptador lo rechaza aunque declara `supports_stop_orders=True`. El vivo atrapa la excepción y sigue | **Alta (para el vivo)** | **Pendiente: defecto REPRODUCIDO en el adaptador**; no lo resuelve ningún parche | L: sonda sintética sin red (`evidence/G_binance/`): `ExecutionError` «not supported», con 0 pedidos al transporte, en la base y en el árbol final. Consecuencia en el vivo, **por inspección** (`live.py:3450-3466`): posición sin stop en el venue, informada solo como aviso de registro | Corrección propuesta, no implementada: mapear STOP a `STOP_LOSS` o usar `STOP_LOSS_LIMIT`, capacidades veraces, y que la falla del stop cuente como posición desprotegida. Requiere validación en testnet (X). **Bloquea el uso del vivo sobre Binance.** Es independiente de R19 y de la guarda 05 |
| **R26 (nuevo)** | El gate 06v3 registra `commit` y `tree` de `HEAD`: corrido fuera de la CI sobre cambios sin commit, `tree` no describe el contenido probado | Muy baja | **Aceptado** (alcance del gate) | L: en el árbol final sin commits, el gate informa el árbol de `72ffae5` | En la CI, el checkout es exactamente el commit. Localmente, el árbol del contenido se calcula aparte con `git write-tree` (`PLAN_INTEGRACION.md` §0) |

## Riesgos sin cambios de estado (revisados aquí)
| # | Riesgo | Severidad | Estado | Lo que se revisó en esta misión |
|---|---|---|---|---|
| R3 | Las capas 2 y 3 de D3 son propias del backtest; el vivo no las tiene igual | Baja | **Pendiente** (fuera de alcance) | Nada nuevo. La guarda 05v2 vigila el backtest y `PaperExecutionProvider`, **no** el vivo |
| R6 | Tolerancia del nivel de stop: relativa en el backtest, absoluta en el vivo | Muy baja | **Aceptado** | Por inspección: backtest `abs(Δ) <= 1e-9 * stop_price` (`engine.py:979-982` con A) y vivo `abs(Δ) <= 1e-9` (`live.py:3433`). Por debajo del tick para precios usuales |
| R17 | Mientras un cierre avanza por llenados parciales, el resto de la posición no tiene stop | Baja | **Pendiente** | Nada nuevo |
| R18 | Un cierre por señal invertida que se rechaza no se reintenta si la señal no vuelve | Baja | **Pendiente** | Por inspección: el vivo cierra con `_close_position("signal reversed")` solo en la barra en que llega la señal opuesta aprobada (`live.py:2062-2064`). Sin prueba de equivalencia |
| R21 | Una re-corrida legítima con otros números se rechaza | Baja | **Aceptado** | Se comprobó en PostgreSQL: el rechazo deja intacta la fila guardada y el almacén sigue usable (07, `test_a_refused_save_keeps_the_stored_row_and_the_store_usable`) |
| R22 / R23 / R14 | Huella del motor: despliegue en caliente, CRLF, comentarios | Muy baja / Baja | **Aceptados** (R22 pendiente-aceptado) | Nada nuevo |
| R8 | Sin firma digital ni ancla externa | Media | **Pendiente** (decisión del propietario) | Este paquete usa hashes SHA-256: prueban integridad, no autoría |
| R11 / R13 | Pruebas de reloj y persistencia | Media | **Resueltos por 03** (si se integra) | Reproducido de nuevo desde una extracción limpia (Fase E, paso 7 de `reproducir.sh`) |
| R12 | CI sin versiones fijadas | Media | **Pendiente**; 04 (opcional) lo resuelve | 04 y 06v3 aplican juntos; 06v3 fija también la evidencia de la corrida |
| Dinero real | — | — | **Bloqueado** | No se tocó `validada_para_operar`, la compuerta de activación ni ningún token; no se ejecutó trading (`evidence/registro/A3_*`, `evidence/registro/99_*`) |

## Lo que bloquea qué
- **Integrar A (+ B):** la CI real (A7), la revisión humana (A8) y el procedimiento de un único commit para A.
- **Uso productivo del almacén con concurrencia:** R15.
- **Uso del vivo:** R25 (Binance, bloqueante), R3, R17, R18 y los controles de persistencia de R19.
- **Dinero real:** sigue bloqueado por diseño. Nada de esta misión lo habilita.
