# Guarda técnica contra una versión de motor falsa (parche 05, propuesta) — **no integrada**

- **Archivo nuevo:** `tests/integration/test_engine_version_contract.py`. No toca código de producción.
- **Parche:** `parche/05_propuesta_guarda_version_motor.patch`, SHA-256 `9fc829ad012534d86645ad9e715bc77a7abee69791514c8187bc51c7ceb8ba47`. El archivo de prueba tiene SHA-256 `ff1ad5402b41ccf8d6ee3da6d71c9404c98295972b75a3e203b307364d21bfa8`.
- **Independencia:** 05 es independiente de 01, 02v3, 03 y 04, que siguen congelados y sin cambios. Aplica con código 0 sobre la base, sobre 02v3 solo, sobre 01+02v3 y sobre la completa. Al revertirlo, la obligatoria vuelve a quedar idéntica a la registrada (`evidencia/G_aplicacion_parche05.txt`).
- **Estado:** propuesta. No se incorporó a los parches congelados ni se integró en nada.

## 1. El problema
- `ENGINE_VERSION = "1.1.0"` es una etiqueta escrita a mano; en el código significa «order hygiene D1-D3».
- 02v3 aplica sin 01 y, sin 01, el motor registra 1.1.0 sin D1–D3. Las 14 pruebas de trazabilidad pasan igual.
- Hoy solo el procedimiento (un único commit) impide esa etiqueta falsa.

## 2. Diseño: por qué no es circular
| Requisito | Cómo se cumple |
|---|---|
| No validar la etiqueta con algo que la propia etiqueta trae | La versión se lee **solo** para saber si hay promesa (≥ 1.1.0). Todo lo demás se observa en la **venue**: un `PaperExecutionProvider` que solo registra qué le llega (envíos, cancelaciones, llenados, posición y órdenes vivas por barra). **No** usa `order_hygiene`, el estado privado del motor, la huella, `resting_orders()` ni las pruebas de 01 |
| No depender de un número de operaciones | Ninguna aserción compara cantidades de operaciones. Las precondiciones son de existencia («se rechazó al menos un cierre») y los límites salen del mecanismo (§4) |
| Fallar contra 02v3 sin 01 | Sí: 5 de 5 pruebas de comportamiento fallan (§3) |
| Pasar con 01+02v3 | Sí: 7 de 7 |
| Detectar mutantes que quitan o desactivan protecciones | M1–M6, M8–M10: todos detectados. M7 (el aviso del informe) queda fuera de alcance a propósito (§3) |
| No dejarse engañar por la interfaz | Mutantes de evasión: 02v3 sin 01 **más** contadores `order_hygiene` falsos, o **más** `resting_orders()` sin usarlo. Los dos fallan |
| Fallar cerrado | Si el motor deja de construir su venue con el nombre que la guarda reemplaza, la guarda **falla** («the engine did not run on the recording venue»), no pasa vacía. Una versión ilegible, como «1.1.0-dev», también falla |

**Qué significa D1–D3 visto desde la venue:**
| Promesa | Comprobación (venue) | Prueba |
|---|---|---|
| D1 | Ningún envío devuelve una orden que ya estaba muerta (rechazada, cancelada o expirada): eso es un reintento suprimido como duplicado. Con stop por tiempo y el primer cierre de cada posición rechazado, ninguna posición sigue abierta más de `TIME_STOP_BARS + 3` barras | `test_a_rejected_close_is_sent_again_as_a_new_order_and_closes` |
| D2 | Con el mismo tamaño, el stop del libro se mueve al menos una vez; nunca se afloja; nunca se reemplaza un stop vivo por uno idéntico (salvo que un cierre lo haya obligado) | `test_the_stop_in_the_book_follows_the_leg` |
| D3 (cierre y en plano) | Después de pedir el cierre, la posición no crece; una entrada nunca llena dentro de una posición posterior a la que abrió; la venue nunca da vuelta la posición | `test_partial_fills_never_add_to_a_closing_position_or_reopen_one` |
| D3 (red de seguridad) | Con cierres inmediatos-o-cancelar, una posición nunca queda más de 1 barra sin un stop ni un cierre vivos | `test_a_close_that_ends_with_position_left_is_followed_by_another` |
| D1–D3 juntos | Rechazos al 30 %, parciales al 60 %, entradas límite y primer cierre rechazado | `test_rejections_partials_and_limit_entries_together` |
| Regla previa que 1.1.0 no debilita | Toda orden de mercado contra la posición es reduce-only | En D3p, D3r y Tj |
| Las comprobaciones no son vacías | Cada una calla con un registro limpio hecho a mano y salta con el defecto para el que está | `test_the_checks_pass_a_clean_record_and_catch_each_defect` |
| La etiqueta | `None` o < 1.1.0: sin promesa; ≥ 1.1.0 (también 1.2.0): con promesa; ilegible: falla | `test_a_version_that_is_not_a_number_cannot_escape_the_guard` |

## 3. Resultados (evidencia: `G_mutantes_guarda_final.json` y `.txt`, con el archivo final; la primera corrida, `G_mutantes_guarda.*`, dio lo mismo)
| Caso | Parte de | Esperado | Resultado | Pruebas que fallan |
|---|---|---|---|---|
| N0, sin cambios | 01+02v3 | Pasa | **7 pasan** | — |
| N1, 02v3 sin 01 | 02v3 | Falla | **5 fallan** | D1c, D2, D3p, D3r, Tj |
| M1: D1, id de salida sin barra | 01+02v3 | Falla | Detectado | D1c, D3r, Tj |
| M2: D1, id de stop sin colocación | 01+02v3 | Falla | Detectado | D1c, D2, D3p, D3r, Tj |
| M3: D2, no compara el nivel | 01+02v3 | Falla | Detectado | D2 («no stop in the book ever moved») |
| M4: D3, no cancela el resto al salir | 01+02v3 | Falla | Detectado | D3p, D3r (crece después del cierre) |
| M5: D3, no cancela el resto en plano | 01+02v3 | Falla | Detectado | D3p (una entrada llena en una posición posterior) |
| M6: D3, sin red de seguridad | 01+02v3 | Falla | Detectado | D3r (sin cobertura) |
| M7: sin el aviso de pierna sin stop | 01+02v3 | Fuera de alcance | No detectado | Es una advertencia del informe, no una regla de la venue. La cubre la prueba de 01 |
| M8: D3, sin ninguna capa | 01+02v3 | Falla | Detectado | D3p, D3r |
| M9: D2, recoloca el stop en cada barra | 01+02v3 | Falla | Detectado | D2 (reemplazo idéntico) |
| M10: cierre sin reduce_only | 01+02v3 | Falla | Detectado | D1c (por precondición: no hay cierres reduce-only que rechazar), D3p, D3r, Tj |
| E1: 02v3 sin 01 con contadores falsos | 02v3 | Falla | Detectado | 5 de 5 |
| E2: 02v3 sin 01 con `resting_orders` | 02v3 | Falla | Detectado | 5 de 5 |
| L1: 01+02v3 declara 1.0.9 | 01+02v3 | Se omite | 2 pasan, 5 omitidas | — |
| L2: 02v3 sin 01 declara 1.0.9 (etiqueta veraz) | 02v3 | Se omite | 2 pasan, 5 omitidas | — |
| L3: 01+02v3 declara 1.2.0 | 01+02v3 | Pasa | 7 pasan | — |
| L4: 02v3 sin 01 declara 1.2.0 | 02v3 | Falla | Detectado | 5 de 5 |
| L5: 01+02v3 declara «1.1.0-dev» | 01+02v3 | Falla (falla cerrado) | Falla | 5 de 5 (no se lee la promesa) |
| Base `72ffae5` | — | Se omite | 2 pasan, 5 omitidas | Sin versión: no hay promesa |

**Márgenes medidos en el motor correcto** (`margenes_g_obl.json`) frente a 02v3 sin 01 (`margenes_g_solo02.json`):
| Escenario | Racha máx. sin cobertura (límite 1) | Permanencia máx. con stop por tiempo (límite 9) | Órdenes muertas reenviadas | Stops movidos (D2) |
|---|---|---|---|---|
| Primer cierre rechazado | 0 frente a **42** | 7 frente a **45** | 0 frente a **201** | 26 frente a 0 |
| Calmo | 0 frente a 0 | — | 0 frente a 0 | 39 frente a **0** |
| Parciales 90 % | 0 frente a **192** | — | 0 frente a 0 | 10 frente a 0 |
| Cierres IOC | 0 frente a **519** | — | 0 frente a 0 | 2 frente a 0 |

## 4. De dónde salen los límites (no son un ajuste a una corrida)
- **`TIME_STOP_SLACK = 3`:**
  - medida en la venue, una posición cuyo cierre por tiempo pasa a la primera se ve abierta `TIME_STOP_BARS` barras;
  - un cierre rechazado agrega una barra;
  - quedan dos barras de margen: lo medido es 7 frente al límite de 9.
- **`MAX_BARS_UNCOVERED = 1`:**
  - el motor coloca o recoloca el stop en la misma barra que lo necesita;
  - medido: 0 barras en los cuatro escenarios sin rechazos aleatorios.
  - En el escenario con un 30 % de rechazos aleatorios la racha llega a 2, porque los stops también se rechazan. Por eso **esa prueba no comprueba la cobertura**.

## 5. Falsos positivos

### 5.1 Medidos
| Comprobación | Resultado |
|---|---|
| **Otras semillas y otros datos**, motor correcto (`evidencia/obl_*.json`, `RESUMEN_ROBUSTEZ.txt`) | **0 de 300 corridas.** Son los 5 escenarios × 20 semillas (1–20) × 3 conjuntos (BTC-USD 1h, BTC-USD 1m, ETH-USD 1m). Ninguna comprobación salta y todas las precondiciones se cumplen |
| La misma evaluación con 02v3 sin 01 (potencia; `evidencia/solo02_1_10.json`) | La guarda entera falla en **30 de 30** casos (datos × semilla). Por escenario: D1 30/30, D2 30/30, D3-red 30/30, todo junto 30/30, D3-parciales 13/30 |
| Determinismo | 3 repeticiones idénticas (`G_determinismo_y_entornos.txt`) |
| Entorno sin versiones fijadas, como instalaría `ci.yml` hoy | 7/7 con 01+02v3; 5 fallan con 02v3 sin 01 |
| Árboles | Completa: 7/7. Base: 2 pasan y 5 se omiten (sin promesa) |
| Suite completa local con 05 sobre la completa | **1985/1985**: las 1978 de la completa más las 7 de la guarda. Sin regresiones ni cambios de resultado frente a la completa sin 05 (`S_suite_completa_mas_05.*`, `S_comparacion_completa_vs_completa_mas_05.txt`). Monkeypatch acotado: no interfiere con el resto |
| Lint | `ruff check` limpio |

### 5.2 Posibles, por diseño (no medidos: son cambios futuros)
| Caso | Qué pasaría | Por qué se acepta o qué hacer |
|---|---|---|
| Una versión futura cierra con órdenes límite en lugar de mercado reduce-only | La precondición de D1 («se rechazó algún cierre») y `growth_after_close` dejan de ver los cierres: la guarda **falla** | La guarda fija el contrato de venue de hoy. Cambiar cómo se cierra es un cambio de contrato y debe actualizar la guarda en el mismo commit. Falla ruidosa, no silenciosa |
| Etiquetas de pre-lanzamiento («1.1.0-dev», «1.2.0rc1») | La guarda **falla** («not a dotted number») | Falla cerrado a propósito. Si se adoptan, cambiar `_declared` por un parser de versiones (PEP 440) |
| Una versión futura cambia la semántica del stop por tiempo o coloca el stop una barra más tarde | `positions_held_too_long` o `uncovered_streaks` podrían saltar | Hay 2 barras de margen en el primer caso y 1 en el segundo, sobre un comportamiento medido de 0. Un cambio así altera la protección prometida: debe discutirse |
| Se renombra o se deja de importar `PaperExecutionProvider` en `tia.backtest.engine` | La guarda **falla** («did not run on the recording venue») | Falla cerrado: nunca pasa en vacío |
| Un stop que se afloja a propósito (otra regla de salida) | `stop_moves` lo marca | Hoy `tighten_stop` solo ajusta. Una regla que afloje cambia la promesa D2 |
| Escenarios con entradas en varias partes (pirámide) | Sin efecto: solo se exige que no crezca **después** de pedir el cierre | — |

### 5.3 Lo que la guarda no cubre
- **M7, el aviso «no stop level»:** lo cubre la prueba de 01.
- **La reversión de solo 02v3 (R4):** sin versión no hay promesa.
- **El borrado de la propia guarda.**
- **El uso en vivo:** la guarda mira solo el backtest.

## 6. Recomendación
- **Integrarla como commit aparte, inmediatamente después del commit único 01+02v3, con su propia revisión.**
- **Qué protege:** ante una integración o reversión parcial que deje 02v3 sin 01, la CI se pone en rojo.
- **Qué no protege:**
  - la reversión de solo 02v3 (R4): sin versión no hay promesa;
  - el borrado de la propia guarda.
- **No reemplaza el commit único.**
