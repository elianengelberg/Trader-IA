"""Revisión adversarial · T-3: ¿cada cita de la tabla de renombres está en el CUERPO del anuncio (A3.1.1), según la
función congelada `cuerpo_de` de cc_clasificar.py (effe8a2e…)? El script del autor solo comprobaba la página completa.
Solo lee páginas archivadas (texto) y la tabla. No lee series.
Uso: python -B -I T3_citas_en_cuerpo.py <cc_clasificar.py> <dir_paginas> <TABLA_RENOMBRES_COMPLETA.json> <salida.json>"""
import importlib.util
import json
import re
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("cc_clasificar_congelado", sys.argv[1])
CC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CC)
PAG, TABLA, SAL = Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


tabla = json.loads(TABLA.read_text())["tabla"]
filas, resumen = [], {"citas": 0, "en_pagina": 0, "en_cuerpo": 0, "titulo_no_hallado": 0}
for t in tabla:
    for ev in t.get("evidencia") or []:
        p = json.loads((PAG / ev["archivo"]).read_text())
        texto = p.get("texto", "")
        cuerpo, pub, hallado = CC.cuerpo_de(p.get("titulo", ""), texto)
        c = norm(ev["cita"])
        en_pag, en_cuerpo = c in norm(texto), (hallado and c in norm(cuerpo))
        resumen["citas"] += 1
        resumen["en_pagina"] += en_pag
        resumen["en_cuerpo"] += bool(en_cuerpo)
        resumen["titulo_no_hallado"] += not hallado
        if not en_cuerpo:
            filas.append({"id": t["id"], "viejo": t["viejo_usdt"], "nuevo": t["nuevo_usdt"], "tratamiento": t["tratamiento"],
                          "archivo": ev["archivo"], "titulo": p.get("titulo", "")[:120], "titulo_hallado": hallado,
                          "cita_en_pagina": en_pag, "cita": c[:200]})
res = {"resumen": resumen, "citas_fuera_del_cuerpo": filas}
SAL.write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps(resumen, ensure_ascii=False))
for f in filas:
    print(json.dumps(f, ensure_ascii=False)[:400])
