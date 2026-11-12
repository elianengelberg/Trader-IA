"""Informe de calidad SIN retornos: cobertura, huecos, conflictos, coherencia OHLC, volumen cero y decimales.
No calcula ni imprime retornos, niveles de precio ni ninguna medida de rendimiento.
Uso: python -B calidad_datos.py <salida.json> <raiz> [<raiz> ...]"""
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import sim1_comun as S


def _decimales(x: float) -> int:
    d = Decimal(repr(x)).normalize()
    return max(0, -d.as_tuple().exponent)


def main(salida, raices):
    raices = [Path(r) for r in raices]
    out = {}
    for simbolo in ("ETHUSDT", "BTCUSDT"):
        velas, meta = S.leer_velas(raices, simbolo)
        incoherentes = sum(1 for v in velas if not (v.low <= min(v.open, v.close) <= max(v.open, v.close) <= v.high))
        no_positivos = sum(1 for v in velas if min(v.open, v.high, v.low, v.close) <= 0)
        vol_cero = sum(1 for v in velas if v.volume == 0)
        dec_px = Counter(max(_decimales(v.open), _decimales(v.high), _decimales(v.low), _decimales(v.close)) for v in velas)
        dec_vol = Counter(_decimales(v.volume) for v in velas)
        por_anio = Counter(v.open_time.year for v in velas)
        meta_sin_lista = {k: v for k, v in meta.items() if k != "archivos"}
        out[simbolo] = {**meta_sin_lista, "ohlc_incoherentes": incoherentes, "precios_no_positivos": no_positivos,
                        "velas_volumen_cero": vol_cero, "max_decimales_precio": max(dec_px), "max_decimales_volumen": max(dec_vol),
                        "velas_por_anio": dict(sorted(por_anio.items())),
                        "mayor_hueco_horas": max((h for _, h in meta["huecos"]), default=0)}
    Path(salida).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for s, d in out.items():
        print(s, {k: d[k] for k in ("n_archivos", "primera_vela", "ultima_vela", "velas", "faltantes", "mayor_hueco_horas",
                                    "ohlc_incoherentes", "precios_no_positivos", "velas_volumen_cero", "max_decimales_precio",
                                    "max_decimales_volumen")}, "huecos:", len(d["huecos"]), "conflictos:", len(d["horas_en_conflicto_excluidas"]))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
