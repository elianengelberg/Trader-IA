"""Comprobaciones independientes sobre el paquete v0.5 (solo lectura). Cada subcomando escribe su informe en stdout.
  zip <zip>                         B1: testzip, lista = SHA256SUMS, cada hash en memoria, sin enlaces ni rutas peligrosas
  registro <paquete>                B2: cadena del REGISTRO_ACCIONES.jsonl, hashes de evidencia y orden de las fechas
  estatico <codigo/verificacion>    B6: importaciones de red y de procesos, llamadas peligrosas, ACCION del ejecutor
  declaracion <trazabilidad_T> [<research/tendencia_btc>]
                                    C1: el .bin es la forma canónica del .json; hashes declarados = archivos actuales
Uso: python3 -I comprobaciones_v05.py <subcomando> <args>"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
import zipfile
from pathlib import Path


def zip_(z: Path) -> int:
    with zipfile.ZipFile(z) as f:
        assert f.testzip() is None
        raiz = {n.split("/")[0] for n in f.namelist()}
        m = {n.split("/", 1)[1]: f.read(n) for n in f.namelist() if not n.endswith("/")}
        peligrosas = [i.filename for i in f.infolist() if (i.external_attr >> 16) & 0o170000 == 0o120000
                      or i.filename.startswith("/") or ".." in i.filename.split("/")]
    s = dict(reversed(x.split("  ", 1)) for x in m["SHA256SUMS.txt"].decode().splitlines())
    malos = [r for r, h in s.items() if hashlib.sha256(m[r]).hexdigest() != h]
    print(f"SHA-256 del ZIP: {hashlib.sha256(z.read_bytes()).hexdigest()}")
    print(f"raíz única: {sorted(raiz)}; miembros: {len(m)}; en SHA256SUMS: {len(s)}; "
          f"lista igual: {set(s) == set(m) - {'SHA256SUMS.txt'}}; hashes distintos: {malos or 'ninguno'}")
    print(f"enlaces simbólicos o rutas absolutas o con '..': {peligrosas or 'ninguno'}")
    return 0 if not malos and not peligrosas and set(s) == set(m) - {"SHA256SUMS.txt"} else 1


def registro(p: Path) -> int:
    lineas = (p / "REGISTRO_ACCIONES.jsonl").read_text(encoding="utf-8").splitlines()
    ant, fallos, utcs, no_ejec = None, [], [], 0
    for i, linea in enumerate(lineas):
        r = json.loads(linea)
        if json.dumps(r, ensure_ascii=False, sort_keys=True) != linea:
            fallos.append(f"{i}: no canónica")
        if r["n"] != i or r["anterior_sha256"] != ant:
            fallos.append(f"{i}: cadena rota")
        if r["evidencia"]:
            utcs.append(r["utc"])
            if hashlib.sha256((p / r["evidencia"]).read_bytes()).hexdigest() != r["evidencia_sha256"]:
                fallos.append(f"{i}: hash de {r['evidencia']} distinto")
        else:
            no_ejec += 1
        ant = hashlib.sha256(linea.encode()).hexdigest()
    print(f"{len(lineas)} entradas ({len(utcs)} con evidencia, {no_ejec} NO ejecutadas); cadena y hashes: "
          f"{'OK' if not fallos else fallos}")
    print(f"cabeza de la cadena: {ant}")
    print(f"fechas (mtime de la evidencia): de {min(utcs)} a {max(utcs)}; en orden cronológico: {utcs == sorted(utcs)}")
    print("LÍMITE (D-4): el registro se genera DESPUÉS, a partir del mtime de cada archivo. Prueba coherencia interna, no "
          "cuándo ocurrió cada acción, y quien controle el equipo puede regenerarlo entero.")
    return 0 if not fallos else 1


def estatico(d: Path) -> int:
    red = {"socket", "http", "urllib", "requests", "ftplib", "smtplib", "ssl", "asyncio"}
    for f in sorted(d.glob("*.py")):
        arbol = ast.parse(f.read_text(encoding="utf-8"))
        imps = set()
        for n in ast.walk(arbol):
            if isinstance(n, ast.Import):
                imps |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.module:
                imps.add(n.module.split(".")[0])
        llamadas = sorted({f"{n.func.value.id}.{n.func.attr}" for n in ast.walk(arbol) if isinstance(n, ast.Call)
                           and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                           and n.func.value.id in {"subprocess", "os", "socket"}
                           and n.func.attr in {"run", "Popen", "call", "check_output", "system", "execv", "execve",
                                               "spawnv", "connect", "fork"}})
        print(f"{f.name}: red={sorted(imps & red) or 'ninguna'}; procesos="
              f"{sorted(imps & {'subprocess', 'multiprocessing', 'pty'}) or 'ninguno'}; llamadas={llamadas or 'ninguna'}")
    arbol = ast.parse((d / "ejecutor_aislado.py").read_text(encoding="utf-8"))
    accion = [ast.literal_eval(a.value) for a in ast.walk(arbol) if isinstance(a, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == "ACCION" for t in a.targets)]
    literales = sorted({v.value for n in ast.walk(arbol) if isinstance(n, ast.Dict)
                        for k, v in zip(n.keys, n.values, strict=True)
                        if isinstance(k, ast.Constant) and k.value == "accion_ejecutada" and isinstance(v, ast.Constant)})
    print(f"ejecutor_aislado.py: ACCION = {accion}; literales asignados a 'accion_ejecutada': "
          f"{literales or 'solo vía ACCION'}")
    return 0 if accion == ["NINGUNA"] and not literales else 1


def declaracion(d: Path, t: Path | None) -> int:
    doc = json.loads((d / "DECLARACION_A_FIRMAR_FUERA_DE_MUESTRA_T.json").read_text(encoding="utf-8"))
    canon = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ok = canon == (d / "DECLARACION_A_FIRMAR_FUERA_DE_MUESTRA_T.bin").read_bytes()
    print(f"SHA-256 del .bin: {hashlib.sha256(canon).hexdigest()}; .bin == forma canónica del .json: {ok}")
    for a in doc["artefactos"]:
        actual = hashlib.sha256((t / a["ruta"]).read_bytes()).hexdigest() if t else None
        print(f"  {a['ruta']}: declarado {a['sha256'][:16]}…; actual == declarado: "
              f"{actual == a['sha256'] if t else 'no comprobado (sin repositorio)'}")
        ok &= (actual == a["sha256"]) if t else True
    return 0 if ok else 1


if __name__ == "__main__":
    c, args = sys.argv[1], [Path(a) for a in sys.argv[2:]]
    sys.exit({"zip": lambda: zip_(args[0]), "registro": lambda: registro(args[0]),
              "estatico": lambda: estatico(args[0]),
              "declaracion": lambda: declaracion(args[0], args[1] if len(args) > 1 else None)}[c]())
