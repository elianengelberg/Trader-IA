# Prerregistro E1: las estrategias del bot con datos reales (2026-10-19, antes de evaluar ningún dato real)

**Estado al escribirlo:**
- De los datos reales solo se leyeron **cobertura y huecos**; ninguna estrategia corrió sobre ellos.
- La verificación del backtester se hizo **solo con datos sintéticos**: `resultados/verificacion_backtester_sintetico.json`.

## 1. Pregunta
¿Alguna de las 3 estrategias del bot (`trend_following`, `mean_reversion`, `breakout`), tal como están codificadas (`tia.strategy.library` v1.1.0) y en la modalidad que spot permite (**long/flat**), tiene:
- una expectativa neta positiva por operación con datos reales de BTCUSDT, después de costos;
- y un timing de entrada mejor que una entrada aleatoria con la misma frecuencia, la misma exposición y las mismas duraciones?

## 2. Datos
- **Fuente:** velas oficiales de 1 h de BTCUSDT spot de data.binance.vision, ya en disco (`research/hcarry_next/datos/binance_vision/spot`). Cada zip se verifica contra su `.CHECKSUM` antes de leerse; si alguno no coincide, el experimento se detiene.
- **Período:** 2019-10-01 00:00 → 2026-05-31 23:00 UTC.
  - 58 440 horas esperadas; faltan 35, en 17 huecos de como mucho 5 h, que **no** se rellenan.
  - Los tiempos vienen en ms hasta 2024 y en µs desde 2025, y se normalizan.
  - `close_time = open_time + 1 h`.
- **Identificación:** se guarda el SHA-256 de cada archivo y de la lista completa (`datos/manifiesto_datos.json`).

## 3. Instrumento de medición
- **Motor:** `BacktestEngine` del paquete, sin cambios en estrategias, features, régimen, fusión, riesgo, tamaño de posición, salidas ni simulador. Hay dos correcciones mecánicas (clase `MotorE1`), copiadas de la sesión en vivo (`tia.runtime.live`), porque sin ellas el backtest no representa las salidas del bot:
  - **D1:** `client_order_id` único por barra en los stops y salidas reintentados. Sin él, un rechazo deja la posición sin stop y sin salida: en datos sintéticos, 3 349 barras sin stop y una operación de 3 356 barras.
  - **D2:** el stop activo se reemplaza cuando cambia el **nivel** (break-even o trailing), no solo la cantidad. Sin esto, en las corridas sintéticas de diagnóstico, entre el 4 % y el 80 % de las barras con posición abierta tenían el stop activo en el nivel original.
- **Verificación hecha con sintéticos:**
  - sin look-ahead (invariancia de prefijo y perturbación del futuro, idénticas en todas las configuraciones);
  - réplica independiente de 300/300 decisiones por estrategia;
  - ninguna posición pasa más de 1 barra seguida sin stop;
  - 0 stops a un nivel equivocado.
- **Gobernadores de caída de la cuenta, neutralizados para medir:**
  - el perfil por defecto («conservative») deja de abrir operaciones al 6 % de caída, y el capital solo se recupera operando, así que es un corte permanente;
  - el breaker de riesgo detiene el sistema al 10 %;
  - se fija `max_drawdown_pct = 90` y la caída que se entrega al presupuesto es 0. Todo lo demás se conserva: volatilidad, racha de pérdidas, límites diarios, confianza mínima de 0,55, percentil de volatilidad, enfriamiento, etc.
  - La configuración con los gobernadores **como en vivo** se informa aparte (S6).
- **Configuración:** la de `BacktestConfig` por defecto, salvo lo indicado. Marco de 1 h, capital de 100 000, semilla 20261019, warmup de 120, lookback de 300, perfil «conservative», tamaño por convicción, EV solo observado, objetivo, break-even a 1R, trailing a 2 ATR, salida por señal opuesta y entradas a mercado.
- **Instrumento:** BTCUSDT; lote 1e-5; nocional mínimo 5; `shortable = False` en las configuraciones principales.

## 4. Costos y ejecución
- **Comisión:** 10 bps por lado (taker estándar de spot, no verificada con la cuenta). El simulador agrega:
  - deslizamiento base de 2 bps por lado;
  - impacto 0,35·√participación;
  - un componente de rango no configurable: 5 % del rango de la barra, con un máximo de 25 bps por lado.
- **Ejecución:** las órdenes a mercado se llenan en la apertura de la barra siguiente; los stops, al peor precio entre el stop y la apertura; con latencia y llenados parciales por defecto y un 1 % de rechazos.
- **Escenarios de estrés:**
  - S2: comisión ×2 (20 bps);
  - S3: una barra más de retraso en todas las órdenes;
  - S4: costos mínimos (comisión 0, deslizamiento base 0, impacto 0; queda solo el componente de rango), solo para separar señal de costo.

## 5. Configuraciones
**Principales (las que deciden):**
- P1 `trend_following` sola, solo largos.
- P2 `mean_reversion` sola, solo largos.
- P3 `breakout` sola, solo largos.

**Secundarias (descriptivas, no deciden):**
- S1: la fusión de las 3 (el bot tal como opera, pesos 0,45/0,30/0,25), solo largos.
- S2, S3 y S4: los escenarios de la sección 4, para P1–P3 y S1.
- S5: cortos hipotéticos (`shortable = True`, sin costo de préstamo; **no ejecutables en spot**), para P1–P3 y S1.
- S6: los gobernadores como en vivo, para P1–P3 y S1.
- S7: el motor original, con D1 y D2, para P1–P3. Sirve solo para cuantificar el defecto.

**Referencias** (mismas barras y mismo modelo de costos del paquete, 8 760 barras por año):
- buy and hold;
- efectivo;
- cruce de medias 20/50 long/flat (la línea base sencilla de tendencia);
- volatilidad objetivo del 15 %.

## 6. Unidad, métrica e inferencia
- **Unidad:** el round trip. Las piezas de cierres parciales se agregan. Se excluye la liquidación forzada al final de la muestra y se informa aparte.
- **Métrica primaria:** m̄, la media del retorno neto por operación en % del nocional de entrada, después de comisiones y deslizamiento simulados. No depende del tamaño de la posición.
- **Inferencia de signo:**
  - bootstrap por bloques de un mes calendario: los 80 meses del período, incluidos los meses sin operaciones, remuestreados con reposición;
  - 10 000 réplicas, semilla 20261019;
  - P = fracción de réplicas con media > 0;
  - IC90 por percentiles 5–95;
  - p_signo = 1 − P.
  - **Por qué bloques de un mes:** las operaciones se agrupan por régimen (rachas de stops en mercados laterales), y el bloque mensual conserva esa dependencia.
  - **Limitación:** subestima el error si la dependencia dura más de un mes. Como sensibilidad, se informan bloques trimestrales.
- **Inferencia de timing (nulo de entrada aleatoria emparejada):**
  - 2 000 réplicas, estratificadas por **trimestre calendario**.
  - En cada trimestre se colocan al azar, sin solaparse, las mismas duraciones (en barras) de las operaciones de la estrategia en ese trimestre: es una composición uniforme de los huecos. Eso conserva exactamente la cantidad, la exposición en el tiempo y la distribución de duraciones, y su reparto entre trimestres.
  - Cada operación aleatoria entra a mercado en la apertura y sale a mercado en la apertura de la barra de entrada + d, con el **mismo modelo de costos**: comisión, deslizamiento base y componente de rango de cada barra.
  - p_nulo = (1 + #{media nula ≥ m̄}) / (1 + 2 000).
  - **Lo que controla:** la frecuencia, la exposición, las duraciones y la deriva de cada trimestre.
  - **Lo que no controla:** la regla de salida, porque la estrategia sale por stop u objetivo y el nulo por tiempo; tampoco el tamaño de cada operación (no influye en m̄). Es decir, compara «estas entradas y salidas» contra «entradas al azar con el mismo perfil de tenencia».
- **Multiplicidad:** Holm al 5 % unilateral sobre las 3 configuraciones principales, aplicado por separado a p_signo y a p_nulo. Las secundarias no se ajustan y son descriptivas.

## 7. Decisión (por cada configuración principal, en este orden)
1. **Menos de 30 round trips:** EVIDENCIA INSUFICIENTE (muestra).
2. **EVIDENCIA EN CONTRA de una ventaja neta (descartada):** el límite superior del IC90 de m̄ es menor que 0.
3. **VENTAJA RESPALDADA:** tienen que cumplirse las cuatro condiciones:
   - p_signo pasa Holm;
   - p_nulo pasa Holm;
   - m̄ > 0 en los 3 subperíodos (2019-10→2021-12, 2022, 2023-01→2026-05);
   - m̄ > 0 con comisión ×2 (S2).
4. **EVIDENCIA INSUFICIENTE:** cualquier otro caso.

**Lecturas secundarias, sin decisión:**
- **Señal sin costos:** S4 y el retorno bruto.
- **El short hipotético:** S5, con la media por operación corta y su IC.
- **Calibración de la confianza:** correlación de Spearman entre la confianza de entrada y el retorno neto, con bootstrap mensual, y la media por banda (0,55–0,65, 0,65–0,75 y ≥ 0,75), solo si la banda tiene al menos 30 operaciones.
- **Por régimen ex ante:** según la rentabilidad de BTC en las 720 horas previas a la entrada: alcista > +10 %, bajista < −10 %, lateral en medio.

## 8. Validez: se comprueba con los datos reales ANTES de interpretar; si falla, se detiene
1. Todos los zips coinciden con su `.CHECKSUM`.
2. Invariancia de prefijo con datos reales para S1: con el 70 % de las barras, las decisiones y operaciones anteriores al corte son idénticas a las de la corrida completa.
3. En las corridas solo largos, 0 operaciones cortas.
4. Stops sin colocar ≤ 3 % de las barras con posición abierta, y ningún round trip de más de 2 000 barras.

## 9. Métricas descriptivas (para todas las configuraciones y referencias)
- **De la curva de capital:** rentabilidad total y anualizada, volatilidad, caída máxima, Sharpe y Sortino. Limitación: con una exposición baja y tamaños chicos, la comparación de la curva con buy and hold refleja sobre todo la exposición, no el timing.
- **De la actividad:** exposición, cantidad de operaciones, costos y rotación.
- **De la distribución por operación:** media, mediana, cuantiles, tasa de acierto, ganancia y pérdida medias, factor de beneficio y la peor racha.
- **Desgloses:** por razón de salida, por subperíodo y por régimen.

## 10. Limitaciones declaradas de antemano
- **Alcance:** un solo activo y un solo mercado.
- **Marco temporal:** 1 h, mientras que el bot opera a 1 m. A 1 h el costo pesa menos frente al movimiento: si no cubre costos a 1 h, es muy improbable que lo haga a 1 m; si los cubre, eso no valida 1 m.
- **Lo que el backtest no tiene de la sesión en vivo:** la marea de marco superior (HTF), el filtro de spread y la exploración.
- **Costos:** el modelo de deslizamiento con componente de rango es conservador para órdenes chicas de BTC.
- **Gobernadores:** están neutralizados en las configuraciones principales.
- **Período:** el período ya se conoce en términos generales, pero las reglas son anteriores y no se ajusta nada.

## 11. Reproducción
```
cd <experimento>/codigo
PYTHONPATH=/home/user/Trader-IA/packages/tia/src:. ../entorno/venv/bin/python -B e1.py --salida ../resultados
```
Entorno: `entorno/requisitos_con_hash.txt`, con ruedas verificadas contra PyPI.

## Adenda 1 (2026-10-19 18:12 UTC, antes de ejecutar ninguna estrategia sobre datos reales)
- **Qué pasó:** el primer intento se detuvo en la carga de datos (`logs/06a_*`) por un control propio: una misma hora aparecía con valores distintos en dos archivos oficiales.
- **Origen:** H-CARRY había descargado 16 archivos diarios para días con huecos, que se solapan con los mensuales en 352 horas. 349 son idénticas y 3 difieren:
  - 2020-12-21 13:00, el día de una caída de Binance: el archivo diario tiene más volumen y operaciones;
  - 2021-12-24 03:00 y 04:00, con diferencias mínimas en volumen y cierre.
- **Regla neutral:** esas 3 horas se tratan como **faltantes**, sin elegir una fuente. Las horas faltantes pasan de 35 a 38; no hay ningún otro cambio.
- **Ningún resultado de estrategia** se calculó antes de esta decisión.

## Adenda 2 (2026-10-19 19:02 UTC): la segunda ejecución real fue INVÁLIDA; se corrige D3 y se repite
- **Qué falló:** la ejecución real (`logs/06b_*`, `resultados/real_intento2_INVALIDO_D3/`) no superó la validez de la §8.4: había un round trip de más de 2 000 barras en P1, P3, S1 y sus variantes. El script se detuvo **antes de analizar**.
- **Qué se miró (solo mecánica; ningún retorno, P, IC ni comparación):**
  - cantidad de round trips: P1 336, P2 139, P3 77, S1 134;
  - duraciones;
  - fechas del atasco: P1 2023-05-28, P3 2022-11-04, S1 2020-11-30, sin ninguna entrada posterior;
  - contadores de órdenes.
- **D3, defecto del backtester:**
  - la entrada se llena en parte; llega el objetivo y se pide una salida dimensionada a la pierna;
  - el resto de la entrada se llena junto con la salida y queda posición, con `exit_pending` fijado para siempre;
  - a partir de ahí la posición queda sin stop, sin salida y sin nuevas entradas hasta el final de la muestra (`logs/07_*`).
  - La sesión en vivo lo evita: `_close_position` cancela la entrada que aún descansa y dimensiona el cierre con lo que realmente tiene.
- **Corrección en `MotorE1`, sin tocar estrategias ni el repositorio:**
  1. al pedir una salida, se cancelan las órdenes de entrada que aún descansan;
  2. en plano, se cancelan los restos de entradas que ya se llenaron en parte;
  3. red de seguridad: si la salida terminó y queda posición, se libera `exit_pending`.
  - Todas las intervenciones quedan contadas.
- **Verificación con sintéticos** (`resultados/verificacion_backtester_sintetico.json`, nueva prueba V6 con llenados parciales al 90 %):
  - el motor original se traba tras 2 operaciones durante unas 7 700 barras;
  - `MotorE1` opera hasta el final, con 0 piernas huérfanas;
  - V1–V5 siguen pasando.
- **Nuevo criterio de validez (§8.5):** 0 barras con una pierna sin stop y sin salida pendiente.
- **Qué se evalúa:** la **tercera** ejecución con datos reales, en `resultados/real/`. Las dos anteriores no se analizan ni se interpretan.
