# Familias de estrategia consideradas y selección (2026-10-17)

Escrito **antes** de calcular cualquier rendimiento de estrategia en cualquier ventana.
- Datos disponibles: velas diarias oficiales de spot de BTCUSDT y ETHUSDT, 2017-08-17 → 2026-05-31, verificadas (`experimentos/calidad_datos.json`).
- Se excluyen el carry y el funding, por pedido del usuario y por lo aprendido en H-CARRY.

## Comparación a priori

| Familia | Hipótesis económica | Evidencia previa (externa) | Coste y rotación | Riesgo de sobreajuste | Falsable con estos datos | Valoración |
|---|---|---|---|---|---|---|
| **1. Tendencia long/flat (momentum de serie temporal)** | La información se difunde despacio, hay manada y flujos que persiguen la tendencia. Tras subas sostenidas siguen más subas que tras caídas. Estar fuera en las caídas largas reduce las pérdidas grandes. | Momentum de serie temporal en futuros (Moskowitz, Ooi y Pedersen, 2012); en cripto, momentum a 1–4 semanas en el mercado agregado (Liu y Tsyvinski, 2021). | Baja: pocos cambios de exposición; solo spot, sin funding | Medio: elegir ventanas. Se mitiga con un ensamble fijo y estándar (1, 3 y 6 meses) | Sí: valor del timing frente a una exposición estática equivalente | **Candidata principal** |
| 2. Momentum con filtro contra entradas tardías | Igual que 1, evitando entrar con el movimiento ya agotado | Débil y dependiente de la implementación | Baja o media | **Alto**: filtros adicionales | Sí | Solo como refinamiento si 1 muestra valor; no ahora |
| 3. Reversión a la media | Sobrerreacción de corto plazo y provisión de liquidez | En BTC diario es débil. A muy corto plazo, la microestructura exige datos intradía y ejecución de maker | **Alta**: muchas operaciones, ~30 bps la ida y vuelta | Medio o alto | Parcialmente | Solo si la autocorrelación diaria de desarrollo es claramente negativa (ver regla) |
| 4. Ruptura (Donchian) | Igual que la tendencia, con otra implementación | Equivalente a 1 | Baja | Medio | Sí | Redundante con 1: no se prueba por separado |
| 5. Exposición gestionada por volatilidad | La volatilidad es predecible y el retorno no le es proporcional, lo que mejora el Sharpe | Moreira y Muir (2017) en acciones; mixta en cripto | Media | Medio | Sí | Complementaria; no es una ventaja de timing por sí misma |
| 6. Momentum de corte transversal entre criptos | Rotar a las más fuertes | Existe en la literatura cripto | Alta | Alto | **No sin sesgo**: hace falta un universo histórico sin supervivientes (altas y bajas), y no lo tenemos verificado | Excluida por datos |
| 7. Estacionalidad (fin de semana, mes) | Débil | Poco robusta | Baja | **Alto**: minería de datos | Sí | Excluida |

## Evidencia inicial (SOLO desarrollo: 2017-08-17 → 2021-12-31) y regla de decisión fijada de antemano

1. **Momentum.** Para cada L ∈ {30, 90, 180} días, en muestras mensuales sin solape de desarrollo: diferencia de la rentabilidad logarítmica de los 30 días siguientes entre «rentabilidad pasada de L días > 0» y «≤ 0».
2. **Reversión.** Autocorrelación de los rendimientos diarios (retardos 1 a 5) y semanales (retardos 1 a 4).
3. **Regla:**
   - Si la diferencia del punto 1 es positiva en al menos 2 de las 3 ventanas → **familia 1**.
   - Si es ≤ 0 en al menos 2 de 3 **y** la autocorrelación diaria de retardo 1 es < −0,10 → estudiar la familia 3. Exige además que la rentabilidad esperada por operación supere los 30 bps de la ida y vuelta.
   - En cualquier otro caso → no hay base para ninguna. Se informa y no se fuerza una estrategia.
4. Esta evidencia **no** se usa para elegir parámetros: el ensamble {30, 90, 180} está fijado aquí.

**Advertencia de contaminación (para todas las familias):**
- El agente que diseña conoce a grandes rasgos la historia del precio del BTC hasta mediados de 2026.
- Los análisis de H-CARRY mostraron regímenes de funding de 2020–2026, que están correlacionados con la tendencia.
- Ninguna ventana histórica es, por tanto, «inédita» en sentido estricto. Mitigaciones:
  - parámetros fijados a priori;
  - criterio de **timing** frente a una exposición estática equivalente y frente a un nulo de desplazamiento circular (más difícil de «saber» de memoria que «el BTC subió»);
  - test de uso único con cerrojo.
- La prueba independiente de verdad es el período reservado (2026-06-01 → 2026-10-13, con autorización y escasa potencia) o una prueba prospectiva.

## Resultado de la evidencia inicial (2026-10-17; `experimentos/evidencia_inicial_desarrollo.json`)

| BTCUSDT (desarrollo) | L = 30 | L = 90 | L = 180 |
|---|---|---|---|
| Rentabilidad log de 30 días siguiente: pasado > 0 / ≤ 0 | +0,051 / +0,025 | +0,030 / +0,050 | +0,033 / +0,046 |
| Diferencia (t) | +0,026 (0,40) | −0,020 (−0,36) | −0,013 (−0,20) |

- Autocorrelación diaria de retardo 1: −0,061; semanal: +0,035.
- **Regla → «sin base».** Ni tendencia (1 de 3 ventanas) ni reversión (−0,061 > −0,10).
- ETHUSDT cumpliría la regla de tendencia (2 de 3; t máximo de 1,21). **No** se cambia de activo principal después de ver esto.
- **Potencia baja:** 47 observaciones mensuales sin solape por ventana. La ausencia de evidencia no prueba que no haya momentum. Pero la regla era esta, y no se reinterpreta.

**Decisión:**
- No se prerregistra la tendencia en BTC (familia 1).
- Tampoco la ruptura ni el momentum con filtros (familias 2 y 4): sería el mismo fracaso con otro nombre.
- Pasa a examen la **familia 5 (exposición gestionada por volatilidad)**, un mecanismo distinto (riesgo, no dirección), con su propia regla fijada **antes** de calcularla.
- **Selección múltiple:** se examinaron 2 familias en desarrollo. Queda declarado.

## Familia 5: regla de evidencia inicial (fijada antes de calcularla; SOLO desarrollo, BTCUSDT)
1. **Persistencia:** correlación entre la volatilidad realizada (rendimientos log diarios) de bloques consecutivos de 30 días. Exige ≥ 0,5.
2. **Riesgo-retorno:** se clasifican los días por la volatilidad realizada de los 30 días **previos** (ex ante), con umbrales fijos de 50 % y 80 % anual. Para cada grupo, la media y la desviación del rendimiento del día siguiente, y su cociente. Exige que el cociente del grupo de baja volatilidad sea ≥ al de alta.
   - Ese cociente es el «Sharpe diario». Si no cae con la volatilidad, reducir exposición en volatilidad alta no mejora la relación riesgo-retorno.
3. **Regla:** si se cumplen 1 y 2 → candidata familia 5. Si no → **ninguna familia tiene base en desarrollo**; se informa y se cierra la búsqueda de esta fase sin forzar una estrategia.

## Resultado de la familia 5 (`experimentos/evidencia_volatilidad_desarrollo.json`)
- **BTCUSDT:** persistencia de la volatilidad de 30 días = **0,32** (< 0,5). Cociente con volatilidad baja / alta: 0,095 / 0,045.
- **Regla → «sin base»:** falla la persistencia; el riesgo-retorno sí apunta en la dirección esperada.
- **ETHUSDT:** 0,16 → «sin base».

**Conclusión del cribado: ninguna familia tiene base en desarrollo con las pruebas fijadas.** Esas pruebas son toscas y de baja potencia.

## Diagnóstico de desarrollo con la regla COMPLETA (desviación declarada del plan; criterio fijado ANTES de ejecutarlo)
- **Por qué:** el cribado usó 47 observaciones mensuales. Para saber si «sin base» es robusto o un artefacto, se ejecutan en **desarrollo** (2018-02-14 → 2021-12-31) las dos reglas completas.
- **Parámetros fijados a priori**, sin ningún ajuste:
  - **T · Tendencia long/flat:**
    - w = media de 1[cierre_d / cierre_{d−L} > 1] para L ∈ {30, 90, 180};
    - se decide con el cierre del día d y se ejecuta en la apertura de d + 1;
    - solo se opera cuando cambia el objetivo.
  - **V · Volatilidad gestionada:**
    - w = min(1; 0,50 / σ̂), con σ̂ la volatilidad realizada de 30 días anualizada;
    - no hay apalancamiento;
    - se opera si |w objetivo − w actual| ≥ 0,10.
- **Costes:** 10 bps de comisión + 5 bps de slippage sobre el valor negociado. Efectivo al 0 %.
- **Criterio para pasar a validación y test** (dos candidatas: umbrales exigentes):
  - **T:** media diaria de (T − estática con la misma exposición media) > 0, con bootstrap por bloques de 20 días P ≥ 0,90 **y** percentil ≥ 0,90 frente a 1 000 desplazamientos circulares de su propia exposición.
  - **V:** Sharpe(V) − Sharpe(buy and hold) > 0, con P ≥ 0,90 por bootstrap pareado por bloques de 20 días; además, caída máxima de V < caída de buy and hold.
- **Si ninguna pasa:** se confirma «sin base» y se cierra la fase con un resultado negativo.
- **Si alguna pasa:** se escribe su prerregistro de validación y test antes de mirar esas ventanas.

## Resultado del diagnóstico con las reglas completas (`experimentos/diagnostico_reglas_desarrollo.json`)

| Desarrollo 2018-02-14 → 2021-12-31 | CAGR | Sharpe | Caída | Exposición | Operaciones | Costes |
|---|---|---|---|---|---|---|
| T tendencia | 53,4 % | 1,12 | 50,2 % | 0,56 | 178 | 5,37 pp/año |
| V volatilidad | 41,5 % | 0,92 | 58,6 % | 0,76 | 75 | 0,69 pp/año |
| Buy and hold | 54,5 % | 0,96 | 72,2 % | 1,00 | 1 | 0,04 |
| Estática con la exposición de T | 37,2 % | 0,96 | 49,0 % | 0,56 | diaria, sin costes | 0 |

- **T:** exceso neto sobre la estática de +14,2 %/año, IC90 [−8,1 %; +37,2 %], **P = 0,842 < 0,90**; percentil nulo 0,912. **No pasa.**
- **V:** Sharpe − buy and hold = −0,05, P = 0,38. **No pasa.**

## Última puerta (fijada ANTES de calcularla): ¿falta señal o sobra rotación?
- **Qué se calcula:** el exceso de timing **bruto** de T (costes 0), con el mismo bootstrap y el mismo nulo.
- **Si bruto P ≥ 0,90 y percentil nulo ≥ 0,90:** la señal existe y el problema es la ejecución (46 operaciones al año). Se permite **una única** revisión estructural:
  - **T2:** la misma señal {30, 90, 180}, decidida solo con el cierre de los domingos (UTC) y ejecutada el lunes;
  - mismo criterio neto que T (P ≥ 0,90 y nulo ≥ 0,90);
  - si T2 pasa, se prerregistra para validación y test;
  - si no pasa, se cierra.
- **Si el bruto no pasa:** se cierra la fase sin estrategia candidata.
- **Ninguna otra iteración.** En desarrollo se habrán evaluado: T, V, T bruto (diagnóstico) y, como mucho, T2.
