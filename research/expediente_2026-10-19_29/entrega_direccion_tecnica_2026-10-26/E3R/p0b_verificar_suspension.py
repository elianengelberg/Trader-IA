"""E3 · P0b: verificación de la evidencia SUSPENSION (Adenda R, R2) en los zips crudos. SIN PRECIOS.
Para una muestra al azar (semilla 20261026) de salidas con SUSPENSION, y para todas las SIN_EVIDENCIA, lee de la fila del día
L + 1 solo open_time, close_time y number_of_trades (columnas 0, 6 y 8 de la kline). Los zips no se modifican (sha256 antes y
después). Uso: python -I p0b_verificar_suspension.py <dir_ejecucion_E3> <P0_resultado.json> <salida.json>"""
import csv
import datetime as dt
import hashlib
import io
import json
import random
import sys
import zipfile
from pathlib import Path

E3, P0, SAL = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
MENS = E3 / "datos_vision" / "data" / "spot" / "monthly" / "klines"
p0 = json.loads(P0.read_text())
con = [s for s in p0["salidas"] if s["en_alcance"] and s["SUSPENSION"]]
sin = [s for s in p0["salidas"] if s["en_alcance"] and not s["con_evidencia"]]
muestra = random.Random(20261026).sample(con, 12) + sin
filas = []
for s in muestra:
    d1 = dt.date.fromisoformat(s["L"]) + dt.timedelta(days=1)
    z = MENS / s["simbolo"] / "1d" / f"{s['simbolo']}-1d-{d1:%Y-%m}.zip"
    out = {"simbolo": s["simbolo"], "L": s["L"], "dia": d1.isoformat(), "zip": z.name, "existe": z.exists()}
    if z.exists():
        h0 = hashlib.sha256(z.read_bytes()).hexdigest()
        with zipfile.ZipFile(z) as zf:
            texto = zf.read(zf.namelist()[0]).decode()
        for fila in csv.reader(io.StringIO(texto)):
            if not fila or not fila[0].strip().isdigit():
                continue
            ot, ct = int(fila[0]), int(fila[6])
            esc = 1000 if ot > 10**14 else 1  # µs desde 2025
            t0 = dt.datetime.fromtimestamp(ot / 1000 / esc, dt.UTC)
            if t0.date() == d1:
                t1 = dt.datetime.fromtimestamp(ct / 1000 / esc, dt.UTC)
                out.update(open_time=t0.isoformat(), close_time=t1.isoformat(), horas=round((ct - ot) / 3.6e6 / esc, 2),
                           operaciones=int(fila[8]))
        out["zip_sin_cambios"] = hashlib.sha256(z.read_bytes()).hexdigest() == h0
    filas.append(out)
SAL.write_text(json.dumps(filas, indent=1, ensure_ascii=False))
for f in filas:
    print(f["simbolo"], f["L"], "→", f.get("dia"), "horas", f.get("horas"), "ops", f.get("operaciones"), "cierre", f.get("close_time", "SIN FILA")[:19], "zip ok" if f.get("zip_sin_cambios") else "")
