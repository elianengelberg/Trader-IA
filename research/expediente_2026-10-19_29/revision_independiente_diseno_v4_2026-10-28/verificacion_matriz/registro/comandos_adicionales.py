"""Comprobaciones adicionales (solo JSON/texto; ningún .npz/zip; ningún precio). Ejecutar desde el scratchpad con: python -B -I comandos_adicionales.py"""
import json, datetime as dt, os, re, collections
E3 = "experimentos/E3_seleccion_posicion_2026-10-19/ejecucion_E3/"; E3R = "experimentos/E3R_desbloqueo_2026-10-26/"; REP = "reparacion_E3H1H2_2026-10-26/"
J = lambda p: json.load(open(p))
print("## 1. P0 oficial y P0 R1prima (E3R/P0_resultado*.json)")
for fn in ("P0_resultado.json", "P0_resultado_R1prima.json"):
    d = J(E3R + fn); print(fn, {k: d[k] for k in ("inicio_H", "semanas_H", "evaluables_H", "veredicto", "componentes")})
    print("  fallas:", [(f["par"], f["E"], f["categoria"], f["en_alcance"]) for f in d["fallas_2_3"]])
print("## 2. marcas de modificación (segundos) de los archivos de la cronología")
for fn in ("CONGELACION_ADENDA_R.txt", "p0_auditoria_interna.py", "P0_resultado.json", "p0b_verificar_suspension.py", "P0d_potencia_H1_segun_ventana.txt",
           "CORRECCION_R1prima_alcance_por_clase.md", "CONGELACION_R1prima.txt", "p0_auditoria_interna_R1prima.py", "REGISTRO_P0.txt", "P0_resultado_R1prima.json"):
    print(dt.datetime.fromtimestamp(os.stat(E3R + fn).st_mtime, dt.timezone.utc).strftime("%H:%M:%S.%f")[:-3], fn)
print("## 3. listas fijas por lunes (F3)")
L = {x["lunes"]: x for x in J(E3 + "resultados/estructural/listas_fijas_por_lunes.json")}
for k in ("2023-04-24", "2023-05-08"): print(k, "apalancados:", L[k]["apalancados"])
print("nº de apalancados por lunes: mín/máx en los 439 lunes:", min(len(x["apalancados"]) for x in L.values()), max(len(x["apalancados"]) for x in L.values()))
for lst in ("lista_fija", "apalancados", "baja_volatilidad_o_duplicado", "elegibles"):
    print("lunes en que algún símbolo BKRW* figura en", lst, ":", sum(1 for x in L.values() if any(s.startswith("BKRW") for s in x[lst])))
print("## 4. vs3 / acciones (REP/segunda_pasada/resoluciones_manuales.json)")
R = J(REP + "segunda_pasada/resoluciones_manuales.json")
print("claves eventos:", len(R["eventos"]), "| sin_fecha:", len(R["sin_fecha"]), "| acciones:", dict(collections.Counter(v["accion"] for v in R["eventos"].values())))
print("vs3 muestra_pasada1==True:", [k for k, v in R["vs3"].items() if v["muestra_pasada1"]])
for k, v in R["vs3"].items():
    if v["resultado"] in ("fecha_corregida", "descartar"): print(" ", k, "muestra_pasada1=", v["muestra_pasada1"], "resultado=", v["resultado"], "E_texto=", v["E_texto"])
print("## 5. omitidos")
p1 = {e["par"] for e in J(E3 + "resultados/conciliacion_pasada1/eventos.json")}; p2 = {e["par"] for e in J(REP + "segunda_pasada/salida_pasada2/eventos.json")}
usdt = set(J(E3 + "datos_vision/listados/simbolos_usdt.json"))
for p in ("TRXUPUSDT", "LINKDOWNUSDT", "GTOUSDT", "BTCSTUSDT", "SRMUSDT", "TRIBEUSDT", "KEYUSDT", "BKRWUSDT"):
    print(p, "en panel:", p in usdt, "| evento pasada1:", p in p1, "| evento pasada2:", p in p2)
W = J(REP + "ventana_A/ventana_A_pasada2.json"); print("fallas ventana A (pasada2):", [(f["par"], f["E"], f["omitido_por_la_extraccion"]) for f in W["fallas_2_3"]], "| inicio", W["inicio_H"], "| semanas", W["semanas_H"])
print("2023 (pasada2, iv'):", W["por_anio_iv_prima"]["2023"]); print("2023 (P0 R1 literal):", J(E3R + "P0_resultado.json")["por_anio"]["2023"])
print("evidencia interna vs anuncio (P0 oficial, suma de años): en_alcance=%d ANUNCIO=%d SUSPENSION=%d COLA_CERO=%d" % tuple(
    sum(v[k] for v in J(E3R + "P0_resultado.json")["por_anio"].values()) for k in ("en_alcance", "ANUNCIO", "SUSPENSION", "COLA_CERO")))
print("## 6. aritmética de fechas")
d = lambda s: dt.date.fromisoformat(s)
for ini in ("2023-05-01", "2023-05-15", "2021-02-22", "2023-05-29", "2020-05-11"):
    print("lunes de", ini, "a 2026-05-18:", (d("2026-05-18") - d(ini)).days // 7 + 1)
print("GTO: último activo 2022-11-27 -> GFT 2023-09-22: diferencia", (d("2023-09-22") - d("2022-11-27")).days, "días; inactivos", (d("2023-09-22") - d("2022-11-27")).days - 1)
print("LUNA viejo: último activo 2022-05-12 -> LUNC primer día 2022-09-09: inactivos", (d("2022-09-09") - d("2022-05-12")).days - 1)
print("UST: último 2022-05-12 -> USTC primero 2023-03-10: inactivos", (d("2023-03-10") - d("2022-05-12")).days - 1)
A = {a["simbolo"]: a for a in J(E3 + "resultados/calidad/auditoria_por_simbolo.json")}
for s in ("GTOUSDT", "GFTUSDT", "LUNCUSDT", "USTUSDT", "USTCUSDT"): print(s, A[s]["episodios"])
print("congelación R 19:43:13.957 -> P0 19:44:40.432: segundos =", round(((dt.datetime(2026,10,26,19,44,40,432000) - dt.datetime(2026,10,26,19,43,13,957000)).total_seconds()), 1))
