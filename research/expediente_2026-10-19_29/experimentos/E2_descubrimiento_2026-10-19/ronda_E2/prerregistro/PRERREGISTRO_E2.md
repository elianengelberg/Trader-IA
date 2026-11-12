# Prerregistro de la ronda E2 (E2-A, E2-B, E2-C), 2026-10-19, antes de calcular ningún resultado

**Estado al escribirlo:**
- **No** se calculó ninguna variable, regresión ni regla con estos datos.
- De Wikipedia solo se bajó **un día** (2015-07-01) para comprobar que la API responde; no aporta información sobre ningún resultado.
- Los esbozos de `INVESTIGACION_E2.md` (§1, C1–C3) dejaban decisiones abiertas. Acá se cierran **todas**, antes de mirar.

## 0. Reglas comunes
- **Una sola ejecución por experimento.** Si algo invalida una prueba (datos, mirada al futuro), se detiene **antes** de interpretarla y se documenta.
- **Datos reutilizados**, marcados como tales; un resultado favorable sobre ellos **no** es una confirmación independiente:
  - BTCUSDT y ETHUSDT spot diarios de data.binance.vision, 2017-08 → 2026-05, ya usados en T;
  - funding de BTC y ETH y prima de BTC (1 h), 2020-01 → 2026-05, ya usados en H-CARRY.
  - Se leen con `tendencia.datos.leer`, que verifica el hash de cada archivo y rechaza los días ≥ 2026-06-01. El funding y la prima se verifican contra el `.CHECKSUM` oficial de cada zip.
- **Datos nuevos:** las vistas diarias de Wikipedia (E2-C).
- **Disponibilidad en el tiempo (sin mirada al futuro):** la información del día d es la que existe al **cierre del día d** (00:00 UTC de d+1).
  - **Precio y volumen:** la vela diaria de d.
  - **Funding:** las liquidaciones con `calc_time` < 00:00 UTC de d+1.
  - **Prima:** las velas de 1 h con cierre ≤ 00:00 UTC de d+1.
  - **Wikipedia:** solo hasta el día **d−1**. La vista del día d se publica después del cierre.
- **Entrenamiento:** al pronosticar en t se usan solo las observaciones s con objetivo realizado, s + h ≤ t (sin solapamiento con el futuro).
- **Pruebas múltiples:** **Holm al 5 % sobre las 3 hipótesis confirmatorias** (p_A, p_B, p_C).
  - Si un experimento queda inconcluso por falta de datos, entra en Holm con p = 1, de modo que m sigue siendo 3.
  - Dentro de E2-A, las 10 pruebas se resumen en un p de familia de Bonferroni: p_A = min(1, 10 × p_mín). Combinado con Holm entre experimentos, es un procedimiento cerrado válido.
- **Predicción frente a rentabilidad:** E2-A y E2-C son pruebas **predictivas**, sin costos y sin regla de trading. Un resultado favorable significa «información incremental», **no** rentabilidad neta. E2-B es una prueba de **trading** con costos.
- **Validez, que se comprueba antes de interpretar:**
  1. hashes y checksums correctos;
  2. a lo sumo 1 % de días faltantes en cada serie dentro de su ventana (si no, el experimento queda inconcluso);
  3. comprobación automática de que cada ajuste usa solo s + h ≤ t;
  4. invariancia frente al futuro: en 5 fechas de corte al azar, recalcular con los datos truncados al corte y obtener pronósticos o exposiciones idénticos hasta el corte;
  5. el estimador de Clark–West se prueba antes con datos **sintéticos** (nulo verdadero y alternativa verdadera).

## 1. E2-A: compuerta de información incremental (predictiva)
- **Hipótesis H-A:** al menos una de 5 variables de estado mejora, fuera de muestra, el pronóstico del retorno logarítmico a h días frente a una base que ya incluye el momentum de T.
- **Activos:** BTC y ETH, en panel con interceptos por activo y pendientes comunes. La **prima** existe solo para BTC: esa variable se prueba solo en BTC.
- **Objetivo:** y(i,t) = ln(C(i,t+h) / C(i,t)), con h ∈ {7, 28} días.
- **Base:** y = a_i + b·MOM(i,t) + e, donde MOM = señal de T (`tendencia.senal.tsmom`, fracción de las ventanas {30, 90, 180} con retorno positivo).
- **Aumentada (k):** y = a_i + b·MOM + c·X_k(i,t) + e. OLS reestimado cada día con ventana expansiva.
- **Variables X_k, definidas al cierre de t:**
  1. **VOL30:** desvío de los 30 retornos logarítmicos diarios hasta t, × √365.
  2. **VOLUMEN_Z30:** (ln V_t − media(ln V de t−30 … t−1)) / desvío(ln V de t−30 … t−1), con V = volumen en USDT de la vela diaria.
  3. **FUNDING7:** media de las liquidaciones de funding con `calc_time` en [t−6 00:00, t+1 00:00) UTC.
  4. **PRIMA7 (solo BTC):** media de los cierres horarios del índice de prima en las 168 h que terminan al cierre de t.
  5. **DD90:** C_t / máx(C de t−89 … t) − 1.
- **Muestra:**
  - el entrenamiento empieza el 2020-01-08, una fecha común para que todas las variables usen la misma muestra;
  - los pronósticos van desde el 2021-01-01 hasta el último t con t + h ≤ 2026-05-31.
- **Prueba:** Clark–West (2007), pérdida cuadrática.
  - f(i,t) = e_b² − [e_a² − (ŷ_b − ŷ_a)²]; se promedia entre los activos disponibles cada día t.
  - Media de f con error de Newey–West (rezagos = h); p unilateral (aumentada mejor).
  - También se informa ΔR²_OOS = 1 − Σe_a² / Σe_b².
- **Decisión de E2-A:**
  - **FAVORABLE (información incremental):** p_A pasa Holm entre experimentos. Se informa qué variable u horizonte pasa el Holm interno de 10.
  - **EN CONTRA (sin información incremental detectable):** las 10 pruebas tienen ΔR²_OOS ≤ 0 y p sin ajustar ≥ 0,10.
  - **INSUFICIENTE:** cualquier otro caso.
- **Potencia:** unos 1 970 pronósticos diarios por activo y horizonte, pero solapados. El tamaño efectivo es de ≈ 280 para h = 7 y ≈ 70 para h = 28 por activo, así que solo se detectan efectos grandes.

## 2. E2-B: funding extremo como señal contraria para spot (trading)
- **Hipótesis H-B:** variar la exposición a spot en contra del funding extremo agrega valor de timing neto de costos.
- **Activos:** BTC y ETH spot; el funding es el del perpetuo del mismo activo.
- **Señal:**
  - F7(t) = FUNDING7, con la misma definición que en E2-A;
  - P10(t) y P90(t) son los percentiles 10 y 90 de los F7 de los días ≤ t (ventana expansiva desde el primer F7, con un mínimo de 180 valores; antes de eso, sin señal y en efectivo).
- **Exposición decidida al cierre de t:**
  - 1 si F7 ≤ P10;
  - 0 si F7 ≥ P90;
  - 0,5 en el resto.
  - Sin histéresis.
- **Ejecución:** con `tendencia.backtest.simular`, código congelado de T usado sin modificarlo. Se ejecuta en la apertura de t+1 y solo cuando cambia el objetivo.
- **Costos:** 10 bps de comisión más 5 bps de deslizamiento por lado sobre el valor negociado (`Costes()`, los de T en cripto). Estrés: ×2.
- **Ventana de evaluación:** [2020-07-06, 2026-06-01). Debe empezar después del primer día con señal; si no, se detiene.
- **Métrica primaria (como en T):** exceso diario = retorno de la regla con costos − retorno de la exposición estática igual a la exposición media de la regla (rebalanceo diario, sin costos).
  - El conjunto es la media de BTC y ETH por día; se anualiza × 365.
- **Inferencia:** bootstrap circular por bloques de 60 días sobre el conjunto (10 000 réplicas, semilla 20261019).
  - P = fracción de réplicas con media > 0; IC90 por percentiles 5–95; p_B = 1 − P.
- **Decisión de E2-B:**
  - **FAVORABLE:** tienen que cumplirse las tres condiciones:
    - p_B pasa Holm entre experimentos;
    - el exceso del conjunto con costos ×2 es > 0;
    - la estimación puntual es > 0 en BTC y en ETH.
  - **EN CONTRA (sin ventaja relevante):** el límite superior del IC90 del conjunto es < +2 %/año.
  - **INSUFICIENTE:** cualquier otro caso. Se aclara si la estimación puntual es negativa.
- **Descriptivo:**
  - días en cada estado, cantidad de episodios (rachas en una cola) y cambios de exposición;
  - costos totales;
  - para la regla, buy and hold y la estática: CAGR, volatilidad, caída máxima y Sharpe.
- **Potencia:** las colas suman un 20 % de los días, pero los episodios independientes son pocos (se informan). Lo esperable es INSUFICIENTE.

## 3. E2-C: atención (vistas de Wikipedia) como información incremental (predictiva)
- **Hipótesis H-C:** el cambio de 4 semanas en las vistas del artículo «Bitcoin» mejora, fuera de muestra, el pronóstico del retorno de BTC a 7 días frente a una base de momentum de 4 semanas.
- **Datos nuevos:** API REST de Wikimedia, `metrics/pageviews/per-article/en.wikipedia/all-access/user/Bitcoin/daily/2015070100/2026053100`. Es una sola solicitud; se guarda la respuesta cruda con su SHA-256, la URL, el estado HTTP y la fecha.
- **Variable:** A(t) = ln(media de las vistas de t−7 … t−1 / media de las vistas de t−35 … t−29), usando solo hasta d−1.
  - Si falta algún día de esas ventanas, A queda indefinida, sin relleno.
- **Base:** y = a + b·M(t), con M = ln(C_t / C_{t−28}). **Aumentada:** + c·A(t).
- **Objetivo:** y = ln(C(t+7) / C(t)), solo BTC.
- **Muestra:**
  - el entrenamiento empieza el primer día con M y A definidas (≈ 2017-09-14; los precios locales empiezan el 2017-08-17);
  - el primer pronóstico es el primer t con al menos 180 observaciones de entrenamiento realizadas (≈ 2018-03);
  - los pronósticos llegan hasta el último t con t + 7 ≤ 2026-05-31.
- **Prueba:** Clark–West con Newey–West (rezagos = 7); p_C unilateral; además ΔR²_OOS.
- **Decisión de E2-C:**
  - **FAVORABLE (información incremental):** p_C pasa Holm entre experimentos y ΔR²_OOS > 0.
  - **EN CONTRA:** ΔR²_OOS ≤ 0 y p_C sin ajustar ≥ 0,10.
  - **INSUFICIENTE:** cualquier otro caso.
  - **INCONCLUSO** si faltan más del 5 % de los días de pronóstico por huecos en las vistas.
- **Limitación conocida:** en 2020 Wikimedia empezó a separar el tráfico «automated» del «user», lo que puede generar un escalón. No se ajusta; la variable de cambio de 4 semanas lo absorbe salvo en unos 35 días alrededor del cambio. Se informa.

## 4. Lo que queda fuera
- Variantes de umbrales, de ventanas o de horizontes.
- Otros activos o artículos.
- Reglas de trading para E2-A y E2-C.
- Breakout y confianza en ETH o SOL (no autorizado).
- Cualquier otra familia.
