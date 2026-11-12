"""Validador de velas (cada defecto inyectado se detecta) y pruebas genéricas de mirada al futuro (B1, B2)."""
import pytest
from pec import datos as D
from pec import mirada_futuro as F
from pec import sintetico as G

H = 3_600_000
INI = 1_798_761_600_000


def validar(filas, n=100, ahora=None):
    return D.validar(filas, H, INI, INI + n * H, ahora if ahora is not None else INI + (n + 5) * H)


def test_serie_limpia_es_valida():
    r = validar(G.velas(100))
    assert r["veredicto"] == "VALIDO" and not r["motivos"] and r["esperadas"] == 100


@pytest.mark.parametrize("defecto,codigo", [
    ("conflicto", "V3"), ("desorden", "V2"), ("fuera_de_grilla", "V4"), ("ohlc_incoherente", "V6"),
    ("volumen_negativo", "V7"), ("no_finito", "V1"), ("campo_faltante", "V1"), ("precio_cero", "V6")])
def test_cada_defecto_invalida_con_su_codigo(defecto, codigo):
    r = validar(G.inyectar(G.velas(100), defecto))
    assert r["veredicto"] == "INVALIDO" and any(m.startswith(codigo) for m in r["motivos"]), r["motivos"]


def test_duplicado_identico_avisa_y_conflicto_invalida():
    r = validar(G.inyectar(G.velas(100), "duplicado"))
    assert r["veredicto"] == "VALIDO" and any("duplicados idénticos" in a for a in r["avisos"])


def test_faltantes_con_umbral():
    pocos = validar(G.inyectar(G.velas(1000), "hueco", 500), n=1000)  # 1 de 1000 = 0,1 % ≤ 0,5 %
    assert pocos["veredicto"] == "VALIDO" and any(a.startswith("V5") for a in pocos["avisos"])
    muchos = validar(G.inyectar(G.velas(100), "hueco", 50))           # 1 de 100 = 1 % > 0,5 %
    assert muchos["veredicto"] == "INVALIDO" and any(m.startswith("V5") for m in muchos["motivos"])
    assert muchos["detalle"]["V5"] == [INI + 50 * H]


def test_vela_incompleta_y_fuera_de_ventana():
    filas = G.velas(100)
    r = validar(filas, ahora=INI + 99 * H + 1)  # la última vela todavía no cerró
    assert r["veredicto"] == "INVALIDO" and any(m.startswith("V8") for m in r["motivos"])
    r = D.validar(G.velas(110), H, INI, INI + 100 * H, INI + 200 * H)
    assert r["veredicto"] == "VALIDO" and any(a.startswith("V9") for a in r["avisos"])


def causal(barras):
    """Media móvil de 5 cierres hasta i−1 contra el último cierre conocido (solo pasado)."""
    out = []
    for i in range(len(barras)):
        ant = [b["close"] for b in barras[max(0, i - 5):i]]
        out.append(1 if len(ant) == 5 and ant[-1] > sum(ant) / 5 else 0)
    return out


def mira_la_barra_actual(barras):
    return [1 if i > 0 and b["close"] > b["open"] else 0 for i, b in enumerate(barras)]


def normaliza_con_toda_la_serie(barras):
    media = sum(b["close"] for b in barras) / len(barras)  # estadística global: usa el futuro
    return [1 if i > 0 and barras[i - 1]["close"] > media else 0 for i in range(len(barras))]


def test_estrategia_causal_pasa_B1_y_B2():
    barras = G.velas(300, semilla=3)
    assert F.truncamiento(causal, barras) == [] and F.futuro_alterado(causal, barras) == []


def test_mirar_la_barra_actual_se_detecta_en_B2():
    barras = G.velas(300, semilla=4)
    assert F.futuro_alterado(mira_la_barra_actual, barras) != []
    # B1 no la detecta (la barra actual existe en la serie truncada): por eso hacen falta las dos pruebas
    assert F.truncamiento(mira_la_barra_actual, barras) == []


def test_estadistica_global_se_detecta_en_B1_y_B2():
    barras = G.velas(300, vol=0.03, semilla=5)
    assert F.truncamiento(normaliza_con_toda_la_serie, barras) != []
    assert F.futuro_alterado(normaliza_con_toda_la_serie, barras) != []
