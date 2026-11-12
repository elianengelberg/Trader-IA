"""E3 · P0 de la Adenda R con la corrección opcional R1′ (alcance por clase; CORRECCION_R1prima_alcance_por_clase.md).
Idéntico a p0_auditoria_interna.py salvo `fuera_de_alcance`, que agrega la clase de §4.5 (lista fija + ISO-4217 y patrón
de token apalancado), leída con ast de `codigo/universo.py` de E3 sin ejecutarlo.

P0 original: auditoría de supervivencia con evidencia interna del venue. SIN RETORNOS.

Lee, de los resultados de E3 (solo lectura, sha256 antes y después):
  - el vector `estado` de cada serie de calidad (nunca O, H, L, C ni QV);
  - las listas fijas por lunes, las semanas evaluables, las salidas observadas y los eventos de la conciliación;
  - la resolución de los casos C (lectura manual del texto archivado, Adenda R §R4), pasada como argumento.
Aplica las reglas R1–R5 de `ADENDA_R_auditoria_de_supervivencia_interna.md` tal como quedaron congeladas.
Uso: python -I p0_auditoria_interna.py <dir_ejecucion_E3> <resoluciones_C.json> <salida.json>
"""
import ast
import datetime as dt
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

E3, RES, SALIDA = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
INICIO = dt.date(2017, 7, 1)
ULTIMO_LUNES = dt.date(2026, 5, 18)
CAL = E3 / "resultados" / "calidad" / "series"
ESTR = E3 / "resultados" / "estructural"
CON = E3 / "resultados" / "conciliacion_pasada1"
INSUMOS = [ESTR / "listas_fijas_por_lunes.json", ESTR / "estructural.json", CON / "salidas.json", CON / "eventos.json"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def huellas(series: list[Path]) -> dict[str, str]:
    return {str(p.relative_to(E3)): sha(p) for p in [*INSUMOS, *series]}


salidas = json.loads((CON / "salidas.json").read_text())
eventos = json.loads((CON / "eventos.json").read_text())
listas = json.loads((ESTR / "listas_fijas_por_lunes.json").read_text())
semanas = json.loads((ESTR / "estructural.json").read_text())["semanas"]
resoluciones = json.loads(RES.read_text())
series = sorted({CAL / f"{x['simbolo']}.npz" for x in salidas})
antes = huellas(series)

lunes = [(d(x["lunes"]), set(x["lista_fija"]), set(x["apalancados"])) for x in listas]
lunes.sort()


def _constantes_universo() -> tuple[set[str], set[str]]:
    arbol = ast.parse((E3 / "codigo" / "universo.py").read_text())
    valores = {}
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and isinstance(nodo.targets[0], ast.Name) and nodo.targets[0].id in ("FIAT_ISO", "LISTA_FIJA"):
            valores[nodo.targets[0].id] = nodo.value
    fiat = set(ast.literal_eval(valores["FIAT_ISO"]))
    fija = valores["LISTA_FIJA"]  # {…} | FIAT_ISO
    return set(ast.literal_eval(fija.left)) | fiat, fiat


LISTA_FIJA, _ = _constantes_universo()
BASES = {x["simbolo"][:-4] for x in json.loads((E3 / "resultados" / "calidad" / "auditoria_por_simbolo.json").read_text())}


def por_clase(simbolo: str) -> bool:
    b = simbolo[:-4]
    return b in LISTA_FIJA or any(b.endswith(suf) and b[: -len(suf)] in BASES for suf in ("UP", "DOWN", "BULL", "BEAR"))


EN_ALGUN_LUNES = set().union(*(f | a for _, f, a in lunes))


def fuera_de_alcance(simbolo: str, fecha: dt.date) -> bool:
    """R1′: la clase de §4.5, o figurar en `lista_fija`/`apalancados` de algún lunes (R1 nunca se quita)."""
    if por_clase(simbolo) or simbolo in EN_ALGUN_LUNES:
        return True
    return _fuera_R1(simbolo, fecha)


def _fuera_R1(simbolo: str, fecha: dt.date) -> bool:
    """R1: en `lista_fija` o `apalancados` del último lunes ≤ fecha (o del primero, si es anterior)."""
    elegido = lunes[0]
    for entrada in lunes:
        if entrada[0] <= fecha:
            elegido = entrada
        else:
            break
    return simbolo in elegido[1] or simbolo in elegido[2]


anunciados = {e["par"] for e in eventos if e.get("categoria") in ("A", "B")}
filas = []
for x in salidas:
    s, L = x["simbolo"], d(x["ultimo_activo"])
    estado = np.load(CAL / f"{s}.npz")["estado"]  # solo el estado; los precios no se cargan
    i = (L - INICIO).days
    cola = estado[i + 1:i + 31]
    ev = {
        "ANUNCIO": s in anunciados,
        "SUSPENSION": bool(i + 1 < len(estado) and estado[i + 1] == 3),
        "COLA_CERO": bool((cola == 2).any()),
    }
    filas.append({"simbolo": s, "L": L.isoformat(), "anio": L.year, "motivo_E3": x.get("motivo"),
                  "en_alcance": not fuera_de_alcance(s, L), **ev, "con_evidencia": any(ev.values())})

por_anio = defaultdict(lambda: defaultdict(int))
for f in filas:
    a = por_anio[f["anio"]]
    a["salidas"] += 1
    if f["en_alcance"]:
        a["en_alcance"] += 1
        for k in ("ANUNCIO", "SUSPENSION", "COLA_CERO"):
            a[k] += f[k]
        a["sin_evidencia"] += not f["con_evidencia"]
tabla = {}
for y in sorted(por_anio):
    a = por_anio[y]
    tabla[y] = {**a, "pct_sin_evidencia": round(100 * a["sin_evidencia"] / a["en_alcance"], 1) if a["en_alcance"] else 0.0}

# (iv′): primer año Y tal que todos los años Y..2026 tienen ≤ 10 % sin evidencia (un año sin salidas en alcance cumple)
anios = list(range(2018, 2027))
cumple = {y: (tabla.get(y, {}).get("en_alcance", 0) == 0
              or tabla[y]["sin_evidencia"] <= 0.10 * tabla[y]["en_alcance"]) for y in anios}
iv = next((y for y in anios if all(cumple[z] for z in anios if z >= y)), None)

# (ii′): última falla en alcance de §2.3 (T, D, C no explicada), con los C resueltos por R4
fallas = []
for e in eventos:
    cat = e.get("categoria")
    if cat not in ("T", "D", "C_no_explicada"):
        continue
    if cat == "C_no_explicada" and resoluciones.get(e["par"], {}).get("resolucion") == "agregado":
        continue
    E = d(e["E"])
    fallas.append({"par": e["par"], "E": e["E"], "categoria": cat, "en_alcance": not fuera_de_alcance(e["par"], E)})
en_alcance = [f for f in fallas if f["en_alcance"]]
ii = max((d(f["E"]) for f in en_alcance), default=None)
ii_lunes = None if ii is None else ii + dt.timedelta(days=(7 - ii.weekday()) % 7 or 7)

i_comp = d(json.loads((ESTR / "estructural.json").read_text())["inicio_componente_i_13_semanas_evaluables"])
iv_lunes = None if iv is None else dt.date(iv, 1, 1) + dt.timedelta(days=(7 - dt.date(iv, 1, 1).weekday()) % 7)
candidatos = [c for c in (i_comp, ii_lunes, iv_lunes) if c is not None]
inicio = max(candidatos) if iv is not None else None
ventana = [w for w in semanas if inicio is not None and inicio <= d(w["lunes"]) <= ULTIMO_LUNES]
evaluables = sum(w["evaluable"] for w in ventana)
no_eval_pct = round(100 * (len(ventana) - evaluables) / len(ventana), 1) if ventana else None
valido = inicio is not None and evaluables >= 156 and (no_eval_pct is not None and no_eval_pct <= 20.0)

despues = huellas(series)
salida = {
    "adenda": "ADENDA_R_auditoria_de_supervivencia_interna.md + CORRECCION_R1prima_alcance_por_clase.md",
    "por_anio": tabla,
    "componentes": {"i": i_comp.isoformat(), "ii_prima": ii_lunes and ii_lunes.isoformat(),
                    "ultima_falla_en_alcance": ii and ii.isoformat(), "iv_prima_anio": iv},
    "fallas_2_3": fallas,
    "resoluciones_C": resoluciones,
    "inicio_H": inicio and inicio.isoformat(),
    "semanas_H": len(ventana), "evaluables_H": evaluables, "no_evaluables_pct": no_eval_pct,
    "veredicto": "VALIDO" if valido else "INVALIDO",
    "salidas": filas,
    "insumos_sin_cambios": antes == despues, "n_insumos": len(antes), "huellas_insumos": antes,
}
SALIDA.write_text(json.dumps(salida, indent=1, ensure_ascii=False))
print(json.dumps({k: salida[k] for k in ("por_anio", "componentes", "inicio_H", "semanas_H", "evaluables_H",
                                         "no_evaluables_pct", "veredicto", "insumos_sin_cambios")}, indent=1,
                 ensure_ascii=False))
