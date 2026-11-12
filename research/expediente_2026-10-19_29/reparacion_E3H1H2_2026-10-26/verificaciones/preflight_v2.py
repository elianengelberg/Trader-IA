"""Preflight del orquestador v2 contra los insumos REALES, sin leer precios: np.load queda bloqueado.
1) verificar_entradas con el manifiesto congelado (solo hash de bytes); 2) modo real sin autorización → debe detenerse
sin crear la salida. No crea ningún archivo de autorización. Uso: python -B -I preflight_v2.py <v2.py> <dir_E3> <ventana> <salida_inexistente>"""
import importlib.util, json, sys
from pathlib import Path
import numpy as np
sys.dont_write_bytecode = True
v2p, e3, ven, sal = (Path(a) for a in sys.argv[1:5])
def bloqueado(*a, **k): raise AssertionError("se intentó leer un precio")
np.load = bloqueado
s = importlib.util.spec_from_file_location("v2", v2p); V2 = importlib.util.module_from_spec(s); s.loader.exec_module(V2)
V2.np.load = bloqueado
r = V2.verificar_entradas(e3, ven)
print("1) insumos verificados:", len(r["insumos"]), "· manifiesto", r["manifiesto"][:16], "· inicio esperado", r["inicio_H_esperado"])
aut = sal.parent / "NO_EXISTE_autorizacion.txt"
assert not aut.exists()
try:
    V2.modo_real(e3, ven, aut, sal)
except SystemExit as x:
    print("2) sin autorización:", str(x)[:160])
assert not sal.exists(), "la salida no debía crearse"
print("   salida creada:", sal.exists())
