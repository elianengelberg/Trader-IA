"""TI · Experimento de poder de detección: mutantes dirigidos a la lógica que protege el capital (stop protector,
re-protección, cierre de emergencia, kill switch, completitud de la persistencia, adaptador de Binance, compuerta).

Cada mutante reemplaza UNA cadena que debe aparecer exactamente una vez; se corre el subconjunto de pruebas que importa el
vivo, el adaptador o la compuerta (lista en el argumento 3), con -x; se restaura el archivo y se verifica su sha256.
«Muerto» = alguna prueba falla; «vivo» = todas pasan (hueco de detección). Los mutantes se fijaron ANTES de correr y
describen defectos plausibles (algunos son exactamente defectos ya encontrados: R25, R18, R19, N1).
Uso: python -I exp_mutacion.py <clon_desechable> <python> <lista_de_pruebas.txt> <salida.json> [ids,...]"""
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

clon, py, lista, salida = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
SOLO = set(sys.argv[5].split(",")) if len(sys.argv) > 5 else None
LIVE = "packages/tia/src/tia/runtime/live.py"
BIN = "packages/tia/src/tia/data/providers/binance_live.py"
GATE = "packages/tia/src/tia/api/gate_probes.py"

MUTANTES = [
    ("M01", LIVE, "dos stops si la cancelación no se confirma",
     "if not await self._cancel_protective():\n                    # The venue did not confirm the cancel",
     "if False:\n                    # The venue did not confirm the cancel"),
    ("M02", LIVE, "segundo stop cuando el venue no sabe del primero",
     "if self._protective is not None and self._protective.get(\"order_id\"):\n                    # The venue could not say",
     "if False:\n                    # The venue could not say"),
    ("M03", LIVE, "no esperar al stop de respuesta perdida",
     "if not await self._settle_unknown_stop():\n                # The venue still cannot say",
     "if False:\n                # The venue still cannot say"),
    ("M04", LIVE, "ignorar el cambio de cantidad (stop más chico que la posición)",
     "if same_size and same_level:", "if same_level:"),
    ("M05", LIVE, "rechazo del stop en silencio (R25 original)",
     "self._protection_lost(f\"protective stop refused: {str(exc)[:300]}\")", "pass"),
    ("M06", LIVE, "stop rechazado tomado como protección",
     "if order.state.is_terminal and not order.fills:\n            _log.warning(\n                \"protective_stop_rejected\",",
     "if False:\n            _log.warning(\n                \"protective_stop_rejected\","),
    ("M07", LIVE, "stop protector sin reduce_only",
     "            reduce_only=True,\n        )\n        try:\n            order = await self._execution.submit_order(intent)\n        except ReconciliationError as exc:\n            # The request left",
     "            reduce_only=False,\n        )\n        try:\n            order = await self._execution.submit_order(intent)\n        except ReconciliationError as exc:\n            # The request left"),
    ("M08", LIVE, "stop del lado equivocado",
     "side = Side.SELL if position_quantity > 0 else Side.BUY\n        self._stop_placements += 1",
     "side = Side.BUY if position_quantity > 0 else Side.SELL\n        self._stop_placements += 1"),
    ("M09", LIVE, "redondeo del nivel hacia el lado que agranda la pérdida",
     "return float(quantize_price_passive(stop_price, tick, buy=not long))",
     "return float(quantize_price_passive(stop_price, tick, buy=long))"),
    ("M10", LIVE, "re-protección sin mirar si el estado admite órdenes reductoras",
     "if not self.machine.state.accepts_reducing_orders:\n            self._protection_lost(",
     "if False:\n            self._protection_lost("),
    ("M11", LIVE, "sin re-protección tras un cierre que no trabaja (R18)",
     "await self._reprotect(f\"exit ({reason}) not working\")", "pass"),
    ("M12", LIVE, "sin re-protección tras un cierre no enviado (R18)",
     "await self._reprotect(f\"exit ({reason}) not sent\")  # the stop is gone (R18)", "pass"),
    ("M13", LIVE, "sin re-protección de la posición restaurada al arrancar (N5)",
     "await self._protect_restored_position()", "pass"),
    ("M14", LIVE, "más de un stop en reposo al reiniciar sin bloquear",
     "if len(resting) > 1:", "if len(resting) > 2:"),
    ("M15", LIVE, "flush «completo» con escrituras fallidas (R19)",
     "return not self._persist_in_flight and self._persist_counts[\"failed\"] == 0", "return not self._persist_in_flight"),
    ("M16", LIVE, "cierre de emergencia a mercado encima de un stop que puede seguir en reposo",
     "                and protective is not None\n                and protective.get(\"order_id\")\n            ):",
     "                and protective is not None\n                and False\n            ):"),
    ("M17", LIVE, "cancelar todo olvida órdenes cuya cancelación no se confirmó",
     "if await self._cancel(ref, purpose=\"cancel all\") is not None:", "if True:"),
    ("M18", LIVE, "estado desconocido sin detener las entradas",
     "self.halt_new_orders(reason=f\"unknown order state: {exc}\")", "pass"),
    ("M19", BIN, "error de transporte después de enviar tomado como no enviado (N1)",
     "if method != \"GET\" and not isinstance(exc, _NOT_SENT):", "if False:"),
    ("M20", BIN, "timeInForce enviado con STOP_LOSS",
     "_NO_TIME_IN_FORCE = frozenset({OrderType.MARKET, OrderType.LIMIT_MAKER, OrderType.STOP})",
     "_NO_TIME_IN_FORCE = frozenset({OrderType.MARKET, OrderType.LIMIT_MAKER})"),
    ("M21", GATE, "la compuerta no exige el stop aceptado en testnet (R25)",
     "if record.facts.get(\"protective_stop_accepted\") is not True:", "if False:"),
    ("M22", LIVE, "posición desprotegida sin detener órdenes nuevas",
     "self.halt_new_orders(reason=\"open position without a confirmed protective stop\")", "pass"),
]

pruebas = [x for x in lista.read_text().split() if x]
filas = []
for mid, rel, desc, viejo, nuevo in MUTANTES:
    if SOLO and mid not in SOLO:
        continue
    p = clon / rel
    orig = p.read_bytes()
    sha = hashlib.sha256(orig).hexdigest()
    texto = orig.decode()
    n = texto.count(viejo)
    if n != 1:
        filas.append({"id": mid, "archivo": rel, "descripcion": desc, "resultado": f"NO_APLICA (aparece {n} veces)"})
        print(filas[-1], flush=True)
        continue
    p.write_text(texto.replace(viejo, nuevo))
    t0 = time.time()
    try:
        r = subprocess.run([py, "-m", "pytest", *pruebas, "-x", "-q", "-p", "no:cacheprovider"], cwd=clon,
                           env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "packages/tia/src", "HOME": "/root"},
                           capture_output=True, text=True, timeout=1500)
        rc, out = r.returncode, r.stdout
    except subprocess.TimeoutExpired:
        rc, out = -9, "timeout"
    finally:
        p.write_bytes(orig)
    assert hashlib.sha256(p.read_bytes()).hexdigest() == sha
    fallida = next((ln for ln in out.splitlines() if ln.startswith(("FAILED", "ERROR"))), "")
    filas.append({"id": mid, "archivo": rel, "descripcion": desc, "rc": rc,
                  "resultado": "MUERTO" if rc not in (0, -9) else ("VIVO" if rc == 0 else "TIMEOUT"),
                  "primera_falla": fallida[:220], "segundos": round(time.time() - t0, 1)})
    print(json.dumps(filas[-1], ensure_ascii=False), flush=True)
json.dump({"pruebas": pruebas, "mutantes": filas}, open(salida, "w"), indent=1, ensure_ascii=False)
vivos = [f["id"] for f in filas if f.get("resultado") == "VIVO"]
print(f"RESULTADO: {sum(f.get('resultado') == 'MUERTO' for f in filas)} muertos, {len(vivos)} vivos {vivos}, "
      f"{sum(str(f.get('resultado','')).startswith('NO_APLICA') for f in filas)} no aplican")
