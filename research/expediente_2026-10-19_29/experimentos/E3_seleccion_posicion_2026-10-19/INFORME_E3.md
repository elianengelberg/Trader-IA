# Informe E3: selección de nuevas estrategias de posición (investigación y diseño, 2026-10-19)

**Estado:**
- **No** descargué datos, **no** ejecuté backtests ni experimentos, **no** instalé nada y **no** modifiqué el repositorio.
- Leí literatura en la web e inspeccioné los datos locales sin alterarlos.
- El borrador de protocolo de la próxima ronda está en `PROTOCOLO_E3_BORRADOR.md`. Sigue **sin ejecutar** y **sin congelar**.

**Leyenda:**
- **[Pub]**: publicado; verificado hoy en el texto o en el resumen oficial.
- **[Pub-sec]**: publicado, pero solo lo vi en un resumen de terceros (prensa, blog o nota institucional).
- **[Pub\*]**: citado de memoria; no lo verifiqué hoy.
- **[Ind]**: análisis de la industria, sin revisión por pares.
- **[Hip]**: hipótesis o estimación mía.
- **[TIA]**: resultado de Trader-IA.

Ningún número [Pub] es un resultado del bot. Ningún número [Hip] es una rentabilidad esperada: son órdenes de magnitud para dimensionar la potencia y los costos.

---

## 0. Resumen y recomendación

**Recomendación: la próxima ronda debería tener 2 candidatas, no 3.**

1. **XS-MOM: momentum transversal long-only** en un universo líquido de Binance spot (USDT). Es la única familia que cumple a la vez:
   - aporta información que el proyecto nunca probó: **qué** monedas tener, no **cuándo** estar invertido;
   - tiene evidencia publicada específica para cripto en horizontes de 1 a 4 semanas;
   - usa **datos nunca vistos** (las altcoins), gratuitos y con checksum oficial;
   - se puede implementar en spot, sin cortos ni infraestructura nueva.
2. **Capa de efectivo por momentum absoluto** sobre la cartera de la candidata 1: un lugar de la cartera solo se ocupa si la moneda tiene tendencia propia positiva; si no, queda en efectivo.
   - Es la forma más simple y sin parámetros nuevos de responder «cuándo quedarse fuera».
   - Su probabilidad de éxito es **baja**: el timing de corto plazo no mostró valor en T ni en E2.
3. **El tercer lugar queda vacío a propósito.** Ninguna otra familia cumple a la vez cuatro condiciones:
   - un mecanismo propio;
   - evidencia que sobreviva a los costos;
   - datos no vistos y viables;
   - independencia real de lo ya probado.
   La fuente más independiente, la **prima de riesgo de varianza** (venta de volatilidad en opciones), requiere infraestructura de opciones y datos pagos. Si querés avanzar por ahí, propongo un **estudio de viabilidad documental**, sin datos ni backtest.

**Advertencias:**
- **La evidencia a favor de XS-MOM es mixta y probablemente está inflada:**
  - viene de muestras anteriores a 2019, monedas chicas, carteras long-short sin costos y datos con sesgo de supervivencia;
  - corregido ese sesgo, el momentum de una semana desaparece ([Pub] Ammann et al., 2022);
  - entre las monedas sobrevivientes no hay momentum ([Pub] Grobys et al., 2026).
- **Lo que justifica una sola prueba:** tres estudios independientes encuentran que el momentum es **más fuerte o persiste en las monedas grandes y líquidas**, justo donde los costos son bajos (LTW, Zaremba et al., Fieberg et al.).
- **Mi expectativa a priori es baja o moderada** [Hip]: lo más probable es «insuficiente» o «información sin ventaja operable».
- **Potencia:** la prueba de **información** (correlación de rangos semanal sobre ~100 monedas) puede detectar efectos moderados. La prueba **económica** (cartera long-only neta frente a la canasta) solo detectaría ventajas muy grandes, del orden de 35–45 %/año [Hip]. Una ventaja neta solo se podría respaldar después, con datos prospectivos.

---

## 1. Punto de partida [TIA]

| Línea | Qué preguntaba | Resultado |
|---|---|---|
| T (tendencia 1/3/6 meses, BTC y ETH) | ¿Cuándo estar invertido? | INSUFICIENTE: +7,0 %/año fuera de muestra, IC90 −8,8 / +22,9. Evaluación en papel en curso |
| T-MULTI (T en 11 ETF) | ¿Cuándo, en otros mercados? | INSUFICIENTE: −0,48 %/año |
| V (volatilidad gestionada) y R (reversión diaria) | ¿Cuánto o cuándo? | DESCARTADAS |
| H-CARRY (funding delta neutral) | Prima de carry | CERRADA. Se reabre solo si el funding de 90 días supera el 12 %/año. Al 2026-10-01 estaba en 6,5 % |
| E1 (estrategias del bot, 1 h) | ¿Cuándo, intradía? | EN CONTRA las tres |
| E2-A, E2-B y E2-C | ¿Variables de estado, funding o atención para timing? | Insuficiente (nula), insuficiente y en contra |

**Lecciones:**
1. Todo lo probado es **timing de BTC y ETH** (una sola dimensión: cuándo estar invertido). Ninguna variante superó al beta.
2. Las pruebas de timing en uno o dos activos tienen **potencia muy baja**: en E2-B, el efecto mínimo detectable era de ≈ 15 %/año.
3. **Conclusión metodológica:** conviene que la próxima prueba tenga **amplitud** (muchos activos por muchas semanas), no solo más años. Esa es otra razón para priorizar la dimensión transversal.

**Mapa de fuentes de información** (dos estrategias con indicadores distintos que comparten fuente no cuentan como independientes):

| Fuente | Familias que la usan | Estado en el proyecto |
|---|---|---|
| (i) Serie de precio propia (timing) | T, momentum temporal, rupturas, medias móviles, volatilidad gestionada, reversión temporal, estrategias del bot | Agotada en BTC y ETH a 1 h, diario y mensual |
| (ii) Precio relativo entre activos (transversal) | XS-MOM, CTREND, reversión transversal, MAX | **Nunca probada** |
| (iii) Posicionamiento en derivados | Funding, prima, open interest, base | Sin información en series de tiempo (E2) |
| (iv) Primas de seguro o carry | Prima de varianza, carry delta neutral | Carry cerrado por regla; prima de varianza nunca probada |
| (v) Atención o flujos externos | Wikipedia, stablecoins, flujos de ETF | E2-C en contra |
| (vi) Fundamentales on-chain | MVRV, valor de red | No probada (datos pagos) |

Una cartera XS-MOM long-only mezcla (i) a través del beta de mercado con (ii) a través de la selección. **Solo el componente de selección** (cartera menos canasta) es información nueva, y el protocolo lo mide por separado.

---

## 2. Candidata principal: momentum transversal (XS-MOM)

### 2.1 Mecanismo
- **[Pub\*] Comportamiento:** subreacción y difusión lenta de la información, comportamiento de manada y flujos que persiguen rendimientos (en acciones: Jegadeesh y Titman, 1993; Asness, Moskowitz y Pedersen, 2013).
- **[Pub]** Liu y Tsyvinski (2021) vinculan la atención de los inversores con los retornos cripto. LTW (2022) proponen un factor de momentum cripto.
- **[Hip] Específico de cripto:** el capital rota entre narrativas (capas 1, DeFi, memes, IA) durante semanas. Los minoristas compran lo que sube, y el arbitraje transversal está limitado porque no siempre se puede vender en corto.
- **[Hip] Por qué podría persistir en monedas líquidas:** ahí la información se difunde por canales minoristas lentos, mientras que en las ilíquidas domina la reversión por provisión de liquidez.

### 2.2 Evidencia a favor
- **[Pub] Liu, Tsyvinski y Wu (JF 2022; texto del working paper de 2019):**
  - monedas con capitalización > US$1 M de CoinMarketCap, 2014–2018; quintiles ponderados por valor y rebalanceo semanal;
  - el long-short de momentum a **1, 2, 3 y 4 semanas** rinde **2,7 %, 3,3 %, 4,1 % y 2,5 % semanal**, con t entre 2,0 y 2,7. A 8, 16, 50 y 100 semanas **no** es significativo;
  - **el momentum funciona mejor en las monedas grandes:** 4,2 %/semana en el grupo de tamaño sobre la mediana, frente a 0,6 % no significativo bajo la mediana;
  - **pero no es significativo en regresiones de Fama–MacBeth**, que equivalen a ponderar igual; sí lo es para monedas > US$10 M;
  - eligieron 3 semanas como medida principal porque daba el mayor diferencial: una elección posterior, que yo no repito.
- **[Pub-sec] Dobrynskaya** (~2000 monedas, 2014–2020; según la nota de HSE y un blog): momentum positivo hasta ~2 semanas y **reversión desde ~4 semanas**.
- **[Pub] Swinkels (2018; resumen de seminario, más de 3100 monedas, 2013–2018):** momentum transversal fuerte de 1 día a 2 semanas.
- **[Pub] Zaremba et al. (IRFA 2021; más de 3600 monedas, datos diarios):** la reversión diaria se concentra en las monedas ilíquidas; **las más grandes y negociables muestran momentum diario**.
- **[Pub] Fieberg et al. (JFQA 2025; resumen):** CTREND, una señal de tendencia que combina precio y volumen en varios horizontes con aprendizaje automático (> 3000 monedas). Predice retornos, **sobrevive a los costos y persiste en monedas grandes y líquidas**.
- **[Pub] Fieberg et al. (QF 2023):** el momentum de factores cripto es robusto entre subperíodos (2014–2022).
- **[Pub] Mercik et al. (IRFA 2025; > 500 monedas importantes, 2017–2023):** interacciones entre liquidez, riesgo y retornos pasados; long-short fuera de muestra con Sharpe > 1.

### 2.3 Evidencia en contra
- **[Pub] Grobys y Sapkota (Economics Letters 2019; 143 monedas, 2014–2018, mensual):** sin momentum significativo.
- **[Pub] Ammann, Burdorf, Liebi y Stöckl (2022; 3904 monedas, 2014–2021):**
  - el sesgo de supervivencia y exclusión es de **62 %/año en carteras de peso igual** (0,93 % en las ponderadas por valor);
  - corregido, **no hay relación positiva entre el retorno y el momentum de una semana**.
- **[Pub] Grobys, Sandretto y Äijö (FRL 2026):**
  - entre las monedas que se mantuvieron en el top 100 de 2017 a 2024, **no hay momentum**;
  - con las 30 más grandes de cada año, solo da ganancias tras recortar los datos, y aun así **depende mucho de la muestra**.
- **[Pub] Grobys, Kolari et al. (FMPM 2025; cripto de gran capitalización, peso igual):**
  - el momentum sufre **caídas severas**;
  - **una sola moneda puede volver no significativos los retornos**;
  - la gestión por volatilidad mitiga las caídas;
  - las burbujas recurrentes pueden fabricar momentum aparente.
- **[Pub] Han, Kang y Ryu (working paper; resumen):** con costos y fluctuaciones diarias, muchas carteras se liquidan. La evidencia de momentum transversal es **débil**; los perdedores rebotan y generan pérdidas.
- **[Pub] Bianchi, Babiak y Dickerson (JBF 2022):** la reversión de corto plazo, como provisión de liquidez, rinde en pares de baja actividad. Es compatible con Zaremba, pero muestra que en el universo amplio el signo de 1 semana es ambiguo.
- **[Pub-sec] ABFER 2026 (resumen de conferencia):** los activos con grandes oscilaciones de precio tienen después retornos ajustados por riesgo **negativos** hasta 8 semanas. Es un riesgo directo para comprar «ganadores» volátiles.
- **[Pub\*] General:**
  - las anomalías pierden ≈ 30–60 % tras su publicación (McLean y Pontiff, 2016);
  - con muchas pruebas hace falta t > 3 (Harvey, Liu y Zhu, 2016).

### 2.4 Lectura crítica
- **La evidencia positiva tiene casi todos los defectos que debemos evitar:** muestras de 2014–2018 con burbujas, monedas chicas, long-short ponderado por valor sin costos y supervivencia mal controlada.
- **Nuestro escenario es casi enteramente posterior a esas publicaciones:** universo líquido, long-only, 2019–2024 y con costos. Si el efecto existía, lo esperable es que sea **mucho menor** que lo publicado, o nulo.
- **El argumento a favor de probarlo una vez:** la literatura coincide en que el efecto es **más fuerte en las monedas grandes y líquidas** (LTW, Zaremba, CTREND). En equities pasa lo contrario. Si no aparece en el universo líquido y barato de operar, la familia queda descartada para Trader-IA.
- **¿Sobrevive a los costos y a la competencia?**
  - **Costos** [Hip]: con rebalanceo semanal y banda de permanencia, estimo un lastre de **≈ 4–8 %/año**. Una correlación de rangos de 0,01 apenas daría ≈ 7 %/año bruto; hace falta 0,02–0,03 o más.
  - **Competencia:** los fondos cuantitativos de cripto operan factores de momentum. Para una cuenta chica la capacidad no limita, pero el decaimiento posterior a la publicación sí.
- **Independencia:**
  - **alta** en la información (dimensión transversal);
  - **baja** en el riesgo: la cartera long-only tiene beta alto frente a BTC y cae junto con T y con el buy and hold en las crisis;
  - por eso el protocolo mide aparte el **componente de selección** (cartera menos canasta) y su correlación con BTC y con T.
- **Cómo puede fallar:**
  1. no hay correlación de rangos en monedas líquidas después de 2019;
  2. hay información, pero los costos o la rotación se la comen;
  3. hay caídas por rebote de los perdedores, o el resultado depende de una sola moneda;
  4. faltan las monedas excluidas en los datos (sesgo de supervivencia), lo que invalida la prueba;
  5. riesgos de la cotización en USDT y del exchange.
- **Qué obliga a descartarla:** el límite superior del IC90 de la correlación de rangos media queda < 0,01, o la validez de supervivencia falla. Los detalles están en §2.8.

### 2.5 Especificación inicial: cada elección justificada antes de ver datos

| Elemento | Elección | Por qué (sin mirar datos) |
|---|---|---|
| Mercado | Binance spot, pares contra USDT | Es donde ejecuta el bot. Los datos son oficiales, gratuitos y con checksum. Se usaron en T y H-CARRY, solo para BTC y ETH |
| Formación y ejecución | Señal con el cierre del domingo (00:00 UTC del lunes); ejecución en la **apertura oficial del lunes** | Semanal como en LTW. El día de la semana queda fijo, no se elige por resultados |
| Elegibilidad (en cada fecha, con datos hasta ese momento) | ≥ 180 días desde la primera vela diaria; los últimos 28 días completos; mediana de 30 días del volumen diario en USDT ≥ 1 M | Evitar el efecto de listado ([Ind]: los nuevos listados tienden a caer tras subidas previas) y datos inestables. El piso de liquidez es [Hip] |
| Exclusiones (por regla) | Stablecoins y fiat (lista fijada de antemano, más la regla «volatilidad anual de 90 días < 10 %»); tokens apalancados (sufijos UP, DOWN, BULL, BEAR); duplicados envueltos o en staking (si la correlación de 90 días con otra moneda elegible y más líquida es > 0,98, queda solo la más líquida); tokens respaldados por materias primas (lista de antemano) | No son activos con su propio riesgo cripto. Las reglas son mecánicas, no de juicio |
| Universo de información (U100) | Top 100 elegibles por mediana de volumen | **Amplitud para la prueba predictiva**: la potencia crece con el número de monedas |
| Universo invertible (U30) | Top 30 elegibles por mediana de volumen | Costos bajos. Grobys et al. (2026) usan «las 30 más grandes» como versión simple |
| Supervivencia | Se incluyen **todos** los pares USDT que existieron, también los excluidos después, mientras cotizaban | Ammann et al. (2022). Hay un control de validez antes de interpretar |
| Señal | **Compuesta:** media de los rangos percentiles transversales de los retornos logarítmicos de 7, 14, 21 y 28 días | Es la franja de 1 a 4 semanas documentada (LTW; Dobrynskaya; Swinkels). No se elige el «mejor» horizonte (LTW eligió 3 semanas después de mirar). Se excluyen horizontes > 4 semanas, donde se reporta reversión o nada |
| Sin período de salto | No se descarta la última semana | En monedas líquidas se observa momentum diario, no reversión (Zaremba). Saltar sería un parámetro más |
| Posiciones | k = 6 (quintil superior de U30) | Coincide con las carteras por quintiles de la literatura |
| Banda de permanencia | Se mantiene mientras el rango sea ≤ 12 (el 40 % superior); los lugares libres se llenan con los mejores rangos no tenidos | Reduce la rotación; es una técnica estándar contra costos ([Pub\*] Novy-Marx y Velikov, 2016). El 2k es [Hip] |
| Ponderación | 1/6 al entrar. Sin rebalanceo de los que se quedan, salvo que su peso salga de [1/12, 1/3]; entonces vuelve a 1/6 | Peso igual: robusto y sin estimar covarianzas ([Pub\*] DeMiguel et al., 2009). La deriva limita la rotación |
| Salida | Al bajar del rango 12, al perder elegibilidad o al ser excluida del exchange (última vela disponible) | Reglas mecánicas |
| Efectivo (candidata 2) | Cada lugar se ocupa solo si la moneda tiene **momentum absoluto** (media de los retornos de 7–28 días) > 0; si no, ese sexto queda en USDT | Momentum dual; reutiliza la misma señal con umbral 0, sin parámetros nuevos |
| Comisión | 10 pb por lado | Binance VIP 0 sin descuento BNB ([Pub] la tabla de Binance.US muestra 0,10 %; hay que confirmar la de Binance global) |
| Spread y slippage | Por tramo de liquidez: rangos 1–2: 5 pb; 3–10: 10 pb; 11–30: 20 pb, por lado | [Hip], conservador. Estrés ×2 sobre el costo total. Se informa el costo de equilibrio. El estimador de Abdi–Ranaldo [Pub\*] se usa solo como control descriptivo |
| Exclusión del exchange | Salida al último cierre disponible; estrés con −30 % adicional | [Hip] |

**Órdenes de magnitud** [Hip; el resultado real se informa]:
- rotación ≈ 25 % de la cartera reemplazada por semana con la banda;
- ≈ 25–30 veces de valor negociado por año;
- lastre ≈ 4–8 %/año;
- permanencia media ≈ 4 semanas, lo que encaja con «varios días o semanas».

No son «pocas operaciones» en número absoluto (≈ 1,5 cambios por semana), pero sí son posiciones de semanas con costos controlados por la banda.

### 2.6 Exposición al mercado y caídas simultáneas
- La versión **totalmente invertida** tiene beta > 1 frente a BTC [Hip] y sufre caídas de todo el mercado cripto (en E2, el buy and hold de BTC cayó 77 % [TIA]; las altcoins suelen caer más).
- En las crisis, las correlaciones suben y la liquidez desaparece.
- El **efectivo es USDT**, con riesgo de despegue y de contraparte. También hay riesgo del propio exchange.
- **Defensa incluida:** solo la capa de efectivo (candidata 2). No agrego stop-loss: sería un parámetro más sin evidencia.
- **Métricas que se informan:**
  - caída máxima, CVaR del 5 % semanal y peor semana;
  - tiempo bajo el agua;
  - beta frente a BTC;
  - correlación del componente de selección con BTC y con T;
  - concentración: aporte de la mejor moneda al exceso acumulado.

### 2.7 Comparaciones
| Referencia | Para qué |
|---|---|
| **EW-U30:** las 30 elegibles con peso igual, rebalanceo semanal, mismos costos | **Principal:** aísla el valor de la selección |
| BTC buy and hold | La alternativa realista del usuario |
| Efectivo (0 %) | Mínimo absoluto |
| **Exposición equivalente** (candidata 2): la cartera totalmente invertida escalada a la exposición media de la variante con efectivo (diaria, sin costos extra) | Aísla el valor del timing de la capa de efectivo |
| **Nulo de selección aleatoria:** 6 monedas al azar de U30 con la misma banda y mecánica, 2000 réplicas | Controla los efectos de composición del universo y de la mecánica |
| Correlación con T_BTC y T_ETH, y con BTC | Mide la independencia |

### 2.8 Evaluación fuera de muestra y controles contra el sobreajuste
- **Prerregistro con hash antes de descargar.** Como las altcoins nunca se vieron, las reglas se congelan **antes** de bajar el primer archivo.
- **Separación de etapas por código:**
  - la etapa de calidad de datos (supervivencia, universo, huecos) **no puede** calcular retornos de estrategias;
  - el período reservado **ni siquiera se descarga** hasta que corresponda abrirlo, y el código además lo bloquea.
- **Períodos fijados ahora:**
  - **confirmatorio:** desde la primera semana con ≥ 30 elegibles (se determina por regla en la etapa de calidad; estimo 2019 [Hip]) hasta el **2024-12-31**;
  - **reservado E3:** [**2025-01-01, 2026-06-01**), unas 74 semanas. Se abre **una sola vez**, y solo si el confirmatorio da «favorable» o «información sin ventaja». Si no, queda reservado para hipótesis futuras;
  - **no se usa** el período reservado de H-CARRY [2026-06-01, 2026-10-14): el prerregistro de T-papel prohíbe evaluar dentro de él. Usarlo requiere tu autorización;
  - **después:** evaluación prospectiva en papel, como en T-papel.
- **Pruebas confirmatorias (Holm, m = 3):**
  - **H1 (predictiva):** correlación de rangos de Spearman semanal entre la señal y el retorno de la semana siguiente en U100. Media > 0, con Newey–West de 4 rezagos y p unilateral.
  - **H2 (económica):** exceso semanal neto de la cartera top 6 sobre EW-U30. Bootstrap circular por bloques de 13 semanas, 10 000 réplicas.
  - **H3 (efectivo):** exceso de timing de la variante con efectivo frente a la exposición equivalente. Mismo bootstrap.
- **Condiciones que endurecen la conclusión** (no son pruebas alternativas):
  - exceso > 0 con costos ×2;
  - correlación de rangos > 0 en al menos 2 de 3 tercios del período;
  - p del nulo aleatorio ≤ 0,05;
  - sin la moneda que más aporta, el exceso sigue > 0 (el problema de «una sola moneda» de Grobys et al.).
- **Sensibilidad, solo descriptiva y posterior:** k ∈ {4, 6, 10}; N ∈ {20, 30, 50}; cada horizonte por separado; sin banda. **No** se usa para elegir nada.
- **Pruebas sintéticas antes de los datos reales:**
  - sin momentum, el rechazo debe rondar el 5 %;
  - con una correlación plantada de 0,05, se debe detectar;
  - invariancia al truncar en 5 cortes;
  - comprobaciones de que no se mira al futuro.
- **Sharpe deflactado** [Pub\*] (Bailey y López de Prado) para cualquier Sharpe que se reporte.
- **Potencia** [Hip]:
  - **H1:** el desvío de la correlación semanal es ≈ 0,12–0,15 con ~100 monedas; con ≈ 280 semanas, el error estándar es ≈ 0,009 y el **efecto mínimo detectable ≈ 0,025–0,03**. Una correlación de 0,03 equivale a ≈ 20 %/año bruto en el top 6.
  - **H2:** tracking error ≈ 25–35 %/año, así que el **efecto mínimo es ≈ 35–45 %/año**.
  - **H3:** **≈ 15–25 %/año**, como en E2-B.
  - Lo esperable es que solo H1 pueda dar una respuesta clara.

---

## 3. Otras familias: evidencia y crítica

Cada familia sigue el mismo esquema: mecanismo, a favor, en contra, costos y competencia, independencia, cómo falla, veredicto.

### 3.1 Momentum temporal de varios horizontes (= familia de T)
- **Mecanismo:** subreacción y manada en la serie propia ([Pub\*] Moskowitz, Ooi y Pedersen, 2012).
- **A favor:**
  - [Pub] Han, Kang y Ryu: evidencia de momentum temporal «fuerte» con costos;
  - [Pub] Swinkels: momentum temporal de 1 día a 1 mes fuerte… **hasta la llegada de los futuros de BTC (dic-2017)**.
- **En contra:**
  - [Pub] Swinkels: **desapareció tras los futuros**;
  - [Pub] Hudson y Urquhart (2021): sin predictibilidad fuera de muestra en BTC;
  - [TIA] T: insuficiente; T-MULTI: insuficiente.
- **Independencia:** **ninguna** frente a T. Cambiar de ventanas o de indicador (medias móviles, canales) es la misma fuente (i).
- **Veredicto:** **no merece recursos nuevos.** La evaluación en papel de T es la vía correcta. «T en muchas altcoins» (C4) tampoco: las tendencias de las altcoins están muy correlacionadas con la de BTC [Hip] y no agregan información independiente.

### 3.2 Rupturas de rango
- **Mecanismo:** igual que la tendencia. Una ruptura de un canal de N días es una regla de tendencia con otra forma ([Pub\*] la literatura de trend following trata los canales y las medias como variantes de la misma señal).
- **A favor:** ninguna evidencia específica que sobreviva fuera de muestra en cripto.
- **En contra:** [TIA] breakout en E1: −0,198 %/operación; H-E1-BC es una pista de 1 de 4 miradas.
- **Independencia:** nula frente a T a escala diaria.
- **Veredicto:** **no.** H-E1-BC sigue exploratoria. Además opera en 1 h, fuera del objetivo de posiciones de semanas.

### 3.3 Reversión
- **(a) Reversión transversal de corto plazo (provisión de liquidez):**
  - [Pub] Bianchi et al. (2022) y Zaremba et al. (2021): rinde en **pares ilíquidos y de baja actividad**;
  - en el universo líquido hay momentum; el efecto vive donde los costos lo matan;
  - long-only solo captura la mitad y se contradice con XS-MOM a 1 semana;
  - un resultado de prensa (342 %/año neto) **no está verificado** y probablemente refleja los pares ilíquidos.
  - **Veredicto: no.**
- **(b) Reversión tras movimientos extremos o cascadas de liquidación:**
  - mecanismo defendible: las ventas forzadas demandan liquidez ([Pub\*] Brunnermeier y Pedersen, 2009);
  - **no encontré estudios rigurosos de retornos**; solo un preprint sobre señales de alerta temprana, que no es predicción de retornos;
  - [TIA] R descartada (autocorrelación −0,06); MR de E1 en contra;
  - los datos de liquidaciones históricas no están en local, y no verifiqué que haya un historial público completo.
  - **Veredicto: no.**

### 3.4 Volatilidad y prima de riesgo
- **(a) Volatilidad gestionada:** [TIA] V descartada. No reabrir.
- **(b) Prima de riesgo de varianza** (vender volatilidad implícita, cubierta):
  - **mecanismo:** prima de seguro; los compradores pagan por protección;
  - **a favor:** [Pub] Alexander e Imeraj (2020) construyen índices de volatilidad de BTC con opciones de Deribit y miden la prima; [Pub] Almeida et al.: varianza neutral al riesgo 0,72 frente a física 0,58 (prima ≈ 0,14), que **depende del régimen**;
  - **en contra:** no encontré rentabilidades netas de venta de volatilidad revisadas por pares. El riesgo de cola es extremo y exige margen y cobertura delta;
  - **independencia: la más alta del catálogo** (fuente iv);
  - **viabilidad: baja hoy.** Hacen falta opciones (Deribit), cuenta con margen, datos históricos de opciones (en general pagos) y un motor nuevo;
  - **veredicto:** no en la próxima ronda experimental. Es la candidata natural para un **estudio de viabilidad documental**, si querés diversificar fuentes a largo plazo.

### 3.5 Posicionamiento y funding
- **(a) Series de tiempo:** [TIA] E2-B insuficiente; FUNDING7 y PRIMA7 empeoran el pronóstico en E2-A. **No reabrir.**
- **(b) Funding transversal** (las monedas con funding relativo extremo rinden menos):
  - mecanismo plausible: apiñamiento de largos apalancados ([Pub] Schmeling, Schrimpf y Todorov);
  - **no encontré ningún estudio** que lo pruebe;
  - los datos serían gratuitos (`fundingRate` de todos los perpetuos);
  - el riesgo es que parezca un «rescate» de una familia que ya falló.
  - **Veredicto:** no ahora. Solo como interacción, después y si XS-MOM muestra información.
- **(c) Open interest y cocientes long/short:** historial público corto o no verificado. **No.**

### 3.6 Carry (delta neutral; carry transversal)
- **A favor:**
  - [Pub] Christin et al.: corto en futuros cubierto con spot, **Sharpe 7–10 dentro de muestra**;
  - [Pub] BIS WP 1087: el carry se explica por demanda apalancada minorista y escasez de arbitraje, con riesgo de caídas;
  - [Pub] He, Manela, Ross y von Wachter: miden desvíos grandes del perpetuo respecto de su valor fundamental.
- **En contra:** [TIA] H-CARRY dio +3,76 % frente a un comparador del 5 %. Se cerró con una regla de reapertura (funding de 90 días > 12 %); el monitor marcó 6,5 %.
- **Independencia:** alta (neutral al mercado). Es valiosa para un selector futuro.
- **Veredicto:** respetar el cierre. El monitor de T-papel es el mecanismo de reapertura. No es mi decisión reabrirla.

### 3.7 Estrategias que eligen cuándo quedarse en efectivo
- Es una **capa**, no una fuente propia: depende de la señal que la alimenta.
- En el proyecto, la única señal de efectivo con algo de evidencia es T (insuficiente); E2 no encontró variables de estado útiles.
- La candidata 2 prueba la versión más simple y coherente con XS-MOM.
- La arquitectura de largo plazo (elegir entre estrategias o efectivo) está en §7.

### 3.8 Otras familias consideradas (breve)
| Familia | Por qué no ahora |
|---|---|
| Tamaño (monedas chicas) | [Pub] La prima más documentada, pero sobreestimada ≈ 50 % por la supervivencia (Ammann et al.), ilíquida y no implementable long-only con costos razonables |
| MAX o lotería | [Pub] Evidencia contradictoria: Özdamar et al. (2021), relación **positiva**; Yadav (2025, horario), **negativa** |
| Valor o adopción de red | [Pub\*] Cong et al. Requiere datos on-chain por moneda (pagos) y es difícil de reconstruir en el tiempo |
| Deriva tras listados | [Ind] Subidas antes del anuncio y deriva corta o negativa. Se usa como **regla de exclusión** (edad ≥ 180 días), no como estrategia |
| Emisión de stablecoins | [Pub] Wei (2018) y Lyons y Viswanath-Natraj: sin efecto sistemático sobre precios. Descartada |
| Atención | [TIA] E2-C en contra |
| Momentum por sector o narrativa | Las categorías no existen en el tiempo (se asignan después). Riesgo de mirar al futuro |
| Interacciones y aprendizaje automático (CTREND, Mercik) | Mismo origen que XS-MOM, con muchos más grados de libertad. Solo como extensión si XS-MOM simple muestra información |
| Ventanas macro, estacionalidad | Descartadas en E2 (C9 de baja prioridad; C12 sin mecanismo) |
| Juicio de un LLM sobre noticias | Solo prospectivo: el modelo conoce el futuro histórico |

---

## 4. Inventario de datos

### 4.1 Datos locales (inspeccionados sin modificar)
| Conjunto | Período | Tamaño | Usado en | ¿Reutilizado? |
|---|---|---|---|---|
| BTCUSDT y ETHUSDT spot 1d (mensual) | 2017-08 → 2026-05 | 106 archivos por activo | T, E2 | Sí |
| BTCUSDT y ETHUSDT spot 1d (diario, `datos_papel`) | 2026-04-20 → 2026-10-16 | 180 archivos por activo | Historia de la señal de T-papel. **Incluye el período reservado de H-CARRY: solo como historia, nunca para evaluar** | Sí (restringido) |
| BTCUSDT spot 1h | 2019-10 → 2026-05 | 80 + 16 archivos | H-CARRY, E1 | Sí |
| BTCUSDT perpetuo: velas, mark, prima (1 h) y funding | 2020-01 → 2026-05 | 77 archivos por serie | H-CARRY, E2 | Sí |
| Funding de ETHUSDT | 2020-01 → 2026-05 | 77 | H-CARRY, E2 | Sí |
| Funding de SOLUSDT | 2020-09 → 2026-05 | 69 | H-CARRY (otros símbolos) | Sí |
| Funding de BTCUSDT (papel) | 2026-07 → 2026-09 | 3 | Monitor del carry | Sí |
| 12 ETF (SPY, EFA, EEM, IWM, TLT, IEF, SHY, LQD, GLD, SLV, USO, DBC), diario más dividendos | ≈ 2010-12 → 2026-10 | 24 + 12 archivos | T-MULTI | Sí |
| DTB3 (Letras del Tesoro de 3 meses) | 2019-12 → 2026-05 | 1 | H-CARRY | Sí |
| Tasas de Aave v3 USDT | — | 1 | H-CARRY (causal) | Sí |
| Vistas de Wikipedia «Bitcoin» | 2015-07 → 2026-05 | 1 | E2-C | Sí |
| `data/fixtures` | — | 4 CSV | **Sintéticos**, sin valor de mercado | — |

**No hay ningún dato local de altcoins** (salvo el funding de SOL). XS-MOM requiere una descarga nueva.

### 4.2 Por hipótesis
| Hipótesis | Disponible | Falta | ¿Ya participó? | Imprescindible | Costo aproximado |
|---|---|---|---|---|---|
| **XS-MOM (candidata 1)** | BTC y ETH 1d | Velas 1d de **todos** los pares USDT de Binance spot que existieron, incluidos los excluidos después; la lista histórica de símbolos | BTC y ETH sí (2 de ~30–100 monedas); **altcoins, nunca** | Confirmar que data.binance.vision **conserva los pares excluidos** (un issue público lo sugiere; sin verificar) y contrastarlo con anuncios oficiales de exclusión | **Gratis.** Estimo 500–700 símbolos, ≈ 30–40 mil archivos con su `.CHECKSUM` y ≈ 100–200 MB [Hip]. Descarga de 1–3 h con pausas; 1 sesión de calidad y 1 de ejecución. Sin dependencias nuevas (numpy del entorno de E1) |
| **Capa de efectivo (candidata 2)** | — | Lo mismo que la candidata 1 | Ídem | Ídem | Costo marginal casi nulo |
| Prima de varianza | Nada | Opciones de BTC (Deribit): historial de precios o de volatilidad implícita, más el índice DVOL | No | Datos históricos de opciones (en general pagos) y un motor con margen | Viabilidad documental: gratis. Datos: pagos (precio a confirmar). Infraestructura: semanas |
| Funding transversal | Funding de BTC, ETH y SOL | Funding de todos los perpetuos USD-M, incluidos los excluidos | BTC, ETH y SOL sí | Supervivencia de los perpetuos excluidos | Gratis, ≈ decenas de MB [Hip] |
| H-E1-BC (rupturas) | BTC 1h | ETH y SOL 1h | BTC sí (origen de la pista) | — | ≈ 150 archivos, ≈ 8 MB |
| Carry transversal | BTC | Funding de todos los perpetuos más el spot | Sí | Decisión de reapertura (cerrado) | — |
| Reversión por liquidaciones | — | Historial de liquidaciones | No | Fuente histórica completa (sin verificar) | Desconocido |

### 4.3 Períodos reservados, fijados antes de cualquier prueba
- **E3:** [2025-01-01, 2026-06-01) para todos los activos. **No se descarga** hasta su apertura única (§2.8), y el código además lo bloquea.
- **H-CARRY:** [2026-06-01, 2026-10-14) **intacto.** E3 no lo usa sin tu autorización.
- **Prospectivo:** desde la autorización en adelante, en papel.
- **Contaminación declarada:**
  - BTC y ETH de 2019 a 2026-05 ya se usaron (T, E2): son 2 monedas del universo;
  - además, conozco a grandes rasgos la historia cripto (qué narrativas subieron y cuándo). Las reglas mecánicas lo mitigan, pero no lo eliminan.

---

## 5. Ranking

| # | Hipótesis | Mecanismo | Horizonte | A favor | En contra | Diferencia con lo existente | Datos | Costos y riesgos | Experimento mínimo que la refuta | ¿Recursos? |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **XS-MOM long-only líquido** | Subreacción y flujos que persiguen rendimientos entre monedas | 1–4 semanas de señal; ≈ 4 semanas de permanencia | LTW (más fuerte en grandes), Zaremba (momentum en líquidas), CTREND (persiste en líquidas y con costos), Swinkels | Supervivencia (Ammann), sobrevivientes sin momentum (Grobys 2026), caídas y dependencia de una moneda (Grobys 2025), débil con costos (Han et al.), decaimiento tras publicación | **Fuente nueva (ii):** qué monedas, no cuándo | Gratis, **nunca vistos** (altcoins) | Lastre de ≈ 4–8 %/año; beta alto; exclusiones del exchange; USDT | IC90 de la correlación de rangos media < 0,01 en U100 durante 2019–2024 | **Sí: prioridad 1** |
| 2 | **Capa de efectivo por momentum absoluto** | Tendencia propia de corto plazo como filtro de riesgo | Semanas | Teoría del momentum dual; [Pub] gestión del riesgo contra las caídas del momentum (Grobys 2025, con volatilidad) | El momentum temporal desapareció tras los futuros (Swinkels); T insuficiente; potencia baja | Responde a «quedarse en efectivo» dentro de la nueva fuente | Igual que la 1 | Retrasos en la reentrada; potencia de ≈ 15–25 %/año | IC90 del exceso de timing < +2 %/año | **Sí (barata), con expectativa baja** |
| 3 | Prima de varianza (venta de volatilidad) | Prima de seguro | Días a semanas (vencimientos) | Prima medida en BTC (Alexander e Imeraj; Almeida et al.) | Sin rentabilidades netas publicadas; colas extremas | **Fuente (iv), la más independiente** | Pagos; infraestructura nueva | Margen; caídas; operación compleja | Prima neta tras costos de cobertura ≤ 0 en un estudio con datos históricos | **Solo un estudio de viabilidad documental** |
| 4 | Funding transversal | Apiñamiento apalancado | 1–4 semanas | Mecanismo (BIS) | Sin estudios; E2 nulo en series | Fuente (iii), transversal | Gratis | Parecer un rescate de una idea fallida | Correlación de rangos ≤ 0 | No ahora; solo si la 1 muestra información |
| 5 | CTREND o aprendizaje automático transversal | Tendencia multihorizonte con volumen | Semanas | JFQA 2025 | Muchos grados de libertad | Igual que la 1 | Igual que la 1 | Sobreajuste | — | No ahora; extensión de la 1 |
| 6 | Momentum temporal multihorizonte o T en altcoins | Tendencia propia | Meses | Moskowitz et al.; Han et al. | Swinkels; T y T-MULTI insuficientes | **Ninguna** (fuente i) | Locales | — | — | No: sigue T-papel |
| 7 | Rupturas (incluida H-E1-BC) | Tendencia | Días | — | E1 en contra; 1 de 4 miradas | Ninguna a escala diaria | ETH y SOL 1h (descarga) | — | Protocolo H-E1-BC | No (pista exploratoria) |
| 8 | Reversión transversal | Provisión de liquidez | Días | Bianchi; Zaremba | Vive en las ilíquidas | Opuesta a la 1 | Igual que la 1 | Costos | — | No |
| 9 | Reversión tras extremos o liquidaciones | Ventas forzadas | Días | Mecanismo | Sin estudios rigurosos; R y E1-MR en contra | Fuente (i) | Faltan las liquidaciones | — | — | No |
| 10 | Carry delta neutral o transversal | Prima de carry | Semanas | Christin et al.; BIS | H-CARRY por debajo del comparador | Fuente (iv) | Locales en parte | Riesgo de base y de exchange | Regla del monitor | Cerrada (monitor) |
| 11 | Funding o prima en series | Apiñamiento | Días a semanas | — | E2 | — | — | — | Ya refutada | No |
| 12 | Tamaño, MAX, valor, listados, stablecoins, sector, macro, estacionalidad | Varios | — | Variable | Supervivencia, contradicciones, datos | — | Varios | — | — | No (§3.8) |

---

## 6. Candidatas elegidas y por qué

1. **XS-MOM (H1 + H2).**
   - Es la única familia que agrega una **fuente de información nueva** con datos **no vistos**, evidencia específica en cripto **justo en el segmento líquido** y una implementación spot simple.
   - Su prueba predictiva tiene **amplitud** (~100 monedas por ~280 semanas), así que es mucho más informativa que cualquier prueba de timing de BTC.
   - Si fracasa, cierra con claridad una vía grande: la selección de altcoins por momentum.
2. **Capa de efectivo (H3).**
   - El costo marginal es casi nulo y responde directamente a tu objetivo de «quedarse en efectivo».
   - Expectativa baja, declarada de antemano.
3. **Sin tercera candidata.**
   - Las alternativas son la misma fuente que T (rupturas, momentum temporal), fuentes ya refutadas (funding en series, atención, reversión de BTC), familias cerradas (carry) o fuentes que requieren infraestructura o datos pagos (prima de varianza, on-chain).
   - Llenar el lugar solo agregaría pruebas múltiples y bajaría la potencia de Holm.

**Qué cambiaría esta recomendación:**
- si la etapa de calidad muestra que data.binance.vision **no** conserva los pares excluidos, la candidata 1 queda **inválida** con esa fuente;
- en ese caso propondría buscar una fuente alternativa con monedas muertas (instantáneas históricas de capitalización), con su costo y sus condiciones de uso evaluados antes.

---

## 7. Largo plazo: elegir entre estrategias o quedarse en efectivo

**Principios** [Hip; ninguno probado]:
1. **Solo entran componentes validados por separado**, cada uno con su prerregistro y su evaluación prospectiva. Hoy **no hay ninguno validado**: T está en papel. Un selector ahora sería prematuro.
2. **Componentes de fuentes distintas** (§1): por ejemplo, T decide **cuánto** mercado tener, XS-MOM **qué** monedas, y una prima (carry o varianza) aporta un retorno neutral al mercado.
3. **Asignación por presupuesto de riesgo fijo**, no por rendimiento reciente. Elegir la estrategia que «viene ganando» es otra estrategia de momentum, con sus propios riesgos de sobreajuste.
4. **El efectivo es el valor por defecto:** se sale de un componente si su regla prerregistrada de detención se activa, como el criterio de 12 meses de T-papel.
5. **El selector mismo se evalúa solo de forma prospectiva.**

---

## 8. Propuesta concreta para la siguiente fase

| Paso | Qué | Requiere |
|---|---|---|
| F0 | Revisás este informe y el borrador `PROTOCOLO_E3_BORRADOR.md` | Tu revisión (y la de ChatGPT) |
| F1 | Congelo el prerregistro con SHA-256 **antes** de cualquier descarga | Tu aprobación del protocolo |
| F2 | Descarga de la lista de símbolos y de las velas 1d de todos los pares USDT spot **hasta 2024-12**, con `.CHECKSUM` | **Autorización de descarga** (gratis; ≈ 100–200 MB [Hip]) |
| F3 | Calidad de datos y **control de supervivencia**: muestra de 10 exclusiones oficiales elegidas al azar antes de mirar precios; universo en el tiempo; semanas con ≥ 30 elegibles. Sin retornos de estrategia | — |
| F4 | Pruebas sintéticas y de invariancia | — |
| F5 | **Ejecución única** del período confirmatorio (H1, H2, H3; Holm m = 3) e informe | — |
| F6 | Apertura única del período reservado E3, solo si F5 da «favorable» o «información sin ventaja» | Tu autorización |
| F7 | Si todo pasa: evaluación prospectiva en papel con reglas congeladas (decisiones a 12 y 24 meses) | Tu autorización |

**Criterios de descarte** (detalle en el protocolo):

| Hipótesis | Se descarta si |
|---|---|
| H1 | IC90 de la correlación de rangos media < 0,01 |
| H2 | No pasa Holm, o pasa pero con costos ×2 queda ≤ 0. Queda como «información sin ventaja operable» si H1 pasa |
| H3 | IC90 del exceso de timing < +2 %/año |
| Validez | El control de supervivencia falla, o más del 20 % de las semanas tiene < 30 elegibles: INVÁLIDO, sin interpretar |

---

## 9. Restricciones respetadas
- **No descargué datos.** Solo leí literatura y documentación en la web.
  - La herramienta de lectura guardó temporalmente un PDF del working paper de LTW para leerlo; es un artículo, no un conjunto de datos.
  - Borro la extracción de texto que hice para leerlo.
- **No instalé dependencias ni ejecuté backtests o experimentos.**
- **No modifiqué** el repositorio, E1, E2, T, T-MULTI ni sus artefactos (lo verifico al cerrar).
- **No hice commits, pushes, merges, rebases, cherry-picks ni deploys.** No operé.
- **No amplío el alcance después de este ranking sin tu autorización.**

---

## Fuentes consultadas
- Liu, Tsyvinski y Wu, *Common Risk Factors in Cryptocurrency* (NBER WP 25882): https://www.nber.org/papers/w25882.pdf
- Ammann, Burdorf, Liebi y Stöckl, *Survivorship and Delisting Bias in Cryptocurrency Markets*: https://alexandria.unisg.ch/handle/20.500.14171/108037
- Grobys, Sandretto y Äijö, *On survivor cryptocurrency momentum* (FRL 2026): https://osuva.uwasa.fi/handle/11111/20040
- Grobys y Sapkota, *Cryptocurrencies and momentum* (Economics Letters 2019): https://osuva.uwasa.fi/handle/11111/2278
- Grobys, Kolari et al., *Cryptocurrency momentum has (not) its moments* (FMPM 2025): https://osuva.uwasa.fi/handle/10024/20018
- Dobrynskaya, nota de HSE: https://www.hse.ru/en/news/research/559533243.html
- Han, Kang y Ryu, *Time Series and Cross Sectional Momentum in the Cryptocurrency Market*: https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/Time_Series_and_Cross_Sectional_Momentum_in_the_Cryptocurrency_Market_with_IA.pdf
- Fieberg et al., *A Trend Factor for the Cross Section of Cryptocurrency Returns* (JFQA 2025): https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/trend-factor-for-the-cross-section-of-cryptocurrency-returns/4C1509ACBA33D5DCAF0AC24379148178
- Fieberg et al., *Cryptocurrency Factor Momentum* (QF 2023): https://ideas.repec.org/a/taf/quantf/v23y2023i12p1853-1869.html
- Zaremba et al., *Up or down? Short-term reversal, momentum, and liquidity effects in cryptocurrency markets* (IRFA 2021): https://ideas.repec.org/a/eee/finana/v78y2021ics1057521921002349.html
- Bianchi, Babiak y Dickerson, *Trading volume and liquidity provision in cryptocurrency markets* (JBF 2022): https://www.riksbank.se/globalassets/media/rapporter/working-papers/2022/no.-413-trading-volume-and-liquidity-provision-in-cryptocurreny-markets.pdf
- Mercik et al., *Cross-sectional interactions in cryptocurrency returns* (IRFA 2025): https://open.icm.edu.pl/handle/123456789/25545
- Swinkels (2018), resumen de seminario: https://utilities.tinbergen.nl/?p=66235
- Alexander e Imeraj, *The Bitcoin VIX and its variance risk premium*: https://sro.sussex.ac.uk/id/eprint/91094/
- Almeida et al., *Risk Premia in the Bitcoin Market*: https://arxiv.org/html/2410.15195v2
- Christin et al., *The Crypto Carry Trade*: https://www.andrew.cmu.edu/user/azj/files/CarryTrade.v1.0.pdf
- BIS WP 1087, *Crypto carry*: https://www.bis.org/publ/work1087.htm
- He, Manela, Ross y von Wachter, *Fundamentals of Perpetual Futures*: https://arxiv.org/pdf/2212.06888v3
- Özdamar, Akdeniz y Şensoy (MAX): https://repository.bilkent.edu.tr/items/78167f5c-d3e2-4f07-b4bc-5e8a3ed0b2c0
- Yadav (2025, MAX horario): https://ideas.repec.org/a/eme/sefpps/sef-07-2024-0461.html
- Lyons y Viswanath-Natraj (VoxEU, stablecoins): https://cepr.org/voxeu/columns/stable-coins-dont-inflate-crypto-markets
- Wei (Tether; vía Bitcoin Magazine): https://bitcoinmagazine.com/markets/new-study-argues-tether-wasnt-used-prop-bitcoin-price
- Listados [Ind]: https://www.thetie.io/insights/what-does-an-exchange-listing-actually-deliver-in-2026 · https://rockawayx.com/insights/bullish-or-bearish-what-really-happens-when-tokens-list-on-a-cex · https://www.blockchainresearchlab.org/?p=3721
- Comisiones (Binance.US; las de Binance global hay que confirmarlas): https://support.binance.us/en/articles/9843536-binance-us-launches-trading-fee-discount-and-vip-program-with-bnb
- Binance public data: https://github.com/binance/binance-public-data/ · issues sobre pares excluidos: https://github.com/binance/binance-public-data/issues?q=delisted
- ABFER 2026, *Predictive crypto crashes*: https://abfer.org/component/edocman/main-annual-conference/predictive-crypto-crashes-and-asset-pricing-implications-an-inelastic-market-perspective
