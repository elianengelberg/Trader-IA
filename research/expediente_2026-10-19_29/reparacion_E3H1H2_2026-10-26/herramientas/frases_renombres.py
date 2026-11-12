"""Para cada candidato de renombre (164), frases clave del cuerpo archivado. Solo lectura; sin precios.
Uso: frases_renombres.py <dir_E3> <salida.txt>"""
import json, re, sys
E3, SAL = sys.argv[1], sys.argv[2]
ren = json.load(open(f"{E3}/datos_anuncios/commoncrawl/renombres_candidatos.json"))
clave = re.compile(r"\b\d[\d,]*\s*:\s*\d[\d,]*\b|ratio|rebrand|renam|redenominat|ticker|will be (?:changed|replaced)|"
                   r"suspend(?:ed)? trading|resume trading|open trading|halt|cease trading|delist|new token|old token|"
                   r"convert|swap ratio|\b1\s+[A-Z]{2,8}\s*=|=\s*\d", re.I)
vistos = {}
with open(SAL, "w") as out:
    for i in sorted(range(len(ren)), key=lambda i: (ren[i].get("publicado") or "", ren[i]["titulo"])):
        r = ren[i]; t = r["titulo"].split(" | ")[0].strip()
        if t in vistos:
            out.write(f"#{i:3d} (= #{vistos[t]}) {r.get('publicado')} {t}\n"); continue
        vistos[t] = i
        body = re.sub(r"\s+", " ", r.get("cuerpo") or "")
        frases = [s for s in re.split(r"(?<=[.!?])\s+", body) if clave.search(s)]
        out.write(f"#{i:3d} {r.get('publicado')} {t} | usdt={r.get('pares_usdt')}\n")
        for s in frases[:9]: out.write(f"      · {s[:300]}\n")
print("ok")
