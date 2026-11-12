"""Tablas en Markdown a partir de resultado_dev.json y/o resultado_oos.json (solo formatea; no recalcula nada).
Uso: python -B tablas_sim1.py <resultado.json> [<resultado.json> ...] > tablas.md"""
import json
import sys


def f(x, d=3):
    if x is None:
        return "—"
    if isinstance(x, (int,)) and not isinstance(x, bool):
        return str(x)
    if isinstance(x, float):
        return f"{x:+.{d}f}" if abs(x) < 1e6 else f"{x:,.0f}"
    return str(x)


def tabla_conjunto(nombre, c, decision=None):
    conf = c["configuraciones"]
    base = [k for k in ("P3", "P1", "P2", "S1", "M1") if k in conf]
    out = [f"### {nombre}", "", f"Velas: {c.get('barras')} · {c.get('primera', c.get('primera_decision'))} → {c.get('ultima')}", ""]
    out += ["**Por operación** (neto en % del nocional; IC90 por bootstrap de bloques mensuales)", "",
            "| Config. | n | Media neta | IC90 | p (media ≤ 0) | Mediana | Acierto | Ganancia media | Pérdida media | F. beneficio | Bruto (S4) | Costo implícito | Comisión ×2 (S2) | +1 vela (S3) | Gobernadores (S6) | Veredicto |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k in base:
        d = conf[k]; de = d["descripcion"]; bs = d.get("bootstrap_mensual") or {}
        sens = d.get("sensibilidad", {})
        ic = bs.get("ic90")
        out.append(f"| {k}{' (q=' + str(d['q_min_confianza']) + ')' if d.get('q_min_confianza') else ''} | {de.get('n')} | {f(de.get('media_neta_pct'))} | "
                   f"{'[' + f(ic[0]) + ', ' + f(ic[1]) + ']' if ic else '—'} | {f(d.get('p_unilateral'))} | {f(de.get('mediana_pct'))} | "
                   f"{f(de.get('tasa_acierto'), 2)} | {f(de.get('ganancia_media_pct'))} | {f(de.get('perdida_media_pct'))} | "
                   f"{f(de.get('factor_beneficio'), 2)} | {f(sens.get('S4'))} | {f(d.get('costo_total_implicito_por_operacion_pct'))} | "
                   f"{f(sens.get('S2'))} | {f(sens.get('S3'))} | {f(sens.get('S6'))} | {(decision or {}).get(k, '—')} |")
    out += ["", "**Capital** (cuenta de 100 000 USDT; curva diaria desde la primera decisión)", "",
            "| Config. | Capital final | Retorno neto total | Anualizado | Volatilidad anual | Sharpe | IC90 Sharpe | Sortino | Máx. caída | Exposición (velas en mercado) | Comisiones (USDT) | Comisión / nocional |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k in base:
        d = conf[k]; ca = d["capital"]; ex = d["exposicion"]
        ic = ca.get("sharpe_ic90_bootstrap_mensual")
        out.append(f"| {k} | {ca['capital_final']:,.2f} | {f(ca['retorno_neto_total_pct'])} % | {f(ca.get('retorno_anualizado_pct'))} % | "
                   f"{f(ca.get('volatilidad_anualizada_pct'))} % | {f(ca.get('sharpe_diario_anualizado'), 2)} | "
                   f"{'[' + f(ic[0], 2) + ', ' + f(ic[1], 2) + ']' if ic else '—'} | {f(ca.get('sortino'), 2)} | {f(ca['max_caida_pct'])} % | "
                   f"{ex['pct_velas_en_mercado_aprox']:.1f} % | {d['comisiones_usdt']:,.2f} | {f(d.get('comisiones_pct_del_nocional_operado'))} % |")
    out += ["", "**Contra el azar** (entrada aleatoria emparejada: mismas duraciones, estratificado por trimestre)", "",
            "| Config. | Media | Media del nulo | Banda90 del nulo | Exceso | p_nulo |", "|---|---|---|---|---|---|"]
    for k in base:
        nu = conf[k].get("nulo_entrada_aleatoria")
        if nu:
            out.append(f"| {k} | {f(conf[k]['descripcion']['media_neta_pct'])} | {f(nu['media_nulo_pct'])} | "
                       f"[{f(nu['banda90_nulo_pct'][0])}, {f(nu['banda90_nulo_pct'][1])}] | {f(nu['exceso_sobre_nulo_pct'])} | {f(nu['p_nulo'])} |")
    subs = list(next(iter(conf[b]["por_subperiodo"] for b in base if "por_subperiodo" in conf[b])).keys()) if base else []
    out += ["", "**Por período** (n · media neta %)", "", "| Config. | " + " | ".join(subs) + " |", "|---|" + "---|" * len(subs)]
    for k in base:
        ps = conf[k].get("por_subperiodo", {})
        out.append(f"| {k} | " + " | ".join(f"{ps[s]['n']} · {f(ps[s]['media_pct'])}" if s in ps else "0 · —" for s in subs) + " |")
    out += ["", "**Por condición de mercado** (retorno de 30 días antes de la entrada; n · media neta %)", "",
            "| Config. | alcista (> +10 %) | lateral | bajista (< −10 %) | ρ confianza–neto |", "|---|---|---|---|---|"]
    for k in base:
        rg = conf[k].get("por_regimen_ex_ante_30d", {})
        cell = lambda r: f"{rg[r]['n']} · {f(rg[r]['media_pct'])}" if r in rg else "—"  # noqa: E731
        out.append(f"| {k} | {cell('alcista')} | {cell('lateral')} | {cell('bajista')} | {f(conf[k].get('confianza', {}).get('spearman'))} |")
    out += ["", "**Referencias** (misma ventana; comisión de 10 bps y deslizamiento de 2 bps donde operan)", "",
            "| Referencia | Retorno total | Anualizado | Volatilidad | Sharpe | Máx. caída | Exposición | Operaciones |", "|---|---|---|---|---|---|---|---|"]
    for k, r in c["referencias"].items():
        out.append(f"| {k} | {f(r['total_return_pct'], 1)} % | {f(r['annualized_return_pct'], 1)} % | {f(r['annualized_volatility_pct'], 1)} % | "
                   f"{f(r['sharpe'], 2)} | {f(r['max_drawdown_pct'], 1)} % | {f(r['exposure_pct'], 1)} % | {r['operaciones']} |")
    return "\n".join(out) + "\n"


def main(paths):
    for p in paths:
        d = json.load(open(p))
        if "conjuntos" in d:
            for nombre, c in d["conjuntos"].items():
                print(tabla_conjunto(nombre, c))
            print("### Regla de promoción de M1\n\n```\n" + json.dumps(d["m1"], indent=1, ensure_ascii=False) + "\n```\n")
        else:
            c = {**d, "primera": d.get("primera_decision")}
            print(tabla_conjunto("OOS-ETH (prueba final, una sola lectura)", c, d["decision"]["veredicto"]))
            print("```\n" + json.dumps(d["decision"], indent=1, ensure_ascii=False) + "\n```\n")


if __name__ == "__main__":
    main(sys.argv[1:])
