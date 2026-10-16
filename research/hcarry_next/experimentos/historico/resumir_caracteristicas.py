"""Resume las características operativas de la regla prerregistrada (SINTÉTICO) → resultados/caracteristicas/RESUMEN.md"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

AQUI = Path(__file__).resolve().parent


def main() -> None:
    filas = [json.loads(linea) for log in sorted(AQUI.glob("caracteristicas_*.log"))
             for linea in log.read_text(encoding="utf-8").splitlines() if linea.startswith("{")]
    assert all(f["categoria"] == "sintetico" and f["conclusion_oficial"] == "EVIDENCIA INSUFICIENTE" for f in filas)
    out = ["# Características operativas de la regla prerregistrada (SINTÉTICO)", "",
           ("**No es evidencia económica.** Cada mundo recorrió el pipeline real (formato oficial, manifiesto, calidad y "
           "evaluador). La conclusión oficial fue siempre EVIDENCIA INSUFICIENTE, por ser datos sintéticos. La tabla "
           "muestra la conclusión **en sombra**, es decir, la que daría la regla si los datos fueran históricos."), "",
           ("| Variante | Mundos | VENTAJA RESPALDADA | HIPÓTESIS NO RESPALDADA | EVIDENCIA INSUFICIENTE | "
           "Persistencia mediana (7 d) | CAGR test rev5 / umbral (medianas) |"), "|---|---|---|---|---|---|---|"]
    for variante in sorted({f["variante"] for f in filas}):
        for nulo in (False, True):
            sub = [f for f in filas if f["variante"] == variante and f["nulo"] == nulo]
            if not sub:
                continue
            c = Counter(f["sombra_P1"] for f in sub)
            pers = statistics.median(f["persistencia"] for f in sub)
            cr = statistics.median(f["cagr_test"]["rev5"] for f in sub)
            cu = statistics.median(f["cagr_test"]["umbral"] for f in sub)
            out.append(f"| {variante}{' NULO' if nulo else ''} | {len(sub)} | {c['VENTAJA RESPALDADA']} | "
                       f"{c['HIPÓTESIS NO RESPALDADA']} | {c['EVIDENCIA INSUFICIENTE']} | {pers:+.2f} | {cr:.2%} / {cu:.2%} |")
    for nulo in (False, True):
        p2 = Counter(f["sombra_P2"] for f in filas if f["nulo"] == nulo)
        out.append(f"\nP2 (carry de rev. 5), mundos {'nulos' if nulo else 'normales'}, en sombra: {dict(p2)}")
    res = {f["mundo"]: json.loads(next((AQUI / "resultados" / "caracteristicas" / f["mundo"]).glob(
        "sintetico/datos_*/resultado.json")).read_text(encoding="utf-8")) for f in filas}
    out += ["", f"Huellas del código en estos resultados: {sorted({r['codigo_sha256'][:12] for r in res.values()})}", "",
            "## Comparación en test con costes base (medianas por grupo)", "",
            ("| Grupo | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación anual | "
             "Liquidaciones (suma) |"), "|---|---|---|---|---|---|---|---|---|"]
    grupos = [(v, n) for v in sorted({f["variante"] for f in filas}) for n in (False, True)]
    for variante, nulo in grupos:
        sub = [res[f["mundo"]]["test"] for f in filas if f["variante"] == variante and f["nulo"] == nulo]
        for pol in ("rev5", "umbral"):
            def med(k: str, sub: list = sub, pol: str = pol) -> float:
                return statistics.median(t[pol][k] for t in sub)
            out.append(f"| {variante}{' NULO' if nulo else ''} | {pol} | {med('cagr_neto'):.2%} | "
                       f"{med('caida_maxima'):.2%} | {med('funding_neto'):.0f} | {med('costes'):.0f} | "
                       f"{med('tiempo_en_mercado'):.0%} | {med('rotacion_anual'):.1f} | "
                       f"{sum(t[pol]['liquidaciones'] for t in sub)} |")
    escenarios = list(next(iter(res.values()))["test"]["sensibilidad"])
    out += ["", "## Sensibilidad en test: umbral − rev. 5 en PnL (mediana) y mundos con diferencia > 0", "",
            "| Grupo | base | " + " | ".join(escenarios) + " |", "|---" * (len(escenarios) + 2) + "|"]
    for variante, nulo in grupos:
        sub = [res[f["mundo"]]["test"] for f in filas if f["variante"] == variante and f["nulo"] == nulo]
        celdas = []
        for esc in [None, *escenarios]:
            difs = [(t["umbral"] if esc is None else t["sensibilidad"][esc]["umbral"])["pnl_neto"]
                    - (t["rev5"] if esc is None else t["sensibilidad"][esc]["rev5"])["pnl_neto"] for t in sub]
            celdas.append(f"{statistics.median(difs):+.0f} ({sum(d > 0 for d in difs)}/{len(difs)})")
        out.append(f"| {variante}{' NULO' if nulo else ''} | " + " | ".join(celdas) + " |")
    d14 = Counter(r["test"]["rev5_R0_d1_d4"]["resultado"] for f, r in zip(filas, res.values(), strict=True)
                  if not f["nulo"])
    out += ["", f"D1–D4 de rev. 5 (reconstrucción, regla R0) en test, mundos normales: {dict(d14)}"]
    out += ["", "## Por mundo", "",
            "| Mundo | P1 en sombra | P(dif > 0) | Diferencia de PnL en test | Estrés | Validación | Persistencia |",
            "|---|---|---|---|---|---|---|"]
    for f in filas:
        d = f["detalles"]
        out.append(f"| {f['mundo']} | {f['sombra_P1']} | {d['p_dif_mayor_que_cero']} | {d['dif_pnl_test']:.0f} | "
                   f"{'ok' if d['estres_ok'] else 'falla'} | {'ok' if d['validacion_mismo_signo'] else 'falla'} | "
                   f"{f['persistencia']:+.2f} |")
    destino = AQUI / "resultados" / "caracteristicas"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "RESUMEN.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
