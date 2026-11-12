"""Corre la matriz de p2b_handler_con_hilos.py y registra el código de salida de cada caso (−N = muerto por la señal N).
Lo uso en lugar de un bucle de bash porque bash aborta el bucle cuando un hijo muere por SIGINT.
Uso: python3 -I -B correr_p2b.py <python_del_venv> <dir_tmp_base>"""
import os
import subprocess
import sys
import tempfile

aqui = os.path.dirname(os.path.abspath(__file__))
py, base = sys.argv[1], sys.argv[2]
for variante in ("handler_numpy", "handler_hilo_previo"):
    for senal in ("SIGINT", "SIGTERM"):
        for origen in ("interna", "externa"):
            d = tempfile.mkdtemp(dir=base)
            r = subprocess.run([py, "-I", "-B", os.path.join(aqui, "p2b_handler_con_hilos.py"), variante, senal, origen, d],
                               capture_output=True, text=True, timeout=60)
            print(f"## {variante} {senal} {origen}")
            print(r.stdout.strip())
            if r.stderr.strip():
                print("stderr (última línea):", r.stderr.strip().splitlines()[-1])
            print(f"returncode={r.returncode}", flush=True)
