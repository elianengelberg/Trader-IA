"""E4 · Guarda de rutas: ninguna entrada o salida del experimento puede apuntar a datos protegidos de E3.
Rechaza una ruta si:
  (1) su ruta real (enlaces simbólicos resueltos) es, o está debajo de, una ruta protegida;
  (2) algún ancestro de la ruta real tiene el mismo (dispositivo, inodo) que una ruta protegida (atrapa montajes y alias);
  (3) es, o contiene en sus primeros 6 niveles, una carpeta `resultados/calidad/series` o un archivo `.npz`;
  (4) es un enlace duro de un archivo protegido (mismo dispositivo e inodo).
Solo usa `realpath` y `stat`: no lee el contenido de las rutas protegidas.
Uso como biblioteca: `verificar(ruta, protegidos)`; `cargar_protegidos(PROTEGIDOS.tsv)`."""
import os


class RutaProtegida(Exception):
    pass


def cargar_protegidos(tsv):
    out = []
    with open(tsv) as f:
        for linea in f:
            tipo, ruta = linea.rstrip("\n").split("\t")
            out.append(ruta)
    return out


def _id(p):
    st = os.stat(p)
    return st.st_dev, st.st_ino


def verificar(ruta, protegidos):
    real = os.path.realpath(ruta)
    ids = {}
    for p in protegidos:
        rp = os.path.realpath(p)
        if real == rp or real.startswith(rp.rstrip("/") + "/"):
            raise RutaProtegida(f"(1) {ruta} → {real} está en {rp}")
        if os.path.exists(rp):
            ids[_id(rp)] = rp
    a = real
    while True:
        if os.path.exists(a) and _id(a) in ids:
            raise RutaProtegida(f"(2)/(4) {ruta}: {a} es el mismo objeto que {ids[_id(a)]}")
        padre = os.path.dirname(a)
        if padre == a:
            break
        a = padre
    if "resultados/calidad/series" in real:
        raise RutaProtegida(f"(3) {ruta}: estructura resultados/calidad/series")
    if os.path.isdir(real):
        base = real.count(os.sep)
        for raiz, dirs, archivos in os.walk(real):
            if raiz.count(os.sep) - base >= 6:
                dirs[:] = []
            if raiz.endswith(os.path.join("resultados", "calidad", "series")) or any(x.endswith(".npz") for x in archivos):
                raise RutaProtegida(f"(3) {ruta}: contiene {raiz}")
    elif real.endswith(".npz"):
        raise RutaProtegida(f"(3) {ruta}: archivo .npz")
    return real
