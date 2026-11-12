# Matriz de revisión de los parches (revisión independiente, 2026-10-22)

- **Origen:** los parches se tomaron de la entrega v2 (`entrega_integracion_D1_D3_v2_2026-10-22.zip`, `793e8d6a…`), después de verificar su suma externa y sus 82 sumas internas (`registro/01_verificacion_entrega_v2.txt`).
- **Cómo se revisaron:** leyendo cada diff completo, con pruebas dirigidas y con sondas que solo miden.
- **Veredictos posibles:**
  - **Correcto** — se integra tal cual;
  - **Corregido** — tenía un defecto; se integra la versión corregida;
  - **Opcional** — mejora, sin defectos, no obligatoria.

## Parche 01 — D1–D3 y pruebas definitivas (`1944f433…`). Veredicto: **Correcto**
| Comprobación | Resultado | Evidencia |
|---|---|---|
| Hash = declarado; aplica limpio sobre `72ffae5` | Sí | `registro/01`, `evidencia/R7_*` |
| `engine.py` y `paper.py` resultantes = los verificados en SIM1 y en la entrega anterior | Sí (`85965ec5…`, `05569d16…` tras 01) | `R7_*` |
| Corrige D1: ids nuevos por barra (cierres) y por colocación (stops) | Sí, por código | Diff; M1 y M2 detectados |
| Corrige D2: el stop sigue al nivel, sin recolocaciones de más | Sí | M3 y M9 detectados |
| Corrige D3 en sus tres capas | Sí | M4, M5, M6 y M8 detectados |
| No debilita reglas de ejecución | Sí, nada se debilita: el cierre sigue siendo reduce-only, el stop se cancela antes del cierre y no se recoloca sobre un cierre en curso, un resto parcial se cancela en lugar de crecer la posición. Ninguna orden nueva abre exposición | Lectura del diff (`MATRIZ_REVISION`, este archivo); `paper.py` sigue rechazando un reduce-only que abriría (`_reduces`) |
| Las 8 pruebas fallan con el motor original y pasan con el parche | 8/8 fallan por `AssertionError`; 8/8 pasan | `M_pruebas_D1_D3_contra_original_v2_mismo_archivo.txt`; reproducción, paso 3 |
| Mutantes | 10, 0 vivos. M10 (cierre sin `reduce_only`) se detecta solo por la cobertura de los escenarios, no por una invariante | `M_mutantes_D1_D3_v3.*`, `MATRIZ_MUTANTES.md` |
| Cambia resultados (esperado) | Sí: en la API real, con el mismo pedido, 13 operaciones con el motor de 72ffae5 frente a 12 con el parche | `R5_compat_resumen.txt` |
| Observación fuera de alcance | Los stops protectores no se envían como reduce-only. Es así desde la base, no lo introduce 01. Con el motor actual no es alcanzable, porque el stop se cancela antes del cierre | Lectura de código |

## Parche 02 — trazabilidad. Veredicto: **Corregido** (`02` original `32a42a5d…` → `02v3` `d5c90091…`)
| Comprobación | 02 original | 02v3 corregido | Evidencia |
|---|---|---|---|
| Hash = declarado; aplica limpio sobre 01 | Sí | Sí (hash nuevo) | `registro/01`, `R7_*` |
| `run_id` distingue otra **versión** del motor | Sí | Sí | Pruebas; T6 detectado |
| `run_id` distingue otro **código** del motor sin versión nueva | Sí | Sí | T4 y T9 detectados |
| La huella cubre todo el código que corre un backtest | Sí: los 57 módulos `tia.*` cargados están en los 10 subpaquetes hasheados | Igual | Comprobación de módulos cargados (§2 del informe) |
| `run_id` distingue otros **datos** con el mismo nombre de dataset | Sí | Sí | T3 detectado |
| `run_id` distingue otros **instrumentos** y otro conjunto de estrategias | Sí | Sí | `universe_digest`; T7 detectado |
| Todos los campos de `BacktestConfig` entran en el `run_id` | Sí: 27 de 27 (24 por `digest()`, 3 explícitos) | Igual | Comprobación de campos (§2 del informe) |
| **Impide sobrescrituras incompatibles** | **No del todo.** Con la misma procedencia registrada y números distintos (entorno o pieza sustituida), **sobrescribía en silencio**: 9 operaciones reemplazadas por 8 bajo el mismo `run_id` | **Sí:** lo rechaza y conserva el primer resultado | `R1_*` (defecto), `R3_*` (corregido), `R2_*` (la prueba nueva falla con el 02 original) |
| Re-correr lo mismo reemplaza solo a sí mismo | Sí | Sí, también con un ratio NaN (SQLite lo guarda como NULL) | Pruebas; T14 detectado |
| No altera resultados numéricos | Sí | Sí: paridad con E1, mismas huellas que v2 y E17 en dos entornos | `P_paridad_v3_*` |
| Registros históricos | Probado con una fila simulada | **Probado con la API real de 72ffae5:** la fila vieja queda intacta (`engine_version` null), la API vieja la sigue leyendo, el mismo pedido da otro `run_id` y una re-corrida se reemplaza solo a sí misma | `R5_compat_*` |
| Sin migración | Sí: la columna JSON `conditions` existe en la migración 0007 | Igual | `CI_alembic.txt` |
| Mutantes | 12, 0 vivos, 1 equivalente | 14, 0 vivos, 1 equivalente (T13 y T14 nuevos, detectados) | `R4_mutantes_trazabilidad_v2.*` |
| Comentario de código | Sobrestimaba lo que cubre el id («everything that decides the numbers») | Dice qué cubre el id y qué no | `R6_diferencia_02_original_vs_corregido.diff` |

**Causa del defecto.**
- El guardado del 02 original solo comparaba la procedencia **registrada**.
- La procedencia no puede registrar todo lo que cambia los números: versiones de numpy o Python en un redespliegue sin versiones fijadas (la CI hoy resuelve 3 paquetes distintos a los fijados), o una pieza del motor sustituida por quien lo llama.

**Corrección mínima.**
- Bajo el mismo `run_id` y la misma procedencia, `save` compara los números guardados (`bars`, `trades`, `total_return_pct`, `max_drawdown_pct`, `sharpe`, `equity_curve`) y rechaza si difieren.
- Son +30 líneas en `repositories.py`, 2 pruebas y 2 mutantes nuevos. El comentario de `engine.py` y `ARCHITECTURE.md` se corrigieron.

## Parche 03 — pruebas sensibles al entorno (`0be65ea6…`). Veredicto: **Correcto (opcional, recomendado)**
| Comprobación | Resultado | Evidencia |
|---|---|---|
| Hash = declarado; aplica limpio sobre 01+02v3 | Sí | `R7_*` |
| Modifica **solo pruebas** | Sí: 3 archivos en `tests/integration/`, +45 −13 | `ARCHIVOS_MODIFICADOS.txt` |
| No relaja nada | Quita líneas de anclaje, una aserción vacía (`… or True`) y dos `pytest.skip`. Agrega 4 aserciones. No toca ningún tiempo límite | `R8_parche03_lineas_quitadas.txt` |
| No oculta errores del producto | En producción no se da ninguna de las dos condiciones: la sesión en vivo usa `SystemClock`, sondea cada 5 s y reconstruye el día con el mismo reloj de pared; el papel en tiempo real sondea cada 10 s. Un intervalo de 0 existe solo en los ayudantes de prueba | `api/state.py` (líneas 2280–2320 y 2477); `live.py:302` |
| Mejora la estabilidad | Con el reloj fijado en la franja crítica, los 3 módulos fallan 2–3 pruebas por corrida en la base y 0 en la integración (salvo R19, abajo). La de persistencia baja de 25–31 s a 3–4 s y pasa siempre | `R9_*`, `R10_*`, `B3_*` de v2 |
| No arregla todo | Bajo carga de CPU ≈5, otra prueba con el mismo patrón (`test_partial_fills_and_fees_rebuild_identically_however_often`) falló en la base (2 de 4) y en la integración (1 de 4). Es preexistente (R19) y **no** lo cubre 03 | `R10_intermitencia_bajo_carga.txt` |

## Parche 04 — CI con versiones fijadas (`8d396356…`). Veredicto: **Opcional (decisión del propietario)**
| Comprobación | Resultado | Evidencia |
|---|---|---|
| Qué cambia | `constraints/ci-py311.txt` (74 versiones, las verificadas) y dos líneas de `ci.yml`: `pip install -c constraints/ci-py311.txt …` y `cache-dependency-path` | Diff |
| YAML válido | Sí (`yaml.safe_load`) | `CI_parche04_yaml.txt` |
| El paso «Install» del parche, ejecutado tal cual | 74 paquetes, idénticos a las restricciones | `CI_parche04_instalacion.txt` |
| No toca producto ni pruebas | Sí | Diff |
| Qué **no** se puede verificar sin una corrida real | El comportamiento de `actions/setup-python` con `cache: pip` y la imagen `ubuntu-latest` | Informe §4 |
