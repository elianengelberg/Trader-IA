# Trader-IA — Auditoría cuantitativa integral de la simulación paper-live de 12 h

Run `live_01M4BP8GBCYAV30YAECK2H1RJ3` · código `ab68d1c` · ventana 2026-10-07 17:23:35Z → 2026-10-08 05:23:45Z · auditoría escrita el 2026-10-09

Documento de solo lectura. No se modificó código, configuración, credenciales ni base de datos;
no se reinició ningún servicio ni se inició ninguna simulación. Complementa
`PAPER_REALTIME_12H_AUDIT.md` (auditoría previa) y `PAPER_REALTIME_12H_REPORT.md` (informe
forense inicial), y los reemplaza donde discrepa.

Convención de evidencia. Cada afirmación lleva una de estas etiquetas:
**[HECHO]** verificado en código (archivo:línea) o en datos capturados del VPS;
**[INFERENCIA]** deducción directa de hechos verificados;
**[HIPÓTESIS]** explicación plausible no confirmada, con el dato que la confirmaría.
Los datos del VPS provienen de cuatro capturas: pre-flight 2026-10-07 17:18Z, trece checkpoints
horarios y el paquete `PACK.txt` (2026-10-08 05:23Z), consultas de cierre 2026-10-09 ~19:20Z. El
estado de contenedores **hoy** no se verificó en esta sesión: §17 incluye el bloque de refresco.

---

## 1. Resumen ejecutivo

**Veredicto.** La baja actividad no es un bug aislado ni una configuración mal puesta: es una
combinación de (a) un **gate de valor esperado que cuenta los costos dos veces** y etiqueta como
"disproven" cualquier bucket con media no positiva sin exigir significancia; (b) una **evidencia
sintética generada por diseño** (deriva y volatilidad fijadas por escenario) que alimenta sin filtro
de procedencia al estimador de EV y al motor retrospectivo, de modo que la política `real_only`
solo tocó el scoreboard; (c) una **geometría de stop/objetivo en velas de 1 minuto** (stop 2×ATR ≈
8–10 bps, objetivo 3×ATR ≈ 12–15 bps) frente a costos de ida y vuelta de 10–11 bps que exige una
tasa de acierto cercana al 84 % para empatar; y (d) una **circularidad** por la cual las únicas
operaciones posibles son exploratorias y las exploratorias nunca cuentan como evidencia juzgada.

El sistema **funciona técnicamente**: 12 h sin un reinicio, reconexión, incidente ni ruptura de
reconciliación; invariantes de seguridad intactas; procedencia de las dos filas reales correcta.
Eso no dice nada sobre rentabilidad: la expectativa neta de las estrategias en BTC a 1 minuto
**no está medida**, y con las reglas actuales no puede llegar a medirse.

Cuello de botella dominante: el gate de riesgo filtra el 60 % de las accionables (confianza por
debajo de 0,55, stop más cerca que 5 bps, percentil de volatilidad), y el gate de EV filtra el
96 % de lo que sobrevive (53 de 55). El rechazo de riesgo por confianza es coherente con su regla;
el rechazo de EV **no es una inferencia válida sobre el mercado real**.

Estado: **AUDIT_COMPLETE** para el diagnóstico de baja actividad, con tres refinamientos
pendientes de datos del VPS (§13) que afinan magnitudes sin cambiar el veredicto.

---

## 2. Estado de seguridad y configuración (Fase A)

| componente | estado observado | evidencia | riesgo / discrepancia | acción |
|---|---|---|---|---|
| Repo (workspace de auditoría) | rama `claude/algo-trading-simulation-platform-ngf7xo`, HEAD `ab68d1c`, un archivo sin seguimiento (`docs/PAPER_REALTIME_12H_REPORT.md`, informe previo de esta misma sesión) | `git status`, 2026-10-09 | ninguna; sin cambios de código | ninguna |
| Repo (VPS `/home/tia/Trader-IA`) | HEAD `ab68d1c`, árbol limpio | pre-flight 10-07 (`head=`, `dirty=0`) | no re-verificado hoy | bloque §17 |
| Backend | `running/healthy`, 0 reinicios durante toda la ventana; imagen reconstruida desde `ab68d1c` tras el incidente de despliegue del 10-07 | 13 checkpoints (`docker inspect`) | el `deploy.sh` del repo hizo rollback de imagen tras una migración ya aplicada (crash loop `Can't locate revision 0007`, resuelto a mano el 10-07) | P0 operativo, §14 |
| PostgreSQL | `running/healthy`, 0 reinicios; alembic `0007`, `schema_info=7` | pre-flight y checkpoints | ninguna | ninguna |
| Configuración efectiva | `scoreboard_policy=real_only`, `simulated_only=true`, `use_testnet=true`, `live.enabled=false`, `mm.real_money=false`, símbolo BTC-USD 1 m, datos públicos Mainnet | `get_settings().redacted()` en el contenedor, pre-flight | `settings_market_data.provider=synthetic` confunde: aplica solo a entrenamiento; paper-live construye el proveedor público a mano (`state.py:2212-2226`) | documentar |
| Proveedor de ejecución | `PaperExecutionProvider` (`is_simulated=True`), `activation=None` | `state.py:2232-2238`, snapshot `mode=paper-live simulated=true activation=null` | ninguna | ninguna |
| Activación / sesiones reales | 0 runs `mode='live'`, 0 paper-live abiertos tras el stop, `health.live_runtime` sin activación | consultas 10-07, 10-08, 10-09 | tabla `activation_attempts` no consultada | bloque §17 |
| Secretos | ningún valor impreso por el instrumental (settings redactadas, login dentro del contenedor) | scripts `api.sh`, pre-flight | el 10-07 el operador exportó la API key y el secret de Binance en la shell de root y ese texto quedó en el historial y en la transcripción del chat; no afecta a paper-live, que no firma nada | rotar esas claves (fuera del repo); limpiar historial |
| Identidad del run | `live_01M4BP8GBCYAV30YAECK2H1RJ3`, `runs.started_at=17:23:35.285Z`, `stopped_at=05:23:45.462Z`, `initial_capital=10000`, `scenario=realtime` | fila `runs`, `PACK.txt` | ninguna | ninguna |
| Checkpoints y evidencia | `/home/tia/tia-testnet/paper12h_20261007T171850Z/` (13 `ckpt_*`, `equity_samples.csv`, `btc_klines_1m.json`, `PACK.txt`) | `ls` del 10-09 | fuera del repo; sin copia | archivar en `docs/evidence/` si se desea |

---

## 3. Evidencia y metodología

Fuentes: (1) código en `ab68d1c` leído con número de línea; (2) `PACK.txt` con 13 checkpoints del
snapshot `/api/live`, `/api/health`, consultas SQL por `run_id`, logs filtrados y 718 muestras de
equity cada 60 s; (3) consultas de cierre del 10-09: filas de `orders`, `incidents`, scoreboard
legacy reconstruido y deduplicación de los 13 `activity.json` (150 eventos cada uno); (4) 720 velas
públicas 1 m de BTCUSDT de la ventana.

Límites: los eventos `live.no_trade` llevan etapa y motivo pero **no** `strategy_id` ni confianza;
el runtime no persiste decisiones, rechazos, equity ni estados de órdenes tras la colocación
(§4.4); el feed de actividad se capturó cada hora con límite 150 y la deduplicación cubre el 100 %
de los `no_trade` (142 = 89 + 53), por lo que ninguna hora perdió eventos.

---

## 4. Reconstrucción de la ejecución (Fase B)

### 4.1 Línea temporal

| UTC | evento | fuente |
|---|---|---|
| 17:23:14 | WebSocket conectado (`btcusdt@kline_1m/bookTicker`) | snapshot de arranque |
| 17:23:28–35 | `disarmed → arming → armed → running`; `POST /api/live/paper-start`; fila `runs` creada | evento `live.state`, fila `runs` |
| 17:23:35 | HTF leído: `bias=flat` (z 1 sem −0,25 sd, z 4 sem +0,61 sd) | `live.trend` |
| 17:23:38 | ckpt 000: 1 vela de historia evaluada, no accionable; latencia EMA 2.608 ms (calentamiento) | ckpt 000 |
| 18:23 … 04:24 | ckpts 001–011 cada hora; latencia EMA 118–127 ms; skew 114–124 ms; reconciliaciones limpias acumuladas 30, 61, 91, 122, 153, 183, 214, 244, 275, 305, 336 | ckpts |
| 02:13:00.20 | **trade 1**: `live.exploration` (`unproven`), orden limit sell 0,01204375 @ 83.038,31 → `live.order_resting` (timeout 3 velas) | activity, `orders` |
| 02:13:59.999 | fill maker 0,012043 @ 83.026,00, fee 0,2500 | `fills` |
| 02:14:00.17 | stop protector buy @ 83.111,10 (`live.stop_placed`) | activity, `orders` |
| 02:15:59.999 | stop ejecutado taker @ 83.116,49, fee 0,7507; `trade.closed` net −20,907 bps | `fills`, activity |
| 02:16:00.17 | `live.order_expired` sobre la orden de entrada ya ejecutada (residuo de cantidad, §4.4) | activity |
| 04:05:00.17 | **trade 2**: `live.exploration` (`unproven`), limit sell 0,012093 @ 82.682,90 | activity, `orders` |
| 04:06:59.999 | fill maker 0,012093 @ 82.681,15, fee 0,2500 | `fills` |
| 04:07:00.14 | stop protector buy @ 82.751,00 | activity, `orders` |
| 04:07:59.999 | stop ejecutado taker @ 82.793,09 (salto de vela, §9), fee 0,7509; net −23,549 bps | `fills`, activity |
| 05:23:36 | fin de ventana detectado; checkpoint `final_window` | monitor |
| 05:23:45 | `POST /api/live/stop`; `live.state → stopped`; `runs.stopped_at` sellado | activity, fila `runs` |

Velas procesadas 721 (720 cerradas por el stream + 1 de la historia inicial); ciclos 4.389;
`quality_skipped=0`; errores 0; desconexiones 0; reconexiones 0; incidentes 0 (consulta
corregida del 10-09); reconciliaciones 365/365 limpias; reinicios 0; estados vistos solo
`running`. **[HECHO]**

### 4.2 Fichas de los dos trades

| campo | trade 1 | trade 2 | etiqueta |
|---|---|---|---|
| señal | `sig_CEMC3M5CQEAQRFYAMPDSZC1Z` (vela 531) | `sig_B3F7VZ8VMWAFJH1BN0SG9QGD` (vela 643) | observado |
| orden entrada / stop | `ord_MMKQ2A9GFKG57WY1DGC2D6YW` / `ord_00YG7EW0XGR4A1J8FGJE0RCJ` | `ord_FR2Z9JP30B0RT82VX7K7JR47` / `ord_ACKBQQDNREPPNP7MCJNVXQ92` | observado |
| fills | `fill_J9BQ…` (entrada), `fill_56Z1…` (salida) | `fill_3MXJ…`, `fill_PHFC…` | observado |
| outcome | `edge_NZZW6FP6FFPTMF3GWTCEYJEP` | `edge_C21P7RNW7XPZKEXYB82C2Q2Y` | observado |
| t señal / orden / fill / stop / cierre | 02:13:00 / 02:13:00.20 / 02:13:59.999 / 02:14:00.17 / 02:15:59.999 | 04:05:00 / 04:05:00.17 / 04:06:59.999 / 04:07:00.14 / 04:07:59.999 | observado |
| estrategia acreditada / versión | trend_following / 1.1.0 | trend_following / 1.1.0 | observado (ver §4.3 sobre atribución) |
| dirección / régimen | short / trending_down | short / trending_down | observado |
| confianza de la señal | 0,891 | 0,920 | observado (`trade.closed`) |
| precio de referencia (close de la vela de decisión) | ≈ 83.0xx (no persistido; límite = ref + ½ spread) | ≈ 82.68x | desconocido |
| entrada / salida | 83.026,00 / 83.116,49 | 82.681,15 / 82.793,09 | observado |
| cantidad / nominal | 0,012043 BTC / 999,88 USD | 0,012093 BTC / 999,86 USD | observado |
| cantidad aprobada por riesgo | ≈ 0,048175 BTC (≈ 4.000 USD): la orden salió al 25 % (fracción de exploración) | ≈ 0,048372 BTC | reconstruido; restricción vinculante desconocida (decisión no persistida) |
| stop inicial | 83.111,10 = entrada + 10,25 bps (2×ATR ⇒ ATR ≈ 42,6 USD ≈ 5,1 bps) | 82.751,00 = entrada + 8,45 bps (ATR ≈ 34,9 USD ≈ 4,2 bps) | observado (`orders.stop_price`); ATR reconstruido |
| objetivo | entrada − 3×ATR ≈ 82.898 | ≈ 82.576 | reconstruido desde `library.py:44,104` |
| motivo de cierre | protective stop | protective stop | observado |
| movimiento adverso | +10,9 bps en 2 velas | +13,5 bps en 1 vela | observado |
| P&L bruto / comisiones / neto | −10,899 / 10,008 / −20,907 bps = −2,09 USD | −13,539 / 10,010 / −23,549 bps = −2,35 USD | observado |
| otros costos modelados | slippage entrada 1,483 bps, salida 0,649 bps; latencia 180 ms | 0,211 / 0,000 bps; 180 ms | observado |
| MAE / MFE | MAE ≥ 10,9 bps (el stop); MFE no calculable sin velas alineadas | MAE ≥ 13,5 bps | desconocido (recuperable con `btc_klines_1m.json`) |
| por qué se permitió | bucket `trending_down/short/0.85-1.01` clasificado `unproven` (+19,2 bps de media sobre 12.444 trades sintéticos) → exploración con dinero simulado, 25 % del tamaño | ídem (12.445 trades) | observado (`live.exploration`) |
| filtros atravesados | tide (flat) → mute (no) → resting (no) → riesgo (aprobado) → posición (ninguna) → halt/budget/capital (no) → spread (no) → EV (no operable) → exploración (sí) → guardrail (neutral) → sizing ×0,25 | ídem | inferencia desde `live.py:994-1298` |
| información disponible al decidir | velas cerradas hasta la anterior, quote del bookTicker, HTF horario, evidencia sintética cargada al arranque | ídem | hecho |

### 4.3 Atribución: una advertencia

`strategy_id` de la señal = `result.contributing[0].strategy_id` (`strategy/engine.py:170-172`),
donde `contributing=agreeing` conserva el orden de evaluación de las estrategias
(`fusion.py:254,307`), es decir el orden de `StrategyConfig.enabled`: trend_following,
mean_reversion, breakout (`config.py:217`). `breakout` también aplica en `trending_down`
(`library.py:273-275`). **[HECHO]** Por tanto "trend_following" acreditado no excluye que
`breakout` co-firmara la señal; el stop y el objetivo salen de la opinión de mayor fuerza
(`fusion.py:270`), que puede ser otra. **[INFERENCIA]** La atribución por estrategia del
scoreboard es por construcción "la primera de la lista que estuvo de acuerdo".

### 4.4 Lo que la ejecución reveló del runtime

- **Residuo de cantidad y orden "vencida" [HECHO].** `_build_intent` solo cuantiza si hay
  `step_size` (`live.py:1354-1356`); paper-live construye `LiveRuntime` sin `symbol_filters`
  (`state.py:2245-2259`, los filtros solo se cargan en el camino MM, `state.py:1435-1448`). La orden
  1 salió con 0,01204375 BTC; el simulador redondea al lote 1e-6 (`paper.py:282`,
  `instruments.py:92-96`) y llenó 0,012043, dejando 0,00000375 sin ejecutar: la orden quedó
  `PARTIALLY_FILLED`, no terminal. `_manage_resting` (`live.py:1510-1520`) la mantuvo como "en
  reposo" dos velas (rechazos `resting` que eran en realidad `position_open`) y a la tercera la
  canceló y contó `orders_expired=1` sobre una posición ya cerrada. La orden 2 salió con 6
  decimales y fue terminal. Sin efecto en P&L; sí en embudo y contadores.
- **`orders` solo refleja la colocación [HECHO].** Las 4 filas están en `acknowledged`,
  `filled_quantity=0`, `fees_paid=0`. `_save("order")` se invoca al colocar (`live.py:1483`,
  `1906`) y en salidas a mercado (`1546`, `1999`), nunca al recibir un fill de una orden ya colocada
  (`_on_fill`, `live.py:2040-2075`, guarda solo el fill). La verdad de ejecución está en `fills`.
- **Órdenes y fills en memoria para la API [HECHO].** `/api/orders` y `/api/fills` leen
  `recent_orders`/`recent_fills` (deques de 200, `live.py:441-442`, `state.py:778-788`).
- **Equity y posiciones no persistidas en paper-live [HECHO].** El `kind="equity"` de `_persist`
  solo lo emite el runtime de simulación (`state.py:693`); la curva de equity de esta corrida existe
  únicamente porque el monitor externo muestreó `/api/live` cada 60 s.
- **Duplicación de eventos [HECHO, negativa].** `_on_fill` deduplica por `fill_id`
  (`live.py:2041-2043`); el refresco de evidencia excluye las filas propias por `run_id` y por id
  (`state.py:439-445`); los 142 `no_trade` deduplicados coinciden con el embudo. No hay doble
  conteo de fills, outcomes ni rechazos.

---

## 5. Análisis de las dos operaciones

Ambas fueron shorts exploratorios en `trending_down`, alineados con la deriva de la ventana (BTC
−0,59 %) y aun así perdedores: el stop estaba a 10,25 y 8,45 bps de la entrada, es decir a 2–3 σ de
un minuto (σ 1 m observada 3,98 bps), y el mercado rebotó ese orden de magnitud en una o dos velas.
La comisión de ida y vuelta (2,5 maker + 7,5 taker = 10,0 bps) fue mayor que la distancia del stop
del trade 2 y prácticamente igual a la del trade 1. **[HECHO]**

Qué sí se puede concluir: (1) el circuito señal → riesgo → EV → exploración → sizing → orden →
fill → stop → outcome → persistencia funcionó de punta a punta con procedencia correcta
(`source=live`, `market_data=real`, `execution_mode=simulated`, `strategy_version=1.1.0`,
`live.py:2187-2218`); (2) la geometría stop/costo hace que un trade así tenga expectativa negativa
salvo tasas de acierto extremas (§9.3).

Qué no se puede concluir: nada sobre la expectativa de `trend_following` en BTC (n = 2,
exploratorios, un solo régimen, una sola dirección); nada sobre si el bucket sintético
`trending_down/short/0.85-1.01` describe el mercado real; nada sobre MAE/MFE sin alinear velas.

El motivo exacto por el que ese bucket no fue operable como trade normal (y por tanto solo
exploratorio) no está persistido para las operaciones tomadas. Dos candidatos **[HIPÓTESIS]**:
el techo `max_cost_ratio=0.6` (`expected_value.py:512-521`: con media 19,2, ajuste por SE y
costos ≈ 11 bps el cociente queda cerca de 0,6) o el recorte por ventana reciente
(`expected_value.py:253-303`). El dato que lo decide es `edge_outcomes.expected_net_bps` de las dos
filas (= `evaluation.net_edge_bps` al decidir, `live.py:1307`): si es ≥ 5 bps, fue el techo de
costos; si es < 5, fue el recorte o la SE. Consulta en §17.

---

## 6. Embudo de decisiones (Fase C)

### 6.1 Orden real de los gates (`live.py`, función `_process_bar`, 958–1313)

| # | etapa | archivo:línea | condición exacta | contador | entran | salen | rechazadas |
|---|---|---|---|---|---|---|---|
| 0 | watchdog de datos, skew, reconciliación, estados PAUSED/SAFE_MODE | `_cycle_once` 883–911 | `bar_age > TTL`; `abs(skew) > 2500 ms`; cada N ciclos | `skew_halts`, incidentes | — | — | 0 |
| 1 | historia mínima | 963 | `len(window) < features.min_bars` | ninguno (silencioso) | 721 | 721 | 0 |
| 2 | calidad de datos | 966–975 | `report.hard_fail` | `quality_skipped` | 721 | 721 | 0 |
| 3 | features → régimen → fusión | 978–992 | siempre produce candidato | `signals`, `evaluated` (+1 c/u, idénticos) | 721 | 721 | — |
| 4 | accionable | 994–997 | `direction ∈ {long, short}` | `not_actionable` / `actionable` | 721 | 148 | 573 |
| 5 | marea HTF | 1003–1021 | hard: `agrees is False` → rechazo; soft: ×0,5 | `tide`, `htf_rejected` | 148 | 148 | 0 (bias `flat` toda la ventana ⇒ `agrees_with` devuelve None, `trend_context.py:60-62`) |
| 6 | mute del scoreboard | 1023–1029 | `scoreboard.is_muted(strategy_id)` | `muted`, `strategy_muted` | 148 | 148 | 0 (real_only, 0 juzgados) |
| 7 | orden en reposo | 1031–1036 | `self._resting is not None` | `resting`, `resting_skipped` | 148 | 145 | 3 (2 de ellas eran posición abierta, §4.4) |
| 8 | motor de riesgo | 1044–1058 | `not decision.allows_execution`; solo `reasons[0]` se cuenta en `_risk_reasons` | `risk`, `risk_rejected` | 145 | 56 | 89 |
| 9 | posición abierta | 1060–1073 | posición no plana: opuesta → cierre "signal reversed" (sin gate de edge); misma → `position_open` | `position_open`, `suppressed_position_open` | 56 | 55 | 1 |
| 10 | estado acepta órdenes | 1075–1077 | `not accepts_new_orders` | `halted` | 55 | 55 | 0 |
| 11 | presupuesto de riesgo | 1087–1109 | `not budget.allows_new_trades` (emergencia DD, cap diario 20, exposición bruta 80 %) | `budget` | 55 | 55 | 0 |
| 12 | ledger de capital | 1111–1118 | pérdida total o ledger detenido | `capital` | 55 | 55 | 0 |
| 13 | spread | 1128–1141 | `quote and spread_bps > max_spread_bps (10)` | `spread`, `spread_rejected` | 55 | 55 | 0 |
| 14 | valor esperado | 1142–1208 | `not evaluation.is_tradeable` → unknown / unproven / disproven; exploración solo si unknown/unproven, habilitada, sin guardrail activo y con presupuesto | `expected_value`, `ev_*` | 55 | 2 | 53 (todas `disproven`) |
| 15 | guardrail retrospectivo | 1210–1228 | `guard.is_active and net < threshold + add` (no aplica a exploración) | `guardrail` | 2 | 2 | 0 |
| 16 | exploración (contabilidad) | 1230–1256 | — | `exploration`, `exploration_trades` | 2 | 2 | — |
| 17 | sizing por convicción | 1258–1289 | exploración ⇒ 25 %; si no, t-stat → fracción | `sized_down` | 2 | 2 | — |
| 18 | orden | 1291–1298, `_submit` 1401–1483 | `assert_may_trade`, limit post-only al toque | `orders` (funnel y counter) | 2 | 2 | — |
| 19 | ejecución simulada | `paper.py:229-319` | fill en vela t+1 con trade-through | `fills`, `maker_fills` | 2 | 2 | — |
| 20 | gestión de posición | `_manage_position` 1779–1831, `_sync_protective_stop` 1833–1910, `_tighten_stop` 1740–1777 | objetivo, time stop (off), break-even, trailing, un stop | `stops_placed`, `exits_*` | — | — | — |

Contabilidad: 148 = 0 + 0 + 3 + 89 + 1 + 0 + 0 + 0 + 0 + 53 + 2. Cierra exacto. **[HECHO]**

Las categorías son **mutuamente excluyentes por construcción**: cada camino termina en un único
`_refuse(etapa)` o en `_submit`, y `_refuse` incrementa un solo contador (`live.py:1692-1700`).
Excepciones a tener en cuenta: `counters["orders"]` también cuenta salidas a mercado
(`_close_position`, 1988) mientras `funnel["orders"]` solo entradas (en esta corrida ambos valen 2);
`signals` y `evaluated` son el mismo número.

### 6.2 Dentro del motor de riesgo (`risk/engine.py:171-320`, en este orden)

estado del sistema → accionable → TTL de la señal (300 s) → calidad de datos (score ≥ 0,75,
frescura ≥ 0,70) → **confianza ≥ 0,55** (233) → instrumento y shortable → cortacircuitos
(drawdown 10 %, pérdida diaria 2 %) → condiciones de mercado (spread ≤ 25 bps, volumen mínimo,
**percentil de volatilidad ≤ 0,97**, 485–501) → frecuencia (20/día, 5/símbolo/día, enfriamiento
300 s, 504–552) → **sizing** (`sizing.py:74-86`: `stop_too_close` si la distancia < 0,05 % = 5 bps)
→ límites de cartera → mínimo nominal.

Solo se conserva **el primer motivo** (`live.py:1055`), de modo que la distribución de `risk_reasons`
es la del primer check fallido en ese orden. Observado: `confidence X below minimum 0.550` ≈ 61
(X entre 0,234 y 0,523), `stop_too_close` 23, `volatility … exceeds the 97.0% limit` 5 (todas
durante la caída, 03:24–05:23Z). **[HECHO]** sobre los 8 motivos más frecuentes; los 61 son resta.

### 6.3 Tasas de conversión

| transición | tasa |
|---|---|
| velas → accionables | 148 / 721 = 20,5 % |
| accionables → llegan a riesgo | 145 / 148 = 98,0 % |
| llegan a riesgo → aprobadas | 56 / 145 = 38,6 % |
| aprobadas → llegan a EV | 55 / 56 = 98,2 % |
| llegan a EV → operables (no exploración) | 0 / 55 = 0 % |
| llegan a EV → exploración | 2 / 55 = 3,6 % |
| velas → órdenes | 2 / 721 = 0,28 % |
| accionables → órdenes | 2 / 148 = 1,35 % |

Restricciones dominantes: riesgo (89 de 148 accionables, 60 %) y EV (53 de 55 que llegan, 96 %).
El 7,6 % de las velas llega a la decisión de EV; el 0,28 % termina en orden.

### 6.4 Respuestas expresas

- **Señales potencialmente válidas perdidas por etapa**: 89 en riesgo (coherentes con sus reglas,
  pero ver §9.3 sobre `stop_too_close`), 3 en reposo (2 mal clasificadas), 1 posición abierta, 53
  en EV (**no** se puede afirmar que fueran válidas ni inválidas: el EV las juzgó con evidencia
  sintética, §7).
- **Filtros redundantes o contradictorios [HECHO]**: (i) el motor de riesgo tiene su propio tope de
  spread (25 bps) y el bucle otro (10 bps) que lo precede: redundante e inocuo; (ii) la frecuencia
  del motor de riesgo (20/día, **5/símbolo/día**, enfriamiento 300 s) **nunca se arma** en el
  runtime: `live.py` nunca llama a `RiskEngine.record_execution` (sí lo hacen el motor de
  simulación, `runtime/engine.py:570`, y el backtester, `backtest/engine.py:229`), por lo que
  en la sesión 24/7 `trades_today` sigue en 0 y esos tres límites son letra muerta; el único cap efectivo es `_trades_today` del presupuesto (20/día, `live.py:1441`), y el
  enfriamiento de 5 minutos tras un stop no existe en la práctica; (iii) `max_trades_per_symbol_per_day=5`
  contradice al perfil balanced (20/día) para una sesión de un solo símbolo, si alguna vez se
  armara; (iv) con `min_agreement=0` la fusión nunca exige acuerdo; (v) la banda de confianza
  0,00–0,55 del estimador es inalcanzable en vivo porque riesgo rechaza antes a < 0,55.
- **¿La exploración se ejecuta demasiado tarde?** No: va después de riesgo y de EV, que es donde
  debe ir para no eludir límites. Su problema es de **alcance**, no de orden: solo se abre para
  buckets `unknown` o `unproven`, y `disproven` se define sin significancia (§7.4).
- **¿Conservador por diseño, por falta de evidencia o por bug?** Las tres cosas a la vez, en
  proporciones medibles: por diseño (riesgo: 89), por una definición de evidencia que no distingue
  "no sabemos" de "sabemos que no" y que cuenta costos dos veces (EV: 53, §7), y por bugs menores
  que no cambian el resultado pero sí la lectura (residuo de cantidad, frecuencia muerta, §4.4, §6.4).

---

## 7. Auditoría del estimador de valor esperado (Fase D)

### 7.1 Rutas de código

| función | archivo:línea | entradas | salidas | consumidores |
|---|---|---|---|---|
| carga de evidencia al arranque | `state.py:_load_live_evidence` (400–415) → `EdgeStateRepository.load_all()` `repositories.py:467-471` | **todas** las filas de `edge_outcomes`, orden `closed_at`, sin filtro de `source`/`market_data` | `prior_outcomes` (regime, direction, confidence, net_bps) y `prior_reviews` (fila completa) | `EdgeEstimator.record_many` (`live.py:311`), `RetrospectiveEngine.record_many` (`live.py:324`), `StrategyScoreboard.record_many` (`live.py:331`) |
| refresco periódico | `state.py:_evidence_refresh_loop` 566–578 (cada 60 s) → `refresh_session_evidence` 429–458 → `LiveRuntime.absorb_evidence` 652–701 | filas nuevas por `ingested_at`, excluidas las propias por `run_id` e id | ídem | ídem (solo añade) |
| bucket y estimación | `EdgeEstimator.record/estimate/_fit/_with_recent` `expected_value.py:172-336` | `(regime, direction, band_of(confidence))` → lista de `net_return_bps` | `EdgeEstimate(mean, adjusted, se, samples, level, decayed…)` | `ExpectedValueEngine.evaluate` |
| decisión | `ExpectedValueEngine.evaluate` `expected_value.py:462-524`; `ExpectedValue.is_tradeable` 381–382 | estimación + `TradeCosts` | `tradeable`, `net_edge_bps`, `explain()` | `live.py:1155-1208` |
| costos | `CostModel.estimate` `costs.py:171-205` (fees, spread, slippage, impacto, latencia) | cantidad, `MarketConditions` (precio, spread del quote, ATR por vela, profundidad al toque, volumen, latencia medida) | `TradeCosts` | EV |
| clasificación unknown/unproven/disproven | `live.py:1177-1208` | `evaluation.edge_estimate`, `mean_bps`, `decayed` | contadores `ev_*`, exploración o rechazo | embudo |
| registro de la propia operación | `live.py:2129-2136` (estimador), `2137-2149` (retrospectivo), `2153-2157` (scoreboard con `market_data="real"`), `2187-2218` (persistencia) | round trip cerrado | — | — |
| generación sintética | `scripts/train_sims.py` → `runtime/engine.py` (`enforce_expected_value=False`, línea 213; entradas **market**, 1157–1164) → `runtime/scenarios.py` (`generate_series` 228–300) | escenarios con deriva y volatilidad por segmento | filas `source` sim/paper, `market_data=synthetic`, `execution_mode=simulated` (`engine.py:934-935`) | la misma tabla |

### 7.2 Fórmula, unidades, costos

**[HECHO]**

- Unidad: puntos básicos del nominal de entrada.
- `Outcome.net_return_bps` = (salida − entrada)/entrada · 10⁴ con signo por dirección, **menos
  `fees_bps`** (`live.py:2121-2127`, `engine.py:845-854`). Es neto de comisiones realmente pagadas.
- Por bucket: `mean`, `variance/(n−1)`, `SE = sqrt(var/n)`; `adjusted = max(0, mean − k·SE)` si
  `mean > 0`, `min(0, mean + k·SE)` si no; `k = 1` (bucket exacto, ≥ 30 muestras) o `k = 2`
  (pool de las cuatro bandas del mismo régimen y dirección, ≥ 60 muestras) (`expected_value.py:306-336`).
- Ventana reciente: si el bucket tiene ≥ 60 muestras, se ajusta por separado la cola de 60 (en
  **orden de ingestión**, que para `load_all` es `closed_at`); si `tail.mean + k·tail.SE <
  full.adjusted` el estimado se recorta a `tail.adjusted`, y si queda ≤ 0 se marca `decayed`
  (253–303). El recorte solo baja, nunca sube.
- `gross_edge_bps = adjusted`; `net_edge_bps = gross_edge_bps − costs.total_bps`;
  `is_tradeable = estimate is not None and net ≥ threshold (5 bps)`; además, si
  `costs/gross > 0.6` se fuerza no operable (`expected_value.py:373-382, 512-521`).
- Costos de la operación actual (`costs.py:171-205`): comisiones de ida y vuelta (entrada maker
  2,5 + salida taker 7,5 = 10,0 bps; `FeeSchedule` construida desde `settings.execution`,
  `live.py:302-309`), medio spread por cruce (solo la salida cruza), slippage (0 si la orden cabe en
  el toque del bookTicker; si no hay profundidad, medio ATR de vela), impacto
  (0,35·√participación·100), latencia (ATR·√(latencia/60 s)·seguridad). Con 0,012 BTC y las
  condiciones de la ventana, total ≈ 10,5–11,5 bps **[INFERENCIA]**. Funding no entra en el EV;
  solo en el ledger (`_accrue_funding`), y en esta corrida no hubo tasa (`last_rate=null`).

### 7.3 Doble conteo de costos **[HECHO, con efecto cuantificable]**

El estimado se construye con retornos **netos** de comisiones y el motor le resta **otra vez** los
costos de la operación actual (`net_edge_bps = adjusted(net pasado) − costs_now`). El comentario
de `Outcome` (`expected_value.py:91-93`: "Gross would double-count: costs are subtracted again
downstream") afirma lo contrario de lo que hace la aritmética: para que restar costos aguas abajo
sea correcto, el estimado debería ser bruto. Efecto: el umbral efectivo no es "neto ≥ 5 bps" sino
"bruto pasado ≥ 5 + costos pasados (≈10) + costos presentes (≈11) ≈ 26 bps por trade", en un
sistema cuyo objetivo es 3×ATR ≈ 12–15 bps. Consecuencia secundaria: el motor retrospectivo
compara `expected_net_bps` (así calculado) con el neto realizado, por lo que las operaciones
sistemáticamente "superan" la expectativa en ≈ costos y el guardrail nunca ve una decepción.
Ningún test unitario cubre esta propiedad (`tests/unit/test_economics.py` construye outcomes con
`net_return_bps` y comprueba floor, shrink y bandas, no la aritmética neto-contra-costos).

### 7.4 Qué activa "disproven" **[HECHO]**

`live.py:1177-1196`: si `estimate is None` → `unknown`; si `mean_bps > 0 and not decayed` →
`unproven`; **cualquier otro caso** → `disproven`. Es decir, un bucket con 30 muestras y media
−0,3 ± 15 bps es "disproven" igual que uno con 12.000 muestras y media −20 ± 0,5. La etiqueta
confunde "sin evidencia de ventaja" con "evidencia de no ventaja", y es la que cierra la puerta a
la exploración (solo `unknown`/`unproven` exploran, 1197–1203). Las 53 señales rechazadas en EV
cayeron aquí: sus buckets sintéticos tienen media no positiva o decaída. Confirmación por bucket:
consulta `synthetic_buckets` de §17 (pendiente).

### 7.5 Procedencia y mezcla

| dimensión | estado en el estimador | evidencia |
|---|---|---|
| `market_data` / `execution_mode` / `source` | **ignoradas**: `_as_outcome` solo toma régimen, dirección, confianza y `net_bps` (`state.py:330-340`); `load_all()` no filtra | HECHO |
| `strategy_id` / `strategy_version` | **ignoradas por diseño**: el bucket es (régimen, dirección, banda) y pool de estrategias (`scoreboard.py:3-7`); 262.651 de 265.611 filas sintéticas no tienen `strategy_id` (anteriores a la migración 0005) y por tanto tampoco versión | HECHO (consulta legacy 10-09) |
| antigüedad / `closed_at` | solo para la ventana "reciente", que en filas sintéticas ordena por el reloj del escenario o del lote de entrenamiento, no por recencia de mercado | HECHO + INFERENCIA |
| `run_id` / escenario / semilla | ignorados; cada lote de `train_sims.py` añade filas a la misma tabla; `--seed-base 0` deriva semillas del reloj (línea 29–31) | HECHO |
| mercado / timeframe | el generador usa `start_price=50_000` y 1 m (`scenarios.py:235`, `engine.py:182`); misma barra que el vivo, precio distinto (irrelevante en bps) | HECHO |
| costos incluidos | sí, netos de las mismas comisiones configuradas (2,5/7,5) pero con **entradas market** (`engine.py:1157-1164`) frente a entradas limit en vivo: la evidencia pagó taker+taker (15 bps) y el vivo paga maker+taker (10 bps) | HECHO |
| independencia | trades consecutivos de un mismo run comparten régimen y deriva de segmento; nada en el estimador pondera por run ni por autocorrelación | INFERENCIA |
| bruto vs neto | neto en los outcomes; vuelto a restar en EV (§7.3) | HECHO |

Los escenarios sintéticos (`scenarios.py:84-223`) fijan deriva y volatilidad por segmento: p. ej.
`trend_down` tiene un tramo de 360 velas con deriva −8,5·10⁻⁵ por vela (−0,85 bps/vela) y σ
4,2·10⁻⁴ (4,2 bps/vela). Esa relación deriva/σ ≈ 0,2 por vela es un trend de fuerza irreal; un
short en ese tramo gana ≈ 0,85 bps por vela de tenencia **por construcción**. **[HECHO]** Por eso
el bucket `trending_down/short/0.85-1.01` muestra +19,2 bps netos sobre 12.444 trades: el
estimador aprendió el parámetro del generador. Y por eso la mayoría de los demás buckets son
negativos: con σ ≈ 4 bps/vela, stop 2×ATR y comisiones de 15 bps (market) el ruido se come la
geometría (§9.3). La evidencia sintética prueba lo que se diseñó y castiga lo que cuesta; no habla
de BTC.

### 7.6 Respuestas a las doce preguntas

1. **Fórmula**: `net = adjusted(net_pasado) − costos_actuales ≥ 5 bps` y `costos/adjusted ≤ 0,6`,
   con `adjusted = mean ∓ k·SE` recortado a la cola de 60 si es inconsistente (§7.2).
2. **Unidades**: bps del nominal de entrada; el `explain()` los traduce a USD de la posición.
3. **Costos**: comisiones, spread, slippage, impacto y latencia sí; funding no. Y se cuentan dos
   veces (§7.3).
4. **Qué activa disproven**: media ≤ 0 o decaída, sin prueba de significancia (§7.4).
5. **Validez estadística**: la contracción por SE es razonable como heurística, pero la muestra no
   es iid (segmentos con deriva impuesta, runs correlacionados, sin ponderación), la "recencia" no
   es temporal, y el umbral efectivo es el doble del declarado. No es un test de hipótesis.
6. **Sesgo de selección / look-ahead / leakage**: no hay look-ahead en el bucle (decisión sobre la
   vela cerrada, fill en la siguiente, `paper.py:247-249`); no hay leakage de filas propias
   (`state.py:439-445`). Sí hay **sesgo de población**: la evidencia se generó con
   `enforce_expected_value=False` (toda señal aprobada por riesgo se ejecuta) y el vivo solo opera
   lo que pasa EV; además la evidencia pagó entradas market y el vivo limit.
7. **Doble contabilización**: de costos sí (§7.3); de outcomes y fills no (§4.4).
8. **Qué datos necesita**: outcomes reales-paper del mismo símbolo, timeframe, versión de
   estrategia y tipo de entrada, etiquetados por procedencia, con decisión y costos persistidos por
   señal; y una regla explícita sobre qué puede hacer la evidencia sintética (§8.4).
9. **¿Puede aceptar por datos sintéticos favorables?** Sí: el único bucket positivo lo es por la
   deriva del generador; si el ajuste hubiera superado el techo de costos habría operado al tamaño
   completo con esa sola base.
10. **¿Puede rechazar una estrategia válida por datos sintéticos desfavorables?** Sí: es
    exactamente lo que hizo 53 veces, y la etiqueta "disproven" impide incluso explorar.
11. **¿`real_only` afecta al EV?** No. Solo a `StrategyScoreboard.record` (`scoreboard.py:157-162`).
    `EdgeEstimator` y `RetrospectiveEngine` reciben todo (`live.py:311,324`).
12. **Muestra independiente y suficiente**: hoy "suficiente" = 30 por bucket (o 60 pooled) y
    "independiente" no está definido. Propuesta en §8.4 y §15.

---

## 8. Scoreboard y exploración (Fase E)

### 8.1 Implementación de `real_only` **[HECHO]**

`StrategyScoreboard.record` (`scoreboard.py:140-169`): sin `strategy_id` → se ignora; con política
`real_only` y `market_data != "real"` → cuenta en `excluded_synthetic` (o `excluded_unknown` si es
None) y **no toca** `trades`, `wins` ni `_net`; con `market_data == "real"` → `trades += 1`, win si
`net > 0`, y solo si **no** es exploratorio se añade a `_net` (lo que `judged` cuenta). Mute:
`judged ≥ 30 and mean + 1,0·SE < 0` (93–97). `is_muted` de una estrategia sin registro → False.

Filas que entran por estrategia en esta corrida (`scoreboard.report()`, ckpt final):
trend_following 2 trades / 2 exploratorios / 0 juzgados / 2.446 sintéticas excluidas;
mean_reversion 0/0/0/493; breakout 0/0/0/21. Las 262.651 filas sin `strategy_id` no entran a
ninguna política.

### 8.2 Relación entre scoreboard, EV, exploración, mute, riesgo y evidencia

- El scoreboard solo **refusa** (mute) y solo con trades juzgados reales.
- El EV decide con todos los outcomes (sintéticos incluidos) y define qué es explorable.
- La exploración solo se abre en `unknown`/`unproven`, después de riesgo, con tope diario (20) y
  fracción de tamaño (0,25); está deshabilitada con proveedor live (`exploration_enabled`,
  `live.py:470-482`).
- Un trade exploratorio: alimenta al `EdgeEstimator` como una muestra más del bucket (peso
  1/12.445 en el bucket de esta corrida), al retrospectivo sin calibración (`retrospective.py:275`),
  y al scoreboard como `trades`/`exploratory` sin juzgar.

### 8.3 La circularidad, confirmada **[HECHO + datos]**

1. El scoreboard necesita trades juzgados (no exploratorios) para formarse opinión.
2. El EV, con evidencia sintética, clasifica casi todo como `disproven` (sin significancia) y lo
   poco positivo como `unproven` (recorte/SE/techo de costos y doble conteo).
3. Lo único que puede abrir una operación es la exploración, y solo en `unproven`/`unknown`.
4. Los trades exploratorios no juzgan, y como muestras del estimador solo pueden **bajar** la
   estimación sintética (la ventana reciente nunca sube).
5. `judged` permanece en 0; ninguna estrategia puede salir del estado inicial. Datos: 2 trades, 2
   exploratorios, 0 juzgados, `needed_to_judge=30` para las tres estrategias.

La salida teórica del círculo (un bucket sintético que pase EV al tamaño completo) solo ocurre si
el generador la escribió, lo que es el problema de §7.5 desde el otro lado.

### 8.4 Política propuesta de estados por estrategia (no implementada)

| estado | entrada | requisitos cuantitativos | salida | qué puede hacer |
|---|---|---|---|---|
| **No evaluada** | sin filas reales-paper de esta versión en este símbolo/timeframe | `n_real = 0` | al primer trade real | solo exploración controlada |
| **Exploración controlada** | `0 < n_real < n_min` | tope diario y fracción de tamaño; sin guardrail activo; riesgo intacto; registra decisión y costos por señal | `n_real ≥ n_min` (propuesta: 30 por estrategia, con la varianza real medida para recalcular, §15) | exploración; la evidencia sintética solo **prioriza** qué bucket explorar, nunca autoriza tamaño completo |
| **Evidencia provisional** | `n_real ≥ n_min` | IC 90 % de la media neta real calculado; sin verdicto | `n_real ≥ n_suf` donde `n_suf = (z·σ_real/δ)²` con δ = umbral mínimo de ventaja (p. ej. 5 bps) | tamaño reducido (p. ej. 50 %), sujeto a EV con evidencia **real** del bucket |
| **Evidencia suficiente** | `n_real ≥ n_suf` y límite inferior del IC > 0 después de costos | profit factor, drawdown y consistencia entre regímenes reportados | si el límite inferior cae bajo 0 → provisional; si media + SE < 0 → rechazada | tamaño completo por convicción |
| **Rechazada por evidencia robusta** | `n_real ≥ n_min` y `mean + 1·SE < 0` sobre trades reales juzgados (la regla actual del mute, aplicada solo a reales) | — | revisión manual con nueva versión de estrategia (nuevo `strategy_version` ⇒ nuevo estado "no evaluada") | nada |
| **Pausada por riesgo o integridad** | halt del watchdog, skew, ruptura de reconciliación, pérdida de estado tras reinicio con posición abierta | — | reconciliación limpia y decisión del operador | nada |

Regla general: **"no sabemos" nunca se escribe como "sabemos que no"**; `disproven` requiere
`mean + k·SE < 0` sobre evidencia admitida para autorizar, y la sintética no está admitida para
autorizar ni para rechazar, solo para priorizar e investigar.

---

## 9. Costos, stops y calidad de ejecución (Fase F)

### 9.1 Modelo de ejecución simulada (`execution/paper.py`) **[HECHO]**

- Sin libro: fills contra OHLCV de la vela siguiente; una orden creada en la vela t no puede
  llenarse en t (`229-249`).
- **Market**: referencia = apertura de la vela siguiente (328–329) + slippage adverso.
- **Limit/post-only**: exige que el precio atraviese el límite (`low < limit` para compra, `high >
  limit` para venta); referencia = `min(limit, open)` / `max(limit, open)` (331–341); se cobra
  comisión maker; **se aplica slippage adverso también al fill maker** (286), cosa que un venue no
  hace con una limit (nunca llena peor que su límite): sesgo pesimista. Sin modelo de cola: si el
  precio atraviesa, llena; sesgo optimista. Ambos observados: entrada 1 a 83.026,00 con límite
  83.038,31 (1,48 bps peor).
- **Stop**: dispara si `high ≥ stop` (compra); referencia = `max(stop, open)` (343–355) + slippage,
  **acotado al rango de la vela** (414). Un salto de apertura por encima del stop llena en la
  apertura: trade 2 llenó 5,09 bps más allá del stop con slippage registrado 0 (apertura = máximo
  de la vela). Realista.
- Slippage: base 2 bps + impacto 0,35·√participación·100 + 5 % del rango de la vela (tope 25),
  acotado al rango (388–420). Participación máxima 10 % del volumen de la vela. Rechazo aleatorio
  1 %, fill parcial aleatorio 15 % (35–85 % de la cantidad) (422–432).
- Comisiones en ambas patas (288–291). Long/short simétricos; shorting permitido en BTC-USD (spot)
  sin coste de préstamo; funding solo vía ledger si hay tasa (no la hubo).
- Latencia como desplazamiento de timestamps (180 ms), no afecta al precio.
- Sin look-ahead: decisión sobre la vela cerrada, fill en la siguiente; el stop se evalúa con la
  vela completa (no sabe si tocó el stop antes o después del máximo: en una vela que toca stop y
  objetivo, el orden de evaluación da prioridad al objetivo, `live.py:1813-1818`, sesgo optimista
  no observado aquí).
- `expire_stale_orders` existe pero no lo usa el runtime; la expiración es la del bucle (3 velas).

### 9.2 Los 23 `stop_too_close` y los stops de los trades **[HECHO + INFERENCIA]**

`sizing.py:33,74-86`: distancia mínima 0,05 % del precio = 5 bps. Las estrategias ponen el stop a
k×ATR(14) de 1 m (k = 2 trend/breakout, 1,5 mean reversion; `library.py:43,162,281`). Con σ 1 m
≈ 4 bps, ATR(14) oscila entre ≈ 2 y 6 bps; cuando ATR < 2,5 bps el stop de trend_following queda
bajo 5 bps y riesgo lo rechaza. Los 23 rechazos son minutos tranquilos. Los dos trades tuvieron
ATR ≈ 5,1 y 4,2 bps → stops de 10,25 y 8,45 bps.

| magnitud | trade 1 | trade 2 |
|---|---|---|
| distancia al stop | 10,25 bps (85,1 USD/BTC) | 8,45 bps (69,9 USD/BTC) |
| costos de ida y vuelta modelados | 10,0 fees + 0,65 + 1,48 slip ≈ 12,1 bps | 10,0 + 0,21 + 0,00 ≈ 10,2 bps |
| σ de 1 m observada | 3,98 bps | 3,98 bps |
| spread observado | ≈ 0,1–0,2 bps (bid/ask del bookTicker en las muestras: 83.434,67/83.434,68) | ídem |
| tamaño / nominal | 0,012043 BTC / 999,88 USD | 0,012093 / 999,86 |
| riesgo monetario al stop | 1,02 USD (0,010 % del equity) + comisiones 1,00 | 0,85 + 1,00 |
| presupuesto de riesgo del perfil | 0,5 % = 50 USD | 50 USD |

Lo que se observa: el riesgo monetario real por trade fue ≈ 2 USD (incluyendo comisiones), es decir
el 4 % del presupuesto por trade. El tamaño no lo limitó el riesgo sino el tope nominal y la
fracción de exploración. **[INFERENCIA]**

### 9.3 Coherencia regla de riesgo ↔ estrategia ↔ costos

Con stop 2×ATR, objetivo 3×ATR y ATR ≈ 4–5 bps, un trade de trend_following a 1 m tiene
pérdida bruta ≈ 8–10 bps y ganancia bruta ≈ 12–15 bps **antes** de 10–11 bps de costos (o 15 bps en
la evidencia sintética, que entró a mercado). Tasa de acierto de equilibrio: `p·(15 − 11) = (1 −
p)·(10 + 11)` ⇒ `p ≈ 0,84`. Ninguna estrategia direccional de 1 minuto sostiene eso; la evidencia
sintética lo refleja como medias negativas (trend_following −15,8 bps, mean_reversion −22,5,
breakout −23,3 por estrategia, consulta 10-09). **[INFERENCIA sobre HECHOS]** La regla de riesgo
("stop ≥ 5 bps") es coherente consigo misma; lo incoherente es un horizonte de 1 minuto con
comisiones de 10 bps. No se recomienda ni ampliar ni estrechar el stop para subir la frecuencia:
primero hay que decidir el horizonte (timeframe, múltiplos) a la luz de los costos (§14, P1-F).

---

## 10. Atribución y estadística (Fase G)

Denominadores: "señales" = velas evaluadas; "accionables" = señales con dirección; "trades" =
round trips cerrados; win rate **solo** sobre trades cerrados.

| estrategia | señales | accionables | rechazos por etapa | órdenes | fills | trades cerrados | win rate | media neta | profit factor | drawdown | exposición |
|---|---|---|---|---|---|---|---|---|---|---|---|
| trend_following | NO_PERSISTED | NO_PERSISTED | NO_PERSISTED | 2 | 4 | 2 (exploratorios) | 0/2 | −22,2 bps (n = 2; IC inútil) | 0 | −4,45 USD | ≈ 3 min |
| mean_reversion | NO_PERSISTED | NO_PERSISTED | NO_PERSISTED | 0 | 0 | 0 | — | — | — | — | 0 |
| breakout | NO_PERSISTED | NO_PERSISTED | NO_PERSISTED | 0 | 0 | 0 | — | — | — | — | 0 |
| total | 721 | 148 | 89 riesgo, 3 reposo, 1 posición, 53 EV | 2 | 4 | 2 | 0/2 | −22,2 bps | 0 | −4,45 USD (−0,0445 %) | 0,4 % |

Por régimen: ambos trades en `trending_down`; la distribución de régimen de las 721 velas no está
persistida (el `live.trend` horario es la marea HTF, no el régimen de 1 m). Por versión: 1.1.0 en
ambos. Por dirección: 2 short, 0 long. MAE/MFE: no calculables sin alinear velas (posible ex-post
con `btc_klines_1m.json`, no hecho).

Métricas no estimables hoy y qué falta: win rate, expectativa, profit factor y drawdown por
estrategia (hacen falta decenas de trades juzgados por estrategia); embudo por estrategia (hace
falta `strategy_id` y confianza en cada `live.no_trade` o una tabla `decisions` escrita por el
runtime); régimen por vela (persistir la evaluación de régimen); MAE/MFE (persistir máximos y
mínimos durante la posición o reconstruir con velas). Con n = 2 cualquier métrica es ruido y así
debe reportarse.

---

## 11. Contrafactuales y límites (Fase H)

- **Legacy habría silenciado** a trend_following (2.446 filas sintéticas, media −15,83, SE 0,61,
  media + SE = −15,2 < 0) y a mean_reversion (493, −22,50 ± 1,09); breakout (21 < 30) no es
  juzgable; el bucket sin `strategy_id` (262.651, −8,16 ± 0,16) también, pero solo afecta a señales
  sin estrategia, que no hubo. **[HECHO]** (regla del scoreboard aplicada en SQL sobre las mismas
  filas que legacy habría cargado vía `record_many`; la regla no depende de la política,
  `scoreboard.py:29-30`).
- **Las dos operaciones no habrían ocurrido bajo legacy**: ambas acreditadas a trend_following, y
  el mute se evalúa antes que EV y exploración (`live.py:1023` vs `1177`). **[HECHO]**
- **¿Causó `real_only` la actividad?** Sí, para esas dos: sin mute no hay otra diferencia de
  código entre políticas. Pero el aumento de actividad fue de 0 a 2 trades exploratorios en 12 h;
  real_only abrió la puerta del mute, no la del EV. **[INFERENCIA]**
- **Qué bloqueó al resto**: riesgo 89, EV 53, reposo 3, posición 1 (§6).
- **Señales más cercanas a ejecutarse**: en riesgo, las de confianza 0,523 y 0,511 (umbral 0,55);
  en EV, las dos `unproven` que sí entraron como exploración; de las 53 `disproven` no se conoce el
  neto estimado sin los textos de `explain()` (§17).
- **Efectos de secuencia que invalidan cálculos simples**: bajo legacy, con trend_following muteada
  no se habría abierto posición en 02:13 ni 04:05, así que los 3 rechazos `resting` y el
  `position_open` no habrían existido y esas 4 señales habrían llegado a riesgo y EV; el equity y el
  streak de pérdidas habrían sido otros (el budget usa `consecutive_losses`); y como el
  `strategy_id` acreditado es el primero de la lista, señales co-firmadas por breakout habrían
  caído igualmente en el mute de trend_following. Ninguno de estos efectos cambia el resultado de
  "0 órdenes bajo legacy", pero sí la composición del embudo. **[INFERENCIA]**
- No se puede reconstruir la política histórica exacta más allá del scoreboard: el estado del
  estimador al arranque (mismo `load_all`) es idéntico bajo ambas políticas.

---

## 12. Causas raíz confirmadas

| id | causa raíz | evidencia | efecto |
|---|---|---|---|
| CR-1 | El EV resta costos sobre un estimado ya neto de costos | `expected_value.py:91-93, 373-374, 462-524`; `live.py:2121-2135`; `engine.py:845-862` | umbral efectivo ≈ 2× el declarado; sesgo sistemático a NO_TRADE |
| CR-2 | "disproven" = media ≤ 0 o decaída, sin significancia | `live.py:1177-1196` | 53 rechazos que cierran también la exploración |
| CR-3 | Evidencia sintética sin política de procedencia en EV y retrospectivo | `state.py:_load_live_evidence`, `repositories.py:467-471`, `live.py:311,324` | el generador decide qué buckets son "buenos" y "malos" |
| CR-4 | Los exploratorios no juzgan y solo pueden bajar el estimado | `scoreboard.py:166-169`; `expected_value.py:276-281` | circularidad: `judged` = 0 para siempre |
| CR-5 | Geometría stop/objetivo a 1 m frente a costos de 10–15 bps | `library.py:43-44,98-104`; `config.py:127-128`; σ observada | tasa de acierto de equilibrio ≈ 84 % |
| CR-6 | Evidencia generada con entradas market y sin EV; vivo con entradas limit y EV | `engine.py:213,1157-1164` vs `live.py:1159-1166` | poblaciones distintas; costos pasados 15 vs presentes 10 |
| CR-7 | Cantidad sin cuantizar en paper-live | `live.py:1354-1356`; `state.py:2245-2259`; `paper.py:282` | órdenes no terminales, rechazos mal clasificados, expiraciones espurias |
| CR-8 | Frecuencia del motor de riesgo nunca armada en la sesión 24/7 | `live.py` no llama a `RiskEngine.record_execution`; el motor de simulación (`engine.py:570`) y el backtester (`backtest/engine.py:229`) sí | enfriamiento y topes por símbolo muertos en paper-live |
| CR-9 | Persistencia insuficiente: sin decisiones, rechazos con estrategia, estados de orden post-fill, equity | `live.py:_save` (order, fill, edge_outcome, latency) | no se puede reconstruir un run por estrategia tras un reinicio |

## 13. Hipótesis no confirmadas

| id | hipótesis | qué la confirmaría |
|---|---|---|
| H-1 | El bucket `trending_down/short/0.85-1.01` no fue operable por el techo `max_cost_ratio=0.6` (y no por el recorte de ventana reciente) | `expected_net_bps` de las 2 filas de la corrida (≥ 5 ⇒ techo; < 5 ⇒ recorte/SE), §17 |
| H-2 | Los 53 `disproven` corresponden a buckets con media sintética negativa en `trending_down/short` de bandas < 0,85 y en otros regímenes, no a `decayed` | textos de `live.no_trade` etapa `expected_value` y tabla `synthetic_buckets`, §17 |
| H-3 | Las 61 razones de riesgo no listadas son todas "confidence below 0.550" | tally de `live.no_trade` etapa `risk`, §17 |
| H-4 | La cantidad aprobada (≈ 4.000 USD) vino del tope nominal escalado y no del presupuesto de riesgo | no verificable sin persistir `RiskDecision`; irrelevante para el veredicto |
| H-5 | El orden `closed_at` de las filas sintéticas hace que la "ventana reciente" sea el último lote de entrenamiento | `SELECT run_id, MIN(closed_at), MAX(closed_at) FROM edge_outcomes WHERE market_data='synthetic' GROUP BY run_id ORDER BY 2 DESC LIMIT 5` |

## 14. Datos faltantes

Por señal: estrategia acreditada, confianza, régimen, stop/objetivo propuestos, decisión de riesgo
completa (checks, restricción vinculante), evaluación de EV completa (`as_dict()`), motivo de
rechazo con estrategia. Por orden: transiciones de estado y fills acumulados. Por vela: régimen
clasificado, ATR, spread. Por sesión: equity por vela, posición abierta con stop vigente, MAE/MFE.
Por evidencia: etiqueta de uso permitido (investigación / exploración / autorización) y versión de
estrategia en todas las filas (262.651 sin ella).

---

## 15. Plan de corrección priorizado (Fase I, sin implementar)

Criterios: **P0** seguridad/integridad; **P1** invalida decisiones o resultados; **P2** riesgo,
ejecución o instrumentación; **P3** mejora.

### P0-A Rollback de `scripts/deploy.sh` tras migración aplicada
- Evidencia: incidente del 10-07 (health check vía `TIA_DOMAIN` vacío → fallo → retag de imagen
  anterior sobre schema 7 → crash loop). Causa: el rollback de imagen no comprueba la revisión de
  alembic. Cambio mínimo: antes de retag, comparar `alembic current` con la revisión soportada por
  la imagen anterior y abortar con mensaje; health check por `127.0.0.1:8000` dentro del contenedor.
  Tests: script bajo `bats`/shell con mock de `docker` y `alembic`. Aceptación: un despliegue con
  health falso y migración aplicada termina en "rollback refused" con el servicio nuevo arriba.
  Riesgo: bajo. Efecto secundario: ninguno.

### P0-B Credenciales expuestas fuera del repo
- Evidencia: exportación en shell del 10-07. Acción: rotar en Binance; `history -c` en root. No es
  cambio de código. Aceptación: claves antiguas revocadas.

### P1-A Doble conteo de costos en el EV (CR-1)
- Archivos: `economics/expected_value.py:85-93, 462-524`; `runtime/live.py:2129-2135`;
  `runtime/engine.py:856-862`. Cambio mínimo (elegir uno y documentarlo): (i) alimentar al
  estimador con `gross_bps` y seguir restando costos actuales; o (ii) mantener neto y hacer
  `net_edge = adjusted − (costs_now − costs_paid_mean)` (ajuste por diferencia de estructura de
  costos). (i) es más simple y hace comparables evidencia market y vivo limit. Alternativa:
  persistir ambos y elegir por configuración. Riesgo: cambia qué buckets son operables; debe
  ir con P1-B y P1-C, nunca solo. Tests unitarios: un bucket con bruto 20 y comisiones 10 debe
  dar neto ≈ 20 − costos_now, no 10 − costos_now; propiedad "EV(neto_pasado) + costos_pasados =
  EV(bruto_pasado)". Integración: `test_live_runtime` con evidencia sintética controlada.
  Regresión: los tests actuales de `test_economics.py` deben seguir pasando con outcomes
  reconvertidos. Validación estadística: re-evaluar las 55 señales de la corrida con el fix (los
  datos de bucket existen) y reportar cuántas cambian de verdicto. Aceptación: el umbral efectivo
  medido coincide con el configurado ±1 bps. Efecto secundario: el retrospectivo deja de ver
  "mejor de lo esperado" sistemáticamente.

### P1-B `disproven` requiere significancia (CR-2)
- Archivo: `runtime/live.py:1177-1208` (y un helper en `expected_value.py`). Cambio mínimo:
  `disproven` ⇔ `estimate.adjusted_bps < 0` con `mean + k·SE < 0` (la misma forma que el mute);
  `unproven` ⇔ IC contiene 0 (sea la media positiva o negativa); `decayed` se reporta aparte.
  Tests: tabla de casos (n, media, SE) → estado; regresión de `test_exploration_buys_lessons_in_unproven_buckets_but_never_in_disproven_ones`
  reescrita con buckets significativos. Aceptación: ningún bucket con |t| < 1 se clasifica
  `disproven`. Riesgo: más exploración (acotada por el tope diario). 

### P1-C Procedencia en EV y retrospectivo; modelo de evidencia (CR-3, CR-4)
- Archivos: `api/state.py:_load_live_evidence, _as_outcome, refresh_session_evidence`;
  `persistence/repositories.py:load_all`; `runtime/live.py:311,324,683-685`; `core/config.py`
  (`LiveConfig`). Cambio mínimo: un `evidence_policy` con tres conjuntos explícitos —
  **autorizar** (filas `market_data='real'` de la misma `strategy_version`, símbolo y timeframe),
  **explorar/priorizar** (sintéticas y paper antiguas: eligen qué bucket explorar primero, nunca
  tamaño completo), **investigar** (todo, solo para informes). El estimador que decide
  `is_tradeable` se construye solo con el conjunto "autorizar"; un segundo estimador "prior" solo
  ordena la exploración. Exploratorios reales **sí** cuentan como evidencia del bucket real (con su
  fracción de tamaño no afecta al bps). Scoreboard: los exploratorios reales entran a un contador
  `judged_exploratory` con su propio mínimo, o se juzgan igual (decisión de diseño; recomendado
  juzgar, porque la exploración ya pasó riesgo). Tests: tres estimadores se construyen con los
  conjuntos correctos; una base con 265k sintéticas y 0 reales produce `unknown` en todo (no
  `disproven`); un bucket con 30 reales y 12.000 sintéticas decide solo con los 30. Aceptación:
  `judged` crece con trades exploratorios reales; ningún verdicto `disproven` cita filas
  sintéticas. Riesgo: al principio el sistema explora más y opera a tamaño reducido; es el
  comportamiento deseado. Efecto secundario: la página Learning debe mostrar el conjunto.

### P1-D Horizonte y geometría frente a costos (CR-5, CR-6)
- No es un fix de código inmediato sino una decisión: con comisiones 2,5/7,5 bps, el timeframe de
  1 m exige objetivos ≥ 3× los costos. Opciones a evaluar en backtest con datos reales (no
  sintéticos): timeframe 5–15 m con los mismos múltiplos; o 1 m con objetivo ≥ 6×ATR y stop ≥
  3×ATR; o entradas y salidas maker. Criterio de aceptación para cualquier opción: en backtest
  sobre ≥ 90 días de velas reales, `mediana(objetivo bruto) ≥ 3 × costos modelados` y expectativa
  neta con IC 90 % > 0 en al menos dos regímenes. Riesgo: cambiar múltiplos invalida la evidencia
  sintética (que ya no debería autorizar, P1-C). Además unificar el tipo de entrada entre
  evidencia y vivo (limit en ambos o registrar `entry_order_type` en cada fila).

### P1-E Cuantización de cantidad en paper-live (CR-7)
- Archivos: `runtime/live.py:1337-1400` (`_build_intent`), `api/state.py:2245-2259`,
  `runtime/live.py:1510-1520`. Cambio mínimo: cuantizar siempre al lote del instrumento
  (`DEFAULT_UNIVERSE`) cuando no hay `step_size`; y en `_manage_resting` tratar
  `remaining_quantity < lot_size` como terminal. Tests: intent de 0,01204375 produce 0,012043; una
  orden con residuo < lote no se cuenta como `resting` ni `orders_expired`. Aceptación: 0
  `orders_expired` en una sesión cuyas entradas se llenaron. Riesgo: nulo.

### P2-A Persistencia para reconstrucción (CR-9)
- Persistir por señal una fila `decisions` (ya existe el repositorio, `state.py:655`) con
  estrategia, versión, confianza, régimen, stop/objetivo, `RiskDecision.as_dict()`,
  `ExpectedValue.as_dict()`, etapa de rechazo y motivo; `_save("order")` también en cada fill y
  transición; equity por vela (`PortfolioRepository.append_equity`); régimen por vela. Tests de
  integración: un run de 50 velas con 3 trades se reconstruye íntegramente desde la base (embudo
  por estrategia idéntico a los contadores). Aceptación: `SELECT` reproduce los 20 renglones del
  embudo de §6 sin el runtime en memoria. Riesgo: volumen (≈ 1.440 filas/día/símbolo; trivial).

### P2-B Armar o retirar la frecuencia del motor de riesgo (CR-8)
- Llamar a `RiskEngine.record_execution` desde la sesión 24/7 (como ya hacen el simulador y el backtester), y resolver la contradicción
  5/símbolo/día vs 20/día (un solo símbolo ⇒ el tope efectivo sería 5). Tests: tras un trade,
  `trade_cooldown` rechaza durante 300 s. Aceptación: el embudo muestra la razón `cooldown` cuando
  corresponde. Riesgo: baja la frecuencia; es intencional.

### P2-C Atribución
- `live.no_trade` con `strategy_id`, `strategy_version`, `confidence`, `regime`; `strategy_id`
  acreditado = opinión de mayor fuerza (la misma que da stop y objetivo) o lista completa de
  co-firmantes. Tests: una señal co-firmada por dos estrategias registra ambas. Aceptación: el
  embudo por estrategia de §10 deja de ser NO_PERSISTED.

### P2-D Instrumental de monitoreo
- Corregir las cuatro consultas con `GROUP BY` sobre el literal; volcar `orders` y actividad
  completa por checkpoint; capturar `expected_value.as_dict()` de cada evaluación. Aceptación: un
  `PACK.txt` reproduce §6 y §7 sin consultas adicionales.

### P2-E Funding y HTF
- Investigar por qué el monitor de funding no devolvió tasa en 12 h (`last_rate=null`); el modo
  HTF `hard` con `bias=flat` fue un no-op: documentar o exigir marea para operar.

### P3 Observabilidad y documentación
- Mostrar en Learning el conjunto de evidencia de cada estimador; renombrar `disproven` en la UI
  a algo que no implique prueba; documentar que `settings_market_data.provider` no aplica a paper-live.

### Pruebas transversales (G y H del pedido)
- Estados `unknown/unproven/disproven/proven` asignados por tabla de casos con IC; propiedad
  "ninguna fila sintética aparece en el conjunto de autorización"; leakage: un outcome con
  `closed_at` posterior a la decisión nunca entra al estimador que la tomó (test con reloj
  controlado); contaminación: dos bases (sintética, real) se cargan por separado y la unión solo
  existe en el estimador "investigar".

---

## 16. Protocolo de la siguiente simulación (Fase J, sin ejecutar)

**Prerrequisito.** Sin P1-C y P1-B (como mínimo) la próxima corrida repetirá esta: el gate de EV
seguirá cerrado por evidencia sintética y la exploración seguirá sin juzgar. Si se quiere medir
antes de cambiar código, la única opción honesta es una corrida **de observación**: igual que esta,
pero con el instrumental P2-D capturando `expected_value.as_dict()` por señal, para estimar cuántas
señales habrían pasado con cada corrección (contrafactual sin secuencia, con sus límites de §11).

**Diseño recomendado (post-correcciones P1-A/B/C/E, P2-A/C/D).**

- Duración: **7 días** continuos (10.080 velas), para cubrir sesiones asiática/europea/americana y
  un fin de semana; con la frecuencia observada (2 exploratorios/12 h) 12 h no alcanzan ni para
  medir la frecuencia. Prolongable a 14 si la frecuencia resultante es < 2 trades/día.
- Qué guardar: todo P2-A más el `PACK` horario; velas públicas de la ventana; snapshot de
  configuración y hash de código al inicio; conjunto de evidencia de autorización al inicio (ids).
- Métricas pre-registradas: embudo por etapa y estrategia; trades por estrategia/dirección/régimen;
  media neta por trade con IC 90 % (bootstrap sobre trades); profit factor; max drawdown; exposición
  (% de minutos con posición); costos medios por componente; distribución de distancias de stop en
  bps y en σ; MAE/MFE; tasa de fills maker; discrepancias de reconciliación.
- Gráficos: equity vs buy-and-hold **con la misma ventana y 10.000 USDT**, descomponiendo retorno
  = exposición × retorno de mercado + selección + costos; histograma de netos por trade; embudo
  apilado por hora; stop/σ.
- Condiciones de parada: drawdown ≥ 2 % del capital; cualquier reinicio con posición abierta;
  feed sin velas > 10 min; ruptura de reconciliación; skew > 2.500 ms; cualquier orden fuera del
  simulador (imposible por construcción, pero se verifica).
- Reglas anti-sobreajuste: parámetros congelados y publicados antes de arrancar (hash del
  `.env` redactado y de `config.py`); ningún cambio durante la ventana; métricas definidas antes;
  si se hace una segunda corrida con parámetros distintos se declara como nueva prueba, no como
  continuación.
- Tamaño muestral: con `σ_real` desconocida no hay cálculo defendible. El piloto de 7 días mide
  `σ_real` y la frecuencia `f`. Después: `n = (z_{1−α/2} + z_{1−β})² · σ² / δ²`; con α = 0,10,
  potencia 0,80 (suma de z ≈ 2,5), δ = 5 bps y σ = 40 bps (orden de magnitud de un trade de 1 m
  con stop 10 y objetivo 15), `n ≈ 400` trades por estrategia; con σ = 80 bps, `n ≈ 1.600`. A 2
  trades/día eso son años: el piloto debe decir si la frecuencia tras P1 es compatible con la
  pregunta, o si el horizonte debe cambiar (P1-D).
- Inconclusa si: < 30 trades juzgados en alguna estrategia activa; uptime del feed < 99 %; algún
  reinicio; cualquier condición de parada; o si > 50 % de los trades salen de un solo régimen.
- "Prometedora" (no "rentable"): media neta > 0 con IC 90 % cuyo límite inferior > −5 bps; profit
  factor > 1,2; drawdown < 1 %; resultados del mismo signo en ≥ 2 regímenes y en ambas direcciones
  si la estrategia las produce; embudo con rechazos explicables; 0 incidentes de integridad. Una
  caída menor que buy-and-hold **no** cuenta: la descomposición debe mostrar selección positiva,
  no solo exposición baja.

---

## 17. Comandos de reproducción seguros (solo lectura, en el VPS)

```bash
# Fase A — estado real hoy (nada se modifica)
cd /home/tia/Trader-IA
echo "head=$(git rev-parse --short HEAD) branch=$(git branch --show-current) dirty=$(git status --porcelain | wc -l)"
docker inspect -f 'backend status={{.State.Status}} health={{.State.Health.Status}} restarts={{.RestartCount}} image={{.Config.Image}}' trader-ia-backend-1
docker inspect -f 'postgres status={{.State.Status}} health={{.State.Health.Status}} restarts={{.RestartCount}}' trader-ia-postgres-1
docker exec trader-ia-backend-1 curl -fsS --max-time 5 http://127.0.0.1:8000/api/health
docker exec trader-ia-backend-1 python -c "from tia.core.config import get_settings; s=get_settings(); print('policy=',s.live.scoreboard_policy,'simulated_only=',s.is_simulation_only,'use_testnet=',s.live.use_testnet,'live_enabled=',s.live.enabled,'mm_real_money=',getattr(s.mm,'real_money',None))"
R=live_01M4BP8GBCYAV30YAECK2H1RJ3
docker exec trader-ia-postgres-1 psql -U tia -d tia -At \
 -c "SELECT 'alembic', version_num FROM alembic_version;" -c "SELECT 'schema', version FROM schema_info;" \
 -c "SELECT 'runs_by_mode', mode, COUNT(*), COUNT(*) FILTER (WHERE stopped_at IS NULL) AS open FROM runs GROUP BY 2 ORDER BY 2;" \
 -c "SELECT 'activation_attempts', COUNT(*) FROM activation_attempts;" \
 -c "SELECT 'edge_by_source', source, COALESCE(market_data,'<NULL>'), COALESCE(execution_mode,'<NULL>'), COUNT(*) FROM edge_outcomes GROUP BY 2,3,4 ORDER BY 2,3,4;" \
 -c "SELECT 'H1_expected_net', outcome_id, ROUND(expected_net_bps::numeric,3), ROUND(net_bps::numeric,3), ROUND(confidence::numeric,3) FROM edge_outcomes WHERE run_id='$R' ORDER BY closed_at;" \
 -c "SELECT 'H5_recent_order', run_id, MIN(closed_at), MAX(closed_at), COUNT(*) FROM edge_outcomes WHERE market_data='synthetic' GROUP BY run_id ORDER BY 3 DESC LIMIT 5;" \
 -c "SELECT 'synthetic_buckets', regime, direction, CASE WHEN confidence<0.55 THEN '0.00-0.55' WHEN confidence<0.70 THEN '0.55-0.70' WHEN confidence<0.85 THEN '0.70-0.85' ELSE '0.85-1.01' END, COUNT(*), ROUND(AVG(net_bps)::numeric,2), ROUND((STDDEV_SAMP(net_bps)/SQRT(COUNT(*)))::numeric,2), ROUND(AVG(gross_bps)::numeric,2), ROUND(AVG(fees_bps)::numeric,2), ROUND((100.0*COUNT(*) FILTER (WHERE net_bps>0)/COUNT(*))::numeric,1) FROM edge_outcomes WHERE market_data='synthetic' GROUP BY 2,3,4 ORDER BY 2,3,4;"

# H-2 / H-3 — textos exactos de los rechazos de EV y de riesgo, y motivo completo de las exploraciones
EV=$(cat /home/tia/tia-testnet/paper12h_CURRENT)
python3 - "$EV" <<'PY'
import json, sys, glob, collections, re
ev = sys.argv[1]; seen = set(); evr = collections.Counter(); risk = collections.Counter()
for f in sorted(glob.glob(f"{ev}/ckpt_*/activity.json")):
    try: rows = json.load(open(f))
    except Exception: continue
    for r in rows if isinstance(rows, list) else []:
        d = r.get("data") or {}; key = (r.get("at"), r.get("type"), d.get("correlation_id"), d.get("stage"))
        if key in seen: continue
        seen.add(key); t = r.get("type")
        if t == "live.exploration": print("EXPLORATION", r.get("at"), d.get("reason"))
        if t != "live.no_trade": continue
        reason = re.sub(r"[-+]?\$?\d[\d,]*\.?\d*", "#", d.get("reason", ""))[:180]
        (evr if d.get("stage") == "expected_value" else risk)[reason] += 1
print("\nEV refusals by pattern:"); [print(n, "|", k) for k, n in evr.most_common()]
print("\nrisk refusals by pattern:"); [print(n, "|", k) for k, n in risk.most_common()]
PY
```

Ninguno de estos comandos escribe, reinicia ni imprime secretos.

---

## Anexo — Lo que esta auditoría no hizo

No ejecutó comandos en el VPS (trabajó sobre el código del commit `ab68d1c` y sobre capturas ya
realizadas), no corrió los tests, no modificó parámetros ni umbrales, no inició simulaciones y no
tocó código ni configuración. Archivo creado: este documento. Archivo previo sin seguimiento en el
workspace: `docs/PAPER_REALTIME_12H_REPORT.md`.
