# Adaptador de Binance: protección de posiciones (tratado aparte de R19 y de la guarda 05)

**Clasificación:** **DEFECTO REPRODUCIDO en el adaptador** con una sonda sintética, sin red. **No lo resuelve ningún parche** de esta misión ni de v3r3: 01, 02v3, 03, 04, 05v2, 06 y 07 no tocan `binance_live.py` ni `runtime/live.py`. No se corrigió.

## Hechos (sonda ejecutada)
Sonda: `herramientas/sonda_binance_stop.py` (`c3dd8fcf…`). Resultados en `sonda_base.json`, `sonda_final.json` y `resumen_sonda.txt`. Condiciones: transporte simulado (`httpx.MockTransport`), modo testnet (`simulated=True`), sin token de activación y sin credenciales reales.

| Comprobación | Base `72ffae5` | Árbol final (A + 05v2 + 03 + 04 + 06) |
|---|---|---|
| El adaptador declara `supports_stop_orders` | `True` | `True` |
| Una orden con la forma del stop protector del vivo (`OrderType.STOP`, `reduce_only=True`, GTC, `stop_price`) | `ExecutionError`: «order type stop is not supported by this adapter» | Igual |
| Pedidos que llegan al transporte con esa orden | 0 | 0 |
| Control: una orden MARKET con el mismo adaptador | 1 pedido, se llena | Igual |

**Causa en el código:** `_ORDER_TYPE_MAP` (`binance_live.py:76-83`) traduce MARKET, LIMIT, LIMIT_MAKER, STOP_LIMIT y TAKE_PROFIT. **No traduce `OrderType.STOP`.** Aun así, las capacidades del adaptador declaran `supports_stop_orders=True` (`binance_live.py:139`).

## Consecuencia en el vivo (por inspección; no ejecutada de punta a punta)
- `LiveRuntime` usa este adaptador como ejecución cuando opera contra Binance, tanto en testnet como en el venue real (`api/state.py:2288`).
- El stop protector se construye con `order_type=OrderType.STOP` (`live.py:3450` y `3457`).
- La excepción se atrapa en `live.py:3465-3466`: se registra el aviso `protective_stop_failed` y la función devuelve sin más.
- En ese camino **no** se incrementa `unprotected_positions`. Ese contador solo cuenta las entradas **sin** nivel de stop (`live.py:3411-3417`).
- En cada barra se vuelve a intentar y vuelve a fallar.
- **El vivo no tiene un stop por barra en software:** la gestión de la posición mira el objetivo, el stop por tiempo, la liquidación y la señal invertida (`live.py:3366-3398`), y para el stop depende de la orden que reposa en el venue.
- **Inferencia (no verificada de punta a punta):** sobre Binance, una posición abierta por el vivo queda **sin stop protector en el venue durante toda su vida**. Solo la cubren el objetivo, el stop por tiempo, la liquidación y la reversión. Y el sistema no lo informa como posición desprotegida, solo con avisos de registro.

## Relación con «la revisión anterior del adaptador»
- Busqué acotadamente en los documentos del repositorio (`docs/*.md` y `docs/evidence/`, base `72ffae5`) y **no encontré** una revisión previa documentada de este defecto.
- No puedo afirmar que lo hallado aquí sea el mismo defecto que menciona el pedido, ni que esa revisión lo haya tratado. Queda como hallazgo de esta misión, verificado de forma independiente.
- **Evidencia documental del repositorio, registrada antes y no reverificada aquí:**
  - las corridas de testnet del market maker guardan el `exchangeInfo` de BTCUSDT con `orderTypes` `['LIMIT', 'LIMIT_MAKER', 'MARKET', 'STOP_LOSS', 'STOP_LOSS_LIMIT', 'TAKE_PROFIT', 'TAKE_PROFIT_LIMIT']` (`docs/evidence/mm_testnet_20261003T224159Z.json:60`);
  - es decir, en testnet el venue ofrecía `STOP_LOSS`, y el adaptador no lo usa.

## Qué no está verificado
- **Ninguna corrida contra el venue real ni contra la testnet**, porque no hay red hacia Binance.
- Tampoco se verificó si el venue aceptaría `STOP_LOSS` en spot para este uso.
- No se ejecutó una sesión del vivo con este adaptador. La consecuencia anterior sale de leer el código.

## Corrección propuesta (no implementada; requiere decisión y validación en testnet)
1. **Opción a:** mapear `OrderType.STOP` a `STOP_LOSS` de spot, que tiene `stopPrice` y no lleva `timeInForce`.
2. **Opción b:** que el vivo use `STOP_LIMIT` (`STOP_LOSS_LIMIT`) con un límite de peor precio cuando el proveedor no soporte STOP.
3. Además, el adaptador debería declarar las capacidades que **realmente** traduce, de modo que `supports_stop_orders` no prometa algo que rechaza.
4. Además, en el vivo, una falla al colocar el stop debería contar como posición desprotegida (`unprotected_positions`) y llevar a una acción: bloquear entradas, cerrar o alertar. Hoy queda solo como un aviso.
5. Prueba que haría falta: una prueba del adaptador que envíe la intención exacta que arma el vivo para su stop. Hoy las pruebas de `test_binance_live.py` no cubren ningún tipo STOP.

**Relación con otras piezas:**
- **No** depende de R19, que es persistencia, ni de la guarda 05, que cubre el motor de backtest.
- La guarda 05v2 vigila el backtest y `PaperExecutionProvider`, **no** el vivo ni este adaptador.
- Mientras siga abierto, el uso del vivo con Binance queda **bloqueado**, sumado a que el dinero real ya está bloqueado por la compuerta de activación.
