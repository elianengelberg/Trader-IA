"""Segunda lectura (protocolo SL-v1, §7.3) · clasifica con la función congelada `clasificar` (copia de conciliacion.py
6f764845…, verificada por hash) las remociones de pares USDT confirmadas por lectura que no son eventos de la conciliación.
Regla fija: categoría T o D → falla; C → «C_no_explicada» (falla) salvo reapertura o postergación/cancelación documentada
en la lectura, que la deja «C_explicada»; A o B → no se agregan (solo podrían sumar evidencia ANUNCIO a (iv′): omitirlas es
conservador) y se informan. Solo lee `estado`, `NT` y la auditoría por símbolo, como el código congelado; ningún precio.
Entrada: lista JSON de {"par", "E", "cita", "fuente", "explicada": bool}.
Uso: python -B -I clasificar_omitidos_L2.py <dir_copia_congelada> <dir_ejecucion_E3> <omitidos_confirmados.json> <salida_dir>"""
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

COPIA, E3, ENT, OUT = (Path(a) for a in sys.argv[1:5])
assert hashlib.sha256((COPIA / "conciliacion.py").read_bytes()).hexdigest() == \
    "6f764845598b4ecf6c3cffbc6c7b584f21e493403c7bcd14339f5f582c9273ad", "copia alterada"
sys.path.insert(0, str(COPIA))
import conciliacion as C  # noqa: E402

usdt = set(json.loads((E3 / "datos_vision/listados/simbolos_usdt.json").read_text()))
aud = {a["simbolo"]: a for a in json.loads((E3 / "resultados/calidad/auditoria_por_simbolo.json").read_text())}
meses = {s: set(a.get("meses_con_archivo", [])) for s, a in aud.items()}
act, _ = C.cargar_actividad(E3 / "resultados/calidad")
fallas, informados = [], []
for o in json.loads(ENT.read_text()):
    cat, L = C.clasificar(o["par"], dt.date.fromisoformat(o["E"]), act, meses, usdt, False)
    fila = {"par": o["par"], "E": o["E"], "categoria_clasificar": cat, "L": L, "en_bucket": o["par"] in usdt,
            "cita": o["cita"], "fuente": o["fuente"]}
    if cat in ("T", "D"):
        fallas.append({**fila, "categoria": cat})
    elif cat == "C":
        fila["categoria"] = "C_explicada" if o.get("explicada") else "C_no_explicada"
        (informados if o.get("explicada") else fallas).append(fila)
    else:
        informados.append({**fila, "categoria": cat})
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "fallas_extra_L2.json").write_text(json.dumps(fallas, ensure_ascii=False, indent=1))
(OUT / "omitidos_no_falla_L2.json").write_text(json.dumps(informados, ensure_ascii=False, indent=1))
print(json.dumps({"fallas_extra": [(f["par"], f["E"], f["categoria"]) for f in fallas],
                  "no_falla": [(f["par"], f["E"], f["categoria"]) for f in informados]}, ensure_ascii=False))
