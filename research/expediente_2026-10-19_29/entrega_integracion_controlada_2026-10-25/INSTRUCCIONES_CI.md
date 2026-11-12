# CI: equivalencia local, cómo correr la CI real y cómo leer el resultado (Fase J)

**La CI remota NO corrió sobre estos parches.** No se hizo push, por falta de autorización. Todo lo que dice «pasa» en este documento es **local**: el árbol, el intérprete y los pasos son los del workflow, en esta máquina. No reemplaza una corrida real de GitHub Actions.

## 1. El árbol que hay que probar

- Base: commit `72ffae5d2698440c8f1afaff12e07bd8adde66fb` (árbol `44850cfc…`).
- Cadena de parches, en este orden (`parches/CADENA.txt`):
  - del paquete previo, sin modificar: 01, 02v3, 05v2, 03, 04 y 07;
  - de esta misión: 08, 09, 10, 11, 12, 13 y 15.
- Árbol resultante: **`17332e1c510d0004f7744bde0a68f008f01652b7`**.
- Se reconstruye con `reproducir.sh`, que clona en un directorio temporal y **no** opera sobre el repositorio protegido.
- Opcional, **no incluido** (pide autorización de producción): `14_OPCIONAL_produccion_apagado_ordenado_docker.patch`.
- `06v3` **no** se aplica. Queda solo como evidencia histórica; el gate v4 del parche 12 lo reemplaza.

## 2. Equivalencia entre el workflow y la corrida local (`herramientas/ci_local.sh`)

| Paso de `.github/workflows/ci.yml` | Local | Diferencia |
|---|---|---|
| `setup-python 3.11` + `pip install -c constraints/ci-py311.txt -e ".[…]"` | venv propio con las mismas restricciones (`registro/A4_venv.txt`; freeze canónico `a1a96cac…`) | El proyecto no se instala en modo editable: se usa `PYTHONPATH=packages/tia/src`, que es lo mismo que el `pythonpath` de pytest. El gate solo compara las distribuciones fijadas, así que un `tia==0.1.0` editable no lo afecta |
| `ruff check packages tests scripts` | igual, con `--no-cache` | ninguna funcional |
| `python -m pytest tests -q -p scripts.ci_provenance --junitxml=ci-evidence/junit.xml` | igual | `CI_RUN_NONCE` local (`local-<job>-<aleatorio>`) |
| `python scripts/ci_gate.py ci-evidence ci-evidence/junit.xml` (`if: !cancelled()`) | igual; corre siempre | — |
| `upload-artifact` | se copian `junit.xml`, `session.json` y `provenance.json` a `logs/J_<job>/` | — |
| `alembic upgrade head` (SQLite) | igual | — |
| job `postgresql`: servicio `postgres:16`, `CI_GATE_REQUIRE_POSTGRESQL=1`, `TIA_TEST_POSTGRESQL_URL` | PostgreSQL 16.15 desechable, local, por socket Unix (`herramientas/pg.sh`) | socket en lugar de TCP `localhost:5432` |
| `alembic upgrade head` → `downgrade base` → `upgrade head` en PostgreSQL | igual, sobre una base `ci_migrations` que se crea y se borra | — |
| job `frontend` | **no se corrió** | fuera del alcance de los parches (no tocan `frontend/`) |

## 3. Resultado local sobre el árbol final

Ver `logs/J_main/resumen.txt` y `logs/J_pg/resumen.txt`; los números finales están en `VERIFICACION_FINAL.txt`.

## 4. Omisiones (skips) documentadas

- **Job python:** 10 omitidas, todas de PostgreSQL. Sin `TIA_TEST_POSTGRESQL_URL` se omiten y **nunca** caen a SQLite. El gate las permite por prefijo (`allowed_skips` de `scripts/ci_gate_policy.json`):
  - `tests.integration.test_backtest_store_concurrency` × 5 (R15);
  - `tests.integration.test_backtest_store_postgresql` × 4 (07);
  - `tests.integration.test_incident_kind_length::test_on_postgresql_…` × 1 (R24-H1).
- **Job postgresql:** **0** omitidas. Con `CI_GATE_REQUIRE_POSTGRESQL=1` el gate no permite ninguna, y exige al menos 10 pruebas de PostgreSQL pasadas y ninguna omitida. Que falle si se omiten es el caso N21 del arnés.
- **xfail:** no hay ninguno en la suite. Un `xpass` hace fallar el gate (caso N19).

## 5. Pruebas que dependen de la hora, el huso, el orden o la carga

| Prueba | Dependencia | Estado en el candidato | Evidencia |
|---|---|---|---|
| `test_risk_state_persistence.py::test_five_restored_entries_for_the_symbol_refuse_the_sixth_after_the_restart` | **Hora UTC.** La base falla de 00:00 a 05:55 UTC: el día restaurado sale del reloj de pared y la sesión vive unas 5 h 55 min atrás | **Corregida por el parche 03** (ancla la serie a un día fijo). Se demostró: base FALLA a las 00:30, 02:30 y 05:50 y PASA a las 05:56, 12:00 y 23:59; el candidato PASA a todas esas horas. El propósito se mantiene: con un mutante que ignora el estado restaurado, la prueba FALLA a las 02:30 y a las 12:00 (`assert 2 == 0` sobre las órdenes enviadas) | `logs/J_hora/reloj_base_vs_candidato.txt` |
| `test_account_restore.py` (escenario del día) | Hora UTC: antes se **omitía** con `pytest.skip` si el día cambiaba | Corregida por 03: el `skip` pasó a ser un `assert` | parche 03 |
| `test_account_restore.py::test_partial_fills_and_fees_rebuild_identically_however_often` | **Carga.** El bucle propio de la sesión giraba al lado de la prueba y el flush medía esa carrera | Corregida por 03 (`_drive_by_hand`). Además, el parche 11 exige que las escrituras perdidas a propósito se declaren (`settle_lossy`) | parches 03 y 11 |
| `test_funding_recovery.py` (modo `drop_batch`) | Semántica de R19: deja caer un lote a propósito | El parche 11 lo adapta (`settle_lossy` solo en ese modo). Lo detectó la primera CI local, ver §6 | `logs/J_intento1/` |
| 17 archivos que usan el escenario `trend_up` | Hora | Pasan a las 02:30 y a las 12:00 UTC | `logs/J_hora/viaje_0230.txt`, `viaje_1200.txt` |

Para esta prueba se instaló `time-machine` **fuera** del venv fijado, solo para el experimento.

## 6. Fallas: infraestructura frente a funcionales (corridas locales de esta misión)

| Corrida | Árbol | Resultado | Tipo | Causa |
|---|---|---|---|---|
| `J_intento1` | `32486a9f…` (antes del arreglo) | 1 falla, el gate FALLA | **Funcional** (regresión de esta misión) | `test_funding_recovery::test_a_batch_that_never_reached_the_store_is_settled_once_by_the_next_session`: con R19, un lote perdido a propósito ya no cuenta como «completo». Se corrigió la prueba (declara la pérdida); el código no cambió |
| `J_intento2` | `85d973ee…` | pasa | — | El árbol de procedencia (`15fd49b…`) **no** coincidía con el árbol candidato. Defecto del plugin, ver §7 |
| `J_intento3` | `c7688384…` | pasa, procedencia = árbol candidato | — | Base del arnés adversario del gate |
| final | `17332e1c…` | ver `VERIFICACION_FINAL.txt` | — | — |

- Ninguna falla fue de infraestructura: no hubo red, disco ni tiempos de espera.
- El disco de la máquina tenía unos 2 GB libres, así que se borraron clones desechables entre corridas. Ninguna corrida falló por eso.

## 7. Defecto encontrado en el propio gate v4 y corregido

- **Qué pasaba:** el id del árbol de trabajo se calculaba con un índice temporal **vacío**. Los archivos versionados que coinciden con un patrón de `.gitignore` (11 `.log` en `research/hcarry_next/`) quedaban fuera del árbol, y un cambio en ellos no se detectaba.
- **Arreglo:** el índice temporal se siembra desde `HEAD` (`git read-tree HEAD`), en el plugin y en el gate.
- **Verificación:** el árbol registrado ahora es exactamente el árbol candidato (`c7688384…` en J_intento3, `17332e1c…` en la final). El arnés agrega N25 (archivo versionado e ignorado, alterado después de la corrida: el gate FALLA) y N26 (archivo nuevo plantado después: el gate FALLA).

## 8. Arnés adversario del gate v4 (`herramientas/gate_v4_adversario.py`)

Los resultados esperados se fijaron antes de correr. Detalle en `logs/C_gate_v4/` y `logs/C_gate_v4_N04b/`.

- **18 casos originales de 06v3:** 18 de 18 con el desenlace esperado.
  - De los 7 que 06v3 aprobaba en falso (K1–K5, J1, J2, J5), ahora todos fallan.
  - El control J7 (otro intérprete para el gate) aprueba, como corresponde.
- **29 casos nuevos:** 28 de 29 con el desenlace y la **razón** esperados.
  - **N04** falló cerrado, pero por otra razón. La sombra puesta en `PYTHONPATH` nunca llegó a importarse: el `pythonpath` de pytest pone el checkout primero, y el gate registró, con razón, el motor del checkout.
  - Se agregó **N04b** (la sombra entra por un `sitecustomize`). El gate FALLA por las cuatro razones esperadas: versión 1.0.0 frente a 1.2.0, archivo fuera del checkout, hash distinto y guarda no superada.
- **Ningún caso aprobó en falso.**

## 9. Cómo correr la CI real (requiere autorización)

1. Reconstruir el árbol con `reproducir.sh` y comprobar `17332e1c…`.
2. Con autorización, crear una rama **aislada** con ese árbol (un commit) y hacer push. No mezclar.
3. Esperar los jobs `python`, `postgresql` y `frontend`, y bajar los artefactos `ci-evidence-*`.
4. Verificar en el artefacto:
   - `provenance.json` con `verdict: pass`;
   - `working_tree` igual al árbol del commit;
   - `tests ≥ 2031`;
   - job python: 10 omitidas, todas del allow-list;
   - job postgresql: 0 omitidas y `postgresql_tests_passed ≥ 10`;
   - guarda con 7 de 7;
   - las migraciones de PostgreSQL arriba, abajo y arriba en verde.
5. Solo con eso se puede decir que la CI remota aprobó. Hasta entonces, **no**.
