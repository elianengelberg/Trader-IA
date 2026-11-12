"""E4 v1 · Recolector por rango de días (NO calcula nada: no abre los ZIP). Requiere autorización para correr con la fuente real.
Para cada símbolo XUSDT de `data/spot/daily/klines/` y cada intervalo (1d y 1h), averigua con el listado S3 qué días existen,
baja `XUSDT-<iv>-D.zip` y su `.CHECKSUM` oficial, verifica el sha256 y guarda `destino/D/<iv>/XUSDT.zip` (+ `.CHECKSUM`).
Al terminar cada día escribe `destino/D/MANIFIESTO.sha256` (todos los ZIP del día) y anexa al registro encadenado
`destino/REGISTRO.jsonl` una línea RECOLECCION con el sha256 del manifiesto. Nunca reescribe un ZIP guardado.
Un ZIP cuyo sha256 no coincide con su .CHECKSUM no se guarda y se registra (CHECKSUM_DISTINTO): ese par-día queda faltante.
Errores: un archivo que no figura en el listado no se pide (el par no operó ese día); cualquier fallo de red, tras 3 reintentos,
cuenta como error, el día queda con `errores > 0` y el proceso termina con código 2 (hay que volver a correrlo; el evaluador
rechaza días con errores). Pausa entre pedidos (términos de Binance Vision §7). Fuente de prueba: file://<dir>.
Uso: python3 -I -B recolector.py --fuente <url|file://dir> --desde YYYY-MM-DD --hasta YYYY-MM-DD --destino <dir> --protegidos <tsv>"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guarda_rutas as G  # noqa: E402

PREFIJO = "data/spot/daily/klines/"
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?"
INTERVALOS = ("1d", "1h")
PAUSA_S = 0.2
REINTENTOS = 3


class Ausente(Exception):
    pass


def leer(url, pausa, timeout=60):
    if url.startswith("file://"):
        p = url[len("file://"):]
        if not os.path.exists(p):
            raise Ausente(url)
        with open(p, "rb") as f:
            return f.read()
    ultimo = None
    for k in range(REINTENTOS):
        time.sleep(pausa * (2 ** k))
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise Ausente(url)
            ultimo = e
        except Exception as e:  # noqa: BLE001  (red: se reintenta)
            ultimo = e
    raise RuntimeError(f"{url}: {ultimo}")


def _s3(q, pausa):
    raiz = ET.fromstring(leer(S3 + urllib.parse.urlencode(q), pausa))
    return raiz, {"s": raiz.tag.split("}")[0].strip("{")}


def listar_simbolos(fuente, pausa):
    if fuente.startswith("file://"):
        return sorted(json.loads(leer(fuente.rstrip("/") + "/LISTADO.json", 0)))
    simbolos, token = [], None
    while True:
        q = {"delimiter": "/", "prefix": PREFIJO, "list-type": "2"}
        if token:
            q["continuation-token"] = token
        raiz, ns = _s3(q, pausa)
        simbolos += [p.text[len(PREFIJO):].strip("/") for p in raiz.findall("s:CommonPrefixes/s:Prefix", ns)]
        nxt = raiz.find("s:NextContinuationToken", ns)
        if nxt is None:
            break
        token = nxt.text
    return sorted(s for s in simbolos if re.fullmatch(r"[A-Z0-9]{2,20}USDT", s))


def dias_existentes(fuente, simbolo, iv, meses, dias, pausa):
    """Días del rango para los que existe el archivo (listado S3 por mes; en file://, existencia en disco)."""
    if fuente.startswith("file://"):
        base = fuente[len("file://"):].rstrip("/")
        return {d for d in dias if os.path.exists(f"{base}/{simbolo}/{iv}/{simbolo}-{iv}-{d}.zip")}
    out = set()
    for m in meses:
        token = None
        while True:
            q = {"list-type": "2", "prefix": f"{PREFIJO}{simbolo}/{iv}/{simbolo}-{iv}-{m}"}
            if token:
                q["continuation-token"] = token
            raiz, ns = _s3(q, pausa)
            for c in raiz.findall("s:Contents", ns):
                k = c.find("s:Key", ns).text
                if k.endswith(".zip"):
                    out.add(k.rsplit(f"-{iv}-", 1)[1][:-4])
            nxt = raiz.find("s:NextContinuationToken", ns)
            if nxt is None:
                break
            token = nxt.text
    return out & set(dias)


def url_archivo(fuente, simbolo, iv, dia):
    if fuente.startswith("file://"):
        return f"{fuente.rstrip('/')}/{simbolo}/{iv}/{simbolo}-{iv}-{dia}.zip"
    return f"{fuente.rstrip('/')}/{PREFIJO}{simbolo}/{iv}/{simbolo}-{iv}-{dia}.zip"


def anexar(reg, fila):
    prev = "0" * 64
    if os.path.exists(reg):
        with open(reg, "rb") as f:
            lineas = f.read().splitlines()
        if lineas:
            prev = hashlib.sha256(lineas[-1]).hexdigest()
    linea = json.dumps({**fila, "prev": prev}, sort_keys=True, ensure_ascii=True).encode()
    fd = os.open(reg, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, linea + b"\n")
        os.fsync(fd)
    finally:
        os.close(fd)


def _escribir_nuevo(ruta, datos):
    tmp = ruta + ".tmp"
    with open(tmp, "xb") as f:
        f.write(datos)
        f.flush()
        os.fsync(f.fileno())
    os.link(tmp, ruta)
    os.unlink(tmp)


def manifiesto_dia(carpeta):
    """Escribe MANIFIESTO.sha256 (líneas «sha256  <iv>/<SÍMBOLO>.zip», ordenadas) por reemplazo atómico y devuelve su sha256."""
    lineas = []
    for iv in INTERVALOS:
        d = os.path.join(carpeta, iv)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith(".zip"):
                    with open(os.path.join(d, f), "rb") as g:
                        lineas.append(f"{hashlib.sha256(g.read()).hexdigest()}  {iv}/{f}\n")
    cuerpo = "".join(lineas).encode()
    tmp = os.path.join(carpeta, "MANIFIESTO.sha256.tmp")
    with open(tmp, "wb") as f:
        f.write(cuerpo)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, os.path.join(carpeta, "MANIFIESTO.sha256"))
    return hashlib.sha256(cuerpo).hexdigest(), len(lineas)


def main():
    a = argparse.ArgumentParser()
    for k in ("fuente", "desde", "hasta", "destino", "protegidos"):
        a.add_argument("--" + k, required=True)
    x = a.parse_args()
    d0, d1 = dt.date.fromisoformat(x.desde), dt.date.fromisoformat(x.hasta)
    if d1 < d0 or (not x.fuente.startswith("file://") and d1 >= dt.datetime.now(dt.timezone.utc).date()):
        raise SystemExit("rango inválido: el último día tiene que ser anterior a hoy (UTC)")
    os.makedirs(x.destino, exist_ok=True)
    G.verificar(x.destino, G.cargar_protegidos(x.protegidos))
    pausa = 0.0 if x.fuente.startswith("file://") else PAUSA_S
    dias = [(d0 + dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]
    meses = sorted({d[:7] for d in dias})
    reg = os.path.join(x.destino, "REGISTRO.jsonl")
    simbolos = listar_simbolos(x.fuente, pausa)
    cuenta = {d: {"guardados": 0, "ya_estaban": 0, "checksum_distinto": 0, "errores": 0} for d in dias}
    for s in simbolos:
        for iv in INTERVALOS:
            try:
                existen = dias_existentes(x.fuente, s, iv, meses, dias, pausa)
            except Exception as e:  # noqa: BLE001
                for d in dias:
                    cuenta[d]["errores"] += 1
                anexar(reg, {"tipo": "ERROR_LISTADO", "simbolo": s, "intervalo": iv, "error": str(e)[:300]})
                continue
            for d in sorted(existen):
                carpeta = os.path.join(x.destino, d, iv)
                dst = os.path.join(carpeta, s + ".zip")
                if os.path.exists(dst):
                    cuenta[d]["ya_estaban"] += 1
                    continue
                u = url_archivo(x.fuente, s, iv, d)
                try:
                    datos = leer(u, pausa)
                    chk_txt = leer(u + ".CHECKSUM", pausa)
                except Exception as e:  # noqa: BLE001  (figuraba en el listado: no puede faltar)
                    cuenta[d]["errores"] += 1
                    anexar(reg, {"tipo": "ERROR_DESCARGA", "dia": d, "simbolo": s, "intervalo": iv, "error": str(e)[:300]})
                    continue
                chk = chk_txt.decode().split()[0]
                h = hashlib.sha256(datos).hexdigest()
                if h != chk:
                    cuenta[d]["checksum_distinto"] += 1  # no se guarda; el par-día queda como faltante (se informa)
                    anexar(reg, {"tipo": "CHECKSUM_DISTINTO", "dia": d, "simbolo": s, "intervalo": iv, "sha256": h, "oficial": chk})
                    continue
                os.makedirs(carpeta, exist_ok=True)
                _escribir_nuevo(dst, datos)
                _escribir_nuevo(dst + ".CHECKSUM", chk_txt)
                cuenta[d]["guardados"] += 1
    errores = 0
    for d in dias:
        carpeta = os.path.join(x.destino, d)
        os.makedirs(carpeta, exist_ok=True)
        sha, n = manifiesto_dia(carpeta)
        errores += cuenta[d]["errores"]
        anexar(reg, {"tipo": "RECOLECCION", "dia": d, "utc": dt.datetime.now(dt.timezone.utc).isoformat(), "simbolos_listados": len(simbolos),
                     "manifiesto_sha256": sha, "archivos": n, **cuenta[d]})
    print(json.dumps({"desde": x.desde, "hasta": x.hasta, "simbolos": len(simbolos), "errores": errores,
                      "guardados": sum(c["guardados"] for c in cuenta.values())}))
    if errores:
        sys.exit(2)


if __name__ == "__main__":
    main()
