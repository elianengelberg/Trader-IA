"""Busca renombres, redenominaciones o canjes con cambio de ticker que la extracción no clasificó como «renombre».
Recorre los títulos y los cuerpos de todas las páginas clasificadas con otro tipo. Solo lectura; sin precios.
Uso: renombres_omitidos.py <dir_E3> <salida.txt>"""
import json, re, sys, collections
E3, SAL = sys.argv[1], sys.argv[2]
cl = json.load(open(f"{E3}/datos_anuncios/commoncrawl/anuncios_clasificados.json"))
rx_tit = re.compile(r"rebrand|renam|redenominat|ticker|token swap|token migration|contract swap|mainnet swap|token split|"
                    r"migration plan|swap plan|will be changed to|change of (?:token|ticker)", re.I)
rx_cuerpo = re.compile(r"(?:will (?:assume|adopt) the ticker|ticker (?:will be )?(?:changed|updated|renamed) (?:from|to)|"
                       r"rebrand(?:ed|ing)? (?:to|as)|renamed (?:to|as)|redenominat\w+|at a ratio of 1[ ,]?[\d,]* ?[A-Z]{2,10} ?= ?[\d,]+)", re.I)
por_tit = collections.OrderedDict()
for c in sorted(cl, key=lambda c: (str(c.get("publicado") or ""), c["titulo"])):
    if c["tipo"] == "renombre":
        continue
    t = c["titulo"].split(" | ")[0].strip()
    cuerpo = re.sub(r"\s+", " ", c.get("cuerpo") or "")
    m_t, m_c = rx_tit.search(t), rx_cuerpo.search(cuerpo)
    if not (m_t or m_c):
        continue
    if t in por_tit:
        por_tit[t]["urls"].append(c["url"]); continue
    frag = cuerpo[max(0, m_c.start() - 160):m_c.end() + 200] if m_c else ""
    por_tit[t] = {"tipo": c["tipo"], "publicado": c.get("publicado"), "urls": [c["url"]], "por_titulo": bool(m_t), "frag": frag}
with open(SAL, "w") as out:
    out.write(f"{len(por_tit)} títulos no clasificados como renombre con señales de renombre/canje/redenominación\n")
    for t, v in por_tit.items():
        out.write(f"- {v['publicado']} [{v['tipo']}] {'T' if v['por_titulo'] else 'c'} {t[:150]} ({len(v['urls'])} url)\n")
        if v["frag"]:
            out.write(f"      …{v['frag'][:420]}…\n")
print(len(por_tit))
