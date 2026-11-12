# Plan de integración del parche D1–D3 (propuesta; NO ejecutada)

**Nada de esto se ejecutó.** Cada paso que escribe en git o en GitHub requiere tu autorización expresa: crear la rama, el commit, el push y el PR.

## 0. Punto de partida (verificado el 2026-10-21 a las 23:19Z)
- **Repositorio:** `elianengelberg/trader-ia`. En GitHub hay **una sola rama**, `claude/algo-trading-simulation-platform-ngf7xo`:
  - en `72ffae5d2698440c8f1afaff12e07bd8adde66fb`;
  - **sin protección**;
  - sin PRs abiertos ni cerrados;
  - no hay `main`.
- **Clon local `/home/user/Trader-IA`:** misma rama, mismo commit, 0 cambios.
- **Parche:** `parche/integracion_D1_D3_72ffae5.patch` (SHA-256 en `SHA256SUMS`). Toca 3 archivos (`parche/ARCHIVOS_QUE_CAMBIAN.txt`).

## 1. Pasos exactos (en el clon local, después de tu autorización)
```bash
cd /home/user/Trader-IA
# 1.1 Precondiciones: árbol limpio y base exacta
test -z "$(git status --porcelain)" && test "$(git rev-parse HEAD)" = 72ffae5d2698440c8f1afaff12e07bd8adde66fb
git fetch origin claude/algo-trading-simulation-platform-ngf7xo
test "$(git rev-parse origin/claude/algo-trading-simulation-platform-ngf7xo)" = 72ffae5d2698440c8f1afaff12e07bd8adde66fb
# 1.2 Rama separada (el nombre lo decidís vos; propuesta:)
git switch -c fix/backtest-order-hygiene-d1-d3 72ffae5d2698440c8f1afaff12e07bd8adde66fb
# 1.3 Aplicar y comprobar que el resultado es byte a byte el verificado
git apply --check <entrega>/parche/integracion_D1_D3_72ffae5.patch
git apply <entrega>/parche/integracion_D1_D3_72ffae5.patch
sha256sum -c <entrega>/parche/SHA256_archivos_resultantes.txt
git status --porcelain   # exactamente: M engine.py, M paper.py, ?? tests/unit/test_backtest_order_hygiene.py
# 1.4 Verificación local, como la CI
ruff check packages tests scripts
PYTHONPATH=packages/tia/src python -m pytest tests -q -p no:cacheprovider --junitxml=/tmp/junit_d1d3.xml   # esperado: 1962 pasan
# 1.5 Commit y push SOLO con autorización
git add packages/tia/src/tia/backtest/engine.py packages/tia/src/tia/execution/paper.py tests/unit/test_backtest_order_hygiene.py
git commit -m "Backtest order hygiene: fresh ids for retried exits/stops (D1), stop follows its level (D2), no stuck legs from entry remainders (D3)"
git push -u origin fix/backtest-order-hygiene-d1-d3
# 1.6 PR hacia claude/algo-trading-simulation-platform-ngf7xo (la única rama; base de facto), en borrador, con revisión
```

## 2. Criterios de aceptación (todos, antes de fusionar)
| # | Criterio | Cómo se comprueba |
|---|---|---|
| A1 | La rama sale exactamente de `72ffae5` y solo cambian los 3 archivos listados | `git diff --name-status 72ffae5..HEAD` |
| A2 | Los archivos resultantes coinciden con `SHA256_archivos_resultantes.txt` | `sha256sum -c` |
| A3 | `ruff check packages tests scripts`: limpio | CI o local |
| A4 | Suite completa: las 1956 de la base con **el mismo resultado que la base corrida en el mismo momento y entorno**, más 6 nuevas que pasan. Sin las 3 pruebas sensibles al entorno (R11: reloj entre 00:00 y ≈ 05:45 UTC; R13: límite de 10 s en una máquina lenta) eso es **1962/1962**, como en `E9_*` | JUnit más `herramientas/comparar_suites.py`; `reproducir.sh completo`, paso 7; `evidencia/E12_*` y `E25_*` |
| A5 | Las 6 pruebas nuevas **fallan con el motor de 72ffae5** y pasan con el parche | `reproducir.sh rapido`, paso 3 |
| A6 | Mutantes: 0 vivos | `reproducir.sh rapido`, paso 5 |
| A7 | El workflow `ci.yml` de GitHub en verde | Nunca corrió (el propio archivo dice «REQUIRES VALIDATION»). Si falla por causas ajenas al parche, comparar con una corrida sobre la base |
| A8 | Revisión humana del diff (`parche/diff_legible_motor_con_funciones_completas.diff`) | Aprobación en el PR |

## 3. Reversión
- **Antes de fusionar:**
  - cerrar el PR y borrar la rama `fix/backtest-order-hygiene-d1-d3`;
  - la rama base no cambia.
- **Después de fusionar:**
  - `git revert <commit del parche>` en una rama nueva y un PR de reversión. No se reescribe la historia;
  - el revert devuelve exactamente los blobs de `72ffae5` para `engine.py` y `paper.py` y borra la prueba nueva;
  - comprobar con `git diff 72ffae5 -- packages/tia/src/tia/backtest/engine.py packages/tia/src/tia/execution/paper.py`, que debe salir vacío.
- **Disparadores de reversión:**
  - cualquier falla de la suite, distinta de la base, atribuible al motor;
  - una advertencia nueva («no stop level») en backtests donde antes no había y no se explique por piernas realmente sin stop;
  - una diferencia en el panel o la API de backtests que no corresponda a D1–D3.
- **Estado persistido:** no hay migraciones ni cambios de esquema; revertir no requiere tocar la base de datos.
  - Los backtests guardados después del parche quedan con resultados del motor corregido. `BacktestRepository.save` hace upsert por `run_id`, y `run_id` no incluye la versión del motor (riesgo R4 del informe).

## 4. Qué cambia para el resto del sistema al fusionar
- **Backtests:** sus resultados cambian siempre que haya rechazos, llenados parciales o movimientos de break-even o trailing. Eso es el arreglo, no un efecto colateral. El mismo `run_id` puede quedar con un resultado distinto al anterior (R4).
- **API `/backtests` y panel:** la lista `warnings` puede incluir la advertencia nueva «… bars held a position with no stop level …», y entonces `is_reliable` pasa a falso.
- **Sesión en vivo, papel en tiempo real, market making, T-papel:** **sin cambios**. No usan `BacktestEngine._request_exit` ni `_sync_protective_stop`; `resting_orders()` es un método nuevo de solo lectura.
- **Seguridad y operación:** no se toca `validada_para_operar`, la configuración, las credenciales ni el despliegue. La CI no despliega (`ci.yml`).

## 5. Seguimientos propuestos (no incluidos en el parche)
1. **R4:** agregar a `BacktestConditions` una versión del motor (por ejemplo `engine_version`) y usarla en `run_id`, para que un resultado guardado diga con qué motor se calculó.
2. **Protección de la rama base:** exigir PR y CI verde antes de fusionar. Hoy la única rama no tiene protección.
3. **Tolerancia del nivel del stop:** alinearla entre backtest y vivo. El backtest compara con una tolerancia relativa de 1e-9 × precio y el vivo con una absoluta de 1e-9; con precios de BTC ambas son menores que el tick, sin efecto práctico.
