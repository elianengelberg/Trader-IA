"""Análisis EXPLORATORIO POSTERIOR al test (ejecutado una vez el 2026-10-16 20:47 UTC, cerrojo TEST_CONSUMIDO.json).
Usa toda la muestra 2020-01 → 2026-05: ya no es evidencia independiente; sirve para entender por qué salió lo que
salió y para formular hipótesis nuevas, que necesitarían datos nuevos (período reservado con autorización, o prospectivo).

1. Funding por año y trimestre: nivel (APR sobre nocional) y composición (en la tasa base 0,01 %, por debajo, por
   encima, negativo).
2. Techo de las reglas de salida (oráculo E3) en validación y test.
3. Umbral de funding necesario para que rev. 5 supere el comparador del 5 %.

Uso: PYTHONPATH=src .venv/bin/python -B experimentos/historico/post_test_exploratorio.py"""

from __future__ import annotations

import datetime as dt
import json
import statistics as st
from pathlib import Path

from hcarry.data.binance_vision import construir_panel
from hcarry.lab import experimento as X
from hcarry.lab import historico as H

AQUI = Path(__file__).resolve().parent
DIR = AQUI.parents[1] / "datos" / "binance_vision"
DATOS = {"fuente": "binance_vision", "directorio": str(DIR), "desde": "2020-01-01", "hasta": "2026-06-01"}
APR = 3 * 365
BASE = 1e-4


def composicion(tasas: list[float]) -> dict:
    n = len(tasas)
    return {"eventos": n, "apr": st.fmean(tasas) * APR,
            "frac_en_base_0_01": sum(abs(x - BASE) < 1e-9 for x in tasas) / n,
            "frac_positiva_bajo_base": sum(0 <= x < BASE - 1e-9 for x in tasas) / n,
            "frac_sobre_base": sum(x > BASE + 1e-9 for x in tasas) / n,
            "frac_negativa": sum(x < 0 for x in tasas) / n}


def main() -> None:
    assert (AQUI / "resultados" / "historico" / H.CERROJO_TEST).exists(), "solo después de consumir el test"
    panel, _ = construir_panel(DIR, "2020-01-01", "2026-06-01")
    por_ano: dict[str, list[float]] = {}
    por_trim: dict[str, list[float]] = {}
    for e in panel.funding:
        d = dt.datetime.fromtimestamp(e.t / 1000, dt.UTC)
        por_ano.setdefault(str(d.year), []).append(e.tasa)
        por_trim.setdefault(f"{d.year}T{(d.month - 1) // 3 + 1}", []).append(e.tasa)
    out: dict = {"categoria": "EXPLORATORIO posterior al test (no independiente)", "codigo_sha256": X.huella_codigo(),
                 "funding_por_ano": {k: composicion(v) for k, v in por_ano.items()},
                 "funding_por_trimestre": {k: round(st.fmean(v) * APR, 4) for k, v in por_trim.items()}}
    # techo de salidas (oráculo) por división, sobre el funding que cobró rev. 5
    import importlib.util
    spec = importlib.util.spec_from_file_location("inv", AQUI / "investigacion_desarrollo.py")
    inv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inv)  # type: ignore[union-attr]
    out["techo_salidas_pp_anual"] = {}
    for nombre, (a, b) in {"desarrollo": ("2020-01-01", "2023-01-01"), "validacion": ("2023-01-01", "2024-02-01"),
                           "test": ("2024-02-01", "2026-06-01")}.items():
        cfg = H._cfg(f"post_{nombre}", DATOS, {"desde": a, "hasta": b}, H.PRERREGISTRO["politicas"]["rev5"])
        r = X.correr(cfg)[0]
        out["techo_salidas_pp_anual"][nombre] = {str(k): inv.e3_costes(r, k) for k in (0.5, 1, 2)}
        anos = r.dias / 365
        # nocional al precio de cada liquidación: importe = cantidad × mark × tasa
        nocional = st.fmean([abs(x["importe"] / x["tasa"]) for x in r.funding if abs(x["tasa"]) > 1e-12])
        out.setdefault("rev5_por_division", {})[nombre] = {
            "funding_neto_apr_sobre_nocional": r.funding_total / nocional / anos,
            "nocional_medio_sobre_capital": nocional / r.capital,
            "costes_pp_anual_equity": r.costes_total / r.capital / anos * 100}
    # funding necesario para que rev. 5 (ρ = 1) iguale el comparador del 5 % con su coste medio observado
    t = out["rev5_por_division"]["test"]
    out["funding_apr_necesario_para_5pct"] = (0.05 + t["costes_pp_anual_equity"] / 100) / t["nocional_medio_sobre_capital"]
    (AQUI / "post_test" ).mkdir(exist_ok=True)
    (AQUI / "post_test" / "exploratorio.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
