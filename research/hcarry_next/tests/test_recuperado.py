"""El material recuperado de rev. 5 sigue intacto (bytes y hashes) y en solo lectura, y el paquete no lo importa."""

from __future__ import annotations

import hashlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REC = RAIZ / "recuperado"
ZIP_SHA = "5783517c7f2355de414d4c8b6ee0b8b9b73abc140fb5e260e1bb6341952da93d"
PRECHEQUEO_SHA = "17a336c14ec1a21c244ed5fe645decedfe8320fd02a4bdec65efec760d086562"


def test_hashes_del_material_recuperado() -> None:
    assert hashlib.sha256((REC / "recuperacion_parcial_hcarry_rev5.zip").read_bytes()).hexdigest() == ZIP_SHA
    lineas = (REC / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 9
    for linea in lineas:
        sha, rel = linea.split(maxsplit=1)
        assert hashlib.sha256((REC / rel).read_bytes()).hexdigest() == sha, rel
    pre = next(REC.rglob("prechequeo_exchangeinfo.py"))
    assert hashlib.sha256(pre.read_bytes()).hexdigest() == PRECHEQUEO_SHA


def test_recuperado_en_solo_lectura_y_no_importado() -> None:
    for p in REC.rglob("*"):
        assert not p.stat().st_mode & 0o222, p  # sin permiso de escritura para nadie
    for py in (RAIZ / "src").rglob("*.py"):
        assert "recuperado" not in py.read_text(encoding="utf-8"), py
