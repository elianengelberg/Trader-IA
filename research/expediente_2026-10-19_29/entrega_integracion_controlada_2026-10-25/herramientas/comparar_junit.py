"""Compara JUnit de esta misión con los de referencia (revisión adversaria): conteos, nodeids, resultado por prueba.
Uso: python -I comparar_junit.py <dir_logs_mision> <dir_logs_referencia> nombre:ref [nombre:ref ...]"""
import collections
import hashlib
import pathlib
import sys
import xml.etree.ElementTree as ET


def leer(ruta: pathlib.Path):
    raiz = ET.parse(ruta).getroot()
    suites = [raiz] if raiz.tag == "testsuite" else list(raiz.iter("testsuite"))
    attrs = collections.Counter()
    casos = {}
    dup = 0
    tiempo = 0.0
    for s in suites:
        for k in ("tests", "failures", "errors", "skipped"):
            attrs[k] += int(s.get(k, 0))
        tiempo += float(s.get("time", 0))
        for c in s.iter("testcase"):
            nid = f"{c.get('classname')}::{c.get('name')}"
            hijos = [h.tag for h in c]
            res = "failed" if "failure" in hijos else "error" if "error" in hijos else "skipped" if "skipped" in hijos else "passed"
            dup += nid in casos
            casos[nid] = res
    return dict(attrs), casos, dup, tiempo


mis, ref = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
for par in sys.argv[3:]:
    n, r = par.split(":")
    a = mis / f"D_{n}.xml"
    b = ref / f"D_{r}.xml"
    at, ca, da, ta = leer(a)
    bt, cb, db, tb = leer(b)
    log = mis / f"D_{n}.pytest.txt"
    print(f"{n:10s} junit {hashlib.sha256(a.read_bytes()).hexdigest()[:16]} · log {hashlib.sha256(log.read_bytes()).hexdigest()[:16]} · "
          f"atributos {at} · casos {len(ca)} · {dict(collections.Counter(ca.values()))} · duplicados {da} · tiempo {ta:.1f} s")
    print(f"{'':10s} frente a la referencia {r} ({len(cb)} casos, {dict(collections.Counter(cb.values()))}): "
          f"mismos nodeids {set(ca) == set(cb)} · mismo resultado por prueba {ca == cb} · "
          f"faltan {sorted(set(cb) - set(ca))[:3]} · sobran {sorted(set(ca) - set(cb))[:3]} · "
          f"cambian {[k for k in ca if k in cb and ca[k] != cb[k]][:3]}")
