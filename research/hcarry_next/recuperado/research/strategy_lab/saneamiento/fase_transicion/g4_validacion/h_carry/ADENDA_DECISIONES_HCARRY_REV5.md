# Adenda de decisiones provisionales de H-CARRY (rev. 5)

Fecha: 2026-10-16. Estado: **decisiones provisionales registradas; nada ejecutado**.

En esta etapa:
- no se descargó ni se leyó ningún dato de mercado, de funding ni de metadatos de Binance;
- no se ejecutó ningún backtest ni ninguna evaluación económica;
- no se consultó el período reservado (2026-06-01 a 2026-10-13);
- el protocolo original `protocolo_hcarry.json` (1.0) no se modificó: SHA-256 `edde54cc1f8509a120564e8d71d06d6a3700f6a357020bbbec385b55982de9f5`.

Las afirmaciones de esta adenda se apoyan en el código, en el borrador y en pruebas **sintéticas**. Ninguna se apoya en datos reales.

## 0. Decisiones provisionales y dónde quedan fijadas

| Decisión del responsable | Dónde queda fijada | Cómo se comprueba |
|---|---|---|
| **D1** con 850,9583 días fijos | Borrador, `metricas_decisorias.D1`: «D = 850,9583 días, FIJO: (20 424 horas de la ventana − 1)/24 … Se usa aunque la entrada se retrase». Plan: `config.criterios.D1.dias = "(horas de la ventana − 1)/24"`. Código: `hc_metricas.calcular`. | `test_d1` (texto del borrador, recuento de horas, plan, y que el 1.0 no fija días) y `test_d1b` (entrada retrasada 10 h: D sigue siendo (n − 1)/24) |
| **D4** con el equity final tras pagar la salida | Borrador, `D4` (sin cambios desde el cierre); plan: `config.criterios.D4.serie` | `m1b` y pruebas de D4 de la suite de cierre |
| **R0 y umbrales congelados** | Plan: `config.regla_inviable`, `config.criterios`, `config.funding`, `config.coherencia_entre_series`, `config.filtros` | El script que actualizó el borrador comprueba que no cambian criterios, costes, capital, ventana, reequilibrio, comparador ni D2–D4 |
| **Funding estricto**: no se rellena nada ni se supone una dirección | Borrador, `datos.integridad_del_funding`; código, `hc_datos` (líneas 205–245) | `test_a1`, `test_a1b`, `test_a2`, `test_a3` |
| **Sin firmas criptográficas** | Borrador, `controles_externos.modelo_de_amenazas` | §D de esta adenda |
| **exchangeInfo** solo con autorización aparte | Borrador, `solicitud_exchangeinfo`; `SOLICITUD_EXCHANGEINFO_HCARRY.md` | `test_x1`, `test_x2`, `test_x3` |
| **Evaluación histórica prohibida** en esta etapa | Expediente, §13 | No se ejecutó |

**Confirmación de D1.**
- El protocolo que se va a aprobar es el borrador 1.1 rev. 5 (`c1f6b110…`). Su D1 dice textualmente 850,9583 días fijos.
- El plan que congela el código (`eb4a5311…`) referencia ese borrador por su hash y calcula D = (n − 1)/24, con n = 20 424 horas. Por tanto, D = 20 423/24 = 850,958 3̅.
- El 1.0 define D1 como «neto anualizado sobre capital ≤ efectivo + 1 punto (≤ 6,0 %)» y no fija el recuento de días. No hay conflicto, y el 1.0 no se toca.

## A. Funding: qué se puede concluir con omisiones

### A.1 Qué se detecta y qué no

El calendario de funding se infiere de los datos (S10). La lista de intervalos admitidos es cerrada: {1, 2, 4, 8} h.

| Omisión o anomalía | ¿Deja huella? | Clase | Efecto |
|---|---|---|---|
| Una o varias liquidaciones omitidas en un tramo de 8 h (el hueco pasa a 16, 24… h, que no está admitido) | Sí | A2 | SIN VEREDICTO |
| Omisión que alarga el intervalo observado (4 → 8 h, 2 → 4 h, 1 → 2 h) | Sí | A2b | SIN VEREDICTO. Un cambio **real** de calendario a un intervalo más largo también lo produce: es el precio de no suponer nada. |
| Faltan liquidaciones al principio o al final de la ventana | Sí | A2 | SIN VEREDICTO |
| Liquidación no alineada con su intervalo | Sí | A2 | SIN VEREDICTO |
| Duplicadas o desordenadas | Sí | A7 | SIN VEREDICTO |
| Desfase > 60 s respecto de la hora | Sí | A8 | SIN VEREDICTO |
| Tasa implausible (máx. > 5 % o mediana > 0,1 %) | Sí | A4 | SIN VEREDICTO |
| markPrice incompatible con el mark de su hora | Sí | P2 | SIN VEREDICTO |
| **Omisiones que dejan un calendario regular, alineado y que nunca se alarga.** Ejemplo: el calendario real es de 4 h y faltan exactamente las de las 04, 12 y 20 h, de modo que se ve uno de 8 h. | **No** | — | El veredicto se emite, **limitado por S10** |
| Tasas bien formadas pero con valores falsos plausibles | No | — | Fuera del alcance de los controles (ver §D) |

**Consecuencia demostrable de la tabla.**
- Si el calendario real es de 8 h en toda la ventana, **toda omisión deja huella** y da SIN VEREDICTO. Esto se debe a que 8 h es el máximo admitido, a que se exige alineación y a que se controlan el principio y el final (`hc_datos.py:224-244`; pruebas `a1` en medio, al final y al principio).
- Una omisión indetectable exige que, en algún tramo, el intervalo **real** fuera más corto que el observado, y que el calendario observado nunca se alargue.
- No se ha verificado cuál fue el calendario real de BTCUSDT en 2024–2026. Lo recordado no cuenta como evidencia (S1).

### A.2 La dirección del sesgo no está garantizada

La prueba `tests/test_hc_decisiones.py::test_a2` (sintética) lo demuestra así:
- Construye un calendario real de 4 h con tasas de ±0,0005 de signo alterno.
- El registro publicado omite las liquidaciones de las 04, 12 y 20 h: lo que queda es un calendario de 8 h perfectamente regular, sin ninguna incidencia.
- Las 9 liquidaciones omitidas tienen la posición abierta (q = 0,083 BTC, a 60 000).

| Signo de lo omitido | Equity observado − equity real | Efecto |
|---|---|---|
| Tasas negativas (el corto pagaba) | +9 · 0,083 · 60 000 · 0,0005 = **+22,41 USDT** | **Sobrestima** |
| Tasas positivas (el corto cobraba) | **−22,41 USDT** | **Subestima** |

Por tanto:
- **No** se puede afirmar que las omisiones sean conservadoras ni que lleven el resultado «hacia cero». Omitir un subconjunto mueve la suma del funding hacia arriba o hacia abajo según el signo neto de lo omitido.
- Incluso con todas las tasas positivas, omitir lleva el resultado hacia el escenario `sin_funding`, no hacia cero. Ese escenario puede ser negativo por los costes.
- La magnitud **no se puede acotar de forma útil** sin una referencia externa del calendario. La única cota del código es la de plausibilidad (|tasa| ≤ 5 %), y es demasiado amplia para servir.

### A.3 Clasificación según el protocolo

**VEREDICTO LIMITADO** (borrador, `datos.integridad_del_funding.clasificacion`).
- Si hay una huella, el resultado es SIN VEREDICTO.
- Si no la hay, el protocolo emite DESCARTADA o NO DESCARTADA, pero **solo condicionado a S10**.
- La condición va dentro de `resultado.json` (`condiciones_del_veredicto`, id `S10-funding`, con el número de liquidaciones publicadas y los intervalos observados) y en la sección 1 del informe. El veredicto no se presenta sin ella.
- Ninguno de los dos veredictos es robusto a un fallo de S10. Una DESCARTADA tampoco es conservadora respecto del funding.

**Qué recibe el revisor para juzgarlo:**
- liquidaciones publicadas, intervalos observados, cambios y transiciones;
- la tasa modal y su fracción. Es un diagnóstico, no un control: un calendario fijo suele repetir la tasa base.

Una referencia independiente del calendario (anuncios de Binance o un archivo de terceros) reduciría la limitación. No está disponible y requeriría una autorización aparte.

**Alternativa que el responsable puede elegir en vez de aceptar la limitación:** tratar S10 como bloqueante, es decir, SIN VEREDICTO salvo que exista una referencia externa. Con esa opción, el experimento no podría emitir ningún veredicto sin datos adicionales. No se recomienda; queda en la decisión 4 de la tabla final.

## B. Filtros: qué se valida y qué interpretación es admisible

| Aspecto | Contenido |
|---|---|
| **Validable con los metadatos actuales** (comprobación previa, si se autoriza) | (1) Que los tipos y campos vigentes de BTCUSDT caben en la lista cerrada; si no, M1. (2) Que los valores vigentes se interpretan y dan una retícula no vacía, con mínimos múltiplos de sus pasos; si no, Q1. (3) Los valores **vigentes** de paso, mínimos, máximos y nocionales. |
| **No validable** | Qué filtros regían en cada fecha de 2024–2026, y si una orden simulada habría sido aceptada en su fecha. |
| **Limitaciones de aplicarlos retrospectivamente** | Un paso o un mínimo históricos mayores habrían rechazado o redondeado órdenes que el modelo ejecuta, y al revés. Un nocional mínimo distinto cambia qué reequilibrios pequeños se ejecutan. Los tipos de filtro antiguos o retirados no se modelan. |
| **Expectativa (no verificada)** | Con 10 000 USDT, la posición es del orden de 0,05–0,2 BTC. Con valores como los recordados (S1), solo actuaría el paso. |
| **Interpretación económica admisible** | «El veredicto vale **bajo los filtros vigentes en la descarga**.» Es la condición `S8-filtros` de `resultado.json`, con el número de órdenes impedidas, de reducciones limitadas y de operaciones divididas (S7). Si los tres recuentos son 0, solo actuó el paso vigente. |
| **Qué NO se puede afirmar** | Que el resultado reproduce lo que habría sido ejecutable en cada fecha. El escenario `sin_filtros` mide cuánto pesa la retícula **en el modelo**, con los mismos datos; **no reconstruye** los filtros históricos ni la ejecutabilidad real. |

La comprobación previa del `exchangeInfo` actual reduce un riesgo **operativo**: gastar el único experimento en un SIN VEREDICTO por M1 o Q1. **No** aporta información sobre el resultado económico ni sobre los filtros históricos. Está en `SOLICITUD_EXCHANGEINFO_HCARRY.md` y **no se ha ejecutado**.

## C. Liquidación, margen, base y ejecución

| Riesgo no modelado | Qué hace el modelo | Dirección sobre el resultado | Qué se informa sin modelo nuevo |
|---|---|---|---|
| Margen por tramos y comisión de liquidación reales | Margen de mantenimiento fijo del 1 %, sin comisión | No garantizada: una liquidación real deja la pata spot sin cubrir | Distancia mínima del mark máximo horario a la liquidación **del modelo**, con su hora (`riesgo_no_decisorio`). En el caso sintético de referencia es ≈ +98,6 % (`test_c1`, calculada a mano). |
| ADL, fondo de seguros, mark atípico dentro de la hora | Mark máximo horario publicado | No garantizada | Hora del mínimo de distancia, para revisarla |
| Liquidación parcial; margen cruzado con otras posiciones | Cuenta aislada del experimento | No garantizada | — |
| Retraso o fallo de transferencias; caídas del exchange o de la API | Transferencias instantáneas | No garantizada | — |
| **Ejecución asimétrica por patas** | Las dos patas, a la vez, en la apertura | No garantizada: la exposición direccional entre órdenes puede ganar o perder | Condición `S12-ejecucion` |
| Slippage según tamaño o volatilidad; latencia; nivel de comisiones | Slippage y comisiones fijos | Probablemente desfavorable, pero no está demostrado | Escenarios `costes_cero` y `costes_dobles` (informativos) |
| Base dentro de la hora | Solo aperturas y cierres | No garantizada | Base máxima en los cierres, con su hora; D3 sobre la base adversa en cada operación ejecutada |

**Clasificación.** Estos riesgos **no impiden** emitir el veredicto del protocolo, que está definido respecto del modelo. Lo **limitan**:
- DESCARTADA significa «no supera los criterios bajo el modelo y los costes registrados».
- NO DESCARTADA significa «pasa bajo el modelo», nunca «rentable en la realidad».
- D2 = «no» **no** es evidencia de que no haya riesgo de liquidación real.

**¿Hace falta un modelo nuevo para evitar un resultado engañoso?** No. Un resultado sería engañoso si se presentara sin sus condiciones. Por eso `resultado.json` incluye siempre `S11-S13-margen` (con la distancia mínima) y `S12-ejecucion`, y el informe las muestra justo debajo del veredicto. Un modelo de margen por tramos o de ejecución por patas exigiría parámetros que no se pueden fijar sin datos. Ampliaría el alcance y abriría grados de libertad.

**Resultado:** la evaluación es **informativa con veredicto limitado**. No queda sin veredicto por estos riesgos.

## D. Integridad sin firmas: garantías y amenazas no cubiertas

**Qué garantiza el mecanismo actual:**
1. **Identidad del código y del plan.** Si el código, el protocolo o el plan cambian, si queda bytecode viejo o si se olvida un módulo, la ejecución se detiene (B3). Protege frente a **errores**, no frente a quien recalcula las huellas.
2. **Ledger encadenado con nonce en el génesis.** Cualquier edición, truncamiento o reordenación de una línea cambia la cabeza. Se detecta **solo** si el revisor compara la cabeza con el ancla que el responsable guardó fuera de la carpeta.
3. **Autorizaciones ligadas a hashes.** La de descarga nombra el plan y el génesis; la de evaluación nombra además la descarga y la cabeza. Impide reutilizar una autorización en otra carpeta o con otra descarga (B4, B5) **por accidente**.
4. **Verificador independiente en un proceso nuevo.** Reejecuta byte a byte y cruza el resultado con el ledger y con las anclas.

**Frente a qué NO protege** (borrador, `controles_externos.modelo_de_amenazas`):

| Amenaza | Protección |
|---|---|
| Falsificar autorizaciones o anclas: son JSON sin firma | **No.** El revisor las compara con los originales del responsable, recibidos por otro canal. |
| Copiar la carpeta tras autorizar la descarga, descargar otra vez y evaluar la copia | **No por el código.** Exige falsificar la autorización de evaluación. La cubre el procedimiento: el responsable conserva las anclas y emite una sola autorización. |
| Modificar el código, incluido el verificador, y recalcular el inventario | **No por el código.** El revisor compara las huellas con un inventario recibido por un canal independiente. |
| Red manipulada que devuelve respuestas falsas pero bien formadas | **Parcial.** Se comprueban forma, rango, corte y coherencia entre series. **No** se detectan valores falsos plausibles. |
| Un operador que controla la máquina, el código y el canal de las anclas | **No.** Ningún control interno lo impide. Solo la separación de funciones: responsable, operador y revisor distintos. |
| Repudio: negar haber emitido una autorización | **No.** No hay no repudio sin firmas. |

Las amenazas que **sí** cubre el código se detallan en el borrador: error accidental, datos corruptos o de otro activo, interrupción, doble evaluación, autorización cruzada y confusión entre datos de prueba y del protocolo.

**Requisito procedimental mínimo** si se acepta no usar firmas:
- el responsable, el operador y el revisor no son la misma persona;
- el responsable guarda las anclas fuera de la máquina del experimento;
- el revisor recibe el inventario y las anclas por un canal distinto del de la carpeta.

## E. Estado de hashes tras esta etapa

| Artefacto | SHA-256 | Cambio |
|---|---|---|
| `protocolo_hcarry.json` (1.0) | `edde54cc1f8509a120564e8d71d06d6a3700f6a357020bbbec385b55982de9f5` | Ninguno |
| `protocolo_hcarry_v1_1_borrador.json` (rev. 5) | `c1f6b110300a0fa4694c59805ce10a5544f796509202ed06af1fcba00717d53c` | Antes `cfaefb10…`: textos de D1, funding, filtros, liquidación, amenazas, solicitud y decisiones. Ningún criterio, umbral ni parámetro cambió (comprobado por script). |
| `plan_protocolo_rev5.json` | `eb4a53112a8aeec5044e2a9beffad1a984e0eb2a5e0e0885f8d7141afd7bda4d` | Antes `08aca1df…`: cambian el hash del borrador y las huellas de `hc_informe.py` y `hc_evaluacion.py` |
| `hc_informe.py` | `a641c1eee4b1d375b908579199b7790d96048cd27d4fddc10222baa1b35af1f2` | Condiciones del veredicto y riesgo no decisorio; solo informativo, no decide |
| `hc_evaluacion.py` | `0dcfc37e336f80356087c5651e3d716811ae57c938ee5e108c29b3ba59d79887` | Añade `condiciones_del_veredicto` a `resultado.json` |

**Inventario completo:** `INVENTARIO_HCARRY_REV5.sha256`. **Registro de la suite:** `pytest_h_carry_cierre_rev5.log`.

El plan solo se congela en la máquina autorizada y con autorización. Su hash depende del código y del borrador: cualquier cambio posterior lo invalida, y entonces hay que regenerar la vista previa y el inventario antes de aprobar.
