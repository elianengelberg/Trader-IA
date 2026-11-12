"""Pruebas del orquestador v2 frente al v1 congelado. SOLO datos sintéticos: ningún precio real.

Cada prueba de regresión corre contra las dos implementaciones:
  - v1 (`ejecutar_E3R.py`, 3b64a04d…): marcada xfail(strict=True). DEBE fallar; si pasara, la suite falla.
  - v2 (`ejecutar_E3_v2.py`): debe pasar.
Una guarda autouse hace fallar cualquier prueba que intente abrir una serie real de E3.
Uso: python -B -m pytest -p no:cacheprovider pruebas/test_orquestador_v2.py
"""
import datetime as dt
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

sys.dont_write_bytecode = True
AQUI = Path(__file__).resolve().parent
ORQ_V2 = AQUI.parent / "ejecutar_E3_v2.py"
REP = AQUI.parent.parent
E3R = REP.parent / "experimentos" / "E3R_desbloqueo_2026-10-26"
E3_REAL = REP.parent / "experimentos" / "E3_seleccion_posicion_2026-10-19" / "ejecucion_E3"
SERIES_REALES = str(E3_REAL / "resultados" / "calidad" / "series")
MODULOS = ("universo.py", "motor.py", "inferencia.py", "pruebas_motor.py", "conciliacion.py")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


V1 = cargar("orq_v1", E3R / "ejecutar_E3R.py")
V2 = cargar("orq_v2", ORQ_V2)
assert sha(E3R / "ejecutar_E3R.py") == "3b64a04dcb6b39d20cb218ff5f5ef0bd03c1dd45cd75e475b0640fb1ecfd8dce"
IMPLS = [pytest.param(V1, id="v1", marks=pytest.mark.xfail(strict=True, reason="defecto del v1 que corrige el v2")),
         pytest.param(V2, id="v2")]


class LecturaDePrecios(Exception):
    """Centinela: el orquestador intentó abrir una serie de precios."""


@pytest.fixture(autouse=True)
def sin_series_reales(monkeypatch):
    original = np.load

    def guarda(f, *a, **k):
        if SERIES_REALES in str(f):
            raise AssertionError(f"una prueba intentó leer una serie real: {f}")
        return original(f, *a, **k)
    monkeypatch.setattr(np, "load", guarda)


@pytest.fixture(scope="module")
def e3_falso(tmp_path_factory):
    """Copia de los módulos congelados (hash verificado) en un árbol temporal; el árbol congelado no se toca."""
    d = tmp_path_factory.mktemp("e3") / "ejecucion_E3"
    (d / "codigo").mkdir(parents=True)
    for m in MODULOS:
        shutil.copyfile(E3_REAL / "codigo" / m, d / "codigo" / m)
    assert all(sha(d / "codigo" / m) == sha(E3_REAL / "codigo" / m) for m in MODULOS)
    return d


@pytest.fixture(scope="module")
def mods(e3_falso):
    return V2.importar_congelados(e3_falso)


# ===================================================================== C2 · R4 contra el EW bruto (N14)

class Corte(Exception):
    pass


@pytest.mark.parametrize("impl", IMPLS)
def test_r4_mide_el_aporte_contra_el_ew_bruto(impl, mods, monkeypatch):
    universo, motor, inferencia = mods
    import pruebas_motor
    P = pruebas_motor.panel_sintetico(20261026, momentum=0.02)
    F = pruebas_motor.formaciones()
    visto = {}

    def espia(P_, sim, formaciones, sim_ew):
        visto["r_ew"] = np.asarray(sim_ew["r"])
        raise Corte
    monkeypatch.setattr(impl, "contribuciones", espia)
    with pytest.raises(Corte):
        impl.ejecutar(P, F, universo, motor, inferencia, replicas_R5=1, diag_B=19)
    bruto = motor.simular(P, F, motor.Config(objetivo="ew", mult_costo=0.0), {})
    neto = motor.simular(P, F, motor.Config(objetivo="ew"), {})
    assert not np.allclose(bruto["r"], neto["r"]), "precondición: con costos, el EW neto difiere del bruto"
    np.testing.assert_allclose(visto["r_ew"], bruto["r"], rtol=0, atol=1e-15)


def test_contribuciones_aritmetica_y_bordes(mods):
    """Control (igual en v1 y v2): Σ w·(r_c − r_EW), con P_val si falta la apertura de t+7 y sin aporte si falta p0."""
    universo, _, _ = mods
    D = 30
    O = np.full((3, D), np.nan)
    C = np.full((3, D), np.nan)
    act = np.zeros((3, D), dtype=bool)
    for s, p in enumerate((100.0, 50.0, 10.0)):
        O[s, :], C[s, :], act[s, :] = p, p, True
    O[0, 8], C[0, 8] = 110.0, 110.0           # moneda 0: +10 % de apertura a apertura
    act[1, 8], O[1, 8], C[1, 8] = False, np.nan, np.nan
    C[1, 7] = 55.0                             # moneda 1: sin apertura en t+7 → P_val(t+6) = cierre del día 7
    act[2, :2], O[2, :2], C[2, :2] = False, np.nan, np.nan   # moneda 2: sin p0 en t = 1 ni P_val previo
    P = universo.Panel(["AUSDT", "BUSDT", "CUSDT"], O, C, np.ones((3, D)), act)
    sim = {"pesos": [(1, {0: 0.5, 1: 0.3, 2: 0.2})]}
    ew = {"r": np.array([0.02])}
    for impl in (V1, V2):
        a = impl.contribuciones(P, sim, [1, 8], ew)
        assert set(a) == {0, 1}
        assert a[0] == pytest.approx(0.5 * (0.10 - 0.02))
        assert a[1] == pytest.approx(0.3 * (55 / 50 - 1 - 0.02))


def test_r4_neto_o_bruto_puede_cambiar_la_moneda_excluida(mods):
    """Materialidad del defecto: A se tiene 50 semanas con +0,1 pp sobre EW; B, 2 semanas con +3 pp. Contra el EW bruto
    (N14) el mayor aporte es B; contra el EW neto (0,3 pp menos por semana, como hacía el v1) pasa a ser A."""
    universo, _, _ = mods
    K, g, costo = 50, 0.01, 0.003
    t = [1 + 7 * k for k in range(K + 1)]
    D = t[-1] + 8
    pa, pb = [100.0], [100.0]
    for k in range(K):
        pa.append(pa[-1] * (1 + g + 0.001))
        pb.append(pb[-1] * (1 + g + (0.03 if k < 2 else 0.0)))
    O = np.empty((2, D))
    for k in range(K + 1):
        fin = t[k + 1] if k < K else D
        O[0, t[k]:fin], O[1, t[k]:fin] = pa[k], pb[k]
    O[:, :1] = O[:, 1:2]
    P = universo.Panel(["AAAUSDT", "BBBUSDT"], O, O.copy(), np.ones((2, D)), np.ones((2, D), dtype=bool))
    sim = {"pesos": [(t[k], {0: 0.5, 1: 0.5} if k < 2 else {0: 0.5}) for k in range(K)]}
    bruto, neto = {"r": np.full(K, g)}, {"r": np.full(K, g - costo)}
    a_b, a_n = V2.contribuciones(P, sim, t, bruto), V2.contribuciones(P, sim, t, neto)
    assert max(a_b, key=a_b.get) == 1 and max(a_n, key=a_n.get) == 0


# ===================================================================== C3 · verificación de insumos antes de leer precios

FRASE_V1 = V1.FRASE


def npz(ruta, simbolo, D=40, precio=1.0):
    np.savez(ruta, simbolo=np.array(simbolo), O=np.full(D, precio), C=np.full(D, precio), QV=np.full(D, 1e6),
             estado=np.ones(D, dtype=np.int8), NT=np.ones(D))


@pytest.fixture
def caso_real(tmp_path, e3_falso):
    """Árbol E3 falso con 3 series sintéticas, listas y estructural; manifiesto y autorizaciones válidos para v1 y v2."""
    e3 = tmp_path / "ejecucion_E3"
    shutil.copytree(e3_falso / "codigo", e3 / "codigo")
    ser = e3 / "resultados" / "calidad" / "series"
    ser.mkdir(parents=True)
    for s in ("AAAUSDT", "BBBUSDT", "CCCUSDT"):
        npz(ser / f"{s}.npz", s)
    est = e3 / "resultados" / "estructural"
    est.mkdir(parents=True)
    (est / "estructural.json").write_text(json.dumps({"cortes_con_reanudacion": {"lista_saltos": []}, "semanas": []}))
    (est / "listas_fijas_por_lunes.json").write_text("[]")
    rep = tmp_path / "reparacion"
    (rep / "renombres").mkdir(parents=True)
    (rep / "renombres" / "mapeos_adenda1.json").write_text(json.dumps({"mapeos": []}))
    orq = rep / "orquestador_v2"
    orq.mkdir()
    ventana = tmp_path / "ventana_A.json"
    ventana.write_text(json.dumps({"veredicto": "VALIDO", "inicio_H": "2023-05-15", "adenda": "ADENDA_R"}))
    entradas = [{"nombre": "series", "base": "E3", "ruta": "resultados/calidad/series", "tipo": "conjunto"},
                {"nombre": "estructural", "base": "E3", "ruta": "resultados/estructural/estructural.json", "tipo": "archivo"},
                {"nombre": "listas", "base": "E3", "ruta": "resultados/estructural/listas_fijas_por_lunes.json", "tipo": "archivo"},
                {"nombre": "mapeos", "base": "reparacion", "ruta": "renombres/mapeos_adenda1.json", "tipo": "archivo"},
                {"nombre": "ventana", "base": "ventana", "ruta": None, "tipo": "archivo"},
                *({"nombre": m, "base": "E3", "ruta": f"codigo/{m}", "tipo": "archivo"} for m in MODULOS)]
    for x in entradas:
        p = ventana if x["base"] == "ventana" else (e3 if x["base"] == "E3" else rep) / x["ruta"]
        x["sha256"] = V2.hash_conjunto(p) if x["tipo"] == "conjunto" else sha(p)
    manif = orq / "ENTRADAS_CONGELADAS.json"
    manif.write_text(json.dumps({"inicio_H_esperado": "2023-05-15", "mapeos": "renombres/mapeos_adenda1.json", "entradas": entradas}))
    aut2 = tmp_path / "autorizacion_v2.txt"
    aut2.write_text(f"{V2.FRASE}\n{sha(ORQ_V2)}\n{sha(manif)}\n")
    aut1 = tmp_path / "autorizacion_v1.txt"
    aut1.write_text("\n".join([FRASE_V1, sha(E3R / "ejecutar_E3R.py"), sha(ventana),
                               sha(E3R / "ADENDA_R_auditoria_de_supervivencia_interna.md"),
                               sha(E3R / "ADENDA_R2_cortes_con_salto_de_precio.md")]))
    return {"e3": e3, "ventana": ventana, "manif": manif, "aut1": aut1, "aut2": aut2, "orq": orq, "salida": tmp_path / "salida"}


def correr(impl, c, monkeypatch, aut=None):
    """Corre el modo real con un centinela en np.load: devuelve si se intentó leer un precio."""
    leido = {"n": 0}

    def centinela(*a, **k):
        leido["n"] += 1
        raise LecturaDePrecios
    monkeypatch.setattr(impl.np, "load", centinela)
    if impl is V2:
        monkeypatch.setattr(V2, "AQUI", c["orq"])
        args = (c["e3"], c["ventana"], aut or c["aut2"], c["salida"], c["manif"])
    else:
        args = (c["e3"], c["ventana"], aut or c["aut1"], c["salida"])
    try:
        impl.modo_real(*args)
    except LecturaDePrecios:
        return "leyo_precios"
    except SystemExit as x:
        return f"detenido: {x}"
    return "termino"


@pytest.mark.parametrize("impl", IMPLS)
def test_serie_alterada_se_rechaza_sin_leer_precios(impl, caso_real, monkeypatch):
    p = caso_real["e3"] / "resultados" / "calidad" / "series" / "BBBUSDT.npz"
    b = bytearray(p.read_bytes())
    b[-1] ^= 0x01
    p.write_bytes(bytes(b))
    r = correr(impl, caso_real, monkeypatch)
    assert r.startswith("detenido") and "no coinciden" in r, r
    assert not caso_real["salida"].exists()


def test_v2_entradas_correctas_pasan_la_guarda(caso_real, monkeypatch):
    """Sin falsos rechazos: con los insumos congelados, el v2 registra la ejecución y recién después lee precios."""
    r = correr(V2, caso_real, monkeypatch)
    assert r == "leyo_precios", r
    reg = json.loads((caso_real["salida"] / "REGISTRO_EJECUCION.json").read_text())
    assert reg["entradas"]["inicio_H_esperado"] == "2023-05-15"


@pytest.mark.parametrize("alteracion", ["estructural", "listas", "serie_faltante", "serie_extra", "mapeos", "ventana", "motor"])
def test_v2_cualquier_insumo_alterado_detiene_antes_de_leer(alteracion, caso_real, monkeypatch):
    c = caso_real
    if alteracion == "estructural":
        p = c["e3"] / "resultados/estructural/estructural.json"
        p.write_text(p.read_text() + " ")
    elif alteracion == "listas":
        (c["e3"] / "resultados/estructural/listas_fijas_por_lunes.json").write_text("[ ]")
    elif alteracion == "serie_faltante":
        (c["e3"] / "resultados/calidad/series/CCCUSDT.npz").unlink()
    elif alteracion == "serie_extra":
        npz(c["e3"] / "resultados/calidad/series/DDDUSDT.npz", "DDDUSDT")
    elif alteracion == "mapeos":
        (c["orq"].parent / "renombres/mapeos_adenda1.json").write_text(json.dumps({"mapeos": [{"regla": 1}]}))
    elif alteracion == "ventana":
        c["ventana"].write_text(json.dumps({"veredicto": "VALIDO", "inicio_H": "2021-02-22"}))
    elif alteracion == "motor":
        p = c["e3"] / "codigo/motor.py"
        p.write_text(p.read_text() + "\n# alterado\n")
    r = correr(V2, c, monkeypatch)
    assert r.startswith("detenido") and "no coinciden" in r, r
    assert not c["salida"].exists()


@pytest.mark.parametrize("falta", ["frase", "hash_orquestador", "hash_manifiesto", "frase_v1"])
def test_v2_autorizacion_incompleta_no_lee_precios(falta, caso_real, monkeypatch):
    c = caso_real
    lineas = {"frase": V2.FRASE, "hash_orquestador": sha(ORQ_V2), "hash_manifiesto": sha(c["manif"])}
    if falta == "frase_v1":
        lineas["frase"] = FRASE_V1
    else:
        lineas.pop(falta)
    aut = c["salida"].parent / "aut_incompleta.txt"
    aut.write_text("\n".join(lineas.values()))
    r = correr(V2, c, monkeypatch, aut=aut)
    assert r.startswith("detenido") and "autorización" in r, r
    assert not c["salida"].exists()


def test_v2_salida_existente_no_se_reescribe(caso_real, monkeypatch):
    caso_real["salida"].mkdir()
    r = correr(V2, caso_real, monkeypatch)
    assert r.startswith("detenido") and "ya existe" in r


# ===================================================================== C5 · INVÁLIDO como resultado explícito

@pytest.mark.parametrize("impl", IMPLS)
def test_ventana_invalida_deja_resultado_explicito(impl, caso_real, monkeypatch):
    c = caso_real
    c["ventana"].write_text(json.dumps({"veredicto": "INVALIDO", "inicio_H": None, "adenda": "ADENDA_R"}))
    m = json.loads(c["manif"].read_text())
    for x in m["entradas"]:
        if x["base"] == "ventana":
            x["sha256"] = sha(c["ventana"])
    c["manif"].write_text(json.dumps(m))
    c["aut2"].write_text(f"{V2.FRASE}\n{sha(ORQ_V2)}\n{sha(c['manif'])}\n")
    c["aut1"].write_text(c["aut1"].read_text().replace(c["aut1"].read_text().splitlines()[2], sha(c["ventana"])))
    r = correr(impl, c, monkeypatch)
    assert r.startswith("detenido") and "INVALIDO" in r, r
    res = json.loads((c["salida"] / "RESULTADO_E3.json").read_text())
    assert res["veredicto"] == "INVALIDO" and res["H1"] is None and res["H2"] is None


# ===================================================================== C4 · mapeos de la Adenda 1 en el panel (sin R2)

INICIO = dt.date(2017, 7, 1)
D = 220


def dia(i):
    return (INICIO + dt.timedelta(days=int(i))).isoformat()


def arrays(series):
    """series: {símbolo: (precios por día o NaN)} → syms, O, C, QV, act."""
    syms = list(series)
    C = np.array([series[s] for s in syms], dtype=float)
    act = np.isfinite(C)
    return syms, C.copy(), C.copy(), np.where(act, 1e6, np.nan), act


def serie(ini, fin, p0, paso=1.001):
    x = np.full(D, np.nan)
    x[ini:fin] = p0 * paso ** np.arange(fin - ini)
    return x


def panel_con(impl, universo, series, mapeos):
    """v2: aplica los mapeos. v1: aplica R2 a los cortes con salto ≥ ×10 (lo único que hace) y no conoce los mapeos."""
    syms, O, C, QV, act = arrays(series)
    if impl is V2:
        syms, O, C, QV, act, _ = V2.aplicar_mapeos(syms, O, C, QV, act, mapeos, universo.INICIO)
        return universo.Panel(syms, O, C, QV, act)
    saltos = []
    for s in syms:
        a = np.flatnonzero(act[syms.index(s)])
        for k in range(1, a.size):
            if a[k] - a[k - 1] > 1:
                i = syms.index(s)
                ratio = C[i, a[k]] / C[i, a[k - 1]]
                saltos.append({"simbolo": s, "ultimo_activo": dia(a[k - 1]), "reanuda": dia(a[k]), "ratio_precio": ratio})
    return V1.particionar(syms, O, C, QV, act, saltos, universo)[0]


@pytest.mark.parametrize("impl", IMPLS)
def test_regla2_redenominacion_conserva_edad_y_continuidad(impl, mods):
    """QUICK-like: 1 viejo = 1.000 nuevos; corte del día 100 al 104. La serie sigue continua y la edad no se reinicia."""
    universo = mods[0]
    x = serie(0, 100, 50.0)
    x[104:] = serie(104, D, x[99] * 1.001 ** 5 / 1000)[104:]
    P = panel_con(impl, universo, {"QQQUSDT": x}, [{"regla": 2, "viejo_usdt": "QQQUSDT", "nuevo_usdt": "QQQUSDT", "r": 1000, "E": dia(100)}])
    assert P.sym == ["QQQUSDT"]
    s = 0
    assert P.ep_ini[s, 150] == 0, "el listado vigente empieza en el día 0: la edad se hereda"
    assert abs(np.log(P.C[s, 104] / P.C[s, 99])) < 0.01, "sin salto ficticio a través del corte"
    assert P.pval(s, 102) == pytest.approx(x[99] / 1000)


@pytest.mark.parametrize("impl", IMPLS)
def test_regla1_renombre_hereda_edad_y_fila(impl, mods):
    """MC→BEAMX-like: 1 viejo = 100 nuevos. Y continúa a X en la misma fila (hereda edad y posiciones)."""
    universo = mods[0]
    xs = serie(0, 100, 20.0)
    ys = serie(105, D, xs[99] * 1.001 ** 6 / 100)
    P = panel_con(impl, universo, {"MMMUSDT": xs, "NNNUSDT": ys, "ZZZUSDT": serie(0, D, 1.0)},
                  [{"regla": 1, "viejo_usdt": "MMMUSDT", "nuevo_usdt": "NNNUSDT", "r": 100, "E": dia(100)}])
    assert "MMMUSDT" not in P.sym and P.sym.count("NNNUSDT") == 1
    s = P.sym.index("NNNUSDT")
    assert P.ep_ini[s, 150] == 0
    assert abs(np.log(P.C[s, 105] / P.C[s, 99])) < 0.01
    assert P.act[s, :100].all() and P.act[s, 105:].all()


@pytest.mark.parametrize("impl", IMPLS)
def test_corte_sin_anuncio_sigue_la_regla_3(impl, mods):
    """BNX-like: corte de 6 días con salto ×0,01 y SIN mapeo. Regla 3: mismo listado, sin partir la serie ni inventar r."""
    universo = mods[0]
    x = serie(0, 100, 5.0)
    x[106:] = serie(106, D, x[99] / 100)[106:]
    P = panel_con(impl, universo, {"BBXUSDT": x}, [])
    assert P.sym == ["BBXUSDT"], "no se crea ningún símbolo nuevo"
    assert P.ep_ini[0, 150] == 0
    np.testing.assert_array_equal(P.C[0][np.isfinite(x)], x[np.isfinite(x)])


def test_v2_cadena_redenominacion_y_renombre(mods):
    """COCOS-like: regla 2 (1.000 viejos = 1 nuevo) y después regla 1 hacia otro símbolo (1:1), en la misma fila."""
    universo = mods[0]
    a = serie(0, 60, 0.001)
    a[64:150] = serie(64, 150, a[59] * 1000 * 1.001 ** 5)[64:150]
    b = serie(155, D, a[149] * 1.001 ** 6)
    P = panel_con(V2, universo, {"COCUSDT": a, "CMBUSDT": b},
                  [{"regla": 2, "viejo_usdt": "COCUSDT", "nuevo_usdt": "COCUSDT", "r": 0.001, "E": dia(60)},
                   {"regla": 1, "viejo_usdt": "COCUSDT", "nuevo_usdt": "CMBUSDT", "r": 1, "E": dia(152)}])
    assert P.sym == ["CMBUSDT"]
    c = P.C[0]
    assert abs(np.log(c[64] / c[59])) < 0.01 and abs(np.log(c[155] / c[149])) < 0.01
    assert P.ep_ini[0, 200] == 0


@pytest.mark.parametrize("caso", ["viejo_ausente", "nuevo_activo_antes", "viejo_activo_despues", "regla2_sin_corte", "regla2_sin_reapertura"])
def test_v2_mapeos_imposibles_abortan(caso, mods):
    """No se une nada a ciegas: cada inconsistencia entre el mapeo y la actividad detiene la construcción del panel."""
    universo = mods[0]
    xs, ys = serie(0, 100, 20.0), serie(105, D, 0.2)
    m = {"regla": 1, "viejo_usdt": "MMMUSDT", "nuevo_usdt": "NNNUSDT", "r": 100, "E": dia(100)}
    series = {"MMMUSDT": xs, "NNNUSDT": ys}
    if caso == "viejo_ausente":
        m["viejo_usdt"] = "OTROUSDT"
    elif caso == "nuevo_activo_antes":
        series["NNNUSDT"] = serie(90, D, 0.2)
    elif caso == "viejo_activo_despues":
        series["MMMUSDT"] = serie(0, 120, 20.0)
    elif caso == "regla2_sin_corte":
        series = {"QQQUSDT": serie(0, D, 1.0)}
        m = {"regla": 2, "viejo_usdt": "QQQUSDT", "nuevo_usdt": "QQQUSDT", "r": 1000, "E": dia(100)}
    elif caso == "regla2_sin_reapertura":
        series = {"QQQUSDT": serie(0, 100, 1.0)}
        m = {"regla": 2, "viejo_usdt": "QQQUSDT", "nuevo_usdt": "QQQUSDT", "r": 1000, "E": dia(100)}
    with pytest.raises(SystemExit):
        panel_con(V2, universo, series, [m])


def test_tabla_de_mapeos_congelada_solo_con_anuncio():
    """La tabla real de mapeos (sin precios): reglas válidas y ningún cambio de símbolo sin anuncio archivado."""
    t = json.loads((REP / "renombres" / "mapeos_adenda1.json").read_text())["mapeos"]
    assert len(t) == 22
    for m in t:
        assert m["regla"] in (1, 2) and float(m["r"]) > 0 and m["viejo_usdt"].endswith("USDT") and m["nuevo_usdt"].endswith("USDT")
        assert (m["regla"] == 2) == (m["viejo_usdt"] == m["nuevo_usdt"])
        assert m["cita"] and m["fuente"]
    sin_anuncio = {"TOMOUSDT", "GALUSDT", "RNDRUSDT", "KLAYUSDT", "DARUSDT", "FTMUSDT", "EOSUSDT", "MKRUSDT", "FXSUSDT", "OMUSDT",
                   "BNXUSDT", "LUNAUSDT", "VIDTUSDT", "AGIXUSDT", "OCEANUSDT"}
    assert not sin_anuncio & {m["viejo_usdt"] for m in t}
    en_A = {(m["viejo_usdt"], m["nuevo_usdt"]) for m in t if m["E"] >= "2023-05-15"}
    assert en_A == {("COCOSUSDT", "COMBOUSDT"), ("QUICKUSDT", "QUICKUSDT"), ("MCUSDT", "BEAMXUSDT"), ("TVKUSDT", "VANRYUSDT"),
                    ("PLAUSDT", "PDAUSDT"), ("STRAXUSDT", "STRAXUSDT"), ("MATICUSDT", "POLUSDT")}
