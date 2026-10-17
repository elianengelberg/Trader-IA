# H-CARRY: señal, ejecución y asignación de capital por separado (2026-10-17)

**Fuentes:**
- desarrollo: `experimentos/historico/desarrollo/`, histórico antes del test;
- validación y test: `causal/` y `post_test/`, exploratorio posterior al test;
- cifras del test prerregistrado: `resultados/historico/`.

## A. Señal

| Pregunta | Evidencia | Respuesta |
|---|---|---|
| ¿Hay ventaja estadística antes de costes? | El funding es una renta predecible: positivo en el 85 % de los eventos de 2020–22, con APR del 17 %. El carry bruto (escenario C) gana en todos los años. | **Sí como renta absoluta**, pero no frente al efectivo desde 2023: C < T-bill en validación y test. |
| ¿Persiste fuera de muestra? | Persistencia: correlación semanal de 0,72 (desarrollo), 0,72 (validación) y 0,80 (test). El **nivel** del funding no persiste: 17 % → 7 % → 0,9 %. | La persistencia de corto plazo sí; el nivel, no. |
| ¿Qué aporta información incremental? | Ex ante y solo en desarrollo: el funding de los 7 días previos predice el siguiente (0,71). La tendencia de 30 días también (0,52), pero sobre todo a través del propio funding. Volatilidad y volumen: \|corr\| < 0,05. | **El funding reciente.** La tendencia apenas suma; volatilidad y volumen, nada. |
| ¿Qué parece explicativo pero no predice retornos? | La base F/S se correlaciona 0,85 con el funding del mismo día (es casi su definición), pero no añade nada sobre el funding pasado. La persistencia predice el funding, no el **beneficio de salir**: tras la zona de salida, el funding siguiente sigue positivo (+0,5 % en test, +3,3 % en validación). | Predecir el funding ≠ predecir el valor de la decisión. El techo con oráculo de las salidas es de 0–0,17 pp/año. |

## B. Ejecución y costes

| Concepto | rev. 5 (test) | UmbralFunding (test) | Nota |
|---|---|---|---|
| Comisiones | 27,1 USDT (0,12 pp/año) | 52,3 (0,22) | Tarifa: 10 bps spot y 5 bps perpetuo, sobre cada ejecución |
| Slippage (incluye spread) | 18,0 (0,08) | 34,9 (0,15) | **Estimación**: 5 bps por pata; el spread real de BTCUSDT es de una fracción de bp |
| Costes / turnover | 12,5 bps | 12,5 bps | Lineal por construcción |
| Latencia y retraso | Retraso de 1 h y 3 h: ±0,01 pp | Ídem | Despreciable: el carry no depende del momento exacto |
| Pata adversa (peor precio de la hora) | −0,42 pp (test); −2,8 pp (desarrollo) | −0,30 pp (test) | Estrés extremo; marca el límite pesimista de la ejecución |
| Teórico frente a ejecutable | C − D = 0,19 pp/año | 0,36 pp/año | **La ejecución no explica el resultado** |
| Costes favorables / adversos | +0,08 / −0,14 pp | +0,15 / −0,29 pp | Supuestos alternativos, no verificados |

No hay libro de órdenes, ejecuciones parciales ni fallos de una pata. Con 7–8 operaciones en 28 meses y BTCUSDT líquido, la incertidumbre de ejecución es pequeña en relación con el resultado.

## C. Asignación de capital (test; CAGR)

| Alternativa | CAGR | Riesgos y supuestos |
|---|---|---|
| Exposición permanente (rev. 5) | **3,76 %** | Contraparte de un exchange; ≈ 47 % del capital como garantía sin rendimiento |
| Exposición condicionada a la señal (UmbralFunding) | 2,68 % | Ídem; ≈ 54 % del tiempo en USDT al 0 % |
| Exposición parcial | No se evaluó: escala el carry linealmente (≈ 0,5 × rev. 5 + 0,5 × efectivo) | No crea ventaja |
| Efectivo: USDT sin remunerar | 0 % | Riesgo de stablecoin y de exchange |
| Efectivo: USDT en Aave v3 (DeFi) | 4,84 % | Contrato inteligente, despegue, gas. Accesible, **no equivalente** a un T-bill |
| Efectivo: letra del Tesoro a 3 meses | 4,42 % | **No accesible** para USDT en un exchange: exige salir a USD bancarios (otra custodia, moneda y plazo) |
| Comparador prerregistrado | 5 % | Umbral de aceptación |

- **Rentabilidad absoluta y rentabilidad incremental:** rev. 5 ganó en todos los años, pero su exceso sobre el efectivo accesible fue negativo en validación y test: de −0,4 a −1,2 pp/año según la alternativa.
- **Apalancamiento:** subir el nocional (ρ < 1 o colateral spot) aumentaría la rentabilidad absoluta en la misma proporción que la exposición al funding y al riesgo de liquidación. **No compensa la falta de ventaja**, y no se usó.

## Conclusión: qué limita más y qué se reutiliza
**Lo que más limita es la asignación de capital frente al nivel de mercado del funding.**
1. Por la estructura, solo ≈ 53 % del capital gana funding.
2. Desde 2023, ese funding (≈ 7 % en test) no supera, en esa proporción, al rendimiento accesible del efectivo (4–5 %).
3. La ejecución es un factor menor (≈ 0,2 pp/año).
4. La señal de UmbralFunding predice bien el funding, pero su acción (salir a efectivo al 0 %) no tiene valor económico.

**Reutilizable en futuras estrategias** (probado con datos reales):
- pipeline de datos oficiales: descarga reanudable, checksums, manifiesto con procedencia, archivos diarios para huecos, velas irregulares, formato µs;
- informe de calidad con filtros prerregistrables;
- prerregistro con hash, adendas y **cerrojo global** de test de uso único;
- registro de experimentos con huellas de código y de datos;
- bootstrap por bloques;
- conciliación contable independiente con descomposición de PnL;
- el método de los **techos con oráculo**, para descartar una familia antes de optimizarla.

**No reutilizable:** el motor de dos cuentas spot/perpetuo y las políticas de funding, que son específicos del carry.
