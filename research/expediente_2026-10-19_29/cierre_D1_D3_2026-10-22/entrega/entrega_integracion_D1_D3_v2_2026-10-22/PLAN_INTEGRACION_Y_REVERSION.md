# Plan de integración y de reversión (v2)

**Estado: propuesta. Nada de esto se ejecutó.** Crear la rama, el commit, el push y el PR requiere tu autorización expresa, paso por paso.

## 0. Punto de partida
- **Repositorio:** `elianengelberg/trader-ia`, rama única `claude/algo-trading-simulation-platform-ngf7xo`, en `72ffae5d2698440c8f1afaff12e07bd8adde66fb`.
- **Clon local `/home/user/Trader-IA`:** mismo commit, 0 cambios (`registro/00_*` y `registro/99_*`).
- **Parches, en este orden:**

| # | Parche | Carácter | Archivos |
|---|---|---|---|
| 01 | `parches/01_obligatorio_D1_D3_motor_y_pruebas_definitivas.patch` | **Obligatorio** | `backtest/engine.py`, `execution/paper.py`, `tests/unit/test_backtest_order_hygiene.py` (nuevo, 8 pruebas) |
| 02 | `parches/02_obligatorio_trazabilidad_version_motor.patch` | **Obligatorio**, aplica sobre 01 | `backtest/engine.py`, `backtest/result.py`, `persistence/repositories.py`, `api/state.py`, `docs/ARCHITECTURE.md`, `tests/integration/test_backtest_provenance.py` (nuevo, 12 pruebas) |
| 03 | `parches/03_opcional_pruebas_reloj_y_persistencia.patch` | **Opcional**, independiente de 01 y 02 | `tests/integration/test_account_restore.py`, `test_risk_state_persistence.py`, `test_adverse_recovery.py` (solo pruebas) |

- **01 y 02 van juntos.** Con 01 sin 02, el motor cambia los resultados y el `run_id` sigue siendo el mismo que con el motor viejo. Un backtest re-corrido reemplazaría en silencio al guardado: es el riesgo R4, demostrado en `evidencia/C_run_id_*.json`.
- **02 sin 01 no aplica**: comparte `engine.py`.
- **03 no toca código de producción.** Puede ir en el mismo PR o en uno aparte.

## 1. Pasos exactos (después de tu autorización)
```bash
cd /home/user/Trader-IA
# 1.1 Precondiciones: árbol limpio y base exacta, local y remota
test -z "$(git status --porcelain)" && test "$(git rev-parse HEAD)" = 72ffae5d2698440c8f1afaff12e07bd8adde66fb
git fetch origin claude/algo-trading-simulation-platform-ngf7xo
test "$(git rev-parse origin/claude/algo-trading-simulation-platform-ngf7xo)" = 72ffae5d2698440c8f1afaff12e07bd8adde66fb
# 1.2 Rama nueva (nombre propuesto; lo decidís vos)
git switch -c fix/backtest-d1-d3-and-engine-provenance 72ffae5d2698440c8f1afaff12e07bd8adde66fb
# 1.3 Aplicar y comprobar byte a byte
E=<ruta de la extracción de esta entrega>
git apply --check $E/parches/01_*.patch && git apply $E/parches/01_*.patch
git apply --check $E/parches/02_*.patch && git apply $E/parches/02_*.patch
sha256sum -c $E/parches/SHA256_archivos_resultantes_obligatoria.txt
# opcional: git apply $E/parches/03_*.patch && sha256sum -c $E/parches/SHA256_archivos_resultantes_completa.txt
git status --porcelain     # 8 entradas (11 con 03); ver parches/ARCHIVOS_MODIFICADOS.txt
# 1.4 Verificación local, como la CI, con las versiones fijadas
python3.11 -m venv /tmp/v && /tmp/v/bin/pip install -c $E/entorno/ci-py311.txt -e ".[api,db,postgres,redis,llm,dev]"
/tmp/v/bin/ruff check packages tests scripts
PYTHONPATH=packages/tia/src /tmp/v/bin/python -m pytest tests -q -p no:cacheprovider --junitxml=/tmp/junit.xml
# 1.5 Commits y push, SOLO con autorización: uno por parche, para poder revertirlos por separado.
#     Como engine.py recibe cambios de 01 y de 02, se rehace desde la base aplicando y confirmando de a uno:
git restore --staged --worktree . && git clean -fd -- tests/unit/test_backtest_order_hygiene.py tests/integration/test_backtest_provenance.py
git apply $E/parches/01_*.patch && git add -A packages tests && git commit -m "Backtest order hygiene D1-D3: fresh ids for retried exits and stops, the stop follows its level, no leg stuck behind an entry remainder"
git apply $E/parches/02_*.patch && git add -A packages tests docs && git commit -m "Record the backtest engine's provenance and never replace a stored result of another engine"
git apply $E/parches/03_*.patch && git add -A tests && git commit -m "Tests: anchor restart scenarios to the session clock and drive the loop by hand only"   # opcional
sha256sum -c $E/parches/SHA256_archivos_resultantes_completa.txt   # (o _obligatoria sin 03)
git push -u origin fix/backtest-d1-d3-and-engine-provenance
# 1.6 PR en borrador hacia claude/algo-trading-simulation-platform-ngf7xo, con revisión humana
```

## 2. Criterios de aceptación (todos, antes de fusionar)
| # | Criterio | Cómo se comprueba | Estado en esta entrega |
|---|---|---|---|
| A1 | La rama sale de `72ffae5` y cambian solo los archivos listados | `git diff --name-status 72ffae5..HEAD` | Verificado en copias aisladas |
| A2 | Archivos resultantes = los registrados | `sha256sum -c` | Verificado |
| A3 | `ruff check packages tests scripts` limpio | local o CI | Verificado localmente |
| A4 | Suite completa sin regresiones frente a la base corrida en el mismo momento; las 20 nuevas pasan; con 03, las 3 sensibles al entorno pasan | JUnit + `herramientas/comparar_suites_v2.py` | Ver `evidencia/F_*` |
| A5 | Las 8 pruebas D1–D3 fallan con el motor de `72ffae5` y pasan con el parche | `reproducir.sh`, paso 3 | Verificado |
| A6 | Mutantes D1–D3: 0 vivos de 10; trazabilidad: 0 vivos de 11 (+1 equivalente justificado) | `reproducir.sh`, paso 5 | Verificado |
| A7 | El workflow `ci.yml` de GitHub en verde | **Nunca corrió.** El primer PR es su primera corrida | **No verificado** |
| A8 | Revisión humana del diff | Aprobación en el PR | Pendiente |

## 3. Qué cambia al fusionar
- **Backtests:**
  - Los resultados cambian cuando hay rechazos, llenados parciales o movimientos de break-even o trailing. Es el arreglo de D1–D3.
  - Cada resultado nuevo lleva `engine_version` 1.1.0, la huella del código del motor, la de los datos y la del universo.
  - El `run_id` cambia de fórmula: todo backtest nuevo tiene un id distinto al que tenía con el motor viejo.
- **Base de datos:**
  - **Sin migración ni cambio de esquema.** Los campos nuevos viven dentro de la columna JSON `conditions`, que ya existe.
  - Las filas guardadas antes quedan intactas, con su `run_id` y sus números. No se tocan, no se reescriben y no se completan.
  - Un intento de guardar sobre un `run_id` existente con otra procedencia se rechaza con `ValueError`, que la API devuelve como 400.
- **API `GET /api/backtests`:**
  - Cada fila agrega `engine_version`.
  - Vale `null` para las filas viejas: motor desconocido.
  - El resto de la respuesta no cambia.
- **Panel:** puede ignorar el campo nuevo. Mostrarlo es un seguimiento opcional.
- **Sesión en vivo, papel en tiempo real, market making, T-papel:**
  - **Sin cambios de código.** No usan `BacktestEngine` ni `BacktestRepository`.
  - El parche 03 solo toca pruebas.
- **Seguridad y operación:**
  - No se tocan `validada_para_operar`, la configuración, las credenciales ni el despliegue.
  - La CI no despliega.

## 4. Tratamiento de los registros históricos
- **Filas de `backtests` sin `engine_version`:**
  - Motor **desconocido**.
  - No se les asigna versión, ni siquiera «1.0.0», porque nadie registró con qué código se calcularon.
  - Para compararlas con resultados nuevos, primero hay que reconstruir su procedencia por fuera, con fecha y commit desplegado. Si no se puede, quedan como no comparables.
- **E1, SIM1, T-MULTI, T-papel, E3-H1:** no se regeneran ni se modifican. Sus manifiestos verifican igual antes y después (`registro/99_*`).

## 5. Reversión
- **Antes de fusionar:** cerrar el PR y borrar la rama. La rama base no cambia.
- **Después de fusionar, en una rama nueva, con un PR de reversión y sin reescribir la historia:**
  - `git revert <commit 03>`, si se incluyó: devuelve las tres pruebas a su versión de `72ffae5`.
  - `git revert <commit 02>`: el `run_id` vuelve a la fórmula vieja y el guardado vuelve al upsert ciego.
    - Las filas guardadas con procedencia **se conservan**: el código viejo las lee sin problema, porque son JSON extra en `conditions`.
    - **Advertencia:** sin 02, un backtest re-corrido puede volver a sobrescribirse en silencio (R4). Revertir 02 sin revertir 01 reabre R4.
  - `git revert <commit 01>`: devuelve `engine.py` y `paper.py` a los blobs de `72ffae5` y borra la prueba nueva.
  - Comprobación: `git diff 72ffae5 -- packages/tia/src/tia/backtest/engine.py packages/tia/src/tia/execution/paper.py` debe salir vacío.
- **Estado persistido:** ninguna reversión requiere tocar la base de datos.
- **Disparadores de reversión:**
  - una falla de la suite, distinta de la base, atribuible a 01 o 02;
  - un rechazo de guardado («another provenance») sin un conflicto real detrás;
  - una diferencia en la API o el panel que no corresponda a lo descrito en §3.

## 6. Seguimientos (fuera de esta integración)
1. **Protección de la rama base:** exigir PR y CI verde antes de fusionar.
2. **CI con versiones fijadas:** usar `entorno/ci-py311.txt` en `ci.yml`, como `pip install -c`. Es un cambio de infraestructura de CI que no se hizo: lo decidís vos.
3. **Pruebas con el mismo patrón latente que la de persistencia:** otras pruebas llaman a `start()` y después hacen ciclos a mano con el bucle de fondo girando (`test_account_restore`, `test_funding_*`). Pasaron en todas las corridas de hoy, pero no se midió su holgura una por una; ver `INFORME_TECNICO_FINAL.md` §B3 y R19.
4. **Mostrar `engine_version` en el panel.**
