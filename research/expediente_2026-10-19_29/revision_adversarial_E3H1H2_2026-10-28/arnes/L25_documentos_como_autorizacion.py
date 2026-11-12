"""Revisión adversarial · L-25: ¿algún documento congelado ya satisface, tal cual, el control de autorización del v1, el
v2 o el v3? Reimplementación ESTÁTICA de las condiciones `requeridos` de cada orquestador (copiadas de su código). No
importa ni ejecuta ningún orquestador: solo lee texto y calcula sha256. No escribe nada salvo el informe en <salida>.
Uso: python -B -I L25_documentos_como_autorizacion.py <evidencia> <paquete_docs> <salida.json>"""
import ast
import hashlib
import json
import sys
from pathlib import Path

EV, DOCS, SAL = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
E3R = EV / "experimentos/E3R_desbloqueo_2026-10-26"
V1 = E3R / "ejecutar_E3R.py"
V2 = EV / "reparacion_E3H1H2_2026-10-26/orquestador_v2/ejecutar_E3_v2.py"
V3 = EV / "cierre_bloqueantes_E3H1H2_2026-10-27/orquestador_v3/ejecutar_E3_v3.py"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def constantes(py):
    t = ast.parse(Path(py).read_text())
    out = {}
    for n in t.body:
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name):
            if n.targets[0].id == "FRASE":
                out["FRASE"] = n.value.value
            if n.targets[0].id == "FRASES_DECISION":
                out["DEC"] = [v.value for v in n.value.values]
    return out


c1, c2, c3 = constantes(V1), constantes(V2), constantes(V3)
p0s = sorted(E3R.glob("P0_resultado*.json"))
sha_p0 = {p.name: sha(p) for p in p0s}
adenda_p0 = {p.name: json.loads(p.read_text()).get("adenda", "") for p in p0s}
s_v1, s_R, s_R2 = sha(V1), sha(E3R / "ADENDA_R_auditoria_de_supervivencia_interna.md"), sha(E3R / "ADENDA_R2_cortes_con_salto_de_precio.md")
corr = E3R / "CORRECCION_R1prima_alcance_por_clase.md"
s_corr = sha(corr) if corr.exists() else None
s_v2, s_m2 = sha(V2), sha(V2.parent / "ENTRADAS_CONGELADAS.json")
s_v3, s_m3 = sha(V3), sha(V3.parent / "ENTRADAS_CONGELADAS_V3.json")


def v1_acepta(t, p0):
    req = {"FRASE": c1["FRASE"] in t, "orquestador": s_v1 in t, "P0": sha_p0[p0] in t, "adenda_R": s_R in t, "adenda_R2": s_R2 in t}
    if "R1prima" in adenda_p0[p0]:
        req["correccion_R1prima"] = s_corr is not None and s_corr in t
    req["una_sola_opcion"] = not any(sha_p0[q] in t for q in sha_p0 if q != p0)
    return req


def v2_acepta(t):
    return {"FRASE": c2["FRASE"] in t, "orquestador_v2": s_v2 in t, "entradas_congeladas": s_m2 in t}


def v3_acepta(t):
    return {"FRASE": c3["FRASE"] in t, "orquestador_v3": s_v3 in t, "entradas_congeladas": s_m3 in t,
            **{f"decision_{i}": d in t for i, d in enumerate(c3["DEC"])}}


filas, completos = [], []
for raiz in (EV, DOCS):
    for p in sorted(x for x in raiz.rglob("*") if x.is_file() and not x.is_symlink()):
        if raiz == DOCS and EV in p.parents:
            continue
        try:
            t = p.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            continue
        for nombre, req in [*((f"v1 con {q}", v1_acepta(t, q)) for q in sha_p0), ("v2", v2_acepta(t)), ("v3", v3_acepta(t))]:
            n = sum(req.values()) - (1 if "una_sola_opcion" in req and req["una_sola_opcion"] else 0)
            total = len(req) - (1 if "una_sola_opcion" in req else 0)
            if n >= total - 1 and n > 0:  # documentos a lo sumo a un elemento de ser aceptados
                fila = {"archivo": str(p.relative_to(raiz.parent if raiz == EV else raiz)), "orquestador": nombre,
                        "cumple": n, "de": total, "faltan_o_sobran": [k for k, v in req.items() if not v]}
                filas.append(fila)
                if all(req.values()):
                    completos.append(fila)
res = {"elementos": {"sha_v1": s_v1, "sha_v2": s_v2, "sha_v3": s_v3, "sha_P0": sha_p0, "adenda_de_cada_P0": adenda_p0},
       "documentos_aceptados_tal_cual": completos, "documentos_a_un_elemento": filas}
SAL.write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps(res, ensure_ascii=False, indent=1))
