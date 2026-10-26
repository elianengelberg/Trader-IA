# Bloqueantes operativos de la candidata v3 — documentados, NO corregidos en esta rama

Cada bloqueante tiene su referencia de código y las pruebas que harían falta para cerrarlo.
- Las referencias son a esta rama, relativas a `packages/tia/src/tia/`.
- Las pruebas que hoy **observan** cada defecto están en el paquete de evidencia de la revisión independiente (`revisores/…`; ver `INFORME_REVISION_INDEPENDIENTE_V3.md`). No forman parte de `tests/` a propósito: pasan **porque** el defecto existe.
- **Criterio de cierre:** la prueba que observa el defecto pasa a fallar y una prueba nueva fija el comportamiento correcto; las dos se suman a `tests/`.

## 1. Conciliación de fills de stops, incluidas las ejecuciones tardías (crítico)

**Defecto.**
- Los fills solo se arman desde la respuesta del envío (`data/providers/binance_live.py:716-719`).
- `GET /api/v3/order` no devuelve `fills`, según la documentación oficial; los fills con su comisión están en `GET /api/v3/myTrades`.
- `runtime/live.py` nunca llama a `get_fills`/`myTrades`.
- Un stop FILLED en el venue se marca «failed … filled, unfilled» (`runtime/live.py:3874-3881`):
  - el round trip no se cierra;
  - el P&L no se registra;
  - en live, la conciliación lo toma como un retiro.
- Lo mismo con una limit llenada después. Y con la respuesta perdida de una compra: se resuelve FILLED sin fills, se cuenta como rechazada y la posición queda sin rastrear (`runtime/live.py:2641-2659`).

**Pruebas necesarias:**
- Una orden terminal con `executedQty > 0` y sin `fills` dispara la lectura de `myTrades` por `orderId`, y los fills se registran **una sola vez** (idempotencia por `tradeId`).
- Un stop-out cierra el round trip, registra el P&L realizado y lo cuenta para el límite de pérdida diario.
- Fills parciales repartidos en varias lecturas.
- Si `myTrades` falla, no se ve nada: bloqueo de entradas más un incidente, y nunca «sin fills» como si no hubiera pasado nada.
- Reinicio entre el fill y su registro.
- Después, validar en Testnet: un stop que salta y queda registrado.

## 2. Reemplazo seguro del stop sin cancelar la protección válida (crítico)

**Defecto.**
- `_sync_protective_stop` cancela el stop vigente antes de enviar el reemplazo (`runtime/live.py:3672-3677`).
- Si el venue rechaza el nuevo con `-2010` («Order would trigger immediately.»), la posición queda sin stop aunque el nivel viejo fuera válido.
- El nivel se recorta contra el cierre de la vela cuando se calcula (`execution/exits.py:122-124`), pero no contra el último precio cuando se envía.
- No hay salida a mercado y los reintentos no tienen tope.
- El bloqueo de entradas (`runtime/live.py:2093`) llega antes que el cierre por reversión (`:2137`) y lo suprime.
- El motor paper llena ese stop en la vela siguiente (`execution/paper.py:444-456`): paper y live divergen.

**Pruebas necesarias:**
- Ajuste rechazado con `-2010`: el stop anterior sigue en el venue, o la política elegida se aplica de forma explícita y queda registrada.
- El reemplazo se confirma antes de cancelar lo anterior (o se usa `cancelReplace` con el modo adecuado), sin quedar nunca con cero stops ni con dos.
- El nivel se valida contra el último precio antes de enviar.
- Tope de reintentos y política de salida decidida por el dueño (era D25).
- El bloqueo de entradas no suprime las salidas.
- Paridad paper/live en el mismo escenario.

## 3. Estados sin stop, residuos y comisiones en monedas distintas de USD (crítico)

**Defecto.**
- Cuando la tenencia difiere de lo registrado en más de un lote, se detiene antes de poner el stop (`runtime/live.py:3410-3423`). Pasa con la comisión cobrada en BTC.
- El estado de protección queda en «none», el mismo valor que significa «sin posición».
- `_track_round_trip` espera vender la cantidad bruta (`runtime/live.py:4331`): con polvo, el round trip nunca se cierra.
- La restauración exige igualdad exacta, con tolerancia de 1e-9 (`runtime/live.py:917-923`).
- `fee_asset` no se lee en `runtime/live.py`: las comisiones en BTC o BNB se registran como si fueran USD.
- El primer stop recién se coloca al cierre de la vela siguiente a la entrada.

**Pruebas necesarias:**
- `test_d26_a_buy_that_paid_its_fee_in_the_base_asset_is_still_protected` deja de ser `xfail`. Además, el xfail actual debería fijar su modo de falla (`raises=` o mensaje).
- Comisión por fill desde `myTrades` (`commission`, `commissionAsset`), valuada en quote con una fuente declarada; si no se puede valuar, bloqueo **por fill**, no un solo chequeo al armar.
- Política de polvo, decidida por el dueño: umbral y reconocimiento.
- Un estado «posición sin protección» distinto de «sin posición», con incidente.
- Un tope de tiempo entre la entrada y el primer stop.

## 4. Exclusión mutua entre el market maker live y la sesión live (crítico si se habilitan los dos)

**Defecto.**
- `start_mm_live` solo comprueba `self._mm_live.is_running` (`api/state.py:1790`). Asigna `_mm_live` recién en `api/state.py:1878`, sin lock: dos arranques simultáneos crean dos makers.
- `arm_live` y paper no miran al market maker.
- El slot de H11 es por base de datos, no por cuenta del venue.
- `emergency_flatten` vende **todos** los activos de la cuenta, no solo el símbolo de la sesión (`runtime/live.py:1719-1751`, `data/providers/binance_live.py:530-548`).
- El barrido de huérfanos del market maker cancela las cotizaciones de otro maker vivo.

**Pruebas necesarias:**
- Con una sesión live corriendo, `start_mm_live` se rechaza.
- Con el market maker corriendo, `arm_live` se rechaza.
- Dos `start_mm_live` concurrentes: uno se rechaza.
- Un lock por cuenta del venue entre procesos, con procesos reales.
- `emergency_flatten` limitado al símbolo de la sesión.
- La decisión de producto sobre si pueden coexistir, y si sí, con cuentas separadas.

## 5. Apagado controlado y recuperación ante fallas de PostgreSQL (alto)

**Defecto.**
- `AppState.shutdown` detiene todo en serie y en este orden: escenario, sesión, market maker, vaciado (`api/state.py:202-258`, `337-357`). Las esperas con tope suman unos 55 s.
- `_mark_stopping` escribe en la base sin tope de tiempo (`api/state.py:286-289`): con la base particionada, el apagado se colgó hasta que lo cortó la medición, a los 40 s.
- Ningún compose fija `stop_grace_period` ni `init`.
- El tope de 5 s (`api/main.py`) solo acota la espera de conexiones HTTP.
- **H11:**
  - la pérdida del lock se detecta recién en el heartbeat siguiente (cada 30 s, `runtime/live.py:735`);
  - ante una partición de red, el backend retiene el lock hasta que vence el keepalive TCP;
  - la recuperación al arrancar sella la fila de otra sesión antes de reclamar el slot (`api/state.py:3101` antes de `3113`);
  - el `equity` de una corrida terminada se escribe con el `run_id` de la siguiente (`api/state.py:976-984`).

**Pruebas necesarias:**
- Apagado con la base particionada: termina dentro de un tope y deja un registro honesto.
- `docker stop` real con el compose de producción, el stream abierto y el escenario en curso.
- Orden de apagado: primero lo que toca dinero.
- `arm_live` justo después de perder el lock.
- Pruebas que maten los mutantes X-H11-2 (una sesión que termina sola no libera el slot), X-H11-3 (el heartbeat no verifica la exclusión) y X-H11-7 (`arm_live` no reclama el slot).
- `equity` atribuida a su propia corrida.

## Fuera de esta rama

Ninguno de estos cambios se hizo acá. El dueño tiene que decidir y autorizar:
- las políticas de D25, D26, el polvo, la coexistencia del market maker y la sesión, y el plazo y el orden del apagado;
- su implementación.
