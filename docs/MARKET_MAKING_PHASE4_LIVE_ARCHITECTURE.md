# Market maker — Fase 4: arquitectura para ejecución real en Binance Spot (diseño e implementación)

**ESTADO = IMPLEMENTADO EN CÓDIGO, NO ACTIVADO, NO VALIDADO EN TESTNET.** Fecha: 2026-10-02.
Base: commit `564de85` (paper MM corriendo sobre el feed real con órdenes simuladas;
PHASE3_STATUS = IMPLEMENTATION, evidencia PENDIENTE, NO EDGE DETECTED).

Esta fase **no activa dinero real**. Agrega al repositorio la arquitectura que permitiría,
en un paso posterior y explícito del operador, cotizar en Binance Spot con órdenes
post-only — y la rodea de las mismas barreras que ya protegen al runtime direccional:
el `LiveActivationToken` que sólo emite `LiveActivationGate.arm()` tras los 27 chequeos y
la frase de confirmación, el `GlobalTradingSafetyGate` de solo lectura, y la regla de que
ninguna variable de entorno sustituye a una activación. `TIA_MM__REAL_MONEY` sigue sin
ser leída por nada. El paper MM sigue funcionando exactamente como antes (mismo journal,
mismo hash, mismos tests).

Principio rector, sin cambios: **DATA INTEGRITY > EXECUTION INTEGRITY > STATISTICAL
INTEGRITY > RISK > PnL.** En ejecución real se agrega una regla de desempate: **Binance
gana en cualquier discrepancia.** El estado local es una hipótesis; el venue es el hecho.

---

## 1. Arquitectura propuesta (y realizada)

```
MarketDataService (Fase 2, sin cambios)
        │  subscribe(kind, event, R)            ← camino caliente, síncrono, sin red
        ▼
MarketMakerEngine (Fase 3, extendido con tres puntos de inyección: execution, ledger, authorizers)
   DATA VALIDITY → GLOBAL SAFETY GATE → RISK CONTROLLER → [MMRiskAuthorizer] → QUOTING
   → [MMEconomicsAuthorizer] → execution.place / cancel_all        (paper: lista vacía de authorizers)
        │
        ├── PaperMarketMakerExecution  (tia/mm/sim.py, sin cambios de comportamiento; mode="paper")
        │
        └── LiveMarketMakerExecution   (tia/mm/execution.py; mode="live")
              │  valida maker-only con SymbolFilters del exchangeInfo; construye OrderIntent LIMIT_MAKER
              │  encola comandos (submit / cancel / resolve / poll) ── asyncio.Queue ──▶ worker asíncrono
              │  drena resultados (ack, reject, unknown, cancel, trades) en on_event()      ◀── deque
              ▼
        ExecutionProvider (abstracción de tia/execution/provider.py)
              └── BinanceExecutionProvider (tia/data/providers/binance_live.py; NUNCA importado desde tia/mm)
```

Piezas nuevas, todas en `tia/mm/` salvo el tipo de orden:

| Módulo | Qué hace | Qué no hace |
|---|---|---|
| `tia/domain/enums.py` + `orders.py` + `binance_live.py` | **`OrderType.LIMIT_MAKER`** (no existía: la premisa de que ya estaba implementado era incorrecta). Validador: requiere `limit_price`. Mapeo a `LIMIT_MAKER` **sin `timeInForce`**. `Fill.fee_asset` para no contabilizar una comisión en BNB como USDT. `get_trades(symbol=...)` para reconciliar antes de la primera orden. | No cambia el runtime direccional ni los 27 chequeos. |
| `tia/mm/execution.py` | Contrato `MMExecution` (place, cancel, cancel_all, open_orders, on_event, stats, mode). `SymbolFilters` (tick, step, minQty, maxQty, minNotional, `orderTypes` ∋ LIMIT_MAKER) y `validate_maker_order`. `LiveMarketMakerExecution`: ids únicos (`tiamm-<nonce>-<ms>-<seq>`), sólo LIMIT_MAKER, nunca MARKET ni LIMIT, nunca cruzando el libro local; timeout → `UNKNOWN` + bloqueo de nuevas órdenes + resolución por consulta (nunca reenvío); cancel/replace estricto (no se reemplaza un lado hasta que el venue confirma el cancel); fills **sólo** desde `get_trades()` (trade id, order id, isMaker, fee, fee asset); fills de órdenes desconocidas → crítico. | No contiene ninguna URL, ningún endpoint, ninguna credencial, ningún `httpx`. |
| `tia/mm/authorization.py` | `MMRiskAuthorizer` (ALLOW / REDUCE_ONLY / DENY con razones): compone el veredicto del gate global, el `RiskAllowance` del controlador, el tope de capital del token (`max_live_capital`), la validez del token con margen de expiración, la salud de la ejecución (órdenes UNKNOWN, errores de API) y el kill switch del MM. `MMEconomicsAuthorizer` (ALLOW / DENY por lado): captura esperada − fee maker − adverse selection medida − costo de inventario − slippage de unwind − riesgo de latencia − costo de requote, todos los componentes en el journal. | No llama a `RiskEngine.evaluate()` con una señal falsa; no crea long/short para el `ExpectedValueEngine`. |
| `tia/mm/kill_switch.py` | `MMKillSwitch` propio del MM, debajo del global: `engage(trigger, reason, severity, sticky)`; severidades `no_new_quotes` y `cancel_open` (sólo escala, nunca baja); un enganche sticky conserva su **primera causa** (las siguientes quedan en el historial); sticky requiere `release(approved_by=...)` (en la práctica: stop + start por un operador); los transitorios (`data`, `unknown_order_state`) se limpian solos cuando la condición cesa; alimenta el `system_unsafe` del gate, de modo que el bloqueo recorre el camino existente (`_block` → `cancel_all` → journal). | No libera ni toca el kill switch de la sesión ni el `RiskEngine`. |
| `tia/mm/live_ledger.py` | `LiveLedger`: parte de los **balances reales** (USDT libre, BTC libre+bloqueado, mark), contabiliza sólo fills confirmados con la **comisión del venue** (BNB → marcada `unconverted`, se usa el fee asumido y se cuenta aparte), `reconcile_balances()` adopta las cifras del venue y registra la discrepancia. | No arranca en $10.000; no se restaura desde la base de datos (siempre se reconstruye desde el venue). |
| `tia/mm/reconciliation.py` | Comparación pura: órdenes abiertas del venue vs locales (ajenas, desconocidas, faltantes), balances esperados vs reales con tolerancia de un step/tick, trades nuevos vs línea base. Produce `MMReconciliationReport` con severidad. | No repara nada por su cuenta. |
| `tia/mm/live_service.py` | `LiveMarketMakerService(MarketMakerService)`: `start_live()` (verifica filtros vs configuración, arranca el worker, **reconcilia primero**, siembra el ledger, suscribe), reconciliación periódica con histéresis (un desajuste de balances debe repetirse antes de adoptar las cifras del venue), **heartbeat** que hace avanzar el engine cuando el feed calla (expiran TTLs, la regla de edad de datos cancela), kill switch, `stop()` (cancelar, esperar acks, reconciliar, cerrar), `engage_kill_switch()`, `status()`. | No arranca al boot; no existe camino desde `adaptive_enabled`. |
| `tia/api/state.py` + `app.py` | `start_mm_live(operator, confirmation)` y los endpoints `/api/mm/live/status|start|stop|kill-switch|reconcile`. | Ningún endpoint pone `real_money=True`; ningún endpoint acepta credenciales ni capital. |

## 2. Archivos modificados

- `packages/tia/src/tia/domain/enums.py`, `domain/orders.py` — `LIMIT_MAKER`, validador, `Fill.fee_asset`.
- `packages/tia/src/tia/data/providers/binance_live.py` — mapeo `LIMIT_MAKER`, sin `timeInForce`, `commissionAsset`, `get_trades(symbol=)`.
- `packages/tia/src/tia/execution/paper.py` — un `LIMIT_MAKER` descansa y se llena como maker (los simuladores no rechazan por "cruzaría": eso es del venue).
- `packages/tia/src/tia/mm/sim.py` — `mode = "paper"` (un atributo; comportamiento idéntico).
- `packages/tia/src/tia/mm/engine.py` — kwargs opcionales `execution`, `ledger`, `authorizers` con defaults paper; dos puntos de autorización que no escriben nada en el journal cuando la lista está vacía.
- `packages/tia/src/tia/mm/ledger.py` — `apply_fill` factorizado en `_book(fill, fee)`; misma aritmética, mismo resultado.
- `packages/tia/src/tia/mm/service.py` — acepta `execution`, `ledger`, `authorizers`, `system_unsafe` compuesto; paper sin cambios.
- `packages/tia/src/tia/core/config.py` — parámetros de afinación del MM live (`live_*`): intervalos de reconciliación y sondeo, margen de expiración, errores de API por minuto, edge neto mínimo, cancel/replace estricto. **Ninguno activa nada.**
- `packages/tia/src/tia/api/state.py`, `api/app.py` — estado y rutas.
- `tests/unit/mm/test_engine_replay.py` — la prueba "nada en tia/mm puede alcanzar un execution provider" se reemplaza por la frontera nueva (§7).
- `docs/MARKET_MAKING_PHASE3_AUDIT.md` (§23, enlace a este documento), `.env.example` (comentarios).

## 3. Archivos nuevos

`tia/mm/execution.py`, `tia/mm/authorization.py`, `tia/mm/kill_switch.py`, `tia/mm/live_ledger.py`,
`tia/mm/reconciliation.py`, `tia/mm/live_service.py`; tests `tests/unit/mm/fake_venue.py`,
`test_mm_execution_live.py`, `test_mm_authorization.py`, `test_mm_kill_switch.py`,
`test_mm_reconciliation.py`, `test_mm_live_service.py`, `test_live_boundary.py`,
`tests/unit/test_order_types_limit_maker.py`; este documento.

## 4. Riesgos técnicos (y cómo se tratan)

1. **`LIMIT_MAKER` nunca se ejercitó contra Binance** (como todo el adaptador: REQUIRES VALIDATION). El código -2010 "would immediately match and take", la ausencia de `timeInForce`, el nombre del filtro `NOTIONAL`/`MIN_NOTIONAL` y `commissionAsset` están escritos desde la documentación. Se validan en Testnet antes de cualquier mainnet.
2. **Cancel ≠ desaparecido.** Entre el pedido de cancel y su confirmación la orden puede llenarse. Se trata así: el cancel se marca `requested`; el estado sólo cambia con la respuesta del venue; cualquier `executedQty` o trade posterior se contabiliza aunque la orden ya figure cancelada ("fill después de requote"); y con `live_strict_cancel_replace=True` no se coloca un lado nuevo hasta que el cancel del anterior se confirmó.
3. **Timeout = estado desconocido.** No se reintenta. La orden pasa a `UNKNOWN`, se bloquean nuevas órdenes y el worker consulta al venue por `origClientOrderId` (`resolve_unknown_order`): presente → se adopta; ausente → se marca `refused` (no se reenvía la intención; la próxima decisión colocará una cotización nueva si corresponde); la consulta falla → sigue bloqueado, kill switch tras N errores.
4. **Expiración del token y cancels.** El `ExecutionProvider` también exige token válido para **cancelar**. Si el token expira con órdenes descansando, no se podrían retirar. Por eso el autorizador niega cotizar y el servicio cancela todo cuando faltan `live_activation_expiry_margin_s` (120 s por defecto) para la expiración, mientras el token todavía sirve.
5. **Fills fuera del MM en la misma cuenta.** Un trade nuevo cuyo `orderId` no es nuestro, o una orden abierta sin nuestro prefijo, es crítico: NO QUOTE y cancel de lo nuestro. Implica que el MM live no convive con otra actividad en la misma cuenta (incluido el runtime direccional real). Es una limitación aceptada, no un descuido.
6. **Comisión en BNB.** Un fee en BNB no es un monto en USDT. Se contabiliza con el fee asumido del modelo de costos, se marca `fee_status="unconverted:BNB"` y se suma aparte. La conversión real queda para cuando el Testnet muestre el formato.
7. **Reloj.** `tia/mm` sigue en el camino de decisión: ningún `datetime.now()`; el reloj del provider y `now_ms` se inyectan. `created_at` de cada intención sale de `clock.now()`.
8. **CPU.** Un servicio live y el paper pueden coexistir sobre el mismo feed (dos suscriptores). En el droplet de 2 vCPU eso duplica el trabajo por evento; se mide antes de dejarlos juntos.
9. **Latencia física no resuelta** (§22.7 del audit): un libro atrasado segundos es inutilizable para cotizar en real. `usable` ya lo detecta; cotizar en real exige además la calibración de `TIA_MM__MAX_VENUE_AGE_S` y la causa raíz de los 4–11 s.

### Endpoints

- `GET /api/mm/live/status` (usuario autenticado): `running`, `state` (`not_started | quoting | no_quote | safe | stopping | stopped`), `is_live`, `real_money` (True sólo con provider real, que exige token), `activation`, `kill_switch`, `reconciliation`, `execution`, `ledger`, `open_orders`, `authorizations`.
- `POST /api/mm/live/start` (operador; body `{"confirmation": "<frase exacta>"}`): 403 sin `TIA_LIVE__ENABLED`, con frase incorrecta o sin credenciales; 409 sin market data, sin perfil de latencia, con grilla distinta a la del venue, con otro MM live corriendo o si el gate no pasa (venue real); 503 si el venue no responde. Respuesta: `started`, `initial_reconciliation`, y el status.
- `POST /api/mm/live/stop` (operador): cancela, espera confirmaciones, reconcilia, cierra el provider.
- `POST /api/mm/live/kill-switch` (operador; body `{"reason"}`): sticky; sin cotizaciones nuevas, cancela lo que descansa, reconcilia.
- `POST /api/mm/live/reconcile` (operador): reconciliación inmediata; devuelve el reporte.
- Ningún endpoint acepta credenciales, capital ni pone `real_money=True`. Los cuatro de mutación exigen rol operador.

## 5. Cómo se preserva el paper

- `PaperMarketMakerExecution` no cambia de lógica; sólo gana el atributo `mode = "paper"`.
- `MarketMakerEngine(config, latency=..., gate=...)` sin kwargs nuevos construye exactamente lo mismo que antes; la lista de autorizadores vacía no agrega claves al journal, así que el `journal_hash` de un replay es idéntico (test explícito).
- `MarketMakerService` paper no recibe provider; `AppState._start_market_maker` sigue construyéndolo igual; `adaptive_enabled` sigue arrancando **sólo** paper.
- Las rutas `/api/mm/market|state|journal|metrics` no cambian de forma; el frontend no cambia.

## 6. Cómo se garantiza baja latencia

- El camino caliente (`MarketDataService._handle` → `_on_market_event` → `engine.on_event` → `execution.on_event` → decisión → `execution.place/cancel_all`) es **síncrono** de punta a punta: no hay `await`, HTTP, SQL ni escritura a disco. `LiveMarketMakerExecution.place` sólo valida, construye y hace `queue.put_nowait`; `on_event` sólo drena una `deque` de resultados y actualiza diccionarios.
- La red vive en un **worker asíncrono** separado (`asyncio.Task`) que consume la cola FIFO: submit, cancel, resolve, sondeo de trades y de órdenes abiertas. La persistencia ya era asíncrona (cola propia del servicio).
- Test: el proveedor falso bloquea 10 s en cada llamada y el camino caliente igualmente retorna sin ceder el loop; además `inspect.iscoroutinefunction` es falso para `on_event`, `place`, `cancel`, `cancel_all`.
- El camino caliente no espera a la red para decidir: decide sobre el estado local y el worker ajusta ese estado cuando el venue responde.

## 7. Cómo se garantiza que ningún camino opere real sin activación

1. **El provider.** `ExecutionProvider.__init__` rechaza `is_simulated=False` sin `LiveActivationToken` + `Clock`; el token sólo lo emite `LiveActivationGate.arm()` (sentinela `_ISSUER`, no forjable). Sin cambios.
2. **La ejecución del MM.** `LiveMarketMakerExecution` rechaza en construcción un provider que diga `is_live` y no tenga `activation`; antes de **cada** submit llama `provider.assert_may_trade(fingerprint)`; el cancel lo chequea el provider.
3. **El servicio.** `start_mm_live` exige `TIA_LIVE__ENABLED=true`, market data corriendo, la **frase de confirmación exacta**, credenciales en el entorno del proceso, filtros del exchange y una reconciliación limpia. Si `use_testnet=false` (venue real), además ejecuta `gate.arm()` con los 27 probes, registra el intento (pase o no) y pasa el token al provider y a la autorización. Con `use_testnet=true` el provider es simulado por construcción contra `testnet.binance.vision`; no se emite token y `real_money` se reporta `False`.
4. **La frontera de código.** `tests/unit/mm/test_engine_replay.py`: ningún archivo de `tia/mm` nombra `binance_live`, `BinanceExecutionProvider`, `binance_signing`, `httpx`, `ccxt`, `LiveActivationGate`, `LiveActivationToken(`, `_ISSUER`, ni credenciales; sólo `execution.py` y `live_service.py` pueden nombrar la abstracción `ExecutionProvider`/`submit_order`; `real_money` sigue sin lectores. `tests/unit/mm/test_live_boundary.py`: por AST, ningún módulo de `tia.mm` importa `tia.data.providers.*` ni `tia.live.*`. `tests/unit/test_scope_boundary.py` sigue vigente (endpoints de órdenes sólo en el adaptador, credenciales sólo en la firma, sin reloj de pared en `mm`).
5. **El boot.** `AppState.startup()` arranca market data (`enabled`) y paper (`adaptive_enabled`). No existe rama que construya un `LiveMarketMakerService` al arrancar ni al reanudar.
6. **La bandera.** `TIA_MM__REAL_MONEY` sigue sin efecto; el test lo prueba con `MarketMakingConfig(real_money=True)`: la respuesta de `/api/mm/live/start` es idéntica.

## 8. Estrategia de tests

- **Paper intacto**: replay de un tape sintético con y sin la lista vacía de autorizadores → mismo `journal_hash`; `tests/unit/mm/*` existentes sin modificar salvo la frontera.
- **Adaptador live** (`test_mm_execution_live.py`, proveedor falso en memoria): sólo `LIMIT_MAKER`; nunca `MARKET`/`LIMIT`; ids únicos; cancel y cancel_all; timeout → `UNKNOWN`, bloqueo, sin reintento, resolución presente/ausente; -2010 → rechazo sin fallback; validación de tick/step/minQty/minNotional y de cruce con el libro; cancel/replace estricto; fills sólo desde trades (maker/taker, fee, fee asset, dedupe por trade id); fill después de cancel; orden desaparecida; trade de orden desconocida → crítico; **camino caliente sin await**.
- **Autorización** (`test_mm_authorization.py`): DENY por halted / safe mode / degraded / datos inválidos / kill switch / ejecución bloqueada / token expirado o por expirar; REDUCE_ONLY por inventario al límite y por tope de capital; ALLOW limpio; economía ALLOW/DENY con componentes; el engine escribe los veredictos.
- **Kill switch** (`test_mm_kill_switch.py`): severidades, sticky vs transitorio, liberación con nombre, el gate lo ve.
- **Reconciliación** (`test_mm_reconciliation.py`, `test_mm_live_service.py`): orden ajena abierta, orden nuestra desconocida localmente, orden local faltante, balances fuera de tolerancia, línea base de trades, arranque en estado seguro cuando hay discrepancia.
- **Frontera** (`test_live_boundary.py`): imports por AST; provider `is_live` sin token rechazado.
- **API** (`tests/integration/test_live_api.py`): 401 sin sesión, 403 viewer, 403 con live deshabilitado, 403 con frase incorrecta, `real_money=True` sin efecto, status/stop/kill/reconcile sin servicio, ciclo completo start→status→reconcile→kill→stop con un venue falso inyectado.

## 8b. Fuente de ejecución: el account stream primero, `myTrades` como respaldo (2026-10-02, segunda iteración)

**Antes.** `LiveMarketMakerExecution` conocía los fills sondeando `/myTrades` cada ~3 s: hasta
tres segundos de inventario sin contabilizar, y una lectura de peso 20 por sondeo.

**Ahora.** El *user data stream* de Binance (`tia/data/providers/binance_user_stream.py`,
en la capa de providers) es una suscripción firmada sobre la **WebSocket API** de la venue
(`wss://ws-api.binance.com:443/ws-api/v3`; Testnet `wss://ws-api.testnet.binance.vision/ws-api/v3`):
un socket, un request `userDataStream.subscribe.signature` cuyos parámetros firma
`BinanceSigner.sign_ws_params` (HMAC sobre `apiKey`, `recvWindow`, `timestamp` ordenados
alfabéticamente; sirve cualquier tipo de key, sin `session.logon`), y desde el `status: 200`
los eventos llegan envueltos como `{"subscriptionId": n, "event": {...}}`. El *listen key*
(`POST /api/v3/userDataStream`) que usaba la primera versión fue retirado por Binance el
2026-02-20 (anuncio 2026-01-21; deprecado desde 2025-04-07) y responde HTTP 410; ya no hay
keepalive: la suscripción vive lo que vive la conexión, que la venue cierra a las 24 h y ante
`serverShutdown`, y ambas cosas son una caída reportada seguida de reconexión. Traduce cada
`executionReport` al tipo neutral `ExecutionReport` (`tia/domain/orders.py`)
y cada `outboundAccountPosition` a `AccountBalance` (free/locked por activo). `tia/mm` no
importa el módulo: el stream entrega a tres callbacks del adaptador
(`absorb_execution_report`, `absorb_balances`, `absorb_stream_status`), cableados por la capa
API en `start_mm_live` (o por un `FakeUserStream` en tests).

**Qué hace el adaptador con un reporte** (`absorb_execution_report`, síncrono, en el task
del stream, nunca en el callback de market data):

1. Lo ignora y lo cuenta si llega antes de que la reconciliación inicial haya terminado
   (`accepting_reports`): en ese instante la reconciliación es la verdad.
2. Lo deduplica por `(orden, tipo, estado, cantidad acumulada, trade id, hora)`.
3. Lo correlaciona por `clientOrderId` (para un cancel, por el `C` original) o por `orderId`.
   Si no corresponde a ninguna orden local: histórico si es anterior a la línea base; si
   lleva nuestro prefijo, `venue_order_unknown_locally` (crítico); si no, `unknown_execution_report`
   (crítico por defecto).
4. Si es un trade (`x = TRADE`, `t ≥ 0`, `l > 0`): lo contabiliza **una sola vez** por trade id,
   compartido con el sondeo de `myTrades` (`_book_fill` es la única puerta para todo fill).
   La atribución sale de `m`: `maker`, `taker` o `unknown` si la venue no lo dice; nunca se adivina.
   Comisión y activo de comisión vienen del reporte (`n`, `N`).
5. Adopta el estado (`X`): NEW → `resting` (y cuenta el ack si el REST no respondió aún:
   `reports_before_rest_ack`), PARTIALLY_FILLED → `resting`, FILLED → `filled`,
   CANCELED/EXPIRED/EXPIRED_IN_MATCH → `cancelled`, REJECTED → `refused` con `r`. Idempotente:
   una orden terminal no se reabre; un ack se cuenta una vez venga del stream, del REST, de la
   sincronización de órdenes abiertas o de una resolución.
6. Una orden `UNKNOWN` que el stream describe queda resuelta (`stream_resolved`), y un cancel
   pedido mientras era desconocida sale entonces.

**Fills al ledger sin esperar al próximo evento.** El servicio instala `fill_sink`
(`engine._on_fill`): el fill se contabiliza en el instante en que la venue lo reporta
(ledger, markouts, journal). Sin sink, `on_event` los entrega en el siguiente tick.

**Fills embebidos en la respuesta de `POST /order`.** No se contabilizan nunca: la respuesta
no dice quién hizo el mercado (`_parse_embedded_fill` lo documenta). Sólo actualizan
`venue_executed_qty`, lo que fuerza una lectura inmediata de `myTrades`. La atribución
definitiva llega por el reporte o por `myTrades` (ambos con `isMaker`), y el trade id
garantiza que entre respuesta FULL, reporte y `myTrades` se contabilice una sola vez.

**`myTrades` sigue.** Con el stream arriba es verificación cruzada a la cadencia lenta
(`idle`, 30 s); con el stream caído o ausente es la única fuente y vuelve a la cadencia
rápida (3 s) mientras haya órdenes. `venue_executed_qty > filled` fuerza una lectura.

**Si el stream se cae** (`absorb_stream_status(False)`): no se inventa ningún estado. El
adaptador pide `myTrades` ya, y declara `user_stream_down`; el servicio lo convierte en un
kill **transitorio** con `cancel_open` (lo que descansa se cancela, nada nuevo se cotiza), que
sólo se limpia cuando el stream volvió **y** una reconciliación posterior leyó la cuenta.
Un reporte con estado desconocido no se adivina: `unknown_execution_report` (crítico).

**Balances.** `BinanceExecutionProvider.get_balances()` devuelve free y locked por activo;
`LiveLedger.seed()` recibe los cuatro números; `balances()` responde con los **free** que la
venue reportó por último (stream o reconciliación), nunca con un cálculo local: un bid nuevo
sólo puede financiarse con USDT libre, un ask nuevo con BTC libre. La reconciliación compara
totales (free + locked, porque lo bloqueado son nuestras propias órdenes descansando). La
reconciliación inicial deja constancia de `capital_cap_usd` y `max_inventory_btc` y anota
si un activo no alcanza para financiar un lado.

**Telemetría de latencia** (`stats()["latency"]` del adaptador y `status()["latency"]` del
servicio, todas `LatencyStats` con p50/p95/p99): `market_event_to_processed_ms` (R → decisión
aplicada, incluye features, fair value, autorización, validación y enqueue; sin red),
`callback_ms`, `decision_to_enqueue_ms`, `enqueue_to_submit_ms`, `rest_submit_rtt_ms`,
`submit_to_ack_ms` (REST aplicado), `submit_to_first_ack_ms` (primer ack, stream o REST),
`report_to_local_ms` (E del reporte → procesado; incluye el offset host-venue),
`fill_to_ledger_ms` (sólo con el sink instalado), `cancel_to_ack_ms`.

**Lo que esto no cambia.** El camino caliente sigue sin HTTP ni DB; submit y cancel siguen en
el worker; el timeout sigue siendo UNKNOWN sin reenvío; el paper MM no toca nada de esto
(mismo hash de journal, test explícito). **Nada de esto se ejecutó contra Binance Testnet**:
las formas de `executionReport`, `outboundAccountPosition` y la suscripción firmada están
escritas desde la documentación oficial (`web-socket-api.md`, `user-data-stream.md`, 2026-09).

## 9. Lo que sólo Binance Testnet puede confirmar

Forma y campos de `executionReport` (`c`/`C` en cancels, `t = -1` sin trade, `m`, `n`/`N`), de `outboundAccountPosition`, aceptación de `userDataStream.subscribe.signature` con una key HMAC en Testnet (`wss://ws-api.testnet.binance.vision/ws-api/v3`) y el `subscriptionId` devuelto; formato exacto de `exchangeInfo.filters` (`NOTIONAL` vs `MIN_NOTIONAL`), `orderTypes` con `LIMIT_MAKER`;
rechazo -2010 y su `msg`; que `timeInForce` efectivamente sea rechazado para `LIMIT_MAKER`;
`commissionAsset` en `myTrades` y si la cuenta paga en BNB; latencia real de submit/cancel y
cuántos ciclos de requote cuesta el cancel/replace estricto; comportamiento de `openOrders`
con órdenes de otras sesiones; `-2011` al cancelar una orden ya cerrada; que `myTrades` con
`limit` devuelva los más recientes; el límite de 36 caracteres y el charset de
`newClientOrderId`.

## 10. Validación en Binance Spot Testnet (2026-10-03, commit `1ebc584`)

Ejecutada por el operador desde el VPS con `scripts/validate_mm_testnet.py --symbol BTC-USD
--percent-away 2.0`, en un contenedor efímero sobre la imagen de producción con el checkout
montado sólo lectura, credenciales de Testnet pasadas por entorno sin persistirlas, sin
tocar el backend de producción. Resultado reportado por el operador; el JSON completo quedó
en el VPS en `/home/tia/tia-testnet/mm_testnet_20261003T215105Z.json` y su copia al repo
(`docs/evidence/`, ver el índice en `docs/evidence/README.md`) está pendiente.

**PASS.** REST Testnet y hora de la venue; firma HMAC de la WebSocket API y
`userDataStream.subscribe.signature` aceptado (`subscriptionId` 0); cuenta y balances free y
locked de USDT y BTC, parser igual al payload; `exchangeInfo` y filtros; un `LIMIT_MAKER`
colocado 2 % bajo el mejor bid, reconocido por REST y por `executionReport` NEW;
correlación `clientOrderId` ↔ `orderId`; cancelación por REST, `executionReport` CANCELED
con `C` igual al id original, confirmación REST por `orderId` con estado CANCELED; ledger
sin fill fantasma; deduplicación de reportes; corte del account stream con una orden
abierta → estado seguro señalado (`user_stream_down`), estado local no inventado,
reconciliación REST que ve la orden, reconexión con una suscripción nueva, cancelación de
la segunda orden; latencias por tramo con el offset de reloj declarado aparte; rails sólo
Testnet; ningún request a Mainnet; `is_live=False`, `activation=None`,
`TIA_MM__REAL_MONEY=false`; limpieza con cero órdenes abiertas.

**NOT TESTED, por diseño de la prueba.** Partial fill, `report + myTrades` con un solo
booking y `fill_to_ledger_ms`: la orden descansó lejos del mercado y no se produjo ningún
fill. El shape del `executionReport` TRADE (`t`, `m`, `n`, `N`, `l`, `L`), la contabilidad del
fill en el `LiveLedger`, el `outboundAccountPosition` posterior y la reconciliación de
balances tras un fill siguen UNIT TESTED con el venue falso y no observados en la venue.

**Dos defectos reales encontrados por correr, corregidos antes de este resultado.** El
listen key retirado por Binance (HTTP 410; commit `a2d050e`, §8b) y la consulta de
confirmación por el `clientOrderId` del cancel en vez del `orderId` (-2013; commit
`1ebc584`), que además destapó dos huecos de idempotencia en el adapter de ejecución.

### 10.1 La sonda de fill (`--fill-probe SEGUNDOS`, opcional, no ejecutada todavía)

Para cerrar lo NOT TESTED sin forzar nada: una fase opcional del harness descansa un bid
post-only del tamaño mínimo **en** el mejor bid (nunca en el ask, nunca MARKET, nunca
persigue el precio) y espera hasta N segundos a que el mercado de Testnet opere contra él.
Si llega un print: verifica los campos del `executionReport` TRADE, el booking único contra
`myTrades`, el `fill_to_ledger_ms`, el `outboundAccountPosition` posterior y una
reconciliación de balances REST contra lo que implican los fills contabilizados; después
deshace la posición con un ask post-only en el mejor ask bajo las mismas reglas, cancela lo
que no se llene y reporta el inventario residual de Testnet (activos sin valor). Si no llega
ningún print, los items quedan NOT TESTED y el bid se cancela. Es segura porque sólo existe
en Testnet, con los rails del script, en tamaño mínimo y con los dos tipos de orden que el
adapter conoce; aporta valor porque la contabilidad del P&L real depende exactamente de los
campos que ninguna corrida ha observado. Comando, desde el VPS, con el mismo `docker run`
de la validación anterior más `--fill-probe 300`.

**Segunda corrida, 2026-10-03 22:41 UTC, commit `9cac585`, con `--fill-probe 300`.** Mismo
resultado en todos los items anteriores, sin FAIL. La sonda descansó un bid post-only de
8e-05 BTC a 84792.00, el mejor bid de Testnet en ese instante, durante 300 s; ningún print
llegó a ese precio; el bid se canceló. `4.partial_fill`, `5.report_plus_myTrades_single_booking`,
`6b.fill_observed` y `7.fill_to_ledger_ms` quedaron NOT TESTED, que es el resultado correcto:
nada se forzó. Evidencia: `/home/tia/tia-testnet/mm_testnet_20261003T224159Z.json` en el VPS,
pendiente de copiar a `docs/evidence/`.

**Lo que las dos corridas prueban sobre el parser, con reportes reales.** El `executionReport`
CANCELED de Binance llega con `c` igual al id del cancel (`TyvZa3BffgIWPTmCc5oZgi` en la
evidencia) y `C` igual a nuestro `clientOrderId`; `t` es −1 y `m` no viene en NEW/CANCELED. El
parser los traduce a `orig_client_order_id` nuestro, `trade_id` None e `is_maker` None, y la
correlación cierra la orden correcta una sola vez. Los campos de TRADE (`t`, `m`, `l`, `L`, `n`,
`N`) siguen sin observarse.

### 10.2 Lo que esta validación no cubre

El camino completo del servicio (`LiveMarketMakerService.start_live` → reconciliación inicial
→ siembra del ledger → cotización del engine → fills → `stop`) y los endpoints
`/api/mm/live/*` contra la venue: siguen INTEGRATION TESTED con un venue falso. Mainnet: no
tocado, por regla.

### 10.3 La validación del servicio (`scripts/validate_mm_live_service_testnet.py`, no ejecutada todavía)

Arma exactamente lo que arma `POST /api/mm/live/start` en Testnet, sin la API, sin la base de
datos y sin la configuración de producción: `BinanceExecutionProvider` simulado y sin token,
`MarketDataService` sobre los streams de **Testnet** (`wss://stream.testnet.binance.vision/stream`,
snapshot de `testnet.binance.vision`), `LiveMarketMakerService` con el perfil de latencia
medido en el host, un tope de capital como el que impondría el token, el `BinanceUserDataStream`
firmado, y corre `start_live()` → N minutos → `stop()`. Rails: los tres hosts deben ser Testnet;
cualquier host de Mainnet es rechazo antes de conectar. Verifica: datos usables, reconciliación
inicial no crítica, ledger sembrado desde balances reales, stream suscripto vía el servicio,
engine procesando eventos, órdenes colocadas y reconocidas por el adapter real (o la razón exacta
por la que el engine no cotizó: gate, controller, autorización de riesgo o de economía, todas
registradas), cancel/replace sin UNKNOWN, fills contabilizados una vez si los hubo, reconciliación
periódica, kill switch no enganchado al final, `stop()` con cero órdenes abiertas localmente y
en la venue preguntada con un cliente nuevo. El libro de Testnet es fino y sus precios son
propios: que la economía niegue cotizaciones es un resultado, no un fallo. Requiere el perfil de
latencia del host: en el VPS vive en el volumen `tia-data`, montado sólo lectura en el contenedor
efímero.

Nota de diseño que esta validación hace visible: en la API, el servicio live usa el
`MarketDataService` de la Fase 2, que lee los streams públicos de **Mainnet**, con ejecución en
Testnet cuando `use_testnet=true`. Para Mainnet real los dos coinciden; para validar en Testnet
el script usa datos de Testnet para que cotización y ejecución miren el mismo libro.

### 10.4 Corrida del servicio en Testnet (2026-10-04, commit `8e058f7`, 3 minutos): S10 y su causa raíz

Resultado reportado por el operador: S0 a S7, S9, S11, S12, S12b y S13 PASS; S8 NOT TESTED (ningún
fill, no provocado); **S10 FAIL**. Cifras: 620 eventos de mercado, 285 decisiones, 196 heartbeats, 0
errores del engine; 33 órdenes colocadas, 33 reconocidas, 0 rechazadas, 0 UNKNOWN, 33 canceladas (19
por TTL); 13 reconciliaciones, 0 fallidas; 65 reportes y 65 actualizaciones de balance por el account
stream, 0 desconexiones; cero órdenes abiertas al final, local y en la venue con un cliente nuevo. El
kill switch terminó enganchado, sticky, `trigger=reconciliation`, `reason="venue_order_unknown_locally x2"`,
más un transitorio `user_stream_down: account stream dropped: closed`.

**Causa raíz, demostrada por reproducción (`tests/unit/mm/test_mm_live_service.py::test_a_quote_cancelled_while_the_reconciliation_was_reading_the_venue_is_the_snapshots_age_not_a_zombie`).**
`reconcile()` lee las órdenes abiertas de la venue en un instante T1 y después lee balances y
trades (dos requests más, 100 a 300 ms cada uno en Testnet). La comparación con el estado local
ocurre en T2 > T1. Entre T1 y T2 el maker siguió cotizando: TTL de 1 s, requote cada 500 ms, 33
cancelaciones en 3 minutos. Dos cotizaciones que la foto de T1 listaba abiertas fueron canceladas
y confirmadas por la venue antes de T2. `compare_orders` recibía solo las órdenes locales abiertas
y las desconocidas, no las que el run conocía y había cerrado, así que clasificó esas dos como
"órdenes de este maker que el run no administra" — crítico — y el servicio enganchó el kill
sticky. No hubo ninguna ventana en la que el sistema no supiera dónde estaba una orden: ambas
estaban cerradas localmente con la confirmación CANCELED de la venue. Fue un **falso positivo del
clasificador de la reconciliación** (categoría A, bug de producción), y el kill switch respondió
correctamente a lo que se le dijo (categoría C para el switch). El transitorio `user_stream_down`
era el propio `stop()` cerrando el stream que él mismo abrió, leído como caída (categoría A,
cosmético pero engañoso). Y S10 tal como estaba escrito habría fallado también en una corrida
limpia: `stop()` engancha el switch sticky por diseño (categoría B, bug del validador).

**Corrección.** `compare_orders` recibe además las órdenes cerradas que el run conoce y el
instante de la foto. Una orden cerrada aquí y abierta en la foto es `local_closed_venue_open`,
aviso, con un contador de apariciones consecutivas; a la segunda reconciliación consecutiva es
crítica (una orden que la venue sostiene y nadie administra). Una orden reconocida después de la
foto no puede estar en ella y no se reporta como faltante. El adapter, al ver una orden cerrada
listada abierta, distingue: si la venue misma la cerró (reporte o respuesta CANCELED o FILLED) la
foto es vieja y no pregunta nada; si el cierre fue solo nuestro (una submission resuelta como
"nunca llegó", un cancel antes del submit) pregunta por `orderId`, y si la venue la sostiene
abierta la reabre localmente, la cancela de nuevo y eleva el crítico `closed_order_open_at_venue`.
`stop()` ya no trata el cierre de su propio stream como caída. El validador juzga el kill switch
en dos lecturas: antes de `stop()` ningún enganche sticky (S10), y después de `stop()` el stop es
la única causa sticky y no queda ningún transitorio (S10b).

Esta corrida no está en `docs/evidence/`: el JSON quedó en el VPS. Debe copiarse como las dos
anteriores.

### 10.5 Segunda corrida del servicio (2026-10-04, commit `8608db6`, 180 s): S10b y la decisión de modelo

Resultado reportado por el operador: todos los items PASS salvo S8 NOT TESTED (ningún fill, no
provocado) y **S10b FAIL**. Cifras: 765 eventos, 272 decisiones, 153 heartbeats, 0 errores del
engine; 62 colocadas, 62 reconocidas, 0 rechazadas, 0 UNKNOWN, 62 canceladas (19 por TTL); 13
reconciliaciones, 0 fallidas, la última `ok`; 123 reportes y 123 balances por el stream, 0
desconexiones; 0 abiertas al final, local y en la venue. Varios bloqueos transitorios por datos
stale (`venue data 1.6s old`, `last event 4151 ms ago`, `last event 5106 ms ago`) que **no**
quedaron sticky y volvieron a `kill=False gate=safe` al recuperarse los datos. El estado final
del switch: `engaged=true, sticky=true, trigger=stop`, más un transitorio
`data: market data not usable: venue data 1.1s old...`.

**Diagnóstico: B más C.** El shutdown fue correcto (categoría C): canceló, esperó, reconcilió,
cero abiertas. Pero el modelo de estado era ambiguo (categoría B) en dos puntos. Primero,
`stop()` se registraba como un kill **sticky** con trigger `stop`, indistinguible en los campos
del switch de un hallazgo crítico salvo por el nombre del trigger; `state_label` ya decía
"stopped", el puente de incidentes tenía que excluir `stop` a mano, y todo consumidor de
`as_dict()` (API, frontend, validador, operador) veía `engaged=true`. Segundo, los transitorios
son lecturas vivas que solo mantiene `_watch`, ejecutado en cada evento de mercado y en cada
heartbeat; `stop()` cancela el heartbeat y desuscribe el feed, así que un `data` enganchado en
el último heartbeat antes del stop no tenía quién lo limpiara y sobrevivía como fantasma. No
fue un bug del kill switch (sus mecánicas hicieron lo especificado) ni del validador en sentido
estricto: el validador detectó un estado final genuinamente ambiguo.

**Decisión de semántica.** Un shutdown deliberado es un estado propio, no un kill de
seguridad: `MMKillSwitch.shutdown(reason, actor)` cancela lo que descansa, cierra la cotización
por el mismo gate (el engine no coloca nada mientras el servicio drena), limpia los transitorios
registrando cada limpieza en el historial, y deja intacto y visible cualquier sticky previo con
su primera causa. `engaged` pasa a significar exclusivamente "hay un enganche de seguridad".
Justificación: la arquitectura ya trataba el stop como algo distinto en tres lugares
(`state_label`, el puente de incidentes, la regla de primera causa); el modelo solo lo hace
explícito. El validador lee ahora: S10, ningún sticky antes del stop; S10b, shutdown registrado,
sin sticky, sin transitorios, `engaged=false`. Tests en `tests/unit/mm/test_mm_kill_switch.py`,
`tests/unit/mm/test_mm_live_service.py` y `tests/unit/test_mm_service_validator_semantics.py`.

**Sobre `unknown_order_resolved_present` en esta corrida.** Ese log lo emite el adapter en
`resolve_unknown_order`, que sirve a toda consulta "preguntale a la venue por esta orden": una
submission con timeout, una orden que la foto de `openOrders` no listó, un cancel rechazado. El
texto afirmaba "the timed-out submission DID reach the venue" sin saberlo. Con `unknown = 0` en
los contadores, la resolución **no** vino de un timeout de submit (ese camino incrementa
`unknown` antes de resolver); vino de la edad de la foto del sync de órdenes abiertas, que
reportaba como "missing at venue" una orden reconocida después de la foto. El sync del adapter
recibe ahora el instante de la foto y no pregunta por órdenes reconocidas después; el log dice
lo que sabe. La propiedad SUBMIT UNKNOWN → RESOLVE → FOUND → ADOPT, nunca RETRY, está cubierta
por `test_a_timeout_after_the_venue_accepted_is_adopted_not_duplicated` y por el escenario
adversarial de la vida completa de una submission con timeout. El JSON de esta corrida,
`mm_service_testnet_20261003T235710Z.json`, quedó en el VPS; debe copiarse a `docs/evidence/`
sin editar su FAIL.

**Latencias.** El perfil usado es el medido en el host (`39096a455e3a46c1`, commit `710d0ac`);
el servicio lo carga desde el volumen y el autorizador de economía lo usa para el riesgo de
latencia de la orden. Tramos medidos en `status().latency`: decisión → enqueue, enqueue →
submit, RTT del submit, submit → ack REST, submit → primer ack de cualquier fuente, `E` del
reporte → recepción (incluye el offset de reloj), recepción del reporte → aplicado (nuevo),
fill → ledger, cancel → ack, evento de mercado → procesado, duración del callback. Falta y
queda documentado: un reloj de la venue para `bookTicker` (Spot no lo trae) y el offset de reloj
host-venue dentro del servicio (el harness por bloques lo mide; el servicio no lo corrige).

### 10.6 Matriz de cobertura sintética (objetivos 3, 4, 6 y 7 de la revisión del 2026-10-04)

Todo lo de esta tabla es **UNIT/ADVERSARIAL TESTED** contra `FakeVenue` y `FakeUserStream`:
evidencia sobre nuestros invariantes bajo órdenes hostiles, no sobre Binance. Archivos:
`E` = `tests/unit/mm/test_mm_execution_live.py`, `S` = `tests/unit/mm/test_mm_live_service.py`,
`K` = `tests/unit/mm/test_mm_kill_switch.py`, `R` = `tests/unit/mm/test_mm_reconciliation.py`,
`AF` = `tests/adversarial/test_mm_fill_paths_synthetic.py`,
`AS` = `tests/adversarial/test_mm_service_safety_synthetic.py`,
`AI` = `tests/adversarial/test_mm_order_identity_synthetic.py` (nuevo),
`U` = `tests/unit/test_binance_user_stream.py`, `V` = `tests/unit/test_mm_service_validator_semantics.py`.

| Escenario | Test |
|---|---|
| Datos stale con órdenes abiertas: nada nuevo, lo que descansa se cancela, ningún estado inventado | S `a_silent_feed_is_seen_by_the_heartbeat...`, S `repeated_stale_and_recovery_cycles...` |
| Recuperación de datos: vuelve a safe, sin sticky | S `a_silent_feed...`, S `repeated_stale...`, K `a_transient_condition_clears_itself...` |
| Stale/recuperación repetidos: sin residuo, sin kills falsos acumulados | S `repeated_stale_and_recovery_cycles_leave_no_residue...` (3 ciclos, 3 engage, 3 clear, no sticky, no shutdown) |
| Kill realmente crítico queda sticky | S `a_breached_limit...`, S `an_unknown_fill...`, S `a_reconciliation_that_fails_mid_run...`, AS `a_sticky_kill_from_a_critical_finding_survives_to_stop...` |
| Shutdown deliberado ≠ safety kill | K `a_shutdown_is_its_own_state...`, S `a_stale_data_condition_engaged_just_before_stop...`, V (5 casos: limpio, transitorio durante la corrida, sticky, transitorio fantasma, stop como sticky) |
| Shutdown con órdenes abiertas: cancela, espera, reconcilia, 0 abiertas | S `the_service_reconciles_first_quotes_post_only...stops_clean`, S `a_partial_fill_the_stream_never_reported_is_booked_by_the_final_reconciliation_at_stop`, AS `a_sticky_kill...nothing_open` |
| Shutdown sin órdenes abiertas | S `a_stop_with_nothing_open_is_a_clean_shutdown_too` |
| Reconciliación 1: local + venue presente | R `orders_are_classified_by_who_placed_them...`, S `the_service_reconciles_first...` |
| Reconciliación 2: local + venue ausente | E `an_order_that_vanishes_at_the_venue_is_asked_about_not_assumed`, R `the_snapshots_age_is_told_apart_from_a_real_discrepancy` |
| Reconciliación 3: desaparición temporal (edad de la foto) | AS `a_just_acknowledged_order_absent_from_an_older_open_orders_picture_is_not_asked_about`, AS `an_order_acknowledged_after_the_venue_snapshot_is_not_reported_missing` |
| Reconciliación 4: desaparición confirmada | E `an_order_that_vanishes_at_the_venue...` (resuelta al estado real), E `a_cancel_the_venue_rejects_as_already_closed_resolves_the_true_state` |
| Reconciliación 5: orden cancelándose | S `a_quote_cancelled_while_the_reconciliation_was_reading_the_venue_is_the_snapshots_age_not_a_zombie`, E `cancel_and_cancel_all_wait_for_the_venue...` |
| Reconciliación 6: respuesta REST del cancel antes del `executionReport` | AI `a_canceled_report_that_arrives_after_the_rest_cancel_answered_changes_nothing_and_asks_nothing` (nuevo) |
| Reconciliación 7: `executionReport` antes de la respuesta del cancel | E `canceled_expired_and_rejected_reports_close_the_order_as_the_venue_says`, E `a_rest_cancel_rejected_after_the_stream_reported_canceled_changes_nothing_and_asks_nothing` |
| Reconciliación 8: `executionReport` duplicado | E `a_duplicate_report_and_a_duplicate_trade_book_nothing_twice`, AF `a_trade_the_history_booked_first_is_not_booked_again...` |
| Reconciliación 9: report demorado | AF `a_fill_during_a_stream_outage...late_report_after_reconnect_is_a_duplicate`, E `a_fill_reported_after_the_rest_ack_books_normally...` |
| Reconciliación 10: después de un cancel | S `an_order_the_venue_keeps_listing_open_after_we_closed_it_is_critical_on_the_second_sighting`, E `an_order_we_closed_that_the_venue_still_holds_open_is_reopened_cancelled_again_and_critical` |
| Reconciliación 11: durante cancel/replace | AS `an_order_acknowledged_after_the_venue_snapshot_is_not_reported_missing` |
| Reconciliación 12: UNKNOWN → resuelto | E `a_timeout_is_unknown_blocks_new_orders_and_is_resolved_by_asking_never_by_resending`, E `a_timeout_after_the_venue_accepted_is_adopted_not_duplicated`, AS `an_unknown_order_the_venue_confirms_never_arrived...`, AS `the_whole_life_of_a_submission_whose_answer_timed_out_after_the_venue_accepted_it` |
| Reconciliación 13: orden en la venue con identidad local distinta | E `a_market_maker_order_the_venue_holds_but_this_run_does_not_know_is_critical`, E `a_report_about_an_order_this_run_does_not_know_is_critical...`, AI `the_venue_id_fallback_never_adopts_an_order_whose_ids_match_nothing_we_hold` (nuevo) |
| Reconciliación 14: `orderId`/`clientOrderId` no coinciden | AI `a_report_named_only_by_our_venue_order_id_is_correlated_by_it_and_applied` (nuevo), U `a_cancel_report_refers_to_the_original_order_id`, `tests/unit/test_binance_live.py` (cancel re-keyed, -2013 por `origClientOrderId`) |
| Reconciliación 15: -2013 sobre orden conocida | E `a_cancel_the_venue_rejects_as_already_closed_resolves_the_true_state`, E `a_rest_cancel_rejected_after_the_stream_reported_canceled...`, `tests/unit/test_binance_live.py` (-2013 tras ack es contradicción, no confirmación) |
| Stream: disconnect / reconnect | U `a_dropped_socket_is_reported_as_a_drop_and_a_fresh_signature_is_sent_on_reconnect`, U `a_subscription_the_venue_terminates_is_a_drop_followed_by_a_new_subscription`, E `a_dropped_account_stream_invents_no_state_asks_for_the_trade_history_and_is_critical` |
| Stream: reconnect con órdenes abiertas y reconciliación antes de volver a operar | S `a_dropped_account_stream_degrades_to_a_safe_state_until_a_reconciliation_after_it_is_back`, AF `a_fill_during_a_stream_outage_is_booked_from_the_history...` |
| Stream: report después / antes del cancel | AF `a_replayed_new_report_never_reopens_a_cancelled_order`, AI (6), E (7) |
| Stream: fill report, balance update | E `partial_and_full_fills_arrive_as_reports_book_once_each...`, E `balances_from_the_stream_are_recorded_and_handed_to_the_sink`, S `fills_reported_by_the_stream_are_booked_at_once_and_balances_follow_the_venue` |
| Fills: parcial, total, duplicado, fill + cancel race, TRADE report, `myTrades`, report demorado, `fill_to_ledger_ms`, reconciliación tras fill | E `partial_and_full_fills...`, E `a_duplicate_report_and_a_duplicate_trade...`, E `a_fill_that_races_the_cancel_is_booked_and_the_order_ends_filled`, E `fills_come_only_from_the_venue_trade_history...`, AF (5 escenarios), E `the_fill_sink_books_the_moment_the_venue_reports...`, AS `a_fill_the_venue_reports_reconciles_clean_and_the_ledger_agrees_with_the_account` |

Lo que esta matriz **no** prueba: un fill real en Testnet (S8 sigue NOT TESTED; un LIMIT_MAKER no
cruza por definición y provocar el cruce con una orden agresiva está prohibido por las reglas
de esta validación), y el comportamiento del servidor de Binance ante cualquiera de estos
órdenes de llegada.

### 10.7 El perfil de latencia para Testnet (2026-10-04, sobre `7b748d2`)

**Lo que pasó.** La corrida del servicio sobre `7b748d2` terminó en S0 NOT TESTED: "latency
profile not found at /app/data/runtime/mm/latency_profile.json". No es un bug: el perfil
`39096a455e3a46c1` (commit `710d0ac`, medido 2026-09-18) vive en el volumen Docker de
producción `trader-ia_tia-data`, que las dos corridas anteriores montaban en `/app/data/runtime`
y esta no. `find /home/tia` no lo encuentra porque los volúmenes Docker no están bajo `/home`.

**Por qué no se reutiliza para Testnet.** Ese perfil fue medido en este host, pero contra los
streams públicos de Mainnet: hasta hoy `scripts/mm_market_data_check.py` no sabía medir contra
otra venue (`BinancePublicProvider()` y `DEFAULT_STREAM_URL` apuntan a `api.binance.com` y
`stream.binance.com`). Es el perfil correcto para el paper, que lee Mainnet; para validar el
servicio contra Testnet, el entorno es otro (otros hosts, otra latencia). Las corridas §10.4 y
§10.5 pasaron S0 con ese perfil; el item decía "measured on this host", y era cierto, pero no
decía contra qué venue. Desde este commit el detalle de S0 incluye el `source` del perfil.

**Cambio mínimo.** `mm_market_data_check.py` acepta `--rest-url` y `--stream-url` (por defecto,
Mainnet público: el paper no cambia), rechaza mezclar venues (snapshots de una y diffs de otra
no sincronizan nunca), y graba en `source` los hosts contra los que midió. Solo datos públicos:
no lee credenciales, no envía nada. Test: `tests/unit/test_mm_market_data_check_cli.py`.

**Dónde vive el perfil Testnet.** Nunca en el volumen de producción (el paper lo usa). En un
directorio propio del host, `/home/tia/tia-testnet/runtime/mm/latency_profile.json`, montado en
`/app/data/runtime` solo lectura durante la validación. `scripts/run_mm_service_testnet_validation.sh`
hace la secuencia completa con verificación entre pasos: repo en fast-forward, imagen con el
commit, presencia de claves sin imprimirlas, medición de 5 min contra Testnet, carga del perfil
con el mismo código del validator dentro del contenedor (debe nombrar Testnet y tener muestras
en los tres componentes), corrida de 3 min, evidencia escaneada y copiada sin modificar.

**Evidencia histórica.** Las corridas §10.4 y §10.5 montaron `$HOME/tia-testnet` desde una
shell root: sus JSON están en `/root/tia-testnet/`, no en `/home/tia/tia-testnet/`. El runbook
los copia a `docs/evidence/` si los encuentra, sin editarlos.

## 11. Modelo de estados de seguridad del maker live

El kill switch del maker (`tia/mm/kill_switch.py`) alimenta el `system_unsafe` del gate global;
el engine no cotiza mientras el switch esté enganchado y, con severidad `cancel_open`, cancela lo
que descansa en el momento del enganche. Hay tres clases de condición, y la clase la decide quién
puede saber que la condición terminó.

| Clase | Trigger | Entrada | Severidad | Recuperación | Quién la decide |
|---|---|---|---|---|---|
| **Transitoria** | `data` | market data no usable (stale, desconectado, libro inválido) | cancel_open | se limpia sola cuando los datos vuelven a ser usables | el sistema, leyendo el feed |
| **Transitoria** | `unknown_order_state` | una orden en UNKNOWN (timeout en submit o cancel) | no_new_quotes | se limpia sola cuando ninguna orden queda UNKNOWN: la resolución por consulta (`orderId` si se conoce, si no `origClientOrderId`) la cierra como presente o como nunca llegada; -2013 sobre una orden reconocida no es "ausente", es UNKNOWN | el sistema, preguntando a la venue |
| **Transitoria** | `user_stream_down` | el account stream cayó con órdenes abiertas o sin ellas | cancel_open | se limpia sola cuando el stream volvió **y** una reconciliación posterior leyó la cuenta | el sistema, tras reconciliar |
| **Sticky** | `reconciliation` | hallazgo crítico: orden ajena, orden del maker que el run no conoce, orden cerrada aquí que la venue sostiene abierta dos veces seguidas, desajuste de balances adoptado, reconciliación fallida | cancel_open / no_new_quotes | **stop y start por un operador** | una persona |
| **Sticky** | `unknown_fill`, `unknown_execution_report`, `foreign_open_order`, `venue_order_unknown_locally`, `closed_order_open_at_venue`, `outcome_apply_failed` | la cuenta no es lo que creíamos | cancel_open | stop y start por un operador | una persona |
| **Sticky** | `unresolved_order`, `excessive_api_errors`, `activation` | la venue no contesta o rechaza la autorización | no_new_quotes | stop y start por un operador | una persona |
| **Sticky** | `risk_limit` | el controller del maker disparó (pérdida diaria, drawdown) | cancel_open | stop y start por un operador | una persona |
| **Sticky** | `operator` | parada de emergencia explícita de un operador (`POST /api/mm/live/kill-switch`) | cancel_open | stop y start por un operador | una persona |
| **Shutdown** | `stop()` | parada deliberada: `POST /api/mm/live/stop`, el cierre del proceso, el fin de una validación | cancela lo que descansa y cierra la cotización por el mismo gate | no es un enganche de seguridad: `engaged` queda en lo que digan las condiciones de seguridad; los transitorios se limpian y quedan en el historial como "limpiado por el shutdown"; un sticky previo sigue visible con su primera causa | start por un operador |

Reglas que el modelo garantiza y que los tests sintéticos atacan:

1. Una condición transitoria la limpia únicamente la evidencia que la contradice: datos usables,
   cero órdenes UNKNOWN, stream arriba más reconciliación. Nunca el paso del tiempo.
2. Un estado UNKNOWN jamás se interpreta como seguro: bloquea nuevas órdenes hasta que la venue
   responda; una orden UNKNOWN nunca se reenvía; su cancel se recuerda y sale cuando la venue dice
   que descansa.
3. Un enganche sticky conserva su **primera causa**; las siguientes quedan en el historial y
   solo pueden subir la severidad. `stop()` **no** es un enganche: es un estado de shutdown
   propio (`kill_switch.shutdown`), que bloquea la cotización por el gate mientras el servicio
   drena y se reporta como shutdown. En una corrida limpia el estado final es
   `engaged=false`, `sticky=false`, `transient={}`, `shutdown={reason, actor, at_ms}`.
   Un transitorio engancha solo mientras alguien pueda observar la condición; un servicio
   parado no puede, así que el shutdown limpia los transitorios y lo registra.
4. Una reconciliación limpia posterior **no** libera un sticky: el hallazgo crítico fue una
   afirmación sobre la cuenta ("alguien más opera", "una orden nuestra que nadie administra") que
   una persona debe mirar aunque haya desaparecido. Lo que sí se exige del clasificador es que
   no produzca hallazgos críticos a partir de la edad de la foto; de ahí §10.4.
5. Un enganche sticky se persiste como incidente y llega al webhook de alertas; un stop del
   operador no.

Lo que una persona debe hacer ante un sticky: leer `GET /api/mm/live/status` (`kill_switch`,
`reconciliation.last`, `open_orders`, `unknown_orders`), confirmar en la venue, y recién después
`POST /api/mm/live/stop` y, si corresponde, `start`. No existe ningún endpoint que libere el
switch sin parar el servicio.

