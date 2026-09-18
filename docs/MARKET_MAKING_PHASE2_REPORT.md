# Market maker profesional — Reporte de la Fase 2 (datos de mercado)

**Estado: PHASE2_STATUS = PENDING.** La infraestructura y las pruebas están completas y
verificadas 9/9, pero la Fase 2 **no está aprobada**: la aprobación exige evidencia real
del VPS y el entorno donde se construyó este código no alcanza Binance (el proxy corta la
conexión; comprobado el 2026-09-18). La sección B dice exactamente qué correr y qué
mirar. Nada de la sección A cuenta como evidencia de funcionamiento real.

Alcance de la fase: **solo datos de mercado**. No hay fair value, quoting, inventario,
modelo de fills ni rentabilidad. Ningún módulo de `tia/mm` puede construir un proveedor
de ejecución ni enviar una orden. `TIA_MM__ENABLED=false`, `TIA_MM__REAL_MONEY=false`
(esta última bandera no la lee ningún módulo de ejecución; no tiene efecto).

---

## A. Validación offline / sintética (entorno de construcción)

Fecha: 2026-09-18, 17:00–19:20 UTC. Branch `claude/algo-trading-simulation-platform-ngf7xo`.

### A.1 Reglas del proyecto y cómo se cumplieron

| Regla | Cumplimiento |
|---|---|
| No dinero real | Banderas apagadas por defecto; `real_money` no tiene efecto por construcción. |
| No eliminar ni reemplazar funcionalidad | Sólo campos opcionales con default en `TradePrint`/`OrderBook`, métodos nuevos en el proveedor REST, sección nueva de configuración, endpoint nuevo de solo lectura. Estrategias, runtime 24/7 y cuenta paper intactos. |
| No aflojar las 27 verificaciones ni la RiskEngine | No se tocaron. |
| No inventar datos | Todo número de esta sección sale de tests o de corridas sintéticas rotuladas. |
| Cuenta simulada separada | Decisión confirmada; se implementa en Fases 11–13. Hoy no existe ninguna cuenta del market maker. |
| Grabación a disco por lotes | `TickRecorder`: segmentos horarios `jsonl.gz` + manifiesto con sha256. |
| Comisiones provisionales | `maker_fee_bps=10.0`, estado `PROVISIONAL_COST_ASSUMPTION`, escenarios asumido / verificado / adverso. |

### A.2 Procedimiento de Binance implementado (verificado contra la documentación vigente)

1. Abrir `<símbolo>@depth@100ms` y bufferear los eventos.
2. `GET /api/v3/depth?symbol=…&limit=N` (N ≤ 5000) → `lastUpdateId`.
3. Si `lastUpdateId` < `U` del primer evento bufferado → snapshot viejo → pedir otro.
4. Descartar eventos con `u ≤ lastUpdateId`.
5. El primer evento restante debe cumplir `U ≤ lastUpdateId + 1 ≤ u`; si no, pedir otro.
6. Cada evento posterior: `U > id_local + 1` ⇒ gap ⇒ libro inválido ⇒ volver a 1.
   Cantidad `0` elimina el nivel; las cantidades son absolutas.

Tres streams por una sola conexión combinada
(`wss://stream.binance.com:9443/stream?streams=btcusdt@depth@100ms/btcusdt@trade/btcusdt@bookTicker`).
`bookTicker` en Spot no trae `E`: su latencia **no se mide ni se inventa**. Se mide en
`depth` (`E`) y en `trade` (`E`, `T`).

### A.3 Componentes

| Archivo | Función |
|---|---|
| `tia/mm/streams.py` | Conexión combinada, parseo, reconexión con backoff; contadores separados de conexiones logradas, caídas de una conexión que estaba arriba, intentos fallidos; duración de la conexión actual y la más larga; latencias p50/p95/p99/min/max. |
| `tia/mm/order_book.py` | `LocalOrderBook` (EMPTY → SYNCING → SYNCED → OUT_OF_SYNC), procedimiento A.2, verificación de libro cruzado y spread implausible, métricas, primer/último update aplicado, `levels()` y `digest()` para checkpoints. |
| `tia/mm/recorder.py` | Segmentos horarios con manifiesto: líneas, bytes crudos y comprimidos, sha256, ids, eventos por tipo, snapshots y checkpoints, eventos perdidos, desconexiones, gaps, faltas inyectadas, `replayable`, `corrupt`. Cada hora abre con un checkpoint del libro; el snapshot REST se graba en el punto exacto donde la sincronización lo adoptó. Retención por días y tope de bytes. `verify()` recalcula checksum y conteo. |
| `tia/mm/market_data.py` | `MarketDataService`: orquesta stream + snapshot + grabador; `usable` sólo con libro válido, stream conectado y dato con menos de `max_data_age_s`. Checkpoint periódico (300 s) y al cierre. Cuenta episodios de silencio mayores al límite (`stale_episodes`, `max_silence_ms`) y la latencia de procesamiento local en µs. `hold(seconds)` ignora eventos a propósito para validar la detección de datos viejos; queda escrito en el manifiesto como falta inyectada. |
| `tia/mm/replay.py` | `replay_segment`: lee el archivo completo, verifica checksum y conteo contra el manifiesto, reconstruye el libro con el mismo código del servicio, compara cada checkpoint nivel por nivel y por digest, cuenta gaps no registrados, cortes de secuencia, saltos de id de trade, libros cruzados, y compara el estado final con el manifiesto. |
| `scripts/mm_market_data_check.py` | Corrida en vivo de N minutos: reporte con las secciones de aceptación (Binance/WebSocket, libro, latencia, grabador, recursos del host, comparación con bookTicker, prueba de datos viejos, replay de los segmentos recién escritos, criterios). |
| `scripts/mm_replay_check.py` | Replay de un directorio o de un segmento. |
| `tia/core/config.py`, `tia/api/*`, compose | `MarketMakingConfig` (`TIA_MM__*`), `GET /api/mm/market` (solo lectura). |

`tia/mm` está clasificado en el camino de decisión (`tests/unit/test_scope_boundary.py`):
recibe su reloj, no lee el reloj de pared.

### A.4 Tests (todos sintéticos)

`tests/unit/mm`: **32** tests. Sincronización completa, snapshot viejo rechazado, gap ⇒
invalidación y reconstrucción, solapamientos, cantidad cero, libro cruzado, buffer
acotado, percentiles, parseo, dispatch, reconexión, lotes y manifiesto, checksum,
corrupción, retención, desconexión antes del primer tick, servicio end-to-end, **replay
de un segmento grabado hasta el libro grabado** (checkpoint comparado nivel por nivel y
por digest), **manipulación del archivo detectada** (checksum y gap no registrado),
segmento marcado rechazado salvo `allow_flagged`, **stall inyectado ⇒ dato viejo ⇒ gap ⇒
resync** con el manifiesto marcado, checkpoint como primera línea de cada hora, conteo
separado de caídas e intentos fallidos. Más un test de integración del endpoint.

Verificación completa del repositorio: lint, unit (867), integration (145), property
(27), failure (12), e2e (8), typecheck, build y smoke: **9/9 PASS**.

### A.5 Corrida sintética del script de verificación (no es evidencia real)

El script completo se ejecutó offline con un feed sintético (conector y snapshot
parcheados) para comprobar que todas las secciones del reporte se producen sin error.
Resultado (30 s, stall de 3 s inyectado): libro SYNCED, 1 gap explicado por el stall,
`stale_detected_after_s=2.0` con motivo `data 2.1s old, over 2.0s`, resync 1,5 s
después, segmento íntegro, replay OK con checkpoint coincidente. **Estos números
describen el harness, no Binance.**

### A.6 Problemas encontrados y corregidos

1. Un libro recién sincronizado sin evento posterior se reportaba obsoleto: el snapshot
   siembra el reloj de frescura.
2. Una desconexión o gap antes del primer tick de la hora no quedaba en el manifiesto.
3. `tia/mm` leía el reloj de pared: ahora recibe su reloj.
4. Sin el snapshot grabado, un segmento no podía reproducirse: ahora se graba el snapshot
   adoptado y un checkpoint al abrir cada hora, cada 300 s y al cierre.
5. Un intento de conexión fallido se contaba y se emitía como desconexión: ahora se
   distinguen conexiones, caídas e intentos fallidos.

---

## B. Validación en vivo en el VPS — PENDIENTE

Requisito para aprobar la fase. Dos corridas, dentro del contenedor del backend:

```
cd /home/tia/Trader-IA
git pull origin claude/algo-trading-simulation-platform-ngf7xo
docker compose -f docker-compose.prod.yml up -d --build backend

# Corrida 1: limpia, 5 minutos. Produce el segmento que debe ser replayable=true.
docker compose -f docker-compose.prod.yml exec backend python scripts/mm_market_data_check.py --minutes 5 --ticks-dir /app/data/runtime/ticks-check

# Corrida 2: 2 minutos con un stall de 4 s inyectado. Prueba la detección de datos viejos.
docker compose -f docker-compose.prod.yml exec backend python scripts/mm_market_data_check.py --minutes 2 --inject-stall 4 --ticks-dir /app/data/runtime/ticks-stall

# Replay independiente del segmento limpio y tamaño real en disco.
docker compose -f docker-compose.prod.yml exec backend python scripts/mm_replay_check.py --ticks-dir /app/data/runtime/ticks-check
docker compose -f docker-compose.prod.yml exec backend du -sh /app/data/runtime/ticks-check /app/data/runtime/ticks-stall
```

Nota: si la corrida cruza un cambio de hora UTC, el grabador abre un segundo segmento;
el primero se cierra con checksum y el segundo arranca con un checkpoint del libro.

### B.1 Qué debe verse en el JSON final para marcar PASS

| Criterio | Campo del reporte | Condición |
|---|---|---|
| 1 Binance alcanzable | `binance_websocket.connections` | ≥ 1 |
| 2 Snapshot real | `binance_websocket.rest_snapshots_fetched` | ≥ 1 |
| 3 Updates reales | `binance_websocket.depth_updates_received` | > 0 |
| 4 Libro SYNCED | `criteria.4_book_reached_synced` | true |
| 5 Sin gaps inexplicados | `order_book.gaps_unexplained` | 0 (gaps − desconexiones − stalls inyectados) |
| 6 Sin pérdida silenciosa | `recorder.events_dropped`, `binance_websocket.events_dropped_by_subscribers` | 0 y 0 |
| 7 Segmentos íntegros | `recorder.segments_detail[*].verify.ok` | true |
| 8 Replay | `replay[*].ok`, `criteria.8b_clean_segment_replayed` (corrida 1) | true |
| 9 Datos viejos detectados | `stale_test.stale_detected_after_s` (corrida 2) | no nulo, con `gap_detected_after_s` y `usable_again_after_s` |
| 10 Sin ejecución real | `criteria.10_real_execution_enabled` | false |
| Comparación con bookTicker | `book_ticker_comparison.crossed_vs_venue`, `persistent_inconsistency` | 0 y false; diferencias de 1 tick son timing entre streams |

### B.2 Cifras a transcribir en esta sección cuando existan

Binance/WebSocket (conexiones, caídas, intentos fallidos, duración más larga, streams,
updates, trades, snapshots, errores de parseo, eventos descartados) · Libro (snapshot
`lastUpdateId`, primer y último update aplicado, updates procesados, gaps,
invalidaciones, reconstrucciones, estado final, best bid/ask, spread, libros cruzados,
episodios stale) · Latencia (exchange→local depth y trade: p50/p95/p99/min/max;
procesamiento local en µs; bookTicker: NO MEDIDO por falta de timestamp del exchange) ·
Grabador (segmentos, duración, eventos por segmento, bytes crudos y comprimidos, ratio,
sha256, corrupción, eventos perdidos, gaps, replayable) · Recursos (CPU del proceso,
RSS, memoria del host, loadavg, disco libre, crecimiento del directorio de ticks en
MB/hora) · Replay (checksum, snapshots aplicados, checkpoints comparados, mismatches,
gaps no registrados, estado final, coincidencia con el manifiesto).

### B.3 Limitaciones conocidas

- La latencia exchange→local incluye el desfase de reloj entre el host y Binance; no se
  corrige ni se estima.
- `bookTicker` Spot no trae timestamp del exchange: sin latencia para ese stream.
- La comparación con `bookTicker` es entre streams distintos: se reportan diferencias en
  ticks y sólo cuenta como inconsistencia un libro local cruzado contra el venue o un
  desacuerdo persistente (≥ 3 muestras consecutivas de 5 s).
- Un gap por reconexión o por stall inyectado se considera explicado sólo si fue
  detectado, el libro se invalidó, hubo resync, quedó en el manifiesto y `usable` fue
  false mientras tanto; el reporte lo muestra en `stale_test.timeline` y en los
  manifiestos.
- Los segmentos con gap, desconexión o falta inyectada quedan `replayable=false` por la
  decisión confirmada (2); el replay igual puede correrlos con `--allow-flagged` y
  reproduce el mismo gap y el mismo resync porque el snapshot está en la cinta.
