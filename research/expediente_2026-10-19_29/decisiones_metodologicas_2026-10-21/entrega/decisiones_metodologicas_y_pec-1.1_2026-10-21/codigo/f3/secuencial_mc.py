"""Calibración del diseño secuencial COMPLETO (5 miradas) con la regla decisiva validada por A-S1. Solo datos sintéticos.

Procedimiento simulado (el mismo que PEC-1.1 prescribe para la fase prospectiva):
- una serie diaria de exceso x_1 … x_N (N = n_max) del proceso C1–C6 de ``pec.sintetico.proceso`` (código r1), con media
  poblacional 0 bajo H₀ o desplazada en μ_d bajo H₁ (solo potencia, descriptiva);
- miradas k = 1 … 5 sobre los PREFIJOS anidados x_1 … x_{n_k}, n_k = round(k·N/5): la dependencia entre miradas es la real;
- en cada mirada, p_k = máx(p_ℓ20, p_ℓ40, p_NW) de ``pec.inferencia`` (código r1), con B = 9999 y la MISMA semilla de
  bootstrap en las 5 miradas (la del prerregistro);
- se confirma en la primera k con p_k ≤ a_k = 1 − Φ(c_k), con c_k las fronteras de Lan–DeMets tipo O'Brien–Fleming de
  ``pec.secuencial.fronteras_obf`` para t_k = n_k/N y α = 0,025; una mirada degenerada no decide (p = 1);
- la futilidad (no vinculante) se omite: solo detiene sin confirmar, así que omitirla da una COTA SUPERIOR del error.

Evaluación con cortocircuito EXACTO: máx(p) ≤ a ⇔ p_NW ≤ a ∧ p_ℓ20 ≤ a ∧ p_ℓ40 ≤ a. Se calcula primero p_NW (barato) y
los bootstraps solo si hacen falta; la decisión es idéntica a la de ``inferencia.respaldo`` (lo comprueba
``prueba_equivalencia``). Reanudable por celda; nunca sobrescribe.

Uso:
  python3 -B -I secuencial_mc.py <paquete_r1> <especificacion.json> <salida> [--procesos 4]
  python3 -B -I secuencial_mc.py <paquete_r1> <especificacion.json> <salida> --equivalencia"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import multiprocessing as mp
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist

sys.dont_write_bytecode = True
_N = NormalDist()
_PEC = {}  # módulos de r1 (inferencia, sintetico, secuencial); los heredan los hijos (fork)
_CFG: dict = {}
TROZO = 100
GUARDAR_Z = 2000  # se guardan los z de Newey–West de las primeras réplicas de cada celda (descriptivo)


def _ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def cargar_r1(paq: Path, esperados: dict[str, str]) -> dict:
    """Importa pec/ de r1 tras comprobar cada archivo contra SHA256SUMS.txt y contra la especificación."""
    sumas = {}
    for linea in (paq / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        h, ruta = linea.split(maxsplit=1)
        sumas[ruta.lstrip("*")] = h
    for ruta, h in esperados.items():
        if not (sumas.get(ruta) == h == _sha(paq / ruta)):
            raise SystemExit(f"ABORTADO: {ruta} no coincide con r1 o con la especificación")
    sys.path.insert(0, str(paq / "protocolo_cuantitativo"))
    mods = {}
    for nombre in ("inferencia", "sintetico", "secuencial"):
        spec = importlib.util.spec_from_file_location(f"pec.{nombre}", paq / "protocolo_cuantitativo" / "pec" / f"{nombre}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"pec.{nombre}"] = mod
        spec.loader.exec_module(mod)
        mods[nombre] = mod
    return mods


def miradas(n_max: int, k: int) -> list[int]:
    return [round(j * n_max / k) for j in range(1, k + 1)]


def umbrales(n_max: int, k: int, alfa: float) -> dict:
    nk = miradas(n_max, k)
    fr = _PEC["secuencial"].fronteras_obf([v / n_max for v in nk], alfa)
    return {"n_k": nk, "t_k": fr["t"], "c_k": fr["fronteras_z"], "a_k": [1.0 - _N.cdf(c) for c in fr["fronteras_z"]],
            "alfa_por_mirada_teorico": fr["alfa_por_mirada"]}


def _p(f, *args) -> float:
    try:
        return f(*args)["p_unilateral"]
    except _PEC["inferencia"].ErrorSerieDegenerada:
        return 1.0


def secuencia(proceso: str, n_max: int, semilla: int, b: int, a_k: list[float], n_k: list[int], mu_d: float,
              guardar_z: bool) -> dict:
    """Una trayectoria completa. Devuelve la mirada de confirmación (0 = ninguna) y lo calculado."""
    inf = _PEC["inferencia"]
    x = _PEC["sintetico"].proceso(proceso, n_max, semilla)
    if mu_d:
        x = [v + mu_d for v in x]
    zs, boots, mirada = [], [], 0
    for k, (nk, a) in enumerate(zip(n_k, a_k, strict=True), start=1):
        if mirada and not guardar_z:
            break
        pref = x[:nk]
        try:
            nw = inf.newey_west(pref, 20)
            p_nw, z = nw["p_unilateral"], nw["z"]
        except inf.ErrorSerieDegenerada:
            p_nw, z = 1.0, None
        zs.append(z)
        if mirada or p_nw > a:  # tras confirmar solo se completan los z (descriptivos); no se decide nada más
            continue
        p20 = _p(inf.bootstrap_t, pref, 20, b, semilla)
        p40 = _p(inf.bootstrap_t, pref, 40, b, semilla) if p20 <= a else None
        boots.append([k, p_nw, p20, p40])
        if p40 is not None and p40 <= a:
            mirada = k
    return {"mirada": mirada, "z": zs if guardar_z else None, "boots": boots}


def _trabajo(t: tuple) -> tuple[int, int, list[dict]]:
    i, proceso, n_max, base, r0, r1, mu_d = t
    u = _CFG["umbrales"][n_max]
    return i, r0, [secuencia(proceso, n_max, base * 10 ** 6 + r, _CFG["B"], u["a_k"], u["n_k"], mu_d, r < GUARDAR_Z)
                   for r in range(r0, r1)]


def celdas(esp: dict) -> list[dict]:
    out = []
    for pr in esp["H0"]["procesos"]:
        for n in esp["H0"]["n_max"]:
            out.append({"nombre": f"H0_{pr}_N{n}", "proceso": pr, "n_max": n, "base": esp["H0"]["semilla_base"],
                        "R": esp["H0"]["replicas"], "ir": 0.0})
    for pr in esp["H1"]["procesos"]:
        for n, irs in esp["H1"]["n_max_ir"].items():
            for ir in irs:
                out.append({"nombre": f"H1_{pr}_N{n}_IR{ir}", "proceso": pr, "n_max": int(n),
                            "base": esp["H1"]["semilla_base"], "R": esp["H1"]["replicas"], "ir": ir})
    return out


def mu_diario(ir: float, sd: float) -> float:
    """IR anual = media anual / desvío anual, con 365,25 días y series sin autocorrelación (C1, C2, C5)."""
    return ir * sd / math.sqrt(365.25)


def preparar(paq: Path, esp: dict) -> None:
    global _PEC
    _PEC.update(cargar_r1(paq, esp["codigo_r1_sha256"]))
    ns = sorted({c["n_max"] for c in celdas(esp)})
    _CFG.update({"B": esp["B"], "umbrales": {n: umbrales(n, esp["K"], esp["alfa"]) for n in ns}})


def prueba_equivalencia(paq: Path, esp: dict, procesos: int) -> int:
    """Cortocircuito frente a ``inferencia.respaldo`` completo, mirada por mirada, con la semilla de DESARROLLO."""
    preparar(paq, esp)
    inf = _PEC["inferencia"]
    dev = esp["desarrollo"]
    casos, distintos, confirmadas = 0, 0, 0
    for umbral_artificial in (None, [0.3] * esp["K"]):  # el segundo ejercita todas las ramas
        for pr in esp["H0"]["procesos"]:
            for mu_ir in (0.0, 2.0):
                n_max = dev["n_max"]
                u = umbrales(n_max, esp["K"], esp["alfa"])
                a_k = umbral_artificial or u["a_k"]
                for r in range(dev["replicas_equivalencia"]):
                    sem = dev["semilla_base"] * 10 ** 6 + r
                    mu = mu_diario(mu_ir, 0.01)
                    rapido = secuencia(pr, n_max, sem, dev["B"], a_k, u["n_k"], mu, False)["mirada"]
                    x = _PEC["sintetico"].proceso(pr, n_max, sem)
                    x = [v + mu for v in x] if mu else x
                    lento = 0
                    for k, (nk, a) in enumerate(zip(u["n_k"], a_k, strict=True), start=1):
                        try:
                            p = inf.respaldo(x[:nk], dev["B"], sem)["p_unilateral"]
                        except inf.ErrorSerieDegenerada:
                            p = 1.0
                        if p <= a:
                            lento = k
                            break
                    casos += 1
                    distintos += rapido != lento
                    confirmadas += lento > 0
    print(json.dumps({"trayectorias_comparadas": casos, "distintas": distintos, "con_confirmacion": confirmadas,
                      "B": dev["B"],
                      "semilla_base_desarrollo": dev["semilla_base"]}, ensure_ascii=False))
    return 0 if distintos == 0 else 1


def ejecutar(paq: Path, esp_ruta: Path, sal: Path, procesos: int) -> int:
    esp = json.loads(esp_ruta.read_text(encoding="utf-8"))
    preparar(paq, esp)
    inicio, t0 = _ahora(), time.perf_counter()
    lista = celdas(esp)
    dir_c = sal / "celdas"
    dir_c.mkdir(parents=True, exist_ok=True)
    pend = [i for i, c in enumerate(lista) if not (dir_c / f"{c['nombre']}.json").exists()]
    log = (sal / "progreso.log").open("a", encoding="utf-8")

    def anotar(m: str) -> None:
        log.write(f"{_ahora()} {m}\n")
        log.flush()
        print(m, flush=True)

    anotar(f"inicio: {len(lista) - len(pend)} celdas hechas, {len(pend)} pendientes, {procesos} procesos")
    tareas = [(i, lista[i]["proceso"], lista[i]["n_max"], lista[i]["base"], r0, min(r0 + TROZO, lista[i]["R"]),
               mu_diario(lista[i]["ir"], esp["sd"])) for i in pend for r0 in range(0, lista[i]["R"], TROZO)]
    acum: dict[int, dict[int, dict]] = {i: {} for i in pend}
    hechas = len(lista) - len(pend)
    with mp.get_context("fork").Pool(procesos) as pool:
        for i, r0, outs in pool.imap_unordered(_trabajo, tareas):
            for j, o in enumerate(outs):
                acum[i][r0 + j] = o
            c = lista[i]
            if len(acum[i]) == c["R"]:
                filas = [acum[i][r] for r in range(c["R"])]
                datos = {**c, "B": esp["B"], "K": esp["K"], "alfa": esp["alfa"],
                         "umbrales": _CFG["umbrales"][c["n_max"]],
                         "miradas": "".join(str(f["mirada"]) for f in filas),
                         "boots": [[r, *bb] for r, f in enumerate(filas) for bb in f["boots"]],
                         "z_nw_primeras": [f["z"] for f in filas[:GUARDAR_Z]]}
                tmp = dir_c / f"{c['nombre']}.json.tmp"
                tmp.write_text(json.dumps(datos) + "\n", encoding="utf-8")
                tmp.replace(dir_c / f"{c['nombre']}.json")
                del acum[i]
                hechas += 1
                anotar(f"celda {hechas}/{len(lista)} completa: {c['nombre']} ({time.perf_counter() - t0:.0f} s)")
    meta = {"inicio_utc": inicio, "fin_utc": _ahora(), "segundos": round(time.perf_counter() - t0, 1),
            "celdas_pendientes_al_inicio": len(pend), "procesos": procesos, "cpu": os.cpu_count(),
            "python": sys.version, "plataforma": platform.platform(), "especificacion_sha256": _sha(esp_ruta),
            "simulador_sha256": _sha(Path(__file__))}
    with (sal / "ejecuciones.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
    anotar(f"fin: {len(lista)} celdas")
    return 0


def principal() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paquete_r1", type=Path)
    ap.add_argument("especificacion", type=Path)
    ap.add_argument("salida", type=Path)
    ap.add_argument("--procesos", type=int, default=4)
    ap.add_argument("--equivalencia", action="store_true")
    a = ap.parse_args()
    if a.equivalencia:
        return prueba_equivalencia(a.paquete_r1, json.loads(a.especificacion.read_text(encoding="utf-8")), a.procesos)
    return ejecutar(a.paquete_r1, a.especificacion, a.salida, a.procesos)


if __name__ == "__main__":
    sys.exit(principal())
