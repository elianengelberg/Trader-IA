"""Clasifica, con la función congelada `clasificar` (copia verificada de conciliacion.py 6f764845…), los pares que el texto
archivado excluye pero que la extracción omitió. Solo lee `estado` y la auditoría por símbolo; ningún precio.
Uso: python -B -I eventos_omitidos.py <dir_copia_congelada> <dir_ejecucion_E3> <salida.json>"""
import datetime as dt, hashlib, json, sys
from pathlib import Path
COPIA, E3, SAL = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
assert hashlib.sha256((COPIA / "conciliacion.py").read_bytes()).hexdigest().startswith("6f764845598b4ecf"), "copia alterada"
sys.path.insert(0, str(COPIA))
import conciliacion as C  # noqa: E402
usdt = set(json.loads((E3 / "datos_vision/listados/simbolos_usdt.json").read_text()))
aud = {a["simbolo"]: a for a in json.loads((E3 / "resultados/calidad/auditoria_por_simbolo.json").read_text())}
meses = {s: set(a.get("meses_con_archivo", [])) for s, a in aud.items()}
act, _ = C.cargar_actividad(E3 / "resultados/calidad")
CITA = ("Binance will delist and cease redemption for the TRXUP, TRXDOWN, DOTUP, DOTDOWN, LINKUP and LINKDOWN leveraged tokens at the "
        "following timings: At 2023-05-09 06:00 (UTC) : TRXUP, TRXDOWN At 2023-05-10 06:00 (UTC) : DOTUP, DOTDOWN At 2023-05-11 06:00 (UTC) : LINKUP, LINKDOWN")
FUENTE = "datos_anuncios/commoncrawl/paginas/url_https___www.binance.com_en_support_announcement_binance-to-delist-and-cease-_6079c69de2a3.json (captura 20240810193751)"
out = []
for par, E in (("TRXUPUSDT", "2023-05-09"), ("LINKDOWNUSDT", "2023-05-11")):
    cat, L = C.clasificar(par, dt.date.fromisoformat(E), act, meses, usdt, False)
    out.append({"par": par, "E": E, "en_bucket": par in usdt, "categoria": cat, "L": L, "episodios": aud.get(par, {}).get("episodios"),
                "meses_con_archivo_2022_2023": sorted(m for m in meses.get(par, set()) if m >= "2022-10"),
                "cita": CITA, "fuente": FUENTE,
                "motivo_omision": "La extracción generó eventos para TRXDOWN, DOTUP, DOTDOWN y LINKUP del mismo anuncio, pero no para TRXUP ni LINKDOWN."})
SAL.write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps(out, ensure_ascii=False, indent=1))
