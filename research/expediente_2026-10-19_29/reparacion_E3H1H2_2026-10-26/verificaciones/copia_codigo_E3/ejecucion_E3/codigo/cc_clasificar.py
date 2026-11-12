"""E3 · A3: clasificación y extracción de anuncios archivados (Enmienda 2, E2.1; Adenda 3, A3.1). Reglas fijas; lo no resuelto queda «E».

Uso: python -I cc_clasificar.py <dir_anuncios> <simbolos_usdt.json>
Salida: anuncios_clasificados.json (todos), exclusiones_usdt.json (V-S1), listados_usdt.json (V-S2), renombres_candidatos.json,
correcciones.json, resumen_clasificacion.json.

El texto de cada página archivada incluye navegación y una barra lateral con títulos de otros anuncios. Solo se usa el CUERPO:
desde la última aparición del título hasta «Thanks for your support», «Binance Team», «Related Articles» o «Find us on Telegram».
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

MESES = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
NO_SPOT = re.compile(r"futures|margin|perpetual|options|earn\b|savings|convert\b|alpha|loan|lending|staking|launchpool|copy trading|"
                     r"trading bot|simple earn|dual investment|vip loan|nft|p2p|pay\b|card\b|fan token|mining pool|binance\.us|\btr\b|"
                     r"binance (?:turkey|australia|indonesia|thailand|japan)", re.I)
T_CORR = re.compile(r"postpone|cancel|reschedul|update[sd]? (?:on|regarding|to) .*delist|delay", re.I)
T_DELIST = re.compile(r"\bdelist|cease trading|removal of (?:spot )?trading pairs|remove (?:&|and )?cease|will remove .*trading pair|"
                      r"remove .*spot trading pairs", re.I)
T_REN = re.compile(r"rebrand|renam|token swap|redenominat|migration|contract swap|ticker change|token conversion|mainnet swap", re.I)
T_LIST = re.compile(r"will list|binance lists|\blists |adds? .*trading pair|opens? trading|new trading pairs|trading pairs added|"
                    r"will open trading", re.I)
FECHA = re.compile(r"(20[12]\d)[-/.](\d{1,2})[-/.](\d{1,2})")
FECHA_TXT = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20[12]\d)", re.I)
PAR = re.compile(r"\b([A-Z0-9]{2,15})\s*/\s*USDT\b")
PAR_CUALQ = re.compile(r"\b[A-Z0-9]{2,15}\s*/\s*(?:BTC|ETH|BNB|BUSD|USDT|TUSD|FDUSD|USDC|PAX|USDS|TRY|EUR|GBP|AUD|BRL|RUB|XRP|TRX|DAI|IDRT|BIDR|UAH|NGN|ZAR)\b")
TOK_PAR = re.compile(r"\(([A-Z0-9]{2,12})\)")
NO_TOKEN = {"UTC", "USD", "NFT", "API", "KYC", "VIP", "P2P", "ETF", "EEA", "UK", "EU", "FAQ", "AM", "PM", "OTC", "AMA", "DEX", "CEX"}
FIN_CUERPO = re.compile(r"Thanks for your support|Binance Team|Related Articles|Related articles|Find us on Telegram")
CABECERA = re.compile(r"^\s*Binance\s+((?:[A-Z][a-z]+ \d{1,2}, \d{4})|(?:\d{4}-\d{2}-\d{2}))(?: \d{1,2}:\d{2})?\s*(?:Follow)?\s*")


def fechas_en(texto):
    out = []
    for m in FECHA.finditer(texto):
        try:
            out.append((m.start(), dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))))
        except ValueError:
            pass
    for m in FECHA_TXT.finditer(texto):
        try:
            out.append((m.start(), dt.date(int(m.group(3)), MESES[m.group(1).lower()[:3]], int(m.group(2)))))
        except ValueError:
            pass
    return sorted(out)


def limpiar_titulo(t):
    return re.sub(r"\s*(?:\|\s*Binance Support|–\s*Binance(?: Support)?)\s*$", "", t).strip()


def cuerpo_de(titulo, texto):
    """Cuerpo del anuncio y fecha de publicación de la cabecera; (texto completo, None, False) si no se encuentra el título."""
    i = texto.rfind(titulo) if titulo else -1
    if i < 0:
        return texto, None, False
    resto = texto[i + len(titulo):]
    pub = None
    m = CABECERA.match(resto)
    if m:
        f = fechas_en(m.group(1))
        pub = f[0][1] if f else None
        resto = resto[m.end():]
    j = FIN_CUERPO.search(resto)
    return (resto[:j.start()] if j else resto[:20000]), pub, True


def fecha_publicacion(p, pub_cabecera):
    if p.get("publicado_ms"):
        v = int(p["publicado_ms"])
        return dt.datetime.fromtimestamp(v / (1000 if v > 10**11 else 1), dt.timezone.utc).date()
    if pub_cabecera:
        return pub_cabecera
    if p.get("time_datetime"):
        try:
            return dt.date.fromisoformat(p["time_datetime"][:10])
        except ValueError:
            pass
    return None


def fecha_efectiva(titulo, cuerpo, patron):
    """Primera fecha en el título; si no, la primera fecha en una oración del cuerpo que contiene el patrón y no habla de
    depósitos ni retiros."""
    ft = fechas_en(titulo)
    if ft:
        return ft[0][1], "titulo"
    for oracion in re.split(r"(?<=[.!?])\s+", cuerpo):
        if patron.search(oracion) and not re.search(r"withdraw|deposit", oracion, re.I):
            f = fechas_en(oracion)
            if f:
                return f[0][1], "cuerpo"
    return None, None


def tokens_titulo(titulo):
    toks = set(TOK_PAR.findall(titulo))
    m = re.search(r"(?:delist(?:s|ing)?|cease trading (?:on|of)?)\s+(?:of\s+)?(.+?)(?:\s+on\s+20|\s+-\s+20|\s+at\s+20|$)", titulo, re.I)
    if m:
        for x in re.split(r",|&|\band\b", m.group(1)):
            x = x.strip().strip(".")
            if re.fullmatch(r"[A-Z0-9]{2,12}", x):
                toks.add(x)
    return sorted(toks - NO_TOKEN)


def main(d: Path, simbolos_path: Path):
    usdt = set(json.loads(simbolos_path.read_text()))
    todos, exclusiones, listados, renombres, correcciones = [], [], [], [], []
    for f in sorted((d / "paginas").glob("*.json")):
        p = json.loads(f.read_text())
        tit = limpiar_titulo(p.get("titulo", ""))
        cuerpo, pub_cab, cuerpo_ok = cuerpo_de(tit, p.get("texto", ""))
        fpub = fecha_publicacion(p, pub_cab)
        spot = not NO_SPOT.search(tit)
        tipo = "otro"
        if spot and T_DELIST.search(tit) and T_CORR.search(tit):
            tipo = "correccion"
        elif spot and T_DELIST.search(tit):
            tipo = "exclusion"
        elif spot and T_REN.search(tit):
            tipo = "renombre"
        elif spot and T_LIST.search(tit):
            tipo = "listado"
        reg = {"archivo": f.name, "url": p["url"], "url_archivada": p.get("url_archivada"), "captura": p["captura"], "titulo": tit,
               "publicado": fpub.isoformat() if fpub else None, "tipo": tipo, "cuerpo_identificado": cuerpo_ok}
        if tipo == "exclusion":
            pares = sorted(set(PAR.findall(cuerpo)) | set(PAR.findall(tit)))
            toks = tokens_titulo(tit)
            lista_pares = bool(PAR_CUALQ.search(cuerpo))
            fe, origen = fecha_efectiva(tit, cuerpo, T_DELIST)
            es_par = bool(re.search(r"removal of|remove|trading pairs", tit, re.I)) and not re.search(r"\bdelist", tit, re.I)
            afectados, ambiguo, fuera = set(), [], []
            if es_par:
                afectados = {x + "USDT" for x in pares}
            else:
                for t in toks:
                    if lista_pares and t not in pares:
                        fuera.append(t)              # v3 §2.3: el texto lista los pares y USDT no está
                    else:
                        afectados.add(t + "USDT")
                afectados |= {x + "USDT" for x in pares}
                if not toks:
                    ambiguo.append("sin tokens en el título")
            if fe is None:
                ambiguo.append("sin fecha efectiva")
            if not cuerpo_ok:
                ambiguo.append("cuerpo no identificado")
            reg.update({"subtipo": "remocion_pares" if es_par else "exclusion_token", "tokens": toks, "texto_lista_pares": lista_pares,
                        "tokens_sin_par_usdt_en_texto": fuera, "pares_usdt": sorted(afectados),
                        "fecha_efectiva": fe.isoformat() if fe else None, "origen_fecha": origen, "ambiguo": ambiguo,
                        "en_listado_vision": sorted(a for a in afectados if a in usdt), "cuerpo": cuerpo[:4000]})
            for a in sorted(afectados) or [None]:
                exclusiones.append({**{k: reg[k] for k in ("url", "url_archivada", "captura", "titulo", "publicado", "subtipo", "tokens",
                                                           "texto_lista_pares", "fecha_efectiva", "origen_fecha")},
                                    "par": a, "par_en_texto": bool(a) and a[:-4] in pares,
                                    "ambiguo": ambiguo + ([] if a else ["sin par USDT identificable"])})
        elif tipo == "correccion":
            fe, origen = fecha_efectiva(tit, cuerpo, T_DELIST)
            reg.update({"tokens": tokens_titulo(tit), "pares_usdt": sorted({x + "USDT" for x in PAR.findall(cuerpo)}),
                        "fecha": fe.isoformat() if fe else None, "cuerpo": cuerpo[:3000]})
            correcciones.append(reg)
        elif tipo == "renombre":
            fe, origen = fecha_efectiva(tit, cuerpo, re.compile(r"trading|swap|rebrand|renam", re.I))
            reg.update({"fecha": fe.isoformat() if fe else None, "tokens_titulo": sorted(set(TOK_PAR.findall(tit)) - NO_TOKEN),
                        "pares_usdt": sorted({x + "USDT" for x in PAR.findall(cuerpo)}), "cuerpo": cuerpo[:3000]})
            renombres.append(reg)
        if tipo == "listado" or (tipo == "renombre" and T_LIST.search(tit)):
            pares = sorted(set(PAR.findall(cuerpo)) | set(PAR.findall(tit)))
            fe, origen = fecha_efectiva(tit, cuerpo, re.compile(r"open trading|trading (?:will )?(?:open|start)|will list|\blist", re.I))
            reg.update({"pares_usdt_listados": [x + "USDT" for x in pares], "fecha_apertura": fe.isoformat() if fe else None,
                        "origen_fecha_apertura": origen})
            for x in pares:
                listados.append({"par": x + "USDT", "fecha_apertura": reg["fecha_apertura"], "url": p["url"], "titulo": tit,
                                 "publicado": reg["publicado"], "url_archivada": p.get("url_archivada")})
        todos.append(reg)
    for nombre, obj in (("anuncios_clasificados", todos), ("exclusiones_usdt", exclusiones), ("listados_usdt", listados),
                        ("renombres_candidatos", renombres), ("correcciones", correcciones)):
        (d / f"{nombre}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=0))
    resumen = {"paginas": len(todos), "cuerpo_identificado": sum(r["cuerpo_identificado"] for r in todos),
               "por_tipo": {t: sum(1 for r in todos if r["tipo"] == t) for t in ("exclusion", "correccion", "renombre", "listado", "otro")},
               "exclusiones_filas_par": len(exclusiones), "exclusiones_ambiguas": sum(1 for e in exclusiones if e["ambiguo"]),
               "listados_pares_usdt": len(listados), "renombres": len(renombres), "correcciones": len(correcciones),
               "paginas_por_anio_publicacion": {}}
    for r in todos:
        y = (r["publicado"] or "sin_fecha")[:4]
        resumen["paginas_por_anio_publicacion"][y] = resumen["paginas_por_anio_publicacion"].get(y, 0) + 1
    resumen["paginas_por_anio_publicacion"] = dict(sorted(resumen["paginas_por_anio_publicacion"].items()))
    (d / "resumen_clasificacion.json").write_text(json.dumps(resumen, indent=1))
    print(json.dumps(resumen, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
