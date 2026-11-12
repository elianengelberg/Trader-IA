"""Higiene del código de esta entrega. El mismo defecto apareció dos veces (en v0.5, `sonda_p4.py`, y durante la
construcción de esta entrega, en la prueba diferencial): un subproceso con `-I` ignora PYTHONDONTWRITEBYTECODE y, sin
`-B`, escribe `__pycache__` dentro del paquete. Esta prueba lo impide en todo el código de la entrega."""
import ast
from pathlib import Path

ENTREGA = Path(__file__).resolve().parent.parent.parent


def _listas_con_I_sin_B(fuente: Path) -> list[int]:
    malas = []
    for n in ast.walk(ast.parse(fuente.read_text(encoding="utf-8"))):
        if isinstance(n, ast.List):
            textos = {e.value for e in n.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
            if "-I" in textos and "-B" not in textos:
                malas.append(n.lineno)
    return malas


def test_ningun_subproceso_python_aislado_escribe_bytecode():
    archivos = [p for p in ENTREGA.rglob("*.py") if "referencia_E3" not in p.parts]
    assert len(archivos) >= 15
    malas = {str(p.relative_to(ENTREGA)): lineas for p in archivos if (lineas := _listas_con_I_sin_B(p))}
    assert not malas, malas


def test_la_prueba_detecta_el_defecto_de_v05():
    """Control positivo: la línea defectuosa de v0.5 (`sonda_p4.py`, antes de la corrección) se detecta."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "sonda.py"
        f.write_text('p = subprocess.Popen([sys.executable, "-I", "-c", prog])\n', encoding="utf-8")
        assert _listas_con_I_sin_B(f) == [1]
        f.write_text('p = subprocess.Popen([sys.executable, "-I", "-B", "-c", prog])\n', encoding="utf-8")
        assert _listas_con_I_sin_B(f) == []
