"""Calibración de tamaño de la prueba primaria (MEC v0.2 §5; Etapa B10 del plan). PREPARADA Y BLOQUEADA.

Requiere la autorización A-S1 del propietario. Los parámetros están FIJADOS en ``parametros_calibracion.json`` (su
SHA-256 figura en 05_PLAN_CUANTITATIVO.md) ANTES de ver cualquier tasa de rechazo. No usa datos reales.

Modos:
  --plan                         cuenta el trabajo y mide el costo con UNA réplica (no estima ninguna tasa).
  --prueba-humo                  2 réplicas por proceso con n = 80: comprueba que el circuito funciona (no informa tasas).
  --ejecutar --autorizacion REF  ejecuta todo y escribe <salida.json>. Sin REF no corre.
Criterio (MEC §5): para cada proceso y tamaño, la tasa de rechazo al 2,5 % y al 5 % debe ser ≤ el límite superior de su
banda (±2 errores de Monte Carlo). Un sub-rechazo se acepta y se informa. Si la prueba primaria falla, se evalúa la
regla de respaldo (D-S3) con los MISMOS datos sintéticos; si también falla, la prueba no está validada."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
from pec import inferencia, sintetico  # noqa: E402

PARAMETROS = AQUI / "parametros_calibracion.json"


def _replica(proceso: str, n: int, r: int, semilla: int, b: int, respaldo: bool) -> dict:
    x = sintetico.proceso(proceso, n, semilla + r)
    try:
        res = inferencia.respaldo(x, b, semilla + r) if respaldo else inferencia.bootstrap_t(x, 20, b, semilla + r)
        return {"p": res["p_unilateral"], "degenerada": False}
    except inferencia.ErrorSerieDegenerada:
        return {"p": 1.0, "degenerada": True}  # sin variabilidad no hay rechazo posible


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true")
    g.add_argument("--prueba-humo", action="store_true")
    g.add_argument("--ejecutar", action="store_true")
    ap.add_argument("--autorizacion", default=None)
    ap.add_argument("--salida", default=None)
    a = ap.parse_args()
    crudo = PARAMETROS.read_bytes()
    par = json.loads(crudo)
    huella = hashlib.sha256(crudo).hexdigest()
    procesos, tamanos, reps, b, semilla = (par["procesos"], par["tamanos"], par["replicas"], par["B"], par["semilla"])
    if a.plan:
        t0 = time.perf_counter()
        _replica("C2", max(tamanos), 0, semilla, b, False)
        una = time.perf_counter() - t0
        total = len(procesos) * len(tamanos) * reps
        print(json.dumps({"parametros_sha256": huella, "replicas_totales_prueba_primaria": total,
                          "segundos_por_replica_n_max": round(una, 3),
                          "horas_estimadas_cota_superior": round(total * una / 3600, 2),
                          "horas_estimadas_con_regla_de_respaldo": round(3 * total * una / 3600, 2),
                          "nota": "estimación con una réplica de n máximo; no se estimó ninguna tasa de rechazo"},
                         ensure_ascii=False, indent=1))
        return 0
    if a.prueba_humo:
        for pr in procesos:
            for respaldo in (False, True):
                for r in range(2):
                    out = _replica(pr, 80, r, semilla, 199, respaldo)
                    assert 0 < out["p"] <= 1, out
        print(f"prueba de humo: {len(procesos)} procesos × 2 réplicas × 2 reglas sin error (no se informa ninguna tasa)")
        return 0
    if not a.autorizacion or not a.salida:
        print("BLOQUEADO: la calibración requiere la autorización A-S1 (--autorizacion REF) y --salida", file=sys.stderr)
        return 2
    resultados = {"parametros_sha256": huella, "autorizacion": a.autorizacion, "filas": []}
    for respaldo in (False, True):
        for pr in procesos:
            for n in tamanos:
                ps, deg = [], 0
                for r in range(reps):
                    out = _replica(pr, n, r, semilla, b, respaldo)
                    ps.append(out["p"])
                    deg += out["degenerada"]
                fila = {"regla": "respaldo_max" if respaldo else "bootstrap_t_l20", "proceso": pr, "n": n,
                        "degeneradas": deg}
                for alfa, (_lo, hi) in par["bandas"].items():
                    tasa = sum(1 for p in ps if p <= float(alfa)) / reps
                    fila[f"rechazo_{alfa}"] = tasa
                    fila[f"cumple_{alfa}"] = tasa <= hi
                resultados["filas"].append(fila)
    Path(a.salida).write_text(json.dumps(resultados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
