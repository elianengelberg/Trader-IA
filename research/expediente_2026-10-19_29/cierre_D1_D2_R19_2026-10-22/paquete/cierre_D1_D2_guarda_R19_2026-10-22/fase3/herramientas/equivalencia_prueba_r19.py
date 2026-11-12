"""Compara (por AST) la prueba de R19 y los ayudantes que usa en dos árboles. Uso: python -I equivalencia_prueba_r19.py <árbol1> <árbol2>"""
import ast, sys, pathlib
F = "tests/integration/test_account_restore.py"
NOMBRES = ("test_partial_fills_and_fees_rebuild_identically_however_often", "settle", "persister", "register_run", "_db", "engine_for", "build")
def defs(raiz):
    arbol = ast.parse((pathlib.Path(raiz) / F).read_text())
    return {n.name: ast.dump(n, include_attributes=False) for n in arbol.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in NOMBRES}
a, b = defs(sys.argv[1]), defs(sys.argv[2])
for n in NOMBRES:
    print(f"{n:62s} {'idéntica' if a.get(n) == b.get(n) else 'DISTINTA'}")
