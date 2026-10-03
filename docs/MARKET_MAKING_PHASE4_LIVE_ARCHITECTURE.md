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

### 10.2 Lo que esta validación no cubre

El camino completo del servicio (`LiveMarketMakerService.start_live` → reconciliación inicial
→ siembra del ledger → cotización del engine → fills → `stop`) y los endpoints
`/api/mm/live/*` contra la venue: siguen INTEGRATION TESTED con un venue falso. Mainnet: no
tocado, por regla.

