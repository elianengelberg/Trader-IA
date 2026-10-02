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

## 9. Lo que sólo Binance Testnet puede confirmar

Formato exacto de `exchangeInfo.filters` (`NOTIONAL` vs `MIN_NOTIONAL`), `orderTypes` con `LIMIT_MAKER`;
rechazo -2010 y su `msg`; que `timeInForce` efectivamente sea rechazado para `LIMIT_MAKER`;
`commissionAsset` en `myTrades` y si la cuenta paga en BNB; latencia real de submit/cancel y
cuántos ciclos de requote cuesta el cancel/replace estricto; comportamiento de `openOrders`
con órdenes de otras sesiones; `-2011` al cancelar una orden ya cerrada; que `myTrades` con
`limit` devuelva los más recientes; el límite de 36 caracteres y el charset de
`newClientOrderId`.
