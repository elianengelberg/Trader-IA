"""Busca paneles SINTÉTICOS (pruebas_motor.panel_sintetico) en los que la moneda de mayor aporte (R4) cambie según se
mida contra el EW neto (v1) o el bruto (v2, N14). Sin datos reales."""
import importlib.util, sys, warnings
from pathlib import Path
sys.dont_write_bytecode = True
warnings.filterwarnings("ignore")
C = Path(sys.argv[1]); E3 = C / "experimentos/E3_seleccion_posicion_2026-10-19/ejecucion_E3"
spec = importlib.util.spec_from_file_location("v2", C / "reparacion_E3H1H2_2026-10-26/orquestador_v2/ejecutar_E3_v2.py")
V2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(V2)
cod = C / "codigo_copia"
universo, motor, inferencia = V2.importar_congelados(cod.parent / "e3copia")
import pruebas_motor
F = pruebas_motor.formaciones()
hall = []
for semilla in range(1, 61):
    for mom in (0.0, 0.02):
        P = pruebas_motor.panel_sintetico(semilla, momentum=mom)
        cache = {}
        base = motor.simular(P, F, motor.Config(), cache, registrar_pesos=True)
        ew = motor.simular(P, F, motor.Config(objetivo="ew"), cache)
        bew = motor.simular(P, F, motor.Config(objetivo="ew", mult_costo=0.0), cache)
        a_n, a_b = V2.contribuciones(P, base, F, ew), V2.contribuciones(P, base, F, bew)
        mn, mb = max(a_n, key=a_n.get), max(a_b, key=a_b.get)
        if mn != mb:
            hall.append((semilla, mom, P.sym[mn], P.sym[mb]))
print("paneles probados:", 120, "· con moneda R4 distinta:", len(hall), hall[:10])
