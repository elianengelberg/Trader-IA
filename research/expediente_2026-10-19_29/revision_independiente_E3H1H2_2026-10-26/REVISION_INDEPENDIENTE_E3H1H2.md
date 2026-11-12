# Revisión independiente final: reparación E3-H1/H2

**Fecha:** 2026-10-27 (UTC).
**Objeto:** la reparación cerrada el 26/10/2026 en `reparacion_E3H1H2_2026-10-26/`:
- `orquestador_v2/DIFF_v1_v2.diff`;
- `renombres/CLASIFICACION_RENOMBRES.md`;
- `segunda_pasada/SEGUNDA_PASADA_CASO_POR_CASO.md`;
- `INFORME_REPARACION_E3H1H2.md`;
- su relación con `CIERRE_E3.md` (§2 y §4) y con la Adenda R.

**Área de trabajo:** `revision_independiente_E3H1H2_2026-10-26/`, dentro del scratchpad. Las rutas de este informe son relativas al scratchpad, salvo indicación.

> **Limitación de independencia, declarada primero.** Esta revisión la hizo el mismo agente que escribió la reparación. Para compensarlo:
> - no tomé el informe del autor como prueba;
> - escribí código propio para recalcular la ventana, verificar mapeos y citas y buscar omisiones;
> - verifiqué cada prueba con fallos provocados.
>
> Aun así, comparto con el autor los puntos ciegos de método. **No reemplaza una revisión humana o de un tercero.**

**Lo que no hice:**
- no ejecuté E3-H1/H2;
- no leí precios reales: ningún arreglo O, H, L, C ni QV de las 757 series;
- no calculé retornos con datos reales;
- no creé ninguna autorización ni archivo que la reemplace;
- no modifiqué árboles congelados, datos originales, series ni páginas archivadas;
- no toqué Git ni desplegué nada.

De las series reales solo se leyó el arreglo `estado`, con una guarda que aborta ante cualquier otro arreglo. Para las huellas se leyeron bytes, sin interpretarlos.

Ningún archivo de esta revisión contiene a la vez la frase de autorización y los hashes que exige el v2:
- la frase aparece solo dentro de `verificaciones/diff_recalculado.diff`, como línea de código del v2, igual que en `DIFF_v1_v2.diff`;
- el hash completo del v2 aparece solo como aserción de identidad de la copia, en `pruebas/test_revision_adicional.py`.

---

## 0. Disponibilidad e integridad (verificado antes y después)

| Control | Inicio (`registro/huellas_inicio.txt`) | Fin (`registro/huellas_fin.txt`) |
|---|---|---|
| `MANIFEST.sha256` de la reparación | 92/92 OK (`registro/manifest_reparacion_check.txt`) | 92/92 OK |
| Árbol E3 | `4909ef95…` | `4909ef95…` |
| Árbol E3R | `649a72f5…` | `649a72f5…` |
| Árbol de la reparación | `9bcacf49…` | `9bcacf49…` |
| Páginas archivadas | `f12afb98…` | `f12afb98…` |
| Repositorio | HEAD `72ffae5`, 0 cambios, índice `37490035…` | idéntico |

**Recetas de las huellas:**
- árboles: `find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum`;
- páginas: `sha256sum * | sha256sum`;
- Git: `git --no-optional-locks status --porcelain` y `sha256sum .git/index`.

**Copia aislada:** `revision_independiente…/copia_aislada/` es byte a byte idéntica a la reparación (`diff -rq` sin diferencias, MANIFEST 92/92) y a los módulos congelados de E3. Todas las pruebas corrieron ahí o contra módulos importados sin escribir en el árbol congelado.

---

## 1. Resumen ejecutivo

**Recomendación: NO APTO PARA SOLICITAR AUTORIZACIÓN, todavía.** La distancia a APTO es corta y mecánica: una tabla de mapeos re-congelada, un v2 corregido y un informe corregido. Además hacen falta tus decisiones de fondo, que esta revisión no puede tomar.

**Lo que se sostiene, demostrado con código propio:**
- **Ventana A.** El recálculo independiente da inicio 2023-05-15, 158 semanas, 158 evaluables y mínimo 120 elegibles. El último inicio válido es 2023-05-29, así que el margen es de 2 semanas.
- **(ii′) y (iv′).** (ii′) coincide con la (ii) de la v3: el inicio de A lo fija la v3, no la Adenda R. (iv′) se cumple desde 2018. El año más ajustado es 2023: 1 de 19 salidas sin evidencia (NBTUSDT).
- **Corrección de R4 (N14).** Es correcta y está aislada:
  - el diferencial sintético propio da 0 de 143 campos distintos en dos paneles;
  - en el panel con semilla 37 solo cambian R4 y el Sharpe deflactado, que depende de R4;
  - el caso construido, de punta a punta, excluye C04USDT con el v2 y C34USDT con el v1.
- **El diff no esconde otros cambios.** Comisiones, retornos, precios, exclusiones y denominadores son idénticos al v1. El diff recalculado coincide byte a byte con el entregado.
- **Segunda pasada.** Es reproducible byte a byte (5/5 salidas). Las 47 citas de resoluciones están en las páginas y las fechas coinciden.
- **Exclusiones.** Los cuerpos de las 8.028 páginas archivadas no contienen ninguna exclusión spot de pares USDT, con fecha ≥ 2023-04-28, que no esté contabilizada.

**Lo que impide solicitar hoy:**
1. **B1 · Tabla de mapeos incompleta frente a la Adenda 1, con efecto dentro de A.**
   - MFT→HIFI (1 MFT = 0,01 HIFI, completado el 2023-01-12) tiene anuncio oficial archivado y no está mapeado. Cambia la elegibilidad por edad de HIFIUSDT en hasta 9 formaciones de A.
   - Hay además al menos 9 renombres o redenominaciones archivados sin mapear, previos a A: BNX, VIDT, LUNA, BTT, NANO, BZRX, RAMP, EPS y GXS.
   - Queda un caso dudoso: GTO→GFT.
   - El informe afirma «LUNA, VIDT, BNX: sin anuncio archivado», y es falso.
2. **B2 · Un fallo durante la ejecución consume la ejecución única sin dejar estado explícito.** Después de crear la carpeta de salida, cualquier excepción deja solo `REGISTRO_EJECUCION.json`, sin `RESULTADO_E3.json`. Incluye el propio aborto de `aplicar_mapeos`. La guarda de «salida existente» impide repetir.

**Importantes,** a corregir en la misma re-congelación:
- el código acepta cualquier ventana que fije un manifiesto autorizado;
- el archivo de mapeos no tiene que estar entre las entradas verificadas;
- un manifiesto vacío pasa la guarda;
- el código que se ejecuta puede no ser el que tiene hash (bytecode en `__pycache__`);
- hay una brecha de tiempo entre verificar y leer (TOCTOU);
- la suite del autor escribe la frase real y el hash real en archivos temporales.

**Metodología:**
- La Adenda R **es una modificación metodológica**: sustituye (ii)–(iv) y anula (iii).
- Revierte una decisión expresa del CIERRE §2 («No se relajó la regla (iv)»).
- No cumple la condición de reapertura del CIERRE §4: la lista de renombres es incompleta incluso dentro del período archivado.
- Eso no la invalida, pero solo vos podés aprobarla, y por escrito.

> **APTO PARA SOLICITAR no es autorización para ejecutar.** Aunque se corrija todo, la ejecución sigue requiriendo tu autorización expresa y separada.

---

## 2. Hallazgos

### 2.1 Bloqueantes

**B1 · La tabla de mapeos no cumple la Adenda 1 «aplicada sin excepciones», y el efecto cae dentro de A.**

**Evidencia documental confirmada,** todo texto archivado en el cuerpo de la página:

- **MFT→HIFI** (`url_…binance-has-completed-the-ma_934dcf237cdb.json`, captura 20230322004714):
  - «Binance has completed the Mainframe (MFT) token swap, redenomination and rebranding plan to Hifi Finance (HIFI)… at a ratio of 1 MFT = 0.01 HIFI»;
  - fecha del anuncio: 2023-01-12;
  - actividad: MFTUSDT termina el 2023-01-02 y HIFIUSDT empieza el 2023-01-12 (hueco de 9 días, < 30);
  - en la tabla de 22 no está, y `CLASIFICACION_RENOMBRES.md` no lo lista.
- **Efecto en A** (inferencia aritmética, sin leer volumen):
  - sin mapeo, HIFIUSDT recién cumple (b), edad ≥ 180 días, el 2023-07-11;
  - con mapeo hereda la edad de MFT (desde 2019-08-27);
  - las formaciones 2023-05-15 a 2023-07-10 (9) pueden cambiar de composición si HIFI cumple (a) y (d);
  - no verifiqué (d) porque exige leer QV real.
- **BNX:**
  - «As Binance has completed the BinaryX (BNX) token swap and redenomination… update the trading start time for the… BNX/USDT… to 2023-02-22»;
  - «The distribution of BNX was conducted at a ratio of 1 BNXOLD = 100 BNX»;
  - el informe (§4, tabla de los 8 cortes) dice «Sin anuncio archivado → regla 3»: **falso**.
- **VIDT:** «Binance will support the VIDT Datalink (VIDT) token swap, redenomination and rebranding plan to VIDT DAO (VIDT)». El informe dice que no hay anuncio: **falso**.
- **LUNA (vieja)→LUNC y Terra 2.0** (bn_c52fa3c6…, bn_d044a674…): «The ticker for Terra Classic, or the LUNA (old) token, has since been renamed as LUNC». El informe dice que no hay anuncio: **falso**.
  - LUNAUSDT es el ejemplo que **motivó** la Adenda 1.
  - Con la regla 3 que aplica el v2, el LUNA nuevo (Terra 2.0) hereda la edad del viejo, justo lo que la regla 1 quería impedir («ese tramo es un listado nuevo… aunque el corte haya durado menos de 30 días»).
  - En A no tiene efecto: con cualquiera de las dos lecturas, LUNA y LUNC superan los 180 días antes del 2023-05-15, y el corte es de 2022.
- **Otros renombres o redenominaciones archivados y no mapeados,** todos en páginas con título ilegible (CSS), de 2022, previos a A:
  - BTT→BTTC 1:1000;
  - NANO→XNO;
  - BZRX→OOKI 1:10;
  - RAMP→LEVER;
  - EPS→EPX;
  - GXS→REI.
  - Las citas están en `verificaciones/renombres_en_paginas_ilegibles.txt`.
- **GTO→GFT** (dos páginas: «will support…» y «has completed…»): «ratio of 1 GTO = 1 GFT», canje completado alrededor del 2023-02-08.
  - GTOUSDT terminó el 2022-11-27, **antes** del canje, y GFTUSDT empezó el 2023-09-22.
  - La regla 1 habla de «el listado vigente de X», y en la fecha efectiva no había par USDT de X vigente.
  - **Duda no resuelta:** la regla congelada no decide este caso. Ver también el hallazgo M2.

**Por qué es bloqueante:**
- la autorización fija por hash una tabla que se sabe incompleta respecto de una regla congelada «sin excepciones»;
- el efecto cae dentro de A;
- la ejecución es única;
- la corrección es barata y se apoya solo en textos, sin retornos.

**Causa raíz:**
- la extracción de candidatos de renombre depende del título. Hay 929 páginas con título CSS ilegible, todas clasificadas «otro», y en 2023 hay páginas tituladas genéricamente «Announcement», como las de MFT→HIFI y GTO→GFT;
- el control por actividad del autor (`segunda_pasada/escaneo_cambios_simbolo_A.txt`) empieza en 2023-05-03. Pero la edad de un par importa dentro de A si empezó a cotizar hasta 180 días antes, desde 2022-11-16. HIFIUSDT, que empezó el 2023-01-12, quedó fuera por construcción.

**Efecto de los casos previos a A** (demostrado sintéticamente, ver §6):
- un salto de nivel ×0,01 en un corte, sin regla 2, no cambia el universo, la señal, A ni el IC de ninguna formación posterior a la reapertura;
- esto vale porque (a) exige 30 días activos seguidos y `P.r` no cruza huecos;
- en particular, BNX (reapertura 2023-02-22, dentro de [inicio de A − 90 días, inicio de A)) no altera A;
- igual deben mapearse, porque la regla lo exige.

**B2 · El camino de fallo consume la ejecución única sin estado explícito.**

- **Dónde:** `ejecutar_E3_v2.py`, `modo_real`.
  - Línea 521: `salida.mkdir(parents=True)`.
  - Línea 525: escribe `REGISTRO_EJECUCION.json`.
  - Líneas 528–543: importar, aplicar los mapeos, calcular la validez y `ejecutar`, sin `try/except`.
  - Línea 511: `if salida.exists(): raise SystemExit("… la ejecución confirmatoria es única")`.
- **Escenario concreto:**
  - `aplicar_mapeos` aborta con `SystemExit("mapeo imposible…")` (líneas 124–125, 131–132, 135–136, 143–147) solo cuando ya leyó las series reales;
  - lo mismo pasa con un error numérico o de memoria en `ejecutar`;
  - queda la carpeta de salida sin `RESULTADO_E3.json`, ni «INVALIDO» ni «ERROR»;
  - la ejecución única queda consumida;
  - el resultado se confunde con «fallo ordinario» o «dato faltante»: el punto 4 del encargo lo prohíbe.
- **Probado:** `test_fallo_durante_el_calculo_deja_estado_explicito`, xfail estricto, falla con «no queda ningún estado explícito del fallo».
- **Acción:**
  - escribir siempre `RESULTADO_E3.json` con `veredicto: "ERROR"`, la etapa, el tipo, el mensaje y el hash del traceback;
  - prerregistrar qué pasa tras un ERROR (por ejemplo: un fallo antes de cualquier estadístico admite una repetición con autorización nueva; un fallo después, no);
  - mover la verificación de consistencia de mapeos, que solo necesita `estado`, **antes** de crear la salida.

### 2.2 Importantes

**I1 · El código no fija la ventana A.**
- La línea 526 compara `vd["inicio_H"]` con `entradas["inicio_H_esperado"]`, que viene del manifiesto.
- Con otro manifiesto, y una autorización con su hash, acepta otra ventana, por ejemplo B (2021-02-22). Lo prueba `test_solo_la_ventana_A_es_aceptada_por_el_codigo`, que falla con «aceptó otra ventana».
- La FRASE dice «VENTANA A», pero no fija la fecha.
- La cadena humana, en la que la autorización nombra el hash del manifiesto, lo mitiga. Falta la defensa en profundidad.
- **Acción:** constante en el código con el inicio 2023-05-15 y el sha256 del archivo de ventana A.

**I2 · El archivo de mapeos no está atado a una entrada verificada.**
- La línea 529 lee `AQUI.parent / entradas["mapeos"]`, una ruta que dicta el manifiesto, sin comprobar que esté entre las entradas verificadas.
- Hoy coincide con `mapeos_adenda1` (`aeb8b5f2…`), pero el código no lo garantiza. Lo prueba `test_archivo_de_mapeos_debe_estar_verificado`.
- **Acción:** leer los mapeos solo desde la entrada verificada, idealmente de los mismos bytes hasheados.

**I3 · Un manifiesto vacío o parcial pasa la guarda.**
- `verificar_entradas` (líneas 80–90) recorre las entradas que haya. Con `"entradas": []` no verifica nada y sigue.
- Lo prueba `test_manifiesto_sin_entradas_no_pasa_la_guarda`.
- **Acción:** el código exige el conjunto mínimo de 15 nombres y rutas.

**I4 · Lo que se ejecuta no es necesariamente lo que tiene hash.**
- `importar_congelados` (líneas 53–62) verifica los `.py` y después hace `import`.
- Python carga `codigo/__pycache__/*.cpython-311.pyc` si la cabecera, que guarda fecha y tamaño de la fuente, coincide, sin mirar el contenido.
- El árbol congelado de E3 **tiene** esos `.pyc`, con cabeceras que coinciden.
- `sys.dont_write_bytecode` (línea 32) impide escribir, no leer.
- **Hoy los `.pyc` son equivalentes a las fuentes:** `verificaciones/pyc_check/comparar_pyc.py` compila en memoria y compara el código (`resultado.txt`: True ×3).
- La guarda no lo garantiza. Lo prueba `test_importar_congelados_ejecuta_el_codigo_con_hash`, con un `.pyc` fabricado en un árbol temporal.
- **Acción:** compilar y ejecutar desde los mismos bytes verificados, o `sys.pycache_prefix` hacia un directorio vacío. Eso también cierra I5 para los módulos.

**I5 · Brecha entre verificación y lectura (TOCTOU).**
- `verificar_entradas` (línea 85) hashea bytes; `panel_real` (línea 102) e `importar_congelados` vuelven a leer los archivos.
- Un cambio intermedio no se detecta. Lo prueba `test_insumo_alterado_entre_verificacion_y_lectura_se_detecta`, que falla con «el panel se construyó con datos alterados después de la guarda».
- La probabilidad es baja con un solo usuario, pero la afirmación «verifica antes de leer cualquier precio» promete más de lo que garantiza.

**I6 · La Adenda R y el CIERRE: el informe no lo presenta completo.**

El informe (§9 y §10) pide nombrar «la sustitución de (iv) por (iv′) y de la condición de reapertura de CIERRE §4». No menciona:
- que (iii) también se deja de aplicar (Adenda R, R3);
- que (ii) se sustituye por (ii′);
- que el CIERRE §2 registró como «**decisión expresa**» «No se relajó la regla (iv)».

Ver §4.

**I7 · La extracción congelada tiene recall incompleto y el informe sobrestima la cobertura.**
- Hay 929 páginas con título ilegible (`verificaciones/titulos_rotos.json`), todas tipo «otro». 188 tienen lenguaje de exclusión, en su mayoría en las barras laterales.
- En los cuerpos de esas páginas encontré 40 frases de exclusión (`paginas_no_extraidas.json`). 10 son spot con par USDT, fechadas del 2021-12-14 al 2022-09-26; ninguna es ≥ 2023-04-28.
- **Efecto en A:** ninguno. El escaneo de los cuerpos de las 8.028 páginas (`escaneo_exclusiones_en_A.json`) no encontró exclusiones spot USDT ≥ 2023-04-28 sin contabilizar.
- **Efecto en renombres:** sí lo hay (B1).
- «Están listas la ventana, los mapeos y la guarda» (informe §10) no es cierto para los mapeos ni para la guarda.

**I8 · La suite del autor escribe la frase real y hashes reales en archivos temporales.**
- `orquestador_v2/pruebas/test_orquestador_v2.py`, líneas 193, 195, 269–275 y 298.
- Escribe `V2.FRASE` real + sha256 real del v2 en `autorizacion_v2.txt`, y la FRASE real del v1 + el hash real del v1 en `autorizacion_v1.txt`.
- Con el hash del manifiesto real, que es público, ese texto sería una autorización válida.
- En esta revisión **no** la corrí así: usé un `conftest.py` que neutraliza frase y hashes (ver §6).
- No encontré archivos residuales con la frase real en `/tmp/pytest-of-root` ni en las áreas de trabajo.
- **Acción:** inyectar una frase y un hash de prueba en la propia suite.

### 2.3 Menores

**M1 · Latente: un token apalancado pierde su marca si su base se renombra.**
- `universo.Panel` (línea 31) infiere «apalancado» de las bases presentes, y el v2 retira la fila X.
- Lo prueba `test_apalancado_conserva_su_marca_si_su_base_se_renombra`.
- **Sin efecto hoy:** ningún símbolo del panel con sufijo UP, DOWN, BULL o BEAR tiene por prefijo una base retirada, ni siquiera MFT, GTO, BNX o VIDT. Lo verifiqué con los nombres de archivo de las 757 series.

**M2 · Latente: un mapeo con hueco de 30 días o más reinicia la edad sin aviso.**
- Es la regla mecánica de 30 días de `universo` después de la fusión. Lo prueba `test_mapeo_con_hueco_de_30_dias_o_mas_conserva_la_edad`: edad reiniciada en el día 140.
- Hueco máximo actual en regla 1: 7 días.
- **Se vuelve material si se mapea GTO→GFT** (hueco de unos 10 meses): el mapeo quedaría anulado en silencio.
- **Acción:** abortar o advertir en `aplicar_mapeos`.

**M3 · Latente: una regla 2 duplicada se aplica dos veces.**
- `aplicar_mapeos` (línea 122) no deduplica.
- Lo prueba `test_mapeo_de_regla_2_duplicado_se_rechaza`: «DID NOT RAISE».
- Es relevante porque la tabla se va a re-congelar.

**M4 · Se perdieron del docstring las «Operacionalizaciones fijadas… antes de cualquier resultado» del v1.**
- Abarcan la semilla de R5, §6.4, V[SR] sobre 20 excesos, BTCUSDT del mismo panel y N19 no calculado (líneas 20–26 eliminadas en el diff).
- El código no cambia. Solo se pierde el registro en el archivo que se autoriza.
- **Acción:** restituirlas o citarlas con el hash del v1.

**M5 · Corrección de fecha N5 en 4 eventos de tokens apalancados.**
- Las fechas pasan de 2023-04-27 (título, A3.1.5) a 2023-05-09/10/11 (cuerpo).
- A3.5 (a) prevé «E corregida según el texto» para casos C; para estos casos T la regla de extracción congelada es la fecha del título.
- La corrección es fiel a N5 y **acorta** A de 160 a 158 semanas. Con las dos lecturas A es VÁLIDA.
- Es una desviación de procedimiento, conservadora, que hay que declarar.

**M6 · BTCST «1:10»: el sentido no está explícito en el texto** (certeza media). Es previo a A y no afecta.

**M7 · Procedencia de la Adenda R.**
- `CONGELACION_ADENDA_R.txt` fija solo el hash de la adenda, a las 19:43:13Z.
- El script P0 (`0452347d…`) recién quedó registrado al ejecutar P0, a las 19:44:40Z.
- En ese registro ya figuran `p0b_verificar_suspension.py` y `p0_auditoria_interna_R1prima.py`. R1′ se congeló después, a las 19:46:57Z.
- No hay evidencia de que se viera un resultado P0 antes de congelar, ni forma de excluirlo (ver §4.4).

**M8 · `contribuciones` usa `zip(…, strict=False)` (línea 206).**
- Si las longitudes difirieran, truncaría sin aviso.
- Hoy no difieren: la forma de `r` es `len(formaciones) − 1`.
- Viene del v1.

---

## 3. Tabla de hallazgos

Las líneas del v2 se refieren a `reparacion_E3H1H2_2026-10-26/orquestador_v2/ejecutar_E3_v2.py` (`01fc9344…`). Las pruebas están en `revision_independiente…/pruebas/test_revision_adicional.py`.

| ID | Sev. | Evidencia verificable | Impacto | Acción requerida |
|---|---|---|---|---|
| B1 | **Bloq.** | Cita MFT→HIFI «1 MFT = 0.01 HIFI» (`…ma_934dcf237cdb.json`); actividad MFT ≤ 2023-01-02, HIFI ≥ 2023-01-12; `nuevos_pares_vs_anuncios.json`. BNX «1 BNXOLD = 100 BNX», reapertura 2023-02-22; VIDT; LUNA→LUNC; 6 más en `renombres_en_paginas_ilegibles.txt`. GTO→GFT 1:1 con par X ya terminado | Hasta 9 formaciones de A con composición distinta (HIFI); el informe afirma algo falso; se violaría la regla 1/2 «sin excepciones» | Completar la tabla leyendo los **cuerpos**; decidir GTO→GFT y documentarlo; re-congelar (`mapeos` → `ENTRADAS_CONGELADAS` → hashes); corregir CLASIFICACION e INFORME |
| B2 | **Bloq.** | Líneas 511, 521, 525, 528–543; `aplicar_mapeos`, líneas 124–147; prueba xfail `fallo_durante_el_calculo` | Ejecución única consumida sin estado; ambigüedad «fallo ordinario» | Estado «ERROR» explícito siempre; regla prerregistrada tras ERROR; chequeo de mapeos antes de `mkdir` |
| I1 | Imp. | Línea 526; prueba `solo_la_ventana_A` | Otra ventana sería aceptada con otro manifiesto autorizado | Fijar la fecha y el hash de la ventana A en el código |
| I2 | Imp. | Línea 529; prueba `archivo_de_mapeos_debe_estar_verificado` | Mapeos sin verificar llegarían al panel | Leer los mapeos de la entrada verificada |
| I3 | Imp. | Líneas 80–90; prueba `manifiesto_sin_entradas` | Guarda vacía | Conjunto mínimo obligatorio en el código |
| I4 | Imp. | Líneas 53–62; `.pyc` en `E3/…/codigo/__pycache__` con cabecera coincidente; `pyc_check/resultado.txt`; prueba `importar_congelados_ejecuta_el_codigo_con_hash` | El código ejecutado no está cubierto por el hash | Ejecutar desde los bytes verificados o con `pycache_prefix` vacío |
| I5 | Imp. | Líneas 85 frente a 102 y 59–61; prueba `insumo_alterado_entre_verificacion_y_lectura` | Garantía más débil que la declarada | Leer una vez, hashear y usar los mismos bytes |
| I6 | Imp. | CIERRE §2 («decisión expresa»), §4; Adenda R, R3 ((iii) no se aplica); informe §10 | La solicitud podría omitir dos sustituciones y la reversión de una decisión | La solicitud nombra (ii)→(ii′), (iii) anulada, (iv)→(iv′), dispensa del §4 y reversión del §2 |
| I7 | Imp. | `titulos_rotos.json` (929 / 188); `paginas_no_extraidas.json`; `escaneo_exclusiones_en_A.json` | Recall incompleto de la extracción; sin efecto en las exclusiones de A, con efecto en los renombres | Declararlo; búsqueda por cuerpo de renombres (B1) |
| I8 | Imp. | `test_orquestador_v2.py`, líneas 193, 195, 269–275, 298 | Archivos con 2 de los 3 elementos de una autorización real | Frase y hash de prueba en la suite |
| M1 | Menor | `universo.py`, línea 31; prueba xfail | Ninguno hoy | Conservar la marca al fusionar o abortar |
| M2 | Menor | Prueba xfail «edad reiniciada en el día 140» | Material si se mapea GTO→GFT | Abortar o advertir si el hueco es ≥ 30 días |
| M3 | Menor | Línea 122; prueba xfail «DID NOT RAISE» | Doble división por r | Rechazar duplicados |
| M4 | Menor | Diff, líneas 20–26 eliminadas | Registro perdido | Restituir o citar |
| M5 | Menor | `resoluciones_manuales.json`: 4 `fecha_corregida`; A3.1.5 frente a N5 | A 158 en lugar de 160 semanas; las dos válidas | Declarar la desviación |
| M6 | Menor | Nota del mapeo BTCST | Ninguno en A | — |
| M7 | Menor | `CONGELACION_ADENDA_R.txt`, `REGISTRO_P0.txt` | Duda de orden; no demostrable | Declarar |
| M8 | Menor | Línea 206 | Ninguno hoy | `strict=True` |

---

## 4. Evaluación independiente de la ventana A y de la Adenda R

### 4.1 Reconstrucción

**Con la v3 congelada pura:**
- (i) da 2020-05-11;
- (ii) da 2023-05-15: es la semana siguiente a la última falla T, que corresponde a tokens apalancados con E entre el 2023-05-09 y el 2023-05-11;
- (iii) no se cumple, por la cobertura del archivo;
- (iv) no se cumple en 2025 (51/51 sin anuncio) ni en 2026 (26/26).
- **La v3 pura da INVÁLIDA.** Coincido con el autor y con el CIERRE.

**Con la Adenda R y R1 literal** (recálculo propio en `verificaciones/ventana_independiente.py`, sin reutilizar el código del autor y leyendo solo `estado`):

| Componente | Valor |
|---|---|
| (i) | 2020-05-11 |
| (ii) de la v3 | 2023-05-15 |
| (ii′) | 2023-05-15: las 6 fallas siguen en alcance con R1 literal |
| (iv′) | 2018 |
| Inicio | 2023-05-15 |
| Semanas | 158 |
| Evaluables | 158 |
| Mínimo de elegibles | 120 (umbral: 30) |
| Último inicio válido | 2023-05-29 (≥ 156 evaluables hasta 2026-05-18) |
| Margen | 2 semanas |

Salidas en alcance sin evidencia, por año:

| Año | Salidas en alcance | Sin evidencia |
|---|---|---|
| 2018 | 1 | 0 |
| 2019 | 2 | 0 |
| 2020 | 17 | 0 |
| 2021 | 10 | 0 |
| 2022 | 35 | 0 |
| 2023 | 19 | 1 (NBTUSDT, 5,3 %) |
| 2024 | 44 | 0 |
| 2025 | 51 | 0 |
| 2026 | 26 | 0 |

**Consecuencia:** el inicio de A **no** lo produce la Adenda R. Lo fija la (ii) de la propia v3. Lo único que hace R es que (iv) se cumpla y que (iii) deje de exigirse.

### 4.2 ¿Corrección, modificación o ambas?

**Las dos, y conviene separarlas:**

- **Correcciones de implementación,** que devuelven el código al protocolo congelado:
  - R4 según N14 (EW bruto);
  - mapeos de la Adenda 1 en lugar de R2, que contradecía la regla 3 de la Adenda 1;
  - segunda pasada según A3.11.
- **Modificación metodológica:** la Adenda R reemplaza un criterio de validez de un protocolo congelado. Sustituye (ii)–(iv) y anula (iii).
  - La propia adenda lo admite (§5: «cambiar un criterio de validez… es una decisión estratégica (categoría B)»).
  - Choca con el CIERRE §2, «No se relajó la regla (iv)», registrado como **decisión expresa**.
  - No cumple la condición del CIERRE §4: «una lista completa y verificable de las exclusiones y renombres de pares USDT… entre 2020-05 y 2026-05». El archivo termina el 2024-11-06 y la lista de renombres es incompleta incluso antes (B1).

### 4.3 Aprobación documental necesaria (toda tuya)

Una autorización escrita que nombre expresamente:
1. la reapertura de E3 (CIERRE §2, último punto);
2. la adopción de la Adenda R (`87f60413…`) con R1 literal, que sustituye (ii) por (ii′) y (iv) por (iv′) y **anula (iii)**;
3. la reversión de la decisión expresa del CIERRE §2 sobre (iv);
4. la dispensa de la condición del CIERRE §4;
5. la aceptación de los riesgos residuales de §7, en particular el punto ciego posterior al 2024-11-06 y el margen de 2 semanas;
6. los hashes **re-congelados** después de B1, B2 e I1–I5 (tabla de mapeos, `ENTRADAS_CONGELADAS.json`, v2);
7. una actualización del registro de hipótesis.

### 4.4 Circularidad y selección retrospectiva

No las doy por inexistentes porque no aparezcan en el diff.

**Regla elegida después de observar su consecuencia:**
- La Adenda R se escribió **después** de que (iv) diera INVÁLIDO.
- Su autor conocía los conteos de salidas por año y que había «242 de 279» filas inválidas en el borde (§5 de la adenda).
- O sea, sabía que había evidencia interna disponible antes de definir SUSPENSION como criterio.
- Se congeló 87 segundos antes de ejecutar P0, con scripts de P0b y R1′ ya escritos (M7).
- No hay prueba de que se haya visto P0 antes de congelar, ni forma de excluirlo.
- Lo que sí se puede afirmar: en los artefactos de E3R y de la reparación **no hay ningún retorno de estrategia, IC ni relación señal-resultado** calculado con datos reales. La elección afecta **si** la prueba corre, no **qué** da.

**Circularidad de (iv′):**
- Usa marcas del propio Vision (`estado` 2 y 3) para certificar que Vision no trunca salidas.
- Una truncación «limpia», sin vela parcial ni cola, es indetectable.
- El tope es de 10 % por año en alcance, y lo mide R6.

**Punto ciego de (ii′):**
- Las fallas T, D y C se detectan con anuncios archivados, y después del 2024-11-06 no hay ninguno.
- Una falla en alcance, no observada, con E posterior al 2023-05-29, dejaría A **INVÁLIDA** (margen de 2 semanas).
- A favor:
  - ninguna exclusión archivada resultó D;
  - las T en alcance fueron tokens apalancados, retirados antes.
- Es un argumento inductivo, no una prueba.

### 4.5 Dictamen sobre A

- **Computacionalmente,** A es VÁLIDA bajo la v3 + la Adenda R con R1 literal. Está demostrado con código propio.
- **Metodológicamente,** su validez depende por completo de que aceptes la Adenda R.
- Con la v3 pura no hay ventana válida.

---

## 5. Dictámenes separados

| Ámbito | Dictamen | Fundamento |
|---|---|---|
| **Integridad y reproducibilidad** | **FAVORABLE con observaciones** | MANIFEST 92/92; diff, segunda pasada y ventana reproducidos byte a byte o de forma independiente; huellas intactas. Observaciones: I4 (el bytecode no está cubierto) e I5 (TOCTOU) |
| **Corrección del orquestador** | **NO FAVORABLE todavía** | C2 (R4) es correcta y está aislada; C4, C5 y C6 son correctas en el camino normal. B2 rompe el punto 4 (estado explícito); I1–I3 debilitan los puntos 5 y 7; I4 e I5, el punto 7 |
| **Validez metodológica** | **CONDICIONAL** | Depende de tu decisión sobre la Adenda R, el CIERRE §2 y el §4 (I6). Además requiere B1 resuelto: hoy viola la Adenda 1 dentro de A |
| **Preparación para ejecutar E3-H1/H2** | **NO PREPARADO** | B1 y B2 abiertos; artefactos por re-congelar; sin autorización |

---

## 6. Pruebas sintéticas adicionales (reproducibles)

**Entorno:** Python 3.11.17, numpy 2.4.6, pytest 9.1.1 (venv `integracion_controlada_2026-10-25/venv`). Siempre con `-B` y `-p no:cacheprovider`, y temporales en `--basetemp` dentro del scratchpad, borrados al terminar.

### 6.1 Suite del autor, reproducida sin la frase real

- **Comando:** `pytest --rootdir copia_aislada --confcutdir copia_aislada …/orquestador_v2/pruebas/test_orquestador_v2.py`.
- **Neutralización:** `copia_aislada/conftest.py` cambia FRASE (v1 y v2) por frases de prueba, y `sha` por `sha256(b"PRUEBA|" + bytes)` en el v1, el v2 y el módulo de prueba. No toca ninguna aserción.
- **Resultado** (`pruebas/resultado_suite_autor_neutralizada.txt`): **28 passed, 6 xfailed.** Coincide con lo que declara el autor.
- **Las 6 regresiones del v1 fallan por la razón correcta** (`pruebas/razones_xfail_suite_autor.txt`):

| Caso | Fallo del v1 |
|---|---|
| R4 | aserción de aporte bruto |
| Serie alterada | `leyo_precios` |
| Ventana inválida | «detenido: P0 no es VÁLIDO: no hay ventana H», en lugar de un INVÁLIDO explícito |
| Regla 2 | crea `R2X0QQQUSDT` |
| Regla 1 | MMMUSDT no se fusiona |
| Regla 3 | crea `R2X0BBXUSDT` |

- Después de correrla, la búsqueda de la frase real y de los hashes reales (v1, v2, manifiesto) en los temporales no encontró nada.

### 6.2 Suite de la revisión (`pruebas/test_revision_adicional.py`)

- **Resultado** (`pruebas/resultado_suite_revision.txt`): **7 passed, 10 xfailed (estrictos).**
- Con `--runxfail`, cada xfail falla por la razón declarada (`pruebas/razones_de_fallo_xfail.txt`).

| Prueba | Resultado | Qué muestra |
|---|---|---|
| `control_la_guarda_de_prueba_funciona` | pasa | El arnés llega a `panel_real` con entradas correctas |
| `validez_previa_fallida_deja_INVALIDO_explicito` | pasa | INVÁLIDO explícito, H1 = H2 = None, evaluables = 0 |
| `escalar_una_serie_por_una_constante_no_cambia_el_motor` | pasa | Sustento de la regla 2: invariancia de escala de r, objetivos e IC |
| `aplicar_mapeos_sin_mapeos_es_identidad` | pasa | Sin efectos colaterales |
| `v2_no_conserva_rutas_de_R2_ni_de_B` | pasa | Sin `particionar`, R2X, R1′, P0 ni «una_sola_opcion» |
| `r4_excluye_la_moneda_de_mayor_aporte_bruto[v2]` | pasa | Semilla 37: C04USDT |
| `salto_de_nivel_en_un_corte_no_cambia_universo_senal_ni_IC_posteriores` | pasa | Un corte de 3 días con salto ×0,01 deja universo, U_pred, U_inv, S, A e IC posteriores idénticos; `P.r` no cruza el hueco. Sustenta que BNX sin regla 2 no altera A |
| `r4_…[v1]` | xfail | `'C34USDT' == 'C04USDT'`: defecto del v1 |
| `fallo_durante_el_calculo_deja_estado_explicito` | xfail | B2 |
| `insumo_alterado_entre_verificacion_y_lectura_se_detecta` | xfail | I5 |
| `archivo_de_mapeos_debe_estar_verificado` | xfail | I2 |
| `solo_la_ventana_A_es_aceptada_por_el_codigo` | xfail | I1 |
| `manifiesto_sin_entradas_no_pasa_la_guarda` | xfail | I3 |
| `importar_congelados_ejecuta_el_codigo_con_hash` | xfail | I4 |
| `apalancado_conserva_su_marca_si_su_base_se_renombra` | xfail | M1 |
| `mapeo_con_hueco_de_30_dias_o_mas_conserva_la_edad` | xfail | M2 |
| `mapeo_de_regla_2_duplicado_se_rechaza` | xfail | M3 |

### 6.3 Otros controles con código propio (`verificaciones/`)

- **`diff_recalculado.diff`:** idéntico al entregado.
- **`pruebas/diferencial_propio.py`** (v1 frente a v2, 143 campos de salida):

| Panel | Campos distintos |
|---|---|
| Semilla 20261026, momentum 0,02 | 0 |
| Semilla 20261026, momentum 0 | 0 |
| Semilla 37, momentum 0 | 5: R4_sin_mayor_aporte, R4_exceso, y en el Sharpe deflactado V_SR, dsr y sr0 |

  - **Cómo leerlo:** la identidad muestra **ausencia de diferencias no buscadas**, no corrección. El código compartido hereda lo que haga el v1.
  - La corrección de R4 se apoya en el caso construido, en la aritmética de `test_contribuciones_aritmetica_y_bordes` del autor y en la semilla 37 de punta a punta.
  - V[SR] cambia porque incluye el exceso de R4 entre los 20 (M4 documenta esa operacionalización).
- **`pruebas/buscar_semilla_r4.py`:** de 120 paneles sintéticos naturales, solo 1 hace que R4 cambie de moneda. El defecto del v1 es real, pero rara vez material.
- **`ventana_independiente.py`:** §4.1, y las 47/47 resoluciones verificadas contra el texto archivado.
- **`pasada2_reproducida/`:** `conciliacion.py` congelado con las resoluciones da 5/5 salidas idénticas.
- **`verificar_mapeos.py`** (22 mapeos):
  - citas presentes;
  - relaciones y fechas extraídas de forma independiente;
  - actividad coherente: ningún viejo activo después de E y ningún nuevo activo antes;
  - la regla 2 es coherente con el salto registrado por F3 en `estructural.json` (sin leer precios): COCOS 1,11; DREP 1,00; SUN 1,04; QUICK 1,00; STRAX 0,99;
  - BTCST no tiene salto registrado;
  - PLA→PDA: «1 PLA = 1 PDA» está en la página, aunque mi extractor no lo tomó.
- **`escaneo_exclusiones_en_A.py`, `paginas_no_extraidas.py`, `titulos_rotos.py`:** I7.
- **`renombres_por_cuerpo.py`, `nuevos_pares_vs_anuncios.py`, `buscar_sin_anuncio.py`:**
  - B1;
  - 112 pares nuevos con primer día en [2022-11-16, 2024-11-06], de los cuales 9 tienen anuncio de canje: 5 mapeados, HIFI, GFT, AMB y RDNT;
  - AMB y RDNT son canjes del mismo símbolo sin par USDT previo y no requieren mapeo;
  - KLAY→KAIA y GAL→G aparecen solo en títulos de barras laterales.
- **`salidas_2023_sin_evidencia.py`:** NBTUSDT es la única salida de 2023 sin evidencia.
- **`pyc_check/comparar_pyc.py`:** I4.

### 6.4 Pruebas que faltan (solo sintéticas)

1. ERROR explícito ante una excepción en cada etapa: importación, mapeos, validez, `ejecutar` y escritura.
2. Mapeos con hueco ≥ 30 días, X sin listado vigente en E (GTO→GFT) y duplicados.
3. La guarda carga el código desde bytes verificados aunque haya `.pyc` envenenados.
4. Lectura única de cada insumo, con TOCTOU imposible por construcción.
5. Prueba de propiedad de R4: con costos 0, R4 neto = R4 bruto.
6. Invariancia del v2 ante permutar el orden de las filas y de los mapeos con la misma E.
7. Panel sintético que reproduzca un renombre dentro de la ventana con apalancados, listas fijas y regla 2 encadenadas.
8. Prueba de la frase: ningún archivo de prueba contiene la FRASE real ni hashes reales.

---

## 7. Riesgos residuales y evidencia faltante

1. **Punto ciego posterior al 2024-11-06** (§4.4). Una falla en alcance no observada con E posterior al 2023-05-29 invalidaría A. Falta evidencia externa: anuncios posteriores al archivo.
2. **Circularidad de (iv′).** Las truncaciones sin rastro son indetectables. El tope es el 10 % anual, y R6 lo mide.
3. **Recall de los controles propios.** Fueron por expresiones regulares y sobre un archivo con 929 títulos ilegibles. MFT→HIFI y GTO→GFT aparecieron recién con el cuarto enfoque, así que puede haber más. Hace falta una lectura humana de las páginas de 2022–2024 con título «Announcement» o ilegible.
4. **Renombres posteriores al archivo,** tratados con la regla 3: DAR→D, FTM→S, EOS→A, MKR→SKY, FXS→FRAX, OM→MANTRA, la fusión AGIX/OCEAN→FET, y TOMO→VIC, RNDR→RENDER, KLAY→KAIA y GAL→G sin cuerpo archivado. El efecto es de composición: salida con liquidación contable más listado nuevo, conservador según la Adenda R §1.
5. **Cortes de 1 día dentro de A sin anuncio** (SCR, USUAL, AXS). Una redenominación con |log₁₀ r| < 1 no se detectaría.
6. **Mapeos de certeza media dentro de A:** COCOS→COMBO y TVK→VANRY (solo está archivado el anuncio de finalización; E = esa fecha). En los dos la actividad es coherente.
7. **Potencia baja** (0,35–0,56 según el autor; no la recalculé). Un INSUFICIENTE informaría poco.
8. **Margen de 2 semanas.** Cualquier corrección que retrase el inicio más de dos semanas deja A INVÁLIDA, y no se permite buscar otra ventana.
9. **Independencia.** Esta revisión no es independiente en sentido estricto (encabezado).
10. **No verificado por mí:**
    - si HIFI cumple (d) en esas 9 formaciones (exige QV real);
    - la potencia;
    - que la máquina de ejecución real coincida con este entorno (versión de numpy y orden de suma).

---

## 8. Recomendación final

**NO APTO PARA SOLICITAR AUTORIZACIÓN**, hasta cumplir lo siguiente:

1. **B1:**
   - completar `mapeos_adenda1.json` con MFT→HIFI y con todos los renombres y redenominaciones de cuerpo archivado (BNX, VIDT, LUNA→LUNC, BTT, NANO, BZRX, RAMP, EPS, GXS…);
   - decidir y documentar GTO→GFT;
   - re-verificar la actividad y re-congelar.
2. **B2 e I1–I5:** v2 nuevo con estado ERROR explícito, ventana y mapeos atados en el código, conjunto mínimo de entradas, ejecución desde bytes verificados y lectura única; pruebas nuevas, con las de §6.4.
3. **Documentación:**
   - corregir el informe en las afirmaciones falsas («LUNA, VIDT, BNX sin anuncio», «mapeos listos»);
   - completar la lista de sustituciones (I6);
   - declarar M5 y M7.
4. Una **segunda revisión, humana o de un tercero,** del diff nuevo y de la tabla nueva.

Con eso, el dictamen pasaría a **APTO PARA SOLICITAR AUTORIZACIÓN**. Aun así, la ejecución seguiría dependiendo de tu autorización expresa sobre los puntos de §4.3. **APTO para solicitar no es autorización.**

---

## 9. Qué está demostrado, qué depende del informe original y qué decidís vos

### 9.1 Hechos demostrados (con código o lectura propia, reproducibles desde `revision_independiente…/`)

- Los archivos existen; MANIFEST 92/92; las huellas y el estado de Git son idénticos al inicio y al fin.
- El diff entregado es el diff real entre el v1 congelado y el v2.
- C2 implementa N14: el EW bruto, con `mult_costo = 0`, en las líneas 378–380.
- Comisiones, retornos, precios, exclusiones y denominadores no cambian: diferencial de 0/143 en dos paneles.
- La ventana A (2023-05-15, 158/158, mínimo 120, último inicio 2023-05-29) se reproduce con código independiente.
- (ii′) = (ii) de la v3, y (iv′) = 2018.
- Las 47 resoluciones son citas textuales presentes en las páginas, con fechas coherentes.
- La segunda pasada es reproducible byte a byte.
- Ninguna exclusión spot USDT ≥ 2023-04-28 en los cuerpos archivados quedó sin contabilizar.
- MFT→HIFI, GTO→GFT, BNX, VIDT, LUNA→LUNC, BTT→BTTC, NANO→XNO, BZRX→OOKI, RAMP→LEVER, EPS→EPX y GXS→REI tienen anuncio oficial archivado, y ninguno está en la tabla.
- Las brechas B2, I1–I5 y M1–M3 existen; cada una tiene una prueba que falla por esa razón.
- Los `.pyc` actuales equivalen a sus fuentes.
- Un salto de nivel en un corte previo a A no altera A (sintético).
- La suite del autor da 28 pasadas y 6 xfail, y los xfail fallan por la razón correcta.

### 9.2 Afirmaciones que dependen del informe original y no verifiqué de forma independiente

- La potencia de 0,35–0,56.
- Que el conjunto de las 757 series (`6506fb03…`) sea el mismo que congeló F3. Verifiqué la huella del árbol E3, no la historia de F3.
- La clasificación de los cortes sin anuncio posteriores al archivo.
- Que ningún resultado de P0 se viera antes de congelar la Adenda R. No es demostrable ni refutable con los artefactos.
- Las certezas «media» de COCOS→COMBO y TVK→VANRY, más allá de la coherencia de actividad.
- Que HIFI cumpla o no (d) en las 9 formaciones.

### 9.3 Decisiones que te corresponden

1. Si reabrís E3 (CIERRE §2).
2. Si adoptás la Adenda R con R1 literal: (ii)→(ii′), (iii) anulada y (iv)→(iv′). Implica revertir la decisión expresa del CIERRE §2 y dispensar el §4.
3. Cómo tratar GTO→GFT: mapear, con el riesgo M2, o no mapear y declarar.
4. Si aceptás la desviación conservadora M5 (158 en lugar de 160 semanas) o preferís la lectura literal de A3.1.5.
5. Si aceptás los riesgos residuales de §7, en especial el punto ciego posterior al 2024-11-06 con margen de 2 semanas.
6. Si exigís una segunda revisión humana o de un tercero antes de solicitar.
7. Finalmente, y por separado, si autorizás la ejecución única. Nada de lo de este informe lo autoriza.
