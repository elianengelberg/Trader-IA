# Market maker profesional — Reporte de la Fase 2 (datos de mercado)

Commit: `94ac7af` en `claude/algo-trading-simulation-platform-ngf7xo`. Verificación: 9/9.

Alcance de la fase: **solo datos de mercado**. No hay fair value, quoting, inventario,
modelo de fills ni cálculo de rentabilidad. Ningún módulo de `tia/mm` puede construir
un proveedor de ejecución ni enviar una orden.

## 1. Reglas del proyecto y cómo se cumplieron

| Regla | Cumplimiento |
|---|---|
| No dinero real | `TIA_MM__ENABLED=false` y `TIA_MM__REAL_MONEY=false` por defecto. La segunda bandera no es leída por ningún módulo de ejecución: aunque se ponga en `true`, no hace nada. |
| No eliminar ni reemplazar funcionalidad | Sólo se agregaron campos opcionales con default (`TradePrint.trade_id/event_time/is_buyer_maker`, `OrderBook.last_update_id`), dos métodos nuevos en el proveedor REST, una sección nueva de configuración, un endpoint nuevo de solo lectura. Las estrategias, el runtime 24/7 y la cuenta paper no cambiaron. |
| No aflojar las 27 verificaciones | No se tocó `tia/live` ni la puerta de dinero real. |
| No inventar datos | Este entorno no alcanza Binance (el proxy corta la conexión). Las cifras en vivo quedan **pendientes del VPS**; el ejemplo y el benchmark de abajo usan eventos sintéticos y están rotulados como tales. |
| Cuenta simulada separada | Decisión confirmada; se implementa en la Fase 11–13. En esta fase no existe ninguna cuenta del market maker. |
| Grabación a disco por lotes, no Postgres | `TickRecorder`: segmentos horarios `jsonl.gz`, escritura por lotes, manifiesto con checksum. |
| Comisiones provisionales | `maker_fee_bps=10.0` con estado `PROVISIONAL_COST_ASSUMPTION`; escenarios asumido / verificado / adverso, configurables por variables de entorno. |

## 2. Verificación de la API de Binance antes de implementar

Implementado según la documentación vigente de Binance Spot ("How to manage a local
order book correctly"), no según supuestos:

1. Abrir el stream `<símbolo>@depth@100ms` y **bufferear** los eventos.
2. Pedir `GET /api/v3/depth?symbol=…&limit=N` (N ≤ 5000) y leer `lastUpdateId`.
3. Si `lastUpdateId` es menor que la `U` del primer evento bufferado, el snapshot es viejo:
   pedir otro.
4. Descartar todo evento con `u ≤ lastUpdateId`.
5. El primer evento restante debe cumplir `U ≤ lastUpdateId + 1 ≤ u`. Si no, pedir otro
   snapshot.
6. Para cada evento posterior: si `U > id_local + 1` hay un **gap** ⇒ libro inválido,
   volver a 1. Cantidad `0` elimina el nivel; las cantidades son absolutas.

Los tres streams van por **una sola conexión combinada**
(`wss://stream.binance.com:9443/stream?streams=btcusdt@depth@100ms/btcusdt@trade/btcusdt@bookTicker`).
`bookTicker` en Spot no trae `E`, así que su latencia no se mide; sí se mide en `depth`
(`E`) y en `trade` (`E` y `T`).

## 3. Componentes construidos

| Archivo | Líneas | Función |
|---|---|---|
| `tia/mm/streams.py` | 330 | Conexión combinada, parseo de los tres eventos, reconexión con backoff, latencias p50/p95/p99, contadores (mensajes, parse errors, eventos descartados por suscriptores que fallan). |
| `tia/mm/order_book.py` | 412 | `LocalOrderBook` con estados EMPTY → SYNCING → SYNCED → OUT_OF_SYNC, buffer acotado, procedimiento del §2, verificación de libro cruzado y spread implausible, métricas (`updates_applied`, `updates_ignored_old`, `gaps`, `rebuilds`, `snapshots_rejected_stale`, `crossed_books`, `invalidations`, `max_buffer`), lecturas: mejor bid/ask, top N, mid, spread, profundidad, imbalance, microprice, mid ponderado, impacto de precio, concentración. |
| `tia/mm/latency.py` | 62 | Percentiles nearest-rank sobre ventana deslizante. |
| `tia/mm/recorder.py` | 394 | Segmentos horarios `<símbolo>/<YYYYMMDD-HH>.jsonl.gz` + `.manifest.json` (líneas, bytes, sha256, primer/último id, eventos perdidos, desconexiones, gaps, `replayable`, `corrupt`). Retención por días y tope de bytes (evicción del más viejo). `verify()` recalcula checksum y conteo. Buffer lleno ⇒ descarta y cuenta, nunca bloquea. |
| `tia/mm/market_data.py` | 213 | `MarketDataService`: orquesta stream + snapshot + grabador; `usable` sólo con libro válido, stream conectado y dato fresco (`max_data_age_s`). |
| `tia/data/providers/binance_public.py` | +88 | `depth_snapshot` (con `lastUpdateId`, límite 5000) y `agg_trades`. |
| `tia/core/config.py` | +42 | `MarketMakingConfig` (`TIA_MM__*`). |
| `tia/api/state.py`, `app.py` | +71 | Arranque/cierre del servicio cuando está habilitado; `GET /api/mm/market` (solo lectura, autenticado). |
| `scripts/mm_market_data_check.py` | 134 | Verificación en vivo: corre N minutos y emite el reporte de integridad. |
| `docker-compose.prod.yml`, `.env.example` | +21 | Variables `TIA_MM__*`, todas apagadas por defecto. |

`tia/mm` está clasificado en el **camino de decisión** (`tests/unit/test_scope_boundary.py`):
no lee el reloj de pared, recibe su reloj. Es la condición para que el replay de la
Fase 12 sea reproducible.

## 4. Tests

| Suite | Resultado |
|---|---|
| `tests/unit/mm` (nuevos) | 24 passed |
| `tests/unit` (total) | 859 passed |
| `tests/integration` (incluye el test del endpoint) | 145 passed |
| `tests/property` | 27 passed |
| `tests/failure` | 12 passed |
| `tests/e2e` | 8 passed |
| Lint, typecheck y build del frontend, smoke | PASS |

Lo que cubren los 24 tests nuevos: procedimiento de sincronización completo, snapshot
viejo rechazado, gap ⇒ invalidación y reconstrucción, eventos solapados y viejos,
cantidad cero elimina nivel, libro cruzado invalida, buffer acotado, percentiles,
parseo de los tres eventos, dispatch y latencias, suscriptor que falla no tumba el
stream, reconexión, lotes y manifiesto del grabador, checksum, detección de corrupción,
retención y evicción, codificación por tipo de evento, desconexión antes del primer tick,
servicio end-to-end (sync, gap con rebuild y marca en la grabación, desconexión con
resync, dato viejo ⇒ no usable con motivo), endpoint apagado por defecto y
`real_money=false`.

## 5. Ejemplo de reconstrucción del libro (eventos sintéticos, rotulado)

Corrida offline del mismo código con eventos guionados. **No son datos de mercado.**

```
1) stream abierto, eventos bufferados ANTES del snapshot
   REST snapshot #1: lastUpdateId=1000100
   evento U=1000090..u=1000095  -> descartado (u <= lastUpdateId)
   evento U=1000096..u=1000101  -> aplicado (cubre lastUpdateId+1)
   evento U=1000102..u=1000104  -> aplicado (elimina 115000.20, agrega 115000.30)
   estado=synced update_id=1000104 best_bid=(115000.1, 0.8) best_ask=(115000.3, 0.6)
   metrics: updates_applied=2 updates_ignored_old=1 gaps=0 rebuilds=1
2) trade + update en secuencia
   update_id=1000107 microprice=115000.21 imbalance(3)=-0.119
3) GAP: llega U=1000120 con el libro en 1000107
   gaps=1 invalidations=1 -> snapshot #2 lastUpdateId=1000220 -> reconstruido, rebuilds=2
4) desconexión y reconexión
   reconexiones=1 -> snapshot #3 -> synced, resyncs=3
5) GET /api/mm/market: usable=true, resync_failures=0
6) disco: 20250918-17.jsonl.gz, 6 líneas, 295 bytes, sha256 verificado
   manifiesto: book_gaps=1 disconnects=1 replayable=false
   motivos: ["order book reported a sequence gap", "stream disconnected during the hour"]
```

Formato de una línea grabada (depth): `{"k":"depth","R":<recibido_ms>,"E":<evento_ms>,"U":…,"u":…,"b":[[precio,cantidad]…],"a":[…]}`.

## 6. Benchmark sintético de capacidad (no es una medición de mercado)

| Medición | Resultado |
|---|---|
| Libro local: 200.000 updates con 4,19 M cambios de nivel | 62.376 updates/s, 16 µs por update, todos válidos |
| Lecturas best_bid + best_ask + microprice + imbalance(5) | 127 µs el conjunto |
| Grabador: 100.000 eventos depth | 8.758 eventos/s, 10,46 MB comprimido por 41,86 MB crudo (4×), 105 bytes/evento, 0 perdidos |

Binance envía del orden de 10 eventos `depth@100ms` por segundo más decenas de trades;
el margen es de dos órdenes de magnitud. Los eventos reales de BTCUSDT traen más
cambios de nivel que los sintéticos, así que el tamaño real por evento será mayor: el
número correcto sale del VPS.

## 7. Pendiente del VPS (no medible desde el entorno de construcción)

Updates procesados, gaps, reconstrucciones, eventos perdidos, latencia observada,
CPU/RAM/disco y tamaño real de los archivos se obtienen con:

```
cd /home/tia/Trader-IA && git pull origin claude/algo-trading-simulation-platform-ngf7xo && docker compose -f docker-compose.prod.yml up -d --build backend
docker compose -f docker-compose.prod.yml exec backend python scripts/mm_market_data_check.py --minutes 5 --ticks-dir /app/data/runtime/ticks-check
```

El script imprime cada 10 s el estado y al final el reporte JSON con: estado y
`update_id` del libro, 10 niveles por lado, spread, microprice, imbalance, métricas del
libro, contadores del stream, latencias p50/p95/p99, contadores de sync, comparación del
libro local contra `bookTicker` (muestras y desacuerdos), CPU y RSS, estado del grabador y
los archivos con su tamaño. Criterio de avance: 0 desacuerdos con `bookTicker`, gaps
explicados por reconexiones, 0 eventos perdidos en el grabador.

## 8. Problemas encontrados en la fase y corregidos

1. Un libro recién sincronizado sin evento posterior se reportaba como obsoleto: el
   snapshot REST ahora siembra el reloj de frescura.
2. Una desconexión o gap antes del primer tick de la hora no quedaba en el manifiesto:
   ahora abre el segmento y lo marca no reproducible.
3. `tia/mm` leía el reloj de pared (detectado por el test de frontera de alcance): ahora
   recibe su reloj vía `SystemClock`.

## 9. Confirmaciones

- Ningún dato fue inventado: los únicos números de esta fase salen de tests, de una
  corrida sintética rotulada y de un benchmark sintético rotulado.
- No se habilitó ejecución real: no existe proveedor de ejecución en `tia/mm`; las
  banderas están apagadas y `real_money` no tiene efecto por construcción.
- La sesión 24/7, sus estrategias, la cuenta paper de $10.000 y la puerta de dinero real
  siguen exactamente igual.

## 10. Siguiente paso

Fase 3 (lectura del libro: profundidad, imbalances, microprice) ya está cubierta en
`LocalOrderBook`; se formaliza con sus tests al arrancar la Fase 4, `OrderFlowEngine`,
una vez validadas las cifras del VPS.
