"""SIM-1 — piezas comunes: datos verificados, instrumentos y configuración.

Reutiliza sin cambios la metodología de E1 (``e1_comun``: configuración, escenarios, round trips), pero con el
``BacktestEngine`` del paquete ya corregido (D1–D3 en ``tia.backtest.engine``), sin la subclase ``MotorE1``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import e1_comun as C  # noqa: F401  (configuración, escenarios y round trips de E1, sin cambios)
from tia.domain.enums import AssetClass
from tia.domain.instruments import Instrument, InstrumentUniverse
from tia.domain.market import Candle

HORA = timedelta(hours=1)
#: tick y lote: BTCUSDT como en E1; ETHUSDT inferidos de los decimales de los archivos oficiales (ver calidad).
FILTROS = {"BTCUSDT": {"base": "BTC", "tick": 0.01, "lote": 1e-5, "nocional_min": 5.0},
           "ETHUSDT": {"base": "ETH", "tick": 0.01, "lote": 1e-4, "nocional_min": 5.0}}


def leer_velas(raices: list[Path], simbolo: str) -> tuple[list[Candle], dict]:
    """Igual que ``e1_comun.leer_velas`` (checksum antes de leer; µs→ms; conflicto = faltante; sin relleno),
    sobre varias raíces y para cualquier símbolo."""
    filas: dict[int, tuple] = {}
    conflictos: dict[int, set] = {}
    archivos = []
    zips = sorted(z for r in raices for z in r.rglob(f"{simbolo}-1h-*.zip"))
    if not zips:
        raise SystemExit(f"sin archivos de {simbolo}")
    for z in zips:
        datos = z.read_bytes()
        h = hashlib.sha256(datos).hexdigest()
        chk = z.with_name(z.name + ".CHECKSUM")
        oficial = chk.read_text().split()[0] if chk.is_file() else None
        if oficial != h:
            raise SystemExit(f"{z} no coincide con su .CHECKSUM oficial: se detiene")
        archivos.append({"archivo": z.name, "sha256": h, "bytes": len(datos)})
        with zipfile.ZipFile(io.BytesIO(datos)) as f:
            for n in f.namelist():
                for r in csv.reader(io.TextIOWrapper(f.open(n))):
                    t = int(r[0])
                    t = t // 1000 if t > 10**14 else t
                    fila = (float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), int(r[8]))
                    if t in filas and filas[t] != fila:
                        conflictos.setdefault(t, {filas[t]}).add(fila)
                    filas[t] = fila
    for t in conflictos:
        del filas[t]
    velas = []
    for t in sorted(filas):
        o, hi, lo, c, v, n = filas[t]
        ini = datetime.fromtimestamp(t / 1000, tz=timezone.utc)
        velas.append(Candle(symbol=simbolo, timeframe="1h", open_time=ini, close_time=ini + HORA, open=o, high=hi,
                            low=lo, close=c, volume=v, trade_count=n, provider="data.binance.vision"))
    esperadas = int((velas[-1].open_time - velas[0].open_time) / HORA) + 1
    huecos = [(a.open_time.isoformat(), int((b.open_time - a.open_time) / HORA) - 1)
              for a, b in zip(velas, velas[1:]) if b.open_time - a.open_time > HORA]
    lista = "\n".join(f"{a['sha256']}  {a['archivo']}" for a in archivos)
    meta = {"simbolo": simbolo, "fuente": f"data.binance.vision spot klines 1h {simbolo}, verificados contra .CHECKSUM",
            "n_archivos": len(archivos), "sha256_lista_archivos": hashlib.sha256(lista.encode()).hexdigest(),
            "archivos": archivos, "primera_vela": velas[0].open_time.isoformat(),
            "ultima_vela": velas[-1].open_time.isoformat(), "velas": len(velas), "esperadas": esperadas,
            "faltantes": esperadas - len(velas), "huecos": huecos, "zona_horaria": "UTC",
            "transformaciones": "ninguna: sin relleno ni ajuste; close_time = open_time + 1 h",
            "horas_en_conflicto_excluidas": [datetime.fromtimestamp(t / 1000, tz=timezone.utc).isoformat()
                                             for t in sorted(conflictos)]}
    return velas, meta


def universo(simbolo: str) -> InstrumentUniverse:
    f = FILTROS[simbolo]
    return InstrumentUniverse(instruments=(Instrument(
        symbol=simbolo, asset_class=AssetClass.CRYPTO, base_currency=f["base"], quote_currency="USDT",
        tick_size=f["tick"], lot_size=f["lote"], min_notional=f["nocional_min"], shortable=False,
        correlation_cluster="crypto", venue="binance_spot_simulado"),))


def tramo(velas: list[Candle], desde: str | None, hasta: str | None) -> list[Candle]:
    """Velas con open_time en [desde, hasta) (ISO, UTC)."""
    a = datetime.fromisoformat(desde) if desde else None
    b = datetime.fromisoformat(hasta) if hasta else None
    return [v for v in velas if (a is None or v.open_time >= a) and (b is None or v.open_time < b)]
