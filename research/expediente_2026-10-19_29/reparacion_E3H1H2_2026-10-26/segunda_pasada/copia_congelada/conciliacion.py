"""E3 · F3: conciliación de supervivencia (v3 §2.3, §4.11; N6, N7; Adenda 3). Sin retornos: no importa motor.py ni usa precios.

Uso: python -I conciliacion.py <dir_calidad> <dir_anuncios> <dir_listados_vision> <estructural.json> <salida_dir> [resoluciones.json]
"""
import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

import numpy as np

INICIO = dt.date(2017, 7, 1)
U_INI, U_FIN = dt.date(2018, 1, 1), dt.date(2026, 5, 31)
FIN_H = dt.date(2026, 5, 18)
COTIZ = ("USDT", "BTC", "ETH", "BNB", "BUSD", "TUSD", "USDC", "PAX", "USDS", "FDUSD", "TRY", "EUR", "GBP", "AUD", "BRL", "RUB", "XRP",
         "TRX", "DAI", "IDRT", "BIDR", "UAH", "NGN", "ZAR", "BKRW", "VAI", "USDP", "DOGE", "JPY", "PLN", "RON", "ARS", "MXN", "COP", "CZK")
PAR_TXT = re.compile(r"\b([A-Z0-9]{2,15})\s*/\s*USDT\b|\b([A-Z0-9]{2,15})USDT\b")


def i_(d):
    return (d - INICIO).days


def f_(i):
    return INICIO + dt.timedelta(days=int(i))


def iso(s):
    return dt.date.fromisoformat(s) if s else None


def lunes_desde(d):
    return d + dt.timedelta(days=(0 - d.weekday()) % 7)


def cargar_actividad(dir_calidad: Path):
    act = {}
    v5 = 0
    for f in sorted((dir_calidad / "series").glob("*.npz")):
        z = np.load(f)
        e, nt = z["estado"], z["NT"]
        v5 += int(((e == 1) & (nt <= 0)).sum())
        act[str(z["simbolo"])] = np.flatnonzero(e == 1)
    return act, v5


def inicios_listado(a):
    if a.size == 0:
        return []
    return [int(a[0])] + [int(a[k]) for k in range(1, a.size) if a[k] - a[k - 1] - 1 >= 30]


def clasificar(par, E, act, meses, usdt, sin_fecha=False):
    """N6 (o A3.4 si sin_fecha, con E = R)."""
    if par not in usdt:
        return "D", None
    a = act.get(par, np.array([], dtype=np.int64))
    iE = i_(E)
    lim = iE + 61 if sin_fecha else iE + 1
    c_lo, c_hi = (iE + 61, iE + 90) if sin_fecha else (iE + 1, iE + 30)
    if np.any((a > c_lo) & (a <= c_hi)):
        return "C", None
    prev = a[a <= lim]
    if prev.size == 0:
        return "D", None
    L = int(prev[-1])
    if L >= iE - 7:
        return "A", f_(L).isoformat()
    m0, m1 = f_(L).strftime("%Y-%m"), min(E, U_FIN).strftime("%Y-%m")
    y, m = int(m0[:4]), int(m0[5:])
    faltan = []
    while f"{y:04d}-{m:02d}" <= m1:
        if f"{y:04d}-{m:02d}" not in meses.get(par, set()):
            faltan.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return ("T" if faltan else "B"), f_(L).isoformat()


def main(dir_calidad, dir_anuncios, dir_listados, estructural, salida, resol_path=None):
    salida.mkdir(parents=True, exist_ok=True)
    R = json.loads(resol_path.read_text()) if resol_path else {}
    R_ev, R_sf, R_tok = R.get("eventos", {}), R.get("sin_fecha", {}), R.get("tokens_sin_par", {})
    R_ren, R_vs2, R_vs3 = R.get("renombres", []), R.get("vs2", {}), R.get("vs3", {})
    usdt = set(json.loads((dir_listados / "simbolos_usdt.json").read_text()))
    todos_sym = set(json.loads((dir_listados / "simbolos_todos.json").read_text()))
    aud = {a["simbolo"]: a for a in json.loads((dir_calidad / "auditoria_por_simbolo.json").read_text())}
    meses = {s: set(a.get("meses_con_archivo", [])) for s, a in aud.items()}
    act, v5 = cargar_actividad(dir_calidad)
    exc = json.loads((dir_anuncios / "exclusiones_usdt.json").read_text())
    lis = json.loads((dir_anuncios / "listados_usdt.json").read_text())
    cor = json.loads((dir_anuncios / "correcciones.json").read_text())
    ren = json.loads((dir_anuncios / "renombres_candidatos.json").read_text())
    clasif = json.loads((dir_anuncios / "anuncios_clasificados.json").read_text())
    cuerpo_por_url = {c["url"]: c.get("cuerpo", "") for c in clasif}
    # Evidencia documental de pares USDT (A3.3.1): cualquier mención en cualquier página archivada, o un listado
    evid = collections.defaultdict(set)
    for f in sorted((dir_anuncios / "paginas").glob("*.json")):
        p = json.loads(f.read_text())
        for m in PAR_TXT.finditer(p.get("texto", "")):
            evid[(m.group(1) or m.group(2)) + "USDT"].add(p["url"])
    for l in lis:
        evid[l["par"]].add(l["url"])

    # 1) Filas → eventos (A3.2)
    fuera, revisar_sin_par, sin_fecha_filas, filas = [], [], [], []
    for r in exc:
        if r["par"] is None:
            (fuera if r["texto_lista_pares"] else revisar_sin_par).append(r)
            continue
        E = iso(r["fecha_efectiva"])
        if E is None:
            k = f"{r['par']}|{r['url']}"
            if k in R_sf and R_sf[k].get("E"):
                E, r = iso(R_sf[k]["E"]), {**r, "origen_fecha": "manual", "cita": R_sf[k].get("cita")}
            else:
                sin_fecha_filas.append(r)
                continue
        filas.append({**r, "E": E})
    eventos = []
    por_par = collections.defaultdict(list)
    for r in filas:
        por_par[r["par"]].append(r)
    for par, g in sorted(por_par.items()):
        g.sort(key=lambda r: (r["E"], r["url"]))
        actual = [g[0]]
        for r in g[1:]:
            if (r["E"] - actual[-1]["E"]).days <= 3:
                actual.append(r)
            else:
                eventos.append(actual)
                actual = [r]
        eventos.append(actual)
    ev = []
    for g in eventos:
        tit = [r for r in g if r["origen_fecha"] == "titulo"]
        E = tit[0]["E"] if tit else min(r["E"] for r in g)
        ev.append({"par": g[0]["par"], "E": E, "urls": sorted({r["url"] for r in g}), "titulos": sorted({r["titulo"] for r in g}),
                   "subtipos": sorted({r["subtipo"] for r in g}), "par_en_texto": any(r["par_en_texto"] for r in g),
                   "tokens": sorted({t for r in g for t in r["tokens"]}), "url_archivada": g[0]["url_archivada"], "sin_fecha": False})
    # Filas sin fecha (A3.4): R = publicación o captura
    for r in sin_fecha_filas:
        Rf = iso(r["publicado"]) or dt.datetime.strptime(r["captura"][:8], "%Y%m%d").date()
        ev.append({"par": r["par"], "E": Rf, "urls": [r["url"]], "titulos": [r["titulo"]], "subtipos": [r["subtipo"]],
                   "par_en_texto": r["par_en_texto"], "tokens": r["tokens"], "url_archivada": r["url_archivada"], "sin_fecha": True})
    universo_ev = [e for e in ev if U_INI <= e["E"] <= U_FIN]

    # 2) Clasificación N6 + A3.3 + A3.5
    revisar = {"C": [], "D_sin_evidencia_ni_otro_par": [], "sin_fecha": [], "sin_par": revisar_sin_par}
    sin_par_documentado = []
    for e in universo_ev:
        e["clave"] = f"{e['par']}|{e['E'].isoformat()}" + ("|sin_fecha" if e["sin_fecha"] else "")
        cat, L = clasificar(e["par"], e["E"], act, meses, usdt, e["sin_fecha"])
        e["categoria_auto"], e["L"] = cat, L
        nota = None
        if cat == "D" and e["par"] not in usdt and not e["par_en_texto"] and "exclusion_token" in e["subtipos"]:
            base = e["par"][:-4]
            otros = sorted(s for s in todos_sym if s != e["par"] and any(s == base + q for q in COTIZ))
            if evid.get(e["par"]):
                nota = {"A3.3": 1, "evidencia": sorted(evid[e["par"]])[:5]}
            elif otros:
                nota = {"A3.3": 2, "otros_pares_en_bucket": otros}
                cat = "fuera_sin_par_usdt_documentado"
            else:
                nota = {"A3.3": 3}
                tk = R_tok.get(base)
                if tk:
                    cat = "D" if tk["accion"] == "D" else "descartado"
                    nota["manual"] = tk
                else:
                    revisar["D_sin_evidencia_ni_otro_par"].append(e)
        e["nota"] = nota
        m = R_ev.get(e["clave"])
        if m:
            e["manual"] = m
            if m["accion"] == "fecha_corregida":
                e["E_original"], e["E"] = e["E"].isoformat(), iso(m["E"])
                cat, e["L"] = clasificar(e["par"], e["E"], act, meses, usdt, False)
            elif m["accion"] == "C_explicada":
                cat = "C_explicada"
            elif m["accion"] == "descartar":
                cat = "descartado"
            elif m["accion"] == "confirmar":
                pass
        if cat == "C":
            if m is None:
                revisar["C"].append(e)
            cat = "C_no_explicada"
        if e["sin_fecha"] and m is None:
            revisar["sin_fecha"].append(e)
        e["categoria"] = cat
        if cat == "fuera_sin_par_usdt_documentado":
            sin_par_documentado.append(e)
    en_u = [e for e in universo_ev if e["categoria"] not in ("fuera_sin_par_usdt_documentado", "descartado")]
    FALLAS = ("T", "D", "C_no_explicada")
    por_anio = {}
    for y in range(2018, 2027):
        g = [e for e in en_u if e["E"].year == y]
        cnt = collections.Counter(e["categoria"] for e in g)
        tot = len(g)
        por_anio[y] = {"total": tot, **{k: cnt.get(k, 0) for k in ("A", "B", "T", "C_explicada", "C_no_explicada", "D")},
                       "E_sin_fecha": sum(1 for e in g if e["sin_fecha"]),
                       "cobertura_conservadora_AB": (cnt.get("A", 0) + cnt.get("B", 0)) / tot if tot else None,
                       "fallas": sum(cnt.get(k, 0) for k in FALLAS)}

    # 3) Salidas observadas (N7, A3.7)
    pag_exc = [c for c in clasif if c["tipo"] == "exclusion"]
    renom = {(r["viejo"]): r for r in R_ren}
    salidas = []
    for s, a in aud.items():
        for ini, fin in a.get("episodios", []):
            L = iso(fin)
            if L > dt.date(2026, 5, 1):
                continue
            lo, hi = L - dt.timedelta(days=1), L + dt.timedelta(days=365)
            base = s[:-4]
            motivo = None
            r = renom.get(s)
            if r and lo <= iso(r["E"]) <= hi:
                motivo = "renombre_mapeado"
            elif any(e["par"] == s and lo <= e["E"] <= hi for e in ev):
                motivo = "evento_del_par"
            else:
                for c in pag_exc:
                    fe = iso(c.get("fecha_efectiva"))
                    if base in c.get("tokens", []) and fe and lo <= fe <= hi:
                        motivo = "exclusion_del_token"
                        break
            salidas.append({"simbolo": s, "ultimo_activo": fin, "motivo": motivo})
    sal_anio = {}
    for y in range(2017, 2027):
        g = [x for x in salidas if x["ultimo_activo"][:4] == str(y) and x["motivo"] != "renombre_mapeado"]
        sin = sum(1 for x in g if x["motivo"] is None)
        sal_anio[y] = {"observadas": len(g), "con_anuncio": len(g) - sin, "sin_anuncio": sin,
                       "frac_sin_anuncio": sin / len(g) if g else None}

    # 4) Inicio de H (A3.8)
    est = json.loads(estructural.read_text())
    comp = {"i": iso(est["inicio_componente_i_13_semanas_evaluables"])}
    fallas = [e for e in en_u if e["categoria"] in FALLAS]
    comp["ii"] = (max(e["E"] for e in fallas) + dt.timedelta(days=1)) if fallas else None
    comp["iii"] = dt.date(min(e["E"] for e in en_u).year, 1, 1) if en_u else None
    Y = None
    for y0 in range(2018, 2027):
        if all(sal_anio[y]["frac_sin_anuncio"] is None or sal_anio[y]["frac_sin_anuncio"] <= 0.10 for y in range(y0, 2027)):
            Y = y0
            break
    comp["iv"] = dt.date(Y, 1, 1) if Y else None
    if any(v is None for k, v in comp.items() if k != "ii") or comp["iii"] is None:
        inicio = None
    else:
        inicio = lunes_desde(max(v for v in comp.values() if v is not None))
    semanas = [w for w in est["semanas"] if inicio and inicio.isoformat() <= w["lunes"] <= FIN_H.isoformat()]
    n_ev = sum(w["evaluable"] for w in semanas)
    pct_no = 100 * (1 - n_ev / len(semanas)) if semanas else None
    invalido = inicio is None or n_ev < 156 or (pct_no is not None and pct_no > 20)

    # 5) V-S2 (A3.6)
    vis = {}
    for l in lis:
        A = iso(l["fecha_apertura"])
        if A and U_INI <= A <= U_FIN:
            vis.setdefault((l["par"], A.isoformat()), l)
    claves = sorted(vis.keys(), key=lambda k: (k[0], k[1], vis[k]["url"]))
    sel = sorted(np.random.default_rng(20261025).choice(len(claves), min(len(claves), 50), replace=False).tolist()) if claves else []
    vs2 = []
    for j in sel:
        par, A = claves[j]
        k = f"{par}|{A}"
        A_uso = iso(R_vs2.get(k, {}).get("fecha_corregida")) or iso(A)
        par_uso = R_vs2.get(k, {}).get("par_corregido") or par
        ok = par_uso in usdt and any(abs(st - i_(A_uso)) <= 3 for st in inicios_listado(act.get(par_uso, np.array([], dtype=np.int64))))
        sts = [f_(x).isoformat() for x in inicios_listado(act.get(par_uso, np.array([], dtype=np.int64)))]
        vs2.append({"clave": k, "par": par_uso, "A": A_uso.isoformat(), "acierto": bool(ok), "inicios_listado": sts[:6],
                    "url": vis[(par, A)]["url"], "titulo": vis[(par, A)]["titulo"], "manual": R_vs2.get(k)})
    vs2_tasa = sum(x["acierto"] for x in vs2) / len(vs2) if vs2 else None

    # 6) V-S3 (A3.6)
    claves_u = sorted(en_u, key=lambda e: (e["par"], e["E"], e["urls"][0]))
    sel3 = sorted(np.random.default_rng(20261026).choice(len(claves_u), min(len(claves_u), 10), replace=False).tolist()) if claves_u else []
    vs3 = [{"clave": claves_u[j]["clave"], "par": claves_u[j]["par"], "E": claves_u[j]["E"].isoformat(), "categoria": claves_u[j]["categoria"],
            "L": claves_u[j]["L"], "urls": claves_u[j]["urls"], "titulos": claves_u[j]["titulos"], "revision": R_vs3.get(claves_u[j]["clave"]),
            "cuerpo": cuerpo_por_url.get(claves_u[j]["urls"][0], "")[:2500]} for j in sel3]

    def ser(e):
        return {k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in e.items()}
    res = {
        "eventos_total": len(ev), "eventos_en_universo": len(en_u), "fuera_por_texto_sin_usdt": len(fuera),
        "fuera_sin_par_usdt_documentado": len(sin_par_documentado),
        "descartados": sum(1 for e in universo_ev if e["categoria"] == "descartado"),
        "por_anio": por_anio, "salidas_por_anio": sal_anio,
        "salidas_renombre_mapeado": sum(1 for x in salidas if x["motivo"] == "renombre_mapeado"),
        "primer_evento": min(e["E"] for e in en_u).isoformat() if en_u else None,
        "ultima_falla": ser(max(fallas, key=lambda e: e["E"])) if fallas else None,
        "componentes_inicio": {k: (v.isoformat() if v else None) for k, v in comp.items()},
        "inicio_H": inicio.isoformat() if inicio else None, "semanas_H": len(semanas), "evaluables_H": n_ev,
        "pct_no_evaluables_H": pct_no, "INVALIDO": invalido,
        "V_S2": {"n": len(vs2), "aciertos": sum(x["acierto"] for x in vs2), "tasa": vs2_tasa, "cumple": vs2_tasa is not None and vs2_tasa >= 0.95},
        "V_S3_revisados": sum(1 for x in vs3 if x["revision"]), "V_S4": "NO EJECUTADO (HTTP 451; Adenda 3, A3.9)",
        "V_S5_dias_activos_con_0_operaciones": v5,
        "pendiente_revision_manual": {k: len(v) for k, v in revisar.items()},
        "resoluciones_manuales_usadas": bool(resol_path),
    }
    (salida / "conciliacion.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    (salida / "eventos.json").write_text(json.dumps([ser(e) for e in sorted(universo_ev, key=lambda e: (e["E"], e["par"]))], ensure_ascii=False, indent=0))
    (salida / "salidas.json").write_text(json.dumps(salidas, ensure_ascii=False, indent=0))
    (salida / "fuera_del_universo.json").write_text(json.dumps({"texto_lista_pares_sin_usdt": fuera, "sin_par_usdt_documentado": [ser(e) for e in sin_par_documentado]}, ensure_ascii=False, indent=0))
    (salida / "revision_manual.json").write_text(json.dumps({
        "C": [ser({**e, "cuerpo": cuerpo_por_url.get(e["urls"][0], "")[:2500]}) for e in revisar["C"]],
        "D_sin_evidencia_ni_otro_par": [ser({**e, "cuerpo": cuerpo_por_url.get(e["urls"][0], "")[:2500]}) for e in revisar["D_sin_evidencia_ni_otro_par"]],
        "sin_fecha": [ser({**e, "cuerpo": cuerpo_por_url.get(e["urls"][0], "")[:2500]}) for e in revisar["sin_fecha"]],
        "sin_par": revisar["sin_par"], "V_S2_desaciertos": [x for x in vs2 if not x["acierto"]], "V_S3": vs3,
        "renombres_candidatos": [{k: r.get(k) for k in ("url", "titulo", "publicado", "fecha", "tokens_titulo", "pares_usdt", "cuerpo")} for r in ren],
        "correcciones": cor}, ensure_ascii=False, indent=0))
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    a = sys.argv
    main(Path(a[1]), Path(a[2]), Path(a[3]), Path(a[4]), Path(a[5]), Path(a[6]) if len(a) > 6 else None)
