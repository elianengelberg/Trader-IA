"""Genera `ejecutar_E3_v3.py` a partir del v2 congelado (01fc9344…), sin modificarlo:
  cabecera nueva (plantilla_cabecera.py) + bloque de cálculo del v2 (validez previa … modo_sintetico) con UN solo
  reemplazo (`strict=False` → `strict=True` en contribuciones) + cola nueva (plantilla_cola.py).
Rellena los sha256 fijados en el código: los recalcula a partir de los bytes (sin interpretar ningún precio) y los compara
con ENTRADAS_CONGELADAS.json de la reparación; el de la tabla completa sale de tabla/mapeos_adenda1_completa.json.
Escribe además ENTRADAS_CONGELADAS_V3.json y DIFF_v2_v3.diff.
Uso: python -I generar_v3.py <dir_ejecucion_E3> <dir_reparacion> <ventana_A_pasada2.json>"""
import difflib
import hashlib
import json
import os
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
E3, REP, VENTANA = (Path(a) for a in sys.argv[1:4])
V2 = REP / "orquestador_v2" / "ejecutar_E3_v2.py"
assert hashlib.sha256(V2.read_bytes()).hexdigest() == "01fc934459b791fd5fbd451aa1c6931fc9e6764b9361e5caea46314cc5ee6f68"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def conjunto(d):
    arch = {}
    for raiz, _, archivos in os.walk(d, followlinks=False):
        for n in archivos:
            p = Path(raiz, n)
            arch["./" + p.relative_to(d).as_posix()] = p.read_bytes()
    rel = sorted(arch, key=lambda r: r.encode())
    return sha("".join(f"{sha(arch[r])}  {r}\n" for r in rel).encode())


previo = {x["nombre"]: x for x in json.loads((REP / "orquestador_v2" / "ENTRADAS_CONGELADAS.json").read_text())["entradas"]}
hashes = {}
for nombre, x in previo.items():
    if nombre == "mapeos_adenda1":
        continue
    p = VENTANA if x["base"] == "ventana" else (E3 if x["base"] == "E3" else REP) / x["ruta"]
    h = conjunto(p) if x["tipo"] == "conjunto" else sha(p.read_bytes())
    assert h == x["sha256"], (nombre, h, x["sha256"])
    hashes[nombre] = h
hashes["mapeos_adenda1_completa"] = sha((AQUI.parent / "tabla" / "mapeos_adenda1_completa.json").read_bytes())

cab = (AQUI / "plantilla_cabecera.py").read_text()
for k, v in hashes.items():
    cab = cab.replace(f"@@{k}@@", v)
assert "@@" not in cab, "quedó un sha256 sin rellenar"
lineas = V2.read_text().splitlines(keepends=True)
assert lineas[158].startswith("# ------------------------------------------------------------------ validez previa")
assert lineas[498].rstrip().endswith('default=float, ensure_ascii=False))') and lineas[501].startswith("def resultado_invalido")
medio = "".join(lineas[158:499])
viejo = 'r_ew = dict(zip(formaciones[:-1], sim_ew["r"], strict=False))'
assert medio.count(viejo) == 1
medio = medio.replace(viejo, 'r_ew = dict(zip(formaciones[:-1], sim_ew["r"], strict=True))')
v3 = cab + medio + (AQUI / "plantilla_cola.py").read_text()
destino = AQUI / "ejecutar_E3_v3.py"
destino.write_text(v3)

ns = {"__file__": str(destino), "__name__": "generar_v3_importa"}
exec(compile(v3, str(destino), "exec"), ns)
manifiesto = {"_nota": "Insumos del orquestador v3 con su sha256. Debe coincidir EXACTAMENTE con EXIGIDAS del v3.",
              "inicio_H_esperado": ns["INICIO_H_A"],
              "entradas": [{"nombre": n, "base": b, "ruta": r, "tipo": t, "sha256": h} for n, (b, r, t, h) in ns["EXIGIDAS"].items()]}
(AQUI / "ENTRADAS_CONGELADAS_V3.json").write_text(json.dumps(manifiesto, ensure_ascii=False, indent=1) + "\n")
diff = difflib.unified_diff(V2.read_text().splitlines(keepends=True), v3.splitlines(keepends=True),
                            fromfile="reparacion_E3H1H2_2026-10-26/orquestador_v2/ejecutar_E3_v2.py",
                            tofile="cierre_bloqueantes_E3H1H2_2026-10-27/orquestador_v3/ejecutar_E3_v3.py")
(AQUI / "DIFF_v2_v3.diff").write_text("".join(diff))
print("v3:", sha(v3.encode()), "· manifiesto:", sha((AQUI / "ENTRADAS_CONGELADAS_V3.json").read_bytes()))
print("hashes fijados:", json.dumps({k: v[:12] for k, v in hashes.items()}, ensure_ascii=False))
