# 01 — Resultados de la auditoría integral de v0.5

**Objeto:** `SOLUCION_FINAL_TRADER_IA_v0.5_2026-10-20.zip`, SHA-256
`5bf9bc5d004b51188fdd407ae71eaae2ccefec7251af7001f8d89b264b4f5308`.

**Clases de cada resultado:**
| Clase | Significado |
|---|---|
| **[REPR]** | Reproducido en esta misión desde una extracción nueva |
| **[INDEP]** | Comprobado con una herramienta o un cálculo distinto del que usa v0.5 |
| **[INSP]** | Solo inspeccionado |
| **[HER]** | Heredado del expediente, no comprobado ahora |

## 1. Preservación y estado inicial (fase A)
| Comprobación | Resultado | Clase | Evidencia |
|---|---|---|---|
| El ZIP existe en la ruta informada y su SHA-256 = `5bf9bc5d…` | Sí | [INDEP] (`sha256sum`) | `B1_*` |
| HEAD, rama, origin y commits sin publicar | `692f2b2`; rama `claude/algo-trading-simulation-platform-ngf7xo`; origin `c6339e3`; sin publicar `f518ac1` y `692f2b2` | [INDEP] (git) | `A1_*` |
| Huella de `git status --porcelain --ignored` | `87b9585d…`, la informada | [INDEP] | `A1_*` |
| Cambios preexistentes | 3 versionados modificados (`research/.gitignore`, `ARTEFACTOS_SHA256.txt`, `PRERREGISTRO_PAPEL.md`), 5 sin seguimiento y 13 ignorados. Ninguno es de esta misión | [INDEP] | `A1_*` |
| Huella fuerte = la registrada al cierre de v0.5 (`91_*`) | Idéntica byte a byte: el repositorio no cambió entre misiones | [INDEP] | `A2_*` |
| T y T-MULTI frente a HEAD (git como referencia) | 50 archivos versionados de `tendencia_btc` iguales al blob de HEAD; solo difieren los 2 cambios preexistentes | [INDEP] | `A3_*` |
| Artefactos protegidos de T | Los 4 iguales al registro de v0.5 (`941b6e11…`, `4f8fafde…`, `94a16556…`, `88644d85…`) | [INDEP] | `A3_*` |
| Entregas anteriores | 25 ZIP inventariados: 19 con SHA-256 igual al registrado. En 5 (3 ZIP con datos de mercado y 2 copias en el repositorio) **no** se calculó el SHA-256, para no leer esos bytes, pero el directorio central de las copias coincide. 1 sin hash registrado (`recuperacion_parcial`) | [INDEP] | `A3_*` |
| Manifiestos de las carpetas de entregas | 18 manifiestos: 0 fallan, 0 faltan. Se omiten las entradas de datos de mercado | [INDEP] | `A3_*` |
| ENTREGA_ORIGINAL y EXPEDIENTE_METODOLOGICO | Solo existen como copias en `00_preservado` de v0.5 (`974d1ce2…`, `33ba77c1…`), iguales a lo registrado; sus carpetas originales verifican con su manifiesto | [INDEP] | `A3_*` |

## 2. Auditoría de v0.5 (fase B)
| Comprobación | Resultado | Clase | Evidencia |
|---|---|---|---|
| `verificar_zip.py`, `unzip -t`, extracción nueva y `sha256sum -c` | OK: 205 archivos + SHA256SUMS | [REPR] | `B1_*` |
| Comprobación independiente del ZIP | Lista = manifiesto; todos los hashes coinciden; sin enlaces ni rutas peligrosas | [INDEP] | `B1_*` |
| Cadena del `REGISTRO_ACCIONES.jsonl` | 28 entradas; cadena y hashes de la evidencia OK. **Observación D-4:** las fechas son mtime y no siguen el orden cronológico; es una reconstrucción posterior | [INDEP] | `B2_*` |
| `evidencia/95_*` | Recalculado con su script, sobre el ZIP B (`6bf96048…`) y su extracción: idéntico byte a byte | [REPR] | `B3_*` |
| Etapa 13 (paquete intacto) | Detecta bytes cambiados, archivos borrados, nuevos, renombrados y ocultos. **No detecta** enlaces simbólicos nuevos, directorios vacíos nuevos ni un archivo reemplazado por un enlace (**D-1**) | [INDEP] (12 escenarios adversariales) | `B4_*` |
| Afirmaciones frente a lo observable | **26 de 27 coinciden** con la evidencia del ZIP. Con la reproducción: 25 de 27 (C14 = D-3; C25 = I-1). La que no: «X1–X26» son 24 escenarios, porque X10 y X17 no existen en ninguna versión (**D-3**) | [INDEP] (`ast` sobre el código de las pruebas + colección real de pytest) | `B5_*` |
| Separación integridad / autenticidad / reproducción / autorización | Se mantiene: T INCONCLUSO (`SIN_REFERENCIA_INDEPENDIENTE`) con integridad COMPLETA; P2 NO_CANDIDATA; autorización NO_OTORGADA | [REPR] (`80_*` de la reproducción) + [INSP] | `B8_*` |
| Ejecutor: sin acciones reales | Ningún módulo importa red; solo P4 lanza procesos (el cálculo aislado con `-I -S -B` y el entorno vacío); `ACCION = "NINGUNA"` | [INDEP] (AST) | `B6_*` |
| Ejecutor: idempotencia | 32 pruebas de contrato y de extremo a extremo (caídas en 5 puntos, reanudación, concurrencia) dentro de la suite reproducida | [REPR] | `B8_*` |
| Parches 0001–0007 | `git apply --check` y `git apply` en orden sobre HEAD y origin exportados; la suite pasa en las dos copias | [REPR] | `B7_*` |
| Reproducción completa (`ejecutar_todo.sh` en una extracción nueva, 81 min) | Iguales a v0.5:<br>- suite: 449 pasan;<br>- estabilidad: 3 × 130;<br>- matriz: 48 de 48;<br>- mutaciones: 11/11, 20/20, 4/4 y 10/10;<br>- regresiones idénticas: 350 pasan y 9 fallan deliberadamente; 112;<br>- sondas idénticas;<br>- P2: 86.400 de 86.400;<br>- Ed25519 diferencial: pasa;<br>- 102 cortes y 72 fallos de escritura por código, sin violaciones;<br>- parches: OK;<br>- etapa 13: paquete intacto.<br>Comparación con la evidencia del ZIP: 36 de 37 comparaciones semánticas y 139 de 139 archivos idénticos. Las únicas diferencias (`99_*`, 90 ≠ 91) son el **incidente I-1** de esta misión, verificado: 90 = huella inicial y 91 = huella tras revertir | [REPR] | `B8_*` |
| Declaración de T para firmar | El `.bin` es exactamente la forma canónica del `.json`; los 3 hashes coinciden con los archivos actuales | [INDEP] | `C1_*` |

## 3. Defectos y observaciones de v0.5
Cada uno con: (1) evidencia anterior, (2) reproducción mínima, (3) causa, (4) impacto, (5) corrección, (6) pruebas
antes y después, y (7) estado.

**D-1. La etapa 13 no detecta entradas que no son archivos regulares.** Gravedad: baja.
1. **Evidencia anterior:** `97_*` de v0.5 dice «sin cambios ni archivos nuevos».
2. **Reproducción mínima:** `ln -s uso_unico.py codigo/verificacion/enlace.py` o `mkdir codigo/verificacion/__pycache__`
   en una copia → la etapa dice «intacto».
3. **Causa:** `find -type f` no lista enlaces ni directorios, y `sha256sum -c` sigue los enlaces.
4. **Impacto:** la afirmación de `97_*` es más amplia que lo comprobado. En los hechos, la ejecución B que respalda la
   evidencia de v0.5 no creó entradas de ese tipo (comprobado aparte, `B8_*`). Ningún resultado cambia.
5. **Corrección:** `correcciones_propuestas_v0.5.1/0001-…patch`: enlaces y entradas especiales siempre cuentan como
   cambio; solo se admiten los directorios que contienen archivos del manifiesto.
6. **Antes y después:** 3 diferencias → 0 en 12 escenarios. Sin falsos positivos sobre la ejecución real B. Detecta el
   caso real de la ejecución A.
7. **Estado:** corrección propuesta y probada; **v0.5 no se reconstruye**.

**D-2. Fugas de temporales en TMPDIR.** Gravedad: baja (higiene; fuera del paquete y del repositorio).
1. **Evidencia anterior:** ninguna; nadie lo había medido.
2. **Reproducción mínima:** las sondas y las pruebas de P1 con un TMPDIR nuevo → quedan 19 y 11 entradas.
3. **Causa:** `tempfile.mkdtemp()` en `sonda_*.py` y en `adaptador.py`, y `cd "$(mktemp -d)"` en
   `ejecutar_sondas.sh`, sin borrado.
4. **Impacto:** decenas de directorios por ejecución completa (`B8_*`); ningún resultado afectado.
5. **Corrección:** `0002-…patch`: TMPDIR propio con `trap` en el lanzador de las sondas y borrado al salir en el
   adaptador.
6. **Antes y después:** 19 → 0 y 11 → 0; la salida de las sondas es idéntica (`D2_*`).
7. **Estado:** propuesta y probada.
- **Residual (no corregible aquí):** un `calculo_*` vacío de P4 queda si el padre y el hijo mueren a la vez. Ningún
  proceso muerto puede limpiar. En la matriz, que ejecuta versiones viejas, es el comportamiento esperado de esas
  versiones (`B8_*`).

**D-3. «X1–X26» describe 24 escenarios.** Gravedad: documental.
- X10 y X17 no existen en v0.3, v0.4 ni v0.5; X19 figura en un comentario de `test_X4_*`.
- **Corrección:** decir «24 escenarios (X1–X26 sin X10 ni X17)» en la próxima versión de los documentos.
- **Estado:** documentado. No se modifica v0.5.

**D-4 (observación). El registro de acciones es una reconstrucción posterior.**
- `registrar_acciones.py` usa el mtime de la evidencia: el registro prueba coherencia interna, no cuándo ocurrió cada
  acción, y se puede regenerar entero.
- Su docstring lo dice, pero «registro encadenado de las acciones» puede leerse como contemporáneo.
- **Control propuesto:** un registro de solo añadidos escrito en el momento y anclado (04, A-27).

**Observación sobre `.git`:** los `git status` de solo lectura cambian el mtime del directorio `.git` (un `index.lock`
temporal). El índice, las referencias y los objetos no cambian (`G1_*`).

## 4. Hallazgos en el código NUEVO de esta misión, corregidos antes de entregar
| ID | Hallazgo | Cómo apareció | Corrección | Prueba que lo impide |
|---|---|---|---|---|
| N-1 | Los estadísticos de orden de los intervalos se calculaban en coma flotante: (1 − 0,90)/2·1000 = 49,99…, y el suelo daba el orden 49 en vez del 50 | El contraste diferencial con la implementación de E3 (los extremos del IC90 diferían) | Aritmética exacta con `Fraction` | `test_estadisticos_de_orden_exactos` y el diferencial |
| N-2 | B2 multiplicaba todo el futuro por un factor común: no detecta una estrategia que mira la barra actual (conserva cierre > apertura), ni una estadística global | Las pruebas de B2 | Dos alteraciones: aleatoria e independiente por barra, y desplazamiento de nivel ×3 | `test_mirar_la_barra_actual_se_detecta_en_B2` y `test_estadistica_global_…` |
| N-3 | Los procesos sintéticos se centraban en la muestra: T = 0 siempre, y la calibración no habría medido nada | Revisión antes de las pruebas | Media poblacional 0, sin centrar la muestra | `test_procesos_sinteticos_deterministas_y_no_centrados` |
| N-4 | Un subproceso `-I` sin `-B` escribió `__pycache__` dentro de la entrega: la misma clase que el defecto de v0.5 | `find` tras las pruebas | `-B` en todos los subprocesos | `test_higiene.py`: recorre todo el código con AST; ya encontró una segunda instancia |
| N-5 | `probar_etapa13.sh` copiaba un archivo a `/tmp` y dejaba temporales | Revisión del script | Eliminado; el script borra todo lo que crea; se borraron los 3 archivos de `/tmp` tras verificar que eran copias exactas creadas por él | Ejecución: 0 restos |

## 5. Incidente I-1: una modificación atribuible a esta misión en el repositorio, ya revertida
- **Qué pasó:**
  - para saber qué bibliotecas había, ejecuté `research/hcarry_next/.venv/bin/python -m pytest --version` **sin `-B`**;
  - eso escribió `pytest/__pycache__/__main__.cpython-311.pyc` (495 bytes, `c00ad62e…`) dentro del `.venv` del
    repositorio, a las 14:44:27 UTC.
- **Cómo se detectó:**
  - por la huella fuerte del repositorio (G1–G2), no por git: el `.venv` está ignorado y la huella porcelain no cambió;
  - el control funcionó.
- **Qué se hizo:**
  - se borró **solo** ese archivo, que no existía antes;
  - el directorio `pytest/__pycache__/` existía con `__init__.cpython-311.pyc` del 2026-10-16, que no se tocó;
  - **no se modificó ningún mtime** para que la huella volviera a coincidir: eso sería manipular la verificación.
- **Estado residual:**
  - el contenido del repositorio es idéntico al inicial;
  - la huella fuerte difiere **solo** en la línea de metadatos de `.venv`, por el mtime de ese directorio;
  - la verificación lo marca como **desviación conocida I-1**, sin ocultarla (`I1_*`, `G1_*`).
- **Consecuencia para la reproducción de v0.5:** su huella inicial (`90_*`) se tomó antes del incidente, así que su
  `99_*` informa un cambio. La causa es I-1, no v0.5 (`B8_*`).
- **Prevención:** todo intérprete del proyecto se usa con `-B` (`test_higiene.py` lo exige en esta entrega).

## 6. Conclusión de la auditoría
**Cierre técnico de la auditoría de v0.5 con autenticidad pendiente.**
- Las afirmaciones críticas de v0.5 se comprobaron o reprodujeron. Las discrepancias (D-1 a D-4) son del arnés o de la
  documentación, no de P1, P2, P4 ni del ejecutor, y ninguna cambia un resultado.
- **T sigue INCONCLUSO** (`SIN_REFERENCIA_INDEPENDIENTE`), P2 sigue NO_CANDIDATA y nada está autorizado.
- **Lo que no pudo comprobarse:**
  - la autenticidad de T (necesita tu firma);
  - un ancla externa real;
  - un corte de energía real;
  - la reproducción en otra máquina o por otra persona;
  - la revisión independiente (B-7).
- **Todo lo hizo el mismo autor** que escribió v0.5.
