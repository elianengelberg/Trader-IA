# Market maker profesional — Reporte de la Fase 2 (datos de mercado)

**Estado: PHASE2_STATUS = PASS** (declarado por el operador el 2026-09-18 tras la segunda
prueba limpia en el VPS, sobre un directorio nuevo, con el código del commit `9362dfa`).
Resultado reportado por el operador: Binance alcanzable; snapshot real; updates de
profundidad reales; libro local SYNCED; 0 gaps inexplicados; 0 eventos perdidos en
silencio; integridad de segmentos OK; replay OK; segmento limpio reproducido; checksum
OK; `final_update_id` igual al manifiesto; digest igual al checkpoint; comparación con
bookTicker 60/60 exactas; ejecución real deshabilitada. Las cifras detalladas del JSON
(latencias, tamaños, recursos) quedan en poder del operador; este documento no las
reproduce porque no las recibió íntegras. La primera prueba real reveló dos defectos del
grabador, documentados y corregidos en la sección C.

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

### A.6 Problemas encontrados y corregidos (antes de la primera prueba real)

1. Un libro recién sincronizado sin evento posterior se reportaba obsoleto: el snapshot
   siembra el reloj de frescura.
2. Una desconexión o gap antes del primer tick de la hora no quedaba en el manifiesto.
3. `tia/mm` leía el reloj de pared: ahora recibe su reloj.
4. Sin el snapshot grabado, un segmento no podía reproducirse: ahora se graba el snapshot
   adoptado y un checkpoint al abrir cada hora, cada 300 s y al cierre.
5. Un intento de conexión fallido se contaba y se emitía como desconexión: ahora se
   distinguen conexiones, caídas e intentos fallidos.

---

## B. Validación en vivo en el VPS — realizada por el operador (segunda prueba, limpia)

Requisito para aprobar la fase. Un directorio **nuevo** (`ticks-phase2-final`) para que
los segmentos defectuosos de la primera prueba queden intactos como evidencia y no
contaminen la validación:

```
cd /home/tia/Trader-IA
git pull origin claude/algo-trading-simulation-platform-ngf7xo
docker compose -f docker-compose.prod.yml up -d --build backend

# Prueba limpia, 5 minutos, sin stall.
docker compose -f docker-compose.prod.yml exec backend python scripts/mm_market_data_check.py --minutes 5 --ticks-dir /app/data/runtime/ticks-phase2-final

# Replay independiente sobre esos segmentos y tamaño real en disco.
docker compose -f docker-compose.prod.yml exec backend python scripts/mm_replay_check.py --ticks-dir /app/data/runtime/ticks-phase2-final
docker compose -f docker-compose.prod.yml exec backend du -sh /app/data/runtime/ticks-phase2-final
```

Si la corrida cruza un cambio de hora UTC, el grabador cierra la hora vieja con un
checkpoint de cierre y abre la nueva con el mismo estado: cada archivo se reconstruye
por separado y ambos deben dar replay OK.

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
| 8 Replay | `replay[*].ok`, `criteria.8b_clean_segment_replayed` | true; además por segmento: `checksum=ok`, `gaps_in_replay == gaps_in_manifest`, `unregistered_gaps=0`, `final_matches_manifest=true`, `digest_matches_manifest=true`, `final_valid=true`, `final_state=synced` |
| 7b Manifiesto íntegro | `recorder.segments_detail[*].lines` vs `replay[*].lines` | iguales; `sealed=true`, `corrupt=false`, `replayable=true`, `first_state` no nulo, `closing_checkpoint=true` |
| 9 Datos viejos detectados | ya demostrado en la primera prueba (`stale_test`, corrida con `--inject-stall 4`) | no se repite en la prueba limpia |
| 10 Sin ejecución real | `criteria.10_real_execution_enabled` | false |
| 12 Comparación con bookTicker | `book_ticker_comparison.persistent_inconsistency`, `impossible_state` | false y false (ver B.4) |

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

### B.4 Regla de comparación con bookTicker (documentada en `tia/mm/consistency.py`)

`depth@100ms` se emite por lotes cada 100 ms; `bookTicker` en cada cambio del tope.
Muestreados en el mismo instante están en momentos distintos, y cada uno trae el id de
secuencia del venue que dice cuál es más fresco. Por eso:

- Una diferencia de ticks en una muestra es **timing**, se describe y no se juzga.
- Un tope local dentro del tope del venue en un instante (el caso real de la primera
  prueba: local 81213.99/81214.00 contra venue 81214.59/81214.60, 60 ticks, una sola
  muestra, `bookTicker` adelantado) es **timing salvo que persista**.
- Sólo dos verdictos son inconsistencia: `impossible_state` (ask local ≤ bid local, que
  el propio libro invalida) y `persistent_inconsistency` (desacuerdo mayor a 1 tick en
  ≥ 3 muestras consecutivas separadas 5 s, dos órdenes de magnitud sobre el lote de
  100 ms).
- El reporte informa además `venue_ahead_samples` (el ticker tenía un id mayor que el
  libro) y `id_lag` por muestra, para que la explicación por timing sea verificable y no
  asumida.

---

## C. Defectos encontrados por la primera prueba real y su corrección

### C.1 Segmento `20260918-18.jsonl.gz` sin snapshot ni checkpoint, declarado replayable

**Síntoma.** 50.299 líneas (35.875 bookTicker, 2.994 depth, 11.430 trades), 0 snapshots,
0 checkpoints, `replayable=true`; el replay termina en `syncing` con
`final_update_id=0`.

**Causa.** El grabador declaraba `replayable=true` por ausencia de fallos (sin gap, sin
desconexión, sin pérdida), no por presencia de lo necesario para reconstruir. Un archivo
sin estado inicial del libro pasaba la regla. Además, el formato de manifiesto anterior
al commit `c7c5bf1` nunca grababa snapshots ni checkpoints, así que cualquier segmento
de ese formato es irreconstruible por construcción; el manifiesto no llevaba versión y
no había forma de distinguirlo.

**Corrección.**
- La condición de `replayable` se decide **al cerrar el segmento, a partir de su
  contenido**: exige al menos una línea de estado (snapshot o checkpoint) y que la última
  línea sea un checkpoint; si falta cualquiera, el manifiesto lo marca con el motivo.
- Los manifiestos llevan `format=2`; uno sin versión (formato 1) se lista y se reporta
  como `legacy manifest format: the book's state was never recorded`, nunca como
  reproducible.
- Un segmento sin `closed_at` (el proceso no lo cerró) es `not sealed` y no es
  reproducible hasta cerrarse.
- En el cambio de hora, la hora vieja recibe un **checkpoint de cierre** y la nueva abre
  con el mismo estado, así cada archivo se reconstruye y se verifica por separado.
- El manifiesto registra `first_state_kind`, `first_state_line`, `closing_checkpoint`.

### C.2 `20260918-19.jsonl.gz`: 114.721 líneas reales, 56.803 según el manifiesto

**Síntoma.** Checksum OK, conteo de líneas distinto; el contenido se reconstruye y el
digest coincide con el checkpoint.

**Causa (reproducida offline).** El grabador abría el archivo de la hora con
`gzip.open(path, "ab")`: **append**. Una segunda sesión en la misma hora (otra corrida
del script, o un reinicio) agregaba sus líneas al archivo existente y creaba un manifiesto
nuevo que contaba sólo las suyas; el sha256 se calculaba al cierre sobre el archivo
entero, por eso el checksum "pasaba" mientras el conteo fallaba. 114.721 − 56.803 =
57.918 líneas pertenecían a la sesión anterior. No hubo doble apertura dentro de un
proceso ni concurrencia entre flush y cierre: fue reanudación sobre un archivo existente.

**Corrección.**
- **Nunca se anexa.** El archivo se abre en modo exclusivo (`"xb"`); si `<hora>.jsonl.gz`
  existe, la sesión escribe `<hora>.partNN.jsonl.gz` con su propio manifiesto. Un
  manifiesto describe exactamente un archivo escrito por exactamente una sesión.
- **Un escritor por directorio.** Lock exclusivo (`flock`) sobre `.recorder.lock`; un
  segundo grabador sobre el mismo directorio lanza `RecorderBusyError` y el script sale
  con `REFUSED` en vez de intercalar.
- `segments()` ordena por hora y parte.

**Tests de regresión** (`tests/unit/mm/test_recorder_integrity.py`): segunda sesión en la
misma hora → archivo `part02`, ambos manifiestos con el conteo exacto de su archivo y
replay OK; escritor concurrente rechazado; segmento sin estado inicial nunca
reproducible; segmento sin checkpoint de cierre no reproducible; cambio de hora con
checkpoint de cierre y de apertura y replay OK de ambos archivos con digest coincidente;
manifiesto legacy reportado; segmento sin sellar reportado; reglas de comparación con
bookTicker (una muestra dentro del tope del venue es timing; tres consecutivas es
persistente; libro local cruzado es imposible).

### C.3 Comprobación offline del script completo tras la corrección (sintético, rotulado)

Dos ejecuciones del script en la misma hora sobre el mismo directorio: la segunda
concurrente fue rechazada (`REFUSED … refusing to interleave`); la secuencial produjo
`20260918-19.part02.jsonl.gz`; `mm_replay_check.py` reconstruyó ambos archivos: checksum
OK, 402 líneas = 402 en el manifiesto, `final_matches_manifest=True`,
`digest_matches_manifest=True`. Estos números describen el harness, no Binance.
