"""Manifiesto determinista de la evidencia de T-MULTI (y de la cadena histórica de T) para verificarla sin depender de
nadie: rutas, SHA-256, tamaños, commits, versión de Python y todo el código que el experimento importa realmente.
No recalcula el experimento ni descarga nada.

Uso (PYTHONPATH=src:../hcarry_next/src):  evidencia_t_multi.py generar | verificar"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "EVIDENCIA_T_MULTI.json"
ARTEFACTOS = ["PRERREGISTRO_T_MULTI.md", "experimentos/t_multi.py", "experimentos/t_multi.json", "INFORME_T_MULTI.md",
              "datos_multi/MANIFIESTO.json", "datos_multi/VALIDACION.json",
              "datos/BTCUSDT/MANIFIESTO.json", "datos/ETHUSDT/MANIFIESTO.json"]  # los dos últimos: autoprueba
CADENA_T = ["PRERREGISTRO_FUERA_DE_MUESTRA_T.md", "experimentos/fuera_de_muestra_T.py",
            "experimentos/fuera_de_muestra_T.json", "INFORME_FUERA_DE_MUESTRA_T.md",
            "REVISION_CRITICA_FUERA_DE_MUESTRA_T.md", "experimentos/revision_fuera_de_muestra_T.py",
            "experimentos/revision_fuera_de_muestra_T.json"]


def _sha(p: Path) -> dict:
    b = p.read_bytes()
    return {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)}


def _git(*a: str) -> str:
    return subprocess.run(["git", *a], check=False, cwd=RAIZ, capture_output=True, text=True).stdout.strip()


def dependencias() -> dict:
    """Archivos de research/ que importa ``t_multi`` (medido en un proceso aparte, no supuesto)."""
    cod = ("import sys, json; sys.path.insert(0, 'experimentos'); import t_multi; "
           "print(json.dumps(sorted({m.__file__ for m in list(sys.modules.values()) if getattr(m, '__file__', None)})))")
    r = subprocess.run([sys.executable, "-B", "-c", cod], check=True, cwd=RAIZ, capture_output=True, text=True)
    base = RAIZ.parent
    rutas = [Path(f).resolve() for f in json.loads(r.stdout)]
    return {p.relative_to(base).as_posix(): _sha(p) for p in sorted(rutas) if base in p.parents and ".venv" not in p.parts}


def generar() -> dict:
    sys.path.insert(0, str(RAIZ / "src"))
    from tendencia import papel as P
    res = json.loads((RAIZ / "experimentos/t_multi.json").read_text(encoding="utf-8"))
    man = json.loads((RAIZ / "datos_multi/MANIFIESTO.json").read_text(encoding="utf-8"))
    pr = res["principal"]
    return {
        "proposito": "evidencia de T-MULTI: qué se ejecutó, con qué código, datos y criterios; histórico, no prospectivo",
        "commits": {"regla_T_congelada": _git("rev-parse", "89278f7"), "congelado_T_MULTI": _git("rev-parse", "f518ac1"),
                    "remoto_conocido": _git("rev-parse", "c6339e3")},
        "regla_T": {"codigo_sha256": P.huella_codigo(), "reglas_sha256": P.hash_prerregistro()},
        "python": ".".join(map(str, sys.version_info[:3])), "dependencias_externas": "ninguna (solo biblioteca estándar)",
        "codigo_importado": dependencias(),
        "artefactos": {a: _sha(RAIZ / a) for a in ARTEFACTOS},
        "datos_crudos": {e["archivo"]: {"sha256": e["sha256"], "bytes": e["bytes"], "url": e["url"],
                                        "estado": e["estado"], "fecha_servidor": e["fecha_servidor"]}
                         for e in sorted(man["entradas"], key=lambda e: e["archivo"])},
        "resultado": {"decision": res["decision_prerregistrada"], "E": pr["E"], "ic90_bootstrap": pr["ic90_bootstrap"],
                      "P_decision": pr["P_decision"], "superior_decision": pr["superior_decision"],
                      "E_costes_x2": pr["E_costes_x2"], "excluidos": res["excluidos"]},
        "cadena_historica_T_fuera_de_muestra": {a: _sha(RAIZ / a) for a in CADENA_T},
        "reproducir": ["cd research/tendencia_btc; export PYTHONPATH=src:../hcarry_next/src",
                       "python -B experimentos/evidencia_t_multi.py verificar   # todos los hashes",
                       "python -B experimentos/t_multi.py autoprueba            # regla y métrica (sin red)",
                       ("python -B -c \"import sys, pathlib; sys.path.insert(0, 'experimentos'); import t_multi; "
                        "t_multi.evaluar(salida=pathlib.Path('/tmp/t_multi_reevaluado.json'))\"   # sin tocar el "
                        "original; requiere los datos crudos de datos_multi/")],
    }


def verificar() -> None:
    guardado = json.loads(SALIDA.read_text(encoding="utf-8"))
    actual = generar()
    malos = [k for k in guardado if k != "datos_crudos" and guardado[k] != actual[k]]
    crudos = [a for a, e in guardado["datos_crudos"].items()
              if not (RAIZ / "datos_multi" / a).exists() or _sha(RAIZ / "datos_multi" / a)["sha256"] != e["sha256"]]
    print(f"secciones distintas: {malos or 'ninguna'}; datos crudos faltantes o distintos: {crudos or 'ninguno'} "
          f"({len(guardado['datos_crudos'])} archivos)")
    sys.exit(1 if malos or crudos else 0)


if __name__ == "__main__":
    if sys.argv[1:] == ["generar"]:
        SALIDA.write_text(json.dumps(generar(), indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        print(f"{SALIDA.name} generado")
    elif sys.argv[1:] == ["verificar"]:
        verificar()
    else:
        sys.exit("uso: evidencia_t_multi.py generar | verificar")
