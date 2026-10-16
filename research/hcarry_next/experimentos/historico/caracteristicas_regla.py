"""Características operativas de la regla de decisión PRERREGISTRADA (SINTÉTICO): con qué frecuencia concluiría
«ventaja respaldada», «no respaldada» o «insuficiente» si los datos fueran históricos, en mundos con persistencia del
funding (normales) y sin ella (nulos: funding barajado en el tiempo).

Cada mundo recorre el pipeline real completo: fabricación en formato oficial → manifiesto «sintetico» → calidad →
evaluador histórico. El evaluador concluye EVIDENCIA INSUFICIENTE por ser sintético; aquí se calcula además la
conclusión EN SOMBRA (``concluir("historico", …)``) solo para medir la regla. No es evidencia económica.

Uso: python -B experimentos/historico/caracteristicas_regla.py VARIANTE SEMILLA_INICIAL N > log"""

from __future__ import annotations

import json
import random
import shutil
import sys
from dataclasses import replace
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parents[1] / "src"))

from hcarry.data.fabricar import fabricar_sintetico
from hcarry.data.schema import Panel
from hcarry.data.sintetico import ParamsSintetico, generar
from hcarry.lab import historico as H

TMP = Path("/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/caracteristicas")


def main() -> None:
    variante, ini, n = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    for s in range(ini, ini + n):
        for nulo in (False, True):
            panel = generar(ParamsSintetico(semilla=s, variante=variante))
            if nulo:
                tasas = [e.tasa for e in panel.funding]
                random.Random(s).shuffle(tasas)
                panel = Panel(panel.barras, [replace(e, tasa=f) for e, f in zip(panel.funding, tasas, strict=True)],
                              panel.origen + ":nulo", panel.notas)
            mundo = f"{variante}_{s}" + ("_nulo" if nulo else "")
            d = TMP / mundo
            shutil.rmtree(d, ignore_errors=True)
            fabricar_sintetico(panel, d)
            out = H.evaluar(d, AQUI / "resultados" / "caracteristicas" / mundo)
            sombra = H.concluir("historico", out)
            t = out["test"]
            print(json.dumps({"mundo": mundo, "variante": variante, "nulo": nulo, "categoria": out["categoria"],
                              "conclusion_oficial": out["conclusion"]["P1_umbral_vs_rev5"],
                              "sombra_P1": sombra["P1_umbral_vs_rev5"], "sombra_P2": sombra["P2_carry_rev5"],
                              "detalles": sombra["detalles"], "persistencia": out["diagnostico_previo_desarrollo"].get("correlacion"),
                              "cagr_test": {"rev5": t["rev5"]["cagr_neto"], "umbral": t["umbral"]["cagr_neto"]},
                              "dd_test": {"rev5": t["rev5"]["caida_maxima"], "umbral": t["umbral"]["caida_maxima"]}},
                             ensure_ascii=False), flush=True)
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    main()
