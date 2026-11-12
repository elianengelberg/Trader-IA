"""Construye los árboles T16..T22 de la iniciativa técnica sobre T15 y escribe los parches 16..22, en el clon dev, con un
índice temporal (el índice del clon no se toca). Verifica que el último árbol sea exactamente el árbol de trabajo de dev.
live.py.L1 es live.py en T16 y live.py.L2 en T17..T20 (T21 y T22 toman el de dev).
Uso: python -I cadena_TI.py <dev> <dir_versiones_intermedias> <dir_parches> <dir_registro>"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

dev, W, P, R = (Path(a) for a in sys.argv[1:5])
LIVE = "packages/tia/src/tia/runtime/live.py"
STATE = "packages/tia/src/tia/api/state.py"
PASOS = [
    ("16_TI_controles_de_emergencia_conservan_la_proteccion", {LIVE: W / "live.py.L1"},
     ["tests/integration/test_order_integrity.py", "tests/integration/test_emergency_controls_protection.py"]),
    ("17_TI_compuerta_de_evidencia_real", {LIVE: W / "live.py.L2"},
     ["packages/tia/src/tia/api/gate_probes.py", "tests/integration/test_edge_evidence_gate.py"]),
    ("18_TI_metricas_de_la_sesion_24x7", {STATE: W / "state.py.S1"}, ["tests/integration/test_live_metrics.py"]),
    ("19_TI_contrato_de_persistencia_y_alertas", {},
     [STATE, "packages/tia/src/tia/runtime/engine.py", "tests/integration/test_session_persistence_contract.py",
      "tests/integration/test_scenario_engine_persistence.py", "tests/integration/test_live_api.py",
      "tests/integration/test_alert_delivery.py"]),
    ("20_TI_pruebas_que_cierran_huecos_de_deteccion", {},
     ["tests/integration/test_protective_stop_contract.py", "tests/integration/test_unknown_entry_halts_entries.py"]),
    ("21_TI_watchdog_al_reanudar_tras_una_pausa", {}, [LIVE, "tests/integration/test_watchdog_after_standing.py"]),
    ("22_TI_documentacion_del_kill_switch", {}, ["docs/LIVE_RUNBOOK.md", "docs/DEPLOYMENT.md"]),
]


def git(*args, env=None, inp=None):
    return subprocess.run(["git", *args], cwd=dev, env=env, input=inp, capture_output=True, text=True, check=True).stdout.strip()


with tempfile.TemporaryDirectory() as tmp:
    env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / "index"))
    previo = (R / "T15.txt").read_text().strip()
    git("read-tree", previo, env=env)
    for nombre, versiones, desde_dev in PASOS:
        for ruta, fuente in versiones.items():
            blob = git("hash-object", "-w", str(fuente))
            git("update-index", "--add", "--cacheinfo", f"100644,{blob},{ruta}", env=env)
        for ruta in desde_dev:
            blob = git("hash-object", "-w", str(dev / ruta))
            git("update-index", "--add", "--cacheinfo", f"100644,{blob},{ruta}", env=env)
        arbol = git("write-tree", env=env)
        parche = subprocess.run(["git", "diff", "--binary", previo, arbol], cwd=dev, capture_output=True, text=True,
                                check=True).stdout
        (P / f"{nombre}.patch").write_text(parche)
        (R / f"T{nombre[:2]}.txt").write_text(arbol + "\n")
        print(f"{nombre}: {arbol} · {len(parche.splitlines())} líneas · archivos {git('diff', '--name-only', previo, arbol).split()}")
        previo = arbol
with tempfile.TemporaryDirectory() as tmp:
    env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / "index"))
    git("read-tree", "HEAD", env=env)
    git("add", "-A", env=env)
    trabajo = git("write-tree", env=env)
print(f"árbol de trabajo de dev: {trabajo} · {'COINCIDE con T22' if trabajo == previo else 'DISTINTO de T22'}")
