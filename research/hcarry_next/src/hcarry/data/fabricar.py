"""Fabrica archivos con el FORMATO de data.binance.vision a partir de un panel SINTÉTICO, para ensayar el pipeline
completo (descarga → importación → calidad → panel → evaluación) sin datos reales.

El manifiesto lleva ``procedencia: "sintetico"`` y ``construir_panel`` etiqueta el panel como sintético: estos archivos
no pueden pasar por históricos. Reproduce las particularidades conocidas del formato: el spot sin cabecera y con marcas
en microsegundos desde 2025; los futuros con cabecera; el funding con unos milisegundos de desfase."""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import zipfile
from pathlib import Path

from hcarry.conventions import HORA_MS, ms
from hcarry.data.binance_vision import MARCA_SINTETICO, Archivo, _escribir_manifiesto, ruta_mensual
from hcarry.data.schema import Panel

CAB_KLINES = ("open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,"
              "taker_buy_quote_volume,ignore")
MICRO_DESDE = ms("2025-01-01")


def _zip(nombre_csv: str, lineas: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.comment = MARCA_SINTETICO
        info = zipfile.ZipInfo(nombre_csv, date_time=(2026, 1, 1, 0, 0, 0))
        z.writestr(info, "\n".join(lineas) + "\n")
    return buf.getvalue()


def _kline(t: int, o: float, h: float, low: float, c: float, qv: float, micro: bool) -> str:
    f = 1000 if micro else 1
    vol = qv / c if c else 0.0
    return f"{t * f},{o:.2f},{h:.2f},{low:.2f},{c:.2f},{vol:.6f},{(t + HORA_MS - 1) * f},{qv:.2f},1000,0,0,0"


def fabricar_sintetico(panel: Panel, destino: Path, simbolo: str = "BTCUSDT", omitir: set[tuple[str, str]] = frozenset()) -> dict:
    """Escribe un archivo mensual por tipo y mes del panel (más su .CHECKSUM) y un manifiesto "sintetico".
    ``omitir``: pares (tipo, 'AAAA-MM') que no se escriben, para ensayar huecos de cobertura."""
    if not panel.sintetico:
        raise ValueError("solo se fabrican archivos a partir de paneles SINTÉTICOS")
    por_mes: dict[str, list] = {}
    for b in panel.barras:
        por_mes.setdefault(dt.datetime.fromtimestamp(b.t / 1000, tz=dt.UTC).strftime("%Y-%m"), []).append(b)
    fund_mes: dict[str, list] = {}
    for e in panel.funding:
        fund_mes.setdefault(dt.datetime.fromtimestamp(e.t / 1000, tz=dt.UTC).strftime("%Y-%m"), []).append(e)
    archivos = []
    for ym, barras in sorted(por_mes.items()):
        a, m = int(ym[:4]), int(ym[5:])
        contenidos = {
            "spot": [_kline(b.t, b.S_o, b.S_h, b.S_l, b.S_c, b.qv_spot or 0.0, b.t >= MICRO_DESDE) for b in barras],
            "perp": [CAB_KLINES] + [_kline(b.t, b.F_o, b.F_h, b.F_l, b.F_c, b.qv_perp or 0.0, False) for b in barras],
            "mark": [CAB_KLINES] + [_kline(b.t, b.M_o, b.M_h, b.M_l, b.M_c, 0.0, False) for b in barras],
            "premium": [CAB_KLINES] + [f"{b.t},{p:.8f},{p:.8f},{p:.8f},{p:.8f},0,{b.t + HORA_MS - 1},0,60,0,0,0"
                                       for b in barras if (p := b.prima) is not None],
            "funding": ["calc_time,funding_interval_hours,last_funding_rate"] + [
                f"{e.t + 3},8,{e.tasa:.8f}" for e in fund_mes.get(ym, [])],
        }
        for tipo, lineas in contenidos.items():
            if (tipo, ym) in omitir or len(lineas) <= (0 if tipo == "spot" else 1):
                continue
            rel = ruta_mensual(tipo, simbolo, a, m)
            nombre = rel.rsplit("/", 1)[1]
            cuerpo = _zip(nombre.replace(".zip", ".csv"), lineas)
            sha = hashlib.sha256(cuerpo).hexdigest()
            p = destino / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(cuerpo)
            p.with_name(nombre + ".CHECKSUM").write_text(f"{sha}  {nombre}\n", encoding="utf-8")
            archivos.append(Archivo(tipo, rel, sha, len(cuerpo), sha).__dict__)
    manifiesto = {"procedencia": "sintetico", "fuente": f"hcarry.data.sintetico ({panel.origen})",
                  "via": "fabricado en formato oficial para ensayar el pipeline", "simbolo": simbolo,
                  "aviso": "SINTÉTICO: no son datos de mercado", "archivos": archivos}
    destino.mkdir(parents=True, exist_ok=True)
    _escribir_manifiesto(destino, manifiesto)
    return manifiesto
