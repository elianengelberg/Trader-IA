"""Pipeline de datos de extremo a extremo con archivos en formato oficial FABRICADOS (sintéticos): procedencia que no se
puede falsear, verificación contra el manifiesto y los .CHECKSUM, importación, cobertura, meses no publicados,
reanudación e informe de calidad con sus filtros."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from hcarry.data import binance_vision as BV
from hcarry.data import calidad
from hcarry.data.fabricar import fabricar_sintetico
from hcarry.data.sintetico import ParamsSintetico, generar
from hcarry.estrategias import Siempre
from hcarry.metricas import calcular
from hcarry.model.motor import simular

PANEL = generar(ParamsSintetico(semilla=3, desde="2024-11-01", hasta="2025-02-01"))  # cruza el cambio a µs del spot


@pytest.fixture()
def fabricado(tmp_path: Path) -> Path:
    d = tmp_path / "fab"
    fabricar_sintetico(PANEL, d)
    return d


def test_procedencia_sintetica_no_puede_pasar_por_historica(fabricado: Path) -> None:
    panel, inf = BV.construir_panel(fabricado, "2024-11-01", "2025-02-01")
    assert panel.origen.startswith("sintetico:") and inf.info["procedencia"] == "sintetico"
    assert calcular(simular(panel, Siempre()))["sintetico"] is True
    assert [b.S_c for b in panel.barras[:50]] == pytest.approx([b.S_c for b in PANEL.barras[:50]], abs=0.006)
    assert len(panel.funding) == len(PANEL.funding) and panel.barras[0].prima is not None


def test_sin_manifiesto_o_con_archivo_alterado_se_rechaza(fabricado: Path, tmp_path: Path) -> None:
    sin = tmp_path / "sin"
    shutil.copytree(fabricado, sin)
    (sin / "MANIFIESTO.json").unlink()
    with pytest.raises(ValueError, match="MANIFIESTO"):
        BV.construir_panel(sin, "2024-11-01", "2025-02-01")
    alterado = tmp_path / "alt"
    shutil.copytree(fabricado, alterado)
    zp = alterado / BV.ruta_mensual("perp", "BTCUSDT", 2024, 12)
    datos = bytearray(zp.read_bytes())
    datos[len(datos) // 2] ^= 0xFF  # un solo byte cambiado
    zp.write_bytes(bytes(datos))
    with pytest.raises(ValueError, match="alterado"):
        BV.construir_panel(alterado, "2024-11-01", "2025-02-01")
    man = json.loads((fabricado / "MANIFIESTO.json").read_text())
    man["procedencia"] = "otra"
    falso = tmp_path / "falso"
    shutil.copytree(fabricado, falso)
    (falso / "MANIFIESTO.json").write_text(json.dumps(man))
    with pytest.raises(ValueError, match="procedencia"):
        BV.construir_panel(falso, "2024-11-01", "2025-02-01")


def test_importar_verifica_los_checksums_y_declara_la_via(fabricado: Path, tmp_path: Path) -> None:
    copia = tmp_path / "copia" / "data"  # estructura de una copia aportada: .../data/spot/monthly/...
    shutil.copytree(fabricado, copia)
    (copia / "MANIFIESTO.json").unlink()
    man = BV.importar(tmp_path / "copia", tmp_path / "imp")
    # sin manifiesto y con checksums válidos, la marca de los zips fabricados impide etiquetarlos como históricos
    assert man["procedencia"] == "sintetico" and man["via"].startswith("importación de archivos FABRICADOS")
    assert len(man["archivos"]) == len(json.loads((fabricado / "MANIFIESTO.json").read_text())["archivos"])
    # un .CHECKSUM que no coincide se rechaza
    zp = next((copia / "futures").rglob("*.zip"))
    zp.with_name(zp.name + ".CHECKSUM").write_text("0" * 64 + "  " + zp.name)
    with pytest.raises(ValueError, match="checksum distinto"):
        BV.importar(tmp_path / "copia", tmp_path / "imp2")
    zp.with_name(zp.name + ".CHECKSUM").unlink()
    with pytest.raises(ValueError, match="falta su .CHECKSUM"):
        BV.importar(tmp_path / "copia", tmp_path / "imp3")


def test_descarga_con_meses_no_publicados_reanudable(fabricado: Path, tmp_path: Path) -> None:
    """La fuente no publica el mark de 2024-11: queda anotado como ausente y el inicio común pasa a 2024-12. Una
    segunda descarga no vuelve a bajar los zips ya verificados."""
    bajados: list[str] = []

    def abrir(url: str) -> bytes:
        rel = url.removeprefix(BV.BASE + "/")
        if "markPriceKlines" in rel and "2024-11" in rel:
            raise BV.NoPublicado(url)
        if not rel.endswith(".CHECKSUM"):
            bajados.append(rel)
        return (fabricado / rel).read_bytes()

    d = tmp_path / "desc"
    man = BV.descargar(d, "2024-11", "2025-02", abrir=abrir)
    assert {"tipo": "mark", "ruta": BV.ruta_mensual("mark", "BTCUSDT", 2024, 11)} in man["ausentes"]
    assert BV.inicio_comun(d) == "2024-12-01" and man["procedencia"] == "historico_oficial"
    n = len(bajados)
    BV.descargar(d, "2024-11", "2025-02", abrir=abrir)
    assert len(bajados) == n  # reanudación: nada se descarga dos veces
    assert all((d / (a["ruta"] + ".CHECKSUM")).exists() for a in man["archivos"])


def test_informe_de_calidad_apto_y_filtros_que_fallan(fabricado: Path, tmp_path: Path) -> None:
    inf = calidad.evaluar(fabricado, hasta="2025-02-01")
    assert inf["apto"] and inf["procedencia"] == "sintetico" and inf["filtros"]["C2_cobertura"]["inicio_comun"] == "2024-11-01"
    assert "SINTÉTICO" in calidad.markdown(inf)
    # hueco de funding: se elimina una liquidación del archivo de diciembre (y se rehace su manifiesto)
    roto = tmp_path / "roto"
    p = PANEL
    fabricar_sintetico(type(p)(p.barras, [e for i, e in enumerate(p.funding) if i != 100], p.origen), roto)
    inf2 = calidad.evaluar(roto, hasta="2025-02-01")
    assert not inf2["apto"] and not inf2["filtros"]["C4_funding"]["ok"]
    # mes requerido ausente dentro de la ventana
    hueco = tmp_path / "hueco"
    fabricar_sintetico(PANEL, hueco, omitir={("spot", "2024-12")})
    inf3 = calidad.evaluar(hueco, hasta="2025-02-01")
    assert not inf3["apto"] and inf3["filtros"]["C2_cobertura"]["faltan"] == {"spot": ["2024-12"]}


def test_checksum_oficial_alterado_falla_c1(fabricado: Path) -> None:
    rel = BV.ruta_mensual("funding", "BTCUSDT", 2025, 1)
    cp = fabricado / (rel + ".CHECKSUM")
    cp.write_text(hashlib.sha256(b"otro").hexdigest() + "  " + rel.rsplit("/", 1)[1])
    inf = calidad.evaluar(fabricado, hasta="2025-02-01")
    assert not inf["filtros"]["C1_procedencia"]["ok"] and not inf["apto"]


def test_el_registro_de_experimentos_hereda_la_procedencia(fabricado: Path, tmp_path: Path) -> None:
    """Un experimento sobre archivos fabricados queda registrado como SINTÉTICO aunque use el cargador oficial."""
    from hcarry.lab import experimento as X
    cfg = {"nombre": "x", "datos": {"fuente": "binance_vision", "directorio": str(fabricado), "desde": "2024-11-01",
                                    "hasta": "2025-02-01"},
           "division": {"desde": "2024-11-01", "hasta": "2025-02-01"},
           "politica": {"nombre": "siempre", "params": {}}, "costes": {}, "filtros": {}, "motor": {}}
    _, m, e = X.correr(cfg, tmp_path / "r.jsonl")
    assert e["categoria"] == "sintetico" and e["datos"]["sintetico"] and "SINTÉTICO" in e["aviso"] and m["sintetico"]


def test_un_archivo_sintetico_no_puede_entrar_en_un_manifiesto_historico(fabricado: Path, tmp_path: Path) -> None:
    falso = tmp_path / "falso"
    shutil.copytree(fabricado, falso)
    man = json.loads((falso / "MANIFIESTO.json").read_text())
    man["procedencia"] = "historico_oficial"  # alguien reescribe el manifiesto
    (falso / "MANIFIESTO.json").write_text(json.dumps(man))
    with pytest.raises(ValueError, match="SINTÉTICO en un manifiesto histórico"):
        BV.construir_panel(falso, "2024-11-01", "2025-02-01")


# ------------------------------------------------------------------ datos reales: velas irregulares y diarios oficiales
def _zip_oficial(nombre_csv: str, lineas: list[str]) -> bytes:
    """Zip con el formato oficial y SIN la marca sintética (simula un archivo del emisor)."""
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(nombre_csv, "\n".join(lineas) + "\n")
    return buf.getvalue()


def _velas(t0: int, n: int, precio: float, cab: bool) -> list[str]:
    from hcarry.conventions import HORA_MS
    filas = [f"{t0 + k * HORA_MS},{precio},{precio + 1},{precio - 1},{precio},1,{t0 + (k + 1) * HORA_MS - 1},"
             f"{precio},10,0,0,0" for k in range(n)]
    return ([("open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,"
             "taker_buy_quote_volume,ignore")] if cab else []) + filas


def test_vela_irregular_se_excluye_y_se_anota_en_vez_de_abortar() -> None:
    from hcarry.conventions import HORA_MS, ms
    t = ms("2020-02-19T11:00")
    lineas = _velas(t - HORA_MS, 1, 100.0, False) + [f"{t},100,101,99,100,1,{t + 35 * 60000},100,10,0,0,0"]
    z = _zip_oficial("x.csv", lineas)
    with pytest.raises(ValueError, match="no dura 1 h"):
        BV.leer_klines(z)
    irr: list = []
    velas = BV.leer_klines(z, irregulares=irr)
    assert t not in velas and t - HORA_MS in velas and irr == [(t, t + 35 * 60000)]


def test_diarios_oficiales_completan_solo_las_horas_ausentes(tmp_path: Path) -> None:
    from hcarry.conventions import HORA_MS, ms
    t0, n = ms("2024-12-01"), 31 * 24
    dia = ms("2024-12-10")
    sin_dia = [x for x in _velas(t0, n, 100.0, True) if not x[:13].isdigit() or not dia <= int(x[:13]) < dia + 24 * HORA_MS]
    sin_dia.insert(1 + 9 * 24, _velas(dia, 1, 100.0, False)[0])  # el mensual conserva la primera hora del día
    fuente = {
        BV.ruta_mensual("spot", "BTCUSDT", 2024, 12): _zip_oficial("s.csv", _velas(t0, n, 100.0, False)),
        BV.ruta_mensual("perp", "BTCUSDT", 2024, 12): _zip_oficial("p.csv", _velas(t0, n, 100.1, True)),
        BV.ruta_mensual("mark", "BTCUSDT", 2024, 12): _zip_oficial("m.csv", sin_dia),
        BV.ruta_mensual("funding", "BTCUSDT", 2024, 12): _zip_oficial("f.csv", [
            "calc_time,funding_interval_hours,last_funding_rate"] + [f"{t0 + k * 8 * HORA_MS},8,0.0001"
                                                                    for k in range(31 * 3)]),
        # diario oficial del mark: 24 h; la primera coincide con el mensual
        BV.ruta_diaria("mark", "BTCUSDT", "2024-12-10"): _zip_oficial("d.csv", _velas(dia, 24, 100.0, True)),
    }

    def abrir(url: str) -> bytes:
        import hashlib
        rel = url.removeprefix(BV.BASE + "/")
        base = rel.removesuffix(".CHECKSUM")
        if base not in fuente:
            raise BV.NoPublicado(url)
        if rel.endswith(".CHECKSUM"):
            return f"{hashlib.sha256(fuente[base]).hexdigest()}  {base.rsplit('/', 1)[1]}\n".encode()
        return fuente[base]

    d = tmp_path / "hist"
    BV.descargar(d, "2024-12", "2025-01", tipos=BV.REQUERIDOS, abrir=abrir)
    _, inf = BV.construir_panel(d, "2024-12-01", "2025-01-01")
    assert inf.info["horas_rellenadas"] == 23  # sin el diario: 23 h de mark ausentes
    man = BV.completar_con_diarios(d, hasta="2025-01-01", abrir=abrir)
    assert [a["ruta"] for a in man["archivos"] if a.get("granularidad") == "diaria"] == [
        BV.ruta_diaria("mark", "BTCUSDT", "2024-12-10")]
    assert BV.cobertura(d)["mark"] == ["2024-12"]  # el diario no altera la cobertura mensual
    antes = (d / "MANIFIESTO.json").read_bytes()
    BV.completar_con_diarios(d, hasta="2025-01-01", abrir=abrir)  # idempotente: sin cambios no reescribe
    assert (d / "MANIFIESTO.json").read_bytes() == antes
    _, inf = BV.construir_panel(d, "2024-12-01", "2025-01-01")
    assert inf.info["horas_rellenadas"] == 0 and inf.info["horas_de_archivos_diarios"] == {"mark": 23}
    assert "D1" not in inf.clases()
    # si el diario contradice al mensual en una hora común, es una incidencia (bloqueante en calidad)
    fuente[BV.ruta_diaria("mark", "BTCUSDT", "2024-12-10")] = _zip_oficial("d.csv", _velas(dia, 24, 100.5, True))
    d2 = tmp_path / "hist2"
    BV.descargar(d2, "2024-12", "2025-01", tipos=BV.REQUERIDOS, abrir=abrir)
    BV.completar_con_diarios(d2, hasta="2025-01-01", abrir=abrir)
    _, inf2 = BV.construir_panel(d2, "2024-12-01", "2025-01-01")
    assert "D1" in inf2.clases()
    # una diferencia SOLO de volumen no bloquea: se conserva el mensual y queda anotada
    vol = _velas(dia, 24, 100.0, True)
    vol[1] = vol[1].replace(",100.0,10,", ",123.0,10,")
    fuente[BV.ruta_diaria("mark", "BTCUSDT", "2024-12-10")] = _zip_oficial("d.csv", vol)
    d3 = tmp_path / "hist3"
    BV.descargar(d3, "2024-12", "2025-01", tipos=BV.REQUERIDOS, abrir=abrir)
    BV.completar_con_diarios(d3, hasta="2025-01-01", abrir=abrir)
    _p3, inf3 = BV.construir_panel(d3, "2024-12-01", "2025-01-01")
    assert "D1" not in inf3.clases() and len(inf3.info["volumen_distinto_diario_mensual"]) == 1
