"""Mutante para el experimento de reloj (Fase J): el estado de riesgo restaurado se ignora (RiskEngine.restore no hace
nada). Una prueba que conserve su propósito debe fallar con este mutante a cualquier hora."""
import tia.risk.engine as risk


def pytest_configure(config):
    risk.RiskEngine.restore = lambda self, restore: None
