"""Ejecuta la matriz congelada de R19 (PLAN_R19 + enmienda 1). No toca ningún repositorio: lee los árboles del plan y
escribe solo en <salida>. Cada corrida de pytest va con `unshare -n` (sin red: solo la interfaz lo) y con un entorno
mínimo (sin credenciales ni proxies). Los quemadores de CPU se crean por corrida y se matan siempre.
Uso: python r19_experimento.py <plan.json> <salida_nueva>"""
import json
import os
import pathlib
import random
import resource
import subprocess
import sys
import time

plan = json.load(open(sys.argv[1]))
out = pathlib.Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=False)
HERR = pathlib.Path(__file__).resolve().parent


def ejecutables():
    """Procesos ejecutables en este instante (/proc/loadavg, 4.º campo): refleja los quemadores enseguida; el promedio de
    1 minuto tarda en subir y no sirve para comprobar la carga de una corrida corta."""
    return int(open("/proc/loadavg").read().split()[3].split("/")[0])

corridas = []
for arbol in plan["arboles"]:
    for k in plan["K"]:
        for park in plan["park"]:
            corridas += [{"arbol": arbol, "K": k, "park": park, "sel": "prueba", "rep": i} for i in range(1, plan["N"] + 1)]
            corridas += [{"arbol": arbol, "K": k, "park": park, "sel": "modulo", "rep": i} for i in range(1, plan["N_modulo"] + 1)]
random.Random(plan["semilla_orden"]).shuffle(corridas)
(out / "orden.json").write_text(json.dumps(corridas, indent=0))

registro = open(out / "corridas.jsonl", "a")
for n, c in enumerate(corridas, 1):
    tag = f"{n:03d}_{c['arbol']}_K{c['K']}_park{c['park']}_{c['sel']}{c['rep']}"
    j, log, tmp = out / f"{tag}.json", out / f"{tag}.log", out / "tmp" / tag
    tmp.mkdir(parents=True)
    carga_antes, ejec_antes = os.getloadavg(), ejecutables()
    quemadores = [subprocess.Popen(["python3", "-c", "while True: pass"]) for _ in range(c["K"])]
    try:
        if quemadores:
            time.sleep(plan["calentamiento_s"])
        carga_con_quemadores, ejec_con_quemadores = os.getloadavg(), ejecutables()
        env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp), "LANG": "C.UTF-8", "TMPDIR": str(tmp),
               "PYTHONPATH": f"packages/tia/src:{HERR}", "PYTHONDONTWRITEBYTECODE": "1", "R19_OUT": str(j),
               "R19_PARK": str(c["park"]), "R19_EXTRA": str(plan["extra_s"]), "R19_EXTRA2": str(plan["extra2_s"])}
        sel = plan["prueba"] if c["sel"] == "prueba" else plan["modulo"]
        cmd = ["unshare", "-n", "--", plan["python"], "-B", "-m", "pytest", "-p", "sonda_r19_v2", "-p", "no:cacheprovider",
               "-o", "addopts=", "-q", "-rA", "--tb=short", sel]
        t0, ru0 = time.time(), resource.getrusage(resource.RUSAGE_CHILDREN)
        try:
            r = subprocess.run(cmd, cwd=plan["arboles"][c["arbol"]], env=env, capture_output=True, text=True,
                               timeout=plan["limite_corrida_s"])
            rc, salida = r.returncode, r.stdout + r.stderr
        except subprocess.TimeoutExpired as exc:
            rc = "limite"
            salida = (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        seg = round(time.time() - t0, 2)
        ru1 = resource.getrusage(resource.RUSAGE_CHILDREN)  # antes de esperar a los quemadores: solo pytest
        cpu_pytest = round((ru1.ru_utime - ru0.ru_utime) + (ru1.ru_stime - ru0.ru_stime), 2)
    finally:
        for q in quemadores:
            q.kill()
        for q in quemadores:
            q.wait()
    log.write_text(salida)
    fila = {**c, "n": n, "tag": tag, "rc": rc, "seg": seg, "inicio_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0)),
            "carga_antes": carga_antes, "carga_con_quemadores": carga_con_quemadores, "carga_despues": os.getloadavg(),
            "ejecutables_antes": ejec_antes, "ejecutables_con_quemadores": ejec_con_quemadores,
            "cpu_pytest_s": cpu_pytest, "fraccion_cpu_pytest": round(cpu_pytest / seg, 3) if seg else None, "json": j.exists()}
    registro.write(json.dumps(fila) + "\n")
    registro.flush()
    print(f"{n:3d}/{len(corridas)} {tag} rc={rc} {seg}s carga={carga_con_quemadores[0]:.2f}", flush=True)
print("FIN")
