"""Auxiliar de reproducir.sh. No importa nada del paquete ni ejecuta su código: lee archivos y compara.

  python -I auxiliar.py json <esperado.json> <obtenido.json>
      Compara dos JSON. Las rutas absolutas (valores o claves) se comparan desde la primera carpeta conocida del paquete
      (experimentos/, reparacion_…, revision_…, cierre_…), porque dependen de dónde se extrajo la evidencia.

  python -I auxiliar.py higiene <evidencia> <temporales>
      Extrae con `ast` (sin ejecutar) las frases de autorización del v1, el v2 y el v3, y las frases de decisión del v3.
      - En <temporales>: ninguna puede aparecer, salvo en las copias de código de los mutantes (mutante_*.py).
      - En <evidencia>: la FRASE y las frases de decisión del v3 solo pueden aparecer en el código del v3, en su plantilla
        y en el diff. Las frases del v1 y del v2 se informan, pero no se consideran falla (son documentos congelados)."""
import ast
import json
import sys
from pathlib import Path

ANCLAS = ("experimentos/", "reparacion_E3H1H2_2026-10-26", "revision_independiente_E3H1H2_2026-10-26",
          "cierre_bloqueantes_E3H1H2_2026-10-27")


def normalizar(x):
    if isinstance(x, str) and x.startswith("/"):
        pos = [x.find(a) for a in ANCLAS if a in x]
        return "<RAIZ>/" + x[min(pos):] if pos else x
    if isinstance(x, dict):
        return {normalizar(k): normalizar(v) for k, v in x.items()}
    if isinstance(x, list):
        return [normalizar(v) for v in x]
    return x


def diferencias(a, b, ruta="$", out=None):
    out = [] if out is None else out
    if type(a) is not type(b):
        out.append(f"{ruta}: tipo {type(a).__name__} ≠ {type(b).__name__}")
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append(f"{ruta}.{k}: falta en {'esperado' if k not in a else 'obtenido'}")
            else:
                diferencias(a[k], b[k], f"{ruta}.{k}", out)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{ruta}: longitud {len(a)} ≠ {len(b)}")
        for i, (u, v) in enumerate(zip(a, b)):
            diferencias(u, v, f"{ruta}[{i}]", out)
    elif a != b:
        out.append(f"{ruta}: {str(a)[:80]} ≠ {str(b)[:80]}")
    return out


def frases(py: Path):
    arbol = ast.parse(py.read_text(encoding="utf-8"))
    res = {}
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1 and isinstance(nodo.targets[0], ast.Name):
            nombre = nodo.targets[0].id
            if nombre == "FRASE" and isinstance(nodo.value, ast.Constant):
                res["FRASE"] = nodo.value.value
            elif nombre == "FRASES_DECISION" and isinstance(nodo.value, ast.Dict):
                for k, v in zip(nodo.value.keys, nodo.value.values):
                    res[f"DECISION_{k.value}"] = v.value
    return res


def higiene(ev: Path, tmp: Path) -> int:
    cb = ev / "cierre_bloqueantes_E3H1H2_2026-10-27"
    fuentes = {"v1": ev / "experimentos/E3R_desbloqueo_2026-10-26/ejecutar_E3R.py",
               "v2": ev / "reparacion_E3H1H2_2026-10-26/orquestador_v2/ejecutar_E3_v2.py",
               "v3": cb / "orquestador_v3/ejecutar_E3_v3.py"}
    buscadas = {f"{v}_{k}": t.encode("utf-8") for v, p in fuentes.items() for k, t in frases(p).items()}
    assert {"v1_FRASE", "v2_FRASE", "v3_FRASE"} <= set(buscadas) and sum(k.startswith("v3_DECISION") for k in buscadas) == 2, sorted(buscadas)
    permitidos_v3 = {cb / "orquestador_v3" / n for n in ("ejecutar_E3_v3.py", "plantilla_cabecera.py", "DIFF_v2_v3.diff")}
    fallas = 0
    paquete = ev.parent if (ev.parent / "00_LEEME_REVISOR.md").is_file() else ev  # también los documentos del paquete
    for raiz, etiqueta in ((tmp, "temporales"), (paquete, "paquete")):
        for p in sorted(x for x in raiz.rglob("*") if x.is_file() and not x.is_symlink()):
            datos = p.read_bytes()
            for nombre, frase in buscadas.items():
                if frase not in datos:
                    continue
                if etiqueta == "temporales":
                    ok = p.name.startswith("mutante_") and p.suffix == ".py"
                elif nombre.startswith("v3_"):
                    ok = p in permitidos_v3
                else:
                    ok = None  # informativo
                estado = "FALLA" if ok is False else ("permitido" if ok else "informativo")
                fallas += ok is False
                print(f"  [{estado}] {nombre} en {p.relative_to(raiz)} ({etiqueta})")
    print(f"higiene: {len(buscadas)} frases buscadas · fallas: {fallas}")
    return 1 if fallas else 0


if __name__ == "__main__":
    if sys.argv[1] == "json":
        esperado, obtenido = (normalizar(json.loads(Path(a).read_text(encoding="utf-8"))) for a in sys.argv[2:4])
        d = diferencias(esperado, obtenido)
        for linea in d[:20]:
            print("  ", linea)
        print("json:", "IGUALES" if not d else f"{len(d)} DIFERENCIAS")
        sys.exit(1 if d else 0)
    elif sys.argv[1] == "higiene":
        sys.exit(higiene(Path(sys.argv[2]), Path(sys.argv[3])))
    raise SystemExit(__doc__)
