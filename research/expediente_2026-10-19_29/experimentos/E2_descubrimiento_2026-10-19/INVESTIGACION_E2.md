# E2: descubrimiento abierto después de E1. Investigación, no implementación (2026-10-19)

**Alcance.** Este documento es solo investigación y diseño:
- no se descargaron datos;
- no se instalaron dependencias;
- no se ejecutó ningún experimento;
- no se tocaron E1, T-MULTI ni sus artefactos.

El único uso de la red fue la búsqueda de literatura.

**Etiquetas:**
- **[Pub]** resultado publicado, verificado en esta sesión (fuente enlazada en el §6);
- **[Pub\*]** resultado publicado, citado de memoria y **no** verificado hoy (conviene confirmarlo antes de apoyarse en él);
- **[Hip]** hipótesis propia;
- **[TIA]** resultado experimental de Trader-IA.

Las rentabilidades publicadas no se trasladan como expectativa: un resultado publicado no es una predicción para este proyecto.

## 0. Punto de partida: lo que Trader-IA ya sabe [TIA]
| Línea | Resultado | Implicancia |
|---|---|---|
| H-CARRY (carry de funding, delta neutral) | Evidencia insuficiente: +3,76 % en test frente a un comparador del 5 % | Cerrada. Solo la reabre el monitor del carry si supera el 12 % anual |
| V (volatilidad gestionada, BTC diario) | Descartada: la volatilidad de 30 días tiene poca persistencia (0,32); Sharpe 0,92 frente a 0,96 | No repetir en BTC |
| R (reversión diaria, BTC) | Sin base: autocorrelación de retardo 1 de −0,06 y unos 30 bps por ida y vuelta | Confirmada a 1 h por E1 |
| T (tendencia long/flat 1/3/6 meses, BTC y ETH) | Desarrollo con P = 0,84; fuera de muestra +7 %/año con P = 0,755: insuficiente | Historia cerrada; solo el papel prospectivo (revisión el 2027-04-18) |
| T-MULTI (11 ETF) | Queda excluida una ventaja neta ≥ 0,65 %/año; el bruto de ≈ +1 % se lo comen los costos | La tendencia cruzada entre mercados no paga sus costos con esa rotación |
| E1 (trend, MR y breakout del bot, BTC 1 h) | Evidencia en contra de una ventaja neta en las tres; el timing no se distingue de una entrada aleatoria emparejada | No optimizar sobre BTC 1 h |

**Lecciones que condicionan el diseño:**
1. **Las ventajas plausibles son chicas frente a los costos.** Toda candidata tiene que operar poco o tener un efecto grande.
2. **La potencia estadística es el cuello de botella.** Con un solo mercado cripto (BTC y ETH equivalen a ≈ 1,2 activos efectivos [TIA]), más años no alcanzan. Hacen falta mercados o fuentes de información nuevas, o datos prospectivos.
3. **Casi todos los precios locales ya se usaron:**
   - BTC y ETH diarios 2017–2026 (T);
   - BTC 1 h 2019–2026 (E1);
   - ETF 2011–2026 (T-MULTI).
   - Usarlos de nuevo con otra señal no es fuera de muestra «limpio» para el diseñador: conoce a grandes rasgos lo que pasó. Se puede hacer, pero declarándolo y con una sola prueba por hipótesis.
4. **Una IA que «elige cuándo operar» solo agrega valor si alguna variable de estado tiene información.** En E1, la confianza del bot no ordenó los retornos, salvo una pista posterior en breakout.

## 1. Familias candidatas
Para cada una se indica: mecanismo · evidencia a favor y en contra · horizonte, mercado y régimen · costos, datos y riesgo de sobreajuste · diferencia con lo evaluado · datos disponibles o necesarios · experimento mínimo capaz de refutarla.

### C1. Posicionamiento apalancado extremo (funding y prima del perpetuo) como timing contrario para spot, de días a semanas
- **Mecanismo [Hip]:**
  - un funding muy alto indica largos apalancados apiñados, que son frágiles ante cascadas de liquidación, lo que anticipa un retorno spot menor;
  - un funding negativo sostenido indica capitulación o cortos apiñados, lo que anticipa rebotes.
  - Se opera **en spot long/flat**: estar en efectivo con el extremo alto y entrar tras el extremo bajo.
- **A favor:**
  - [Pub] Schmeling, Schrimpf y Todorov (BIS WP 1087) atribuyen el carry de futuros cripto a la demanda de inversores minoristas que persiguen la tendencia con apalancamiento, y a un capital de arbitraje escaso, con riesgo de liquidaciones en las caídas. Eso respalda que el funding mida apiñamiento, no que prediga retornos.
  - [Pub] Blogs de exchanges y de análisis (BitMEX, K33) informan de rebotes tras funding negativo. Son fuentes con interés comercial y episodios aislados.
- **En contra:**
  - [Pub] La propia tabla de BitMEX da tasas de acierto de ≈ 45–53 %, casi una moneda al aire.
  - No encontré ningún estudio revisado por pares que pruebe la predicción de retornos spot a partir del funding.
- **Horizonte y régimen:** de 3 a 30 días; sobre todo en finales de euforia y en capitulaciones.
- **Costos y riesgos:**
  - pocas operaciones, del orden de 10–30 episodios extremos en 6 años, así que la **potencia es muy baja**;
  - umbrales arbitrarios: hay que fijar uno solo, en percentil y con ventana expansiva;
  - el funding de un exchange (Binance) no es el de todo el mercado.
- **Diferencia con lo evaluado:**
  - H-CARRY **cobraba** el funding de forma delta neutral; C1 lo usa como **señal direccional**;
  - es probable que tenga correlación baja o negativa con la tendencia (T está largo justo cuando el funding es alto), así que **diversifica**.
- **Datos:**
  - locales: funding de BTC, ETH y SOL (2020-01/09 → 2026-05) y la prima de BTC, más BTC y ETH spot diarios;
  - falta SOL spot (habría que descargarlo).
  - **Contaminación:** las series de funding se miraron en H-CARRY (persistencia del nivel), no como señal direccional.
- **Experimento mínimo:**
  - **regla única prerregistrada:** funding medio de 7 días por encima del percentil 90 de su historia expansiva → efectivo; por debajo del percentil 10 → largo; en el resto, la exposición base. Se decide al cierre diario y se ejecuta en la apertura siguiente, con 10 bps por lado.
  - **métrica:** exceso de timing frente a la exposición estática equivalente, al estilo de T, con bootstrap por bloques y en BTC + ETH (y SOL si se autoriza).
  - **refutación:** P < 0,5 o un IC90 del exceso que incluya 0 con un límite superior < +2 %/año.
  - Con tan pocos episodios, lo esperable es «insuficiente»: es un experimento barato, pero de baja potencia.

### C2. Atención de los inversores (vistas de Wikipedia, búsquedas) como señal semanal
- **Mecanismo [Pub]:** la atención atrae compras de inversores poco informados; produce momentum de corto plazo y, a veces, reversión posterior.
- **A favor:**
  - [Pub] Liu y Tsyvinski (RFS 2021): los indicadores de atención **predicen con fuerza** los retornos cripto; además encuentran momentum temporal fuerte.
  - [Pub\*] Kristoufek (2013) vincula Google Trends y Wikipedia con el precio de BTC.
- **En contra:**
  - la muestra de Liu y Tsyvinski es de 2011–2018, previa a la institucionalización (ETF, futuros);
  - [Pub] Swinkels informa que el momentum cripto **se habría debilitado** tras la llegada de los futuros;
  - Google Trends se remuestrea y se revisa, así que no es reproducible.
- **Horizonte:** de 1 a 4 semanas; régimen de entradas masivas de minoristas.
- **Costos y riesgos:**
  - semanal, de baja rotación;
  - riesgo de que la atención solo repita el momentum (hay que medir su información **incremental**);
  - riesgo de mirada al futuro si se usa una serie revisada.
- **Diferencia con lo evaluado:** es una **fuente de información nueva**, no precio; diversifica en parte (está correlacionada con el momentum).
- **Datos:**
  - **ninguno local**;
  - la API pública de vistas diarias de Wikimedia (desde 2015-07, por verificar) es estable y reproducible, con un volumen ínfimo (KB). **Requiere autorización.**
- **Experimento mínimo:**
  - Clark–West fuera de muestra (ventana expansiva desde 2018) sobre el retorno de BTC a 7 días:
    - modelo base: retorno medio más el momentum de 4 semanas;
    - modelo aumentado: más la variación de las vistas de 4 semanas.
  - **refutación:** sin mejora predictiva significativa (p > 0,05).
  - Solo si pasa, se diseña una regla de trading.

### C3. Información incremental de volumen, volatilidad, liquidez y funding a horizonte de posición (prueba de compuerta, no una estrategia)
- **Mecanismo:** probar, antes de construir estrategias, si alguna variable de estado tiene información sobre el retorno a 1–4 semanas **más allá** del precio.
- **A favor:**
  - [Pub] Balcilar et al. (2017): el volumen predice los retornos de BTC en buena parte de la distribución, salvo en regímenes alcistas o bajistas extremos, y no predice la volatilidad;
  - [Pub] Detzel et al. (2021): los cocientes entre precio y media móvil predicen los retornos diarios de BTC dentro y fuera de muestra.
- **En contra:**
  - [Pub] Hudson y Urquhart (2021): **sin predictibilidad fuera de muestra en BTC**, aunque sí en otras criptos;
  - [Pub] un estudio posterior sobre 12 criptos encuentra rentabilidad genuina solo en un cociente de media móvil de corto plazo.
  - [TIA] El filtro de volumen de breakout en E1 no salvó la estrategia.
- **Por qué primero:** responde tu pedido («no asumir que añadir indicadores mejora») con un costo mínimo y **datos locales**, y decide qué señales merecen convertirse en estrategia.
- **Datos:** locales. BTC y ETH diarios con volumen (2017–2026), y funding y prima (2020–2026). Contaminación: los precios se usaron en T; las variables candidatas, no.
- **Experimento mínimo:**
  - lista **cerrada** de 5 variables: volatilidad realizada de 30 días, z-score del volumen de 30 días, funding medio de 7 días, prima media de 7 días y drawdown desde el máximo de 90 días;
  - objetivos: retornos de BTC y ETH a 7 y 28 días;
  - regresiones fuera de muestra con ventana expansiva desde 2021-01, frente a la base (media histórica más el momentum de T, que ya es conocido);
  - Clark–West, con **Holm sobre 5 variables × 2 horizontes**;
  - **refutación:** ninguna variable mejora tras Holm. En ese caso, «agregar indicadores» queda descartado como vía.

### C4. Tendencia o momentum temporal de posición, con baja rotación (familia de T)
- **Mecanismo [Pub\*]:** subreacción y difusión lenta de la información, más manada (Moskowitz, Ooi y Pedersen, 2012; Hurst, Ooi y Pedersen, 2017).
- **A favor:**
  - [Pub] Liu y Tsyvinski: momentum temporal fuerte en cripto;
  - [Pub] Han, Kang y Ryu (WP): momentum temporal fuerte en cripto incluso con costos, mientras que el transversal es débil.
- **En contra:**
  - [Pub\*] Huang, Li, Wang y Zhou (JFE 2020) ponen en duda el TSMOM en el panel de activos;
  - [Pub\*] Kim, Tse y Wald (2016) muestran que buena parte se explica por el escalado de volatilidad;
  - [TIA] T insuficiente en cripto y T-MULTI sin ventaja neta en ETF.
- **Estado:** por **decisión previa**, no se vuelve a probar T con datos históricos. Una variante de menor rotación es una hipótesis **nueva** motivada por los resultados: solo prospectiva o en activos no tocados.
- **Diversificación:** nula frente a T.
- **Experimento mínimo:** T **sin cambios** en un universo **nuevo** de criptos (SOL, BNB, XRP, ADA… con fecha de listado anterior a 2021), con prerregistro. Requiere descarga y tiene un límite claro: BTC y ETH correlacionan 0,69 en el exceso; si las altcoins correlacionan parecido, se suman menos de 0,5 activos efectivos [Hip].

### C5. Momentum transversal entre criptos (rotación hacia los ganadores, solo largos)
- **A favor:** [Pub] Liu, Tsyvinski y Wu (JF 2022): los factores de mercado, tamaño y **momentum** explican el corte transversal de los retornos cripto.
- **En contra:**
  - [Pub] Grobys y Sapkota (Econ. Letters 2019): **sin momentum significativo** con 143 monedas entre 2014 y 2018;
  - [Pub] Han, Kang y Ryu: el transversal es débil y sus beneficios desaparecen con costos.
- **Riesgos:**
  - **sesgo de supervivencia**: falta saber si data.binance.vision conserva los pares deslistados;
  - liquidez de las monedas chicas y spreads altos;
  - en spot no se puede vender en corto, así que solo queda la versión «top-k frente a BTC».
- **Diversificación:** alta, porque es transversal.
- **Factibilidad:** baja. Exige un universo histórico en cada fecha, que hoy no existe en disco.
- **Experimento mínimo:** el top-3 por momentum de 4 semanas, entre las 20 más líquidas en cada fecha (incluidas las deslistadas), rebalanceado semanalmente, frente a BTC y una canasta equiponderada. **Refutación:** el IC90 del exceso incluye 0.

### C6. Valor relativo BTC/ETH (rotación sin cortos)
- **Mecanismo [Hip]:** si el cociente ETH/BTC revierte a su media, se mantiene la moneda «barata» frente a una canasta 50/50 rebalanceada. No requiere cortos.
- **A favor:** [Pub] el pairs trading en cripto funciona «en ciertas condiciones» (Fil y Kristoufek, IEEE Access 2020).
- **En contra:**
  - [Pub] el mismo trabajo rinde muy por debajo de la literatura previa y registra una rentabilidad decreciente;
  - [Hip] ETH/BTC tuvo tendencias estructurales largas (2022–2025), así que no es obvio si el cociente revierte o sigue tendencia. Elegir la dirección después de mirar sería sobreajuste.
- **Datos:** locales (BTC y ETH diarios).
- **Experimento mínimo:** **una** dirección fijada por la literatura (reversión, la del pairs trading), con z-score del cociente a 90 días, umbral de ±1,5 y rebalanceo semanal, frente a la canasta 50/50. **Refutación:** IC90 del exceso con un límite superior < +1 %/año.
- **Prioridad:** media-baja, porque el mecanismo es ambiguo.

### C7. Valoración on-chain (MVRV, NUPL, precio realizado) en régimen de semanas a meses
- **Mecanismo [Hip]:** la ganancia latente agregada anticipa presión vendedora en los techos; la pérdida latente, capitulación en los pisos.
- **A favor:** [Pub] Grobys, Näsman y Sandretto informan reglas on-chain que superan a buy and hold y a entradas aleatorias de Monte Carlo en 3 ciclos (2013–2025). Falta verificar si tiene una muestra reservada.
- **En contra:**
  - solo hay **unos 3 ciclos independientes**, una muestra mínima;
  - los umbrales de los practicantes no coinciden entre sí (MVRV «caliente» en 3,0, 3,5 o 3,7), un signo de sobreajuste;
  - la serie del proveedor puede revisarse.
- **Datos:** no locales. Coin Metrics Community ofrece métricas diarias gratuitas (MVRV incluido, por verificar). Requiere autorización.
- **Diversificación:** alta, por la información y por la frecuencia baja.
- **Experimento mínimo:** **una** regla de la literatura (MVRV-Z con el umbral del paper) aplicada a ETH, que no es el activo del paper. Lo esperable es «insuficiente» por la falta de ciclos.

### C8. Prima de riesgo de varianza (vender volatilidad o calls cubiertos sobre BTC)
- **A favor:**
  - [Pub] Alexander e Imeraj (2021) construyen un VIX de bitcoin y su prima de varianza;
  - [Pub] Almeida et al. (2024) estiman una prima de varianza positiva, mayor en el régimen de volatilidad baja.
- **En contra:**
  - la mayor parte de lo publicado es descriptivo; no encontré pruebas de estrategias **netas de costos**;
  - riesgo de cola severo;
  - requiere opciones (Deribit), margen y liquidación, que es otra infraestructura.
- **Prioridad:** baja por factibilidad, aunque diversificaría mucho.

### C9. Eventos macro (FOMC, CPI, NFP): gestión de riesgo más que alfa
- **Evidencia mixta:**
  - [Pub] NY Fed SR 1052: BTC **no responde** a sorpresas de tasas de corto plazo;
  - [Pub] un trabajo de la Fed (2026, visto solo en un resumen secundario) informa reacciones fuertes desde 2020, de volatilidad y de precio ante sorpresas de «risk-off».
- **Uso posible [Hip]:** reducir la exposición en ventanas de anuncio para bajar la caída, no para ganar.
- **Riesgos:** unos 8 FOMC por año, así que la potencia es baja.
- **Datos:** el calendario es público y requiere descarga.
- **Prioridad:** baja.

### C10. Reversión tras movimientos extremos o cascadas de liquidación (de 1 a 5 días)
- **Mecanismo [Hip]:** las liquidaciones forzadas exageran la caída y luego hay un rebote.
- **Evidencia:** [Pub] algunos trabajos encuentran que en BTC la estrategia contraria supera al momentum; la evidencia es dispersa.
- **En contra:**
  - [TIA] la reversión del bot perdió a 1 h y la diaria no tenía base;
  - el condicional extremo es otra prueba, pero el umbral es arbitrario y hay pocos eventos.
- **Datos:** BTC 1 h spot y futuros son locales; no hay datos de liquidaciones (se aproximarían con caída más colapso de la prima).
- **Prioridad:** media-baja.

### C11. Predictibilidad cruzada entre criptos (lead-lag)
- **A favor:** [Pub] Guo, Sang, Tu y Wang (JEDC 2024): los retornos rezagados de otras monedas predicen hasta **10 minutos**.
- **Descarte para esta fase:** es alta frecuencia, contraria al foco de posiciones selectivas, y requiere otra infraestructura.

### C12. Estacionalidad (día de la semana, fin de semana, ciclo del halving)
- **Evidencia:** [Pub] mixta. Aharon y Qadan encuentran un efecto de día de la semana; Kinateder y Papavassiliou, ninguno en retornos, solo menor riesgo el fin de semana.
- **Descarte:** sin mecanismo económico sólido, con alto riesgo de minería de datos; el halving tiene n = 4.

### C13. IA o aprendizaje automático para elegir cuándo operar (meta-labeling y abstención) sobre una señal base
- **Mecanismo [Hip]:** un clasificador decide **si** tomar una señal base, según el estado del mercado, y se abstiene en el resto.
- **A favor:**
  - [Pub\*] Gu, Kelly y Xiu (RFS 2020): el aprendizaje automático mejora la predicción en el corte transversal de acciones (mensual);
  - [Pub] López de Prado propone el meta-labeling, la triple barrera y la validación con purga y embargo.
- **En contra:**
  - [Pub] no encontré pruebas independientes y fuera de muestra del meta-labeling (la evidencia positiva es de un proveedor);
  - [Pub] un preprint de 2026 sobre BTC horario: los modelos ganan en bruto, pero pierden con 10 bps salvo que se filtren por costo;
  - [TIA] en E1 el timing ≈ azar y la confianza no estaba calibrada.
- **Advertencia crítica [Hip]:** un modelo de lenguaje entrenado con datos de 2025 **conoce el futuro** de cualquier backtest anterior. Usarlo para juzgar noticias históricas es mirada al futuro, así que **las señales con LLM solo pueden evaluarse de forma prospectiva**.
- **Prioridad:** después de C3. Solo tiene sentido si alguna variable mostró información incremental.

### C14. Carry o base de futuros con vencimiento (variante de H-CARRY)
- **Estado:** cerrada por decisión previa; solo la reabre el disparador del monitor (> 12 % anual).
- No se prioriza.

## 2. La pista de breakout y confianza (H-E1-BC): solo hipótesis exploratoria
- **[TIA] La observación:** en E1, la correlación de Spearman entre la confianza de entrada y el retorno neto fue de +0,22 (IC90 0,11 / 0,32, con n = 185) solo en breakout. En trend fue −0,02, en mean reversion −0,08 y en la fusión −0,02.
- **Por qué es exploratoria:**
  - es 1 de 4 análisis secundarios sin ajustar;
  - con 4 miradas al 90 %, la probabilidad de al menos un falso positivo ronda el 34 %;
  - el tamaño observado está inflado por el sesgo del ganador.
- **El protocolo de confirmación** está en `PROTOCOLO_H_E1_BC_BORRADOR.md`. **No se ejecuta.** Prueba la **relación monótona**, no un umbral; fija el universo, los costos y los criterios antes de descargar; y limita la cantidad de pruebas.

## 3. Ranking (1 a 5: más es mejor; el valor esperado combina la probabilidad previa con lo que cambiaría la decisión)
| # | Candidata | Valor esperado | Diversidad | Factibilidad | Calidad de la evidencia | ¿Datos locales? | Lectura |
|---|---|---|---|---|---|---|---|
| 1 | **C3 Información incremental** (compuerta) | 4 | 3 | **5** | 3 | **Sí** | Barata y decisiva: dice qué variables merecen convertirse en estrategia |
| 2 | **C1 Funding o prima extremos → timing spot** | 3 | **4** | **5** | 2 | **Sí** | Mecanismo plausible, que diversifica a T y es de posición; potencia baja |
| 3 | **C2 Atención (Wikipedia)** | 3 | 4 | 4 | **4** | No (KB) | El mejor respaldo académico entre las fuentes nuevas; posible decaimiento |
| 4 | H-E1-BC breakout × confianza en ETH/SOL | 2 | 1 | 4 | 1 | No (≈ 4 MB por activo) | Probabilidad previa baja; solo confirmatoria |
| 5 | C5 Momentum transversal | 3 | 5 | 2 | 3 | No (universo histórico) | Valioso, pero caro en datos y con riesgo de supervivencia |
| 6 | C6 Valor relativo BTC/ETH | 2 | 4 | 5 | 2 | Sí | Mecanismo ambiguo |
| 7 | C7 On-chain | 2 | 5 | 3 | 2 | No | Pocos ciclos; umbrales sobreajustados |
| 8 | C10 Reversión tras extremos | 2 | 2 | 4 | 2 | Sí | Pariente de lo ya refutado |
| 9 | C13 IA de selección | 2 hoy (4 si C3 pasa) | 2 | 3 | 1 | Sí | Hoy no hay señal base que filtrar |
| 10 | C4 Tendencia en otras criptos | 2 | 1 | 3 | 3 | No | Poca potencia adicional |
| 11 | C8 Prima de varianza | 2 | 5 | 1 | 2 | No | Otra infraestructura y riesgo de cola |
| 12 | C9 Macro | 1 | 3 | 3 | 2 | No | Gestión de riesgo, no alfa |
| — | C11 lead-lag, C12 estacionalidad, C14 carry | — | — | — | — | — | Descartadas o cerradas en esta fase (ver el registro) |

## 4. Plan experimental concreto propuesto (para revisar juntos; nada ejecutado)
**Ronda E2, con un máximo de 3 hipótesis confirmatorias y Holm entre ellas:**
1. **E2-A, compuerta C3, con datos locales y sin autorización adicional.**
   - Diario, objetivos a 7 y 28 días, en BTC y ETH, desde 2021-01 (período con funding).
   - Lista cerrada de 5 variables; ventana expansiva; Clark–West; Holm 10×.
   - Prerregistro antes de leer nada.
2. **E2-B, C1 timing por funding en spot.**
   - Una regla fija de percentiles en BTC y ETH, con datos locales, decisión diaria y 10 bps.
   - Puede ir en paralelo a E2-A, pero se prerregistra como hipótesis independiente: no se elige mirando E2-A.
3. **E2-C, uno de dos según tu decisión:**
   - **C2 atención** (requiere autorizar la descarga de las vistas de Wikipedia), o
   - **H-E1-BC** en ETHUSDT y SOLUSDT a 1 h (requiere autorizar ≈ 8 MB de data.binance.vision).

**Reglas comunes:**
- prerregistro con hash antes de cualquier dato;
- una sola ejecución por hipótesis;
- costos de spot de 10 bps por lado más deslizamiento;
- ejecución en la apertura siguiente;
- nulo emparejado (frecuencia, exposición y duración) o exceso frente a la estática equivalente;
- bootstrap por bloques;
- Holm sobre la ronda;
- informar el Sharpe deflactado ([Pub\*] Bailey y López de Prado, 2014) cuando haya una curva de capital;
- un registro de todo lo probado, incluido lo que falle.

**Qué no hacer:**
- variantes de umbrales;
- elegir activos o períodos después de mirar;
- usar LLM sobre el pasado;
- agregar indicadores sin pasar por la compuerta C3.

**Autorizaciones que harían falta (solo si elegís esas ramas):**
| Datos | Fuente | Período | Volumen aproximado |
|---|---|---|---|
| Vistas diarias de los artículos «Bitcoin» y «Ethereum» | API REST de Wikimedia | 2015-07 → 2026-10 | < 1 MB |
| ETHUSDT y SOLUSDT spot 1 h, mensuales, con `.CHECKSUM` | data.binance.vision | 2019-10 (SOL 2020-08) → 2026-05 | ≈ 8 MB |
| SOLUSDT spot 1d, si se incluye SOL en C1 | data.binance.vision | 2020-08 → 2026-05 | < 1 MB |

## 5. Objeciones principales a este plan (las más fuertes)
1. **«Todo vuelve a ser BTC y ETH 2020–2026».** Es cierto: sin datos prospectivos ni mercados nuevos, la potencia seguirá siendo baja. Por eso C3 es una compuerta barata, no una promesa.
2. **«Las fuentes favorables a C1 son comerciales».** Por eso C1 se plantea como prueba de refutación, con una sola regla.
3. **«C2 puede ser momentum disfrazado».** Por eso se mide contra una base que ya incluye momentum.
4. **«Probar tres cosas a la vez infla los falsos positivos».** Se controla con Holm y con un tope de 3 hipótesis.
5. **«Posiblemente no exista una ventaja neta accesible para un participante minorista en spot».** Es una conclusión legítima si la ronda E2 también falla. Ahorraría capital.

## 6. Fuentes
Verificadas en esta sesión:
- Liu y Tsyvinski, *Risks and Returns of Cryptocurrency*, RFS 34(6), 2021: [IDEAS](https://ideas.repec.org/a/oup/rfinst/v34y2021i6p2689-2727..html), [NBER WP](https://www.nber.org/system/files/working_papers/w24877/w24877.pdf).
- Liu, Tsyvinski y Wu, *Common Risk Factors in Cryptocurrency* (JF 2022): [SSRN](https://papers.ssrn.com/abstract=3379131), [resumen](https://alphaarchitect.com/factors-investing-in-cryptocurrency/).
- Grobys y Sapkota, *Cryptocurrencies and momentum*, Econ. Letters 180, 2019: [IDEAS](https://ideas.repec.org/a/eee/ecolet/v180y2019icp6-10.html), [repositorio](https://osuva.uwasa.fi/handle/11111/2278).
- Hudson y Urquhart, *Technical trading and cryptocurrencies*, Ann. Oper. Res. 297, 2021: [repositorio](https://reading-clone.eprints-hosting.org/85715), [Hull](https://hull-repository.worktribe.com/output/2328042).
- Detzel et al., *Learning and predictability via technical analysis…*, Financial Management 50(1), 2021: [IDEAS](https://ideas.repec.org/a/bla/finmgt/v50y2021i1p107-137.html); evidencia contraria en 12 criptos: [Glasgow](https://eprints.gla.ac.uk/302711).
- Schmeling, Schrimpf y Todorov, *Crypto carry*, BIS WP 1087: [BIS](https://www.bis.org/publ/work1087.pdf), [CEPR DP 20719](https://cepr.org/publications/dp20719).
- He, Manela, Ross y von Wachter, *Fundamentals of Perpetual Futures*: [arXiv 2212.06888](https://arxiv.org/abs/2212.06888v5).
- Funding como señal (fuentes no académicas): [BitMEX](https://www.bitmex.com/blog/xbtusd-funding-mean-reversion-strategy), [The Block / K33](https://www.theblock.co/post/315831/perp-signal-bitcoin-bottom-bullish-year-end-k33), [tesis de York](https://yorkspace.library.yorku.ca/items/21b012fb-41e8-4da7-9fc3-0daaecdd39ff).
- Momentum temporal cripto: [Swinkels (seminario)](https://utilities.tinbergen.nl/?p=66235), [Han, Kang y Ryu (WP)](https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/Time_Series_and_Cross_Sectional_Momentum_in_the_Cryptocurrency_Market_with_IA.pdf), [Borgards 2021](https://econpapers.repec.org/RePEc:eee:ecofin:v:57:y:2021:i:c:s1062940821000590), [momentum intradía de BTC](https://research.birmingham.ac.uk/en/publications/bitcoin-intraday-time-series-momentum/).
- Balcilar et al., *Can volume predict Bitcoin returns and volatility?*, Econ. Modelling 64, 2017: [repositorio](https://repository.up.ac.za/handle/2263/60028).
- Fil y Kristoufek, *Pairs trading in cryptocurrency markets*, IEEE Access 8, 2020: [referencia](https://mdev.sciencepod.net/?p=163213), [tesis que lo revisa](https://thesis.eur.nl/pub/67552/Thesis-Pairs-trading-.pdf).
- Guo, Sang, Tu y Wang, *Cross-cryptocurrency return predictability*, JEDC 163, 2024: [IDEAS](https://ideas.repec.org/a/eee/dyncon/v163y2024ics0165188924000551.html).
- Prima de varianza: [Alexander e Imeraj](https://sro.sussex.ac.uk/id/eprint/91094/), [Almeida et al.](https://arxiv.org/html/2410.15195v2).
- On-chain: [tesis de Vaasa](https://osuva.uwasa.fi/items/48a4f9df-03ca-4b96-9072-07b462b14dfa/full); umbrales de practicantes, p. ej. [Nansen](https://www.nansen.ai/post/onchain-metrics-key-indicators-for-cryptocurrency-price-prediction).
- Macro y cripto: [NY Fed SR 1052](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr1052.pdf), [resumen del trabajo de la Fed de 2026](https://rwatimes.substack.com/p/how-do-cryptocurrencies-price-economic).
- Estacionalidad: [Aharon y Qadan](https://cris.haifa.ac.il/en/publications/bitcoin-and-the-day-of-the-week-effect/), [Quantpedia](https://quantpedia.com/are-there-any-simple-calendar-effects-in-bitcoin-market/).
- Aprendizaje automático en BTC con costos: [preprint](https://www.emergentmind.com/papers/2606.00060), [Souza et al. 2019](https://doaj.org/article/fb0504422054491a930c694bc7009c98); meta-labeling, solo evidencia de un proveedor: [Hudson & Thames](https://hudsonthames.org/?p=3448).

Citadas de memoria, **sin verificar hoy**:
- Moskowitz, Ooi y Pedersen (JFE 2012); Hurst, Ooi y Pedersen (JPM 2017);
- Huang, Li, Wang y Zhou (JFE 2020); Kim, Tse y Wald (JFM 2016);
- Moreira y Muir (JF 2017); Cederburg et al. (JFE 2020);
- Daniel y Moskowitz (JFE 2016);
- Harvey, Liu y Zhu (RFS 2016); Bailey y López de Prado (JPM 2014); Bailey, Borwein, López de Prado y Zhu (J. Comp. Finance 2017);
- White (Econometrica 2000); Hansen (JBES 2005);
- Gu, Kelly y Xiu (RFS 2020); López de Prado (*Advances in Financial ML*, 2018);
- Kristoufek (Sci. Reports 2013); Lucca y Moench (JF 2015).
