# Revisión técnica del parche D1–D3 del motor de backtest (Trader-IA)

**Fecha:** 2026-10-21 (23:17Z – cierre en `registro/99_*`).
**Alcance:** auditoría y preparación de la integración en copias aisladas.
- Sin commits, push, despliegues ni trading.
- El repositorio original no se modificó (`registro/00_*` y `registro/99_*`).

## 1. Veredicto: **APTO PARA REVISIÓN**
- El parche del motor de SIM1 se aplica **sin cambios** sobre `72ffae5`.
- Corrige D1, D2 y D3, y cada corrección queda demostrada por una prueba que falla con el código original y pasa con el parche.
- La suite completa pasa (1962/1962 en la corrida limpia de las 23:36Z) sin alterar ningún resultado de la base.
- En las 4 corridas completas, la integración da el mismo resultado que la base, prueba a prueba (§5, R11 y R13).

**Un hallazgo exigió cambiar las pruebas (no el motor).** Las 4 pruebas de regresión de SIM1 **no detectaban 4 de las 8 piezas del parche**:
- el id por barra de la salida (mitad de D1);
- la cancelación del resto en plano y la red de seguridad (dos capas de D3);
- la advertencia de pierna sin stop.

La entrega incluye una versión 2 de las pruebas (6 pruebas) que detecta las 8 por comportamiento.

## 2. Identidad de la base
| Elemento | Valor |
|---|---|
| Repositorio original | `/home/user/Trader-IA`, rama `claude/algo-trading-simulation-platform-ngf7xo`. En GitHub es la **única** rama, sin protección ni PRs |
| Commit base | `72ffae5d2698440c8f1afaff12e07bd8adde66fb` (HEAD = origin), 0 cambios, 0 stash (`registro/00_*`) |
| `engine.py` en la base | blob `1a1ba3d15b21…`; sha256 `547109460bb5734ab7b108dc9387fca802e69b29cc8e74c262b80bdc55533ea4`. Es el mismo hash que E1 registró como «sin cambios» |
| `paper.py` en la base | blob `a6212245a7c7…`; sha256 `f5e0cb87a98d951ada347dc183968c59cc914cd52ac5cdaddf574f7264b7ff00` |
| Entrega SIM1 | `entrega_SIM1_2026-10-21.zip`, sha256 `73cdb790f1741116f5642c4911da12bab471da9caa543ed7f778bb63ebe37c8d` (el informado), `unzip -t` sin errores, `SHA256SUMS` 61/61 OK, 0 archivos fuera del manifiesto (`registro/01_*`) |
| Parche SIM1 | `parche_motor_D1_D3.diff`, sha256 `ca23679d…`. Sus líneas `index` nombran exactamente los blobs de `72ffae5`; `git apply --check` limpio (`registro/02_*`) |
| Resultado del parche | `engine.py` `85965ec5…` y `paper.py` `05569d16…`: idénticos a los congelados en `HUELLAS.txt` de SIM1 y a la copia de trabajo de SIM1 (`registro/03_*`) |

**Límite.** `SHA256SUMS` va dentro del ZIP: su autenticidad descansa en el hash del ZIP que reportó SIM1, sin firma ni ancla externa (D-G4/R-5 siguen pendientes).

## 3. Hallazgos D1–D3
Las líneas se refieren a `engine.py` original (O) y parcheado (P).

### D1: reintentos de salida y de stop suprimidos como duplicados
- **Causa raíz.**
  - `PaperExecutionProvider.submit_order` devuelve la orden existente si el `client_order_id` ya se usó (idempotencia correcta).
  - El motor construía ese id sin la barra ni el intento:
    - salida: `signal_id=f"exit:{reason}:{leg.signal_id}"` (O:807);
    - stop: `signal_id=f"{leg.signal_id}:protective"`, con la misma cantidad (O:863).
  - **Salida.** Tras un rechazo, el reintento recibía la orden RECHAZADA como «duplicado»: `is_terminal and not fills`, y vuelve a no hacer nada (O:827). El cierre por regla, por ejemplo el stop por tiempo, no se ejecutaba nunca.
  - **Stop.** Tras una cancelación o un rechazo, re-colocar el stop con la misma cantidad devolvía la orden muerta: la posición quedaba **sin stop**.
- **Corrección.**
  - Id de salida con la hora de cierre de la barra: `f"{exit_key}:{candle.close_time.isoformat()}"` (P:833).
  - Id de stop con un contador de colocaciones por corrida: `:protective:{self._stop_placements}` (P:922). Se reinicia en cada `run()`, así que es determinista.
  - La sesión en vivo ya usaba un id por barra (`runtime/live.py`: `protective:{symbol}:{run_id}:{bars}`).
- **Pruebas** (fallan con O y pasan con P):
  - `test_stops_and_exits_survive_rejections`: con O, «9 bars without a stop»;
  - `test_a_rejected_close_is_sent_again_and_closes` (nueva): con O, «no rejected time stop was ever sent again: the retry was suppressed as a duplicate». Usa un proveedor que rechaza el primer intento de cada cierre.
- **Casos límite.** En una misma barra no puede haber dos pedidos de salida para la misma pierna, porque `exit_pending` lo impide; así, el id por barra no puede chocar. El `intent_id` de la salida ya incluía la barra en O; solo cambia el `client_order_id`.

### D2: el stop del libro no seguía el break-even ni el trailing
- **Causa raíz.**
  - `tighten_stop` actualiza `leg.stop_price` (O:393–406).
  - Pero `_sync_protective_stop` solo comparaba la cantidad cubierta (O:855): si el tamaño no cambiaba, la orden seguía al nivel viejo.
  - El informe mostraba pérdidas «acotadas» por un stop que no estaba en el libro.
- **Corrección:** `same_size and same_level`, con una tolerancia relativa de 1e-9 × precio (P:905–909). Es lo mismo que hace la sesión en vivo (`live.py`: `same_level`, con una tolerancia absoluta de 1e-9).
- **Acoplamiento.** D2 **depende de D1**: sin el id por colocación, re-colocar el stop al nuevo nivel con el mismo tamaño también chocaría como duplicado.
- **Prueba:** `test_the_stop_in_the_book_follows_the_leg`. Con O: «leg stop 62584.94, order in the book 62608.52».
- **Re-colocación excesiva:** no la hay. Sin rechazos, las colocaciones de stop son iguales a los cambios reales de (pierna, tamaño, nivel): 51 = 51 (`evidencia/E6_*`).

### D3: posición trabada esperando un cierre ya terminado
- **Causa raíz.**
  - El cierre es una orden reduce-only con el tamaño de la pierna **al pedirlo** (O:810 y 817).
  - Si quedaba un resto de la entrada parcial en el libro, se llenaba en la misma barra que el cierre. El cierre terminaba FILLED, pero con posición restante.
  - `exit_pending` seguía puesto: `_sync_protective_stop` no re-colocaba el stop (O:845), las reglas de salida no se evaluaban, y la pierna quedaba **sin stop ni salida para siempre**. En E1, eso aparecía como round trips de más de 2000 barras.
  - **Variante en plano:** si el stop cerraba la pierna con un resto todavía en el libro, ese resto abría después una posición «fantasma», sin señal de origen ni stop. El mutante M5 la muestra: «position for '' after it closed».
- **Corrección, en tres capas:**
  1. al pedir el cierre, cancelar los restos de entrada (no reduce-only, no STOP) del símbolo (P:820), como hace `live._close_position`;
  2. en plano, cancelar los restos con algo ya llenado (P:877). Una entrada nueva, sin llenar, se respeta;
  3. red de seguridad: si el cierre terminó y queda posición, se libera la pierna para re-colocar el stop y volver a pedir el cierre (P:887).

  Las capas 2 y 3 son defensas propias del backtest; no tienen un equivalente literal en la sesión en vivo.
- **Pruebas:**
  - `test_partial_fills_leave_no_untracked_or_stuck_position`, con los invariantes:
    - la posición de la venue es igual a la pierna seguida;
    - nada se agrega mientras el cierre está en vuelo;
    - una señal cerrada no reabre;
    - no queda ninguna pierna esperando un cierre terminado.
  - `test_a_close_that_leaves_position_is_released_and_retried` (nueva): cierres «immediate-or-cancel» que dejan posición.
  - Con O, ambas fallan con «still held, waiting on a close that is filled».
- **Casos límite revisados.**
  - Con una pierna abierta, el motor no puede tener en el libro la entrada de **otra** señal: la reversión cierra y hace `continue`, otra entrada del mismo sentido se suprime y, si hay `pending`, se saltea. Por eso la cancelación de la capa 1 solo alcanza el resto de la propia pierna.
  - Con cierres IOC, cada reintento tarda 2 barras: la red libera al final de la barra y la regla de salida vuelve a pedir el cierre en la siguiente. El residuo se cierra en varios pasos; es correcto, pero lento con una venue adversa (`evidencia/` y la sonda IOC).

### Advertencia nueva (falla segura)
- `bars_with_leg_and_no_stop` cuenta las barras con posición sin nivel de stop y sin cierre en vuelo. Si es mayor que 0, agrega una advertencia y `is_reliable` pasa a falso (P:675–680).
- **Prueba:** `test_a_leg_without_a_stop_level_is_reported`. Con O no aparece la advertencia.

## 4. ¿Las pruebas detectan realmente cada defecto? (mutantes)
Cada fila es el motor parcheado con **una** pieza revertida (`herramientas/mutantes.py`).

| Mutante | Pruebas SIM1 (4) | Pruebas v2 (6) |
|---|---|---|
| M1 D1 salida sin id por barra | **sobrevive** | muere: `rejected_close_is_sent_again` |
| M2 D1 stop sin id por colocación | muere | muere: `survive_rejections` |
| M3 D2 sin comparar nivel | muere | muere: `stop_in_the_book_follows` |
| M4 D3 sin cancelar el resto al salir | muere **solo por un contador** | muere por comportamiento: «the close filled in full and … is still held» |
| M5 D3 sin cancelar el resto en plano | **sobrevive** | muere: «position for '' after it closed» |
| M6 D3 sin red de seguridad | **sobrevive** | muere: «waiting on a close that is expired» (IOC) |
| M7 sin la advertencia | **sobrevive** | muere: `leg_without_a_stop_level_is_reported` |
| M8 D3 sin ninguna capa | muere | muere |

Evidencia: `evidencia/E4_*` (SIM1), `E13_*` (pruebas finales, sha `f10baa10…`). **Mutantes vivos con las pruebas finales: ninguno.**

## 5. Pruebas ejecutadas (resultados observados)
Entorno limpio (`registro/04_*`):
- `python3.11 -m venv`, más la instalación documentada de la CI: `pip install -e ".[api,db,postgres,redis,llm,dev]"`.
- Diferencias con el entorno de SIM1: anthropic 2.0.0→2.1.0 y fastapi 0.158.2→0.159.1 (`registro/04b_*`).

| Prueba | Comando | Resultado |
|---|---|---|
| Suite completa en la base 72ffae5 | `PYTHONPATH=packages/tia/src python -m pytest tests -q -p no:cacheprovider --junitxml=…` | **1956 / 1956 pasan** (`E7_*`). Es la línea base documentada |
| Suite completa, parche + pruebas SIM1 | ídem | **1960 / 1960 pasan** (`E8_*`). Es el resultado informado por SIM1 |
| Suite completa, árbol de integración (parche + pruebas v2) | ídem | **1962 / 1962 pasan** (`E9_*`) |
| Conjuntos de pruebas | comparación del JUnit | Ninguna prueba de la base falta ni cambia de resultado; solo se suman las nuevas (`E12_*`) |
| Pruebas v2 contra el motor original | `pytest tests/unit/test_backtest_order_hygiene.py` | **6 / 6 fallan**, todas por aserción (`E14_*`) |
| Pruebas v2 contra el parcheado | ídem | 6 / 6 pasan (dentro de `E9_*`) |
| Mutantes | `herramientas/mutantes.py` | 8 / 8 mueren (`E13_*`) |
| Pruebas que dependen del reloj | `herramientas/con_reloj.py` (time-machine, entorno descartable) con el reloj fijado entre 00:30Z y 23:59Z | Idéntico en la base y en la integración. De 00:30 a 05:30Z, 1 falla y 1 se omite; de 05:55 a 23:59Z pasan las dos (`E20_*`, `E24_*`) |
| Comparación prueba a prueba, base contra integración, en las 4 corridas completas (23:36Z, 00:12Z, 00:36Z, 02:01Z) | `herramientas/comparar_suites.py` | En las 4: **0 pruebas de la base con otro resultado** en la integración y las 6 nuevas pasan. Las únicas pruebas de la base que no pasan son las 3 sensibles al entorno, en ambos árboles (`E25_*`) |
| Lint de la CI | `ruff check packages tests scripts` | limpio en la base y en la integración (`E16_*`) |
| mypy (informativo; la CI no lo corre) | sobre `engine.py` y `paper.py` | los mismos 15 errores preexistentes en la base y en la integración; ninguno nuevo (`E16_*`) |
| Interfaces públicas | `herramientas/firmas.py` | única diferencia: `PaperExecutionProvider.resting_orders()` nuevo, de solo lectura (`E11_*`). Nadie en el repositorio hereda de `BacktestEngine` ni llama a sus métodos privados (`E10_*`) |
| Sintéticas: look-ahead, rechazos, parciales, determinismo | `verificacion_motor.py` de SIM1 (generador de E1) | V1, V2 (prefijo), V3 (futuro alterado), V6 (parciales al 90 %) y DET bien; V1, V6 y la huella DET son idénticos a SIM1 (`E15_*`) |
| **Datos reales:** paridad con E1 y salida completa | `herramientas/paridad_completa.py` (BTCUSDT 1h de E1) | Ver §5.1 |

**Separación de evidencia.**
- Sintéticas: las pruebas D1–D3 (velas fijas del repositorio, `data/fixtures`), los mutantes y `verificacion_motor.py`.
- Datos reales: solo la paridad del §5.1. Usa BTC 1h de E1, ya consumido, sin cálculo de métricas de decisión; no es un experimento confirmatorio.

### 5.1 Paridad con datos reales: qué se compara exactamente
- **Lista agregada de round trips** (`e1_comun.round_trips`), comparada como JSON con la registrada por E1 (sha `cc52fbf8…`, que coincide con el `SHA256SUMS` de E1).
  - Campos: entrada, salida, dirección, nocional, neto %, bruto %, comisiones %, barras, razón de salida, confianza, régimen y piezas.
- **No** se comparan contra E1 la curva de equity, las métricas, los contadores de decisiones ni el detalle de cada `ClosedTrade`: E1 no los registró.
- Esas salidas se resumen en huellas SHA-256 y se comparan **entre dos entornos independientes**: el de la CI y el de E1.
- **Igualdad de operaciones no es igualdad de resultados económicos de la cuenta.** Por eso la equity y las métricas se verifican aparte, y solo entre entornos.

| Config. | Round trips = E1 (entorno CI / entorno E1) | n | Operaciones completas | Equity | Métricas | Decisiones | Igual entre entornos |
|---|---|---|---|---|---|---|---|
| P1 | sí / sí | 629 de 629 | `1418ebccb21c…` | `0ebbe7234446…` | `568ad0f3185f…` | `b3fce5a9a721…` | sí |
| P2 | sí / sí | 139 de 139 | `075c89b57b43…` | `d03f117df87a…` | `74a2dc8b4c69…` | `57968d388770…` | sí |
| P3 | sí / sí | 185 de 185 | `60583835ba17…` | `46c01be279da…` | `ea61c6b7b66b…` | `db697b3c8f98…` | sí |
| S1 | sí / sí | 795 de 795 | `8b153452ef81…` | `ad1013dcc713…` | `fca2fa53eb76…` | `0f949974d087…` | sí |

- **Entornos:** CI (pydantic 2.14.1) y E1 (pydantic 2.13.5, requisitos con hash de E1), ambos con numpy 2.4.6. El motor es el del árbol de integración (`85965ec5…`).
- **Higiene en los cuatro:** 0 salidas terminadas con posición restante, 0 barras sin stop, 0 advertencias. Restos de entrada cancelados al salir: P1 4, P3 2, S1 3.
- **Evidencia:** `evidencia/E17_*` y `E18_*`.

## 6. Riesgos residuales y limitaciones
| # | Riesgo | Severidad | Mitigación / estado |
|---|---|---|---|
| R1 | Los resultados de backtest **cambian** al integrar (el arreglo). Cualquier informe anterior hecho con el motor original no es comparable | Media | Esperado. E1, SIM1 y lo posterior ya usaron el motor corregido. Documentar en el PR |
| R2 | La advertencia nueva puede volver «no confiables» corridas con piernas realmente sin stop, en la API y en `experiment.py` | Baja | Es el comportamiento buscado (falla segura). Ninguna prueba existente cambió |
| R3 | Las capas 2 y 3 de D3 son propias del backtest; la sesión en vivo no las tiene igual | Baja | Probadas por comportamiento (M5 y M6). Revisar si la sesión en vivo necesita algo equivalente queda fuera del alcance |
| R4 | `run_id` no incluye la versión del motor y `BacktestRepository.save` hace upsert por `run_id`: re-correr un backtest guardado sobrescribe el resultado viejo sin rastro de qué motor lo produjo | Media | No lo cambia el parche (fuera de alcance). Seguimiento propuesto en `PLAN_INTEGRACION.md` §5 |
| R5 | Con cierres IOC adversos, cada reintento tarda 2 barras | Baja | Correcto, pero lento; el paper actual no es IOC |
| R6 | Tolerancia del nivel: relativa 1e-9 × precio (backtest) contra absoluta 1e-9 (vivo) | Muy baja | Por debajo del tick |
| R7 | El workflow de GitHub `ci.yml` **nunca corrió** (lo dice el propio archivo) | Media | La suite se corrió localmente con el mismo comando y la misma instalación. El primer PR será su primera corrida real (A7) |
| R8 | Sin ancla externa: la autenticidad de las entregas descansa en hashes reportados en el chat | Media | D-G4/R-5 pendientes del propietario |
| R9 | **No verificado:** el frontend (`npm`), las migraciones (`alembic upgrade head`) y la sesión en vivo con una venue real | — | El parche no toca esos componentes, pero no se ejecutaron |
| R11 | **Dos pruebas de la base dependen del reloj.** `test_five_restored_entries_for_the_symbol_refuse_the_sixth_after_the_restart` falla y `test_a_day_that_hit_the_loss_limit_still_refuses_entries_after_a_restart` se omite entre las **00:00 y ≈ 05:45 UTC** (fallan a las 05:30, pasan a las 05:55), **con o sin el parche**. Comparan el día del reloj de pared con el de la serie de velas falsa, anclada en `now` | Media: la CI es intermitente en esa franja | No es del parche: idéntico en ambos árboles (`E20_*`, `E24_*`, `E25_*`). El criterio A4 compara prueba a prueba con la base. Corregir esas pruebas, aparte |
| R13 | **Prueba con un tiempo límite fijo.** `test_adverse_recovery::test_rejects_and_partials_over_hundreds_of_bars_keep_the_invariants_and_the_record_whole` exige vaciar las escrituras de persistencia (SQLite) en 10 s. Antes del reinicio del contenedor tardaba 4–7 s y pasaba; después tardó 16–57 s y falló en la base (0 de 6) y en la integración (1 de 6 pasó) (`E21_*`, `E22_*`) | Media: CI intermitente en máquinas lentas | No es del parche. Con cobertura (`E23_*`), durante esa prueba `engine.py` no ejecuta ninguna línea y de `paper.py` solo corre la línea del `def resting_orders` (la definición de la clase), nunca su cuerpo. Revisar ese límite de tiempo, aparte |
| R12 | **Dependencias sin fijar.** La instalación de la CI resuelve versiones nuevas: en una hora pasó de python-dateutil 2.9.0.post0 a 3.0.0 (`E19_*`) | Media | No afectó a estas pruebas (`E20_*` corre con 3.0.0). Recomendable un archivo de bloqueo para la CI, aparte |
| R10 | Las corridas de 3 h de SIM1 (DEV y OOS) **no se repitieron**: no hacía falta. La paridad del §5.1, las suites, los mutantes y la reproducción puntual de SIM1 (P3 DEV y OOS idénticos byte a byte, desde una extracción limpia) bastan para el parche | — | — |

**Corrección de un registro de SIM1.** La evidencia `S1b_regresion_v2_contra_motor_original.txt` se generó con la prueba **antes** de una corrección cosmética de ruff:
- archivo `a942bf0e…`, un guion largo en el docstring;
- la entregada es `685cf4ec…`.

Aquí se repitió la corrida con la prueba exacta de SIM1 contra el motor original: 4/4 fallan (`E3_*`).

## 7. Artefactos
Ver `LEEME.md` y `SHA256SUMS`. Ubicación en el disco de trabajo:
`/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_parche_D1_D3_2026-10-21/`.

## 8. Plan
Ver `PLAN_INTEGRACION.md`: pasos exactos, criterios A1–A8 y reversión. **No se ejecutó.**
