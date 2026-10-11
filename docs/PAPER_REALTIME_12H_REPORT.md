# Informe forense — simulación paper-live de 12 h con política `real_only`

Corrida `live_01M4BP8GBCYAV30YAECK2H1RJ3` · código `ab68d1c` · 2026-10-07 17:23:35Z → 2026-10-08 05:23:45Z

Compañero post-corrida de `PAPER_REALTIME_12H_AUDIT.md`. Todo lo que sigue sale del paquete
`paper12h_20261007T171850Z/PACK.txt` (13 checkpoints, 718 muestras de equity, filas de la base,
velas públicas de BTC), de las consultas de cierre de §11 y del código en `ab68d1c`. Nada se
modificó, reinició ni desplegó durante la ventana. Cada métrica lleva su clasificación:
**MEASURED** (leída tal cual de API, base o venue), **RECONSTRUCTED** (derivada de muestras o de
filas crudas) o **NOT_PERSISTED** (el runtime no la guarda).

## 0. RESULTADO 12H

| | |
|---|---|
| Duración efectiva | 12 h 0 min 10 s (stop oficial `POST /api/live/stop`, fila `runs.stopped_at` sellada) |
| Invariantes de seguridad | `simulated_only=true`, `activation=null`, `mode=paper-live`, 0 runs en modo live, 0 órdenes fuera de esta corrida (orders 4 → 8), ejecución `PaperExecutionProvider` |
| Infraestructura | 0 reinicios backend/postgres, 0 reconexiones del feed, 0 incidentes, 365/365 reconciliaciones limpias, skew 114–124 ms (umbral 2.500) |
| Velas procesadas | 721 (720 cerradas por WebSocket + 1 de la historia inicial) |
| Embudo | 721 evaluadas → 148 accionables → 0 silenciadas → 89 riesgo → 1 posición abierta → 3 orden en reposo → 53 valor esperado → **2 órdenes** |
| Trades | 2, ambos `trend_following` short en régimen `trending_down`, ambos exploratorios, ambos cerrados por stop protector en 1–2 velas |
| P&L | **−4,45 USD (−0,0445 %)**: bruto −2,44 USD, comisiones −2,00 USD |
| Equity | 10.000,00 → 9.995,55; drawdown máximo −4,45 USD (−0,0445 %) a las 04:08:18Z; exposición ≈ 3 min de 720 (0,4 %) |
| BTC en la ventana | 83.426,01 → 82.932,00 (−0,592 %); buy-and-hold de 10.000 USDT = −59,22 USD |
| Scoreboard `real_only` | 0 trades juzgados en las tres estrategias; 2.960 filas sintéticas excluidas (2.446 / 493 / 21); ninguna estrategia silenciada |
| Contrafáctico legacy | con la evidencia sintética, `trend_following` y `mean_reversion` habrían estado silenciadas desde la primera vela: **las 2 órdenes de la sesión existen solo por `real_only`** |
| Procedencia de las 2 filas nuevas | `source=live`, `market_data=real`, `execution_mode=simulated`, `strategy_version=1.1.0` |

**Lectura en una frase.** La Fase 1 hizo exactamente lo que especifica: el scoreboard dejó de
escuchar la evidencia sintética, no silenció a nadie y por eso existieron dos trades que legacy
habría frenado en el gate de mute. Pero la restricción vinculante se mudó al gate de valor
esperado, que sigue alimentado por las mismas 265.611 filas sintéticas sin filtro de procedencia y
declaró `disproven` 53 de las 55 señales que llegaron hasta él. Las únicas dos órdenes fueron
exploratorias, y las filas exploratorias nunca cuentan como juzgadas: bajo `real_only`, tal como
está hoy, el scoreboard no puede acumular evidencia real.

## 1. Identidad de la corrida y condiciones

- Pre-flight: 16/16 PASS (`PAPER12H_PREFLIGHT_READY`), HEAD `ab68d1c`, árbol limpio, alembic
  `0007`, schema 7, baseline 265.611 outcomes / 0 reales / 4 órdenes / 0 runs live.
- Configuración efectiva (redactada): `scoreboard_policy=real_only`, `use_testnet=true`,
  `live.enabled=false`, `mm.real_money=false`, símbolo BTC-USD 1 m, `market_stream=true`,
  datos públicos Mainnet (`https://api.binance.com`, `wss://stream.binance.com:9443/stream`),
  entrada limit con timeout 3 velas, EV ≥ 5 bps, `max_cost_ratio=0.6`, spread ≤ 10 bps, HTF modo
  `hard` 1 h, exploración 20/día con fracción 0,25, cap 20 trades/día, perfil `balanced`, capital
  10.000, leverage máx 5, funding cargado, `max_holding_bars=0`, trailing 2×ATR, break-even a 1R.
- `settings_market_data.provider=synthetic` aplica a entrenamientos y backtests; el arranque
  paper-live construye a mano el proveedor público de Binance (`state.py:2212-2226`), como
  confirma la URL del feed en el snapshot.
- Arranque 17:23:35Z (14:23:35 ART). Fin teórico 05:23:35Z; el monitor detectó el fin a
  05:23:36Z, capturó la ventana final y envió el stop a 05:23:45Z.
- Marea HTF (`live.trend`, 12 lecturas horarias): `bias=flat` toda la ventana, z 1 semana entre
  −0,04 y −0,26 sd, z 4 semanas entre +0,58 y +0,71 sd (retorno 4 semanas +5,6 a +6,8 %):
  "no agreed tide beyond ±1sd". En modo hard una marea plana no rechaza nada.

## 2. Integridad operativa — MEASURED

| indicador | valor |
|---|---|
| Estados del runtime vistos en 718 muestras | solo `running` (luego `stopped` por el operador) |
| Reinicios backend / postgres | 0 / 0 |
| Health | `ok`, `degraded=[]`, `simulated_only=true` en los 13 checkpoints |
| Feed | WebSocket, 3.661.420 mensajes (~85/s), 720 velas cerradas, 0 reconexiones, `last_error` vacío |
| Latencia evento→proceso | 5.252 ms en el primer evento y EMA 3.782 ms a t+0 (calentamiento: carga de 1.500 velas de historia); EMA 2.608 ms a t+3 s; 118–127 ms estable desde el checkpoint 001 |
| Skew contra Binance | 114–124 ms, `ok=true`, `skew_halts=0`; VPS sincronizado por NTP |
| Reconciliaciones | 365, 365 limpias, 0 rupturas (una cada ~2 min) |
| Watchdog de datos | `market_data_age_s` entre 4,8 y 55,9 s en checkpoints (menor al TTL); `quality_skipped=0` |
| Recursos del contenedor | CPU 0,55–6,93 %, memoria 428 → 447 MiB |
| `last_error` / líneas de error filtradas en logs | vacío / 0 en todos los checkpoints |
| Incidentes (tabla `incidents`, consulta corregida) | 0 |
| Cobertura del feed de actividad | 142 eventos `live.no_trade` deduplicados entre checkpoints = 89 riesgo + 53 EV, exactamente el embudo: ninguna hora perdió eventos |

## 3. Embudo de decisiones — MEASURED

Contadores acumulados al cierre (checkpoint `final_window`, idénticos en `post_stop`):

| etapa | señales | % de accionables | notas |
|---|---|---|---|
| evaluadas | 721 | | una por vela |
| no accionables | 573 (79,5 %) | | sin señal operable |
| accionables | 148 (20,5 %) | 100 % | |
| silenciadas (scoreboard) | 0 | 0 % | **efecto `real_only`** (ver §6) |
| riesgo | 89 | 60,1 % | ver desglose |
| posición abierta | 1 | 0,7 % | trade 2, vela 04:07 |
| orden en reposo | 3 | 2,0 % | trade 1, velas 02:14–02:16; artefacto, ver §4 |
| marea HTF | 0 | | `bias=flat` toda la ventana |
| spread | 0 | | `max_spread_bps=10` nunca excedido |
| presupuesto / capital / halt | 0 / 0 / 0 | | |
| valor esperado | 53 | 35,8 % | `ev_disproven=53`, `ev_unproven=2`, `ev_unknown=0` |
| guardrail | 0 | | |
| exploración | 2 | 1,4 % | los 2 `unproven` → trades exploratorios, `sized_down=2` |
| órdenes | 2 | 1,4 % | |

Contabilidad: 148 = 89 + 1 + 3 + 53 + 2. Cierra exacto.

Desglose del gate de riesgo (89). El runtime conserva solo las 8 razones más frecuentes:
`position cannot be sized: stop_too_close` 23; `volatility at the 100.0% percentile exceeds the
97.0% limit` 5 (aparecen entre 03:24Z y 05:23Z, durante la caída a 82.227); las 61 restantes son
`confidence X below minimum 0.550` con X entre 0,234 y 0,523 (RECONSTRUCTED: 89 − 23 − 5; las
razones por debajo del top 8 son con alta probabilidad del mismo tipo; los 89 eventos
`live.no_trade` de etapa `risk` están en los `activity.json` de los checkpoints si hiciera falta
el detalle exacto).

Evolución horaria de accionables / riesgo / EV / órdenes: 39/22/17/0 (1 h), 43/25/18/0 (2 h),
50/26/24/0 (3 h), 65/35/30/0 (4 h), 65/35/30/0 (5 h), 68/38/30/0 (6 h), 81/51/30/0 (7 h),
93/55/38/0 (8 h), 115/72/40/1 (9 h), 131/76/52/1 (10 h), 139/80/53/2 (11 h), 148/89/53/2 (12 h).
La actividad se concentró en la segunda mitad, cuando el mercado cayó.

## 4. Trades — MEASURED (filas `edge_outcomes`, `fills`, `orders` y eventos de actividad)

| | trade 1 | trade 2 |
|---|---|---|
| outcome | `edge_NZZW6FP6FFPTMF3GWTCEYJEP` | `edge_C21P7RNW7XPZKEXYB82C2Q2Y` |
| señal / confianza | `sig_CEMC3M5CQEAQRFYAMPDSZC1Z` / 0,891 | `sig_B3F7VZ8VMWAFJH1BN0SG9QGD` / 0,920 |
| estrategia / dirección / régimen | trend_following / short / trending_down | trend_following / short / trending_down |
| exploratorio / versión | sí (`unproven`) / 1.1.0 | sí (`unproven`) / 1.1.0 |
| orden de entrada | limit sell 0,01204375 @ 83.038,31 · 02:13:00Z · timeout 3 velas | limit sell 0,012093 @ 82.682,90 · 04:05:00Z · timeout 3 velas |
| fill de entrada | 0,012043 @ 83.026,00 · 02:13:59.999Z · maker · fee 0,2500 · slip 1,483 bps | 0,012093 @ 82.681,15 · 04:06:59.999Z · maker · fee 0,2500 · slip 0,211 bps |
| stop protector | buy stop 0,012043 @ **83.111,10** (entrada +10,25 bps) · colocado 02:14:00Z | buy stop 0,012093 @ **82.751,00** (entrada +8,45 bps) · colocado 04:07:00Z |
| fill de salida | 0,012043 @ 83.116,49 · 02:15:59.999Z · taker · fee 0,7507 · slip 0,649 bps (= 0,65 bps más allá del stop) | 0,012093 @ 82.793,09 · 04:07:59.999Z · taker · fee 0,7509 · slip 0,000 (5,09 bps más allá del stop: la vela saltó el nivel y el simulador llenó al precio de la vela) |
| nominal | 999,88 USD | 999,86 USD |
| duración | 2 velas (1 vela en reposo + 2 en posición) | 1 vela (2 en reposo + 1 en posición) |
| movimiento adverso | +10,9 bps | +13,5 bps |
| bruto / comisiones / neto | −10,899 / 10,008 / **−20,907 bps** | −13,539 / 10,010 / **−23,549 bps** |
| USD | −2,09 | −2,35 |
| motivo de salida | protective stop | protective stop |

Observaciones:
- Comisión de ida y vuelta 10,0 bps (2,5 maker + 7,5 taker). Los stops estaban a 10,25 y 8,45
  bps de la entrada: **la distancia del stop estuvo en el orden de la comisión total**. Con la
  volatilidad observada (σ de 1 minuto ≈ 4 bps) un stop así se toca con un movimiento de 2–3 σ en
  una o dos velas, que es exactamente lo que pasó.
- Latencia modelada 180 ms en los 4 fills; fills al cierre de vela (`xx:59.999`): simulador por
  velas, no por libro. La entrada limit de venta a 83.038,31 se llenó a 83.026,00 (1,48 bps peor
  que el límite): el simulador aplica slippage también a fills maker, cosa que un venue real no
  hace con una limit. En el trade 2 el stop se llenó 5,09 bps más allá de su nivel con slippage
  registrado 0: el salto de vela por encima del stop se llena al precio de la vela, no al del stop.
- **La orden "vencida" es un artefacto de precisión de cantidad.** La orden de entrada del trade 1
  salió con 0,01204375 BTC (8 decimales) porque en paper-live `LiveRuntime` no recibe filtros del
  venue (`symbol_filters` solo se cargan en el camino MM/live, `state.py:1435-1448`) y
  `_build_intent` no cuantiza sin `step_size`. El simulador llenó 0,012043 (redondeo al lote,
  `instruments.round_quantity`), dejó un residuo de 0,00000375 BTC y la orden quedó
  `PARTIALLY_FILLED`, no terminal. `_check_resting` la siguió tratando como en reposo: las tres
  señales de las velas 02:14–02:16 se rechazaron como `resting` (deberían haber sido
  `position_open`), y a las 3 velas la canceló y contó `orders_expired=1` (evento
  `live.order_expired` 02:16:00Z, `waited_bars=3`, `reducing=false`) sobre una posición que ya
  había abierto y cerrado. La orden del trade 2 salió con 6 decimales, se llenó exacta, fue
  terminal y el rechazo siguiente fue `position_open`, como corresponde. No afectó el P&L; sí
  contamina el embudo y los contadores.
- **La tabla `orders` solo refleja la colocación.** Las 4 filas de la corrida están en
  `acknowledged`, `filled_quantity=0`, `fees_paid=0`, incluidos los dos stops que se ejecutaron y
  la entrada del trade 2 que se llenó completa. `_save("order")` se invoca al colocar
  (`live.py:1483`, `1906`) y en salidas a mercado (`1546`, `1999`), nunca al recibir el fill de
  una orden ya colocada. La verdad de ejecución está en `fills`; `orders` no sirve para leer
  estados ex-post.
- Fracción de exploración 0,25 sobre el tamaño aprobado (`sized_down=2`); `leverage_used=0` en
  todos los checkpoints porque ninguna posición estaba abierta al tomarlos.

## 5. Capital y curva de equity

| métrica | valor | clasificación |
|---|---|---|
| equity inicial / final | 10.000,00 / 9.995,55 USD | MEASURED |
| retorno | −0,0445 % | MEASURED |
| realizado / comisiones | −4,445 / 2,0016 USD | MEASURED |
| no realizado al cierre | 0 (sin posición) | MEASURED |
| máximo / mínimo de equity | 10.000,00 / 9.995,55 | RECONSTRUCTED (718 muestras cada 60 s) |
| drawdown máximo | −4,45 USD (−0,0445 %) a las 04:08:18Z | RECONSTRUCTED |
| muestras con posición abierta | 3 de 718 (≈ 3 min, 0,4 % de la ventana) | RECONSTRUCTED |
| liquidaciones / funding | 0 / 0 pagos (`last_rate=null`: sin tasa disponible, `skipped_no_rate=0`) | MEASURED |
| trayectoria intra-minuto del equity | — | NOT_PERSISTED |

## 6. Scoreboard, procedencia y contrafáctico legacy — MEASURED

| estrategia | trades | exploratorios | juzgados | silenciada | faltan | sintéticas excluidas |
|---|---|---|---|---|---|---|
| trend_following | 2 | 2 | 0 | no | 30 | 2.446 |
| mean_reversion | 0 | 0 | 0 | no | 30 | 493 |
| breakout | 0 | 0 | 0 | no | 30 | 21 |

- Las 2 filas nuevas quedaron en `edge_outcomes` con `source=live`, `market_data=real`,
  `execution_mode=simulated`, `strategy_version=1.1.0`; `edge_total` 265.611 → 265.613,
  `edge_real_total` 0 → 2. Es el primer registro con procedencia real de la base.
- Regla de mute (`scoreboard.py`): juzgados ≥ 30 y media + 1,0·SE < 0; los exploratorios se
  registran pero nunca juzgan. Con 2 trades exploratorios y 0 juzgados, el silencio por evidencia
  real es imposible por construcción en esta ventana.

Contrafáctico legacy, reconstruido sobre las filas sintéticas con la misma regla (todas las
sintéticas son no exploratorias):

| estrategia | sintéticas | media bps | SE bps | media + SE | legacy la silenciaría |
|---|---|---|---|---|---|
| trend_following | 2.446 | −15,83 | 0,61 | −15,2 | **sí** |
| mean_reversion | 493 | −22,50 | 1,09 | −21,4 | **sí** |
| breakout | 21 | −23,26 | 8,33 | — | no (menos de 30) |
| sin `strategy_id` | 262.651 | −8,16 | 0,16 | −8,0 | sí, pero solo afecta a señales sin estrategia (no hubo) |

Consecuencia: bajo legacy, toda señal de `trend_following` o `mean_reversion` habría muerto en el
gate de mute, antes de riesgo y de EV. Las dos órdenes de la sesión eran `trend_following`:
**no habrían existido sin `real_only`**. Cuántas de las 148 accionables pertenecían a esas dos
estrategias no se puede saber (NOT_PERSISTED, §9); como mínimo las 2 que llegaron a orden.

## 7. Benchmark BTC — MEASURED (720 velas 1 m públicas, 0 huecos)

| | |
|---|---|
| apertura / cierre | 83.426,01 / 82.932,00 (−0,592 %) |
| máximo / mínimo | 83.606,01 (+0,22 %) / 82.227,56 (−1,44 %) |
| volatilidad | σ 1 m 0,0398 %; ventana 1,066 %; anualizada 28,8 % |
| buy-and-hold 10.000 USDT | −59,22 USD |
| bot | −4,45 USD |
| diferencia | +54,77 USD a favor del bot, con exposición de ≈ 3 minutos: es un resultado de estar en caja, no de la estrategia |

## 8. Hallazgos

- **H1 — La Fase 1 se comporta como se especificó.** Invariantes de seguridad intactas 12 h;
  `muted=0` en los 13 checkpoints; las filas reales se etiquetaron correctamente y el scoreboard
  las acreditó como trades sin juzgarlas (exploratorias). El contrafáctico de §6 prueba que el
  cambio tuvo efecto observable: dos trades que legacy habría frenado.
- **H2 — La restricción vinculante se mudó al gate de valor esperado.** `_load_live_evidence`
  usa `EdgeStateRepository.load_all()` sin filtro de procedencia y `LiveRuntime` vuelca todo en el
  `EdgeEstimator` (`live.py:311`). Las 53 señales `disproven` lo fueron por evidencia sintética.
  Incluso el mejor bucket sintético (trending_down/short en la banda de confianza de los dos
  trades: +19,2 bps de media sobre 12.444 trades) no resultó operable: el estimador descuenta la
  media en SE, la recorta a la ventana reciente de 60 trades si esta no la sostiene, exige neto
  ≥ 5 bps después de ~11 bps de costos y rechaza si los costos superan el 60 % del bruto. Quedó
  `unproven` y solo entró como exploración al 25 % del tamaño.
- **H3 — Bajo `real_only`, el scoreboard no puede acumular evidencia real.** Los únicos trades
  posibles mientras todos los buckets estén `disproven` o `unproven` son exploratorios, y los
  exploratorios no juzgan. Sin un cambio de diseño, `judged` se queda en 0 indefinidamente.
- **H4 — Geometría del stop en velas de 1 m.** Stops a 8,45 y 10,25 bps de la entrada, tocados
  en 1–2 velas, con comisiones de 10,0 bps por ida y vuelta, más 23 rechazos `stop_too_close` en
  riesgo. Un stop del orden de la comisión necesita una tasa de acierto muy alta para ser
  positivo. Basado en 2 trades: es una señal para revisar, no una conclusión estadística.
- **H5 — El gate de riesgo es el mayor filtro (89 de 148).** Confianza por debajo de 0,55 (~61),
  stop demasiado cerca (23) y percentil de volatilidad (5, durante la caída).
- **H6 — Infraestructura impecable.** Ningún reinicio, reconexión, incidente, ruptura de
  reconciliación ni halt por reloj en 12 h; la latencia de 5 s del arranque es calentamiento, no
  desfase de reloj.
- **H7 — Cantidad sin cuantizar en paper-live (bug).** Sin `symbol_filters`, una orden puede
  salir con más decimales que el lote del simulador; el residuo deja la orden no terminal, el
  runtime la trata como en reposo, rechaza señales por el motivo equivocado y la "vence" tras 3
  velas aunque la posición ya haya abierto y cerrado (§4). Sin efecto en P&L; sí en embudo y
  contadores.
- **H8 — `orders` no se actualiza después de la colocación (observabilidad).** Estados y
  cantidades llenadas no se persisten; `fills` es la única fuente ex-post.
- **H9 — Defectos del instrumental (míos, no del sistema).** Cuatro consultas agregadas del
  checkpoint (`orders_run_by_state`, `fills_run_by_liquidity`, `edge_run_by_strategy`,
  `incidents_run`) tenían `GROUP BY` sobre el literal y fallaron; se cerraron con las consultas de
  §11 y los volcados por fila.

## 9. Limitaciones y clasificación de métricas

- **MEASURED**: embudo y contadores (API), órdenes, fills y outcomes con procedencia (base),
  equity y cuenta en checkpoints (API), estado del feed, skew, reconciliaciones, incidentes, fila
  de `runs`, velas de BTC (Binance público), salud y reinicios de contenedores, eventos de
  actividad (cobertura completa verificada contra el embudo).
- **RECONSTRUCTED**: curva de equity y drawdown (muestras cada 60 s), tiempo de exposición,
  benchmark buy-and-hold, desgloses por estrategia y por liquidez (a partir de filas crudas),
  composición de los 61 rechazos de confianza (resta sobre el total), contrafáctico legacy
  (regla del scoreboard aplicada en SQL sobre las filas sintéticas).
- **NOT_PERSISTED**: atribución por estrategia de las 148 señales accionables y de cada rechazo
  (los eventos `live.no_trade` llevan etapa y motivo, no estrategia), trayectoria intra-vela de
  precios y equity, razones de riesgo más allá del top 8 (recuperables de los `activity.json`),
  snapshot de la posición en el instante del stop (las muestras son cada 60 s; 3 la vieron
  abierta), estados finales de las órdenes (ver H8).
- **Modelo del simulador**: fills al cierre de vela con slippage y latencia modelados (180 ms),
  sin libro de órdenes; slippage aplicado también a fills maker; un stop saltado se llena al
  precio de la vela. Las posiciones abiertas no sobreviven un reinicio del proceso (documentado
  en la auditoría previa; no ocurrió).

## 10. Conclusiones — respuestas a las preguntas de la Fase 11

1. **¿`real_only` eliminó los outcomes sintéticos del scoring?** Sí, en el scoreboard: 2.960 filas
   sintéticas excluidas, 0 juzgados, 0 silenciadas, y las 2 filas reales acreditadas con la
   procedencia correcta. No, en el estimador de valor esperado, que no tiene política de
   procedencia y rechazó 53 señales con evidencia sintética.
2. **¿Cuántas señales extra llegaron a gates posteriores?** Las 148 accionables pasaron el gate de
   mute sin un solo rechazo. Bajo legacy, `trend_following` y `mean_reversion` habrían estado
   silenciadas desde el inicio (media + SE de −15,2 y −21,4 bps sobre 2.446 y 493 filas
   sintéticas); cuántas de las 148 eran de esas estrategias no quedó persistido, pero las 2 que
   llegaron a orden sí lo eran y no habrían existido.
3. **¿Alguna estrategia llegó a 30 trades reales juzgados?** No. Máximo 2 trades, ambos
   exploratorios, 0 juzgados. Al ritmo observado (2 exploratorios en 12 h y 0 juzgados) el
   umbral es inalcanzable sin que el gate de EV apruebe entradas no exploratorias.
4. **¿Alguna estrategia fue silenciada por evidencia real?** No. Imposible con 0 juzgados.
5. **¿P&L contra buy-and-hold de BTC?** Bot −4,45 USD (−0,0445 %) contra −59,22 USD (−0,592 %)
   del buy-and-hold. La diferencia de +54,77 USD se explica por 0,4 % de exposición, no por
   acierto direccional: los dos trades perdieron y el 45 % de la pérdida son comisiones.

## 11. Consultas de cierre ejecutadas (solo lectura) y defectos del instrumental

Ejecutadas el 2026-10-09 sobre el VPS, sin escribir nada: filas de `orders` de la corrida (4,
todas `acknowledged`), `incidents` (0), scoreboard legacy reconstruido sobre `edge_outcomes`
con `market_data='synthetic'` (tabla de §6) y deduplicación de los 13 `activity.json`
(142 `live.no_trade` = 89 `risk` + 53 `expected_value`; 12 `live.trend`; 2 `live.exploration`;
2 `live.order_resting`; 2 `live.stop_placed`; 2 `trade.closed`; 1 `live.order_expired`;
2 `live.state`).

Refinamiento opcional, también de solo lectura: el texto exacto con que el gate de EV rechazó
cada una de las 53 señales y el motivo completo de las 2 exploraciones.

```bash
EV=$(cat /home/tia/tia-testnet/paper12h_CURRENT)
python3 - "$EV" <<'PY'
import json, sys, glob, collections, re
ev = sys.argv[1]; seen = set(); ev_reasons = collections.Counter(); risk = collections.Counter()
for f in sorted(glob.glob(f"{ev}/ckpt_*/activity.json")):
    try: rows = json.load(open(f))
    except Exception: continue
    for r in rows if isinstance(rows, list) else []:
        d = r.get("data") or {}; key = (r.get("at"), r.get("type"), d.get("correlation_id"), d.get("stage"))
        if key in seen: continue
        seen.add(key); t = r.get("type")
        if t == "live.exploration": print("EXPLORATION", r.get("at"), d.get("reason"))
        if t != "live.no_trade": continue
        reason = re.sub(r"[-+]?\d[\d,]*\.?\d*", "#", d.get("reason", ""))[:170]
        (ev_reasons if d.get("stage") == "expected_value" else risk)[reason] += 1
print("\nEV refusals by reason pattern:"); [print(n, "|", k) for k, n in ev_reasons.most_common()]
print("\nrisk refusals by reason pattern:"); [print(n, "|", k) for k, n in risk.most_common()]
PY
```

Defectos del instrumental a corregir antes de la próxima corrida: las cuatro consultas con
`GROUP BY 1` sobre el literal de etiqueta (usar `GROUP BY 2[,3…]`), y conservar las filas de
`orders` y los eventos de actividad completos en cada checkpoint, no solo los conteos.

## 12. Decisiones abiertas para la Fase 2 (nada implementado)

1. **Política de procedencia en el `EdgeEstimator`.** Hoy `real_only` cubre solo el scoreboard.
   Opciones: excluir lo sintético del EV (todos los buckets pasan a `unknown` y la exploración
   compra evidencia real a 20/día con dinero simulado), o descontarlo como prior.
2. **Qué cuenta como juzgado bajo `real_only`.** Si los exploratorios reales siguen sin juzgar,
   el scoreboard real no arranca nunca. Alternativa: un contador separado de evidencia real que
   juzgue con su propio mínimo, sin tocar la regla de mute.
3. **Cuantización de cantidad en paper-live (H7).** Pasar filtros de lote al runtime en
   paper-live, o cuantizar en `_build_intent` con el lote del instrumento cuando no haya
   `step_size`, o tratar un residuo por debajo del lote como orden completa en `_check_resting`.
4. **Persistir transiciones de estado de órdenes (H8)** al recibir fills de órdenes ya colocadas,
   para que `orders` sea legible ex-post.
5. **Geometría del stop en 1 m (H4).** Distancia mínima de stop en función del costo de ida y
   vuelta, y revisar `max_holding_bars=0` y el trailing 2×ATR con la volatilidad observada
   (σ 1 m ≈ 4 bps).
6. **Atribución por estrategia de los rechazos.** Persistir `strategy_id` en `live.no_trade` o en
   `decisions` para que el embudo se pueda leer por estrategia ex-post.
7. **Instrumental de monitoreo.** Corregir las consultas de §11 y volcar `orders` y actividad
   completa por fila.
