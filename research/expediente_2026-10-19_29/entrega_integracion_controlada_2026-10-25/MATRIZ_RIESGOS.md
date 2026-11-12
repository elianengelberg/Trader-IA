# Matriz de riesgos: integración controlada (2026-10-25)

**Árbol candidato:** `17332e1c510d0004f7744bde0a68f008f01652b7`.

No modifica las matrices anteriores; las retoma: cierre integral `MATRIZ_RIESGOS.md` y revisión adversaria §6.

## Estados

- **CORREGIDO_Y_VERIFICADO:** hay un parche, y una prueba que fallaba sin él y pasa con él, ejecutada aquí.
- **CORREGIDO_PARCIALMENTE:** parche y pruebas locales, pero falta una verificación necesaria (testnet, CI real).
- **NO_REPRODUCIDO:** no se pudo provocar.
- **PENDIENTE:** sigue abierto. Incluye los riesgos aceptados y los que esperan una decisión.
- **BLOQUEANTE:** impide el uso indicado.

## Tipo de evidencia

| Sigla | Qué es |
|---|---|
| **L** | Local, en esta máquina |
| **PG** | PostgreSQL 16.15 real y desechable |
| **SIM** | Simulación en papel (`SIMULACION_INTEGRAL.md`) |
| **T** | Testnet: **ninguna fila la tiene** |
| **CI** | GitHub Actions: **ninguna fila la tiene** |
| **INS** | Por inspección del código, sin ejecución |

## 1. Riesgos del encargo

| Riesgo | Descripción | Severidad | Estado | Parche | Evidencia | Qué falta |
|---|---|---|---|---|---|---|
| **P0 / R25** | El stop protector del vivo (`OrderType.STOP`) no tenía traducción en el adaptador de Binance: cada posición quedaba sin stop y la sesión seguía | Alta (vivo) | **CORREGIDO_PARCIALMENTE**. **BLOQUEANTE** para el vivo con Binance | 08 | L: STOP → `STOP_LOSS` (stopPrice, sin price ni timeInForce); un stop mal formado se rechaza antes de enviar; un stop adoptado del venue se lee como stop; la compuerta de activación **falla** sin un registro de testnet `protective_stop_accepted: true`; `validate_binance.py --stop` exige `--testnet`. 18 de las 25 pruebas nuevas de R25 y R18 fallaban sin el arreglo y pasan las 25 con él (`logs/D0_*`, `logs/D1_*`). SIM E04b: con un venue que rechaza stops, la posición cuenta como desprotegida, se bloquean las entradas, `HALT_NEW_ORDERS` y el incidente queda guardado (base: no cumple; candidato: cumple) | **T:** correr `scripts/validate_binance.py --account --order --stop --testnet` con credenciales **de testnet**. No se simuló una respuesta de Binance como evidencia de compatibilidad |
| **R18** | Ventana sin protección: un cierre rechazado (y también un fill de entrada o un reinicio) dejaba una barra sin stop | Media | **CORREGIDO_Y_VERIFICADO** (papel y backtest) | 08 y 13 | L, tolerancia **0** medida en el emparejamiento: backtest (`test_backtest_protection_window.py`, 4 escenarios con rechazos reales); vivo (`test_live_position_protection.py`). SIM E08: protegida en la misma llamada, ninguna barra sin stop (base no cumple). SIM E13: posición restaurada protegida **antes** de su primera barra (base no cumple) | Con Binance, depende de R25 (testnet) |
| **R15** | Guardado de backtest sin atomicidad: dos escritores del mismo `run_id`, y un escritor descartado recibe éxito | Media | **CORREGIDO_Y_VERIFICADO** | 09 | **PG:** 880 intentos por árbol (2 semillas × 440). Éxitos dados a un escritor descartado: **base 266, candidato 0**. Celdas con ambos aceptados y contenido distinto: base 200, candidato 0. Rollback, timeout de bloqueo, desconexión antes del commit y reintento tras un commit ambiguo, todos probados (`registro/F1_r15.txt`). 5 pruebas de concurrencia en PG en la suite | CI real con el job postgresql |
| **R19** | `flush_persistence` decía «completo» con escrituras fallidas o en vuelo | Media | **CORREGIDO_Y_VERIFICADO** (vivo) | 11 | L, matriz con SQLite real y 200 escrituras × 7 condiciones × 2 corridas × 2 árboles, en orden alterno: **FALSO_COMPLETO base 2, candidato 0**; cierre limpio con pendientes: base 2, candidato 0 (`registro/G_r19_matriz.txt`). 7 pruebas nuevas. SIM E12: flush no dice completo y la sesión siguiente no opera sobre un registro corto | El motor de escenarios tiene el mismo patrón: ver N3 |
| **R24-H1** | `incidents.kind` VARCHAR(32) perdía incidentes `entries_blocked:*` (hasta 34 caracteres) | Media | **CORREGIDO_Y_VERIFICADO** | 10 | **PG:** base rechaza 3 de 6 tipos (`StringDataRightTruncationError`), y de punta a punta guarda 1 de 4 con un flush que da `True`; candidato: 6 de 6 y 4 de 4, columna de 64 (`logs/H1_*`). Migración 0008 **reversible**: la vuelta atrás se niega si cortaría datos (E15: niega, exporta, revierte y vuelve a subir sin perder nada). Migraciones arriba, abajo y arriba en PG | CI real |
| **R24-H2** | — | — | **PENDIENTE** | — | No hay definición en ninguna fuente (`registro/A6_*`) | Que el propietario la aporte. **No se inventó** |
| **R24-H3** | — | — | **PENDIENTE** | — | Ídem | Ídem |
| **P2** | La guarda 05v2 solo vale si un gate de CI la exige y el gate no se puede engañar | Media | **CORREGIDO_Y_VERIFICADO** (local) | 05v2 + 12 | L: gate v4. 47 casos adversarios (18 originales de 06v3 y 29 nuevos) más N04b, sin ningún aprobado en falso; 18 de 18 originales correctos (06v3 aprobaba 7 en falso). Guarda: hash fijado y 7 de 7 pruebas corridas y pasadas en los dos jobs locales | **CI:** una corrida real; protección de rama exigiendo el check |
| **R17** | Mientras un cierre avanza por llenados parciales, el resto no tiene **stop** (el cierre en curso cuenta como cobertura) | Baja | **PENDIENTE** (decisión de diseño, T8) | — | L: con tolerancia 0, ninguna barra queda sin cobertura (stop **o** cierre en curso). SIM E09 | Decidir si el resto necesita un stop propio |
| **R22** | La huella del motor se calcula al primer uso; un despliegue en caliente podría no corresponder al código cargado | Muy baja | **PENDIENTE** (aceptado antes; sin cambios) | — | INS | — |
| **R3** | El vivo no tiene las capas 2 y 3 de D3 | Baja | **PENDIENTE** (fuera del alcance) | — | — | Paridad vivo/backtest de D3 |
| **R6** | Tolerancia del nivel de stop: relativa en el backtest y absoluta en el vivo | Muy baja | **PENDIENTE** (aceptado; sin cambios) | — | INS | Unificarla si se toca |

## 2. Defectos nuevos encontrados en esta misión

| # | Defecto | Severidad | Estado | Parche | Evidencia |
|---|---|---|---|---|---|
| **N1** | Un error de transporte **después** de enviar una orden o una cancelación (conexión cortada, protocolo roto, escritura interrumpida) se trataba como «no entregada» (`ProviderUnavailableError`), y el vivo no reconciliaba | Alta (vivo) | **CORREGIDO_Y_VERIFICADO** (L, transporte simulado) | 15 | 4 de 6 pruebas nuevas fallaban sin el arreglo (`logs/R25b/`). Ahora: estado DESCONOCIDO, sin reintento, `HALT_NEW_ORDERS` y reconciliación (el mismo camino que el timeout). Un fallo de conexión y las lecturas siguen siendo una caída del proveedor. Falta la testnet (como R25) |
| **N2** | Colisión del client id del stop del vivo al reponerlo en la misma barra después de cancelarlo | Media | **CORREGIDO_Y_VERIFICADO** | 08 | Lo encontró una prueba nueva. El id incluye el número de colocación |
| **N3** | `RuntimeEngine.flush_persistence` (motor de escenarios, corridas simuladas desde la API) da `True` con escrituras fallidas. Esas corridas alimentan el historial de papel de la compuerta | Media-baja | **PENDIENTE** | — | INS (`runtime/engine.py:1617`). Decisión T9 |
| **N4** | El motor de escenarios usa ids de stop por barra (`protective:{symbol}:{bars}`): posible colisión al reponer en la misma barra (el análogo de N2) | Baja | **PENDIENTE** (no reproducido) | — | INS (`runtime/engine.py:1173`) |
| **N5** | Una posición restaurada al reiniciar quedaba sin stop durante su primer emparejamiento | Alta (vivo) | **CORREGIDO_Y_VERIFICADO** | 13 | Lo encontró la simulación E13 (base: no cumple; candidato: cumple). Prueba de reinicio en `test_live_position_protection.py` |
| **N6** | Docker: `sh -c` sin `exec` no reenvía el SIGTERM a Python, y la gracia de 10 s mata la sesión sin flush ni liberación del lease | Media | **PENDIENTE** (requiere autorización) | 14 (opcional, no integrado) | L: reproducido con dash fuera de Docker (`logs/N_sigterm/resultado.txt`). Sin `exec`, Python sigue vivo sin recibir la señal; con `exec`, la recibe |
| **N7** | Gate v4: el árbol de procedencia omitía los archivos versionados que coinciden con `.gitignore`, así que un cambio en ellos no se detectaba | Baja | **CORREGIDO_Y_VERIFICADO** | 12 (v2) | Árbol de procedencia = árbol candidato; casos N25 y N26 |
| **N8** | En `PAUSED` y `SAFE_MODE` no se repone un stop perdido | Media (vivo) | **PENDIENTE** (decisión T2) | — | INS |
| **N9** | Durante la sesión, una escritura perdida de un fill no bloquea las entradas | Media | **PENDIENTE** (decisión T5) | — | L: matriz R19 y E12 (el bloqueo ocurre en la sesión siguiente) |

## 3. Riesgos de proceso

| Riesgo | Estado | Qué falta |
|---|---|---|
| **A7 / R7:** la CI real nunca corrió sobre estos parches | **PENDIENTE** | Push autorizado de una rama aislada y una corrida en verde de los jobs python y postgresql (`INSTRUCCIONES_CI.md` §9) |
| **A8:** revisión humana del diff | **PENDIENTE** | Revisión firmada de los parches 08–13 y 15 |
| **R8:** sin firma digital ni ancla externa | **PENDIENTE** | Los hashes SHA-256 prueban integridad, no autoría |
| **Dinero real** | **BLOQUEANTE** | NO AUTORIZADO PARA OPERAR CON DINERO REAL. `validada_para_operar` sin cambios; ningún token ni compuerta habilitados |

## 4. Lo que bloquea qué

- **Integrar en una rama aislada:** nada técnico; hace falta autorización. Después: CI real (A7) y revisión humana (A8).
- **Vivo con Binance, aun en testnet como operación continua:** R25 y N1 (registro de testnet), N8, y las decisiones T1, T4, T5 y T7.
- **Dinero real:** todo lo anterior, más una autorización explícita que este trabajo no da.
