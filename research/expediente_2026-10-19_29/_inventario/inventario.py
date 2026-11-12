"""Inventario de lo que NO se versiona: (a) lo excluido dentro de las fuentes seleccionadas, con huella de árbol
(sha256 de las líneas «sha256  ruta» ordenadas) para poder verificar una copia recuperada; (b) las páginas archivadas,
una por una, con su URL y sha256; (c) las entradas del scratchpad que no se seleccionaron, con archivos y tamaño.
Uso: python3 -I -B inventario.py <scratchpad> <plan_dir> <archivos_podados.tsv> <salida_dir>"""
import collections
import hashlib
import json
import os
import sys

S, PLAN, PODADOS, OUT = sys.argv[1:5]
os.makedirs(OUT, exist_ok=True)


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def arbol(p):
    lineas, n, t = [], 0, 0
    for raiz, dirs, archivos in os.walk(p):
        dirs.sort()
        for a in sorted(archivos):
            q = os.path.join(raiz, a)
            if os.path.islink(q) or not os.path.isfile(q):
                continue
            lineas.append(f"{sha(q)}  {os.path.relpath(q, p)}")
            n += 1
            t += os.path.getsize(q)
    return hashlib.sha256("\n".join(sorted(lineas)).encode()).hexdigest(), n, t


# (a) excluidos dentro de las fuentes
filas = []
paginas = []
for l in open(os.path.join(PLAN, "fuera.tsv")):
    motivo, rel = l.rstrip("\n").split("\t", 1)
    p = os.path.join(S, rel.rstrip("/"))
    if rel.endswith("/"):
        h, n, t = arbol(p)
        filas.append((rel, motivo, n, t, h))
        if "páginas web archivadas" in motivo:
            for raiz, _, archivos in os.walk(p):
                for a in sorted(archivos):
                    q = os.path.join(raiz, a)
                    url = None
                    try:
                        url = json.load(open(q)).get("url")
                    except Exception:  # noqa: BLE001
                        pass
                    paginas.append((os.path.relpath(q, S), sha(q), url or a))
    elif os.path.islink(p):
        filas.append((rel, motivo, 1, 0, "enlace → " + os.readlink(p)))
    else:
        filas.append((rel, motivo, 1, os.path.getsize(p), sha(p)))
with open(os.path.join(OUT, "EXCLUIDOS_DENTRO_DE_LAS_FUENTES.tsv"), "w") as f:
    f.write("ruta_en_el_scratchpad\tmotivo\tarchivos\tbytes\tsha256_o_huella_de_arbol\n")
    for r in sorted(filas):
        f.write("\t".join(map(str, r)) + "\n")
with open(os.path.join(OUT, "PAGINAS_ARCHIVADAS_NO_VERSIONADAS.tsv"), "w") as f:
    f.write("ruta_en_el_scratchpad\tsha256\turl_o_nombre\n")
    for r in sorted(paginas):
        f.write("\t".join(r) + "\n")

# (c) entradas no seleccionadas
sel = set()
for l in open(os.path.join(PLAN, "dentro.tsv")):
    r = l.rstrip("\n").split("\t", 1)[1]
    sel.add(r.split("/")[0] if not r.startswith("experimentos/") else "/".join(r.split("/")[:2]))
por = collections.defaultdict(lambda: [0, 0])
for l in open(PODADOS, errors="replace"):
    t, p = l.rstrip("\n").split("\t", 1)
    p = p[2:]
    k = p.split("/")[0] if not p.startswith("experimentos/") else "/".join(p.split("/")[:2])
    por[k][0] += 1
    por[k][1] += int(t)
with open(os.path.join(OUT, "ENTRADAS_NO_SELECCIONADAS.tsv"), "w") as f:
    f.write("entrada_del_scratchpad\tarchivos\tbytes\tparcialmente_incluida\n")
    for k, (n, t) in sorted(por.items()):
        if k in sel and k.startswith(("experimentos/",)):
            continue
        f.write(f"{k}\t{n}\t{t}\t{'sí (sus entregables están en el expediente)' if k in sel else 'no'}\n")
print(f"excluidos dentro: {len(filas)} · páginas: {len(paginas)} · entradas: {len(por)}")
