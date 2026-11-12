# Plan de integración y reversión (v3) — propuesta, **no ejecutada**

## 0. Qué se integra y en qué orden
| Orden | Parche | Archivo | SHA-256 | Carácter |
|---|---|---|---|---|
| 1 | 01 — D1–D3 y pruebas definitivas | `parches/01_obligatorio_D1_D3_motor_y_pruebas_definitivas.patch` | `1944f433334cada2c4fa937080241bf51643c1393f54b4d2530003557b2e60bf` | Obligatorio |
| 2 | 02v3 — trazabilidad **corregida** | `parches/02v3_obligatorio_trazabilidad_version_motor_CORREGIDO.patch` | `d5c90091b705647cdbdd9044d0406ccc28f12e39c6070deeb5cd8aef03cf6a62` | Obligatorio, **inseparable de 01** |
| 3 | 03 — pruebas sensibles al entorno | `parches/03_opcional_pruebas_reloj_y_persistencia.patch` | `0be65ea6a5e7072ff83c25ed1cccec80877ceb7b1e0609e2468a025b5294e33a` | Recomendado (solo pruebas) |
| 4 | 04 — CI con versiones fijadas | `parches/04_opcional_CI_versiones_fijadas.patch` | `8d39635635c81a4bf91071a42fb3a348ebf50b819efd92227915be3953306dd5` | Opcional, tu decisión (configuración de CI) |

- **No integrar** `parches/originales_v2/02_obligatorio_trazabilidad_version_motor.patch` (`32a42a5d…`), por el defecto R4b.
- **01 sin 02v3 reabre R4:** el mismo `run_id` para resultados de motores distintos, más el upsert ciego.
- **02v3 no aplica sin 01:** comparten `engine.py`.
- **Recomendación:** un **solo commit** con 01 + 02v3, para que no puedan separarse ni al integrar ni al revertir. 03 en un commit aparte. 04 en un commit o PR aparte, porque es configuración de CI.

## 1. Pasos exactos (después de tu autorización; cada bloque es una autorización distinta)
```bash
cd /home/user/Trader-IA
E=<extracción de entrega_integracion_D1_D3_v3_2026-10-22>
# 1.1 Precondiciones
test -z "$(git status --porcelain)" && test "$(git rev-parse HEAD)" = 72ffae5d2698440c8f1afaff12e07bd8adde66fb
git fetch origin claude/algo-trading-simulation-platform-ngf7xo
test "$(git rev-parse origin/claude/algo-trading-simulation-platform-ngf7xo)" = 72ffae5d2698440c8f1afaff12e07bd8adde66fb
(cd $E && sha256sum -c SHA256SUMS)
# 1.2 Rama local                                                          [AUTORIZACIÓN 1: crear rama local]
git switch -c fix/backtest-d1-d3-and-engine-provenance 72ffae5d2698440c8f1afaff12e07bd8adde66fb
# 1.3 Unidad 01 + 02v3                                                    [AUTORIZACIÓN 2: aplicar y commit]
git apply --check $E/parches/01_*.patch && git apply $E/parches/01_*.patch
git apply --check $E/parches/02v3_*.patch && git apply $E/parches/02v3_*.patch
sha256sum -c $E/parches/SHA256_archivos_resultantes_obligatoria_v3.txt
git add -A packages tests docs && git commit -m "Backtest: order hygiene D1-D3 and engine provenance (one unit)"
# 1.4 Parche 03                                                           [AUTORIZACIÓN 3]
git apply --check $E/parches/03_*.patch && git apply $E/parches/03_*.patch
sha256sum -c $E/parches/SHA256_archivos_resultantes_completa_v3.txt
git add -A tests && git commit -m "Tests: anchor restart scenarios to the session clock; drive the loop by hand only"
# 1.5 Verificación local antes de publicar (no requiere autorización: no publica nada)
python3.11 -m venv /tmp/v && /tmp/v/bin/pip install -c $E/entorno/ci-py311.txt -e ".[api,db,postgres,redis,llm,dev]"
/tmp/v/bin/ruff check packages tests scripts
PYTHONPATH=packages/tia/src /tmp/v/bin/python -m pytest tests -q -p no:cacheprovider --junitxml=/tmp/junit.xml
# 1.6 Publicación                                                         [AUTORIZACIÓN 4: push]
git push -u origin fix/backtest-d1-d3-and-engine-provenance
# 1.7 PR en borrador hacia claude/algo-trading-simulation-platform-ngf7xo  [AUTORIZACIÓN 5: abrir PR]
# 1.8 (opcional) 04 en un PR aparte, después de que el PR principal tenga CI real  [AUTORIZACIÓN 6]
# 1.9 Merge                                                               [AUTORIZACIÓN 7: solo con CI real en verde y revisión]
```

## 2. Criterios para fusionar (todos)
| # | Criterio | Estado hoy |
|---|---|---|
| A1 | La rama sale de `72ffae5`; cambian solo los archivos listados (`parches/ARCHIVOS_MODIFICADOS.txt`) | Verificado en copias aisladas |
| A2 | Archivos resultantes = los registrados (`sha256sum -c`) | Verificado |
| A3 | `ruff check` limpio | Verificado localmente, con y sin versiones fijadas |
| A4 | Suite sin regresiones frente a la base; 22 nuevas pasan; con 03, las 3 sensibles pasan | Verificado localmente en dos entornos |
| A5 | Las 8 pruebas D1–D3 fallan con 72ffae5 | Verificado |
| A6 | Mutantes: D1–D3 0/10 vivos; trazabilidad 0/14 (1 equivalente) | Verificado |
| A7 | **CI real de GitHub en verde** (python y frontend) | **Pendiente**: nunca corrió |
| A8 | Revisión humana del diff | Pendiente |

## 3. Reversión
- **Antes de fusionar:** cerrar el PR y borrar la rama. La rama base no cambia.
- **Después de fusionar, con PR de reversión y sin reescribir la historia:**
  1. `git revert <commit 03>`, si se integró: devuelve las 3 pruebas a `72ffae5`.
  2. `git revert <commit 01+02v3>`: revierte la unidad entera. **Nunca revertir solo una parte.**
  3. Comprobar con `git diff 72ffae5 -- packages/` sin salida.
- **Datos:**
  - **No hace falta tocar la base de datos.** Las filas guardadas con procedencia son JSON extra en `conditions`: **la API de 72ffae5 las lee sin problemas**, verificado (`evidencia/R5_compat_5_base_lee_despues.json`).
  - Después de revertir, el código viejo vuelve al upsert ciego (R4) para los backtests nuevos.
- **04:** `git revert` de su commit. Solo cambia `ci.yml` y quita `constraints/`.
- **Disparadores de reversión:**
  - una falla de suite distinta de la base atribuible a 01 o 02v3;
  - un rechazo de guardado sin un conflicto real detrás;
  - una diferencia en la API o el panel fuera de lo descrito en `COMPARACION_BASE_VS_INTEGRACION.md`.

## 4. Seguimientos (fuera de esta integración)
1. **R19:** aplicar `_drive_by_hand` después de `start()` en las pruebas que conducen los ciclos a mano (34 llamadas en 4 módulos). Es solo de pruebas y necesita su propia revisión.
2. **R24:** correr las pruebas de trazabilidad contra PostgreSQL.
3. **R15:** guardado atómico (transacción con bloqueo), si alguna vez hay escritores concurrentes.
4. **Protección de la rama base:** exigir PR y CI verde.
5. Mostrar `engine_version` en el panel.
