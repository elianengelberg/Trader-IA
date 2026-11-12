"""Convierte resultado_e1.json en tablas Markdown para el informe (no calcula nada nuevo).
Uso: python3 -I tablas.py <resultado_e1.json>"""
import json
import sys

d = json.load(open(sys.argv[1], encoding="utf-8"))
C = d["configuraciones"]
NOM = {"P1": "P1 trend_following", "P2": "P2 mean_reversion", "P3": "P3 breakout", "S1": "S1 fusión (bot)"}


def f(x, n=2, pct=False):
    if x is None or isinstance(x, str):
        return "—" if x is None else x
    return f"{x:+.{n}f}{' %' if pct else ''}" if pct else f"{x:.{n}f}"


print("### Resultado principal (solo largos, costos base)\n")
print("| Config. | Ops. | Media neta/op. | IC90 (mensual) | P(>0) | IC90 (trimestral) | Mediana | Acierto | Bruta/op. | Nulo: media | p_nulo | Veredicto |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for k in ("P1", "P2", "P3", "S1"):
    c = C[k]; de = c["descripcion"]; b = c.get("bootstrap_mensual", {}); bt = c.get("bootstrap_trimestral", {}); nu = c.get("nulo_entrada_aleatoria", {})
    ver = d["decision"]["veredicto"].get(k, "secundaria (no decide)")
    print(f"| {NOM[k]} | {de.get('n')} | {f(de.get('media_neta_pct'), 3, True)} | [{f(b.get('ic90', [None])[0], 3)}, {f(b.get('ic90', [None, None])[1], 3)}] | "
          f"{f(b.get('P_media_mayor_0'), 3)} | [{f(bt.get('ic90', [None])[0], 3)}, {f(bt.get('ic90', [None, None])[1], 3)}] | {f(de.get('mediana_pct'), 3)} | "
          f"{f(de.get('tasa_acierto'), 2)} | {f(de.get('media_bruta_pct'), 3, True)} | {f(nu.get('media_nulo_pct'), 3)} | {f(nu.get('p_nulo'), 4)} | {ver} |")

print("\n### Holm\n")
for nombre, h in (("signo", d["decision"]["holm_signo"]), ("nulo", d["decision"]["holm_nulo"])):
    print(nombre, {k: (round(v["p"], 4), round(v["umbral_holm"], 4), v["rechaza_nulo"]) for k, v in h.items()})

print("\n### Estrés y variantes (media neta por operación, % ; n)\n")
print("| Config. | Base | Comisión ×2 (S2) | +1 barra (S3) | Costos mínimos (S4) | Gobernadores en vivo (S6) | Motor original (S7) |")
print("|---|---|---|---|---|---|---|")
for k in ("P1", "P2", "P3", "S1"):
    fila = [NOM[k]]
    for pref in ("", "S2|", "S3|", "S4|", "S6|", "S7|"):
        c = C.get(f"{pref}{k}" if pref else k)
        fila.append("—" if c is None else f"{f(c['descripcion'].get('media_neta_pct'), 3)} ({c['descripcion'].get('n')})")
    print("| " + " | ".join(fila) + " |")

print("\n### Subperíodos y régimen ex ante (media neta %, n)\n")
for k in ("P1", "P2", "P3", "S1"):
    c = C[k]
    print(NOM[k], {a: (f(b["media_pct"], 3), b["n"]) for a, b in c.get("por_subperiodo", {}).items()},
          {a: (f(b["media_pct"], 3), b["n"]) for a, b in c.get("por_regimen_ex_ante_30d", {}).items()})

print("\n### Curva de capital y referencias\n")
print("| Serie | Rent. total | Anualizada | Vol. anual | Sharpe | Sortino | Caída máx. | Exposición |")
print("|---|---|---|---|---|---|---|---|")
for k in ("P1", "P2", "P3", "S1"):
    m = C[k]["metricas_curva"]
    print(f"| {NOM[k]} | {f(m['total_return_pct'], 2)} % | {f(m['annualized_return_pct'], 2)} % | {f(m['annualized_volatility_pct'], 2)} % | {f(m['sharpe'], 2)} | {f(m['sortino'], 2)} | {f(m['max_drawdown_pct'], 2)} % | {f(m['exposure_pct'], 1)} % |")
for k, m in d["referencias"].items():
    print(f"| {k} | {f(m['total_return_pct'], 2)} % | {f(m['annualized_return_pct'], 2)} % | {f(m['annualized_volatility_pct'], 2)} % | {f(m['sharpe'], 2)} | {f(m['sortino'], 2)} | {f(m['max_drawdown_pct'], 2)} % | {f(m['exposure_pct'], 1)} % |")

print("\n### Distribución por operación, salidas, confianza y cortos hipotéticos\n")
for k in ("P1", "P2", "P3", "S1"):
    de = C[k]["descripcion"]
    print(NOM[k], {x: de.get(x) for x in ("cuantiles_pct", "ganancia_media_pct", "perdida_media_pct", "factor_beneficio", "peor_racha_perdedora",
                                          "comisiones_medias_pct", "barras_medias")})
    print("   salidas:", de.get("por_razon_salida"))
    print("   confianza:", C[k].get("confianza"))
    s5 = C.get(f"S5|{k}", {})
    if "solo_cortos_hipoteticos" in s5:
        sc = s5["solo_cortos_hipoteticos"]
        print("   cortos hipotéticos (S5):", sc.get("n"), f(sc.get("media_neta_pct"), 3), sc.get("bootstrap_mensual"),
              "| largos en S5:", s5["solo_largos"].get("n"), f(s5["solo_largos"].get("media_neta_pct"), 3))
    if f"S6|{k}" in C:
        print("   gobernadores en vivo (S6):", C[f"S6|{k}"].get("gobernadores"))
    print("   decisiones:", C[k]["decisiones"])
print("\nmeta:", {k: v for k, v in d["meta"].items() if k != "datos"})
