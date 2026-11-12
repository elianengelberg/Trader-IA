"""E3 · A2: descarga verificada de klines 1d mensuales de spot (pares USDT) desde data.binance.vision.

Uso (siempre con python -I; los datos descargados nunca se ejecutan):
  descarga_vision.py listar     <dir_datos>          # listado S3 de símbolos y de archivos por símbolo (XML crudo guardado)
  descarga_vision.py descargar  <dir_datos>          # zips + .CHECKSUM hasta 2026-05 (reanudable)
  descarga_vision.py reparar    <dir_datos>          # diarios oficiales para meses sin mensual o con checksum fallido

Límites (v3 §9): ≤ 5 solicitudes/s, reintentos con espera ante 429/5xx/red, nada ≥ 2026-06.
BTCUSDT y ETHUSDT no se descargan (N20: se reutilizan los locales verificados).
"""
import concurrent.futures as cf
import hashlib
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BUCKET = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
BASE = "https://data.binance.vision/"
UA = "Trader-IA-investigacion/0.1 (uso academico no comercial)"
ULTIMO_MES = "2026-05"
REUTILIZADOS = {"BTCUSDT", "ETHUSDT"}
NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
CTX = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE"))


class Limitador:
    def __init__(self, por_segundo: float):
        self.intervalo, self.siguiente, self.lock = 1.0 / por_segundo, time.monotonic(), threading.Lock()

    def esperar(self):
        with self.lock:
            ahora = time.monotonic()
            t = max(ahora, self.siguiente)
            self.siguiente = t + self.intervalo
        time.sleep(max(0.0, t - ahora))


LIM = Limitador(5.0)
LOG_LOCK = threading.Lock()


def log(dir_datos: Path, entrada: dict):
    entrada["utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with LOG_LOCK, open(dir_datos / "registro_descargas.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entrada, ensure_ascii=False) + "\n")


def obtener(url: str, dir_datos: Path, intentos: int = 6) -> tuple[int, bytes]:
    espera = 2.0
    for i in range(intentos):
        LIM.esperar()
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), context=CTX, timeout=60)
            cuerpo = r.read()
            log(dir_datos, {"url": url, "http": r.status, "bytes": len(cuerpo), "sha256": hashlib.sha256(cuerpo).hexdigest()})
            return r.status, cuerpo
        except urllib.error.HTTPError as e:
            log(dir_datos, {"url": url, "http": e.code, "intento": i + 1})
            if e.code == 404:
                return 404, b""
            if e.code not in (429, 500, 502, 503, 504):
                return e.code, b""
        except Exception as e:  # red
            log(dir_datos, {"url": url, "error": type(e).__name__, "detalle": str(e)[:200], "intento": i + 1})
        time.sleep(espera)
        espera *= 2
    return -1, b""


def listar_s3(prefijo: str, dir_datos: Path, delim: bool, destino: Path) -> tuple[list[str], list[dict]]:
    marcador, prefijos, claves, pagina = "", [], [], 0
    destino.mkdir(parents=True, exist_ok=True)
    while True:
        url = f"{BUCKET}?prefix={urllib.parse.quote(prefijo, safe='/')}" + ("&delimiter=/" if delim else "") + (f"&marker={urllib.parse.quote(marcador, safe='/')}" if marcador else "")
        st, cuerpo = obtener(url, dir_datos)
        if st != 200:
            raise RuntimeError(f"listado falló {st} {url}")
        (destino / f"pagina_{pagina:03d}.xml").write_bytes(cuerpo)
        raiz = ET.fromstring(cuerpo)
        prefijos += [p.text for p in raiz.iter(NS + "Prefix") if p.text and p.text != prefijo and p.text.endswith("/")]
        for c in raiz.iter(NS + "Contents"):
            claves.append({"key": c.find(NS + "Key").text, "size": int(c.find(NS + "Size").text),
                           "etag": c.find(NS + "ETag").text.strip('"'), "last_modified": c.find(NS + "LastModified").text})
        trunc = raiz.find(NS + "IsTruncated").text == "true"
        if not trunc:
            break
        nm = raiz.find(NS + "NextMarker")
        marcador = nm.text if nm is not None else (claves[-1]["key"] if claves else prefijos[-1])
        pagina += 1
    return prefijos, claves


def listar(dir_datos: Path):
    raiz = "data/spot/monthly/klines/"
    prefijos, _ = listar_s3(raiz, dir_datos, True, dir_datos / "listados" / "prefijos")
    simbolos = sorted({p[len(raiz):].rstrip("/") for p in prefijos})
    usdt = [s for s in simbolos if s.endswith("USDT") and len(s) > 4]
    (dir_datos / "listados" / "simbolos_todos.json").write_text(json.dumps(simbolos, indent=0))
    (dir_datos / "listados" / "simbolos_usdt.json").write_text(json.dumps(usdt, indent=0))
    print(f"símbolos totales {len(simbolos)}; terminados en USDT {len(usdt)}", flush=True)
    archivos = {}

    def uno(s):
        _, claves = listar_s3(f"{raiz}{s}/1d/", dir_datos, False, dir_datos / "listados" / "por_simbolo" / s)
        return s, claves

    with cf.ThreadPoolExecutor(5) as ex:
        for s, claves in ex.map(uno, usdt):
            archivos[s] = claves
    (dir_datos / "listados" / "archivos_1d_mensuales.json").write_text(json.dumps(archivos))
    n = sum(1 for v in archivos.values() for c in v if c["key"].endswith(".zip") and mes(c["key"]) <= ULTIMO_MES)
    print(f"zips 1d mensuales ≤ {ULTIMO_MES} (sin BTC/ETH): {sum(1 for s, v in archivos.items() if s not in REUTILIZADOS for c in v if c['key'].endswith('.zip') and mes(c['key']) <= ULTIMO_MES)}; con BTC/ETH: {n}", flush=True)


def mes(clave: str) -> str:
    m = re.search(r"-(\d{4}-\d{2})\.zip", clave)
    return m.group(1) if m else "9999-99"


def bajar_par(clave_zip: str, dir_datos: Path) -> dict:
    destino = dir_datos / clave_zip
    chk = destino.with_name(destino.name + ".CHECKSUM")
    if destino.exists() and chk.exists() and verificar(destino, chk):
        return {"key": clave_zip, "estado": "ya_verificado"}
    st1, z = obtener(BASE + urllib.parse.quote(clave_zip, safe="/"), dir_datos)
    st2, c = obtener(BASE + urllib.parse.quote(clave_zip + ".CHECKSUM", safe="/"), dir_datos)
    if st1 != 200 or st2 != 200:
        return {"key": clave_zip, "estado": "fallo_descarga", "http_zip": st1, "http_checksum": st2}
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(z)
    chk.write_bytes(c)
    ok = verificar(destino, chk)
    return {"key": clave_zip, "estado": "verificado" if ok else "checksum_falla"}


def verificar(z: Path, chk: Path) -> bool:
    esperado = chk.read_text().split()[0].strip().lower()
    return hashlib.sha256(z.read_bytes()).hexdigest() == esperado


def descargar(dir_datos: Path):
    archivos = json.loads((dir_datos / "listados" / "archivos_1d_mensuales.json").read_text())
    tareas = [c["key"] for s, v in sorted(archivos.items()) if s not in REUTILIZADOS
              for c in v if c["key"].endswith(".zip") and mes(c["key"]) <= ULTIMO_MES]
    print(f"tareas: {len(tareas)}", flush=True)
    res, t0 = [], time.time()
    with cf.ThreadPoolExecutor(5) as ex:
        for i, r in enumerate(ex.map(lambda k: bajar_par(k, dir_datos), tareas)):
            res.append(r)
            if (i + 1) % 1000 == 0:
                print(f"{i + 1}/{len(tareas)} ({time.time() - t0:.0f} s)", flush=True)
    resumen = {}
    for r in res:
        resumen[r["estado"]] = resumen.get(r["estado"], 0) + 1
    (dir_datos / "resultado_descarga_mensual.json").write_text(json.dumps({"resumen": resumen, "detalle": res}, indent=0))
    print("resumen:", resumen, flush=True)


def reparar(dir_datos: Path):
    """Meses sin mensual (huecos internos entre el primer y el último mensual) o con checksum fallido → diarios oficiales."""
    archivos = json.loads((dir_datos / "listados" / "archivos_1d_mensuales.json").read_text())
    det = json.loads((dir_datos / "resultado_descarga_mensual.json").read_text())["detalle"]
    malos = {r["key"] for r in det if r["estado"] != "verificado" and r["estado"] != "ya_verificado"}
    pendientes = {}
    for s, v in archivos.items():
        if s in REUTILIZADOS:
            continue
        meses = sorted(mes(c["key"]) for c in v if c["key"].endswith(".zip") and mes(c["key"]) <= ULTIMO_MES)
        if not meses:
            continue
        y0, m0 = map(int, meses[0].split("-"))
        y1, m1 = map(int, meses[-1].split("-"))
        todos = []
        y, m = y0, m0
        while (y, m) <= (y1, m1):
            todos.append(f"{y:04d}-{m:02d}")
            m += 1
            if m == 13:
                y, m = y + 1, 1
        faltan = [mm for mm in todos if mm not in set(meses)]
        fallidos = [mes(k) for k in malos if f"/{s}/" in k]
        if faltan or fallidos:
            pendientes[s] = sorted(set(faltan + fallidos))
    (dir_datos / "reparaciones_pendientes.json").write_text(json.dumps(pendientes, indent=0))
    print(f"símbolos con meses a reparar: {len(pendientes)}; meses: {sum(len(v) for v in pendientes.values())}", flush=True)
    resultados = {}
    for s, meses in pendientes.items():
        _, claves = listar_s3(f"data/spot/daily/klines/{s}/1d/", dir_datos, False, dir_datos / "listados" / "diarios" / s)
        diarios = [c["key"] for c in claves if c["key"].endswith(".zip") and any(f"-{mm}-" in c["key"] for mm in meses)]
        resultados[s] = [bajar_par(k, dir_datos) for k in diarios]
    (dir_datos / "resultado_reparaciones.json").write_text(json.dumps(resultados, indent=0))
    print("reparaciones:", sum(len(v) for v in resultados.values()), "archivos diarios", flush=True)


if __name__ == "__main__":
    fase, d = sys.argv[1], Path(sys.argv[2])
    d.mkdir(parents=True, exist_ok=True)
    {"listar": listar, "descargar": descargar, "reparar": reparar}[fase](d)
