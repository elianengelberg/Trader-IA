"""Corrida SUPLEMENTARIA de R19 (no decide nada): misma prueba, mismos árboles y mismo aislamiento que la principal, con el
registrador pasivo registro_cola_r19.py en lugar de la sonda. Matriz reducida: árboles × K × park × réplicas, en orden
aleatorio con semilla fija. Uso: python r19_suplementario.py <plan_congelado.json> <salida_nueva> [K=0,8] [réplicas=3]"""
import json
import os
import pathlib
import random
import subprocess
import sys
import time

plan = json.load(open(sys.argv[1]))
out = pathlib.Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=False)
ks = [int(x) for x in (sys.argv[3] if len(sys.argv) > 3 else "0,8").split(",")]
reps = int(sys.argv[4]) if len(sys.argv) > 4 else 3
HERR = pathlib.Path(__file__).resolve().parent
corridas = [{"arbol": a, "K": k, "park": p, "rep": i} for a in plan["arboles"] for k in ks for p in plan["park"] for i in range(1, reps + 1)]
random.Random(20261023).shuffle(corridas)
(out / "orden.json").write_text(json.dumps(corridas, indent=0))
registro = open(out / "corridas.jsonl", "a")
for n, c in enumerate(corridas, 1):
    tag = f"{n:03d}_{c['arbol']}_K{c['K']}_park{c['park']}_r{c['rep']}"
    tmp = out / "tmp" / tag
    tmp.mkdir(parents=True)
    quemadores = [subprocess.Popen(["python3", "-c", "while True: pass"]) for _ in range(c["K"])]
    try:
        if quemadores:
            time.sleep(plan["calentamiento_s"])
        env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp), "LANG": "C.UTF-8", "TMPDIR": str(tmp),
               "PYTHONPATH": f"packages/tia/src:{HERR}", "PYTHONDONTWRITEBYTECODE": "1",
               "RC_OUT": str(out / f"{tag}.json"), "RC_PARK": str(c["park"])}
        cmd = ["unshare", "-n", "--", plan["python"], "-B", "-m", "pytest", "-p", "registro_cola_r19", "-p", "no:cacheprovider",
               "-o", "addopts=", "-q", "-rA", "--tb=short", plan["prueba"]]
        t0 = time.time()
        r = subprocess.run(cmd, cwd=plan["arboles"][c["arbol"]], env=env, capture_output=True, text=True, timeout=plan["limite_corrida_s"])
        seg = round(time.time() - t0, 2)
    finally:
        for q in quemadores:
            q.kill()
        for q in quemadores:
            q.wait()
    (out / f"{tag}.log").write_text(r.stdout + r.stderr)
    registro.write(json.dumps({**c, "n": n, "tag": tag, "rc": r.returncode, "seg": seg}) + "\n")
    registro.flush()
    print(f"{n:3d}/{len(corridas)} {tag} rc={r.returncode} {seg}s", flush=True)
print("FIN")
