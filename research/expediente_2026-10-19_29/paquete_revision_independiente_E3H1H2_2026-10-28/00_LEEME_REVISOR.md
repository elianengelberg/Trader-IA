# Paquete para la revisión independiente de E3-H1/H2

**Preparado:** 2026-10-28.

**Para:** un revisor que **no** haya participado en E3, en E3R, en la reparación, en la revisión del 2026-10-26 ni en el cierre de bloqueantes del 2026-10-27.

**Quién lo preparó:** el mismo agente (Claude) que escribió la reparación, la revisión anterior y el orquestador v3. Por eso este paquete **no contiene conclusiones a aceptar**. Contiene evidencia, preguntas y la forma de reproducirlas.

---

## 1. Qué se pide y qué no

**Se pide** un dictamen independiente, con dos partes que **no se mezclan**:

- **Parte técnica** (`02_COMPROBACIONES_TECNICAS.md`): ¿el código y los datos hacen lo que dicen? Cada punto se responde CONFIRMADO, REFUTADO o NO VERIFICABLE, con evidencia.
  - el diff v2→v3;
  - la tabla de renombres como **extracción** (citas, fechas, relaciones y actividad);
  - la ruta de ejecución real;
  - la **implementación** de la política de reintentos;
  - pruebas, mutación e integridad.
- **Parte metodológica** (`03_DECISIONES_METODOLOGICAS.md`): ¿qué reglas se deberían adoptar? El revisor da su opinión fundada; **decide el usuario**. Pronunciamientos **obligatorios**:
  1. **Adenda R** (reemplazo de §4.11 (ii)–(iv), anulación de (iii), reversión de lo decidido en el CIERRE §2 y dispensa del CIERRE §4);
  2. **GTO→GFT**, junto con LUNA→LUNC y UST→USTC (decisión D-1);
  3. **158 frente a 160 semanas** (fecha del texto N5 frente a la del título A3.1.5; decisión D-3);
  4. **riesgos residuales** (decisión D-5).

  Además se pide opinión sobre la **política de reintentos como regla de gobierno** (D-4), la **metodología estadística** y la bifurcación BCC (D-2, menor).

**Regla de separación:**
- una comprobación técnica puede verificar que el v3 **implementa** la lectura literal de D-1, pero no decide si esa lectura es la correcta;
- una opinión metodológica no puede apoyarse en una comprobación técnica que el revisor no haya confirmado.

**No se pide ni se permite:**
- **No ejecutar E3-H1/H2.** No llamar a `ejecutar_E3_v3.py real` ni a `ejecutar_E3_v2.py real` con insumos reales y una autorización.
- **No crear ni usar autorizaciones.** El v3 exige una frase y unos hashes que **no** deben escribirse en ningún archivo. Las pruebas usan frases y hashes de prueba, con sal.
- **No leer precios ni volúmenes reales.** No acceder a los arreglos O, H, L, C ni QV de las series. Las verificaciones del paquete leen solo `estado` y `simbolo`, con una guarda que aborta ante cualquier otro arreglo.
- **No modificar** la evidencia: trabajar sobre una copia.

**Regla de detención.** Si el revisor encuentra una **contradicción** entre documentos, código y datos, o **evidencia insuficiente** para un punto obligatorio:
- **se detiene en ese punto**;
- lo documenta en la sección «Contradicciones y evidencia insuficiente» de la plantilla;
- **no** emite una recomendación sobre la autorización.

Un dictamen que llega hasta el final con contradicciones abiertas no es válido.

---

## 2. Contenido

| Archivo o carpeta | Qué es |
|---|---|
| `00_LEEME_REVISOR.md` | Esta guía |
| `01_ESTADO_Y_DECISION_DEL_USUARIO.md` | Estado actual y lo que decidió el usuario el 2026-10-28 (la revisión independiente es condición previa) |
| `02_COMPROBACIONES_TECNICAS.md` | Lista técnica T-1…T-10: qué comprobar, cómo, resultado esperado y qué lo refutaría |
| `03_DECISIONES_METODOLOGICAS.md` | M-1…M-7: pregunta, reglas congeladas, opciones, evidencia a favor y en contra, y lo demostrado frente a lo interpretativo |
| `04_PLANTILLA_DICTAMEN.md` | Plantilla del dictamen, con los pronunciamientos obligatorios y el registro de contradicciones |
| `05_LIMITES_CONOCIDOS_Y_PUNTOS_DEBILES.md` | Lo que el autor sabe que es débil o dudoso en su propio trabajo. Para revisar primero, no para dar por resuelto |
| `evidencia/` | Copia de solo lectura de la evidencia, con la estructura original. Ver §3 |
| `reproducir/reproducir.sh` | Corre la verificación de integridad, las suites, las verificaciones sobre datos, la higiene de autorizaciones y, con `--mutacion`, las pruebas de mutación |
| `reproducir/auxiliar.py` | Compara JSON y busca las frases de autorización (con `ast`, sin ejecutar el código) |
| `registro/` | Huellas antes y después de armar el paquete, script que copió la evidencia, inventarios de origen e inventario completo del árbol E3 |
| `MANIFEST_PAQUETE.sha256` | sha256 de cada archivo del paquete principal (el enlace `copia_aislada/experimentos → ../../experimentos` no figura porque no es un archivo) |
| `MANIFEST_DATOS.sha256` | Viene en el paquete de datos: sha256 de cada serie y cada página |

**Paquete de datos** (aparte, carpeta o archivo `…_DATOS`):
- las 757 series de calidad (`.npz`);
- las 8.028 páginas archivadas.

Hace falta para T-3 (renombres), T-7 (ventana), T-8 (mapeos sobre la actividad real) y las suites: algunas pruebas hashean las series reales.

Se extrae **en la raíz del paquete principal**, de modo que su `evidencia/` se combine con la del paquete:

```bash
tar -xzf paquete_revision_independiente_E3H1H2_2026-10-28.tar.gz
tar -xzf paquete_revision_independiente_E3H1H2_2026-10-28_DATOS.tar.gz \
    -C paquete_revision_independiente_E3H1H2_2026-10-28 --strip-components=1
```

Así quedan en la raíz `MANIFEST_DATOS.sha256` y, en `registro/`, `INVENTARIO_ORIGEN_B.tsv`.

> **Atención: las series contienen precios y volúmenes reales.** Están en el paquete solo porque los scripts leen de ellas `estado` y `simbolo`. El revisor no debe abrir otros arreglos.

---

## 3. Mapa de la evidencia (`evidencia/`)

| Carpeta | Qué contiene | Estado |
|---|---|---|
| `experimentos/E3_seleccion_posicion_2026-10-19/` | Protocolo v3 (`PROTOCOLO_E3_v3_PROPUESTO.md`), cierre, registros de hipótesis, notas y adendas (`ejecucion_E3/protocolo/`), código congelado (`ejecucion_E3/codigo/*.py`), resultados estructurales y de conciliación de la primera pasada, auditoría de actividad | Congelado (copia parcial; el inventario completo está en `registro/INVENTARIO_E3_COMPLETO.sha256`) |
| `experimentos/E3R_desbloqueo_2026-10-26/` | Adenda R, R2, R1′, P0, orquestador v1 (`ejecutar_E3R.py`) | Congelado |
| `reparacion_E3H1H2_2026-10-26/` | Segunda pasada, tabla de 22 mapeos, ventana A, orquestador v2 y su informe | Congelado (MANIFEST 92/92) |
| `revision_independiente_E3H1H2_2026-10-26/` | Revisión del 2026-10-26 (no independiente) con sus pruebas | Congelado (MANIFEST 41/41) |
| `cierre_bloqueantes_E3H1H2_2026-10-27/` | Tabla completa de renombres, orquestador v3, suite y mutación, comparación metodológica e informe de cierre | Congelado (MANIFEST 48/48) |

**Orden de lectura sugerido:**
1. `experimentos/…/CIERRE_E3.md`
2. `experimentos/…/PROTOCOLO_E3_v3_PROPUESTO.md` §2.3 y §4.11, y `ejecucion_E3/protocolo/ADENDA_1_…` y `ADENDA_3_…`
3. `experimentos/E3R_desbloqueo_2026-10-26/ADENDA_R_auditoria_de_supervivencia_interna.md`
4. `revision_independiente…/REVISION_INDEPENDIENTE_E3H1H2.md`
5. `cierre_bloqueantes…/INFORME_CIERRE_BLOQUEANTES_E3H1H2.md`
6. `05_LIMITES_CONOCIDOS_Y_PUNTOS_DEBILES.md`
7. Después, `02` y `03`.

---

## 4. Cómo reproducir

**Requisitos:** Python 3.11, numpy 2.4 y pytest 9 (las versiones con que se generó la evidencia: 3.11.17, 2.4.6 y 9.1.1). Linux, por `fcntl`.

```bash
# 1) Integridad del paquete y del de datos (extraído encima)
cd <paquete> && sha256sum -c --quiet MANIFEST_PAQUETE.sha256 && sha256sum -c --quiet MANIFEST_DATOS.sha256
# 2) Todo lo reproducible, sin mutación o con mutación (varios minutos más)
PY=python3 bash reproducir/reproducir.sh <paquete>/evidencia
PY=python3 bash reproducir/reproducir.sh <paquete>/evidencia --mutacion
```

**Qué hace `reproducir.sh`:**
- usa temporales fuera del paquete (`$OUT`; por defecto, un directorio nuevo en `$TMPDIR` o `/tmp`) y no escribe en `evidencia/`;
- compara la huella de `evidencia/` al principio y al final;
- corre todo con `-B` y sin caché de pytest;
- **no** llama a ningún orquestador en modo `real` y **no** contiene ni crea ninguna autorización;
- termina con una tabla `RESUMEN.txt` (paso, esperado, obtenido, OK / FALLA / OMITIDO) y un código de salida distinto de 0 si algo falla;
- `reproducir/auxiliar.py` solo lee y compara: no importa ni ejecuta código del paquete.

**Resultados esperados** (los que obtuvo el autor):

| Paso | Esperado |
|---|---|
| Manifiestos de la reparación, la revisión y el cierre | 92/92, 41/41, 48/48 |
| sha256 de v1, v2, v3, manifiesto del v3, mapeos completos y ventana A | `3b64a04d…`, `01fc9344…`, `c089cc6a…`, `a89b6a23…`, `bd07e7f9…`, `dcbd80ab…` |
| Huellas de las series y las páginas | `6506fb03…` (757) y `f12afb98…` (8.028) |
| Suite del autor (v2), neutralizada | 28 passed, 6 xfailed |
| Suite de la revisión (v2) | 7 passed, 10 xfailed; con `--runxfail`, las 10 razones de `reproduccion/razones_xfail_revision_v2.txt` |
| Suite del v3 | 51 passed |
| Mutación | 15 mutantes, 0 sobreviven |
| `construir_tabla.py` y `tabla_a_markdown.py` | `TABLA_RENOMBRES_COMPLETA.json`, `.md`, `mapeos_adenda1_completa.json` y `clasificacion_barrido.json` idénticos byte a byte (76 entradas, 50 mapeos, 107 citas verificadas, 0 problemas) |
| Ventana con la tabla completa | inicio 2023-05-15, 158/158, mínimo 120, último inicio válido 2023-05-29, (iv′) 2018; JSON igual al del autor |
| Mapeos sobre la actividad real | JSON igual al del autor (50 aplicados, 735 filas, HIFI con 9 formaciones distintas en A); arreglos leídos `['estado', 'simbolo']` |
| Higiene | 0 fallas. La frase de D-1 del v3 aparece solo en el v3, su plantilla y el diff. La FRASE del v3 y la frase de reapertura no aparecen literales en ningún archivo: en el código están partidas en varias líneas. Ninguna frase real en los temporales. Como información, las frases del v1 y del v2 aparecen en 9 archivos congelados: el código del v1 y 8 documentos o diffs (`05`, L-25) |
| Evidencia | Sin cachés, sin registro de intentos y con la misma huella al final |

**Que se reproduzcan no prueba que estén bien.** Es el punto de partida de la revisión, no su conclusión.

**Se recomienda que el revisor:**
- escriba **sus propios** mutantes y casos de prueba;
- lea a mano una **muestra** de las citas de la tabla en las páginas archivadas;
- busque renombres que los tres barridos del autor no hayan encontrado.
