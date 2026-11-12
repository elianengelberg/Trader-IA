# Decisiones pendientes (Fase M)

**Fecha:** 2026-10-25. **Árbol candidato:** `17332e1c510d0004f7744bde0a68f008f01652b7` (cadena completa hasta el parche 15).
**Estado de autorización:** NO AUTORIZADO PARA OPERAR CON DINERO REAL.

## 0. Qué se buscó y qué no apareció

- **D1–D17:** no hay en las fuentes disponibles ninguna lista de decisiones numeradas D1–D17 (búsqueda acotada en `registro/A6_busqueda_definiciones.txt`).
  - Con esa numeración solo existen otras cosas: defectos antiguos D1–D12 (`AUDIT_REPORT.md`), decisiones de market making D1–D4, el defecto D10 del corte de papel y los defectos D1–D3 del motor.
  - **No se inventan.** Abajo, los temas que nombra el encargo van como temas (T1–T12), sin número D.
  - Si existe una lista D1–D17, hay que aportarla para mapear cada tema a su número.
- **R24-H2 y R24-H3:** sin definición en ninguna fuente. Quedan **PENDIENTES**; hace falta que el propietario diga qué son.

## 1. Regla aplicada

- Solo se implementó la opción más conservadora y siempre que estuviera dentro del alcance: bloquear, detener, no reintentar, no declarar éxito.
- Nada de lo implementado es una política de producción irreversible:
  - cada comportamiento queda detrás de los estados existentes (`HALT_NEW_ORDERS`, bloqueos de entrada, `SAFE_MODE`);
  - se revierte quitando el parche correspondiente.
- Donde la opción conservadora cambia la producción (Docker), **no se integró**: queda como parche opcional que pide autorización.

## 2. Temas

| # | Tema | Comportamiento actual en el candidato | Opciones | Recomendación provisional (no es política) | Quién decide | Evidencia |
|---|---|---|---|---|---|---|
| **T1** | Re-protección y recuperación automática | Si el stop no se puede poner: la posición cuenta como desprotegida, se bloquean las entradas (`position_unprotected`), la sesión pasa a `HALT_NEW_ORDERS`, se guarda el incidente y se reintenta el stop en cada ciclo. Cuando el venue confirma un stop, el bloqueo se levanta, pero `HALT_NEW_ORDERS` **queda** hasta que actúe el operador | (a) dejarlo así; (b) volver a `RUNNING` solo, tras N barras con el stop confirmado; (c) cerrar la posición si el stop no se confirma en N intentos | (a) mientras no haya evidencia de testnet. La (b) solo con un límite y un incidente propio | Propietario / operador | `tests/integration/test_live_position_protection.py`; simulación E04b, E08 y E13 |
| **T2** | Re-protección en `PAUSED` y `SAFE_MODE` | En esos estados el ciclo no gestiona posiciones: si el stop se pierde ahí, no se repone hasta salir del estado | (a) dejarlo así; (b) permitir solo acciones de protección (poner o reponer el stop, nunca abrir) en `PAUSED` y `SAFE_MODE` | (b) es la más segura para el capital, pero cambia el contrato de `SAFE_MODE` («no tocar nada»). Hay que decidirlo antes de implementarla | Propietario | Por inspección de `runtime/live.py`; no hay prueba |
| **T3** | Apagado ordenado en Docker (≥ 30 s de gracia) | `docker-compose.prod.yml` sin cambios: `sh -c '… && python -m tia.api.main'` y gracia por defecto de 10 s. Se reprodujo que el SIGTERM no llega a Python (`logs/N_sigterm/resultado.txt`): sin flush, sin liberar el lease | Parche **14 opcional**: `exec` y `stop_grace_period: 40s` | Integrarlo, **con autorización**: toca la configuración de producción | Propietario (cambio de producción) | `parches/14_OPCIONAL_produccion_apagado_ordenado_docker.patch`; `logs/N_sigterm/` |
| **T4** | Política ante una posición desprotegida | T1: bloquear y detener las entradas, sin cierre automático | (a) dejarlo así; (b) cerrar a mercado tras N fallos; (c) cerrar enseguida | (a) en papel y testnet. Para dinero real hace falta una decisión explícita, porque (b) y (c) también pueden dañar el capital (cierre a mal precio) | Propietario | E04b |
| **T5** | Política ante escrituras no confirmadas | `flush_persistence` da `True` solo sin escrituras en vuelo **y** sin fallas. `stop()` deja `last_error` («the record is incomplete»). La sesión siguiente no opera sobre un registro corto (E12). **Durante** la sesión, una escritura perdida de un fill **no** bloquea las entradas | (a) dejarlo así; (b) bloquear las entradas desde la primera escritura fallida de órdenes o fills; (c) detener la sesión | (b): es conservadora y está dentro del alcance, pero cambia cuándo opera la sesión. Se deja para decisión porque una falla transitoria de la base pararía la operatoria | Propietario | `tests/integration/test_persistence_completeness.py`; matriz R19 (`registro/G_r19_matriz.txt`); E12 |
| **T6** | Reconciliación al reiniciar | Reconstrucción desde el diario. `_protect_restored_position()` corre **antes** del primer emparejamiento: adopta el único stop en reposo o pone uno. Con más de un stop, bloquea (`orders_unverified`) y pasa a `HALT_NEW_ORDERS`. Una orden ajena lleva a `SAFE_MODE` (E14) | (a) dejarlo así; (b) cancelar automáticamente los stops sobrantes | (a): cancelar órdenes que no se entienden es una acción sobre el venue que debe autorizar una persona | Propietario / operador | E13 y E14; prueba de reinicio en `test_live_position_protection.py` |
| **T7** | Límites de reintento y estados ambiguos | Timeout o error de transporte **después** de enviar (parche 15): estado DESCONOCIDO, sin reintento, `HALT_NEW_ORDERS` y reconciliación. 10 fallas del proveedor sin una barra nueva en el medio (el contador vuelve a 0 con cada barra): `SAFE_MODE`. Stop protector: se reintenta en cada ciclo, sin límite (el contador sube una vez por racha) | (a) dejarlo así; (b) un límite de reintentos del stop con escalada (`SAFE_MODE` o cierre, T4); (c) un límite de reconciliaciones fallidas | (b), con el número fijado por el propietario. No se eligió un número sin datos | Propietario | `tests/unit/test_binance_ambiguous_transport.py`; `test_binance_live.py` |
| **T8** | R17: cierre que avanza por llenados parciales | Regla actual: no se pone un stop sobre un cierre en curso; el cierre que trabaja cuenta como cobertura (pruebas de tolerancia 0). El resto de la posición no tiene **stop** mientras el cierre trabaja | (a) aceptarlo; (b) un stop sobre el resto, con el riesgo de vender de más en spot | Decisión de diseño. No se cambió | Propietario | `tests/unit/test_backtest_protection_window.py` (definición de cobertura); E09 |
| **T9** | Escrituras del motor de escenarios (`runtime/engine.py`) | Defecto nuevo, **no corregido**: `RuntimeEngine.flush_persistence` da `True` aunque haya escrituras fallidas (solo las cuenta). Las corridas simuladas alimentan el historial de papel que exige la compuerta de activación | (a) alinear con el vivo (R19); (b) excluir de la compuerta las corridas con fallas | (a) en una tarea aparte, con su propia prueba | Propietario | Por inspección (`runtime/engine.py:1617`); ver `MATRIZ_RIESGOS.md` N3 |
| **T10** | Prueba en testnet del stop protector (R25) | El adaptador mapea STOP a `STOP_LOSS` y la compuerta de activación **falla** hasta que haya un registro de testnet con `protective_stop_accepted: true` | Correr `scripts/validate_binance.py --account --order --stop --testnet` con credenciales **de testnet** | Hacerlo antes de cualquier uso del vivo con Binance | Propietario (credenciales de testnet) | `tests/unit/test_binance_protective_stop.py` |
| **T11** | Integración en el repositorio | Nada se commiteó, se pusheó ni se mezcló. El árbol se reconstruye con `reproducir.sh` | Rama aislada → corrida real de la CI (jobs python y postgresql) → revisión humana → protección de rama | Ver `INSTRUCCIONES_CI.md` | Propietario | `VERIFICACION_FINAL.txt` |
| **T12** | R24-H2 / R24-H3 y D1–D17 | Sin definición | Aportar las definiciones | — | Propietario | `registro/A6_busqueda_definiciones.txt` |

## 3. Qué NO se decidió por el propietario

- No se cambió `validada_para_operar`.
- No se habilitó dinero real.
- No se tocó la compuerta de activación, salvo para **exigir** la evidencia del stop en testnet: es más estricta, no más permisiva.
- No se eligieron números de reintentos ni de barras: cada número que falta queda señalado en T1, T4 y T7.
