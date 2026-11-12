"""E3 · A3: consulta del índice público de Common Crawl (data.commoncrawl.org) por rangos HTTP, sin el servidor de índices.

Common Crawl (ToU: licencia de acceso y uso con fines lícitos; investigación) publica para cada captura un `cluster.idx`
ordenado por clave SURT y los fragmentos `cdx-NNNNN.gz` (miembros gzip independientes). Aquí: bisección por rangos sobre
`cluster.idx` para un prefijo SURT, descarga de los bloques gzip necesarios y, aparte, de registros WARC concretos.
≤ 2 solicitudes/s; cada solicitud queda registrada (URL, rango, estado, bytes, sha256).
"""
import gzip
import hashlib
import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.request

BASE = "https://data.commoncrawl.org/"
UA = "Trader-IA-investigacion/0.1 (uso academico no comercial)"
CTX = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE"))
_lock = threading.Lock()
_sig = [0.0]


def _esperar(intervalo=0.5):
    with _lock:
        ahora = time.monotonic()
        t = max(ahora, _sig[0])
        _sig[0] = t + intervalo
    time.sleep(max(0.0, t - ahora))


def obtener(ruta: str, rango: tuple | None, registro: str, intentos=6) -> bytes:
    espera = 2.0
    for i in range(intentos):
        _esperar()
        h = {"User-Agent": UA}
        if rango:
            h["Range"] = f"bytes={rango[0]}-{rango[1]}"
        try:
            r = urllib.request.urlopen(urllib.request.Request(BASE + ruta, headers=h), context=CTX, timeout=90)
            b = r.read()
            with open(registro, "a") as f:
                f.write(json.dumps({"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "url": BASE + ruta, "rango": rango,
                                    "http": r.status, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}) + "\n")
            return b
        except urllib.error.HTTPError as e:
            with open(registro, "a") as f:
                f.write(json.dumps({"url": BASE + ruta, "rango": rango, "http": e.code, "intento": i + 1}) + "\n")
            if e.code == 404:
                raise
        except Exception as e:
            with open(registro, "a") as f:
                f.write(json.dumps({"url": BASE + ruta, "rango": rango, "error": type(e).__name__, "intento": i + 1}) + "\n")
        time.sleep(espera)
        espera *= 2
    raise RuntimeError(f"no se pudo obtener {ruta} {rango}")


def tamano(ruta: str, registro: str) -> int:
    _esperar()
    r = urllib.request.urlopen(urllib.request.Request(BASE + ruta, method="HEAD", headers={"User-Agent": UA}), context=CTX, timeout=60)
    return int(r.headers["Content-Length"])


def _linea_en(ruta, pos, registro, total):
    """Primera línea completa que empieza después de `pos` (o en 0)."""
    trozo = obtener(ruta, (pos, min(total - 1, pos + 16383)), registro)
    if pos > 0:
        j = trozo.find(b"\n")
        trozo = trozo[j + 1:]
    k = trozo.find(b"\n")
    return trozo[:k].decode("utf-8", errors="replace") if k >= 0 else None


def bloques_para_prefijo(crawl: str, prefijo: str, registro: str):
    """Líneas de cluster.idx que cubren el prefijo SURT: desde la última con clave < prefijo hasta la primera con clave > prefijo~."""
    ruta = f"cc-index/collections/{crawl}/indexes/cluster.idx"
    total = tamano(ruta, registro)
    lo, hi = 0, total
    while hi - lo > 32768:                                   # bisección en bytes
        mid = (lo + hi) // 2
        lin = _linea_en(ruta, mid, registro, total)
        if lin is None or lin.split(" ")[0] >= prefijo:
            hi = mid
        else:
            lo = mid
    trozo = obtener(ruta, (lo, min(total - 1, lo + 262143)), registro).decode("utf-8", errors="replace")
    lineas = trozo.split("\n")[1:-1] if lo > 0 else trozo.split("\n")[:-1]
    sel, previa = [], None
    for lin in lineas:
        clave = lin.split(" ")[0]
        if clave < prefijo:
            previa = lin
            continue
        if previa is not None and not sel:
            sel.append(previa)
        sel.append(lin)
        if clave > prefijo + "~":
            break
    if not sel and previa is not None:
        sel = [previa]
    out = []
    for lin in sel:
        partes = lin.split("\t")
        out.append({"clave": partes[0], "archivo": partes[1], "offset": int(partes[2]), "longitud": int(partes[3])})
    return out


def lineas_cdx(crawl: str, bloque: dict, prefijo: str, registro: str):
    ruta = f"cc-index/collections/{crawl}/indexes/{bloque['archivo']}"
    b = obtener(ruta, (bloque["offset"], bloque["offset"] + bloque["longitud"] - 1), registro)
    texto = gzip.decompress(b).decode("utf-8", errors="replace")
    res = []
    for lin in texto.split("\n"):
        if lin.startswith(prefijo):
            clave, ts, js = lin.split(" ", 2)
            res.append({"clave": clave, "timestamp": ts, **json.loads(js)})
    return res


def registro_warc(rec: dict, registro: str) -> bytes:
    off, ln = int(rec["offset"]), int(rec["length"])
    b = obtener(rec["filename"], (off, off + ln - 1), registro)
    return gzip.decompress(b)
