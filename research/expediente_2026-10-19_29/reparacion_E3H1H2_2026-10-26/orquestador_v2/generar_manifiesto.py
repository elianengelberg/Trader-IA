"""Fija ENTRADAS_CONGELADAS.json: sha256 de cada insumo del orquestador v2 (sin leer precios; solo bytes para el hash).
Uso: python -I generar_manifiesto.py <dir_ejecucion_E3> <dir_reparacion> <ventana_A_pasada2.json> <salida.json>"""
import hashlib, json, sys
from pathlib import Path
E3, REP, VEN, SAL = (Path(a) for a in sys.argv[1:5])
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def conjunto(d):
    rel = sorted(("./" + p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file()), key=lambda r: r.encode())
    return hashlib.sha256("".join(f"{sha(d / r[2:])}  {r}\n" for r in rel).encode()).hexdigest()
E = [("series_calidad_757", "E3", "resultados/calidad/series", "conjunto"),
     ("estructural", "E3", "resultados/estructural/estructural.json", "archivo"),
     ("listas_fijas_por_lunes", "E3", "resultados/estructural/listas_fijas_por_lunes.json", "archivo"),
     ("universo.py", "E3", "codigo/universo.py", "archivo"), ("motor.py", "E3", "codigo/motor.py", "archivo"),
     ("inferencia.py", "E3", "codigo/inferencia.py", "archivo"), ("pruebas_motor.py", "E3", "codigo/pruebas_motor.py", "archivo"),
     ("conciliacion.py", "E3", "codigo/conciliacion.py", "archivo"),
     ("resoluciones_manuales", "reparacion", "segunda_pasada/resoluciones_manuales.json", "archivo"),
     ("pasada2_conciliacion", "reparacion", "segunda_pasada/salida_pasada2/conciliacion.json", "archivo"),
     ("pasada2_eventos", "reparacion", "segunda_pasada/salida_pasada2/eventos.json", "archivo"),
     ("pasada2_salidas", "reparacion", "segunda_pasada/salida_pasada2/salidas.json", "archivo"),
     ("eventos_omitidos", "reparacion", "segunda_pasada/eventos_omitidos.json", "archivo"),
     ("mapeos_adenda1", "reparacion", "renombres/mapeos_adenda1.json", "archivo"),
     ("ventana_A", "ventana", None, "archivo")]
out = {"_nota": "Insumos del orquestador v2 con su sha256. El modo real los verifica todos antes de leer cualquier precio.",
       "inicio_H_esperado": json.loads(VEN.read_text())["inicio_H"], "mapeos": "renombres/mapeos_adenda1.json", "entradas": []}
for nombre, base, ruta, tipo in E:
    p = VEN if base == "ventana" else (E3 if base == "E3" else REP) / ruta
    out["entradas"].append({"nombre": nombre, "base": base, "ruta": ruta, "tipo": tipo, "sha256": conjunto(p) if tipo == "conjunto" else sha(p)})
SAL.write_text(json.dumps(out, ensure_ascii=False, indent=1))
for x in out["entradas"]: print(x["sha256"][:16], x["nombre"])
print("inicio_H_esperado", out["inicio_H_esperado"])
