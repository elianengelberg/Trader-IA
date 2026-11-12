# E3-H1/H2 · Informe de decisión independiente sobre la ejecución confirmatoria única

**Fecha:** 2026-10-26.
**Ámbito:** evaluación metodológica previa.
- No se calculó ningún retorno, IC, exceso ni estadístico de E3.
- No se ejecutó la prueba confirmatoria.
- No se modificó ningún artefacto original.
- Todo el trabajo quedó en `decision_E3H1H2_2026-10-26/`.

**Notación:**
- **[H]** hecho comprobado, con fuente o comprobación reproducible;
- **[I]** inferencia;
- **[J]** juicio técnico.

---

## 1. Decisión final y nivel de confianza

### DECISIÓN 3 — NO AUTORIZAR TODAVÍA

- **No autorizo ninguna ejecución.**
- La ventana **B queda descartada en forma definitiva**: su defecto es haberse elegido después de conocer su efecto, y más evidencia no lo corrige.
- La ventana **A es la única candidata**. Solo podrá reconsiderarse si se cumplen los requisitos R-1 a R-5 del §7.

**Confianza:**
- **Alta** en que hoy no corresponde ejecutar. Hay tres motivos verificados y materiales:
  1. la validez de A depende de un paso obligatorio del protocolo congelado que nunca se hizo, y su margen es de 4 semanas;
  2. el orquestador congelado tiene un desvío respecto de una nota congelada que puede cambiar la clasificación;
  3. el tratamiento de renombres y redenominaciones se aparta de la v3 sin que el código congelado pueda aplicar lo que la v3 manda.
- **Moderada** sobre si A terminará siendo autorizable. Depende del resultado de la segunda pasada (R-1), que hoy nadie conoce.

**Corrección de mi recomendación anterior:**
- El 26/10 recomendé B. **Fue un error.** Confundí «elegida sin ver retornos» con «libre de sesgo».
- Le di a la potencia un peso que el protocolo no le da (§4).
- No verifiqué que la conciliación definitiva estuviera hecha (§3).

---

## 2. Inventario de artefactos inspeccionados y hashes verificados

Lista completa con hashes: `INVENTARIO_VERIFICADO.txt`.

| Artefacto | Verificación |
|---|---|
| v3 `279a865f…`, Adenda 1, Adenda 3, Enmienda 2, notas N1–N22, limitaciones, `CIERRE_E3.md` | **[H]** Coinciden con `CIERRE_E3_MANIFIESTO.sha256` (2026-10-20T12:05:07Z); la v3 también con `CONGELACION_v3.txt`. Las 176 entradas de archivo del manifiesto verifican; además tiene 5 líneas de hash de conjunto, recalculadas aparte |
| `universo.py` `2af45115…`, `motor.py` `cadb805d…`, `inferencia.py` `7b280386…`, `pruebas_motor.py` `54f832d3…` | **[H]** Coinciden con el manifiesto de cierre y con las huellas de F3 |
| `estructural.json`, `listas_fijas_por_lunes.json`, `eventos.json`, `salidas.json`, `conciliacion.json`, `revision_manual.json`, `DECISION_CALIBRACION.txt` | **[H]** Coinciden con el manifiesto de cierre |
| Datos crudos: 757 series (`6506fb03…`), 52 210 archivos Vision (`574ef630…`), 26 105 zips (`cf27c8dd…`), 8028 páginas archivadas (`f12afb98…`) | **[H]** Recalculados con las recetas originales, recuperadas de la transcripción: **coinciden** (`verificaciones/conjuntos_recalculados.txt`) |
| `MANIFIESTO_F3.sha256` | **[H]** Archivos individuales OK. Sus 2 líneas `-` (hashes de conjunto) fallan en `sha256sum -c` por formato, no por contenido; con la receta original coinciden |
| Adenda R `87f60413…`, R1′ `86c8fd0b…`, R2 `6905afd4…`, scripts P0 | **[H]** Coinciden con sus registros de congelación y con `REGISTRO_P0.txt` |
| `P0_resultado.json`, `P0_resultado_R1prima.json` | **[H]** **Reproducidos byte a byte** al re-ejecutar los scripts en el área aislada |
| Orquestador `ejecutar_E3R.py` `3b64a04d…` y salidas sintéticas | **[H]** Coinciden con `CONGELACION_ORQUESTADOR.txt`; las dos corridas sintéticas se **reproducen byte a byte** |
| Guardas del modo real | **[H]** Re-probadas: 5 de 5 rechazan sin leer precios (sin autorización; solo la frase; dos opciones; sin el hash del orquestador; salida existente) |
| Registro de hipótesis `HIPOTESIS_PROGRAMA.json` `253b5c88…` | **[H]** 14 copias idénticas. Cita `REGISTRO_HIPOTESIS_tras_cierre_E3.md` `0e592295…`, y ese hash coincide. Estado de E3-H1/H2/H3: CERRADA · NO_EVALUABLE |
| Entrega del 26/10 | **[H]** `MANIFEST.sha256` OK; ZIP `05a57657…` |
| Árbol de E3 antes y después de esta evaluación | **[H]** `4909ef95…` en ambos momentos |

**Faltan, por diseño** (nunca se crearon, ver §7):
- `resoluciones_manuales.json`;
- la segunda pasada de la conciliación.

---

## 3. Diferencias entre la entrega del 26/10 y la evidencia primaria

| # | Lo que decía la entrega | Lo que muestran las fuentes |
|---|---|---|
| D1 | «El bloqueo era la regla (iv); lo resolví con evidencia interna» | **[H]** `CIERRE_E3.md` §2 registra que la regla (iv) **no se relajó por decisión expresa**. §4: reabrir exige «una lista completa y verificable de las exclusiones **y renombres** de pares USDT … entre 2020-05 y 2026-05». La Adenda R **sustituye** esa condición: no la cumple |
| D2 | La conciliación como base cerrada | **[H]** La segunda pasada que la Adenda 3 (A3.11) declara **definitiva** nunca se hizo (`resoluciones_manuales_usadas: false`). P0 usa la primera pasada. Pendientes: 12 «sin par», 8 «sin fecha», 1 desacierto de V-S2, 10 de V-S3 y **164 candidatos de renombre**. La Adenda R solo resolvió los 5 casos C |
| D3 | Adenda R §1: las fallas T (apalancados y BKRW) «por las listas fijas de §4.5, ninguno puede entrar en un universo» | **[H]** BKRW **no** está en la lista fija de `universo.py` y no aparece en **ninguna** de las 439 listas semanales de F3: nunca pasó los filtros de actividad, edad y liquidez. La premisa es falsa para BKRW, que es justamente el par que fija el inicio de B |
| D4 | Plan §4: «la regla (ii) protege el universo elegible; los apalancados nunca lo son» | **[H]** La v3 §2.3 cuenta **todas** las fallas de pares USDT: «dentro de la ventana H no puede haber ninguna falla». **[I]** Con ese criterio, el inicio de (ii), con los C explicados por A3.5, es 2023-05-01, que es exactamente A. B no deriva de la v3: la contradice |
| D5 | Ventana A: «160 semanas» | **[H]** Es correcto, pero el margen es mínimo: cualquier falla en alcance con fecha efectiva ≥ **2023-05-29** deja A por debajo de 156 → INVÁLIDO (`verificaciones/ventanas_independiente.txt`) |
| D6 | R2: «no hay ningún mapeo congelado» | **[H]** Es cierto solo porque no se hizo el mapeo obligatorio (v3 §2.2.4; Adenda 1, reglas 1, 2 y 4). Hay anuncios oficiales archivados de redenominación o canje para **QUICK, STRAX, DREP, SUN y COCOS** (además de MATIC→POL), 5 de los 8 cortes que R2 parte. Y R2 contradice la regla 3 de la Adenda 1 («no se corrigen con reglas inventadas»); la propia R2 lo admite |
| D7 | Orquestador: «no reimplementa nada… solo conecta» | **[H]** R4 calcula los aportes contra el EW-U30 **neto** (`contribuciones(P, base, formaciones, ew)`, línea 335). La N14 congelada exige el **bruto**. Además, el modo real **no verifica el hash** de los datos de entrada |
| D8 | Potencia: B 0,54–0,79 y A 0,35–0,56 | **[H]** Reproducido. Es aritmética sobre supuestos que la v3 §7.1 marca «[Hip, ninguno medido]». Con la autocorrelación de la calibración de H1 (φ = 0,1) baja a 0,46–0,70 y 0,30–0,48. **[H]** La v3 §7.2 ya preveía el caso: «si la regla de supervivencia acorta H, todas las potencias bajan, y **se informa** cuánto». Es decir, se informa, no se cambia la regla |
| D9 | «Elección ciega al resultado» | **[H]** Confirmado en la transcripción: antes de congelar la Adenda R (19:43:12Z) solo se leyeron claves y formas, excluyendo explícitamente O, H, L, C y QV. **[H]** Pero R1′ se congeló a las 19:46:56Z, **después** de ver que R1 daba 160 semanas, y R2 después de ver los saltos y su dirección. Ciega a los retornos, sí; ciega a sus consecuencias sobre la ventana, no |

---

## 4. Análisis comparativo de A y B

| | **A** (Adenda R, R1 literal) | **B** (Adenda R + R1′) |
|---|---|---|
| Inicio y semanas | 2023-05-01; 160 evaluables (0 % no evaluables) [H] | 2021-02-22; 274 evaluables [H] |
| Qué fija el inicio | DOTUP, DOTDOWN y TRXDOWN, T, 2023-04-27 [H] | BKRW, T, 2021-02-19 [H] |
| Relación con la v3 congelada | (ii) **coincide** con la v3 (con C explicados por A3.5). Se aparta en (iii) (suprimida) y (iv) (reemplazada por evidencia interna) [H] | Se aparta en (ii), (iii) y (iv). Excluye fallas que la v3 cuenta [H] |
| Cuándo se definió la regla | Antes de calcular P0 [H]. La intención declarada de la Adenda R ya buscaba sacar esas fallas [H, §1 de la Adenda R]: A coincide con la v3 **a pesar** de esa intención, no gracias a ella [I] | Después de P0 y de conocer su efecto sobre la ventana [H] |
| Dirección de la corrección | — | Solo agrega exclusiones, así que solo puede alargar la ventana: asimétrica [H] |
| Coherencia interna | La regla literal se aplica tal cual [H] | Su principio («nunca elegible, no cuenta») excluiría también a BKRW, y el inicio cambiaría otra vez. R1′ es **una** de varias operacionalizaciones posibles, cada una con su ventana [H/I] |
| Potencia de H1 (IC 0,02, α 0,025; supuestos no medidos) | 0,35–0,56 [H] | 0,54–0,79 [H] |
| Validez hoy | Depende de la segunda pasada (margen de 4 semanas) [H] | También depende, y además su regla es post hoc [H/J] |

**[J] Por qué B no es defendible, aunque sea ciega a los retornos:**
- es un cambio de regla de alcance, no la corrección de un defecto de la v3, porque la v3 cuenta todas las fallas;
- se tomó conociendo su efecto;
- es asimétrico, inconsistente (BKRW) y contrario a lo que la v3 §7.2 prescribe para una H corta;
- más potencia aumenta la probabilidad de detectar un efecto **si existe**; no dice nada sobre si existe;
- elegir el período por su efecto sobre la potencia, con conocimiento general del mercado de 2021–2022, abre un camino de sesgo que no se puede auditar.

**[J] Por qué A es la única candidata:** su inicio coincide con el de la v3 congelada. El único apartamiento sustantivo es el reemplazo de (iv), sin el cual E3 no es evaluable.

---

## 5. Sesgos y grados de libertad analíticos

1. **Sustitución de la condición de reapertura** (D1). La evidencia interna verifica que las salidas **observadas** fueron reales: en la muestra de P0b, las 12 salidas tienen el día L + 1 una vela parcial con operaciones; 9 cierran a las 02:59:59 y 3 a las 03:59, 07:59 y 09:59 [H]. Pero **no puede detectar pares ausentes de Vision** (falla D), y el archivo web termina el 2024-11-06. Para 2024-11 → 2026-05 no hay ningún control de ausencias [H].
   - Evidencia atenuante [H]: el bucket conserva 228 pares retirados; ningún evento archivado quedó en D; y para los 27 tokens de los dos avisos de conversión dentro de A, ningún par USDT documentado falta en Vision (las 35 coincidencias aparentes eran falsos positivos, como ALGO/USDT).
2. **Conciliación incompleta** (D2). Es el riesgo más concreto [I]. NSBT, SGB, SOLO y XYM no tienen **ningún** par en el bucket, en ninguna cotización [H]. La A3.3.3 manda leerlos a mano: si el texto los identifica como negociados en spot, son D, con fechas en 2023-12 o 2024-08, dentro de **ambas** ventanas. Lo más probable es que no lo sean (los textos los llaman «airdropped/delisted»), pero eso solo lo puede decidir la lectura prevista [J].
3. **R1′** (B): elegida tras ver la ventana; asimétrica; inconsistente. Ver §4.
4. **R2:** neutraliza saltos ficticios en ambas direcciones, lo cual es conservador y correcto en espíritu [J]. Pero reemplaza un mapeo que la v3 exige, para cortes con anuncio oficial, y contradice la regla 3 de la Adenda 1 [H].
5. **Operacionalizaciones del orquestador**, fijadas antes de cualquier retorno pero después de la congelación de E3 [H]:
   - semillas de R5 (20261021 + b);
   - forma de anular aportes en el §6.4;
   - conjunto de 20 configuraciones del Sharpe deflactado;
   - fuente de BTC.

   Solo la semilla de R5 toca una condición de clasificación (R5 forma parte de ROBUSTA); las demás son descriptivas [H/J].
6. **Conocimiento del período:** quienes diseñamos conocemos el mercado 2021–2026 (v3 §1, declarado) [H]. Es inherente a cualquier ventana; agrava la elección post hoc de B [J].

---

## 6. Verificaciones estadísticas y técnicas efectuadas

- **[H] Integridad:** manifiestos, congelaciones y conjuntos de datos (§2).
- **[H] P0:** reproducción byte a byte (`reproduccion_P0/`), más una verificación con código nuevo e independiente de inicios, semanas evaluables y margen de A (`verificaciones/ventanas_independiente.py`).
- **[H] Cronología** reconstruida desde la transcripción (`verificaciones/cronologia_transcripcion.txt` y `sesion_previa_a_adenda_R.txt`).
  - Ninguna lectura de O, H, L, C ni QV de series reales después del cierre de E3.
  - P0b leyó solo `open_time`, `close_time` y número de operaciones.
- **[H] Pruebas sintéticas del orquestador:** reproducidas byte a byte. Bajo el nulo, IC̄ = −0,0015 y el diagnóstico de §5.4 rechaza el 5,05 %; con momentum plantado, el camino completo funciona.
- **[H] Inferencia contra el texto congelado:**
  - **sin desvíos encontrados en:**
    - H1: Newey–West L = 4 (calibración aceptada), IC90 con el mismo error estándar;
    - H2: p = máx(boot ℓ13, boot ℓ26, NW13), según `DECISION_CALIBRACION`, e IC90 como envolvente (Enmienda 2, E2.2);
    - Holm m = 2;
    - criterios de §6.1, §6.2 y §6.5;
    - robustez R1, R2, R3, R5 y R6;
    - costos (§4.9 y N15);
  - **desvío confirmado:** R4 (D7);
  - **ambigüedad menor:** el diagnóstico de §5.4 aplica solo bootstrap ℓ13. No tiene consecuencia, porque la regla del máximo ya rige.
- **[H] Interpretación sin ambigüedad:** las clasificaciones de la v3 §6.5 son exhaustivas y mutuamente excluyentes en el código. Correspondencia con la terminología pedida:
  - RESPALDADA = RESPALDADA HISTÓRICAMENTE;
  - REFUTADA = EN CONTRA (solo por H1, §6.1);
  - INSUFICIENTE = INSUFICIENTE o NO CONCLUYENTE;
  - NO EVALUABLE = INVÁLIDO por la validez previa.

  **[J]** El resultado se leería sin cambiar reglas, una vez corregido R4. Falta además registrar «INVÁLIDO» como salida explícita: hoy el script termina con un mensaje.
- **[H] Guardas:** re-probadas (§2).
- **[H] Reproducibilidad del modo real:** no verificable sin ejecutarlo. No lo ejecuté.
- **[H] Tiempos:** medidos solo con un panel sintético de tamaño real.

---

## 7. Evidencia faltante, limitaciones y qué permitiría reconsiderar

| Req. | Qué falta y qué debe hacerse (todo antes de calcular cualquier retorno, congelado con hash y hora) | Criterio de aceptación |
|---|---|---|
| **R-1** | **Segunda pasada A3.11** completa, con cita del texto archivado local para **cada** caso de **cada** lista: 12 sin par, 8 sin fecha, 1 desacierto de V-S2, 10 de V-S3 y 164 candidatos de renombre, incluida la A3.3.3 para NSBT, SGB, SOLO y XYM. Después, `conciliacion.py` congelado, sin cambios, sobre `resoluciones_manuales.json` | Lista definitiva de fallas T, D y C no explicadas, y tabla de renombres y redenominaciones con relación de canje |
| **R-2** | Recalcular P0 con la Adenda R **y la regla R1 literal** sobre las fallas de la segunda pasada | **VÁLIDO** con ≥ 156 semanas evaluables. Si aparece una falla en alcance con E ≥ 2023-05-29, A es **INVÁLIDO**: E3 queda NO EVALUABLE, **sin recurrir a B ni a reglas nuevas** |
| **R-3** | Renombres y redenominaciones con anuncio oficial: implementar el mapeo de la v3 §2.2.4 (continuidad con la relación de canje; el nuevo símbolo hereda edad y posiciones) en la construcción del panel. R2 queda solo para los cortes que sigan sin mapeo (hoy LUNA, VIDT y BNX). El código congelado de E3 no lo implementa (`Panel.mapeos` nunca se usa) [H] | Pruebas sintéticas específicas del mapeo, más una revisión independiente del diff |
| **R-4** | Corregir el orquestador | Nuevo hash congelado; pruebas sintéticas repetidas; diff revisado |
| **R-5** | Plan y plantilla de autorización nuevos, **solo para A**, con todos los hashes nuevos. Más tu autorización explícita posterior | Guardas re-probadas |

Las correcciones de **R-4** son:
- R4 contra el EW **bruto** (N14);
- verificar, antes de leer cualquier precio, los hashes de las series (`6506fb03…`), de `estructural.json`, de las listas y de las salidas de la segunda pasada;
- registrar INVÁLIDO como resultado explícito;
- aplicar los mapeos de R-3;
- eliminar la ruta de R1′ y la opción B de las guardas.

**[J] Sobre la condición de reapertura** (`CIERRE_E3.md` §4), una vez hechos R-1 y R-3:
- **Renombres:** quedarían cubiertos para el período archivado.
- **Exclusiones:** quedarían cubiertas por el archivo hasta 2024-11-06 y, desde ahí, por la evidencia interna, con un residual declarado: un par **ausente** de Vision en 2024-11 → 2026-05 no se puede detectar.
- **Mi juicio:** ese residual es aceptable por la evidencia atenuante del §5.1. Pero es una sustitución de **tu** condición de cierre; tu autorización de A debe nombrarla expresamente.

**Limitaciones de esta evaluación:**
- No pude verificar exchangeInfo (HTTP 451; V-S4 no ejecutado desde E3).
- No leí los textos de la segunda pasada salvo los cuatro necesarios para medir la materialidad.
- No re-ejecuté F3 (calidad, estructural, conciliación pasada 1): verifiqué sus salidas por hash, no su cálculo.

---

## 8. Riesgos residuales (incluso si se cumplen R-1 a R-5)

- **Pares ausentes de Vision después de 2024-11-06** (falla D no detectable). Severidad media y probabilidad baja [J].
- **Potencia baja de A:** 0,35–0,56 para un IC de 0,02, con supuestos no medidos. Un INSUFICIENTE informa poco. **Se acepta y se informa** (v3 §7.2); no justifica cambiar la ventana [J].
- **Contaminación declarada:** ninguna clasificación autoriza capital (v3 §6.5 y §7.3) [H].
- **El código nuevo de R-3 y R-4 es posterior a la congelación de E3.** Se mitiga con pruebas sintéticas, revisión independiente y congelación previa a cualquier retorno [J].
- **Liquidaciones contables al último precio:** supuesto, estresado por R6 [H].

---

## 9. Por qué esta decisión resiste una revisión independiente

1. **No se apoya en resúmenes.** Cada bloqueo remite a un archivo con hash verificado contra el manifiesto de cierre, o a una comprobación reproducible del área aislada.
2. **Aplica el protocolo congelado tal como está escrito:**
   - la regla de validez de la v3 §2.3;
   - la segunda pasada definitiva de A3.11;
   - el mapeo de renombres de la v3 §2.2.4 y de la Adenda 1;
   - el tratamiento de una H corta de la v3 §7.2;
   - la condición de reapertura de `CIERRE_E3.md` §4.
3. **No es exceso de cautela.** El margen de A es de 4 semanas, y la segunda pasada pendiente contiene casos fechados dentro de la ventana. Ejecutar hoy podría producir un resultado sobre una ventana que el propio protocolo declararía inválida.
4. **No optimiza.** No propone otra ventana. Descarta B por su procedencia, no por su resultado esperado. Fija por adelantado qué pasa si A resulta inválida: cierre, sin alternativas.
5. **Corrige mi propia recomendación anterior**, con las razones a la vista.

---

## 10. Instrucción operativa final

1. **NO EJECUTAR E3.** No hay ninguna autorización vigente, y la plantilla de autorización de `E3R/PLAN_EJECUCION_UNICA_E3R.md` §5 **queda revocada para las dos opciones**.
   - No debe crearse ningún archivo de autorización.
   - El orquestador `3b64a04d…` no debe correrse en modo `real`.
2. **La opción B queda descartada en forma definitiva.**
3. **Próximo trabajo, si se decide continuar con E3:** R-1 → R-2 → R-3 → R-4 → R-5, en ese orden, cada uno congelado antes del siguiente y **antes de cualquier retorno**.
4. **Si R-2 da INVÁLIDO:** E3-H1/H2 siguen CERRADAS · NO EVALUABLES, sin reformulación con estos datos.
5. **Si R-1 a R-5 se cumplen:** se emite una recomendación nueva de autorizar A, con una frase y hashes nuevos. La ejecución solo se habilita con tu autorización explícita posterior.

**NO AUTORIZADO PARA OPERAR CON DINERO REAL.** Sin commits, push, PR, despliegues, exchanges ni Testnet.
