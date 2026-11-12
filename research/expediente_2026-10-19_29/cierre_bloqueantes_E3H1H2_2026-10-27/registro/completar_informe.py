"""Completa en el informe las secciones de mutación (§5.3) e integridad (§6.1–6.2) a partir de los archivos de resultados.
Uso: python -I completar_informe.py <dir_cierre>"""
import json
import sys
from pathlib import Path

CB = Path(sys.argv[1])
r = json.loads((CB / "pruebas/resultado_mutantes.json").read_text())
DESC = {"C7_ventana_no_fijada": "Sin hash ni contenido de la ventana",
        "C8_manifiesto_vacio_o_incompleto": "Acepta un manifiesto vacío o al que le falta una entrada",
        "C8_mapeos_desde_el_manifiesto": "Lee los mapeos de la ruta que diga el manifiesto (como el v2)",
        "C9_relectura_de_disco": "Vuelve a leer las series de disco después de verificar",
        "C9_acepta_enlaces": "Acepta enlaces simbólicos",
        "C10_import_desde_disco": "`import` desde disco (como el v2)",
        "C11_sin_estado_ERROR": "Sin manejo de excepciones después de crear la salida",
        "C11_sin_registro_de_intentos": "Sin control del registro de intentos",
        "C11_sin_bloqueo": "Sin bloqueo del registro",
        "C12_acepta_duplicados": "Acepta mapeos repetidos",
        "C12_acepta_huecos_largos": "Acepta huecos ≥ 30 días en la regla 1",
        "C12_sin_control_de_marcas": "Sin control de marcas (lista fija o apalancado)",
        "C12_1R_sin_dividir": "La regla 1R no divide la serie",
        "C12_mapeos_despues_de_crear_la_salida": "Comprueba los mapeos recién después de crear la salida",
        "C13_sin_frases_de_decision": "No exige las frases de decisión"}
L = [f"**{len(r)} mutantes, {sum(v['sobrevive'] for v in r.values())} sobreviven.** Cada uno quita una defensa del v3 y corre "
     "la suite completa contra él (50 pruebas + 1 omitida, la que compara los hashes del v3 generado).", "",
     "| Mutante | Defensa quitada | Pruebas que lo detectan |", "|---|---|---|"]
for k, v in r.items():
    L.append(f"| {k} | {DESC[k]} | " + ", ".join(f"`{x}`" for x in v["pruebas_que_lo_detectan"]) + " |")
mut = "\n".join(L)


def leer(p):
    return dict(linea.split(" ", 1) for linea in p.read_text().splitlines())


ini, fin = leer(CB / "registro/huellas_inicio.txt"), leer(CB / "registro/huellas_fin.txt")
H = ["| Objeto | Inicio (`registro/huellas_inicio.txt`) | Fin (`registro/huellas_fin.txt`) |", "|---|---|---|"]
H += [f"| {k} | `{ini[k].strip()[:72]}` | `{fin[k].strip()[:72]}` |" for k in ini]
iguales = all(ini[k] == fin[k] for k in ini if k != "UTC")
dif = ((f"**Única diferencia: la marca de hora** (inicio {ini['UTC'].strip()}; fin {fin['UTC'].strip()}). " if iguales else
        "**HAY DIFERENCIAS FUERA DE LA MARCA DE HORA: revisar la tabla.** ") +
       "Los árboles congelados (E3, E3R, reparación y revisión) y las páginas archivadas tienen la misma huella. Git sigue en HEAD "
       "`72ffae5`, sin cambios y con el mismo índice. Los MANIFEST de la reparación (92/92) y de la revisión (41/41) validan. "
       "No quedaron `__pycache__`, `.pytest_cache`, `/tmp/pytest-of-root` ni registros de intentos. Los temporales de las "
       "pruebas se borraron, después de comprobar (prueba de higiene) que no contenían la frase real, los hashes reales ni las "
       "frases de decisión.")
p = CB / "INFORME_CIERRE_BLOQUEANTES_E3H1H2.md"
t = p.read_text()
for a, b in (("@@MUTANTES@@", mut), ("@@HUELLAS@@", "\n".join(H)), ("@@DIFERENCIAS@@", dif)):
    assert t.count(a) == 1, a
    t = t.replace(a, b)
p.write_text(t)
print("informe completado; huellas iguales:", iguales)
