# Fase E: suites reproducidas desde una extracción limpia (todo local; no es la CI)

**Entorno común:**
- Python 3.11.17.
- 74 paquetes fijados con `ci-py311.txt`; `pip freeze` sha256 `a1a96cac94471aac46ac7e5374846d0e3ffe93f046df198b71c95fec6869766e`.
- En la reproducción de v3r3, `reproducir.sh` crea un venv **nuevo** desde PyPI con esas restricciones, y su `freeze` coincide con el de referencia: 0 diferencias en `freeze_diferencias.txt`.
- Las suites finales usan el venv de referencia, con el mismo hash.

## Resultados
| Suite | Árbol | Comando | rc | Pruebas | Pasan / fallan / errores / omitidas | Duración (JUnit) | Carga | JUnit sha256 | Log sha256 |
|---|---|---|---|---|---|---|---|---|---|
| Base | `72ffae5` (extracción limpia de v3r3, `env -i`) | `correr_suite_ci.sh` de v3r3: `python -B -m pytest tests -q -p no:cacheprovider --junitxml` | 0 | **1956** | 1956 / 0 / 0 / 0 | 358,0 s | concurrente con la suite final v1 | `f3dd24a3…` | `8fde500a…` |
| 01 + 02v3 (A) | ídem | ídem | 0 | **1978** | 1978 / 0 / 0 / 0 | 408,6 s | ídem | `798058c2…` | `4dde8221…` |
| 01 + 02v3 + 03 | ídem | ídem | 0 | **1978** | 1978 / 0 / 0 / 0 | 385,8 s | ídem | `9a9a6201…` | `fdbcc480…` |
| Final v1: A + 05v2 + 03 + 04 + 06 | `b1ff3fe3…` (write-tree) | `PYTHONPATH=packages/tia/src python -B -m pytest tests -q -p no:cacheprovider --junitxml=ci-evidence/junit.xml` | 0 | **1985** | 1985 / 0 / 0 / 0 | 377,0 s | 3,1–3,9 (con la reproducción de v3r3) | `4f2d0cd0…` | `71a6c36b…` |
| Final v2: … + 06v2 | `92fee676…` | ídem | 0 | **1985** | 1985 / 0 / 0 / 0 | 395,1 s | 0,6–0,9 | `c8c4b23e…` | `71a6c36b…` |
| **Final v3: … + 06v3 (el propuesto)** | **`0477c6a2…`** | ídem | 0 | **1985** | 1985 / 0 / 0 / 0 | 404,8 s | 0,2–0,9 | `cdc413b3…` | `71a6c36b…` |

Hashes completos y archivos: `logs/E/` (`E1_v3r3_salidas/`, `E*_ci_evidence/`, `E*_pytest.txt`, `E*_suite_gate.log`). La salida de pytest con `-q` es idéntica en las tres suites finales, por eso tiene el mismo hash.

## Diferencias de conteo, investigadas
- **1956, 1978 y 1978 coinciden exactamente con v3r3.**
  - De la base a A se suman **22 pruebas nuevas**: 14 de trazabilidad y 8 de D1–D3, y todas pasan.
  - Ninguna prueba de la base falta ni cambia de resultado (`comparar_suites_v2.py`, en el log de la reproducción).
- **1985 = 1978 + 7.** La diferencia entre el árbol final y «completa» son **exactamente** las 7 pruebas de la guarda 05v2.
  - No falta ninguna prueba.
  - Todas las comunes tienen el mismo resultado.
- **No hay diferencias sin explicar.**

## Otras comprobaciones de la Fase E
| Comprobación | Resultado | Dónde |
|---|---|---|
| Reproducción completa de v3r3 desde una extracción limpia, con `env -i` y un HOME nuevo | **TERMINADA SIN DIFERENCIAS** (rc 0) | `logs/E/E1_reproduccion_v3r3_completo.log` |
| D1–D3 contra el motor ORIGINAL | 8/8 fallan por aserción | ídem, paso 3 |
| D1–D3 y trazabilidad con A | 8/8 y 14/14 | paso 4 |
| Paso 4b (R4c): 02v3 sin 01 | aplica, declara 1.1.0 sin D1–D3 y sus 14 pruebas pasan igual | paso 4b |
| Mutantes D1–D3 y de trazabilidad | 10 con 0 vivos; 14 con 0 vivos (1 equivalente) | paso 5 |
| Reloj fijado a 5 horas (con 03) | 2/2 en cada hora; persistencia 3/3 | paso 7 |
| Ruff (obligatoria y completa) | limpio | paso 6 |
| Ruff en el árbol final, como `ci.yml` (`packages tests scripts`) | **06 v1: 5 errores en `scripts/ci_gate.py`** → corregido en 06v2 y 06v3: limpio | `E2_final_suite_gate.log`, `E4_final_v3_suite_gate.log` |
| Alembic desde cero (base, completa y los tres finales) | rc 0 | pasos 8b, `E*_alembic.txt` |
| Paridad con E1 | mismas huellas que la evidencia | paso 9 |
| Gate 06v3 sobre la suite final | **pass**; guarda 7/7; `engine_version` 1.1.0 | `E4_final_v3_suite_gate.log` |
| Pruebas del gate (11 casos, veredicto fijado de antemano) | 06v2: 10/11 (**falla abierto** con otro intérprete) → 06v3: **11/11** | `evidence/E_gate/` |
| Prueba de R19 (`test_partial_fills_and_fees_rebuild_identically_however_often`) en estas 6 suites completas | pasó en las 6 (dato adicional; no cambia la clasificación de R19) | JUnits |
