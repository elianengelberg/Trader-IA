"""Ensayo FUNCIONAL de sim1.py con velas SINTÉTICAS (generador de E1). No es evidencia de nada económico.
Sustituye la lectura de datos por series sintéticas y el candado por uno temporal. Uso: python -B ensayo_sintetico_sim1.py <dir>"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import e1_comun as C
import sim1
import sim1_comun as S

N = 4000


def _falsas(raices, simbolo):
    v = C.sinteticas(N, 11 if simbolo == "BTCUSDT" else 23, t0=datetime(2022, 8, 1, tzinfo=timezone.utc))
    v = [x.model_copy(update={"symbol": simbolo, "provider": "SINTETICO"}) for x in v]
    return v, {"simbolo": simbolo, "fuente": "SINTÉTICO"}


S.leer_velas = _falsas
sim1.B, sim1.R = 500, 200
sim1.CONFIGS = {"P3": sim1.CONFIGS["P3"], "S1": sim1.CONFIGS["S1"]}  # ensayo reducido
sim1.VARIANTES = {k: v for k, v in sim1.VARIANTES.items() if k in ("", "S2|", "S4|")}
d = Path(sys.argv[1])
sim1.CANDADO = d / "CANDADO_ENSAYO.txt"
(d / "dev").mkdir(parents=True)
sim1.main_dev(d / "dev")
(d / "final").mkdir()
sim1.main_final(d / "final", d / "dev" / "m1_promocion.json")
try:
    sim1.main_final(d / "final2", d / "dev" / "m1_promocion.json")
    print("ERROR: el candado no impidió una segunda lectura")
except FileExistsError:
    print("OK: el candado impide una segunda lectura")
