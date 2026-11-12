"""E3 · Adenda 3, A3.11: construye `resoluciones_manuales.json` para la segunda pasada de `conciliacion.py` (congelado).

Cada resolución lleva una cita del texto archivado local. Antes de escribir, el script verifica que cada cita
aparezca literalmente (con los espacios normalizados) en alguna página archivada asociada al caso; si una falta, aborta.
Solo lee textos de anuncios y listas de la primera pasada: ningún precio, ningún retorno.

Uso: python -I construir_resoluciones.py <dir_ejecucion_E3> <clasificacion_renombres.json> <salida.json>
"""
import glob
import json
import re
import sys
from pathlib import Path

E3, REN, SALIDA = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
CC = E3 / "datos_anuncios" / "commoncrawl"
P1 = E3 / "resultados" / "conciliacion_pasada1"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


paginas = {}
for f in sorted(glob.glob(str(CC / "paginas" / "*.json"))):
    d = json.loads(Path(f).read_text())
    paginas.setdefault(d["url"], []).append({"archivo": Path(f).name, "texto": norm(d.get("texto", "")),
                                             "warc": d.get("url_archivada"), "captura": d.get("captura")})

eventos_p1 = {e["clave"]: e for e in json.loads((P1 / "eventos.json").read_text())}
rev_p1 = json.loads((P1 / "revision_manual.json").read_text())


def fuente(urls, cita):
    """Devuelve la primera página (de las URL dadas) que contiene la cita; si ninguna la contiene, aborta."""
    c = norm(cita)
    for u in urls:
        for p in paginas.get(u, []):
            if c in p["texto"]:
                return {"url": u, "archivo": p["archivo"], "warc": p["warc"], "captura": p["captura"]}
    raise SystemExit(f"CITA NO ENCONTRADA en {urls}: {cita!r}")


# ---------------------------------------------------------------- eventos (55 claves; se revisaron todas)
CONF, CORR, CEXP, DESC = "confirmar", "fecha_corregida", "C_explicada", "descartar"
FTX = "and will stop trading at 2020/03/31 10:00 AM (UTC)"
DEC = {
    "CLOAKUSDT|2019-02-22": (CONF, None, "for the following coins and tokens on 2019/02/22 at 10:00 AM UTC: CloakCoin (CLOAK) Modum (MOD) SALT (SALT) Substratum (SUB) Wings (WINGS)"),
    "MODUSDT|2019-02-22": (CONF, None, "for the following coins and tokens on 2019/02/22 at 10:00 AM UTC: CloakCoin (CLOAK) Modum (MOD) SALT (SALT) Substratum (SUB) Wings (WINGS)"),
    "SALTUSDT|2019-02-22": (CONF, None, "for the following coins and tokens on 2019/02/22 at 10:00 AM UTC: CloakCoin (CLOAK) Modum (MOD) SALT (SALT) Substratum (SUB) Wings (WINGS)"),
    "SUBUSDT|2019-02-22": (CONF, None, "for the following coins and tokens on 2019/02/22 at 10:00 AM UTC: CloakCoin (CLOAK) Modum (MOD) SALT (SALT) Substratum (SUB) Wings (WINGS)"),
    "WINGSUSDT|2019-02-22": (CONF, None, "for the following coins and tokens on 2019/02/22 at 10:00 AM UTC: CloakCoin (CLOAK) Modum (MOD) SALT (SALT) Substratum (SUB) Wings (WINGS)"),
    "BCHSVUSDT|2019-04-22": (CONF, None, "for the following coin on 2019/04/22 at 10:00 AM UTC: Bitcoin SV (BCHSV)"),
    **{f"{p}USDT|2020-03-31": (CONF, None, FTX) for p in ("BEAR", "BNBBEAR", "BNBBULL", "BULL", "EOSBEAR", "EOSBULL",
                                                         "ETHBEAR", "ETHBULL", "XRPBEAR", "XRPBULL")},
    "MCOUSDT|2020-10-23": (CONF, None, "Binance will remove and cease trading on the following trading pairs at 2020/10/23 12:00 PM (UTC): BTS/BUSD, MCO/BTC, MCO/USDT"),
    "HCUSDT|2020-11-10": (CONF, None, "Binance will remove and cease trading on the following trading pairs at 2020/11/10 12:00 PM (UTC): AION/BUSD, DCR/BUSD, EVX/ETH, HC/USDT"),
    "BKRWUSDT|2021-02-19": (DESC, None, "This announcement has been updated on 2021-02-20 to correct the BKRW/USDT trading pair to the USDT/BKRW trading pair"),
    "HNTUSDT|2022-10-14": (CONF, None, "Binance will remove and cease trading on the following trading pairs at 2022-10-14 03:00 (UTC) : Spot Pairs : HNT/BTC, HNT/USDT"),
    "FTTUSDT|2022-11-15": (CONF, None, "Binance will remove and cease trading on the following trading pairs at 2022-11-15 04:30 (UTC) : Spot Pairs : FTT/BNB, FTT/BTC, FTT/ETH and FTT/USDT"),
    "AUTOUSDT|2023-04-18": (CONF, None, "for the following tokens at 2023-04-18 03:00 (UTC) : Kepple (QLC) Neblio (NEBL) Auto"),
    "NEBLUSDT|2023-04-18": (CONF, None, "for the following tokens at 2023-04-18 03:00 (UTC) : Kepple (QLC) Neblio (NEBL) Auto"),
    "DOTDOWNUSDT|2023-04-27": (CORR, "2023-05-10", "At 2023-05-10 06:00 (UTC) : DOTUP, DOTDOWN"),
    "DOTUPUSDT|2023-04-27": (CORR, "2023-05-10", "At 2023-05-10 06:00 (UTC) : DOTUP, DOTDOWN"),
    "TRXDOWNUSDT|2023-04-27": (CORR, "2023-05-09", "At 2023-05-09 06:00 (UTC) : TRXUP, TRXDOWN"),
    "LINKUPUSDT|2023-04-27": (CORR, "2023-05-11", "At 2023-05-11 06:00 (UTC) : LINKUP, LINKDOWN"),
    "AUDUSDT|2023-06-01": (CONF, None, "Binance will remove and cease trading on the following spot trading pairs at 2023-06-01 06:00 (UTC): Spot Pairs: ADA/AUD, AUD/BUSD, AUD/USDT"),
    "YFIIUSDT|2023-08-22": (CONF, None, "for the following tokens at 2023-08-22 03:00 (UTC) : Sonm (SNM) Serum (SRM) DFI.Mone"),
    **{f"{p}USDT|2023-09-22": (CEXP, None, "Binance will open trading for the ARK/USDT, CREAM/USDT, FTT/USDT, GFT/USDT, IQ/USDT")
       for p in ("ARK", "CREAM", "FTT", "GFT", "IQ")},
    **{f"{p}USDT|2023-12-07": (CONF, None, "for the following token(s) at 2023-12-07 03:00 (UTC) : BitShares (BTS) PERL.eco (PER")
       for p in ("BTS", "PERL", "WTC")},
    **{f"{p}USDT|2024-02-20": (CONF, None, "for the following token(s) at 2024-02-20 03:00 (UTC) : Aragon (ANT) Multichain (MULT")
       for p in ("ANT", "MULTI", "XMR")},
    **{f"{p}USDT|2024-07-22": (CONF, None, "on all spot trading pairs for the following token(s) at 2024-07-22 03:00 (UTC) : BarnBridge (BOND) Dock (")
       for p in ("BOND", "DOCK", "MDX", "POLS")},
    **{f"{p}USDT|2024-11-06": (CONF, None, "on all spot trading pairs for the following token(s) at 2024-11-06 03:00 (UTC) : Rupiah Token (IDRT) Keep")
       for p in ("KP3R", "OOKI", "UNFI")},
}
JUST = {
    CONF: "El texto archivado fija la misma fecha de cese de la negociación spot que la primera pasada (N5).",
    CORR: "La primera pasada tomó la fecha del título (fecha de publicación, A3.1.5); el cuerpo fija el cese de la negociación del par en otra fecha. Se aplica N5: E = día UTC en que cesa la negociación spot según el texto.",
    CEXP: "A3.5 (b): el texto agrega (abre) el par USDT en esa fecha; lo que remueve son los pares BUSD. Relisting documentado; no es una exclusión del par USDT.",
    DESC: "El propio anuncio corrige el par: el removido es USDT/BKRW (otro símbolo), no BKRW/USDT. Error de identificación del par.",
}
eventos = {}
claves_sf = {k for k in eventos_p1 if k.endswith("|sin_fecha")}
faltan = sorted(set(eventos_p1) - set(DEC) - claves_sf)
if faltan:
    raise SystemExit(f"eventos sin resolución: {faltan}")
for k, (acc, E, cita) in DEC.items():
    e = eventos_p1[k]
    r = {"accion": acc, "cita": cita, "justificacion": JUST[acc], "fuente": fuente(e["urls"], cita),
         "categoria_pasada1": e["categoria"], "certeza": "alta"}
    if E:
        r["E"] = E
    eventos[k] = r

# ---------------------------------------------------------------- filas sin fecha (8 = 4 tokens × 2 URL)
sin_fecha = {}
CITA_SF = "for the following coins and tokens at 2018/10/12 10:00 AM (UTC)"
for e in rev_p1["sin_fecha"]:
    k = f"{e['par']}|{e['urls'][0]}"
    sin_fecha[k] = {"E": "2018-10-12", "cita": CITA_SF, "fuente": fuente(e["urls"], CITA_SF), "certeza": "alta",
                    "justificacion": "A3.4.1: el cuerpo fija el cese (fecha explícita). Ningún par USDT del token en el bucket: sigue fuera del universo por A3.3.2."}
if len(sin_fecha) != 8:
    raise SystemExit(f"se esperaban 8 filas sin fecha y hay {len(sin_fecha)}")

# ---------------------------------------------------------------- V-S2 (1 desacierto) y V-S3 (10 sorteados)
def fuente_titulo(sub_titulo, cita):
    urls = [u for u, ps in paginas.items() for p in ps if sub_titulo in p["texto"][:400]]
    return fuente(urls, cita)


vs2 = {}
for x in rev_p1["V_S2_desaciertos"]:
    c_lis = "ETHBEAR/USDT and ETHBULL/BUSD trading pairs at 2020/01/17 12:00 PM (UTC)"
    c_halt = "ETHBEAR/USDT and ETHBEAR/BUSD trading pairs at 2020/02/03 10:00 AM (UTC)"
    vs2[x["clave"]] = {
        "revision": "Sin corrección. El texto de listado es correcto (apertura 2020-01-17); el primer día activo del bucket es 2020-02-03 porque hubo una suspensión documentada en otro anuncio archivado (reanudación 2020-02-03). El par y la fecha extraídos no estaban mal, así que A3.6 no permite corregir: sigue siendo un desacierto (49/50 = 98 % ≥ 95 %).",
        "cita": c_lis, "fuente": fuente([x["url"]], c_lis),
        "cita_reanudacion": c_halt, "fuente_reanudacion": fuente_titulo("Binance Will Resume Trading for ETHBULL/USDT", c_halt),
        "certeza": "alta"}
# V-S3: la muestra de A3.6 es la de la primera pasada (10). El código congelado vuelve a sortear con la misma semilla sobre el
# universo de la segunda pasada, que cambia de orden y de tamaño; como se releyeron los 47 eventos, se registra la revisión de todos
# y se marca cuáles eran la muestra original.
muestra_p1 = {x["clave"] for x in rev_p1["V_S3"]}
if len(muestra_p1 & set(DEC)) != 10:
    raise SystemExit("V-S3 incompleto")
vs3 = {k: {"muestra_pasada1": k in muestra_p1, "par_ok": acc != DESC, "categoria_pasada1": eventos_p1[k]["categoria"],
           "resultado": acc, "E_texto": E or k.split("|")[1], "cita": cita}
       for k, (acc, E, cita) in DEC.items()}

# ---------------------------------------------------------------- renombres mapeados (Adenda 1, regla 1: cambio de símbolo con par USDT)
cls = json.loads(REN.read_text())
renombres = [{"viejo": m["viejo_usdt"], "nuevo": m["nuevo_usdt"], "E": m["E"], "relacion_nuevas_por_vieja": m["r"],
              "cita": m["cita"], "fuente": m["fuente"], "certeza": m["certeza"]}
             for m in cls["mapeos"] if m["regla"] == 1]

salida = {
    "_nota": "Segunda pasada A3.11. Claves y acciones con el formato que lee conciliacion.py (6f764845…). Las secciones que empiezan con «_» son solo documentación: el código no las lee.",
    "eventos": eventos, "sin_fecha": sin_fecha, "tokens_sin_par": {}, "renombres": renombres, "vs2": vs2, "vs3": vs3,
}
SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=1))
print(json.dumps({"eventos": len(eventos), "sin_fecha": len(sin_fecha), "renombres": len(renombres), "vs2": len(vs2), "vs3": len(vs3),
                  "acciones": {a: sum(1 for r in eventos.values() if r["accion"] == a) for a in (CONF, CORR, CEXP, DESC)}}, ensure_ascii=False))
