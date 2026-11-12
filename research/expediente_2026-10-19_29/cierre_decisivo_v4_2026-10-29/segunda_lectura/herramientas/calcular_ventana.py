"""Segunda lectura (protocolo SL-v1, §8) · corre la conciliación congelada y el cálculo de ventana congelado, y registra
parámetros, entradas, salidas, hashes y la salida estándar. SIN RETORNOS: ninguno de los dos programas lee O, H, L, C ni QV
(la conciliación lee `estado` y `NT`; la ventana, solo `estado`).
  - conciliacion.py: 6f764845… (copia verificada por hash antes de correr)
  - p0_pasada2.py:   d05c8dd5… (copia verificada por hash antes de correr)
Uso: python3 -I -B calcular_ventana.py <python_venv> <dir_copias_congeladas> <dir_ejecucion_E3> <resoluciones.json>
       <resoluciones_C.json> <fallas_extra.json|-> <dir_salida>"""
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

PY, COP, E3, RES, RESC, EXTRA, OUT = sys.argv[1], *(Path(a) for a in sys.argv[2:8])
CONGELADOS = {"conciliacion.py": "6f764845598b4ecf6c3cffbc6c7b584f21e493403c7bcd14339f5f582c9273ad",
              "p0_pasada2.py": "d05c8dd53787fe0608cac66e837bd59c12bc7e9c9372e040a0d66bd58b2874a8"}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


for nombre, h in CONGELADOS.items():
    assert sha(COP / nombre) == h, f"copia alterada: {nombre}"
OUT.mkdir(parents=True, exist_ok=False)
conc_dir = OUT / "conciliacion"
pasos = []
cmd1 = [PY, "-I", "-B", str(COP / "conciliacion.py"), str(E3 / "resultados/calidad"), str(E3 / "datos_anuncios/commoncrawl"),
        str(E3 / "datos_vision/listados"), str(E3 / "resultados/estructural/estructural.json"), str(conc_dir), str(RES)]
cmd2 = [PY, "-I", "-B", str(COP / "p0_pasada2.py"), str(E3), str(conc_dir), str(RESC), str(EXTRA), str(OUT / "ventana.json")]
entradas = {str(p): sha(p) for p in (RES, RESC, *([EXTRA] if str(EXTRA) != "-" else []))}
for cmd in (cmd1, cmd2):
    t0 = dt.datetime.now(dt.timezone.utc).isoformat()
    r = subprocess.run(cmd, capture_output=True, text=True)
    pasos.append({"comando": cmd, "inicio_utc": t0, "fin_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "returncode": r.returncode,
                  "stdout": r.stdout[-6000:], "stderr": r.stderr[-3000:]})
    if r.returncode != 0:
        break
salidas = {str(p.relative_to(OUT)): sha(p) for p in sorted(OUT.rglob("*")) if p.is_file()}
registro = {"protocolo": "SL-v1 §8", "interprete": PY, "copias_congeladas": CONGELADOS, "entradas": entradas, "pasos": pasos,
            "salidas": salidas, "entradas_sin_cambios_despues": {k: sha(Path(k)) == v for k, v in entradas.items()}}
(OUT / "registro_calculo.json").write_text(json.dumps(registro, ensure_ascii=False, indent=1))
if (OUT / "ventana.json").exists():
    v = json.loads((OUT / "ventana.json").read_text())
    print(json.dumps({k: v.get(k) for k in ("componentes", "inicio_H", "semanas_H", "evaluables_H", "margen_semanas",
                                             "ultimo_inicio_con_156_evaluables", "veredicto", "insumos_sin_cambios")}, ensure_ascii=False))
    print(json.dumps([(f["par"], f["E"], f["categoria"], f["en_alcance"]) for f in v["fallas_2_3"]]))
else:
    print("SIN VENTANA: ver registro_calculo.json", [p["returncode"] for p in pasos])
