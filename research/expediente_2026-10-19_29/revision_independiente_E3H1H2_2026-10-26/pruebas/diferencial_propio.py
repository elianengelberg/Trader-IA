"""Diferencial propio v1 (congelado) frente a v2 (copia) con `ejecutar` completo en paneles SINTÉTICOS.
Uso: python -B -I diferencial_propio.py <dir_revision>"""
import importlib.util, json, sys, warnings
from pathlib import Path
sys.dont_write_bytecode = True; warnings.filterwarnings("ignore")
RV = Path(sys.argv[1]); S = RV.parent
def cargar(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
V1 = cargar("v1", S / "experimentos/E3R_desbloqueo_2026-10-26/ejecutar_E3R.py")
V2 = cargar("v2", RV / "copia_aislada/reparacion_E3H1H2_2026-10-26/orquestador_v2/ejecutar_E3_v2.py")
universo, motor, inferencia = V2.importar_congelados(RV / "copia_aislada/e3copia")
import pruebas_motor
def plano(x, pre=""):
    if isinstance(x, dict):
        o = {}
        for k, v in x.items(): o.update(plano(v, f"{pre}.{k}" if pre else str(k)))
        return o
    return {pre: json.dumps(x, default=float)}
F = pruebas_motor.formaciones()
informe = {}
for semilla, mom in ((20261026, 0.02), (20261026, 0.0), (37, 0.0)):
    P = pruebas_motor.panel_sintetico(semilla, momentum=mom)
    a = plano(V1.ejecutar(P, F, universo, motor, inferencia, replicas_R5=20, diag_B=199))
    b = plano(V2.ejecutar(P, F, universo, motor, inferencia, replicas_R5=20, diag_B=199))
    dif = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    informe[f"{semilla}/{mom}"] = {"campos": len(set(a) | set(b)), "difieren": dif}
    print(f"semilla {semilla} momentum {mom}: {len(set(a)|set(b))} campos, {len(dif)} difieren: {dif}")
(RV / "pruebas/diferencial_propio.json").write_text(json.dumps(informe, indent=1, ensure_ascii=False))
