"""Construye y verifica la tabla completa de renombres y redenominaciones exigida por la Adenda 1.

Entradas (solo textos y actividad; ningún precio ni volumen):
  - las 8.028 páginas archivadas (cada cita se verifica como subcadena del texto normalizado del archivo citado);
  - `auditoria_por_simbolo.json` (episodios y cortes con reanudación);
  - la tabla de 22 mapeos de la reparación (`mapeos_adenda1.json`, aeb8b5f2…), que se reverifica y se conserva;
  - `splits_apalancados.json` y `barrido_renombres.json` de esta carpeta.
Salidas: TABLA_RENOMBRES_COMPLETA.json, mapeos_adenda1_completa.json (lo que aplica el orquestador v3) y
clasificacion_barrido.json (los 117 pares del barrido, cada uno con su clase). Aborta si una cita no está en su página,
si la actividad contradice un mapeo o si queda un par del barrido sin clasificar.
Uso: python -I construir_tabla.py <dir_E3> <mapeos_adenda1.json> <dir_salida>
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

E3, MAP22, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
AQUI = Path(__file__).resolve().parent
PAG = E3 / "datos_anuncios/commoncrawl/paginas"
aud = {a["simbolo"]: a for a in json.loads((E3 / "resultados/calidad/auditoria_por_simbolo.json").read_text())}
d = dt.date.fromisoformat
INICIO_A = d("2023-05-15")


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


_cache = {}


def texto(archivo):
    if archivo not in _cache:
        j = json.loads((PAG / archivo).read_text())
        _cache[archivo] = (norm(j.get("texto", "")), str(j.get("captura", "")), j.get("url", ""))
    return _cache[archivo]


def ev(archivo, cita):
    t, cap, url = texto(archivo)
    return {"archivo": archivo, "captura": cap, "url": url, "cita": cita, "cita_en_pagina": norm(cita) in t}


def episodios(s):
    return aud[s]["episodios"] if s in aud else None


def ultimo_activo(s):
    return d(aud[s]["episodios"][-1][1])


def primer_activo(s):
    return d(aud[s]["episodios"][0][0])


# ----------------------------------------------------------------- 1) los 22 de la reparación, reverificados
tabla = []
for m in json.loads(MAP22.read_text())["mapeos"]:
    evs = [ev(m["fuente"]["archivo"], m["cita"])]
    if m.get("cita_fechas"):
        evs.append(ev(m["fuente"]["archivo"], m["cita_fechas"]))
    tabla.append({"id": None, "origen": "tabla_22_reparacion", "viejo_usdt": m["viejo_usdt"], "nuevo_usdt": m["nuevo_usdt"],
                  "tratamiento": f"regla_{m['regla']}", "r": m["r"], "E": m["E"], "apertura_texto": m.get("apertura_segun_texto"),
                  "certeza": m["certeza"], "nota": m.get("nota"), "evidencia": evs})

# ----------------------------------------------------------------- 2) renombres y redenominaciones nuevos (regla 1 y 2)
U = "url_https___www.binance.com_en_support_announcement_"
NUEVOS = [
    ("MFTUSDT", "HIFIUSDT", "regla_1", 0.01, "2023-01-12", None, "media",
     "Solo está archivado el anuncio de finalización (fechado 2023-01-12); fija símbolos, relación y fecha de "
     "finalización, no la hora de cese del par viejo. E = fecha del anuncio de finalización (mismo criterio que "
     "COCOS→COMBO y TVK→VANRY en la tabla de 22).",
     [(U + "binance-has-completed-the-ma_934dcf237cdb.json",
       "Binance has completed the Mainframe (MFT) token swap, redenomination and rebranding plan to Hifi Finance (HIFI)"),
      (U + "binance-has-completed-the-ma_934dcf237cdb.json",
       "The distribution of Hifi Finance ( HIFI) was conducted at a ratio of 1 MFT = 0.01 HIFI"),
      (U + "binance-has-completed-the-ma_934dcf237cdb.json", "Binance Team 2023-01-12")]),
    ("BTTUSDT", "BTTCUSDT", "regla_1", 1000, "2022-01-17", "2022-01-25", "alta", None,
     [("bn_2722e6da4f5141dd9b2fb07b5b1f3f75_372793e0ce0b.json",
       "at a ratio of 1 BTT (Old) = 1,000 BTTC"),
      ("bn_2722e6da4f5141dd9b2fb07b5b1f3f75_372793e0ce0b.json",
       "the old BTT tokens will be renamed as BTTOLD, and the new tokens’ ticker will be BTTC"),
      ("bn_2722e6da4f5141dd9b2fb07b5b1f3f75_372793e0ce0b.json",
       "Binance will delist all existing BTT spot trading pairs (BTT/USDT, BTT/BUSD, BTT/USDC, BTT/BNB, BTT/TRX, BTT/TUSD, "
       "BTT/TRY, BTT/EUR, BTT/BRL) at 2022-01-17 04:00 (UTC)"),
      ("bn_2722e6da4f5141dd9b2fb07b5b1f3f75_372793e0ce0b.json",
       "Trading will then open for BTTC/USDT, BTTC/USDC and BTTC/TRY spot trading pairs at 2022-01-25 04:00 (UTC)")]),
    ("NANOUSDT", "XNOUSDT", "regla_1", 1, "2022-01-24", "2022-01-28", "alta", None,
     [("bn_3dc8f6de281f4781a246a1658a21cb80_e7bc3f27677f.json", "Binance will update the ticker of NANO to XNO"),
      ("bn_3dc8f6de281f4781a246a1658a21cb80_e7bc3f27677f.json",
       "At 2022-01-24 04:00 AM (UTC), Binance will halt trading for all NANO spot trading pairs"),
      ("bn_3dc8f6de281f4781a246a1658a21cb80_e7bc3f27677f.json", "at a ratio of 1 NANO = 1 XNO"),
      ("bn_3dc8f6de281f4781a246a1658a21cb80_e7bc3f27677f.json",
       "At 2022-01-28 04:00 AM (UTC), Binance will open trading for the new XNO/USDT")]),
    ("BZRXUSDT", "OOKIUSDT", "regla_1", 10, "2021-12-20", "2021-12-24", "alta", None,
     [("bn_dff27dc6bcbb432c902bcbea5e24ddfa_117538216109.json",
       "Binance will support the bZx Protocol Token (BZRX) token swap and redenomination plan to OokiDAO Token (OOKI)"),
      ("bn_dff27dc6bcbb432c902bcbea5e24ddfa_117538216109.json",
       "Binance will delist all existing BZRX spot trading pairs (BZRX/BTC, BZRX/USDT, and BZRX/BUSD) and cancel all pending "
       "BZRX spot orders at 2021-12-20 04:00 (UTC)"),
      ("bn_dff27dc6bcbb432c902bcbea5e24ddfa_117538216109.json", "at a ratio of 1 BZRX = 10 OOKI"),
      ("bn_dff27dc6bcbb432c902bcbea5e24ddfa_117538216109.json",
       "Trading will then open for OOKI/USDT and OOKI/BUSD spot trading pairs at 2021-12-24 04:00 (UTC)")]),
    ("RAMPUSDT", "LEVERUSDT", "regla_1", 35, "2022-07-04", "2022-07-13", "alta", None,
     [("bn_0a445bbdac634512886df1bdce74f3da_3631af0d9289.json",
       "Binance will support the RAMP (RAMP) token swap, redenomination and rebranding plan to LeverFi (LEVER)"),
      ("bn_0a445bbdac634512886df1bdce74f3da_3631af0d9289.json",
       "At 2022-07-04 04:00 (UTC), Binance will delist all existing RAMP spot trading pairs (RAMP/USDT, RAMP/BUSD, and RAMP/BTC)"),
      ("bn_0a445bbdac634512886df1bdce74f3da_3631af0d9289.json",
       "At 2022-07-13 04:00 (UTC), trading will open for LEVER/USDT and LEVER/BUSD spot trading pairs"),
      ("bn_0a445bbdac634512886df1bdce74f3da_3631af0d9289.json", "at a ratio of 1 RAMP = 35 LEVER")]),
    ("EPSUSDT", "EPXUSDT", "regla_1", 88, "2022-05-09", "2022-05-18", "alta",
     "El texto anuncia la apertura de EPX/USDT para el 2022-05-18; un anuncio posterior archivado informa una demora "
     "(«Binance will require additional time…»). La actividad muestra el primer día de EPXUSDT el 2022-05-23 "
     "(hueco de 14 días, < 30).",
     [("bn_cf9526489aa041508f4cd57612f34119_c6ec648a669e.json", "The ticker of EPS will be updated to EPX"),
      ("bn_cf9526489aa041508f4cd57612f34119_c6ec648a669e.json",
       "Binance will delist all existing EPS spot trading pairs (EPS/USDT, EPS/BUSD and EPS/BTC) and cancel all pending EPS "
       "spot orders at 2022-05-09 04:00 (UTC)"),
      ("bn_cf9526489aa041508f4cd57612f34119_c6ec648a669e.json", "at a ratio of 1 EPS = 88 EPX"),
      ("bn_bab533fdba1e4b2ba21053a7668c2865_ce3a108df373.json", "The distribution of EPX was conducted at a ratio of 1 EPS = 88 EPX"),
      ("bn_4e21b7d402a840928c652e1f74812547_7d7dc741f0af.json", "Binance will require additional time to complete the Ellipsis (EPS) "
       "token migration, redenomination and ticker change to EPX")]),
    ("GXSUSDT", "REIUSDT", "regla_1", 10, "2022-04-25", "2022-05-04", "alta", None,
     [("bn_bdfb52830f2f4bfcba496f3f92876b5c_ccba14b6e687.json",
       "Binance will support the GXChain (GXS) mainnet token swap and redenomination plan to REI Network (REI)"),
      ("bn_bdfb52830f2f4bfcba496f3f92876b5c_ccba14b6e687.json",
       "Binance will delist all existing GXS spot trading pairs (GXS/BTC, GXS/USDT, GXS/BNB and GXS/ETH) and cancel all "
       "pending GXS spot orders at 2022-04-25 04:00 (UTC)"),
      ("bn_bdfb52830f2f4bfcba496f3f92876b5c_ccba14b6e687.json", "at a ratio of 1 GXS = 10 REI"),
      ("bn_bdfb52830f2f4bfcba496f3f92876b5c_ccba14b6e687.json",
       "Trading will then open for REI/USDT, REI/BNB and REI/ETH spot trading pairs at 2022-05-04 04:00 (UTC)")]),
    ("BNXUSDT", "BNXUSDT", "regla_2", 100, "2023-02-16", "2023-02-22", "alta",
     "El anuncio previo fija la reapertura para el 2023-02-24; un anuncio posterior archivado la adelanta al 2023-02-22, "
     "que coincide con la actividad.",
     [(U + "binance-will-support-the-bin_8c6a897856c8.json", "at a ratio of 1 old BNX = 100 new BNX"),
      (U + "binance-will-support-the-bin_8c6a897856c8.json",
       "At 2023-02-16 03:00 (UTC), Binance will suspend and delist all existing BNX spot trading pairs"),
      (U + "binance-has-completed-the-bi_cb114013aaba.json", "The distribution of BNX was conducted at a ratio of 1 BNXOLD = 100 BNX"),
      (U + "updates-to-listing-time-for-_c4e094937856.json",
       "Binance will update the trading start time for the BNX/BTC, BNX/BNB, BNX/BUSD and BNX/USDT spot trading pairs from "
       "2023-02-24 08:00 (UTC) to 2023-02-22 08:00 (UTC)")]),
    ("VIDTUSDT", "VIDTUSDT", "regla_2", 10, "2022-10-31", "2022-11-09", "alta", None,
     [(U + "binance-will-support-the-vid_5d4ce6e224e4.json", "at a ratio of 1 old VIDT = 10 new VIDT"),
      (U + "binance-will-support-the-vid_5d4ce6e224e4.json",
       "At 2022-10-31 03:00 (UTC), Binance will delist all existing VIDT spot trading pairs (VIDT/USDT, VIDT/BUSD, and VIDT/BTC)"),
      (U + "binance-will-support-the-vid_5d4ce6e224e4.json",
       "At 2022-11-09 08:00 (UTC), trading will open for VIDT/USDT, VIDT/BUSD, and VIDT/BTC spot trading pairs")]),
]
for x, y, trat, r, E, ap, cert, nota, evs in NUEVOS:
    tabla.append({"id": None, "origen": "nuevo_cierre", "viejo_usdt": x, "nuevo_usdt": y, "tratamiento": trat, "r": r, "E": E,
                  "apertura_texto": ap, "certeza": cert, "nota": nota, "evidencia": [ev(a, c) for a, c in evs]})

# ----------------------------------------------------------------- 3) reverse splits de tokens apalancados (regla 2)
for s in json.loads((AQUI / "splits_apalancados.json").read_text()):
    an, fi = s["anuncio"], s["finalizacion"]
    E = (d(s["ultimo_activo"]) + dt.timedelta(days=1)).isoformat()
    evs = [ev(an["archivo"], an["cita"])] + ([ev(fi["archivo"], fi["cita"])] if fi else [])
    tabla.append({"id": None, "origen": "nuevo_cierre", "viejo_usdt": s["simbolo"], "nuevo_usdt": s["simbolo"],
                  "tratamiento": "regla_2", "r": 1 / an["relacion_N_por_1"], "E": E, "apertura_texto": s["reanuda"] if fi else None,
                  "certeza": "alta" if fi else "media",
                  "nota": "Token apalancado: excluido de todo universo (v3 §4.5); la regla 2 se aplica por literalidad y no "
                          "altera ningún cálculo." + ("" if fi else " No está archivado el aviso de finalización; la "
                          "fecha de inicio del anuncio coincide con el corte."), "evidencia": evs})

# ----------------------------------------------------------------- 4) reutilización de ticker (regla 1, última oración)
tabla.append({"id": None, "origen": "nuevo_cierre", "viejo_usdt": "LUNAUSDT", "nuevo_usdt": None, "tratamiento": "regla_1_reutilizacion",
              "r": None, "E": None, "reutilizacion_desde": "2022-05-31", "apertura_texto": "2022-05-31", "certeza": "alta",
              "nota": "Adenda 1, regla 1: «Si después X vuelve a negociarse, ese tramo es un listado nuevo (otro activo), "
                      "aunque el corte haya durado menos de 30 días». LUNAUSDT desde el 2022-05-31 es Terra 2.0: listado "
                      "nuevo. La fecha exacta del cambio de ticker no está archivada («has since been renamed»); el corte "
                      "de actividad (2022-05-12 → 2022-05-31) y la apertura de Terra 2.0 sí. La continuación del LUNA viejo "
                      "por LUNCUSDT (primer día 2022-09-09, 120 días después) es la decisión D-1.",
              "evidencia": [ev("bn_9c8abd90df5d4890822e6988f7dc8f0c_da2dc145761b.json",
                               "LUNA (old) was renamed as LUNC while LUNA (new) assumes the ticker LUNA"),
                            ev("bn_d044a6742e484b77a170111460b0eed3_a6996a0ba9ba.json",
                               "Binance will list Terra 2.0 (LUNA) in the Innovation Zone and will open trading for LUNA/USDT "
                               "and LUNA/BUSD trading pairs at 2022-05-31 06:00 (UTC)"),
                            ev("bn_d044a6742e484b77a170111460b0eed3_a6996a0ba9ba.json",
                               "The ticker for Terra Classic, or the LUNA (old) token, has since been renamed as LUNC")]})

# ----------------------------------------------------------------- 5) casos que la regla 1 no resuelve (decisión D-1)
D1 = "D1_sin_continuidad_lectura_literal"
tabla += [
    {"id": None, "origen": "nuevo_cierre", "viejo_usdt": "GTOUSDT", "nuevo_usdt": "GFTUSDT", "tratamiento": D1, "r": 1, "E": None,
     "apertura_texto": "2023-09-22", "certeza": "alta",
     "nota": "El par GTO/USDT se retiró por anuncio el 2022-11-28 (último día activo 2022-11-27), antes del canje "
             "(anunciado con calendario desde el 2023-01-18; completado con 1 GTO = 1 GFT). GFT/USDT abrió el 2023-09-22 "
             "(299 días después). En la fecha efectiva del canje no había «listado vigente» de X en USDT.",
     "evidencia": [ev(U + "notice-of-removal-of-trading_e69561bf9f77.json",
                      "Binance will remove and cease trading on the following trading pairs at 2022-11-28 03:00 (UTC) : Spot "
                      "Pairs : ARK/BTC, BEAM/BTC, BTCST/BTC, BTCST/USDT, GTO/BTC, GTO/USDT"),
                   ev(U + "binance-will-support-the-gif_a146802a7fbd.json", "Binance will support the Gifto (GTO) token swap to Gifto (GFT)"),
                   ev(U + "binance-has-completed-the-gi_680cabd50dfb.json",
                      "The distribution of Gifto (GFT) was conducted at a ratio of 1 GTO = 1 GFT"),
                   ev(U + "notice-of-addition-removal-o_de27e21c5438.json",
                      "Binance will open trading for the ARK/USDT, CREAM/USDT, FTT/USDT, GFT/USDT, IQ/USDT")]},
    {"id": None, "origen": "nuevo_cierre", "viejo_usdt": "LUNAUSDT", "nuevo_usdt": "LUNCUSDT", "tratamiento": D1, "r": 1, "E": None,
     "apertura_texto": None, "certeza": "alta",
     "nota": "Continuación del LUNA viejo (último día en LUNAUSDT 2022-05-12) por LUNCUSDT (primer día 2022-09-09). La "
             "reutilización del ticker sí está resuelta (entrada regla_1_reutilizacion).",
     "evidencia": [ev("bn_9c8abd90df5d4890822e6988f7dc8f0c_da2dc145761b.json",
                      "LUNA (old) was renamed as LUNC while LUNA (new) assumes the ticker LUNA")]},
    {"id": None, "origen": "nuevo_cierre", "viejo_usdt": "USTUSDT", "nuevo_usdt": "USTCUSDT", "tratamiento": D1, "r": 1, "E": None,
     "apertura_texto": None, "certeza": "alta",
     "nota": "USTUSDT termina el 2022-05-12; USTCUSDT empieza el 2023-03-10. UST y USTC están en la lista fija (§4.5): "
             "sin efecto con cualquier lectura.",
     "evidencia": [ev("bn_9c8abd90df5d4890822e6988f7dc8f0c_da2dc145761b.json", "UST (old) was renamed as USTC")]},
]

# ----------------------------------------------------------------- 6) anunciados pero fuera de la regla 1 o 2
FUERA = [
    ("BCCUSDT", "BCHABCUSDT", "bifurcacion_un_X_dos_Y",
     "Bifurcación: BCC se reemplazó por dos activos (BCHABC y BCHSV, 1:1 cada uno). La regla 1 presupone un único Y "
     "que hereda posiciones; aquí no hay uno. Salida de BCC y dos listados nuevos. Sin efecto en A (2018).",
     [(U + "360019875411_1a77d5c2148e.json", "BCHABC and BCHSV balances were each distributed to users in a ratio of 1 BCC = 1 "
       "BCHABC and 1 BCC = 1 BCHSV")]),
    ("RGTUSDT", "TRIBEUSDT", "fusion_en_par_existente",
     "Canje de RGT por TRIBE (1 RGT : 26,7 TRIBE). TRIBEUSDT ya cotizaba desde 2021-08-24, antes del fin de RGTUSDT "
     "(2022-03-13): Y no puede «continuar» a X. Salida de RGT. Sin efecto en A.",
     [("bn_260d553938db4d568d7d58414fa317fa_7e314ae2c509.json", "1 RGT : 26.7 TRIBE")]),
    ("BETHUSDT", "WBETHUSDT", "conversion_con_solapamiento",
     "WBETHUSDT cotiza desde 2023-07-19 y BETHUSDT hasta 2023-10-10: se solapan; no hay continuación posible. Salida de "
     "BETH (2023, con evidencia en (iv′)).",
     [(U + "binance-introduces-wrapped-b_296d1552616a.json", "1 WBETH = 1 BETH")]),
    ("USDSBUSDT", "USDSUSDT", "conversion_con_solapamiento",
     "USDSUSDT ya cotizaba desde 2019-02-14. Ambos en la lista fija (§4.5): sin efecto.",
     [(U + "360034156752_302a31dcd79b.json", "1 USDSB = 1 USDS")]),
]
for x, y, trat, nota, evs in FUERA:
    tabla.append({"id": None, "origen": "nuevo_cierre", "viejo_usdt": x, "nuevo_usdt": y, "tratamiento": trat, "r": None, "E": None,
                  "apertura_texto": None, "certeza": "alta", "nota": nota, "evidencia": [ev(a, c) for a, c in evs]})

# ----------------------------------------------------------------- 7) cambios y cortes SIN anuncio archivado (regla 3)
SIN = [("TOMOUSDT", "VICUSDT"), ("GALUSDT", "GUSDT"), ("RNDRUSDT", "RENDERUSDT"), ("KLAYUSDT", "KAIAUSDT"),
       ("AGIXUSDT", "FETUSDT"), ("OCEANUSDT", "FETUSDT"), ("DARUSDT", "DUSDT"), ("FTMUSDT", "SUSDT"), ("EOSUSDT", "AUSDT"),
       ("MKRUSDT", "SKYUSDT"), ("FXSUSDT", "FRAXUSDT"), ("OMUSDT", "MANTRAUSDT")]
for x, y in SIN:
    tabla.append({"id": None, "origen": "reparacion_reverificado", "viejo_usdt": x, "nuevo_usdt": y, "tratamiento": "regla_3_sin_anuncio_archivado",
                  "r": None, "E": None, "apertura_texto": None, "certeza": None,
                  "nota": "Sin cuerpo archivado que lo anuncie (barridos por cuerpo, sin saludo y por actividad). Salida con "
                          "liquidación contable (§4.10) y listado nuevo; se informa como limitación.",
                  "evidencia": [], "actividad_viejo": episodios(x), "actividad_nuevo": episodios(y)})
EVID_CORTE = {
    "KEYUSDT": [(U + "notice-of-removal-of-trading_6bd297194a12.json",
                 "Binance will remove and cease trading on the following spot trading pairs: At 2023-02-10 03:00 (UTC) : "
                 "BOND/ETH, BSW/ETH, C98/BNB, C98/BRL, ERN/BNB, ENJ/GBP, KEY/USDT")],
    "SCRUSDT": [(U + "binance-will-end-the-scroll-_3831fc868ecd.json",
                 "Binance will end the Scroll (SCR) Pre-Market at 2024-10-21 09:00 (UTC) and open spot trading for the following "
                 "pairs at 2024-10-22 08:00 (UTC)")],
}
NOTAS_CORTE = {
    "KEYUSDT": "Retiro del par KEY/USDT el 2023-02-10 (anuncio archivado: «Binance will remove and cease trading on the "
               "following spot trading pairs: At 2023-02-10 03:00 (UTC) : … KEY/USDT») y reanudación el 2023-03-10, 28 días "
               "después. No es canje ni redenominación: mismo listado por la regla de 30 días (v3 §2.2.3). Previo a A.",
    "SCRUSDT": "Fin del pre-mercado y apertura spot (anuncio archivado: «end the Scroll (SCR) Pre-Market at 2024-10-21 09:00 "
               "(UTC) and open spot trading … at 2024-10-22 08:00 (UTC)»). No es canje. Mismo listado (corte de 1 día).",
}
for s, a in sorted(aud.items()):
    for L, F, n in a["cortes_con_reanudacion"]:
        if any(t["viejo_usdt"] == s and t["tratamiento"].startswith("regla_") and t["tratamiento"] != "regla_3_sin_anuncio_archivado"
               and (t.get("E") and d(L) <= d(t["E"]) < d(F) or t.get("reutilizacion_desde") == F) for t in tabla):
            continue
        tabla.append({"id": None, "origen": "nuevo_cierre", "viejo_usdt": s, "nuevo_usdt": s, "tratamiento": "regla_3_corte_sin_anuncio",
                      "r": None, "E": None, "corte": [L, F, n], "apertura_texto": None, "certeza": None,
                      "nota": NOTAS_CORTE.get(s, "Corte con reanudación sin anuncio archivado de canje o redenominación: mismo "
                                                 "listado (corte < 30 días, v3 §2.2.3)."),
                      "evidencia": [ev(a, c) for a, c in EVID_CORTE.get(s, [])]})

# ----------------------------------------------------------------- verificación de actividad
problemas = []
for i, t in enumerate(sorted(tabla, key=lambda t: (t["E"] or t.get("reutilizacion_desde") or "9999", t["viejo_usdt"]))):
    t["id"] = f"T{i + 1:03d}"
for t in tabla:
    ch = {}
    x, y, trat = t["viejo_usdt"], t["nuevo_usdt"], t["tratamiento"]
    if not all(e["cita_en_pagina"] for e in t["evidencia"]):
        problemas.append((t["id"], "cita ausente de su página"))
    if trat == "regla_1":
        Lx, Fy = ultimo_activo(x), primer_activo(y)
        ch = {"ultimo_activo_viejo": Lx.isoformat(), "primer_activo_nuevo": Fy.isoformat(), "hueco_dias": (Fy - Lx).days - 1,
              "viejo_inactivo_desde_E": Lx <= d(t["E"]), "nuevo_empieza_despues": Fy > Lx, "hueco_menor_30": (Fy - Lx).days - 1 < 30,
              "nuevo_con_menos_de_180_dias_en_A": (INICIO_A - Fy).days < 180}
        if not (ch["viejo_inactivo_desde_E"] and ch["nuevo_empieza_despues"] and ch["hueco_menor_30"]) or not t["r"] > 0:
            problemas.append((t["id"], f"actividad incoherente {ch}"))
    elif trat == "regla_2":
        cortes = [c for c in aud[x]["cortes_con_reanudacion"] if d(c[0]) <= d(t["E"]) < d(c[1])]
        ch = {"corte": cortes[0] if cortes else None, "reapertura_coincide": bool(cortes) and (t["apertura_texto"] in (None, cortes[0][1]))}
        if not cortes or not t["r"] > 0:
            problemas.append((t["id"], "regla 2 sin corte que contenga E"))
    elif trat == "regla_1_reutilizacion":
        cortes = [c for c in aud[x]["cortes_con_reanudacion"] if c[1] == t["reutilizacion_desde"]]
        ch = {"corte": cortes[0] if cortes else None}
        if not cortes:
            problemas.append((t["id"], "reutilización sin corte que termine en la fecha"))
    elif trat == D1:
        Lx, Fy = ultimo_activo(x), primer_activo(y)
        reus = [c for c in aud[x]["cortes_con_reanudacion"] if any(u.get("reutilizacion_desde") == c[1] and u["viejo_usdt"] == x for u in tabla)]
        if reus:                                                    # ticker reutilizado: fin del tramo del activo viejo
            Lx = d(reus[0][0])
        ch = {"ultimo_activo_viejo": Lx.isoformat(), "primer_activo_nuevo": Fy.isoformat(), "hueco_dias": (Fy - Lx).days - 1}
    t["chequeo_actividad"] = ch

# ----------------------------------------------------------------- clasificación de los 117 pares del barrido
CLASE = {}
for t in tabla:
    if t["nuevo_usdt"]:
        CLASE[(t["viejo_usdt"][:-4], t["nuevo_usdt"][:-4])] = t["tratamiento"]
AIRDROP = {("BTC", "BCD"), ("BTC", "BCX"), ("BTC", "SBTC"), ("BCH", "BCHA"), ("BCC", "BCHSV"), ("EOS", "ADD"), ("EOS", "ATD"),
           ("EOS", "EON"), ("EOS", "EOP"), ("EOS", "IQ"), ("NEO", "ONT"), ("THETA", "TFUEL"), ("TRX", "BTT"), ("WIN", "TRX"),
           ("QTUM", "QI"), ("STEEM", "HIVE"), ("BTS", "NBS"), ("OGN", "OGV"), ("OMG", "BOBA"), ("XEM", "XYM"), ("XRP", "FLR"),
           ("XVS", "VRT"), ("NULS", "NVT"), ("PUNDIX", "PURSE"), ("MTL", "XPR"), ("LUNA", "LUNA"), ("LUNC", "LUNA"),
           ("UST", "LUNA"), ("USTC", "LUNA")}
CONVERSION_AL_RETIRAR = {("BEAR", "BUSD"), ("BULL", "BUSD"), ("BNBBEAR", "BUSD"), ("BNBBULL", "BUSD"), ("EOSBEAR", "BUSD"),
                         ("EOSBULL", "BUSD"), ("ETHBEAR", "BUSD"), ("ETHBULL", "BUSD"), ("XRPBEAR", "BUSD"), ("XRPBULL", "BUSD"),
                         ("USDS", "BUSD"), ("DGD", "ETH")}
PARTE_DE = {("BNX", "BNX"): "BNXUSDT regla_2", ("BNX", "BNXOLD"): "BNXUSDT regla_2", ("BNXOLD", "BNX"): "BNXUSDT regla_2",
            ("BTT", "BTTOLD"): "BTT→BTTC", ("SUN", "SUN"): "SUNUSDT regla_2", ("SUN", "SUNOLD"): "SUNUSDT regla_2",
            ("SUNOLD", "SUN"): "SUNUSDT regla_2", ("QUICK", "QUICK"): "QUICKUSDT regla_2", ("STRAX", "STRAX"): "STRAXUSDT regla_2",
            ("VIDT", "VIDT"): "VIDTUSDT regla_2", ("WBETH", "BETH"): "BETH→WBETH", ("UST", "WUST"): "UST→USTC",
            ("BCC", "BCHABC"): "bifurcación BCC",
            ("PHB", "PHB"): "redenominación 100:1 de 2022 anterior al primer día de PHBUSDT (2022-11-18): no hay serie USDT que ajustar"}
for (x, y), v in PARTE_DE.items():
    CLASE.setdefault((x, y), "parte_de: " + v)
clasif, sin_clase = [], []
for p in json.loads((AQUI / "barrido_renombres.json").read_text())["pares"]:
    k = (p["viejo"], p["nuevo"])
    xu, yu = p["viejo_usdt_en_panel"], p["nuevo_usdt_en_panel"]
    if k in CLASE:
        c = CLASE[k]
    elif k in AIRDROP:
        c = "airdrop_o_bifurcacion: el viejo sigue cotizando; no es renombre"
    elif k in CONVERSION_AL_RETIRAR:
        c = "conversion_al_retirar: salida del viejo; no es renombre"
    elif p["viejo"] == p["nuevo"] and (p["relaciones_nuevo_por_viejo"] in ([], [1.0])):
        c = "canje_mismo_simbolo_r1: sin mapeo (regla 2 exige r ≠ 1)"
    elif re.search(r"OLD$|V1$", p["viejo"]) or p["viejo"] in ("KNCL", "XDATA", "TUSDB", "BTCB", "REPV1") or (not xu and k[1] in ("REP", "DATA", "KNC", "TUSD", "BTC")):
        c = "canje_mismo_simbolo_r1: el viejo renombrado sin par USDT; el par USDT del nuevo símbolo sigue (r = 1)"
    elif not xu:
        c = "sin_par_usdt_del_viejo: el nuevo es un listado nuevo; no hay listado de X que continuar"
    elif not yu:
        c = "sin_par_usdt_del_nuevo: no hay Y en el panel (renombre del viejo para su retiro, o airdrop)"
    else:
        c = None
        sin_clase.append(k)
    clasif.append({"viejo": p["viejo"], "nuevo": p["nuevo"], "clase": c, "frase": p["frases"][0][:200]})
if sin_clase:
    problemas.append(("barrido", f"pares sin clasificar: {sin_clase}"))

# ----------------------------------------------------------------- salidas
aplica = [t for t in tabla if t["tratamiento"] in ("regla_1", "regla_2", "regla_1_reutilizacion")]
mapeos = []
for t in sorted(aplica, key=lambda t: (t["E"] or t["reutilizacion_desde"], t["viejo_usdt"])):
    m = {"id": t["id"], "regla": {"regla_1": 1, "regla_2": 2, "regla_1_reutilizacion": "1R"}[t["tratamiento"]],
         "viejo_usdt": t["viejo_usdt"], "nuevo_usdt": t["nuevo_usdt"], "r": t["r"], "E": t["E"],
         "fuente": t["evidencia"][0]["archivo"], "cita": t["evidencia"][0]["cita"]}
    if t["tratamiento"] == "regla_1_reutilizacion":
        m["reutilizacion_desde"] = t["reutilizacion_desde"]
    mapeos.append(m)
(OUT / "TABLA_RENOMBRES_COMPLETA.json").write_text(json.dumps({"tabla": tabla, "problemas": problemas}, ensure_ascii=False, indent=1))
(OUT / "mapeos_adenda1_completa.json").write_text(json.dumps(
    {"_nota": "Tabla completa de la Adenda 1 (reglas 1, 1R y 2) para el orquestador v3. Generada por construir_tabla.py; "
              "GTO→GFT, LUNA→LUNC y UST→USTC NO se mapean (lectura literal de la regla 1; decisión D-1 pendiente).",
     "mapeos": mapeos}, ensure_ascii=False, indent=1))
(OUT / "clasificacion_barrido.json").write_text(json.dumps(clasif, ensure_ascii=False, indent=1))
cuenta = {}
for t in tabla:
    cuenta[t["tratamiento"]] = cuenta.get(t["tratamiento"], 0) + 1
print("entradas:", len(tabla), cuenta)
print("mapeos aplicados por el v3:", len(mapeos), "· citas verificadas:", sum(len(t["evidencia"]) for t in tabla),
      "· pares del barrido clasificados:", len(clasif))
print("PROBLEMAS:", problemas if problemas else "ninguno")
