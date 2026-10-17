"""Datos públicos oficiales de Binance en https://data.binance.vision (archivos mensuales con su .CHECKSUM SHA-256).

Conjuntos usados (BTCUSDT, 1 h):
  spot/monthly/klines, futures/um/monthly/klines, futures/um/monthly/markPriceKlines, futures/um/monthly/fundingRate.

Formatos esperados (se validan; cualquier desviación se rechaza en vez de adivinarse):
  - klines: 12 columnas (open_time, open, high, low, close, volume, close_time, quote_volume, count,
    taker_buy_volume, taker_buy_quote_volume, ignore), con o sin cabecera; marcas en ms, o en µs (spot desde 2025).
  - fundingRate: calc_time, funding_interval_hours, last_funding_rate (con cabecera).

La descarga necesita que la política de red del entorno permita data.binance.vision. Nunca pide meses del período
reservado (≥ 2026-06).

PROCEDENCIA: todo directorio de datos lleva un MANIFIESTO.json con el campo ``procedencia``:
  - "historico_oficial": archivos de data.binance.vision verificados contra su .CHECKSUM oficial (``descargar`` aquí
    o en otra máquina, o ``importar`` de una copia aportada por el usuario que conserva los .CHECKSUM);
  - "sintetico": archivos FABRICADOS con el formato oficial para ensayar el pipeline (``fabricar_sintetico``).
``construir_panel`` exige el manifiesto, verifica cada archivo contra él y etiqueta el panel con su procedencia: un
ensayo sintético nunca puede presentarse como histórico."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from hcarry.conventions import HORA_MS, RESERVADO_INICIO_MS, comprobar_fuera_de_reservado, iso, ms
from hcarry.data.schema import Barra, Panel
from hcarry.data.validacion import Informe, alinear_funding, validar_barras, validar_funding

BASE = "https://data.binance.vision/data"
TIPOS = ("spot", "perp", "mark", "funding", "premium")  # premium: opcional (índice de prima oficial)
REQUERIDOS = ("spot", "perp", "mark", "funding")
MARCA_SINTETICO = b"HCARRY-SINTETICO: archivo fabricado, no es un dato de mercado"


def es_sintetico(contenido_zip: bytes) -> bool:
    """True si el zip lleva la marca de los archivos fabricados por ``hcarry.data.fabricar``."""
    with zipfile.ZipFile(io.BytesIO(contenido_zip)) as z:
        return z.comment.startswith(MARCA_SINTETICO[:16])
PROCEDENCIAS = ("historico_oficial", "sintetico")


def ruta_mensual(tipo: str, simbolo: str, ano: int, mes: int, intervalo: str = "1h") -> str:
    s, i, ym = simbolo, intervalo, f"{ano}-{mes:02d}"
    rutas = {
        "spot": f"spot/monthly/klines/{s}/{i}/{s}-{i}-{ym}.zip",
        "perp": f"futures/um/monthly/klines/{s}/{i}/{s}-{i}-{ym}.zip",
        "mark": f"futures/um/monthly/markPriceKlines/{s}/{i}/{s}-{i}-{ym}.zip",
        "premium": f"futures/um/monthly/premiumIndexKlines/{s}/{i}/{s}-{i}-{ym}.zip",
        "funding": f"futures/um/monthly/fundingRate/{s}/{s}-fundingRate-{ym}.zip",
    }
    return rutas[tipo]


def ruta_diaria(tipo: str, simbolo: str, fecha: str, intervalo: str = "1h") -> str:
    """Archivo DIARIO oficial ('AAAA-MM-DD'). Solo se usa para completar horas que faltan en el archivo mensual de la
    misma serie (el funding no tiene archivos diarios)."""
    s, i = simbolo, intervalo
    rutas = {
        "spot": f"spot/daily/klines/{s}/{i}/{s}-{i}-{fecha}.zip",
        "perp": f"futures/um/daily/klines/{s}/{i}/{s}-{i}-{fecha}.zip",
        "mark": f"futures/um/daily/markPriceKlines/{s}/{i}/{s}-{i}-{fecha}.zip",
        "premium": f"futures/um/daily/premiumIndexKlines/{s}/{i}/{s}-{i}-{fecha}.zip",
    }
    return rutas[tipo]


def meses(desde: str, hasta: str) -> list[tuple[int, int]]:
    """Meses [desde, hasta) en formato 'AAAA-MM'. Rechaza cualquier mes que toque el período reservado."""
    a, m = int(desde[:4]), int(desde[5:7])
    fa, fm = int(hasta[:4]), int(hasta[5:7])
    salida = []
    while (a, m) < (fa, fm):
        salida.append((a, m))
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    if salida:
        ult_a, ult_m = salida[-1]
        fin = ms(f"{ult_a + (ult_m == 12)}-{1 if ult_m == 12 else ult_m + 1:02d}-01")
        comprobar_fuera_de_reservado(ms(f"{salida[0][0]}-{salida[0][1]:02d}-01"), fin)
    return salida


# ---------------------------------------------------------------------------------------------- descarga
@dataclass
class Archivo:
    tipo: str
    ruta: str
    sha256: str
    bytes: int
    checksum_oficial: str | None


class NoPublicado(Exception):
    """El archivo mensual no existe en la fuente (HTTP 404)."""


def _abrir_http(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=60) as r:  # respeta HTTPS_PROXY del entorno
            return r.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NoPublicado(url) from exc
        raise


def _escribir(p: Path, cuerpo: bytes) -> None:
    if p.exists():
        if p.read_bytes() != cuerpo:
            raise FileExistsError(f"{p} ya existe con otro contenido")
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(cuerpo)
    tmp.replace(p)


def _checksum_de(texto: bytes, nombre: str) -> str:
    partes = texto.decode("utf-8").split()
    if len(partes) < 2 or len(partes[0]) != 64 or not partes[1].endswith(nombre):
        raise ValueError(f".CHECKSUM con formato inesperado para {nombre}: {partes[:2]}")
    return partes[0].lower()


def _bajar_verificado(destino: Path, rel: str, abrir: Callable[[str], bytes], reintentos: int) -> dict | None:
    """Baja un archivo y su .CHECKSUM oficial, lo verifica y lo guarda. None si la fuente no lo publica (404).
    Reanudable: si ya existe con el hash oficial no se vuelve a bajar. Solo se reintentan los fallos de red."""
    import time
    nombre = rel.rsplit("/", 1)[1]
    url = f"{BASE}/{rel}"
    for intento in range(reintentos + 1):
        try:
            check = abrir(url + ".CHECKSUM")
            oficial = _checksum_de(check, nombre)
            p = destino / rel
            if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == oficial:
                cuerpo = p.read_bytes()
            else:
                cuerpo = abrir(url)
            break
        except NoPublicado:
            return None
        except OSError as exc:  # fallos transitorios de red; un formato o un hash erróneos no se reintentan
            if intento == reintentos:
                raise RuntimeError(f"no se pudo descargar {rel}: {exc}") from exc
            time.sleep(2 ** intento)
    sha = hashlib.sha256(cuerpo).hexdigest()
    if sha != oficial:
        raise ValueError(f"checksum distinto en {rel}: {sha} ≠ {oficial}")
    _escribir(destino / rel, cuerpo)
    _escribir(destino / (rel + ".CHECKSUM"), check)
    return {"sha256": sha, "bytes": len(cuerpo), "checksum_oficial": oficial}


def descargar(destino: Path, desde: str, hasta: str, simbolo: str = "BTCUSDT", tipos: tuple[str, ...] = TIPOS,
              abrir: Callable[[str], bytes] = _abrir_http, reintentos: int = 4) -> dict:
    """Descarga los meses [desde, hasta) de cada tipo junto con su .CHECKSUM oficial, verifica cada archivo y escribe
    un manifiesto con procedencia "historico_oficial". Reanudable (no vuelve a bajar lo ya verificado); un mes no
    publicado (404) queda anotado como ausente; nunca sobrescribe un archivo con contenido distinto."""
    destino.mkdir(parents=True, exist_ok=True)
    archivos, ausentes = [], []
    for tipo in tipos:
        for a, m in meses(desde, hasta):
            rel = ruta_mensual(tipo, simbolo, a, m)
            r = _bajar_verificado(destino, rel, abrir, reintentos)
            if r is None:
                ausentes.append({"tipo": tipo, "ruta": rel})
                continue
            archivos.append(Archivo(tipo, rel, r["sha256"], r["bytes"], r["checksum_oficial"]).__dict__)
    import datetime as _dt
    manifiesto = {"procedencia": "historico_oficial", "fuente": BASE, "via": "descarga directa",
                  "fecha_utc": _dt.datetime.now(_dt.UTC).isoformat(), "simbolo": simbolo, "desde": desde,
                  "hasta": hasta, "archivos": archivos, "ausentes": ausentes}
    _escribir_manifiesto(destino, manifiesto)
    return manifiesto


def _es_diario(a: dict) -> bool:
    return a.get("granularidad") == "diaria"


def _horas_mensuales(directorio: Path, man: dict, tipo: str) -> set[int]:
    horas: set[int] = set()
    for a in man["archivos"]:
        if a["tipo"] == tipo and not _es_diario(a):
            horas.update(leer_klines((directorio / a["ruta"]).read_bytes(), irregulares=[]))
    return horas


def completar_con_diarios(destino: Path, hasta: str = "2026-06-01", simbolo: str = "BTCUSDT",
                          tipos: tuple[str, ...] = ("spot", "perp", "mark"), abrir: Callable[[str], bytes] = _abrir_http,
                          reintentos: int = 4) -> dict:
    """Completa las horas que faltan en los archivos MENSUALES con los archivos DIARIOS oficiales de la misma serie y
    del mismo emisor (cada uno con su .CHECKSUM). No sustituye nada: ``construir_panel`` solo toma de un diario las
    horas ausentes del mensual y exige que las horas presentes en ambos coincidan exactamente (D1). Un día que la
    fuente no publica queda anotado en ``ausentes_diarios``. Solo para manifiestos "historico_oficial"."""
    import datetime as _dt
    man = leer_manifiesto(destino)
    if man["procedencia"] != "historico_oficial":
        raise ValueError("solo se completan descargas históricas oficiales")
    ini, fin = ms(inicio_comun(destino)), ms(hasta)
    comprobar_fuera_de_reservado(ini, fin)
    ya = {a["ruta"] for a in man["archivos"]}
    nuevos, ausentes, dias_por_tipo = [], list(man.get("ausentes_diarios", [])), {}
    for tipo in tipos:
        presentes = _horas_mensuales(destino, man, tipo)
        dias = sorted({iso(t)[:10] for t in range(ini, fin, HORA_MS) if t not in presentes})
        dias_por_tipo[tipo] = dias
        for dia in dias:
            rel = ruta_diaria(tipo, simbolo, dia)
            if rel in ya:
                continue
            r = _bajar_verificado(destino, rel, abrir, reintentos)
            if r is None:
                if {"tipo": tipo, "ruta": rel} not in ausentes:
                    ausentes.append({"tipo": tipo, "ruta": rel})
                continue
            nuevos.append({**Archivo(tipo, rel, r["sha256"], r["bytes"], r["checksum_oficial"]).__dict__,
                           "granularidad": "diaria"})
    if not nuevos and ausentes == man.get("ausentes_diarios", []) and "complementos_diarios" in man:
        return man  # nada nuevo: el manifiesto (y su hash, que identifica los datos) no se toca
    man["archivos"] = man["archivos"] + nuevos
    man["ausentes_diarios"] = ausentes
    man.setdefault("complementos_diarios", []).append({
        "fecha_utc": _dt.datetime.now(_dt.UTC).isoformat(), "hasta": hasta, "dias_con_horas_ausentes": dias_por_tipo,
        "archivos_nuevos": len(nuevos),
        "motivo": "horas ausentes en los archivos mensuales; se completan con los diarios oficiales del mismo emisor"})
    _escribir_manifiesto(destino, man)
    return man


def _escribir_manifiesto(destino: Path, manifiesto: dict) -> None:
    manifiesto["archivos"] = sorted(manifiesto["archivos"], key=lambda x: x["ruta"])
    (destino / "MANIFIESTO.json").write_text(json.dumps(manifiesto, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def importar(origen: Path, destino: Path, simbolo: str = "BTCUSDT") -> dict:
    """Importa una copia de data.binance.vision aportada por el usuario (p. ej., descargada con ``descargar`` en su
    máquina): cada zip debe venir con su .CHECKSUM oficial al lado y conservar la ruta oficial. Se verifica todo y se
    escribe un manifiesto "historico_oficial" (o "sintetico" si los archivos llevan la marca); ``via`` describe la importación
    sin atribuir el origen a nadie. Un zip sin .CHECKSUM o que no coincide se rechaza."""
    destino.mkdir(parents=True, exist_ok=True)
    patrones = {tipo: ruta_mensual(tipo, simbolo, 2000, 1).rsplit("/", 1)[0] for tipo in TIPOS}
    archivos, marcados = [], 0
    for zp in sorted(origen.rglob("*.zip")):
        rel_total = zp.relative_to(origen).as_posix()
        tipo = next((k for k, pat in patrones.items() if f"/{pat}/" in f"/{rel_total}"), None)
        if tipo is None:
            continue
        rel = rel_total[rel_total.index(patrones[tipo]):]
        check_p = zp.with_name(zp.name + ".CHECKSUM")
        if not check_p.exists():
            raise ValueError(f"{rel}: falta su .CHECKSUM oficial")
        oficial = _checksum_de(check_p.read_bytes(), zp.name)
        cuerpo = zp.read_bytes()
        sha = hashlib.sha256(cuerpo).hexdigest()
        if sha != oficial:
            raise ValueError(f"checksum distinto en {rel}: {sha} ≠ {oficial}")
        marcados += es_sintetico(cuerpo)
        _escribir(destino / rel, cuerpo)
        _escribir(destino / (rel + ".CHECKSUM"), check_p.read_bytes())
        archivos.append(Archivo(tipo, rel, sha, len(cuerpo), oficial).__dict__)
    if not archivos:
        raise ValueError("no se encontró ningún archivo con la ruta oficial de data.binance.vision")
    import datetime as _dt
    previo_man = json.loads(previo.read_text(encoding="utf-8")) if (previo := origen / "MANIFIESTO.json").exists() else {}
    sintetica = marcados > 0 or previo_man.get("procedencia") == "sintetico"
    if sintetica and marcados not in (0, len(archivos)):
        raise ValueError(f"copia mezclada: {marcados} de {len(archivos)} archivos son SINTÉTICOS")
    manifiesto = {"procedencia": "sintetico" if sintetica else "historico_oficial",
                  "fuente": "archivos fabricados (marca SINTÉTICO)" if sintetica else BASE,
                  "via": ("importación de archivos FABRICADOS (marca SINTÉTICO); no los aportó el usuario" if sintetica
                          else "importación de una copia externa verificada contra sus .CHECKSUM oficiales"),
                  "fecha_utc": _dt.datetime.now(_dt.UTC).isoformat(), "simbolo": simbolo, "archivos": archivos,
                  "manifiesto_origen_sha256": hashlib.sha256(previo.read_bytes()).hexdigest() if previo.exists() else None}
    _escribir_manifiesto(destino, manifiesto)
    return manifiesto


def leer_manifiesto(directorio: Path) -> dict:
    p = directorio / "MANIFIESTO.json"
    if not p.exists():
        raise ValueError(f"{directorio}: sin MANIFIESTO.json no se acepta ningún dato (procedencia desconocida)")
    man = json.loads(p.read_text(encoding="utf-8"))
    if man.get("procedencia") not in PROCEDENCIAS:
        raise ValueError(f"procedencia no válida: {man.get('procedencia')!r}")
    return man


def cobertura(directorio: Path) -> dict[str, list[str]]:
    """Meses ('AAAA-MM') disponibles por tipo según el manifiesto."""
    salida: dict[str, list[str]] = {t: [] for t in TIPOS}
    for a in leer_manifiesto(directorio)["archivos"]:
        if _es_diario(a):
            continue
        salida[a["tipo"]].append(a["ruta"].rsplit("-", 2)[-2] + "-" + a["ruta"].rsplit("-", 1)[-1][:2])
    return {k: sorted(v) for k, v in salida.items()}


def inicio_comun(directorio: Path) -> str:
    """Primer mes en que existen TODAS las series requeridas (regla fijada antes de ver los datos)."""
    cob = cobertura(directorio)
    primeros = [cob[t][0] for t in REQUERIDOS if cob[t]]
    if len(primeros) != len(REQUERIDOS):
        faltan = [t for t in REQUERIDOS if not cob[t]]
        raise ValueError(f"faltan series requeridas: {faltan}")
    return max(primeros) + "-01"


def sha_manifiesto(directorio: Path) -> str:
    return hashlib.sha256((directorio / "MANIFIESTO.json").read_bytes()).hexdigest()


# ---------------------------------------------------------------------------------------------- lectura
def _filas_csv(contenido_zip: bytes) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(contenido_zip)) as z:
        nombres = [n for n in z.namelist() if n.endswith(".csv")]
        if len(nombres) != 1:
            raise ValueError(f"se esperaba 1 CSV en el zip, hay {len(nombres)}")
        texto = z.read(nombres[0]).decode("utf-8")
    return [f for f in csv.reader(io.StringIO(texto)) if f]


def _ms(valor: str) -> int:
    v = int(valor)
    if v > 10 ** 15:  # microsegundos (spot desde 2025-01-01)
        if v % 1000:
            raise ValueError(f"marca en µs no entera en ms: {valor}")
        v //= 1000
    return v


def leer_klines(contenido_zip: bytes, irregulares: list | None = None) -> dict[int, tuple[float, float, float, float, float]]:
    """t → (open, high, low, close, quote_volume). Cabecera opcional; 12 columnas exactas.
    Una vela que no dura exactamente 1 h (p. ej., una parada del exchange a mitad de hora) es un error, salvo que se
    pase ``irregulares``: entonces se EXCLUYE y se anota (apertura, cierre) en esa lista. Su hora queda sin datos."""
    salida: dict[int, tuple[float, float, float, float, float]] = {}
    for k, f in enumerate(_filas_csv(contenido_zip)):
        if k == 0 and not f[0].strip().lstrip("-").isdigit():
            if f[0].strip() != "open_time":
                raise ValueError(f"cabecera inesperada: {f[:3]}")
            continue
        if len(f) != 12:
            raise ValueError(f"kline con {len(f)} columnas")
        t = _ms(f[0])
        if t % HORA_MS:
            raise ValueError(f"apertura no alineada a la hora: {f[0]}")
        # el cierre es apertura + 1 h − 1 unidad de la marca: −1 ms, o −1 µs en el spot desde 2025
        micro = int(f[0]) > 10 ** 15
        cierre = int(f[6])
        if cierre != int(f[0]) + HORA_MS * (1000 if micro else 1) - 1:
            if irregulares is None:
                raise ValueError(f"vela que no dura 1 h: {f[0]}–{f[6]}")
            irregulares.append((t, cierre // 1000 if micro else cierre))
            continue
        if t in salida:
            raise ValueError(f"hora repetida: {iso(t)}")
        salida[t] = (float(f[1]), float(f[2]), float(f[3]), float(f[4]), float(f[7]))
    return salida


def leer_funding(contenido_zip: bytes) -> list[tuple[int, float, float | None]]:
    """(marca_ms, tasa, mark=None). Requiere la cabecera documentada."""
    filas = _filas_csv(contenido_zip)
    cab = [c.strip() for c in filas[0]]
    if cab[:1] != ["calc_time"] or "last_funding_rate" not in cab:
        raise ValueError(f"cabecera de funding inesperada: {cab}")
    i_t, i_r = cab.index("calc_time"), cab.index("last_funding_rate")
    return [(_ms(f[i_t]), float(f[i_r]), None) for f in filas[1:]]


def construir_panel(directorio: Path, desde: str, hasta: str, simbolo: str = "BTCUSDT",
                    rellenar_huecos: bool = True) -> tuple[Panel, Informe]:
    """Panel horario [desde, hasta) a partir de los zips descargados. Las horas sin alguna de las tres series se
    rellenan con una barra plana al último cierre, marcada ``relleno`` (el motor no decide en ellas) e informada como H1;
    con ``rellenar_huecos=False`` cualquier hueco es un error."""
    ini, fin = ms(desde), ms(hasta)
    comprobar_fuera_de_reservado(ini, fin)
    man = leer_manifiesto(directorio)
    esperados = {a["ruta"]: a["sha256"] for a in man["archivos"]}
    inf = Informe()
    inf.info["procedencia"] = man["procedencia"]
    series: dict[str, dict] = {"spot": {}, "perp": {}, "mark": {}, "premium": {}}
    meses_sin_prima = 0
    irregulares: list[tuple[str, str, float]] = []
    de_diarios: dict[str, int] = {}
    vol_distinto: list[tuple[str, str, float, float]] = []
    crudos_funding: list[tuple[int, float, float | None]] = []
    meses_ = meses(desde[:7], _mes_siguiente(hasta) if not hasta.endswith("-01") else hasta[:7])
    for a, m in meses_:
        for tipo in ("spot", "perp", "mark", "funding", "premium"):
            p = directorio / ruta_mensual(tipo, simbolo, a, m)
            if not p.exists():
                if tipo == "premium":  # opcional: las políticas usan entonces F/S − 1 como aproximación
                    meses_sin_prima += 1
                else:
                    inf.add("A1", f"falta el archivo {p.name} ({tipo})")
                continue
            datos = p.read_bytes()
            rel = ruta_mensual(tipo, simbolo, a, m)
            if esperados.get(rel) != hashlib.sha256(datos).hexdigest():
                raise ValueError(f"{rel}: no figura en el manifiesto o su hash no coincide (¿archivo alterado?)")
            if man["procedencia"] == "historico_oficial" and es_sintetico(datos):
                raise ValueError(f"{rel}: archivo SINTÉTICO en un manifiesto histórico")
            if tipo == "funding":
                crudos_funding += leer_funding(datos)
            else:
                irr: list = []
                series[tipo].update(leer_klines(datos, irregulares=irr))
                irregulares += [(tipo, iso(t), round((c - t + 1) / 60000, 1)) for t, c in irr if ini <= t < fin]
    for a in man["archivos"]:  # diarios oficiales: SOLO horas ausentes del mensual; las comunes deben coincidir
        if not _es_diario(a):
            continue
        dia = a["ruta"].rsplit("-", 3)[-3:]
        if not ini <= ms("-".join(dia)[:10]) < fin:
            continue
        datos = (directorio / a["ruta"]).read_bytes()
        if hashlib.sha256(datos).hexdigest() != a["sha256"]:
            raise ValueError(f"{a['ruta']}: su hash no coincide con el manifiesto (¿archivo alterado?)")
        irr = []
        for t, v in leer_klines(datos, irregulares=irr).items():
            previo = series[a["tipo"]].get(t)
            if previo is None:
                series[a["tipo"]][t] = v
                de_diarios[a["tipo"]] = de_diarios.get(a["tipo"], 0) + 1
            elif previo[:4] != v[:4]:  # precios distintos entre dos archivos oficiales: bloqueante
                inf.add("D1", f"el diario y el mensual difieren en los precios de {a['tipo']}", t)
            elif previo != v:  # solo el volumen: se conserva el mensual y se deja constancia
                vol_distinto.append((a["tipo"], iso(t), previo[4], v[4]))
    inf.info["velas_irregulares_excluidas"] = irregulares
    inf.info["horas_de_archivos_diarios"] = de_diarios
    inf.info["volumen_distinto_diario_mensual"] = vol_distinto
    barras: list[Barra] = []
    rellenas = 0
    previa = None
    for t in range(ini, fin, HORA_MS):
        s, f, mk = series["spot"].get(t), series["perp"].get(t), series["mark"].get(t)
        if s and f and mk:
            pr = series["premium"].get(t)
            previa = Barra(t, *s[:4], *f[:4], *mk[:4], s[4], f[4], prima=pr[3] if pr else None)
            barras.append(previa)
            continue
        if previa is None or not rellenar_huecos:
            raise ValueError(f"falta la hora {iso(t)} (spot={bool(s)}, perp={bool(f)}, mark={bool(mk)})")
        rellenas += 1
        if rellenas <= 20:
            inf.add("H1", f"hora rellenada (spot={bool(s)}, perp={bool(f)}, mark={bool(mk)})", t)
        pb = previa
        previa = Barra(t, pb.S_c, pb.S_c, pb.S_c, pb.S_c, pb.F_c, pb.F_c, pb.F_c, pb.F_c, pb.M_c, pb.M_c, pb.M_c,
                       pb.M_c, 0.0, 0.0, relleno=True)
        barras.append(previa)
    inf.info["horas_rellenadas"] = rellenas
    inf.info["meses_sin_prima"] = meses_sin_prima
    malas = [b.t for b in barras if b.prima is not None and abs(b.prima) > 0.05]
    if malas:
        inf.add("A4", f"{len(malas)} horas con |prima| > 5 %: ¿otra unidad?", malas[0])
    eventos = [e for e in alinear_funding(crudos_funding, inf) if ini <= e.t < fin]
    validar_funding(eventos, ini, fin, inf)
    validar_barras(barras, inf)
    if any(e.t >= RESERVADO_INICIO_MS for e in eventos):  # imposible por construcción; doble guarda
        raise AssertionError("evento en el período reservado")
    panel = Panel(barras, eventos, f"{man['procedencia']}:binance_vision:{simbolo}:{desde}:{hasta}",
                  [str(i) for i in inf.incidencias[:50]])
    return panel, inf


def _mes_siguiente(fecha: str) -> str:
    a, m = int(fecha[:4]), int(fecha[5:7])
    a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return f"{a}-{m:02d}"
