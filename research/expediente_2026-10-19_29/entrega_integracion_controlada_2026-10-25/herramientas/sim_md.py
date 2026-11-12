"""Tablas de SIMULACION_INTEGRAL.md generadas desde los JSON de la simulación (Fase K), sin transcribir a mano.
Uso: python -I sim_md.py <dir_con_sim_{cand,base}_{7,8}.json> > tablas.md"""
import json
import sys
from pathlib import Path

d = Path(sys.argv[1])
corridas = {(arbol, s): json.loads((d / f"sim_{arbol}_{s}.json").read_text()) for arbol in ("cand", "base") for s in (7, 8)}
nombres = [e["escenario"] for e in corridas[("cand", 7)]["escenarios"]]


def esc(arbol, s, nombre):
    return next(e for e in corridas[(arbol, s)]["escenarios"] if e["escenario"] == nombre)


print("## Resumen por escenario, árbol y semilla\n")
print("| Escenario | Candidato s7 | Candidato s8 | Base s7 | Base s8 | Esperado incumplido en la base |")
print("|---|---|---|---|---|---|")
for n in nombres:
    v = [esc(a, s, n)["veredicto"] for a, s in (("cand", 7), ("cand", 8), ("base", 7), ("base", 8))]
    inc = sorted({x for s in (7, 8) for x in esc("base", s, n)["incumplidos"]})
    print(f"| {n} | {v[0]} | {v[1]} | {v[2]} | {v[3]} | {'; '.join(inc) or '—'} |")
tot = {k: sum(e["veredicto"] == "CUMPLE" for e in c["escenarios"]) for k, c in corridas.items()}
print(f"\nTotales CUMPLE: candidato {tot[('cand', 7)]}/15 y {tot[('cand', 8)]}/15; base {tot[('base', 7)]}/15 y {tot[('base', 8)]}/15. "
      f"Clones: candidato `{Path(corridas[('cand', 7)]['arbol']).name}`, base `{Path(corridas[('base', 7)]['arbol']).name}`.\n")


def contadores(c):
    keys = ("orders", "round_trips", "stops_placed", "unprotected_positions", "protective_stop_failures", "exits_rejected",
            "exits_stop", "exits_reversal", "exits_time", "unknown_order_states", "orders_lost")
    return ", ".join(f"{k}={c.get(k)}" for k in keys if c.get(k))


print("## Detalle por escenario (candidato, semilla 7; la base se indica donde difiere)\n")
for n in nombres:
    e = esc("cand", 7, n)
    o = e["observado"]
    print(f"### {n}\n")
    print(f"- **Esperado (fijado antes de correr):** {'; '.join(e['esperado'])}.")
    ini = o.get("inicial")
    if ini:
        print(f"- **Estado inicial:** `{ini['estado']}`, posición {ini['posicion']}, órdenes abiertas {ini['ordenes_abiertas'] or 'ninguna'}.")
    if o.get("transiciones"):
        print(f"- **Transiciones (hasta el cierre del escenario):** {' → '.join(t.split(':')[0] for t in o['transiciones'])}.")
    fin = o.get("final") or {}
    if fin:
        print(f"- **Estado final:** `{fin.get('estado')}`, posición {fin.get('posicion')}, órdenes abiertas "
              f"{fin.get('ordenes_abiertas') or 'ninguna'}, bloqueos {fin.get('bloqueos') or 'ninguno'}"
              f"{', last_error: «' + fin['last_error'][:160] + '»' if fin.get('last_error') else ''}.")
        print(f"- **Órdenes y contadores:** {contadores(fin.get('contadores', {})) or 'sin actividad'}.")
    if o.get("proteccion"):
        p = o["proteccion"]
        print(f"- **Protección medida en cada emparejamiento:** barras con posición {p['barras_con_posicion']}, barras sin protección "
              f"**{p['barras_sin_proteccion']}**, máximo de stops simultáneos {p['max_stops_simultaneos']}.")
    for k in ("tras_el_rechazo", "al_arrancar", "reconstruccion", "final_reconstruido", "proteccion_sesion_b"):
        if k in o:
            print(f"- **{k.replace('_', ' ')}:** `{json.dumps(o[k], ensure_ascii=False)}`.")
    if o.get("escrituras"):
        w = o["escrituras"]
        print(f"- **Escrituras:** programadas {w['scheduled']}, confirmadas {w['confirmed']}, fallidas {w['failed']}, en vuelo "
              f"{w['in_flight']}, completo={w['complete']}; `persistence_flushed`={o.get('persistence_flushed')}.")
    if o.get("filas"):
        f = o["filas"]
        print(f"- **Filas en la base:** órdenes {f['orders']}, fills {f['fills']}, incidentes {f['incidents']} "
              f"({', '.join(f['tipos_de_incidente']) or 'ninguno'}), corridas {f['runs']}.")
    otros = {k: v for k, v in o.items() if k not in ("inicial", "transiciones", "final", "proteccion", "escrituras", "filas",
                                                    "persistence_flushed", "tras_el_rechazo", "al_arrancar", "reconstruccion",
                                                    "final_reconstruido", "proteccion_sesion_b", "corriendo")}
    if otros:
        print(f"- **Otros observables:** `{json.dumps(otros, ensure_ascii=False, default=str)[:400]}`.")
    print(f"- **Errores:** {e['error'] or 'ninguno'}.")
    print(f"- **Inconsistencias (esperado no cumplido):** {', '.join(e['incumplidos']) or 'ninguna'}. **Veredicto: {e['veredicto']}.**")
    b = esc("base", 7, n)
    if b["veredicto"] != e["veredicto"]:
        bo = b["observado"]
        bf = bo.get("final") or {}
        extra = {k: bo[k] for k in ("tras_el_rechazo", "al_arrancar", "flush_dijo", "escrituras", "ambos_aceptados", "exito_descartado") if k in bo}
        print(f"- **Base (A+B+03):** {b['veredicto']}, incumple: {', '.join(b['incumplidos'])}. Estado final `{bf.get('estado')}`, "
              f"bloqueos {bf.get('bloqueos') or 'ninguno'}"
              f"{', protección: ' + json.dumps(bo['proteccion']) if bo.get('proteccion') else ''}"
              f"{', ' + json.dumps(extra, ensure_ascii=False) if extra else ''}.")
    print()
