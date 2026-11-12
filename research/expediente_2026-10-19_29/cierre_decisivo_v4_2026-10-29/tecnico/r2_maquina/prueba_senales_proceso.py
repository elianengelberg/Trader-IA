"""Pruebas negativas de R-1 y R-2 con procesos reales sobre ext4. NO es E3; no lee datos.
Para cada señal (SIGINT, SIGTERM, SIGHUP, SIGQUIT, SIGUSR1 no manejada, SIGKILL), cada modo (manejador = corrección;
mascara = diseño v4 tal como estaba) y N momentos aleatorios (semilla fija), lanza `orquestador_real.py` con numpy, le manda
la señal, captura su salida estándar como canal externo, reconcilia y comprueba:
  S-1 sin repetición: tras cualquier final, `puede_abrir` es False si el canal registró ABIERTO_DURABLE;
  S-2 sección crítica: con una señal MANEJADA, si hay DECISION en el registro, también hay PUBLICADO y objeto verificado;
  S-3 clase coherente: DECISION en el registro ⇒ la clase la refleja; anuncio sin DECISION ⇒ DECISION_ANUNCIADA_NO_PERSISTIDA;
  S-4 nada de INCIERTO con señales manejadas (siempre hay un final ordenado: ERROR durable o publicación completa);
  S-5 la reconciliación no altera bytes previos y es idempotente.
Se espera que el modo `mascara` viole S-2 (prueba de que la batería detecta R-1) y que el modo `manejador` no viole nada.
Uso: python3 -I -B prueba_senales_proceso.py <python_venv> <dir_tmp_base> <N_por_combinacion> <salida.json>"""
import json
import os
import random
import signal
import subprocess
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import proto_v4 as P  # noqa: E402

PY, BASE, N, SAL = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
SENALES = {"SIGINT": signal.SIGINT, "SIGTERM": signal.SIGTERM, "SIGHUP": signal.SIGHUP, "SIGQUIT": signal.SIGQUIT,
           "SIGUSR1": signal.SIGUSR1, "SIGKILL": signal.SIGKILL}
MANEJADAS = {"SIGINT", "SIGTERM", "SIGHUP", "SIGQUIT"}
PAUSA = 0.08
rng = random.Random(20261029)


def uno(modo, nombre, esc):
    d = tempfile.mkdtemp(dir=BASE)
    t = rng.uniform(0.25, 2.2)  # incluye la importación de numpy, las etapas y la sección crítica
    p = subprocess.Popen([PY, "-I", "-B", os.path.join(AQUI, "orquestador_real.py"), d, esc, modo, str(PAUSA)],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=d)
    time.sleep(t)
    if p.poll() is None:
        p.send_signal(SENALES[nombre])
    out, err = p.communicate(timeout=60)
    canal = [json.loads(x) for x in out.splitlines() if x.startswith("{")]
    fs = P.FsReal(d)
    raw = fs.leer(P.REG) if fs.existe(P.REG) else b""
    st0 = P.leer_registro(raw)
    tipos = [e["tipo"] for e in st0["eventos"]]
    clase, det = P.reconciliar(fs, canal)
    raw1 = fs.leer(P.REG) if fs.existe(P.REG) else b""
    clase2, _ = P.reconciliar(fs, canal)
    raw2 = fs.leer(P.REG) if fs.existe(P.REG) else b""
    st = P.leer_registro(raw2)
    fallas = []
    abierto_canal = any(c.get("tipo") == "ABIERTO_DURABLE" for c in canal)
    if abierto_canal and P.puede_abrir(st, canal, "EVAL-SINTETICA", P.Almacen(fs)):
        fallas.append("S-1")
    if nombre in MANEJADAS and "DECISION" in tipos and not ("PUBLICADO" in tipos and clase in ("EVALUADO", "INVALIDO")):
        fallas.append("S-2")
    dec = [e["datos"]["tipo"] for e in st0["eventos"] if e["tipo"] == "DECISION"]
    if dec and not clase.startswith((dec[-1], f"TERMINAL_SIN_OBJETO({dec[-1]})")):
        fallas.append("S-3")
    if not dec and any(c.get("tipo") == "ANUNCIO_DECISION" for c in canal) and not clase.startswith("DECISION_ANUNCIADA_NO_PERSISTIDA"):
        fallas.append("S-3")
    if nombre in MANEJADAS and modo == "manejador" and clase == "INCIERTO":
        fallas.append("S-4")
    if not raw1.startswith(raw) or raw2 != raw1 or clase2 != clase:
        fallas.append("S-5")
    return {"modo": modo, "senal": nombre, "escenario": esc, "t_senal": round(t, 3), "returncode": p.returncode,
            "eventos": tipos, "clase": clase, "detalle": det, "fallas": fallas, "stderr_ultima": (err.strip().splitlines() or [""])[-1][:200]}


filas = []
for modo in ("manejador", "mascara"):
    for nombre in SENALES:
        for i in range(N):
            filas.append(uno(modo, nombre, "EVALUADO" if i % 3 else "INVALIDO"))
res = {}
for modo in ("manejador", "mascara"):
    for nombre in SENALES:
        g = [f for f in filas if f["modo"] == modo and f["senal"] == nombre]
        clases = {}
        for f in g:
            k = f["clase"].split("(")[0]
            clases[k] = clases.get(k, 0) + 1
        res[f"{modo}/{nombre}"] = {"corridas": len(g), "con_fallas": sum(1 for f in g if f["fallas"]),
                                   "fallas": sorted({x for f in g for x in f["fallas"]}), "clases": clases,
                                   "con_DECISION": sum(1 for f in g if "DECISION" in f["eventos"])}
with open(SAL, "w") as fh:
    json.dump({"resumen": res, "filas": filas}, fh, ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False, indent=1))
