"""Pruebas del orquestador v3. SOLO datos sintéticos: ninguna serie real se abre (guarda autouse).

Las defensas se prueban en el CAMINO REAL (`modo_real`) sobre un árbol E3 sintético:
  - los sha256 esperados se recalculan para los archivos sintéticos con `sha256(b"PRUEBA|" + bytes)`, que no coincide
    con ningún hash real ni lo contiene;
  - FRASE y FRASES_DECISION se reemplazan por frases de prueba. Ningún archivo producido aquí sirve para autorizar nada.
El v3 a probar se toma de la variable V3_RUTA (para correr la misma suite contra mutantes); por omisión, el generado.
Uso: python -B -m pytest -p no:cacheprovider --basetemp <dir> test_orquestador_v3.py
"""
import datetime as dt
import fcntl
import functools
import hashlib
import importlib.util
import json
import marshal
import os
import pathlib
import shutil
import struct
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

sys.dont_write_bytecode = True
warnings.filterwarnings("ignore", category=RuntimeWarning)
CB = Path(__file__).resolve().parents[1]
S = CB.parent
V3_RUTA = Path(os.environ.get("V3_RUTA", CB / "orquestador_v3" / "ejecutar_E3_v3.py"))
V2_RUTA = S / "reparacion_E3H1H2_2026-10-26" / "orquestador_v2" / "ejecutar_E3_v2.py"
E3_REAL = S / "experimentos" / "E3_seleccion_posicion_2026-10-19" / "ejecucion_E3"
SERIES_REALES = str(E3_REAL / "resultados" / "calidad" / "series")
MODULOS = ("universo.py", "motor.py", "inferencia.py", "pruebas_motor.py", "conciliacion.py")
D_TOTAL = (dt.date(2026, 5, 31) - dt.date(2017, 7, 1)).days + 1


def sha_real(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def sal(b):
    return hashlib.sha256(b"PRUEBA|" + b).hexdigest()


def cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


assert sha_real(V2_RUTA) == "01fc934459b791fd5fbd451aa1c6931fc9e6764b9361e5caea46314cc5ee6f68"
V3 = cargar("orq_v3", V3_RUTA)
V2 = cargar("orq_v2", V2_RUTA)
REALES = {"frase": V3.FRASE, "sha_v3": V3.SHA_PROPIO, "decisiones": tuple(V3.FRASES_DECISION.values())}
FUENTES = {m[:-3]: (E3_REAL / "codigo" / m).read_bytes() for m in MODULOS}


class Centinela(BaseException):
    """Corta la ejecución en un punto conocido (hereda de BaseException: el v3 la tiene que atrapar como ERROR)."""


# ---------------------------------------------------------------- guardas

_read_bytes_original = pathlib.Path.read_bytes


@pytest.fixture(autouse=True)
def sin_series_reales(monkeypatch):
    original = np.load

    def guarda(f, *a, **k):
        if SERIES_REALES in str(f):
            raise AssertionError(f"lectura de una serie real: {f}")
        return original(f, *a, **k)

    def rb(self):
        if SERIES_REALES in str(self):
            raise AssertionError(f"lectura de bytes de una serie real: {self}")
        return _read_bytes_original(self)
    monkeypatch.setattr(np, "load", guarda)
    monkeypatch.setattr(pathlib.Path, "read_bytes", rb)


@pytest.fixture(autouse=True)
def modulos_limpios():
    nombres = ("universo", "motor", "inferencia", "pruebas_motor")
    previos = {n: sys.modules.get(n) for n in nombres}
    yield
    for n, m in previos.items():
        if m is None:
            sys.modules.pop(n, None)
        else:
            sys.modules[n] = m


@pytest.fixture(scope="module")
def mods():
    return V3.cargar_modulos(dict(FUENTES))


# ---------------------------------------------------------------- árbol E3 sintético y camino real

def npz(ruta, simbolo, rng=None, precio=1.0, desde=0):
    D = D_TOTAL
    if rng is None:
        C = np.full(D, precio)
    else:
        C = 10 * np.exp(np.cumsum(rng.normal(0, 0.03, D)))
    O = np.r_[C[0], C[:-1]]
    est = np.ones(D, dtype=np.int8)
    est[:desde] = 0
    C, O = np.where(est == 1, C, np.nan), np.where(est == 1, O, np.nan)
    np.savez(ruta, simbolo=np.array(simbolo), O=O, C=C, QV=np.where(est == 1, 5e6, np.nan), estado=est, NT=np.ones(D))


class Entorno:
    def __init__(self, tmp, monkeypatch, n_monedas=3, mapeos=None):
        self.tmp, self.mp = tmp, monkeypatch
        self.e3, self.rep, self.cierre = tmp / "ejecucion_E3", tmp / "reparacion", tmp / "cierre"
        (self.e3 / "codigo").mkdir(parents=True)
        for m in MODULOS:
            (self.e3 / "codigo" / m).write_bytes(FUENTES[m[:-3]])
        self.series = self.e3 / "resultados" / "calidad" / "series"
        self.series.mkdir(parents=True)
        rng = np.random.default_rng(20261027)
        nombres = [f"C{i:02d}USDT" for i in range(n_monedas)] + (["BTCUSDT"] if n_monedas > 3 else [])
        for s in nombres:
            npz(self.series / f"{s}.npz", s, rng if n_monedas > 3 else None)
        est = self.e3 / "resultados" / "estructural"
        est.mkdir(parents=True)
        (est / "estructural.json").write_text("{}")
        (est / "listas_fijas_por_lunes.json").write_text("[]")
        for r in ("segunda_pasada/resoluciones_manuales.json", "segunda_pasada/salida_pasada2/conciliacion.json",
                  "segunda_pasada/salida_pasada2/eventos.json", "segunda_pasada/salida_pasada2/salidas.json",
                  "segunda_pasada/eventos_omitidos.json"):
            (self.rep / r).parent.mkdir(parents=True, exist_ok=True)
            (self.rep / r).write_text("[]")
        (self.cierre / "tabla").mkdir(parents=True)
        self.mapeos_archivo = self.cierre / "tabla" / "mapeos_adenda1_completa.json"
        self.mapeos_archivo.write_text(json.dumps({"mapeos": mapeos or []}))
        self.ventana = tmp / "ventana_A.json"
        self.ventana.write_text(json.dumps({"veredicto": "VALIDO", "inicio_H": "2023-05-15"}))
        self.salida = tmp / "salida"
        self.intentos = tmp / "INTENTOS_E3.jsonl"
        mp = monkeypatch
        mp.setattr(V3, "sha_bytes", sal)
        mp.setattr(V3, "SHA_PROPIO", sal(V3_RUTA.read_bytes()))
        mp.setattr(V3, "FRASE", "FRASE DE PRUEBA SIN VALOR V3")
        mp.setattr(V3, "FRASES_DECISION", {"reapertura_y_adenda_R": "DECISION DE PRUEBA 1 SIN VALOR",
                                           "D1_lectura_literal": "DECISION DE PRUEBA 2 SIN VALOR"})
        mp.setattr(V3, "REPARACION", self.rep)
        mp.setattr(V3, "CIERRE", self.cierre)
        mp.setattr(V3, "INTENTOS", self.intentos)
        self.fijar()

    def fijar(self):
        """Recalcula los sha256 «fijados en el código» para el árbol sintético actual (con la sal de prueba)."""
        congel = {m: sal(FUENTES[m[:-3]]) for m in ("universo.py", "motor.py", "inferencia.py")}
        self.mp.setattr(V3, "CONGELADOS", congel)
        self.mp.setattr(V3, "PRUEBAS_MOTOR", sal(FUENTES["pruebas_motor"]))
        self.mp.setattr(V3, "SHA_VENTANA_A", sal(self.ventana.read_bytes()))
        raices = {"E3": self.e3, "reparacion": self.rep, "cierre": self.cierre, "ventana": self.ventana}
        exig = {}
        for n, (b, r, t, _) in V2_EXIGIDAS.items():
            p = raices[b] if b == "ventana" else raices[b] / r
            exig[n] = (b, r, t, V3.hash_conjunto_bytes(V3._leer_conjunto(p)) if t == "conjunto" else sal(p.read_bytes()))
        self.mp.setattr(V3, "EXIGIDAS", exig)
        self.exig = exig

    def manifiesto(self, entradas=None, **extra):
        ent = entradas if entradas is not None else [{"nombre": n, "base": b, "ruta": r, "tipo": t, "sha256": h}
                                                     for n, (b, r, t, h) in self.exig.items()]
        m = self.tmp / "ENTRADAS_CONGELADAS_V3.json"
        m.write_text(json.dumps({"inicio_H_esperado": "2023-05-15", "entradas": ent, **extra}))
        return m

    def autorizacion(self, m, extra="", nombre="autorizacion_de_prueba.txt", sin=()):
        lineas = [V3.FRASE, V3.SHA_PROPIO, sal(m.read_bytes()), *V3.FRASES_DECISION.values()]
        lineas = [x for k, x in enumerate(lineas) if k not in sin]
        a = self.tmp / nombre
        a.write_text("\n".join(lineas) + "\n" + extra)
        return a

    def correr(self, m=None, a=None, salida=None):
        m = m or self.manifiesto()
        a = a or self.autorizacion(m)
        try:
            V3.modo_real(self.e3, self.ventana, a, salida or self.salida, m)
        except V3.Rechazo as x:
            return f"rechazo: {x}"
        except V3.FinTerminal as x:
            return f"terminal: {x}"
        except Centinela:
            return "centinela_sin_atrapar"
        return "termino"

    def resultado(self, salida=None):
        return json.loads(((salida or self.salida) / "RESULTADO_E3.json").read_text())

    def eventos(self):
        return [json.loads(x) for x in self.intentos.read_text().splitlines()] if self.intentos.exists() else []


V2_EXIGIDAS = dict(V3.EXIGIDAS)  # forma (base, ruta, tipo) del v3 a probar; los sha256 se recalculan por entorno


@pytest.fixture
def ent(tmp_path, monkeypatch):
    return Entorno(tmp_path, monkeypatch)


def cortar(monkeypatch, funcion, captura=None):
    def corte(*a, **k):
        if captura is not None:
            captura["args"] = a
        raise Centinela(funcion)
    monkeypatch.setattr(V3, funcion, corte)


# ================================================================= C7 · ventana A
def test_control_el_camino_real_llega_al_panel(ent, monkeypatch):
    cortar(monkeypatch, "panel_real")
    r = ent.correr()
    assert r.startswith("terminal") and ent.resultado()["veredicto"] == "ERROR" and ent.resultado()["etapa"] == "panel"
    assert [e["evento"] for e in ent.eventos()] == ["INICIADO", "ERROR"]


def test_ventana_B_se_rechaza_antes_de_crear_la_salida(ent, monkeypatch):
    ent.ventana.write_text(json.dumps({"veredicto": "VALIDO", "inicio_H": "2021-02-22"}))
    r = ent.correr()
    assert r.startswith("rechazo") and "ventana_A" in r and not ent.salida.exists() and ent.eventos() == []


def test_ventana_B_con_manifiesto_y_hash_ajustados_igual_se_rechaza(ent, monkeypatch):
    """Aunque alguien fijara el hash de otra ventana, el contenido tiene que ser inicio 2023-05-15 (doble control)."""
    ent.ventana.write_text(json.dumps({"veredicto": "VALIDO", "inicio_H": "2021-02-22"}))
    ent.fijar()
    r = ent.correr()
    assert r.startswith("rechazo") and "no es la A" in r and not ent.salida.exists()


# ================================================================= C8 · manifiesto y entradas exigidas
@pytest.mark.parametrize("caso", ["vacio", "falta_una", "sobra_una", "repetida", "otra_ruta", "otro_inicio", "ilegible"])
def test_manifiesto_invalido_se_rechaza_sin_crear_salida(ent, caso):
    ent_ = [{"nombre": n, "base": b, "ruta": r, "tipo": t, "sha256": h} for n, (b, r, t, h) in ent.exig.items()]
    extra = {}
    if caso == "vacio":
        ent_ = []
    elif caso == "falta_una":
        ent_ = [x for x in ent_ if x["nombre"] != "mapeos_adenda1_completa"]
    elif caso == "sobra_una":
        ent_.append({"nombre": "otra", "base": "E3", "ruta": "codigo/motor.py", "tipo": "archivo", "sha256": "x"})
    elif caso == "repetida":
        ent_.append(dict(ent_[0]))
    elif caso == "otra_ruta":
        (ent.cierre / "tabla" / "otra.json").write_text(json.dumps({"mapeos": []}))
        x = next(x for x in ent_ if x["nombre"] == "mapeos_adenda1_completa")
        x["ruta"], x["sha256"] = "tabla/otra.json", sal((ent.cierre / "tabla" / "otra.json").read_bytes())
    elif caso == "otro_inicio":
        extra = {"inicio_H_esperado": "2021-02-22"}
    m = ent.manifiesto(ent_, **extra)
    if caso == "ilegible":
        m.write_text("{no es json")
    r = ent.correr(m=m, a=ent.autorizacion(m))
    assert r.startswith("rechazo") and "manifiesto" in r, r
    assert not ent.salida.exists() and ent.eventos() == []


def test_mapeos_solo_desde_la_entrada_verificada(ent, monkeypatch):
    """Una clave «mapeos» en el manifiesto (como en el v2) no tiene efecto; se usa la entrada fijada en el código."""
    (ent.cierre / "tabla" / "otro.json").write_text(json.dumps({"mapeos": [{"regla": 2, "viejo_usdt": "C00USDT", "nuevo_usdt": "C00USDT",
                                                                              "r": 10, "E": "2020-01-01"}]}))
    m = ent.manifiesto(mapeos="tabla/otro.json")
    cap = {}
    cortar(monkeypatch, "panel_real", cap)
    ent.correr(m=m, a=ent.autorizacion(m))
    assert cap["args"][2] == []


def test_tabla_de_mapeos_alterada_se_rechaza(ent):
    m = ent.manifiesto()
    ent.mapeos_archivo.write_text(json.dumps({"mapeos": [{"regla": 2, "viejo_usdt": "C00USDT", "nuevo_usdt": "C00USDT", "r": 10,
                                                            "E": "2020-01-01"}]}))
    r = ent.correr(m=m, a=ent.autorizacion(m))
    assert r.startswith("rechazo") and "mapeos_adenda1_completa" in r and not ent.salida.exists()


def test_exigidas_del_v3_coinciden_con_los_insumos_congelados():
    """Los sha256 fijados en el código son los de la reparación (series, estructural, módulos, segunda pasada, ventana)
    y el de la tabla completa; el manifiesto generado coincide exactamente con EXIGIDAS."""
    if os.environ.get("V3_RUTA"):
        pytest.skip("solo para el v3 generado")
    previo = {x["nombre"]: x["sha256"] for x in json.loads((V2_RUTA.parent / "ENTRADAS_CONGELADAS.json").read_text())["entradas"]}
    for n, (b, r, t, h) in V3.EXIGIDAS.items():
        if n == "mapeos_adenda1_completa":
            assert h == sha_real(CB / "tabla" / "mapeos_adenda1_completa.json")
        else:
            assert h == previo[n], n
    man = json.loads((V3_RUTA.parent / "ENTRADAS_CONGELADAS_V3.json").read_text())
    assert {x["nombre"]: (x["base"], x["ruta"], x["tipo"], x["sha256"]) for x in man["entradas"]} == V3.EXIGIDAS
    assert man["inicio_H_esperado"] == V3.INICIO_H_A == "2023-05-15"
    assert V3.SHA_VENTANA_A == "dcbd80abf5b0d4a2373d411c3db37cf4a2089dc8fcbcb193dce085b838d57e24"


# ================================================================= C9 · lectura única y enlaces
def test_alterar_insumos_despues_de_verificar_no_llega_al_panel(ent, monkeypatch):
    """TOCTOU: entre verificar y usar, se reescribe una serie (precio 999) y un módulo en disco. El v3 usa los bytes
    ya verificados: el panel no tiene 999 y el módulo ejecutado es el original."""
    original = V3.cargar_modulos

    def alterar_y_seguir(fuentes):
        npz(ent.series / "C01USDT.npz", "C01USDT", precio=999.0)
        (ent.e3 / "codigo" / "inferencia.py").write_bytes(FUENTES["inferencia"] + b"\nMARCA_TOCTOU = 1\n")
        return original(fuentes)
    monkeypatch.setattr(V3, "cargar_modulos", alterar_y_seguir)
    visto = {}

    def capturar(P, *a, **k):
        visto["C"] = P.C.copy()
        raise Centinela("validez")
    monkeypatch.setattr(V3, "validez_previa", capturar)
    ent.correr()
    assert "C" in visto and not np.any(visto["C"] == 999.0), "el panel usó datos alterados después de la guarda"
    assert not hasattr(sys.modules["inferencia"], "MARCA_TOCTOU")


def test_cada_insumo_se_lee_una_sola_vez(ent, monkeypatch):
    lecturas = {}

    def contar(self):
        lecturas[str(Path(self).resolve())] = lecturas.get(str(Path(self).resolve()), 0) + 1
        return _read_bytes_original(self)
    monkeypatch.setattr(pathlib.Path, "read_bytes", contar)
    cortar(monkeypatch, "validez_previa")
    m = ent.manifiesto()
    a = ent.autorizacion(m)
    lecturas.clear()
    ent.correr(m=m, a=a)
    relevantes = {k: v for k, v in lecturas.items() if str(ent.tmp) in k}
    assert relevantes and all(v == 1 for v in relevantes.values()), {k: v for k, v in relevantes.items() if v != 1}
    assert any(k.endswith("C01USDT.npz") for k in relevantes) and any(k.endswith("inferencia.py") for k in relevantes)


def test_enlace_simbolico_en_las_series_se_rechaza(ent):
    os.symlink(ent.series / "C00USDT.npz", ent.series / "C99USDT.npz")
    r = ent.correr()
    assert r.startswith("rechazo") and "enlace simbólico" in r and not ent.salida.exists()


# ================================================================= C10 · código ejecutado
def test_pyc_envenenado_no_se_ejecuta(ent, monkeypatch):
    import importlib.util as iu
    fuente = ent.e3 / "codigo" / "inferencia.py"
    st = os.stat(fuente)
    otro = compile(fuente.read_text() + "\nMARCA_PYC = 'codigo distinto del verificado'\n", str(fuente), "exec")
    (ent.e3 / "codigo" / "__pycache__").mkdir()
    (ent.e3 / "codigo" / "__pycache__" / f"inferencia.{sys.implementation.cache_tag}.pyc").write_bytes(
        iu.MAGIC_NUMBER + struct.pack("<III", 0, int(st.st_mtime) & 0xFFFFFFFF, st.st_size & 0xFFFFFFFF) + marshal.dumps(otro))
    ent.fijar()  # __pycache__ está fuera de la lista de insumos de E3: no cambia ningún sha256 exigido
    for n in ("universo", "motor", "inferencia"):
        sys.modules.pop(n, None)
    cortar(monkeypatch, "panel_real")
    ent.correr()
    inf = sys.modules["inferencia"]
    assert not hasattr(inf, "MARCA_PYC"), "se ejecutó un .pyc distinto del código verificado"
    assert inf.__file__.startswith("<verificado:inferencia.py:")


def test_sha_propio_es_el_de_los_bytes_cargados():
    assert hashlib.sha256(V3_RUTA.read_bytes()).hexdigest() == REALES["sha_v3"]


# ================================================================= C11 · estados terminales, errores e intentos
def test_INVALIDO_explicito_y_no_reescrito_como_ERROR(ent):
    r = ent.correr()
    res = ent.resultado()
    assert r.startswith("terminal: INVALIDO") and res["veredicto"] == "INVALIDO" and res["H1"] is None
    assert [e["evento"] for e in ent.eventos()] == ["INICIADO", "INVALIDO"]


def test_EVALUADO_de_punta_a_punta_y_sin_segunda_ejecucion(tmp_path, monkeypatch):
    """Panel sintético de 40 monedas + BTCUSDT en todo el rango: el camino real completo termina en EVALUADO (con pocas
    réplicas para que la prueba sea rápida). Una segunda ejecución, con otra salida, se rechaza."""
    e = Entorno(tmp_path, monkeypatch, n_monedas=40)
    monkeypatch.setattr(V3, "ejecutar", functools.partial(V3.ejecutar, replicas_R5=2, diag_B=199))
    r = e.correr()
    assert r == "termino", r
    res = e.resultado()
    assert res["veredicto"] == "EVALUADO" and res["validez_previa"]["valido"] and res["semanas_ic"] > 150
    assert [x["evento"] for x in e.eventos()] == ["INICIADO", "EVALUADO"]
    r2 = e.correr(salida=tmp_path / "salida_2")
    assert r2.startswith("rechazo") and "resultado terminal" in r2 and not (tmp_path / "salida_2").exists()


@pytest.mark.parametrize("etapa,funcion", [("panel", "panel_real"), ("validez_previa", "validez_previa"), ("calculo", "ejecutar")])
def test_excepcion_en_cada_etapa_deja_ERROR_explicito(ent, monkeypatch, etapa, funcion):
    if funcion == "ejecutar":
        monkeypatch.setattr(V3, "validez_previa", lambda *a, **k: ({"valido": True}, {}))

    def roto(*a, **k):
        raise RuntimeError(f"fallo sintético en {etapa}")
    monkeypatch.setattr(V3, funcion, roto)
    r = ent.correr()
    res = ent.resultado()
    assert r.startswith("terminal: ERROR") and res["veredicto"] == "ERROR" and res["etapa"] == etapa
    assert res["tipo"] == "RuntimeError" and res["sha_traceback"] == sal(res["traceback"].encode())
    assert res["estadisticos_iniciados"] == (etapa == "calculo")
    assert [e["evento"] for e in ent.eventos()] == ["INICIADO", "ERROR"]


def test_systemexit_e_interrupcion_dentro_del_calculo_tambien_son_ERROR(ent, monkeypatch):
    monkeypatch.setattr(V3, "validez_previa", lambda *a, **k: ({"valido": True}, {}))

    def corte(*a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(V3, "ejecutar", corte)
    try:
        ent.correr()
    except KeyboardInterrupt:  # si el orquestador no la atrapa, la prueba falla sin cortar la sesión de pytest
        pass
    assert (ent.salida / "RESULTADO_E3.json").exists(), "la interrupción no dejó estado terminal"
    assert ent.resultado()["veredicto"] == "ERROR" and ent.resultado()["tipo"] == "KeyboardInterrupt"


def test_fallo_al_escribir_el_resultado_es_ERROR_valido(ent, monkeypatch):
    monkeypatch.setattr(V3, "validez_previa", lambda *a, **k: ({"valido": True}, {}))
    monkeypatch.setattr(V3, "ejecutar", lambda *a, **k: {"no_serializable": object(), "semanas_ic": 0})  # float(object()) falla
    ent.correr()
    res = ent.resultado()
    assert res["veredicto"] == "ERROR" and res["etapa"] == "escritura" and res["estadisticos_iniciados"]
    assert not list(ent.salida.glob("*.tmp"))


def test_reintento_tras_ERROR_previo_a_estadisticos(ent, monkeypatch):
    def roto(*a, **k):
        raise RuntimeError("fallo sintético en el panel")
    monkeypatch.setattr(V3, "panel_real", roto)
    m = ent.manifiesto()
    a1 = ent.autorizacion(m)
    ent.correr(m=m, a=a1)
    h = ent.eventos()[-1]["sha_resultado"]
    s2 = ent.tmp / "salida_2"
    assert ent.correr(m=m, a=a1, salida=s2).startswith("rechazo")                     # misma autorización
    a2 = ent.autorizacion(m, extra="otra autorizacion\n", nombre="a2.txt")
    assert "citar" in ent.correr(m=m, a=a2, salida=s2)                                    # nueva, sin citar el ERROR
    a3 = ent.autorizacion(m, extra=f"REINTENTO TRAS ERROR {h}\n", nombre="a3.txt")
    cortar(monkeypatch, "panel_real")
    ent.correr(m=m, a=a3, salida=s2)
    assert [e["evento"] for e in ent.eventos()] == ["INICIADO", "ERROR", "INICIADO", "ERROR"] and s2.exists()
    assert ent.eventos()[2]["reintento_de"] == h


def test_reintento_tras_ERROR_con_estadisticos_se_rechaza(ent, monkeypatch):
    monkeypatch.setattr(V3, "validez_previa", lambda *a, **k: ({"valido": True}, {}))

    def roto(*a, **k):
        raise RuntimeError("fallo en el cálculo")
    monkeypatch.setattr(V3, "ejecutar", roto)
    m = ent.manifiesto()
    ent.correr(m=m)
    h = ent.eventos()[-1]["sha_resultado"]
    a2 = ent.autorizacion(m, extra=f"REINTENTO TRAS ERROR {h}\n", nombre="a2.txt")
    r = ent.correr(m=m, a=a2, salida=ent.tmp / "salida_2")
    assert r.startswith("rechazo") and "decisión metodológica" in r and not (ent.tmp / "salida_2").exists()


def test_intento_sin_estado_terminal_bloquea(ent):
    ent.intentos.write_text(json.dumps({"utc": "x", "evento": "INICIADO", "id_intento": "abc:s", "sha_autorizacion": "z"}) + "\n")
    r = ent.correr()
    assert r.startswith("rechazo") and "sin estado terminal" in r and not ent.salida.exists()


def test_ejecucion_concurrente_bloqueada(ent):
    with open(ent.intentos, "a+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        r = ent.correr()
    assert r.startswith("rechazo") and "en curso" in r and not ent.salida.exists()


def test_salida_existente_no_se_reescribe(ent):
    ent.salida.mkdir()
    assert ent.correr().startswith("rechazo") and ent.eventos() == []


# ================================================================= C13 · autorización
@pytest.mark.parametrize("falta", [0, 1, 2, 3, 4])
def test_autorizacion_incompleta_se_rechaza(ent, falta):
    m = ent.manifiesto()
    r = ent.correr(m=m, a=ent.autorizacion(m, sin=(falta,)))
    assert r.startswith("rechazo") and "autorización" in r and not ent.salida.exists()


# ================================================================= C12 · mapeos
INICIO = dt.date(2017, 7, 1)


def dia(i):
    return (INICIO + dt.timedelta(days=int(i))).isoformat()


def serie(ini, fin, p0, D=260, paso=1.001):
    x = np.full(D, np.nan)
    x[ini:fin] = p0 * paso ** np.arange(fin - ini)
    return x


def arrays(series):
    syms = list(series)
    C = np.array([series[s] for s in syms], dtype=float)
    act = np.isfinite(C)
    return syms, C.copy(), C.copy(), np.where(act, 1e6, np.nan), act


def test_mapeo_de_regla_2_duplicado_se_rechaza():
    x = np.full(260, np.nan)
    x[:100], x[104:] = 1000.0 * 1.001 ** np.arange(100), 1.0 * 1.001 ** np.arange(156)
    m = {"regla": 2, "viejo_usdt": "QQQUSDT", "nuevo_usdt": "QQQUSDT", "r": 1000, "E": dia(101)}
    with pytest.raises(V3.Rechazo, match="repetido"):
        V3.aplicar_mapeos(*arrays({"QQQUSDT": x, "RRRUSDT": serie(0, 260, 5.0)}), [m, dict(m)], INICIO)


def test_regla_1_con_hueco_de_30_dias_o_mas_se_rechaza():
    s = {"XXXUSDT": serie(0, 100, 20.0), "YYYUSDT": serie(140, 260, 20.0)}
    with pytest.raises(V3.Rechazo, match="hueco"):
        V3.aplicar_mapeos(*arrays(s), [{"regla": 1, "viejo_usdt": "XXXUSDT", "nuevo_usdt": "YYYUSDT", "r": 1, "E": dia(100)}], INICIO)


def test_regla_1_con_hueco_corto_hereda_la_edad(mods):
    universo = mods["universo"]
    s = {"XXXUSDT": serie(0, 100, 20.0), "YYYUSDT": serie(110, 260, 0.2)}
    syms, O, C, QV, act, reg, origen = V3.aplicar_mapeos(*arrays(s), [{"regla": 1, "viejo_usdt": "XXXUSDT", "nuevo_usdt": "YYYUSDT",
                                                                      "r": 100, "E": dia(100)}], INICIO)
    P = universo.Panel(syms, O, C, QV, act)
    assert syms == ["YYYUSDT"] and P.ep_ini[0, 200] == 0 and origen == [("XXXUSDT", "YYYUSDT")]
    assert np.isclose(C[0, 99] * 1, 20.0 * 1.001 ** 99 / 100)


def test_retirar_la_base_de_un_apalancado_se_rechaza(mods):
    s = {"XXXUSDT": serie(0, 100, 20.0), "XXXUPUSDT": serie(0, 260, 5.0), "YYYUSDT": serie(105, 260, 0.2)}
    syms, O, C, QV, act, reg, origen = V3.aplicar_mapeos(*arrays(s), [{"regla": 1, "viejo_usdt": "XXXUSDT", "nuevo_usdt": "YYYUSDT",
                                                                      "r": 100, "E": dia(100)}], INICIO)
    with pytest.raises(V3.Rechazo, match="marcas"):
        V3.comprobar_marcas(list(s), syms, origen, mods["universo"])


def test_fusionar_marcas_distintas_se_rechaza(mods):
    """Un estable (lista fija) «renombrado» a un token común cambiaría retroactivamente la marca de su historia."""
    s = {"USDCUSDT": serie(0, 100, 1.0), "ZZZUSDT": serie(103, 260, 1.0)}
    syms, O, C, QV, act, reg, origen = V3.aplicar_mapeos(*arrays(s), [{"regla": 1, "viejo_usdt": "USDCUSDT", "nuevo_usdt": "ZZZUSDT",
                                                                      "r": 1, "E": dia(100)}], INICIO)
    with pytest.raises(V3.Rechazo, match="marcas"):
        V3.comprobar_marcas(list(s), syms, origen, mods["universo"])


def test_regla_1R_divide_la_serie_y_el_tramo_nuevo_es_listado_nuevo(mods):
    universo = mods["universo"]
    x = np.full(260, np.nan)
    x[:100], x[115:] = 50.0, 1.0
    s = {"LLLUSDT": x, "MMMUSDT": serie(0, 260, 3.0)}
    syms, O, C, QV, act, reg, origen = V3.aplicar_mapeos(*arrays(s), [{"regla": "1R", "viejo_usdt": "LLLUSDT", "nuevo_usdt": None,
                                                                      "r": None, "E": None, "reutilizacion_desde": dia(115)}], INICIO)
    assert syms == ["LLLUSDT", "MMMUSDT", f"LLL~HASTA{(INICIO + dt.timedelta(days=99)):%Y%m%d}USDT"]
    P = universo.Panel(syms, O, C, QV, act)
    assert P.ep_ini[0, 200] == 115 and not act[0, :115].any() and act[2, :100].all() and not act[2, 100:].any()
    V3.comprobar_marcas(list(s), syms, origen, universo)
    assert reg[0]["ultimo_activo_tramo_anterior"] == dia(99)


def test_regla_1R_sin_corte_se_rechaza():
    s = {"LLLUSDT": serie(0, 260, 50.0)}
    with pytest.raises(V3.Rechazo, match="corte"):
        V3.aplicar_mapeos(*arrays(s), [{"regla": "1R", "viejo_usdt": "LLLUSDT", "reutilizacion_desde": dia(115)}], INICIO)


def test_regla_desconocida_se_rechaza():
    with pytest.raises(V3.Rechazo, match="regla desconocida"):
        V3.aplicar_mapeos(*arrays({"AAAUSDT": serie(0, 260, 1.0)}), [{"regla": 3, "viejo_usdt": "AAAUSDT"}], INICIO)


def test_cadena_regla_1_y_regla_2(mods):
    """STRAT→STRAX (regla 1) y después STRAX 1:10 (regla 2): se aplican en orden de fecha sobre la misma fila."""
    x = serie(0, 100, 2.0)
    y = np.full(260, np.nan)
    y[105:180], y[185:] = 2.0, 0.2
    syms, O, C, QV, act, reg, origen = V3.aplicar_mapeos(*arrays({"AAAUSDT": x, "BBBUSDT": y}), [
        {"regla": 2, "viejo_usdt": "BBBUSDT", "nuevo_usdt": "BBBUSDT", "r": 10, "E": dia(181)},
        {"regla": 1, "viejo_usdt": "AAAUSDT", "nuevo_usdt": "BBBUSDT", "r": 1, "E": dia(100)}], INICIO)
    assert syms == ["BBBUSDT"] and np.isclose(C[0, 150], 0.2) and np.isclose(C[0, 50], 2.0 * 1.001 ** 50 / 10)


def test_sin_mapeos_es_identidad():
    s = {"AAAUSDT": serie(0, 260, 1.0), "BBBUSDT": serie(10, 200, 2.0)}
    a = arrays(s)
    r = V3.aplicar_mapeos(*a, [], INICIO)
    assert r[0] == a[0] and all(np.array_equal(x, y, equal_nan=True) for x, y in zip(r[1:5], a[1:5])) and r[5] == []


def test_mapeo_imposible_se_detecta_antes_de_crear_la_salida(tmp_path, monkeypatch):
    e = Entorno(tmp_path, monkeypatch, mapeos=[{"regla": 1, "viejo_usdt": "C00USDT", "nuevo_usdt": "NOESTAUSDT", "r": 1, "E": "2020-01-01"}])
    r = e.correr()
    assert r.startswith("rechazo") and "mapeo imposible" in r and not e.salida.exists() and e.eventos() == []


def test_marcas_replica_a_universo_Panel(mods):
    universo = mods["universo"]
    syms = ["BTCUSDT", "BTCUPUSDT", "USDCUSDT", "EURUSDT", "AAAUSDT", "AAADOWNUSDT", "ZZZBULLUSDT", "LUNA~HASTA20220512USDT"]
    D = 40
    P = universo.Panel(syms, np.ones((len(syms), D)), np.ones((len(syms), D)), np.ones((len(syms), D)), np.ones((len(syms), D), bool))
    esperado = {s: (bool(P.fijo[k]), bool(P.apalancado[k])) for k, s in enumerate(syms)}
    assert V3.marcas(syms, universo) == esperado


# ================================================================= el cálculo del v3 es el del v2
def test_hash_conjunto_en_memoria_igual_al_del_v2(tmp_path):
    d = tmp_path / "c"
    (d / "sub").mkdir(parents=True)
    for n, b in (("a.npz", b"1"), ("b.npz", b"22"), ("sub/c.bin", b"333"), ("Z.npz", b"4")):
        (d / n).write_bytes(b)
    assert V3.hash_conjunto(d) == V2.hash_conjunto(d)


@pytest.mark.parametrize("semilla,momentum", [(20261026, 0.02), (37, 0.0)])
def test_ejecutar_del_v3_identico_al_del_v2(mods, semilla, momentum):
    universo, motor, inferencia, pm = mods["universo"], mods["motor"], mods["inferencia"], mods["pruebas_motor"]
    P = pm.panel_sintetico(semilla, momentum=momentum)
    F = pm.formaciones()
    a = V2.ejecutar(P, F, universo, motor, inferencia, replicas_R5=2, diag_B=199, btc="C00USDT")
    b = V3.ejecutar(P, F, universo, motor, inferencia, replicas_R5=2, diag_B=199, btc="C00USDT")
    assert json.dumps(a, default=float, sort_keys=True) == json.dumps(b, default=float, sort_keys=True)


# ================================================================= higiene
def test_ningun_archivo_de_prueba_contiene_la_frase_ni_los_hashes_reales(tmp_path_factory):
    """Se ejecuta al final (orden de definición): revisa todo el directorio base de temporales de esta sesión."""
    base = tmp_path_factory.getbasetemp()
    prohibidos = [REALES["frase"], REALES["sha_v3"], *REALES["decisiones"],
                  hashlib.sha256((CB / "orquestador_v3" / "ENTRADAS_CONGELADAS_V3.json").read_bytes()).hexdigest()]
    hallados = [str(p) for p in base.rglob("*") if p.is_file() and any(x.encode() in _read_bytes_original(p) for x in prohibidos)]
    assert hallados == []
