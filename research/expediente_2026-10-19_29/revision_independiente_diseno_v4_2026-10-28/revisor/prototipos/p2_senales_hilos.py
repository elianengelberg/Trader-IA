"""P2 (revisor) · ¿`pthread_sigmask` en el hilo principal difiere SIGINT/SIGTERM cuando el proceso tiene otros hilos?
NO es E3. El diseño §A.3 dice: «Durante los pasos 4 a 6, SIGINT y SIGTERM se difieren con pthread_sigmask».

POSIX entrega una señal dirigida al proceso a CUALQUIER hilo que no la tenga bloqueada. Si existe un hilo creado antes
de la máscara (los hilos de OpenBLAS que crea `import numpy`, por ejemplo), la máscara del hilo principal no alcanza:
  - SIGINT: el manejador C de CPython se dispara en el hilo que recibe la señal y el hilo principal ejecuta el manejador
    Python (KeyboardInterrupt) en el siguiente bytecode, pese a su máscara;
  - SIGTERM: sin manejador Python, la acción por defecto (terminar el proceso) se aplica de inmediato.

Variantes (argumento 1):
  sin_hilo        un solo hilo, máscara en el principal              (lo que el diseño supone)
  hilo_previo     un hilo Python creado ANTES de la máscara            (modelo de los hilos de BLAS)
  numpy           `import numpy` antes de la máscara (hilos reales de BLAS); requiere el intérprete del venv
  handler         alternativa: `signal.signal` con un manejador que difiere (válido para todo el proceso)
Argumento 2: SIGINT | SIGTERM.
Uso: <python> -I -B p2_senales_hilos.py <variante> <señal>
"""
import json
import os
import signal
import sys
import threading
import time


def main(variante, nombre_senal):
    sig = getattr(signal, nombre_senal)
    res = {"variante": variante, "senal": nombre_senal, "pid": os.getpid()}
    stop = threading.Event()
    if variante == "hilo_previo":
        threading.Thread(target=stop.wait, daemon=True).start()
    elif variante == "numpy":
        import numpy  # noqa: F401  (crea los hilos de BLAS)
        res["numpy"] = numpy.__version__
    res["hilos_del_proceso"] = len(os.listdir("/proc/self/task"))
    diferidas = []
    if variante == "handler":
        signal.signal(sig, lambda s, f: diferidas.append(s))
    else:
        signal.pthread_sigmask(signal.SIG_BLOCK, {sig})
    res["interrumpido_en_seccion_critica"] = False
    try:
        os.kill(os.getpid(), sig)  # la señal llega durante la «sección crítica» (pasos 4 a 6)
        t0 = time.monotonic()
        while time.monotonic() - t0 < 0.5:  # trabajo en bytecode Python
            pass
        res["seccion_critica_completada"] = True
        res["pendientes_al_final"] = sorted(int(s) for s in signal.sigpending())
    except KeyboardInterrupt:
        res["interrumpido_en_seccion_critica"] = True
        res["seccion_critica_completada"] = False
    res["diferidas_por_handler"] = [int(s) for s in diferidas]
    print(json.dumps(res), flush=True)
    stop.set()
    if variante != "handler":
        signal.pthread_sigmask(signal.SIG_UNBLOCK, {sig})  # ahora sí puede llegar (y matar o interrumpir)
        time.sleep(0.05)
    print(json.dumps({"despues_de_desbloquear": "sigo vivo"}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
