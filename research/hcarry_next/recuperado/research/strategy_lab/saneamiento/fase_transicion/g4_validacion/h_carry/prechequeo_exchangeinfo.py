"""Comprobación PREVIA de los filtros de H-CARRY con el exchangeInfo ACTUAL (rev. 5). NO es parte del experimento.

Responde, antes de congelar el plan, una sola pregunta: ¿los metadatos VIGENTES de BTCUSDT (spot y perpetuo) caben en
la lista cerrada de filtros del plan (si no, M1) y dan una retícula de órdenes no vacía (si no, Q1)? Así no se gasta el
único experimento en un SIN VEREDICTO por metadatos.

Alcance cerrado:
  - exactamente 2 peticiones GET, las dos de exchangeInfo del plan (hc_plan.peticiones): spot con symbol=BTCUSDT y
    futuros USDⓈ-M sin parámetros; ninguna vela, ningún funding, nada histórico, ninguna clave;
  - solo se ejecuta con una autorización explícita (--autorizacion <referencia>); sin ella termina sin conectar;
  - guarda las dos respuestas crudas por su SHA-256 y un resumen; no cambia el plan ni el código: si aparece un M1 o
    un Q1, cualquier cambio de la lista cerrada se decide y se documenta ANTES de congelar (cambia el plan_sha256).
LÍMITE: dice cómo son los filtros HOY; no dice nada de los filtros que regían en 2024-2026 (S8).

Uso (solo con autorización):  python -I -B h_carry/prechequeo_exchangeinfo.py --autorizacion REF --salida DIR"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))  # con python -I la carpeta del script no entra en sys.path

import hc_comun as HC  # noqa: E402
import hc_datos as DATOS  # noqa: E402
import hc_descarga as DESC  # noqa: E402
import hc_plan as PL  # noqa: E402

ESQUEMA = "hcarry-prechequeo-exchangeinfo/1"
PETICIONES = [p for p in PL.peticiones(PL.VENTANA_PROTOCOLO) if p["tipo"] == "exchangeinfo"]
assert [p["id"] for p in PETICIONES] == ["exchangeinfo-spot", "exchangeinfo-perp"]


def _tipos(info: Any, mercado: str) -> dict:
    """Tipos y campos de filtro de BTCUSDT tal como llegan, clasificados contra la lista cerrada (informativo)."""
    cfg = PL.FILTROS[mercado]
    simbolos = info.get("symbols") if isinstance(info, dict) else None
    hallados = [s for s in simbolos or [] if isinstance(s, dict) and s.get("symbol") == PL.SIMBOLO]
    if len(hallados) != 1:
        return {"simbolo_encontrado": len(hallados)}
    salida = {"simbolo_encontrado": 1, "contractType": hallados[0].get("contractType"), "filtros": {}}
    for f in hallados[0].get("filters") or []:
        tipo = f.get("filterType") if isinstance(f, dict) else None
        clase = "aplicado" if tipo in cfg["aplicados"] else "no aplicable (S6)" if tipo in cfg["no_aplicables"] else "DESCONOCIDO"
        salida["filtros"][str(tipo)] = {"clase": clase, "campos": sorted(f) if isinstance(f, dict) else None}
    return salida


def comprobar(transporte: Any, salida: Path | None = None, autorizacion: str = "") -> dict:
    """Las 2 peticiones, la revisión de forma de cada respuesta y la lectura estricta de los filtros del plan."""
    if not isinstance(autorizacion, str) or not autorizacion.strip():
        raise PermissionError("la comprobación previa necesita una autorización explícita (--autorizacion)")
    cuerpos, shas = {}, {}
    for p in PETICIONES:
        cuerpo = transporte.obtener(p["base"], p["ruta"], dict(p["params"]))
        DESC.revisar_pagina(p, cuerpo, PL.CORTE_MS)  # P1 si no es JSON o no trae la lista de símbolos
        cuerpos[p["id"]], shas[p["id"]] = cuerpo, HC.sha256_bytes(cuerpo)
    spot, perp = (json.loads(cuerpos[i]) for i in ("exchangeinfo-spot", "exchangeinfo-perp"))
    reg = DATOS.Registro()
    filtros, info = DATOS.leer_filtros(spot, perp, reg)
    resumen = {
        "esquema": ESQUEMA, "autorizacion": autorizacion.strip(), "transporte": str(getattr(transporte, "descripcion", "")),
        "peticiones": [{"id": p["id"], "base": p["base"], "ruta": p["ruta"], "params": p["params"]} for p in PETICIONES],
        "sha256": shas, "incidencias": reg.incidencias, "apto": not reg.incidencias,
        "tipos": {"spot": _tipos(spot, "spot"), "perp": _tipos(perp, "perp")},
        "parametros": None if filtros is None else {
            "periodo": filtros.periodo, "minimo": filtros.minimo, "maximo": filtros.maximo,
            "nocional_min_spot": filtros.nocional_min_spot, "nocional_min_perp": filtros.nocional_min_perp,
            "nocional_max_spot": filtros.nocional_max_spot},
        "supuestos_declarados": info.get("supuestos", []),
        "limite": "filtros VIGENTES hoy; no prueba nada sobre los filtros de 2024-2026 (S8)",
    }
    if salida is not None:
        (salida / "datos").mkdir(parents=True, exist_ok=False)
        for i, cuerpo in cuerpos.items():
            HC.escribir_atomico(salida / "datos" / f"{shas[i]}.json", cuerpo)
        HC.escribir_atomico(salida / "resumen.json", HC.canonico(resumen))
    return resumen


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--autorizacion", default="", help="referencia de la autorización explícita del responsable")
    ap.add_argument("--salida", type=Path, required=True, help="carpeta NUEVA para las 2 respuestas y el resumen")
    args = ap.parse_args(argv[1:])
    if not args.autorizacion.strip():
        print("sin autorización explícita: no se hace ninguna petición", file=sys.stderr)
        return 2
    import hc_transporte_http as HTTP  # solo aquí: único punto con red

    resumen = comprobar(HTTP.TransporteHTTP(), args.salida, args.autorizacion)
    print(json.dumps(json.loads(HC.canonico(resumen)), ensure_ascii=False, indent=1))
    return 0 if resumen["apto"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
