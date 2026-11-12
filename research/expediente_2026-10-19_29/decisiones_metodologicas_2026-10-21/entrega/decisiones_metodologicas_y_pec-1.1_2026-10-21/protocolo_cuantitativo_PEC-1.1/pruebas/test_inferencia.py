"""Prueba primaria del MEC §4: valores a mano, dualidad p ↔ IC, determinismo, regla de respaldo y contraste diferencial
con la implementación independiente de E3 (`7b280386…`), ejecutada con numpy en un subproceso."""
import hashlib
import json
import math
import os
import random
import shutil
import subprocess
from pathlib import Path

import pytest
from pec import inferencia as I

AQUI = Path(__file__).resolve().parent
E3 = AQUI / "referencia_E3" / "inferencia_E3.py"
SHA_E3 = "7b28038621c1d366655d726bb885ca0105f1a25cfcdb9615e86a7fe39e85f3e1"


def serie(n: int, media: float, semilla: int, sd: float = 0.01) -> list[float]:
    rng = random.Random(semilla)
    return [rng.gauss(media, sd) for _ in range(n)]


def test_medias_de_bloque_y_estadistico_a_mano():
    # x = 1, 2, 3, 4 con ℓ = 2: bloques circulares 1,5 2,5 3,5 2,5; x̄ = 2,5; σ̂²_C = (2/4)·(1 + 0 + 1 + 0) = 1; T = 5
    assert I.medias_bloques_circulares([1, 2, 3, 4], 2) == [1.5, 2.5, 3.5, 2.5]
    r = I.bootstrap_t([1, 2, 3, 4], ell=2, b=1, inicios=[[0, 2]])
    assert r["sigma_C"] == pytest.approx(1.0) and r["T"] == pytest.approx(5.0) and r["k"] == 2
    # réplica: bloques centrados −1 y +1 → ē* = 0, σ̂*² = 2/(2−1)·2 = 4, T* = 0 → p = (1 + 0)/(1 + 1) = 0,5
    assert r["p_unilateral"] == pytest.approx(0.5)


def test_estadisticos_de_orden_exactos():
    """Regresión: en coma flotante (1 − 0,90)/2·1000 = 49,99… y el suelo daba el orden 49 en vez del 50 (hallado por
    el contraste diferencial con E3 durante la construcción). Con Fraction el orden es exacto."""
    from fractions import Fraction
    assert math.floor((1 - 0.90) / 2 * 1000) == 49  # el defecto de la aritmética flotante, documentado
    assert I._orden((1 - Fraction(90, 100)) / 2, 999, False) == 50
    assert I._orden(1 - (1 - Fraction(90, 100)) / 2, 999, True) == 950
    assert I._orden((1 - Fraction(95, 100)) / 2, 9999, False) == 250
    assert I._orden(1 - (1 - Fraction(95, 100)) / 2, 9999, True) == 9750


def test_dualidad_p_e_intervalo():
    """Con B = 999, p ≤ 0,025 ⇔ extremo inferior del IC95 > 0 y p ≤ 0,05 ⇔ extremo inferior del IC90 > 0 (exacto)."""
    casos = 0
    for i in range(40):
        r = I.bootstrap_t(serie(300, 0.0008 * (i % 5), 100 + i), ell=20, b=999, semilla=i)
        assert (r["p_unilateral"] <= 0.025) == (r["ic95"][0] > 0), r
        assert (r["p_unilateral"] <= 0.05) == (r["ic90"][0] > 0), r
        casos += r["p_unilateral"] <= 0.025
    assert 0 < casos < 40  # se ejercitaron las dos ramas


def test_determinismo_y_sensibilidad_a_la_semilla():
    x = serie(400, 0.0005, 3)
    a, b = I.bootstrap_t(x, b=999, semilla=11), I.bootstrap_t(x, b=999, semilla=11)
    assert a == b
    otra = I.bootstrap_t(x, b=999, semilla=12)
    assert otra["T"] == a["T"] and otra["sigma_C"] == a["sigma_C"]  # T no depende del remuestreo
    assert otra["ic95"] != a["ic95"]  # los cuantiles de T* sí dependen de la semilla


def test_deriva_fuerte_rechaza_y_negativa_no():
    assert I.bootstrap_t(serie(500, 0.004, 5), b=999)["p_unilateral"] < 0.01
    assert I.bootstrap_t(serie(500, -0.002, 6), b=999)["p_unilateral"] > 0.5


def test_degenerada_y_errores_de_uso():
    with pytest.raises(I.ErrorSerieDegenerada):
        I.bootstrap_t([0.0] * 100, b=99)
    with pytest.raises(ValueError):
        I.bootstrap_t([0.1] * 30, ell=20, b=99)  # n < 2ℓ
    with pytest.raises(ValueError):
        I.bootstrap_t(serie(100, 0, 1), ell=20, b=2, inicios=[[0, 1]])  # forma incorrecta


def test_newey_west_a_mano():
    x = [1.0, -1.0, 2.0, 0.0]  # x̄ = 0,5; d = 0,5 −1,5 1,5 −0,5
    d = [0.5, -1.5, 1.5, -0.5]
    g0 = sum(v * v for v in d) / 4
    g1 = (d[1] * d[0] + d[2] * d[1] + d[3] * d[2]) / 4
    lrv = g0 + 2 * 0.5 * g1
    r = I.newey_west(x, retardos=1)
    assert r["ee"] == pytest.approx(math.sqrt(lrv / 4)) and r["z"] == pytest.approx(0.5 / math.sqrt(lrv / 4))


def test_regla_de_respaldo_es_el_maximo_y_la_envolvente():
    r = I.respaldo(serie(600, 0.0006, 9), b=499)
    comp = r["componentes"].values()
    assert r["p_unilateral"] == max(c["p_unilateral"] for c in comp)
    for c in comp:
        assert r["ic90"][0] <= c["ic90"][0] and r["ic90"][1] >= c["ic90"][1]


@pytest.mark.skipif(not (shutil.which("python3") and E3.is_file()), reason="sin python3 o sin la referencia de E3")
def test_diferencial_contra_la_implementacion_de_E3():
    """Mismas series y MISMOS inicios de bloque: T, σ̂_C, p e intervalos deben coincidir con la implementación de E3.
    Las dos vienen del mismo autor: es un contraste de implementación, no una revisión independiente."""
    assert hashlib.sha256(E3.read_bytes()).hexdigest() == SHA_E3
    py = os.environ.get("PEC_PY_NUMPY", "/usr/bin/python3")
    if subprocess.run([py, "-I", "-B", "-c", "import numpy"], capture_output=True).returncode != 0:
        pytest.skip("el intérprete externo no tiene numpy")
    casos = []
    for i, (n, ell, media) in enumerate([(120, 13, 0.0), (300, 20, 0.0007), (257, 20, -0.0003), (401, 40, 0.001),
                                        (90, 7, 0.002)]):
        x = serie(n, media, 500 + i)
        k = -(-n // ell)
        rng = random.Random(900 + i)
        b = 999
        inicios = [[rng.randrange(n) for _ in range(k)] for _ in range(b)]
        casos.append({"x": x, "ell": ell, "B": b, "inicios": inicios})
    programa = (
        "import json, sys, importlib.util\nimport numpy as np\n"
        "spec = importlib.util.spec_from_file_location('e3', sys.argv[1]); e3 = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(e3)\n"
        "class R:\n    def __init__(s, m): s.m = np.array(m)\n    def integers(s, lo, hi, size): return s.m\n"
        "out = []\nfor c in json.load(sys.stdin):\n"
        "    r = e3.bootstrap_t(np.array(c['x']), ell=c['ell'], B=c['B'], rng=R(c['inicios']))\n"
        "    out.append({k: (list(map(float, r[k])) if isinstance(r[k], tuple) else float(r[k])) "
        "for k in ('T', 'sigma_C', 'p_unilateral', 'ic90', 'ic95', 'media')})\n"
        "print(json.dumps(out))\n")
    s = subprocess.run([py, "-I", "-B", "-c", programa, str(E3)], input=json.dumps(casos), capture_output=True, text=True,
                       check=True)
    ref = json.loads(s.stdout)
    for c, e in zip(casos, ref, strict=True):
        m = I.bootstrap_t(c["x"], ell=c["ell"], b=c["B"], inicios=c["inicios"])
        for clave in ("T", "sigma_C", "p_unilateral", "media"):
            assert m[clave] == pytest.approx(e[clave], rel=1e-10, abs=1e-12), clave
        for clave in ("ic90", "ic95"):
            assert list(m[clave]) == pytest.approx(e[clave], rel=1e-10, abs=1e-12), clave
