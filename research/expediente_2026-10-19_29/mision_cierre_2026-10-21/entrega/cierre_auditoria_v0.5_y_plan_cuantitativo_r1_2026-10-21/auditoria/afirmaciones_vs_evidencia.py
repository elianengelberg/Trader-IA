"""Contrasta cada cifra que v0.5 DECLARA (README, GARANTIAS, informe de cierre) con lo OBSERVABLE: la evidencia de una
ejecución de ``ejecutar_todo.sh`` y el código fuente de las pruebas (tamaños de los oráculos calculados con ``ast``, sin
importar ni ejecutar las pruebas). Solo lee. Uso:
  python3 -I afirmaciones_vs_evidencia.py <paquete v0.5 extraído> <carpeta evidencia/> [<salida de pytest --collect-only -q>]
Salida 0 si todas las afirmaciones coinciden; las discrepancias se listan con su causa."""
from __future__ import annotations

import ast
import json
import math
import re
import sys
from pathlib import Path


def _tuplas(fuente: Path) -> dict[str, int]:
    """Longitud de cada tupla literal asignada a nivel de módulo (los ejes de los oráculos)."""
    arbol = ast.parse(fuente.read_text(encoding="utf-8"))
    return {n.targets[0].id: len(n.value.elts) for n in arbol.body if isinstance(n, ast.Assign)
            and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Tuple)}


def _ultimo(p: Path, patron: str) -> re.Match | None:
    m = None
    for linea in p.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.search(patron, linea) or m
    return m


def main(paq: Path, ev: Path, coleccion: Path | None) -> int:
    filas: list[tuple[str, str, str, bool, str]] = []

    def afirma(id_: str, declarado: str, observado: str, ok: bool, nota: str = "") -> None:
        filas.append((id_, declarado, observado, ok, nota))

    m = _ultimo(ev / "11_suite_v0_5.txt", r"(\d+) passed(?:, (\d+) \w+)?")
    afirma("C01 suite completa", "449 passed, 0 failed", m.group(0) if m else "?",
           bool(m) and m.group(1) == "449" and "failed" not in (ev / "11_suite_v0_5.txt").read_text())
    corridas = re.findall(r"corrida \d: (\d+) passed", (ev / "13_repeticiones.txt").read_text())
    afirma("C02 estabilidad", "3 corridas de 130", f"{len(corridas)} corridas: {corridas}",
           corridas == ["130"] * 3 and "failed" not in (ev / "13_repeticiones.txt").read_text())
    filas_m = [x for x in (ev / "10_matriz_resumen.txt").read_text().splitlines() if re.match(r"\| P\d-", x)]
    si = sum(x.rstrip().endswith("| sí |") for x in filas_m)
    afirma("C03 matriz antes/después", "48 de 48 filas con el patrón", f"{si} de {len(filas_m)} filas «sí»",
           si == len(filas_m) == 48)
    for id_, f, esperado in (("C04 mutaciones P2", "31_p2_mutaciones_oraculo.txt", "11 de 11"),
                             ("C05 mutaciones de la cadena", "52_cruzada_mutaciones.txt", "20 de 20"),
                             ("C06 mutaciones de durabilidad", "53_durabilidad_mutaciones.txt", "4 de 4"),
                             ("C07 mutaciones del ejecutor", "54_ejecutor_mutaciones.txt", "10 de 10")):
        lineas = [x for x in (ev / f).read_text().splitlines() if "\t" in x]
        muertas = sum(x.startswith("MUERTA") for x in lineas)
        afirma(id_, esperado, f"{muertas} de {len(lineas)} detectadas (MUERTA)",
               f"{muertas} de {len(lineas)}" == esperado)
    m = re.search(r"Coinciden con el oráculo independiente: (\d+) de (\d+)", (ev / "32_p2_tabla_resumen.txt").read_text())
    afirma("C08 tabla de decisión de P2", "86.400 de 86.400", m.group(0) if m else "?",
           bool(m) and m.group(1) == m.group(2) == "86400")
    t = (ev / "70_ed25519_diferencial.txt").read_text()
    casos = {k: (int(n), int(a), int(b)) for k, n, a, b in
             re.findall(r"'(\w+)': '(\d+) casos; aceptados: propia (\d+), OpenSSL (\d+)'", t)}
    total = sum(v[0] for v in casos.values())
    degenerados = {k: v for k, v in casos.items() if "orden" in k}
    afirma("C09 Ed25519 diferencial", "807 casos; propia rechaza toda clave/R degenerada; OpenSSL acepta 34/128 y 7/40",
           f"{total} casos; propia acepta {sum(v[1] for v in degenerados.values())} degeneradas; OpenSSL "
           f"{casos.get('clave_orden_pequeno', (0, 0, 0))[2]}/{casos.get('clave_orden_pequeno', (0,))[0]} y "
           f"{casos.get('clave_orden_mixto', (0, 0, 0))[2]}/{casos.get('clave_orden_mixto', (0,))[0]}",
           total == 807 and all(v[1] == 0 for v in degenerados.values())
           and casos.get("clave_orden_pequeno", (0, 0, 0))[2] == 34 and casos.get("clave_orden_mixto", (0, 0, 0))[2] == 7
           and casos.get("valida", (0, 0, 0))[1:] == (120, 120))
    for id_, carpeta, nombre, n in (("C10 corte de energía simulado", "14_corte_energia", "corte", 102),
                                    ("C11 fallos de escritura", "10_matriz_antes_despues", "fallos_es", 72)):
        obs = []
        for cod in ("det", "nodet"):
            d = json.loads((ev / carpeta / f"{nombre}_v0_5_{cod}.json").read_text())
            obs.append((cod, len(d), sum(bool(r["violaciones"]) for r in d)))
        afirma(id_, f"{n} escenarios por código, 0 violaciones", str(obs), all(x[1] == n and x[2] == 0 for x in obs))
    if coleccion is not None:
        col = coleccion.read_text().splitlines()
        tot = _ultimo(coleccion, r"(\d+) tests? collected")
        afirma("C12 pruebas recogidas", "449 (= C01)", tot.group(1) if tot else "?", bool(tot) and tot.group(1) == "449")
        integ = sum(x.startswith("integracion/") for x in col)
        afirma("C13 pruebas del ejecutor aislado", "32", str(integ), integ == 32)
        ids = {int(n) for x in col if x.startswith("cruzada/") for n in re.findall(r"X(\d+)", x.split("::", 1)[-1])}
        en_comentarios = {int(n) for f in (paq / "pruebas/cruzada").glob("test_*.py") for x in f.read_text().splitlines()
                          if x.startswith("# ----------") for n in re.findall(r"X(\d+)", x)} - ids
        faltan = sorted(set(range(1, 27)) - ids - en_comentarios)
        afirma("C14 escenarios cruzados", "X1–X26", f"{len(ids)} en nombres de prueba + {sorted(en_comentarios)} solo en "
               f"comentarios; faltan {faltan}", not faltan,
               "X10 y X17 no existen en ninguna versión (v0.3–v0.5): la numeración salta. Imprecisión de documentación "
               "(D-3): son 24 escenarios, no 26")
    v04 = (paq / "pruebas/p1/test_p1_v04.py").read_text()
    m = re.search(r"assert len\(combinaciones\) == ([\d *]+)\n", v04)
    n720 = math.prod(int(x) for x in m.group(1).split("*")) if m else None
    afirma("C15 oráculo P1 (estados)", "720 combinaciones", str(n720), n720 == 720)
    ejes = _tuplas(paq / "pruebas/p1/test_p1_v05.py")
    n80 = ejes.get("DECL", 0) * ejes.get("RESERVA", 0) * ejes.get("CORRUPCION", 0)
    n210 = ejes.get("VIA", 0) * ejes.get("REPRO_DECL", 0) * ejes.get("RESERVA_REPRO", 0) * ejes.get("CONTENIDO", 0)
    afirma("C16 oráculo P1 (recibos ligados)", "80 combinaciones", f"{n80} = DECL×RESERVA×CORRUPCION", n80 == 80)
    afirma("C17 oráculo P1 (reproducción)", "210 combinaciones", f"{n210} = VIA×REPRO_DECL×RESERVA_REPRO×CONTENIDO",
           n210 == 210)
    afirma("C18 fuzzing P1", "300 mutaciones aleatorias", "range(300)" if "for i in range(300):" in
           (paq / "pruebas/p1/test_p1_v05.py").read_text() else "?",
           "for i in range(300):" in (paq / "pruebas/p1/test_p1_v05.py").read_text())
    p4 = (paq / "pruebas/p4/test_p4_v05.py").read_text()
    ok = "for i in range(60):" in p4 and '@pytest.mark.parametrize("codigo", ["det", "nodet"])' in p4
    afirma("C19 mutaciones aleatorias P4", "120", "60 casos × 2 códigos" if ok else "?", ok)
    t27 = (ev / "27_regresion_suite_v0_4_sin_modificar_contra_v0_5.txt").read_text()
    m = _ultimo(ev / "27_regresion_suite_v0_4_sin_modificar_contra_v0_5.txt", r"(\d+) failed, (\d+) passed")
    nf = len((ev / "27_regresion_suite_v0_4_fallidas.txt").read_text().splitlines())
    afirma("C20 suite de v0.4 sin modificar", "350 pasan, 9 fallan (deliberadas)", f"{m and m.group(0)}; lista: {nf}",
           bool(m) and m.group(1) == "9" and m.group(2) == "350" and nf == 9 and bool(t27))
    m = _ultimo(ev / "25_regresion_p4_v0_3_sin_modificar_contra_v0_5.txt", r"(\d+) passed")
    afirma("C21 suite P4 de v0.3 sin modificar", "112 pasan", m.group(0) if m else "?", bool(m) and m.group(1) == "112")
    t60 = (ev / "60_parches_comprobacion.txt").read_text()
    ok60 = t60.count("de los 7 parches en orden: OK") == 2 and t60.count("(código de salida 0)") == 2
    afirma("C22 parches 0001–0007", "aplican y la suite pasa en HEAD y origin exportados",
           f"{t60.count('de los 7 parches en orden: OK')} aplicaciones OK; "
           f"{t60.count('(código de salida 0)')} suites OK", ok60)
    e80 = json.loads((ev / "80_estado_real_de_T.json").read_text())
    afirma("C23 estado real de T", "INCONCLUSO (SIN_REFERENCIA_INDEPENDIENTE); P2 NO_CANDIDATA",
           f"{e80['estado_p1']} {e80['motivos_p1']}; P2 {e80['estado_p2']['avance']}",
           e80["estado_p1"] == "INCONCLUSO" and e80["motivos_p1"] == ["SIN_REFERENCIA_INDEPENDIENTE"]
           and e80["estado_p2"]["avance"] == "NO_CANDIDATA" and e80["archivos_leidos_sin_cambios"] is True)
    t98 = (ev / "98_integridad_final.txt").read_text()
    afirma("C24 entregas anteriores", "5 de 5 OK", f"{t98.count(': OK')} OK", t98.count(": OK") == 5 and "FAILED" not in t98)
    g90, g91 = (ev / "90_estado_git_antes.txt").read_bytes(), (ev / "91_estado_git_despues.txt").read_bytes()
    afirma("C25 estado de git", "antes == después; huella 87b9585d…", g91.decode().splitlines()[-1][:16] + "…",
           g90 == g91 and g91.decode().splitlines()[-1].startswith("87b9585d"))
    t97 = (ev / "97_paquete_intacto.txt").read_text() if (ev / "97_paquete_intacto.txt").exists() else ""
    afirma("C26 paquete intacto (etapa 13)", "sin cambios ni archivos nuevos", t97.strip().splitlines()[-1] if t97 else "?",
           "paquete intacto" in t97, "Límite D-1: la etapa 13 de v0.5 no mira enlaces ni directorios vacíos")
    t12 = (ev / "12_ruff.txt").read_text()
    afirma("C27 estilo (ruff)", "sin hallazgos", t12.strip().splitlines()[0], "All checks passed!" in t12)

    malas = [f for f in filas if not f[3]]
    print("| Afirmación | Declarado | Observado | ¿Coincide? | Nota |\n|---|---|---|---|---|")
    for id_, d, o, ok, nota in filas:
        print(f"| {id_} | {d} | {o} | {'sí' if ok else '**NO**'} | {nota} |")
    print(f"\n{len(filas) - len(malas)} de {len(filas)} afirmaciones coinciden con lo observable")
    return 1 if malas else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]) if len(sys.argv) > 3 else None))
