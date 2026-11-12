# E3-H1/H2: cierre de bloqueantes, sin autorización de ejecución

**Fecha:** 2026-10-27.

**Área aislada:** `cierre_bloqueantes_E3H1H2_2026-10-27/`, dentro del scratchpad. Las rutas son relativas a esa carpeta salvo indicación.

**Punto de partida:** `revision_independiente_E3H1H2_2026-10-26/REVISION_INDEPENDIENTE_E3H1H2.md`, tomado como hipótesis a verificar, no como verdad.

> **Independencia.** Lo hizo el mismo agente que escribió la reparación y la revisión anterior. Para compensarlo:
> - cada defensa del v3 se demostró con pruebas sobre el camino real y con **pruebas de mutación**: se quita la defensa y alguna prueba tiene que fallar;
> - la tabla de renombres verifica cada cita contra el texto archivado.
>
> Las decisiones de interpretación (§3.3 y §7) necesitan igual tu juicio y, si querés, el de un tercero.

**Restricciones respetadas:**
- **No** se ejecutó E3-H1/H2;
- **no** se leyó ningún precio ni volumen real (detalle en §6.3);
- **no** se creó ninguna autorización;
- **no** se tocaron árboles congelados, resultados originales, el repositorio ni ramas;
- **no** hubo commits, push ni despliegues.

Todo lo nuevo está en el área aislada.

---

## 1. Resumen

| Bloqueante o defecto (revisión) | Estado | Dónde |
|---|---|---|
| **B1** Tabla de mapeos incompleta (MFT→HIFI con efecto en A; BNX, VIDT, LUNA, BTT, NANO, BZRX, RAMP, EPS, GXS…) | **Resuelto**, salvo la decisión D-1 (GTO→GFT, LUNA→LUNC, UST→USTC), que es interpretativa y queda a tu cargo | `tabla/` |
| **B2** Un fallo consumía la ejecución única sin estado | **Resuelto**: ERROR explícito, atómico, con registro de intentos y política de reintento | `orquestador_v3/` |
| I1 Ventana A no fijada | **Resuelto** (C7) | v3 |
| I2 Mapeos sin verificar | **Resuelto** (C8) | v3 |
| I3 Manifiesto vacío o incompleto | **Resuelto** (C8) | v3 |
| I4 Bytecode no verificado | **Resuelto** (C10) | v3 |
| I5 TOCTOU | **Resuelto** (C9) | v3 |
| I6 Adenda R presentada de forma incompleta | **Resuelto** como documento; la decisión es tuya | `metodologia/COMPARACION_METODOLOGICA.md` |
| I7 Recall de la extracción | **Declarado y medido**. Hallazgo nuevo: retiros USDT de 2022–2023 que no figuran como eventos; no mueven A | §3.4 |
| I8 La suite del autor escribe la frase real | La suite del v3 no lo hace (prueba de higiene). La del v2 está congelada y se corrió neutralizada | §5 |
| M1–M3 Defectos latentes de mapeo | **Resueltos** (C12) | v3 |
| M4 Operacionalizaciones del docstring | **Restituidas** en el v3 | v3 |
| M5 Fechas N5 frente a A3.1.5 | **Pendiente: decisión D-3** | metodología |
| M8 `zip(strict=False)` | **Corregido** (`strict=True`); idéntico en resultados | v3 |

**Recomendación: APTO PARA SOLICITAR AUTORIZACIÓN, con condiciones explícitas** (§8). No hay bloqueantes técnicos abiertos. Lo que queda son **decisiones metodológicas tuyas**, que el v3 exige ver escritas en la autorización. **Esto no autoriza la ejecución.**

---

## 2. Fase 1: bloqueantes

### 2.1 B1, tabla completa de renombres

**Método.** Tres barridos independientes, solo con textos y actividad:
1. Cuerpo de las 8.028 páginas (A3.1.1), con patrones de relación con decimales y de cambio de ticker (`tabla/barrido_renombres.py`): 117 pares con algún lado en el panel.
2. Las 1.636 páginas sin saludo, con el texto completo (`tabla/barrido_sin_saludo.py`): ningún par nuevo.
3. Guiado por actividad (`tabla/barrido_por_actividad*.py`): cada símbolo que empieza ≤ 60 días después de que otro termina, o entre 61 y 400 días con palabras de renombre, cruzado con cuerpos que nombran a los dos. También cada uno de los 34 cortes con reanudación. Solo agregó GTO→GFT y confirmó los demás.

**Construcción y verificación** (`tabla/construir_tabla.py`):
- toma los 22 mapeos de la reparación y les suma los nuevos;
- **cada cita se verifica como subcadena del texto archivado del archivo citado**: 107 citas, 0 fallas;
- se verifica la actividad: X inactivo desde E; Y empieza después; hueco < 30 días; en la regla 2, corte que contiene E;
- **aborta** si algo no cuadra o si queda un par del barrido sin clasificar: los 117 están clasificados.

**Resultado** (`tabla/TABLA_RENOMBRES_COMPLETA.md` y `.json`; mapeos que aplica el v3: `tabla/mapeos_adenda1_completa.json`, `bd07e7f9…`):

| Grupo | Entradas | Se aplica en el v3 |
|---|---|---|
| Regla 1 (renombre X → Y) | 23 = 16 de la tabla de 22 + **7 nuevos**: MFT→HIFI (r 0,01), BTT→BTTC (1000), NANO→XNO (1), BZRX→OOKI (10), RAMP→LEVER (35), EPS→EPX (88), GXS→REI (10) | Sí |
| Regla 1, última oración (ticker reutilizado) | 1: **LUNAUSDT desde el 2022-05-31 es Terra 2.0, un listado nuevo** | Sí (nueva regla «1R» del v3) |
| Regla 2 (mismo símbolo, r ≠ 1) | 26 = 6 de la tabla + **BNX** (1 BNXOLD = 100 BNX; E 2023-02-16; reapertura 2023-02-22) + **VIDT** (1:10; E 2022-10-31; reapertura 2022-11-09) + **18 reverse splits de tokens apalancados** (10.000 o 100.000 a 1). Los apalancados se incluyen por literalidad; sin efecto, porque §4.5 los excluye | Sí |
| Decisión D-1 | 3: GTO→GFT, LUNA(viejo)→LUNC, UST→USTC | **No** (lectura literal; §2.2) |
| Anunciados pero fuera de la regla 1 | 4: BCC→BCHABC+BCHSV (bifurcación), RGT→TRIBE (fusión en un par existente), BETH→WBETH y USDSB→USDS (solapados) | No |
| Regla 3 (sin anuncio archivado) | 19: 12 cambios de símbolo (TOMO→VIC, GAL→G, RNDR→RENDER, KLAY→KAIA, AGIX/OCEAN→FET, DAR, FTM, EOS, MKR, FXS, OM) y 7 cortes sin canje (AEUR, AUD, AXS, KEY, NBT, SCR, USUAL) | Limitación declarada |

**Coherencia con la actividad real:**
- verificada aplicando la tabla con las funciones del v3 sobre `estado` real (`verificaciones/mapeos_sobre_estado_real.json`);
- los 50 mapeos se aplican **sin ningún rechazo**: 757 filas → 735, y la guarda de marcas pasa;
- solo se leyeron los arreglos `estado` y `simbolo`, comprobado por la guarda.

**Efecto en A, solo criterios (a) y (b):**
- frente a la tabla de 22, la única diferencia es **HIFIUSDT en 9 formaciones** (2023-05-15 a 2023-07-10), que ahora cumple (a) y (b);
- el criterio (d), volumen, **no se evaluó** porque exige leer QV real. **Queda pendiente**: no se sabe si HIFI entra efectivamente al universo en esas semanas;
- todo lo demás de la tabla nueva cae antes de A o no altera nada en A. En el caso de BNX, una prueba sintética muestra que un salto de nivel en un corte previo no cambia el universo, la señal ni el IC posteriores (`P.r` no cruza huecos).

**Ventana A con la tabla completa** (recálculo propio, `verificaciones/ventana_tabla_completa.json`):
- **sin cambios**: 2023-05-15, 158/158 semanas evaluables, mínimo 120 elegibles, último inicio válido 2023-05-29, (iv′) = 2018;
- 2023 queda en 18 salidas en alcance con 1 sin evidencia (NBTUSDT, 5,6 %).

### 2.2 GTO→GFT: qué permite concluir la evidencia y qué exige interpretación

**Demostrado con el texto archivado y la actividad:**
1. **El par GTO/USDT se retiró el 2022-11-28 03:00 UTC**, por anuncio archivado de retiro de pares: «Binance will remove and cease trading on the following trading pairs at 2022-11-28 03:00 (UTC) : … GTO/USDT». El último día activo de GTOUSDT es el 2022-11-27.
2. **El canje GTO→GFT es posterior:** anunciado con calendario desde el 2023-01-18 y completado con «1 GTO = 1 GFT».
3. **GFT/USDT abrió el 2023-09-22**, 298 días después del último día de GTOUSDT (anuncio archivado de alta de pares).

**Lo que la regla congelada no resuelve:** la regla 1 de la Adenda 1 dice «el listado **vigente** de X termina en la fecha efectiva. Y lo continúa…». En la fecha efectiva del canje **no había** listado vigente de GTO en USDT.

| Opción | Qué implica | ¿Implementable sin cambiar reglas? |
|---|---|---|
| **(a) Lectura literal**, recomendada | La regla 1 no aplica. La salida de GTOUSDT es un retiro de par (§4.10) y GFTUSDT es un listado nuevo (edad desde el 2023-09-22) | **Sí.** Es lo que implementa la tabla |
| (b) Continuidad del activo | GFT hereda la edad de GTO a través de 298 días sin USDT | **No.** La regla mecánica de 30 días del universo congelado reiniciaría la edad. Habría que **escribir una regla nueva**: modificación metodológica |

**Efecto en A:** con (a), GFTUSDT cumple la edad desde ~2024-03; con (b), desde ~2023-10, unas 21 formaciones antes.

Los mismos rasgos tienen LUNA(viejo)→LUNC (119 días) y UST→USTC (301 días; los dos en la lista fija, sin efecto). Por eso D-1 es **una** decisión para los tres.

**Me detengo aquí:** no adopté (b) porque exige una regla nueva. El v3 **exige** que tu autorización contenga la frase de D-1 (lectura literal); sin ella, rechaza.

### 2.3 B2, tratamiento de errores

Ver C11 en §4.

**Resultado terminal inequívoco:**
- **antes** de crear la salida, todo fallo es un `Rechazo`: no consume la ejecución ni deja registro de intento;
- **después**, cualquier excepción (incluidas `SystemExit` de código congelado y `KeyboardInterrupt`) deja `RESULTADO_E3.json` con «ERROR», escrito atómicamente, nunca un éxito aparente;
- si ni siquiera se puede escribir, el intento queda abierto y el siguiente se rechaza (revisión manual).

---

## 3. Hallazgos nuevos de esta fase

1. **BTT, NANO, BZRX, RAMP, EPS, GXS, VIDT, BNX y LUNA** tienen anuncio archivado completo (fechas, relación y apertura). La afirmación del informe de reparación «sin anuncio archivado» es falsa para LUNA, VIDT y BNX, como ya decía la revisión.
2. **LUNAUSDT es una serie única que mezcla dos activos.** La v2 trataba a Terra 2.0 como continuación del LUNA viejo, justo el caso que motivó la Adenda 1. El v3 lo divide (regla 1R).
3. **18 reverse splits de tokens apalancados** con anuncio archivado. Se aplican por literalidad; sin efecto, porque los apalancados están excluidos de todo universo.
4. **Recall de la conciliación congelada:** no figuran como eventos varios retiros de pares USDT con anuncio archivado:
   - GTO, BTCST, SRM y TRIBE, el 2022-11-28;
   - KEY, el 2023-02-10;
   - los cierres por canje de 2021–2023.

   Ninguno mueve A: una falla con fecha < 2023-05-08 da un lunes siguiente ≤ 2023-05-15, y el escaneo por cuerpo desde el 2023-04-28 ya estaba completo. Es una limitación de M0/M1 que se declara.
5. **KEY** (corte de 28 días) es un retiro y una reincorporación del par, no un canje. **SCR** es el paso de pre-mercado a spot. Los dos son el mismo listado.

---

## 4. Fase 2: modificaciones técnicas (orquestador v3)

**Archivos:**

| Archivo | sha256 |
|---|---|
| `orquestador_v3/ejecutar_E3_v3.py` | `c089cc6a…` |
| `ENTRADAS_CONGELADAS_V3.json` | `a89b6a23…` |
| `DIFF_v2_v3.diff` | — |

**Generación:** `generar_v3.py` toma el v2 congelado (`01fc9344…`, sin modificarlo) y arma el v3 con cabecera nueva + **el bloque de cálculo del v2, verificado línea por línea: 341 líneas, 1 sola distinta** + cola nueva.

**El cálculo no cambia:** `ejecutar` del v3 y del v2 dan **salidas idénticas** en dos paneles sintéticos (prueba `test_ejecutar_del_v3_identico_al_del_v2`).

| Cambio | Qué hace, exactamente | Función o constante |
|---|---|---|
| **C7** Ventana A | `INICIO_H_A = "2023-05-15"` y `SHA_VENTANA_A = dcbd80ab…` fijados en el código. El archivo de ventana se verifica por hash **y** por contenido (VÁLIDO, 2023-05-15). Otra ventana se rechaza **antes** de crear la salida | `EXIGIDAS["ventana_A"]`, `modo_real` |
| **C8** Entradas exigidas | `EXIGIDAS`: 15 entradas (nombre, base, ruta, tipo y sha256) fijadas en el código. El manifiesto tiene que coincidir **exactamente**: se rechaza si está vacío, si falta o sobra una entrada, si hay una repetida, si cambia una ruta, si es otro inicio o si es ilegible. Los mapeos se leen **solo** de `mapeos_adenda1_completa` | `leer_y_verificar` |
| **C9** Lectura única | Cada insumo se lee **una vez** a memoria, se hashea y se usa desde esos bytes: series vía `np.load(BytesIO)`, JSON y módulos. Ninguna segunda lectura de disco. Se rechazan enlaces simbólicos (`os.walk` sin seguirlos) | `_leer_archivo`, `_leer_conjunto`, `hash_conjunto_bytes`, `panel_real`, `actividad_desde_bytes` |
| **C10** Código ejecutado | `universo`, `motor` e `inferencia` se **compilan y ejecutan desde los bytes verificados** y se registran en `sys.modules`; nunca `import` desde disco ni `__pycache__`. `SHA_PROPIO` se toma de los bytes leídos al cargar el archivo | `cargar_modulos`, `_BYTES_PROPIOS` |
| **C11** Estados terminales | `Rechazo` antes de la salida; después, EVALUADO, INVALIDO o **ERROR** (etapa, tipo, mensaje, traceback y su sha256, y si había estadísticos), con escritura atómica (temporal, fsync y reemplazo). **Registro de intentos** `INTENTOS_E3.jsonl` con `flock`. Se rechaza: después de un EVALUADO o un INVALIDO; con un intento abierto; tras un ERROR con estadísticos iniciados; tras un ERROR previo sin autorización **nueva** que cite «REINTENTO TRAS ERROR \<sha256 del RESULTADO\>». Una ejecución concurrente queda bloqueada | `escribir_atomico`, `Intentos`, `permitir_intento`, `resultado_error`, `resultado_invalido`, `modo_real` |
| **C12** Mapeos completos | Reglas 1, 2 y **1R** (ticker reutilizado: el tramo anterior pasa a la fila «X~HASTAaaaammddUSDT» y X queda como listado nuevo). Se rechazan duplicados, reglas desconocidas, huecos ≥ 30 días en la regla 1 y cualquier cambio de marca de lista fija o de apalancado. La comprobación corre **antes** de crear la salida, solo con `estado` | `aplicar_mapeos`, `comprobar_marcas`, `marcas` |
| **C13** Autorización | Además de la FRASE (nueva, nombra la ventana y la tabla completa) y de los sha256 del v3 y del manifiesto, exige las frases de **decisión**: reapertura y Adenda R (D-A/B/C), y D-1 | `FRASE`, `FRASES_DECISION` |
| M4 | Restituidas en el docstring las operacionalizaciones fijadas antes de cualquier resultado | docstring |
| M8 | `zip(…, strict=True)` en `contribuciones` | — |

**Demostración en el camino real:**
1. Las pruebas del v3 corren `modo_real` completo sobre árboles E3 sintéticos. Una de ellas llega a **EVALUADO de punta a punta**, con la validez previa y `ejecutar` reales, sobre 40 monedas y BTCUSDT en todo el rango.
2. **Pruebas de mutación** (§5.3): se quitó cada defensa del código y la suite la detectó en todos los casos.
3. Con los insumos **reales**:
   - `leer_y_verificar` del v3 pasa los 15 sha256;
   - la tabla se aplica sin rechazos (solo `estado`);
   - el punto de entrada real **rechaza sin autorización**, sin crear la salida ni el registro de intentos (`verificaciones/entrada_real_sin_autorizacion.txt`).

**Residuales técnicos declarados:**
- **sha256 propio:** se toma de los bytes leídos al cargar el módulo, no de lo que compiló el intérprete. Queda una ventana de microsegundos al arrancar.
- **Registro de intentos:** borrarlo a mano anula su protección. Las carpetas de salida persisten, y una salida existente igual se rechaza.
- **Enlaces simbólicos en directorios padres** de los insumos: no se controlan.
- **Atomicidad:** es por construcción (temporal, fsync y `os.replace`); se prueba que no queden temporales y que el JSON sea válido, no un corte de energía real.

---

## 5. Fase 4: pruebas reproducibles

**Entorno:** Python 3.11.17, numpy 2.4.6, pytest 9.1.1 (venv `integracion_controlada_2026-10-25/venv`). Siempre con `-B -p no:cacheprovider` y temporales dentro del área aislada.

### 5.1 Suites

| Suite | Contra | Resultado | Archivo |
|---|---|---|---|
| Autor (`test_orquestador_v2.py`), neutralizada con el `conftest.py` de la revisión | v2 | **28 passed, 6 xfailed**; los 6 xfail del v1 fallan por la razón declarada | `pruebas/reproduccion/suite_autor_v2.txt` |
| Revisión (`test_revision_adicional.py`) | v2 | **7 passed, 10 xfailed**; cada xfail falla por su razón: los defectos **siguen en el v2** | `pruebas/reproduccion/suite_revision_v2.txt`, `razones_xfail_revision_v2.txt` |
| **Nueva** (`pruebas/test_orquestador_v3.py`) | **v3** | **51 passed** | `pruebas/resultado_suite_v3.txt` |

### 5.2 Mismo escenario: falla en el v2 y pasa en el v3

| Defecto | En el v2 (xfail, razón verificada) | En el v3 (pasa) |
|---|---|---|
| B2 fallo sin estado | «no queda ningún estado explícito del fallo» | `test_excepcion_en_cada_etapa_deja_ERROR_explicito` ×3, `…systemexit_e_interrupcion…`, `…fallo_al_escribir…` |
| I5 TOCTOU | «el panel se construyó con datos alterados después de la guarda» | `test_alterar_insumos_despues_de_verificar…`, `test_cada_insumo_se_lee_una_sola_vez` |
| I2 mapeos sin verificar | «usó un archivo de mapeos sin verificar» | `test_mapeos_solo_desde_la_entrada_verificada`, `test_tabla_de_mapeos_alterada…` |
| I1 ventana | «aceptó otra ventana» | `test_ventana_B_se_rechaza…`, `test_ventana_B_con_manifiesto_y_hash_ajustados…` |
| I3 manifiesto | «aceptó un manifiesto vacío» | `test_manifiesto_invalido…` ×7 |
| I4 bytecode | «se ejecutó un .pyc distinto del .py verificado» | `test_pyc_envenenado_no_se_ejecuta` |
| M1 apalancado | «el token apalancado perdió su marca» | `test_retirar_la_base_de_un_apalancado_se_rechaza`, `test_fusionar_marcas_distintas…` |
| M2 hueco ≥ 30 | «edad reiniciada en el día 140» | `test_regla_1_con_hueco_de_30_dias_o_mas_se_rechaza` |
| M3 duplicado | «DID NOT RAISE» | `test_mapeo_de_regla_2_duplicado_se_rechaza` |

**Además, nuevas en el v3:**
- regla 1R y su rechazo sin corte;
- cadena regla 1 → regla 2;
- regla desconocida;
- identidad sin mapeos;
- réplica de las marcas de `universo.Panel`;
- reintentos (con y sin estadísticos);
- intento abierto;
- concurrencia;
- salida existente;
- autorización incompleta ×5;
- EVALUADO de punta a punta y rechazo de una segunda ejecución;
- hash del conjunto igual al del v2;
- hashes fijados iguales a los congelados;
- **higiene:** ningún temporal contiene la frase real, los hashes reales ni las frases de decisión.

### 5.3 Mutación (`pruebas/mutantes.py`, `pruebas/resultado_mutantes.txt` y `.json`)

**15 mutantes, 0 sobreviven.** Cada uno quita una defensa del v3 y corre la suite completa contra él (50 pruebas + 1 omitida, la que compara los hashes del v3 generado).

| Mutante | Defensa quitada | Pruebas que lo detectan |
|---|---|---|
| C7_ventana_no_fijada | Sin hash ni contenido de la ventana | `test_ventana_B_con_manifiesto_y_hash_ajustados_igual_se_rechaza`, `test_ventana_B_se_rechaza_antes_de_crear_la_salida` |
| C8_manifiesto_vacio_o_incompleto | Acepta un manifiesto vacío o al que le falta una entrada | `test_manifiesto_invalido_se_rechaza_sin_crear_salida[falta_una]`, `test_manifiesto_invalido_se_rechaza_sin_crear_salida[vacio]` |
| C8_mapeos_desde_el_manifiesto | Lee los mapeos de la ruta que diga el manifiesto (como el v2) | `test_mapeos_solo_desde_la_entrada_verificada` |
| C9_relectura_de_disco | Vuelve a leer las series de disco después de verificar | `test_alterar_insumos_despues_de_verificar_no_llega_al_panel`, `test_cada_insumo_se_lee_una_sola_vez` |
| C9_acepta_enlaces | Acepta enlaces simbólicos | `test_enlace_simbolico_en_las_series_se_rechaza` |
| C10_import_desde_disco | `import` desde disco (como el v2) | `test_pyc_envenenado_no_se_ejecuta` |
| C11_sin_estado_ERROR | Sin manejo de excepciones después de crear la salida | `test_control_el_camino_real_llega_al_panel`, `test_excepcion_en_cada_etapa_deja_ERROR_explicito[calculo-ejecutar]`, `test_excepcion_en_cada_etapa_deja_ERROR_explicito[panel-panel_real]`, `test_excepcion_en_cada_etapa_deja_ERROR_explicito[validez_previa-validez_previa]`, `test_fallo_al_escribir_el_resultado_es_ERROR_valido`, `test_reintento_tras_ERROR_con_estadisticos_se_rechaza`, `test_reintento_tras_ERROR_previo_a_estadisticos`, `test_systemexit_e_interrupcion_dentro_del_calculo_tambien_son_ERROR` |
| C11_sin_registro_de_intentos | Sin control del registro de intentos | `test_EVALUADO_de_punta_a_punta_y_sin_segunda_ejecucion`, `test_intento_sin_estado_terminal_bloquea`, `test_reintento_tras_ERROR_con_estadisticos_se_rechaza`, `test_reintento_tras_ERROR_previo_a_estadisticos` |
| C11_sin_bloqueo | Sin bloqueo del registro | `test_ejecucion_concurrente_bloqueada` |
| C12_acepta_duplicados | Acepta mapeos repetidos | `test_mapeo_de_regla_2_duplicado_se_rechaza` |
| C12_acepta_huecos_largos | Acepta huecos ≥ 30 días en la regla 1 | `test_regla_1_con_hueco_de_30_dias_o_mas_se_rechaza` |
| C12_sin_control_de_marcas | Sin control de marcas (lista fija o apalancado) | `test_fusionar_marcas_distintas_se_rechaza`, `test_retirar_la_base_de_un_apalancado_se_rechaza` |
| C12_1R_sin_dividir | La regla 1R no divide la serie | `test_regla_1R_divide_la_serie_y_el_tramo_nuevo_es_listado_nuevo` |
| C12_mapeos_despues_de_crear_la_salida | Comprueba los mapeos recién después de crear la salida | `test_mapeo_imposible_se_detecta_antes_de_crear_la_salida` |
| C13_sin_frases_de_decision | No exige las frases de decisión | `test_autorizacion_incompleta_se_rechaza[3]`, `test_autorizacion_incompleta_se_rechaza[4]` |

### 5.4 Verificaciones con datos reales, sin precios ni volúmenes

| Script | Lee | Resultado |
|---|---|---|
| `tabla/construir_tabla.py` | textos y actividad | 107 citas verificadas; actividad coherente; 0 problemas |
| `verificaciones/ventana_tabla_completa.py` | `estado` (con guarda) | Ventana A sin cambios |
| `verificaciones/mapeos_sobre_estado_real.py` | bytes de las series (solo hash) + `estado` y `simbolo` (con guarda) | 50 mapeos sin rechazo; solo cambia HIFI en A |

---

## 6. Integridad antes y después

### 6.1 Huellas, con la misma receta

Árboles: `find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum`. Páginas: `sha256sum * | sha256sum`.

| Objeto | Inicio (`registro/huellas_inicio.txt`) | Fin (`registro/huellas_fin.txt`) |
|---|---|---|
| UTC | `2026-10-27T18:11:53Z` | `2026-10-27T18:52:23Z` |
| E3 | `4909ef95f7186d4affb98ebe3ea998568e00a0c0aea9229f60622eaf83f477df` | `4909ef95f7186d4affb98ebe3ea998568e00a0c0aea9229f60622eaf83f477df` |
| E3R | `649a72f537905d8dab9166ca17bb50aa9c24bfe409319df6687292cc9f23ad54` | `649a72f537905d8dab9166ca17bb50aa9c24bfe409319df6687292cc9f23ad54` |
| REP | `9bcacf49935f8000274dc8aa2e1bd7b133d92e1d5ce696b6c8f472111d41ceae` | `9bcacf49935f8000274dc8aa2e1bd7b133d92e1d5ce696b6c8f472111d41ceae` |
| RV | `a6fb7f6b33c066205c2b264d1c38633f5ba1425f338e5dff259d93ab75e09e8d` | `a6fb7f6b33c066205c2b264d1c38633f5ba1425f338e5dff259d93ab75e09e8d` |
| paginas | `f12afb9897a80a1cfaeb09c94dbf11cd2cd3f3839a21883c65a5a2d461cbdb8f` | `f12afb9897a80a1cfaeb09c94dbf11cd2cd3f3839a21883c65a5a2d461cbdb8f` |
| git | `HEAD 72ffae5 rama claude/algo-trading-simulation-platform-ngf7xo cambios` | `HEAD 72ffae5 rama claude/algo-trading-simulation-platform-ngf7xo cambios` |
| MANIFEST_reparacion | `92/92` | `92/92` |
| MANIFEST_revision | `41/41` | `41/41` |

### 6.2 Diferencias

**Única diferencia: la marca de hora** (inicio 2026-10-27T18:11:53Z; fin 2026-10-27T18:52:23Z). Los árboles congelados (E3, E3R, reparación y revisión) y las páginas archivadas tienen la misma huella. Git sigue en HEAD `72ffae5`, sin cambios y con el mismo índice. Los MANIFEST de la reparación (92/92) y de la revisión (41/41) validan. No quedaron `__pycache__`, `.pytest_cache`, `/tmp/pytest-of-root` ni registros de intentos. Los temporales de las pruebas se borraron, después de comprobar (prueba de higiene) que no contenían la frase real, los hashes reales ni las frases de decisión.

### 6.3 Qué datos reales se leyeron

- **Textos archivados:** las 8.028 páginas.
- **Actividad:** `auditoria_por_simbolo.json`.
- **Arreglos `estado` y `simbolo`** de las series, con una guarda que aborta ante cualquier otro.
- **Bytes de las series, solo para hashearlos** (huellas, `generar_v3.py`, `leer_y_verificar`).
- **Ningún** O, H, L, C ni QV; ningún precio derivado (no se usaron los saltos de precio de `estructural.json`); ningún retorno.

---

## 7. Fase 3: metodología

Detalle en `metodologia/COMPARACION_METODOLOGICA.md`.

**M0** (v3 congelada):
- no tiene ventana válida: (iv) falla en todos los años porque el archivo termina el 2024-11-06;
- E3 sigue **CERRADO · NO EVALUABLE**.

**M1** (M0 + Adenda R con R1 literal):
- ventana A del 2023-05-15 al 2026-05-18, 158 semanas, margen de 2 semanas;
- **revierte** la decisión expresa del CIERRE §2 sobre (iv);
- **anula** (iii);
- reemplaza (ii) por (ii′) y (iv) por (iv′);
- **dispensa** el CIERRE §4.

**Riesgos de M1:**
- (iv′) es parcialmente circular;
- punto ciego para fallas posteriores al 2024-11-06;
- fragilidad: una salida más sin evidencia en 2023 la invalida;
- la regla de validez se eligió después de ver que M0 no corre, aunque sin ninguna fuga de información sobre H1/H2.

**No adopté R ni modifiqué ninguna regla congelada.**

---

## 8. Recomendación final

**APTO PARA SOLICITAR AUTORIZACIÓN**, con estas condiciones explícitas:

1. **La solicitud tiene que presentar como decisiones tuyas:**
   - D-A: reabrir E3;
   - D-B: adoptar la Adenda R con R1 literal;
   - D-C: revertir el CIERRE §2 en lo que toca a (iv) y dispensar el CIERRE §4;
   - **D-1**: lectura literal de la regla 1 para GTO→GFT, LUNA→LUNC y UST→USTC.

   El v3 no corre sin esas frases.
2. **D-3** (fechas N5 frente a A3.1.5) y **D-5** (riesgos residuales) se aceptan o se rechazan expresamente.
3. **Revisión independiente (D-6).** La revisión anterior ponía una segunda revisión humana o de un tercero como condición para quedar APTO. **Esa revisión no se hizo**: esta fase la hizo el mismo agente.
   - La saco de las condiciones para **solicitar** y la recomiendo como paso **previo a firmar** la autorización.
   - El motivo: la parte de ingeniería ahora tiene evidencia objetiva (camino real y mutación), así que depende menos de quién la revisó. Las interpretaciones de §2.2 y §7, en cambio, sí se beneficiarían de otra mirada.
   - Si preferís mantenerla como condición previa a la solicitud, el dictamen es **NO APTO hasta esa revisión**, y nada más falta.
4. **Lo que sigue sin resolverse, porque exigiría datos prohibidos o una regla nueva:**
   - si HIFI cumple (d) en sus 9 formaciones (requiere QV real);
   - la continuidad GTO→GFT por la opción (b) (requiere una regla nueva);
   - la exhaustividad de exclusiones posteriores al 2024-11-06 (no hay fuente permitida).

**Justificación:**
- los dos bloqueantes y los cinco defectos importantes de la revisión están corregidos en el camino real y demostrados con pruebas que fallan en el v2 y pasan en el v3;
- ningún mutante sobrevive;
- la tabla está completa para el período archivado y verificada contra el texto;
- la ventana A no cambia;
- el cálculo es idéntico al del v2.

> **Quedar apto para solicitar no es una autorización.** No avanzo a E3-H1/H2 sin una aprobación explícita posterior.

---

## 9. Hechos demostrados, dependencias y decisiones

### Demostrado (reproducible desde el área aislada)

- **Tabla:** 76 entradas, 50 mapeos, 107 citas presentes en sus páginas, actividad coherente y los 117 pares del barrido clasificados.
- **Retiro de GTO/USDT:** ocurrió el 2022-11-28, antes del canje.
- **Ventana A** sin cambios con la tabla completa.
- **v3:**
  - bloque de cálculo idéntico al del v2 salvo `strict`, y salidas idénticas en dos paneles;
  - 51 pruebas pasan;
  - ningún mutante sobrevive;
  - los insumos reales pasan los 15 sha256;
  - la entrada real rechaza sin autorización.
- **v2:** sus defectos persisten (10 xfail por la razón correcta).
- **Integridad:** huellas iniciales y finales idénticas para E3, E3R, la reparación, la revisión y las páginas; Git sin cambios.

### Depende de otros informes, no lo verifiqué yo

- La potencia de 0,35–0,56.
- La historia de F3 (que las 757 series sean las mismas que F3 congeló): verifiqué la huella, no la historia.
- Que nadie haya visto P0 antes de congelar la Adenda R: ni demostrable ni refutable.
- Las certezas «media» de COCOS→COMBO, TVK→VANRY y MFT→HIFI: solo está archivado el anuncio de finalización, así que E es la fecha de ese anuncio.

### Te corresponde decidir

D-A, D-B, D-C, D-1, D-2, D-3, D-4, D-5, D-6 y, por separado, **D-7 (autorizar la ejecución única)**.
