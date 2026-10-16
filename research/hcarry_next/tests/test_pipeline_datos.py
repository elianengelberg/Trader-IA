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
