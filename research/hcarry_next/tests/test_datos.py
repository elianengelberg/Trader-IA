"""Período reservado, validación del calendario de funding (portada de las pruebas a1, a1b y a2 recuperadas de rev. 5)
y lectura de archivos con el formato de data.binance.vision (fabricados localmente: no hay red)."""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import pytest
from ayudas import INI, P0, panel

from hcarry.conventions import HORA_MS, PeriodoReservadoError, comprobar_fuera_de_reservado, ms
from hcarry.data import binance_vision as BV
from hcarry.data.schema import EventoFunding
from hcarry.data.sintetico import ParamsSintetico, generar
from hcarry.data.validacion import validar_funding
from hcarry.estrategias import Siempre
from hcarry.model.motor import simular


# ====================================================================== período reservado
def test_periodo_reservado_bloqueado_en_todas_las_entradas() -> None:
    comprobar_fuera_de_reservado(ms("2024-01-01"), ms("2026-06-01"))  # justo antes: permitido
    comprobar_fuera_de_reservado(ms("2026-10-14"), ms("2026-12-01"))  # justo después: permitido
    for desde, hasta in (("2026-05-31", "2026-06-02"), ("2026-07-01", "2026-08-01"), ("2026-10-13", "2026-10-15")):
        with pytest.raises(PeriodoReservadoError):
            comprobar_fuera_de_reservado(ms(desde), ms(hasta))
    with pytest.raises(PeriodoReservadoError):
        generar(ParamsSintetico(desde="2026-05-01", hasta="2026-07-01"))
    with pytest.raises(PeriodoReservadoError):
        BV.meses("2026-04", "2026-07")
    assert BV.meses("2026-04", "2026-06") == [(2026, 4), (2026, 5)]


# ====================================================================== calendario de funding (rev. 5 a1, a1b, a2)
def _eventos(horas: list[int], tasa: float = 0.0001) -> list[EventoFunding]:
    return [EventoFunding(INI + h * HORA_MS, tasa) for h in horas]


@pytest.mark.parametrize("omitida, texto", [(24, "hueco"), (64, "final"), (0, "principio")])
def test_omisiones_detectables_en_8h(omitida: int, texto: str) -> None:
    ev = _eventos([h for h in range(0, 72, 8) if h != omitida])
    inf = validar_funding(ev, INI, INI + 72 * HORA_MS)
    assert "A2" in inf.clases() and any(texto in i.detalle for i in inf.incidencias)


def test_omision_en_4h_alarga_el_intervalo() -> None:
    ev = _eventos([h for h in range(0, 72, 4) if h != 36])
    assert validar_funding(ev, INI, INI + 72 * HORA_MS).clases() == {"A2b"}


@pytest.mark.parametrize("signo, sentido", [(1, "sobrestima"), (-1, "subestima")])
def test_omision_indetectable_sesga_en_cualquier_direccion(signo: int, sentido: str) -> None:
    """Calendario real de 4 h con tasas alternas ±0,0005; el registro visto omite las de las 04, 12 y 20 h y parece
    un calendario de 8 h perfecto. Según el signo de lo omitido, el resultado sobrestima o subestima el real."""
    def tasa(h: int) -> float:
        return 0.0005 * signo if h % 8 == 0 else -0.0005 * signo
    real = {h: tasa(h) for h in range(0, 72, 4)}
    visto = {h: f for h, f in real.items() if h % 8 != 4}
    ini, fin = INI, INI + 72 * HORA_MS
    ev_real = [EventoFunding(INI + h * HORA_MS, f) for h, f in sorted(real.items())]
    ev_visto = [EventoFunding(INI + h * HORA_MS, f) for h, f in sorted(visto.items())]
    inf_r, inf_v = validar_funding(ev_real, ini, fin), validar_funding(ev_visto, ini, fin)
    assert inf_r.clases() == inf_v.clases() == set()                   # nada lo delata
    assert inf_v.info["funding"]["intervalos_h"] == {"8": 8} and inf_r.info["funding"]["intervalos_h"] == {"4": 17}
    r_real = simular(panel([P0] * 72, real), Siempre())
    r_visto = simular(panel([P0] * 72, visto), Siempre())
    assert r_visto.final - r_real.final == pytest.approx(signo * 9 * 0.083 * P0 * 0.0005, abs=1e-9)
    assert (r_visto.final > r_real.final) == (sentido == "sobrestima")


def test_sintetico_pasa_la_validacion_y_tiene_tasa_modal_de_interes() -> None:
    p = generar(ParamsSintetico(semilla=5, desde="2022-01-01", hasta="2022-07-01"))
    inf = validar_funding(p.funding, p.inicio, p.fin)
    assert inf.clases() == set() and inf.info["funding"]["tasa_modal"]["tasa"] == 0.0001
    assert p.sintetico and "SINTÉTICO" in p.notas[0]


# ====================================================================== formato data.binance.vision
def _zip(nombre: str, filas: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(nombre, "\n".join(filas) + "\n")
    return buf.getvalue()


def _klines(ini: int, n: int, precio: float, cabecera: bool, micro: bool = False) -> list[str]:
    filas = [("open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,"
             "taker_buy_quote_volume,ignore")] if cabecera else []
    for k in range(n):
        t = ini + k * HORA_MS
        f = 1000 if micro else 1
        filas.append(f"{t * f},{precio},{precio * 1.01},{precio * 0.99},{precio},1.5,{(t + HORA_MS - 1) * f},"
                     f"{precio * 1.5},100,0.7,{precio * 0.7},0")
    return filas


def _fuente(ini_mes: str, horas: int, faltan: tuple[int, ...] = ()) -> dict[str, bytes]:
    """Archivos de un mes en el formato publicado, con su .CHECKSUM."""
    a, m = int(ini_mes[:4]), int(ini_mes[5:7])
    t0 = ms(f"{ini_mes}-01")
    archivos = {}
    for tipo in ("spot", "perp", "mark", "premium"):
        precio = {"perp": 60_030.0, "premium": 0.0005}.get(tipo, 60_000.0)
        filas = _klines(t0, horas, precio, cabecera=tipo != "spot", micro=tipo == "spot")
        if tipo == "perp":
            filas = [f for k, f in enumerate(filas) if k - 1 not in faltan]
        archivos[BV.ruta_mensual(tipo, "BTCUSDT", a, m)] = _zip("x.csv", filas)
    fund = ["calc_time,funding_interval_hours,last_funding_rate"] + [
        f"{t0 + h * HORA_MS + 3},8,0.0001" for h in range(0, horas, 8)]
    archivos[BV.ruta_mensual("funding", "BTCUSDT", a, m)] = _zip("f.csv", fund)
    salida = {}
    for rel, cuerpo in archivos.items():
        url = f"{BV.BASE}/{rel}"
        salida[url] = cuerpo
        salida[url + ".CHECKSUM"] = f"{hashlib.sha256(cuerpo).hexdigest()}  {rel.rsplit('/', 1)[1]}".encode()
    return salida


def test_rutas_oficiales() -> None:
    assert BV.ruta_mensual("funding", "BTCUSDT", 2023, 1) == \
        "futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2023-01.zip"
    assert BV.ruta_mensual("mark", "BTCUSDT", 2023, 1, "1h") == \
        "futures/um/monthly/markPriceKlines/BTCUSDT/1h/BTCUSDT-1h-2023-01.zip"


def test_descarga_verifica_checksums_y_construye_el_panel(tmp_path: Path) -> None:
    fuente = _fuente("2023-01", 31 * 24, faltan=(100,))
    man = BV.descargar(tmp_path, "2023-01", "2023-02", abrir=lambda u: fuente[u])
    assert len(man["archivos"]) == 5 and all(a["sha256"] == a["checksum_oficial"] for a in man["archivos"])
    panel, inf = BV.construir_panel(tmp_path, "2023-01-01", "2023-02-01")
    assert len(panel.barras) == 31 * 24 and panel.barras[100].relleno and not panel.barras[99].relleno
    assert inf.info["horas_rellenadas"] == 1 and "H1" in {i.clase for i in inf.incidencias}
    assert not inf.bloqueante and len(panel.funding) == 93 and panel.funding[0].t == ms("2023-01-01")
    assert panel.barras[0].S_o == 60_000.0 and panel.barras[0].F_o == 60_030.0   # spot en µs leído en ms
    assert panel.barras[0].prima == 0.0005 and inf.info["meses_sin_prima"] == 0     # índice de prima oficial
    r = simular(panel, Siempre())
    assert not any(o["t"] == panel.barras[100].t for o in r.operaciones)          # sin decisiones en la hora rellenada


def test_checksum_distinto_se_rechaza(tmp_path: Path) -> None:
    fuente = _fuente("2023-01", 48)
    url = f"{BV.BASE}/{BV.ruta_mensual('spot', 'BTCUSDT', 2023, 1)}"
    fuente[url + ".CHECKSUM"] = b"0" * 64 + b"  BTCUSDT-1h-2023-01.zip"
    with pytest.raises(ValueError, match="checksum distinto"):
        BV.descargar(tmp_path / "a", "2023-01", "2023-02", abrir=lambda u: fuente[u])
    fuente[url + ".CHECKSUM"] = b"0" * 64 + b"  otro.zip"
    with pytest.raises(ValueError, match="formato inesperado"):
        BV.descargar(tmp_path / "b", "2023-01", "2023-02", abrir=lambda u: fuente[u])


def test_formatos_inesperados_se_rechazan() -> None:
    with pytest.raises(ValueError, match="columnas"):
        BV.leer_klines(_zip("x.csv", ["1672531200000,1,1,1,1,1"]))
    with pytest.raises(ValueError, match="cabecera"):
        BV.leer_funding(_zip("f.csv", ["1672531200000,0.0001"]))
    with pytest.raises(ValueError, match="1 h"):
        BV.leer_klines(_zip("x.csv", ["1672531200000,1,1,1,1,1,1672531259999,1,1,1,1,0"]))
