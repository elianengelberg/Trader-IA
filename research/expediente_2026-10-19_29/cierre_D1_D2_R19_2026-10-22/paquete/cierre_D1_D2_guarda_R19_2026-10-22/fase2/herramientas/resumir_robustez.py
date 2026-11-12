"""Resume la evaluación de robustez: por árbol y escenario, en cuántas corridas (datos × semilla) salta cada comprobación y
en cuántas no se cumple la precondición. Uso: python resumir_robustez.py <dir_robustez>"""
import json, sys, pathlib, collections
d = pathlib.Path(sys.argv[1])
grupos = {"motor correcto (01+02v3)": ["obl_1_10.json", "obl_11_20.json"], "02v3 sin 01": ["solo02_1_10.json"]}
for nombre, archivos in grupos.items():
    filas = [f for a in archivos for f in json.load(open(d / a))["filas"]]
    semillas = sorted({f["semilla"] for f in filas}); datos = sorted({f["datos"] for f in filas})
    print(f"== {nombre}: {len(filas)} corridas · datos {datos} · semillas {semillas[0]}–{semillas[-1]} ({len(semillas)})")
    errores = [f for f in filas if "error" in f]
    if errores: print("   ERRORES:", errores[:3])
    por_esc = collections.defaultdict(list)
    for f in filas:
        if "error" not in f: por_esc[f["escenario"]].append(f)
    for esc, fs in por_esc.items():
        saltan = collections.Counter(c for f in fs for c in f["saltan"])
        alguna = sum(1 for f in fs if f["saltan"])
        sin_pre = sum(1 for f in fs if not f["precondicion"])
        falla_prueba = sum(1 for f in fs if f["saltan"] or not f["precondicion"])
        print(f"   {esc:22s} corridas={len(fs):3d} · la prueba fallaría en {falla_prueba:3d} · alguna comprobación salta en {alguna:3d} · "
              f"precondición no cumplida en {sin_pre:3d} · por comprobación {dict(saltan)}")
        por_datos = collections.Counter(f["datos"] for f in fs if f["saltan"] or not f["precondicion"])
        if por_datos: print(f"   {'':22s} fallas por datos: {dict(por_datos)}")
        pos = [f["posiciones"] for f in fs]
        print(f"   {'':22s} posiciones por corrida: mín {min(pos)} · mediana {sorted(pos)[len(pos)//2]} · máx {max(pos)}")
