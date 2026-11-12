"""Plugin de pytest del revisor: bloquea todo cálculo de la estrategia o de estadísticos (validez_previa, ejecutar,
modo_sintetico) en los módulos V3 y V2 de la suite. Una prueba que necesite calcular falla con «CÁLCULO BLOQUEADO
POR EL REVISOR». Las pruebas que sustituyen esas funciones por sus propios stubs siguen funcionando (su monkeypatch
se aplica después de este). Uso: PYTHONPATH=<arnes> python -B -m pytest -p guarda_revisor …"""
import pytest


class CalculoBloqueado(Exception):
    pass


def _bloqueado(*a, **k):
    raise CalculoBloqueado("CÁLCULO BLOQUEADO POR EL REVISOR")


@pytest.fixture(autouse=True)
def _bloquear_calculo(request, monkeypatch):
    for nombre in ("V3", "V2"):
        M = getattr(request.module, nombre, None)
        if M is None:
            continue
        for f in ("validez_previa", "ejecutar", "modo_sintetico"):
            if hasattr(M, f):
                monkeypatch.setattr(M, f, _bloqueado)
    yield
