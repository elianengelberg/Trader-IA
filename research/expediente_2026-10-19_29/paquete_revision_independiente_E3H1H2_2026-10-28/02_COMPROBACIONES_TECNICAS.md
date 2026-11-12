# Parte técnica: comprobaciones T-1…T-10

**Alcance.** Cada punto responde si el código, los datos o los documentos **hacen lo que afirman**. Ninguno decide qué regla metodológica es la correcta: eso está en `03_DECISIONES_METODOLOGICAS.md`.

**Veredicto por punto:** CONFIRMADO, REFUTADO o NO VERIFICABLE, siempre con la evidencia (archivo, línea, salida de un comando).

**Convenciones:**
- `EV` es `evidencia/`;
- `CB` es `EV/cierre_bloqueantes_E3H1H2_2026-10-27`;
- `REP` es `EV/reparacion_E3H1H2_2026-10-26`;
- `E3X` es `EV/experimentos/E3_seleccion_posicion_2026-10-19/ejecucion_E3`;
- las líneas citadas del v3 son de `CB/orquestador_v3/ejecutar_E3_v3.py` (sha256 `c089cc6a…`).

---

## T-1 · Integridad y procedencia

**Qué:**
- que la evidencia sea la que se generó y que nada se haya alterado;
- que los hashes congelados citados por todos los documentos coincidan con los archivos.

**Cómo:**
- `sha256sum -c MANIFEST_PAQUETE.sha256` en la raíz del paquete;
- `sha256sum -c MANIFEST.sha256` en `REP`; `sha256sum -c MANIFEST_REVISION.sha256` en la revisión; `sha256sum -c MANIFEST_CIERRE.sha256` en `CB`;
- comparar `registro/INVENTARIO_ORIGEN_*.tsv`: cada copia lleva el sha256 de su origen;
- con el paquete de datos extraído, el conjunto de series tiene que dar `6506fb03…` con la receta de CIERRE (`find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum` dentro de `E3X/resultados/calidad/series`), y las páginas, `f12afb98…` (`sha256sum * | sha256sum` dentro de `paginas`).

**Esperado:**
- todo OK;
- v1 `3b64a04d…`, v2 `01fc9344…`, v3 `c089cc6a…`;
- manifiesto del v3 `a89b6a23…`;
- tabla de mapeos `bd07e7f9…`;
- ventana A `dcbd80ab…`.

**Refuta:** cualquier discrepancia de hash o un archivo citado que no esté.

**Límite:** el paquete no incluye los ZIP de Vision ni los índices de Common Crawl. Solo están sus hashes, en `registro/INVENTARIO_E3_COMPLETO.sha256`.

---

## T-2 · Diff v2→v3

**Qué:**
- que el v3 sea el v2 con **solo** los cambios declarados (C7–C13, M4 y M8);
- que el bloque de cálculo sea idéntico.

**Cómo:**
- leer `CB/orquestador_v3/DIFF_v2_v3.diff` completo;
- regenerar el v3 en una **copia** con `CB/orquestador_v3/generar_v3.py` (necesita el paquete de datos para recalcular hashes) y comparar el sha256 con `c089cc6a…`;
- comparar el bloque `validez_previa`…`modo_sintetico` del v2 (líneas 159–499) con el del v3 (líneas 385–725). Según el autor, la única línea distinta es la 432 del v3: `strict=True`.

**Para cada cambio, verificar en el código:**

| Cambio | Dónde (v3) | Qué tiene que cumplirse |
|---|---|---|
| C7 ventana | l. 69–70; `EXIGIDAS["ventana_A"]`; `modo_real` l. 847–849 | Otra ventana se rechaza antes de crear la salida, por hash **y** por contenido |
| C8 entradas | `EXIGIDAS` l. 71–86; `leer_y_verificar` l. 192–228 | El manifiesto tiene que coincidir exactamente; los mapeos salen solo de `mapeos_adenda1_completa` (l. 853) |
| C9 lectura única | `_leer_archivo`, `_leer_conjunto` l. 157–179; `panel_real` l. 253; `actividad_desde_bytes` l. 243 | Ninguna lectura de disco de los insumos después de verificar; enlaces simbólicos rechazados |
| C10 código | `cargar_modulos` l. 124–139; `_BYTES_PROPIOS`/`SHA_PROPIO` l. 57–58 | Ningún `import` de universo, motor ni inferencia desde disco en modo real |
| C11 estados | `escribir_atomico` l. 730; `Intentos` l. 743; `permitir_intento` l. 771; `resultado_error` l. 808; `modo_real` l. 859–890 | Antes de `mkdir` (l. 859), solo `Rechazo`; después, siempre EVALUADO, INVALIDO o ERROR |
| C12 mapeos | `aplicar_mapeos` l. 292–382; `comprobar_marcas` l. 279; comprobación previa l. 854–857 | Reglas 1, 2 y 1R; rechazo de duplicados, huecos ≥ 30 días y cambios de marca, antes de la salida |
| C13 autorización | `FRASE` l. 88; `FRASES_DECISION` l. 90; `requeridos` en `modo_real` | Sin las frases de decisión, rechazo |

**Refuta:**
- un cambio no declarado;
- una diferencia en el bloque de cálculo;
- un cambio declarado que el código no implementa;
- un camino que esquive una guarda.

---

## T-3 · Tabla de renombres como extracción

Solo la extracción. Si la regla está bien aplicada a casos dudosos se discute en M-2 y M-7.

**Qué:**
- que cada entrada esté respaldada por texto archivado del **cuerpo** del anuncio (A3.1.1), con fecha efectiva, relación y apertura correctamente leídas;
- que la actividad sea coherente;
- que no falten renombres que exijan mapeo.

**Cómo:**
1. Reproducir `CB/tabla/construir_tabla.py` en una copia. Tiene que dar 76 entradas, 50 mapeos, 107 citas presentes y 0 problemas, con `TABLA_RENOMBRES_COMPLETA.json` idéntico (sha256 `b3eaf177…`).
2. **Revisar a mano** al menos las 7 reglas 1 nuevas, BNX, VIDT, LUNA (1R), GTO→GFT, y una muestra de 5 de la tabla de 22 y de 3 *reverse splits*:
   - abrir la página en `E3X/datos_anuncios/commoncrawl/paginas/<archivo>`;
   - confirmar que la cita está en el cuerpo (no en una barra lateral);
   - confirmar el **sentido** de r (unidades nuevas por unidad vieja), E (día en que cesa la negociación spot del par viejo, N5) y la apertura.
3. Revisar la clasificación de los 117 pares del barrido (`CB/tabla/clasificacion_barrido.json`).
4. **Búsqueda propia de faltantes:** con un método distinto de los tres del autor (`barrido_renombres.py`, `barrido_sin_saludo.py` y `barrido_por_actividad*.py`), buscar renombres o redenominaciones de pares del panel en el período archivado.

**Esperado:**
- citas en el cuerpo;
- r, E y apertura coherentes con el texto;
- actividad coherente (`chequeo_actividad` en el JSON);
- sin faltantes.

**Refuta:**
- una cita fuera del cuerpo;
- un r invertido;
- una E mal leída;
- un renombre exigido por la Adenda 1 que no está;
- un caso clasificado como «no es renombre» que sí lo es.

**Puntos débiles conocidos:** `05_LIMITES…`, ítems L-1 a L-6.

---

## T-4 · Ruta de ejecución real

**Qué:**
- en `modo_real` (l. 828–894), el orden de las operaciones;
- que **no se lea ningún precio** antes de la autorización y de la verificación de todos los insumos;
- que ningún fallo previo a la salida consuma la ejecución.

**Orden según el autor:**
1. la salida no existe;
2. autorización completa (FRASE, sha256 propio y del manifiesto, y frases de decisión);
3. bloqueo y registro de intentos;
4. lectura única y verificación de los 15 insumos;
5. ventana A por contenido;
6. carga de módulos desde bytes;
7. comprobación de mapeos **solo con `estado`**;
8. `mkdir`;
9. INICIADO;
10. panel con precios;
11. validez previa;
12. cálculo;
13. escritura.

**Cómo:**
- lectura del código;
- correr las pruebas `test_control…`, `test_cada_insumo_se_lee_una_sola_vez`, `test_mapeo_imposible_se_detecta_antes_de_crear_la_salida` y `test_EVALUADO_de_punta_a_punta…`;
- opcional: repetir `CB/verificaciones/entrada_real_sin_autorizacion.txt` llamando a `ejecutar_E3_v3.py real` con una ruta de autorización que **no exista** y una salida en un temporal. Tiene que rechazar sin crear la salida ni el registro de intentos.

**Refuta:**
- una lectura de O, C o QV antes del paso 10;
- una salida creada antes del paso 8;
- un fallo previo al paso 8 que deje rastro de intento.

---

## T-5 · Política de reintentos: implementación

Si la política es razonable se discute en M-5.

**Política declarada:**
- no hay otra ejecución después de EVALUADO o INVALIDO;
- un intento INICIADO sin estado terminal bloquea hasta una revisión manual;
- un ERROR con estadísticos iniciados (etapas «calculo» y «escritura») bloquea;
- un ERROR en «panel» o «validez_previa» admite un reintento solo con una autorización **nueva**, distinta de las usadas, que contenga `REINTENTO TRAS ERROR <sha256 del RESULTADO_E3.json con ERROR>`;
- una ejecución concurrente queda bloqueada (`flock`).

**Cómo:**
- lectura de `permitir_intento` (l. 771–797), `Intentos` (l. 743–768), `resultado_error` (l. 808–825) y `ETAPAS_SIN_ESTADISTICOS` (l. 95);
- pruebas `test_reintento_*`, `test_intento_sin_estado_terminal_bloquea`, `test_ejecucion_concurrente_bloqueada` y `test_EVALUADO_de_punta_a_punta…`.

**Revisar en particular:**
- que el sha256 citado sea el del archivo escrito: `escribir_atomico` devuelve el hash del texto que escribe;
- qué pasa si el registro se borra o se corrompe;
- qué pasa si falla la escritura del ERROR;
- que `validez_previa` (que simula la estrategia en memoria) figure como etapa «sin estadísticos».

**Refuta:** una diferencia entre la política declarada y la implementada, o una secuencia que permita una segunda ejecución con resultado.

**Puntos débiles conocidos:** `05_LIMITES…`, ítems L-11 a L-13. En L-13 el autor describe, sin haberla probado, una secuencia que contradice la política declarada (un INVALIDO sobrescrito por un ERROR reintentable cuando falla el registro). Confirmarla o refutarla.

---

## T-6 · No se leyeron precios ni volúmenes

**Qué:** que las verificaciones con datos reales lean solo `estado` y `simbolo`, y bytes únicamente para hashear.

**Cómo:**
- leer las guardas (`SoloEstado`) en `CB/verificaciones/ventana_tabla_completa.py` y `CB/verificaciones/mapeos_sobre_estado_real.py`;
- comprobar el campo `arreglos_leidos` de `mapeos_sobre_estado_real.json`: tiene que ser `["estado", "simbolo"]`;
- comprobar que `construir_tabla.py` y los barridos leen solo textos y `auditoria_por_simbolo.json`.

**Refuta:** cualquier acceso a O, H, L, C o QV, o a precios derivados (por ejemplo, `ratio_precio` de `estructural.json`), en el trabajo de cierre.

---

## T-7 · Ventana A con la tabla completa

**Cómo:** reproducir `CB/verificaciones/ventana_tabla_completa.py` (argumentos en su docstring; necesita el paquete de datos) y comparar con `REP/ventana_A/ventana_A_pasada2.json`.

**Esperado:**
- inicio 2023-05-15, 158/158, mínimo 120, último inicio válido 2023-05-29, (iv′) 2018;
- 2023 con 18 salidas en alcance y 1 sin evidencia (NBTUSDT).

**Revisar:** el v3 fija el archivo de ventana **calculado con la tabla de 22** (`dcbd80ab…`). El veredicto no cambia, pero sus conteos por año sí (`05_LIMITES…`, L-10).

**Refuta:** otro inicio, otro número de semanas u otro (iv′).

---

## T-8 · Mapeos sobre la actividad real

**Cómo:** reproducir `CB/verificaciones/mapeos_sobre_estado_real.py`.

**Esperado:**
- 50 mapeos aplicados sin rechazo;
- 757 filas → 735;
- guarda de marcas sin fallas;
- en A, solo HIFIUSDT cambia en los criterios (a) y (b): 9 formaciones (2023-05-15 a 2023-07-10).

**Límite:** el criterio (d) de volumen no se evaluó: exigiría leer QV.

---

## T-9 · Pruebas y mutación

**Cómo:** `reproducir/reproducir.sh` (y `--mutacion`).

**Esperado:**

| Suite | Resultado esperado |
|---|---|
| Autor | 28 passed, 6 xfailed |
| Revisión | 7 passed, 10 xfailed, por las razones declaradas |
| v3 | 51 passed |
| Mutación | 15 mutantes, 0 sobrevivientes |

**Revisar el diseño de las pruebas:**
- las pruebas del v3 parchean los sha256 fijados con una sal de prueba y las frases con frases de prueba. Comprobar que ese parche **no oculta** una falla real. Los hashes reales se controlan aparte en `test_exigidas_del_v3_coinciden_con_los_insumos_congelados`, y la verificación real en T-8;
- los 15 mutantes los eligió el autor. **Escribir mutantes propios.** Sugerencias:
  - invertir el orden de la comprobación de mapeos y `mkdir`;
  - sacar «validez_previa» de `ETAPAS_SIN_ESTADISTICOS`;
  - quitar el `except FinTerminal`;
  - escribir el resultado sin `os.replace`;
  - quitar la comparación de autorización repetida;
  - aflojar el control de corte de la regla 2.

**Refuta:**
- una prueba que pasa por un motivo distinto del declarado;
- un mutante relevante que sobrevive.

---

## T-10 · Higiene de autorizaciones

**Qué:**
- que no exista ninguna autorización;
- que ningún archivo fuera del código contenga la FRASE real del v3 ni las frases de decisión;
- que no exista `INTENTOS_E3.jsonl`.

**Cómo:**
- buscar en todo el paquete las cadenas de `FRASE` y `FRASES_DECISION` del v3. Pueden aparecer solo en `ejecutar_E3_v3.py`, `plantilla_cabecera.py` y `DIFF_v2_v3.diff`;
- confirmar que la suite del v3 incluye la prueba de higiene sobre sus temporales.

**Aviso:** la suite **del autor** (v2) escribe la frase real del v2 y el hash real del v2 en temporales. Por eso `reproducir.sh` la corre con el `conftest.py` de neutralización de la revisión.

**Refuta:** una autorización existente o la frase real en un archivo de datos o de prueba.
