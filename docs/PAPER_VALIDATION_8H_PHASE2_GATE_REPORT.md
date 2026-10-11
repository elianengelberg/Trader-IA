# Trader-IA — Fase 2: simulación nocturna de validación (8 h) en paper trading

## Resultado: CORRIDA NO INICIADA POR INCUMPLIMIENTO DE REQUISITOS

La puerta de entrada se ejecutó completa el 2026-10-10 entre las 06:45Z y las 06:50Z desde el entorno de trabajo de esta sesión (contenedor de Claude Code, checkout en `/home/user/Trader-IA`). Tres requisitos de seguridad y control no pueden garantizarse en ningún entorno al que esta sesión tenga acceso, por lo que la simulación **no se inició**. No se creó ningún proceso, orden simulada, registro de corrida ni dato de mercado. Ninguna cifra de este informe proviene de una corrida: las secciones que piden resultados de corrida se declaran explícitamente sin datos.

Estado de la corrida (marcar uno):

- [ ] Corrida completada
- [ ] Corrida interrumpida
- [x] **Corrida no iniciada por incumplimiento de requisitos**

---

## Motivos de no inicio (en orden de severidad)

| # | Requisito del encargo | Hallazgo verificado | Consecuencia |
|---|---|---|---|
| M1 | Usar únicamente datos públicos reales de mercado | Desde este entorno el proxy de red deniega el túnel a `api.binance.com` y a `data-api.binance.vision` (CONNECT 403, "policy denial") y `stream.binance.com:9443` no responde (timeout 5 s). El estado del proxy registra los rechazos como `connect_rejected`. | `POST /api/live/paper-start` fallaría con `ProviderUnavailableError` (503) y, aunque arrancara, no habría velas reales. Sustituir por fixtures sintéticas está prohibido para este propósito. |
| M2 | Evaluar el sistema "después de las correcciones de la Fase 1" | Las correcciones existen solo como cambios **sin commit** en este árbol de trabajo (15 archivos modificados, 9 nuevos, huella `d98ab6359eb3edfe`). El único despliegue en marcha (VPS, `trader-ia-backend-1`) ejecuta la imagen anterior a la Fase 1. Esta sesión no tiene acceso al VPS, y commit, push, despliegue y reinicio están prohibidos por el encargo. | No existe ningún entorno permitido donde el código corregido pueda correr con datos reales. |
| M3 | Mecanismo fiable de finalización y supervisión durante 8 h | La sesión paper del proyecto arranca con `POST /api/live/paper-start` y se detiene con `POST /api/live/stop`; **no tiene límite de duración propio**. En la corrida de 12 h el corte lo hizo un monitor ad hoc en el VPS, fuera del repositorio. Este contenedor es efímero (se recicla por inactividad), los comandos en segundo plano están limitados a 2 h y no hay base de datos en marcha (sin listener en 5432; la configuración por defecto caería a un archivo SQLite local inexistente, una topología de persistencia distinta a la del VPS). | El encargo ordena no inventar un mecanismo de corte ni dejar procesos sin supervisión. |
| M4 | Verificar la configuración efectiva del despliegue a evaluar | La configuración efectiva de **este árbol** sí se verificó (tabla abajo). La del VPS no puede verificarse desde esta sesión; la última verificación fue la del usuario durante la corrida de 12 h, sobre la imagen anterior. | Sin verificación del entorno real a evaluar no se inicia. |

Ninguno de estos motivos se resolvió "para conseguir que arranque": no se cambió de commit, no se descartó nada, no se modificó configuración ni red.

---

## 1. Hora real de inicio y finalización

- Puerta de entrada: inicio 2026-10-10T06:45Z aprox., fin 2026-10-10T06:50Z (UTC).
- Simulación: **no iniciada**. No hay hora de inicio ni de fin.

## 2. Duración efectiva

- Simulación: 0 s. Duración objetivo del encargo: 8 h.

## 3. Rama y commit evaluados

| Dato | Valor |
|---|---|
| Rama | `claude/algo-trading-simulation-platform-ngf7xo` |
| HEAD | `ab68d1c128a7181f54e1e79d3d7f37261365d821` |
| Árbol de trabajo | 15 archivos modificados, 9 sin seguimiento, nada commiteado |
| Huella del `git diff` (sha256, 16) | `d98ab6359eb3edfe`, idéntica antes y después de la puerta |
| Código evaluado por las suites | HEAD + cambios sin commit (Fase 1) |
| Código en ejecución en el VPS | imagen anterior a la Fase 1 (no verificable desde aquí) |

## 4. Confirmación del modo exclusivamente simulado

Configuración efectiva de este árbol, leída con `Settings()` sobre una lista blanca de campos no sensibles (no hay `.env` ni variables `TIA_*` en este entorno, de modo que rigen los valores por defecto del código):

| Campo | Valor efectivo |
|---|---|
| `mode` | `paper` |
| `is_simulation_only` | `True` |
| `live.enabled` | `False` |
| `live.use_testnet` | `True` |
| `live.max_live_capital` | `0.0` |
| `mm.enabled` / `mm.adaptive_enabled` / `mm.real_money` | `False` / `False` / `False` |
| `live.symbol` | `BTC-USD` |
| `live.risk_profile` | `conservative` |
| `live.scoreboard_policy` / `live.ev_evidence_policy` | `legacy` / `legacy` |
| `risk.max_trades_per_day` / `per_symbol_per_day` / `trade_cooldown_seconds` | 20 / 5 / 300 |
| `risk.daily_loss_limit_pct` / `max_drawdown_pct` | 2,0 % / 10,0 % |

Procesos: ningún proceso de Trader-IA, uvicorn ni Postgres en ejecución en este entorno; binario `docker` presente pero sin daemon; sin listeners en 8000 ni 5432. No se envió ninguna orden, real ni simulada. No se mostró, copió ni modificó ningún secreto.

Esta confirmación aplica al árbol de trabajo. **No** constituye verificación del modo del VPS en este momento.

## 5. Disponibilidad y calidad de los datos

| Destino | Resultado (timeout 5 s) |
|---|---|
| `https://api.binance.com/api/v3/time` | CONNECT 403 (denegación de política del proxy) |
| `https://api.binance.com/api/v3/klines?...` | CONNECT 403 |
| `https://data-api.binance.vision/api/v3/time` | CONNECT 403 |
| `https://stream.binance.com:9443/ws` | timeout |

Datos públicos reales: **no disponibles** desde este entorno. Fixtures locales en `data/fixtures` (BTC-USD 1m/1h, ETH-USD 1m, SPX-IDX 1m): **sintéticas**, no aptas para esta validación y no utilizadas.

## 6. Evaluaciones y señales por estrategia

Sin datos: la corrida no se ejecutó.

## 7. Rechazos por motivo

Sin datos: la corrida no se ejecutó.

## 8. Órdenes, fills, posiciones y round trips

Sin datos: la corrida no se ejecutó. Cero órdenes simuladas creadas.

## 9. P&L bruto, costos y P&L neto

Sin datos: la corrida no se ejecutó.

## 10. Errores, desconexiones e inconsistencias

- Ninguno atribuible a una corrida (no hubo corrida).
- Hallazgo de la puerta: denegación de red a los hosts públicos de Binance (ver §5). No es un error del proyecto; es la política de red del entorno.

## 11. Diferencias respecto del comportamiento esperado

- Se esperaba poder verificar el entorno de ejecución objetivo; el único despliegue (VPS) no es accesible desde esta sesión y ejecuta código anterior a la Fase 1.
- Se esperaba disponibilidad de datos públicos; el entorno los bloquea.
- Lint del repositorio completo (`ruff check .`): 6 avisos de orden de imports en `infra/migrations/` (archivos no tocados por la Fase 1). El alcance de lint del proyecto (`scripts/verify.sh`: `ruff check packages tests scripts`) pasa limpio. Se reporta por honestidad; no es un bloqueo de la puerta.

## 12. Limitaciones de la muestra

No hay muestra. Cualquier afirmación sobre actividad, rechazos, P&L o estabilidad operativa posterior a la Fase 1 sigue **sin evidencia empírica**.

## 13. Conclusiones operativas

1. La puerta de entrada cumplió su función: detectó que la corrida no podía garantizarse como segura, controlada y basada en datos reales, y no se inició.
2. El código de la Fase 1 sigue siendo verificable solo por sus pruebas (ver §15, suites) y por la revisión independiente ya entregada; su comportamiento en sesión real de 8 h permanece sin observar.
3. Para que la Fase 2 pueda ejecutarse hacen falta, como mínimo, decisiones que corresponden al usuario y que este encargo prohíbe tomar automáticamente:
   - Un host con egreso a los datos públicos de Binance y una base de datos en marcha (el VPS cumple ambas).
   - Que el código de la Fase 1 esté en ese host: requiere autorización explícita para commit, push, despliegue y reinicio del servicio (o, alternativamente, aceptar evaluar la imagen anterior, lo que no cumple el objetivo declarado).
   - Un operador que arranque (`POST /api/live/paper-start`) y detenga (`POST /api/live/stop`) la sesión a las 8 h, o un monitor supervisado como el usado en la corrida de 12 h, con los chequeos periódicos de la §5 del encargo.
   - Decidir **antes** de arrancar, y dejar constancia, el valor de `TIA_LIVE__EV_EVIDENCE_POLICY` (hoy `legacy`: el EV aprende también de filas sintéticas) y de `TIA_LIVE__SCOREBOARD_POLICY`. No es un cambio de parámetros de estrategia durante la corrida, pero sí una decisión del protocolo que debe quedar escrita.
4. Si se autoriza lo anterior, el protocolo de instrumentación y las consultas de solo lectura ya documentadas en `docs/PAPER_REALTIME_12H_FORENSIC_AUDIT.md` (§ protocolo de la próxima simulación) son directamente reutilizables.

## 14. Qué se puede concluir y qué no sobre la estrategia

- **Se puede concluir:** nada nuevo sobre la estrategia. Las suites confirman la aritmética del EV, las políticas de evidencia, el comportamiento del simulador y el armado de límites de frecuencia en pruebas controladas.
- **No se puede concluir:** rentabilidad, ventaja estadística, estabilidad operativa de 8 h, tasa de actividad tras las correcciones, ni comportamiento de los límites de riesgo en sesión continua. Nada en este informe respalda operar con dinero real.

## 15. Estado final de Git y procesos

| Ítem | Estado al cierre |
|---|---|
| Rama / HEAD | sin cambios: `claude/algo-trading-simulation-platform-ngf7xo` @ `ab68d1c` |
| Cambios sin commit de la Fase 1 | intactos (huella `d98ab6359eb3edfe`) |
| Archivos nuevos | los 9 de la Fase 1 + **este informe** (`docs/PAPER_VALIDATION_8H_PHASE2_GATE_REPORT.md`, sin seguimiento) |
| Commits / push / despliegue / reinicio | ninguno |
| Procesos iniciados | ninguno; no quedan procesos en segundo plano |
| Lint (alcance del proyecto) | `ruff check packages tests scripts`: All checks passed |
| Suite unitaria | 1232 passed, 69,66 s (Python 3.11.15, pytest 9.1.1) |
| Suite de integración | 163 passed, 78,65 s |

Las suites se ejecutaron sobre HEAD + cambios sin commit, con `PYTHONPATH=packages/tia/src`, sin red y sin base de datos externa.
