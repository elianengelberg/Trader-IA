# Dictamen técnico D-1 a D-8

**Fecha:** 2026-10-29 (UTC).

**Autor:** el agente autor de la reparación, del v3 y del diseño v4. **No es una revisión independiente.**

**Este dictamen no autoriza nada.** «RESUELTA» quiere decir que la respuesta se deduce de las fuentes congeladas sin una regla nueva. No quiere decir que la hayas aprobado.

**Estados posibles de cada decisión:**
- **RESUELTA:** se deduce de las fuentes;
- **PENDIENTE DE DECISIÓN HUMANA:** depende de tu autoridad o de una regla que las fuentes no fijan;
- **BLOQUEANTE:** impide avanzar mientras no se resuelva.

**Abreviaturas de rutas:**
- `E3` = `experimentos/E3_seleccion_posicion_2026-10-19`;
- `E3R` = `experimentos/E3R_desbloqueo_2026-10-26`;
- `DEC` = `decision_E3H1H2_2026-10-26`;
- `REP` = `reparacion_E3H1H2_2026-10-26`;
- `CB` = `cierre_bloqueantes_E3H1H2_2026-10-27`.

Ningún argumento usa rendimiento: no se calculó ni consultó ningún retorno, IC ni estadístico.

## Cronología verificada (horas UTC)

| Momento | Hecho | Fuente |
|---|---|---|
| 2026-10-20 01:34:04 | v3 congelada (`279a865f…`) junto con las NOTAS (`21c37596…`) | `E3/ejecucion_E3/protocolo/CONGELACION_v3.txt` |
| 2026-10-20 02:15:29 | Adenda 3 (`47c17145…`) y código de conciliación congelados | `…/CONGELACION_ADENDA_3.txt` |
| 2026-10-20 | **Cierre de E3 por tu decisión:** NO EVALUABLE; «E3 no continúa» | `E3/CIERRE_E3.md` l. 3–4 y 19 |
| 2026-10-26 19:43:13.957 | Adenda R congelada «antes de calcular P0» | `E3R/CONGELACION_ADENDA_R.txt` |
| 2026-10-26 19:44:40.432 | P0 con R1 literal: VÁLIDO, 160 semanas | `E3R/REGISTRO_P0.txt` l. 2 y `P0_resultado.json` |
| 2026-10-26 19:46:57.953 | R1′ congelada «después de P0 (R1 literal)» | `E3R/CONGELACION_R1prima.txt` l. 1–2 |
| 2026-10-26 | Informe de decisión: «NO AUTORIZAR TODAVÍA»; B «descartada en forma definitiva»; R1′ «Fue un error» | `DEC/INFORME_DECISION_E3H1H2.md` l. 19–33 |
| 2026-10-26/27 | Segunda pasada A3.11: 158 semanas, margen 2 | `REP/INFORME_REPARACION_E3H1H2.md` l. 37–96 |
| 2026-10-29 00:24:56 | Protocolo SL-v1 congelado | `registro/CONGELACION_SL-v1.txt` |
| 2026-10-29 00:39 | Segunda lectura ciega, ronda 1 recibida | `registro/RECEPCION_RONDA1.txt` |

## D-1 · Reapertura

**Opciones exactas:**
- (a) no reabrir: E3 sigue NO EVALUABLE;
- (b) reabrir **solo el diseño y la verificación**, sin ejecución;
- (c) reabrir para ejecución con la Adenda R, que sustituye (iv) por (iv′) y deja (iii) sin efecto, y dispensar la condición del CIERRE §4;
- (d) reabrir con una adenda nueva;
- (e) obtener la lista completa de exclusiones (opciones a–d del §8 del informe de ejecución).

**Evidencia primaria:**

| Fuente | Qué dice |
|---|---|
| `CIERRE_E3.md` l. 15 | «No se relajó la regla (iv)» |
| `CIERRE_E3.md` l. 19 | «E3 no continúa. Reabrirlo o derivar experimentos nuevos de él requiere una autorización expresa» |
| `CIERRE_E3.md` l. 29–30 | Para reabrir, una «lista completa y verificable» 2020-05 → 2026-05 |
| `ADENDA_R` l. 3 | «No autoriza ninguna ejecución confirmatoria» |
| `ADENDA_R` l. 73 | «la ejecución confirmatoria requiere tu autorización expresa» |
| `INFORME_DECISION` §7 [J] | La Adenda R «es una sustitución de **tu** condición de cierre; tu autorización de A debe nombrarla expresamente» |
| `INFORME_EJECUCION_E3.md` §8 l. 225–239 | Recomendaba (a) o (e) y «no relajar la regla (iv)» |

**Precedencia:**
- El CIERRE es tu decisión y prevalece sobre cualquier propuesta posterior del agente.
- La Adenda R es una propuesta congelada, no una autorización.
- Desde el 2026-10-26 encargaste de forma expresa fases de diseño, revisión y verificación sobre E3, y en todas excluiste la ejecución. Este encargo dice: «Mantener E3 en estado BLOQUEADO»; «No ejecutar E3».

**Recomendación:**
- **(b) es lo que tus instrucciones ya establecen.** El diseño está reabierto por tu encargo expreso, y la ejecución no.
- Reabrir para ejecución (c) exige una autorización escrita que nombre:
  1. la sustitución de (iv) por (iv′);
  2. la dispensa del CIERRE §4, aceptando el punto ciego posterior al 2024-11-06;
  3. la ventana que resulte de SL-v1;
  4. D-2 a D-8.

**Consecuencias:**

| Opción | Consecuencia |
|---|---|
| (a) | La historia queda sin usar para fines confirmatorios (CIERRE l. 12) |
| (b) | Sin riesgo: no consume nada |
| (c) | Usa la única historia, con la potencia de D-8 y el riesgo de (iv′) |
| (d) | Otra congelación previa a cualquier resultado |
| (e) | Costo alto y factibilidad incierta |

**Estado:**
- **D-1(b): RESUELTA** por tus instrucciones;
- **D-1(c): PENDIENTE DE DECISIÓN HUMANA.**

## D-2 · R1 frente a R1′

**Opciones:**
- R1 literal (`ADENDA_R` l. 22–26);
- R1′ (`CORRECCION_R1prima_alcance_por_clase.md`, `86c8fd0b…`);
- la v3 pura (todas las fallas cuentan, v3 §2.3 l. 133).

**Evidencia y cronología:**
- R1′ se escribió y congeló **2 min 17 s después de P0** (19:44:40 → 19:46:57).
- El propio texto de R1′ dice:
  - l. 3: «congelada **después** de calcular P0»;
  - l. 8: su consecuencia observada en P0;
  - l. 22: su motivo, la potencia («casi duplica la información de H1»);
  - l. 23: su riesgo («sienta el precedente de corregir una regla después de ver qué hace con la ventana»).
- Su autor la retiró (`INFORME_DECISION` l. 22 y 33) y documentó que fue «ciega a los retornos, sí; ciega a sus consecuencias sobre la ventana, no» (D9, l. 76).

**Precedencia:**
- R1′ «solo rige si se elige expresamente» (l. 3), y nadie la eligió.
- Además contradice la v3 §2.3: «dentro de la ventana H no puede haber ninguna falla» (`INFORME_DECISION` D4, l. 71).

**Hecho decisivo.** Con la segunda pasada, el (ii) de la v3 pura coincide con el (ii′) de R1 literal: los dos dan 2023-05-15 (`ventana_A_pasada2.json`, `componentes.ii_v3_pura_lunes`). Es decir, **A no depende de la regla de alcance**.

**Recomendación:** R1 literal. R1′ es inadmisible como regla confirmatoria.

**Consecuencias:**
- R1′ daría un inicio por (i) y (iv′), del orden de 2020-05: es la familia de la ventana B, ya descartada. No está recalculado y no se recalcula.
- R1 da A.

**Estado: RESUELTA.** Solo aplica si D-1(c).

## D-3 · Regla de la fecha efectiva (se fija antes de elegir entre 158 y 160)

**Opciones:**
- (I) A3.1.5: la primera fecha del título;
- (II) N5: el día UTC en que cesa la negociación spot, según el texto.

**Evidencia:**

| Fuente | Qué dice |
|---|---|
| v3 §0.2 l. 32 | La v3 prevalece sobre todo documento de E3. La v3 no define la fecha efectiva |
| `NOTAS` l. 3 | Las notas «no cambian ningún … criterio»; si contradicen la v3, prevalece la v3 |
| `NOTAS` l. 16 (N5) | Es la **definición** |
| `ADENDA_3` l. 8 | «Esta adenda **no cambia** categorías, umbrales, ventanas ni criterios. Solo fija cómo se leen los casos que la v3 deja a "la mejor lectura documentada"» |
| `ADENDA_3` l. 10 | A3.1.5 está en «A3.1 **Extracción** (`cc_clasificar.py`)» |
| `ADENDA_3` l. 18 | A3.1.5 se rotula «(N5)» |
| `ADENDA_3` A3.5 (a) l. 50, A3.6 l. 60, A3.11 l. 89–91 | Prevén la corrección de E según el texto |

**Precedencia y cronología.** Las NOTAS se congelaron con la v3, **antes** que la Adenda 3. La Adenda 3 declara que no cambia criterios.

**Interpretación:**
- A3.1.5 es la **heurística del extractor** que implementa N5, no una definición rival.
- Donde el título trae la fecha de publicación y el cuerpo otra fecha de cese, la heurística falló en implementar N5. Corregirlo **aplica** el criterio congelado; no lo cambia.

**Universalidad:**
- La regla se aplicó a los 47 eventos, no solo a la muestra.
- SL-v1 la volvió a aplicar a los 47 con un lector ciego. Resultado: **47/47 concordantes con la segunda pasada** (§ Resultado SL-v1).

**Dirección:** la corrección **acorta** la ventana (160 → 158). No se eligió por un resultado favorable.

**Recomendación:** N5 como regla, con aplicación universal.

**Estado: RESUELTA** por precedencia documental. Podés desautorizarla, y entonces regiría (I) por una regla nueva explícita.

## D-4 · 158 o 160 semanas

**Opciones:**
- (a) la muestra V-S3 es solo un control: 160;
- (b) se resuelven las listas de A3.11, incluida DOTUP: 158;
- (c) N5 universal: 158.

**Deducción.** Con D-3 resuelta, las 160 semanas exigirían que A3.1.5 prevaleciera sobre N5, lo que contradice `ADENDA_3` l. 8. Quedan (b) y (c), y las dos dan el mismo inicio.

**Resultado SL-v1:**
- La relectura ciega de los 47 eventos reproduce las 4 fechas corregidas, con 47/47 concordantes.
- Con los 47 eventos y las omisiones de 2023 (TRXUP y LINKDOWN), el inicio es 2023-05-15, con 158 semanas.
- Pero la búsqueda de omitidos (D-5) agregó 6 remociones BLVT de 2024 cuya fecha decide la validez (ver «Resultado SL-v1»): con la fecha adjudicada, **A es INVÁLIDA**.
- Por eso la disyuntiva entre 158 y 160 **deja de importar**: ni 158 ni 160 sobreviven a las reglas congeladas con SL-v1.

**Estado: RESUELTA** en cuanto a la regla (158 por N5). **Sin efecto práctico**, porque A no supera la segunda lectura.

## D-5 · Eventos omitidos

**Opciones:**
- (a) ningún omitido;
- (b) búsqueda acotada;
- (c) búsqueda completa.

**Regla reproducible adoptada:** la de SL-v1 §7, congelada antes de correrla.
- Enumeración, por el lector, de todas las remociones de pares X/USDT en cada página leída.
- Escaneo Ω mecánico: 535 páginas con publicación ≥ 2023-04-01 o sin publicación; 169 candidatos en 108 páginas, todos leídos.
- Clasificación con la función congelada `clasificar`.

**Por qué alcanza ese alcance (deducción del código congelado, sin datos):**
- (iv′) solo cuenta como evidencia ANUNCIO los eventos A o B (`p0_pasada2.py` l. 66). Agregar eventos **no puede** aumentar las salidas SIN_EVIDENCIA. Por eso los omitidos no pueden empeorar (iv′); esto resuelve V63.
- Un omitido solo puede mover (ii′) si es una falla con E ≥ 2023-05-12, y solo invalida A si E ≥ 2023-05-29.

**Resultado.** 13 remociones de pares USDT confirmadas que no eran eventos:
- 2 en las páginas ya leídas: TRXUP y LINKDOWN, que dan T en 2023-05;
- 11 del escaneo Ω, todas en páginas cuyo título no es de exclusión:
  - 5 canjes: MC, PLA y MATIC dan A; QUICK y STRAX dan C explicada;
  - **6 BLVT de 2024**: dan A con E = 2024-02-28 y **T (falla en alcance)** con E = la fecha de delisting, que es la adjudicada.

Esto refuta la afirmación de completitud de `REP/INFORME_REPARACION_E3H1H2.md` l. 64, que valía solo para páginas con título de exclusión.

**Límites:**
- recall del escaneo (expresiones regulares);
- páginas no archivadas;
- punto ciego posterior al 2024-11-06.

**Estado: RESUELTA** como regla reproducible y aplicada. Su resultado invalida A (ver «Resultado SL-v1»).

## D-6 · Continuidad: GTO→GFT, LUNA→LUNC y UST→USTC

**Opciones:**
- (a) listado nuevo cuando el par de X ya no estaba vigente en la fecha del canje;
- (b) continuidad a pesar del hueco.

**Evidencia:**
- `ADENDA_1` l. 8, regla 1: «el listado **vigente** de X termina en la fecha efectiva. Y lo continúa…». La herencia presupone un listado vigente.
- v3 §2.2.3 l. 97–100: un listado termina tras 30 días inactivos.
- v3 §2.2.5 l. 102: un par USDT removido cuenta como salida.
- Hechos (`CB/INFORME_CIERRE_BLOQUEANTES_E3H1H2.md` §2.2 y `CB/tabla/TABLA_RENOMBRES_COMPLETA.md` l. 103–110):
  - GTO/USDT se retiró el 2022-11-28, antes del canje (2023-01/02); GFT/USDT abrió el 2023-09-22, a 298 días;
  - LUNA→LUNC tiene un hueco de 119 días;
  - UST→USTC tiene un hueco de 301 días.
- La tabla vigente ya implementa (a). La (b) exigiría **escribir una regla nueva**, porque la regla de 30 días del universo congelado reinicia la edad.

**Efecto:**

| Caso | Efecto en A |
|---|---|
| UST→USTC | Ninguno: los dos están en la lista fija |
| LUNA→LUNC | Ninguno en A |
| GTO→GFT | Solo la elegibilidad de GFT: con (a), desde ~2024-03; con (b), ~21 formaciones antes. No afecta a la ventana |

**Recomendación:** (a), como regla general: «la herencia de §2.2.4 requiere un listado vigente de X en la fecha efectiva del canje; si el par USDT de X ya había terminado por §2.2.3 o §2.2.5, Y es un listado nuevo». Es la lectura literal y la conservadora (`ADENDA_R` l. 12).

**Estado: RESUELTA** (lectura literal ya implementada). La (b) sería un cambio de metodología.

## D-7 · Reintentos: formalizar cero reintentos

**Opciones:**
- (i) reintento después de un ERROR en panel o validez (lo que implementó el v3);
- (ii) solo en panel;
- (iii) ninguno.

**Evidencia:**
- v3 l. 73: «una sola ejecución»;
- v3 §3.3 l. 175: «1 ejecución confirmatoria», y l. 180–183: «cualquier otra ejecución es exploratoria»;
- `ADENDA_R` l. 61: «**una** ejecución confirmatoria»;
- `E3R/PLAN_EJECUCION_UNICA_E3R.md` l. 35: «Sin repeticiones».

**Formalización:**
- Ejecución = un intento con `ABIERTO` durable o anunciado en el canal externo.
- Hay exactamente una por evaluación.
- Todo final distinto de EVALUADO o INVALIDO es terminal: NO EVALUABLE (fallo).
- La comprobación previa, sin leer datos, se puede repetir.
- Ver `tecnico/MAQUINA_ESTADOS_v4_1.md`.

**Comprobación (prototipo, evidencia preliminar del autor):**

| Prueba | Resultado |
|---|---|
| Disco sombra | 722 casos (interrupciones, reinicios, escritura partida, ENOSPC, EIO, `fsync` que miente; con y sin corte, con canal perdido): **0 reaperturas tras leer datos** con el canal disponible |
| Procesos reales | 72 corridas con señales y SIGKILL: 0 reaperturas |
| Estados inciertos | Clasificados como INCIERTO o DECISION_ANUNCIADA_NO_PERSISTIDA, siempre terminales |
| Mutante M8 (la política (i)) | Viola INV-1 |

**Límite:** con un `fsync` que miente y sin canal externo, 15 casos reabren. **El ancla externa es condición necesaria.**

**Recomendación:** (iii). Todo lo que pueda fallar por infraestructura se pone en la comprobación previa.

**Estado: RESUELTA** por el texto literal, que además es tu instrucción.

**Consecuencia:** un fallo de infraestructura después de `ABIERTO` consume la historia.

## D-8 · Potencia, supuesto del 10 % anual y riesgos residuales

Fuente: `metodologia/potencia_D8.py` y `potencia_D8.txt`. Es analítico, con los supuestos de la v3 §7.1, todos [Hip, ninguno medido], y sin datos. Las cifras corresponden a **158 semanas** (3,03 años).

| | α 0,025 | α 0,05 |
|---|---|---|
| H1, IC 0,02 | 0,35–0,55 (0,30–0,47 con AR(1) φ = 0,1) | 0,47–0,67 |
| H1, IC 0,03 | 0,65–0,88 | 0,76–0,93 |
| H2, 10 %/año | 0,07–0,10 (0,05–0,06 si el tracking error es 41–59 %) | 0,13–0,17 |
| H2, 20 %/año | 0,17–0,29 | 0,26–0,40 |
| Efecto mínimo detectable con 80 % | IC 0,027–0,036; H2 40–56 %/año | IC 0,024–0,032; H2 36–50 %/año |

**Cota de P(RESPALDADA):**
- ≤ 0,13–0,17 con 10 %/año;
- ≤ 0,26–0,40 con 20 %/año.

**Sobre el supuesto del 10 %:**
- No es una estimación: es un tamaño de efecto hipotético de la v3 §7.2, que la §7.3 llama «realista (5–20 %/año)» sin una medición que lo respalde.
- No se puede estimar sin mirar datos, y mirarlos está prohibido.
- Por eso se informa la curva completa y el efecto mínimo detectable.

**Cuánto informa un INSUFICIENTE** (ninguna hipótesis rechaza):
- con IC 0,02 y 10 %/año: probabilidad 0,40–0,60 si el efecto existe, frente a ≈ 0,95 si no existe;
- la razón de verosimilitud es 0,42–0,64: **evidencia débil** en contra del efecto;
- un INSUFICIENTE no refuta H1 ni H2.

**La potencia insuficiente no es evidencia favorable ni desfavorable:**
- solo dice que la prueba distingue mal;
- la v3 §7.3 ya lo preveía («quedará casi seguro en "insuficiente"»), y la §7.4 cierra la familia en ese caso.

**Riesgos residuales:**

| Riesgo | Detalle |
|---|---|
| Punto ciego posterior al 2024-11-06 | Una falla D en ese período no se detecta |
| Circularidad de (iv′) | La evidencia sale de los propios datos de Vision |
| Margen de 2 semanas | Una falla en alcance con E ≥ 2023-05-29 invalida A |
| Fragilidad de 2023 | Una salida más sin evidencia en 2023 da 2/19 = 10,5 % > 10 %, y A pasa a INVÁLIDA (V83) |
| Recall de renombres | No verificado |
| Volumen de HIFI | No verificado (V84) |
| Lecturas por agentes de la misma familia | — |
| Liquidaciones al último precio | Las mide R6 |
| Contaminación declarada | v3 §7.3 |

**Recomendación (técnica, no es una autorización):**
- **No ejecutar** salvo que tengas una decisión concreta que cambie según H1 y que justifique gastar la única historia con una potencia de 0,35–0,55 para el efecto de referencia de H1.
- Si se ejecuta, que sea solo con la finalidad que admite la v3 §7.3 (información sobre H1, nunca capital), registrando **antes** de cualquier resultado:
  - que INSUFICIENTE se lee como «no concluyente por potencia»;
  - y que se acepta la cláusula de cierre de la §7.4.
- Fijar ahora un umbral mínimo de potencia sería una regla nueva, válida porque es previa a cualquier resultado. Con cualquier umbral habitual (≥ 0,8), A no lo cumple, y eso equivale a no ejecutar.

**Estado: PENDIENTE DE DECISIÓN HUMANA.** En la práctica queda subordinada al resultado de SL-v1, que invalida A.

## Resultado SL-v1 (segunda lectura y ventana)

Detalle: `segunda_lectura/RESULTADO_SL-v1.md`.

**Qué se hizo:**
- **Control:** la conciliación congelada reproduce byte a byte la segunda pasada.
- **47/47 eventos concordantes** en la lectura ciega.
- **Omisiones:** 13 remociones confirmadas.

**Ambigüedad decisiva.** Los 6 BLVT tienen dos fechas en el texto: cese del trading el 2024-02-28 y delisting el 2024-04-01/02/03. La regla R-E de SL-v1 tiene dos frases que apuntan a fechas distintas:
- N5 apunta al cese del trading;
- la cláusula de tokens apalancados, **que agregué yo** y que no está en N5, apunta al delisting.

**Lecturas:**
- el lector eligió el cese del trading;
- el adjudicador ciego del §6 eligió el **delisting** en los 6 casos.

**Ventana L2 con el código congelado:**

| Alternativa | Inicio | Semanas | Veredicto |
|---|---|---|---|
| Cese del trading | 2023-05-15 | 158 | VÁLIDA |
| **Delisting (adjudicada)** | **2024-04-08** | **111** | **INVÁLIDA** |

El resultado no depende de R1 frente a la v3 pura: el (ii) de la v3 pura da lo mismo.

**Conclusión (§9 de SL-v1, fijado antes de leer):**
- A no supera la segunda lectura conforme a la Adenda R.
- **Recomendación técnica: cerrar E3 sin cambiar la ventana.** Que siga NO EVALUABLE. Nada de B, R1′ ni reglas nuevas.
- Elegir ahora la lectura que rescata a A sería corregir una regla después de ver su efecto, y **no lo recomiendo**.

**Efecto sobre D-1 y D-8:**
- D-1(c) (reabrir para ejecución) no tiene una ventana candidata que lo sostenga.
- D-8 queda subordinada: no hay ejecución que evaluar.
