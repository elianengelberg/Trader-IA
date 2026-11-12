"""Orquestador de la calibración A-S1 (MEC v0.2 §5): reparte las réplicas del script congelado entre varios procesos.

No reimplementa la calibración:
- cada réplica la calcula ``_replica`` de ``calibracion_mec.py`` (código del paquete r1, verificado por SHA-256) con los
  mismos argumentos que usaría su ``main()``;
- al terminar se ejecuta ese mismo ``main()`` con ``--ejecutar --autorizacion … --salida …`` y ``_replica`` sustituida
  por la consulta de los valores ya calculados: la agregación, el criterio y el archivo de salida son los del script.
Reanudable: cada celda (regla, proceso, n) se guarda al completarse; las réplicas son deterministas.

Uso:
  python3 -B -I orquestar_calibracion.py <paquete_r1> <salida> --autorizacion REF [--procesos 4]
  python3 -B -I orquestar_calibracion.py <paquete_r1> <salida> --equivalencia
      (secuencial frente a paralelo con la semilla 1, distinta de la congelada: no calcula ninguna réplica de la
      calibración)"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
PARAMETROS_SHA = "28764d31b62028f2dd095c35449cd43fccb4c970ae6e00fdf118c744c1efc425"  # congelado (05 y A-S1)
TROZO = 50
_CAL = None  # módulo calibracion_mec del paquete r1; lo heredan los procesos hijos (fork)


def _ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _verificar(paq: Path) -> dict:
    """Todo archivo de pec/ y calibracion/ debe coincidir con SHA256SUMS.txt del paquete r1."""
    sumas = {}
    for linea in (paq / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        h, ruta = linea.split(maxsplit=1)
        sumas[ruta.lstrip("*")] = h
    vistos = {}
    for sub in ("protocolo_cuantitativo/pec", "protocolo_cuantitativo/calibracion"):
        for f in sorted((paq / sub).iterdir()):
            rel = f.relative_to(paq).as_posix()
            if not f.is_file() or sumas.get(rel) != _sha(f):
                raise SystemExit(f"ABORTADO: {rel} no coincide con SHA256SUMS.txt del paquete r1")
            vistos[rel] = sumas[rel]
    par = "protocolo_cuantitativo/calibracion/parametros_calibracion.json"
    if vistos[par] != PARAMETROS_SHA:
        raise SystemExit("ABORTADO: los parámetros no son los congelados")
    return {"SHA256SUMS.txt": _sha(paq / "SHA256SUMS.txt"), **vistos}


def _cargar(paq: Path):
    ruta = paq / "protocolo_cuantitativo" / "calibracion" / "calibracion_mec.py"
    spec = importlib.util.spec_from_file_location("calibracion_mec", ruta)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["calibracion_mec"] = mod
    spec.loader.exec_module(mod)
    return mod


def _celdas(par: dict) -> list[tuple[bool, str, int]]:
    """El mismo orden que los bucles de ``main()``."""
    return [(respaldo, pr, n) for respaldo in (False, True) for pr in par["procesos"] for n in par["tamanos"]]


def _nombre(c: tuple[bool, str, int]) -> str:
    return f"{'respaldo' if c[0] else 'primaria'}_{c[1]}_n{c[2]}.json"


def _trabajo(t: tuple) -> tuple[int, int, list[dict]]:
    i, respaldo, pr, n, r0, r1, semilla, b = t
    return i, r0, [_CAL._replica(pr, n, r, semilla, b, respaldo) for r in range(r0, r1)]


def equivalencia(paq: Path, procesos: int) -> int:
    global _CAL
    _verificar(paq)
    _CAL = _cargar(paq)
    par = json.loads(_CAL.PARAMETROS.read_bytes())
    semilla, b = 1, 199
    assert semilla != par["semilla"]
    tareas = [(0, respaldo, pr, n, r, r + 1, semilla, b) for respaldo in (False, True) for pr in par["procesos"]
              for n in (80, 366) for r in range(4)]
    secuencial = [_trabajo(t) for t in tareas]
    with mp.get_context("fork").Pool(procesos) as pool:
        paralelo = pool.map(_trabajo, list(reversed(tareas)), chunksize=3)[::-1]
    iguales = secuencial == paralelo
    print(json.dumps({"replicas_comparadas": len(tareas), "semilla": semilla, "B": b, "identicas": iguales},
                     ensure_ascii=False))
    return 0 if iguales else 1


def ejecutar(paq: Path, sal: Path, ref: str, procesos: int) -> int:
    global _CAL
    inicio, t0 = _ahora(), time.perf_counter()
    verif = _verificar(paq)
    _CAL = _cargar(paq)
    par = json.loads(_CAL.PARAMETROS.read_bytes())
    reps, b, semilla = par["replicas"], par["B"], par["semilla"]
    celdas = _celdas(par)
    dir_c = sal / "celdas"
    dir_c.mkdir(parents=True, exist_ok=True)
    pendientes = [i for i, c in enumerate(celdas) if not (dir_c / _nombre(c)).exists()]
    registro = (sal / "progreso.log").open("a", encoding="utf-8")

    def anotar(msg: str) -> None:
        registro.write(f"{_ahora()} {msg}\n")
        registro.flush()
        print(msg, flush=True)

    anotar(f"inicio: {len(celdas) - len(pendientes)} celdas ya hechas, {len(pendientes)} pendientes, {procesos} procesos")
    tareas = [(i, *celdas[i], r0, min(r0 + TROZO, reps), semilla, b) for i in pendientes for r0 in range(0, reps, TROZO)]
    tareas.sort(key=lambda t: (not t[1], -t[3], t[0], t[4]))  # las celdas más caras primero, una tras otra
    acum: dict[int, dict[int, dict]] = {i: {} for i in pendientes}
    hechas = len(celdas) - len(pendientes)
    with mp.get_context("fork").Pool(procesos) as pool:
        for i, r0, outs in pool.imap_unordered(_trabajo, tareas):
            for k, o in enumerate(outs):
                acum[i][r0 + k] = o
            if len(acum[i]) == reps:
                c = celdas[i]
                datos = {"regla": "respaldo_max" if c[0] else "bootstrap_t_l20", "proceso": c[1], "n": c[2],
                         "semilla": semilla, "B": b,
                         "replicas": [[acum[i][r]["p"], acum[i][r]["degenerada"]] for r in range(reps)]}
                tmp = dir_c / (_nombre(c) + ".tmp")
                tmp.write_text(json.dumps(datos) + "\n", encoding="utf-8")
                tmp.replace(dir_c / _nombre(c))
                del acum[i]
                hechas += 1
                anotar(f"celda {hechas}/{len(celdas)} completa: {_nombre(c)} ({time.perf_counter() - t0:.0f} s)")
    # Agregación y salida: las del main() congelado, alimentado con las réplicas ya calculadas.
    tabla = {}
    for c in celdas:
        d = json.loads((dir_c / _nombre(c)).read_text(encoding="utf-8"))
        assert (d["semilla"], d["B"], len(d["replicas"])) == (semilla, b, reps), _nombre(c)
        for r, (p, deg) in enumerate(d["replicas"]):
            tabla[(c[0], c[1], c[2], r)] = {"p": p, "degenerada": deg}
    usados: set = set()

    def consulta(proceso: str, n: int, r: int, sem: int, bb: int, respaldo: bool) -> dict:
        k = (respaldo, proceso, n, r)
        assert (sem, bb) == (semilla, b) and k not in usados, k
        usados.add(k)
        return tabla[k]

    salida = sal / "resultado_calibracion.json"
    if salida.exists():
        raise SystemExit(f"ABORTADO: {salida} ya existe; no se sobrescribe")
    original, _CAL._replica = _CAL._replica, consulta
    sys.argv = ["calibracion_mec.py", "--ejecutar", "--autorizacion", ref, "--salida", str(salida)]
    rc = _CAL.main()
    _CAL._replica = original
    assert rc == 0 and len(usados) == len(tabla) == len(celdas) * reps
    meta = {"inicio_utc": inicio, "fin_utc": _ahora(), "segundos": round(time.perf_counter() - t0, 1),
            "celdas_pendientes_al_inicio": len(pendientes), "procesos": procesos, "cpu": os.cpu_count(),
            "python": sys.version, "plataforma": platform.platform(), "autorizacion": ref,
            "orquestador_sha256": _sha(Path(__file__)), "codigo_r1_sha256": verif,
            "salida_sha256": _sha(salida), "replicas_consultadas_por_main": len(usados)}
    with (sal / "ejecuciones.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
    anotar(f"fin: main() congelado rc={rc}; {len(usados)} réplicas; salida {meta['salida_sha256'][:16]}…")
    return 0


def principal() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paquete", type=Path)
    ap.add_argument("salida", type=Path)
    ap.add_argument("--autorizacion")
    ap.add_argument("--equivalencia", action="store_true")
    ap.add_argument("--procesos", type=int, default=4)
    a = ap.parse_args()
    if a.equivalencia:
        return equivalencia(a.paquete, a.procesos)
    if not a.autorizacion:
        print("BLOQUEADO: falta --autorizacion", file=sys.stderr)
        return 2
    return ejecutar(a.paquete, a.salida, a.autorizacion, a.procesos)


if __name__ == "__main__":
    sys.exit(principal())
