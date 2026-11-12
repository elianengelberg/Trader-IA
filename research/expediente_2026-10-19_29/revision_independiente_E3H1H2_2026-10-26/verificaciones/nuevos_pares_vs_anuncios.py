"""Control enfocado en A: cada par USDT cuyo primer episodio empieza en [2022-11-16, 2024-11-06] (su edad importa dentro de A)
se busca en los CUERPOS archivados junto a palabras de canje/rebranding. Solo episodios de actividad y textos; sin precios.
Uso: python -I nuevos_pares_vs_anuncios.py <dir_E3> <mapeos_adenda1.json> <salida.json>"""
import json, re, sys
from pathlib import Path
E3, MAP, SAL = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
aud = json.loads((E3 / "resultados/calidad/auditoria_por_simbolo.json").read_text())
mapeados_nuevo = {m["nuevo_usdt"] for m in json.loads(MAP.read_text())["mapeos"] if m["regla"] == 1}
nuevos = sorted((a["episodios"][0][0], a["simbolo"]) for a in aud if a.get("episodios") and "2022-11-16" <= a["episodios"][0][0] <= "2024-11-06")
FIN = ("Thanks for your support", "Binance Team", "Latest Articles", "Related Articles")
CLAVE = r"(?:token swap|rebrand|renam|redenominat|ticker|migration)"
cuerpos = []
for f in sorted((E3 / "datos_anuncios/commoncrawl/paginas").glob("*.json")):
    t = re.sub(r"\s+", " ", json.loads(f.read_text()).get("texto", "")); i = t.find("Fellow Binancians")
    if i < 0:
        continue
    c = t[i:]; js = [c.find(m) for m in FIN if c.find(m) > 0]
    cuerpos.append((f.name, c[:min(js)] if js else c))
out = []
for ini, s in nuevos:
    b = s[:-4]
    rx = re.compile(rf"[^.]{{0,220}}\({re.escape(b)}\)[^.]{{0,220}}" if len(b) > 1 else r"$^")
    hits = []
    for a, c in cuerpos:
        for m in rx.finditer(c):
            frag = m.group(0)
            if re.search(CLAVE, frag, re.I) and re.search(rf"\bto [^.(]{{0,60}}\({re.escape(b)}\)|ratio of [^.]{{0,40}}{re.escape(b)}|assume the ticker of {re.escape(b)}", frag):
                hits.append({"archivo": a, "frag": frag[:420]})
    if hits:
        out.append({"nuevo": s, "primer_activo": ini, "mapeado": s in mapeados_nuevo, "evidencia": hits[:2]})
SAL.write_text(json.dumps({"nuevos_revisados": len(nuevos), "con_anuncio_de_canje": out}, ensure_ascii=False, indent=1))
print("pares nuevos revisados:", len(nuevos), "· con anuncio archivado de canje/rebranding:", len(out))
for o in out:
    print(f"- {o['nuevo']:<14} desde {o['primer_activo']} mapeado={o['mapeado']} | {o['evidencia'][0]['frag'][:300]}")
