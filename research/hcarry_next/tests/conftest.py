"""Configuración de pruebas: ruta del paquete y bloqueo de red (ninguna prueba puede conectarse a internet)."""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(autouse=True)
def _sin_red(monkeypatch: pytest.MonkeyPatch) -> None:
    def bloqueado(*a, **k):  # pragma: no cover - solo salta si una prueba intenta usar la red
        raise RuntimeError("red bloqueada en las pruebas")
    monkeypatch.setattr(socket, "create_connection", bloqueado)
    monkeypatch.setattr(socket.socket, "connect", bloqueado)
