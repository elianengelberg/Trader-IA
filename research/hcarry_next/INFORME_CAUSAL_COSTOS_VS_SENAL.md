# H-CARRY: ¿falló la estrategia o la destruyeron los costes? (2026-10-17)

**Categoría:** EXPLORATORIO POSTERIOR AL TEST. Reconstruye y descompone lo que ya ocurrió. No es evidencia independiente ni sirve para elegir parámetros. El test prerregistrado se ejecutó una vez (2026-10-16 20:47 UTC) y no se repitió.
- **Fuente de las cifras:** `experimentos/historico/causal/causal.json` y `cascada_deficit.json`.
- **Huellas:** código `9d11ecbe…`, datos `8bdabde7…`.

## 0. Respuesta directa
**Los costes solo agravaron una estrategia que ya era insuficiente. No destruyeron una ventaja.**

- En **validación y test (2023-01 → 2026-05)**, rev. 5 sin ningún coste de ejecución (escenario C) habría rendido un **4,40 %** y un **3,95 %** anual. Queda por debajo de la letra del Tesoro (5,21 % y 4,42 %), del USDT en Aave (4,43 % y 4,84 %) y del 5 % exigido.
  - Los costes restaron solo **0,19–0,36 pp/año**.
  - Con costes favorables (descuento BNB y 1 bp de slippage), la mejora es de +0,08 a +0,16 pp: no cambia nada.
- En **desarrollo (2020–2022)** sí había una ventaja clara frente al efectivo: 9,48 % neto, frente a un T-bill del 0,81 %. Los costes no la destruyeron: restaron 0,38 pp.
- **Lo que decide el resultado** es el nivel del funding (mercado) combinado con la estructura de dos cuentas: alrededor del 47 % del capital queda inmovilizado como patrimonio de futuros, sin rendimiento.

**Confianza:**
- **Alta** en que los costes no son la causa. La conclusión resiste costes de ×0,5 a ×3, un escenario favorable y uno adverso, en las tres divisiones.
- **Media** en el reparto entre mercado y estructura. El contrafactual de «todo el capital como nocional» no es operable sin cambiar el riesgo, y solo hay una ventana reciente.

## 1. Escenarios (cada uno es una simulación completa: mismos datos, motor y políticas; solo cambian los costes)

| Escenario | Definición exacta | Para qué sirve |
|---|---|---|
| **A · Bruto teórico** | Solo el funding neto devengado en C, en pp/año del capital inicial. Sin patas de precio ni costes. | Tamaño de la fuente de ingresos |
| **B · Sin comisiones** | Comisión 0 en ambas patas; slippage de 5 bps por pata. Conserva funding y patas. | Peso de las comisiones |
| **C · Sin costes de ejecución** | Comisión y slippage 0; conserva funding y PnL de las patas. | Techo diagnóstico: no es operable |
| **D · Realista neto** | Costes prerregistrados: spot 10 + 5 bps; perpetuo 5 + 5 bps. Es lo que se informó. | Referencia |
| Costes favorables | Spot 7,5 + 1 bps; perpetuo 4,5 + 1 bps (supuesto, no verificado) | Sensibilidad |
| Costes adversos | Slippage de 15 bps por pata | Sensibilidad |
| **E · Capital alternativo** | Efectivo al 0 % (supuesto del motor). Letra del Tesoro a 3 meses (FRED DTB3). USDT en Aave v3 (DefiLlama; desde 2023-02). **Se presentan por separado.** | Coste de oportunidad |

**Sobre el escenario E.** La letra del Tesoro **no** es accesible para USDT depositado en un exchange: exige salir a dólares bancarios, con otra custodia, moneda y plazo. Aave rinde en DeFi, con riesgo de contrato inteligente, de despegue de la stablecoin y costes de gas; no está verificado on-chain. Binance Simple Earn no publica un historial verificable sin credenciales, así que **no se usa**. Para 2020–2022 no hay ninguna serie de stablecoin verificable.

**Spread:** no se mide. Queda incluido en el slippage de 5 bps por pata. En BTCUSDT el spread típico es de una fracción de bp, pero sin libro histórico es una **estimación**; los rangos están en los escenarios favorable y adverso.

## 2. Resultados por escenario (CAGR neto, capital de 10 000 USDT)

| División | Política | A (pp/año) | B | C | **D** | Favorables | Adversos | Efectivo 0 % | T-bill 3M | Aave USDT | Exigido |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Desarrollo 2020–22 | rev. 5 | 10,92 | 9,69 % | 9,85 % | **9,48 %** | 9,63 % | 9,18 % | 0 | 0,81 % | n/d | 5 % |
| | umbral | 9,88 | 8,61 % | 9,07 % | **7,95 %** | 8,43 % | 7,04 % | | | | |
| Validación 2023-01 → 2024-01 | rev. 5 | 4,40 | 4,25 % | 4,40 % | **4,04 %** | 4,20 % | 3,73 % | 0 | 5,21 % | 4,43 % (89 % de cobertura) | 5 % |
| | umbral | 3,54 | 3,28 % | 3,59 % | **2,80 %** | 3,16 % | 2,17 % | | | | |
| **Test 2024-02 → 2026-05** | **rev. 5** | 4,07 | 3,87 % | 3,95 % | **3,76 %** | 3,84 % | 3,62 % | 0 | **4,42 %** | **4,84 %** | 5 % |
| | **umbral** | 3,09 | 2,89 % | 3,04 % | **2,68 %** | 2,83 % | 2,39 % | | | | |
| Completo 2020–26 | rev. 5 | 8,08 | 6,60 % | 6,71 % | **6,47 %** | 6,57 % | 6,29 % | 0 | 2,85 % | 4,72 % (51 %) | 5 % |
| | umbral | 6,74 | 5,55 % | 5,85 % | **5,11 %** | 5,43 % | 4,51 % | | | | |

**Contraste con lo informado:** el escenario D del test reproduce **exactamente** el PnL archivado (rev. 5: 899,475; umbral: 635,131).

## 3. Descomposición contable exacta del escenario D (conciliación independiente; identidad verificada)

Identidad: PnL neto = PnL spot + PnL perpetuo + funding neto − costes. Error < 10⁻⁶ del capital en todos los casos.

| Test 2024-02 → 2026-05 (USDT) | rev. 5 | umbral |
|---|---|---|
| PnL pata spot | +3 759,9 | +4 280,4 |
| PnL pata perpetua | −3 764,1 | −4 279,1 |
| **Patas netas (cobertura)** | **−4,2** | **+1,3** |
| Funding cobrado / pagado | 1 021,7 / 72,9 | 726,5 / 5,4 |
| **Funding neto** | **+948,9** | **+721,1** |
| Comisión spot / perpetuo | 18,1 / 9,0 | 34,9 / 17,4 |
| Slippage spot / perpetuo | 9,0 / 9,0 | 17,4 / 17,4 |
| **Costes totales** | **45,2** (0,19 pp/año) | **87,2** (0,37 pp/año) |
| Turnover spot / perpetuo | 18 063 / 18 061 | 34 895 / 34 886 |
| Costes / turnover | 12,5 bps | 12,5 bps |
| **PnL neto** | **+899,5** (3,86 pp/año simple; CAGR 3,76 %) | **+635,1** (2,72 pp; 2,68 %) |

- **Tarifas aplicadas:** a cada ejecución y sobre su nocional; 15 bps en spot (10 de comisión y 5 de slippage) y 10 bps en el perpetuo (5 y 5).
- **Transferencias entre cuentas:** gratuitas.
- **No hay más costes registrados:** ni intereses, ni retiros, ni gas.
- **Desarrollo y período completo:** en `causal.json`. Mismo patrón: rev. 5 paga 113 USDT en costes en 2020–22 frente a 354 de umbral.

**Uso del capital** (media horaria; capital = equity del momento):

| | BTC spot (cubierto) | Patrimonio de futuros (garantía) | USDT ocioso | Nocional / capital inicial |
|---|---|---|---|---|
| rev. 5, test | 52,9 % | **47,1 %** | 0 % | 0,56 |
| umbral, test | 24,4 % | 21,9 % | **53,7 %** | 0,55 mientras tiene posición |

En los dos casos, cerca de la mitad del capital no gana funding y el motor lo remunera al 0 %.

## 4. Cascada del déficit frente al 5 % (identidad exacta, en pp/año simples sobre el capital inicial)

`5 − R = (5 − APR) + APR·(1 − n) + K − P`
- **R:** rentabilidad neta.
- **APR:** funding anual efectivo sobre el nocional.
- **n:** nocional / capital inicial.
- **K:** costes.
- **P:** patas netas.
- **(5 − APR):** el mercado frente al objetivo si todo el capital fuera nocional.
- **APR·(1 − n):** el funding que no se gana por la estructura.

| División | Política | R | APR del funding | n | **Déficit** | Mercado | Estructura | Costes | Patas | APR necesario para el 5 % |
|---|---|---|---|---|---|---|---|---|---|---|
| Desarrollo | rev. 5 | 10,41 | 17,5 % | 0,63 | **−5,41** (excedente) | −12,48 | +6,55 | +0,38 | +0,14 | 8,8 % |
| Validación | rev. 5 | 4,05 | 8,6 % | 0,51 | **+0,95** | −3,58 | +4,18 | +0,36 | −0,01 | 10,4 % |
| **Test** | **rev. 5** | 3,86 | **7,2 %** | 0,56 | **+1,14** | −2,24 | **+3,17** | +0,19 | +0,02 | **9,3 %** |
| Test | umbral | 2,72 | 5,6 % | 0,55 | **+2,28** | −0,63 | +2,54 | +0,37 | −0,01 | 9,8 % |

**Lectura:** el funding de 2024–26 (7,2 %) habría superado el 5 % si todo el capital ganara funding. La estructura ρ = 1 deja casi la mitad como garantía, y por eso hace falta un funding de ≈ 9,3 %. Los costes explican el 17 % del déficit de rev. 5 en test (0,19 de 1,14 pp) y el 38 % en validación. **Es una identidad contable, no una asignación causal única.** El término de estructura supone desplegar todo el capital, lo que en esta estructura no es posible sin más apalancamiento o colateral spot.

## 5. Por año y por régimen (PnL del escenario D en USDT; toda la muestra; régimen EX ANTE según la rentabilidad del BTC en los 30 días previos)

| | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 (ene–may) |
|---|---|---|---|---|---|---|---|
| rev. 5 | +896 | **+1 972** | +271 | +565 | +882 | +367 | **+22** |
| umbral | +828 | +1 793 | **−41** | +309 | +734 | +145 | 0 |

| Régimen ex ante | Alcista (> +10 %) | Lateral | Bajista (< −10 %) | Sin historia |
|---|---|---|---|---|
| rev. 5 | +3 160 (64 %) | +1 526 | +203 | +87 |
| umbral | +2 790 | +846 | +59 | +73 |

Ningún año fue negativo para rev. 5. El carry es un ingreso de mercados alcistas: dos tercios del PnL llegan con el BTC subiendo más de un 10 % mensual.

## 6. Contrafactuales (preguntas 1 a 7)

| # | Pregunta | Respuesta (test; validación entre paréntesis) |
|---|---|---|
| 1 | ¿Ganancia antes de costes? | **Sí.** C = +3,95 % (+4,40 %); también en todos los años. |
| 2 | ¿Superaba el benchmark sin comisiones? | **No.** B = 3,87 % (4,25 %), por debajo del T-bill (4,42 %; 5,21 %), de Aave (4,84 %; 4,43 %) y del 5 %. |
| 3 | ¿Sin ningún coste de ejecución? | **No.** C = 3,95 % (4,40 %), aún por debajo de los tres benchmarks. |
| 4 | ¿Qué hacía falta? | +1,24 pp de CAGR en test, es decir, un funding de ≈ 9,3 % anual sobre el nocional (se cobró 7,2 %). En validación, ≈ 10,4 % (se cobró 8,6 %). |
| 5 | ¿De dónde sale el déficit? | Costes, 0,19 pp, de los cuales 0,12 son comisiones. Estructura (capital como garantía no remunerada), 3,17 pp. Mercado a favor, −2,24 pp. Patas, 0,02 pp. |
| 6 | ¿Pérdida absoluta o rendimiento relativo inferior? | **Rendimiento inferior a la alternativa, no pérdida.** rev. 5 ganó en todos los años; umbral perdió solo en 2022 (−41 USDT). |
| 7 | ¿Cambia con otros costes? | **No.** Favorables, +0,08 pp; adversos, −0,14 pp; ×3, −0,40 pp. Ningún supuesto razonable lleva rev. 5 por encima del T-bill o de Aave en test. |

## 7. ¿Falló la hipótesis o su implementación?

| Posible fallo | Evidencia | Veredicto |
|---|---|---|
| **De señal / mercado** | El funding bruto disponible cayó del 17,3 % (2020–22) al 7,0 % (test) y al 0,9 % en 2026, también en ETH y SOL. Bajo esta estructura, A < T-bill en test (4,07 frente a 4,42). | **Sí, a partir de 2023:** la oportunidad bruta no alcanzó. |
| **De diseño** | rev. 5: la estructura ρ = 1 limita el nocional a ≈ 0,53 del equity (§3–4). UmbralFunding: sale a efectivo al 0 % cuando el funding sigue positivo (§8). | **Sí.** En rev. 5 la estructura es el mayor término; en umbral, las salidas sin valor. |
| **De ejecución / costes** | 0,19–0,38 pp/año (rev. 5) y 0,37–1,18 pp (umbral). C sigue por debajo de los benchmarks. | **No es la causa.** Agrava; en umbral, bastante más. |
| **De asignación de capital** | ≈ 47 % del capital como garantía no remunerada (rev. 5) y ≈ 54 % en USDT ocioso (umbral). El objetivo del 5 % es ≈ el rendimiento accesible del efectivo. | **Sí.** No compensa el coste de oportunidad desde 2023. |

**Qué no se puede identificar:** si la compresión del funding es permanente o cíclica. Hay 6,4 años de datos y un solo ciclo completo.

## 8. Por qué UmbralFunding perdió frente a rev. 5 (test: −264,3 USDT = funding −227,8 − costes 42,0 + patas 5,5)

| Pregunta | Cifra (test; validación) | Lectura |
|---|---|---|
| ¿Entraba tarde? | Funding perdido en los 7 días antes de volver a entrar: 30 USDT (22) | Explica ≈ 16 % de lo perdido estando fuera. Secundario. |
| ¿Salía tarde? | Funding negativo pagado estando dentro: 5 USDT (3) | **No.** |
| ¿Salía cuando no hacía falta? | **4 de 4 tramos fuera tuvieron funding neto positivo** (3 de 3); se perdieron 194 (99) | **Causa principal:** sale con funding bajo pero positivo y el efectivo rinde 0 %. |
| ¿Turnover y comisiones? | Costes extra: 42 (45) | ≈ 16 % de la diferencia. |
| ¿Poca capacidad predictiva? | Correlación entre la media de 21 eventos y la siguiente: **0,80** (0,72) | **No:** la señal predice bien el funding. Pero tras la zona de salida (< 3 %), el funding siguiente fue **+0,5 %** (+3,3 %): positivo, así que salir no evita nada. |
| ¿Dependía de pocos episodios? | 3 tramos = 99,7 % del funding perdido (100 %) | Sí: pocos episodios largos. |
| ¿Umbral o hipótesis? | Techo con oráculo de cualquier regla de salida frente a rev. 5: **0,00 pp/año** en validación y test | **La hipótesis general**, no el umbral. Con efectivo al 0 %, ninguna regla de salida puede ganar. |

**Hipótesis distinta para el futuro (no probada; no se usa el test consumido):** «salir solo cuando el funding esperado sea menor que el rendimiento *accesible* del efectivo». Exploratoriamente, su techo con oráculo es de 0,4–1,0 pp/año (`post_test/efectivo_remunerado.json`). Requeriría una serie verificable de ese rendimiento y una prueba prospectiva.

## 9. Limitaciones
- Una sola ventana reciente (28 meses) y una sola de validación.
- Spread y slippage supuestos, sin libro de órdenes.
- Rendimientos alternativos imperfectos: el T-bill no es accesible para USDT en un exchange; Aave tiene otros riesgos y empieza en 2023-02; para 2020–22 no hay serie de stablecoin.
- Sin riesgo de contraparte, ADL ni liquidación dentro de la hora.
- Motor reconstruido, no el código congelado de rev. 5.
- **Discrepancias con informes anteriores:** ninguna material.
  - El «funding necesario ≈ 9,2 %» de `INFORME_ECONOMICO_HISTORICO.md` coincide con el 9,3 % de aquí. La diferencia es el método: allí, el nocional por evento; aquí, la identidad contable sobre el capital inicial.
  - El «nocional 0,51–0,63» coincide.

## 10. Reproducir
```
cd research/hcarry_next && export PYTHONPATH=src
.venv/bin/python -B experimentos/historico/causal_costos_vs_senal.py      # escribe causal/causal.json (≈ 20 s)
```
- **Entradas:** `datos/binance_vision` (manifiesto `8bdabde7…`), `post_test/externos/DTB3.csv` (`f9526199…`) y `causal/externos/aave_v3_usdt_ethereum.json` (procedencia en `PROCEDENCIA.json`).
- **Cascada:** la escribe el mismo script en `causal/cascada_deficit.json`, con el error de la identidad (< 10⁻¹³).
- El script exige que el test ya esté consumido.
