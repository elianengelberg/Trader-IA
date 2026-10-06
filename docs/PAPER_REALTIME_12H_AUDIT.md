# Auditoría previa — simulación de trading de 12 h sobre mercado real (Binance Mainnet, datos públicos, ejecución simulada)

Commit auditado: `9bd4b17` (rama `claude/algo-trading-simulation-platform-ngf7xo`). Auditoría de solo lectura:
no se modificó código, configuración ni evidencia. Fecha: 2026-10-06.

Este documento responde a la primera fase del pedido ("Primero AUDITAR. Después EJECUTAR. Después OBSERVAR.
Después RECONSTRUIR. Finalmente AUDITAR"). Nada de lo que sigue autoriza por sí mismo la ejecución: la
decisión queda en manos del operador tras leer la sección 9.

Convención de etiquetas: **FACTO** (leído en el código o medido), **INFERENCIA** (deducción directa de
factos), **HIPÓTESIS** (plausible, no verificada), **NO VERIFICADO** (no comprobable desde este entorno;
el VPS y Binance no son alcanzables desde el contenedor de desarrollo: `curl` a `api.binance.com`,
`data-api.binance.vision` y `fapi.binance.com` devuelve HTTP 000).

---

## 0. Resumen ejecutivo

1. **El sistema ya contiene exactamente la sesión pedida**: `POST /api/live/paper-start` arranca el runtime
   real de Trader-IA (`LiveRuntime`) sobre datos públicos de Mainnet en tiempo real (WebSocket `kline_1m`
   + `bookTicker`, REST como respaldo) y sobre un simulador de ejecución (`PaperExecutionProvider`).
   Funciona sin credenciales y está diseñada para correr 24/7 con reanudación tras reinicios. **FACTO.**
2. **El camino de órdenes termina en el simulador, demostrado por código** (sección 2). El único
   constructor de ejecución real (`BinanceExecutionProvider`) vive en dos funciones que `paper-start` no
   toca, y el runtime exige token de activación únicamente cuando el proveedor declara `is_live`. **FACTO.**
3. **Cuatro requisitos del pedido NO se cumplen con el código actual** y no se pueden cumplir sin cambios:
   - fills simulados a partir del libro de órdenes (el simulador es **bar-based**: usa OHLCV de la vela
     1 m siguiente; su propio docstring dice "There is no order book");
   - estado del libro registrado por fill (no existe en la tabla `fills`);
   - latencia de ejecución medida (la del fill es una **constante configurada**: 120 + 60 ms);
   - persistencia de la curva de equity y de las decisiones de la sesión paper-live (no se escriben
     `equity_points` ni `decisions`; solo viven en memoria).
4. **Seis requisitos se cubren operativamente sin tocar el repo** (checkpoints cada 30 min, métricas de
   CPU/RAM, benchmark buy&hold, bloques de 2 h, exportación completa, 12 h continuas) mediante comandos
   en el VPS que leen la API y Postgres (sección 8).
5. **Tensión con la regla "NO conectar jamás a Binance Mainnet"**: la sesión abre conexiones de solo
   lectura a endpoints públicos de Mainnet (`api.binance.com`, `stream.binance.com`, `fapi.binance.com`
   para la tasa de funding). No hay firma, no hay API key, no hay endpoint de órdenes. Se ejecuta bajo la
   instrucción explícita del pedido actual; lo dejo escrito para que la excepción quede acotada.
6. **Recomendación**: ejecutar las 12 h con el sistema tal cual, etiquetando los fills como *bar-based*
   y la latencia como *CONFIGURADA / NOT MEASURED*, y decidir después, con el informe en mano, si
   conviene (a) agregar persistencia mínima (decisiones, equity, cotización por fill) para la siguiente
   corrida o (b) diseñar un simulador basado en libro. Secuenciar: primero cerrar la corrida pendiente de
   60 min del MM en Testnet (`9bd4b17`), después las 12 h, para no mezclar CPU/RAM ni evidencia.

---

## 1. Alcance y método

Archivos leídos íntegra o parcialmente:

- `packages/tia/src/tia/api/state.py` (`start_paper_realtime` 2186–2277, `_carried_session_pnl`,
  `stop_realtime_session` 2296–2309, `_maybe_resume_paper_realtime` 2311–2380, `_persist` 650–700,
  `_build_mm_live_provider` ~1485–1500, `_build_live_runtime` ~2130–2150, `orders`/`fills` 768–785,
  `health` ~2520–2560, `prometheus_metrics` ~2625–2650).
- `packages/tia/src/tia/api/app.py` (rutas `/api/live/*`, `/api/orders`, `/api/fills`, `/api/journal`,
  `/api/health`, `/api/metrics`, `/api/auth/login`).
- `packages/tia/src/tia/runtime/live.py` (constructor 222–240, `LatencyTracker` 118–180, `start` 534–605,
  `_cycle_once` 880–955, `_process_bar` 956–1300, `_manage_resting` 1482–1547, `_accrue_funding`
  1549–1600, `_check_liquidation` 1600–1645, `_refresh_quote` 1660–1688, `_on_fill` 2036–2073,
  `_reconcile` 2210–2300, `snapshot` 2570–2690).
- `packages/tia/src/tia/execution/paper.py` (completo), `tia/execution/provider.py`,
  `tia/domain/portfolio.py` (`apply_fill`, `equity`).
- `packages/tia/src/tia/data/providers/binance_public.py`, `binance_stream.py`, `tia/data/funding.py`.
- `packages/tia/src/tia/persistence/models.py` (tablas y columnas), `repositories.py` (firmas).
- `packages/tia/src/tia/core/config.py` (`ExecutionSimConfig` 118–140, `LiveConfig` 299–410).
- `docker-compose.prod.yml`, `.env.production.example`, `docs/DEPLOYMENT.md` §9, `docs/LIVE_RUNBOOK.md`,
  `SYSTEM_STATUS.md`, `scripts/daily_report.py`, `scripts/endurance.py`.

No ejecuté nada contra el VPS ni contra Binance. Todo lo que dependa del estado real del VPS (si hay una
sesión paper corriendo, si las credenciales están presentes, si la región alcanza Mainnet) está marcado
**NO VERIFICADO** y tiene su comando de verificación en la sección 8.

---

## 2. Prueba de seguridad del camino de órdenes

### 2.1 Punto de entrada

`POST /api/live/paper-start` (`app.py:946`) → `AppState.start_paper_realtime` (`state.py:2186`). **FACTO.**

Qué construye, en orden (`state.py:2206–2259`):

| Paso | Objeto | Qué es | Referencia |
|---|---|---|---|
| 1 | `BinancePublicProvider(base_url=settings.live.public_data_url)` | Cliente REST **público, sin firma ni API key** ("Market data only — no key, no signature, and no order-placing surface exists on this class", `binance_public.py:63`). Endpoints: `/api/v3/klines`, `/api/v3/time`, `/api/v3/ticker/bookTicker`, `/api/v3/depth`, `/api/v3/aggTrades`. | `state.py:2208`, `binance_public.py:176,206,214,241,268,314` |
| 2 | `BinanceStreamProvider(rest, symbol, timeframe, stream_url)` | WebSocket público `wss://stream.binance.com:9443/stream?streams=btcusdt@kline_1m/btcusdt@bookTicker`; reconexión con backoff 1–30 s; si el stream lleva > 10 s sin eventos, REST es la verdad. | `state.py:2213–2221`, `binance_stream.py:48,52,56,179,308` |
| 3 | `PaperExecutionProvider(settings.execution, DEFAULT_UNIVERSE, clock, RngRegistry(seed), initial_capital=capital + prior_pnl)` | **Simulador de ejecución.** Declara `is_simulated=True`. | `state.py:2227–2233`, `paper.py:52,66` |
| 4 | `FundingMonitor` (si `charge_funding`) | Lee `GET https://fapi.binance.com/fapi/v1/premiumIndex` (Futures Mainnet, público, sin firma) para la tasa de funding. No envía nada. | `state.py:2234–2238`, `funding.py:43` |
| 5 | `LiveRuntime(settings, activation=None, market_data=market, execution=execution, ...)` | El runtime real, **sin token de activación**. | `state.py:2240–2253` |

El comentario del propio código fija la intención: "Mainnet public data on purpose, whatever use_testnet
says: paper's execution is simulated, and a track record needs real spreads" (`state.py:2206–2207`).
**FACTO.** Consecuencia: `TIA_LIVE__USE_TESTNET` no interviene en esta sesión (sigue en su valor; no hace
falta tocarlo). **INFERENCIA.**

### 2.2 Por qué una orden no puede llegar a Binance

1. **El proveedor decide si es "live"**: `ExecutionProvider.is_live` devuelve `not capabilities.is_simulated`
   (`provider.py:100–102`). El simulador declara `is_simulated=True` (`paper.py:66`) → `is_live == False`.
   **FACTO.**
2. **`assert_may_trade` es no-op para simuladores** (`provider.py:108–116`), y el constructor de la clase
   base rechaza construir un proveedor no simulado sin token (`provider.py:72–75`). **FACTO.**
3. **El runtime exige token solo si el proveedor es live** (`live.py:222–233`): "a provider that can spend
   real funds demands a token; a simulator demands none". Con `activation=None` y un simulador, la
   construcción es válida; con `activation=None` y un proveedor live, lanza `LiveActivationError`. **FACTO.**
4. **Único punto de envío**: toda orden del runtime pasa por `self._execution.submit_order(intent)`
   (entradas, stops protectores `OrderType.STOP`, salidas de mercado por expiración: `live.py:1420–1441`,
   `1535`, `1869–1876`, `1977`). `self._execution` es el objeto del paso 3. **FACTO.**
5. **Dónde sí se construye ejecución real**: `BinanceExecutionProvider` (`binance_live.py:112`, con
   `_ORDER_PATH = "/api/v3/order"`) aparece en exactamente dos sitios del paquete:
   `AppState._build_live_runtime` (`state.py:~2142`, requiere el token del gate `/api/live/arm` y un
   `signer` con credenciales) y `AppState._build_mm_live_provider` (`state.py:~1497`, camino del MM).
   `start_paper_realtime` no llama a ninguno de los dos ni construye un `signer`. **FACTO.**
6. **Credenciales**: la sesión paper no las lee. En `docker-compose.prod.yml:145–146` las variables
   `TIA_LIVE__BINANCE_API_KEY/SECRET` vienen vacías por defecto ("The 24/7 paper session needs none").
   Si estuvieran presentes en el `.env` del VPS, el camino `paper-start` igual no las consume (no hay
   `signer_from_live_config` en ese camino). **FACTO** sobre el código; presencia/ausencia en el VPS:
   **NO VERIFICADO** (comando en §8.1, imprime solo `set`/`unset`).
7. **Modo reportado**: `snapshot()["mode"]` es `"paper-live"` y `snapshot()["simulated"]` es `True`
   cuando `not execution.is_live` (`live.py:2578–2579`); la fila en `runs` se crea con `mode="paper-live"`,
   `scenario="realtime"` (`state.py:2266–2274`). El primer checkpoint debe confirmar ambos. **FACTO.**

### 2.3 Hosts que la sesión contacta (todos públicos, solo lectura)

| Host | Protocolo | Para qué | Firma |
|---|---|---|---|
| `api.binance.com` | HTTPS GET | klines 1 m (historial y respaldo), `time`, `bookTicker` de respaldo | ninguna |
| `stream.binance.com:9443` | WSS | `kline_1m` y `bookTicker` en tiempo real | ninguna |
| `fapi.binance.com` | HTTPS GET | `premiumIndex` (tasa de funding del perpetuo) | ninguna |

Ningún `POST`, ningún `DELETE`, ningún header `X-MBX-APIKEY` en estos clientes (`binance_public.py`
no contiene la cadena; `funding.py` tampoco). **FACTO.** Geo: `api.binance.com` responde 451 a IPs de
datacenter en EE. UU.; el VPS está en Frankfurt y la ruta pública ya fue verificada allí el 2026-08-18
(`SYSTEM_STATUS.md:125–132`). **FACTO** histórico; vigencia hoy **NO VERIFICADO**.

---

## 3. Qué hace exactamente la sesión (pipeline por vela)

Ciclo (`_cycle_once`, `live.py:880–955`): el loop despierta al cierre de vela o cada 10 s
(`poll_interval_seconds=10.0`, `state.py:2252`). En cada ciclo:

1. Latido (`last_heartbeat`). Watchdog de datos: sin vela nueva durante 300 s → `HALT_NEW_ORDERS`
   (`market_data_ttl_seconds = 300`); se recupera solo con una reconciliación limpia (`live.py:888–895,
   941–952`).
2. Chequeo de desfase de reloj contra el venue cada N ciclos; > ±2 500 ms → halt (`MAX_CLOCK_SKEW_MS`).
3. Reconciliación cada 12 ciclos (`reconcile_every_cycles=12`, ≈ 2 min) → fila en `reconciliations`.
4. `get_candles(limit=200)`; si hay vela cerrada nueva: refresca cotización (`bookTicker`) y tendencia HTF;
   **el simulador casa las órdenes en reposo contra la vela cerrada** (`on_bar(latest)`); gestiona la
   orden en reposo (timeout 3 velas), funding, posición abierta (stops, liquidación); luego
   `_process_bar`.
5. `_process_bar` (`live.py:956–1300`): calidad de datos → features → régimen → estrategias → gate HTF
   (`hard`) → scoreboard (mute) → una sola orden en reposo a la vez → RiskEngine → presupuesto de riesgo
   (perfil `balanced`: 0,5 % por trade, 20 entradas/día) → límite de pérdida del ledger → **gate de spread**
   (cotización real del `bookTicker`; > 10 bps rechaza) → **EV enforce** (con exploración paper: hasta
   20 trades/día al 25 % del tamaño, en buckets sin evidencia) → sizing por convicción → orden de entrada
   **LIMIT** (`TIA_LIVE__ENTRY_ORDER_TYPE=limit`, timeout 3 velas) → stop protector `STOP` en el
   simulador; salida expirada → `MARKET`.

Toda la estrategia, el riesgo y el EV son los de producción; nada de esto se toca. **FACTO.**

---

## 4. Modelo de fills del simulador (lo que el pedido llama "simulación de ejecución")

`PaperExecutionProvider` (`paper.py`). **FACTO** salvo indicación:

| Aspecto | Comportamiento | Referencia |
|---|---|---|
| Fuente | **OHLCV de la vela 1 m siguiente** a la orden; "There is no order book" (docstring). Una orden creada en la vela *t* no puede llenarse con *t* (`created_at >= close_time` → espera). | `paper.py:229–258` |
| MARKET | Precio de referencia = `open` de la vela siguiente, más slippage adverso. | `paper.py:328–329` |
| LIMIT / LIMIT_MAKER | Exige **trade-through**: compra si `low < limit` (no basta tocar); precio `min(limit, open)`. LIMIT_MAKER se trata igual que LIMIT (ambos en `_MAKER_TYPES`); no se simula el rechazo post-only por cruzar. | `paper.py:48,331–340` |
| STOP / STOP_LIMIT / TAKE_PROFIT | Disparan en extremos de la vela; el STOP se llena al peor entre stop y open. | `paper.py:342–372` |
| Slippage | `2 bps base + 0,35·√(participación)·100 + min(5 % del rango de la vela en bps, 25)`, siempre adverso, acotado al rango `[low, high]`. | `paper.py:388–420`, `config.py:127–135` |
| Capacidad | Máximo 10 % del volumen de la vela por fill. | `paper.py:376–386`, `config.py:133` |
| Parciales / rechazos | RNG determinístico por seed: parcial con prob. 0,15 (35–85 % del remanente), rechazo con prob. 0,01. | `paper.py:422–432`, `config.py:138–139` |
| Fees | Maker 2,5 bps (LIMIT, LIMIT_MAKER), taker 7,5 bps (resto). Por defecto; prod no los sobreescribe (`docker-compose.prod.yml` no define `TIA_EXECUTION__*`). | `paper.py:287–290`, `config.py:127–128` |
| Latencia | **Constante configurada**: `submit_latency_ms + ack_latency_ms = 120 + 60 = 180 ms`, estampada en cada fill como `latency_ms`. Los timestamps de estado se desplazan por esos valores; no hay espera real. | `paper.py:196–209,304`, `config.py:136–137` |
| Libro | El `bookTicker` **sí** entra en la decisión (gate de spread, `top_of_book_quantity` para el costo EV, `live.py:1125–1160`) pero **no** en el matching. | `live.py`, `paper.py` |

Consecuencias para el pedido:

- **Requisito "fills basados en el libro (MARKET/LIMIT/LIMIT_MAKER)": NO CUMPLIDO.** El simulador es
  bar-based. Un diseño basado en libro requeriría el stream de profundidad (ya existe en el MM:
  `LocalOrderBook` + `depth@100ms` en `tia/mm`) y un modelo de cola. Es trabajo nuevo, no un ajuste.
- **Requisito "estado del libro registrado por fill": NO CUMPLIDO.** La tabla `fills` guarda
  `price, quantity, fee, slippage_bps, latency_ms, liquidity, filled_at` (`models.py:222–248`); no hay
  bid/ask/tamaños. La última cotización vive en memoria (`_last_quote`) y no se persiste por fill.
- **Requisito "latencia real o NOT MEASURED": PARCIAL.** Lo que sí se mide: el camino de decisión en el
  host (`LatencyTracker`: `market_received → decision → risk → order_submit → order_ack → fill_received`,
  reloj monotónico, persistido en `latency_samples`, `live.py:118–180, 1461–1475`). Lo que no se mide:
  la latencia de venue (`submit_to_ack` en el simulador es procesamiento local, microsegundos; el
  `latency_ms` de cada fill es la constante 180 ms). En el informe final la latencia de ejecución se
  reportará como **CONFIGURADA (180 ms), NOT MEASURED**. La latencia de datos sí se mide
  (`feed.latency_ms`, event time del exchange vs reloj local, `binance_stream.py:248–250,347–350`)
  pero solo se expone en el snapshot, no se persiste.
- **Fees**: 2,5/7,5 bps son supuestos. La cuenta se modela como perpetuo apalancado; para Spot VIP0 sin
  BNB la tarifa real es 10/10 bps, para Futures USDⓈ-M VIP0 es 2/5 bps. Se declararán como supuesto.
  **FACTO** sobre el modelo, **HIPÓTESIS** sobre la tarifa aplicable a una cuenta real.

---

## 5. Capital virtual y cuenta simulada

| Parámetro | Valor en prod | Fuente |
|---|---|---|
| Capital inicial | 10 000 USDT (`TIA_LIVE__PAPER_CAPITAL`) **más el P&L realizado previo** que el registro `edge_outcomes` (source `live`) ya tenga: `initial_capital = capital + prior_pnl` | `state.py:2224–2233`, `_carried_session_pnl` |
| Apalancamiento | 5× (`TIA_LIVE__LEVERAGE`); margen de mantenimiento 0,5 %; fee de liquidación 50 bps | `docker-compose.prod.yml:139–142`, `live.py:1600–1645` |
| Funding | Cada 8 h, a la tasa real del perpetuo (`fapi premiumIndex`); solo si hay posición abierta; una tasa ausente se cuenta en `funding.skipped_no_rate`, nunca se inventa | `live.py:1549–1600` |
| Perfil de riesgo | `balanced`: 0,5 % por trade, 20 entradas/día | compose `TIA_LIVE__RISK_PROFILE` |
| Exploración | 20 trades/día al 25 % del tamaño, solo en buckets sin evidencia; marcados `exploratory=true` en `edge_outcomes` | compose, `live.py:1176–1265` |
| Entrada | LIMIT en reposo, timeout 3 velas; HTF `hard`; spread máx. 10 bps; sizing por convicción (mín. 0,35, cap pooled 0,6) | compose |
| Contabilidad | `cash -= signed_qty·price + fee`; `equity = cash + Σ signed_notional` (marcado al cierre de cada vela) | `portfolio.py:198–206, 162–165` |

**Salvedad importante**: si la base del VPS ya tiene round trips `source='live'` de sesiones paper
anteriores, la equity inicial **no será 10 000**; el snapshot lo declara (`account.starting_capital`,
`account.prior_realised_pnl`, `account.equity`). El primer checkpoint debe fijar esos tres números como
punto de partida documentado. **FACTO** sobre el mecanismo; valor concreto **NO VERIFICADO**.

---

## 6. Qué queda persistido y qué no (retención y auditabilidad)

`LiveRuntime` persiste exactamente seis clases de artefacto (`grep _save(` en `live.py`): `order` (4
sitios), `fill`, `edge_outcome`, `latency`, `reconciliation`, `incident`. **FACTO.**

| Dato | ¿Persiste? | Dónde | Observación |
|---|---|---|---|
| Fila de la corrida | Sí | `runs` (`run_id, mode='paper-live', scenario='realtime', started_at, stopped_at, initial_capital, seed, symbols`) | Un reinicio del backend crea **otro `run_id`** sobre la misma evidencia (`_maybe_resume_paper_realtime`). Cualquier discontinuidad queda visible aquí. |
| Órdenes y ciclo de vida | Sí (estado final) | `orders` (`client_order_id, side, order_type, quantity, limit_price, stop_price, state, filled_quantity, average_fill_price, fees_paid, reject_reason, created_at, updated_at`) | Las transiciones intermedias no se escriben (`events` no tiene escritor en el paquete). El estado final + `fills` reconstruyen el ciclo. |
| Fills | Sí | `fills` (`price, quantity, fee, slippage_bps, latency_ms, liquidity, filled_at, sequence`) | Sin cotización/libro por fill. |
| Round trips cerrados | Sí | `edge_outcomes` (`regime, direction, confidence, entry/exit price, quantity, gross/fees/net bps, exploratory, expected_net_bps, exit_reason, strategy_id, closed_at, source='live'`) | Es la fuente para win rate, net bps, régimen por trade. |
| Latencias de decisión (host) | Sí | `latency_samples` (segmentos ms, total) | Medidas con reloj monotónico. |
| Reconciliaciones | Sí (≈ cada 2 min) | `reconciliations` (`clean, divergences`) | Compara equity del ledger vs equity del simulador, tolerancia máx(1 USD, 2 %). |
| Incidentes | Sí | `incidents` | Halts, SAFE_MODE, liquidaciones, fallas de resume. |
| **Decisiones por vela** (por qué no operó) | **No** | — | Solo en memoria: `recent_refusals` (20), `live_activity` (150 eventos), `funnel` (contadores acumulados en el snapshot). `/api/decisions` lee el runtime de simulación, no la sesión paper-live. |
| **Curva de equity** | **No** | — | `equity_points` no se escribe para paper-live (el kind `equity` del `_persist` solo aplica al runtime de simulación, `state.py:688–696`). Solo `snapshot()["account"]["equity"]` en memoria → de ahí la necesidad de checkpoints externos. |
| Pagos de funding | **No** | — | Solo contadores en el snapshot (`funding.payments, paid_usd, last_rate`) y evento en memoria. |
| Velas y cotizaciones | **No** | — | Las velas 1 m se pueden volver a descargar de Binance (públicas, históricas); el `bookTicker` **no** (no hay historial público) → el spread visto en cada decisión se pierde salvo en los checkpoints. |
| Snapshot completo | **No** | — | `GET /api/live` (requiere sesión de operador). |

`/api/fills` y `/api/orders` sirven **deques en memoria** (`state.py:768–785`), no la base: la exportación
completa debe salir de Postgres (§8.5). `scripts/daily_report.py` usa ventanas de 24 h por fecha UTC y
lee `equity_points` (vacío para esta sesión) → sirve como contraste, no como informe de las 12 h.

---

## 7. Mapa requisito por requisito

Leyenda: **CUMPLE** (código actual) · **OPERATIVO** (sin tocar el repo, con comandos en el VPS) ·
**PARCIAL** · **NO CUMPLE** (requiere código) · **POST-RUN** (lo produce la reconstrucción/análisis).

| # | Requisito | Estado | Cómo / por qué |
|---|---|---|---|
| 1 | Prueba de seguridad del camino de órdenes | **CUMPLE** | §2. Verificación en vivo: `mode == "paper-live"`, `simulated == true`, `activation == null` en el primer checkpoint. |
| 2 | Datos de mercado reales en tiempo real | **CUMPLE** | WSS `kline_1m` + `bookTicker` Mainnet; REST respaldo; `feed.transport`, `latency_ms`, `reconnects` en el snapshot. |
| 3 | Estrategia exacta de Trader-IA sin cambios | **CUMPLE** | Mismo `LiveRuntime`, misma config prod. Nada se toca. |
| 4 | Capital virtual documentado | **CUMPLE** con salvedad | 10 000 USDT + P&L previo del registro (§5). Se fija en el checkpoint 0. |
| 5 | Fills simulados a partir del libro (MARKET/LIMIT/LIMIT_MAKER) | **NO CUMPLE** | Bar-based (§4). Se reportará como "fills bar-based, no de libro". |
| 6 | Estado del libro registrado por fill | **NO CUMPLE** | No hay columnas ni captura por fill. Solo la cotización del checkpoint más cercano (30 min). |
| 7 | Latencia real o NOT MEASURED | **PARCIAL** | Host: medida y persistida. Venue: constante 180 ms → **NOT MEASURED**. Datos: medida, no persistida (checkpoints). |
| 8 | Fees maker/taker | **CUMPLE** (supuestos) | 2,5 / 7,5 bps; declarados como supuesto (§4). |
| 9 | Trades auditables | **CUMPLE** | IDs determinísticos (`deterministic_id`), `client_order_id` único, `fills` → `orders` → `edge_outcomes` por `run_id`. |
| 10 | Libro virtual de órdenes con ciclo de vida | **CUMPLE** (estado final) | `orders.state` + `fills`; transiciones intermedias solo en memoria. |
| 11 | Reconciliación cash + posición + fees = equity | **CUMPLE** | Automática ≈ cada 2 min (persistida). Ex-post, la identidad se recompone desde `fills` (§8.6). |
| 12 | Retención de datos | **PARCIAL** | Tablas de §6 sí; velas re-descargables; `bookTicker`, decisiones y equity solo vía checkpoints. |
| 13 | Checkpoints cada 30 min | **OPERATIVO** | Bucle en el VPS que guarda `GET /api/live`, `/api/health`, `/api/live/activity`, `docker stats` (§8.3). |
| 14 | 12 h continuas | **CUMPLE / OPERATIVO** | Sesión 24/7 con watchdog; un reinicio es visible en `runs`. La "continuidad" se audita por `runs` + checkpoints. |
| 15 | Contexto de régimen | **PARCIAL** | Por trade: `edge_outcomes.regime`. Por bloque de 2 h: no persistido; reconstruible offline con las velas + el mismo `RegimeClassifier` (script post-run, read-only, **después** de la revisión del informe). |
| 16 | Análisis de performance | **POST-RUN** | Desde `edge_outcomes`, `fills`, checkpoints. |
| 17 | Benchmark buy & hold | **OPERATIVO / POST-RUN** | Velas 1 m públicas del mismo intervalo (`open` de T0 → `close` de T0+12 h), con fee taker de ida y vuelta declarado. |
| 18 | Bloques de 2 h | **POST-RUN** | Trades y fills por `closed_at`/`filled_at`; equity con granularidad 30 min (checkpoints). |
| 19 | Post-mortem | **POST-RUN** | Lo escribo con la evidencia committeada. |
| 20 | Veredicto estricto por dimensión | **POST-RUN** | Performance / Execution / Reliability / Risk / Data Integrity / Production Readiness. Execution no podrá superar PASS WITH WARNINGS por §4. |
| 21 | No modificar código durante la simulación | **CUMPLE** | No se despliega nada al VPS durante la ventana; este documento es solo docs. |

---

## 8. Plan operativo propuesto (sin cambios de código en el repo)

Todo corre en el VPS como root, en `/home/tia/Trader-IA`, con la pila `docker-compose.prod.yml` ya
levantada. Los comandos leen la API desde dentro del contenedor `backend` (`http://127.0.0.1:8000`),
sin pasar por Caddy ni por TLS. Las credenciales de operador (`TIA_DEMO_USER/PASSWORD`) ya están en el
entorno del contenedor; el login las toma de ahí por `stdin` y **no se imprimen**. Ningún comando
imprime valores de secretos.

### 8.1 Pre-flight (antes de arrancar)

```bash
cd /home/tia/Trader-IA && git rev-parse --short HEAD && git status --short | head
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml exec -T backend curl -sS http://127.0.0.1:8000/api/health
# presencia/ausencia de credenciales dentro del contenedor (nunca el valor):
docker compose -f docker-compose.prod.yml exec -T backend sh -c \
  'for v in TIA_LIVE__BINANCE_API_KEY TIA_LIVE__BINANCE_API_SECRET; do eval "x=\${$v:-}"; [ -n "$x" ] && echo "$v set" || echo "$v unset"; done; echo "TIA_ENV=$TIA_ENV TIA_LIVE__USE_TESTNET=${TIA_LIVE__USE_TESTNET:-default} TIA_MM__REAL_MONEY=${TIA_MM__REAL_MONEY:-default}"'
# alcance Mainnet público desde el VPS (solo lectura):
curl -sS -o /dev/null -w 'api.binance.com %{http_code}\n' https://api.binance.com/api/v3/time
curl -sS -o /dev/null -w 'fapi.binance.com %{http_code}\n' https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT
df -h / | tail -1; date -u
```

Resultado esperado: HEAD `9bd4b17` (o el que se decida), árbol limpio, `backend`/`postgres`/`proxy` `Up`,
`/api/health` con `database: online`, credenciales **unset** (si estuvieran `set`, no bloquea la sesión
paper, pero conviene saberlo), HTTP 200 a ambos hosts.

### 8.2 Estado actual de la sesión paper y arranque

```bash
cd /home/tia/Trader-IA
EV=/home/tia/tia-testnet/paper12h; mkdir -p "$EV"
# login (cookie dentro del contenedor; password por stdin desde el entorno del contenedor)
docker compose -f docker-compose.prod.yml exec -T backend sh -c \
  'printf "{\"username\":\"%s\",\"password\":\"%s\"}" "$TIA_DEMO_USER" "$TIA_DEMO_PASSWORD" | curl -sS -o /dev/null -w "login %{http_code}\n" -c /tmp/tia.cookie -H "Content-Type: application/json" --data-binary @- http://127.0.0.1:8000/api/auth/login'
# ¿hay sesión activa?
docker compose -f docker-compose.prod.yml exec -T backend curl -sS -b /tmp/tia.cookie http://127.0.0.1:8000/api/live \
  | tee "$EV/live_before_start_$(date -u +%Y%m%dT%H%M%SZ).json" | python3 -c 'import json,sys; d=json.load(sys.stdin); print({k:d.get(k) for k in ("active","state","mode","simulated","run_id")})'
```

Decisión del operador según el resultado:

- `active: false` → arrancar:
  ```bash
  docker compose -f docker-compose.prod.yml exec -T backend curl -sS -b /tmp/tia.cookie -X POST http://127.0.0.1:8000/api/live/paper-start \
    | tee "$EV/ckpt_000_start_$(date -u +%Y%m%dT%H%M%SZ).json" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("run_id",d["run_id"],"mode",d["mode"],"simulated",d["simulated"],"activation",d["activation"],"state",d["state"]); a=d["account"]; print("starting_capital",a["starting_capital"],"prior_realised_pnl",a["prior_realised_pnl"],"equity",a["equity"])'
  ```
  Verificar: `mode paper-live`, `simulated True`, `activation None`, `state running`.
- `active: true` → ya hay una sesión 24/7 corriendo. Dos opciones: (a) tomar **esa** sesión y fijar T0 en
  el primer checkpoint (la corrida ya tiene historia; la ventana de 12 h se corta por tiempo), o (b)
  `POST /api/live/stop` y `paper-start` para un `run_id` limpio (el stop queda estampado en `runs`; el
  P&L previo se arrastra igual al capital inicial). Recomiendo (b) por limpieza de la evidencia; es
  decisión del operador.

### 8.3 Checkpoints cada 30 min (12 h = 24 checkpoints + final)

Script **fuera del repo** (`/home/tia/tia-testnet/paper12h/checkpoint.sh`), que re-loguea en cada
iteración (sobrevive a reinicios del backend) y guarda: `GET /api/live`, `GET /api/health`,
`GET /api/live/activity?limit=150`, `GET /api/fills?limit=500`, `GET /api/orders?limit=500` y
`docker stats --no-stream` de `backend` y `postgres`.

```bash
cat > /home/tia/tia-testnet/paper12h/checkpoint.sh <<'EOF'
#!/bin/sh
# Checkpoint de la sesión paper-realtime: solo lecturas. Sin secretos en disco ni en stdout.
set -u
cd /home/tia/Trader-IA || exit 1
EV=/home/tia/tia-testnet/paper12h
N=${1:-0}; TS=$(date -u +%Y%m%dT%H%M%SZ); P="$EV/ckpt_$(printf %03d "$N")_$TS"
DC="docker compose -f docker-compose.prod.yml exec -T backend"
$DC sh -c 'printf "{\"username\":\"%s\",\"password\":\"%s\"}" "$TIA_DEMO_USER" "$TIA_DEMO_PASSWORD" | curl -sS -o /dev/null -c /tmp/tia.cookie -H "Content-Type: application/json" --data-binary @- http://127.0.0.1:8000/api/auth/login'
for ep in live health "live/activity?limit=150" "fills?limit=500" "orders?limit=500"; do
  name=$(echo "$ep" | tr '/?=&' '____')
  $DC curl -sS -b /tmp/tia.cookie "http://127.0.0.1:8000/api/$ep" > "${P}_${name}.json"
done
docker stats --no-stream --format '{{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}' > "${P}_docker_stats.txt"
python3 - "$P" <<'PY'
import json,sys
p=sys.argv[1]; d=json.load(open(p+"_live.json")); a=d.get("account",{}); f=d.get("feed",{})
print(p.split("/")[-1], d.get("state"), d.get("mode"), "equity", a.get("equity"), "pos_open", d.get("position",{}).get("open"),
      "bars", d.get("counters",{}).get("bars"), "fills", d.get("counters",{}).get("fills"),
      "feed", f.get("transport"), "lat_ms", f.get("latency_ms"), "reconnects", f.get("reconnects"))
PY
EOF
chmod +x /home/tia/tia-testnet/paper12h/checkpoint.sh
# bucle de 12 h (25 checkpoints: 0..24, cada 1800 s), en segundo plano, con log propio
nohup sh -c 'i=0; while [ $i -le 24 ]; do /home/tia/tia-testnet/paper12h/checkpoint.sh $i; i=$((i+1)); [ $i -le 24 ] && sleep 1800; done' \
  > /home/tia/tia-testnet/paper12h/checkpoint.log 2>&1 &
echo "loop pid $!"
```

Tiempo T0 = timestamp del `ckpt_000`. Fin de ventana = `ckpt_024` (T0 + 12 h).

### 8.4 Durante las 12 h

Nada. No se despliega, no se reinicia, no se cambia configuración. Si el backend se reinicia por sí
solo, la sesión se reanuda con otro `run_id` y queda registrado en `runs`; se analiza como incidente de
*Reliability*, no se oculta.

### 8.5 Exportación completa desde Postgres (al cierre de la ventana)

```bash
cd /home/tia/Trader-IA; EV=/home/tia/tia-testnet/paper12h
PG="docker compose -f docker-compose.prod.yml exec -T postgres psql -U tia -d tia -At"
$PG -c "SELECT run_id, mode, scenario, started_at, stopped_at, initial_capital, seed FROM runs WHERE mode='paper-live' ORDER BY started_at DESC LIMIT 5" | tee "$EV/runs_tail.txt"
RUN=<run_id del ckpt_000>   # (o varios, si hubo reinicio)
for t in orders fills edge_outcomes latency_samples reconciliations incidents; do
  docker compose -f docker-compose.prod.yml exec -T postgres psql -U tia -d tia \
    -c "\copy (SELECT * FROM $t WHERE run_id='$RUN' ORDER BY 1) TO STDOUT CSV HEADER" > "$EV/${t}_${RUN}.csv"
  wc -l "$EV/${t}_${RUN}.csv"
done
# velas 1 m públicas de la ventana (para benchmark buy&hold, régimen por bloque y marcado final)
START_MS=<T0 en ms>; END_MS=$((START_MS + 12*3600*1000))
curl -sS "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&startTime=$START_MS&endTime=$END_MS&limit=1000" > "$EV/klines_1m_${RUN}.json"
python3 -c 'import json,sys; k=json.load(open(sys.argv[1])); print(len(k),"velas", k[0][0], "->", k[-1][6])' "$EV/klines_1m_${RUN}.json"
python3 scripts/daily_report.py --db "$TIA_DATABASE_URL" --json > "$EV/daily_report_$(date -u +%Y%m%d).json" 2>/dev/null || true
```

Luego copiar `$EV` a `docs/evidence/paper12h_<RUN>/`, commit **solo de evidencia** ("Evidence: …,
unmodified") y push, como con las corridas del MM. Yo la bajo y hago la reconstrucción.

### 8.6 Reconstrucción y reconciliación ex-post (lo que haré con la evidencia)

- `cash_T = capital_inicial − Σ(signed_qty·price) − Σ fee − Σ funding − Σ fee_liquidación`;
  `pos_T = Σ signed_qty`; `equity_T = cash_T + pos_T·mark_T` con `mark_T` = cierre de la última vela
  pública; se compara con `account.equity` del checkpoint final y con la última fila `reconciliations`.
  Funding y liquidación salen de los contadores del snapshot (no están en tablas): se declara.
- Buy & hold: `(close_fin / open_T0 − 1)` sobre el mismo capital, menos 2 × 7,5 bps declarados.
- Bloques de 2 h: trades/fills por timestamp; equity por checkpoints (granularidad 30 min).
- Régimen por bloque: **requiere un script offline** (velas + `RegimeClassifier`) → se propone después
  de la revisión, no antes.

---

## 9. Lo que requiere código (para decidir DESPUÉS de revisar este informe; nada se implementa ahora)

Ordenado por costo creciente. Ninguno toca estrategia, riesgo, EV ni rails.

| Ítem | Qué falta | Tamaño | Afecta comportamiento económico |
|---|---|---|---|
| A | Persistir `decisions` (incl. refusals del funnel) y `equity_points` para la sesión paper-live; persistir pagos de funding | Pequeño (ruteo en `_persist`, `_save` en el runtime, tests) | No |
| B | Guardar la cotización `bid/ask/sizes/spread_bps` y la edad del dato por fill y por orden | Pequeño (columnas + migración + `_on_fill`) | No |
| C | Exportar CPU/RSS en `/api/metrics` (hay `resource.getrusage` en `endurance.py`) | Pequeño | No |
| D | Reporte de ventana arbitraria (`--since/--until`) con bloques, régimen y buy&hold en `daily_report.py` o script nuevo | Mediano | No |
| E | Checkpoint periódico interno (en lugar del bucle externo) | Pequeño | No |
| F | **Simulador basado en libro** (depth stream + modelo de cola + post-only real para LIMIT_MAKER + latencia inyectada) | Grande; diseño aparte, reutilizando `tia/mm` (`LocalOrderBook`, `depth@100ms`) | **Sí** (cambia los fills; necesita validación propia) |

Mi recomendación: A + B + C para la **siguiente** corrida; F solo si el objetivo pasa a ser validar
microestructura de ejecución, que para este runtime (velas 1 m, entradas LIMIT con 3 velas de espera)
pesa menos que para el MM.

---

## 10. Riesgos y condiciones de la corrida

- **Solapamiento con la corrida de 60 min del MM en Testnet** (pendiente sobre `9bd4b17`): corre como
  proceso aparte en el mismo VPS. Recomiendo terminar esa primero. Si se solapan, CPU/RAM de
  `docker stats` no se podrán atribuir limpiamente. **INFERENCIA.**
- **Reinicio del backend** durante las 12 h: la sesión se reanuda sola, con `run_id` nuevo, sobre un
  `PaperExecutionProvider` **nuevo y plano** (`PortfolioState.initial(capital + P&L realizado previo)`).
  No existe código que reconstruya desde `fills` una posición abierta ni las órdenes en reposo
  (`grep replay` en `live.py` no muestra ningún camino de reconstrucción; el propio snapshot dice
  "position_cost_basis: UNKNOWN until fills are replayed"). Una posición abierta en el momento del
  reinicio desaparece del simulador sin cerrarse y su round trip nunca llega a `edge_outcomes`; el
  P&L no realizado de ese trade no se contabiliza en ningún lado. Esto sería un hallazgo de
  Reliability y de Data Integrity, y la reconciliación ex-post (§8.6) lo detectaría como diferencia
  entre la posición recompuesta desde `fills` y la del snapshot. **INFERENCIA** directa del código;
  no observado.
- **Feed stale** > 300 s → halt de entradas; `health.trading_engine: degraded` > 120 s. Se registran
  como incidentes. **FACTO.**
- **Skew de reloj** > 2,5 s → halt; el start falla si el skew inicial lo supera. **FACTO.**
- **`fapi.binance.com` inalcanzable** → funding omitido y contado, no inventado. **FACTO.**
- **Capital inicial ≠ 10 000** si hay P&L previo en el registro (§5). Se documenta en `ckpt_000`.
- **Un solo símbolo**: `BTC-USD` → `BTCUSDT` (`to_venue_symbol`). **FACTO.**
- **Pocos trades en 12 h**: con perfil balanced, HTF hard, spread gate y EV enforce, es plausible que la
  sesión opere poco o nada; el informe tratará "no operar" como resultado válido con su funnel, no como
  fallo. **HIPÓTESIS** sobre la frecuencia.

---

## 11. Clasificación final de esta auditoría

- **FACTO**: todo lo referenciado con `archivo:línea` en §2–§6; la inalcanzabilidad de Binance desde el
  entorno de desarrollo.
- **INFERENCIA**: que `TIA_LIVE__USE_TESTNET` no afecta la sesión paper; que el snapshot del primer
  checkpoint bastará para probar el modo; que el solapamiento con el MM contamina CPU/RAM.
- **HIPÓTESIS**: frecuencia de trades en 12 h; comportamiento de la reanudación con posición abierta;
  tarifa real aplicable a la cuenta modelada.
- **NO VERIFICADO**: estado actual del VPS (sesión activa, credenciales presentes, alcance Mainnet hoy,
  HEAD desplegado, espacio en disco).

**Decisión pendiente del operador**: ejecutar las 12 h con el sistema tal cual (plan §8), con los
requisitos 5, 6 y 7 declarados como NO CUMPLIDO / NOT MEASURED en el informe final, o posponer hasta
implementar A–B (§9) para la siguiente corrida. No se escribirá código hasta que esa decisión llegue.
