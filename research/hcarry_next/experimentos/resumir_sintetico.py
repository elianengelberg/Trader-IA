"""Resume el ensayo del protocolo en mundos SINTÉTICOS y nulos → experimentos/sintetico/RESUMEN.md."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

AQUI = Path(__file__).resolve().parent
BASE = AQUI / "sintetico"


def main() -> None:
    filas = [json.loads(linea) for log in sorted(AQUI.glob("correr_sintetico_*.log"))
             for linea in log.read_text(encoding="utf-8").splitlines() if linea.startswith("{")]
    familias = ("apalancada", "rho_vol", "escala_vol", "umbral", "umbral_apalancado", "prima", "prima_apalancada")
    out = ["# Ensayo del protocolo en mundos SINTÉTICOS", "",
           ("**No es evidencia económica.** Mide qué elige, promueve y declara el protocolo cuando el mundo lo genera "
           "`hcarry.data.sintetico`. En los mundos nulos el funding está barajado en el tiempo (sin persistencia)."), "",
           f"Mundos: {sum(not f['nulo'] for f in filas)} normales y {sum(f['nulo'] for f in filas)} nulos; variantes del generador: {sorted({f['variante'] for f in filas})}.", ""]
    for variante, nulo in [(v, n) for v in sorted({f["variante"] for f in filas}) for n in (False, True)]:
        sub = [f for f in filas if f["nulo"] == nulo and f["variante"] == variante]
        if not sub:
            continue
        out += [f"## Variante {variante}: mundos {'NULOS' if nulo else 'normales'} ({len(sub)})", "",
                ("| familia | seleccionada en desarrollo | promovida a test | componente DEMOSTRADO | "
                "CAGR test mediano (si promovida) | supera a la referencia rev. 5 en test |"), "|---|---|---|---|---|---|"]
        for fam in familias:
            sel = [f for f in sub if fam in f["seleccionados"]]
            nombres = [f["seleccionados"][fam] for f in sel]
            prom = [f for f in sel if any(p.startswith(f["seleccionados"][fam] + " vs") for p in f["promovidos"])]
            tests = [f["test"][f["seleccionados"][fam]] for f in prom if f["seleccionados"][fam] in f["test"]]
            dem = [t for t in tests if t["componente"] == "DEMOSTRADO"]
            cagr = statistics.median(t["cagr"] for t in tests) if tests else None
            vs_ref = sum(1 for t in tests if t["vs_ref"]["pnl_mayor"])
            out.append(f"| {fam} | {len(sel)} | {len(prom)} | {len(dem)} | "
                       f"{'—' if cagr is None else f'{cagr:.2%}'} | {vs_ref}/{len(tests)} |")
            if fam.startswith(("umbral", "prima")) and nombres:
                conteo: dict[str, int] = {}
                for n in nombres:
                    conteo[n] = conteo.get(n, 0) + 1
                out.append(f"|  | parámetros elegidos: {', '.join(f'{k} ×{v}' for k, v in sorted(conteo.items()))} | | | | |")
        refs = [f["ref"]["test"] for f in sub]
        b05 = [f["test_bases"]["siempre_rho05"] for f in sub]
        dds = [f["ref_dd_test"] for f in sub]
        out += ["", (f"Referencia rev. 5 en test: CAGR mediano {statistics.median(refs):.2%} "
                    f"(mín {min(refs):.2%}, máx {max(refs):.2%}); caída mediana {statistics.median(dds):.2%}. "
                    f"Siempre ρ = 0,5: CAGR mediano {statistics.median(b05):.2%}."),
                ""]
    out += ["## Por mundo", "", "| mundo | ref. dev / val / test | promovidos | componentes demostrados |", "|---|---|---|---|"]
    for f in filas:
        dem = [k for k, v in f["test"].items() if v["componente"] == "DEMOSTRADO"]
        out.append(f"| {f['mundo']} | {f['ref']['desarrollo']:.1%} / {f['ref']['validacion']:.1%} / "
                   f"{f['ref']['test']:.1%} | {', '.join(f['promovidos']) or '—'} | {', '.join(dem) or '—'} |")
    (BASE / "RESUMEN.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
