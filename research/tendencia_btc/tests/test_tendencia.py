"""Pruebas del motor long/flat: sin look-ahead, costes exactos, benchmarks, señales y lectura de datos oficiales."""

from __future__ import annotations

import io
import itertools
import math
import zipfile
from pathlib import Path

import pytest

from tendencia import datos as D
from tendencia.backtest import Costes, simular
from tendencia.datos import Vela
from tendencia.estadistica import bootstrap_sharpe
from tendencia.metricas import calcular, rendimientos
from tendencia.senal import tsmom, vol_gestionada


def velas(precios: list[float], ini: str = "2020-01-01") -> list[Vela]:
    import datetime as dt
    d0 = dt.date.fromisoformat(ini)
    out, prev = [], precios[0]
    for k, p in enumerate(precios):
        out.append(Vela((d0 + dt.timedelta(days=k)).isoformat(), prev, max(prev, p), min(prev, p), p, 1e6))
        prev = p
    return out


def test_sin_lookahead_en_senales_y_backtest() -> None:
    p = [100 * math.exp(0.01 * math.sin(k / 7) + 0.002 * k) for k in range(400)]
    q = p[:300] + [x * 3 for x in p[300:]]  # el futuro cambia a partir del día 300
    for f in (tsmom, vol_gestionada):
        assert f(p)[:300] == f(q)[:300]
    a = simular(velas(p), tsmom(p), "2020-01-01", "2021-12-31")
    b = simular(velas(q), tsmom(q), "2020-01-01", "2021-12-31")
    # la equity al cierre del día 299 no puede depender de precios posteriores
    assert a.equity[:300] == b.equity[:300]


def test_buy_and_hold_y_coste_exacto_de_ida_y_vuelta() -> None:
    p = [100.0, 110.0, 121.0, 100.0, 90.0]
    v = velas(p)
    r = simular(v, [1.0] * 5, v[0].dia, "2099-01-01")  # objetivo 1 desde la apertura del 2.º día
    # día 1 sin posición; día 2: compra a la apertura (100) con 15 bps
    assert r.operaciones[0]["valor"] == pytest.approx(10_000) and r.costes == pytest.approx(15.0)
    assert r.equity[-1] == pytest.approx(10_000 - 15 + 10_000 / 100 * (90 - 100))
    # ida y vuelta: 0 → 1 → 0 cuesta exactamente 2 × 15 bps del valor negociado
    r2 = simular(velas([100.0] * 6), [0, 1, 1, 0, 0, 0], "2020-01-01", "2099-01-01")
    # compra de 10 000 (coste 15) y venta de la posición, que vale 10 000 (coste 15)
    assert len(r2.operaciones) == 2 and r2.equity[-1] == pytest.approx(10_000 - 15 - 15)


def test_estatica_sin_costes_rebalanceo_diario() -> None:
    p = [100.0, 120.0, 90.0, 95.0, 130.0]
    r = simular(velas(p), [0.5] * 5, "2020-01-01", "2099-01-01", costes=Costes(0, 0), banda=0.0)
    # desde el día 2, cada día rinde 0,5 × r_btc (la apertura de cada día = el cierre del anterior)
    esperado = 10_000 * math.prod(1 + 0.5 * (b / a - 1) for a, b in itertools.pairwise(p))
    assert r.equity[-1] == pytest.approx(esperado)
    assert all(abs(x - 0.5) < 0.2 for x in r.exposicion[1:])


def test_senales_casos_limite() -> None:
    sube = [100 * 1.01 ** k for k in range(200)]
    baja = [100 * 0.99 ** k for k in range(200)]
    assert tsmom(sube)[-1] == 1 and tsmom(baja)[-1] == 0 and tsmom(sube)[179] is None
    plano = [100.0] * 60
    assert vol_gestionada(plano)[-1] == 1.0
    volatil = [100 * (1.2 if k % 2 else 0.8) for k in range(60)]
    assert vol_gestionada(volatil)[-1] < 0.1


def test_metricas_y_bootstrap() -> None:
    p = [100 * 1.001 ** k for k in range(100)]
    r = simular(velas(p), [1.0] * 100, "2020-01-01", "2099-01-01", costes=Costes(0, 0))
    m = calcular(r)
    assert m["caida_maxima"] == 0 and m["cagr"] > 0 and len(rendimientos(r)) == 100
    a = [0.001 * (1 if k % 3 else -1) for k in range(200)]
    assert bootstrap_sharpe(a, [x / 2 for x in a])["dif_sharpe"] == pytest.approx(0, abs=1e-9)


def _zip(lineas: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("x.csv", "\n".join(lineas) + "\n")
    return buf.getvalue()


def test_lectura_oficial_microsegundos_e_irregulares(tmp_path: Path) -> None:
    import hashlib
    import json
    t = 1735689600000  # 2025-01-01
    micro = f"{t * 1000},1,2,0.5,1.5,10,{(t + D.DIA_MS) * 1000 - 1},15,1,0,0,0"
    irregular = f"{(t + D.DIA_MS) * 1000},1.5,2,1,1.8,10,{(t + D.DIA_MS) * 1000 + 5},15,1,0,0,0"
    rel = D.ruta_1d("BTCUSDT", 2025, 1)
    cuerpo = _zip([micro, irregular])
    (tmp_path / rel).parent.mkdir(parents=True)
    (tmp_path / rel).write_bytes(cuerpo)
    (tmp_path / "MANIFIESTO.json").write_text(json.dumps({
        "procedencia": "historico_oficial", "simbolo": "BTCUSDT", "ausentes": [],
        "archivos": [{"ruta": rel, "sha256": hashlib.sha256(cuerpo).hexdigest()}]}))
    v, inf = D.leer(tmp_path)
    assert [x.dia for x in v] == ["2025-01-01", "2025-01-02"] and inf["duracion_irregular"] == ["2025-01-02"]
    with pytest.raises(ValueError, match="período reservado"):
        D.descargar_1d(tmp_path, "BTCUSDT", hasta="2026-07")
