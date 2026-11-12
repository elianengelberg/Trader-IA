# PROPUESTA DE PRERREGISTRO: H-EMA9-VWAP v0.1

> **PROPUESTA NUEVA · PENDIENTE DE APROBACIÓN · NO EJECUTADA**
> - Este documento **no** es la «v1 congelada» de H-EMA9-VWAP. Esa versión (referencia citada `3114b565…`) **no se encontró** en ninguna fuente accesible (`AUDITORIA_H-EMA9-VWAP.md`).
> - Se numera v0.1 para **no sustituir** a la v1 ni confundirse con ella. Sus parámetros **no** reconstruyen los de la v1: son una definición nueva, redactada el 2026-10-20 **sin mirar datos** de precios ni resultados.
> - No autoriza ninguna ejecución. Las decisiones marcadas **[D-EV-n]** o **[D-MEC-n]** están pendientes de aprobación.

## 1. Hipótesis
- **Conceptual:** la combinación de EMA(9) y VWAP puede identificar condiciones de tendencia o confirmación intradía con una ventaja neta de costos.
- **Operacional (H₁):** en BTCUSDT y ETHUSDT spot, con velas de 1 h, una estrategia long/flat intradía tiene un **exceso de timing neto** positivo frente a la estática con su misma exposición media (§7). Entra cuando hay tendencia de sesión (precio y EMA(9) por encima del VWAP de la sesión) y el precio retoma la EMA(9) tras un retroceso (§3).
- **Nula (H₀):** el exceso es ≤ 0.
- **Estar por encima del VWAP no basta por sí solo:** la entrada exige además el cruce de retoma y una EMA ascendente (§3.4).
- **Evidencia previa relevante, no equivalente:** las reglas de tendencia horarias del bot (E1-P1: EMA 12/26/50 + ADX) perdieron después de costos en BTC a 1 h entre 2019-10 y 2026-05 (−0,237 %/operación). La expectativa previa es baja, y **el costo es el obstáculo principal** (§6).

## 2. Mercado, activos y horario
- **Mercado:** Binance spot. **Activos:** BTCUSDT y ETHUSDT, cada uno con media manga. **Posiciones:** solo largos o efectivo. Sin cortos ni apalancamiento.
- **Velas:** **1 h** UTC [D-EV-1].
  - Es la temporalidad intradía con datos ya verificados en disco para BTC.
  - Opera menos y paga menos costos que 5 o 15 minutos.
  - **No** se elegirá otra temporalidad a posteriori: hacerlo sería otro experimento.
- **Sesión:** el día UTC, de 00:00 a 24:00. Cripto cotiza 24/7; la sesión solo sirve para anclar el VWAP.
- **Horario de entradas:** señales en barras con apertura de 02:00 a 18:00 UTC; ejecución de 03:00 a 19:00 [D-EV-2].

## 3. Definición operacional (inequívoca)
**Notación** (por activo; t = barra de 1 h):
- O_t, H_t, L_t y C_t: precios de la barra.
- V_t: volumen en el activo base (columna 5 de la vela de Binance).
- QV_t: volumen en USDT (columna 7).
- **Barra válida:** presente, cerrada, OHLC coherente, precios > 0, duración de 1 h y sin conflicto entre el archivo mensual y el diario.

1. **EMA(9) del cierre:** EMA_t = α · C_t + (1 − α) · EMA_{t−1}, con **α = 2/(9+1) = 0,2**.
   - **Inicialización:** EMA en la 9.ª barra válida de la serie = media simple de los 9 primeros cierres.
   - **Continua entre días:** no se reinicia por sesión.
   - **Tras un hueco** (barra faltante o inválida), la EMA sigue desde su último valor con el siguiente cierre, sin interpolar. Las señales quedan **bloqueadas las 9 barras siguientes**.
   - **Calentamiento inicial:** 50 barras sin señales.
2. **VWAP de sesión** (anclado a las 00:00 UTC): **VWAP_t = Σ QV_i / Σ V_i**, sobre las barras i de la sesión con i ≤ t.
   - Cada QV_i/V_i es el VWAP exacto de la barra i, porque Binance da los volúmenes en base y en cotización. **No se usa el precio típico.**
   - Si Σ V_i = 0, el VWAP no está definido y no hay señal.
3. **Sesión completa hasta t:** todas las barras de la sesión desde 00:00 hasta t están presentes y válidas.
   - Si falta alguna, **no hay entradas nuevas en el resto de la sesión** (el VWAP estaría incompleto).
4. **Entrada:** al cierre de la barra t se cumplen **todas** estas condiciones y se compra en la **apertura O_{t+1}** con el 100 % de la manga:
   - (a) la apertura de t está entre 02:00 y 18:00 UTC, así que hay al menos 3 barras de sesión;
   - (b) no hay posición abierta en el activo y **no hubo otra entrada en esta sesión** (máximo una por activo y por sesión) [D-EV-3];
   - (c) la sesión está completa hasta t y la EMA no está bloqueada ni en calentamiento;
   - (d) **tendencia:** C_t > VWAP_t y EMA_t > VWAP_t;
   - (e) **confirmación por retoma:** C_{t−1} ≤ EMA_{t−1} y C_t > EMA_t;
   - (f) **EMA ascendente:** EMA_t > EMA_{t−1}.
   - Si la barra t + 1 falta, no hay entrada.
5. **Salida:** al cierre de la barra t en posición, se vende en la **apertura O_{t+1}** por la primera condición que se cumpla:
   1. **Invalidación de tendencia (stop):** C_t < VWAP_t.
   2. **Fin de sesión (duración máxima):** t es la barra de las 23:00. Se vende en la apertura de las 00:00 del día siguiente: **nunca se mantiene una posición en la sesión siguiente.**
   - Si la apertura de salida falta, se vende en la siguiente apertura disponible.
   - **Sin objetivo de ganancia ni stop fijo adicional** [D-EV-4]: el VWAP hace de stop, y no se agrega ATR ni otro indicador.
6. **Señales simultáneas:** BTC y ETH son mangas independientes, con una posición como máximo cada una. No hay prioridad entre activos ni reasignación de capital.
7. **Tamaño:**
   - 100 % de la manga durante la posición; fuera de ella, efectivo USDT al 0 %;
   - sin apalancamiento;
   - no se escala por volatilidad (sería una variante).
8. **Datos retrasados o incompletos:**
   - solo se usan barras **cerradas**;
   - en el histórico, la latencia se modela ejecutando en O_{t+1};
   - en el papel, si la barra t no está publicada en el plazo que fije el ejecutor [D-EV-5], esa barra no genera señal y no se recupera después.

## 4. Datos y requisitos
- **Fuente:** data.binance.vision, `spot/monthly/klines/{SÍMBOLO}/1h`, más los archivos diarios oficiales cuando falten horas en el mensual. Todo con `.CHECKSUM`.
- **BTCUSDT 1h (2019-10 → 2026-05):** **ya en disco y verificado**. Son 96 archivos (80 mensuales + 16 diarios) y son los mismos SHA-256 que en H-CARRY y E1.
  - Faltan **38 de 58 440 velas** (19 huecos de 5 h como máximo), y hay **3 horas en conflicto** que se excluyen.
- **ETHUSDT 1h:** **no está en disco.** Hace falta **autorización de descarga** [A-EV-1]: unos 80 archivos mensuales más los diarios de complemento.
  - Sin ETH, **el experimento no se ejecuta tal como está especificado**. No hay ninguna alternativa silenciosa «solo BTC»; esa sería otra versión.
- **Período INVÁLIDO para un activo** [D-EV-6]:
  - más del 0,5 % de horas faltantes o inválidas;
  - un archivo mensual sin su complemento;
  - un checksum que falla.
- **Sin relleno ni interpolación.**

## 5. Períodos
| Fase | Ventana | Uso |
|---|---|---|
| **D (desarrollo)** | 2019-10-01 → 2021-12-31 | Verificar la implementación y describir. **No se cambia ningún parámetro por sus resultados.** Compuerta opcional [D-EV-7]: si D da P(conjunto) < 0,10, no se gasta E |
| **E (histórica, uso único)** | 2022-01-01 → 2026-05-31 | Una sola ejecución con candado |
| **P (prospectiva, papel)** | Desde la aprobación, con historia solo desde el 2026-10-14 [D-EV-8] | La única evidencia independiente; cortes de 12 y 24 meses |

- **Período reservado de H-CARRY (2026-06-01 → 2026-10-13):** no se lee.
- **Contaminación declarada:** E1 ya evaluó reglas de tendencia horarias en BTC entre 2019-10 y 2026-05, y T usó BTC y ETH entre 2022 y 2026. **E no es independiente.**

## 6. Ejecución y costos
- **Señal** al cierre de la barra; **ejecución** a mercado en la apertura de la barra siguiente.
- **Comisión:** 10 pb por lado. **Slippage y spread:** 5 pb por lado. **Ida y vuelta: 30 pb.**
- **Estrés** (descriptivo): costos ×2 y ×3; slippage de 15 pb; ejecución con una barra extra de retraso (O_{t+2}).
- **Costo mínimo que hay que superar (aritmética, sin datos):** cada operación necesita **más de 30 pb brutos** para empatar.
  - Con hasta una operación por activo y por día, el costo puede llegar a ≈ 110 %/año de la manga (365 × 0,30 %) si se opera todos los días.
  - Es la **razón principal** por la que la expectativa previa es baja. **No** es motivo para ajustar parámetros.

## 7. Benchmark y métricas
- **Benchmark primario:** la estática con la misma exposición media ε_a (rebalanceo diario, sin costos) sobre el rendimiento diario de cierre a cierre (00:00 UTC) del activo. Es la misma construcción que en T y en H-REV-SHOCK.
- **Exceso diario** x_{a,d}: el rendimiento diario de la manga (las operaciones horarias del día compuestas, netas) menos ε_a · r_{a,d}. **Conjunto** = promedio de BTC y ETH.
- **Métrica primaria:** media diaria del exceso conjunto × 365.
- **Secundarias (descriptivas):**
  - por activo: operaciones, retorno neto por operación, parte del bruto que se lleva el costo y duración media;
  - **nulo de entradas aleatorias emparejadas:** mismas horas de entrada posibles, mismas duraciones y mismos costos;
  - estrés de costos y de retraso;
  - subperíodos;
  - Sharpe y caída máxima de la estrategia y de los benchmarks.

## 8. Marco estadístico común (MEC v0.1, idéntico en H-REV-SHOCK)
1. **Una sola métrica primaria:** el exceso de timing anualizado del conjunto.
2. **Incertidumbre:** bootstrap por bloques circulares de la serie diaria de exceso.
   - Bloques de 20 días, B = 2000, semilla 20261020.
   - P = fracción de medias > 0; IC90 por percentiles.
   - Bloques de 10 y 40 días, solo descriptivos [D-MEC-1].
3. **Nulo emparejado:** 1000 réplicas; se informa el percentil.
4. **Una sola configuración primaria.** Ninguna variante decide. Otra temporalidad o configuración es otro experimento, que requiere aprobación.
5. **Holm con m = 2** si ambas hipótesis se evalúan en E en la misma ronda [D-MEC-2].
6. **Criterios de E** [D-MEC-3]:
   - **INVÁLIDO:** falla de datos o de integridad.
   - **INCONCLUSO POR DATOS:** menos de **100 operaciones** en E entre los dos activos [D-EV-9].
   - **RESPALDADA EN E:** P ≥ 0,95 (o el umbral de Holm), exceso con costos ×2 > 0, mismo signo en BTC y ETH y percentil ≥ 0,90 en el nulo emparejado.
   - **NO RESPALDADA:** P < 0,10.
   - **EVIDENCIA INSUFICIENTE:** cualquier otro caso.
7. **Separación de conclusiones:**
   - (i) retorno positivo observado;
   - (ii) ventaja respaldada en E (histórica, contaminada);
   - (iii) robustez fuera de muestra, solo con P a los 24 meses;
   - (iv) viabilidad operativa: fills, slippage horario real y capacidad. **Fuera de alcance.**
   - Ningún P aislado prueba rentabilidad.
8. **Potencia no calculada con datos.** Solo hay una ilustración con supuestos [Hip]: años ≈ (2,49 · TE/μ)². Con E de 4,42 años solo se detectaría μ ≥ ≈ 1,18 · TE. **No se promete potencia.**

## 9. Riesgo
- **Exposición máxima:** 100 % por manga, solo intradía (nunca de una sesión a la otra). Sin apalancamiento ni cortos.
- **Eventos extremos:** no se excluyen. Las caídas del exchange se manejan con las reglas de datos faltantes (§3.3 y §3.8).

## 10. Controles contra el look-ahead y el sobreajuste
- **Datos usados:** el VWAP y la EMA en t usan solo barras ≤ t; la ejecución es en t + 1.
- **Pruebas con datos sintéticos antes de cualquier dato real:**
  1. invariancia al truncar (5 cortes);
  2. el VWAP coincide con Σ QV / Σ V a mano;
  3. la EMA coincide con una implementación de referencia;
  4. control positivo: tendencia intradía plantada;
  5. control negativo: paseo aleatorio;
  6. sesión incompleta, hueco y fin de sesión.
- **Código congelado con hash** antes de leer D. **Candado de uso único para E.** Registro de solo añadidos.
- **Prohibido:**
  - elegir la temporalidad, el anclaje del VWAP, el período de la EMA, el horario o los activos después de ver D o E;
  - repetir E.

## 11. Auditoría y reproducción
- **Registro y reproducción:** igual que en H-REV-SHOCK §11, con hashes del prerregistro, del código, de los manifiestos y de la salida, y la semilla. Un segundo proceso recalcula para verificar.
- **Revisión independiente por otro modelo:** **no realizada** (no disponible ni autorizada).

## 12. Limitaciones conocidas de antemano
- **El costo** probablemente domine; si opera seguido, lo esperable es un exceso negativo.
- **El VWAP con velas de 1 h** es una aproximación por barras: es exacto por barra, pero la resolución de entrada y salida es horaria.
- **Ejecutar en la apertura** de la barra siguiente puede ser optimista en movimientos bruscos (slippage real mayor).
- **BTC y ETH están correlacionados.**

## 13. Fases y autorizaciones necesarias (nada de esto está autorizado)
| Fase | Qué | Requiere |
|---|---|---|
| A-EV-0 | Aprobar y congelar este texto | Tu aprobación |
| A-EV-1 | Descargar ETHUSDT 1h (2019-10 → 2026-05) de data.binance.vision, verificado con checksum | Autorización de descarga |
| A-EV-2 | Implementación, pruebas sintéticas y congelado del código | Autorización |
| A-EV-3 | Ejecutar D y luego E (una vez) | Autorización expresa |
| A-EV-4 | Papel prospectivo, con registros fuera del repositorio | Autorización |

## 14. Decisiones pendientes de aprobación
| ID | Decisión |
|---|---|
| D-EV-1 | Velas de 1 h |
| D-EV-2 | Señales con apertura de 02:00 a 18:00 UTC |
| D-EV-3 | Máximo una entrada por activo y por sesión |
| D-EV-4 | Sin objetivo ni stop fijo; el VWAP como stop |
| D-EV-5 | Plazo de publicación en el papel |
| D-EV-6 | Invalidez si faltan más del 0,5 % de las horas |
| D-EV-7 | Compuerta de D |
| D-EV-8 | Historia para P solo desde el 2026-10-14 |
| D-EV-9 | Mínimo de 100 operaciones en E |
| D-MEC-1 a 3 | Iguales que en H-REV-SHOCK |
