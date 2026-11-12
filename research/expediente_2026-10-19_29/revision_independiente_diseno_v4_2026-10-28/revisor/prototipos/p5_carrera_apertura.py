"""P5 (revisor) · Carrera de apertura: N procesos con autorizaciones distintas (nonces distintos) válidas para la misma
cabeza intentan abrir un intento a la vez. Cada uno: flock LOCK_EX|LOCK_NB sobre el registro, relee la cabeza, comprueba
`cabeza_esperada` y anexa ABIERTO. NO es E3; eventos inventados.
Esperado (I-4/I-8 del diseño): exactamente UN ABIERTO; los demás reciben EWOULDBLOCK (rechazo) o, si llegan a tomar el
bloqueo después de que el ganador lo soltara, fallan la comparación de cabeza.
Variante «sin_cas»: toma el bloqueo pero NO vuelve a comparar la cabeza tras obtenerlo (lee antes de bloquear): muestra
por qué la comparación tiene que hacerse DENTRO del bloqueo.
Uso: /usr/bin/python3 -I -B p5_carrera_apertura.py <dir_trabajo>
"""
import hashlib
import json
import os
import subprocess
import sys
import time

HIJO = r"""
import fcntl, hashlib, json, os, sys, time
ruta, nonce, cabeza_esperada, modo, arranque = sys.argv[1:6]
while time.time() < float(arranque):
    pass
def cabeza():
    d = open(ruta, "rb").read()
    return hashlib.sha256(d).hexdigest() if d else "GENESIS"
vista_antes = cabeza()
fd = os.open(ruta, os.O_RDWR | os.O_APPEND)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    print(json.dumps({"nonce": nonce, "resultado": "RECHAZO_BLOQUEADO"})); sys.exit()
c = vista_antes if modo == "sin_cas" else cabeza()
if c != cabeza_esperada:
    print(json.dumps({"nonce": nonce, "resultado": "RECHAZO_CABEZA_DISTINTA"})); sys.exit()
os.write(fd, (json.dumps({"evento": "ABIERTO", "nonce": nonce, "hash_previo": c}) + "\n").encode())
os.fsync(fd)
time.sleep(0.05)  # retiene el bloqueo un instante (el intento real lo retiene horas)
print(json.dumps({"nonce": nonce, "resultado": "ABIERTO"}))
"""


def carrera(d, modo, n=8):
    ruta = os.path.join(d, f"registro_{modo}.log")
    open(ruta, "wb").close()
    arranque = str(time.time() + 0.6)
    procs = [subprocess.Popen([sys.executable, "-I", "-B", "-c", HIJO, ruta, f"nonce-{i:02d}", "GENESIS", modo, arranque],
                              stdout=subprocess.PIPE, text=True) for i in range(n)]
    salidas = [json.loads(p.communicate()[0]) for p in procs]
    lineas = open(ruta, "rb").read().splitlines()
    return {"resultados": sorted(s["resultado"] for s in salidas), "lineas_ABIERTO_en_registro": len(lineas),
            "nonces_abiertos": [json.loads(x)["nonce"] for x in lineas]}


def dos_fases(d, modo):
    """B lee la cabeza (GENESIS) y se demora; A toma el bloqueo, consume (ABIERTO) y lo libera; B toma el bloqueo
    DESPUÉS. Con CAS dentro del bloqueo, B relee la cabeza y se rechaza; sin CAS, B anexa un segundo ABIERTO."""
    ruta = os.path.join(d, f"registro_dosfases_{modo}.log")
    open(ruta, "wb").close()
    ahora = time.time()
    b = subprocess.Popen([sys.executable, "-I", "-B", "-c", HIJO_DEMORADO, ruta, "nonce-B", "GENESIS", modo, str(ahora + 0.3), "0.6"],
                         stdout=subprocess.PIPE, text=True)
    a = subprocess.Popen([sys.executable, "-I", "-B", "-c", HIJO, ruta, "nonce-A", "GENESIS", "con_cas", str(ahora + 0.5)],
                         stdout=subprocess.PIPE, text=True)
    ra, rb = json.loads(a.communicate()[0]), json.loads(b.communicate()[0])
    lineas = open(ruta, "rb").read().splitlines()
    return {"A": ra["resultado"], "B": rb["resultado"], "lineas_ABIERTO_en_registro": len(lineas),
            "nonces_abiertos": [json.loads(x)["nonce"] for x in lineas]}


HIJO_DEMORADO = HIJO.replace('vista_antes = cabeza()\n', 'vista_antes = cabeza()\ntime.sleep(float(sys.argv[6]))\n')


def main(d):
    os.makedirs(d, exist_ok=True)
    out = {"8_procesos_simultaneos_con_cas": carrera(d, "con_cas"), "8_procesos_simultaneos_sin_cas": carrera(d, "sin_cas"),
           "dos_fases_con_cas": dos_fases(d, "con_cas"), "dos_fases_sin_cas": dos_fases(d, "sin_cas")}
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1])
