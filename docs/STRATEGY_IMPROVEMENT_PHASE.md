# Trader-IA — Fase de mejora rigurosa de estrategia y validación

Base: `ab68d1c`, rama `claude/algo-trading-simulation-platform-ngf7xo`, 2026-10-10. Trabajo en modo
paper/simulación exclusivamente: sin despliegues, sin reinicios, sin commits, sin push, sin tocar
credenciales ni archivos de entorno, sin simulaciones prolongadas, sin cambios de parámetros de
estrategia. Las secciones 1 y 2 se escribieron **antes** de modificar código; las siguientes se
completaron después, con los comandos y resultados exactos.

## 1. Auditoría del estado real del código (Fase 1)

Método: lectura del flujo de datos completo con archivo y línea, más una demostración numérica
ejecutada con las clases reales (sin mocks), `scratchpad/ev_demo.py`:

```
past trades: gross +20, fees 10, net +10 (x40, SE=0)
costs now (maker entry + taker exit, no spread/slip): 10.383 bps
estimate.mean_bps = 10.0  adjusted = 10.0
engine gross_edge_bps = 10.0  net_edge_bps = -0.383  tradeable = False
economically correct expectation for the next identical trade: gross 20 - costs 10.38 = 9.62
```

### 1.A Expectativa y costos

- `Outcome.net_return_bps` es **neto** de las comisiones pagadas (`economics/expected_value.py:91-93`);
  los productores lo calculan como `gross_bps - fees_bps` (`runtime/live.py:2121-2127`,
  `runtime/engine.py:845-854`; `api/state.py:317-322,335-340` leen `row.net_bps`).
- `EdgeEstimator.record` guarda ese neto como muestra (`:172-174`); `ExpectedValueEngine.evaluate`
  usa `gross_edge_bps = estimate.adjusted_bps` (`:505`) y `net_edge_bps = gross − costs.total_bps`
  (`:373-374`); `is_tradeable = net ≥ threshold` (`:381-382`). El umbral está expresado en **neto**.
- Unidades coherentes: todo en bps del nominal de entrada; `explain()` traduce a USD; `BPS=1e-4`.
- Costos: `CostModel.estimate` (`economics/costs.py:171-205`) cobra ambas patas con la misma
  convención long/short (entrada maker o taker según `entry_maker`, salida siempre taker), medio
  spread por cruce, slippage, impacto y latencia. Funding no entra.
- **Conclusión demostrada**: la expectativa comparada contra el umbral es `neto_pasado −
  costos_presentes`, es decir los costos se descuentan dos veces (una dentro de la muestra, otra
  en el motor). El comentario de `Outcome` afirma lo contrario. Backtester y motor de simulación
  comparten la misma aritmética (mismo módulo); los tests de `tests/unit/test_economics.py`
  construyen outcomes con `net_return_bps` sin costos y por eso no detectan la diferencia.

### 1.B Procedencia y contaminación

- Carga: `_load_live_evidence` → `EdgeStateRepository.load_all()` sin filtro (`api/state.py:400-415`,
  `persistence/repositories.py:467-471`); también `_load_prior_outcomes` para el runtime de
  simulación (`api/state.py:302-327`, usado en `:250`).
- Consumo: `EdgeEstimator.record_many` (`live.py:311`), `RetrospectiveEngine.record_many`
  (`:324`), `StrategyScoreboard.record_many` (`:331`). Solo el scoreboard mira `market_data`
  (`learning/scoreboard.py:157-162`). Refresco cada 60 s por la misma vía (`state.py:566-578,
  429-458`) excluyendo las filas propias por `run_id` e id.
- Las seis categorías pedidas y cómo las etiqueta el sistema hoy: (1) sintéticos:
  `market_data='synthetic'`, `execution_mode='simulated'`, `source` sim/paper (`engine.py:934-935`);
  (2) datos históricos de mercado: velas, no son outcomes, no entran a la tabla; (3) decisiones
  sobre datos de mercado: `live.no_trade` solo en memoria y en el feed de actividad, no en la base;
  (4) órdenes simuladas: `orders` (solo colocación); (5) ejecuciones simuladas: `fills`;
  (6) resultados realizados de paper: `edge_outcomes` con `source='live'`, `market_data='real'`,
  `execution_mode='simulated'` (`live.py:2187-2218`).
- **Conclusión**: los sintéticos pueden alterar la expectativa estimada de las operaciones de
  paper y el estado `disproven` (lo hicieron: 53 veces), no pueden silenciar estrategias bajo
  `real_only`, y se mezclan con los reales dentro del mismo bucket del estimador sin distinción.

### 1.C Clasificación y aprendizaje

- `live.py:1177-1196`: `estimate is None → unknown`; `mean > 0 and not decayed → unproven`;
  resto → `disproven`. No interviene SE ni tamaño muestral: una media −0,3 ± 15 es `disproven`.
- Exploración solo en `unknown`/`unproven` (`:1197-1203`), tras riesgo, con tope diario y 25 %.
- Scoreboard: exploratorios no entran a `_net` (`scoreboard.py:166-169`) ⇒ `judged` no crece.
- Círculo confirmado con datos (2 trades, 2 exploratorios, 0 juzgados). Contaminación entre
  estrategias: el estimador agrupa por (régimen, dirección, banda) sin estrategia **por diseño**
  (`scoreboard.py:3-7`); el scoreboard separa por estrategia. Bloqueo por sintéticos: posible en EV
  (sí ocurrió), imposible en el mute bajo `real_only`.

### 1.D Órdenes, ejecuciones, posiciones y cantidades

- `_build_intent` cuantiza solo con `step_size` del venue (`live.py:1354-1356`); paper-live no
  recibe `symbol_filters` (`state.py:2245-2259`); el simulador redondea al lote 1e-6
  (`execution/paper.py:282`, `domain/instruments.py:92-96`). Dato: orden 0,01204375 → fill 0,012043
  → `PARTIALLY_FILLED` → `live.order_expired` sobre una posición ya cerrada.
- Fills limit: trigger si el precio atraviesa el límite (`paper.py:331-341`), referencia
  `max(limit, open)` y **slippage adverso aplicado a un fill maker** (`:286`): un venue nunca llena
  una limit peor que su límite. Dato: 83.026,00 con límite 83.038,31.
- Stops: `max(stop, open)` + slippage acotado al rango de la vela (`:343-355, 414`): correcto.
- Estados terminales: `resolve_fill_state` con tolerancia relativa 1e-9 (`execution/state_machine.py:144-155`);
  el residuo de 3,75e-6 sobre 0,012 (3e-4 relativo) queda fuera de la tolerancia → no terminal.
- Idempotencia: `submit_order` deduplica por `client_order_id` (`paper.py:147-154`); `_on_fill`
  por `fill_id` (`live.py:2041-2043`). Correcto.
- Persistencia de órdenes: `_save("order")` solo al colocar y en salidas a mercado
  (`live.py:1483, 1546, 1906, 1999`); `OrderRepository.upsert` sí actualiza estado y cantidades
  (`repositories.py:218-240`) pero nadie lo llama tras un fill. Dato: 4 filas `acknowledged`.
- Contadores: `counters["orders"]` cuenta colocaciones (y salidas a mercado); no hay contador de
  entradas ejecutadas ni de round trips; `fills` cuenta fills.

### 1.E Atribución

- `strategy_id = result.contributing[0].strategy_id` (`strategy/engine.py:170-172`) con
  `contributing=agreeing` en orden de evaluación (`strategy/fusion.py:254,307`), que es el orden de
  `StrategyConfig.enabled` (`core/config.py:217`). Stop/objetivo vienen de la opinión de mayor
  fuerza (`fusion.py:270`), que puede ser otra. **Confirmado**: la atribución depende del orden de
  una lista.

### 1.F Filtros de riesgo y métricas

- `RiskEngine.record_execution` (`risk/engine.py:130-132`) lo llaman el motor de simulación
  (`runtime/engine.py:570`) y el backtester (`backtest/engine.py:229`), **no** la sesión 24/7
  (`live.py`): enfriamiento 300 s, 20/día y 5/símbolo/día nunca se arman en paper-live (corrige la
  afirmación de la auditoría forense, que los daba por muertos también en el simulador).
- Denominadores: `signals == evaluated` (una por vela); `risk_reasons` conserva solo el primer
  motivo (`live.py:1055`); `funnel.orders` cuenta entradas colocadas, no ejecutadas.
- Métricas potencialmente engañosas por instrumentación: `orders`/`funnel.orders` (colocación ≠
  ejecución), `resting` (incluye residuos), `orders_expired` (incluye residuos),
  `ev_disproven` (sin significancia), `expected_net_bps` (doble descuento), estados en `orders`.

## 2. Informe previo a los cambios (Fase 2)

| # | hallazgo | archivo / función | evidencia | impacto | sev. | cambio mínimo | prueba | riesgo de regresión | clase |
|---|---|---|---|---|---|---|---|---|---|
| 1 | EV descuenta costos dos veces | `expected_value.py` `Outcome`, `EdgeEstimator.record`, `ExpectedValueEngine.evaluate`; productores en `live.py:_score_round_trip`, `engine.py`, `state.py:_as_outcome/_load_prior_outcomes` | demo numérica (arriba); lectura de 1.A | umbral efectivo ≈ umbral + 2×costos; sesgo sistemático a NO_TRADE; calibración del retrospectivo desplazada | P1 | el estimador muestrea el **bruto** (`Outcome.gross_return_bps`/`fees_bps`); el motor resta los costos presentes una vez; productores pasan bruto y comisiones | casos numéricos manuales: bruto−costos, sin segundo descuento, costos 0 y variables, long/short, bajo/en/sobre umbral, inválidos | medio: cambia qué buckets son operables (hacia más); conviction y ventana reciente pasan a operar sobre bruto | **defecto confirmado** |
| 2 | `disproven` sin significancia | `live.py:1177-1196` | lectura; 53 rechazos | cierra exploración en buckets "no sabemos" | P1 | `adjusted_bps < 0` ⇒ disproven (media más de k·SE bajo cero, el mismo criterio del shrink); si no, unproven | tabla de casos (n, media, SE) → estado | bajo: más exploración acotada | **defecto confirmado** |
| 3 | sintéticos autorizan/descartan en EV y retrospectivo | `state.py:_load_live_evidence`, `live.py:311,324`, `absorb_evidence` | lectura 1.B; datos 12 h | la deriva del generador decide qué es operable | P1 | `LiveConfig.ev_evidence_policy` (`legacy` por defecto, `real_only` opcional); `Outcome.market_data`; filtro al cargar y al absorber | miles de sintéticas no cambian la clasificación bajo `real_only`; `legacy` idéntico | bajo: opt-in | **defecto confirmado** |
| 4 | exploratorios nunca juzgan (círculo) | `scoreboard.py:166-169` | datos: judged=0 | el scoreboard real no arranca | P1 | exploratorios reales entran a `_net` (siguen contados aparte); estados de evidencia explícitos en `StrategyRecord` | tests de scoreboard reescritos; estados | medio: el mute puede dispararse con 30 exploratorios reales negativos (intencional) | **defecto confirmado** |
| 5 | cantidad sin cuantizar → residuo → expiración espuria | `live.py:_build_intent`, `_manage_resting`; `state.py:2245-2259` | datos: 0,01204375 vs 0,012043 | embudo y contadores contaminados | P2 | cuantizar al lote del instrumento sin `step_size`; residuo < lote = completa | unit (intent) + integración (sin `orders_expired` tras fill completo) | bajo | **defecto confirmado** |
| 6 | limit llena peor que su límite y mejora al open | `paper.py:_fill_price/_try_fill` | datos: 83.026 vs 83.038,31 | costos inflados en paper-live; sesgo mixto | P2 | fill maker exactamente al límite, slippage 0; trade-through se mantiene (supuesto conservador sin cola) | unit: fill al límite; existentes de slippage (market) intactos | bajo | **defecto confirmado** |
| 7 | `orders` no se actualiza tras fills | `live.py:_manage_resting`, `_poll_protective` | datos: 4 filas `acknowledged` | registro persistido no refleja ejecución | P2 | `_save("order")` cuando hay fills o estado terminal | integración: la fila persistida llega a FILLED | bajo | **defecto confirmado** |
| 8 | frecuencia/enfriamiento muertos en paper-live | `live.py` (sin `record_execution`) | grep de invocadores | controles declarados que no actúan | P2 | `record_execution` en el fill de **entrada** (por round trip) | integración: señal a < 300 s de una entrada rechazada por cooldown | medio: baja la actividad; el tope 5/símbolo/día contradice al perfil (20) — **no se toca el parámetro, se informa** | **defecto confirmado** |
| 9 | atribución por orden de lista | `strategy/engine.py:170-172`, `fusion.py` | lectura 1.E | la estrategia acreditada puede no ser la que fijó el trade | P2 | `FusionResult.primary` (mayor fuerza) → `strategy_id`; `contributing_strategy_ids` | unit: TF débil + BO fuerte ⇒ breakout | bajo: solo filas nuevas | **defecto confirmado** |
| 10 | rechazos sin estrategia/confianza/régimen | `live.py:_refuse` | lectura | embudo por estrategia irreconstruible | P2 | enriquecer `live.no_trade` y `recent_refusals` | integración: campos presentes | nulo | **defecto confirmado** |
| 11 | sin contadores de ejecución | `live.py` counters | lectura | colocación ≠ ejecución en los informes | P2 | `entries_filled`, `round_trips` | integración | nulo | **defecto confirmado** |
| 12 | "ventana reciente" sobre sintéticas ordena por reloj de escenario | `expected_value.py:_with_recent`, `load_all` | lectura | recencia no temporal | P2 | — | consulta H-5 del forense | — | riesgo plausible no demostrado |
| 13 | el simulador cuenta cada fill como trade para frecuencia | `engine.py:570` | lectura | tope efectivo 2,5 round trips/día en la evidencia | P2 | — | — | alterar la generación de evidencia | riesgo plausible; no tocar ahora |
| 14 | geometría stop/objetivo a 1 m vs costos | `strategy/library.py:43-44` | 2 trades + aritmética | viabilidad | P1 | ninguno sin experimento | Fase 4 | — | hipótesis de mejora (experimento) |
| 15 | evidencia sintética con entradas market vs vivo limit | `engine.py:1157-1164` vs `live.py:1159-1166` | lectura | poblaciones no comparables | P2 | registrar `entry_order_type` en cada fila (futuro) | — | — | idea, no todavía |
| 16 | HTF `hard` con marea plana; funding sin tasa | `trend_context.py:60-62`; snapshot | datos 12 h | no-op silenciosos | P3 | — | — | — | idea, no todavía |
| 17 | rollback de `deploy.sh` tras migración; credenciales en shell | operaciones | incidente 10-07 | disponibilidad / seguridad | P0 | fuera del alcance de esta fase (sin despliegue) | — | — | pendiente operativo |

Hallazgo previo **refutado parcialmente**: la auditoría forense afirmaba que la frecuencia del
motor de riesgo no se armaba "en el runtime"; es cierto para la sesión 24/7 y falso para el
simulador y el backtester (1.F). Se corrigió la nota en `PAPER_REALTIME_12H_FORENSIC_AUDIT.md`.

### Estados de evidencia por estrategia (definidos antes de implementar)

Recalculados en cada lectura a partir del registro (sin latch), con las constantes que ya existen
(`MIN_TRADES_TO_JUDGE=30`, `MUTE_SE=1.0`); no se introduce ningún umbral nuevo.

| estado | condición de entrada | condición de salida | qué autoriza |
|---|---|---|---|
| `unevaluated` | `trades == 0` | primer trade acreditado | solo exploración (si el EV no tiene evidencia admitida) |
| `insufficient` | `0 < judged < 30` | `judged ≥ 30` | lo que el EV permita; exploración posible |
| `inconclusive` | `judged ≥ 30` y `mean − SE ≤ 0 ≤ mean + SE` | sale del intervalo | lo que el EV permita |
| `favourable` | `judged ≥ 30` y `mean − SE > 0` | `mean − SE ≤ 0` | lo que el EV permita |
| `unfavourable` | `judged ≥ 30` y `mean + SE < 0` (= mute actual) | `mean + SE ≥ 0` | nada (silenciada) |

Transiciones permitidas: cualquier estado puede pasar a cualquier otro cuando cambian los datos;
no hay memoria más allá del registro. Los exploratorios reales **cuentan** como juzgados (siguen
reportados aparte); los sintéticos nunca entran al registro bajo `real_only`.

## 3. Archivos modificados y motivo (Fase 3)

| archivo | cambio | motivo (hallazgo) |
|---|---|---|
| `packages/tia/src/tia/economics/expected_value.py` | `Outcome` gana `fees_bps`, `gross_return_bps`, `market_data` y la propiedad `edge_sample_bps`; `EdgeEstimator.record` muestrea el **bruto**; docstrings de módulo y clase documentan la única convención | #1 doble descuento de costos |
| `packages/tia/src/tia/runtime/live.py` | productor de `Outcome` pasa bruto, comisiones y `market_data="real"`; política de evidencia (`_evidence_admitted`, filtro en construcción y en `absorb_evidence`, `evidence_policy`/`evidence_excluded` en el snapshot, racha de pérdidas sobre evidencia admitida); clasificación `disproven ⇔ adjusted < 0`; `_build_intent` cuantiza al lote del instrumento sin filtros de venue y `_lot_size`; `_manage_resting` trata residuo < lote como orden completa y persiste la orden tras fills; `_poll_protective` persiste tras fills; `record_execution` al fill de entrada; contadores `entries_filled` y `round_trips`; `_refuse` con estrategia, versión, co-firmantes, confianza, dirección y régimen en los siete puntos de rechazo; import de `DEFAULT_UNIVERSE` a nivel de módulo | #1, #2, #3, #5, #7, #8, #10, #11 |
| `packages/tia/src/tia/runtime/engine.py` | productor de `Outcome` pasa bruto, comisiones y `market_data="synthetic"` | #1, #3 |
| `packages/tia/src/tia/api/state.py` | `_as_outcome` y `_load_prior_outcomes` pasan bruto, comisiones y `market_data` de la fila | #1, #3 |
| `packages/tia/src/tia/core/config.py` | `LiveConfig.ev_evidence_policy: legacy\|real_only = legacy` | #3 |
| `packages/tia/src/tia/learning/scoreboard.py` | los exploratorios entran a `_net` (juzgan) y siguen contados aparte; `StrategyRecord.evidence_state` con los cinco estados; `as_dict` lo expone; docstrings | #4 y estados |
| `packages/tia/src/tia/execution/paper.py` | fills maker al precio límite exacto, slippage 0; se mantiene la exigencia de atravesar el límite | #6 |
| `packages/tia/src/tia/strategy/fusion.py` | `FusionResult.primary` (opinión de mayor fuerza entre las que acuerdan) | #9 |
| `packages/tia/src/tia/strategy/engine.py` | `strategy_id` desde `primary`; `contributing_strategy_ids` | #9 |
| `packages/tia/src/tia/domain/signals.py` | `SignalCandidate.contributing_strategy_ids` | #9 |
| `packages/tia/src/tia/backtest/resample.py` (nuevo) | agregación 1 m → n m sin look-ahead (bucket completo o nada) | Fase 4 |
| `scripts/strategy_experiment.py` (nuevo) | harness por estrategia/horizonte con particiones cronológicas, holdout sellado, sensibilidad a costos, criterios pre-registrados, procedencia | Fase 4 |
| `docker-compose.prod.yml`, `.env.example` | passthrough y documentación de `TIA_LIVE__EV_EVIDENCE_POLICY` (por defecto `legacy`) | #3 |
| `tests/unit/test_expected_value_convention.py` (nuevo) | 13 casos numéricos manuales de la convención | #1 |
| `tests/unit/test_evidence_policy_config.py` (nuevo) | lectura y validación de la variable; independencia de las dos políticas | #3 |
| `tests/unit/test_fusion_attribution.py` (nuevo) | primaria por fuerza, no por orden | #9 |
| `tests/unit/test_resample.py` (nuevo) | OHLCV, bucket parcial, hueco, alineación a la grilla, mismo timeframe | Fase 4 |
| `tests/unit/test_paper_execution.py` | +3 tests: limit al límite sin slippage; venta limit con apertura por encima; market sigue pagando slippage | #6 |
| `tests/unit/test_scoreboard.py` | 2 tests reescritos (exploratorios juzgan, también bajo `real_only`) + 1 test de estados | #4 |
| `tests/integration/test_live_runtime.py` | helper acepta `prior_outcomes`/`prior_reviews`; test de exploración reescrito (rojo dentro del ruido = unproven; rojo fuera = disproven); +8 tests nuevos (política de evidencia ×2, atribución de rechazos, cuantización, residuo, orden persistida con fill, cooldown armado, contadores de ejecución) | #2, #3, #5, #7, #8, #10, #11 |
| `docs/PAPER_REALTIME_12H_FORENSIC_AUDIT.md` | corrección: la frecuencia del motor de riesgo sí se arma en simulador y backtester; solo faltaba en la sesión 24/7 | 1.F |

Sin cambios: credenciales, `.env`, `live.enabled`, `is_simulation_only`, `TIA_LIVE__USE_TESTNET`,
`TIA_MM__REAL_MONEY`, activación, umbrales de EV, parámetros de estrategia, perfiles de riesgo,
esquema de base de datos (no hacía falta migración: `gross_bps`, `fees_bps` y `market_data` ya
existen en `edge_outcomes`).

## 4. Correcciones y sus pruebas

**4.1 Expectativa neta (una convención).** El estimador muestrea el bruto; el motor resta los
costos presentes una vez. Demostración con las clases reales, antes y después, mismo script:

```
ANTES : estimate(net) mean=10.0 | costs now 10.383 | net_edge=-0.383 | tradeable=False
DESPUÉS: estimate(gross) mean=20.0 | costs now 10.383 | net_edge=+9.617 | tradeable=True
TRADE — on a $996 position: expected gross +$1.99 (from 40 past trades) minus costs +$1.03 = net +$0.96, against a required minimum of +$0.50.
```

Tests (`test_expected_value_convention.py`): bruto−costos una vez; outcome solo-neto tratado
como sin costos (explícito, nunca segundo descuento); costos cero; tabla al/bajo/sobre el
umbral (10/5→5 opera, 9,99/5→4,99 no, 10,01/5 sí, 30/10 sí, 12/10 no, −5/5 no); costos variables
mueven el veredicto y no el estimado; techo de cociente de costos se mantiene (12/20 = 0,60 opera,
12,5/20 no); long y short simétricos; la aritmética del productor coincide con la muestra (trade 1
de la corrida: bruto −10,899, neto −20,907); unidades y conversión a USD; una muestra extrema se
contrae por su SE; NaN nunca opera; dirección no accionable se rechaza antes. El umbral no se tocó.

**4.2 Separación de evidencia.** `ev_evidence_policy=real_only` deja fuera del estimador y del
retrospectivo toda fila con `market_data != "real"` (sintéticas y sin procedencia), al arrancar y
al absorber; el scoreboard conserva su propia política. Test de integración: 5.000 filas sintéticas
ganadoras hacen operable un bucket bajo `legacy` y no enseñan nada bajo `real_only`
(`coverage == {}`, memoria retrospectiva vacía, `evidence_excluded == 5000`); 1.000 más absorbidas
→ 0 absorbidas, 1.000 excluidas; 40 reales → 40 en bucket. Filas sin procedencia: excluidas. La
configuración se lee del entorno, valida y es independiente de `scoreboard_policy`. Datos
existentes intactos; sin migración.

**4.3 Estados de evaluación.** `disproven ⇔ adjusted_bps < 0` (media más de k·SE bajo cero, con el
k del propio estimador); lo demás no operable es `unproven` y explorable. Test de integración
reescrito: −5 ± 90 sobre 40 → `unproven` y explora; −60 ± 90 → `disproven`, nunca explora, 0
órdenes. En el scoreboard los exploratorios juzgan (tests reescritos, con la justificación en el
docstring) y `evidence_state` recorre `unevaluated → insufficient → inconclusive/favourable/
unfavourable` sin latch ni umbrales nuevos (test con los cinco estados). La exploración sigue
después de riesgo, con tope diario y fracción de tamaño; no elude nada.

**4.4 Integridad de ejecución simulada.** Cuantización al lote sin filtros de venue
(0,01204375 → 0,012043); residuo < lote = orden completa (test: fill parcial que deja 5e-7, la
orden deja de "descansar", `orders_expired == 0`, `entries_filled == 1`, el resto se cancela);
`orders` persistida con su fill (test: la fila pasa de ACKNOWLEDGED a FILLED con la cantidad
ejecutada); fills maker al límite (3 tests); cooldown y topes armados al fill de entrada (test:
`trades_today == 1`, `last_trade_at` registrado); round trips contados al cierre, no al envío
(test). Cubiertos por tests ya existentes y que siguen pasando: orden aceptada sin ejecución,
cancelación confirmada, cancelación de orden terminal, duplicado por `client_order_id`, stop
atravesado por salto, cantidad en varios bars, reconciliación tras caída de fill. Limitación
documentada: sin libro no hay prioridad de cola; el supuesto conservador es exigir que el precio
atraviese el límite.

**4.5 Métricas y atribución.** `strategy_id` = opinión de mayor fuerza (la que fija stop y objetivo);
`contributing_strategy_ids` conserva a los co-firmantes; cada `live.no_trade` y cada
`recent_refusals` llevan estrategia, versión, co-firmantes, confianza, dirección y régimen (test);
`entries_filled`/`round_trips` separan colocación de ejecución. Los resultados históricos no se
reescribieron: las filas anteriores conservan la atribución por orden de lista y el
`expected_net_bps` con doble descuento, y así deben leerse (§6).

## 5. Comandos ejecutados y resultados exactos

Entorno: `.venv/bin/python` 3.11.15, pytest 9.1.1, `PYTHONPATH=packages/tia/src`, sin red.

| comando | resultado |
|---|---|
| `ruff check packages tests scripts` | `All checks passed!` |
| `pytest tests/unit` (línea base, antes de los cambios) | todos los tests pasaron (`exit=0`; la suma `-q -q` de `addopts` suprime la línea de resumen) |
| `pytest tests/integration` (línea base) | `exit=0` |
| `pytest tests/unit` (después) | `1232 passed in 67.13s` (una corrida intermedia, anterior a corregir el conteo de buckets del re-muestreador, dio `2 failed, 1230 passed`: los dos fallos eran `test_resample.py` y se corrigieron antes de la corrida final) |
| `pytest tests/integration` (después) | `163 passed in 83.00s` |
| `pytest tests/property` | `31 passed in 18.45s` |
| `pytest tests/failure` | `12 passed in 2.61s` |
| `pytest tests/adversarial` | `16 passed in 7.07s` |
| `pytest tests/e2e` | `8 passed in 44.43s` |
| `python scripts/strategy_experiment.py --fixtures data/fixtures --symbol BTC-USD --timeframes 1m,5m,15m --fee-multipliers 1.0,1.5 --extra-slippage-bps 0` | corre de punta a punta sobre las fixtures **sintéticas**; 12 variantes; veredicto `INSUFFICIENT` en las 6 celdas de validación (0–5 trades por celda); holdout sellado |

No se ejecutaron: `scripts/verify.sh` completo (incluye frontend `npm` y `smoke.sh`, que
levantan servicios), ninguna simulación paper-live, ningún despliegue.

## 6. Defectos pendientes y riesgos residuales

1. **La corrección del EV no está activa en producción hasta reiniciar**, y `ev_evidence_policy`
   sigue en `legacy` hasta que el operador opte por `real_only`. Al activarlo, todos los buckets
   arrancan `unknown` y la exploración (hoy 20/día al 25 % del tamaño en producción) es la única
   fuente de evidencia; es el comportamiento diseñado, y conviene decidirlo explícitamente.
2. **Datos históricos no comparables**: `expected_net_bps` de las filas anteriores lleva el doble
   descuento; `strategy_id` anterior sigue la regla de orden de lista. Se marcan, no se reescriben.
3. **Tope por símbolo**: al armar la frecuencia del motor de riesgo, `max_trades_per_symbol_per_day=5`
   limitará a 5 entradas/día en una sesión de un solo símbolo, contradiciendo el perfil balanced
   (20). Parámetro no tocado; decisión del operador.
4. **El simulador de entrenamiento cuenta cada fill (entrada y salida) como "trade"** para la
   frecuencia (`runtime/engine.py:570`); la sesión 24/7 ahora cuenta entradas. Discrepancia
   documentada; no se cambió para no alterar la generación de evidencia.
5. **Exploratorios juzgan**: en producción (`real_only` en el scoreboard) trend_following pasa de
   0 a 2 juzgados con las filas existentes; con 30 exploratorios negativos una estrategia puede
   quedar silenciada. Es el objetivo del cambio, pero es un cambio de comportamiento.
6. **Persistencia de órdenes por sondeo**: la fila se actualiza cuando `_manage_resting` o
   `_poll_protective` ven fills o estado terminal, no en cada transición del venue. Decisiones y
   rechazos siguen sin persistirse (fuera del alcance de esta fase; propuesta P2-A del forense).
7. **Frontend**: no se tocó; `evidence_state`, `evidence_policy`, `evidence_excluded` y los campos de
   atribución en `recent_refusals` están disponibles en la API pero no se muestran.
8. **Fase 4 sin datos reales**: las fixtures son sintéticas y la red hacia `api.binance.com` está
   bloqueada en este entorno (403 del proxy). El harness está listo; el experimento sobre mercado
   real queda **inconcluso** hasta que el operador aporte un CSV de velas con procedencia.
9. **Operativos, fuera de este alcance**: rollback de `scripts/deploy.sh` tras migración aplicada
   (P0 del forense); rotación de las claves expuestas el 10-07.
10. **Tests no ejecutados aquí**: frontend y smoke (requieren servicios).

## 7. Diseño experimental (Fase 4) — hipótesis y criterios fijados antes de ver resultados

Herramienta: `scripts/strategy_experiment.py` + `tia.backtest` (motor, baselines, walk-forward) +
`tia.backtest.resample`. Simulador determinista (rechazos y parciales aleatorios apagados),
entradas a mercado (como el backtester), comisiones 2,5/7,5 bps, slippage base 2 bps, costos y
supuestos idénticos entre horizontes; única diferencia inevitable: a mayor horizonte, menos
barras por partición para la misma ventana temporal.

Datos requeridos: velas 1 m cerradas de BTCUSDT de una fuente pública verificable (p. ej.
`GET /api/v3/klines` o los archivos mensuales públicos de Binance), ≥ 90 días (129.600 barras ⇒
15 m con 8.640), con hash y marcas temporales registrados por el script. Hasta entonces: **inconcluso**.

Particiones cronológicas: investigación 50 % / validación 30 % / holdout 20 %, separadas por purga
20 + embargo 30 barras del horizonte; el holdout no se calcula sin `--unlock-holdout`, que se usa
una sola vez al final. Walk-forward con `build_plan` cuando quepan ≥ 3 pliegues de ≥ 2.000
barras. Sin look-ahead: features sobre barras cerradas, fills en la barra siguiente, re-muestreo
que solo emite buckets completos. Se registra el número de variantes probadas; PBO y Sharpe
deflactado no se calculan con < 16 variantes ni con < 30 trades por celda, y nunca se presentan
como garantía.

| hipótesis | métrica pre-registrada (validación) | referencia | criterio |
|---|---|---|---|
| H1 Horizonte: a 5 m y 15 m la relación objetivo/costos mejora lo suficiente para que la expectativa neta deje de ser negativa | media neta por trade (bps) con IC 90 % bootstrap; PF; maxDD; exposición | 1 m con la misma configuración | `PROMISING_ON_VALIDATION` solo si n ≥ 30, IC inferior > −5 bps, PF > 1,2, maxDD < 1 %, y media neta > 0 con comisiones ×1,5 |
| H2 Estrategias individuales aportan señal distinta | trades/1.000 barras, tasa de aprobación, distribución de retornos, por régimen y dirección | las otras dos estrategias y `always_flat` | n < 30 ⇒ `INSUFFICIENT`; IC superior < 0 ⇒ `UNFAVOURABLE` |
| H3 Robustez a costos | media neta bajo comisiones ×1,5 y ×2, +2 bps de slippage | base | media neta ≤ 0 bajo ×1,5 ⇒ `FRAGILE` |
| H4 Combinación (futuro) | correlación de direcciones por barra entre estrategias; aporte marginal frente a cada una sola y a `sma_cross` | estrategias individuales | no se implementa ensemble hasta que H2 tenga n ≥ 30 por estrategia |

Comprobación del pipeline sobre las fixtures sintéticas (5.000 barras): 12 variantes, 0–5 trades
por celda, veredicto `INSUFFICIENT` en todas; no dice nada de ningún mercado.

### 7.1 Actualización Fase 1.1 (endurecimiento estadístico) — sustituye al criterio de H1

Los criterios y el código viven ahora en `tia.backtest.inference` (`CRITERIA`, `verdict`), que el
harness importa; la fila H1 de la tabla anterior queda **superada** por lo siguiente, fijado antes
de evaluar ninguna variante y sin ajustar a ningún resultado:

| elemento | Fase 1 | Fase 1.1 |
|---|---|---|
| Intervalo | bootstrap i.i.d. percentil, 2.000 remuestreos | **block bootstrap circular** (Politis–Romano) de la media, bloque `round(n^(1/3))` (Hall–Horowitz–Jing), 2.000 remuestreos; el i.i.d. se reporta al lado solo para comparar |
| Nivel | 90 % bilateral | 90 % bilateral **pre-registrado y no cambia**; la decisión lee solo el límite inferior (error unilateral 5 %) |
| Multiplicidad | se registraba `variants_tried_on_validation`, sin corrección | **Bonferroni** sobre la familia de candidatos (estrategia × horizonte) juzgados en la misma validación: el veredicto lee el intervalo al nivel `1 − 0,10/k`; las variantes de costos de un mismo candidato son chequeos de robustez, no candidatos |
| `PROMISING_ON_VALIDATION` | IC inferior > −5 bps, PF > 1,2, maxDD < 1 %, media > 0 con ×1,5 | **límite inferior ajustado > 0 estrictamente** (0 exacto no cuenta), PF > 1,2, maxDD < 1 %, media > 0 con comisiones ×1,5; **sin estrés de costos ejecutado no hay `PROMISING`** (`INCONCLUSIVE`) |
| `UNFAVOURABLE` | IC superior < 0 | igual: intervalo ajustado enteramente por debajo de 0 (superior = 0 exacto ⇒ `INCONCLUSIVE`) |
| `INCONCLUSIVE` | resto | el intervalo cruza o toca cero, o PF/maxDD no pasan, o falta el estrés |
| `FRAGILE` | media ≤ 0 con ×1,5 | igual, evaluado después de intervalo, PF y maxDD |
| Significado | — | `PROMISING_ON_VALIDATION` = "merece una evaluación posterior fuera de muestra"; **no** es rentabilidad ni autorización para dinero real |

Protección del holdout (`tia.backtest.holdout`): cada cómputo con `--unlock-holdout` se registra en
un libro de accesos append-only (`--holdout-log`, por defecto `data/runtime/holdout_access.jsonl`)
con el hash del dataset, el hash de la configuración congelada (criterios, estrategias, horizontes,
particiones, semilla, simulador **y el código fuente de `tia/strategy`**), las variantes probadas,
los veredictos, el commit y si el árbol estaba limpio. Una repetición bajo la misma configuración se
rechaza; una reapertura bajo configuración distinta exige `--holdout-reopen-reason`. Protocolo: se
congela todo, se abre el holdout **una vez**, y cualquier cambio motivado por su resultado exige un
nuevo período fuera de muestra. Límites declarados: el libro es un archivo borrable y no impide
evaluar un recorte distinto de los mismos datos; es procedimiento, no caja fuerte.

Lo que la inferencia sigue sin hacer: no elimina el sesgo de selección de elegir el mejor de `k`
(acota la tasa de falsos positivos de la etiqueta), no estima la probabilidad de sobreajuste del
backtest, y nada dice de datos no evaluados. El holdout **no se ha desbloqueado ni calculado** en la
Fase 1.1.

## 8. Afirmaciones que todavía no pueden hacerse

- Que alguna estrategia tenga expectativa neta positiva en BTC, en ningún horizonte.
- Que la corrección del EV aumente la rentabilidad: aumenta la coherencia de la decisión y,
  previsiblemente, la frecuencia; nada más.
- Que `real_only` en el EV mejore resultados: hace que el sistema aprenda solo de mercado real;
  el resultado de ese aprendizaje no existe aún.
- Que la geometría stop/objetivo a 1 m sea viable o inviable con datos reales (solo aritmética y
  dos trades).
- Que el simulador reproduzca fills reales: sin libro, sin cola, sin funding, sin borrow.
- Que las fixtures digan algo sobre mercados: son sintéticas.
- Que los contrafactuales de la corrida de 12 h (qué habría operado con las correcciones) sean
  exactos: cambiar un gate altera la secuencia posterior.

## 9. Estado de Git

Rama `claude/algo-trading-simulation-platform-ngf7xo`, HEAD `ab68d1c`. **Sin commits ni push.**
Modificados (15): `.env.example`, `docker-compose.prod.yml`, `packages/tia/src/tia/{api/state.py,
core/config.py, domain/signals.py, economics/expected_value.py, execution/paper.py,
learning/scoreboard.py, runtime/engine.py, runtime/live.py, strategy/engine.py, strategy/fusion.py}`,
`tests/integration/test_live_runtime.py`, `tests/unit/{test_paper_execution.py, test_scoreboard.py}`.
Nuevos (9): `docs/PAPER_REALTIME_12H_FORENSIC_AUDIT.md`, `docs/PAPER_REALTIME_12H_REPORT.md`,
`docs/STRATEGY_IMPROVEMENT_PHASE.md`, `packages/tia/src/tia/backtest/resample.py`,
`scripts/strategy_experiment.py`, `tests/unit/{test_evidence_policy_config.py,
test_expected_value_convention.py, test_fusion_attribution.py, test_resample.py}`.
`git diff --stat`: 15 archivos, +607 / −48 (sin contar los nuevos).

## 10. Confirmaciones

Sin despliegues, sin reinicios de servicios ni contenedores, sin operaciones reales, sin commits,
sin push, sin simulaciones prolongadas, sin cambios en credenciales ni archivos de entorno
(`.env.example` es documentación), sin tocar `live.enabled`, `is_simulation_only`,
`TIA_LIVE__USE_TESTNET`, `TIA_MM__REAL_MONEY` ni la activación, sin borrar datos, sin migraciones,
sin cambios de parámetros de estrategia ni de umbrales, sin refactors fuera del alcance. Los dos
documentos previos sin seguimiento del usuario (auditoría forense e informe) se conservan; el
único cambio en ellos es la corrección de 1.F.
