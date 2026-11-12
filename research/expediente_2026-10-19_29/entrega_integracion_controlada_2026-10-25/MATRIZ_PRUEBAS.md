# Matriz de pruebas (integración controlada, 2026-10-25)

- **Entorno:** Python 3.11.17 con `constraints/ci-py311.txt` (74 paquetes, freeze canónico `a1a96cac…`, igual al de la revisión adversaria) y PostgreSQL 16.15 desechable.
- **Lugar:** todo se corrió en clones aislados, fuera del repositorio protegido.
- **Testnet y CI real:** **ninguna** prueba se corrió en testnet ni en GitHub Actions.

## 1. Línea base (Fase A): las suites de referencia se reproducen

| Árbol | Esperado | Pruebas | Resultado | Igual a la revisión adversaria (nodeid y resultado por prueba) |
|---|---|---|---|---|
| base `44850cfc` | — | 1956 | 1956 pasan | sí |
| A (01+02v3) `5d6a0954` | `5d6a0954` | 1978 | 1978 pasan | sí |
| A+03 `a94be41a` | `a94be41a` | 1978 | 1978 pasan | sí |
| Final previo (+04+06v3) `0477c6a2` | `0477c6a2` | 1985 | 1985 pasan | sí |

Fuente: `registro/A7_suites_referencia.txt` y `registro/A5_arboles.txt` (6 árboles coinciden).

## 2. Unidades A y B (Fase B)

- **A (01+02v3)** aplica, revierte y reproduce su árbol: 13 de 13 comprobaciones (`registro/B_unidades_A_B.txt`).
- **B (05v2) falla cerrado:**
  - sin A;
  - con 02v3 sin 01;
  - con 01 sin 02v3.
- **Mutantes de la guarda 05v2:** 25 de 26 detectados por la razón correcta o con el desenlace esperado. El restante (M7) está fuera del alcance declarado.

## 3. Pruebas nuevas o modificadas, por defecto

En «sin arreglo», la prueba se corrió en el árbol anterior al parche, copiando solo el archivo de prueba. Los conteos finales salen del JUnit de `logs/J_main` y `logs/J_pg`.

| Defecto | Archivo | Pruebas | Sin arreglo | Con arreglo (job python / job postgresql) |
|---|---|---|---|---|
| R25 | `tests/unit/test_binance_protective_stop.py` (nuevo) | 12 | — | 12 / 12 pasan |
| R25 + R18 (vivo) | `tests/integration/test_live_position_protection.py` (nuevo; +1 de reinicio en 13) | 9 | — | 9 / 9 |
| R18 (backtest, tolerancia 0) | `tests/unit/test_backtest_protection_window.py` (nuevo) | 5 | — | 5 / 5 |
| R25 + R18, conjunto al crearse (parche 08) | los tres de arriba | 25 en ese momento | **18 fallan**, 7 pasan (`logs/D0_*`) | 25 pasan (`logs/D1_*`) |
| R15 | `tests/integration/test_backtest_store_concurrency.py` (nuevo) | 6 (5 PG) | en PG, la base da éxito a escritores descartados (§4) | 1 pasa + 5 omitidas / **6 pasan** |
| R24-H1 | `tests/integration/test_incident_kind_length.py` (nuevo) | 4 (1 PG) | en PG, la base rechaza 3 de 6 tipos (§4) | 3 + 1 omitida / **4 pasan** |
| R19 | `tests/integration/test_persistence_completeness.py` (nuevo) | 7 | matriz R19: la base da falso completo (§4) | 7 / 7 |
| N1 (R25b) | `tests/unit/test_binance_ambiguous_transport.py` (nuevo) | 6 | **4 fallan**, 2 pasan (`logs/R25b/SIN_correccion.txt`) | 6 / 6 |
| 07 (paquete previo) | `tests/integration/test_backtest_store_postgresql.py` | 4 (PG) | — | omitidas / **4 pasan** |
| Guarda 05v2 | `tests/integration/test_engine_version_contract.py` | 7 | — | 7 / 7. El gate exige 7 de 7 y el hash del archivo |
| Adaptación: el stop se pone al llenarse la entrada y luego se arrastra | `tests/integration/test_live_runtime.py` (modificado) | 77 | — | 77 / 77 |
| Adaptación: R19 exige declarar una pérdida provocada (`settle_lossy`) | `test_account_restore.py`, `test_adverse_recovery.py`, `test_funding_recovery.py` (modificados) | 23 + 2 + 7 | `test_funding_recovery` falló en la primera CI local (§6) | todas pasan |
| Adaptación: versión de esquema | `tests/integration/test_restart_recovery.py` (`== SCHEMA_VERSION`) | 6 | — | 6 / 6 |
| Hora UTC (parche 03) | `tests/integration/test_risk_state_persistence.py` | 9 | ver §5 | 9 / 9 a cualquier hora |

Ninguna prueba existente se debilitó para pasar. Hubo dos ajustes de umbral; los dos están documentados:

- `test_live_runtime`: la protección se mide por stops **trabajando** y cambios de nivel, porque el stop ahora se pone al llenarse la entrada y luego se arrastra.
- Prueba de reversiones del backtest: se exigen ≥ 3 en vez de ≥ 5, porque la fixture tiene 3 reversiones.

## 4. Experimentos con PostgreSQL y SQLite reales

| Experimento | Diseño (fijado antes) | Base | Candidato | Fuente |
|---|---|---|---|---|
| R15: carreras de guardado en PG 16.15 | 440 intentos × 2 semillas, con rollback, timeout de bloqueo, desconexión antes del commit y reintento ambiguo | **266** éxitos dados a escritores descartados; 200 con ambos aceptados | **0 y 0** | `registro/F1_r15.txt`, `logs/F1_*` |
| R24-H1: largo de `kind` en PG | 6 tipos reales de incidente, directo y de punta a punta | 3 de 6 rechazados; de punta a punta, 1 de 4 guardados con flush `True` | 6 de 6 y 4 de 4; columna de 64 | `logs/H1_*` |
| R19: matriz de completitud | 200 escrituras × 7 condiciones × 2 corridas × 2 árboles, orden alterno, SQLite real | FALSO_COMPLETO 2; cierre limpio con pendientes 2 | **0 y 0** | `registro/G_r19_matriz.txt` |
| Almacén 07 en PG | 4 pruebas | — | 4 pasan; 104 escrituras registradas por el servidor; 0 bases sobrantes | `logs/F0_almacen_pg.txt` |
| Migraciones en PG | arriba → base → arriba | — | rc 0 / 0 / 0 | `logs/J_pg/resumen.txt` |
| Reversión de versión (E15) | escribir con v8, leer con v7, revertir, volver a subir | — | ver `SIMULACION_INTEGRAL.md` E15 | `logs/K_E15*` |

Las bases de PostgreSQL se crearon por prueba y se borraron al terminar (`herramientas/pg_plugin.py`). Al final no queda ninguna.

## 5. Dependencia horaria (Fase J), con `time-machine` fuera del venv fijado

| Hora UTC fijada | Base `44850cfc` | Candidato |
|---|---|---|
| 00:30 | **FALLA** (`test_five_restored_entries…`) | pasa 9/9 |
| 02:30 | **FALLA** | pasa |
| 05:50 | **FALLA** | pasa |
| 05:56 | pasa | pasa |
| 12:00 | pasa | pasa |
| 23:59 | pasa | pasa |
| **Mutante** (estado restaurado ignorado) a las 02:30 y a las 12:00 | FALLA | **FALLA** (`assert 2 == 0` sobre las órdenes enviadas): la prueba conserva su propósito |

Los 17 archivos que usan `trend_up` pasan a las 02:30 y a las 12:00 en el candidato. Fuente: `logs/J_hora/`.

## 6. CI local equivalente (Fase J)

| Corrida | Árbol | ruff | pytest | Pruebas | Omitidas | Gate | Migraciones |
|---|---|---|---|---|---|---|---|
| `J_intento1` main / pg | `32486a9f` | OK | **rc 1** (1 falla: `test_funding_recovery`, regresión funcional de R19 en la prueba) | 2031 | 10 / 0 | **FAIL** (correcto) | SQLite OK; PG arriba/abajo/arriba OK |
| `J_intento2` main / pg | `85d973ee` | OK | rc 0 | 2032 | 10 / 0 | pass, pero árbol de procedencia ≠ candidato (defecto N7) | OK |
| `J_intento3` main / pg | `c7688384` | OK | rc 0 | 2032 | 10 / 0 | pass; procedencia = candidato | OK |
| **final** main / pg | **`17332e1c`** | OK | **rc 0** | **2038** | **10 / 0** | **pass / pass**; procedencia = candidato; guarda 7/7 | SQLite OK; **PG arriba/abajo/arriba OK** |

## 7. Arnés adversario del gate v4 (Fases C e I)

Detalle en `INSTRUCCIONES_CI.md` §8 y en `logs/C_gate_v4*`.

- **Originales de 06v3:** 18 de 18 con el desenlace esperado.
- **Nuevos:** 28 de 29 con desenlace y razón esperados. N04 falló cerrado pero por otra razón (su premisa no se dio).
- **N04b:** detecta el módulo sustituido por cuatro razones.
- **Aprobados en falso: 0.**

## 8. Simulación integral (Fase K)

- **Candidato:** 15 de 15 escenarios en las semillas 7 y 8.
- **Base:** 10 de 15; falla en E04b, E08, E11, E12 y E13.
- **E15:** reversión segura.
- Ver `SIMULACION_INTEGRAL.md`.

## 9. Lo que NO se probó

- Binance real o testnet: el adaptador solo se probó contra un transporte simulado.
- GitHub Actions.
- El job `frontend`.
- Docker: el apagado se reprodujo con dash, fuera de Docker.
- Carga sostenida durante horas.
- Una base PostgreSQL de producción.
