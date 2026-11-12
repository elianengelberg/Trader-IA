"""Clasifica la paridad del árbol final con E1 y con la integración anterior (E17).
Uso: python comparar_paridad_v2.py <final_venvA.json> <final_entornoE1.json> <dir_E1> <E17_ci.json> <E17_e1.json> <salida.md>
Categorías: Igualdad verificada · Diferencia explicada · Diferencia no explicada · Imposible de verificar por falta de referencia."""
import hashlib
import json
import re
import sys
from pathlib import Path

fa, fe, e1dir, e17ci, e17e1, salida = sys.argv[1:7]
A, B = json.load(open(fa)), json.load(open(fe))
E1 = Path(e1dir)
rt_e1 = json.load(open(E1 / "resultados/real/operaciones_por_configuracion.json"))
res_e1 = json.load(open(E1 / "resultados/real/resultado_e1.json"))
ref17 = {"ci": json.load(open(e17ci)), "e1": json.load(open(e17e1))}
IG, DE, DN, IM = "Igualdad verificada", "Diferencia explicada", "Diferencia no explicada", "Imposible de verificar por falta de referencia"
filas, no_explicadas = [], 0


def fila(conf, que, cat, detalle):
    global no_explicadas
    no_explicadas += cat == DN
    filas.append(f"| {conf} | {que} | **{cat}** | {detalle} |")


def js(x):
    return json.dumps(x, sort_keys=True)


meta_e1 = res_e1["meta"]["datos"]
for conf in ("P1", "P2", "P3", "S1"):
    a, b = A["configuraciones"][conf], B["configuraciones"][conf]
    # 1. datos de entrada
    claves = ("n_archivos", "sha256_lista_archivos", "velas", "primera_vela", "ultima_vela", "faltantes", "horas_en_conflicto_excluidas")
    iguales = all(js(a["datos_meta"].get(k)) == js(meta_e1.get(k)) for k in claves) and a["barras_meta"] == meta_e1["velas"]
    fila(conf, "Huella de los datos de entrada (lista de 96 archivos con SHA-256 verificados contra .CHECKSUM, velas, extremos, huecos, horas excluidas)",
         IG if iguales else DN, f"lista `{a['datos_meta']['sha256_lista_archivos'][:12]}…`, {a['barras_meta']} velas; E1 `{meta_e1['sha256_lista_archivos'][:12]}…`, {meta_e1['velas']}")
    # 2. operaciones, marcas de tiempo y costes por operación
    for nombre, r in (("entorno CI", a), ("entorno E1", b)):
        ig = js(r["rt"]) == js(rt_e1[conf])
        fila(conf, f"Round trips completos: entrada/salida (marcas de tiempo), dirección, nocional, neto, bruto, **comisiones**, barras, razón, confianza, régimen, piezas — {nombre}",
             IG if ig else DN, f"{len(r['rt'])} de {len(rt_e1[conf])} idénticos como JSON" if ig else f"{len(r['rt'])} contra {len(rt_e1[conf])}: DIFERENTES")
    # 3. métricas de la curva registradas por E1
    m_e1 = res_e1["configuraciones"][conf]["metricas_curva"]
    for nombre, r in (("entorno CI", a), ("entorno E1", b)):
        dif = {k: (r["metricas"].get(k), v) for k, v in m_e1.items() if r["metricas"].get(k) != v}
        fila(conf, f"Métricas de la curva de equity registradas por E1 ({', '.join(m_e1)}) — {nombre}",
             IG if not dif else DN, "7 de 7 idénticas (igualdad exacta de float)" if not dif else f"distintas: {dif}")
    # 4. contadores de decisiones registrados por E1
    d_e1 = res_e1["configuraciones"][conf]["decisiones"]
    for nombre, r in (("entorno CI", a), ("entorno E1", b)):
        dif = {k: (r["decisiones"].get(k), v) for k, v in d_e1.items() if r["decisiones"].get(k) != v}
        if not dif:
            fila(conf, f"Contadores de decisiones y señales registrados por E1 ({', '.join(d_e1)}) — {nombre}", IG, "8 de 8 idénticos")
        else:
            fila(conf, f"Contadores de decisiones y señales registrados por E1 — {nombre}", DN, f"distintos: {dif}")
    # 5. registro completo de decisiones, curva de equity completa y detalle de cada operación: E1 no los registró
    fila(conf, "Registro completo de decisiones por barra, curva de equity punto a punto y detalle de cada `ClosedTrade` frente a E1", IM,
         "E1 no los registró; ver la fila siguiente (entre entornos y frente a la integración anterior)")
    eq_env = all(a[k] == b[k] for k in ("h_operaciones_completas", "h_equity", "h_metricas", "h_decisiones", "h_registro_de_decisiones"))
    fila(conf, "Las mismas salidas completas entre los dos entornos de hoy (operaciones, equity, métricas, decisiones, registro de decisiones)",
         IG if eq_env else DN, f"equity `{a['h_equity'][:12]}…`, registro `{a['h_registro_de_decisiones'][:12]}…`")
    for env, r in (("ci", a), ("e1", b)):
        p = ref17[env]["configuraciones"][conf]
        ig = all(r[k] == p[k] for k in ("h_operaciones_completas", "h_equity", "h_metricas", "h_decisiones"))
        fila(conf, f"Salidas completas frente a la integración anterior (E17, motor `85965ec5…`, entorno {env.upper()}): ¿la trazabilidad cambió algún número?",
             IG if ig else DN, "operaciones, equity, métricas y decisiones con la misma huella" if ig else "DISTINTAS")
    # 6. parámetros efectivos
    fila(conf, "Parámetros efectivos (configuración, universo, escenario, semilla)", IG if A["sha256_e1_comun"] == "b61cab579c86457e7b1d0dd1e27f16fe8dfe06db62fcb4c25aa058bc1641f882" else DN,
         f"construidos por el mismo `e1_comun.py` de la corrida evaluada de E1 (`{A['sha256_e1_comun'][:12]}…` = huella de la adenda 2 de E1); "
         f"ningún parche toca `BacktestConfig`. Digest de hoy `{a['digest_config'][:12]}…` (E1 no registró el digest)")
    # 7. huella del motor
    fila(conf, "Huella del motor", DE,
         f"E1 corrió `MotorE1` (subclase con sus propias correcciones D1–D2 y diagnóstico D3) sobre `engine.py` `547109460bb5…` (72ffae5); "
         f"hoy corre el `BacktestEngine` integrado, sin subclases (`{A['sha256_engine'][:12]}…`, versión {a['condiciones']['engine_version']}, "
         f"huella `{a['condiciones']['engine_fingerprint'][:12]}…`). E1 no registró huella de motor: la equivalencia se apoya en las salidas, no en el código")

# 8. dependencias
req = (E1 / "entorno/requisitos_con_hash.txt").read_text()
fijadas = dict(re.findall(r"^([A-Za-z0-9_.\-]+)==([^\s\\]+)", req, re.M))
fijadas = {k.lower().replace("_", "-"): v for k, v in fijadas.items()}
for nombre, R in (("entorno E1", B), ("entorno CI (restricciones ci-py311)", A)):
    dif = {k: (v, fijadas.get(k.replace("_", "-"))) for k, v in R["versiones"].items() if fijadas.get(k.replace("_", "-")) != v}
    cat = IG if not dif else DE
    det = f"{R['versiones']} · Python {R['python']}" + ("" if not dif else f" · distintas de los requisitos con hash de E1: {dif}; las salidas son idénticas en ambos entornos (filas anteriores)")
    fila("todas", f"Versiones de dependencias — {nombre}", cat, det)

with open(salida, "w") as f:
    f.write("# Paridad del árbol final con E1 (P1, P2, P3, S1)\n\n")
    f.write(f"Motor: `{A['motor']}` (`{A['sha256_engine']}`). Registros de E1: `operaciones_por_configuracion.json` "
            f"`{hashlib.sha256((E1 / 'resultados/real/operaciones_por_configuracion.json').read_bytes()).hexdigest()}`, "
            f"`resultado_e1.json` `{hashlib.sha256((E1 / 'resultados/real/resultado_e1.json').read_bytes()).hexdigest()}`.\n\n")
    f.write("| Config. | Comparación | Categoría | Detalle |\n|---|---|---|---|\n" + "\n".join(filas) + "\n\n")
    f.write(f"**Diferencias no explicadas: {no_explicadas}.**\n")
print("\n".join(filas))
print("NO EXPLICADAS:", no_explicadas)
sys.exit(1 if no_explicadas else 0)
