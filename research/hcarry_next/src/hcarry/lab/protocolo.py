"""Protocolo de investigación de H-CARRY Next, FIJADO ANTES de ver datos reales (su hash entra en el registro).

Cada candidato tiene una LÍNEA BASE PROPIA que aísla su componente:
  - apalancada (ρ = 0,5), escala_vol y umbral (ρ = 1)       → referencia rev. 5 (Siempre, ρ = 1)
  - prima (ρ = 1)                                            → referencia rev. 5
  - rho_vol, umbral_apalancado y prima_apalancada (ρ 0,5)    → Siempre con ρ = 0,5
Así una mejora del umbral con apalancamiento no se atribuye al umbral cuando la produce el apalancamiento.

1. Desarrollo: referencia, líneas base y una lista finita de candidatos (familias fijas + rejilla de UmbralFunding).
   Elegibles: completados, sin liquidaciones, caída máxima ≤ 10 %. Se elige el de mayor CAGR neto de cada familia
   (a igualdad, el primero de la lista).
2. Validación: pasa a test cada elegido que supere a SU línea base en PnL neto con P(dif. diaria media > 0) ≥ 0,8
   (bootstrap por bloques de 20 días) y sin liquidaciones.
3. Test (prerregistrado; una vez por configuración): referencia, líneas base y promovidos; todos también bajo estrés
   (costes ×2, retraso de 1 h, pata del perp adversa, funding × 0,75).
4. Decisión por candidato, frente a su línea base: COMPONENTE DEMOSTRADO si PnL neto > base, P ≥ 0,9, sin
   liquidaciones, caída ≤ caída de la base + 5 pp y con costes ×2 sigue superando a la base con costes ×2.
   Se informa además si supera a la referencia rev. 5.

Mundos nulos (``nulo``): el funding se baraja en el tiempo (misma distribución, sin persistencia). Una regla basada en
la persistencia del funding no debería superar a su base ahí; la frecuencia con que el protocolo la declara
DEMOSTRADA en mundos nulos estima su tasa de falsos descubrimientos con este generador."""

from __future__ import annotations

import copy
import itertools
import json
from pathlib import Path

from hcarry.lab import experimento as X
from hcarry.lab.estadistica import comparar

REFERENCIA = {"nombre": "siempre", "params": {"rho": 1.0, "banda": [0.5, 1.5]}}
APALANCADA = {"rho": 0.5, "banda": [0.3, 0.75]}
BASE_APALANCADA = {"nombre": "siempre", "params": dict(APALANCADA)}
BASES = {"referencia": REFERENCIA, "siempre_rho05": BASE_APALANCADA}


def candidatos() -> list[tuple[str, str, dict, str]]:
    """(familia, etiqueta, política, línea base). El orden importa en los empates (primero = más simple)."""
    c: list[tuple[str, str, dict, str]] = [
        ("apalancada", "siempre_rho05", BASE_APALANCADA, "referencia"),
        # rho_min = rho base: solo AÑADE margen con volatilidad alta (sin apalancamiento extra que confunda)
        ("rho_vol", "rho_vol", {"nombre": "rho_vol", "params": {"base": "siempre", "rho_base": 0.5, "vol_ref": 0.6,
                                                                "rho_min": 0.5, "rho_max": 1.0}}, "siempre_rho05"),
        ("escala_vol", "escala_vol", {"nombre": "escala_vol", "params": {"base": "siempre", "vol_obj": 0.5}},
         "referencia"),
    ]
    for ventana, entrada, salida, apal in itertools.product((63, 21, 9), (0.10, 0.05, 0.15), (0.03, 0.0), (False, True)):
        params = {"ventana": ventana, "entrada": entrada, "salida": salida, "permanencia_h": 72}
        if apal:
            params.update(APALANCADA)
        c.append(("umbral_apalancado" if apal else "umbral",
                  f"umbral_v{ventana}_e{entrada}_s{salida}" + ("_rho05" if apal else ""),
                  {"nombre": "umbral_funding", "params": params}, "siempre_rho05" if apal else "referencia"))
    for ventana_h, entrada, salida, apal in itertools.product((24, 8, 72), (0.05, 0.10), (0.0, 0.03), (False, True)):
        params = {"ventana_h": ventana_h, "entrada": entrada, "salida": salida, "permanencia_h": 24}
        if apal:
            params.update(APALANCADA)
        c.append(("prima_apalancada" if apal else "prima",
                  f"prima_v{ventana_h}_e{entrada}_s{salida}" + ("_rho05" if apal else ""),
                  {"nombre": "umbral_prima", "params": params}, "siempre_rho05" if apal else "referencia"))
    return c


ESTRES = {
    "costes_x2": {"costes": {"multiplicador": 2.0}},
    "retraso_1h": {"motor": {"retraso_barras": 1}},
    "pata_adversa": {"motor": {"pata_perp_adversa": True}},
    "funding_x075": {"estres": {"funding_factor": 0.75}},
}


def definicion() -> dict:
    return {"referencia": REFERENCIA, "bases": BASES, "candidatos": candidatos(), "estres": ESTRES,
            "seleccion": "max CAGR neto por familia en desarrollo; elegibles: completados, sin liquidación, caída ≤ 10 %",
            "promocion": "validación: PnL > base propia y P(dif>0) ≥ 0,8 (bloques 20 d), sin liquidaciones",
            "decision": "test vs base propia: PnL >, P ≥ 0,9 (bloques 30 d), sin liquidación, caída ≤ base + 5 pp, "
                        "costes ×2 sigue > base ×2"}


def hash_protocolo() -> str:
    return X.sha(X.canonico(definicion()))


def nulo(datos: dict, semilla: int) -> dict:
    """Fuente NULA: las mismas barras con el funding barajado en el tiempo (ver experimento.cargar_datos)."""
    return {**datos, "nulo_semilla": semilla}


def _cfg(nombre: str, datos: dict, division, politica: dict, extra: dict | None = None) -> dict:  # type: ignore[no-untyped-def]
    c = {"nombre": nombre, "datos": datos, "division": division, "politica": copy.deepcopy(politica),
         "costes": {}, "filtros": {}, "motor": {}}
    for k, v in (extra or {}).items():
        c[k] = {**c.get(k, {}), **v}
    return c


def ejecutar(datos: dict, directorio: Path, etiqueta: str) -> dict:
    """Corre el protocolo completo sobre una fuente; deja registro, prerregistro e informe JSON en ``directorio``."""
    directorio.mkdir(parents=True, exist_ok=True)
    registro = directorio / "registro.jsonl"
    pre = directorio / "prerregistro_test.json"
    hp = hash_protocolo()
    salida: dict = {"etiqueta": etiqueta, "protocolo_sha256": hp, "datos": datos, "desarrollo": {}, "validacion": {},
                    "test": {}}

    # 1. desarrollo
    for nombre, pol in BASES.items():
        salida["desarrollo"][nombre] = _resumen(X.correr(_cfg(nombre, datos, "desarrollo", pol), registro)[1])
    mejores: dict[str, tuple[str, dict, str, dict]] = {}
    for familia, nombre, pol, base in candidatos():
        if nombre in BASES:
            m = salida["desarrollo"][nombre]
        else:
            m = _resumen(X.correr(_cfg(nombre, datos, "desarrollo", pol), registro)[1])
            salida["desarrollo"][nombre] = m
        elegible = m["estado"] == "completada" and m["liquidaciones"] == 0 and m["caida_maxima"] <= 0.10
        if elegible and (familia not in mejores or m["cagr_neto"] > mejores[familia][3]["cagr_neto"]):
            mejores[familia] = (nombre, pol, base, m)
    salida["seleccionados"] = {f: v[0] for f, v in mejores.items()}

    # 2. validación
    val = {nombre: X.correr(_cfg(nombre, datos, "validacion", pol), registro) for nombre, pol in BASES.items()}
    for nombre in BASES:
        salida["validacion"][nombre] = _resumen(val[nombre][1])
    promovidos = []
    for familia, (nombre, pol, base, _) in mejores.items():
        r, m, _ = val[nombre] if nombre in val else X.correr(_cfg(nombre, datos, "validacion", pol), registro)
        cmp = comparar(r, val[base][0], bloque=20)
        pasa = m["pnl_neto"] > val[base][1]["pnl_neto"] and cmp.get("p_mayor_que_cero", 0) >= 0.8 and m["liquidaciones"] == 0
        salida["validacion"][f"{nombre} vs {base}"] = {**_resumen(m), "base": base, "bootstrap": cmp, "promovido": pasa}
        if pasa:
            promovidos.append((nombre, pol, base))

    # 3. test (prerregistro antes de ejecutar)
    politicas = dict(BASES)
    politicas.update({n: p for n, p, _ in promovidos})
    configs = []
    for nombre, pol in politicas.items():
        configs.append(_cfg(nombre, datos, "test", pol))
        for e, extra in ESTRES.items():
            configs.append(_cfg(f"{nombre}__{e}", datos, "test", pol, extra))
    pre.write_text(json.dumps({"protocolo_sha256": hp, "configuraciones": configs}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    res = {c["nombre"]: X.correr(c, registro, pre) for c in configs}
    for nombre in BASES:
        salida["test"][nombre] = {**_resumen(res[nombre][1]),
                                  "estres": {e: _resumen(res[f"{nombre}__{e}"][1]) for e in ESTRES}}
    ref = res["referencia"]
    for nombre, _, base in promovidos:
        r, m, _ = res[nombre]
        b = res[base]
        cmp = comparar(r, b[0])
        x2 = res[f"{nombre}__costes_x2"][1]["pnl_neto"] > res[f"{base}__costes_x2"][1]["pnl_neto"]
        demostrado = (m["pnl_neto"] > b[1]["pnl_neto"] and cmp.get("p_mayor_que_cero", 0) >= 0.9
                      and m["liquidaciones"] == 0 and m["caida_maxima"] <= b[1]["caida_maxima"] + 0.05 and x2)
        cmp_ref = comparar(r, ref[0])
        salida["test"][nombre] = {
            **_resumen(m), "base": base, "bootstrap_vs_base": cmp, "supera_base_con_costes_x2": x2,
            "componente": "DEMOSTRADO" if demostrado else "NO DEMOSTRADO",
            "vs_referencia_rev5": {"pnl_mayor": m["pnl_neto"] > ref[1]["pnl_neto"],
                                   "p_mayor_que_cero": cmp_ref.get("p_mayor_que_cero")},
            "estres": {e: _resumen(res[f"{nombre}__{e}"][1]) for e in ESTRES}}
    (directorio / "resultado_protocolo.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1, default=str),
                                                         encoding="utf-8")
    return salida


def _resumen(m: dict) -> dict:
    claves = ("estado", "final", "pnl_neto", "cagr_neto", "caida_maxima", "funding_neto", "costes", "pnl_precio_patas",
              "tiempo_en_mercado", "rent_capital_comprometido", "liquidaciones", "entradas", "n_operaciones",
              "distancia_min_liquidacion", "base_adversa_p95_bps", "sharpe", "vol_anual", "rotacion_anual", "por_ano")
    s = {k: m.get(k) for k in claves}
    s["rev5"] = m["rev5"]["resultado"] if "rev5" in m else m.get("rev5")
    return s
