# Runbook — Línea de base del journal de la cuenta paper

Procedimiento para el hallazgo del VPS: `AccountJournalRepository.rebuild()` devuelve
*journal 0 eventos / 0 fills* contra *5 filas en `fills`* (neto −0,276436, comisiones
16,993117), por lo que la reconstrucción de la cuenta queda **incompleta** y el runtime
rechaza nuevas entradas. Este documento explica la causa, cómo confirmarla con lecturas,
cómo repararla **sin borrar fills ni desactivar `cross_check`**, y cómo verificar antes de
arrancar la simulación de 12 h.

## 1. Causa raíz

| Hecho | Evidencia |
|---|---|
| El journal `account.*` existe desde el commit `1c914c5` (2026-10-11). | `git log --diff-filter=A -- packages/tia/src/tia/portfolio/account_journal.py` → `1c914c5`. |
| La imagen que corrió la sesión de 12 h en el VPS fue `ab68d1c` (2026-10-07). | `docs/PAPER_REALTIME_12H_REPORT.md`, encabezado. |
| En `ab68d1c` el runtime **no escribía ningún evento de cuenta**. | `git show ab68d1c:packages/tia/src/tia/api/state.py \| grep -c "account_event\|AccountJournal"` → `0`. |
| Antes del journal cada sesión arrancaba en capital base; una posición abierta al terminar la sesión nunca se cerraba en el registro. | `AppState.start_paper_realtime` previo a 1c914c5: `PaperExecutionProvider(..., initial_capital=capital)` sin `restore_portfolio`. |
| El cross-check compara eventos `account.fill` del journal con filas de `fills` de las runs `paper-live`; con 0 eventos y 5 filas, falla por diseño. | `tia/portfolio/account_journal.py::cross_check`; test `test_fill_rows_without_journal_events_are_an_inconsistent_account`. |

Conclusión: **no hay una escritura perdida ni un bug de transacción**. Las cinco filas son
historia de sesiones anteriores al journal (formato legacy: `fills` sin `account.*`). El
cross-check hace exactamente lo que debe: no da por buena una cuenta cuyo registro no
explica sus fills. Lo que falta es una declaración explícita de dónde empieza el registro.

Sobre la pregunta "¿journal y fills comparten transacción?": no. `_save("fill")` y
`_journal_fill → _save("account_event")` son dos escrituras en dos sesiones de base de
datos distintas, secuenciadas por la cola de persistencia. Es una limitación conocida y
documentada en `cross_check` ("may disagree only when one write was lost"): la pérdida de
una de las dos se **detecta** (reconstrucción incompleta), no se previene. No es la causa
de este caso (0 eventos de cualquier tipo en todas las runs).

## 2. Lecturas de confirmación (solo lectura, sin secretos)

Desde `/home/tia/Trader-IA`. `psql` dentro del contenedor usa el socket local; no imprime
ni requiere la contraseña.

```bash
PSQL='docker compose -f docker-compose.prod.yml exec -T postgres psql -U tia -d tia -At -c'

# 2.1 Runs que comparten la cuenta
$PSQL "SELECT run_id, mode, scenario, started_at, stopped_at FROM runs WHERE mode IN ('paper-live','live') ORDER BY started_at;"

# 2.2 Los fills, con su run (ids, fechas, lado, cantidad, fee, símbolo)
$PSQL "SELECT f.fill_id, f.run_id, r.mode, f.symbol, f.side, f.quantity, f.price, f.fee, f.liquidity, f.filled_at
       FROM fills f JOIN runs r ON r.run_id = f.run_id ORDER BY f.filled_at;"

# 2.3 Eventos account.* por run (esperado: ninguna fila)
$PSQL "SELECT run_id, event_type, COUNT(*) FROM events WHERE event_type LIKE 'account.%' GROUP BY 1,2 ORDER BY 1,2;"

# 2.4 Qué otros eventos dejaron esas runs (prueba de que sí persistían, pero sin journal de cuenta)
$PSQL "SELECT run_id, event_type, COUNT(*), MIN(occurred_at), MAX(occurred_at) FROM events GROUP BY 1,2 ORDER BY 1,2;"

# 2.5 Neto y comisiones por run y símbolo (debe reproducir −0.276436 / 16.993117 en paper-live)
$PSQL "SELECT f.run_id, f.symbol, COUNT(*), SUM(CASE WHEN f.side='buy' THEN f.quantity ELSE -f.quantity END) AS net, SUM(f.fee) AS fees
       FROM fills f JOIN runs r ON r.run_id = f.run_id WHERE r.mode='paper-live' GROUP BY 1,2;"
```

Qué esperar y qué significa:

- **Si el backup cuenta 7 filas en `fills` y el rebuild decía 5**: el rebuild cuenta solo
  los fills de runs `paper-live` del símbolo de la cuenta; el bloque `COPY public.fills`
  del dump tiene *todas* las filas de la tabla, incluidas las de runs de escenario
  (`mode` distinto de `paper-live`), de otro símbolo o de un `mode` `live`. La consulta
  2.2 (con `r.mode` y `f.symbol`) debe explicar cada fila sobrante. Si las 7 fueran
  `paper-live` + `BTC-USD`, es que una sesión siguió operando entre el diagnóstico y el
  backup: el baseline fijará el conjunto **tal como esté al aplicarlo** (el dry-run lo
  lista entero), y la sesión debe estar detenida antes (el script lo exige).
- 2.3 vacío + 2.2 con 5 filas `paper-live` → formato legacy confirmado.
- **Marks o plans en 2.3 sin fills**: el backend nuevo reanuda cualquier run `paper-live`
  sin `stopped_at` y escribe `account.mark` por barra aunque la cuenta no esté verificada.
  No mueven caja ni posición: el baseline los omite y los reporta
  (`events_before_baseline`). Solo `account.fill` y `account.adjustment` anteriores al
  baseline lo rechazan.
- Si 2.5 muestra el neto −0,276436 concentrado en **un fill de venta sin su cierre**, es una
  pierna que la sesión antigua dejó abierta al terminar y que, por diseño de esa época, la
  siguiente sesión no heredó. Nunca existió como posición después de ese reinicio.
- Si en 2.2 aparecen fills de runs `live` o de otro símbolo, el runtime **no los cuenta**
  (`_load_account_restore` usa `modes=("paper-live",)` y filtra por `live.symbol`); el
  número del rebuild manual puede diferir del del runtime si se llamó con los modos por
  defecto (`paper-live` y `live`).

## 3. Reparación elegida: línea de base (`account.baseline`)

Opciones evaluadas:

| Opción | Veredicto |
|---|---|
| Borrar los 5 fills | **Descartada**: destruye historia; prohibido por mandato. |
| Desactivar o relajar `cross_check` | **Descartada**: pierde la detección de escrituras perdidas, que es su razón de existir. |
| Rellenar `account.fill` a partir de las filas de `fills` | **Descartada**: fabrica un registro que la sesión antigua nunca tuvo y resucita un corto de 0,276 BTC sin plan ni creencias, que el runtime adoptaría como posición "gestionable" y bloquearía entradas igualmente. |
| **Evento `account.baseline` escrito por el operador** | **Elegida**: declara en el propio journal dónde empieza el registro; los fills anteriores quedan **apartados, no borrados**, y el evento fija (*pin*) cuántos eran, su neto y sus comisiones. |

Propiedades del fix (código en `1c914c5` + este cambio):

- El runtime **nunca** escribe un baseline; solo lo hace `scripts/account_baseline.py`
  (o `AccountJournalRepository.open_baseline`) a mano, con dry-run por defecto.
- Un baseline solo puede **abrir** un journal: si lo precede cualquier evento que mueva
  la cuenta (`account.fill` del símbolo o `account.adjustment`), la reconstrucción queda
  incompleta con el error "a baseline may open an account's record, never rewrite it".
  Dos baselines también la dejan incompleta. No sirve para ocultar pérdidas de una cuenta
  que ya tiene registro. Los `account.mark` y `account.plan` anteriores (una sesión que
  corrió sobre la cuenta sin verificar) no mueven nada: se omiten y se cuentan en
  `checks.events_before_baseline`.
- `cross_check` sigue activo para **todos** los fills desde el baseline en adelante.
- Los fills anteriores al baseline se comparan con lo fijado en el evento
  (`check_baseline`): si aparece o desaparece una fila fechada antes del baseline, la
  reconstrucción queda incompleta ("legacy record disagrees with its baseline").
- Todo queda visible en `/api/live` → `account_state.restore.checks`
  (`legacy_fills_excluded`, `legacy_net_quantity_table`, `legacy_fees_table`, `baseline_at`).
- Idempotente por símbolo (`idempotency_key = account.baseline:<símbolo>`): repetir el
  comando no crea un segundo baseline. El test
  `test_fill_rows_without_journal_events_are_an_inconsistent_account` sigue vigente sin
  cambios.

Consecuencia contable, dicha explícitamente: la cuenta paper abre su registro en capital
base (10 000 USD). Las pérdidas de los dos trades de la sesión del 7 de octubre
(−2,09 y −2,35 USD) siguen en `edge_outcomes` como evidencia para el scoreboard, pero no
como caja: es exactamente lo que hacía el runtime de esa época en cada arranque.

## 4. Procedimiento

Con la imagen construida desde `f25d485` o posterior desplegada (el script y el código
nuevo viven en la imagen: `COPY scripts/`, `COPY packages/`). Ninguna sesión paper debe
estar corriendo (el script lo comprueba: una run sin `stopped_at` lo hace rechazar).
Atención al arranque del backend nuevo: si la base tenía una run `paper-live` sin
`stopped_at`, el backend la **reanuda** solo (con la cuenta sin verificar y las entradas
bloqueadas). Antes del baseline hay que detenerla por la vía oficial:

```bash
# ¿quedó algo reanudado?
$PSQL "SELECT run_id, started_at, notes FROM runs WHERE mode='paper-live' AND stopped_at IS NULL;"
# detenerla (sesión de operador con cookie)
curl -s -b cookie.txt -X POST https://<host>/api/live/stop
```

### 4.1 Backup verificado (antes de cualquier escritura)

```bash
cd /home/tia/Trader-IA
bash scripts/backup.sh                     # PASS  postgres dump ...: backups/tia-<stamp>.sql.gz
F=$(ls -1t backups/tia-*.sql.gz | head -1)
gzip -t "$F" && echo "gzip OK"             # integridad del archivo
zcat "$F" | grep -c "^COPY public.fills "   # 1: la tabla fills está en el dump
zcat "$F" | sed -n '/^COPY public.fills /,/^\\\./p' | grep -vc "^COPY\|^\\\." # filas de TODA la tabla fills (7 en el VPS: ver §2, no solo las 5 de la cuenta)
zcat "$F" | grep -c "^COPY public.events "  # 1
```

Verificación fuerte (opcional, recomendable): restaurar en una base temporal del mismo
servidor y contar.

```bash
docker compose -f docker-compose.prod.yml exec -T postgres createdb -U tia tia_verify
zcat "$F" | docker compose -f docker-compose.prod.yml exec -T postgres psql -q -U tia -d tia_verify
docker compose -f docker-compose.prod.yml exec -T postgres psql -U tia -d tia_verify -At -c "SELECT COUNT(*) FROM fills;"   # igual al conteo del dump (7)
docker compose -f docker-compose.prod.yml exec -T postgres psql -U tia -d tia_verify -At -c "SELECT r.mode, f.symbol, COUNT(*) FROM fills f JOIN runs r ON r.run_id=f.run_id GROUP BY 1,2;"
docker compose -f docker-compose.prod.yml exec -T postgres dropdb -U tia tia_verify   # solo la base temporal
```

Copiar el dump fuera de la máquina (`docs/DEPLOYMENT.md` §10). No seguir si algún paso falla.

### 4.2 Dry run

```bash
docker compose -f docker-compose.prod.yml exec -T backend python scripts/account_baseline.py
```

Muestra: rebuild actual (incompleto), runs, eventos `account.*` (0), los 5 fills con run,
lado, cantidad, precio, fee y fecha, y el evento que **escribiría** (rolled back). Si
imprime `REFUSED`, atender el motivo (sesión no detenida, journal con eventos, fill
posterior a la hora del baseline) y no forzar.

### 4.3 Aplicar

```bash
docker compose -f docker-compose.prod.yml exec -T backend python scripts/account_baseline.py \
  --apply --actor "<operador>" \
  --reason "fills de sesiones anteriores al journal (imagen ab68d1c); cada sesión arrancaba en capital base"
```

Salida esperada: `Written: {...}` con `legacy_fills: 5`, `legacy_net_quantity: -0.276436`,
`legacy_fees: 16.993117`, y `PASS  complete` con `checks.fills_in_table: 0`,
`checks.legacy_fills_excluded: 5`. Código de salida 0.

### 4.4 Verificar en la API antes de arrancar

```bash
# sesión de operador: POST /api/auth/login (cookie) → luego
curl -s -b cookie.txt https://<host>/api/live | python3 -c 'import json,sys; s=json.load(sys.stdin); a=s.get("account_state") or {}; print(a.get("verified"), (a.get("restore") or {}).get("checks"))'
```

Debe mostrar `verified: True`, `fills_in_table == fills_in_journal == 0`,
`legacy_fills_excluded == 5`, `baseline_at` con la hora aplicada. Después, recién
entonces, `POST /api/live/paper-start?max_hours=12` por el mecanismo oficial.

## 5. Reversión

El único cambio de datos es **una fila** en `events` (`event_type='account.baseline'`,
`idempotency_key='account.baseline:<símbolo>'`, `source='operator'`). Revertir es borrar esa
fila, decisión explícita del operador y nunca automática; con el dump de §4.1 la base
completa es recuperable. El código tolera ambas situaciones: sin baseline, el cross-check
vuelve a marcar la cuenta como inconsistente, que es la verdad del registro.

## 6. Tests de regresión añadidos

- `tests/unit/test_account_journal.py`: el baseline abre en capital base en su día; los
  eventos posteriores pliegan igual que sin baseline; un baseline tras un evento plegado
  se rechaza sin ocultar el fill; un segundo baseline se rechaza; otro símbolo no abre
  nada; `check_baseline` fija el conjunto legacy; los errores se acumulan.
- `tests/integration/test_account_restore.py`: el caso del VPS de punta a punta (5 fills
  legacy → incompleto → baseline → completo, plano, en capital base, con los 5 fills
  visibles y un fill perdido posterior todavía detectado); un runtime arranca
  desbloqueado y plano; el conjunto legacy no puede crecer en silencio; el baseline
  rechaza un journal con registro; condiciones previas (fills, sesión detenida, hora,
  motivo) e idempotencia.
- `tests/integration/test_account_baseline_cli.py`: dry-run sin escribir, apply, rechazo
  sin escribir, base ilegible → código 2, URL sin contraseña.
