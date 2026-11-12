"""E4 v1 · Evaluación en las miradas prerregistradas (365 y 730 días; cero reintentos). Requiere autorización.
Orden de las comprobaciones (todas antes de calcular cualquier estadístico):
  1. CONGELACION: cada línea «sha256  ruta» tiene que coincidir. El prerregistro (.md) se busca junto a CONGELACION y el código
     (codigo/*.py) es el que se está ejecutando; todo .py de la carpeta tiene que figurar. Se verifica ANTES de importar el núcleo.
  2. INICIO_E4.json: su sha256 tiene que ser el anclado (--inicio-sha256), apunta a esta CONGELACION, y T0 = día UTC siguiente al
     bloque que confirmó el ancla. T0 y las miradas no son argumentos.
  3. Guarda de rutas sobre datos y salida; marca SINTETICO.txt coherente con el modo; fecha ≥ T0 + mirada + REZAGO.
  4. REGISTRO: la mirada no se hizo antes, la anterior terminó en CONTINUAR u OMITIDA, ninguna fue FINAL.
  5. Datos: por día, MANIFIESTO.sha256 = el último anotado en REGISTRO (sin errores de recolección), y cada ZIP con su hash.
  6. Lectura: con o sin encabezado, marcas en ms o µs, vela del día correcto. Un archivo ilegible es un par-día faltante; si son
     más del 1 %, se aborta SIN calcular nada (no consume la mirada).
Con --solo-validar hace 1–6 sobre los días ya recolectados y no calcula nada.
Uso: python -I -B evaluar.py --datos <dir> --congelacion <CONGELACION_E4.txt> --inicio <INICIO_E4.json> --inicio-sha256 <hex>
       --mirada {1,2} --salida <dir_nuevo> --protegidos <PROTEGIDOS.tsv> [--solo-validar] [--sintetico --hoy F --miradas-prueba a,b]"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
import sys
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
REZAGO = 3
MAX_FRAC_ILEGIBLE = 0.01


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def verificar_congelacion(cong):
    base = os.path.dirname(os.path.abspath(cong))
    filas = [l.split(None, 1) for l in open(cong).read().splitlines() if l.strip() and not l.startswith("#")]
    vistos, md = set(), []
    for h, ruta in filas:
        ruta = ruta.strip().lstrip("*")
        if ruta.startswith("codigo/"):
            p = os.path.join(AQUI, ruta[len("codigo/"):])
            vistos.add(os.path.basename(p))
        else:
            p = os.path.join(base, ruta)
            md.append(p)
        if not os.path.isfile(p) or sha(p) != h:
            raise SystemExit(f"CONGELACION no coincide en {ruta}: no se evalúa")
    sueltos = sorted(f for f in os.listdir(AQUI) if f.endswith(".py") and f not in vistos)
    if sueltos or len(md) != 1 or not md[0].endswith(".md"):
        raise SystemExit(f"CONGELACION incompleta (código sin congelar: {sueltos}; prerregistros: {len(md)}): no se evalúa")
    return sha(cong)


def verificar_inicio(inicio, sha_esperado, sha_cong):
    if sha(inicio) != sha_esperado:
        raise SystemExit("INICIO_E4.json no es el anclado: no se evalúa")
    d = json.load(open(inicio))
    if d.get("congelacion_sha256") != sha_cong:
        raise SystemExit("INICIO_E4.json apunta a otra CONGELACION: no se evalúa")
    bloque = dt.datetime.fromisoformat(d["ancla"]["bloque_utc"].replace("Z", "+00:00"))
    t0 = dt.date.fromisoformat(d["t0"])
    if t0 != bloque.astimezone(dt.timezone.utc).date() + dt.timedelta(days=1):
        raise SystemExit("T0 no es el día UTC siguiente al bloque del ancla: no se evalúa")
    return t0


def registros(reg):
    return [json.loads(l) for l in open(reg)] if os.path.exists(reg) else []


def verificar_dia(datos, d, ultimo):
    """Devuelve el conjunto de ZIP verificados del día; aborta si el día no está completo o no coincide."""
    carpeta = os.path.join(datos, d)
    man = os.path.join(carpeta, "MANIFIESTO.sha256")
    r = ultimo.get(d)
    if r is None or not os.path.exists(man):
        raise SystemExit(f"día {d}: sin recolección registrada: no se evalúa (recolectarlo primero)")
    if r["errores"] != 0 or sha(man) != r["manifiesto_sha256"]:
        raise SystemExit(f"día {d}: recolección con errores o manifiesto distinto del registrado: no se evalúa")
    listados = {}
    for l in open(man).read().splitlines():
        h, rel = l.split(None, 1)
        listados[rel.strip()] = h
    presentes = {f"{iv}/{f}" for iv in ("1d", "1h") if os.path.isdir(os.path.join(carpeta, iv))
                 for f in os.listdir(os.path.join(carpeta, iv)) if f.endswith(".zip")}
    if presentes != set(listados):
        raise SystemExit(f"día {d}: hay ZIP fuera del manifiesto o faltan ZIP del manifiesto: no se evalúa")
    for rel, h in listados.items():
        if sha(os.path.join(carpeta, rel)) != h:
            raise SystemExit(f"día {d}: {rel} cambió después de la recolección: no se evalúa")
    return listados


def _ms(x):
    v = int(float(x))
    return v // 1000 if v > 10 ** 14 else v  # desde 2025-01-01 las marcas de spot vienen en microsegundos


def filas_csv(p):
    with zipfile.ZipFile(p) as z:
        nombres = [n for n in z.namelist() if n.endswith(".csv")]
        if len(nombres) != 1:
            raise ValueError("el ZIP no tiene exactamente un CSV")
        filas = [f for f in csv.reader(io.TextIOWrapper(z.open(nombres[0]), "ascii")) if f]
    if filas and not filas[0][0].strip().lstrip("-").isdigit():
        filas = filas[1:]  # encabezado
    return filas


def leer_1d(p, d):
    filas = filas_csv(p)
    if len(filas) != 1:
        raise ValueError("la vela 1d tiene que ser una sola fila")
    f = filas[0]
    if _ms(f[0]) != int(dt.datetime.combine(d, dt.time(), dt.timezone.utc).timestamp() * 1000):
        raise ValueError("la vela no es del día del archivo")
    return float(f[4]), float(f[7]), float(f[8])  # cierre, volumen en USDT, operaciones


def leer_1h(p, d):
    filas = filas_csv(p)
    if not filas or len(filas) > 24:
        raise ValueError("el archivo 1h tiene que tener entre 1 y 24 filas")
    if _ms(filas[0][0]) != int(dt.datetime.combine(d, dt.time(), dt.timezone.utc).timestamp() * 1000):
        return 0.0  # no hay vela de las 00:00: sin precio de entrada ese día
    return float(filas[0][4])  # cierre de la vela 00:00–01:00 = precio a las 01:00 UTC


def main():
    a = argparse.ArgumentParser()
    for k in ("datos", "congelacion", "inicio", "inicio-sha256", "salida", "protegidos"):
        a.add_argument("--" + k, required=True)
    a.add_argument("--mirada", type=int, choices=(1, 2), required=True)
    a.add_argument("--solo-validar", action="store_true")
    a.add_argument("--sintetico", action="store_true")
    a.add_argument("--hoy")
    a.add_argument("--miradas-prueba")
    x = a.parse_args()
    sha_cong = verificar_congelacion(x.congelacion)                       # 1 (antes de importar el núcleo)
    sys.path.insert(0, AQUI)
    import guarda_rutas as G
    import nucleo as N
    from recolector import anexar
    t0 = verificar_inicio(x.inicio, x.inicio_sha256, sha_cong)           # 2
    prot = G.cargar_protegidos(x.protegidos)                             # 3
    G.verificar(x.datos, prot)
    G.verificar(os.path.dirname(os.path.abspath(x.salida)), prot)
    if x.sintetico != os.path.exists(os.path.join(x.datos, "SINTETICO.txt")):
        raise SystemExit("modo y marca SINTETICO.txt no coinciden: no se evalúa")
    if (x.hoy or x.miradas_prueba) and not x.sintetico:
        raise SystemExit("--hoy y --miradas-prueba solo se admiten en modo sintético")
    miradas = tuple(int(v) for v in x.miradas_prueba.split(",")) if x.miradas_prueba else N.MIRADAS
    if x.mirada > len(miradas):
        raise SystemExit("esa mirada no existe en el diseño")
    hoy = dt.date.fromisoformat(x.hoy) if x.hoy else dt.datetime.now(dt.timezone.utc).date()
    dias_k = miradas[x.mirada - 1]
    if not x.solo_validar and hoy < t0 + dt.timedelta(days=dias_k + REZAGO):
        raise SystemExit(f"todavía no: la mirada {x.mirada} es a partir de {t0 + dt.timedelta(days=dias_k + REZAGO)}")
    reg = os.path.join(x.datos, "REGISTRO.jsonl")                        # 4
    evals = [r for r in registros(reg) if r.get("tipo") == "EVALUACION"]
    n1 = None
    if not x.solo_validar:
        if any(r.get("decision") == "FINAL" for r in evals) or any(r.get("mirada") == x.mirada for r in evals):
            raise SystemExit("esa mirada ya se hizo o E4 ya terminó: no hay reintentos")
        if x.mirada == 2:
            previa = [r for r in evals if r.get("mirada") == 1]
            if len(previa) != 1 or previa[0].get("decision") not in ("CONTINUAR", "OMITIDA"):
                raise SystemExit("la mirada 2 exige la mirada 1 registrada con CONTINUAR u OMITIDA")
            n1 = previa[0]["n_evaluables"] if previa[0]["decision"] == "CONTINUAR" else None
    ultimo = {}                                                          # 5
    for r in registros(reg):
        if r.get("tipo") == "RECOLECCION":
            ultimo[r["dia"]] = r
    inicio = t0 - dt.timedelta(days=N.VENTANA + 1)
    fin = t0 + dt.timedelta(days=dias_k)
    if x.solo_validar:
        fin = min(fin, max((dt.date.fromisoformat(d) for d in ultimo), default=inicio))
    fechas = [inicio + dt.timedelta(days=i) for i in range((fin - inicio).days + 1)]
    listados = {d: verificar_dia(x.datos, d.isoformat(), ultimo) for d in fechas}
    simbolos = sorted({rel.split("/")[1][:-4] for L in listados.values() for rel in L})
    if not simbolos:
        raise SystemExit("no hay datos")
    import numpy as np                                                   # 6
    cierre = {s: np.zeros(len(fechas)) for s in simbolos}
    volq = {s: np.zeros(len(fechas)) for s in simbolos}
    ops = {s: np.zeros(len(fechas)) for s in simbolos}
    entrada = {s: np.zeros(len(fechas)) for s in simbolos}
    ilegibles, total = [], 0
    for i, d in enumerate(fechas):
        for rel in listados[d]:
            iv, s = rel.split("/")[0], rel.split("/")[1][:-4]
            total += 1
            try:
                p = os.path.join(x.datos, d.isoformat(), rel)
                if iv == "1d":
                    cierre[s][i], volq[s][i], ops[s][i] = leer_1d(p, d)
                else:
                    entrada[s][i] = leer_1h(p, d)
            except Exception as e:  # noqa: BLE001  (par-día faltante; se cuenta)
                ilegibles.append(f"{d}/{rel}: {e}")
    frac_ilegible = len(ilegibles) / total
    resumen = {"dias": len(fechas), "archivos": total, "ilegibles": len(ilegibles), "frac_ilegible": frac_ilegible,
               "ejemplos_ilegibles": ilegibles[:5]}
    if x.solo_validar or frac_ilegible > MAX_FRAC_ILEGIBLE:
        print(json.dumps({"validacion": "OK" if frac_ilegible <= MAX_FRAC_ILEGIBLE else "FALLIDA", **resumen}, ensure_ascii=False))
        if frac_ilegible > MAX_FRAC_ILEGIBLE:
            raise SystemExit("demasiados archivos ilegibles: no se calcula nada (la mirada no se consume)")
        return
    os.mkdir(x.salida)  # falla si existe
    datos = N.Datos(cierre, volq, ops, entrada)
    k0 = (t0 - inicio).days
    dias = [N.dia(datos, t) for t in range(k0, k0 + dias_k)]
    res = N.evaluar_mirada(dias, x.mirada, miradas, n1)
    res.update({"experimento": "E4 v1 H-XS-REV-1 prospectivo", "sintetico": x.sintetico, "t0": t0.isoformat(),
                "congelacion_sha256": sha_cong, "lectura": resumen})
    if res.get("decision") == "FINAL" and res.get("clasificacion") != "INVALIDO":
        res["sensibilidad_costos"] = {f"comision_{c}_medio_spread_{b}": {k: N.economia(dias, c, b)[k] for k in
                                      ("costo_diario_medio", "descarte_rapido_economico", "neto_diario_medio", "t_neto")}
                                      for c, b in ((7.5, 10.0), (7.5, 20.0), (10.0, 5.0))}
    p = os.path.join(x.salida, f"RESULTADO_E4_mirada{x.mirada}.json")
    with open(p, "x") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=float)
        f.flush()
        os.fsync(f.fileno())
    anexar(reg, {"tipo": "EVALUACION", "mirada": x.mirada, "decision": res["decision"], "n_evaluables": res.get("n_evaluables", res.get("n_dias")),
                 "utc": dt.datetime.now(dt.timezone.utc).isoformat(), "sintetico": x.sintetico, "resultado_sha256": sha(p),
                 "clasificacion": res.get("clasificacion")})
    print(json.dumps({k: v for k, v in res.items() if k not in ("nota",)}, ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
