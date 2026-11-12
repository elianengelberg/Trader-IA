# Revisión de diferencias, línea por línea (Fase F)

- **Fuente:** los parches de la extracción limpia de v3r3 (`25902649…`), más 05 (v1, del paquete `410ae629…`).
- **Inventario generado:** `INVENTARIO_PARCHES_v3r3_y_05v1.md` (fragmentos, líneas y patrones de riesgo).
- **Alcance de la lectura:** se leyeron completos los fragmentos de **producción** de 01 y 02v3. Las pruebas se leyeron en las misiones anteriores; aquí se revisaron los patrones marcados por el inventario.

## Unidad A = 01 + 02v3: 8 archivos distintos
| Archivo | De | Qué cambia (leído) | Observación |
|---|---|---|---|
| `backtest/engine.py` | 01 (7 fragmentos, +67 −8) | `_stop_placements` y `order_hygiene` por corrida. `symbol=` pasa a `_sync_protective_stop`. Aviso «N bars held a position with no stop level…». **D3 capa 1:** en `_request_exit`, cancela el resto de la entrada (no reduce-only, no stop) antes del cierre. **D1 cierres:** id de cliente por barra (`exit_key:close_time`), con `signal_id` estable. **D3 capa 2:** en plano, cancela un resto de entrada ya llenado en parte. **D3 capa 3:** libera `exit_pending` si el cierre terminó con posición. **D2:** `same_size and same_level` (relativo, 1e-9). **D1 stops:** id por colocación (`:protective:{n}`), también en `intent_id` | Sin cambios fuera de estas reglas. Ninguna orden nueva abre exposición: el cierre sigue reduce-only y se cancela el stop antes del cierre |
| `execution/paper.py` | 01 (+9) | `resting_orders(symbol)`, solo lectura del libro | Sin efectos laterales |
| `tests/unit/test_backtest_order_hygiene.py` | 01 (nuevo, 342) | 8 pruebas D1–D3 | Revisado en misiones anteriores. Sin red ni credenciales (inventario: ninguna marca) |
| `backtest/engine.py` | 02v3 (4 fragmentos, +76 −2) | `ENGINE_VERSION = "1.1.0"`; `engine_fingerprint()` (sha256 de los `.py` de 10 subpaquetes, en caché; «unavailable» si no hay archivos); `data_fingerprint(bars)`; procedencia en `BacktestConditions` y dentro del `run_id`, junto con estrategias, `liquidate_at_end` y `is_out_of_sample` | Solo agrega campos y cambia el id: no cambia ningún número (paridad con E1 reverificada en la reproducción de r3) |
| `backtest/result.py` | 02v3 (+7) | Cuatro campos `str = ""` en `BacktestConditions` | Las filas viejas quedan con `""`, que significa «desconocido» |
| `persistence/repositories.py` | 02v3 (2 fragmentos, +55) | `save`: rechaza otra procedencia y otros números bajo la misma procedencia (`ValueError`); NaN equivale a None | **R15:** `get` y después `upsert`, sin bloqueo (medido en PostgreSQL, ver R24/R15). **R24:** la comparación de floats es exacta; en PostgreSQL el NaN de `sharpe` vuelve como NaN y `_comparable` lo trata como None de los dos lados (probado en R24) |
| `api/state.py` | 02v3 (+2) | El listado expone `engine_version`, o `None` en filas viejas | — |
| `docs/ARCHITECTURE.md` | 02v3 (+10) | Describe la procedencia y la regla del almacén | Coincide con el código |
| `tests/integration/test_backtest_provenance.py` | 02v3 (nuevo, 302) | 14 pruebas | **Marcas del inventario, revisadas a mano:** `httpx.ASGITransport` con `base_url="http://test"` es en proceso, sin red. `TIA_DEMO_PASSWORD="provenance-password-not-a-secret"` es una credencial de demo de prueba, no un secreto. La base de la prueba de API es SQLite temporal |

- **Archivos ajenos:** ninguno.
- **Lista completa:** `docs/ARCHITECTURE.md`, `api/state.py`, `backtest/engine.py`, `backtest/result.py`, `execution/paper.py`, `persistence/repositories.py`, `tests/integration/test_backtest_provenance.py`, `tests/unit/test_backtest_order_hygiene.py`. Coincide con `ARCHIVOS_MODIFICADOS.txt` y con el paso 1.3 del plan.

## 03 (solo pruebas, 3 archivos)
- `test_account_restore.py`: ancla el reloj de la sesión con `SESSION_DAY_START`; quita un `… or True` y dos `pytest.skip`; agrega aserciones.
- `test_adverse_recovery.py` y `test_risk_state_persistence.py`: `_drive_by_hand` y el ancla del reloj.
- **Sin marcas de riesgo.** No toca ningún límite de tiempo.
- **Para R19:** `build()` agrega `start=None`, que por defecto toma el mismo camino.

## 04 (CI, opcional)
- `ci.yml`: `pip install -c constraints/ci-py311.txt …` y `cache-dependency-path`.
- `constraints/ci-py311.txt`: 74 versiones. Las marcas son nombres de paquetes (`httpx`, `urllib3`, `websockets`), no código.

## 05 v1 (guarda)
- Un archivo nuevo de prueba.
- **Marca:** `pytest.skip` para versiones < 1.1.0 o **sin versión**, que es justo el defecto encontrado en esta misión (ver Fase C): sin versión, la guarda se omitía.
- **05 v2:**
  - sin versión, la guarda **falla**;
  - «1.1» se lee como 1.1.0;
  - un cierre es cualquier orden reduce-only que no sea stop.
- **Diferencias exactas:** `guarda_v1_a_v2.diff`.
