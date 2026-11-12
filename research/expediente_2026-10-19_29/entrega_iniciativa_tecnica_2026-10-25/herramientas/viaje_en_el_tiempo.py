"""Plugin de pytest SOLO para el experimento de dependencia horaria (Fase J): corre la sesión de pruebas con el reloj de
pared desplazado a VIAJE_UTC (time-machine, avanzando: tick=True). No toca el código ni el entorno fijado (se instala
aparte, fuera del venv). time.monotonic no se altera, así que asyncio mide igual."""
import datetime as dt
import os

import time_machine

_viaje = None


def pytest_configure(config):
    global _viaje
    _viaje = time_machine.travel(dt.datetime.fromisoformat(os.environ["VIAJE_UTC"]), tick=True)
    _viaje.start()


def pytest_unconfigure(config):
    if _viaje is not None:
        _viaje.stop()
