"""Ejecutor de cortes de la evaluación en papel: cada prueba reproduce un defecto operativo detectado el 2026-10-17
con una fuente oficial SIMULADA en memoria (no son datos de mercado ni rendimiento prospectivo)."""

from __future__ import annotations

import csv
import datetime as dt
import fcntl
import hashlib
import importlib.util
import io
import json
import math
import os
import pickle
import select
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from hcarry.data import binance_vision as BV

from tendencia import papel as P

_spec = importlib.util.spec_from_file_location("corte", Path(__file__).resolve().parents[1] / "papel" / "corte.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)  # type: ignore[union-attr]
DIA = 86_400_000


def _zip(nombre: str, lineas: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(nombre, "\n".join(lineas) + "\n")
    return buf.getvalue()


def fuente(hasta: str, desde: str = "2026-04-20", fase: float = 0.0) -> dict[str, bytes]:
    """Archivos con el formato oficial: velas 1d diarias (µs) de BTC y ETH y fundingRate mensual de BTC."""
    out: dict[str, bytes] = {}
    for s, f0 in (("BTCUSDT", fase), ("ETHUSDT", fase + 1.0)):
        d, prev = dt.date.fromisoformat(desde), 100.0
        while d.isoformat() < hasta:
            k = (d - dt.date(2026, 4, 20)).days
            c = 100 * math.exp(0.25 * math.sin(k / 37 + f0) + 0.0004 * k)
            t = int(dt.datetime.combine(d, dt.time(), dt.UTC).timestamp() * 1000)
            out[P.ruta_diaria_1d(s, d.isoformat())] = _zip("x.csv", [
                f"{t * 1000},{prev},{max(prev, c)},{min(prev, c)},{c},1,{(t + DIA) * 1000 - 1},1e6,1,0,0,0"])
            prev, d = c, d + dt.timedelta(days=1)
    a, m = 2026, 6
    while (a, m) < (2028, 1):
        ini = dt.datetime(a, m, 1, tzinfo=dt.UTC)
        fin = dt.datetime(a + (m == 12), 1 if m == 12 else m + 1, 1, tzinfo=dt.UTC)
        if fin.date().isoformat() <= hasta:  # el archivo mensual solo existe con el mes completo
            ev, t = ["calc_time,funding_interval_hours,last_funding_rate"], ini
            while t < fin:
                ev.append(f"{int(t.timestamp() * 1000)},8,0.0001")
                t += dt.timedelta(hours=8)
            out[BV.ruta_mensual("funding", "BTCUSDT", a, m)] = _zip("f.csv", ev)
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return out


def abridor(archivos: dict[str, bytes]):  # type: ignore[no-untyped-def]
    def abrir(url: str) -> bytes:
        rel = url.removeprefix(BV.BASE + "/")
        base = rel.removesuffix(".CHECKSUM")
        if base not in archivos:
            raise BV.NoPublicado(url)
        if rel.endswith(".CHECKSUM"):
            return f"{hashlib.sha256(archivos[base]).hexdigest()}  {base.rsplit('/', 1)[1]}\n".encode()
        return archivos[base]
    return abrir


def espia(abrir=None):  # type: ignore[no-untyped-def]
    """Fuente que anota cada consulta; sin ``abrir`` es una fuente caída que falla en todas."""
    llamadas: list[str] = []

    def f(url: str) -> bytes:
        llamadas.append(url)
        if abrir is None:
            raise ConnectionError(f"fuente caída (simulada): {url}")
        return abrir(url)
    return f, llamadas


def huellas(raiz: Path) -> dict[str, tuple]:
    """TODAS las rutas bajo ``raiz`` (también ocultas: temporales) con su SHA-256, tamaño y mtime en ns; las carpetas
    también cuentan. Detecta archivos cambiados, reescritos con los mismos bytes, nuevos o desaparecidos."""
    out: dict[str, tuple] = {}
    for p in sorted(raiz.rglob("*")):
        s = p.lstat()
        out[p.relative_to(raiz).as_posix()] = ("enlace", os.readlink(p)) if p.is_symlink() else ("carpeta",) if (
            p.is_dir()) else (hashlib.sha256(p.read_bytes()).hexdigest(), s.st_size, s.st_mtime_ns)
    return out


def evaluado(raiz: Path, corte: str = "2027-01-01") -> dict[str, tuple]:
    r = C.ejecutar(corte, raiz=raiz, abrir=abridor(fuente(corte)), base=None)
    assert r["estado"] == "EVALUADO"
    h = huellas(raiz)
    for fin in (".zip", ".CHECKSUM", "MANIFIESTO.json", "resultado.json", "decisiones_BTCUSDT.csv", "REGISTRO.jsonl"):
        assert any(k.endswith(fin) for k in h), fin  # la huella cubre todos los tipos de archivo del corte
    return h


def sin_un_dia(archivos: dict[str, bytes]) -> dict[str, bytes]:
    """La misma fuente sin el 2026-12-31: el corte 2027-01-01 queda NO EVALUABLE (provisional)."""
    return {k: v for k, v in archivos.items() if "-1d-2026-12-31" not in k}


def test_sin_observaciones_y_dia_aun_no_publicado(tmp_path: Path) -> None:
    r = C.ejecutar("2026-10-18", raiz=tmp_path, abrir=abridor(fuente("2026-10-17")), base=None)  # D4: no se cae
    assert r["estado"].startswith("SIN OBSERVACIONES") and "evaluacion" not in r
    assert any("no publicados" in p and "2026-10-17" in p for p in r["problemas"])
    assert any("obsoletos" in p for p in r["problemas"])


def test_historia_incompleta_bloquea_en_vez_de_quedar_fuera_del_mercado(tmp_path: Path) -> None:  # D1
    r = C.ejecutar("2027-01-01", raiz=tmp_path, abrir=abridor(fuente("2027-01-01", desde="2026-10-14")), base=None)
    assert r["estado"].startswith("NO EVALUABLE") and "evaluacion" not in r
    assert any("historia" in p for p in r["problemas"])


def test_datos_obsoletos_bloquean(tmp_path: Path) -> None:  # D2
    r = C.ejecutar("2027-02-01", raiz=tmp_path, abrir=abridor(fuente("2027-01-01")), base=None)
    assert r["estado"].startswith("NO EVALUABLE") and any("obsoletos" in p for p in r["problemas"])


def test_corte_evaluado_registra_decisiones_y_no_se_repite(tmp_path: Path) -> None:  # D3 y D7
    src = abridor(fuente("2027-10-19"))
    r = C.ejecutar("2027-10-19", raiz=tmp_path, abrir=src, base=None)
    assert r["estado"] == "EVALUADO" and not r["problemas"] and r["dias_calendario"] == 366
    assert not r["evaluacion"]["decision"].startswith("INFORMATIVO")  # el corte de 12 meses operativo decide
    with (tmp_path / "2027-10-19" / "decisiones_BTCUSDT.csv").open(encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))
    assert len(filas) == 366 and filas[0]["dia"] == "2026-10-18" and filas[0]["decision_con_cierre_de"] == "2026-10-17"
    assert filas[0]["disponible_desde_utc"] == "2026-10-18T00:00:00Z" and filas[0]["exposicion_objetivo"] != ""
    with pytest.raises(C.CorteBloqueado, match="ya está EVALUADO"):  # repetir se detiene y no duplica
        C.ejecutar("2027-10-19", raiz=tmp_path, abrir=src, base=None)
    lineas = (tmp_path / "REGISTRO.jsonl").read_text(encoding="utf-8").splitlines()
    assert sum(json.loads(x)["corte"] == "2027-10-19" for x in lineas) == 1


@pytest.mark.parametrize("corte", ["20270418", "20271019"])
def test_una_fecha_no_canonica_se_rechaza_sin_tocar_nada(tmp_path: Path, corte: str) -> None:  # D10
    src, llamadas = espia(abridor({}))
    with pytest.raises(ValueError, match="forma canónica"):  # sería otro corte para el mismo día
        C.ejecutar(corte, raiz=tmp_path / "cortes", abrir=src, base=None)
    assert llamadas == [] and not (tmp_path / "cortes").exists()


def test_el_corte_del_2027_10_18_no_decide_con_el_codigo_congelado() -> None:
    """Documenta la convención: 365 días = 11,99 «meses» (días/30,44) → informativo; el corte operativo es 2027-10-19."""
    assert P.decidir(365 / 30.44, 0.01, 0.01, -1).startswith("INFORMATIVO")
    assert P.decidir(366 / 30.44, 0.01, 0.01, -1).startswith("HIPÓTESIS NO RESPALDADA")


def test_un_resultado_evaluado_es_inmutable(tmp_path: Path) -> None:
    src = abridor(fuente("2027-01-01"))
    C.ejecutar("2027-01-01", raiz=tmp_path, abrir=src, base=None)
    p = tmp_path / "2027-01-01" / "resultado.json"
    alterado = json.loads(p.read_text(encoding="utf-8"))
    alterado["evaluacion"]["exceso_anual_conjunto"] = 9.99
    p.write_text(json.dumps(alterado), encoding="utf-8")
    with pytest.raises(RuntimeError, match="EVALUADO"):
        C.ejecutar("2027-01-01", raiz=tmp_path, abrir=src, base=None)


def test_revision_de_un_archivo_oficial_ya_registrado(tmp_path: Path) -> None:  # D6
    archivos = fuente("2027-01-01")
    C.ejecutar("2027-01-01", raiz=tmp_path, abrir=abridor(archivos), base=None)
    revisado = dict(archivos)
    rel = P.ruta_diaria_1d("BTCUSDT", "2026-11-05")
    revisado[rel] = revisado[rel].replace(b"x.csv", b"y.csv")
    r = C.ejecutar("2027-01-02", raiz=tmp_path, abrir=abridor(revisado), base=None)
    assert any("revisado" in p for p in r["problemas"]) and r["estado"].startswith("NO EVALUABLE")


def test_monitor_usa_meses_completos_y_no_actua(tmp_path: Path) -> None:  # D5
    r = C.ejecutar("2026-11-17", raiz=tmp_path, abrir=abridor(fuente("2026-11-17")), base=None)
    m = r["monitor_carry"]
    assert (m["ventana_desde"], m["ventana_hasta_exclusivo"]) == ("2026-08-03", "2026-11-01")
    assert m["cobertura"] == 1.0 and m["apr_90d"] == pytest.approx(0.0001 * 3 * 365)
    assert m["disparador_12pct"] is False and m["accion"].startswith("ninguna")


def test_codigo_o_reglas_distintos_bloquean(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(P, "huella_codigo", lambda: "0" * 64)
    r = C.ejecutar("2027-01-01", raiz=tmp_path, abrir=abridor(fuente("2027-01-01")), base=None)
    assert "código distinto del congelado" in r["problemas"] and r["estado"].startswith("NO EVALUABLE")


def test_reintento_de_un_corte_evaluado_con_otra_fuente_no_la_consulta_ni_toca_nada(tmp_path: Path) -> None:  # D7
    antes = evaluado(tmp_path)
    otra, llamadas = espia(abridor(fuente("2027-01-01", fase=0.5)))  # precios distintos, con checksums válidos
    with pytest.raises(C.CorteBloqueado, match="corte 2027-01-01: ya está EVALUADO"):
        C.ejecutar("2027-01-01", raiz=tmp_path, abrir=otra, base=None)
    assert llamadas == [] and huellas(tmp_path) == antes


@pytest.mark.parametrize("caida", ["red", "no_publicado"])
def test_reintento_de_un_corte_evaluado_con_la_fuente_caida_no_la_consulta_ni_toca_nada(tmp_path: Path, caida: str
                                                                                       ) -> None:  # D7
    antes = evaluado(tmp_path, "2027-02-01")
    if caida == "red":
        src, llamadas = espia()
    else:  # la fuente ya no publica nada (404 en todo)
        src, llamadas = espia(abridor({}))
    with pytest.raises(C.CorteBloqueado, match="corte 2027-02-01: ya está EVALUADO"):
        C.ejecutar("2027-02-01", raiz=tmp_path, abrir=src, base=None)
    assert llamadas == [] and huellas(tmp_path) == antes


@pytest.mark.parametrize("dano", ["truncado", "no_utf8", "no_es_objeto", "sin_estado", "estado_desconocido",
                                  "otro_corte", "carpeta", "enlace_roto"])
def test_un_resultado_existente_ilegible_detiene_sin_tocar_nada(tmp_path: Path, dano: str) -> None:  # D7
    evaluado(tmp_path)
    p = tmp_path / "2027-01-01" / "resultado.json"
    b = p.read_bytes()
    if dano == "carpeta":
        p.unlink()
        p.mkdir()
    elif dano == "enlace_roto":  # no se trata como si no existiera
        p.unlink()
        p.symlink_to(p.parent / "no_existe.json")
    else:
        p.write_bytes({"truncado": b[: len(b) // 2], "no_utf8": b"\xff\xfe" + b, "no_es_objeto": b"[]",
                       "sin_estado": b'{"corte_exclusivo": "2027-01-01"}',
                       "estado_desconocido": b'{"corte_exclusivo": "2027-01-01", "estado": "OTRO"}',
                       "otro_corte": b'{"corte_exclusivo": "2027-01-02", "estado": "NO EVALUABLE"}'}[dano])
    antes = huellas(tmp_path)
    src, llamadas = espia(abridor(fuente("2027-01-01")))
    with pytest.raises(C.CorteBloqueado, match="no puede interpretarse|inesperado"):
        C.ejecutar("2027-01-01", raiz=tmp_path, abrir=src, base=None)
    assert llamadas == [] and huellas(tmp_path) == antes


def test_un_resultado_nuevo_se_escribe_completo_y_sin_temporales(tmp_path: Path) -> None:  # D7
    r = C.ejecutar("2027-01-01", raiz=tmp_path, abrir=abridor(fuente("2027-01-01")), base=None)
    texto = (tmp_path / "2027-01-01" / "resultado.json").read_text(encoding="utf-8")
    assert texto == C._canon(r) and json.loads(texto)["estado"] == "EVALUADO"
    assert not [k for k in huellas(tmp_path) if k.endswith(".tmp")]
    ultima = json.loads((tmp_path / "REGISTRO.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert ultima["resultado_sha256"] == hashlib.sha256(texto.encode()).hexdigest()


@pytest.mark.parametrize("falla", ["tablas", "sincronizacion", "escritura", "reemplazo"])
def test_un_fallo_antes_del_reemplazo_no_deja_un_resultado_parcial(tmp_path: Path, monkeypatch, falla: str  # type: ignore[no-untyped-def]
                                                                   ) -> None:  # D7
    completa = fuente("2027-01-01")  # una sola: los zips simulados llevan la hora en que se generan
    C.ejecutar("2027-01-01", raiz=tmp_path, abrir=abridor(sin_un_dia(completa)), base=None)
    p, registro = tmp_path / "2027-01-01" / "resultado.json", tmp_path / "REGISTRO.jsonl"
    previo, reg = p.read_bytes(), registro.read_bytes()
    assert json.loads(previo)["estado"].startswith("NO EVALUABLE")

    def boom(*_a, **_k):  # type: ignore[no-untyped-def]
        raise OSError(f"fallo simulado: {falla}")
    real_replace, real_fsync = os.replace, os.fsync
    tmp = tmp_path / "2027-01-01" / f".resultado.json.{'0' * 16}.tmp"
    if falla == "tablas":
        monkeypatch.setattr(C.csv, "DictWriter", boom)
    elif falla == "sincronizacion":  # el primer fsync: datos y tablas, antes de escribir resultado.json
        monkeypatch.setattr(C.os, "fsync", boom)
    elif falla == "escritura":  # solo el fsync del temporal de resultado.json
        monkeypatch.setattr(C.secrets, "token_hex", lambda _n: "0" * 16)
        monkeypatch.setattr(C.os, "fsync", lambda fd: boom() if tmp.exists() and os.fstat(fd).st_ino == tmp.stat().st_ino
                            else real_fsync(fd))
    elif falla == "reemplazo":  # solo el de resultado.json: los datos de hcarry también usan os.replace
        monkeypatch.setattr(C.os, "replace", lambda a, b: boom() if Path(b).name == "resultado.json"
                            else real_replace(a, b))
    with pytest.raises(OSError) as e:
        C.ejecutar("2027-01-01", raiz=tmp_path, abrir=abridor(completa), base=None)
    assert str(e.value) == f"fallo simulado: {falla}"  # el fallo es el simulado, no otro anterior
    marcos = {x.name for x in e.traceback}
    assert {"tablas": "_sincronizar" not in marcos,
            "sincronizacion": "_sincronizar" in marcos and "_escribir_atomico" not in marcos,
            "escritura": "_escribir_atomico" in marcos and "_sincronizar" not in marcos,
            "reemplazo": "_escribir_atomico" in marcos}[falla]
    assert p.read_bytes() == previo and registro.read_bytes() == reg  # sigue el provisional; nada se registró
    assert not [k for k in huellas(tmp_path) if k.endswith(".tmp")]
    monkeypatch.undo()  # el intento fallido no dejó el corte marcado ni inutilizable
    assert C.ejecutar("2027-01-01", raiz=tmp_path, abrir=abridor(completa), base=None)["estado"] == "EVALUADO"


def test_si_no_se_puede_borrar_el_temporal_se_conserva_el_error_original(tmp_path: Path, monkeypatch  # type: ignore[no-untyped-def]
                                                                         ) -> None:  # D7
    def no_reemplaza(*_a):  # type: ignore[no-untyped-def]
        raise OSError("reemplazo simulado")

    def no_borra(*_a, **_k):  # type: ignore[no-untyped-def]
        raise PermissionError("borrado simulado")
    monkeypatch.setattr(C.os, "replace", no_reemplaza)
    monkeypatch.setattr(C.Path, "unlink", no_borra)
    with pytest.raises(OSError) as e:
        C._escribir_atomico(tmp_path / "resultado.json", "{}\n")
    assert str(e.value) == "reemplazo simulado" and "no se pudo borrar el temporal" in e.value.__notes__[0]
    assert not (tmp_path / "resultado.json").exists()  # nada aparece con el nombre del resultado
    assert [x.name.startswith(".resultado.json.") for x in tmp_path.iterdir()] == [True]


# D8: consistencia entre los resultados y REGISTRO.jsonl. D9: cerrojo entre procesos. Durabilidad (fsync).

def _lineas(raiz: Path) -> list[str]:
    return (raiz / "REGISTRO.jsonl").read_text(encoding="utf-8").splitlines(keepends=True)


def dos_lineas(raiz: Path) -> dict[str, bytes]:
    """Estado coherente de partida, con una sola fuente: 2027-01-01 provisional (línea 1) y después EVALUADO (línea 2)."""
    completa = fuente("2027-02-01")
    C.ejecutar("2027-01-01", raiz=raiz, abrir=abridor(sin_un_dia(completa)), base=None)
    C.ejecutar("2027-01-01", raiz=raiz, abrir=abridor(completa), base=None)
    assert [json.loads(x)["estado"][:8] for x in _lineas(raiz)] == ["NO EVALU", "EVALUADO"]
    return completa


def detecta_sin_tocar(raiz: Path, tipo: str) -> None:
    """La inconsistencia detiene el mismo corte y uno nuevo, una y otra vez (no se repara), sin consultar la fuente, sin
    crear la carpeta del corte nuevo y sin tocar ningún archivo."""
    antes = huellas(raiz)
    for corte in ("2027-01-01", "2027-02-01", "2027-01-01", "2027-02-01"):
        src, llamadas = espia(abridor({}))
        with pytest.raises(C.CorteInconsistente, match=tipo):
            C.ejecutar(corte, raiz=raiz, abrir=src, base=None)
        assert llamadas == [] and huellas(raiz) == antes and not (raiz / "2027-02-01").exists()


DANOS = {"evaluado_sin_entrada": "EVALUADO sin entrada en el registro", "entrada_sin_resultado": "entrada EVALUADO sin "
         "resultado", "hash_distinto": "hash distinto", "resultado_contradice": "resultado contradice el registro",
         "estado_contradictorio": "estado contradictorio", "duplicado": "entrada posterior a la evaluación",
         "cadena_editada": "cadena rota", "cadena_reordenada": "cadena rota", "linea_truncada": "línea incompleta",
         "linea_truncada_con_salto": "línea inválida", "campo_ausente": "línea inválida",
         "registro_no_utf8": "registro ilegible"}


@pytest.mark.parametrize("dano", list(DANOS))
def test_una_inconsistencia_detiene_todo_sin_tocar_nada_ni_repararla(tmp_path: Path, dano: str) -> None:  # D8
    dos_lineas(tmp_path)
    reg, res = tmp_path / "REGISTRO.jsonl", tmp_path / "2027-01-01" / "resultado.json"
    l1, l2 = _lineas(tmp_path)
    x1, x2, r = json.loads(l1), json.loads(l2), json.loads(res.read_text(encoding="utf-8"))
    if dano == "evaluado_sin_entrada":  # se perdió la línea del EVALUADO
        reg.write_text(l1, encoding="utf-8")
    elif dano == "entrada_sin_resultado":
        res.unlink()
    elif dano == "hash_distinto":  # sigue EVALUADO, con otro contenido
        r["evaluacion"]["exceso_anual_conjunto"] = 9.99
        res.write_text(C._canon(r), encoding="utf-8")
    elif dano == "resultado_contradice":  # el archivo dice provisional y el registro, EVALUADO
        r["estado"] = "NO EVALUABLE (editado)"
        res.write_text(C._canon(r), encoding="utf-8")
    elif dano == "estado_contradictorio":  # se editó la última línea (la cadena no la ancla): mismo hash, otro estado
        reg.write_text(l1 + json.dumps({**x2, "estado": "NO EVALUABLE (editado)"}, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    elif dano == "duplicado":  # segunda entrada para el corte evaluado, con la cadena bien hecha
        otra = {**x2, "linea_anterior_sha256": hashlib.sha256(l2.rstrip("\n").encode()).hexdigest()}
        reg.write_text(l1 + l2 + json.dumps(otra, ensure_ascii=False) + "\n", encoding="utf-8")
    elif dano == "cadena_editada":  # se editó la línea 1: la 2 ya no la encadena
        reg.write_text(json.dumps({**x1, "ejecutado_utc": "2000-01-01T00:00:00+00:00"}, ensure_ascii=False) + "\n" + l2,
                       encoding="utf-8")
    elif dano == "cadena_reordenada":
        reg.write_text(l2 + l1, encoding="utf-8")
    elif dano == "linea_truncada":  # escritura interrumpida a mitad de la línea
        reg.write_text(l1 + l2[: len(l2) // 2], encoding="utf-8")
    elif dano == "linea_truncada_con_salto":
        reg.write_text(l1 + l2[: len(l2) // 2] + "\n", encoding="utf-8")
    elif dano == "campo_ausente":
        reg.write_text(l1 + json.dumps({k: v for k, v in x2.items() if k != "resultado_sha256"}) + "\n",
                       encoding="utf-8")
    elif dano == "registro_no_utf8":
        reg.write_bytes(b"\xff" + reg.read_bytes())
    detecta_sin_tocar(tmp_path, DANOS[dano])


@pytest.mark.parametrize("falla", ["linea", "sincronizacion_carpeta", "sincronizacion_registro"])
def test_un_fallo_tras_el_reemplazo_se_detecta_en_la_siguiente_ejecucion(tmp_path: Path, monkeypatch, falla: str  # type: ignore[no-untyped-def]
                                                                         ) -> None:  # D8
    completa = fuente("2027-02-01")
    C.ejecutar("2027-01-01", raiz=tmp_path, abrir=abridor(sin_un_dia(completa)), base=None)  # línea 1, provisional
    reg = tmp_path / "REGISTRO.jsonl"
    previo = reg.read_bytes()
    reemplazado: list[bool] = []
    real_replace, real_fsync, real_open = os.replace, os.fsync, Path.open

    def boom(*_a, **_k):  # type: ignore[no-untyped-def]
        raise OSError(f"fallo simulado: {falla}")

    def reemplazar(a, b):  # type: ignore[no-untyped-def]
        real_replace(a, b)
        reemplazado.append(Path(b).name == "resultado.json")
    if falla == "linea":  # no se puede abrir el registro para añadir la línea
        monkeypatch.setattr(C.Path, "open", lambda self, mode="r", *a, **k: boom() if self.name == "REGISTRO.jsonl"
                            and "a" in mode else real_open(self, mode, *a, **k))
    elif falla == "sincronizacion_carpeta":  # el primer fsync después del reemplazo (la carpeta del corte)
        monkeypatch.setattr(C.os, "replace", reemplazar)
        monkeypatch.setattr(C.os, "fsync", lambda fd: boom() if any(reemplazado) else real_fsync(fd))
    else:  # el fsync del registro, con la línea ya escrita
        monkeypatch.setattr(C.os, "fsync", lambda fd: boom() if os.fstat(fd).st_ino == reg.stat().st_ino
                            else real_fsync(fd))
    with pytest.raises(OSError, match=f"fallo simulado: {falla}"):
        C.ejecutar("2027-01-01", raiz=tmp_path, abrir=abridor(completa), base=None)
    monkeypatch.undo()
    assert json.loads((tmp_path / "2027-01-01" / "resultado.json").read_text(encoding="utf-8"))["estado"] == "EVALUADO"
    if falla == "sincronizacion_registro":  # la línea llegó a escribirse: coherente (su durabilidad no consta)
        assert len(_lineas(tmp_path)) == 2
        with pytest.raises(C.CorteBloqueado, match="ya está EVALUADO") as e:
            C.ejecutar("2027-01-01", raiz=tmp_path, abrir=espia(abridor({}))[0], base=None)
        assert not isinstance(e.value, C.CorteInconsistente)
    else:
        assert reg.read_bytes() == previo  # el resultado se reemplazó y su línea no está
        detecta_sin_tocar(tmp_path, "EVALUADO sin entrada en el registro")


HIJO = r'''
import importlib.util, json, os, pickle, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("prueba", sys.argv[1])
T = importlib.util.module_from_spec(spec)
spec.loader.exec_module(T)
modo, raiz, corte = sys.argv[2], Path(sys.argv[3]), sys.argv[4]
abrir = T.abridor(pickle.loads(Path(sys.argv[5]).read_bytes()))
llamadas = []


def fuente(url):
    llamadas.append(url)
    if modo == "esperar" and len(llamadas) == 1:  # ya tiene el cerrojo: avisa y espera a mitad de preparar()
        print("listo", flush=True)
        sys.stdin.readline()
    return abrir(url)


if modo == "morir_tras_reemplazo":
    real = os.replace

    def reemplazar(a, b):
        real(a, b)
        if Path(b).name == "resultado.json":
            os._exit(17)  # muerte real: no corre ningún except ni finally, ni la línea del registro
    T.C.os.replace = reemplazar
try:
    salida = {"estado": T.C.ejecutar(corte, raiz=raiz, abrir=fuente, base=None)["estado"]}
except T.C.CorteBloqueado as e:
    salida = {"error": type(e).__name__, "mensaje": str(e)}
print(json.dumps({**salida, "llamadas": len(llamadas)}), flush=True)
'''


def hijo(modo: str, raiz: Path, corte: str, archivos: Path) -> subprocess.Popen:
    """Otro proceso que ejecuta un corte con la fuente simulada guardada en ``archivos`` (fuera de la carpeta de cortes),
    con los mismos paquetes que importó esta prueba y el mismo corte.py."""
    paquetes = [Path(P.__file__).resolve().parents[1], Path(BV.__file__).resolve().parents[2]]
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": os.pathsep.join(map(str, paquetes))}
    return subprocess.Popen([sys.executable, "-B", "-c", HIJO, __file__, modo, str(raiz), corte, str(archivos)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)


def listo(p: subprocess.Popen) -> None:
    if not select.select([p.stdout], [], [], 60)[0]:
        p.kill()
        raise AssertionError("el otro proceso no llegó a tomar el cerrojo")
    linea = p.stdout.readline()  # type: ignore[union-attr]
    assert linea.strip() == "listo", (linea, p.stderr.read() if p.poll() is not None else "")  # type: ignore[union-attr]


def fin(p: subprocess.Popen, entrada: str | None = None) -> dict:
    out, err = p.communicate(entrada, timeout=120)
    assert p.returncode == 0, err
    return json.loads(out.strip().splitlines()[-1])


def con_hijos(tmp_path: Path) -> tuple[Path, Path, dict[str, bytes]]:
    raiz, archivos, completa = tmp_path / "cortes", tmp_path / "fuente.pkl", fuente("2027-02-01")
    archivos.write_bytes(pickle.dumps(completa))  # todos los procesos ven exactamente los mismos bytes
    return raiz, archivos, completa


def test_muerte_real_entre_el_reemplazo_y_el_registro_se_detecta_sin_tocar_nada(tmp_path: Path) -> None:  # D8
    raiz, archivos, completa = con_hijos(tmp_path)
    C.ejecutar("2027-01-01", raiz=raiz, abrir=abridor(sin_un_dia(completa)), base=None)  # crea la carpeta; línea 1
    previo = (raiz / "REGISTRO.jsonl").read_bytes()
    p = hijo("morir_tras_reemplazo", raiz, "2027-01-01", archivos)
    out, err = p.communicate(timeout=120)
    assert p.returncode == 17 and out == "", err  # murió justo después del reemplazo, sin llegar a informar nada
    assert json.loads((raiz / "2027-01-01" / "resultado.json").read_text(encoding="utf-8"))["estado"] == "EVALUADO"
    assert (raiz / "REGISTRO.jsonl").read_bytes() == previo  # su línea nunca se escribió
    detecta_sin_tocar(raiz, "EVALUADO sin entrada en el registro")  # y el cerrojo del proceso muerto quedó libre


def test_con_el_cerrojo_tomado_otro_proceso_se_detiene_sin_tocar_nada(tmp_path: Path) -> None:  # D9
    raiz, archivos, _ = con_hijos(tmp_path)
    a = hijo("esperar", raiz, "2027-01-01", archivos)
    listo(a)  # A tiene el cerrojo y está detenido a mitad de preparar()
    antes = huellas(raiz)
    for corte in ("2027-01-01", "2027-02-01"):  # el mismo corte, y otro que comparte el registro
        r = fin(hijo("normal", raiz, corte, archivos))
        assert r["error"] == "CorteBloqueado" and "tiene el cerrojo" in r["mensaje"] and r["llamadas"] == 0
        src, llamadas = espia(abridor({}))  # también desde otro descriptor de este mismo proceso
        with pytest.raises(C.CorteBloqueado, match="tiene el cerrojo"):
            C.ejecutar(corte, raiz=raiz, abrir=src, base=None)
        assert llamadas == [] and huellas(raiz) == antes
    assert fin(a, "\n")["estado"] == "EVALUADO"
    assert fin(hijo("normal", raiz, "2027-02-01", archivos))["estado"] == "EVALUADO"  # después, en orden
    assert "ya está EVALUADO" in fin(hijo("normal", raiz, "2027-01-01", archivos))["mensaje"]
    assert [(x["corte"], x["estado"]) for _, x in C._verificar_estado(raiz, "2099-01-01")] == [
        ("2027-01-01", "EVALUADO"), ("2027-02-01", "EVALUADO")]  # coherente y con la cadena íntegra


@pytest.mark.parametrize("cortes", [("2027-01-01", "2027-01-01"), ("2027-01-01", "2027-02-01")],
                         ids=["mismo_corte", "cortes_distintos"])
def test_dos_procesos_a_la_vez_quedan_serializados_por_el_cerrojo(tmp_path: Path, cortes: tuple[str, str]) -> None:  # D9
    raiz, archivos, completa = con_hijos(tmp_path)
    raiz.mkdir()
    rs = [fin(p) for p in [hijo("normal", raiz, c, archivos) for c in cortes]]  # lanzados juntos
    for r in rs:
        assert r.get("estado") == "EVALUADO" or (r["error"] == "CorteBloqueado" and r["llamadas"] == 0 and (
            "tiene el cerrojo" in r["mensaje"] or "ya está EVALUADO" in r["mensaje"]))
    assert any(r.get("estado") == "EVALUADO" for r in rs)
    for c, r in zip(cortes, rs):  # quien perdió el cerrojo con un corte todavía sin evaluar lo intenta después
        if "tiene el cerrojo" in r.get("mensaje", "") and c not in [x["corte"] for _, x in C._verificar_estado(
                raiz, "2099-01-01")]:
            C.ejecutar(c, raiz=raiz, abrir=abridor(completa), base=None)
    lineas = C._verificar_estado(raiz, "2099-01-01")  # coherente, sin duplicados y con la cadena íntegra
    assert sorted(x["corte"] for _, x in lineas) == sorted(set(cortes)) and all(x["estado"] == "EVALUADO"
                                                                                for _, x in lineas)


def test_el_cerrojo_se_libera_al_morir_o_terminar_y_un_corte_evaluado_se_bloquea(tmp_path: Path) -> None:  # D9
    raiz, archivos, completa = con_hijos(tmp_path)
    a = hijo("esperar", raiz, "2027-01-01", archivos)
    listo(a)
    a.kill()  # SIGKILL: no corre ningún finally
    a.communicate(timeout=60)
    assert a.returncode == -9
    assert all(v == ("carpeta",) for v in huellas(raiz).values())  # solo las carpetas que alcanzó a crear: ningún
    fd = os.open(raiz, os.O_RDONLY)                                 # archivo de cerrojo que haya que borrar
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # libre
    os.close(fd)
    assert C.ejecutar("2027-01-01", raiz=raiz, abrir=abridor(completa), base=None)["estado"] == "EVALUADO"
    fd = os.open(raiz, os.O_RDONLY)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # libre otra vez al terminar normalmente
    os.close(fd)
    src, llamadas = espia(abridor({}))
    with pytest.raises(C.CorteBloqueado, match="ya está EVALUADO") as e:
        C.ejecutar("2027-01-01", raiz=raiz, abrir=src, base=None)
    assert not isinstance(e.value, C.CorteInconsistente) and llamadas == []


@pytest.mark.skipif(not Path("/proc/self/fd").is_dir(), reason="identifica cada fsync por /proc/self/fd")
def test_todo_se_sincroniza_antes_de_la_marca_y_el_registro_despues(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    raiz, eventos = tmp_path.resolve(), []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd):  # type: ignore[no-untyped-def]
        eventos.append(("fsync", os.readlink(f"/proc/self/fd/{fd}")))
        real_fsync(fd)

    def reemplazar(a, b):  # type: ignore[no-untyped-def]
        eventos.append(("replace", str(b)))
        real_replace(a, b)
    monkeypatch.setattr(C.os, "fsync", fsync)
    monkeypatch.setattr(C.os, "replace", reemplazar)
    C.ejecutar("2027-01-01", raiz=raiz, abrir=abridor(fuente("2027-01-01")), base=None)
    monkeypatch.undo()
    d = raiz / "2027-01-01"
    i = eventos.index(("replace", str(d / "resultado.json")))
    antes = {p for e, p in eventos[:i] if e == "fsync"}
    assert {str(p) for p in d.rglob("*") if p.name != "resultado.json"} | {str(d), str(raiz)} <= antes
    assert any("/.resultado.json." in p for p in antes)  # datos, .CHECKSUM, manifiestos, tablas, el temporal y carpetas
    assert eventos[i + 1:] == [("fsync", str(d)), ("fsync", str(raiz / "REGISTRO.jsonl")), ("fsync", str(raiz))]
