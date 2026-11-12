"""Proceso real (NO es E3): orquestador sintético del prototipo v4.1 sobre ext4, con numpy cargado (hilos de BLAS) y
diferido de señales por manejador (corrección de R-1). El canal externo es la salida estándar (una línea JSON por evento),
que el proceso padre captura fuera de este proceso.
Política de señales:
  - SIGINT, SIGTERM, SIGHUP y SIGQUIT se instalan al arrancar con un manejador que solo anota la señal;
  - en los puntos seguros (entre etapas) se mira la anotación: antes de anunciar una decisión se escribe ERROR(senal)
    durable y se sale; después de anunciarla se termina la publicación (objeto y PUBLICADO) y recién entonces se sale;
  - SIGKILL y las señales no manejadas (por ejemplo SIGUSR1) matan el proceso: lo cubre la reconciliación.
Modo `mascara` (mutante, el diseño v4 tal como estaba): usa pthread_sigmask en el hilo principal durante DECISION→PUBLICADO.
Uso: <python> -I -B orquestador_real.py <dir_almacen> <EVALUADO|INVALIDO> <manejador|mascara> <pausa_s>"""
import json
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402  (crea los hilos de OpenBLAS antes que nada)
import proto_v4 as P  # noqa: E402

RAIZ, ESC, MODO, PAUSA = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
pendientes = []
MANEJADAS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)


class Canal(list):
    def append(self, x):
        super().append(x)
        print(json.dumps(x), flush=True)


def anotar(s, _f):
    pendientes.append(s)


if MODO == "manejador":
    for s in MANEJADAS:
        signal.signal(s, anotar)


def calcular():
    a = np.random.default_rng(1).standard_normal((300, 300))
    for _ in range(3):
        a = (a @ a.T) / 300.0  # trabajo real en BLAS con varios hilos
    time.sleep(PAUSA)


class FsLento(P.FsReal):
    """Pausa entre operaciones para que las señales caigan en lugares distintos (incluida la sección crítica)."""
    def anexar(self, r, d):
        time.sleep(PAUSA / 4)
        super().anexar(r, d)

    def enlazar(self, a, b):
        time.sleep(PAUSA / 4)
        super().enlazar(a, b)


def salir_si_senal(alm, canal, cab, etapa):
    if pendientes:
        cab = alm.anexar("ERROR", {"etapa": f"senal_{int(pendientes[0])}_en_{etapa}"}, cab)
        canal.append({"tipo": "ERROR_DURABLE", "evaluacion": "EVAL-SINTETICA", "cabeza": cab, "senal": int(pendientes[0])})
        os._exit(128 + int(pendientes[0]))
    return cab


def main():
    canal = Canal()
    fs = FsLento(RAIZ)
    alm = P.Almacen(fs)
    st = alm.leer()
    if not P.puede_abrir(st, [], "EVAL-SINTETICA", alm):
        print(json.dumps({"tipo": "APERTURA_RECHAZADA"}), flush=True)
        return 3
    cab = alm.anexar("ABIERTO", {"evaluacion": "EVAL-SINTETICA", "nonce": "n"}, st["cabeza"])
    canal.append({"tipo": "ABIERTO_DURABLE", "evaluacion": "EVAL-SINTETICA", "cabeza": cab})
    for etapa in P.ETAPAS:
        cab = salir_si_senal(alm, canal, cab, etapa)
        cab = alm.anexar("ETAPA", {"etapa": etapa}, cab)
        calcular()
        if etapa == "validez" and ESC == "INVALIDO":
            break
    cab = salir_si_senal(alm, canal, cab, "antes_de_decidir")
    tipo = "INVALIDO" if ESC == "INVALIDO" else "EVALUADO"
    contenido = P.serializar_objeto({"veredicto": tipo, "estadistico": 0.0123})
    h = P.sha(contenido)
    if MODO == "mascara":
        signal.pthread_sigmask(signal.SIG_BLOCK, set(MANEJADAS))
    canal.append({"tipo": "ANUNCIO_DECISION", "decision": tipo, "sha_objeto": h, "seq": len(alm.leer()["eventos"]), "cabeza": cab})
    cab = alm.anexar("DECISION", {"tipo": tipo, "sha_objeto": h}, cab)
    calcular()  # trabajo dentro de la sección crítica, con hilos de BLAS vivos
    alm.publicar_objeto(contenido)
    cab = alm.anexar("PUBLICADO", {"sha_objeto": h}, cab)
    canal.append({"tipo": "PUBLICADO_DURABLE", "cabeza": cab})
    if MODO == "mascara":
        signal.pthread_sigmask(signal.SIG_UNBLOCK, set(MANEJADAS))
    if pendientes:
        for s in MANEJADAS:
            signal.signal(s, signal.SIG_DFL)
        os.kill(os.getpid(), pendientes[0])  # se re-entrega la señal ya fuera de la sección crítica
        time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
