# Borrador de prerregistro E3: momentum transversal long-only y capa de efectivo (NO EJECUTAR)

**Estado:**
- Es un borrador para revisión. No se descargó nada y no se escribió código de evaluación.
- Se convierte en prerregistro solo con tu aprobación: fijo su SHA-256 **antes** de bajar el primer archivo de altcoins.
- Los cambios que surjan de la revisión se hacen **antes** de congelarlo. Después, solo adendas documentadas que no dependan de resultados.

## 0. Reglas comunes
- **Una sola ejecución confirmatoria.** Si un control de validez falla, se detiene **antes** de interpretar y se documenta.
- **Etapas separadas por código:**
  1. **calidad de datos:** el código de esta etapa no tiene acceso a funciones de retorno de estrategia;
  2. **pruebas sintéticas;**
  3. **ejecución confirmatoria;**
  4. **período reservado.**
- **Disponibilidad en el tiempo:**
  - la formación es el **lunes 00:00 UTC** con datos hasta el cierre del domingo (la vela diaria que termina el domingo a las 23:59:59.999);
  - la ejecución es en la **apertura oficial del lunes** (vela 1d que empieza el lunes 00:00).
  - Nada calculado en t usa velas posteriores al cierre del domingo.
- **Pruebas múltiples:**
  - **Holm al 5 % sobre H1, H2 y H3** (m = 3);
  - una hipótesis declarada inválida o inconclusa entra con p = 1.
- **Información frente a rentabilidad:** H1 es **predictiva** (sin costos). H2 y H3 son **operables** (con costos).

## 1. Datos
- **Fuente:** data.binance.vision, klines **1d mensuales** de **spot**, todos los símbolos con cotización **USDT**, cada archivo verificado contra su `.CHECKSUM` oficial.
- **Lista de símbolos:** sale del listado de prefijos del bucket (`data/spot/monthly/klines/`). Se guarda cruda, con su SHA-256 y su fecha.
- **Rango de descarga en F2:** desde el primer mes disponible hasta **2024-12**.
  - El período reservado (2025-01 → 2026-05) **no se descarga** hasta F6: así es físicamente imposible mirarlo.
- **Reutilizados:** BTCUSDT y ETHUSDT ya se usaron en T y E2; se marcan como tales. Todas las demás monedas son nuevas para el proyecto.
- **Renombres y redenominaciones:**
  - en F3 (antes de cualquier retorno de estrategia) se arma un mapa a partir de los **anuncios oficiales de Binance**;
  - un renombre mapeado conserva la edad y la posición, con el factor de conversión anunciado;
  - si no se puede mapear con un anuncio, se trata como exclusión más listado nuevo, y se informa cuántos casos hay.
- **Exclusión de un par:** la posición sale al **último cierre disponible**. Estrés: −30 % adicional en esa salida.
- **Huecos:**
  - durante la tenencia, la posición se valúa al último cierre y la operación se pospone hasta que haya precio;
  - una moneda con huecos en su ventana de formación no es elegible esa semana.

## 2. Universo en cada formación t (solo con datos ≤ t)
- **Elegible** si cumple todo lo siguiente:
  1. par USDT cotizando en t;
  2. ≥ 180 días desde su primera vela diaria (o la de su predecesor mapeado);
  3. sin huecos en los últimos 28 días;
  4. mediana de 30 días del volumen diario en USDT (`quote_asset_volume`) ≥ 1 000 000;
  5. no está en ninguna exclusión.
- **Exclusiones:**
  - **Stablecoins, fiat y tokens respaldados por materias primas:** lista base fijada ahora (USDC, BUSD, TUSD, USDP/PAX, DAI, FDUSD, USDS, USDSB, UST, SUSD, PAXG, EUR, GBP, AUD, BRL, RUB, TRY, NGN, UAH, BIDR, IDRT, BVND, ZAR, AEUR, EURI, USD1, más cualquier ticker de moneda fiat ISO-4217), más una **regla automática**: volatilidad anual de 90 días < 10 %.
  - **Tokens apalancados:** base = X + {UP, DOWN, BULL, BEAR}, donde X es otra base listada con su propio par USDT. La lista resultante se congela en F3, antes de mirar precios.
  - **Duplicados** (envueltos, en staking o redenominados): si la correlación de 90 días de los retornos diarios con otra moneda elegible y **más líquida** es > 0,98, queda solo la más líquida.
- **U100:** top 100 elegibles por la mediana de volumen (o todas, si hay menos).
- **U30:** top 30 elegibles.
- **Semana evaluable:** ≥ 30 elegibles. Las demás no entran en ninguna prueba y se cuentan.

## 3. Señal
- Para cada moneda elegible, retornos logarítmicos hasta el cierre del domingo con h ∈ {7, 14, 21, 28} días: R_h = ln(C_t / C_{t−h}).
- En cada universo (U100 para H1; U30 para H2 y H3), se toma el **rango percentil transversal** de cada R_h. La **señal S** es la **media de los 4 rangos**.
- **Momentum absoluto** (solo H3): A = media(R_7, R_14, R_21, R_28).

## 4. H1: información predictiva (U100)
- **Hipótesis:** la señal S ordena positivamente el retorno de la semana siguiente.
- **Retorno adelantado:** ln(O_{lunes siguiente} / O_{lunes}).
  - Si la moneda deja de cotizar en la semana, se usa hasta su último cierre, con el estrés aplicado solo en H2 y H3.
- **Estadístico:** IC_t = Spearman(S, retorno adelantado) entre las elegibles de U100. IC = media de los IC_t de las semanas evaluables confirmatorias.
- **Inferencia:** error de Newey–West con 4 rezagos; **p₁ unilateral** (IC > 0). Se informan también el IC90, el número de semanas y la media de monedas por semana.

## 5. H2: ventaja neta de la cartera long-only (U30)
- **Cartera:**
  - **6 lugares**;
  - se mantienen las que siguen elegibles y en U30 con rango ≤ 12;
  - los lugares libres se llenan con los mejores rangos no tenidos;
  - 1/6 por lugar al entrar; sin rebalanceo de los que se quedan, salvo que su peso salga de [1/12, 1/3] (entonces vuelve a 1/6).
- **Costos por lado sobre el valor negociado:**
  - comisión de 10 pb;
  - spread y slippage por rango de liquidez en el momento de operar: rangos 1–2: 5 pb; 3–10: 10 pb; 11–30: 20 pb;
  - estrés ×2 sobre el costo total.
- **Referencia principal (EW-U30):** las 30 de U30 con 1/30 cada una, rebalanceo semanal en la misma apertura y **los mismos costos**.
- **Métrica:** exceso semanal = retorno neto de la cartera − retorno neto de EW-U30. Se anualiza × 52.
- **Inferencia:** bootstrap circular por bloques de **13 semanas**, 10 000 réplicas, semilla 20261019.
  - P = fracción de medias > 0;
  - **p₂ = 1 − P**;
  - IC90 por percentiles 5–95.

## 6. H3: valor de la capa de efectivo
- **Variante con efectivo:** igual que la cartera de H2, pero un lugar solo se ocupa con una moneda cuyo **A > 0**.
  - Si la moneda pierde esa condición, sale a efectivo (USDT, 0 %).
  - Si ninguna cumple, la cartera queda 100 % en efectivo.
  - Mismos costos.
- **Referencia:** la cartera de H2 (neta), escalada a la **exposición media** de la variante con efectivo, con rebalanceo diario y sin costos adicionales.
- **Métrica:** exceso semanal de timing, anualizado × 52.
- **Inferencia:** como en H2, con **p₃ = 1 − P**.

## 7. Clasificación (fijada ahora)

**Candidata 1 (H1 y H2):**

| Clasificación | Condición |
|---|---|
| **INVÁLIDO** | Falla un control de validez (§9). No se interpreta |
| **VENTAJA NETA HISTÓRICA RESPALDADA** | H1 y H2 rechazan con Holm, **y además**: exceso con costos ×2 > 0; IC > 0 en al menos 2 de 3 tercios del período; p del nulo aleatorio ≤ 0,05 (6 monedas al azar de U30, misma mecánica, 2000 réplicas); sin la moneda que más aporta al exceso acumulado, el exceso sigue > 0 |
| **INFORMACIÓN SIN VENTAJA OPERABLE** | H1 rechaza con Holm y no se cumple la fila anterior |
| **EN CONTRA** | Límite superior del IC90 de IC < 0,01 (sin información económicamente relevante) |
| **INSUFICIENTE** | Cualquier otro caso |

**Candidata 2 (H3):**

| Clasificación | Condición |
|---|---|
| **FAVORABLE** | H3 rechaza con Holm, el exceso de timing con costos ×2 es > 0 y la caída máxima de la variante con efectivo es menor que la de la totalmente invertida |
| **EN CONTRA** | Límite superior del IC90 del exceso de timing < +2 %/año |
| **INSUFICIENTE** | Cualquier otro caso |

**Ninguna clasificación autoriza capital.** Lo máximo es «respaldada históricamente». Después siguen el período reservado y la evaluación en papel.

## 8. Descriptivos y sensibilidad (sin decisiones)
- **Para la cartera, la variante con efectivo, EW-U30, BTC buy and hold y el efectivo:**
  - CAGR, volatilidad, Sharpe (con su versión deflactada) y Sortino;
  - caída máxima, CVaR del 5 % semanal, peor semana y tiempo bajo el agua;
  - beta frente a BTC.
- **Operación:**
  - rotación, costos totales y costo de equilibrio (el multiplicador que deja el exceso en 0);
  - permanencia media y cambios por año;
  - exposición media de la variante con efectivo.
- **Independencia:** correlación del componente de selección (cartera − EW-U30) con BTC y con el exceso de timing de T (T_BTC y T_ETH, reglas congeladas).
- **Concentración:** aporte de cada moneda al exceso acumulado.
- **Sensibilidad, después del resultado principal y sin elegir nada:**
  - k ∈ {4, 6, 10};
  - N ∈ {20, 30, 50};
  - cada horizonte h por separado;
  - sin banda;
  - semana formada el miércoles.
- **Control de costos:** el spread estimado con Abdi–Ranaldo por tramo, comparado con los supuestos.

## 9. Validez (antes de interpretar; si falla, se detiene)
1. **Checksums:** todos los archivos verificados; 0 discrepancias.
2. **Supervivencia:**
   - antes de mirar precios, se eligen al azar (semilla fija) 10 anuncios oficiales de exclusión de pares USDT spot de 2019–2024;
   - **al menos 9 de 10** deben tener datos hasta 3 días antes, o menos, de la fecha anunciada;
   - si no, la prueba es **INVÁLIDA** con esta fuente.
3. **Universo:** a lo sumo 20 % de semanas no evaluables dentro del período confirmatorio. Si no, INVÁLIDO.
4. **Reglas de exclusión congeladas en F3:** listas de apalancados, duplicados y renombres guardadas con hash antes de calcular retornos.
5. **Sin mirada al futuro:** comprobaciones automáticas en la formación y la ejecución; invariancia al truncar en 5 cortes al azar (señales, universos y pesos idénticos hasta cada corte).
6. **Pruebas sintéticas:**
   - con un nulo verdadero, el rechazo de H1 debe ser ≤ 7 % en 500 simulaciones;
   - con un IC plantado de 0,05, la detección debe ser ≥ 80 %;
   - el bootstrap debe estar calibrado bajo el nulo.
7. **Bloqueo del reservado:** una prueba demuestra que leer cualquier fecha ≥ 2025-01-01 falla en modo confirmatorio.

## 10. Períodos
- **Confirmatorio:** desde el primer lunes con semana evaluable, determinado en F3 solo con datos de calidad, hasta el último lunes cuyo retorno adelantado termina antes del 2025-01-01.
- **Reservado E3:** [2025-01-01, 2026-06-01). Se descarga y se abre **una sola vez**, con el mismo código, y **solo** si la candidata 1 da «respaldada» o «información sin ventaja».
  - **CONSISTENTE:** IC medio > 0 y exceso de H2 > 0 (estimaciones puntuales).
  - **CONTRADICE:** límite superior del IC90 de IC < 0.
  - **NO CONCLUYENTE:** cualquier otro caso.
  - Si la candidata 1 falla, el reservado queda **intacto** para hipótesis futuras.
- **Reservado de H-CARRY** [2026-06-01, 2026-10-14): no se usa.
- **Prospectivo (papel):** reglas congeladas desde la autorización; cortes a los 12 y 24 meses, como en T-papel.

## 11. Potencia [Hip]
| Prueba | Supuestos | Efecto mínimo detectable (80 %) |
|---|---|---|
| H1 | Desvío de IC_t ≈ 0,12–0,15; ≈ 260–300 semanas | IC ≈ 0,025–0,03 (≈ 15–20 %/año bruto en el top 6) |
| H2 | Tracking error ≈ 25–35 %/año; ≈ 5–5,5 años | ≈ 35–45 %/año |
| H3 | Como E2-B | ≈ 15–25 %/año |

Lo esperable es que H2 y H3 terminen INSUFICIENTES aunque haya algo real. H1 es la prueba que puede informar.

## 12. Fuera de alcance
- Cortos y perpetuos.
- Otros exchanges.
- Aprendizaje automático o CTREND.
- Funding transversal.
- Tamaño.
- Otras k, N u horizontes (salvo como descriptivo, §8).
- Intradía.
- Cualquier otra familia.

## 13. Autorizaciones que requiere
1. **Aprobar y congelar este protocolo**, con los cambios que salgan de la revisión.
2. **Descarga en F2:** el listado de prefijos del bucket spot de klines y las klines 1d mensuales con `.CHECKSUM` de todos los pares USDT, del primer mes disponible a 2024-12. Gratis; ≈ 100–200 MB [Hip].
3. **Lectura de anuncios oficiales de Binance** (exclusiones y renombres). Es documentación, no datos de precios.
4. **Después y por separado:** descarga y apertura del reservado (F6) y evaluación en papel (F7).
