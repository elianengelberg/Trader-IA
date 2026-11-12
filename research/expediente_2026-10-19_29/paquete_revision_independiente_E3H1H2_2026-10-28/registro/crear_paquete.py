"""Arma la evidencia del paquete de revisión independiente COPIANDO (nunca moviendo ni modificando) desde el scratchpad.
Conserva la estructura relativa original bajo <paquete>/evidencia/, para que las pruebas y scripts encuentren sus rutas.
  - evidencia principal (paquete A): documentos, protocolo, código, resultados pequeños, E3R, reparación, revisión y cierre;
  - datos (paquete B, aparte): series de calidad (757 .npz) y las 8.028 páginas archivadas.
Escribe registro/INVENTARIO_ORIGEN.tsv (ruta en el paquete, sha256, ruta de origen) y registro/INVENTARIO_E3_COMPLETO.sha256
(todos los archivos del árbol E3, incluidos los que NO se copian, para verificarlos más adelante contra el original).
Uso: python -I crear_paquete.py <scratchpad> <paquete>"""
import hashlib
import os
import shutil
import sys
from pathlib import Path

S, PK = Path(sys.argv[1]), Path(sys.argv[2])
E3 = Path("experimentos/E3_seleccion_posicion_2026-10-19")
X = E3 / "ejecucion_E3"
A = [E3 / f for f in ("CAMBIOS_PROPUESTOS_v3.md", "CIERRE_E3.md", "CIERRE_E3_MANIFIESTO.sha256", "DECISIONES_FINALES_E3.md", "INFORME_E3.md",
                      "PROTOCOLO_E3_BORRADOR.md", "PROTOCOLO_E3_v2_BORRADOR.md", "PROTOCOLO_E3_v3_PROPUESTO.md",
                      "REGISTRO_HIPOTESIS_tras_E3_investigacion.md", "REGISTRO_HIPOTESIS_tras_E3_revision.md",
                      "REGISTRO_HIPOTESIS_tras_E3_v3_A1_A3.md", "REGISTRO_HIPOTESIS_tras_cierre_E3.md", "SHA256SUMS")]
A += [X / f for f in ("ESTADO_A3_BLOQUEADO.md", "INFORME_EJECUCION_E3.md", "MANIFIESTO_F3.sha256", "REGISTRO_EJECUCIONES.jsonl",
                      "protocolo", "resultados/estructural", "resultados/conciliacion_pasada1", "resultados/pruebas", "resultados/calibracion",
                      "resultados/calidad/auditoria_por_simbolo.json", "datos_anuncios/commoncrawl/renombres_candidatos.json",
                      "datos_anuncios/commoncrawl/exclusiones_usdt.json", "datos_anuncios/commoncrawl/listados_usdt.json",
                      "datos_anuncios/commoncrawl/anuncios_clasificados.json", "datos_anuncios/commoncrawl/resumen_indice.json",
                      "datos_vision/listados/simbolos_usdt.json")]
A += [X / "codigo" / p.name for p in sorted((S / X / "codigo").glob("*.py"))]
A += [Path(d) for d in ("experimentos/E3R_desbloqueo_2026-10-26", "reparacion_E3H1H2_2026-10-26",
                        "revision_independiente_E3H1H2_2026-10-26", "cierre_bloqueantes_E3H1H2_2026-10-27")]
B = [X / "resultados/calidad/series", X / "datos_anuncios/commoncrawl/paginas"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def copiar(rel, destino_raiz, filas):
    origen = S / rel
    if origen.is_dir() and not origen.is_symlink():
        for raiz, dirs, archivos in os.walk(origen, followlinks=False):
            dirs[:] = [x for x in dirs if x != "__pycache__"]
            for n in dirs + archivos:
                p = Path(raiz, n)
                if p.is_symlink():  # solo existe copia_aislada/experimentos: se recrea como enlace RELATIVO
                    q = destino_raiz / p.relative_to(S)
                    q.parent.mkdir(parents=True, exist_ok=True)
                    destino = os.path.relpath(Path(os.readlink(p)), p.parent)
                    if not q.is_symlink():
                        os.symlink(destino, q)
                    filas.append((str(p.relative_to(S)), "ENLACE->" + destino, str(p)))
            for n in archivos:
                p = Path(raiz, n)
                if p.is_symlink() or p.suffix == ".pyc":
                    continue
                q = destino_raiz / p.relative_to(S)
                q.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, q)
                filas.append((str(p.relative_to(S)), sha(q), str(p)))
    else:
        q = destino_raiz / rel
        q.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, q)
        filas.append((str(rel), sha(q), str(origen)))


for nombre, lista, raiz in (("A", A, PK / "evidencia"), ("B", B, PK.parent / (PK.name + "_DATOS") / "evidencia")):
    filas = []
    for rel in lista:
        copiar(rel, raiz, filas)
    errores = [f for f in filas if not f[1].startswith("ENLACE") and sha(f[2]) != f[1]]
    assert not errores, errores[:3]
    destino = (PK if nombre == "A" else raiz.parent) / "registro"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / f"INVENTARIO_ORIGEN_{nombre}.tsv").write_text("ruta_en_evidencia\tsha256\tsha256_igual_al_origen_en\n" +
                                                             "".join(f"{a}\t{b}\t{c}\n" for a, b, c in filas))
    print(nombre, "archivos:", sum(1 for f in filas if not f[1].startswith("ENLACE")), "enlaces:", sum(1 for f in filas if f[1].startswith("ENLACE")))

arbol = S / E3
lineas = []
for raiz, dirs, archivos in os.walk(arbol, followlinks=False):
    for n in archivos:
        p = Path(raiz, n)
        lineas.append(f"{sha(p)}  ./{p.relative_to(arbol).as_posix()}\n")
lineas.sort(key=lambda x: x[66:].encode())
(PK / "registro" / "INVENTARIO_E3_COMPLETO.sha256").write_text("".join(lineas))
print("inventario E3 completo:", len(lineas), "archivos")
