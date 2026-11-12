"""E3 · A3 con Common Crawl (Enmienda 2, E2.1). Etapas:
  indice   <dir>   índice de todas las capturas 2017-06…2026-06 para los tres prefijos SURT
  paginas  <dir>   selección de URL únicas (captura con HTTP 200 más antigua) y descarga de sus registros WARC (texto extraído)
Uso: python -I cc_anuncios.py <etapa> <dir_anuncios>
"""
import concurrent.futures as cf
import hashlib
import html
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cc_indice as cc  # noqa: E402

PREFIJOS = ["com,binance)/en/support/announcement", "com,binance,support)/hc/en-us/articles", "com,zendesk,binance)/hc/en-us/articles"]


def capturas(d: Path):
    txt = cc.obtener("crawl-data/index.html", None, str(d / "registro_cc.jsonl")).decode("utf-8", errors="replace")
    (d / "crawl_data_index.html").write_text(txt)
    ids = sorted(set(re.findall(r"CC-MAIN-(\d{4})-(\d{2})", txt)))
    return [f"CC-MAIN-{y}-{w}" for y, w in ids if "2017" <= y <= "2026"]


def indice(d: Path):
    reg = str(d / "registro_cc.jsonl")
    (d / "indice").mkdir(exist_ok=True)
    crawls = capturas(d)
    print("capturas:", len(crawls), crawls[0], crawls[-1], flush=True)
    resumen = {}
    for c in crawls:
        dest = d / "indice" / f"{c}.json"
        if dest.exists():
            continue
        filas = []
        for p in PREFIJOS:
            try:
                bl = cc.bloques_para_prefijo(c, p, reg)
                for b in bl:
                    filas += cc.lineas_cdx(c, b, p, reg)
            except Exception as e:  # se registra y se sigue
                filas.append({"error": f"{type(e).__name__}: {str(e)[:150]}", "prefijo": p})
        dest.write_text(json.dumps(filas))
        resumen[c] = {p: sum(1 for f in filas if f.get("clave", "").startswith(p)) for p in PREFIJOS}
        print(c, resumen[c], flush=True)
    (d / "resumen_indice.json").write_text(json.dumps(resumen, indent=1))


def clave_url(u: str) -> str:
    u = u.split("?")[0].split("#")[0].lower().replace("http://", "https://")
    m = re.search(r"/announcement/(?:detail/)?([0-9a-f]{32})", u)
    if m:
        return "bn:" + m.group(1)
    m = re.search(r"/articles/(\d+)", u)
    if m:
        return "zd:" + m.group(1)
    return "url:" + u


def texto_de(html_crudo: str) -> dict:
    t = re.findall(r"<title[^>]*>(.*?)</title>", html_crudo, flags=re.S)
    h1 = re.findall(r"<h1[^>]*>(.*?)</h1>", html_crudo, flags=re.S)
    cuerpo = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html_crudo, flags=re.S)
    plano = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cuerpo))).strip()
    jtit = re.findall(r'"title"\s*:\s*"([^"]{8,300})"', html_crudo)
    fechas_pub = re.findall(r'"(?:publishDate|releaseDate|publish_date)"\s*:\s*(\d{10,13})', html_crudo)
    tdt = re.findall(r'<time[^>]*datetime="([^"]+)"', html_crudo)
    titulo = (html.unescape(re.sub(r"<[^>]+>", " ", h1[0])).strip() if h1 else "") or (html.unescape(t[0]).strip() if t else "") or (jtit[0] if jtit else "")
    return {"titulo": re.sub(r"\s+", " ", titulo)[:400], "publicado_ms": fechas_pub[0] if fechas_pub else None,
            "time_datetime": tdt[0] if tdt else None, "texto": plano[:60000]}


def nombre_archivo(k: str) -> str:
    """Corrección (2026-10-20): el nombre truncado a 120 caracteres colisionaba entre URL largas; se agrega un hash de la clave."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", k)[:80] + "_" + hashlib.sha1(k.encode()).hexdigest()[:12] + ".json"


def renombrar(d: Path):
    """Renombra las páginas ya descargadas según la clave de SU PROPIA url (campo interno) y borra las que no corresponden."""
    out_dir = d / "paginas"
    n = 0
    for f in sorted(out_dir.glob("*.json")):
        p = json.loads(f.read_text())
        nuevo = out_dir / nombre_archivo(clave_url(p["url"]))
        if nuevo != f:
            f.rename(nuevo)
            n += 1
    print("renombradas:", n, "archivos:", len(list(out_dir.glob("*.json"))), flush=True)


def paginas(d: Path):
    reg = str(d / "registro_cc.jsonl")
    todas = {}
    for f in sorted((d / "indice").glob("*.json")):
        for r in json.loads(f.read_text()):
            if r.get("status") != "200" or "filename" not in r:
                continue
            if "html" not in r.get("mime", "") and "html" not in r.get("mime-detected", ""):
                continue
            k = clave_url(r["url"])
            if k not in todas or r["timestamp"] < todas[k]["timestamp"]:
                todas[k] = r
    (d / "urls_unicas.json").write_text(json.dumps(todas))
    print("URL únicas (HTTP 200, html):", len(todas), {p: sum(1 for k in todas if k.startswith(p)) for p in ("bn:", "zd:", "url:")}, flush=True)
    out_dir = d / "paginas"
    out_dir.mkdir(exist_ok=True)

    def una(item):
        k, r = item
        dest = out_dir / nombre_archivo(k)
        if dest.exists():
            return k, "ya"
        try:
            w = cc.registro_warc(r, reg)
            partes = w.split(b"\r\n\r\n", 2)
            cuerpo = partes[2] if len(partes) == 3 else w
            info = texto_de(cuerpo.decode("utf-8", errors="replace"))
            info.update({"url": r["url"], "captura": r["timestamp"], "warc": r["filename"], "offset": r["offset"], "length": r["length"],
                         "url_archivada": f"https://data.commoncrawl.org/{r['filename']} bytes={r['offset']}-{int(r['offset']) + int(r['length']) - 1}"})
            dest.write_text(json.dumps(info, ensure_ascii=False))
            return k, "ok"
        except Exception as e:
            return k, f"error {type(e).__name__}"
    res = {}
    with cf.ThreadPoolExecutor(3) as ex:
        for i, (k, st) in enumerate(ex.map(una, sorted(todas.items()))):
            res[k] = st
            if (i + 1) % 250 == 0:
                print(i + 1, "/", len(todas), flush=True)
    (d / "resultado_paginas.json").write_text(json.dumps(res, indent=0))
    print("páginas:", {s: list(res.values()).count(s) for s in set(res.values())}, flush=True)


if __name__ == "__main__":
    etapa, d = sys.argv[1], Path(sys.argv[2])
    d.mkdir(parents=True, exist_ok=True)
    {"indice": indice, "paginas": paginas, "renombrar": renombrar}[etapa](d)
