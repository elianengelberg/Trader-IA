# Auditoría previa al Market Maker profesional (Fase 1)

*Fecha: 2026-09-18. Alcance: todo lo que existe hoy en Trader-IA que un market maker
necesitaría, verificado archivo por archivo, y lo que falta. Sin código nuevo: este
documento es el entregable de la Fase 1. Todo lo que aquí figura como "no existe" no
se simula; se implementa antes de usarlo.*

---

## 1. Arquitectura actual

### 1.1 Cadena de autoridad (vigente, no se toca)

```
DATA → FEATURES → STRATEGY PROPOSAL → EVIDENCE / EXPECTED VALUE → RISK ENGINE → EXECUTION → JOURNAL → LEARNING
```

Implementada en `tia/runtime/live.py` (`LiveRuntime._process_bar`) para la sesión 24/7 y
en `tia/runtime/engine.py` (`RuntimeEngine._process_bar`) para simulaciones. El orden real
en la sesión es: calidad de datos → features → régimen → estrategias → marea (1–4 semanas)
→ scoreboard por estrategia → **RiskEngine** (veto) → posición abierta → estado de la
máquina → presupuesto de riesgo → ledger de capital → spread gate → **ExpectedValueEngine**
→ guardrails de aprendizaje → exploración → dimensionado por convicción → `_submit`. Cada
rechazo queda en el embudo (`funnel`) con su motivo. Nada llega a ejecución sin pasar por
`RiskEngine.evaluate` y por `ExpectedValueEngine.evaluate`.

### 1.2 Market data que EXISTE hoy

| Fuente | Módulo | Contenido | Timestamps del exchange | Secuencia |
|---|---|---|---|---|
| REST klines | `data/providers/binance_public.py` `get_candles` | velas cerradas 1m…1d, hasta 1000 | `openTime`/`closeTime` de la vela | no |
| REST bookTicker | `binance_public.py` `get_quote` | mejor bid/ask + tamaños | **ninguno** (el endpoint spot no lo trae; se estampa hora local) | no |
| REST depth | `binance_public.py` `order_book(limit=20)` | 20 niveles bid/ask, como lista cruda | ninguno | **`lastUpdateId` se descarta** (no se parsea) |
| WS `kline_1m` | `data/providers/binance_stream.py` | vela en formación y cierre (`x`) | `E` (event time) → latencia medida (última y EMA) | no |
| WS `bookTicker` | `binance_stream.py` | mejor bid/ask en cada cambio | **ninguno** en spot | `u` (update id) llega en el payload pero **no se usa** |
| REST klines 1h | `binance_stream.py` → REST | contexto de marea (1–4 semanas) | sí | no |
| Funding/basis | `data/funding.py` (fapi premiumIndex + fundingRate, cada 5 min) | funding, mark, index | `time`/`fundingTime` | no |
| Otros exchanges | `data/arbitrage.py` (REST cada 15 s) | top of book Binance/Coinbase/Kraken | no | no |
| Noticias | `data/intel.py` (RSS cada 15 min) | titulares filtrados | fecha de publicación | no |

Modelos de dominio disponibles (`domain/market.py`): `Candle`, `Quote` (bid, ask, tamaños; sin
update id), `TradePrint` (precio, tamaño, agresor; **definido pero ningún proveedor lo
produce**), `OrderBookLevel` / `OrderBook` (**definidos, no usados**: el REST depth devuelve
un dict crudo), `MarketSnapshot`.

### 1.3 Market data que NO existe hoy

| Dato | Estado | Consecuencia |
|---|---|---|
| **diff-depth** (`<sym>@depth@100ms`, `U`/`u` por evento) | no existe | no hay libro local sincronizado |
| **snapshot de profundidad con `lastUpdateId`** | el endpoint se llama pero el id se descarta | no se puede alinear un snapshot con el stream |
| **trades / aggTrades** (`<sym>@trade`, `<sym>@aggTrade`; `t`/`a`, `T`, `m` = buyer is maker) | no existe | no hay flujo de órdenes real, ni agresor, ni intensidad |
| **raw trades históricos** | no hay ninguno almacenado | replay tick a tick imposible hoy |
| **sequence ids del exchange** | ninguno consumido | no hay detección de gaps ni de desorden |
| **queue information** | Binance **no lo publica** (libro L2 agregado; no hay L3 ni posición en cola) | la posición en cola solo puede ESTIMARSE; hay que decirlo así |
| **order acknowledgements** | REST: la respuesta a `POST /api/v3/order` es el ack (`binance_live.py`); en papel el ack es inmediato | no hay ack asíncrono; no hay `executionReport` |
| **execution reports / user data stream** | **no se consume**. La verificación `USER_DATA_STREAM` de la compuerta solo comprueba que un `listenKey` se abre y cierra en el script de validación | los fills reales se descubren por polling de la orden y `myTrades` |
| **execution IDs** | reales: `myTrades.id` → `Fill.fill_id`; papel: ids deterministas | existe, pero solo por polling |
| **order IDs** | `Order.order_id` (venue `orderId` en real, `o-N`/deterministas en papel) + `client_order_id` determinista (idempotencia) | existe; no hay `replace`/amend nativo |
| **timestamp de exchange en bookTicker spot** | no lo trae el exchange | la latencia solo se mide con klines (y con depth/trades cuando existan) |
| **percentiles de latencia (p50/p95/p99)** | `LatencyTracker` guarda etapas por orden y una EMA; no calcula percentiles | falta agregación |

### 1.4 Ejecución

- Interfaz `ExecutionProvider` (`execution/provider.py`): `submit_order`, `cancel_order`,
  `get_order`, `get_orders`, `get_positions`, `get_balance`, `get_trades`, `get_pnl`,
  `get_portfolio`, `resolve_unknown_order` (opcional), `close`. **No hay `replace`**: un
  reprice es cancelar y volver a colocar.
- `Order` / `Fill` (`domain/orders.py`): máquina de estados de 13 estados con transiciones
  validadas (`execution/state_machine.py`); `Fill` lleva `liquidity` maker/taker,
  `latency_ms`, `sequence`. No hay campo de execution id ni de secuencia del exchange en
  `Order`.
- **Papel** (`execution/paper.py`): matching **por vela** en `on_bar`. Market: se ejecuta al
  open de la vela siguiente con slippage e impacto (raíz de la participación). Limit: se
  ejecuta cuando la vela **atraviesa** el límite (`low < limit` para compras), es decir
  "price crossed → fill", con tope de participación (`max_participation_rate` × volumen de
  la vela) y fills parciales aleatorios (15%). **No hay** cola, ni libro, ni latencia
  variable, ni matching intra-vela. Comisiones del simulador: maker 2,5 / taker 7,5 bps
  (`ExecutionSimConfig`), **por debajo del nivel minorista real de Binance (10/10)**: hay
  que revisar qué fija el `.env` de producción antes de que el market maker use ese número.
- **Real** (`data/providers/binance_live.py`): solo REST firmado (`/api/v3/order`,
  cancel, consulta por `clientOrderId`, `myTrades`, balances). Sin stream de usuario.
- Reconciliación (`LiveRuntime._reconcile`): órdenes, posiciones y saldo cada 12 ciclos;
  en papel compara equity, en real clasifica movimientos de saldo.
- Cuenta simulada de la sesión: `CapitalLedger` + `PaperExecutionProvider` con margen,
  liquidación y funding (`paper_capital`, `leverage`).

### 1.5 Riesgo, evidencia, aprendizaje

- `RiskEngine.evaluate(signal, portfolio, features, quality, now)`: calidad, breakers
  (drawdown, pérdida diaria), condiciones de mercado (spread, volatilidad), frecuencia
  (cooldown, cap diario), **sizing por distancia al stop** (`risk/sizing.py`), límites de
  cartera. Recibe un `SignalCandidate`; una cotización no tiene "stop" — hace falta un
  adaptador, no un bypass.
- `ExpectedValueEngine.evaluate(regime, direction, confidence, costs)` con `EdgeEstimator`:
  buckets `(régimen | dirección | banda de confianza)`, piso 30 muestras, encogimiento por
  error estándar, backoff al régimen (60 muestras, doble descuento), guardia de
  decaimiento (últimos 60), umbral 5 bps, cost ratio 60%. La evidencia son round trips en
  bps netos.
- `RetrospectiveEngine` (lecciones, guardrails), `StrategyScoreboard` (silencio por
  estrategia), `MentorEngine` (propuestas que aplica un humano).
- Estrategias (`strategy/base.py`): `Strategy.evaluate(features, regime) -> StrategyOpinion`
  (dirección, fuerza, referencias de entrada/stop/objetivo). Un market maker no encaja en
  esta interfaz: propone **cotizaciones**, no una dirección.

### 1.6 Persistencia, observabilidad, infraestructura

- Postgres 16, tablas: runs, events, decisions, orders, fills, positions, equity_points,
  assessments, logs, backtests, news, edge_outcomes (v5, con `strategy_id`, `exit_reason`,
  `exploratory`, `ingested_at`), activation_attempts, reconciliations, capital_events,
  incidents, latency_samples. **No hay tablas de ticks ni de libro.**
- Eventos: bus en memoria (`events/bus.py`, con opción Redis no desplegada), SSE a la web,
  feed de actividad (150 eventos), logs estructurados (`structlog`) persistidos.
- Backtest (`backtest/engine.py`): por velas; walk-forward con aserción de no-fuga
  (`walkforward.py`). **No hay replay tick a tick.**
- Compuerta de dinero real: 27 verificaciones (`live/gate.py` `CheckName`), incluidas
  `USER_DATA_STREAM`, `EV_ENFORCEMENT`, `FEES_VERIFIED_AT_SOURCE`, `EDGE_EVIDENCE`,
  `PAPER_TRACK_RECORD`. El track record ignora trades de exploración.
- Docker: `backend`, `postgres`, `proxy` (Caddy), `backup`. VPS de 2 vCPU / 2 GB.
- Web: Dashboard (command center, sesión, embudo "Why no trade"), Markets (ladder desde REST
  depth), Orders & Fills, Strategy & Costs, Trade Journal, Learning, Live Trading, etc.

---

## 2. Arquitectura propuesta

Un paquete nuevo `tia/mm/` (market making), aislado, que **propone** y nunca ejecuta por su
cuenta. Cadena:

```
Binance WS depth@100ms + trade + bookTicker (+ REST snapshot con lastUpdateId)
   → DepthStream / TradeStream           (mm/streams.py)      datos crudos + timestamps + ids
   → LocalOrderBook                      (mm/order_book.py)   snapshot + diffs, U/u, gaps → invalidar/reconstruir
   → BookFeatures                        (mm/features.py)     top-1/5/10/20, microprice, imbalances, depth, impacto
   → OrderFlowEngine                     (mm/order_flow.py)   taker buy/sell, intensidad, tamaño, ventanas 100ms…10s
   → MicrostructureSignalEngine          (mm/microstructure.py) velocidad, aceleración, spread expansion, depth collapse
   → MarketToxicityEngine                (mm/toxicity.py)     toxicity_score (solo reduce)
   → FairValueEngine                     (mm/fair_value.py)   fair_value + confianza + incertidumbre, interpretable
   → AdverseSelectionEngine              (mm/adverse_selection.py) post-fill return por horizonte, evidencia
   → SpreadEngine + InventoryManager     (mm/spread.py, mm/inventory.py)
   → AdaptiveMarketMaker + QuotingStateMachine (mm/quoting.py, mm/states.py)
        emite QuoteProposal(bid?, ask?, tamaños, TTL, motivo)
   → MarketMakingCostModel               (mm/costs.py)        capture bruto/neto por cotización
   → QuoteEvidence                       (mm/evidence.py)     EdgeEstimator reutilizado con buckets de cotización
   → **ExpectedValueEngine** (existente, método `evaluate_quote`) → NO QUOTE si el neto no supera el umbral
   → **RiskEngine** (existente, método `evaluate_quote`) → mismos breakers, exposición, frecuencia; sizing por pérdida adversa esperada
   → MarketMakerOrderManager             (mm/orders.py)       place / cancel / (replace = cancel+place) / TTL / reconciliación, sobre ExecutionProvider
   → QueueAwarePaperExecution            (mm/sim.py)          cola estimada, fills solo por trades reales al nivel, parciales, latencia
   → Journal (edge_outcomes con strategy_id="market_maker") + observaciones por fill (mm/metrics.py)
   → Learning (retrospectiva y scoreboard existentes; observaciones de fills para adverse selection)
```

Principios de integración:

- **Autoridad**: `RiskEngine` y `ExpectedValueEngine` ganan métodos `evaluate_quote` que
  reutilizan exactamente los mismos breakers, límites, pisos y descuentos. No se añade
  ninguna ruta que los evite. El `MarketMakerOrderManager` solo recibe propuestas que
  vuelven aprobadas de ambos.
- **Dinero real imposible**: el runtime del market maker se construye únicamente con un
  `ExecutionProvider` simulado; si `execution.is_live` es verdadero, el constructor
  lanza. Flags `ADAPTIVE_MARKET_MAKER_ENABLED=false` y
  `ADAPTIVE_MARKET_MAKER_REAL_MONEY=false` (el segundo no tiene efecto alguno en esta
  fase: existe para que un test demuestre que ponerlo en `true` sigue sin abrir ninguna
  ruta). Las 27 verificaciones no se tocan.
- **Cuenta y ledger propios**: el market maker opera sobre su propia
  `PaperExecutionProvider` y su propio `CapitalLedger` (capital configurable), separados
  de la sesión 24/7. Así el P&L, el inventario y la evidencia se atribuyen sin mezcla y la
  sesión existente no cambia de comportamiento.
- **Datos reales / ejecución simulada**: cada fill del simulador lleva `simulated=True`
  y el motivo del fill (qué trades reales lo produjeron); ningún fill se produce por
  "el precio tocó el nivel".
- **Registro tick a tick**: un `TickRecorder` (mm/recorder.py) guarda depth diffs, trades y
  bookTicker con timestamps de exchange y locales, en archivos por hora (JSONL comprimido)
  bajo `data/ticks/`, con un índice en Postgres. Es el insumo del `MarketReplayEngine`.
  Sin esto no hay replay ni backtest posibles: Binance publica históricos de aggTrades
  (REST `aggTrades` y volcados mensuales) pero **no** de profundidad.

---

## 3. Archivos existentes que habría que modificar

| Archivo | Cambio | Riesgo |
|---|---|---|
| `data/providers/binance_public.py` | `order_book` devuelve `lastUpdateId` y el modelo `OrderBook`; nuevo `agg_trades(from_id, limit)` | bajo (aditivo; la página Markets sigue leyendo bids/asks) |
| `data/providers/binance_stream.py` | añadir streams `depth@100ms`, `trade`/`aggTrade` y usar `u` del bookTicker; distribución por suscriptores | medio: es el feed de la sesión 24/7; se hace opt-in por símbolo/streams para no cambiar su comportamiento |
| `domain/market.py` | `OrderBook` gana `last_update_id`/`first_update_id`; `TradePrint` gana `trade_id`, `event_time`, `is_buyer_maker` | bajo (campos opcionales) |
| `domain/orders.py` | `Fill` gana `simulated: bool`, `queue_ahead_at_fill`, `venue_trade_ids` opcionales | bajo |
| `risk/engine.py` | método nuevo `evaluate_quote` que reutiliza `_check_breakers`, `_check_market_conditions`, `_check_frequency`, `_apply_portfolio_limits`; sizing por pérdida adversa esperada en vez de stop | medio: no cambia `evaluate`; tests de equivalencia |
| `economics/expected_value.py` | `EdgeEstimator` parametrizable por clave de bucket (hoy fija a régimen/dirección/banda); `ExpectedValueEngine.evaluate_quote` | medio: la clave actual se mantiene por defecto |
| `economics/costs.py` | `FeeSchedule` verificado contra `.env` de producción; sin cambios de interfaz | bajo |
| `execution/paper.py` | sin cambios; el simulador de cola es una subclase/composición nueva | nulo |
| `persistence/models.py` + migración 0006 | tablas `mm_quotes`, `mm_fills` (observaciones), `mm_book_stats`, `tick_files` | medio: migración aditiva |
| `api/state.py`, `api/app.py` | servicio lazy del market maker, rutas `/api/mm/*`, eventos `mm.*` | bajo |
| `core/config.py` | `MarketMakingConfig` completo (flags en `false`) | bajo |
| `docker-compose.prod.yml`, `.env.example` | variables `TIA_MM__*`; volumen para `data/ticks` | bajo |
| `frontend/` | página "Market Making", tipos, nav | bajo |
| `docs/RESEARCH_CRYPTO_METHODS.md` | sección con hipótesis/datos/método/resultados/incertidumbre | — |

Ningún archivo de estrategia (`strategy/library.py`), ni la compuerta (`live/gate.py`), ni
los límites (`RiskLimits`) se modifican.

## 4. Módulos nuevos

`tia/mm/streams.py`, `order_book.py`, `features.py`, `order_flow.py`, `microstructure.py`,
`toxicity.py`, `fair_value.py`, `adverse_selection.py`, `queue.py`, `spread.py`,
`inventory.py`, `quoting.py`, `states.py`, `orders.py`, `costs.py`, `evidence.py`,
`sim.py`, `recorder.py`, `replay.py`, `backtest.py`, `metrics.py`, `latency.py`,
`runtime.py` (el `MarketMakerRuntime` que orquesta y expone snapshot/embudo); tests en
`tests/unit/mm/`, `tests/integration/mm/`, `tests/security/mm/`; `frontend/src/views/MarketMaking.tsx`.

## 5. Datos que faltan y cómo se obtienen (sin inventar)

| Falta | Fuente real | Fase |
|---|---|---|
| Libro local sincronizado | WS `btcusdt@depth@100ms` (`U`, `u`) + REST `depth?limit=1000` (`lastUpdateId`), procedimiento documentado de Binance: bufferizar eventos, tomar snapshot, descartar `u ≤ lastUpdateId`, exigir `U ≤ lastUpdateId+1 ≤ u` en el primer evento, luego continuidad `U == u_anterior + 1`; cualquier violación invalida y reconstruye | 2–3 |
| Flujo de órdenes real | WS `btcusdt@trade` (id `t`, hora `T`, `m`) — o `aggTrade` (`a`, `f`/`l`) | 2, 4 |
| Timestamps del exchange en quotes | del evento depth (`E`) y trade (`E`, `T`); el bookTicker spot no los trae y se documenta | 2 |
| Posición en cola | **no existe en Binance**. Se estima: al colocar, `queue_ahead = tamaño visible al nivel`; se descuenta por trades ejecutados a ese precio y por reducciones del nivel (cancelaciones), nunca por aumentos; hipótesis conservadora: última posición en cola al colocar. Se registra `estimated_*` y se compara después con lo que habría pasado | 8 |
| Acks / execution reports | en papel: el simulador emite ack con latencia configurable; en real (fuera de esta fase): user data stream `executionReport`, hoy no consumido | 12 (papel) |
| Histórico tick a tick | grabarlo desde ahora (`TickRecorder`); aggTrades históricos vía REST para análisis de flujo; la profundidad histórica solo desde nuestras grabaciones | 2, 14 |
| Percentiles de latencia | agregación p50/p95/p99 por etapa sobre `latency_samples` y sobre el stream | 19 |
| Comisiones verificadas | `.env` de producción / `validate_binance.py` (`FEES_VERIFIED_AT_SOURCE`); el modelo de costos usa el nivel minorista documentado hasta verificar | 20 |

## 6. Riesgos de implementación

1. **Optimismo del simulador**: el mayor riesgo. Mitigación: fills solo por trades reales
   al nivel después de consumir la cola estimada, parciales por tamaño real, latencia
   aplicada a colocación y cancelación, y cada fill etiquetado `simulated` con su causa.
2. **Costo de datos en el VPS (2 vCPU)**: depth@100ms + trades son decenas de mensajes por
   segundo. Mitigación: proceso asíncrono liviano, escritura por lotes a archivos JSONL
   comprimidos (no a Postgres por tick), estadísticas agregadas por segundo a la base.
3. **Sincronización de reloj**: la latencia contra `E` requiere NTP; el monitor de skew
   existe y se reutiliza. Se reporta con la advertencia de offset.
4. **Gaps y reconexiones**: el libro se invalida ante cualquier salto de secuencia; sin
   libro válido, sin cotizaciones (`PAUSED` → `RECOVERY` → `NORMAL`).
5. **Evidencia escasa**: buckets de cotización demasiado finos nunca llegan a 30 muestras.
   Mitigación: claves coarse (régimen × cuartil de spread × cuartil de toxicidad × lado),
   con backoff como el estimador actual.
6. **Fuga de look-ahead en el replay**: reproducción estrictamente por timestamp de
   recepción, decisiones solo con datos ya vistos, seed y configuración guardados.
7. **Colisión con la sesión 24/7**: mismo símbolo, misma cuenta. Mitigación: cuenta y
   ledger propios para el market maker; los límites de riesgo se evalúan sobre su
   propia cartera y, además, contra la exposición combinada.
8. **Sizing sin stop**: el `RiskEngine` dimensiona por distancia al stop. Para una
   cotización el equivalente honesto es la pérdida adversa esperada (del
   `AdverseSelectionEngine`, con piso configurable); nunca menor que la comisión de ida
   y vuelta.
9. **Sobreajuste de parámetros**: walk-forward obligatorio; ningún parámetro cambia en
   producción sin propuesta, registro, comparación con baseline y aprobación humana.
10. **Ruta a dinero real**: se cierra por construcción (constructor rechaza proveedores
    reales) y se prueba con tests de seguridad que intentan cada bypass.
11. **Volumen de trabajo**: 20 fases, cada una con tests; se entrega por fases
    verificadas (9/9) y se detiene ante cualquier conflicto con funcionalidad existente.

## 7. Decisiones que requieren confirmación antes de la Fase 2

1. **Cuenta separada** para el market maker (capital propio, p. ej. $10.000 simulados)
   en lugar de compartir la cuenta de la sesión 24/7.
2. **Grabación de ticks en disco** en el VPS (`data/ticks/`, del orden de 100–300 MB por
   día comprimidos) para hacer posible el replay; con rotación configurable.
3. **Comisiones**: usar el nivel minorista de Binance (maker 10 bps) en el modelo de
   costos del market maker aunque el simulador actual esté configurado con 2,5 bps, hasta
   que se verifiquen en la cuenta real.
