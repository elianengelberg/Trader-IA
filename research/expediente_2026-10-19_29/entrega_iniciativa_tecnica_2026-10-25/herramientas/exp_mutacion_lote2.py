"""TI · Lote 2 de mutación (medida NO contaminada): mutantes fijados ANTES de correr, sobre lógica que protege el capital
y que este ciclo NO tocó ni para la que escribió pruebas (frenos de riesgo, reglas de salida, regla de EV, permisos de
estado). El lote 1 (M01–M22) dejó de ser una medida independiente en cuanto se escribieron pruebas para sus
sobrevivientes; este lote mide la suite tal como está, contra defectos que nadie miró al escribirla.
Mismo procedimiento que exp_mutacion.py (una cadena, exactamente una vez, -x, restauración verificada por sha256), pero
contra la suite COMPLETA (argumento 3: un archivo que dice «tests»).
Uso: python -I exp_mutacion_lote2.py <clon_desechable> <python> <lista_de_pruebas.txt> <salida.json> [ids,...]"""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

clon, py, lista, salida = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
SOLO = set(sys.argv[5].split(",")) if len(sys.argv) > 5 else None

RISK, EXITS, EV, STATES = "packages/tia/src/tia/risk/engine.py", "packages/tia/src/tia/execution/exits.py", "packages/tia/src/tia/economics/expected_value.py", "packages/tia/src/tia/runtime/states.py"
MUTANTES = [
    ("M23", RISK, "el freno de drawdown nunca salta",
     "dd_ok = drawdown < self._limits.max_drawdown_pct", "dd_ok = True"),
    ("M24", RISK, "el freno de drawdown rechaza la señal pero no pone el sistema en modo seguro",
     "            self.enter_safe_mode(self._state.breaker_reason)\n            reasons.append(self._state.breaker_reason)",
     "            reasons.append(self._state.breaker_reason)"),
    ("M25", RISK, "el límite de pérdida diaria nunca bloquea",
     "daily_ok = day_pnl > -self._limits.daily_loss_limit_pct", "daily_ok = True"),
    ("M26", EXITS, "la regla de salida puede aflojar el stop (falta «solo más ajustado»)",
     "if improvement <= entry_price * MIN_STOP_MOVE_PCT / 100.0:", "if improvement == 0.0:"),
    ("M27", EXITS, "el stop puede quedar del otro lado del último cierre",
     "level = min(level, last_close - inside) if long else max(level, last_close + inside)", "level = level"),
    ("M28", EXITS, "se elige el candidato más flojo en vez del más ajustado",
     "level, kind, reason = max(candidates, key=lambda c: c[0]) if long else min(",
     "level, kind, reason = min(candidates, key=lambda c: c[0]) if long else max("),
    ("M29", EV, "sin encogimiento por error estándar",
     "discount = shrink_se * standard_error", "discount = 0.0"),
    ("M30", EV, "un costo desconocido no impide operar",
     "            and self.costs.complete\n", "            and True\n"),
    ("M31", EV, "se ignora el techo de la razón de costos",
     "if result.is_tradeable and result.cost_ratio > self.max_cost_ratio:", "if False:"),
    ("M32", STATES, "HALT_NEW_ORDERS no admite órdenes que reducen (no se puede cerrar ni proteger)",
     "            LiveState.HALT_NEW_ORDERS,\n            LiveState.CANCEL_ONLY,", "            LiveState.CANCEL_ONLY,"),
    ("M33", EV, "muestra mínima de 3 en vez de 30",
     "MIN_SAMPLES_FOR_EDGE = 30", "MIN_SAMPLES_FOR_EDGE = 3"),
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
