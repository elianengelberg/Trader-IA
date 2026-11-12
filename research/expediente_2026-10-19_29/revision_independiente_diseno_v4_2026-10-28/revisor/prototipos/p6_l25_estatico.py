"""P6 (revisor, fase 2) · Comprobación ESTÁTICA propia de la afirmación L-25 del autor: ¿`INFORME_REPARACION_E3H1H2.md`
contiene, tal cual, los tres elementos que el v2 exige por subcadena (FRASE, sha256 del v2, sha256 de su manifiesto)?
No importa ni ejecuta ningún orquestador. Lee la FRASE del v2 con `ast` y NO la imprime ni la escribe: solo booleanos
y conteos. También comprueba el v3 (FRASE + sha + manifiesto + 2 decisiones) contra el mismo documento.
Uso: /usr/bin/python3 -I -B p6_l25_estatico.py <scratchpad>
"""
import ast
import hashlib
import json
import sys
from pathlib import Path

S = Path(sys.argv[1])
V2 = S / "reparacion_E3H1H2_2026-10-26/orquestador_v2/ejecutar_E3_v2.py"
V3 = S / "cierre_bloqueantes_E3H1H2_2026-10-27/orquestador_v3/ejecutar_E3_v3.py"
DOC = S / "reparacion_E3H1H2_2026-10-26/INFORME_REPARACION_E3H1H2.md"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def constantes(py):
    out = {}
    for n in ast.parse(Path(py).read_text()).body:
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name):
            if n.targets[0].id == "FRASE":
                out["FRASE"] = n.value.value
            if n.targets[0].id == "FRASES_DECISION":
                out["DEC"] = [v.value for v in n.value.values]
    return out


t = DOC.read_bytes().decode("utf-8", errors="replace")
c2, c3 = constantes(V2), constantes(V3)
s_v2, s_m2 = sha(V2), sha(V2.parent / "ENTRADAS_CONGELADAS.json")
s_v3, s_m3 = sha(V3), sha(V3.parent / "ENTRADAS_CONGELADAS_V3.json")
res = {
    "documento": str(DOC.relative_to(S)), "sha256_documento": sha(DOC), "bytes": len(t),
    "v2": {"FRASE_presente": c2["FRASE"] in t, "sha_v2_presente": s_v2 in t, "sha_manifiesto_v2_presente": s_m2 in t},
    "v3": {"FRASE_presente": c3["FRASE"] in t, "sha_v3_presente": s_v3 in t, "sha_manifiesto_v3_presente": s_m3 in t,
           "decisiones_presentes": [d in t for d in c3["DEC"]]},
    "sha_v2_esperado_prefijo": s_v2[:8], "sha_v3_esperado_prefijo": s_v3[:8],
}
res["v2"]["ACEPTARIA_v2_por_subcadenas"] = all(res["v2"].values())
res["v3"]["ACEPTARIA_v3_por_subcadenas"] = all([res["v3"]["FRASE_presente"], res["v3"]["sha_v3_presente"],
                                                 res["v3"]["sha_manifiesto_v3_presente"], *res["v3"]["decisiones_presentes"]])
print(json.dumps(res, indent=1, ensure_ascii=False))
