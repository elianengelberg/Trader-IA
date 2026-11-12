"""Inventario línea por línea de un parche unificado (solo lee): por archivo y por fragmento, líneas agregadas y quitadas,
y cada línea agregada que toca un patrón de riesgo (red, credenciales, ejecución real, desactivación de pruebas, salida
de depuración, cambios de límites de tiempo). Uso: python inventario_diff.py <parche>... > inventario.md"""
import re
import sys
from pathlib import Path

RIESGO = {
    "red o servicios externos": re.compile(r"\b(requests|httpx|aiohttp|urllib|socket|websocket|binance\.com|api\.|https?://)", re.I),
    "credenciales": re.compile(r"(api_key|secret|password|token|private_key|\.env\b)", re.I),
    "ejecución real o activación": re.compile(r"(LiveActivationToken|use_testnet\s*=\s*False|real_money\s*=\s*True|TradingMode\.LIVE|validada_para_operar)"),
    "pruebas desactivadas": re.compile(r"(pytest\.skip|@pytest\.mark\.skip|xfail|or True\b|# noqa: PT|pragma: no cover)"),
    "depuración": re.compile(r"(\bprint\(|breakpoint\(|pdb\.set_trace)"),
    "límites de tiempo": re.compile(r"(timeout|sleep\(|deadline)", re.I),
}


def inventario(parche: Path) -> str:
    out = [f"## {parche.name}", "", "| Archivo | Fragmentos | + | − | Nuevo |", "|---|---|---|---|---|"]
    archivos, hallazgos, actual = {}, [], None
    for linea in parche.read_text(errors="replace").splitlines():
        if linea.startswith("diff --git "):
            actual = linea.split(" b/", 1)[1]
            archivos[actual] = {"frag": 0, "mas": 0, "menos": 0, "nuevo": False}
        elif actual is None:
            continue
        elif linea.startswith("new file mode"):
            archivos[actual]["nuevo"] = True
        elif linea.startswith("@@"):
            archivos[actual]["frag"] += 1
        elif linea.startswith("+") and not linea.startswith("+++"):
            archivos[actual]["mas"] += 1
            for nombre, rx in RIESGO.items():
                if rx.search(linea):
                    hallazgos.append((actual, nombre, linea[1:].strip()[:140]))
        elif linea.startswith("-") and not linea.startswith("---"):
            archivos[actual]["menos"] += 1
    for a, d in archivos.items():
        out.append(f"| `{a}` | {d['frag']} | {d['mas']} | {d['menos']} | {'sí' if d['nuevo'] else 'no'} |")
    out += ["", f"Archivos: {len(archivos)} · líneas +{sum(d['mas'] for d in archivos.values())} / −{sum(d['menos'] for d in archivos.values())}", ""]
    out += ["Líneas agregadas que tocan un patrón de riesgo (para revisar a mano; un patrón no es un defecto):", ""]
    out += [f"- `{a}` · {n}: `{t}`" for a, n, t in hallazgos] or ["- ninguna"]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    print("# Inventario de diferencias (generado; la revisión de cada hallazgo está en REVISION_DIFERENCIAS.md)\n")
    for p in sys.argv[1:]:
        print(inventario(Path(p)))
