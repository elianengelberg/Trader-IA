"""Inventario de preservación, en SOLO LECTURA, para comparar el estado antes y después de la misión.

Registra:
- repositorio: HEAD, rama, origin, huella de ``git status --porcelain --ignored`` y, para cada archivo VERSIONADO de
  research/tendencia_btc (T y T-MULTI), si el árbol de trabajo coincide con el blob de HEAD. La referencia es git, no un
  registro escrito por este agente;
- artefactos protegidos de T: SHA-256 frente a los valores registrados en v0.5 (evidencia/98_*);
- archivos de texto sin seguimiento de T (corte.py y otros): SHA-256 frente a ARTEFACTOS_SHA256.txt de la copia de trabajo;
- entregas (ZIP): tamaño, SHA-256 frente al valor registrado y huella del directorio central. En los ZIP que contienen
  datos de mercado NO se calcula el SHA-256, para no leer esos bytes; solo la huella del directorio central (nombres,
  CRC-32 y tamaños) y el tamaño;
- manifiestos de las carpetas de entregas: cada entrada se comprueba, salvo las de datos de mercado, que se cuentan aparte.

Uso: python3 -I inventario_preservacion.py <scratchpad> <repo> <v0.5 extraído> <salida.json>
Salida 0 si nada registrado difiere."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

DATOS = re.compile(r"(^|/)(datos|datos_multi|datos_papel|binance_vision|otros_simbolos|diarios|red)/|\.csv$|\.parquet$"
                   r"|klines|fundingRate|aggTrades|BTCUSDT-|ETHUSDT-")
NO_DATOS = re.compile(r"^(TABLA_DECISION_P2_.*\.csv|MANIFIESTO.*\.json|VALIDACION.*\.json)$")
# ZIP con datos de mercado: según la lista de sus miembros (solo nombres, del directorio central)
ZIP_CON_DATOS = {"hcarry_next_historico_2026-10-16.zip", "hcarry_test_historico_2026-10-16.zip",
                 "trader_ia_research_2026-10-17.zip"}
ZIP_SCRATCHPAD = [
    "SOLUCION_FINAL_TRADER_IA_v0.5_2026-10-20.zip", "fx4_zip_A/SOLUCION_FINAL_TRADER_IA_v0.5_2026-10-20.zip",
    "fx4_zip_B/SOLUCION_FINAL_TRADER_IA_v0.5_2026-10-20.zip", "SOLUCION_VERIFICADA_P1_P2_P4_2026-10-20.zip",
    "CIERRE_FINAL_P1_P2_P4_2026-10-20.zip", "AUDITORIA_PARALELA_P1_P2_P4_2026-10-20.zip",
    "hcarry_next_final.zip", "hcarry_next_historico_2026-10-16.zip", "hcarry_next_snapshot1.zip",
    "hcarry_next_snapshot2.zip", "hcarry_next_validacion_historica.zip", "hcarry_test_historico_2026-10-16.zip",
    "trader_ia_research_2026-10-17.zip", "recuperacion/recuperacion_parcial_hcarry_rev5.zip"]
REGISTRADOS = {  # SHA-256 informados en las entregas anteriores (evidencia/94_*, 95_* y el informe de cierre de v0.5)
    "SOLUCION_FINAL_TRADER_IA_v0.5_2026-10-20.zip": "5bf9bc5d004b51188fdd407ae71eaae2ccefec7251af7001f8d89b264b4f5308",
    "fx4_zip_A/SOLUCION_FINAL_TRADER_IA_v0.5_2026-10-20.zip":
        "d63bfa4f792136d6e4e99babcc38b024b84c8fc56ef31856f0a2ac3bcb5019bb",
    "fx4_zip_B/SOLUCION_FINAL_TRADER_IA_v0.5_2026-10-20.zip":
        "6bf96048492f409b8c15d4cdc294227651409a9b6287f0e8548d25609c37f4f9",
}
MANIFIESTOS = [  # (carpeta, manifiesto relativo a la carpeta)
    ("auditoria_T_REV_EMA9", "SHA256SUMS"), ("auditoria_paralela_P1_P2_P4_2026-10-20", "SHA256SUMS.txt"),
    ("auditoria_paralela_P1_P2_P4_2026-10-20/00_entrega_original", "SHA256SUMS"),
    ("cierre_final_P1_P2_P4_2026-10-20", "SHA256SUMS.txt"), ("entregables_P1_P2_P4_2026-10-20", "SHA256SUMS"),
    ("expediente_metodologico_2026-10-20", "SHA256SUMS"), ("experimentos/E2_descubrimiento_2026-10-19", "SHA256SUMS"),
    ("experimentos/E3_seleccion_posicion_2026-10-19", "SHA256SUMS"), ("fase_documental_2026-10-20", "SHA256SUMS"),
    ("preservacion/contenido", "SHA256SUMS"), ("auditoria_preservacion/fase3_pendientes", "SHA256SUMS_arbol"),
    ("solucion_verificada_P1_P2_P4_2026-10-20", "SHA256SUMS.txt"),
    ("solucion_final_trader_ia_v0.5_2026-10-20", "SHA256SUMS.txt"),
]
MANIFIESTOS_REPO = [("research/entregas_hcarry", "SHA256SUMS"), ("research/entregas_hcarry", "SHA256SUMS_2026-10-17"),
                    ("research/hcarry_next/recuperado", "SHA256SUMS"),
                    ("research/hcarry_next", "ARTEFACTOS_SHA256_2026-10-17.txt"),
                    ("research/tendencia_btc", "ARTEFACTOS_SHA256.txt")]


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _git(repo: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True).stdout


def _directorio_central(p: Path) -> str:
    with zipfile.ZipFile(p) as z:
        filas = sorted(f"{i.filename}\t{i.CRC:08x}\t{i.file_size}\t{i.compress_size}" for i in z.infolist())
    return hashlib.sha256("\n".join(filas).encode()).hexdigest()


def _manifiesto(base: Path, nombre: str) -> dict:
    m = base / nombre
    r = {"manifiesto": str(m), "existe": m.is_file(), "ok": 0, "fallan": [], "faltan": [], "omitidas_datos": 0}
    if not m.is_file():
        return r
    for linea in m.read_text(encoding="utf-8", errors="replace").splitlines():
        partes = linea.split(None, 1)
        if len(partes) != 2 or not re.fullmatch(r"[0-9a-f]{64}", partes[0]):
            continue
        h, ruta = partes[0], partes[1].lstrip("*").removeprefix("./")
        no_es_dato = NO_DATOS.search(Path(ruta).name)  # tablas sintéticas y manifiestos (metadatos)
        if not no_es_dato and (DATOS.search(ruta) or (ruta.endswith(".zip") and Path(ruta).name in ZIP_CON_DATOS)):
            r["omitidas_datos"] += 1
            continue
        f = base / ruta
        if not f.is_file():
            r["faltan"].append(ruta)
        elif _sha(f) != h:
            r["fallan"].append(ruta)
        else:
            r["ok"] += 1
    return r


def main(sp: Path, repo: Path, v05: Path, salida: Path) -> int:
    inv: dict = {}
    porcelain = _git(repo, "status", "--porcelain", "--ignored")
    inv["repositorio"] = {"HEAD": _git(repo, "rev-parse", "HEAD").strip(),
                          "rama": _git(repo, "branch", "--show-current").strip(),
                          "origin": _git(repo, "rev-parse", "origin/claude/algo-trading-simulation-platform-ngf7xo").strip(),
                          "huella_porcelain": hashlib.sha256(porcelain.encode()).hexdigest(),
                          "lineas_porcelain": len(porcelain.splitlines())}
    # T y T-MULTI: árbol de trabajo frente a HEAD (git es la referencia)
    distintos, iguales = [], 0
    for linea in _git(repo, "ls-tree", "-r", "HEAD", "research/tendencia_btc").splitlines():
        meta, ruta = linea.split("\t", 1)
        blob = meta.split()[2]
        if _git(repo, "hash-object", ruta).strip() == blob:
            iguales += 1
        else:
            distintos.append(ruta)
    inv["tendencia_btc_frente_a_HEAD"] = {"iguales": iguales, "distintos": sorted(distintos)}
    t = repo / "research/tendencia_btc"
    registrados_98 = {}
    for linea in (v05 / "evidencia/98_integridad_final.txt").read_text().splitlines():
        if re.match(r"^[0-9a-f]{64}  experimentos/|^[0-9a-f]{64}  PRERREGISTRO", linea):
            h, r = linea.split("  ", 1)
            registrados_98[r] = h
    inv["T_protegidos"] = {r: {"registrado_v05": h, "actual": _sha(t / r), "igual": _sha(t / r) == h}
                           for r, h in sorted(registrados_98.items())}
    artefactos = dict(reversed(x.split("  ", 1)) for x in (t / "ARTEFACTOS_SHA256.txt").read_text().splitlines() if x)
    sin_seguimiento = ["papel/corte.py", "tests/test_papel_corte.py", "papel/VERIFICACION_OPERATIVA_2026-10-17.md"]
    inv["T_sin_seguimiento"] = {r: {"registrado": artefactos.get(r), "actual": _sha(t / r),
                                    "igual": artefactos.get(r) == _sha(t / r)} for r in sin_seguimiento}
    # Entregas
    pres = dict(reversed(x.split("  ", 1))
                for x in (v05 / "evidencia/00_preservacion_relativa.txt").read_text().splitlines())
    hc = dict(reversed(x.split("  ", 1)) for x in (repo / "research/entregas_hcarry/SHA256SUMS_2026-10-17").read_text()
              .splitlines() if x)
    hc.update(dict(reversed(x.split("  ", 1)) for x in (repo / "research/entregas_hcarry/SHA256SUMS").read_text()
                   .splitlines() if x))
    zips = {}
    for rel in ZIP_SCRATCHPAD:
        p = sp / rel
        nombre = Path(rel).name
        e: dict = {"existe": p.is_file()}
        if p.is_file():
            e.update(tamano=p.stat().st_size, directorio_central=_directorio_central(p))
            registrado = REGISTRADOS.get(rel) or pres.get(nombre) or hc.get(nombre)
            e["registrado"] = registrado
            if nombre in ZIP_CON_DATOS:
                e["sha256"] = "NO CALCULADO (contiene datos de mercado)"
            else:
                e["sha256"] = _sha(p)
                e["igual_al_registrado"] = None if registrado is None else e["sha256"] == registrado
        zips[rel] = e
    for nombre in sorted(hc):
        p = repo / "research/entregas_hcarry" / nombre
        e = {"existe": p.is_file(), "registrado": hc[nombre]}
        if p.is_file():
            e.update(tamano=p.stat().st_size, directorio_central=_directorio_central(p))
            if nombre in ZIP_CON_DATOS:
                e["sha256"] = "NO CALCULADO (contiene datos de mercado)"
                copia = zips.get(nombre, {})
                e["directorio_central_igual_a_la_copia_del_scratchpad"] = (
                    copia.get("directorio_central") == e["directorio_central"]
                    and copia.get("tamano") == e["tamano"])
            else:
                e["sha256"] = _sha(p)
                e["igual_al_registrado"] = e["sha256"] == hc[nombre]
        zips[f"repo:research/entregas_hcarry/{nombre}"] = e
    for nombre, h in sorted(pres.items()):  # copias preservadas dentro de v0.5
        p = v05 / "00_preservado" / nombre
        zips[f"v0.5:00_preservado/{nombre}"] = {"existe": p.is_file(), "registrado": h, "sha256": _sha(p),
                                                "igual_al_registrado": _sha(p) == h}
    inv["entregas_zip"] = zips
    inv["manifiestos"] = [_manifiesto(sp / c, m) for c, m in MANIFIESTOS] + \
                         [_manifiesto(repo / c, m) for c, m in MANIFIESTOS_REPO]
    # Resumen
    problemas = []
    if inv["tendencia_btc_frente_a_HEAD"]["distintos"] != ["research/tendencia_btc/ARTEFACTOS_SHA256.txt",
                                                            "research/tendencia_btc/papel/PRERREGISTRO_PAPEL.md"]:
        problemas.append("tendencia_btc: archivos distintos de HEAD fuera de los dos cambios preexistentes")
    problemas += [f"T protegido distinto: {r}" for r, v in inv["T_protegidos"].items() if not v["igual"]]
    problemas += [f"T sin seguimiento distinto: {r}" for r, v in inv["T_sin_seguimiento"].items() if not v["igual"]]
    problemas += [f"ZIP ausente o distinto: {r}" for r, v in zips.items()
                  if not v["existe"] or v.get("igual_al_registrado") is False
                  or v.get("directorio_central_igual_a_la_copia_del_scratchpad") is False]
    problemas += [f"manifiesto {m['manifiesto']}: {len(m['fallan'])} fallan, {len(m['faltan'])} faltan"
                  for m in inv["manifiestos"] if not m["existe"] or m["fallan"] or m["faltan"]]
    inv["problemas"] = problemas
    salida.write_text(json.dumps(inv, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"repositorio: HEAD {inv['repositorio']['HEAD'][:7]}, huella {inv['repositorio']['huella_porcelain'][:16]}…")
    print(f"tendencia_btc frente a HEAD: {iguales} iguales; distintos: {inv['tendencia_btc_frente_a_HEAD']['distintos']}")
    print(f"T protegidos iguales a v0.5: {sum(v['igual'] for v in inv['T_protegidos'].values())} de {len(registrados_98)}")
    print(f"ZIP: {len(zips)} ({sum(1 for v in zips.values() if v.get('igual_al_registrado'))} con SHA-256 igual al "
          f"registrado; {sum(1 for v in zips.values() if 'NO CALCULADO' in str(v.get('sha256')))} sin SHA-256 por datos)")
    for m in inv["manifiestos"]:
        print(f"  {m['manifiesto'].split('/scratchpad/')[-1]}: {m['ok']} OK, {len(m['fallan'])} fallan, "
              f"{len(m['faltan'])} faltan, {m['omitidas_datos']} omitidas (datos)")
    print("problemas:", problemas or "ninguno")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main(*(Path(a) for a in sys.argv[1:5])))
