"""Fase 1: recuento de A-S1 escrito de nuevo para esta verificación (no reutiliza verificar_calibracion.py).

Comprueba, desde una extracción limpia del ZIP A-S1 y otra del ZIP r1:
- correspondencia del código: cada hash de ``ejecuciones.jsonl`` coincide con SHA256SUMS.txt de r1 y con el archivo;
- parámetros: huella 28764d31…, semilla, B, réplicas, procesos y tamaños iguales en parámetros, celdas y resultado;
- 48 celdas × 2000 réplicas = 96 000; 24 celdas y 48 comprobaciones por regla;
- forma de los valores p: en la regla primaria p·(B + 1) es entero en [1, B + 1]; en ambas, p ∈ (0, 1];
- recuento de rechazos (p ≤ α, la comparación del script) y comparación con cada fila del resultado.
Uso: python3 -B -I recuento_a_s1.py <a_s1_extraido> <r1_extraido>"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

PAR_SHA = "28764d31b62028f2dd095c35449cd43fccb4c970ae6e00fdf118c744c1efc425"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main(a: Path, r1: Path) -> int:
    fallas, hechos = [], {}
    sumas = dict(reversed(linea.split(maxsplit=1)) for linea in (r1 / "SHA256SUMS.txt").read_text().splitlines())
    sumas = {k.lstrip("*"): v for k, v in sumas.items()}
    ejec = [json.loads(linea) for linea in (a / "salida" / "ejecuciones.jsonl").read_text().splitlines()]
    hechos["ejecuciones_registradas"] = len(ejec)
    hechos["celdas_pendientes_al_inicio"] = ejec[0]["celdas_pendientes_al_inicio"]
    for ruta, h in ejec[0]["codigo_r1_sha256"].items():
        if ruta == "SHA256SUMS.txt":
            ok = h == sha(r1 / "SHA256SUMS.txt")
        else:
            ok = h == sumas.get(ruta) == sha(r1 / ruta)
        if not ok:
            fallas.append(f"hash de código no corresponde: {ruta}")
    hechos["archivos_de_codigo_correspondientes"] = len(ejec[0]["codigo_r1_sha256"])
    if ejec[0]["orquestador_sha256"] != sha(a / "orquestador" / "orquestar_calibracion.py"):
        fallas.append("el orquestador empaquetado no es el que ejecutó")
    if ejec[0]["salida_sha256"] != sha(a / "salida" / "resultado_calibracion.json"):
        fallas.append("la salida empaquetada no es la registrada")
    ppath = r1 / "protocolo_cuantitativo" / "calibracion" / "parametros_calibracion.json"
    if sha(ppath) != PAR_SHA:
        fallas.append("parámetros distintos de los congelados")
    par = json.loads(ppath.read_text())
    res = json.loads((a / "salida" / "resultado_calibracion.json").read_text())
    if res["parametros_sha256"] != PAR_SHA:
        fallas.append("el resultado declara otros parámetros")
    reps, b, sem = par["replicas"], par["B"], par["semilla"]
    total, filas, i = 0, 0, 0
    por_regla = {}
    for regla, pref in (("bootstrap_t_l20", "primaria"), ("respaldo_max", "respaldo")):
        comprobaciones = 0
        for pr in par["procesos"]:
            for n in par["tamanos"]:
                d = json.loads((a / "salida" / "celdas" / f"{pref}_{pr}_n{n}.json").read_text())
                rp = d["replicas"]
                if (d["semilla"], d["B"], d["proceso"], d["n"], d["regla"]) != (sem, b, pr, n, regla) or len(rp) != reps:
                    fallas.append(f"celda {pref}_{pr}_n{n}: metadatos o tamaño")
                if not all(0 < p <= 1 and isinstance(g, bool) for p, g in rp):
                    fallas.append(f"celda {pref}_{pr}_n{n}: p fuera de (0, 1]")
                if pref == "primaria" and not all(abs(p * (b + 1) - round(p * (b + 1))) < 1e-9 for p, _ in rp):
                    fallas.append(f"celda {pref}_{pr}_n{n}: p no es (1 + c)/(B + 1)")
                total += len(rp)
                fila = res["filas"][i]
                i += 1
                esperado = {"regla": regla, "proceso": pr, "n": n, "degeneradas": sum(g for _, g in rp)}
                for alfa, (_lo, hi) in par["bandas"].items():
                    k = sum(1 for p, _ in rp if p <= float(alfa))
                    esperado[f"rechazo_{alfa}"] = k / reps
                    esperado[f"cumple_{alfa}"] = k / reps <= hi
                    comprobaciones += 1
                if fila != esperado:
                    fallas.append(f"fila del resultado distinta: {regla} {pr} {n}")
                filas += 1
        por_regla[regla] = {"celdas": len(par["procesos"]) * len(par["tamanos"]), "comprobaciones": comprobaciones,
                            "cumplen": sum(1 for f in res["filas"] if f["regla"] == regla
                                           for al in par["bandas"] if f[f"cumple_{al}"])}
    hechos.update({"replicas_totales": total, "filas_resultado": len(res["filas"]), "filas_recontadas": filas,
                   "por_regla": por_regla, "semilla": sem, "B": b, "replicas_por_celda": reps})
    print(json.dumps({"fallas": fallas, "hechos": hechos}, ensure_ascii=False, indent=1))
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
