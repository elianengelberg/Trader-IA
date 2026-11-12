"""Actividad de símbolos USDT según `auditoria_por_simbolo.json` (derivada de `estado`; sin precios).
Uso: actividad_simbolos.py <dir_E3> <BASE1> [<BASE2> ...]  → por base: ¿está en el bucket?, episodios y cortes con reanudación."""
import json, sys
E3, bases = sys.argv[1], sys.argv[2:]
usdt = set(json.load(open(f"{E3}/datos_vision/listados/simbolos_usdt.json")))
aud = {a["simbolo"]: a for a in json.load(open(f"{E3}/resultados/calidad/auditoria_por_simbolo.json"))}
for b in bases:
    s = b + "USDT"
    if s not in usdt:
        print(f"{s:<14} no está en el bucket USDT"); continue
    a = aud.get(s, {})
    print(f"{s:<14} episodios={a.get('episodios')} cortes={a.get('cortes_con_reanudacion')}")
