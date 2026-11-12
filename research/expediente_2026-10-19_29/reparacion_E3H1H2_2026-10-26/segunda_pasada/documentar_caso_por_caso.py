"""Documento caso por caso de la segunda pasada (A3.11). Verifica cada cita contra el texto archivado; si falta, aborta.
Solo textos, listados del bucket y salidas de la conciliación: ningún precio.
Uso: python -I documentar_caso_por_caso.py <dir_ejecucion_E3> <dir_reparacion> <salida.md> <salida.json>
"""
import glob
import json
import re
import sys
from pathlib import Path

E3, REP, SAL_MD, SAL_J = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
CC = E3 / "datos_anuncios" / "commoncrawl"


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


pag = []
for f in sorted(glob.glob(str(CC / "paginas" / "*.json"))):
    d = json.loads(Path(f).read_text())
    pag.append({"archivo": Path(f).name, "url": d["url"], "titulo": d.get("titulo", ""), "texto": norm(d.get("texto", "")),
                "captura": d.get("captura"), "warc": d.get("url_archivada")})


def fuente(sub_url, cita):
    for p in pag:
        if sub_url in p["url"] and norm(cita) in p["texto"]:
            return {k: p[k] for k in ("url", "archivo", "captura", "warc")}
    raise SystemExit(f"CITA NO ENCONTRADA ({sub_url}): {cita!r}")


usdt = set(json.loads((E3 / "datos_vision/listados/simbolos_usdt.json").read_text()))
todos = set(json.loads((E3 / "datos_vision/listados/simbolos_todos.json").read_text()))
COTIZ = ("USDT", "BTC", "ETH", "BNB", "BUSD", "TUSD", "USDC", "PAX", "USDS", "FDUSD", "TRY", "EUR", "GBP", "AUD", "BRL", "RUB", "XRP",
         "TRX", "DAI", "IDRT", "BIDR", "UAH", "NGN", "ZAR", "BKRW", "VAI", "USDP", "DOGE", "JPY", "PLN", "RON", "ARS", "MXN", "COP", "CZK")


def evidencia_usdt(tok):
    rx = re.compile(rf"(?<![A-Z0-9]){tok}\s*/\s*USDT(?![A-Z])|(?<![A-Z0-9]){tok}USDT(?![A-Z])")
    return sorted({p["archivo"] for p in pag if rx.search(p["texto"])})[:3]


def pares_mencionados(tok):
    rx = re.compile(rf"(?<![A-Z0-9]){tok}\s*/\s*[A-Z]{{2,6}}(?![A-Z])")
    return sorted({m.group(0) for p in pag for m in rx.finditer(p["texto"])})[:5]


# ---------------------------------------------------------------- 12 filas «sin par» (exclusiones sin par ni lista de pares)
SIN_PAR = [
    ("0a17fc70baad496aa2bbc47661aa6727", "1 COVER-old = 1 COVER-new", "canje de token (COVER-old → COVER-new)",
     "Sin evento: canje 1:1 del mismo token; COVERUSDT no figura en el bucket", "alta"),
    ("52712c5af7284587b4e7dd2279a670d1", "Binance will remove and cease trading on the following trading pairs at 2021-09-09 12:00 PM (UTC): AAVEBRL, EOSAUD, ICPRUB",
     "remoción de pares", "Fuera del universo: el texto lista los pares y ninguno es contra USDT (A3.2)", "alta"),
    ("a6e9bfe3106f4390abf96622139db6d8", "Binance will perform a conversion of delisted tokens to BUSD",
     "conversión posterior a exclusiones ya ocurridas", "Sin evento nuevo: convierte saldos de tokens ya excluidos", "alta"),
    ("announcement/f45dde7da58b473aa885349946bed269", "Binance will delist all WAPI endpoints from the Binance API at 2021-08-01 2:00 AM (UTC)",
     "cambio de API", "Descartado: no es un token ni un par (error de extracción)", "alta"),
    ("delisting-wapi-endpoints-f45dde7da58b473aa885349946bed269", "Binance will delist all WAPI endpoints from the Binance API",
     "cambio de API (duplicado)", "Descartado: no es un token ni un par (error de extracción)", "alta"),
    ("360026666152", "for the following coin on 2019/04/22 at 10:00 AM UTC: Bitcoin SV (BCHSV)",
     "exclusión de token (captura duplicada)", "Cubierto por el evento BCHSVUSDT|2019-04-22 (categoría A)", "alta"),
    ("360041278332", "Binance has now delisted all FTX leveraged tokens including BULL, BEAR, ETHBULL, ETHBEAR",
     "aviso posterior a la exclusión", "Cubierto por los 10 eventos FTX del 2020-03-31 (categoría A)", "alta"),
    ("Will-Complete-Distribution-of-BUSD", "Binance has now delisted all FTX leveraged tokens",
     "aviso posterior a la exclusión (duplicado)", "Cubierto por los 10 eventos FTX del 2020-03-31 (categoría A)", "alta"),
    ("c-161?navId=161", "Delisting", "página índice de la sección",
     "Descartado: solo navegación, sin contenido de anuncio. La ausencia de contenido no prueba que no hubo eventos", "alta"),
    ("delisting?c=161&navId=161", "Delisting", "página índice de la sección",
     "Descartado: solo navegación, sin contenido de anuncio. La ausencia de contenido no prueba que no hubo eventos", "alta"),
    ("9972ee7df32144d099c78c7df39011a2", "Binance will re-open withdrawals for the following 12 delisted tokens",
     "reapertura de retiros y conversión de 12 tokens ya excluidos", "Sin evento nuevo; cada token se revisa abajo (A3.3)", "alta"),
    ("9ec5cabbc8974a1c8890e1c9d87a98a7", "Binance will perform a conversion of the below tokens to USDC",
     "conversión de 15 tokens ya excluidos", "Sin evento nuevo; cada token se revisa abajo (A3.3)", "alta"),
]
sin_par = []
for sub, cita, tipo, decision, certeza in SIN_PAR:
    sin_par.append({"url_contiene": sub, "cita": cita, "fuente": fuente(sub, cita), "tipo": tipo, "decision": decision, "certeza": certeza})

# ---------------------------------------------------------------- tokens de los dos avisos de conversión (A3.3)
TOKENS = {"2023-12-04": ["AION", "BEAM", "BCD", "GO", "NEBL", "NAS", "NSBT", "NXS", "VIA", "SKY", "SGB", "YOYO"],
          "2024-08-12": ["BTG", "BTCST", "BTS", "DNT", "GRS", "HEGIC", "MOB", "XMR", "MTH", "MULTI", "NAV", "SOLO", "SPARTA", "XYM", "TRIBE"]}
AIRDROP = {"SGB": ("4acc20ea6da14660a61f84b862afc1ed", "Binance will support the Songbird (SGB) Airdrop Program for XRP (XRP) holders"),
           "NSBT": ("c890d42730f44cc082ba5d1f927689bf", "The QiSwap (QI) and Neutrino Token (NSBT) airdrop programs were complete"),
           "XYM": ("17aaa4d4b0884875b241e85199e8bf61", "When Binance performs the snapshot on users’ NEM (XEM) holdings for the Symbol (XYM) airdrop"),
           "SOLO": ("sologenic-solo-airdrop", "Binance will support the Sologenic (SOLO) Airdrop Program for XRP (XRP) holders")}
tokens = []
for aviso, lista in TOKENS.items():
    for t in lista:
        par = t + "USDT"
        otros = sorted(s for s in todos if s != par and any(s == t + q for q in COTIZ))
        ev = evidencia_usdt(t)
        fila = {"aviso": aviso, "token": t, "usdt_en_bucket": par in usdt, "otros_pares_en_bucket": otros,
                "evidencia_usdt_en_paginas": ev, "pares_mencionados": pares_mencionados(t)}
        if par in usdt:
            fila["decision"] = "Par USDT en el bucket: su salida es una salida observada y se audita como tal (N7, Adenda R)"
            fila["evidencia"] = "positiva (par en Vision)"
        elif ev:
            fila["decision"] = "A3.3.1: hay evidencia documental de XYZ/USDT → sería D. REVISAR"
            fila["evidencia"] = "positiva"
        elif otros:
            fila["decision"] = "A3.3.2: sin evidencia de par USDT y con otro par en el bucket → sin par USDT documentado (fuera del universo)"
            fila["evidencia"] = "negativa por regla (el bucket conserva pares retirados)"
        else:
            sub, cita = AIRDROP[t]
            fila["decision"] = ("A3.3.3, lectura manual: el archivo identifica el token como distribuido por airdrop; ninguna página menciona "
                                "un par de negociación spot. No es D")
            fila["cita"], fila["fuente"] = cita, fuente(sub, cita)
            fila["evidencia"] = "positiva de airdrop; ausencia de evidencia de negociación spot (no se toma como prueba de que no existió)"
        if t == "SKY":
            fila["decision"] = ("A3.3.2: el SKYUSDT del bucket empieza el 2025-09-17, casi dos años después del aviso: es otro activo "
                                "(cambio de símbolo MKR→SKY). Para Skycoin no hay evidencia de par USDT y sí otros pares en el bucket → "
                                "sin par USDT documentado (fuera del universo)")
            fila["evidencia"] = "negativa por regla; certeza media-alta (la identidad del SKYUSDT de 2025 se infiere de la actividad)"
        tokens.append(fila)
if any("REVISAR" in f["decision"] for f in tokens):
    raise SystemExit("hay un token con evidencia de par USDT sin par en el bucket: revisar antes de seguir")

res = json.loads((REP / "segunda_pasada/resoluciones_manuales.json").read_text())
omit = json.loads((REP / "segunda_pasada/eventos_omitidos.json").read_text())
con = json.loads((REP / "segunda_pasada/salida_pasada2/conciliacion.json").read_text())
SAL_J.write_text(json.dumps({"sin_par": sin_par, "tokens_avisos_de_conversion": tokens}, ensure_ascii=False, indent=1))

L = ["# Segunda pasada A3.11 · caso por caso", "",
     "Todas las citas se verificaron literalmente contra el texto archivado local (los scripts abortan si una falta).",
     "Evidencia: **positiva** = el texto o el bucket muestran el hecho; **negativa** = una regla congelada lo excluye; "
     "**ausencia de evidencia** = no se encontró nada (no se usa como prueba).", "",
     f"Resultado de `conciliacion.py` (6f764845…) con estas resoluciones: componentes {con['componentes_inicio']}, "
     f"última falla {con['ultima_falla']['par']} {con['ultima_falla']['E']} ({con['ultima_falla']['categoria']}), "
     f"V-S2 {con['V_S2']['aciertos']}/{con['V_S2']['n']}, V-S3 revisados {con['V_S3_revisados']}, "
     f"pendientes {con['pendiente_revision_manual']} (las 12 «sin par» no tienen mecanismo en el código: se resuelven abajo).", "",
     "## 1. Eventos (47 claves; se releyeron todas, no solo las listas de revisión)", "",
     "| Clave (par · E de la 1.ª pasada) | Cat. 1.ª | Decisión | E según el texto | Certeza | Cita | Fuente (archivo · captura) |", "|---|---|---|---|---|---|---|"]
for k, r in sorted(res["eventos"].items(), key=lambda x: (x[0].split("|")[1], x[0])):
    L.append(f"| {k} | {r['categoria_pasada1']} | {r['accion']} | {r.get('E', k.split('|')[1])} | {r['certeza']} | «{r['cita']}» | "
             f"{r['fuente']['archivo'][:60]} · {r['fuente']['captura']} |")
L += ["", "Justificaciones por tipo de decisión:"] + [f"- **{a}**: {j}" for a, j in sorted({r["accion"]: r["justificacion"] for r in res["eventos"].values()}.items())]
L += ["", "## 2. Filas sin fecha (8 = BCN, CHAT, ICN, TRIG × 2 URL)", "", "| Fila | E | Cita | Fuente | Decisión |", "|---|---|---|---|---|"]
for k, r in res["sin_fecha"].items():
    L.append(f"| {k.split('|')[0]} · {k.split('|')[1][-45:]} | {r['E']} | «{r['cita']}» | {r['fuente']['archivo'][:50]} · {r['fuente']['captura']} | {r['justificacion']} |")
L += ["", "## 3. Eventos omitidos por la extracción (mismo anuncio que DOTUP, DOTDOWN, TRXDOWN y LINKUP)", "",
      "| Par | E | Categoría (función congelada `clasificar`) | L | Uso |", "|---|---|---|---|---|"]
for o in omit:
    L.append(f"| {o['par']} | {o['E']} | {o['categoria']} | {o['L']} | Se suman a (ii) y (ii′) como fallas; no mueven el inicio (E ≤ 2023-05-11) |")
L += [f"", f"Cita: «{omit[0]['cita']}» ({omit[0]['fuente']}).", "",
      "## 4. Las 12 filas «sin par» (sin par extraído ni lista de pares)", "", "| URL (fragmento) | Tipo | Decisión | Certeza | Cita | Captura |", "|---|---|---|---|---|---|"]
for s in sin_par:
    L.append(f"| …{s['fuente']['url'][-50:]} | {s['tipo']} | {s['decision']} | {s['certeza']} | «{s['cita'][:120]}» | {s['fuente']['captura']} |")
L += ["", "## 5. Tokens de los dos avisos de conversión (2023-12-04 y 2024-08-12), incluidos NSBT, SGB, SOLO y XYM", "",
      "| Aviso | Token | USDT en bucket | Otros pares en bucket | Evidencia USDT en páginas | Decisión | Evidencia |", "|---|---|---|---|---|---|---|"]
for t in tokens:
    L.append(f"| {t['aviso']} | {t['token']} | {'sí' if t['usdt_en_bucket'] else 'no'} | {', '.join(t['otros_pares_en_bucket'][:4]) or '—'} | "
             f"{len(t['evidencia_usdt_en_paginas'])} | {t['decision']}{(' — ' + t['nota']) if t.get('nota') else ''} | {t['evidencia']} |")
for t in tokens:
    if t.get("cita"):
        L.append(f"- **{t['token']}**: «{t['cita']}» ({t['fuente']['archivo'][:60]}, captura {t['fuente']['captura']}). Pares mencionados en el archivo: {t['pares_mencionados'] or 'ninguno'}.")
L += ["", "## 6. Controles de muestreo", "",
      f"- **V-S2** (1 desacierto, ETHBEARUSDT|2020-01-17): {res['vs2']['ETHBEARUSDT|2020-01-17']['revision']}",
      f"- **V-S3**: la muestra de la primera pasada (10) se revisó completa; el código congelado vuelve a sortear sobre el universo de la segunda pasada y "
      f"los 10 sorteados también tienen revisión (se revisaron los 47 eventos). Resultado: {con['V_S3_revisados']}/10 revisados.", "",
      "## 7. Renombres (164 candidatos) — ver `../renombres/CLASIFICACION_RENOMBRES.md`"]
SAL_MD.write_text("\n".join(L) + "\n")
print(json.dumps({"sin_par": len(sin_par), "tokens": len(tokens), "airdrop_A333": [t["token"] for t in tokens if t.get("cita")]}, ensure_ascii=False))
