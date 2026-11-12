"""Corre el modo sintético del v1 congelado y del v2 sobre la MISMA copia del código de E3 y compara todo el resultado.
Esperado: solo difieren los campos de R4 (y lo que dependa de R4). Sin datos reales.
Uso: python -B -I diferencial_sintetico.py <ejecutar_E3R.py> <ejecutar_E3_v2.py> <dir_copia_E3> <salida_dir>"""
import importlib.util, json, sys
from pathlib import Path
sys.dont_write_bytecode = True
v1p, v2p, e3, sal = (Path(a) for a in sys.argv[1:5])
def cargar(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
V1, V2 = cargar("v1", v1p), cargar("v2", v2p)
V1.E3_DEFECTO = e3                     # el v1 no recibe el directorio: se apunta a la copia, no al árbol congelado
def plano(x, pre=""):
    if isinstance(x, dict):
        out = {}
        for k, v in x.items(): out.update(plano(v, f"{pre}.{k}" if pre else str(k)))
        return out
    if isinstance(x, list) and x and isinstance(x[0], (dict, list)):
        out = {}
        for i, v in enumerate(x): out.update(plano(v, f"{pre}[{i}]"))
        return out
    return {pre: x}
informe = {}
for mom in (0.0, 0.02):
    for nombre, M in (("v1", V1), ("v2", V2)):
        d = sal / nombre; d.mkdir(parents=True, exist_ok=True)
        if nombre == "v1": M.modo_sintetico(d, mom, 50)
        else: M.modo_sintetico(d, mom, 50, e3)
    a = plano(json.loads((sal / "v1" / f"sintetico_momentum_{mom}.json").read_text()))
    b = plano(json.loads((sal / "v2" / f"sintetico_momentum_{mom}.json").read_text()))
    dif = {k: (a.get(k), b.get(k)) for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)}
    informe[str(mom)] = {"campos": len(set(a) | set(b)), "difieren": dif}
(sal / "DIFERENCIAL.json").write_text(json.dumps(informe, indent=1, ensure_ascii=False, default=str))
for m, v in informe.items():
    print(f"momentum {m}: {v['campos']} campos, {len(v['difieren'])} difieren")
    for k, (x, y) in v["difieren"].items(): print(f"   {k}: v1={x} v2={y}")
