"""Revisión independiente de los 22 mapeos (sin reutilizar el código del autor). Solo textos archivados, episodios de
actividad (auditoria_por_simbolo.json) y los saltos ya calculados por F3 (estructural.json). No abre ninguna serie.
Uso: python -I verificar_mapeos.py <dir_ejecucion_E3> <mapeos_adenda1.json> <salida.json>"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

E3, MAP, SAL = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
PAG = E3 / "datos_anuncios" / "commoncrawl" / "paginas"
aud = {a["simbolo"]: a for a in json.loads((E3 / "resultados/calidad/auditoria_por_simbolo.json").read_text())}
saltos = json.loads((E3 / "resultados/estructural/estructural.json").read_text())["cortes_con_reanudacion"]["lista_saltos"]
cand = {r["url"]: r for r in json.loads((E3 / "datos_anuncios/commoncrawl/renombres_candidatos.json").read_text())}


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def texto(fuente):
    if fuente.get("archivo") and (PAG / fuente["archivo"]).exists():
        return norm(json.loads((PAG / fuente["archivo"]).read_text()).get("texto", ""))
    raise SystemExit(f"fuente sin archivo local: {fuente}")


def num(s):
    return float(s.replace(",", ""))


RX_RATIO = [
    re.compile(r"ratio of (?:1 )?([\d,]+) (?:old )?([A-Z]{2,10})(?: \(Old\))? = ([\d,]+) (?:new )?([A-Z]{2,10})"),
    re.compile(r"rate of ([\d,]+) ([A-Z]{2,10}) = ([\d,]+) ([A-Z]{2,10})"),
    re.compile(r"\(i\.e\. ?, ([\d,]+) ([A-Z]{2,10}) = ([\d,]+) ([A-Z]{2,10}) \)"),
]
RX_PROP = re.compile(r"ratio of ([\d,]+):([\d,]+)")
FECHA = r"(20\d\d[-/]\d\d[-/]\d\d)"

out = []
for m in json.loads(MAP.read_text())["mapeos"]:
    t = texto(m["fuente"])
    x, y = m["viejo_usdt"][:-4], m["nuevo_usdt"][:-4]
    f = {"mapeo": f"{m['viejo_usdt']}→{m['nuevo_usdt']}", "regla": m["regla"], "r_tabla": m["r"], "E_tabla": m["E"],
         "apertura_tabla": m.get("apertura_segun_texto"), "cita_presente": norm(m["cita"]) in t}
    # relación, extraída de forma independiente
    rs = []
    for rx in RX_RATIO:
        for a, sa, b, sb in rx.findall(t):
            if sa in (x, y) and sb in (x, y):
                rs.append(num(b) / num(a))
    for a, b in RX_PROP.findall(t):
        rs.append((a, b))
    f["relaciones_en_texto"] = rs
    # fechas cercanas a «delist/halt/cease» del viejo y a «open» del nuevo
    ceses = re.findall(rf"(?:At )?{FECHA}[^.]{{0,40}}(?:Binance will )?(?:suspend and delist|delist|halt|cease)[^.]{{0,160}}\b{x}\b", t)
    ceses += re.findall(rf"(?:halted|halt trading|delist)[^.]{{0,200}}\b{x}\b[^.]{{0,120}}?at {FECHA}", t)
    aperturas = re.findall(rf"(?:At )?{FECHA}[^.]{{0,40}}trading will (?:then )?open for[^.]{{0,80}}\b{y}/", t)
    aperturas += re.findall(rf"open trading for[^.]{{0,120}}\b{y}/[^.]{{0,160}}at {FECHA}", t)
    aperturas += re.findall(rf"open for (?:the new )?{y}/[^.]{{0,160}}at {FECHA}", t)
    f["fechas_cese_en_texto"] = sorted({c.replace("/", "-") for c in ceses})
    f["fechas_apertura_en_texto"] = sorted({a.replace("/", "-") for a in aperturas})
    # actividad (episodios), sin precios
    av, an = aud.get(m["viejo_usdt"], {}), aud.get(m["nuevo_usdt"], {})
    E = dt.date.fromisoformat(m["E"])
    if m["regla"] == 1:
        fin_v = [e[1] for e in av.get("episodios", []) if e[1] <= m["E"]]
        ini_n = [e[0] for e in an.get("episodios", []) if e[0] >= (E - dt.timedelta(days=1)).isoformat()]
        f["ultimo_activo_viejo"], f["primer_activo_nuevo"] = (max(fin_v) if fin_v else None), (min(ini_n) if ini_n else None)
        f["viejo_vuelve_despues_de_E"] = any(e[0] > m["E"] for e in av.get("episodios", []))
        f["nuevo_activo_antes_de_E"] = any(e[0] < m["E"] and e[1] >= (E - dt.timedelta(days=400)).isoformat() and e[0] < (f["ultimo_activo_viejo"] or "")
                                           for e in an.get("episodios", []))
    else:
        c = [k for k in av.get("cortes_con_reanudacion", []) if k[0] <= m["E"] <= k[1]]
        f["corte_en_datos"] = c[0] if c else None
        s = [z for z in saltos if z["simbolo"] == m["viejo_usdt"] and z["ultimo_activo"] <= m["E"] <= z["reanuda"]]
        f["ratio_precio_F3"] = s[0]["ratio_precio"] if s else None
        f["coherente_con_F3"] = (s[0]["ratio_precio"] * float(m["r"]) if s else None)  # ≈ 1 si r es correcto
    out.append(f)
SAL.write_text(json.dumps(out, indent=1, ensure_ascii=False))
for f in out:
    print(json.dumps(f, ensure_ascii=False)[:420])
