"""E4 · Recolector diario (NO calcula nada sobre los datos: no abre los ZIP; solo descarga, verifica el .CHECKSUM oficial y
registra). Requiere autorización para correr con la fuente real (red y tarea programada). En pruebas usa una fuente local file://.
Para cada día D y cada símbolo XUSDT listado en la fuente, baja `XUSDT-1d-D.zip` y su `.CHECKSUM`, verifica el sha256 y guarda
`destino/D/XUSDT.zip`. Registro: `destino/REGISTRO.jsonl`, encadenado por sha256 (cada línea lleva el hash de la anterior);
nunca reescribe un ZIP ya guardado; un ZIP que no verifica no se guarda y queda registrado como `checksum_distinto`.
Antes de escribir, pasa `destino` por la guarda de rutas (no puede apuntar a datos protegidos de E3).
Uso: python3 -I -B recolector.py --fuente <url_base|file://dir> --dia YYYY-MM-DD --destino <dir> --protegidos <PROTEGIDOS.tsv>"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guarda_rutas as G  # noqa: E402

PREFIJO = "data/spot/daily/klines/"


def leer(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def listar_simbolos(fuente):
    if fuente.startswith("file://"):
        return sorted(json.loads(leer(fuente.rstrip("/") + "/LISTADO.json")))
    simbolos, token = [], None
    while True:
        q = {"delimiter": "/", "prefix": PREFIJO, "list-type": "2"}
        if token:
            q["continuation-token"] = token
        xml = leer("https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?" + urllib.parse.urlencode(q))
        raiz = ET.fromstring(xml)
        ns = {"s": raiz.tag.split("}")[0].strip("{")}
        simbolos += [p.text[len(PREFIJO):].strip("/") for p in raiz.findall("s:CommonPrefixes/s:Prefix", ns)]
        nxt = raiz.find("s:NextContinuationToken", ns)
        if nxt is None:
            break
        token = nxt.text
    return sorted(s for s in simbolos if re.fullmatch(r"[A-Z0-9]{2,20}USDT", s))


def url_archivo(fuente, simbolo, dia):
    if fuente.startswith("file://"):
        return f"{fuente.rstrip('/')}/{simbolo}/{simbolo}-1d-{dia}.zip"
    return f"{fuente.rstrip('/')}/{PREFIJO}{simbolo}/1d/{simbolo}-1d-{dia}.zip"


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


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--fuente", required=True)
    a.add_argument("--dia", required=True)
    a.add_argument("--destino", required=True)
    a.add_argument("--protegidos", required=True)
    x = a.parse_args()
    dt.date.fromisoformat(x.dia)
    os.makedirs(x.destino, exist_ok=True)
    G.verificar(x.destino, G.cargar_protegidos(x.protegidos))
    carpeta = os.path.join(x.destino, x.dia)
    os.makedirs(carpeta, exist_ok=True)
    cuenta = {"guardado": 0, "ya_estaba": 0, "ausente": 0, "checksum_distinto": 0}
    simbolos = listar_simbolos(x.fuente)
    for s in simbolos:
        dst = os.path.join(carpeta, s + ".zip")
        if os.path.exists(dst):
            cuenta["ya_estaba"] += 1
            continue
        u = url_archivo(x.fuente, s, x.dia)
        try:
            datos, chk = leer(u), leer(u + ".CHECKSUM").decode().split()[0]
        except Exception:  # noqa: BLE001  (el par no tiene archivo ese día: se registra como ausente)
            cuenta["ausente"] += 1
            continue
        h = hashlib.sha256(datos).hexdigest()
        if h != chk:
            cuenta["checksum_distinto"] += 1
            anexar(os.path.join(x.destino, "REGISTRO.jsonl"), {"tipo": "CHECKSUM_DISTINTO", "dia": x.dia, "simbolo": s, "sha256": h, "oficial": chk})
            continue
        tmp = dst + ".tmp"
        with open(tmp, "xb") as f:
            f.write(datos)
            f.flush()
            os.fsync(f.fileno())
        os.link(tmp, dst)
        os.unlink(tmp)
    anexar(os.path.join(x.destino, "REGISTRO.jsonl"), {"tipo": "RECOLECCION", "dia": x.dia, "utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                                                        "simbolos_listados": len(simbolos), **cuenta})
    print(json.dumps({"dia": x.dia, "simbolos": len(simbolos), **cuenta}))


if __name__ == "__main__":
    main()
