"""Evaluación en papel: reglas congeladas, guardas del período reservado y de lo prospectivo, criterios y ventana."""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import math
import zipfile
from pathlib import Path

import pytest

from tendencia import datos as D
from tendencia import papel as P


def _directorio(tmp: Path, simbolo: str, desde: str, dias: int, semilla: float = 0.0) -> Path:
    d0 = dt.date.fromisoformat(desde)
    filas, prev = [], 100.0
    for k in range(dias):
        t = int(dt.datetime.combine(d0 + dt.timedelta(days=k), dt.time(), dt.UTC).timestamp() * 1000)
        c = 100 * math.exp(0.3 * math.sin(k / 40 + semilla) + 0.0005 * k)
        filas.append(f"{t * 1000},{prev},{max(prev, c)},{min(prev, c)},{c},1,{(t + D.DIA_MS) * 1000 - 1},1e6,1,0,0,0")
        prev = c
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("x.csv", "\n".join(filas) + "\n")
    out = tmp / simbolo
    rel = "spot/daily/klines/x.zip"
    (out / rel).parent.mkdir(parents=True)
    (out / rel).write_bytes(buf.getvalue())
    (out / "MANIFIESTO.json").write_text(json.dumps({"procedencia": "historico_oficial", "simbolo": simbolo, "ausentes": [],
                                                    "archivos": [{"ruta": rel, "sha256": hashlib.sha256(buf.getvalue()).hexdigest()}]}))
    return out


def test_reglas_congeladas_y_ramas() -> None:
    assert P.hash_prerregistro() == P.hash_prerregistro() and len(P.huella_codigo()) == 64
    assert P.PRERREGISTRO_PAPEL["estrategias"]["T_BTC"]["ventanas"] == [30, 90, 180]
    assert P.primera_ejecucion("A") == "2026-10-18" and P.primera_ejecucion("B") == "2027-04-13"


def test_guardas_del_periodo_reservado_y_de_lo_prospectivo(tmp_path: Path) -> None:
    with pytest.raises(PermissionError):
        P.descargar(tmp_path, "BTCUSDT", "2026-04-20", "2026-10-18")  # toca el reservado: falla antes de bajar nada
    reservado = _directorio(tmp_path, "R", "2026-09-01", 20)
    with pytest.raises(AssertionError, match="reservado"):
        D.leer(reservado, permitir_prospectivo=True)
    prospectivo = _directorio(tmp_path, "Q", "2026-10-14", 20)
    with pytest.raises(AssertionError, match="prospectivo"):
        D.leer(prospectivo)
    assert len(D.leer(prospectivo, permitir_prospectivo=True)[0]) == 20


def test_criterios_prerregistrados() -> None:
    assert P.decidir(6, 0.01, 0.01, -1).startswith("INFORMATIVO")
    assert P.decidir(12, 0.05, 0.5, 1).startswith("HIPÓTESIS NO RESPALDADA")
    assert P.decidir(18, 0.99, 0.99, 1).startswith("EVIDENCIA INSUFICIENTE")  # antes de 24 meses no se confirma
    assert P.decidir(24, 0.96, 0.91, 0.01) == "VENTAJA RESPALDADA"
    assert P.decidir(30, 0.96, 0.85, 0.01).startswith("EVIDENCIA INSUFICIENTE")
    assert P.decidir(30, 0.96, 0.95, -0.01).startswith("EVIDENCIA INSUFICIENTE")


def test_la_evaluacion_empieza_en_la_primera_ejecucion_y_no_antes(tmp_path: Path) -> None:
    dirs = {"T_BTC": _directorio(tmp_path, "BTC", "2026-10-14", 700),
            "T_ETH": _directorio(tmp_path, "ETH", "2026-10-14", 700, semilla=1.0)}
    assert P.evaluar(dirs, "2027-04-13", rama="B")["estado"].startswith("sin datos")
    r = P.evaluar(dirs, "2028-04-13", rama="B")
    assert r["dias"] == (dt.date(2028, 4, 13) - dt.date(2027, 4, 13)).days and r["meses"] > 11.9
    assert r["T_BTC"]["T"]["dias"] == r["dias"] and "decision" in r
