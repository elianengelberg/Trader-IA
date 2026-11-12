"""Construye los árboles T23..T25 de la misión de dirección técnica sobre T22 y escribe los parches 23..25, en el clon dev,
con un índice temporal (el índice del clon no se toca). Verifica que T25 sea exactamente el árbol de trabajo de dev.
live.py.L4 (live.py antes de la corrección del lote del stop) es live.py en T24; T25 toma el de dev.
Uso: python -I cadena_DT.py <dev> <dir_parches> <dir_registro>"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

dev, P, R = (Path(a) for a in sys.argv[1:4])
LIVE = "packages/tia/src/tia/runtime/live.py"
L4 = Path(__file__).resolve().parent.parent / "trabajo" / "cadena_TI" / "live.py.L4_antes_lote_del_stop"
PASOS = [
    ("23_DT_una_sola_sesion_viva_por_cuenta_entre_procesos",
     ["packages/tia/src/tia/api/state.py", "tests/integration/test_live_session_lease.py"]),
    ("24_DT_un_resto_menor_que_un_lote_no_es_una_posicion",
     [("LIVE", L4), "tests/integration/test_dust_is_not_a_position.py"]),
    ("25_DT_el_stop_cubre_los_lotes_enteros_que_hay_en_la_cuenta",
     [LIVE, "tests/integration/test_stop_quantity_on_the_lot_grid.py"]),
]


def git(*args, env=None):
    return subprocess.run(["git", *args], cwd=dev, env=env, capture_output=True, text=True, check=True).stdout.strip()


with tempfile.TemporaryDirectory() as tmp:
    env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / "index"))
    previo = (R / "T22.txt").read_text().strip()
    git("read-tree", previo, env=env)
    for nombre, desde_dev in PASOS:
        for ruta in desde_dev:
            ruta, fuente = (LIVE, ruta[1]) if isinstance(ruta, tuple) else (ruta, dev / ruta)
            blob = git("hash-object", "-w", str(fuente))
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
print(f"árbol de trabajo de dev: {trabajo} · {'COINCIDE con T25' if trabajo == previo else 'DISTINTO de T25'}")
