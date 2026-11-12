"""P2b (autor, NO independiente) · ¿La corrección de R-1 (`signal.signal` con manejador que difiere) funciona cuando el
proceso YA tiene otros hilos? El P2 del revisor probó `handler` solo con 1 hilo (registro 11: "hilos_del_proceso": 1).
NO es E3: no importa ningún módulo de E3, no lee datos, no escribe fuera de un directorio temporal propio.

Variantes (argumento 1):
  handler_numpy        `import numpy` (hilos de OpenBLAS) y después el manejador; requiere el intérprete del venv
  handler_hilo_previo  un hilo Python vivo y después el manejador
Argumento 2: SIGINT | SIGTERM.
Argumento 3: interna | externa. «interna» = os.kill al propio pid (como P2); «externa» = otro proceso envía la señal
  al pid durante la sección crítica (como haría el harness o un Ctrl-C de la terminal al grupo).
La sección crítica escribe y hace fsync de un archivo temporal 20 veces (llamadas al sistema reales, no solo bytecode).
Uso: <python> -I -B p2b_handler_con_hilos.py <variante> <señal> <origen> <directorio_temporal_vacio>
"""
import json
import os
import signal
import subprocess
import sys
import threading
import time


def main(variante, nombre_senal, origen, dir_tmp):
    sig = getattr(signal, nombre_senal)
    res = {"variante": variante, "senal": nombre_senal, "origen": origen}
    stop = threading.Event()
    if variante == "handler_numpy":
        import numpy  # noqa: F401  (crea los hilos de BLAS)
        res["numpy"] = numpy.__version__
    elif variante == "handler_hilo_previo":
        threading.Thread(target=stop.wait, daemon=True).start()
    res["hilos_del_proceso"] = len(os.listdir("/proc/self/task"))
    diferidas = []
    anterior = signal.signal(sig, lambda s, f: diferidas.append(s))
    res["interrumpido_en_seccion_critica"] = False
    ruta = os.path.join(dir_tmp, "seccion_critica.bin")
    escrituras = 0
    try:
        if origen == "interna":
            os.kill(os.getpid(), sig)
        else:
            subprocess.Popen(["kill", "-" + nombre_senal[3:], str(os.getpid())])
        fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        for _ in range(20):
            os.write(fd, b"x" * 4096)
            os.fsync(fd)
            escrituras += 1
            time.sleep(0.01)
        os.close(fd)
        res["seccion_critica_completada"] = True
    except KeyboardInterrupt:
        res["interrumpido_en_seccion_critica"] = True
        res["seccion_critica_completada"] = False
    res["escrituras_con_fsync"] = escrituras
    res["diferidas_por_handler"] = [int(s) for s in diferidas]
    print(json.dumps(res), flush=True)
    stop.set()
    signal.signal(sig, anterior)
    if diferidas:
        os.kill(os.getpid(), sig)  # re-lanzar la señal diferida, ya fuera de la sección crítica
        time.sleep(0.2)
    print(json.dumps({"despues_de_relanzar": "sigo vivo (no debería llegar acá si hubo señal diferida)"}), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:5])
