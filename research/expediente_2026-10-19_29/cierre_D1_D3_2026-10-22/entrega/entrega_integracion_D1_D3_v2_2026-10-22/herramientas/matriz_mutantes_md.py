"""Arma MATRIZ_MUTANTES.md a partir de los JSON de los mutantes D1–D3 y de trazabilidad y de la corrida contra el original.
Uso: python matriz_mutantes_md.py <D_mutantes.json> <C_mutantes.json> <pruebas_contra_original.txt> <sha_prueba_d1d3> <sha_prueba_traza> <salida.md>"""
import json
import re
import sys

dj, cj, orig, sha_d, sha_c, salida = sys.argv[1:7]
D, Cm = json.load(open(dj)), json.load(open(cj))
orig_txt = open(orig).read()
orig_fallan = sorted(set(re.findall(r"^FAILED \S+::(\S+)", orig_txt, re.M)))
DEFECTO = {
    "M1_D1_salida_id_sin_barra": "D1 salidas: el cierre reintentado reutiliza su id y se suprime como duplicado",
    "M2_D1_stop_id_sin_colocacion": "D1 stops: el stop recolocado reutiliza su id y se suprime como duplicado",
    "M3_D2_sin_comparar_nivel": "D2: el stop del libro no sigue los movimientos de nivel (solo compara tamaño)",
    "M4_D3_sin_cancelar_resto_al_salir": "D3 capa 1: el resto de la entrada sigue en el libro mientras el cierre trabaja",
    "M5_D3_sin_cancelar_resto_en_plano": "D3 capa 2: el resto viejo de una entrada se llena en plano y abre una pierna sin señal",
    "M6_D3_sin_red_de_seguridad": "D3 capa 3: un cierre terminado con posición restante deja la pierna esperando para siempre",
    "M7_sin_aviso_de_pierna_sin_stop": "Fallar ruidosamente: barras con pierna y sin nivel de stop no se informan",
    "M8_D3_sin_ninguna_capa": "D3 completo sin ninguna de sus tres capas",
    "M9_D2_recoloca_el_stop_en_cada_barra": "D2 sin control: recoloca el stop vivo en cada barra aunque nada se movió",
    "M10_cierre_sin_reduce_only": "El cierre deja de ser reduce-only",
}


def asercion(motivos, prueba):
    for m in motivos:
        if m.startswith("E ") and "Error" in m:
            return m[2:].strip()[:170].replace("|", "/")
    return "—"


with open(salida, "w") as f:
    f.write("# Matriz de mutantes (archivos de prueba definitivos)\n\n")
    f.write(f"- D1–D3: `tests/unit/test_backtest_order_hygiene.py`, SHA-256 `{sha_d}` (8 pruebas).\n")
    f.write(f"- Trazabilidad: `tests/integration/test_backtest_provenance.py`, SHA-256 `{sha_c}` (12 pruebas).\n")
    f.write(f"- Motor original (`72ffae5`, sin parche): con el archivo D1–D3 definitivo fallan **{len(orig_fallan)} de 8**, todas por `AssertionError` "
            f"(`evidencia/D_pruebas_finales_contra_orig_con_pruebas.txt`). Con el árbol integrado pasan 8 de 8.\n\n")
    f.write("## D1–D3 (mutantes sobre el árbol integrado)\n\n| Mutante | Defecto que introduce | Pruebas que lo detectan | Aserción responsable (primera) | Con el motor original | Con la integración |\n|---|---|---|---|---|---|\n")
    for n, v in D["mutantes"].items():
        det = sorted(k for k, s in v["resultados"].items() if s != "PASSED")
        en_orig = "fallan también: " + ", ".join(f"`{x}`" for x in det if x in orig_fallan) if det else "—"
        f.write(f"| {n} | {DEFECTO.get(n, '')} | {', '.join(f'`{x}`' for x in det) or '**NINGUNA (vivo)**'} | `{asercion(v['motivos'], det)}` | {en_orig} | 8/8 pasan |\n")
    f.write("\n**M10** se detecta, pero no por una invariante de comportamiento. Los proveedores de prueba reconocen los cierres por `reduce_only`; sin él, "
            "los escenarios dejan de ejercitar cierres rechazados o IOC y fallan las aserciones de cobertura del escenario. Con cierres dimensionados a la "
            "pierna, la invariante `d3_flipped` no se dispara: `reduce_only` en el cierre es una defensa en profundidad que estos escenarios no pueden "
            "distinguir por comportamiento (riesgo residual R-M10).\n\n")
    f.write("## Trazabilidad (mutantes sobre el árbol integrado)\n\n| Mutante | Pruebas que lo detectan | Aserción responsable (primera) | Estado |\n|---|---|---|---|\n")
    for n, v in Cm["mutantes"].items():
        det = sorted(k for k, s in v["resultados"].items() if s != "PASSED")
        estado = "equivalente (justificado abajo)" if n in Cm.get("equivalentes", {}) else ("detectado" if det else "**VIVO**")
        f.write(f"| {n} | {', '.join(f'`{x}`' for x in det) or '—'} | `{asercion(v['motivos'], det)}` | {estado} |\n")
    for n, why in Cm.get("equivalentes", {}).items():
        f.write(f"\n**{n} (equivalente):** {why}\n")
    f.write("\nCon el motor original no existen las funciones de trazabilidad: las 12 pruebas no pueden importarse. Su efecto sobre el original se "
            "demuestra aparte, por comportamiento (`evidencia/C_run_id_*.json`): la base y el motor con D1–D3 dan el **mismo** `run_id` "
            "(`bt_DJZPATCEBZ0B0DP393XP3W1D`) con resultados distintos, y 400 y 350 barras del mismo dataset también lo comparten.\n")
    vivos_d = [n for n, v in D["mutantes"].items() if all(s == "PASSED" for s in v["resultados"].values())]
    f.write(f"\n**Vivos: D1–D3 {len(vivos_d)} de {len(D['mutantes'])}; trazabilidad {len(Cm['vivos'])} de {len(Cm['mutantes'])} "
            f"(con {len(Cm.get('equivalentes', {}))} equivalente).**\n")
print(open(salida).read()[-1200:])
