"""Velas DIARIAS oficiales de spot (data.binance.vision, spot/monthly/klines/{SIMBOLO}/1d) con su .CHECKSUM.

Reutiliza la bajada verificada de H-CARRY Next (reanudable, 404 = no publicado, checksum obligatorio) y añade lo propio
de las velas diarias: cierre = apertura + 1 día − 1 unidad (ms; µs en el spot desde 2025), días ausentes o repetidos,
OHLC incoherente y precios no positivos. Nunca rellena un día ausente."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from hcarry.data.binance_vision import _abrir_http, _bajar_verificado, _escribir_manifiesto, meses

DIA_MS = 86_400_000
RESERVADO_INICIO = "2026-06-01"


def ruta_1d(simbolo: str, ano: int, mes: int) -> str:
    return f"spot/monthly/klines/{simbolo}/1d/{simbolo}-1d-{ano}-{mes:02d}.zip"


@dataclass(frozen=True)
class Vela:
    dia: str  # AAAA-MM-DD (UTC) de la apertura
    o: float
    h: float
    low: float
    c: float
    vol_quote: float


def descargar_1d(destino: Path, simbolo: str, desde: str = "2017-08", hasta: str = "2026-06", abrir=_abrir_http,  # type: ignore[no-untyped-def]
                 reintentos: int = 4) -> dict:
    if hasta > RESERVADO_INICIO[:7]:
        raise ValueError("no se descarga el período reservado (≥ 2026-06)")
    archivos, ausentes = [], []
    for a, m in meses(desde, hasta):
        rel = ruta_1d(simbolo, a, m)
        r = _bajar_verificado(destino, rel, abrir, reintentos)
        if r is None:
            ausentes.append(rel)
            continue
        archivos.append({"tipo": "spot_1d", "ruta": rel, "sha256": r["sha256"], "bytes": r["bytes"],
                         "checksum_oficial": r["checksum_oficial"]})
    man = {"procedencia": "historico_oficial", "fuente": "https://data.binance.vision/data", "simbolo": simbolo,
           "intervalo": "1d", "desde": desde, "hasta": hasta, "fecha_utc": dt.datetime.now(dt.UTC).isoformat(),
           "archivos": archivos, "ausentes": ausentes}
    _escribir_manifiesto(destino, man)
    return man


def _ms(v: int) -> tuple[int, int]:
    """(valor en ms, unidades por ms): las marcas del spot desde 2025 vienen en µs."""
    return (v // 1000, 1000) if v > 10 ** 15 else (v, 1)


def leer(directorio: Path) -> tuple[list[Vela], dict]:
    """Velas diarias ordenadas + informe de calidad. Verifica cada archivo contra el manifiesto."""
    man = json.loads((directorio / "MANIFIESTO.json").read_text(encoding="utf-8"))
    if man.get("procedencia") != "historico_oficial":
        raise ValueError("solo datos históricos oficiales")
    velas: dict[str, Vela] = {}
    inc: dict[str, list] = {"duracion_irregular": [], "repetidas": [], "ohlc_incoherente": [], "precio_no_positivo": []}
    for a in man["archivos"]:
        datos = (directorio / a["ruta"]).read_bytes()
        if hashlib.sha256(datos).hexdigest() != a["sha256"]:
            raise ValueError(f"{a['ruta']}: hash distinto del manifiesto (¿archivo alterado?)")
        with zipfile.ZipFile(io.BytesIO(datos)) as z:
            texto = z.read(z.namelist()[0]).decode("utf-8")
        for f in csv.reader(io.StringIO(texto)):
            if not f or not f[0].strip().isdigit():
                continue
            t, u = _ms(int(f[0]))
            cierre = int(f[6])
            d = dt.datetime.fromtimestamp(t / 1000, dt.UTC).date().isoformat()
            if t % DIA_MS or cierre != int(f[0]) + DIA_MS * u - 1:
                inc["duracion_irregular"].append(d)
            o, h, lo, c = (float(x) for x in f[1:5])
            if min(o, h, lo, c) <= 0:
                inc["precio_no_positivo"].append(d)
                continue
            if not (lo <= min(o, c) and h >= max(o, c)):
                inc["ohlc_incoherente"].append(d)
            if d in velas:
                inc["repetidas"].append(d)
            velas[d] = Vela(d, o, h, lo, c, float(f[7]))
    dias = sorted(velas)
    ausentes, prev = [], None
    for d in dias:
        if prev is not None:
            g = (dt.date.fromisoformat(d) - dt.date.fromisoformat(prev)).days
            ausentes += [(dt.date.fromisoformat(prev) + dt.timedelta(days=k)).isoformat() for k in range(1, g)]
        prev = d
    if dias and dias[-1] >= RESERVADO_INICIO:
        raise AssertionError("dato del período reservado")
    inf = {"simbolo": man["simbolo"], "archivos": len(man["archivos"]), "meses_no_publicados": man["ausentes"],
           "primer_dia": dias[0] if dias else None, "ultimo_dia": dias[-1] if dias else None, "dias": len(dias),
           "dias_ausentes": ausentes, **{k: v for k, v in inc.items()},
           "manifiesto_sha256": hashlib.sha256((directorio / "MANIFIESTO.json").read_bytes()).hexdigest()}
    inf["apto"] = not ausentes and not inc["repetidas"] and not inc["precio_no_positivo"] and not inc["ohlc_incoherente"]
    return [velas[d] for d in dias], inf
