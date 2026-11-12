"""Prueba exhaustiva del prototipo v4.1 sobre el modelo de disco (FsSombra). NO es E3; no lee datos.

Para cada escenario (EVALUADO, INVALIDO, ERROR_panel, ERROR_validez, ERROR_simulacion), cada operación n de la corrida sin
fallos y cada tipo de fallo aplicable (choque_antes, parcial, EIO, ENOSPC, fsync_miente), se corre el orquestador, se
reconstruye el estado tras el fallo (corte de energía, y también salida sin corte), se reconcilia dos veces y se comprueban:
  INV-1 sin repetición: si `puede_abrir` vuelve a dar True, el intento no llegó a leer datos;
  INV-2 decisión persistida: si una DECISION llegó al disco, la clase la refleja (EVALUADO/INVALIDO/TERMINAL_SIN_OBJETO);
  INV-3 decisión incierta: si se calculó una decisión y no llegó al disco, la clase es DECISION_ANUNCIADA_NO_PERSISTIDA
        o INCIERTO, nunca NO_DECIDIDO ni VACIO;
  INV-4 sin decisiones falsas: si no se calculó ninguna decisión, la clase no es de decisión;
  INV-5 objeto: EVALUADO/INVALIDO solo con el objeto presente, con hash igual al nombre y bytes iguales a los calculados;
  INV-6 reconciliación: no altera bytes previos del registro y la segunda corrida no agrega nada;
  INV-7 bloqueo: si el registro tiene la cadena rota, la clase es BLOQUEADO.
Además corre casos de corrupción explícita (byte cambiado, línea del medio borrada, hueco de ceros pegado a una línea
válida, cola partida de la propia reconciliación) y los mutantes M1, M2, M4, M5 y M8, que tienen que hacer fallar
alguna invariante (si no, la prueba sería circular).
Uso: python3 -I -B prueba_exhaustiva.py <salida.json>"""
import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proto_v4 as P  # noqa: E402

ESCENARIOS = ("EVALUADO", "INVALIDO", "ERROR_panel", "ERROR_validez", "ERROR_simulacion")
CLASES_DECISION = ("EVALUADO", "INVALIDO", "TERMINAL_SIN_OBJETO", "DECISION_ANUNCIADA_NO_PERSISTIDA")


def ops_sin_fallo(esc):
    fs, canal, verdad = P.FsSombra(), [], {}
    P.orquestar(fs, canal, esc, verdad)
    return fs.ops


def correr(esc, fallo, modo_post):
    """modo_post: corte | sin_corte | corte_canal_perdido (la salida estándar no llegó a ningún registro externo)."""
    fs, canal_proc, verdad = P.FsSombra(fallo), [], {}
    canal = canal_proc
    try:
        verdad["retorno"] = P.orquestar(fs, canal_proc, esc, verdad)
    except P.Choque:
        verdad["retorno"] = "CHOQUE"
    post = fs.tras_salida_sin_corte() if modo_post == "sin_corte" else fs.tras_corte()
    canal = [] if modo_post == "corte_canal_perdido" else canal_proc
    # ¿llegó la DECISION al disco? (verdad del modelo, no del lector)
    raw = post.leer(P.REG) if post.existe(P.REG) else b""
    decision_en_disco = None
    for tipo in ("EVALUADO", "INVALIDO"):
        if f'"tipo":"DECISION"'.encode() in raw and f'"datos":{{"sha_objeto":'.encode() in raw:
            pass
    st0 = P.leer_registro(raw)
    for e in st0["eventos"]:
        if e["tipo"] == "DECISION":
            decision_en_disco = e["datos"]["tipo"]
    if decision_en_disco is None and st0["estado"] != "OK":
        # la DECISION puede estar en el disco tras una cola cortada; se busca en todo el texto
        for tipo in ("EVALUADO", "INVALIDO"):
            if f'"tipo":"DECISION"'.encode() in raw and f'"tipo":"{tipo}"'.encode() in raw:
                decision_en_disco = tipo
    clase1, det1 = P.reconciliar(post, canal)
    raw1 = post.leer(P.REG) if post.existe(P.REG) else b""
    clase2, _ = P.reconciliar(post, canal)
    raw2 = post.leer(P.REG) if post.existe(P.REG) else b""
    st = P.leer_registro(raw2)
    reabre = P.puede_abrir(st, canal, "EVAL-SINTETICA", P.Almacen(post))
    fallas = []
    if reabre and verdad.get("datos_leidos"):
        fallas.append("INV-1" if modo_post != "corte_canal_perdido" else "INV-1(sin canal)")
    if decision_en_disco and not clase1.startswith((decision_en_disco, f"TERMINAL_SIN_OBJETO({decision_en_disco})", "BLOQUEADO")):
        fallas.append("INV-2")
    calc = verdad.get("decision_calculada")
    if calc and not decision_en_disco and not clase1.startswith(("DECISION_ANUNCIADA_NO_PERSISTIDA", "INCIERTO", "BLOQUEADO")):
        fallas.append("INV-3")
    if not calc and clase1.startswith(CLASES_DECISION):
        fallas.append("INV-4")
    if clase1 in ("EVALUADO", "INVALIDO"):
        objs = [n for n in post.listar(P.OBJ) if not n.startswith(".tmp-")]
        if len(objs) != 1 or P.sha(post.leer(f"{P.OBJ}/{objs[0]}")) != objs[0] or post.leer(f"{P.OBJ}/{objs[0]}") != verdad.get("objeto"):
            fallas.append("INV-5")
    if not raw1.startswith(raw) or raw2 != raw1 or clase2 != clase1:
        fallas.append("INV-6")
    if st0["estado"] == "CADENA_ROTA" and clase1 != "BLOQUEADO":
        fallas.append("INV-7")
    return {"escenario": esc, "fallo": fallo, "post": modo_post, "retorno": verdad["retorno"], "clase": clase1, "detalle": det1,
            "decision_calculada": calc, "decision_en_disco": decision_en_disco, "reabre": reabre, "fallas": fallas}


def matriz():
    filas = []
    for esc in ESCENARIOS:
        ops = ops_sin_fallo(esc)
        for n, tipo in enumerate(ops, 1):
            fallos = [("choque_antes", n, None), ("fsync_miente", n, None)]
            if tipo == "write":
                fallos += [("ENOSPC", n, None), ("parcial", n, 7), ("parcial", n, 60)]
            if tipo in ("fsync", "fsync_dir"):
                fallos += [("EIO", n, None)]
            for f, post in itertools.product(fallos, ("corte", "sin_corte", "corte_canal_perdido")):
                filas.append(correr(esc, f, post))
        filas.append(correr(esc, None, "corte"))
    return filas


def corrupciones():
    """Corrupción explícita de un registro completo (EVALUADO) ya escrito."""
    fs, canal, verdad = P.FsSombra(), [], {}
    P.orquestar(fs, canal, "EVALUADO", verdad)
    base = fs.leer(P.REG)
    lineas = [P.MARCA + x for x in base.split(P.MARCA) if x]
    casos = {
        "byte_cambiado_en_el_medio": base[:len(base) // 2] + bytes([base[len(base) // 2] ^ 1]) + base[len(base) // 2 + 1:],
        "linea_del_medio_borrada": b"".join(lineas[:2] + lineas[3:]),
        "hueco_de_ceros_pegado_a_linea_valida": b"".join(lineas[:4]) + b"\x00" * 40 + b"".join(lineas[4:]),
        "ultima_linea_cortada": base[:-15],
    }
    out = {}
    for nombre, b in casos.items():
        s = P.FsSombra()
        s.anexar(P.REG, b)
        for n in fs.listar(P.OBJ):
            s.crear_excl(f"{P.OBJ}/{n}", fs.leer(f"{P.OBJ}/{n}"))
        clase, det = P.reconciliar(s, canal)
        out[nombre] = {"estado_lector": P.leer_registro(b)["estado"], "clase": clase, "detalle": det}
    fe, ce, ve = P.FsSombra(), [], {}
    P.orquestar(fe, ce, "ERROR_validez", ve)
    be = fe.leer(P.REG)
    le = [P.MARCA + x for x in be.split(P.MARCA) if x]
    b = b"".join(le[:2]) + b"\x00" * 40 + b"".join(le[2:])
    s = P.FsSombra()
    s.anexar(P.REG, b)
    clase, det = P.reconciliar(s, ce)
    out["hueco_de_ceros_antes_del_ERROR"] = {"estado_lector": P.leer_registro(b)["estado"], "clase": clase, "detalle": det}
    # cola partida de la propia reconciliación: se corta el COLA_DESCARTADA a mitad y se vuelve a reconciliar
    s = P.FsSombra()
    s.anexar(P.REG, base[:-15])
    for n in fs.listar(P.OBJ):
        s.crear_excl(f"{P.OBJ}/{n}", fs.leer(f"{P.OBJ}/{n}"))
    st = P.leer_registro(s.leer(P.REG))
    ln = P.linea(len(st["eventos"]), st["cabeza"], "COLA_DESCARTADA", {"desde": st["fin_valido"], "longitud": len(st["cola"]), "sha": P.sha(st["cola"])})
    s.anexar(P.REG, ln[:20])  # la reconciliación murió a mitad de su escritura
    clase, det = P.reconciliar(s, canal)
    out["cola_partida_de_la_reconciliacion"] = {"estado_lector_final": P.leer_registro(s.leer(P.REG))["estado"], "clase": clase, "detalle": det}
    return out


def resumen(filas):
    malas = [f for f in filas if [x for x in f["fallas"] if x != "INV-1(sin canal)"]]
    limite = [f for f in filas if "INV-1(sin canal)" in f["fallas"]]
    por_clase = {}
    for f in filas:
        k = f["clase"].split("(")[0]
        por_clase[k] = por_clase.get(k, 0) + 1
    return {"casos": len(filas), "con_fallas": len(malas), "invariantes_violadas": sorted({i for f in malas for i in f["fallas"]}),
            "limite_INV1_sin_canal": len(limite), "ejemplo_limite": limite[:1],
            "por_clase": por_clase, "ejemplos_fallas": malas[:5]}


if __name__ == "__main__":
    salida = {"diseno_v4_1": resumen(matriz()), "corrupciones": corrupciones(), "mutantes": {}}
    for m in ("M1_abandonado", "M2_anuncio_tardio", "M4_puerta_sin_canal", "M5_cola_sin_marcador", "M8_reintento_tras_error"):
        P.MUTANTES.clear()
        P.MUTANTES.add(m)
        r = resumen(matriz())
        c = corrupciones() if m == "M5_cola_sin_marcador" else None
        salida["mutantes"][m] = {"casos": r["casos"], "con_fallas": r["con_fallas"], "invariantes_violadas": r["invariantes_violadas"],
                                 "detectado": r["con_fallas"] > 0 or bool(c and any(v.get("estado_lector") != "CADENA_ROTA" or v["clase"] != "BLOQUEADO"
                                                                                     for k, v in c.items() if k.startswith(("hueco", "byte", "linea_del")))),
                                 "corrupciones": c, "ejemplo": (r["ejemplos_fallas"] or [None])[0]}
    P.MUTANTES.clear()
    with open(sys.argv[1], "w") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1, default=str)
    d = salida["diseno_v4_1"]
    print(json.dumps({"diseno_v4_1": {k: d[k] for k in ("casos", "con_fallas", "invariantes_violadas", "limite_INV1_sin_canal", "por_clase")},
                      "corrupciones": {k: v["clase"] for k, v in salida["corrupciones"].items()},
                      "mutantes": {k: (v["detectado"], v["invariantes_violadas"]) for k, v in salida["mutantes"].items()}},
                     ensure_ascii=False, indent=1))
