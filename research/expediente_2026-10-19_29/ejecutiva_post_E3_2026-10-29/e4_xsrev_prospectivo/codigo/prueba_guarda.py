"""Prueba de la guarda de rutas contra las rutas protegidas REALES (solo realpath y stat; no lee su contenido) y contra
alias creados en una carpeta temporal propia: enlace simbólico a una copia real, ruta relativa con «..», carpeta sintética con
estructura de series, y enlace duro a un archivo protegido SINTÉTICO (no a uno real: un enlace duro cambiaría el ctime del
inodo congelado). También comprueba que una
carpeta de datos nueva y vacía se acepta. Uso: python3 -I -B prueba_guarda.py <PROTEGIDOS.tsv> <dir_tmp_vacio> <salida.json>"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guarda_rutas as G  # noqa: E402

TSV, TMP, SAL = sys.argv[1:4]
prot = G.cargar_protegidos(TSV)
os.makedirs(TMP, exist_ok=False)
prot_sint = os.path.join(TMP, "orquestador_protegido_sintetico.py")
open(prot_sint, "w").write("# archivo sintético protegido solo para esta prueba\n")
prot = prot + [prot_sint]
serie_real = [p for p in prot if p.endswith("calidad/series")][0]
orq = [p for p in prot if p.endswith("ejecutar_E3_v2.py")][0]
os.symlink(serie_real, os.path.join(TMP, "atajo_series"))
os.symlink(os.path.dirname(serie_real), os.path.join(TMP, "atajo_calidad"))
duro = os.path.join(TMP, "copia_dura_v2.py")
try:
    os.link(prot_sint, duro)  # enlace duro al protegido SINTÉTICO
    hay_duro = True
except OSError:
    hay_duro = False
os.makedirs(os.path.join(TMP, "sint", "resultados", "calidad", "series"))
os.makedirs(os.path.join(TMP, "datos_nuevos_e4"))
relativa = os.path.relpath(serie_real, TMP)

casos = {"serie_real_directa": serie_real, "subarchivo_de_serie_real": os.path.join(serie_real, "BTCUSDT.npz"),
         "enlace_simbolico_a_serie": os.path.join(TMP, "atajo_series"), "enlace_a_carpeta_padre": os.path.join(TMP, "atajo_calidad"),
         "ruta_relativa_con_puntos": os.path.join(TMP, relativa), "orquestador_v2": orq,
         "estructura_series_sintetica": os.path.join(TMP, "sint"), "carpeta_datos_nueva": os.path.join(TMP, "datos_nuevos_e4")}
if hay_duro:
    casos["enlace_duro_a_orquestador"] = duro
res = {}
for k, ruta in casos.items():
    try:
        G.verificar(ruta, prot)
        res[k] = "ACEPTADA"
    except G.RutaProtegida as e:
        res[k] = f"RECHAZADA {str(e)[:120]}"

esperado = {k: ("ACEPTADA" if k == "carpeta_datos_nueva" else "RECHAZADA") for k in casos}
ok = all(res[k].startswith(esperado[k]) for k in casos)
json.dump({"resultados": res, "ok": ok, "enlace_duro_probado": hay_duro}, open(SAL, "w"), ensure_ascii=False, indent=1)
print(json.dumps({"ok": ok, "enlace_duro_probado": hay_duro, **{k: v.split(" ")[0] for k, v in res.items()}}, ensure_ascii=False))
