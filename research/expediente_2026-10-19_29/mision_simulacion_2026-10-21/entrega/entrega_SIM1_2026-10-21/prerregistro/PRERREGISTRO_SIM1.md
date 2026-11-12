# Prerregistro SIM-1: simulación histórica del bot con el motor corregido

**Estado:** se fija por SHA-256 **antes** de leer cualquier retorno de los datos nuevos.
- Los datos nuevos ya están descargados y verificados contra su `.CHECKSUM` oficial.
- Sobre ellos solo se calcularon cobertura, huecos, coherencia OHLC y decimales (`resultados/calidad_datos.json`).
- No se calculó ningún retorno, nivel de precio ni resultado de estrategia.

**Fecha:** 2026-10-21. **Autor:** Claude (asistente de investigación), por encargo del propietario.
- No hay firma: el hash se fija en `prerregistro/HUELLAS.txt`.
- No hay ancla externa: D-G4 y R-5 siguen pendientes del propietario.

## 1. Qué se sabe antes de empezar (contaminación declarada)
- **BTCUSDT 1h, 2019-10 → 2026-05:** E1 corrió ahí las estrategias del bot. Todas salieron **EN CONTRA**:
  - P1 −0,237 %/op., P2 −0,519 %, P3 −0,198 %, S1 −0,294 %;
  - bruto medio ≈ 0: P3 +0,002 %, P1 −0,037 %;
  - costos ≈ 0,2 % de comisión más el deslizamiento por round trip.
- **BTC y ETH diarios, 2017-08 → 2026-05:** ya vistos en T, T-MULTI y E2. Se conoce su trayectoria general.
- **Nunca se pasaron por el bot:**
  - **ETHUSDT 1h** (ningún período);
  - **BTCUSDT 1h, 2017-08 → 2019-09**.
- **No se usan ni se descargan:**
  - SOL ni otras altcoins: su historia queda para la prueba confirmatoria pendiente de E3-H1;
  - nada desde **2026-06-01**: es el período reservado de H-CARRY.
- **Efecto sobre H-E1-BC:** al correr `breakout` en ETH 1h, su pata ETH queda **consumida**.
  - Si el propietario decidiera iniciarla algún día (D-G1, hoy con recomendación «no iniciar»), solo quedaría SOL o la vía prospectiva.
  - Se declara aquí como consecuencia.

## 2. Motor (versión técnica fija)
- Paquete `tia` en `mision_simulacion_2026-10-21/trader-ia` = HEAD `72ffae5` más el parche de D1–D3 en `tia/backtest/engine.py` y `tia/execution/paper.py`.
  - Su hash queda en `HUELLAS.txt`.
- Correcciones respecto del original:
  - **D1:** id único por intento de salida y de stop;
  - **D2:** el stop sigue el nivel de la pierna;
  - **D3:** el resto de una entrada parcial se cancela al salir y en plano, y una salida terminada con posición restante libera la pierna.
- Verificación:
  - pruebas que fallan con el motor original y pasan con el corregido (`evidencia/S1b_*`);
  - la suite completa pasa (1960);
  - paridad con E1 (`evidencia/S2_*`).
- Las estrategias son las de `tia.strategy.library` **sin cambios** (v1.1.0).
- No se ajusta ningún parámetro de estrategia salvo M1 (§6), bajo su regla.

## 3. Datos
- **Fuente:** data.binance.vision, klines spot mensuales de 1 h, verificados contra `.CHECKSUM` antes de leerlos.
  - Para BTC, además, los 16 archivos diarios de E1 y su regla de conflictos.
- **Tratamiento:** el de E1. Sin relleno; la misma hora con valores distintos se trata como faltante. Tiempos en UTC.
- **Filtros del instrumento:**
  - BTCUSDT: tick 0,01, lote 1e-5, nocional mínimo 5 (E1).
  - ETHUSDT: tick 0,01, inferido de los decimales; lote 1e-4 y nocional mínimo 5 son **[Hip]**.
  - Efecto del lote: menos de 0,04 % de una posición de ≈ 1000 USDT.
  - La API de filtros de Binance no es accesible desde aquí; ver `registro/INCIDENTE_01_*`.

## 4. Períodos (fijos)
| Conjunto | Activo | Velas (open_time UTC) | Uso |
|---|---|---|---|
| **DEV-BTC** | BTCUSDT | 2017-08-17 → 2026-05-31 | Desarrollo. 2019-10+ ya visto en E1 |
| **DEV-ETH** | ETHUSDT | 2017-08-17 → **2022-12-31 23:00** | Desarrollo |
| **OOS-ETH** | ETHUSDT | **2023-01-01 00:00** → 2026-05-31 23:00 | **Prueba final, una sola lectura** |

- **DEV** corre con `warmup_bars = 120`, como E1.
- **OOS-ETH** es una corrida aparte:
  - empieza 299 velas antes del corte, con `warmup_bars = 300`, así que la primera decisión es al cierre de la primera vela ≥ 2023-01-01;
  - capital inicial: 100 000 USDT en el corte;
  - las 299 velas previas son solo historia para los indicadores.
- La liquidación forzada al final de cada corrida se excluye de las métricas por operación (regla de E1).
- **OOS-ETH no se corre ni se lee** hasta que el código final esté congelado por hash (§8).
  - El script lo hace una sola vez y deja un candado.

## 5. Estrategia elegida y configuraciones
**Primaria: P3 = `breakout`, solo largos.** Por qué:
- es la única del bot con bruto ≥ 0 en desarrollo (+0,002 %/op. en BTC);
- es la menos negativa en neto;
- su señal de confianza mostró orden exploratorio (ρ +0,22, sesgado);
- las otras tienen el bruto negativo (P1, P2, S1).

Elegir P3 no significa esperar que gane: el prior, por E1, es negativo.

**Reglas** (las del bot; se resumen, no se cambian):
- **Entrada:** señal `breakout` con confianza ≥ 0,55 (límite de riesgo por defecto). Orden de mercado a la apertura de la vela siguiente.
- **Salida:** stop protector inicial de la estrategia; break-even tras 1R; trailing de 2 ATR; objetivo de la estrategia; reversión de señal.
  - No hay stop por tiempo, porque `max_holding_bars` = 0.
- **Tamaño:** `RiskBudgetEngine` del bot, perfil conservador, con escalado por convicción. En E1 resultaron posiciones ≈ 1 % del capital.
  - Gobernador de caída apagado y `max_drawdown_pct` = 90 en la primaria (como E1), para medir la regla por operación.
  - S6 los enciende.
- **Exposición:** una pierna por símbolo; sin apalancamiento; sin cortos.
- **Costos (E1):**
  - comisión de 10 bps por lado;
  - deslizamiento base de 2 bps, más el componente de rango, más un impacto de 0,35;
  - stops al peor precio;
  - capital inicial de 100 000; semilla 20261019.

**Secundarias (replicación de E1):** P1 `trend_following`, P2 `mean_reversion` y S1, la fusión de las tres.

**Sensibilidades** (las cuatro configuraciones en DEV-ETH y OOS-ETH; en DEV-BTC solo S2 y S4, porque E1 ya corrió S3 y S6 en BTC 2019-10+ y cada corrida de BTC tarda ≈ 15 min):

| Sensibilidad | Cambio |
|---|---|
| S2 | Comisión ×2 (20 bps) |
| S3 | +1 vela de latencia |
| S4 | Sin costos (bruto) |
| S6 | Gobernadores en vivo |

**Referencias** (mismas ventanas):
- comprar y mantener ETH (o BTC);
- efectivo;
- cruce de medias 20/50 long/flat;
- volatilidad objetivo del 15 %;
- nulo de entrada aleatoria emparejada de E1: mismas duraciones, estratificado por trimestre, 2000 réplicas.

## 6. Mejora candidata M1, fijada ahora y decidida solo con DEV
- **M1:** P3 con `RiskLimits.min_confidence = q`.
  - `q` es el percentil 66,67 de la confianza de entrada de las operaciones de P3 base **en DEV del mismo activo**: q_ETH con DEV-ETH y q_BTC con DEV-BTC.
  - Se ejecuta en el motor; no es un filtro posterior de operaciones.
- Se corre M1 base en DEV-BTC y DEV-ETH, y S2 y S4 de M1 en DEV-ETH (y en OOS si se promueve).
- **M1 pasa a OOS solo si**, en DEV:
  - M1 tiene al menos 30 operaciones en cada activo;
  - la media neta por operación de M1 es > 0 en BTC **y** en ETH;
  - **y** el IC90 bootstrap mensual de la media combinada tiene un límite inferior > 0.
- Si no pasa, se informa como «no promovida» y no se mira en OOS.
- **No hay otras mejoras de estrategia** antes de OOS.

**Defectos técnicos que aparezcan en DEV:**
- se corrigen en el motor, con una prueba de regresión;
- se vuelven a correr todas las corridas DEV;
- se registran en `registro/`.

Un resultado económico malo **no** es un defecto técnico.

## 7. Métricas (por configuración y conjunto)
- **Capital:**
  - capital inicial y final;
  - retorno neto total y anualizado;
  - volatilidad anualizada (de la curva diaria);
  - Sharpe y Sortino diarios anualizados (√365), con un IC90 del Sharpe por bootstrap de bloques mensuales;
  - máxima caída;
  - exposición: % de velas en mercado.
- **Por operación:**
  - n, media neta (% del nocional), mediana;
  - tasa de acierto, ganancia media, pérdida media, factor de beneficio;
  - peor racha;
  - media bruta, comisiones medias, barras medias;
  - motivos de salida.
- **Costos:**
  - comisiones totales en USDT y en % del nocional;
  - costo total implícito = media S4 − media base;
  - sensibilidad S2, S3 y S4.
- **Por período:**
  - DEV-BTC: 2017-08→2019-09, 2019-10→2021-12, 2022, 2023→2026-05;
  - DEV-ETH: 2017-08→2019-12, 2020→2021, 2022;
  - OOS: 2023, 2024, 2025-01→2026-05.
- **Por condición de mercado (régimen ex ante, regla de E1):** retorno de 30 días (720 velas) antes de la entrada. Alcista > +10 %, bajista < −10 %, lateral en el resto.
- **Incertidumbre:**
  - IC90 de la media neta por bootstrap de bloques de mes calendario (B = 10 000, semilla 20261019);
  - p unilateral = 1 − P(media* > 0);
  - nulo de entrada aleatoria (p_nulo).
- **Confianza:** ρ de Spearman entre confianza y neto, con IC90 bootstrap mensual. Es descriptivo.

## 8. Decisión en OOS-ETH (única lectura)
**Validez antes de interpretar** (si falla, se detiene sin interpretar):
- checksums;
- invariancia de prefijo en DEV-ETH: S1 completo contra el prefijo del 70 %, con decisiones y operaciones idénticas antes del corte;
- determinismo: P3 en DEV-ETH corrido dos veces da la misma huella;
- 0 operaciones cortas;
- ningún round trip de más de 2000 velas;
- stops sin colocar ≤ 3 % de las velas en mercado;
- se informan los contadores de higiene de órdenes y las advertencias del motor.

**Veredicto por configuración** (P3 primaria con α = 0,05 unilateral; P1, P2, S1 y M1, si fue promovida, con Holm entre las secundarias):
1. n < 30: **INSUFICIENTE (muestra)**.
2. Límite superior del IC90 de la media neta < 0: **EN CONTRA**.
3. **VENTAJA RESPALDADA (histórica)** si se cumplen todas:
   - p ≤ α (Holm en las secundarias);
   - p_nulo ≤ 0,05;
   - media > 0 en cada subperíodo OOS;
   - media de S2 (comisión ×2) > 0.
4. En otro caso: **NO CONCLUYENTE**.

**Consecuencia operativa:**
- Ningún resultado cambia `validada_para_operar` ni habilita capital.
- Una «ventaja respaldada» histórica solo justificaría proponerle al propietario una fase prospectiva en papel, con su propio prerregistro.

## 9. Orden de ejecución
1. Fijar los hashes de este documento, del código y del motor (`HUELLAS.txt`).
2. Correr DEV: BTC, ETH, sensibilidades, M1, validez y determinismo. Analizar y diagnosticar causas.
3. Si hay defectos técnicos: corregirlos, probarlos, re-correr DEV y re-fijar los hashes (adenda con hora, antes de OOS).
4. Congelar el código final (adenda de huellas) y correr OOS-ETH **una vez**: `sim1.py --final`, con candado.
5. Escribir el informe con todo, incluidos los fracasos.
