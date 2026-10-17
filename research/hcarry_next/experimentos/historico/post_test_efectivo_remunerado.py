"""EXPLORATORIO POSTERIOR al test: ¿cambia la comparación si el efectivo ocioso rinde la tasa libre de riesgo?

El prerregistro compara rev. 5 y UmbralFunding con efectivo a 0 % (P1), pero exige a rev. 5 superar un comparador
del 5 % (P2): un marco incoherente que castiga por construcción a toda política que sale del mercado. Aquí el USDT
ocioso de la cuenta spot (U) rinde la letra del Tesoro a 3 meses (FRED DTB3) menos un recorte; variante extrema: también
el margen de futuros (W). Aproximación de coste de oportunidad, NO un rendimiento realizable sin fricción.

Uso: PYTHONPATH=src .venv/bin/python -B experimentos/historico/post_test_efectivo_remunerado.py"""

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

from hcarry.lab import experimento as X
from hcarry.lab import historico as H

AQUI = Path(__file__).resolve().parent
DATOS = {"fuente": "binance_vision", "directorio": str(AQUI.parents[1] / "datos" / "binance_vision"),
         "desde": "2020-01-01", "hasta": "2026-06-01"}
DIVISIONES = {"desarrollo": ("2020-01-01", "2023-01-01"), "validacion": ("2023-01-01", "2024-02-01"),
              "test": ("2024-02-01", "2026-06-01")}


def tbill() -> dict[str, float]:
    tasas, ultima = {}, None
    filas = list(csv.DictReader((AQUI / "post_test" / "externos" / "DTB3.csv").open(encoding="utf-8")))
    d0 = dt.date.fromisoformat(filas[0]["observation_date"])
    d1 = dt.date.fromisoformat(filas[-1]["observation_date"])
    por_fecha = {f["observation_date"]: f["DTB3"] for f in filas}
    d = d0
    while d <= d1 + dt.timedelta(days=3):
        v = por_fecha.get(d.isoformat())
        if v not in (None, "", "."):
            ultima = float(v) / 100
        tasas[d.isoformat()] = ultima
        d += dt.timedelta(days=1)
    return tasas


def ajustar(r, tasas: dict[str, float], recorte: float, con_margen: bool) -> dict:  # type: ignore[no-untyped-def]
    extra, previa = 0.0, None
    for fila in r.serie:
        if previa is not None:
            dia = dt.datetime.fromtimestamp((fila[0] - 1) / 1000, dt.UTC).date().isoformat()
            tasa = max(0.0, tasas[dia] - recorte)
            ocioso = previa[2] + (previa[3] if con_margen else 0.0)
            extra += max(0.0, ocioso) * tasa / 8760
        previa = fila
    final = r.final + extra
    anos = r.dias / 365
    return {"cagr": (final / r.capital) ** (1 / anos) - 1, "extra": extra}


def main() -> None:
    assert (AQUI / "resultados" / "historico" / H.CERROJO_TEST).exists(), "solo después de consumir el test"
    tasas = tbill()
    pols = dict(H.PRERREGISTRO["politicas"])
    pols["efectivo"] = {"nombre": "efectivo", "params": {}}
    out: dict = {"categoria": "EXPLORATORIO posterior al test (no independiente); supuesto de efectivo remunerado",
                 "codigo_sha256": X.huella_codigo(), "fuente_tasa": "FRED DTB3 (ver post_test/externos/PROCEDENCIA.json)",
                 "resultados": {}}
    for div, (a, b) in DIVISIONES.items():
        tb = [v for k, v in tasas.items() if a <= k < b and v is not None]
        out["resultados"][div] = {"tbill_media": sum(tb) / len(tb)}
        for n, p in pols.items():
            r = X.correr(H._cfg(f"efrem_{div}_{n}", DATOS, {"desde": a, "hasta": b}, p))[0]
            anos = r.dias / 365
            fila = {"cagr_efectivo_0": (r.final / r.capital) ** (1 / anos) - 1}
            for rec in (0.0, 0.01):
                fila[f"cagr_U_recorte_{rec:g}"] = ajustar(r, tasas, rec, False)["cagr"]
            fila["cagr_U_y_margen_recorte_0"] = ajustar(r, tasas, 0.0, True)["cagr"]
            out["resultados"][div][n] = fila
    (AQUI / "post_test" / "efectivo_remunerado.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                                                 encoding="utf-8")
    for div, v in out["resultados"].items():
        print(div, f"T-bill media {v['tbill_media']:.2%}")
        for n in pols:
            print("  ", n, {k: f"{x:.2%}" for k, x in v[n].items()})


if __name__ == "__main__":
    main()


def techo_alternancia(div: str, tasas: dict[str, float], mult_coste: float = 1.0) -> dict:
    """Oráculo (NO realizable): alternar entre carry (rev. 5, nocional/equity observado) y efectivo al T-bill, con el
    coste de ida y vuelta, conociendo el futuro. Cota superior de cualquier regla «carry o efectivo»."""
    a, b = DIVISIONES[div]
    r = X.correr(H._cfg(f"techo_{div}", DATOS, {"desde": a, "hasta": b}, H.PRERREGISTRO["politicas"]["rev5"]))[0]
    eq = {fila[0]: fila[1] for fila in r.serie}
    pasos = []
    for x in r.funding:
        e = eq.get(x["t"], r.capital)
        dia = dt.datetime.fromtimestamp((x["t"] - 1) / 1000, dt.UTC).date().isoformat()
        pasos.append((x["importe"] / e, (tasas[dia] or 0.0) * 8 / 8760))  # por evento, en fracción del equity
    n_sobre_e = sum(abs(x["importe"] / x["tasa"]) / eq.get(x["t"], r.capital) for x in r.funding
                    if abs(x["tasa"]) > 1e-12) / len(r.funding)
    c = 2 * (10 + 5 + 5 + 5) * 1e-4 * n_sobre_e * mult_coste  # ida y vuelta en fracción del equity
    carry, efectivo = 0.0, -c / 2  # se empieza en carry (entrada ya pagada por rev. 5) o en efectivo
    for g_carry, g_ef in pasos:
        carry, efectivo = max(carry, efectivo - c / 2) + g_carry, max(efectivo, carry - c / 2) + g_ef
    anos = r.dias / 365
    siempre_carry = sum(p[0] for p in pasos)
    siempre_efectivo = sum(p[1] for p in pasos)
    return {"oraculo_pp_anual": max(carry, efectivo) / anos * 100, "siempre_carry_pp_anual": siempre_carry / anos * 100,
            "siempre_efectivo_pp_anual": siempre_efectivo / anos * 100}

