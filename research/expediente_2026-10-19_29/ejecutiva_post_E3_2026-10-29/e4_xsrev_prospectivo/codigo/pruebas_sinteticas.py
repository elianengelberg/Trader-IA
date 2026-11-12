"""E4 · Pruebas del núcleo con datos SINTÉTICOS (generados acá, rotulados como sintéticos; no son históricos ni se presentan
como tales). No usan red ni datos reales. Uso: python3 -I -B pruebas_sinteticas.py <salida.json>
  P1 nulo: tasa de «RESPALDADA» sin efecto ≈ α = 0,025;
  P2 efecto plantado (reversión): se detecta y el IC estimado se acerca al plantado;
  P3 fuga de futuro: leer más allá del límite lanza FugaDeFuturo; alterar el día t (saltado) o días ≥ t+2 no cambia la
     formación t; alterar t+1 sí cambia el IC (control);
  P4 exclusiones fijas y de tokens apalancados;
  P5 salidas: un par sin vela en t+1 sale del IC y rinde 0 en la cartera;
  P6 rotación y costos;
  P7 clasificación prerregistrada con secuencias de IC construidas."""
import json
import math
import sys

import numpy as np

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import nucleo as N  # noqa: E402

RES = {"aviso": "DATOS SINTÉTICOS generados por este script; no son datos históricos"}


def panel(n_monedas, dias, k_rev, semilla, sd=0.04, extras=()):
    rng = np.random.default_rng(semilla)
    z = rng.standard_normal((n_monedas, dias)) * sd
    r = z.copy()
    r[:, 2:] += -k_rev * z[:, :-2]  # r(d) depende de −z(d−2): reversión entre t−1 y t+1
    cierre, volq, ops = {}, {}, {}
    nombres = [f"S{i:03d}USDT" for i in range(n_monedas)] + list(extras)
    for i, s in enumerate(nombres):
        ri = r[i % n_monedas]
        cierre[s] = 100 * np.cumprod(1 + ri)
        volq[s] = np.full(dias, 1e6 * (1 + (i % 50)))
        ops[s] = np.full(dias, 1000)
    return N.Datos(cierre, volq, ops)


def correr(d, t0, t1):
    return [N.dia(d, t) for t in range(t0, t1)]


# P1 y P2: tasa nula y potencia (60 monedas, 285 formaciones)
def tasa(k, sims, semilla0):
    clases, ics = [], []
    for j in range(sims):
        d = panel(60, 320, k, semilla0 + j)
        ev = N.evaluar(correr(d, 31, 316))
        clases.append(ev["clasificacion"])
        ics.append(ev["ic_medio"])
    return clases, ics


cl, ic = tasa(0.0, 200, 1000)
p_fp = cl.count("RESPALDADA_INFORMACION") / len(cl)
RES["P1_nulo"] = {"sims": len(cl), "tasa_RESPALDADA": p_fp, "tasa_EN_CONTRA": cl.count("EN_CONTRA_SIGNO_OPUESTO") / len(cl),
                  "ic_medio_promedio": float(np.mean(ic)), "ok": 0.005 <= p_fp <= 0.06}
cl2, ic2 = tasa(0.06, 60, 5000)
RES["P2_efecto_plantado"] = {"sims": len(cl2), "k_rev": 0.06, "tasa_RESPALDADA": cl2.count("RESPALDADA_INFORMACION") / len(cl2),
                             "ic_medio_promedio": float(np.mean(ic2)), "ok": cl2.count("RESPALDADA_INFORMACION") / len(cl2) >= 0.5}

# P3: fuga de futuro
d = panel(60, 120, 0.06, 7)
t = 60
base = N.dia(d, t)
try:
    N.universo(d.hasta(t - 1), t)  # universo pide hasta t−1 sobre una vista limitada a t−1: debe funcionar
    N.senal(d.hasta(t - 2), t, base["cartera_q"])  # la señal necesita t−1: con límite t−2 debe fallar
    fuga = False
except N.FugaDeFuturo:
    fuga = True


def alterar(dd, dias_alterados):
    c = {s: v.copy() for s, v in dd.cierre.items()}
    for s in c:
        for x in dias_alterados:
            c[s][x:] *= 1.37 if (hash(s) % 2) else 0.71  # cambia el nivel desde x en adelante
    return N.Datos(c, dd.volq, dd.ops)


alt_t = N.dia(alterar(d, [t + 2]), t)
alt_t1 = N.dia(alterar(d, [t + 1]), t)
c_skip = {s: v.copy() for s, v in d.cierre.items()}
for s in c_skip:
    c_skip[s][t] *= 1.5  # solo el día saltado t (afecta r(t) y r(t+1)); la señal y el universo no deben cambiar
alt_skip = N.dia(N.Datos(c_skip, d.volq, d.ops), t)
RES["P3_fuga"] = {"FugaDeFuturo_lanzada": fuga, "alterar_t+2_no_cambia_ic": alt_t["ic"] == base["ic"],
                  "alterar_t+1_cambia_ic": alt_t1["ic"] != base["ic"],
                  "alterar_t_no_cambia_universo_ni_cartera": alt_skip["cartera_q"] == base["cartera_q"]}
RES["P3_fuga"]["ok"] = all(RES["P3_fuga"].values())

# P4: exclusiones
todos = {"BTCUSDT", "BTCUPUSDT", "FOOUPUSDT", "USDCUSDT", "EURUSDT", "ETHBULLUSDT"}
RES["P4_exclusiones"] = {"BTCUP": N.excluido("BTCUPUSDT", todos), "FOOUP_sin_FOO": N.excluido("FOOUPUSDT", todos),
                         "USDC": N.excluido("USDCUSDT", todos), "EUR": N.excluido("EURUSDT", todos), "BTC": N.excluido("BTCUSDT", todos),
                         "ETHBULL_sin_ETH": N.excluido("ETHBULLUSDT", todos)}
e = RES["P4_exclusiones"]
e["ok"] = e["BTCUP"] and not e["FOOUP_sin_FOO"] and e["USDC"] and e["EUR"] and not e["BTC"] and not e["ETHBULL_sin_ETH"]

# P5: salida en t+1
d5 = panel(60, 120, 0.0, 11)
q = N.dia(d5, t)["cartera_q"]
victima = q[0]
d5.ops[victima][t + 1:] = 0
r5 = N.dia(d5, t)
RES["P5_salidas"] = {"salidas": r5["salidas"], "n_ic": r5["n_ic"], "n_universo": r5["n_universo"], "ok": r5["salidas"] == 1 and r5["n_ic"] == r5["n_universo"] - 1}

# P6: rotación y costos
fijo = [{"evaluable": True, "cartera_q": ["A", "B"]}] * 3
cambio = [{"evaluable": True, "cartera_q": ["A", "B"]}, {"evaluable": True, "cartera_q": ["C", "D"]}]
RES["P6_rotacion"] = {"fija": N.rotacion(fijo), "total": N.rotacion(cambio), "ok": N.rotacion(fijo) == [1.0, 0.0, 0.0] and N.rotacion(cambio) == [1.0, 1.0]}


# P7: clasificación
def dias_ic(vals):
    return [{"evaluable": True, "ic": v, "ret_q": 0.0, "ret_ew": 0.0, "cartera_q": ["A"]} for v in vals]


rng = np.random.default_rng(3)
RES["P7_clasificacion"] = {
    "positivo": N.evaluar(dias_ic(0.04 + 0.1 * rng.standard_normal(365)))["clasificacion"],
    "negativo": N.evaluar(dias_ic(-0.04 + 0.1 * rng.standard_normal(365)))["clasificacion"],
    "cero_preciso": N.evaluar(dias_ic(0.0 + 0.02 * rng.standard_normal(365)))["clasificacion"],
    "cero_ruidoso": N.evaluar(dias_ic(0.0 + 0.2 * rng.standard_normal(365)))["clasificacion"],
    "pocos_dias": N.evaluar(dias_ic(0.04 + 0.1 * rng.standard_normal(100)))["clasificacion"],
}
p7 = RES["P7_clasificacion"]
p7["ok"] = (p7["positivo"] == "RESPALDADA_INFORMACION" and p7["negativo"] == "EN_CONTRA_SIGNO_OPUESTO" and
            p7["cero_preciso"] == "REFUTADA_TAMANO_RELEVANTE" and p7["cero_ruidoso"] == "INSUFICIENTE" and p7["pocos_dias"] == "INVALIDO")
RES["todas_ok"] = all(v.get("ok") for k, v in RES.items() if isinstance(v, dict))
json.dump(RES, open(sys.argv[1], "w"), ensure_ascii=False, indent=1, default=float)
print(json.dumps({k: (v.get("ok") if isinstance(v, dict) else v) for k, v in RES.items()}, ensure_ascii=False))
print(json.dumps({"P1": RES["P1_nulo"], "P2": RES["P2_efecto_plantado"]}, ensure_ascii=False))
