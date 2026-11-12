"""Compila (en memoria) cada fuente congelada y compara el código con el .pyc existente en codigo/__pycache__.
No escribe en el árbol congelado. Uso: python -I comparar_pyc.py <dir_codigo>"""
import hashlib, importlib.util, marshal, sys
from pathlib import Path
cod = Path(sys.argv[1])
for n in ("universo", "motor", "inferencia"):
    src = (cod / f"{n}.py").read_bytes()
    pyc = (cod / "__pycache__" / f"{n}.cpython-311.pyc").read_bytes()
    nuevo = marshal.dumps(compile(src, str(cod / f"{n}.py"), "exec", dont_inherit=True, optimize=0))
    viejo_obj = marshal.loads(pyc[16:])
    nuevo_obj = marshal.loads(nuevo)
    def firma(co):
        out = [co.co_code, co.co_names, co.co_varnames, co.co_name]
        for c in co.co_consts:
            out.append(firma(c) if hasattr(c, "co_code") else repr(c))
        return repr(out)
    print(n, "sha_py", hashlib.sha256(src).hexdigest()[:12], "pyc_mismo_codigo_que_fuente:", firma(viejo_obj) == firma(nuevo_obj),
          "bytes_identicos:", pyc[16:] == nuevo)
