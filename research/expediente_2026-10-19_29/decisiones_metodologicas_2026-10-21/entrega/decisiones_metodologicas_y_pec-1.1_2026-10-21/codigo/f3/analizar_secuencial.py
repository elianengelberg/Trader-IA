"""Análisis de la calibración secuencial. Escrito y fijado por hash ANTES de la corrida confirmatoria.

Criterio VINCULANTE (de la especificación):
- por celda H₀ (proceso × n_max): α̂ = confirmadas/R y U = cota superior exacta de Clopper–Pearson, unilateral, con
  confianza 1 − 0,05/m (m = número de celdas H₀: Bonferroni, válido con cualquier dependencia entre celdas);
- APTO si U ≤ umbral (0,030) en TODAS las celdas; si no, NO APTO.
Lectura descriptiva (no cambia el veredicto): α̂ frente a 2,5 % y al criterio estricto de Bradley [0,9α; 1,1α]; la
proporción que confirma en cada mirada frente al gasto teórico; la correlación de z_NW entre miradas frente a
√(t_j/t_k) (supuesto de incrementos independientes); la potencia bajo H₁ con su intervalo de Wilson.
Verificación: recalcula en ESTE proceso, con ``inferencia.respaldo`` COMPLETO (sin cortocircuito), por cada celda H₀,
3 trayectorias al azar y hasta 10 de las confirmadas, elegidas con random.Random(semilla_verificacion), y exige la
misma mirada de confirmación.
Uso: python3 -B -I analizar_secuencial.py <paquete_r1> <especificacion.json> <salida> <destino>"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import random
import sys
from pathlib import Path

sys.dont_write_bytecode = True
AQUI = Path(__file__).resolve().parent


def _lbin(n: int, k: int, p: float) -> float:
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * math.log(p) + (n - k) * math.log1p(-p)


def cdf_binomial(n: int, k: int, p: float) -> float:
    if p <= 0:
        return 1.0
    if p >= 1:
        return 0.0 if k < n else 1.0
    return min(1.0, sum(math.exp(_lbin(n, j, p)) for j in range(k + 1)))


def cota_superior_cp(k: int, n: int, gamma: float) -> float:
    """Menor p tal que P(Bin(n, p) ≤ k) ≤ γ: cota superior unilateral exacta con confianza 1 − γ."""
    if k >= n:
        return 1.0
    a, b = k / n, 1.0
    for _ in range(100):
        m = (a + b) / 2
        a, b = (m, b) if cdf_binomial(n, k, m) > gamma else (a, m)
    return b


def wilson(k: int, n: int, z: float = 1.959963984540054) -> list[float]:
    f = k / n
    c = (f + z * z / (2 * n)) / (1 + z * z / n)
    m = z * math.sqrt(f * (1 - f) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [c - m, c + m]


def _corr(a: list[float], b: list[float]) -> float:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    sab = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True))
    saa = sum((x - ma) ** 2 for x in a)
    sbb = sum((y - mb) ** 2 for y in b)
    return sab / math.sqrt(saa * sbb)


def main(paq: Path, esp_ruta: Path, sal: Path, dest: Path) -> int:
    spec = importlib.util.spec_from_file_location("secuencial_mc", AQUI / "secuencial_mc.py")
    sim = importlib.util.module_from_spec(spec)
    sys.modules["secuencial_mc"] = sim
    spec.loader.exec_module(sim)
    esp = json.loads(esp_ruta.read_text(encoding="utf-8"))
    sim.preparar(paq, esp)
    crit = esp["criterio"]
    lista = sim.celdas(esp)
    h0 = [c for c in lista if c["ir"] == 0.0]
    m = len(h0)
    gamma = crit["confianza_conjunta_complemento"] / m
    fallas, filas, potencia = [], [], []
    for c in lista:
        d = json.loads((sal / "celdas" / f"{c['nombre']}.json").read_text(encoding="utf-8"))
        if (len(d["miradas"]), d["B"], d["K"], d["alfa"], d["base"], d["proceso"], d["n_max"]) != (
                c["R"], esp["B"], esp["K"], esp["alfa"], c["base"], c["proceso"], c["n_max"]):
            fallas.append(f"celda mal formada: {c['nombre']}")
        u = sim.umbrales(c["n_max"], esp["K"], esp["alfa"])
        if d["umbrales"] != json.loads(json.dumps(u)):
            fallas.append(f"umbrales distintos: {c['nombre']}")
        por_mirada = [d["miradas"].count(str(k)) for k in range(1, esp["K"] + 1)]
        k = sum(por_mirada)
        if c["ir"] == 0.0:
            U = cota_superior_cp(k, c["R"], gamma)
            zs = [z for z in d["z_nw_primeras"] if all(v is not None for v in z)]
            corr = {f"{i + 1}-{j + 1}": [round(_corr([z[i] for z in zs], [z[j] for z in zs]), 4),
                                         round(math.sqrt(u["t_k"][i] / u["t_k"][j]), 4)]
                    for i in range(esp["K"]) for j in range(i + 1, esp["K"])}
            filas.append({"celda": c["nombre"], "proceso": c["proceso"], "n_max": c["n_max"], "R": c["R"],
                          "confirmadas": k, "alfa_global": k / c["R"], "cota_superior": U,
                          "cumple": U <= crit["umbral_alfa_global"],
                          "bradley_estricto": 0.9 * esp["alfa"] <= k / c["R"] <= 1.1 * esp["alfa"],
                          "por_mirada": por_mirada, "gasto_teorico": u["alfa_por_mirada_teorico"],
                          "bootstraps_calculados": len(d["boots"]), "corr_z_nw_observada_vs_teorica": corr,
                          "trayectorias_con_z_completo": len(zs)})
        else:
            potencia.append({"celda": c["nombre"], "proceso": c["proceso"], "n_max": c["n_max"], "IR": c["ir"],
                             "R": c["R"], "potencia": k / c["R"], "wilson95": wilson(k, c["R"]),
                             "por_mirada": por_mirada,
                             "potencia_analitica_z": sim._PEC["secuencial"].potencia(
                                 u["t_k"], u["c_k"], c["ir"] * math.sqrt(c["n_max"] / 365.25))})
    # Verificación con la regla COMPLETA, sin cortocircuito.
    inf = sim._PEC["inferencia"]
    rng = random.Random(crit["semilla_verificacion"])
    recalculadas, distintas = 0, 0
    for c in h0:
        d = json.loads((sal / "celdas" / f"{c['nombre']}.json").read_text(encoding="utf-8"))["miradas"]
        confirmadas = [r for r, v in enumerate(d) if v != "0"]
        rs = sorted(set(rng.sample(range(c["R"]), 3)) | set(rng.sample(confirmadas, min(10, len(confirmadas)))))
        u = sim.umbrales(c["n_max"], esp["K"], esp["alfa"])
        for r in rs:
            sem = c["base"] * 10 ** 6 + r
            x = sim._PEC["sintetico"].proceso(c["proceso"], c["n_max"], sem)
            mirada = 0
            for k, (nk, a) in enumerate(zip(u["n_k"], u["a_k"], strict=True), start=1):
                try:
                    p = inf.respaldo(x[:nk], esp["B"], sem)["p_unilateral"]
                except inf.ErrorSerieDegenerada:
                    p = 1.0
                if p <= a:
                    mirada = k
                    break
            recalculadas += 1
            distintas += str(mirada) != d[r]
    if distintas:
        fallas.append(f"{distintas} de {recalculadas} trayectorias recalculadas con la regla completa no coinciden")
    apto = all(f["cumple"] for f in filas)
    out = {"fallas_de_verificacion": fallas, "trayectorias_recalculadas_regla_completa": recalculadas,
           "m_celdas_H0": m, "gamma_por_celda": gamma, "umbral": crit["umbral_alfa_global"],
           "veredicto": "APTO" if apto and not fallas else "NO_APTO", "filas_H0": filas, "potencia_H1": potencia,
           "especificacion_sha256": hashlib.sha256(esp_ruta.read_bytes()).hexdigest()}
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "resultado_secuencial.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                                                     encoding="utf-8")
    t = ["| Proceso | n_max | R | Confirmadas | α̂ global | Cota sup. CP | ≤ umbral | Por mirada (1–5) |",
         "|---|---|---|---|---|---|---|---|"]
    for f in filas:
        t.append(f"| {f['proceso']} | {f['n_max']} | {f['R']} | {f['confirmadas']} | {f['alfa_global'] * 100:.3f} % | "
                 f"{f['cota_superior'] * 100:.3f} % | {'sí' if f['cumple'] else '**NO**'} | "
                 f"{' / '.join(map(str, f['por_mirada']))} |")
    t += ["", "| Proceso | n_max | IR | R | Potencia simulada | Wilson 95 % | Analítica (prueba z) |", "|---|---|---|---|---|---|---|"]
    for p in potencia:
        t.append(f"| {p['proceso']} | {p['n_max']} | {p['IR']} | {p['R']} | {p['potencia'] * 100:.1f} % | "
                 f"{p['wilson95'][0] * 100:.1f}–{p['wilson95'][1] * 100:.1f} % | {p['potencia_analitica_z'] * 100:.1f} % |")
    (dest / "TABLA_SECUENCIAL.md").write_text("\n".join(t) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("fallas_de_verificacion", "trayectorias_recalculadas_regla_completa",
                                         "veredicto", "m_celdas_H0", "umbral")}, ensure_ascii=False))
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])))
