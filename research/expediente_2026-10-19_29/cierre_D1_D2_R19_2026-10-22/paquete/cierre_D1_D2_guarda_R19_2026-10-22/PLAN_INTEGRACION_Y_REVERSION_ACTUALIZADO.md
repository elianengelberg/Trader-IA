# Plan de integración y reversión, actualizado (2026-10-22) — propuesta, **no ejecutada**

**Base:** `72ffae5d2698440c8f1afaff12e07bd8adde66fb`.

**Fuente de los parches:** la entrega `entrega_integracion_D1_D3_v3r3_2026-10-22.zip`. Su carpeta `parches/` es idéntica byte a byte a la de v3r2: los hashes de abajo no cambian.

Cada bloque marcado **[AUTORIZACIÓN n]** necesita tu autorización explícita y por separado. Nada de esto se ejecutó.

## 0. Unidades y orden
| Orden | Unidad | Archivos | SHA-256 | Carácter | Commit |
|---|---|---|---|---|---|
| 1 | **01 + 02v3** (D1–D3 y trazabilidad) | `parches/01_*.patch`, `parches/02v3_*.patch` | `1944f433…2e60bf`, `d5c90091…cf6a62` | Obligatoria | **Un único commit**: técnicamente separables, pero 02v3 sin 01 declara `engine_version` 1.1.0 sin D1–D3 |
| 2 | **05 — guarda de versión** (propuesta nueva) | `05_propuesta_guarda_version_motor.patch`, un archivo de prueba nuevo | Ver `fase2/` | Opcional. Revisión y autorización **propias** | Commit aparte, inmediatamente después de la unidad 1 |
| 3 | 03 — pruebas sensibles al entorno | `parches/03_*.patch` | `0be65ea6…94e33a` | Recomendado (solo pruebas) | Commit aparte |
| 4 | 04 — CI con versiones fijadas | `parches/04_*.patch` | `8d396356…306dd5` | Opcional | PR aparte |
| — | 02 original | `parches/originales_v2/02_*.patch` | `32a42a5d…` | **No integrar** (R4b) | — |

**Por qué 05 va justo después de la unidad 1:**
- Con 05 en la rama, una reversión o integración parcial que deje 02v3 sin 01 **pone la CI en rojo**: 5 pruebas fallan, verificado con 02v3 sin 01 y con mutantes.
- Sin 05, solo el procedimiento la impide.
- 05 **no reemplaza** el commit único: lo respalda.

## 1. Pasos
```bash
cd /home/user/Trader-IA; E=<extracción de entrega_integracion_D1_D3_v3r3_2026-10-22>; G=<carpeta fase2 de esta entrega>
# 1.1 Precondiciones (solo lectura)
test -z "$(git status --porcelain)" && test "$(git rev-parse HEAD)" = 72ffae5d2698440c8f1afaff12e07bd8adde66fb
(cd $E && sha256sum -c SHA256SUMS)
# 1.2 Rama local                                                                   [AUTORIZACIÓN 1]
git switch -c fix/backtest-d1-d3-and-engine-provenance 72ffae5d2698440c8f1afaff12e07bd8adde66fb
# 1.3 Unidad 01 + 02v3 en UN commit                                                [AUTORIZACIÓN 2]
git apply --check $E/parches/01_*.patch && git apply $E/parches/01_*.patch
git apply --check $E/parches/02v3_*.patch && git apply $E/parches/02v3_*.patch
sha256sum -c $E/parches/SHA256_archivos_resultantes_obligatoria_v3.txt
git add -A packages tests docs && git commit -m "Backtest: order hygiene D1-D3 and engine provenance (one unit)"
diff <(git show --name-only --format= HEAD | LC_ALL=C sort) <(printf "%s\n" docs/ARCHITECTURE.md packages/tia/src/tia/api/state.py packages/tia/src/tia/backtest/engine.py packages/tia/src/tia/backtest/result.py packages/tia/src/tia/execution/paper.py packages/tia/src/tia/persistence/repositories.py tests/integration/test_backtest_provenance.py tests/unit/test_backtest_order_hygiene.py | LC_ALL=C sort)
# 1.4 (opcional) Guarda 05, después de revisarla                                    [AUTORIZACIÓN 3, aparte]
git apply --check $G/parche/05_propuesta_guarda_version_motor.patch && git apply $G/parche/05_propuesta_guarda_version_motor.patch
PYTHONPATH=packages/tia/src python -m pytest -q tests/integration/test_engine_version_contract.py      # 7 passed
git add tests/integration/test_engine_version_contract.py && git commit -m "Tests: tie engine_version 1.1.0 to D1-D3 as seen at the venue"
# 1.5 Parche 03                                                                     [AUTORIZACIÓN 4]
git apply --check $E/parches/03_*.patch && git apply $E/parches/03_*.patch
git add -A tests && git commit -m "Tests: anchor restart scenarios to the session clock; drive the loop by hand only"
# 1.6 Verificación local antes de publicar (no publica nada)
python3.11 -m venv /tmp/v && /tmp/v/bin/pip install -c $E/entorno/ci-py311.txt -e ".[api,db,postgres,redis,llm,dev]"
/tmp/v/bin/ruff check packages tests scripts
PYTHONPATH=packages/tia/src /tmp/v/bin/python -m pytest tests -q -p no:cacheprovider --junitxml=/tmp/junit.xml
# 1.7 Push (dispara la primera CI real)                                             [AUTORIZACIÓN 5]
# 1.8 PR en borrador                                                                [AUTORIZACIÓN 6]
# 1.9 (opcional) 04 en un PR aparte                                                 [AUTORIZACIÓN 7]
# 1.10 Merge: solo con la CI real en verde y revisión humana                        [AUTORIZACIÓN 8]
```

## 2. Criterios para fusionar
| # | Criterio | Estado |
|---|---|---|
| A1–A6 | Rama desde `72ffae5`, archivos registrados, ruff, suites sin regresiones, D1–D3 contra la base, mutantes | Verificados **localmente** (v3r2, y de nuevo en la reproducción limpia de v3r3) |
| A7 | **CI real de GitHub en verde** (python y frontend) | **Pendiente:** GitHub Actions nunca corrió sobre estos parches |
| A8 | Revisión humana del diff | Pendiente |
| A9 | Si se integra 05: la guarda pasa en la CI real | Pendiente. Localmente: 7 de 7 |
| A10 | **Si la primera CI falla**, nombrar la prueba y la excepción, y compararlas con la base | Ver §4 |

## 3. Reversión
- **Antes de fusionar:** cerrar el PR y borrar la rama. La rama base no cambia.
- **Después de fusionar**, con un PR de reversión y sin reescribir la historia, en orden inverso:
  1. `git revert <commit 03>`, si se integró;
  2. `git revert <commit 05>`, si se integró;
  3. `git revert <commit 01+02v3>`, que revierte **la unidad entera**.
- **Nunca revertir solo una parte de la unidad:**
  - Revertir solo 01 deja un motor que declara 1.1.0 sin D1–D3. Con 05 en la rama, la CI lo marca en rojo.
  - Revertir solo 02v3 reabre R4. 05 no lo detecta: sin versión declarada no hay promesa que exigir.
- **Interacción con 05:**
  - Revertir la unidad entera con 05 todavía en la rama es seguro: sin `engine_version`, la guarda se omite (5 omitidas, 2 pasan; verificado en la base).
  - Igual conviene revertir 05 primero, para no dejar una prueba que se omite siempre.
- **Datos:**
  - No hace falta tocar la base de datos. La procedencia es JSON extra en `conditions`, y la API de `72ffae5` lo lee (`R5_*`).
  - Después de revertir, los backtests nuevos vuelven al upsert ciego (R4).
- **Disparadores de reversión:**
  - una falla de suite distinta de la base atribuible a 01, 02v3 o 05;
  - un rechazo de guardado sin un conflicto real detrás;
  - una diferencia en la API o el panel fuera de lo descrito.

## 4. Si la primera CI falla
1. Comparar con la base: correr la CI también sobre `72ffae5`, o usar la evidencia `S_*`.
2. Si falla `persistence writes still in flight` en una prueba que 03 no modifica:
   - el síntoma es **compatible** con R19, que es preexistente;
   - **no se atribuye** a R19 sin la evidencia del mecanismo;
   - el instrumento para conseguirla es la enmienda 1 de R19 (`fase3/`), que está congelada y espera tu aprobación.
3. **No se fusiona en rojo.** No se sube ningún límite de tiempo como «arreglo».

## 5. Seguimientos, fuera de esta integración
1. **R19:** aprobar o corregir `PLAN_R19_ENMIENDA_1.md` y ejecutarla. El parche de pruebas `_drive_by_hand` va solo si se confirma H-ENT.
2. **R24:** correr las pruebas de trazabilidad contra PostgreSQL.
3. **R15:** guardado atómico, si alguna vez hay escritores concurrentes.
4. **Protección de la rama base:** exigir PR y CI verde.
5. Mostrar `engine_version` en el panel.
