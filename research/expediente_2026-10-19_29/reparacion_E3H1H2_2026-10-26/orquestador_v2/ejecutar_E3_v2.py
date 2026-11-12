"""E3 · orquestador v2 de la ejecución confirmatoria ÚNICA de la v3 (H1 y H2) en la ventana A. NO autoriza ninguna ejecución.

Base: `ejecutar_E3R.py` (3b64a04d…, congelado, sin modificar). Cambios, y solo estos (diff en DIFF_v1_v2.diff):
  C2. R4 (N14): el aporte de cada moneda se mide contra el retorno BRUTO de EW-U30 (antes, contra el neto).
  C3. Modo real: antes de leer cualquier precio verifica el sha256 exacto de cada insumo (conjunto de las 757 series,
      estructural, listas, segunda pasada, mapeos, ventana A y módulos congelados) contra `ENTRADAS_CONGELADAS.json`.
      Si algo no coincide, se detiene sin crear la salida y sin leer precios.
  C4. Panel: aplica los mapeos de la Adenda 1 (regla 1, renombre X → Y; regla 2, redenominación X → X con r) y deja de
      aplicar la Adenda R2. Los cortes sin anuncio archivado siguen la regla 3 (mismo listado si el corte dura < 30 días).
  C5. INVÁLIDO es un resultado explícito: si la ventana o la validez previa (v3 §10) fallan, escribe RESULTADO_E3.json
      con «INVALIDO» y el motivo, sin calcular H1 ni H2.
  C6. Solo la ventana A: se eliminan la opción B, R1′ y la elección entre varios P0. La autorización debe contener la
      FRASE nueva, el sha256 de este archivo y el de ENTRADAS_CONGELADAS.json (que fija, entre otros, el de la ventana A).
Todo lo demás (validez previa, H1, H2, Holm, robustez, descriptivo) es idéntico al v1.

Modos:
  sintetico <salida_dir> <momentum> [replicas_R5] [dir_ejecucion_E3]
      Panel sintético de `pruebas_motor.panel_sintetico` (sin datos reales). Prueba el camino completo.
  real <dir_ejecucion_E3> <ventana_A_pasada2.json> <autorizacion.txt> <salida_dir>
      SOLO con autorización explícita posterior. La salida no puede existir (ejecución única).
"""
import datetime as dt
import hashlib
import json
import math
import sys
from pathlib import Path
from statistics import NormalDist

import numpy as np

sys.dont_write_bytecode = True  # no escribir cachés en el directorio congelado de E3
AQUI = Path(__file__).resolve().parent
E3_DEFECTO = AQUI.parent.parent / "experimentos" / "E3_seleccion_posicion_2026-10-19" / "ejecucion_E3"
MANIFIESTO = AQUI / "ENTRADAS_CONGELADAS.json"
CONGELADOS = {"universo.py": "2af45115238d0065d54f0c6230b16c71831293b235b72627e62d1d7c7d7491f7",
              "motor.py": "cadb805d2d882fcf909e0309cff85203ee383c6b8ed0ac08b89f4028ee999b2e",
              "inferencia.py": "7b28038621c1d366655d726bb885ca0105f1a25cfcdb9615e86a7fe39e85f3e1"}
PRUEBAS_MOTOR = "54f832d39422379f14bf5d0ad2f42bba9e8f0b4d40915ea72bcef0c968da04e5"  # HUELLAS_codigo_preparado.txt
FRASE = ("AUTORIZO LA EJECUCION UNICA DE E3 (H1 Y H2) EN LA VENTANA A CON LA V3, LA ADENDA R CON R1 LITERAL, "
         "LA SEGUNDA PASADA Y LOS MAPEOS DE LA ADENDA 1")
ULTIMA_FORMACION = dt.date(2026, 5, 18)
ULTIMO_DIA_DATOS = dt.date(2026, 5, 31)
SEMILLA_H2, SEMILLA_R5, SEMILLA_CORTES, SEMILLA_DIAG = 20261020, 20261021, 20261022, 20261027
DELTA_IC = 0.01
_N = NormalDist()


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def importar_congelados(e3: Path):
    cod = e3 / "codigo"
    for nombre, h in CONGELADOS.items():
        if sha(cod / nombre) != h:
            raise SystemExit(f"{nombre} no coincide con su hash congelado: no se ejecuta")
    sys.path.insert(0, str(cod))
    import inferencia
    import motor
    import universo
    return universo, motor, inferencia


# ------------------------------------------------------------------ insumos (C3), sin leer precios

def hash_conjunto(d: Path) -> str:
    """Receta de CIERRE_E3: sha256 de la salida de `find . -type f -print0 | sort -z | xargs -0 sha256sum`."""
    d = Path(d)
    rel = sorted(("./" + p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file()), key=lambda r: r.encode())
    return hashlib.sha256("".join(f"{sha(d / r[2:])}  {r}\n" for r in rel).encode()).hexdigest()


def verificar_entradas(e3: Path, ventana: Path, manifiesto: Path = None) -> dict:
    """Compara cada insumo con su sha256 congelado. Lee bytes para el hash, no interpreta ningún precio.
    Si falta un insumo o un hash no coincide, aborta: la salida no se crea y no se lee ningún precio."""
    m = json.loads(Path(manifiesto or MANIFIESTO).read_text())
    raices = {"E3": Path(e3), "reparacion": AQUI.parent, "ventana": Path(ventana)}
    obs, malos = {}, {}
    for x in m["entradas"]:
        ruta = raices[x["base"]] if x["base"] == "ventana" else raices[x["base"]] / x["ruta"]
        if not ruta.exists():
            malos[x["nombre"]] = {"esperado": x["sha256"], "observado": "AUSENTE"}
            continue
        h = hash_conjunto(ruta) if x["tipo"] == "conjunto" else sha(ruta)
        obs[x["nombre"]] = h
        if h != x["sha256"]:
            malos[x["nombre"]] = {"esperado": x["sha256"], "observado": h}
    if malos:
        raise SystemExit(f"insumos que no coinciden con ENTRADAS_CONGELADAS.json: {malos}. No se lee ningún precio.")
    return {"manifiesto": sha(Path(manifiesto or MANIFIESTO)), "insumos": obs, "inicio_H_esperado": m["inicio_H_esperado"],
            "mapeos": m["mapeos"]}


# ------------------------------------------------------------------ panel real (solo en modo real, con autorización)

def panel_real(e3: Path, universo, mapeos):
    """Series de calidad de E3: act = estado == 1. Aplica los mapeos de la Adenda 1 (C4); no aplica la Adenda R2."""
    series = sorted((e3 / "resultados" / "calidad" / "series").glob("*.npz"))
    syms, O, C, QV, act = [], [], [], [], []
    for f in series:
        z = np.load(f)
        syms.append(str(z["simbolo"]))
        O.append(z["O"]), C.append(z["C"]), QV.append(z["QV"]), act.append(z["estado"] == 1)
    O, C, QV, act = (np.array(x) for x in (O, C, QV, act))
    syms, O, C, QV, act, registro = aplicar_mapeos(syms, O, C, QV, act, mapeos, universo.INICIO)
    return universo.Panel(syms, O, C, QV, act, mapeos_renombre=registro), registro


def aplicar_mapeos(syms, O, C, QV, act, mapeos, inicio):
    """Adenda 1, reglas 1 y 2 (v3 §2.2.4; §4.10 «renombre mapeado»), en orden de fecha efectiva E.
    r = unidades nuevas por unidad vieja. QV está en USDT y no cambia.
    Regla 2 (X → X): los precios de X anteriores a la reapertura (primer día activo > E) se dividen por r. La serie queda
      continua a través de r y las unidades de una posición, multiplicadas por r. Edad y listado no cambian.
    Regla 1 (X → Y): Y continúa a X en la fila de X: historia de X con precios / r hasta su último día activo y, desde el
      primer día activo de Y, los datos de Y. La fila pasa a llamarse Y (hereda edad y posiciones) y la fila original de Y
      se retira. Aborta si falta X o Y, si X vuelve a estar activo después de E, si Y estuvo activo antes del cese de X,
      o si no hay reapertura: no se une nada a ciegas."""
    syms = list(syms)
    O, C, QV, act = O.copy(), C.copy(), QV.copy(), act.copy()
    retirar, registro = [], []
    for m in sorted(mapeos, key=lambda m: (m["E"], m["regla"])):
        x, y, r = m["viejo_usdt"], m["nuevo_usdt"], float(m["r"])
        if x not in syms or y not in syms or not r > 0:
            raise SystemExit(f"mapeo imposible: {x} → {y} (r = {m['r']})")
        i, e = syms.index(x), (dt.date.fromisoformat(m["E"]) - inicio).days
        if m["regla"] == 2:
            if x != y:
                raise SystemExit(f"regla 2 con símbolos distintos: {x} → {y}")
            despues = np.flatnonzero(act[i, e + 1:])
            if despues.size == 0:
                raise SystemExit(f"{x}: no hay reapertura después de {m['E']}")
            k = e + 1 + int(despues[0])
            antes = np.flatnonzero(act[i, :e + 1])
            if antes.size == 0 or k - int(antes[-1]) < 2:
                raise SystemExit(f"{x}: no hay un corte de negociación alrededor de E = {m['E']}; no se aplica r")
            O[i, :k] /= r
            C[i, :k] /= r
            registro.append({**m, "fila": x, "dia_reapertura": (inicio + dt.timedelta(days=k)).isoformat()})
            continue
        j = syms.index(y)
        activos_x = np.flatnonzero(act[i])
        if activos_x.size == 0 or activos_x[-1] > e:
            raise SystemExit(f"{x}: sin actividad o activo después de E = {m['E']}; no se mapea")
        activos_y = np.flatnonzero(act[j])
        if activos_y.size == 0 or activos_y[0] <= activos_x[-1]:
            raise SystemExit(f"{y}: sin actividad o activo antes del cese de {x}; no se mapea")
        k = int(activos_y[0])
        O[i, :k], C[i, :k] = O[i, :k] / r, C[i, :k] / r
        O[i, k:], C[i, k:], QV[i, k:], act[i, k:] = O[j, k:], C[j, k:], QV[j, k:], act[j, k:]
        syms[i], syms[j] = y, f"#retirada:{y}"
        retirar.append(j)
        registro.append({**m, "fila": y, "ultimo_activo_viejo": (inicio + dt.timedelta(days=int(activos_x[-1]))).isoformat(),
                         "primer_activo_nuevo": (inicio + dt.timedelta(days=k)).isoformat()})
    quedan = [s for s in range(len(syms)) if s not in set(retirar)]
    return [syms[s] for s in quedan], O[quedan], C[quedan], QV[quedan], act[quedan], registro


# ------------------------------------------------------------------ validez previa (v3 §10), sin estadísticos

def validez_previa(P, formaciones, universo, motor):
    """§10.8 bloqueo de fechas; §10.7 semanas evaluables; §10.5 invariancia al truncar (como pruebas_motor, sobre P)."""
    out = {"ultimo_dia_panel": (universo.INICIO + dt.timedelta(days=P.D - 1)).isoformat()}
    out["bloqueo_fechas"] = universo.INICIO + dt.timedelta(days=P.D - 1) <= ULTIMO_DIA_DATOS
    cache = {}
    ev = []
    for t in formaciones[:-1]:
        U = universo.universo(P, t)
        cache[(t, 30, (7, 14, 21, 28), frozenset())] = U
        ev.append(U is not None and U.get("n_elegibles", 0) >= 30)
    out["semanas"], out["evaluables"] = len(ev), int(sum(ev))
    out["no_evaluables_pct"] = round(100 * (len(ev) - sum(ev)) / len(ev), 1) if ev else None
    out["semanas_ok"] = sum(ev) >= 156 and out["no_evaluables_pct"] <= 20.0
    rng = np.random.default_rng(SEMILLA_CORTES)
    base = motor.simular(P, formaciones, motor.Config(), cache, registrar_pesos=True)
    cortes = []
    for c in sorted(rng.choice(np.arange(formaciones[20], formaciones[-10]), size=5, replace=False)):
        P2 = universo.Panel(P.sym, P.O.copy(), P.C.copy(), P.QV.copy(), P.act.copy())
        P2.O[:, c:] *= rng.uniform(0.2, 5, (P.S, 1))
        P2.C[:, c:] *= rng.uniform(0.2, 5, (P.S, 1))
        P2.QV[:, c:] = rng.uniform(0, 1e8, P2.QV[:, c:].shape)
        P2.act[:, c:] = rng.random(P2.act[:, c:].shape) < 0.5
        P2.C[:, c:] = np.where(P2.act[:, c:], P2.C[:, c:], np.nan)
        P2._derivados()
        F2 = [t for t in formaciones if t < c - 7]
        r2 = motor.simular(P2, F2 + [F2[-1] + 7], motor.Config(), {}, registrar_pesos=True)
        ok_u = all((a is None and b is None) or (a["U_inv"] == b["U_inv"] and a["U_pred"] == b["U_pred"]
                                                  and np.allclose(a["S"], b["S"]) and a["rk"] == b["rk"])
                   for a, b in zip(base["univs"][:len(F2)], r2["univs"][:len(F2)], strict=False))
        ok_o = base["objetivos"][:len(r2["objetivos"]) - 1] == r2["objetivos"][:-1]
        ok_p = all(set(a[1]) == set(b[1]) and all(abs(a[1][s] - b[1][s]) < 1e-12 for s in a[1])
                   for a, b in zip(base["pesos"][:len(F2)], r2["pesos"][:len(F2)], strict=False))
        cortes.append({"corte": (universo.INICIO + dt.timedelta(days=int(c))).isoformat(), "universos_y_senal": ok_u,
                       "objetivos": ok_o, "pesos": ok_p})
    out["invariancia_truncado"] = cortes
    out["invariancia_ok"] = all(x["universos_y_senal"] and x["objetivos"] and x["pesos"] for x in cortes)
    out["valido"] = bool(out["bloqueo_fechas"] and out["semanas_ok"] and out["invariancia_ok"])
    return out, cache


# ------------------------------------------------------------------ cálculo (idéntico en los dos modos)

def contribuciones(P, sim, formaciones, sim_ew):
    """R4 (N14): aporte_c = Σ_t w_{c,t} · (r_{c,t} − r_{EW,t}), bruto; r_{c,t} de apertura a apertura de la semana."""
    aporte = {}
    r_ew = dict(zip(formaciones[:-1], sim_ew["r"], strict=False))
    for t, pesos in sim["pesos"]:
        if t not in r_ew:
            continue
        for s, w in pesos.items():
            p0 = P.O[s, t] if P.act[s, t] else P.pval(s, t - 1)
            p1 = P.O[s, t + 7] if t + 7 < P.D and P.act[s, t + 7] else P.pval(s, min(t + 6, P.D - 1))
            if p0 and np.isfinite(p0) and np.isfinite(p1):
                aporte[s] = aporte.get(s, 0.0) + w * ((p1 / p0 - 1) - r_ew[t])
    return aporte


def exceso(sim, sim_ew):
    ev = sim["evaluable"] & sim_ew["evaluable"]
    return (sim["r"] - sim_ew["r"])[ev]


def intervalos(e, inferencia):
    """Los tres métodos de la regla del máximo; IC90 = envolvente (Enmienda 2, E2.2)."""
    b13 = inferencia.bootstrap_t(e, ell=13, B=9999, semilla=SEMILLA_H2)
    b26 = inferencia.bootstrap_t(e, ell=26, B=9999, semilla=SEMILLA_H2)
    nw = inferencia.newey_west(e, L=13)
    ic90 = (min(b13["ic90"][0], b26["ic90"][0], nw["ic90"][0]), max(b13["ic90"][1], b26["ic90"][1], nw["ic90"][1]))
    return b13, b26, nw, ic90


def p_h2(e, inferencia):
    b13, b26, nw, ic90 = intervalos(e, inferencia)
    p = max(b13["p_unilateral"], b26["p_unilateral"], nw["p_unilateral"])
    return {"p": p, "p_boot13": b13["p_unilateral"], "p_boot26": b26["p_unilateral"], "p_nw13": nw["p_unilateral"],
            "media_semanal": float(e.mean()), "anual": 52 * float(e.mean()), "ic90_semanal": ic90,
            "ic90_anual": (52 * ic90[0], 52 * ic90[1]), "n": int(e.size)}


def tercios(x):
    k = len(x) // 3
    return [x[:k], x[k:2 * k], x[2 * k:]]


def metricas(r):
    """Descriptivo §6.2 sobre retornos semanales (semanas evaluables)."""
    r = np.asarray(r, dtype=float)
    if r.size < 2:
        return None
    W = np.cumprod(1 + r)
    dd = W / np.maximum.accumulate(W) - 1
    bajo, racha = 0, 0
    for x in dd:
        racha = racha + 1 if x < 0 else 0
        bajo = max(bajo, racha)
    sd = float(np.std(r, ddof=1))
    neg = r[r < 0]
    cola = np.sort(r)[:max(1, int(math.ceil(0.05 * r.size)))]
    return {"semanas": int(r.size), "cagr": float(W[-1] ** (52 / r.size) - 1), "vol_anual": sd * math.sqrt(52),
            "sharpe_anual": float(r.mean() / sd * math.sqrt(52)) if sd > 0 else None,
            "sortino_anual": float(r.mean() / np.sqrt(np.mean(np.minimum(r, 0) ** 2)) * math.sqrt(52)) if neg.size else None,
            "caida_maxima": float(dd.min()), "cvar5_semanal": float(cola.mean()), "peor_semana": float(r.min()),
            "semanas_bajo_el_agua_max": bajo}


def sharpe_deflactado(e, sharpes):
    """N18 (Bailey y López de Prado, 2014): N = 20 configuraciones; V[SR] de los Sharpe semanales de sus excesos."""
    e = np.asarray(e, dtype=float)
    n, sr = e.size, float(e.mean() / e.std(ddof=1))
    g3 = float(np.mean((e - e.mean()) ** 3) / e.std() ** 3)
    g4 = float(np.mean((e - e.mean()) ** 4) / e.std() ** 4)
    N, v = 20, float(np.var(sharpes, ddof=1))
    gamma = 0.5772156649015329
    sr0 = math.sqrt(v) * ((1 - gamma) * _N.inv_cdf(1 - 1 / N) + gamma * _N.inv_cdf(1 - 1 / (N * math.e)))
    den = math.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2, 1e-12))
    return {"sr_semanal": sr, "sr0_semanal": sr0, "N": N, "V_SR": v, "asimetria": g3, "curtosis": g4,
            "dsr": _N.cdf((sr - sr0) * math.sqrt(n - 1) / den), "configuraciones_en_V": len(sharpes)}


def precio_val(P, s, d):
    return P.O[s, d] if P.act[s, d] else P.pval(s, d - 1)


def exposicion_y_rotacion(P, sim, formaciones):
    """Exposición = Σ pesos tras operar; rotación de un sentido = ½ Σ |w_post − w_pre| (pre = post anterior con deriva)."""
    expo, rot, entradas = [], [], []
    prev, obj_prev = None, None
    objetivos = dict(sim["objetivos"])
    for j, (t, w) in enumerate(sim["pesos"][:-1]):
        if not w:
            prev = None
            continue
        expo.append(sum(w.values()))
        if prev is not None:
            t0, w0 = prev
            crec = {s: precio_val(P, s, t) / precio_val(P, s, t0) for s in w0}
            Wn = (1 - sum(w0.values())) + sum(w0[s] * crec[s] for s in w0)
            pre = {s: w0[s] * crec[s] / Wn for s in w0}
            rot.append(0.5 * sum(abs(w.get(s, 0.0) - pre.get(s, 0.0)) for s in set(w) | set(pre)))
        T = set(objetivos.get(t, []))
        if obj_prev is not None:
            entradas.append(len(T - obj_prev))
        prev, obj_prev = (t, w), T
    return {"exposicion_media": float(np.mean(expo)) if expo else None,
            "rotacion_semanal_media": float(np.mean(rot)) if rot else None,
            "rotacion_anual": 52 * float(np.mean(rot)) if rot else None,
            "entradas_por_semana": float(np.mean(entradas)) if entradas else None,
            "operaciones_estimadas": int(2 * sum(entradas))}


def diagnostico_6_4(P, formaciones, ic, cache, base, ew, e, ic_medio, universo):
    """§6.4: conteos y efecto de anular los aportes (operacionalización fijada en el encabezado)."""
    sin_obs = []
    for t, v, _, _ in ic:
        if not np.isfinite(v):
            continue
        U = cache.get((t, 30, (7, 14, 21, 28), frozenset())) or universo.universo(P, t)
        up = np.array(U["U_pred"])
        m = np.array([bool(P.act[s, t + 6]) for s in up])
        y = np.array([math.log(P.pval(s, t + 6) / P.C[s, t - 1]) for s in up[m]])
        sin_obs.append(universo.spearman(np.asarray(U["S"])[m], y))
    ic_sin = float(np.nanmean(sin_obs)) if sin_obs else float("nan")
    dias = list(formaciones)
    con_evento = np.zeros(len(dias) - 1, dtype=bool)
    for sim in (base, ew):
        for _, d, _ in sim["eventos"]["liquidaciones"]:
            j = np.searchsorted(dias, d, side="right") - 1
            if 0 <= j < con_evento.size:
                con_evento[j] = True
        for j, (t, w) in enumerate(sim["pesos"][:-1]):
            if any(t + 7 < P.D and not P.act[s, t + 7] for s in w):
                con_evento[j] = True
    ev = base["evaluable"] & ew["evaluable"]
    e_sin = (base["r"] - ew["r"])[ev & ~con_evento]
    e_sin_media = float(e_sin.mean()) if e_sin.size else float("nan")
    return {"liquidaciones_estrategia": len(base["eventos"]["liquidaciones"]),
            "liquidaciones_ew": len(ew["eventos"]["liquidaciones"]),
            "marcas_obsoletas_H1": int(sum(x[3] for x in ic)),
            "compras_omitidas": base["eventos"]["compras_omitidas"], "ventas_diferidas": base["eventos"]["ventas_diferidas"],
            "ic_medio_sin_marcas_obsoletas": ic_sin, "semanas_h2_con_evento": int((ev & con_evento).sum()),
            "exceso_medio_sin_semanas_con_evento": e_sin_media,
            "etiqueta_dependiente": bool(np.sign(ic_sin) != np.sign(ic_medio) or np.sign(e_sin_media) != np.sign(e.mean()))}


def ejecutar(P, formaciones, universo, motor, inferencia, replicas_R5=2000, diag_B=999, cache=None,
             formaciones_miercoles=None, btc="BTCUSDT"):
    cache = {} if cache is None else cache
    Cfg = motor.Config
    base = motor.simular(P, formaciones, Cfg(), cache, registrar_pesos=True)
    ew = motor.simular(P, formaciones, Cfg(objetivo="ew"), cache, registrar_pesos=True)
    ic = motor.ic_semanal(P, formaciones, cache)
    serie_ic = np.array([x[1] for x in ic if np.isfinite(x[1])])
    h1 = inferencia.newey_west(serie_ic, L=4)
    e = exceso(base, ew)
    h2 = p_h2(e, inferencia)
    holm = inferencia.holm_dos(h1["p_unilateral"], h2["p"])
    rech1, rech2 = holm["rechaza"]["H1"], holm["rechaza"]["H2"]

    # §6.1 y §6.2
    if rech1:
        c1 = "INFORMACION CONFIRMADA" + (" · relevancia demostrada" if h1["ic90"][0] >= DELTA_IC else " · relevancia no demostrada")
    elif h1["ic90"][1] < DELTA_IC:
        c1 = "EN CONTRA (no relevancia)"
    else:
        c1 = "INSUFICIENTE"
    c2 = "VENTAJA NETA DE SELECCION" if rech2 else ("EN CONTRA (economico)" if h2["ic90_semanal"][1] < 0 else "INSUFICIENTE")

    # §6.3 robustez (siempre se calcula y se informa)
    excesos = {}

    def exc(nombre, cfg_kw, cfg_ew=None, F=None):
        F = formaciones if F is None else F
        s = motor.simular(P, F, Cfg(**cfg_kw), cache)
        b = motor.simular(P, F, Cfg(objetivo="ew", **(cfg_kw if cfg_ew is None else cfg_ew)), cache)
        excesos[nombre] = (exceso(s, b), s)
        return float(excesos[nombre][0].mean())

    bruto_s = motor.simular(P, formaciones, Cfg(mult_costo=0.0), cache)
    bruto_ew = motor.simular(P, formaciones, Cfg(objetivo="ew", mult_costo=0.0), cache)
    aporte = contribuciones(P, base, formaciones, bruto_ew)  # N14: r_EW bruto (v1 usaba el neto)
    mayor = max(aporte, key=lambda s: aporte[s]) if aporte else None
    rob = {
        "R1_costos_x2": exc("R1", {"mult_costo": 2.0}),
        "R2_un_dia_despues": exc("R2", {"demora": 1}),
        "R3_tercios_ic_pos": sum(float(np.mean(x)) > 0 for x in tercios(serie_ic)),
        "R3_tercios_exceso_pos": sum(float(np.mean(x)) > 0 for x in tercios(e)),
        "R4_sin_mayor_aporte": (P.sym[mayor] if mayor is not None else None),
        "R4_exceso": exc("R4", {"excluidos": frozenset({P.sym[mayor]})}) if mayor is not None else float("nan"),
        "R6_liquidaciones_menos_30": exc("R6", {"recorte_liq": 0.70}),
    }
    excesos["bruto"] = (exceso(bruto_s, bruto_ew), bruto_s)
    exc_bruto = float(excesos["bruto"][0].mean())
    nulos, rech_diag = [], 0
    for b in range(replicas_R5):
        s = motor.simular(P, formaciones, Cfg(objetivo="aleatorio", mult_costo=0.0, semilla_aleatoria=SEMILLA_R5 + b), cache)
        x = exceso(s, bruto_ew)
        nulos.append(float(x.mean()))
        rech_diag += inferencia.bootstrap_t(x, ell=13, B=diag_B, semilla=SEMILLA_DIAG)["p_unilateral"] <= 0.05
    p_nulo = (1 + sum(v >= exc_bruto for v in nulos)) / (replicas_R5 + 1)
    rob["R5_exceso_bruto"] = exc_bruto
    rob["R5_p_nulo"] = p_nulo
    rob["diag_5_4_tasa_rechazo"] = rech_diag / replicas_R5 if replicas_R5 else float("nan")
    robusta = (rob["R1_costos_x2"] > 0 and rob["R2_un_dia_despues"] > 0 and rob["R3_tercios_ic_pos"] >= 2
               and rob["R3_tercios_exceso_pos"] >= 2 and rob["R4_exceso"] > 0 and p_nulo <= 0.05
               and rob["R6_liquidaciones_menos_30"] > 0)

    # §6.5
    if rech1 and rech2:
        clase = "RESPALDADA HISTORICAMENTE" if robusta else "VENTAJA NO ROBUSTA"
    elif rech1:
        clase = "INFORMACION SIN VENTAJA OPERABLE"
    elif rech2:
        clase = "NO CONCLUYENTE (H2 sin H1)"
    elif c1.startswith("EN CONTRA"):
        clase = "EN CONTRA"
    else:
        clase = "INSUFICIENTE"

    # Descriptivo prescripto: grilla de sensibilidad (N17), 15 configuraciones; la base es k = 6, N = 30
    grilla = {}
    for k in (4, 6, 10):
        for n in (20, 30, 50):
            nombre = f"k{k}_N{n}"
            if (k, n) == (6, 30):
                excesos[nombre] = (e, base)
            else:
                exc(nombre, {"k": k, "banda": 2 * k, "N_inv": n}, {"N_inv": n})
    for h in (7, 14, 21, 28):
        exc(f"h{h}", {"horizontes": (h,)}, {})
    exc("sin_banda", {"banda": 6})
    if formaciones_miercoles is not None:
        exc("miercoles", {}, {}, formaciones_miercoles)
    for nombre in [x for x in excesos if x not in ("R1", "R2", "R4", "R6", "bruto")]:
        x, s = excesos[nombre]
        grilla[nombre] = {"exceso_anual": 52 * float(x.mean()), "sharpe_exceso_anual": float(x.mean() / x.std(ddof=1) * math.sqrt(52)),
                          "sharpe_cartera_anual": (metricas(s["r"][s["evaluable"]]) or {}).get("sharpe_anual")}
    sharpes = [float(x.mean() / x.std(ddof=1)) for x, _ in excesos.values()]

    # Descriptivo frente a BTC y al efectivo (§6.2), estabilidad por año, exposición y rotación
    ev = base["evaluable"] & ew["evaluable"]
    frente_btc = None
    if btc in P.sym:
        sb = P.sym.index(btc)
        precios = np.array([precio_val(P, sb, t) for t in formaciones])
        r_btc = precios[1:] / precios[:-1] - 1
        e_btc = (base["r"] - r_btc)[ev]
        _, _, _, ic90_btc = intervalos(e_btc, inferencia)
        rb = r_btc[ev]
        rs = base["r"][ev]
        frente_btc = {"exceso_anual": 52 * float(e_btc.mean()), "ic90_anual": (52 * ic90_btc[0], 52 * ic90_btc[1]),
                      "beta": float(np.cov(rs, rb)[0, 1] / np.var(rb, ddof=1)), "correlacion": float(np.corrcoef(rs, rb)[0, 1]),
                      "btc_comprar_y_mantener": metricas(rb)}
    anios = {}
    fechas = [universo.INICIO + dt.timedelta(days=t) for t in formaciones[:-1]]
    for (t, v, _, _), f in zip(ic, fechas, strict=False):
        if np.isfinite(v):
            anios.setdefault(f.year, {"ic": [], "exceso": []})["ic"].append(v)
    for j, f in enumerate(fechas):
        if ev[j]:
            anios.setdefault(f.year, {"ic": [], "exceso": []})["exceso"].append(float(base["r"][j] - ew["r"][j]))
    por_anio = {y: {"semanas": len(v["exceso"]), "ic_medio": float(np.mean(v["ic"])) if v["ic"] else None,
                    "exceso_anual": 52 * float(np.mean(v["exceso"])) if v["exceso"] else None} for y, v in sorted(anios.items())}

    return {
        "semanas_ic": int(serie_ic.size), "semanas_h2": h2["n"],
        "H1": {"ic_medio": h1["media"], "ee_nw": h1["ee"], "z": h1["z"], "p1": h1["p_unilateral"], "ic90": h1["ic90"],
               "clasificacion_6_1": c1},
        "H2": {**h2, "clasificacion_6_2": c2},
        "holm": holm, "robustez": rob, "robusta": robusta, "clasificacion_6_5": clase,
        "diagnostico_6_4": diagnostico_6_4(P, formaciones, ic, cache, base, ew, e, h1["media"], universo),
        "descriptivo": {"estrategia": metricas(base["r"][base["evaluable"]]), "ew_u30": metricas(ew["r"][ew["evaluable"]]),
                        "frente_a_btc": frente_btc, "frente_al_efectivo": metricas(base["r"][ev]),
                        "costos": {"x0": 52 * exc_bruto, "x1": h2["anual"], "x2": 52 * rob["R1_costos_x2"]},
                        "exposicion_y_rotacion": exposicion_y_rotacion(P, base, formaciones),
                        "por_anio": por_anio, "grilla_sensibilidad": grilla,
                        "sharpe_deflactado": sharpe_deflactado(e, sharpes),
                        "exceso_timing_T": "NO CALCULADO: T no se reabre (regla vigente)"},
        "nota": "Ninguna clasificación autoriza capital (v3 §6.5). Evidencia histórica con contaminación declarada (v3 §1).",
    }


# ------------------------------------------------------------------ modos

def modo_sintetico(salida: Path, momentum: float, replicas: int, e3: Path = E3_DEFECTO):
    universo, motor, inferencia = importar_congelados(e3)
    if sha(e3 / "codigo" / "pruebas_motor.py") != PRUEBAS_MOTOR:
        raise SystemExit("pruebas_motor.py no coincide con su huella")
    import pruebas_motor
    P = pruebas_motor.panel_sintetico(20261026, momentum=momentum)
    F = pruebas_motor.formaciones()
    validez, cache = validez_previa(P, F, universo, motor)
    Fm = universo.lunes(dt.date(2018, 9, 3), dt.date(2020, 12, 23), dia_semana=2)
    res = ejecutar(P, F, universo, motor, inferencia, replicas_R5=replicas, diag_B=199, cache=cache,
                   formaciones_miercoles=Fm, btc="C00USDT")
    res["validez_previa"] = validez
    salida.mkdir(parents=True, exist_ok=True)
    (salida / f"sintetico_momentum_{momentum}.json").write_text(json.dumps(res, indent=1, default=float, ensure_ascii=False))
    print(json.dumps({"validez": {k: validez[k] for k in ("semanas", "evaluables", "invariancia_ok", "bloqueo_fechas")},
                      **{k: res[k] for k in ("semanas_ic", "H1", "clasificacion_6_5")}}, default=float, ensure_ascii=False))


def resultado_invalido(salida: Path, motivo: str, **extra):
    """C5: INVÁLIDO como resultado explícito, sin H1 ni H2."""
    res = {"veredicto": "INVALIDO", "motivo": motivo, "H1": None, "H2": None, **extra,
           "nota": "E3-H1/H2 NO EVALUABLES con esta ventana. No se busca otra ventana ni se cambia ninguna regla."}
    (salida / "RESULTADO_E3.json").write_text(json.dumps(res, indent=1, default=float, ensure_ascii=False))
    raise SystemExit(f"INVALIDO: {motivo}. Ver {salida / 'RESULTADO_E3.json'}")


def modo_real(e3: Path, ventana: Path, autorizacion: Path, salida: Path, manifiesto: Path = None):
    if salida.exists():
        raise SystemExit(f"{salida} ya existe: la ejecución confirmatoria es única")
    manifiesto = Path(manifiesto or MANIFIESTO)
    texto = autorizacion.read_text() if autorizacion.exists() else ""
    requeridos = {"FRASE": FRASE in texto, "orquestador_v2": sha(Path(__file__)) in texto,
                  "entradas_congeladas": manifiesto.exists() and sha(manifiesto) in texto}
    if not all(requeridos.values()):
        raise SystemExit(f"autorización ausente o incompleta: {requeridos}. No se lee ningún precio.")
    entradas = verificar_entradas(e3, ventana, manifiesto)  # C3: antes de leer cualquier precio
    vd = json.loads(ventana.read_text())
    salida.mkdir(parents=True)
    registro = {"inicio_utc": dt.datetime.now(dt.UTC).isoformat(), "ventana": str(ventana), "sha_ventana": sha(ventana),
                "sha_orquestador": sha(Path(__file__)), "sha_autorizacion": sha(autorizacion), "entradas": entradas,
                "inicio_H": vd.get("inicio_H")}
    (salida / "REGISTRO_EJECUCION.json").write_text(json.dumps(registro, indent=1))  # antes de calcular
    if vd.get("veredicto") != "VALIDO" or vd.get("inicio_H") != entradas["inicio_H_esperado"]:
        resultado_invalido(salida, "la ventana A no es VÁLIDA o no es la congelada", ventana=vd.get("veredicto"))
    universo, motor, inferencia = importar_congelados(e3)
    mapeos = json.loads((AQUI.parent / entradas["mapeos"]).read_text())["mapeos"]
    P, registro_mapeos = panel_real(e3, universo, mapeos)
    inicio = dt.date.fromisoformat(vd["inicio_H"])
    formaciones = universo.lunes(inicio, ULTIMA_FORMACION + dt.timedelta(days=7))
    validez, cache = validez_previa(P, formaciones, universo, motor)
    (salida / "VALIDEZ_PREVIA.json").write_text(json.dumps({**validez, "mapeos_aplicados": registro_mapeos}, indent=1, default=float))
    if not validez["valido"]:
        resultado_invalido(salida, "validez previa (v3 §10)", validez_previa=validez)
    Fm = universo.lunes(inicio, ULTIMA_FORMACION + dt.timedelta(days=9), dia_semana=2)
    res = ejecutar(P, formaciones, universo, motor, inferencia, cache=cache, formaciones_miercoles=Fm)
    res["veredicto"] = "EVALUADO"
    res["validez_previa"] = validez
    res["mapeos_aplicados"] = registro_mapeos
    res["registro"] = registro
    (salida / "RESULTADO_E3.json").write_text(json.dumps(res, indent=1, default=float, ensure_ascii=False))
    print(json.dumps({k: res[k] for k in ("semanas_ic", "H1", "H2", "holm", "clasificacion_6_5")}, default=float,
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "sintetico":
        modo_sintetico(Path(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 50,
                       Path(sys.argv[5]) if len(sys.argv) > 5 else E3_DEFECTO)
    elif sys.argv[1] == "real":
        modo_real(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5]))
    else:
        raise SystemExit(__doc__)
