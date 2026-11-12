"""Verificación independiente de la calibración A-S1. Escrito y fijado por hash ANTES de la ejecución.

No usa la agregación del script congelado: recuenta desde los valores p crudos de cada celda y lo compara con
``resultado_calibracion.json``. Además:
- comprueba que, réplica a réplica, p_respaldo ≥ p_primaria (la regla de respaldo es el máximo de tres valores p, uno de
  ellos el mismo bootstrap-t ℓ = 20 con la misma semilla) y que las réplicas degeneradas coinciden;
- recalcula en ESTE proceso 2 réplicas por celda elegidas con random.Random(20261021) y exige igualdad exacta;
- aplica la tabla de decisión VINCULANTE de A-S1 (criterio congelado del MEC §5: cada proceso, tamaño y nivel);
- informa, SIN valor vinculante, la prueba binomial exacta de sobre-rechazo por comprobación con Holm (5 %) dentro de
  cada regla, el sub-rechazo y el intervalo de Wilson al 95 %.
Uso: python3 -B -I verificar_calibracion.py <paquete_r1> <salida> <destino>"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import random
import sys
from pathlib import Path

sys.dont_write_bytecode = True
SEMILLA_MUESTRA = 20261021
REGLAS = (("bootstrap_t_l20", False), ("respaldo_max", True))


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _cola_binomial(r: int, k: int, a: float) -> float:
    """P(Bin(r, a) ≥ k)."""
    def lp(j: int) -> float:
        return math.lgamma(r + 1) - math.lgamma(j + 1) - math.lgamma(r - j + 1) + j * math.log(a) + (r - j) * math.log1p(-a)
    return min(1.0, sum(math.exp(lp(j)) for j in range(k, r + 1)))


def _wilson(k: int, r: int, z: float = 1.959963984540054) -> tuple[float, float]:
    f = k / r
    c = (f + z * z / (2 * r)) / (1 + z * z / r)
    m = z * math.sqrt(f * (1 - f) / r + z * z / (4 * r * r)) / (1 + z * z / r)
    return c - m, c + m


def _holm(ps: list[float], nivel: float = 0.05) -> list[bool]:
    orden = sorted(range(len(ps)), key=lambda i: ps[i])
    rech = [False] * len(ps)
    for j, i in enumerate(orden):
        if ps[i] > nivel / (len(ps) - j):
            break
        rech[i] = True
    return rech


def main(paq: Path, sal: Path, dest: Path) -> int:
    fallas: list[str] = []
    cal_py = paq / "protocolo_cuantitativo" / "calibracion" / "calibracion_mec.py"
    spec = importlib.util.spec_from_file_location("calibracion_mec", cal_py)
    cal = importlib.util.module_from_spec(spec)
    sys.modules["calibracion_mec"] = cal
    spec.loader.exec_module(cal)
    crudo = cal.PARAMETROS.read_bytes()
    par = json.loads(crudo)
    reps, b, semilla = par["replicas"], par["B"], par["semilla"]
    bandas = {a: tuple(v) for a, v in par["bandas"].items()}
    res = json.loads((sal / "resultado_calibracion.json").read_text(encoding="utf-8"))
    ejec = [json.loads(x) for x in (sal / "ejecuciones.jsonl").read_text(encoding="utf-8").splitlines()]
    if res["parametros_sha256"] != hashlib.sha256(crudo).hexdigest():
        fallas.append("huella de parámetros distinta")
    if ejec[-1]["salida_sha256"] != _sha(sal / "resultado_calibracion.json"):
        fallas.append("la salida no es la registrada por el orquestador")
    datos: dict[tuple[str, str, int], list] = {}
    for regla, respaldo in REGLAS:
        for pr in par["procesos"]:
            for n in par["tamanos"]:
                d = json.loads((sal / "celdas" / f"{'respaldo' if respaldo else 'primaria'}_{pr}_n{n}.json")
                               .read_text(encoding="utf-8"))
                if (d["regla"], d["proceso"], d["n"], d["semilla"], d["B"], len(d["replicas"])) != (
                        regla, pr, n, semilla, b, reps):
                    fallas.append(f"celda mal formada: {regla} {pr} {n}")
                datos[(regla, pr, n)] = d["replicas"]
    # 1. Recuento independiente frente a la salida del main() congelado.
    filas, i = [], 0
    for regla, _ in REGLAS:
        for pr in par["procesos"]:
            for n in par["tamanos"]:
                rp = datos[(regla, pr, n)]
                f = {"regla": regla, "proceso": pr, "n": n, "degeneradas": sum(1 for _, g in rp if g)}
                for a, (lo, hi) in bandas.items():
                    k = sum(1 for p, _ in rp if p <= float(a))
                    f[a] = {"rechazos": k, "tasa": k / reps, "cumple": k / reps <= hi, "subrechazo": k / reps < lo,
                            "empates_en_alfa": sum(1 for p, _ in rp if p == float(a)),
                            "p_binomial_sobre_rechazo": _cola_binomial(reps, k, float(a)),
                            "wilson95": _wilson(k, reps)}
                o = res["filas"][i]
                i += 1
                esperado = {"regla": regla, "proceso": pr, "n": n, "degeneradas": f["degeneradas"]}
                for a in bandas:
                    esperado[f"rechazo_{a}"] = f[a]["tasa"]
                    esperado[f"cumple_{a}"] = f[a]["cumple"]
                if o != esperado:
                    fallas.append(f"recuento distinto del main() congelado en {regla} {pr} {n}")
                filas.append(f)
    if i != len(res["filas"]):
        fallas.append("número de filas distinto")
    # 2. Coherencia entre reglas.
    incoherentes = 0
    for pr in par["procesos"]:
        for n in par["tamanos"]:
            for (p1, g1), (p2, g2) in zip(datos[("bootstrap_t_l20", pr, n)], datos[("respaldo_max", pr, n)], strict=True):
                incoherentes += (p2 < p1) or (g1 != g2)
    if incoherentes:
        fallas.append(f"{incoherentes} réplicas con p_respaldo < p_primaria o degeneración distinta")
    # 3. Recalculo de una muestra de réplicas en este proceso.
    rng = random.Random(SEMILLA_MUESTRA)
    muestra, distintas = 0, 0
    for regla, respaldo in REGLAS:
        for pr in par["procesos"]:
            for n in par["tamanos"]:
                for r in sorted(rng.sample(range(reps), 2)):
                    o = cal._replica(pr, n, r, semilla, b, respaldo)
                    muestra += 1
                    distintas += [o["p"], o["degenerada"]] != datos[(regla, pr, n)][r]
    if distintas:
        fallas.append(f"{distintas} de {muestra} réplicas recalculadas no coinciden")
    # 4. Decisión vinculante (A-S1) y lectura descriptiva (Holm, no vinculante).
    cumple = {}
    for regla, _ in REGLAS:
        fr = [f for f in filas if f["regla"] == regla]
        cumple[regla] = all(f[a]["cumple"] for f in fr for a in bandas)
        ps = [f[a]["p_binomial_sobre_rechazo"] for f in fr for a in bandas]
        for (f, a), h in zip([(f, a) for f in fr for a in bandas], _holm(ps), strict=True):
            f[a]["sobre_rechazo_holm"] = h
    if cumple["bootstrap_t_l20"]:
        decision = "PRUEBA_PRIMARIA_VALIDADA: se usa tal cual (bootstrap-t por bloques, ℓ = 20)"
    elif cumple["respaldo_max"]:
        decision = "SE_USA_LA_REGLA_DE_RESPALDO: p = máx(p_ℓ20, p_ℓ40, p_NW), declarada en cada prerregistro"
    else:
        decision = "METODO_NO_VALIDADO: ninguna evaluación confirmatoria puede usarlo; rediseño como versión nueva"
    out = {"fallas_de_verificacion": fallas, "replicas_recalculadas": muestra, "replicas_incoherentes": incoherentes,
           "cumple_criterio_congelado": cumple, "decision_vinculante": decision,
           "incumplimientos": [(f["regla"], f["proceso"], f["n"], a) for f in filas for a in bandas
                               if not f[a]["cumple"]],
           "sobre_rechazo_holm_no_vinculante": [(f["regla"], f["proceso"], f["n"], a) for f in filas for a in bandas
                                                if f[a]["sobre_rechazo_holm"]],
           "subrechazos": [(f["regla"], f["proceso"], f["n"], a) for f in filas for a in bandas if f[a]["subrechazo"]],
           "filas": filas, "resultado_sha256": _sha(sal / "resultado_calibracion.json")}
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "verificacion.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    t = ["| Regla | Proceso | n | Degeneradas | Rechazo 2,5 % | Cumple | p binomial | Rechazo 5 % | Cumple | p binomial |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for f in filas:
        celdas = []
        for a in bandas:
            x = f[a]
            marca = "sí" if x["cumple"] else "**NO**"
            marca += " (sub)" if x["subrechazo"] else ""
            marca += " (Holm)" if x["sobre_rechazo_holm"] else ""
            celdas += [f"{x['tasa'] * 100:.2f} % ({x['rechazos']})", marca, f"{x['p_binomial_sobre_rechazo']:.3g}"]
        t.append(f"| {f['regla']} | {f['proceso']} | {f['n']} | {f['degeneradas']} | " + " | ".join(celdas) + " |")
    (dest / "TABLA_CALIBRACION.md").write_text("\n".join(t) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("fallas_de_verificacion", "replicas_recalculadas", "replicas_incoherentes",
                                         "cumple_criterio_congelado", "decision_vinculante", "incumplimientos",
                                         "sobre_rechazo_holm_no_vinculante", "subrechazos")},
                     ensure_ascii=False, indent=1))
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])))
