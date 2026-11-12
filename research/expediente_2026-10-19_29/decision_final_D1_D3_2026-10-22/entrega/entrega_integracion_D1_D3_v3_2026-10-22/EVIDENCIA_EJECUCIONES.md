# Ejecuciones de esta revisión: comandos, códigos de salida y resultados (2026-10-22, 16:06–17:00 UTC)

## Convenciones
- **Árboles:** `fin_base` = `72ffae5`; `fin_obligatoria` = 01 + 02v3; `fin_completa` = 01 + 02v3 + 03. Son clones nuevos con `git clone --no-local` desde el original, que solo se lee.
- **Entornos:**
  - `venv_A` / `venv_B`: restricciones `entorno/ci-py311.txt`, con `pip freeze` idéntico;
  - `venv_T`: `venv_A` más time-machine 3.5.1;
  - `venv_CI_libre`: instalación **sin restricciones**, como `ci.yml` hoy;
  - `venv_CI_04`: el paso «Install» del parche 04.
- **Suite:** `herramientas/correr_suite_ci.sh <árbol> <python> <txt> <xml>` corre `PYTHONPATH=packages/tia/src python -B -m pytest tests -q -p no:cacheprovider --junitxml=…`, el comando de la CI más JUnit.

## Tabla
| # | Qué | Comando (resumido) | Código | Resultado | Evidencia |
|---|---|---|---|---|---|
| 1 | Integridad de la entrega v2 | `sha256sum -c *.zip.sha256`; `sha256sum -c SHA256SUMS` | 0 | ZIP `793e8d6a…` OK; 82/82; hashes de 01, 02 y 03 = declarados | `registro/01_*` |
| 2 | Cobertura de la procedencia | `python -I herramientas/cobertura_procedencia.py fin_obligatoria` | 0 | 57/57 módulos dentro de la huella; 27/27 campos de config en el `run_id` | `evidencia/R11_*` |
| 3 | Defecto de 02: misma procedencia, otros números | `python -I herramientas/sonda_misma_procedencia.py <árbol con 02 original>` | 0 | **ACEPTADO** (sobrescritura silenciosa: 9 operaciones → 8) | `evidencia/R1_*` |
| 4 | El mismo caso con 02v3 | ídem sobre `corr` | 0 | **RECHAZADO**; se conserva el primero | `evidencia/R3_*` |
| 5 | La prueba nueva contra el 02 original | `pytest tests/integration/test_backtest_provenance.py` (v3) sobre 01+02 original | 1 | 13 pasan, 1 falla (`DID NOT RAISE ValueError`) | `evidencia/R2_*` |
| 6 | Pruebas de trazabilidad y D1–D3 en 02v3 | `pytest -o addopts="" tests/integration/test_backtest_provenance.py tests/unit/test_backtest_order_hygiene.py` | 0 | 22 pasan | Salida en la sesión; repetida en la reproducción limpia |
| 7 | Mutantes de trazabilidad v2 (14) | `python herramientas/mutantes_traza_v2.py corr …` | 0 | 13 de 13 no equivalentes detectados; T10 equivalente; 0 vivos | `evidencia/R4_*` |
| 8 | Mutantes D1–D3 (10) | `python herramientas/mutantes_v2.py fin_obligatoria …` | 0 | 10 de 10 detectados | `evidencia/M_mutantes_D1_D3_v3.*` |
| 9 | Compatibilidad histórica con las API reales | `compat_historica.py` ×5: base escribe; corregido lee, escribe y re-corre; base lee | 0 (×5) | Fila vieja intacta y `engine_version` null; nuevo `run_id`; re-corrida idempotente; la API vieja lee las dos | `evidencia/R5_*` |
| 10 | Aplicación de los parches finales | `git apply --check` y `git apply` 01, 02v3, 03 sobre clones nuevos | 0 | Limpio; resultados = `corr` y `b3` | `evidencia/R7_*` |
| 11 | Suite base (venv_A) | `correr_suite_ci.sh fin_base venv_A` | 0 | **1956 / 1956**, 0 fallan, 0 errores, 0 omitidas, 319,9 s | `evidencia/S_suite_base_venvA.*` |
| 12 | Suite obligatoria (venv_B) | `correr_suite_ci.sh fin_obligatoria venv_B` | 0 | **1978 / 1978**, 376,3 s | `evidencia/S_suite_obligatoria_venvB.*` |
| 13 | Suite completa (venv_A) | `correr_suite_ci.sh fin_completa venv_A` | 0 | **1978 / 1978**, 365,9 s | `evidencia/S_suite_completa_venvA.*` |
| 14 | Comparación prueba a prueba | `comparar_suites_v2.py base.xml {obligatoria,completa}.xml [--corregidas]` | 0 / 0 | Ninguna falta; 22 nuevas pasan; 0 cambios de resultado; las 3 sensibles pasan en la completa | `evidencia/S_comparacion_*` |
| 15 | Instalación como la CI de hoy, sin restricciones | `pip install -e ".[api,db,postgres,redis,llm,dev]"` | 0 | 74 paquetes; **3 distintos** a los fijados | `entorno/freeze_CI_libre.txt`, `deriva_*.diff` |
| 16 | Suite base con venv_CI_libre | `correr_suite_ci.sh ci_base venv_CI_libre` | 0 | **1956 / 1956**, 346,9 s | `evidencia/S_suite_base_CI_libre.*` |
| 17 | Suite completa con venv_CI_libre | `correr_suite_ci.sh ci_completa venv_CI_libre` | 0 | **1978 / 1978**, 391,7 s; comparación sin regresiones | `evidencia/S_suite_completa_CI_libre.*`, `S_comparacion_CI_libre.txt` |
| 18 | Lint como la CI | `ruff check packages tests scripts` (venv_A en los 3 árboles; venv_CI_libre en la completa) | 0 (×4) | Limpio | `evidencia/CI_ruff_alembic.txt` |
| 19 | Migraciones como la CI | `TIA_DATABASE_URL=sqlite:///./data/runtime/ci.db python -m alembic upgrade head` (base y final; venv_A y venv_CI_libre) | 0 (×3) | Versión 0007; `backtests.conditions` existe | `evidencia/CI_alembic.txt`, `CI_ruff_alembic.txt` |
| 20 | Trabajo `frontend` de la CI | `npm ci --no-fund --no-audit`; `npm run typecheck`; `npm run build` (Node 22.22.0) | 0 / 0 / 0 | Build de 63 módulos. Los parches no tocan `frontend/` | `evidencia/CI_frontend*.txt` |
| 21 | Parche 04: YAML | `yaml.safe_load(ci.yml)` | 0 | Válido; el paso Install usa `-c constraints/ci-py311.txt` | `evidencia/CI_parche04_yaml.txt` |
| 22 | Parche 04: paso Install tal cual | `pip install -c constraints/ci-py311.txt -e ".[…]"` en un venv nuevo | 0 | 74 paquetes = restricciones | `evidencia/CI_parche04_instalacion.txt` |
| 23 | Paridad con E1, motor v3 (2 entornos) | `python -I herramientas/paridad_e1_v2.py fin_obligatoria/packages/tia/src <código E1> …` | 0 / 0 | P1 629, P2 139, P3 185, S1 795 round trips; huellas = v2 = E17 | `evidencia/P_paridad_v3_*` |
| 24 | Clasificación de la paridad | `comparar_paridad_v2.py …` | 0 | 45 igualdades, 5 diferencias explicadas, 4 imposibles, **0 no explicadas** | `evidencia/P_paridad_v3_clasificada.*` |
| 25 | Módulos de B3 con reloj fijado (6 horas) | `con_reloj.py <hora> pytest <3 módulos>` | — | Base: 1–3 fallas por hora; completa: 0, salvo R19 bajo carga | `evidencia/R9_*` |
| 26 | Intermitencia bajo carga (4 repeticiones) | ídem, con la paridad y los mutantes corriendo (carga 1,3–5,2) | — | R19 (`test_partial_fills_and_fees_rebuild_identically_however_often`) falla con carga ≈5 en la base 2 de 4 y en la completa 1 de 4 | `evidencia/R10_*` |
| 27 | Estado del repositorio original y congelados, al cierre | Mismos comandos que `registro/00`; `herramientas/congelados.sh` | 0 | Idéntico al inicial; 8/8 manifiestos | `registro/99_*` |
| 28 | Reproducción desde la extracción limpia del ZIP v3 | `env -i … bash reproducir.sh <repo> <trabajo> completo <código E1>` | Ver registro externo | Ver `VERIFICACION_EXTRACCION_LIMPIA_v3.txt`, fuera del ZIP | — |
