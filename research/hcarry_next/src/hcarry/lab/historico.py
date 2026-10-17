"""Validación histórica rev. 5 frente a UmbralFunding, PRERREGISTRADA antes de ver datos reales.

``PRERREGISTRO`` fija las políticas y sus parámetros, los costes, las sensibilidades, el diagnóstico previo, los filtros de
calidad y los criterios de las tres conclusiones posibles. Su hash queda en el informe; cambiarlo después de ver datos
es una hipótesis nueva que exige datos nuevos.

Separación de categorías (no configurable): la categoría sale del MANIFIESTO de los datos.
  - procedencia "historico_oficial" → resultados/historico/…  (HISTÓRICO)
  - procedencia "sintetico"         → resultados/sintetico/…  (SINTÉTICO: ensayo del pipeline)
  - evidencia prospectiva: no existe todavía; ningún informe de este módulo la representa.

Flujo: calidad (si no es apta, se detiene: EVIDENCIA INSUFICIENTE) → diagnóstico de persistencia SOLO en desarrollo →
desarrollo y validación → prerregistro del test con los datos concretos → test una vez (base y sensibilidades) →
bootstrap pareado → conclusión por los criterios fijados."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from hcarry.conventions import DIA_MS, ms
from hcarry.data import calidad
from hcarry.data.binance_vision import inicio_comun, leer_manifiesto
from hcarry.lab import experimento as X
from hcarry.lab.divisiones import DIVISIONES
from hcarry.lab.estadistica import comparar

PRERREGISTRO: dict = {
    "version": 1,
    "fecha": "2026-10-16",
    "preguntas": [
        ("P1: ¿mejora UmbralFunding de forma neta y robusta al carry permanente de rev. 5, con los mismos datos, costes "
        "y restricciones?"),
        ("P2: ¿tiene el carry permanente de rev. 5 una ventaja económica neta (CAGR neto > comparador del 5 % y > 0 con "
        "costes ×2)?")],
    "datos": {"fuente": "data.binance.vision", "procedencia_requerida_para_historico": "historico_oficial",
              "simbolo": "BTCUSDT", "series_requeridas": ["spot", "perp", "mark", "funding"],
              "inicio": "primer mes común de las series requeridas (y no antes de 2019-10-01)", "fin": "2026-06-01",
              "filtros_calidad": calidad.UMBRALES},
    "divisiones": DIVISIONES,
    "politicas": {
        "rev5": {"nombre": "siempre", "params": {"rho": 1.0, "banda": [0.5, 1.5]}},
        "umbral": {"nombre": "umbral_funding",
                   "params": {"ventana": 21, "entrada": 0.10, "salida": 0.03, "permanencia_h": 72, "rho": 1.0,
                              "banda": [0.5, 1.5]}},
    },
    "parametros_umbral_origen": "fijados a priori (valores por defecto del laboratorio), sin optimizar con datos reales",
    "costes_base": {"spot_comision_bps": 10.0, "spot_slippage_bps": 5.0, "perp_comision_bps": 5.0,
                    "perp_slippage_bps": 5.0},
    "motor_base": {"capital": 10_000.0, "mmr": 0.01, "apalancamiento_max": 2.0, "al_inviable": "omitir"},
    "sensibilidad": {
        "costes_x05": {"costes": {"multiplicador": 0.5}},
        "costes_x2": {"costes": {"multiplicador": 2.0}},
        "costes_x3": {"costes": {"multiplicador": 3.0}},
        "retraso_1h": {"motor": {"retraso_barras": 1}},
        "retraso_3h": {"motor": {"retraso_barras": 3}},
        "pata_adversa": {"motor": {"pata_perp_adversa": True}},
        "funding_x075": {"estres": {"funding_factor": 0.75}},
        "nocional_min_perp_5": {"filtros": {"nocional_min_perp": 5.0}},
    },
    "rev5_r0": {"motor": {"al_inviable": "detener"}, "uso": "solo para informar D1–D4 de rev. 5 (reconstrucción)"},
    "diagnostico_previo": {"que": "correlación entre medias de funding de bloques consecutivos de 7 días y fracción de "
                                  "eventos negativos, SOLO en desarrollo",
                           "prediccion": "si la correlación es < 0,2, UmbralFunding no debería aportar ventaja"},
    "bootstrap": {"bloque_dias": 30, "remuestreos": 2000, "semilla": 20261016},
    "criterios": {
        "VENTAJA RESPALDADA": [
            "datos HISTÓRICOS y calidad apta",
            "test: PnL neto de umbral > rev5",
            "test: P(diferencia diaria media > 0) ≥ 0,95",
            "test: caída máxima de umbral ≤ caída de rev5 + 5 pp, y sin liquidaciones",
            "test: umbral > rev5 también con costes ×2, con pata adversa y con retraso de 3 h",
            "validación: umbral ≥ rev5 (mismo signo que en test)"],
        "HIPÓTESIS NO RESPALDADA": [
            "datos HISTÓRICOS y calidad apta, y en test: PnL neto de umbral ≤ rev5 o P(dif > 0) < 0,5"],
        "EVIDENCIA INSUFICIENTE": [
            ("datos no históricos o calidad no apta, o resultado intermedio (0,5 ≤ P < 0,95 o fallo de solo algún "
            "estrés o de la validación)")],
        "P2_carry_rev5": "VENTAJA RESPALDADA si en test el CAGR neto de rev5 > 5 % y con costes ×2 > 0; NO RESPALDADA "
                         "si el CAGR neto ≤ 0; si no, EVIDENCIA INSUFICIENTE",
    },
}


def hash_prerregistro() -> str:
    return X.sha(X.canonico(PRERREGISTRO))


def _cfg(nombre: str, datos: dict, division, politica: dict, extra: dict | None = None) -> dict:  # type: ignore[no-untyped-def]
    c = {"nombre": nombre, "datos": datos, "division": division, "politica": politica,
         "costes": dict(PRERREGISTRO["costes_base"]), "filtros": {}, "motor": dict(PRERREGISTRO["motor_base"])}
    for k, v in (extra or {}).items():
        c[k] = {**c.get(k, {}), **v}
    return c


def _persistencia(funding, dias: int = 7) -> dict:  # type: ignore[no-untyped-def]
    if len(funding) < 3:
        return {"aplicable": False}
    ini = funding[0].t
    bloques: dict[int, list[float]] = {}
    for e in funding:
        bloques.setdefault((e.t - ini) // (dias * DIA_MS), []).append(e.tasa)
    m = [sum(v) / len(v) for _, v in sorted(bloques.items())][:-1]
    x, y = m[:-1], m[1:]
    if len(x) < 3:
        return {"aplicable": False}
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sx = sum((a - mx) ** 2 for a in x) ** 0.5
    sy = sum((b - my) ** 2 for b in y) ** 0.5
    corr = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True)) / (sx * sy) if sx and sy else None
    return {"aplicable": True, "bloque_dias": dias, "bloques": len(m), "correlacion": corr,
            "fraccion_negativas": sum(e.tasa < 0 for e in funding) / len(funding),
            "prediccion": ("UmbralFunding no debería aportar (correlación < 0,2)" if corr is not None and corr < 0.2
                           else "persistencia suficiente para que UmbralFunding pueda aportar")}


CERROJO_TEST = "TEST_CONSUMIDO.json"


class TestYaConsumido(RuntimeError):
    """El test histórico prerregistrado ya se ejecutó (con estos u otros datos): no se repite."""


def _cerrojo(raiz_resultados: Path) -> Path:
    return raiz_resultados / "historico" / CERROJO_TEST


def comprobar_test_disponible(raiz_resultados: Path) -> None:
    """El registro por carpeta de datos no basta: una descarga nueva tiene otro manifiesto (otra fecha) y por tanto otra
    carpeta y otro registro. Este cerrojo es global para la categoría histórica y no depende de los datos."""
    c = _cerrojo(raiz_resultados)
    if c.exists():
        raise TestYaConsumido(f"el test histórico prerregistrado ya se consumió: {c.read_text(encoding='utf-8')}")


def reservar_test(raiz_resultados: Path, info: dict) -> None:
    """Marca el test como consumido ANTES de ejecutarlo (creación exclusiva): un fallo a mitad también lo consume."""
    c = _cerrojo(raiz_resultados)
    c.parent.mkdir(parents=True, exist_ok=True)
    with c.open("x", encoding="utf-8") as f:
        f.write(json.dumps(info, ensure_ascii=False, indent=1, default=str) + "\n")


def evaluar(directorio: Path, raiz_resultados: Path) -> dict:
    man = leer_manifiesto(directorio)
    categoria = "historico" if man["procedencia"] == "historico_oficial" else "sintetico"
    if categoria == "historico":
        comprobar_test_disponible(raiz_resultados)
    inf_cal = calidad.evaluar(directorio)
    destino = raiz_resultados / categoria / f"datos_{inf_cal['manifiesto_sha256'][:12]}"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "calidad.md").write_text(calidad.markdown(inf_cal), encoding="utf-8")
    (destino / "calidad.json").write_text(json.dumps(inf_cal, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    salida: dict = {"categoria": categoria, "procedencia": man["procedencia"], "via": man.get("via"),
                    "prerregistro_sha256": hash_prerregistro(), "codigo_sha256": X.huella_codigo(),
                    "fecha_utc": dt.datetime.now(dt.UTC).isoformat(), "calidad_apta": inf_cal["apto"],
                    "manifiesto_sha256": inf_cal["manifiesto_sha256"]}
    if not inf_cal["apto"]:
        salida["conclusion"] = {"P1_umbral_vs_rev5": "EVIDENCIA INSUFICIENTE", "P2_carry_rev5": "EVIDENCIA INSUFICIENTE",
                                "motivo": "los datos no superan los filtros de calidad prerregistrados; no se simuló nada"}
        return _escribir(destino, salida)

    ini = max(inicio_comun(directorio), "2019-10-01")
    datos = {"fuente": "binance_vision", "directorio": str(directorio), "desde": ini, "hasta": "2026-06-01"}
    registro = destino / "registro.jsonl"
    pols = PRERREGISTRO["politicas"]

    # diagnóstico previo SOLO en desarrollo
    panel, _ = X.cargar_datos(datos)
    a, b = ms(DIVISIONES["desarrollo"][0]), ms(DIVISIONES["desarrollo"][1])
    salida["diagnostico_previo_desarrollo"] = _persistencia(panel.recortar(max(a, panel.inicio), b).funding)

    # desarrollo y validación
    for division in ("desarrollo", "validacion"):
        res = {n: X.correr(_cfg(n, datos, division, p), registro) for n, p in pols.items()}
        salida[division] = {n: _resumen(r[1]) for n, r in res.items()}
        cmp = comparar(res["umbral"][0], res["rev5"][0], bloque=20)
        salida[division]["umbral_menos_rev5"] = {"pnl": res["umbral"][1]["pnl_neto"] - res["rev5"][1]["pnl_neto"],
                                                 "bootstrap": cmp}

    # test: prerregistro con los datos concretos y ejecución única
    configs = []
    for n, p in pols.items():
        configs.append(_cfg(n, datos, "test", p))
        for e, extra in PRERREGISTRO["sensibilidad"].items():
            configs.append(_cfg(f"{n}__{e}", datos, "test", p, extra))
    configs.append(_cfg("rev5__R0", datos, "test", pols["rev5"], {"motor": PRERREGISTRO["rev5_r0"]["motor"]}))
    pre = destino / "prerregistro_test.json"
    pre.write_text(json.dumps({"prerregistro_sha256": hash_prerregistro(), "configuraciones": configs},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    if categoria == "historico":
        reservar_test(raiz_resultados, {"prerregistro_sha256": hash_prerregistro(), "codigo_sha256": X.huella_codigo(),
                                        "manifiesto_sha256": inf_cal["manifiesto_sha256"], "destino": str(destino),
                                        "fecha_utc": dt.datetime.now(dt.UTC).isoformat(), "configuraciones": len(configs)})
    res = {c["nombre"]: X.correr(c, registro, pre) for c in configs}
    rev5, umb = res["rev5"], res["umbral"]
    boot = comparar(umb[0], rev5[0], bloque=PRERREGISTRO["bootstrap"]["bloque_dias"],
                    n=PRERREGISTRO["bootstrap"]["remuestreos"], semilla=PRERREGISTRO["bootstrap"]["semilla"])
    sens = {e: {"rev5": _resumen(res[f"rev5__{e}"][1]), "umbral": _resumen(res[f"umbral__{e}"][1]),
                "umbral_menos_rev5_pnl": res[f"umbral__{e}"][1]["pnl_neto"] - res[f"rev5__{e}"][1]["pnl_neto"]}
            for e in PRERREGISTRO["sensibilidad"]}
    salida["test"] = {"rev5": _resumen(rev5[1]), "umbral": _resumen(umb[1]), "bootstrap_umbral_menos_rev5": boot,
                      "sensibilidad": sens, "rev5_R0_d1_d4": res["rev5__R0"][1]["rev5"]}
    salida["conclusion"] = concluir(categoria, salida)
    return _escribir(destino, salida)


def concluir(categoria: str, s: dict) -> dict:
    """Aplica los criterios prerregistrados. Nada de esto es configurable a posteriori."""
    t = s["test"]
    d_pnl = t["umbral"]["pnl_neto"] - t["rev5"]["pnl_neto"]
    p = t["bootstrap_umbral_menos_rev5"].get("p_mayor_que_cero")
    estres_ok = all(t["sensibilidad"][e]["umbral_menos_rev5_pnl"] > 0 for e in ("costes_x2", "pata_adversa", "retraso_3h"))
    val_ok = s["validacion"]["umbral_menos_rev5"]["pnl"] >= 0
    riesgo_ok = (t["umbral"]["caida_maxima"] <= t["rev5"]["caida_maxima"] + 0.05 and t["umbral"]["liquidaciones"] == 0)
    detalles = {"dif_pnl_test": d_pnl, "p_dif_mayor_que_cero": p, "estres_ok": estres_ok, "validacion_mismo_signo": val_ok,
                "riesgo_ok": riesgo_ok}
    if categoria != "historico":
        p1 = p2 = "EVIDENCIA INSUFICIENTE"
        motivo = "datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)"
    else:
        if d_pnl > 0 and p is not None and p >= 0.95 and estres_ok and val_ok and riesgo_ok:
            p1 = "VENTAJA RESPALDADA"
        elif d_pnl <= 0 or (p is not None and p < 0.5):
            p1 = "HIPÓTESIS NO RESPALDADA"
        else:
            p1 = "EVIDENCIA INSUFICIENTE"
        cagr, cagr_x2 = t["rev5"]["cagr_neto"], t["sensibilidad"]["costes_x2"]["rev5"]["cagr_neto"]
        p2 = ("VENTAJA RESPALDADA" if cagr > 0.05 and cagr_x2 > 0 else
              "HIPÓTESIS NO RESPALDADA" if cagr <= 0 else "EVIDENCIA INSUFICIENTE")
        motivo = "criterios prerregistrados aplicados a datos históricos"
    return {"P1_umbral_vs_rev5": p1, "P2_carry_rev5": p2, "motivo": motivo, "detalles": detalles}


def _resumen(m: dict) -> dict:
    claves = ("estado", "final", "pnl_neto", "cagr_neto", "caida_maxima", "funding_neto", "funding_cobrado",
              "funding_pagado", "costes", "pnl_precio_patas", "tiempo_en_mercado", "rent_capital_comprometido",
              "liquidaciones", "entradas", "n_operaciones", "rotacion_anual", "sharpe", "vol_anual",
              "distancia_min_liquidacion", "base_adversa_p95_bps", "por_ano", "comparador_5")
    s = {k: m.get(k) for k in claves}
    s["rev5_d1_d4"] = m["rev5"]["resultado"]
    return s


def _escribir(destino: Path, salida: dict) -> dict:
    (destino / "resultado.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1, default=str),
                                            encoding="utf-8")
    (destino / "INFORME.md").write_text(markdown(salida), encoding="utf-8")
    salida["destino"] = str(destino)
    return salida


def markdown(s: dict) -> str:
    banner = {"historico": "# Validación HISTÓRICA — rev. 5 frente a UmbralFunding\n\n"
                           "Datos oficiales de data.binance.vision verificados por checksum.",
              "sintetico": "# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding\n\n"
                           "> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. "
                           "**No es evidencia económica** y no puede citarse como resultado histórico."}[s["categoria"]]
    c = s["conclusion"]
    out = [banner, "", (f"- Prerregistro: `{s['prerregistro_sha256']}` · código: `{s['codigo_sha256'][:16]}…` · "
                       f"datos: `{s['manifiesto_sha256'][:16]}…` ({s['via']})"),
           f"- Calidad de datos apta: **{'sí' if s['calidad_apta'] else 'NO'}** (ver `calidad.md`)", "",
           "## Conclusión (criterios prerregistrados)", "",
           f"- **P1 · UmbralFunding frente a rev. 5: {c['P1_umbral_vs_rev5']}**",
           f"- **P2 · ventaja neta del carry de rev. 5: {c['P2_carry_rev5']}**", f"- Motivo: {c['motivo']}"]
    if "detalles" in c:
        out.append(f"- Detalles: `{json.dumps(c['detalles'], ensure_ascii=False, default=str)}`")
    if "test" in s:
        d = s.get("diagnostico_previo_desarrollo", {})
        out += ["", "## Diagnóstico previo (solo desarrollo)", "",
                (f"- Correlación de medias de 7 días consecutivos: {d.get('correlacion')} · eventos negativos: "
                f"{d.get('fraccion_negativas')} → {d.get('prediccion')}"), "",
                "## Resultados por división (costes base)", "",
                "| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |",
                "|---|---|---|---|---|---|---|---|"]
        for div in ("desarrollo", "validacion", "test"):
            for n in ("rev5", "umbral"):
                r = s[div][n]
                out.append(f"| {div} | {n} | {r['cagr_neto']:.2%} | {r['caida_maxima']:.2%} | {r['funding_neto']:.0f} | "
                           f"{r['costes']:.0f} | {r['tiempo_en_mercado']:.0%} | {r['rotacion_anual']:.1f} |")
        b = s["test"]["bootstrap_umbral_menos_rev5"]
        out += ["", (f"Bootstrap pareado en test (umbral − rev5): media anual {b.get('media_anual')}, intervalo 90 % "
                    f"{b.get('intervalo_anual')}, P(> 0) = {b.get('p_mayor_que_cero')}"), "",
                "## Sensibilidad en test", "", "| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |", "|---|---|---|---|"]
        for e, v in s["test"]["sensibilidad"].items():
            out.append(f"| {e} | {v['rev5']['cagr_neto']:.2%} | {v['umbral']['cagr_neto']:.2%} | "
                       f"{v['umbral_menos_rev5_pnl']:.0f} |")
        out += ["", f"D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {s['test']['rev5_R0_d1_d4']}"]
    out += ["", "Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva)."]
    return "\n".join(out) + "\n"
