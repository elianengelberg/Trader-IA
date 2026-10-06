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

### 10.8 Auditoría del camino de fills (2026-10-04, código en `7e44954`+)

Las doce preguntas, respondidas sobre el código, sin cambiarlo. Archivos: `Q` =
`tia/mm/quoting.py`, `X` = `tia/mm/execution.py`, `L` = `tia/mm/live_ledger.py`,
`S` = `tia/mm/live_service.py`, `U` = `tia/data/providers/binance_user_stream.py`.

1. **Cotizaciones.** `Q.decide()`: centro = fair value corregido por inventario (bps); bid =
   redondeo hacia abajo de centro·(1 − half/1e4) al tick, ask = redondeo hacia arriba de
   centro·(1 + half/1e4); si bid ≥ ask, ask = bid + tick; se rechaza la decisión si bid o ask
   se alejan del mid más de `max_offset_from_mid_bps`; antes, el controlador de riesgo y la
   confianza mínima del fair value pueden devolver `no_quote`. Tamaño `base_quote_size_btc`,
   TTL `quote_ttl_ms`.
2. **Precio del LIMIT_MAKER.** El de la decisión, tal cual. `X.validate_maker_order` rechaza en
   vez de re-redondear: fuera de grilla, bajo `minQty`/`minNotional`, o un precio que tomaría
   liquidez contra el libro local (bid ≥ best ask, ask ≤ best bid). La venue es el segundo
   rail: LIMIT_MAKER rechaza con -2010 lo que tomaría (`rejected_would_cross`, nunca reenviado).
3. **Maker.** Localmente, la validación anterior. En la venue, el tipo de orden. En el fill, la
   bandera `m` del `executionReport` (`is_maker`): `maker_fills`/`taker_fills`; un fill taker
   sobre una orden nuestra se contabiliza y se registra como anomalía (`mm_live_taker_fill`).
4. **Cancel/replace.** `X.cancel`/`cancel_all` encolan el cancel; con `strict_cancel_replace`
   la pata nueva se difiere mientras la vieja tiene un cancel pendiente
   (`deferred_cancel_pending`). `_do_cancel` solo sale cuando la venue reconoció la orden
   (`_worker_acked`); resultados: `cancelled`, `cancel_rejected` (-2011/-2013 → resolver por
   id), `unknown` → resolver. El vencimiento del TTL cancela por la venue.
5. **Llegada del `executionReport`.** `U.BinanceUserDataStream` (WebSocket API,
   `userDataStream.subscribe.signature`) parsea `ExecutionReport` y llama a
   `X.absorb_execution_report(report, received_at_ms)` en la tarea del stream, nunca en el hot
   path de market data. Tramos medidos: `report_to_local_ms`, `report_received_to_applied_ms`.
6. **Correlación.** `report.order_ref` (`C` origClientOrderId si viene, si no `c`) → `_all`;
   luego `client_order_id`; luego `_by_venue_id[orderId]`. Desconocida con nuestro prefijo:
   `venue_order_unknown_locally`, crítica. Sin prefijo: `unknown_execution_report`. Anterior a
   la línea base de trades: histórica. Antes de la reconciliación inicial: `reports_before_start`.
7. **Fill parcial.** Un TRADE con `t`, `l`, `L` → `_fill_from_report` → `_book_fill` agrega el
   fill; la orden sigue abierta mientras `remaining > step/2`; `_adopt` registra `z` como
   `venue_executed_qty` y, si supera lo contabilizado, fuerza un poll de `myTrades` (`_poll_due`).
8. **Fill total.** `_book_fill` cierra la orden cuando `remaining ≤ step/2` (estado `filled`); o
   `_adopt` con estado FILLED de la venue. Una orden terminal no se reabre (idempotencia).
9. **Ledger.** `fill_sink` → `L.apply_fill(fill)` en el acto: comisión según su estado (`venue`
   en quote, `converted_from_base`, si no asumida y contada en `fills_unconverted`), inventario y
   caja vía `_book`; `fill_to_ledger_ms` medido en `_book_fill`.
10. **Reconciliación posterior.** `S.reconcile()`: órdenes abiertas (con instante de la foto),
    balances y `myTrades`; `_apply_trades` deduplica por trade id y descarta lo anterior a la
    línea base; `L.expected_balances()` contra totales de la venue con tolerancias; un desvío
    aislado es warning, dos seguidos (o el pase final) adoptan las cifras de la venue.
11. **Fill + cancel race.** Respuesta al cancel con FILLED → `cancel_raced_fill`; el fill llega
    por TRADE o por `myTrades`; `z` por delante de lo contabilizado fuerza el poll. Test:
    `test_a_fill_that_races_the_cancel_is_booked_and_the_order_ends_filled`.
12. **Sin doble contabilización.** `_seen_trade_ids` por trade id de la venue a través de
    todas las fuentes, `_seen_report_keys` para reportes duplicados (`dedupe_key`), contadores
    `duplicate_trades`/`duplicate_reports`; `_book_fill` es la única puerta.

### 10.9 Diseño de la prueba de fill real en Testnet (sin agresión)

Un LIMIT_MAKER no cruza por definición; un fill real solo puede venir de que el mercado opere
contra una orden nuestra que descansa. El mecanismo legítimo es el de cualquier maker: estar
AL mejor nivel y esperar. `scripts/validate_mm_testnet.py --fill-probe SEGUNDOS` ya lo hacía
con un bid; desde `7e44954`+:

* `--fill-probe-sides both`: un bid al best bid y un ask al best ask a la vez, post-only, tamaño
  mínimo sobre `minNotional`; el que el mercado alcance primero es el fill, el otro se cancela.
* `--fill-probe-repeg S`: si el best se alejó de una sonda (subió sobre nuestro bid, bajó bajo
  nuestro ask), se cancela (confirmado) y se vuelve a descansar al nuevo best, del lado maker,
  nunca cruzando. Un best que atravesó nuestro precio no es re-peg: es un fill (o está por
  serlo). Helper puro `_repeg_target`, testeado.
* Si hay fill: campos del TRADE, correlación `c/C` ↔ `i`, booking único contra `myTrades`,
  `outboundAccountPosition`, reconciliación de balances, desarme a plano con una sola orden
  post-only del otro lado por el neto (`_net_inventory`). Fill parcial solo si la venue lo
  produce; duplicado y demorado no se pueden forzar en la venue real: siguen SYNTHETIC ONLY.
* Evidencia etiquetada `fill_evidence_kind: real_testnet_fill`; en el validator del servicio,
  S8 dice `real_testnet_fill` si hubo fill y "SYNTHETIC ONLY" si no.

Rails intactos: mismo `validate_maker_order`, mismo adapter, sin MARKET, sin token, Testnet
only. Comando desde el VPS: `FILL_PROBE=1800 bash scripts/run_mm_service_testnet_validation.sh`
(30 min de ventana). Si el mercado no viene, S8 queda NOT TESTED y se dice.

### 10.10 Restart y recuperación: el hueco encontrado y el barrido al arranque

**Auditoría.** Hasta `7e44954`, un servicio que moría con cotizaciones descansando (crash,
`kill -9`, host caído) dejaba esas órdenes en la venue. El siguiente `start_live()` las veía en
la reconciliación inicial como `venue_order_unknown_locally` (prefijo nuestro, desconocidas
para esta corrida) → kill sticky `CANCEL_OPEN` → `execution.cancel_all`, que solo cancela
órdenes **locales**: las huérfanas quedaban descansando en la venue, sin nadie que las
gestionara, hasta que una persona las cancelara a mano. Una huérfana que se llena mientras
tanto es un fill sobre una orden que nadie contabiliza. Riesgo real de recuperación, no
especulativo; afecta Testnet hoy y afectaría cualquier venue.

**Decisión (implementada en `S._sweep_orphans`, llamada desde `start_live` antes de la
reconciliación inicial).** Antes de que esta corrida coloque nada, se leen las órdenes abiertas
de la venue; las que llevan el prefijo del maker son de una corrida anterior y no las gestiona
nadie: cada una se consulta por id (`resolve_unknown_order`, para que el provider la conozca)
y se cancela por la venue (`cancel_order`); el barrido se escribe en el journal
(`kind: orphan_sweep`) y se eleva como incidente `mm_orphans_swept` (una corrida murió con
órdenes abiertas: el operador debe saberlo). Nada se adopta, nada se reenvía. Una huérfana que
la venue no cancela queda para la reconciliación inicial, que la encuentra abierta y
desconocida y engancha el kill sticky como antes. Las órdenes ajenas no se tocan (siguen
críticas). Durante la corrida el barrido no aplica: una orden con nuestro prefijo que la venue
lista y esta corrida no conoce podría ser una submission duplicada, y sigue siendo crítica.
Estado visible en `status()["orphan_sweep"]`.

**Tests (UNIT/ADVERSARIAL).** `test_orders_of_a_previous_run_found_open_at_start_are_cancelled_before_quoting_and_reported`,
`test_an_orphan_the_venue_will_not_cancel_is_left_to_the_initial_reconciliation_which_is_critical`,
`test_a_foreign_open_order_at_start_is_not_swept_and_stays_critical` (servicio) y
`test_a_restart_after_a_run_died_with_orders_open_leaves_no_orphan_and_duplicates_nothing`
(adversarial: dos servicios sobre la misma venue falsa, el primero muere sin `stop()`).

**Simulacro en Testnet (`--recovery-drill`, NOT TESTED todavía).** Tras la ventana, el servicio
muere con cotizaciones descansando (suscripción de mercado cortada, loops cancelados, stream y
worker cortados, sin `stop()`); un segundo servicio arranca con cliente nuevo sobre la misma
cuenta. Items R1 (la venue aún las tiene), R2 (el barrido las encontró y canceló todas), R3
(reconciliación inicial limpia), R4 (ninguna de la corrida muerta abierta), R5 (stream
suscripto), R6 (la segunda corrida cotiza solo con sus ids), R7 (ningún id de la corrida muerta
adoptado ni reenviado). Después, `stop()` y la verificación con cliente nuevo de siempre.
Comando: `RECOVERY_DRILL=1 bash scripts/run_mm_service_testnet_validation.sh`. Nunca deja
órdenes sin reconciliar: la segunda corrida siempre arranca y el cierre cancela todo lo nuestro.

### 10.11 Clasificación de lo demostrado (estado al cierre de este ciclo; §10.15 es la última corrida)

| Clase | Qué |
|---|---|
| **VERIFIED TESTNET** (corridas sobre `1ebc584`…`e5b5625`; §10.15 agrega, bajo overrides EXPERIMENTALES y sólo bajo ellos: S8 a nivel servicio con 24 fills reales de quotes del engine, maker, por el account stream, correlacionados 24/24, asentados una vez, reconciliados con delta cero; un fill parcial real (PARTIALLY_FILLED → FILLED en dos trades); 17 rechazos would-cross del rail post-only; dos corridas de 30 minutos con 116 reconciliaciones limpias cada una y 0 stalls del event loop; §10.13 agrega la recuperación tras una muerte con una orden descansando: barrido por id antes de cotizar, reconciliación limpia, sin adopción ni reenvío; §10.12 agrega: perfil de latencia medido contra Testnet; S10b con el estado `shutdown`; el camino de fills a nivel adapter + stream + ledger con un fill real entero del harness por bloques) | REST y suscripción firmada del stream de cuenta; LIMIT_MAKER post-only; reportes NEW/PARTIALLY_FILLED/FILLED/CANCELED/REJECTED reales y su correlación (incluido el `c`/`C` re-keyed del cancel); cancel por `orderId`; -2010, -2011, -2013; corte y reconexión del stream con orden abierta y reconciliación REST; ensamblado del servicio como el API; reconciliación inicial y ledger sembrado; cotización del engine sobre datos Testnet; cancel/replace a escala (1301/1309 en 30 min); kill transitorio por datos stale y recuperación (239 veces en una corrida); `stop()` con 0 abiertas local y en la venue; rails Testnet-only. |
| **VERIFIED LOCALLY** | Todo el §10.6; estado `shutdown`; barrido de huérfanas; semántica del validator; flags de venue del medidor de latencia; aritmética del fill probe; overrides experimentales del harness (defaults idénticos sin flags; rangos; escenarios de producción rechazados); clasificación de razones de cancel. |
| **SYNTHETIC ONLY** | Reporte duplicado emitido por la venue, reporte demorado; una huérfana que la venue rechaza cancelar; un fill sobre una huérfana antes del barrido; órdenes zombi; semántica de caída/reconexión del stream a nivel servicio. |
| **NOT TESTED** | S8 con los **defaults de producción** (el control de 30 min no produjo ningún fill: §10.15); comisiones con monto distinto de cero; endpoints `/api/mm/live/*` contra Testnet; corridas más largas que 30 minutos (límite de 24 h de la conexión WebSocket API, rotación de suscripción). |
| **KNOWN LIMITATIONS** | Libro de Testnet fino y precios propios; Testnet cobra comisión cero; un fill no puede forzarse sin agresión y los overrides que lo hicieron posible son experimentales; offset de reloj host-venue no corregido en el servicio (y un mínimo negativo aislado en `submit_to_ack`); el status conserva los últimos 20 eventos del kill switch (el contador tiene el total); el estado local de órdenes no persiste entre procesos (la recuperación se apoya en la venue más el barrido, por diseño). |
| **REMAINING RISKS** (mayor a menor) | 1. Con los defaults de producción el maker no provee liquidez al touch y no opera: es una decisión de estrategia no tomada, no un bug, y hoy ningún parámetro de producción está validado como viable. 2. La confianza del fair value escalada por edad de datos y por "no 5 s volatility yet" lleva el tamaño bajo el mínimo y retira ambos lados durante ~20% del tiempo (435 + 219 retiradas en 30 min), con la cadencia de Testnet. 3. Comisiones: el camino de fees con monto real sigue sin observar. 4. Duración: nada supera 30 minutos; la rotación de la conexión WebSocket API a las 24 h no se ha observado. 5. Offset de reloj en los tramos de latencia de la venue. 6. Un fill sobre una huérfana entre la muerte y el barrido queda como trade histórico: balances correctos, sin atribución a orden. 7. El bloqueo de ~1 s del event loop de las corridas de 3 minutos no se reprodujo en 30 (0 stalls ≥ 200 ms en 17867 muestras); sin causa identificada, queda registrado. |

Ninguna de estas filas afirma "production ready", "profitable" ni "safe for real money".

### 10.12 Corrida real del 2026-10-04 16:27Z sobre `f85b3ef` (runbook completo): perfil Testnet, servicio, simulacro de recovery y el primer fill real

Evidencia: `docs/evidence/mm_service_testnet_f85b3ef_20261004T162719Z.json` y
`docs/evidence/mm_testnet_fillprobe_f85b3ef_20261004T162719Z.json`, copiadas sin modificar por el
runbook (commit `6dba9b7`), escaneadas: ninguna clave sensible, ningún token largo. Imagen
`trader-ia:prod` con `TIA_COMMIT=f85b3ef`. Hosts: `https://testnet.binance.vision`,
`wss://ws-api.testnet.binance.vision/ws-api/v3`, `wss://stream.testnet.binance.vision/stream`.
`is_live=False`, `activation=None`, sin token, sin dinero real.

**Perfil de latencia (VERIFIED TESTNET).** Medido 5 min contra Testnet desde el VPS: perfil
`3d7f433eaba72482`, commit `f85b3ef`, `source` nombra `stream.testnet.binance.vision` y
`testnet.binance.vision`. Los seis criterios duros de Fase 2 se cumplieron; `bookTicker`
consistente; 58 muestras instantáneas, 58 exactas. Vive en
`/home/tia/tia-testnet/runtime/mm/latency_profile.json`, fuera del volumen de producción.

**Servicio, primera corrida (180 s, 16:32:37 → 16:35:38).** 183 órdenes colocadas, 183 ack,
0 rechazadas, 182 canceladas confirmadas, 81 vencidas por TTL, 0 unknown, 0 fills, 0 errores
de API; 12 reconciliaciones, 0 fallas, última limpia; stream 365 reportes, 365 balances,
0 desconexiones; 883 eventos de mercado, 275 decisiones, 130 quotes, 88 requotes, 65 heartbeats,
0 errores del engine; 22 engagements transitorios `data` (datos stale, umbral PROVISIONAL de
1.0 s en la venue), todos liberados solos, ninguno sticky. Latencias (p50/p95/p99 ms):
submit RTT 236/250/331; submit → primer ack 238/249/334; reporte `E` → recepción 120/122/127;
recepción → aplicado 0/1/1; cancel → ack 243/485/676; evento → procesado 1/5/8 con un máximo
aislado de 985 ms (un bloqueo del event loop de ~1 s en 807 eventos; el callback en sí fue de
12 ms como máximo; la regla de edad de datos lo cubrió). Esta corrida no pasó por `stop()`:
murió a propósito en el simulacro.

**Simulacro de recovery (R1 a R7).** R1 **FAIL**, y la causa no es Trader-IA ni Binance: la
única orden `resting` al morir (`...-000183`) tenía `t_cancel_requested_ms` seteado con
`cancel_reason` "gate: data_invalid" (`cancel_requests 183, cancelled 182`: exactamente un
cancel en vuelo). El harness la contó como "dejada", la venue completó el cancel, y el GET con
cliente nuevo devolvió vacío. Defecto del simulacro (categoría 2), corregido en el commit
siguiente: el corte ocurre en un instante con alguna orden sin cancel pendiente, la
suscripción de mercado y los loops se cortan de forma sincrónica antes de leer la foto local,
las órdenes con cancel en vuelo se listan aparte y no cuentan, y si la venue no tenía nada
cuando arranca la segunda corrida, R2, R4 y R7 quedan NOT TESTED en vez de pasar en vacío
(como pasaron aquí: `found []`). La segunda corrida (`mm-testnet-service-restarted`, cliente
nuevo) arrancó limpia, cotizó solo con sus ids (57 colocadas, 57 ack, 57 canceladas, 21
vencidas, 0 unknown), 5 reconciliaciones limpias, 114 reportes, y paró con 0 abiertas local y en
la venue. **El barrido de huérfanas sigue SYNTHETIC ONLY**: en esta corrida no tuvo nada que
barrer. El FAIL queda en la evidencia tal como salió.

**S10b en Testnet (VERIFIED TESTNET).** Primera corrida con la semántica nueva: al final,
`engaged=false, sticky=false, transient={}`, `shutdown` registrado con razón y actor,
`blocks_quoting=true`. 9 engagements transitorios `data` durante la segunda corrida, 10 clears,
1 shutdown, 0 sticky. S9, S11, S12, S12b, S13: PASS. S8 en el servicio: NOT TESTED (ningún
quote del engine se llenó).

**El primer fill real (VERIFIED TESTNET, nivel adapter + stream + ledger, no el engine).** El
fill probe descansó un bid a 85301.67 (best bid) y un ask a 85301.68 (best ask), 8e-05 BTC
cada uno, post-only, 0 re-pegs. A los 13 s el mercado compró contra el ask: `executionReport`
TRADE con `t=2344502`, `m=true` (maker), `l=8e-05`, `L=85301.68`, `n=0.0`, `N=USDT`,
`X=FILLED`; `c/C` y `i=9248936` coinciden con el `orderId` local; recibido 115 ms después de
`E`; contabilizado una vez (`fills 1`, un trade id distinto, ledger 1); `myTrades` listó el
mismo print y fue reconocido como duplicado (no se contabilizó dos veces); 4
`outboundAccountPosition` después del fill; reconciliación: quote esperado 10006.824134 vs venue
10006.8241344 (delta 0.0, tolerancia 0.05), base 0.99992 vs 0.99992 (delta 0.0); el bid del
otro lado se canceló por la venue; desarme con un bid post-only a 85315.54 (best bid) que
también se llenó como maker 85 s después: inventario plano. `fill_to_ledger_ms`: 2 muestras,
p50 0 ms. Comisión 0 en Testnet (en USDT y en BTC), de modo que el camino de fee con
`commission_asset=BTC` quedó ejercitado con monto cero. Resultado neto del par: −0.001109
USD de Testnet. NOT TESTED en la venue: fill parcial (ambos fueron enteros), reporte demorado,
reporte duplicado emitido por la venue (el ítem 5 reinyecta un reporte real).

**Lo que esta corrida no demuestra.** Un fill del servicio (engine → cotización → fill);
el barrido de huérfanas contra la venue; un fill parcial real; el perfil de latencia bajo
carga más larga que 5 min.

### 10.13 Corrida real del 2026-10-05 04:16Z sobre `daef8e6`: recovery demostrada en Testnet

Evidencia: `docs/evidence/mm_service_testnet_daef8e6_20261005T041623Z.json`, copiada sin modificar
por el runbook (commit `ea3f44b`), escaneada: ninguna clave sensible, ningún token largo. Imagen
`trader-ia:prod` con `TIA_COMMIT=daef8e6`. Mismos hosts Testnet que §10.12; `is_live=False`,
`activation=None`. Esta vez sin fill probe (`FILL_PROBE` no seteado). Resultado: 27 PASS, 0 FAIL,
1 NOT TESTED (S8 en el servicio).

**Perfil de latencia.** Medido de nuevo contra Testnet: `b4740412038b6bac`, commit `daef8e6`,
`source` nombra Testnet; el perfil anterior quedó apartado como `latency_profile_20261005T041623Z_previous.json`.

**Primera corrida (180 s, 04:21:43 → 04:24:44).** 151 colocadas, 151 ack, 0 rechazadas, 150
canceladas confirmadas, 50 vencidas, 0 unknown, 0 fills, 0 errores de API; 12 reconciliaciones,
0 fallas; stream 301 reportes, 301 balances, 0 desconexiones; 1149 eventos, 264 decisiones, 63
heartbeats, 0 errores del engine; 21 engagements transitorios `data`, ninguno sticky. Latencias
(p50/p95/p99 ms): submit RTT 235/243/280; submit → primer ack 243/246/290; reporte `E` →
recepción 126/127/127; cancel → ack 247/481/578; evento → procesado 1/4/7 con un máximo aislado
de 968 ms.

**Simulacro de recovery, R1 a R7, todos PASS con una huérfana real.** La corrida murió con el
bid `tiamm-c7249c2b-1791174283935-000151` (85763.41, `orderId 9401408`) descansando y sin
cancel en vuelo (`cancel_in_flight_at_death: []`). Detalle que la evidencia muestra y conviene
dejar escrito: al cortar el stream de cuenta, el kill switch transitorio `user_stream_down`
pidió el cancel localmente (`t_cancel_requested_ms 1791174284786`, historial `cancelled: 1`),
pero el worker fue cortado antes de que el pedido saliera, así que la venue siguió teniendo la
orden (`cancel_requests 151, cancelled 150`). Es decir: la "muerte" fue observada en parte por
el servicio, como pasaría con un corte de red, y aun así la orden quedó huérfana en la venue,
que es la condición que importa. R1: la venue la listaba. La segunda corrida
(`mm-testnet-service-restarted`, cliente nuevo) la encontró en el barrido 460 ms después, la
consultó por id (`order_resolved_present`, estado `acknowledged`), la canceló por la venue
(estado `cancelled`), lo registró en el journal (`kind: orphan_sweep`) y lo elevó como
`mm_live_orphans_swept`; reconciliación inicial limpia (R3); ninguna orden de la corrida muerta
abierta (R4); stream suscripto (R5); cotizó solo con sus ids, 64 colocadas (R6); ningún id de la
corrida muerta adoptado ni reenviado, `venue_orders_unknown_locally 0` (R7). Segunda corrida:
64 ack, 64 canceladas, 29 vencidas, 0 unknown, 5 reconciliaciones limpias, 128 reportes, 7
transitorios `data` con 7 clears, `stop()` con `shutdown` registrado, `engaged=false`, 0
abiertas local y en la venue (S10b, S12, S12b PASS).

**Lo que esta corrida demuestra.** La recuperación tras una muerte con órdenes descansando, a
nivel de servicio y contra la venue real: barrido por id antes de cotizar, sin adopción, sin
reenvío, sin duplicados, reconciliación limpia después. **Lo que no demuestra:** una huérfana
que la venue rechace cancelar (SYNTHETIC ONLY), un fill sobre la huérfana entre la muerte y el
barrido (SYNTHETIC ONLY, y el ledger lo trataría como trade histórico), y S8 a nivel servicio.

**Observación recurrente.** Un bloqueo aislado del event loop por corrida: 985 ms (§10.12,
primera corrida), 968 ms y 640 ms aquí (`market_event_to_processed_ms` y
`decision_to_enqueue_ms` máximos; el callback en sí no pasa de 11 ms). La regla de edad de datos
lo cubre (el gate bloquea y cancela), pero la causa no está identificada. Instrumentar el lag
del event loop en el servicio es el siguiente ítem de observabilidad.

### 10.14 Por qué el engine cancela todas sus órdenes en Testnet, y el experimento controlado para S8 a nivel servicio

**Diagnóstico (evidencia `daef8e6`, 2026-10-05).** En la primera corrida, 151 órdenes colocadas,
151 reconocidas, 150 canceladas confirmadas, 0 fills. Las 43 decisiones `quote` del journal
tienen `half_spread_bps = 10.5` con `spread_binding = cost_floor`: el piso de costo asume 10 bps
de comisión maker (`MarketMakerCostConfig.maker_fee_bps = 10.0`, `fee_scenario = "assumed"`)
más 0.5 bps de colchón, así que **cada cotización descansa a 90 USD del mid, de cada lado**,
cuando el spread real de Testnet es un centavo. Además `quote_ttl_ms = 1000` vence cada
cotización al segundo (50 de 151 cancelaciones) y `requote_threshold_bps = 0.5` (0.43 USD) la
reemplaza ante cualquier jitter del fair value (92 requotes, 101 cancelaciones). Para llenarse,
el precio tendría que atravesar 90 USD en el segundo de vida de la orden. El fill probe (§10.12),
que descansó AL best, se llenó en 13 segundos. Conclusión: no es un bug del plumbing ni de
Testnet; con esos parámetros el maker no provee liquidez al touch y no opera, ni acá ni en
Mainnet. Es una decisión de estrategia, y hace imposible S8 a nivel servicio.

**Experimento controlado (commit siguiente a `0ea5286`).** Tres overrides **exclusivamente en el
harness** (`scripts/validate_mm_live_service_testnet.py`), explícitos en la línea de comandos,
validados, y registrados en la evidencia (`args` y `responses.experiment`, más el ítem
`S0.experimental_overrides_recorded`):

| Flag | Default de producción (sin cambios) | Valor del experimento |
|---|---|---|
| `--fee-scenario` | `assumed` (10 bps asumidos) | `testnet_zero`: un `MarketMakerCostConfig` con comisiones cero construido en el harness; Testnet cobra cero (`n=0.0` en los fills reales). El engine sigue buscando el escenario `assumed`: no aprende un nombre nuevo |
| `--quote-ttl-ms` | 1000 | 30000 (rango admitido 100 a 300000) |
| `--requote-threshold-bps` | 0.5 | 5 (rango admitido 0.1 a 100) |

Valores fuera de rango, no numéricos, o los escenarios de producción `verified`/`adverse`, se
rechazan antes de conectar nada. Sin flags, la configuración construida es **idéntica** a la de
siempre (test que compara el dataclass completo). **No cambia** el umbral PROVISIONAL de 1.0 s de
edad de datos (el harness no nombra `max_venue_age_s`, y un test lo vigila), el kill switch, los
autorizadores de riesgo y economía, la validación maker-only, LIMIT_MAKER, el cap de capital, los
rails Testnet-only ni ningún default de producción.

**Estos parámetros son EXPERIMENTALES.** Existen para demostrar el camino engine → adapter →
stream de cuenta → correlación → ledger → reconciliación con un fill real del servicio. No son
una recomendación de estrategia, no son una hipótesis de comisiones para Mainnet y no dicen nada
sobre rentabilidad.

**Evidencia nueva que la corrida registra, con o sin experimento.** `responses.order_lifecycle`
por orden: enviada a la venue, reconocida (y por qué fuente), tiempo que descansó, cómo terminó
(`filled`, `cancelled:ttl`, `cancelled:requote`, `cancelled:stale_data`, `cancelled:shutdown`,
`cancelled:kill_switch`, `cancelled:pacing`) y percentiles de tiempo en libro (ítem
`S5b.order_lifecycle_recorded`); en el simulacro, también el de la corrida muerta.
`responses.fills`: cada fill con trade id, client id, `orderId` de la venue, fuente
(reporte o `myTrades`), liquidez, comisión, y si correlaciona con la orden local (ítems
`S8b.fills_correlated_by_clientOrderId_and_orderId`, `S8c.reconciliation_after_the_fill_clean`,
`S8d.fill_to_ledger_latency_measured`; NOT TESTED sin fill). `responses.event_loop`: lag del
event loop del proceso medido por un durmiente de 100 ms, con percentiles y la lista de stalls
mayores a 200 ms con timestamp (ítem `S4b.event_loop_stalls_observed`, registrado, no juzgado).

Comando del experimento desde el VPS, cuando se decida correrlo:
`S8_EXPERIMENT=1 MINUTES=30 bash scripts/run_mm_service_testnet_validation.sh`.

### 10.15 Corrida del experimento S8 del 2026-10-05 05:39Z sobre `e5b5625` (30 minutos, overrides EXPERIMENTALES): el primer fill real de un quote del engine, y la corrida de control con defaults

Evidencia: `docs/evidence/mm_service_testnet_e5b5625_20261005T053437Z.json` (commit `8511d6b`,
copiada sin modificar desde el VPS). Control: `docs/evidence/mm_service_testnet_0ea5286_20261005T044643Z.json`
(commit `513ea49`, defaults de producción, 30 minutos, misma cuenta y mismo host, una hora antes).
Las dos corridas midieron su perfil de latencia contra Testnet justo antes (el del experimento:
`c4596561e4d56b14`, 05:34:44Z). Todo lo que sigue sale de los JSON, no de los logs.

**Control con defaults (`0ea5286`, 04:52Z, 30 min).** 874 órdenes colocadas, 873 reconocidas,
873 canceladas (304 por el TTL de 1 s; el resto requotes y stale-data), 0 fills, 0 rechazos;
half-spread 10.5 bps (`cost_floor` con 10 bps de comisión asumida); 341 enganches transitorios
del kill switch por datos; sin ninguna orden abierta en 218 de 360 muestras (60% del tiempo); 116
reconciliaciones limpias; un `-1021` en `openOrders` (`api_errors 1`) sin consecuencia; 20 PASS y
S8 NOT TESTED. Confirma el diagnóstico de §10.14 sobre 30 minutos: con los defaults el engine no
se llena.

**Experimento (`e5b5625`, 05:39Z, 30 min, `--fee-scenario testnet_zero --quote-ttl-ms 30000
--requote-threshold-bps 5`, registrados en `args`, `responses.experiment` y
`S0.experimental_overrides_recorded`).** 27 PASS, 0 FAIL, 0 NOT TESTED. Por capa:

- **Engine.** 8716 eventos, 2672 decisiones, 889 quotes, 412 requotes, 1309 cancels, 0 errores.
  Half-spread 2.67 bps = `cost_floor` 1.12 (comisión 0 + adverse selection medida 0.62 bps sobre
  24 markouts + colchón 0.5) + ensanche por toxicidad 1.55: unos 23 USD del centro, contra 90 USD
  con defaults. El autorizador de economía dejó pasar ambos lados ("both quoted sides clear the
  floor", neto ~2.05 bps con comisión cero). El `fee_scenario` del engine sigue siendo `assumed`:
  el harness le dio un `MarketMakerCostConfig` con 0 bps bajo ese nombre, y así quedó grabado
  (`responses.quoting.costs.maker_fee_status = EXPERIMENT_TESTNET_ZERO`).
- **Órdenes** (`responses.order_lifecycle`, 1343 filas). 1341 enviadas (2 canceladas antes de
  salir), 1324 reconocidas, **17 rechazadas por la venue con -2010** (would cross: el rail
  post-only; `taker_fills 0`), 0 unknown. 1309 pedidos de cancel, 1301 canceladas confirmadas,
  **0 por TTL** (los 30 s nunca se alcanzaron: la orden que más descansó vivió 10.2 s), 3
  `cancel_rejected_after_close`: 2 sobre órdenes que se llenaron mientras nuestro cancel viajaba
  (`requote | cancel rejected (code -2011)`; el fill manda y la orden queda `filled`) y 1 sobre una
  orden que el stream ya había cerrado.
- **Cómo terminaron.** Tal como se grabó: `requote` 409, `stale_data` 238, `shutdown` 2, `filled`
  23, `refused` 17 y **`other` 654**. Las 654 son las dos razones `no_quote` del engine, pasadas
  textuales como razón del cancel (`engine.py`, `cancel_all` sobre una decisión sin quote):
  "both sides sized to zero" 435 y "fair value confidence 0.11–0.20 below 0.20" 219. El
  clasificador del harness no las conocía; el commit `9dc3845` agrega las clases
  `no_quote_size`, `no_quote_confidence`, `no_quote_risk` y `no_quote_implausible`, guarda la
  razón hasta 160 caracteres (la evidencia la cortó en 80) y lo cubre con las cadenas reales de
  esta corrida. Es una corrección del harness; no cambia ninguna fila de la evidencia.
- **Tiempo en libro.** p50 1003 ms, p90 2824, máx 10209 (1324 órdenes reconocidas). Por clase:
  requote p50 89 ms (el engine las reemplaza al moverse 5 bps); retiradas `no_quote` p50 1.2 a
  1.4 s; stale-data p50 1.2 s; llenadas p50 776 ms, máx 3896.
- **Fills** (`responses.fills`). **24 trades sobre 23 órdenes, todos maker, todos por el
  account stream** (`attribution_source report`), 0 por `myTrades`; 2478 duplicados reconocidos
  (los polls de respaldo volvieron a ver los mismos trade ids y el dedupe por id los descartó;
  `duplicate_reports 0`). 13 ventas y 10 compras por órdenes; 0.00157 BTC comprados, 0.00197
  vendidos; inventario final -0.0004 BTC (máximo 0.00046). Una orden (`...-000912`, ask 0.00016)
  se llenó en dos trades (0.00005 + 0.00011): PARTIALLY_FILLED → FILLED, ambos asentados una vez:
  **el fill parcial real queda observado**. Comisión 0.0 en los 24 (Testnet), `fee_asset` USDT en
  ventas (`venue`) y BTC en compras (`converted_from_base`, monto cero). 24/24 correlacionados
  (trade id de la venue, nuestro client id, el `orderId`, un asiento por orden). `fill_to_ledger`
  p50 0 ms, máx 1; `report_to_local` p50 127 ms (incluye el offset de reloj). Los fills se
  repartieron a lo largo de los 30 minutos (del minuto 0.3 al 26.4).
- **Ledger y reconciliación.** 116 reconciliaciones, 0 fallas; la final limpia con 0 abiertas en
  ambos lados; `expected_quote_usd 10034.324812` vs venue `10034.3248117` (3e-7 USD, redondeo),
  base 0.9996 en ambos; `trades_seen 26` = 24 de la corrida + 2 históricos anteriores a ella (no
  atribuidos a orden, por diseño). P&L del ledger: realizado -0.01997 USD, no realizado +0.0127,
  neto -0.0073 USD, adverse selection 0.0406 USD, fees 0. Son 24 fills en Testnet con comisión
  cero y precios propios de Testnet: **no dicen nada sobre rentabilidad.**
- **Kill switch.** 239 enganches transitorios por datos (los 238 cancels `stale_data`), ninguno
  sticky, `cancelled_total 6`; el shutdown registrado como shutdown (S10b PASS). La nota de S10
  listó 9 porque el status conserva los últimos 20 eventos; `9dc3845` hace que la nota
  lea el contador. Datos no usables en 41 de 360 muestras (~3.4 min); sin órdenes abiertas en 71
  muestras (~20%, contra 60% con defaults).
- **Stream de cuenta.** 1 conexión, 0 cortes, 2649 reportes, 2649 balances, 0 errores de
  parseo; 249 reportes llegaron antes de la respuesta REST del submit. El `stream_drops 1` y el
  `critical_reason user_stream_down` del status final son el cierre del stream por `stop()`, como
  en §10.13.
- **Event loop** (`responses.event_loop`). 17867 muestras, p50 0.7 ms, p99 5.1, máx 66.5,
  **0 stalls ≥ 200 ms**. El bloqueo de ~1 s visto en las corridas de 3 minutos no apareció en 30.
  `market_event_to_processed` y `decision_to_enqueue` tienen un máximo de 762 ms en un solo
  evento, que el durmiente no vio: una ráfaga encolada, no un bloqueo del loop.
- **Tramos de latencia.** `enqueue_to_submit` p50 234 ms (el worker serializa: la segunda orden
  del par espera el RTT de la primera), `rest_submit_rtt` p50 235 p99 325, `submit_to_first_ack`
  p50 244, `cancel_to_ack` p50 260 p99 747 máx 1198. Un mínimo aislado negativo (-584 ms) en
  `submit_to_ack` y `submit_to_first_ack` es un artefacto de medición de una sola orden, sin
  efecto sobre estados; queda anotado como limitación.

**Qué demuestra y qué no.** Demuestra, contra Binance Spot Testnet, el camino completo engine →
adapter → venue → account stream → correlación → ledger → reconciliación con 24 fills reales de
quotes del engine, incluido un fill parcial, sin unknowns, sin duplicados, con el rail post-only
rechazando las 17 órdenes que habrían cruzado y la reconciliación final con delta cero. **No
demuestra una estrategia**: los overrides son EXPERIMENTALES y con los defaults de producción el
engine no se llena (control). No demuestra comisiones con monto (Testnet cobra cero), ni dice
nada sobre Mainnet, producción ni dinero real.

**Dos observaciones del engine que quedan abiertas (no se modificó nada).** (1) La confianza del
fair value cae con la edad de los datos (`1 - edad/2000 ms`) y se multiplica por 0.8 cuando no
hay volatilidad de 5 s; con la cadencia de Testnet (~1 s, y `_mids` sólo guarda cambios del mid,
así que en 5 s no siempre hay los 4 puntos que `vol_min_returns = 3` exige) ese factor está casi
siempre activo. Con `scale_size_by_confidence`, 0.0002 BTC × confianza ~0.4 a 0.6 × toxicidad
0.85 cae bajo el mínimo de 0.0001 BTC y el engine retira ambos lados ("both sides sized to zero",
435 veces) o no cotiza por confianza < 0.20 (219). Es la causa del 20% de tiempo sin órdenes y de
la mayoría de los cancels. (2) Las 17 would-cross: con half-spread 2.67 bps y re-cotización a 5
bps, algunos quotes llegan a la venue cruzando un touch que ya se movió; el rail funciona, y
mide cuánto se acerca el engine al touch con estos parámetros.

### 10.16 Instrumentación de markouts y contexto por fill (evidencia, sin cambio de comportamiento)

**Por qué.** La auditoría económica de la corrida `e5b5625` sólo pudo medir el adverse selection
a 1 s, y recortado, invirtiendo el EWMA de toxicidad que el spread engine deja ver en el
half-spread muestreado cada 5 s. El engine medía seis horizontes (100, 250, 500, 1000, 2000 y
5000 ms) en memoria y los escribía en su journal, pero el harness exportaba sólo la cola del
journal y ningún mid. Esta iteración exporta los datos crudos. **No cambia ninguna decisión**:
el journal de decisiones, fills y markouts de la cinta sintética de `tests/unit/mm/test_engine_replay.py`
tiene el mismo SHA-256 que antes del cambio (`6eccfa05…b452` para 20 prints, `cf28cbef…8f51`
para 40), pinneado en `tests/unit/mm/test_markout_raw_export.py`; con los buffers de evidencia
deshabilitados el hash es idéntico; y un fallo forzado dentro del registro queda en el registro
y no toca la contabilización del fill. En `engine.py` y `adverse_selection.py` el diff no elimina
ni modifica ninguna línea existente: sólo agrega.

**Convención de resolución de horizontes** (`tia.mm.adverse_selection.HORIZON_RULE`, copiada
textual en la evidencia): un horizonte `h` se resuelve con el **primer mid observado en o
después de `t_fill + h`**, y sólo si ese mid llega dentro de `tolerance_ms` (1000 ms) de
`t_fill + h`; un mid posterior significa un hueco de datos y el horizonte queda **no medido**
(el fill se conserva como `unresolved` con los horizontes que sí se resolvieron). Signo: `markout_bps
= signo × (mid_at_mark − precio) / precio × 1e4`, con signo +1 para compra y −1 para venta:
positivo es favorable, negativo es adverso; `markout_usd = markout_bps / 1e4 × precio × cantidad`.
El mid es el del libro local del servicio (`MarketDataService`), el mismo que ve el tracker.

**Qué exporta ahora `scripts/validate_mm_live_service_testnet.py`.**

| Bloque de la evidencia | Contenido |
|---|---|
| `responses.fills[]` (una fila por fill, unidas por trade id) | lo de antes (correlación, liquidez, fuente, fee) más `trade_id`, `venue_order_id`, `client_order_id`, `t_fill_ms`, `notional_usd`, `inventory_before_btc`, `inventory_after_btc`, `bid_quote`, `ask_quote`, `bid_size`, `ask_size`, `mid_at_quote`, `mid_at_fill`, `mid_used_by_tracker`, `fair_value_at_quote`, `fair_value_at_fill`, `half_spread_bps_at_quote`, `spread_binding_at_quote`, `capture_bps_vs_fair_value_at_quote`, `capture_bps_vs_mid_at_fill`, `confidence_at_quote`, `toxicity_at_quote`, `toxicity_at_fill`, `data_age_at_quote_ms`, `data_age_at_fill_ms`, `vol_5s_bps_at_quote`, `inventory_adjustment_bps_at_quote`, `t_decision_ms`, `t_enqueued_ms`, `t_ack_ms`, `ack_source`, `resting_ms`, `realised_usd`, `regimes`, y `markouts[]` (por horizonte: `horizon_ms`, `target_t_ms`, `mark_t_ms`, `delay_ms`, `mid_at_mark`, `markout_bps`, `markout_usd`, `measured`) con `markouts_resolved/expired/pending` |
| `responses.markouts` | `convention` (la regla, textual), `horizons_ms`, `tracker` (resumen del `MarkoutTracker`), `toxicity_final`, `rows[]` (crudo por fill: resueltos, expirados con lo que sí se midió, y pendientes al stop), `summary` por horizonte: `measured`/`unmeasured`, `markout_bps` {count, mean, median, p25, p75, min, max, weighted_mean por notional}, `markout_usd_sum`, `by_side` buy/sell, `adverse_share`, `clipped_adverse_bps_mean` (lo que ve toxicidad), `clipped_favourable_bps_mean`, `delay_ms` |
| `responses.mid_series` | todos los mids que vio el tracker, `[t_ms, mid]`, con `count`, `t_first_ms`, `t_last_ms` |
| ítem `S8e.markouts_raw_exported_and_consistent` | PASS si cada fill real tiene su fila cruda, cada fila cumple su propia regla (target = t_fill + h; mark ≥ target y dentro de la tolerancia; bps y USD coherentes con el mid y el precio; el primer mid ≥ target de la serie es exactamente el `mid_at_mark`) y cada fill tiene contexto del quote; NOT TESTED sin fills. Juzga completitud y consistencia, nunca el valor |

**Cómo se reconstruye cada markout offline.** Con `responses.mid_series.samples` ordenada por
`t_ms`: para el fill `f` y el horizonte `h`, `target = f.t_fill_ms + h`; tomar la primera muestra
con `t_ms ≥ target`; si `t_ms − target > 1000`, el horizonte no es medible (debe coincidir con
`measured = false`); si no, `mid_at_mark` es su mid, `markout_bps = signo × (mid − f.price) /
f.price × 1e4` y `markout_usd = markout_bps / 1e4 × f.price × f.quantity`. El ítem S8e verifica
esta reconstrucción contra las filas crudas en cada corrida. El contexto del quote
(`fair_value_at_quote`, `confidence_at_quote`, `bid_quote`, `ask_quote`, `toxicity_at_quote`,
`data_age_at_quote_ms`) es lo que el engine sabía en la decisión que colocó la orden;
`capture_bps_vs_fair_value_at_quote` es la distancia del precio de la orden a ese fair value, y
`capture_bps_vs_mid_at_fill` la distancia al mid del libro cuando llegó el reporte del fill.

**Dónde vive en el engine.** Tres buffers de sólo evidencia: `MarketMakerEngine.mid_samples`
(deque de 50 000 `(t_ms, mid)`, alimentado en el mismo punto en que el tracker recibe el mid),
`MarketMakerEngine.fill_records` (deque de 20 000 registros, escrito después de contabilizar el
fill, con `inventory_before` leído antes) y `MarketMakerEngine._order_quotes` (el contexto de la
decisión por orden, podado junto con `_order_regimes`). En el tracker, `Markout.mid_at_mark`,
`Markout.raw()`, `MarkoutTracker.unresolved` y `MarkoutTracker.raw_rows()`; `Markout.as_dict()`,
que es la fila del journal, no cambió. Ninguna decisión, autorizador, spread, toxicidad,
inventario, ejecución ni rail lee nada de esto.

**Próxima corrida.** Mismo comando y mismos overrides EXPERIMENTALES que §10.15
(`S8_EXPERIMENT=1 MINUTES=30 bash scripts/run_mm_service_testnet_validation.sh`, es decir
`--fee-scenario testnet_zero --quote-ttl-ms 30000 --requote-threshold-bps 5`), sin ejecutar
todavía. Con esta evidencia la auditoría de §10.15 se repite con markouts medidos, no inferidos,
en los seis horizontes, con signo, por lado y por inventario.

**Corrección tras la corrida `5ac604e` del 2026-10-05 19:27Z** (evidencia
`mm_service_testnet_5ac604e_20261005T192714Z.json`, 27 ítems, S8e FAIL con 12 inconsistencias).
S8e detectó dos hechos reales, ninguno de ellos un error del cálculo del tracker:

1. **Lag de registro.** El fill lleva el tiempo de la venue (`t_fill`) y se registra en el tracker
   al procesar el reporte, 116 a 153 ms después (p50 127). Un horizonte cuyo instante ya pasó al
   registrar sólo puede resolverse con el primer mid observado **después** del registro. En esta
   corrida afectó al horizonte de 100 ms en los 14 fills (marca efectiva 125 a 233 ms) y a ningún
   otro. El tracker ahora guarda `t_registered_ms` y exporta por horizonte `late_by_ms`,
   `measured_late` y `effective_horizon_ms`; la regla (`HORIZON_RULE`) lo dice textualmente. **No
   se rellena nada hacia atrás**: si el fill llegó tarde, la evidencia lo dice.
2. **Timestamp viejo en `reconcile()`.** El tick que la reconciliación daba al engine llevaba el
   tiempo del *inicio* de la reconciliación, anterior a tres lecturas REST (222 a 843 ms): 107
   muestras de `mid_series` quedaron estampadas antes que muestras ya procesadas, cada una igual al
   `t_ms` de una reconciliación. No alteró ningún markout (una muestra con estampa vieja nunca
   resuelve lo que una más nueva ya resolvió) pero rompía la reconstrucción offline ordenada por
   tiempo. El tick y `absorb_balances` se estampan ahora con la hora posterior a las lecturas.

S8e usa desde ahora la regla con lag ("primer mid observado después del registro con estampa ≥
target"), recorre `mid_series` en orden de procesamiento, cuenta y exporta las inversiones de
timestamp (`responses.mid_series.inversions`), y el resumen separa `measured_on_time` de
`measured_late` con `late_by_ms` y `effective_horizon_ms`. Verificación sobre la evidencia de
`5ac604e`: 0 problemas de reconstrucción con el tiempo de recepción como registro, 107 inversiones
identificadas (S8e seguiría FAIL sobre ese archivo, correctamente, hasta la próxima corrida con el
tick corregido). Los hashes dorados del journal no cambiaron; los markouts de 250 ms a 5 s de esa
corrida coinciden con la reconstrucción offline en 70 de 70 filas. Casos reales `2422185` y
`2423539` fijados como fixtures en `tests/unit/test_mm_service_validator_markouts.py`.

### 10.17 Relojes separados: el outlier de 982 ms, `resting_ms` y el offset host–venue (instrumentación, sin cambio económico)

**Auditoría (commit después de `f74c363`).** La corrida `ee987a5` dejó tres deficiencias de medición;
las tres se demostraron con código y trazas antes de tocar nada.

1. **El máximo de 982 ms en `decision_to_enqueue` y `market_event_to_processed` es la edad del snapshot
   de handover.** `MarketDataService.subscribe()` entrega al nuevo consumidor el libro tal como está,
   estampado con `book.last_received_at_ms` (la recepción de su último update). `LiveMarketMakerService.start_live()`
   se suscribe después del barrido de huérfanas y de la reconciliación inicial (varias lecturas REST), así que
   ese stamp puede tener la edad del silencio del feed en ese instante. El engine decide sobre ese evento con
   `t_ms` = stamp; las primeras órdenes heredan `t_decision_ms` = stamp y `decision_to_enqueue = t_enqueued − stamp`;
   `market_event_to_processed = done − stamp`. Traza: en `ee987a5` el primer mid de `mid_series` tiene estampa
   `1791255058064` (igual a `freshness.last_change_ms`) y la primera orden se encoló en `1791255059046`:
   **982 ms exactos**; en `5ac604e`, 64 ms exactos. El loop no se bloqueó (`callback_ms` máx 25 ms): la métrica
   sumaba la edad del dato con el procesamiento. No es un stall ni un resync.
2. **`resting_ms` mezclaba relojes.** `fill.t_ms` es el `T` de la venue; `t_ack_ms` es la hora del host al
   procesar el reporte NEW o la respuesta REST. En `ee987a5` dio −74 ms en un fill tomado al llegar al libro.
3. **El offset host–venue no estaba medido** (`venue_clock_offset_status: not measured`). Otros cruces de reloj
   auditados y dejados como están, por diseño y documentados: `report_to_local_ms` (recepción host − `E` venue,
   declarado como "incluye el offset"), los horizontes del tracker (`t_fill` venue + h contra mids host; corregible
   offline con el offset) y `trade_baseline_ms` (venue contra host con 60 s de holgura explícita).

**Instrumentación (sólo datos; ningún cambio en spread, fair value, toxicidad, EV, sizing, riesgo, ejecución,
market data ni rails).**

| Dónde | Qué se agrega |
|---|---|
| `LiveOrder` | `t_decided_host_ms` (instante host en que la orden se construyó a partir de la decisión; `t_decision_ms` sigue siendo el stamp del evento de mercado), `venue_ack_time_ms` (aceptación según la venue: `transactTime` de la respuesta REST o `T` del reporte NEW), `mono_enqueued_ms`, `mono_ack_ms` (reloj monotónico del host) |
| `LiveFill` | `received_mono_ms` |
| `LiveMarketMakerService` | `event_age_at_callback_ms` (stamp del evento → inicio del callback; `market_event_to_processed = edad + callback`), `timing_anomalies` (deque acotada: eventos con edad o callback > 200 ms con todos sus stamps, `book_update_id`, `handover`, decisiones y quotes producidos), `status()["timing"]` |
| `MarketDataService` | `sync.handovers`, `sync.last_handover_age_ms` |
| Engine `fill_records` | `host_resting_ms` (recepción host del fill − ack host), `venue_resting_ms` (`T` del trade − aceptación venue; `None` si falta), `resting_ms` = host, `event_age_at_decision_ms`, `t_decided_host_ms`, `venue_ack_time_ms`, stamps monotónicos |
| Harness | `_order_lifecycle` con `host_resting_ms`/`venue_resting_ms`/`event_age_at_decision_ms`/`host_wall_vs_mono_drift_ms` por orden y agregados (máximo con su orden, cuántas > 200 ms); `responses.clock` {`at_start`, `at_end`, `derived`}; `responses.market_at_start_full`, `responses.market_at_end` (resyncs, snapshots, fallos, handovers, conexiones/cortes/reconexiones del stream, transiciones de frescura, episodios stale); `responses.timing`; ítems `S0b.venue_clock_offset_measured` y `S4c.timing_anomalies_and_clocks_recorded` (registrados y explicados, no juzgados) |

**Offset de reloj: metodología y error.** Siete `GET /api/v3/time` con el wall clock del host antes y después:
`offset_i = serverTime − (antes + después)/2`, `rtt_i = después − antes`; estimación = mediana de los offsets;
error acotado por `min(rtt)/2` (el servidor pudo responder en cualquier instante del viaje). Signo positivo:
la venue adelanta al host. Se mide al inicio y al final (deriva). **No se aplica en ningún lado**: `venue_age`
sigue incluyendo el offset, como antes; cambiarlo sería un cambio de comportamiento de market data. Derivados
en la evidencia: `report_latency_est_p50 = report_to_local_p50 − offset`, `depth_latency_est_p50` igual con
`depth_receive_minus_event_ms`, ambos con el error del offset.

**Qué significa cada duración ahora.** `host_resting_ms`: tiempo host desde el ack hasta recibir el reporte del
fill; `venue_resting_ms`: tiempo venue desde la aceptación hasta el trade, `None` si la aceptación venue no se
conoce; `event_age_at_decision_ms`: cuán viejo era el dato de mercado cuando se decidió; `decision_to_enqueue_ms`
conserva su cálculo (stamp del evento → encolado) y su nota dice que incluye la edad del evento; el handover queda
señalado en `timing.anomalies` con `handover: true`. El camino paper tiene un solo reloj simulado: `host_resting`
= antes, `venue_resting` = `None`.

**Tests.** `tests/unit/mm/test_timing_clocks.py` (offsets de reloj venue de −5 s a +5 s sin alterar las
duraciones host; venue_resting sólo de stamps venue; fill sin ack → `None`, nunca negativo; handover de 982 ms
registrado como anomalía con edad 982 y `t_enqueued − t_decided_host = 0`; handover fresco sin anomalía; hashes
dorados intactos) y `tests/unit/test_mm_service_validator_clocks.py` (estimador de offset; lifecycle con el caso
real de −74 ms → host 53 ms y venue 192 ms; compatibilidad con objetos sin los campos nuevos; deriva wall vs
monotónico). Diff: ninguna línea eliminada en spread, fair value, toxicidad, inventario, riesgo, autorización,
quoting, costos, tracker, kill switch, gate ni ledgers.

**Regresión del harness detectada en la primera corrida con esta instrumentación (2026-10-06 05:09Z,
evidencia `mm_service_testnet_0fc5763_20261006T050913Z.json`, commit `9dfa167`): S1 FAIL, corrida abortada
antes de cotizar.** La medición del offset de reloj (siete REST, 1635 ms) se había insertado entre la espera
de "market data usable" y el juicio de S1, que releía `market.usable` después. `market_at_start` muestra
`usable=True` con 24 ms de edad en el instante de la espera; 1.6 s después el feed de Testnet estaba stale y S1
falló. Causa: orden de operaciones en el harness, no el feed ni la economía. Corrección: la medición del offset
va antes de `market.start()`, y S1 se juzga con el snapshot tomado en el instante de la espera, sin ningún
`await` entre medio; test de regresión sobre el orden del código. La evidencia fallida se conserva tal cual.
El offset medido en esa corrida: venue − host **+0.0 ms ± 115.5 ms** (RTT mínimo 231 ms, n=7).

### 10.18 S8e en la corrida de 60 minutos sobre `9bd4b17`: dos reconstrucciones a 100 ms, la causa y la numeración de mids (evidencia, sin cambio económico)

**Resultado observado (2026-10-06, 60 min, overrides EXPERIMENTALES).** 19 fills; los seis horizontes medidos en
todos; 100 ms: 19/19 `measured_late` (lag de registro 120–156 ms, esperado); 250–5000 ms: 0 late; `mid_series`
15 043 muestras, 0 inversiones. S8e FAIL por exactamente dos problemas de reconstrucción, ambos a 100 ms:

| Fill | `mid_series` dice (primer mid con stamp ≥ target visto "después" del registro) | La fila del tracker dice | Diferencia |
|---|---|---|---|
| 2447364@100 | (1791267584469, 85298.775) | (1791267584532, 85289.455) | 63 ms, −1.09 bps |
| 2447492@100 | (1791267741150, 85281.275) | (1791267741230, 85267.495) | 80 ms, −1.62 bps |

**Flujo auditado, sello por sello.**

| Instante | Quién lo produce | Reloj |
|---|---|---|
| `t_fill` | `report.transaction_time_ms` (`T` del executionReport) → `LiveFill.t_ms` → `FillObservation.t_fill_ms` | venue |
| stamp de cada mid de `mid_series` | `MarketDataStream.on_message`: `received_at_ms = self._now_ms()` al leer el mensaje → `DepthUpdate.received_at_ms` → `MarketDataService._notify(kind, event, received)` → `engine.on_event(kind, event, t_ms)` → `mid_samples.append((t_ms, mid))` y `markouts.on_mid(t_ms, mid)`, en la misma línea y con el mismo valor | **`ReceiveClock`**: wall anclado una vez al monotónico al construir el stream (el harness lo construye sin `now_ms`; producción, `state.py`, igual) |
| `t_registered_ms` | `BinanceUserDataStream.on_message`: `received_at_ms = self._now_ms()` → `absorb_execution_report(report, received_at_ms)` → `_book_fill(order, fill, t)` → `fill_sink(fill, t)` → `LiveMarketMakerService._on_live_fill` → `engine._on_fill(fill, t)` → `markouts.register(..., t_registered_ms=t)` | **wall** (`clock.timestamp_ms`, inyectado como `now_ms` por el harness y por `state.py`) |
| `mark_t_ms`, `mid_at_mark` | `MarkoutTracker.on_mid`: el primer `on_mid` **después** de `register` (orden de procesamiento) con `t_ms ≥ t_fill + h` | el del mid (ReceiveClock) |

Dentro de cada camino no hay `await` entre el sello y el procesamiento: ambos `on_message` son sincrónicos hasta el
engine. El engine agrega el mid a `mid_samples` y se lo entrega al tracker con el mismo `(t_ms, mid)`: dentro de un
evento no hay dos selecciones de mid. Lo que no existe es un orden común entre los dos caminos: el fill y el depth
update que lo causa son el **mismo trade** en la venue, salen juntos, llegan por dos conexiones y cada uno recibe el
sello de su propio reloj cuando su tarea lo lee. En los dos casos el evento de mercado se procesó primero (el tracker
lo consumió con el fill todavía desconocido) y la confirmación del fill después; el tracker resolvió, correctamente
(nada se rellena hacia atrás), con el mid **siguiente**, 63 y 80 ms más tarde. El harness, que ubicaba el registro
por su sello (`processed ≥ t_registered` ⇒ "después del registro"), tomó el mid anterior porque su sello era ≥ el del
registro: basta un empate al milisegundo con el mismo reloj (`callback_ms` p50 = 1 ms en la corrida anterior), y con
dos relojes basta que el wall vaya unos ms detrás del `ReceiveClock`. Los dos casos se reprodujeron con el
`MarkoutTracker` real y el `_first_mid_seen` real bajo ambas mecánicas (empate y desfase de 9 ms), con el texto exacto
del problema. Cuál de las dos ocurrió en la corrida lo dice `t_registered_ms` de la evidencia (igual al sello del mid
anterior: empate; menor: desfase); la conclusión no cambia.

**Causa raíz.** "Primer mid observado después del registro" es una afirmación sobre el **orden de procesamiento** del
tracker. El exportador la reconstruía comparando **sellos de dos colas con dos relojes**, y dos sellos no pueden decir
cuál de los dos eventos se procesó primero (ni siquiera con un solo reloj, a resolución de milisegundo). No es un bug
del tracker ni un bug aislado del harness: es una propiedad que la evidencia no registraba.

**Definición única adoptada.** El tracker numera los mids en el orden en que los ve (`mids_seen`, desde 1). Un fill
registrado cuando se habían visto `n` mids lleva `mid_seq_at_registration = n` y sólo puede resolverse con mids
numerados > n; cada horizonte resuelto lleva `mark_seq`, el número del mid que lo resolvió. El engine guarda en
`mid_samples` **la misma muestra que acaba de consumir el tracker con el número que éste le dio**:
`(t_ms, mid, mids_seen)`. Reconstrucción: *primer mid con `mid_seq > mid_seq_at_registration` y stamp ≥ target*.
Ningún sello se compara entre colas; la regla del tracker no cambia en nada (sigue leyendo stamps para los
horizontes y el orden para "después del registro"); sólo queda registrado lo que ya hacía. `HORIZON_RULE` lo dice.

**Cambios (sólo evidencia).** `adverse_selection.py`: `Markout.mid_seq_at_registration`, `Markout.mark_seq`,
`MarkoutTracker.mids_seen`, `register` y `on_mid` los rellenan, `raw()` los exporta; `as_dict()` (la fila del
journal) intacto. `engine.py`: `mid_samples` guarda `(t, mid, seq)` después de entregar el mid al tracker.
Harness: `_first_mid_seen(..., after_seq=)` usa la numeración cuando fila y serie la traen y mantiene la regla por
sellos para evidencia anterior (las fixtures de `5ac604e` siguen pasando sin cambios); `_markout_consistency` exige
además `mark_seq > mid_seq_at_registration` y `mark_seq` no decreciente entre horizontes; `responses.mid_series`
exporta `[t, mid, seq]` y declara la regla. Ninguna tolerancia se amplió.

**Tests.** `tests/unit/mm/test_markout_raw_export.py`: numeración en orden visto, fill que recuerda cuántos había
visto, horizonte no medido sin `mark_seq`, **los dos fills de la corrida** (stamps y mids reales, empate y desfase de
9 ms: por número la serie reproduce la marca, por sellos no), la serie del engine numerada 1..N y cada marca
apuntando a su muestra, hashes dorados intactos. `tests/unit/test_mm_service_validator_markouts.py`: los dos
problemas reproducidos **palabra por palabra** sin numeración y consistentes con ella, `_first_mid_seen` por número
(empate, atraso, adelanto, sin numeración, serie mixta), campos de secuencia verificados entre sí, y la prueba
genérica: el `MarkoutTracker` real con el registro en **cada** posición de procesamiento y sellado antes, igual o
después de sus vecinos (108 combinaciones; filas resueltas, tardías y expiradas): la serie numerada reproduce todos
los horizontes medidos y la regla por sellos sola discrepa en alguna.

**Qué sigue siendo verdad de la corrida de 60 minutos.** Los 19 fills y sus 114 horizontes medidos son correctos tal
como los midió el tracker; los dos problemas eran de **reconstrucción**, no de medición: la evidencia de `9bd4b17`
no trae la numeración y su S8e no puede recalcularse a PASS desde los sellos sin suponer el orden. Si hace falta un
S8e PASS con la regla definitiva, hace falta una corrida con esta instrumentación; esa decisión queda abierta.

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

**Regla 4 — barrido al arranque (desde `7e44954`+).** Antes de la reconciliación inicial, las
órdenes abiertas en la venue con el prefijo del maker son de una corrida anterior y se cancelan
por id, se registran (`orphan_sweep`) y se elevan como incidente; no son un engagement. Lo que
la venue no cancela lo encuentra la reconciliación inicial y es sticky, como siempre. Las
órdenes ajenas no se barren. Durante la corrida la regla no aplica: una orden nuestra que la
venue lista y esta corrida no conoce sigue siendo crítica.
