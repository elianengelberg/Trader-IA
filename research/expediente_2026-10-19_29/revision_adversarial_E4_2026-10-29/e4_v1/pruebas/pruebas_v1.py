"""E4 v1 · Pruebas NUEVAS (solo de lo que cambió respecto de la v0). Datos SINTÉTICOS generados aquí; ninguno es histórico.
U1 rangos promedio · U2 lectura de ZIP (encabezado, ms/µs, día equivocado, filas) · U3 exclusiones (paridad, envoltorios)
U4 fuga de futuro con entrada horaria · U5 límites de Lan-DeMets · U6 α y cobertura del diseño de dos miradas (simulación)
U7 potencia simulada vs analítica · U8 verificación de CONGELACION.
Uso: python -I -B pruebas_v1.py <salida.json>"""
import datetime as dt
import hashlib
import io
import json
import math
import os
import sys
import tempfile
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
COD = os.path.join(os.path.dirname(AQUI), "codigo")
sys.path.insert(0, COD)
import numpy as np  # noqa: E402

import evaluar as E  # noqa: E402
import nucleo as N  # noqa: E402
import secuencial as SQ  # noqa: E402

res = {"aviso": "DATOS SINTÉTICOS generados por este script; no son datos históricos"}

# U1 · Spearman con empates: rangos promedio
r = N.rangos([3.0, 1.0, 2.0, 2.0])
u1a = list(r) == [3.0, 0.0, 1.5, 1.5]
u1b = abs(N.spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1) < 1e-12 and abs(N.spearman([1, 2, 3, 4], [4, 3, 2, 1]) + 1) < 1e-12
u1c = abs(N.spearman([1, 2, 2, 3], [1, 2, 3, 4]) - 0.9486832980505138) < 1e-12  # Pearson de rangos (0,1.5,1.5,3) y (0,1,2,3)
res["U1_rangos"] = bool(u1a and u1b and u1c)


# U2 · Lectura de ZIP
def zipcsv(filas, nombre="X-1d-2030-01-02.csv"):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(nombre, "".join(",".join(map(str, f)) + "\n" for f in filas))
    return b.getvalue()


d = dt.date(2030, 1, 2)
ms = int(dt.datetime.combine(d, dt.time(), dt.timezone.utc).timestamp() * 1000)
fila = [ms, 1, 1, 1, 123.5, 1, ms + 86399999, 4.5e6, 900, 0, 0, 0]
enc = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count", "tb", "tq", "ignore"]
casos = {}
with tempfile.TemporaryDirectory(dir="/dev/shm") as tmp:
    def caso(nombre, contenido, f, *a):
        p = os.path.join(tmp, nombre + ".zip")
        open(p, "wb").write(contenido)
        try:
            return f(p, *a)
        except ValueError as e:
            return "ERROR:" + str(e)[:40]
    casos["1d_ms"] = caso("a", zipcsv([fila]), E.leer_1d, d) == (123.5, 4.5e6, 900.0)
    casos["1d_us"] = caso("b", zipcsv([[ms * 1000] + fila[1:]]), E.leer_1d, d) == (123.5, 4.5e6, 900.0)
    casos["1d_encabezado"] = caso("c", zipcsv([enc, fila]), E.leer_1d, d) == (123.5, 4.5e6, 900.0)
    casos["1d_dia_equivocado"] = str(caso("d", zipcsv([fila]), E.leer_1d, d + dt.timedelta(days=1))).startswith("ERROR")
    casos["1d_dos_filas"] = str(caso("e", zipcsv([fila, fila]), E.leer_1d, d)).startswith("ERROR")
    horas = [[ms + 3600000 * h, 1, 1, 1, 100 + h, 1, ms + 3600000 * (h + 1) - 1, 1, 1, 0, 0, 0] for h in range(24)]
    casos["1h_hora0"] = caso("f", zipcsv(horas), E.leer_1h, d) == 100.0
    casos["1h_us_encabezado"] = caso("g", zipcsv([enc] + [[h[0] * 1000] + h[1:] for h in horas]), E.leer_1h, d) == 100.0
    casos["1h_sin_hora0"] = caso("h", zipcsv(horas[1:]), E.leer_1h, d) == 0.0
    casos["1h_25_filas"] = str(caso("i", zipcsv(horas + horas[:1]), E.leer_1h, d)).startswith("ERROR")
res["U2_lectura"] = {"casos": casos, "ok": all(casos.values())}

# U3 · Exclusiones: paridad (objetiva) y envoltorios
rng = np.random.default_rng(1)
T = 40
sim = {f"S{i:02d}USDT": 100 * np.cumprod(1 + rng.standard_normal(T) * 0.04) for i in range(31)}
sim["NUEVAUSDUSDT"] = 1 + rng.standard_normal(T) * 0.001        # estable no listada en la lista fija
sim["WBTCUSDT"] = 100 * np.cumprod(1 + rng.standard_normal(T) * 0.04)
sim["CASIUNOUSDT"] = 1.0 * np.cumprod(1 + rng.standard_normal(T) * 0.03)  # cotiza cerca de 1 pero se mueve
vol = {s: np.full(T, 1e9 if s == "NUEVAUSDUSDT" else 1e6) for s in sim}
ops = {s: np.full(T, 100.0) for s in sim}
U = N.universo(N.Datos(sim, vol, ops), 35)
res["U3_exclusiones"] = {"estable_nueva_excluida": "NUEVAUSDUSDT" not in U, "envoltorio_excluido": "WBTCUSDT" not in U,
                         "casi_uno_volatil_incluido": "CASIUNOUSDT" in U, "n": len(U)}
res["U3_exclusiones"]["ok"] = all(v for k, v in res["U3_exclusiones"].items() if k != "n")

# U4 · Fuga de futuro con entrada horaria: dia(t) solo puede leer hasta t+1; cambiar t+2 no cambia nada; cambiar t+1 sí
T, n = 60, 40
cierre = {f"S{i:02d}USDT": 100 * np.cumprod(1 + rng.standard_normal(T) * 0.04) for i in range(n)}
entrada = {s: v * (1 + rng.standard_normal(T) * 0.005) for s, v in cierre.items()}
volq = {s: np.full(T, 1e6) for s in cierre}
opsq = {s: np.full(T, 10.0) for s in cierre}
D = N.Datos(cierre, volq, opsq, entrada)
t = 40
base = N.dia(D, t)
lim_ok = True
try:
    N.dia(N.Datos(cierre, volq, opsq, entrada, limite=t), t)
    lim_ok = False
except N.FugaDeFuturo:
    pass
e2 = {s: v.copy() for s, v in entrada.items()}
c2 = {s: v.copy() for s, v in cierre.items()}
for s in e2:
    e2[s][t + 2:] *= 3.0
    c2[s][t + 1:] *= 0.5  # el cierre de t+1 no entra en la formación t
igual = N.dia(N.Datos(c2, volq, opsq, e2), t)["ic"] == base["ic"]
e3 = {s: v.copy() for s, v in entrada.items()}
e3["S00USDT"][t + 1] *= 5.0
cambia = N.dia(N.Datos(cierre, volq, opsq, e3), t)["ic"] != base["ic"]
res["U4_fuga"] = {"limite_t_rechazado": lim_ok, "t_mas_2_y_cierre_t_mas_1_no_influyen": bool(igual), "entrada_t_mas_1_influye": bool(cambia)}
res["U4_fuga"]["ok"] = all(res["U4_fuga"].values())

# U5 · Límites Lan-DeMets O'Brien-Fleming (valores publicados para 2 miradas iguales, α=0,025 unilateral: 2,963 y 1,969)
b1, b2 = SQ.limites(365, 730, 730)
bn, bs = SQ.limites(None, 730, 730)
res["U5_limites"] = {"b1": b1, "b2": b2, "omitida_b2": bs, "ok": abs(b1 - 2.963) < 1e-3 and abs(b2 - 1.969) < 1e-3 and abs(bs - 1.95996) < 1e-4}


# U6/U7 · Simulación del diseño completo con evaluar_mirada (series de IC sintéticas; los demás campos son neutros)
def serie(n, ic, sd, phi, colas, g):
    e = g.standard_t(5, n) / math.sqrt(5 / 3) if colas else g.standard_normal(n)
    x = np.empty(n)
    x[0] = e[0]
    for i in range(1, n):
        x[i] = phi * x[i - 1] + math.sqrt(1 - phi * phi) * e[i]
    return ic + sd * x


def correr(ic, sd, phi, colas, sims, semilla, miradas=(365, 730)):
    g = np.random.default_rng(semilla)
    cuenta = {}
    corte1 = 0
    for _ in range(sims):
        x = serie(miradas[-1], ic, sd, phi, colas, g)
        dias = [{"evaluable": True, "ic": float(v), "ic50": float(v), "ret_q": 0.0, "ret_ew": 0.0, "mercado_senal": 1.0,
                 "cartera_q": ["A"]} for v in x]
        r1 = N.evaluar_mirada(dias[:miradas[0]], 1, miradas)
        if r1["decision"] == "FINAL":
            corte1 += 1
            c = r1["clasificacion"]
        else:
            c = N.evaluar_mirada(dias, 2, miradas, r1["n_evaluables"] if r1["decision"] == "CONTINUAR" else None)["clasificacion"]
        c = "RESPALDADA_INFORMACION" if c.startswith("RESPALDADA") else c
        cuenta[c] = cuenta.get(c, 0) + 1
    return {k: v / sims for k, v in sorted(cuenta.items())} | {"corte_en_mirada_1": corte1 / sims, "sims": sims}


SIMS = 4000
u6 = {"nulo_normal_iid": correr(0.0, 0.15, 0.0, False, SIMS, 11), "nulo_t5_ar01": correr(0.0, 0.15, 0.1, True, SIMS, 12),
      "ic_igual_sesoi_t5_ar01": correr(0.01, 0.15, 0.1, True, SIMS, 13)}
se = math.sqrt(0.025 * 0.975 / SIMS)
lim = 0.025 + 3 * se
u6["ok"] = (all(u6[k].get("RESPALDADA_INFORMACION", 0) <= lim and u6[k].get("EN_CONTRA_SIGNO_OPUESTO", 0) <= lim for k in ("nulo_normal_iid", "nulo_t5_ar01"))
            and u6["ic_igual_sesoi_t5_ar01"].get("REFUTADA_IC_MINIMO", 0) <= lim)
u6["criterio"] = f"tasas ≤ 0,025 + 3·EE de Monte Carlo = {lim:.4f} (RESPALDADA y EN_CONTRA bajo el nulo; REFUTADA con IC = SESOI)"
res["U6_alfa_y_cobertura"] = u6
p1, pt = SQ.potencia(0.02, 0.15, 0.0, 365, 730, 730, SQ.limites_nw(365, 730, 730))  # mismos límites que la evaluación
u7 = correr(0.02, 0.15, 0.0, False, 2000, 14)
u7["analitica"] = {"corte_en_mirada_1": p1, "potencia_total": pt}
u7["ok"] = abs(u7.get("RESPALDADA_INFORMACION", 0) - pt) < 0.03 and abs(u7["corte_en_mirada_1"] - p1) < 0.04
res["U7_potencia"] = u7

# U8 · CONGELACION: válida pasa; un hash alterado o un .py sin congelar se rechazan
with tempfile.TemporaryDirectory(dir="/dev/shm") as tmp:
    pre = os.path.join(tmp, "PRERREGISTRO.md")
    open(pre, "w").write("prueba\n")
    def h(p):
        return hashlib.sha256(open(p, "rb").read()).hexdigest()
    pys = sorted(f for f in os.listdir(COD) if f.endswith(".py"))
    lineas = [f"{h(pre)}  PRERREGISTRO.md"] + [f"{h(os.path.join(COD, f))}  codigo/{f}" for f in pys]
    def prueba(ls):
        c = os.path.join(tmp, "C.txt")
        open(c, "w").write("\n".join(ls) + "\n")
        try:
            E.verificar_congelacion(c)
            return "ACEPTADA"
        except SystemExit as e:
            return "RECHAZADA: " + str(e)[:50]
    alterada = lineas[:1] + [("0" * 64) + lineas[1][64:]] + lineas[2:]
    u8 = {"valida": prueba(lineas), "hash_alterado": prueba(alterada), "py_sin_congelar": prueba(lineas[:-1]),
          "prerregistro_alterado": (open(pre, "a").write("x"), prueba(lineas))[1]}
u8["ok"] = u8["valida"] == "ACEPTADA" and all(v.startswith("RECHAZADA") for k, v in u8.items() if k != "valida")
res["U8_congelacion"] = u8

res["todas_ok"] = all(v.get("ok", True) if isinstance(v, dict) else v for k, v in res.items() if k.startswith("U"))
json.dump(res, open(sys.argv[1], "w"), ensure_ascii=False, indent=1, default=str)
print(json.dumps({k: (v.get("ok") if isinstance(v, dict) else v) for k, v in res.items() if k.startswith("U")} | {"todas_ok": res["todas_ok"]}))
