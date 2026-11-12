"""Tabla de mutación en Markdown, leída de los JSON de exp_mutacion.py / exp_mutacion_lote2.py (sin cifras a mano).
Uso: python -I tabla_mutacion.py <antes.json> <despues.json> [<lote2.json>]"""
import json
import sys
from pathlib import Path


def carga(ruta):
    d = json.loads(Path(ruta).read_text())
    return len(d["pruebas"]), {m["id"]: m for m in d["mutantes"]}


def prueba(m):
    falla = m.get("primera_falla", "")
    return falla.split("::")[-1][:70] if "::" in falla else ""


n_antes, antes = carga(sys.argv[1])
n_despues, despues = carga(sys.argv[2])
print(f"| Id | Defecto simulado | T15 ({n_antes} archivos) | T21 ({n_despues} archivos) | Prueba que lo detecta en T21 |")
print("|---|---|---|---|---|")
for mid in sorted(set(antes) | set(despues)):
    a, b = antes.get(mid, {}), despues.get(mid, {})
    print(f"| {mid} | {(a or b)['descripcion']} | {a.get('resultado', '—')} | {b.get('resultado', '—')} | `{prueba(b)}` |")
muertos = lambda t: sum(m.get("resultado") == "MUERTO" for m in t.values())  # noqa: E731
print(f"\n**Muertos:** T15 {muertos(antes)} de {len(antes)} · T21 {muertos(despues)} de {len(despues)}.")
if len(sys.argv) > 3:
    n2, lote2 = carga(sys.argv[3])
    print(f"\n| Id | Defecto simulado (lote 2, suite completa) | T21 | Primera prueba que falla | Segundos |")
    print("|---|---|---|---|---|")
    for mid, m in sorted(lote2.items()):
        print(f"| {mid} | {m['descripcion']} | {m.get('resultado')} | `{prueba(m)}` | {m.get('segundos', '—')} |")
    print(f"\n**Lote 2:** {muertos(lote2)} muertos de {len(lote2)}.")
