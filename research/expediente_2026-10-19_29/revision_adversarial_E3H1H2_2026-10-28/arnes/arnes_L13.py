"""Revisión adversarial · L-13: inyección de fallos en el flujo de control de `modo_real` del v3.

SIN DATOS Y SIN CÁLCULO: todos los insumos y todas las etapas de cálculo son stubs (no se lee ninguna serie, no se simula
la estrategia, no se calcula ningún estadístico). Los resultados «EVALUADO» que escribe el orquestador contienen solo
la cadena STUB_SIN_CALCULO.

SIN AUTORIZACIONES VÁLIDAS: en el módulo cargado se reemplazan FRASE, FRASES_DECISION y SHA_PROPIO por valores de prueba
con sal. Las autorizaciones de prueba no contienen ni la FRASE real ni el sha256 real del v3, así que el v3 real las
rechaza. Todo se escribe en <base> (directorio temporal propio); INTENTOS apunta a <base>/INTENTOS_E3.jsonl.

Uso:
  python -B -I arnes_L13.py correr <v3.py> <base> <escenario>     # ejecuta el escenario (puede morir con os._exit)
  python -B -I arnes_L13.py observar <v3.py> <base>                # nueva instancia: estado en disco y decisión
"""
import datetime as dt
import hashlib
import importlib.util
import json
import os
import sys
import types
from pathlib import Path

import numpy as np

FRASE_PRUEBA = "FRASE DE PRUEBA DEL REVISOR SIN VALOR"
DECISIONES_PRUEBA = {"reapertura_y_adenda_R": "DECISION DE PRUEBA R SIN VALOR",
                     "D1_lectura_literal": "DECISION DE PRUEBA D1 SIN VALOR"}
STUB = "STUB_SIN_CALCULO"


def sha_b(b):
    return hashlib.sha256(b).hexdigest()


def cargar(v3: Path, base: Path, nombre="v3_revisor"):
    spec = importlib.util.spec_from_file_location(nombre, v3)
    V = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(V)
    assert sha_b(V._BYTES_PROPIOS) == "c089cc6aad32f92a7899ec169c87216a7213c1f6393aeb9f6c9d32b52cb3e07e", "no es el v3 revisado"
    real = {"FRASE": V.FRASE, "SHA": V.SHA_PROPIO, "DEC": tuple(V.FRASES_DECISION.values())}
    V.FRASE = FRASE_PRUEBA
    V.FRASES_DECISION = dict(DECISIONES_PRUEBA)
    V.SHA_PROPIO = sha_b(b"REVISOR|" + V._BYTES_PROPIOS)
    V.INTENTOS = base / "INTENTOS_E3.jsonl"
    return V, real


def stubs(V, valido=True, falla_panel=False):
    U = types.SimpleNamespace(INICIO=dt.date(2017, 7, 1),
                              lunes=lambda a, b, dia_semana=0: [a + dt.timedelta(days=7 * k) for k in range(3)])
    V.leer_y_verificar = lambda man, raices: {
        "ventana_A": json.dumps({"veredicto": "VALIDO", "inicio_H": V.INICIO_H_A}).encode(),
        "mapeos_adenda1_completa": b'{"mapeos": []}', "universo.py": b"", "motor.py": b"", "inferencia.py": b""}
    V.cargar_modulos = lambda fuentes: {"universo": U, "motor": types.SimpleNamespace(), "inferencia": types.SimpleNamespace()}
    V.actividad_desde_bytes = lambda datos: (["XUSDT"], np.ones((1, 3), bool))
    V.aplicar_mapeos = lambda syms, O, C, QV, act, mapeos, inicio: (syms, O, C, QV, act, [], [(s,) for s in syms])
    V.comprobar_marcas = lambda *a: None

    def panel(datos, universo, mapeos):
        if falla_panel:
            raise RuntimeError("fallo inyectado en la etapa panel (stub)")
        return "PANEL_STUB", []
    V.panel_real = panel
    V.validez_previa = lambda P, F, u, m: ({"valido": valido, "nota": STUB}, {})
    V.ejecutar = lambda P, F, u, m, i, cache=None, formaciones_miercoles=None: {
        "semanas_ic": STUB, "H1": STUB, "H2": STUB, "holm": STUB, "clasificacion_6_5": STUB}


def autorizacion(V, base: Path, nombre: str, extra: str = "") -> Path:
    man = base / "manifiesto_prueba.json"
    if not man.exists():
        man.write_bytes(b'{"prueba": "sin valor"}')
    texto = "\n".join([FRASE_PRUEBA, V.SHA_PROPIO, sha_b(man.read_bytes()), *DECISIONES_PRUEBA.values(), extra, nombre]) + "\n"
    p = base / f"autorizacion_prueba_{nombre}.txt"
    p.write_text(texto)
    return p


def inyectar(V, evento_objetivo: str, modo: str, tambien_error: bool = False):
    """Fallo en Intentos.anotar la PRIMERA vez que se anota `evento_objetivo` (y, opcionalmente, también en ERROR)."""
    original = V.Intentos.anotar
    estado = {"hecho": set()}

    def anotar(self, **ev):
        e = ev.get("evento")
        objetivo = (e == evento_objetivo and evento_objetivo not in estado["hecho"]) or (tambien_error and e == "ERROR")
        if not objetivo:
            return original(self, **ev)
        estado["hecho"].add(e)
        if modo == "antes":
            raise OSError(28, f"fallo inyectado al anotar {e} (antes de escribir)")
        if modo == "despues":
            original(self, **ev)
            raise OSError(5, f"fallo inyectado al anotar {e} (después de escribir la línea)")
        if modo == "matar":
            os._exit(137)
        if modo == "interrumpir":
            raise KeyboardInterrupt(f"Ctrl-C inyectado al anotar {e}")
        if modo == "parcial":
            self.f.write(json.dumps({"evento": e, **ev})[:25])
            self.f.flush()
            os.fsync(self.f.fileno())
            os._exit(137)
        raise AssertionError(modo)
    V.Intentos.anotar = anotar


def inyectar_escritura_resultado(V):
    original = V.escribir_atomico
    estado = {"n": 0}

    def escribir(p, obj):
        if Path(p).name == "RESULTADO_E3.json" and estado["n"] == 0:
            estado["n"] += 1
            raise OSError(28, "fallo inyectado al escribir RESULTADO_E3.json (sin espacio)")
        return original(p, obj)
    V.escribir_atomico = escribir


ESCENARIOS = {
    # nombre: (válido, falla_panel, evento, modo, también_error, falla_escritura_resultado)
    "B1_evaluado_sin_fallo": (True, False, None, None, False, False),
    "B2_invalido_sin_fallo": (False, False, None, None, False, False),
    "B3_error_en_panel": (True, True, None, None, False, False),
    "E1_evaluado_anotar_falla_antes": (True, False, "EVALUADO", "antes", False, False),
    "E2_evaluado_anotar_falla_despues": (True, False, "EVALUADO", "despues", False, False),
    "E3_evaluado_proceso_muere": (True, False, "EVALUADO", "matar", False, False),
    "E4_evaluado_escritura_resultado_falla": (True, False, None, None, False, True),
    "E5_evaluado_anotar_falla_y_error_tambien": (True, False, "EVALUADO", "antes", True, False),
    "E6_evaluado_linea_parcial_y_muere": (True, False, "EVALUADO", "parcial", False, False),
    "I1_invalido_anotar_falla_antes": (False, False, "INVALIDO", "antes", False, False),
    "I2_invalido_anotar_falla_despues": (False, False, "INVALIDO", "despues", False, False),
    "I3_invalido_proceso_muere": (False, False, "INVALIDO", "matar", False, False),
    "I4_invalido_anotar_falla_y_error_tambien": (False, False, "INVALIDO", "antes", True, False),
    "E7_evaluado_ctrl_c_al_anotar": (True, False, "EVALUADO", "interrumpir", False, False),
    "I5_invalido_ctrl_c_al_anotar": (False, False, "INVALIDO", "interrumpir", False, False),
    "K1_muere_antes_de_INICIADO": (True, False, "INICIADO", "matar", False, False),
    "K2_INICIADO_falla_antes": (True, False, "INICIADO", "antes", False, False),
}


def correr(v3, base, escenario):
    base.mkdir(parents=True, exist_ok=True)
    V, real = cargar(v3, base)
    valido, falla_panel, evento, modo, tambien, falla_res = ESCENARIOS[escenario]
    stubs(V, valido=valido, falla_panel=falla_panel)
    if evento:
        inyectar(V, evento, modo, tambien)
    if falla_res:
        inyectar_escritura_resultado(V)
    aut = autorizacion(V, base, "intento1")
    texto = aut.read_text()
    assert real["FRASE"] not in texto and real["SHA"] not in texto and not any(d in texto for d in real["DEC"])
    out = {"escenario": escenario}
    try:
        V.modo_real(base / "e3_inexistente", base / "ventana_inexistente", aut, base / "salida_1", base / "manifiesto_prueba.json")
        out["termino"] = "sin excepción"
    except SystemExit as exc:
        out["termino"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    except BaseException as exc:
        out["termino"] = f"EXCEPCIÓN NO CONTROLADA {type(exc).__name__}: {str(exc)[:300]}"
    (base / "correr.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False))


def observar(v3, base):
    """Nueva instancia (otro proceso): estado en disco y decisión del orquestador sobre un nuevo intento."""
    V, real = cargar(v3, base, "v3_nueva_instancia")
    stubs(V, valido=True)
    obs = {"salida_1": {}, "registro": []}
    s1 = base / "salida_1"
    if s1.exists():
        for p in sorted(s1.iterdir()):
            b = p.read_bytes()
            info = {"sha256": sha_b(b), "bytes": len(b), "contiene_STUB": STUB.encode() in b}
            try:
                j = json.loads(b)
                info.update({k: j.get(k) for k in ("veredicto", "etapa", "estadisticos_iniciados") if k in j})
            except ValueError:
                info["json"] = "ilegible"
            obs["salida_1"][p.name] = info
    else:
        obs["salida_1"] = "NO EXISTE"
    led = base / "INTENTOS_E3.jsonl"
    obs["registro"] = led.read_text().splitlines() if led.exists() else "NO EXISTE"
    # ¿qué sha256 cita el registro y coincide con el archivo en disco?
    try:
        evs = [json.loads(x) for x in obs["registro"]] if isinstance(obs["registro"], list) else []
        res = s1 / "RESULTADO_E3.json"
        en_disco = sha_b(res.read_bytes()) if res.exists() else None
        obs["registro_vs_disco"] = [{"evento": e["evento"], "sha_resultado": e.get("sha_resultado"),
                                     "coincide_con_disco": e.get("sha_resultado") == en_disco}
                                    for e in evs if "sha_resultado" in e]
        errores = [e for e in evs if e["evento"] == "ERROR"]
    except ValueError as exc:
        obs["registro_vs_disco"] = f"registro ilegible: {exc}"
        errores = []
    # Nuevo intento con una autorización NUEVA (que, si hubo ERROR, cita su sha256 como exige la política).
    extra = f"REINTENTO TRAS ERROR {errores[-1]['sha_resultado']}" if errores else ""
    aut2 = autorizacion(V, base, "intento2", extra)
    try:
        V.modo_real(base / "e3_inexistente", base / "ventana_inexistente", aut2, base / "salida_2", base / "manifiesto_prueba.json")
        obs["nuevo_intento"] = "PERMITIDO: corrió completo"
    except SystemExit as exc:
        nombre = type(exc).__name__
        obs["nuevo_intento"] = ("RECHAZADO: " if nombre == "Rechazo" else f"PERMITIDO y terminó en {nombre}: ") + str(exc)[:250]
    except BaseException as exc:
        obs["nuevo_intento"] = f"EXCEPCIÓN NO CONTROLADA {type(exc).__name__}: {str(exc)[:250]}"
    s2 = base / "salida_2"
    obs["salida_2"] = sorted(p.name for p in s2.iterdir()) if s2.exists() else "NO EXISTE"
    (base / "observar.json").write_text(json.dumps(obs, ensure_ascii=False, indent=1))
    print(json.dumps(obs, ensure_ascii=False, indent=1))


def concurrencia(v3, base):
    """Un proceso retiene el bloqueo del registro; otro proceso intenta una ejecución."""
    import subprocess
    base.mkdir(parents=True, exist_ok=True)
    V, _ = cargar(v3, base, "v3_retiene_bloqueo")
    retenido = V.Intentos(V.INTENTOS)  # toma el flock exclusivo
    r = subprocess.run([sys.executable, "-B", "-I", __file__, "correr", str(v3), str(base), "B1_evaluado_sin_fallo"],
                       capture_output=True, text=True, timeout=120)
    retenido.cerrar()
    out = {"segundo_proceso": r.stdout.strip()[-300:], "salida_1_existe": (base / "salida_1").exists()}
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    accion, v3, base = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    if accion == "correr":
        correr(v3, base, sys.argv[4])
    elif accion == "observar":
        observar(v3, base)
    elif accion == "concurrencia":
        concurrencia(v3, base)
    else:
        raise SystemExit(__doc__)
