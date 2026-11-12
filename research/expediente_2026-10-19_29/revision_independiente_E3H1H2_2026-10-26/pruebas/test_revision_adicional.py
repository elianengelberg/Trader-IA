"""Pruebas adversariales adicionales de la revisión independiente. SOLO datos sintéticos.

- Se ejecutan contra una COPIA del v2 (bytes idénticos, verificado) y, cuando corresponde, contra el v1 congelado (solo importado).
- Ninguna prueba escribe la frase real de autorización ni un hash real en un archivo de autorización: `FRASE` se reemplaza
  por una frase de prueba y `sha` por sha256(b"PRUEBA|" + bytes), que no contiene ni coincide con ningún hash real, de modo
  que ningún archivo producido aquí sirve (ni siquiera en parte) para habilitar una ejecución real.
- Las marcadas `xfail(strict=True)` DOCUMENTAN un defecto o una brecha del v2: deben fallar mientras exista; si pasaran,
  la suite falla (y habría que actualizar la revisión).
Uso: python -B -m pytest -p no:cacheprovider --basetemp <dir_temporal> test_revision_adicional.py
"""
import datetime as dt
import hashlib
import importlib.util
import json
import shutil
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

sys.dont_write_bytecode = True
warnings.filterwarnings("ignore", category=RuntimeWarning)
S = Path(__file__).resolve().parents[2]
COPIA = S / "revision_independiente_E3H1H2_2026-10-26" / "copia_aislada"
V2_RUTA = COPIA / "reparacion_E3H1H2_2026-10-26" / "orquestador_v2" / "ejecutar_E3_v2.py"
V1_RUTA = S / "experimentos" / "E3R_desbloqueo_2026-10-26" / "ejecutar_E3R.py"
SERIES_REALES = str(S / "experimentos" / "E3_seleccion_posicion_2026-10-19" / "ejecucion_E3" / "resultados" / "calidad" / "series")
FRASE_PRUEBA = "FRASE DE PRUEBA SIN VALOR PARA NINGUNA EJECUCION"


def sha_real(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def sha_prueba(p):
    """Hash «con sal» de prueba: distinto de cualquier sha256 real y sin contenerlo."""
    return hashlib.sha256(b"PRUEBA|" + Path(p).read_bytes()).hexdigest()


assert sha_real(V2_RUTA) == "01fc934459b791fd5fbd451aa1c6931fc9e6764b9361e5caea46314cc5ee6f68", "la copia del v2 no es la revisada"
assert sha_real(V1_RUTA) == "3b64a04dcb6b39d20cb218ff5f5ef0bd03c1dd45cd75e475b0640fb1ecfd8dce"


def cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


V1, V2 = cargar("rv_v1", V1_RUTA), cargar("rv_v2", V2_RUTA)
DEFECTO = pytest.mark.xfail(strict=True, reason="defecto o brecha del v2 documentado en la revisión")


@pytest.fixture(autouse=True)
def sin_series_reales(monkeypatch):
    original = np.load

    def guarda(f, *a, **k):
        if SERIES_REALES in str(f):
            raise AssertionError(f"lectura de una serie real: {f}")
        return original(f, *a, **k)
    monkeypatch.setattr(np, "load", guarda)


@pytest.fixture(scope="module")
def mods():
    return V2.importar_congelados(COPIA / "e3copia")


# ---------------------------------------------------------------- utilidades del modo real sintético

D_TOTAL = (dt.date(2026, 5, 31) - dt.date(2017, 7, 1)).days + 1


def npz(ruta, simbolo, precio=1.0, D=D_TOTAL):
    np.savez(ruta, simbolo=np.array(simbolo), O=np.full(D, precio), C=np.full(D, precio), QV=np.full(D, 5e6),
             estado=np.ones(D, dtype=np.int8), NT=np.ones(D))


@pytest.fixture
def caso(tmp_path, monkeypatch):
    """Árbol E3 sintético + manifiesto y autorización de PRUEBA (frase y hashes sin valor real)."""
    pref = sha_prueba
    cod = COPIA / "e3copia" / "codigo"
    assert all(sha_real(cod / k) == v for k, v in V2.CONGELADOS.items())
    monkeypatch.setattr(V2, "sha", pref)
    monkeypatch.setattr(V2, "FRASE", FRASE_PRUEBA)
    monkeypatch.setattr(V2, "CONGELADOS", {k: pref(cod / k) for k in V2.CONGELADOS})
    e3 = tmp_path / "ejecucion_E3"
    shutil.copytree(COPIA / "e3copia" / "codigo", e3 / "codigo")
    ser = e3 / "resultados/calidad/series"
    ser.mkdir(parents=True)
    for s in ("AAAUSDT", "BBBUSDT", "CCCUSDT"):
        npz(ser / f"{s}.npz", s)
    rep = tmp_path / "rep"
    (rep / "renombres").mkdir(parents=True)
    (rep / "renombres/mapeos_adenda1.json").write_text(json.dumps({"mapeos": []}))
    orq = rep / "orq"
    orq.mkdir()
    monkeypatch.setattr(V2, "AQUI", orq)
    ventana = tmp_path / "ventana.json"
    ventana.write_text(json.dumps({"veredicto": "VALIDO", "inicio_H": "2023-05-15"}))

    def manifiesto(inicio="2023-05-15", mapeos="renombres/mapeos_adenda1.json", entradas=None):
        ent = entradas if entradas is not None else [
            {"nombre": "series", "base": "E3", "ruta": "resultados/calidad/series", "tipo": "conjunto"},
            {"nombre": "mapeos", "base": "reparacion", "ruta": "renombres/mapeos_adenda1.json", "tipo": "archivo"},
            {"nombre": "ventana", "base": "ventana", "ruta": None, "tipo": "archivo"}]
        for x in ent:
            p = ventana if x["base"] == "ventana" else (e3 if x["base"] == "E3" else rep) / x["ruta"]
            x["sha256"] = V2.hash_conjunto(p) if x["tipo"] == "conjunto" else pref(p)
        m = orq / "ENTRADAS_CONGELADAS.json"
        m.write_text(json.dumps({"inicio_H_esperado": inicio, "mapeos": mapeos, "entradas": ent}))
        aut = tmp_path / "autorizacion_de_prueba.txt"
        aut.write_text(f"{FRASE_PRUEBA}\n{pref(V2_RUTA)}\n{pref(m)}\n")
        return m, aut
    return {"e3": e3, "rep": rep, "orq": orq, "ventana": ventana, "salida": tmp_path / "salida", "manifiesto": manifiesto}


class Centinela(Exception):
    pass


def correr(c, m, aut, monkeypatch, cortar_en="panel_real", captura=None):
    def corte(*a, **k):
        if captura is not None:
            captura["args"] = a
        raise Centinela
    if cortar_en:
        monkeypatch.setattr(V2, cortar_en, corte)
    try:
        V2.modo_real(c["e3"], c["ventana"], aut, c["salida"], m)
    except Centinela:
        return "llego_a_" + cortar_en
    except SystemExit as x:
        return f"detenido: {x}"
    return "termino"


def test_control_la_guarda_de_prueba_funciona(caso, monkeypatch):
    m, aut = caso["manifiesto"]()
    assert correr(caso, m, aut, monkeypatch) == "llego_a_panel_real"


def test_validez_previa_fallida_deja_INVALIDO_explicito(caso, monkeypatch):
    """Camino real completo con 3 series sintéticas: < 30 elegibles en todas las semanas → INVÁLIDO explícito."""
    m, aut = caso["manifiesto"]()
    r = correr(caso, m, aut, monkeypatch, cortar_en=None)
    assert r.startswith("detenido") and "INVALIDO" in r, r
    res = json.loads((caso["salida"] / "RESULTADO_E3.json").read_text())
    assert res["veredicto"] == "INVALIDO" and res["H1"] is None and res["H2"] is None
    assert res["validez_previa"]["evaluables"] == 0 and not res["validez_previa"]["semanas_ok"]


@DEFECTO
def test_fallo_durante_el_calculo_deja_estado_explicito(caso, monkeypatch):
    """Si `ejecutar` falla, la ejecución única queda consumida sin RESULTADO_E3.json (ni ERROR ni INVÁLIDO)."""
    m, aut = caso["manifiesto"]()
    monkeypatch.setattr(V2, "validez_previa", lambda *a, **k: ({"valido": True}, {}))

    def roto(*a, **k):
        raise RuntimeError("fallo sintético a mitad del cálculo")
    monkeypatch.setattr(V2, "ejecutar", roto)
    with pytest.raises(RuntimeError):
        V2.modo_real(caso["e3"], caso["ventana"], aut, caso["salida"], m)
    assert (caso["salida"] / "RESULTADO_E3.json").exists(), "no queda ningún estado explícito del fallo"


@DEFECTO
def test_insumo_alterado_entre_verificacion_y_lectura_se_detecta(caso, monkeypatch):
    """TOCTOU: el hash se verifica y los archivos se leen después; un cambio intermedio no se detecta."""
    m, aut = caso["manifiesto"]()
    original = V2.importar_congelados

    def alterar_y_seguir(e3):
        npz(caso["e3"] / "resultados/calidad/series/BBBUSDT.npz", "BBBUSDT", precio=999.0)
        return original(e3)
    monkeypatch.setattr(V2, "importar_congelados", alterar_y_seguir)
    visto = {}
    monkeypatch.setattr(V2, "validez_previa", lambda P, *a, **k: (_ for _ in ()).throw(Centinela(visto.update(C=P.C.copy()))))
    with pytest.raises((Centinela, SystemExit)):
        V2.modo_real(caso["e3"], caso["ventana"], aut, caso["salida"], m)
    assert "C" not in visto or not np.any(visto["C"] == 999.0), "el panel se construyó con datos alterados después de la guarda"


@DEFECTO
def test_archivo_de_mapeos_debe_estar_verificado(caso, monkeypatch):
    """El manifiesto puede apuntar `mapeos` a un archivo que no figura entre las entradas verificadas."""
    (caso["rep"] / "otro.json").write_text(json.dumps({"mapeos": [{"regla": 1, "viejo_usdt": "AAAUSDT", "nuevo_usdt": "BBBUSDT",
                                                                     "r": 1, "E": "2020-01-01"}]}))
    m, aut = caso["manifiesto"](mapeos="otro.json")
    r = correr(caso, m, aut, monkeypatch)
    assert r.startswith("detenido"), f"usó un archivo de mapeos sin verificar: {r}"


@DEFECTO
def test_solo_la_ventana_A_es_aceptada_por_el_codigo(caso, monkeypatch):
    """El código acepta cualquier ventana VÁLIDA que fije un manifiesto firmado (p. ej., la B, 2021-02-22)."""
    caso["ventana"].write_text(json.dumps({"veredicto": "VALIDO", "inicio_H": "2021-02-22"}))
    m, aut = caso["manifiesto"](inicio="2021-02-22")
    r = correr(caso, m, aut, monkeypatch)
    assert r.startswith("detenido"), f"aceptó otra ventana: {r}"


@DEFECTO
def test_manifiesto_sin_entradas_no_pasa_la_guarda(caso, monkeypatch):
    """Un manifiesto con la lista de entradas vacía pasa la verificación sin comprobar nada."""
    m, aut = caso["manifiesto"](entradas=[])
    r = correr(caso, m, aut, monkeypatch)
    assert r.startswith("detenido"), f"aceptó un manifiesto vacío: {r}"


# ---------------------------------------------------------------- mapeos y nombres

INICIO = dt.date(2017, 7, 1)


def dia(i):
    return (INICIO + dt.timedelta(days=int(i))).isoformat()


def serie(ini, fin, p0, D=220, paso=1.001):
    x = np.full(D, np.nan)
    x[ini:fin] = p0 * paso ** np.arange(fin - ini)
    return x


def arrays(series):
    syms = list(series)
    C = np.array([series[s] for s in syms], dtype=float)
    act = np.isfinite(C)
    return syms, C.copy(), C.copy(), np.where(act, 1e6, np.nan), act


@DEFECTO
def test_apalancado_conserva_su_marca_si_su_base_se_renombra(mods):
    """Al retirar la fila X por un renombre X→Y, la base X desaparece y XUP deja de detectarse como apalancado
    (universo.Panel lo infiere de las bases presentes). Sin efecto con la tabla actual: ninguna base retirada tiene apalancados."""
    universo = mods[0]
    s = {"XXXUSDT": serie(0, 100, 20.0), "XXXUPUSDT": serie(0, 200, 5.0), "YYYUSDT": serie(105, 220, 0.2)}
    antes = universo.Panel(*arrays(s))
    assert antes.apalancado[antes.sym.index("XXXUPUSDT")], "precondición"
    syms, O, C, QV, act, _ = V2.aplicar_mapeos(*arrays(s), [{"regla": 1, "viejo_usdt": "XXXUSDT", "nuevo_usdt": "YYYUSDT",
                                                            "r": 100, "E": dia(100)}], INICIO)
    despues = universo.Panel(syms, O, C, QV, act)
    assert despues.apalancado[despues.sym.index("XXXUPUSDT")], "el token apalancado perdió su marca"


@DEFECTO
def test_mapeo_con_hueco_de_30_dias_o_mas_conserva_la_edad(mods):
    """Un renombre mapeado con 40 días sin negociación: el panel reinicia la edad (regla mecánica de 30 días) y el v2 no lo
    rechaza ni lo advierte. Sin efecto con la tabla actual (hueco máximo: 8 días)."""
    universo = mods[0]
    s = {"XXXUSDT": serie(0, 100, 20.0), "YYYUSDT": serie(140, 220, 20.0 * 1.001 ** 140)}
    syms, O, C, QV, act, _ = V2.aplicar_mapeos(*arrays(s), [{"regla": 1, "viejo_usdt": "XXXUSDT", "nuevo_usdt": "YYYUSDT",
                                                            "r": 1, "E": dia(100)}], INICIO)
    P = universo.Panel(syms, O, C, QV, act)
    assert P.ep_ini[0, 200] == 0, f"edad reiniciada en el día {P.ep_ini[0, 200]}"


def test_escalar_una_serie_por_una_constante_no_cambia_el_motor(mods):
    """Sustento de la regla 2: dividir los precios previos al corte por r no altera nada de lo que el motor calcula antes
    del corte (no hay umbrales de precio absoluto). Se escala toda una serie por 1000 y se compara."""
    universo, motor, _ = mods
    import pruebas_motor
    F = pruebas_motor.formaciones()
    P = pruebas_motor.panel_sintetico(20261026, momentum=0.02)
    P2 = universo.Panel(P.sym, P.O.copy(), P.C.copy(), P.QV.copy(), P.act.copy())
    P2.O[7] *= 1000.0
    P2.C[7] *= 1000.0
    P2._derivados()
    a = motor.simular(P, F, motor.Config(), {}, registrar_pesos=True)
    b = motor.simular(P2, F, motor.Config(), {}, registrar_pesos=True)
    np.testing.assert_allclose(a["r"], b["r"], rtol=1e-9, atol=1e-12)
    assert a["objetivos"] == b["objetivos"]
    ia, ib = motor.ic_semanal(P, F, {}), motor.ic_semanal(P2, F, {})
    np.testing.assert_allclose([x[1] for x in ia], [x[1] for x in ib], rtol=1e-9, atol=1e-12, equal_nan=True)


def test_aplicar_mapeos_sin_mapeos_es_identidad(mods):
    s = {"AAAUSDT": serie(0, 220, 1.0), "BBBUSDT": serie(10, 200, 2.0)}
    syms, O, C, QV, act = arrays(s)
    r = V2.aplicar_mapeos(syms, O, C, QV, act, [], INICIO)
    assert r[0] == syms and all(np.array_equal(x, y, equal_nan=True) for x, y in zip(r[1:5], (O, C, QV, act)))


def test_v2_no_conserva_rutas_de_R2_ni_de_B():
    src = V2_RUTA.read_text()
    for prohibido in ("particionar", "R2X", "R1prima", "P0_resultado", "una_sola_opcion"):
        assert prohibido not in src, prohibido


# ---------------------------------------------------------------- R4 de punta a punta en un panel sintético natural

@pytest.mark.parametrize("impl", [pytest.param(V1, id="v1", marks=pytest.mark.xfail(strict=True, reason="v1 usa el EW neto")),
                                  pytest.param(V2, id="v2")])
def test_r4_excluye_la_moneda_de_mayor_aporte_bruto(impl, mods):
    """Semilla 37, momentum 0 (hallada al recorrer 120 paneles sintéticos): contra el EW bruto el mayor aporte es C04USDT;
    contra el neto, C34USDT. Se corre `ejecutar` completo con pocas réplicas."""
    universo, motor, inferencia = mods
    import pruebas_motor
    P = pruebas_motor.panel_sintetico(37, momentum=0.0)
    F = pruebas_motor.formaciones()
    res = impl.ejecutar(P, F, universo, motor, inferencia, replicas_R5=1, diag_B=199)
    assert res["robustez"]["R4_sin_mayor_aporte"] == "C04USDT"


# ---------------------------------------------------------------- código ejecutado ≠ código con hash (bytecode en caché)

@DEFECTO
def test_importar_congelados_ejecuta_el_codigo_con_hash(tmp_path, monkeypatch):
    """`importar_congelados` verifica el sha256 de los .py, pero `import` carga `__pycache__/*.pyc` si su cabecera
    (fecha y tamaño de la fuente) coincide, sin mirar su contenido. El árbol congelado de E3 tiene esos .pyc.
    Se fabrica, en un árbol temporal, un .pyc con cabecera válida y código distinto: la guarda no lo detecta."""
    import importlib.util as iu
    import marshal
    import os
    import struct
    cod = tmp_path / "ejecucion_E3" / "codigo"
    cod.mkdir(parents=True)
    for m in ("universo.py", "motor.py", "inferencia.py"):
        shutil.copy2(COPIA / "e3copia" / "codigo" / m, cod / m)
    fuente = cod / "inferencia.py"
    st = os.stat(fuente)
    otro = compile(fuente.read_text() + "\nMARCA_PYC = 'codigo distinto del que tiene hash'\n", str(fuente), "exec")
    (cod / "__pycache__").mkdir()
    (cod / "__pycache__" / f"inferencia.{sys.implementation.cache_tag}.pyc").write_bytes(
        iu.MAGIC_NUMBER + struct.pack("<III", 0, int(st.st_mtime) & 0xFFFFFFFF, st.st_size & 0xFFFFFFFF) + marshal.dumps(otro))
    monkeypatch.setattr(sys, "path", list(sys.path))
    nombres = ("universo", "motor", "inferencia")
    previos = {n: sys.modules.pop(n) for n in nombres if n in sys.modules}
    try:
        _, _, inferencia = V2.importar_congelados(tmp_path / "ejecucion_E3")
    finally:
        for n in nombres:
            sys.modules.pop(n, None)
        sys.modules.update(previos)
    assert not hasattr(inferencia, "MARCA_PYC"), "se ejecutó un .pyc distinto del .py verificado"


# ---------------------------------------------------------------- BNX (1 BNXOLD = 100 BNX, reapertura 2023-02-22) sin mapear

def test_salto_de_nivel_en_un_corte_no_cambia_universo_senal_ni_IC_posteriores(mods):
    """Sustento (sintético) de que dejar BNX sin regla 2 no altera A: con un corte de 3 días y un salto ×0,01 al reabrir,
    universo, señal S, A y el IC de todas las formaciones posteriores a la reapertura son idénticos a los del caso sin salto.
    (a) exige 30 días activos seguidos y P.r no cruza huecos, así que ningún retorno usado atraviesa el corte."""
    universo, motor, _ = mods
    import pruebas_motor
    F = pruebas_motor.formaciones()
    base = pruebas_motor.panel_sintetico(20261026, momentum=0.02)
    i, g = 3, F[60] - 40
    assert base.act[i, g - 200:g + 300].all(), "precondición: serie activa alrededor del corte"

    def con_corte(salto):
        O, C, QV, act = base.O.copy(), base.C.copy(), base.QV.copy(), base.act.copy()
        act[i, g:g + 3] = False
        O[i, g:g + 3] = C[i, g:g + 3] = QV[i, g:g + 3] = np.nan
        O[i, g + 3:] *= salto
        C[i, g + 3:] *= salto
        return universo.Panel(base.sym, O, C, QV, act)
    A, B = con_corte(1.0), con_corte(0.01)
    assert np.isnan(B.r[i, g:g + 4]).all() and np.isfinite(B.r[i, g + 4]), "P.r no debe cruzar el hueco"
    posteriores = [t for t in F if t - 1 >= g + 3]
    assert len(posteriores) > 40
    usados = 0
    for t in posteriores:
        ua, ub = universo.universo(A, t), universo.universo(B, t)
        for k in ("elegibles", "U_pred", "U_inv"):
            assert ua[k] == ub[k], (t, k)
        np.testing.assert_allclose(ua["S"], ub["S"], rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(ua["A"], ub["A"], rtol=1e-9, atol=1e-12)
        usados += i in ua["elegibles"]
    assert usados > 20, "la serie con salto tiene que ser elegible en muchas formaciones posteriores"
    ia, ib = motor.ic_semanal(A, posteriores, {}), motor.ic_semanal(B, posteriores, {})
    np.testing.assert_allclose([x[1] for x in ia], [x[1] for x in ib], rtol=1e-9, atol=1e-12, equal_nan=True)


@DEFECTO
def test_mapeo_de_regla_2_duplicado_se_rechaza(mods):
    """`aplicar_mapeos` no rechaza entradas repetidas: una regla 2 duplicada divide dos veces por r, sin aviso.
    Sin efecto con la tabla actual (22 entradas distintas), pero la tabla se va a re-congelar (MFT→HIFI, BNX, VIDT…)."""
    x = np.full(220, np.nan)
    x[:100] = 1000.0 * 1.001 ** np.arange(100)
    x[104:] = 1.0 * 1.001 ** np.arange(116)
    m = {"regla": 2, "viejo_usdt": "QQQUSDT", "nuevo_usdt": "QQQUSDT", "r": 1000, "E": dia(101)}
    with pytest.raises(SystemExit):
        V2.aplicar_mapeos(*arrays({"QQQUSDT": x, "RRRUSDT": serie(0, 220, 5.0)}), [m, dict(m)], INICIO)
