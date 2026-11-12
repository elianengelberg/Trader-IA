"""E3 · orquestador v3 de la ejecución confirmatoria ÚNICA de la v3 (H1 y H2) en la ventana A. NO autoriza ninguna ejecución.

Base: `ejecutar_E3_v2.py` (01fc9344…), derivado a su vez de `ejecutar_E3R.py` (3b64a04d…, congelado). El cálculo
(validez previa, H1, H2, Holm, robustez, descriptivo) es el del v2, con un único cambio: `zip(…, strict=True)` en
`contribuciones` (antes truncaba en silencio si las longitudes diferían). Cambios del v3 (diff en DIFF_v2_v3.diff):
  C7. Ventana A fijada en el código: inicio 2023-05-15 y sha256 del archivo de ventana. Cualquier otra se rechaza
      antes de crear la salida.
  C8. Entradas exigidas fijadas en el código (nombre, base, ruta, tipo y sha256). El manifiesto tiene que coincidir
      exactamente: uno vacío, incompleto, con entradas de más, repetidas o con otra ruta se rechaza. Los mapeos se
      leen SOLO de la entrada verificada `mapeos_adenda1_completa`.
  C9. Lectura única: cada insumo se lee una vez a memoria, se hashea y se usa desde esos mismos bytes (series, JSON
      y módulos). No hay una segunda lectura de disco entre verificar y usar. Se rechazan enlaces simbólicos.
  C10. Código ejecutado = código verificado: universo, motor e inferencia se compilan y ejecutan desde los bytes
      verificados, nunca con `import` desde disco ni desde `__pycache__`. El sha256 del propio orquestador se toma de
      los bytes leídos al cargarlo.
  C11. Estados terminales: antes de crear la salida, todo fallo es un rechazo que NO consume la ejecución. Después,
      cualquier excepción deja RESULTADO_E3.json con «ERROR» (etapa, tipo, mensaje, traceback y su sha256, y si ya
      había estadísticos), escrito de forma atómica. Un registro de intentos con bloqueo (INTENTOS_E3.jsonl) impide
      repetir después de EVALUADO o INVALIDO, o con un intento sin estado terminal. Para reintentar después de un
      ERROR previo a los estadísticos exige una autorización nueva que cite el sha256 del RESULTADO con ERROR.
  C12. Mapeos completos de la Adenda 1: reglas 1, 2 y 1R (reutilización de ticker: el tramo posterior es un listado
      nuevo). Se rechazan duplicados, huecos ≥ 30 días en la regla 1 y cualquier cambio en las marcas de lista fija o
      de apalancado. La consistencia de los mapeos se comprueba ANTES de crear la salida, leyendo solo `estado`.
  C13. Además de la FRASE y de los sha256 del orquestador y del manifiesto, la autorización tiene que contener las
      frases de las decisiones metodológicas que el código no puede tomar por sí mismo: reapertura y Adenda R, y
      lectura literal D-1.
Operacionalizaciones fijadas antes de cualquier resultado, heredadas del v1 (ninguna cambia una clasificación):
  - R5: la réplica b usa la semilla 20261021 + b. Diagnóstico §5.4: bootstrap con semilla 20261027 y B = 999 en cada réplica.
  - §6.4 «al anular esos aportes»: IC̄ recalculado sin las monedas con marca obsoleta en t+6; ē recalculado sin las semanas
    con una liquidación contable o una posición sin apertura en t+7, en la cartera o en EW-U30. Etiqueta si cambia un signo.
  - Sharpe deflactado: V[SR] sobre los 20 excesos calculados (15 de la grilla, R1, R2, R4, R6 y el bruto).
  - BTC: la fila BTCUSDT del mismo panel de Vision (no `research/tendencia_btc/datos/`, N20): misma fuente que la cartera.
  - Exceso de timing de T (N19): NO se calcula; T no se reabre (regla vigente del proyecto).

Modos:
  sintetico <salida_dir> <momentum> [replicas_R5] [dir_ejecucion_E3]
      Panel sintético de `pruebas_motor.panel_sintetico` (sin datos reales). Prueba el camino completo.
  real <dir_ejecucion_E3> <ventana_A_pasada2.json> <autorizacion.txt> <salida_dir>
      SOLO con autorización explícita posterior. La salida no puede existir (ejecución única).
"""
import datetime as dt
import fcntl
import hashlib
import io
import json
import math
import os
import sys
import traceback
import types
from pathlib import Path
from statistics import NormalDist

import numpy as np

sys.dont_write_bytecode = True  # no escribir cachés en ningún directorio
_BYTES_PROPIOS = Path(__file__).read_bytes()  # C10: los bytes de este archivo, leídos una vez al cargarlo
SHA_PROPIO = hashlib.sha256(_BYTES_PROPIOS).hexdigest()
AQUI = Path(__file__).resolve().parent
E3_DEFECTO = AQUI.parent.parent / "experimentos" / "E3_seleccion_posicion_2026-10-19" / "ejecucion_E3"
REPARACION = AQUI.parent.parent / "reparacion_E3H1H2_2026-10-26"
CIERRE = AQUI.parent
MANIFIESTO = AQUI / "ENTRADAS_CONGELADAS_V3.json"
INTENTOS = AQUI / "INTENTOS_E3.jsonl"
CONGELADOS = {"universo.py": "@@universo.py@@",
              "motor.py": "@@motor.py@@",
              "inferencia.py": "@@inferencia.py@@"}
PRUEBAS_MOTOR = "@@pruebas_motor.py@@"  # HUELLAS_codigo_preparado.txt
INICIO_H_A = "2023-05-15"  # C7
SHA_VENTANA_A = "@@ventana_A@@"
EXIGIDAS = {  # C8: nombre → (base, ruta, tipo, sha256)
    "series_calidad_757": ("E3", "resultados/calidad/series", "conjunto", "@@series_calidad_757@@"),
    "estructural": ("E3", "resultados/estructural/estructural.json", "archivo", "@@estructural@@"),
    "listas_fijas_por_lunes": ("E3", "resultados/estructural/listas_fijas_por_lunes.json", "archivo", "@@listas_fijas_por_lunes@@"),
    "universo.py": ("E3", "codigo/universo.py", "archivo", CONGELADOS["universo.py"]),
    "motor.py": ("E3", "codigo/motor.py", "archivo", CONGELADOS["motor.py"]),
    "inferencia.py": ("E3", "codigo/inferencia.py", "archivo", CONGELADOS["inferencia.py"]),
    "pruebas_motor.py": ("E3", "codigo/pruebas_motor.py", "archivo", PRUEBAS_MOTOR),
    "conciliacion.py": ("E3", "codigo/conciliacion.py", "archivo", "@@conciliacion.py@@"),
    "resoluciones_manuales": ("reparacion", "segunda_pasada/resoluciones_manuales.json", "archivo", "@@resoluciones_manuales@@"),
    "pasada2_conciliacion": ("reparacion", "segunda_pasada/salida_pasada2/conciliacion.json", "archivo", "@@pasada2_conciliacion@@"),
    "pasada2_eventos": ("reparacion", "segunda_pasada/salida_pasada2/eventos.json", "archivo", "@@pasada2_eventos@@"),
    "pasada2_salidas": ("reparacion", "segunda_pasada/salida_pasada2/salidas.json", "archivo", "@@pasada2_salidas@@"),
    "eventos_omitidos": ("reparacion", "segunda_pasada/eventos_omitidos.json", "archivo", "@@eventos_omitidos@@"),
    "mapeos_adenda1_completa": ("cierre", "tabla/mapeos_adenda1_completa.json", "archivo", "@@mapeos_adenda1_completa@@"),
    "ventana_A": ("ventana", None, "archivo", SHA_VENTANA_A),
}
FRASE = ("AUTORIZO LA EJECUCION UNICA DE E3 (H1 Y H2) EN LA VENTANA A (INICIO 2023-05-15) CON LA V3, LA ADENDA R CON R1 "
         "LITERAL, LA SEGUNDA PASADA, LA TABLA COMPLETA DE LA ADENDA 1 Y EL ORQUESTADOR V3")
FRASES_DECISION = {  # C13: decisiones metodológicas que tienen que figurar expresamente en la autorización
    "reapertura_y_adenda_R": ("REABRO E3 (CIERRE_E3 §2), ADOPTO LA ADENDA R CON R1 LITERAL EN LUGAR DE V3 §4.11 (II) Y (IV), "
                              "SIN (III), Y DISPENSO LA CONDICION DE REAPERTURA DE CIERRE_E3 §4"),
    "D1_lectura_literal": "DECISION D-1: LECTURA LITERAL DE LA REGLA 1 (SIN CONTINUIDAD GTO->GFT, LUNA->LUNC NI UST->USTC)",
}
ETAPAS_SIN_ESTADISTICOS = ("panel", "validez_previa")  # C11: un ERROR en estas etapas no expuso H1 ni H2
ULTIMA_FORMACION = dt.date(2026, 5, 18)
ULTIMO_DIA_DATOS = dt.date(2026, 5, 31)
SEMILLA_H2, SEMILLA_R5, SEMILLA_CORTES, SEMILLA_DIAG = 20261020, 20261021, 20261022, 20261027
DELTA_IC = 0.01
_N = NormalDist()


class Rechazo(SystemExit):
    """Detención ANTES de crear la salida: no se leyó ningún precio y no se consume la ejecución única."""


class FinTerminal(SystemExit):
    """Estado terminal ya escrito (INVALIDO o ERROR): no se reescribe."""


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ------------------------------------------------------------------ C10: código desde bytes verificados

ORDEN_MODULOS = ("universo", "motor", "inferencia", "pruebas_motor")


def cargar_modulos(fuentes: dict) -> dict:
    """Compila y ejecuta cada módulo desde sus bytes verificados, en orden de dependencia, y lo registra en
    sys.modules antes del siguiente (motor hace `from universo import …`). No busca nada en disco: ni el .py ni
    `__pycache__`."""
    mods = {}
    for nombre in ORDEN_MODULOS:
        if nombre not in fuentes:
            continue
        virtual = f"<verificado:{nombre}.py:{sha_bytes(fuentes[nombre])[:12]}>"
        codigo = compile(fuentes[nombre], virtual, "exec", dont_inherit=True)
        m = types.ModuleType(nombre)
        m.__file__ = virtual
        sys.modules[nombre] = m
        exec(codigo, m.__dict__)
        mods[nombre] = m
    return mods


def importar_congelados(e3: Path):
    """Modo sintético: lee los módulos de E3 una vez, verifica su sha256 y los carga desde esos mismos bytes."""
    cod = Path(e3) / "codigo"
    fuentes = {}
    for nombre, h in {**CONGELADOS, "pruebas_motor.py": PRUEBAS_MOTOR}.items():
        b = (cod / nombre).read_bytes()
        if sha_bytes(b) != h:
            raise Rechazo(f"{nombre} no coincide con su hash congelado: no se ejecuta")
        fuentes[nombre[:-3]] = b
    mods = cargar_modulos(fuentes)
    return mods["universo"], mods["motor"], mods["inferencia"]


# ------------------------------------------------------------------ C8 + C9: insumos leídos una vez y verificados

def _leer_archivo(p) -> bytes:
    p = Path(p)
    if p.is_symlink():
        raise ValueError(f"{p} es un enlace simbólico")
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return p.read_bytes()


def _leer_conjunto(d) -> dict:
    d = Path(d)
    if d.is_symlink() or not d.is_dir():
        raise FileNotFoundError(f"{d} no es un directorio real")
    out = {}
    for raiz, dirs, archivos in os.walk(d, followlinks=False):
        for n in dirs + archivos:
            if Path(raiz, n).is_symlink():
                raise ValueError(f"{Path(raiz, n)} es un enlace simbólico")
        for n in archivos:
            p = Path(raiz, n)
            out[p.relative_to(d).as_posix()] = p.read_bytes()
    return out


def hash_conjunto_bytes(conj: dict) -> str:
    """Receta de CIERRE_E3 (sha256 de `find . -type f -print0 | sort -z | xargs -0 sha256sum`), sobre bytes en memoria."""
    rel = sorted(("./" + r for r in conj), key=lambda r: r.encode())
    return hashlib.sha256("".join(f"{sha_bytes(conj[r[2:]])}  {r}\n" for r in rel).encode()).hexdigest()


def hash_conjunto(d: Path) -> str:
    """La misma receta, leyendo del directorio (pruebas y generación del manifiesto)."""
    return hash_conjunto_bytes(_leer_conjunto(d))


def leer_y_verificar(manifiesto_bytes: bytes, raices: dict) -> dict:
    """C8: el manifiesto tiene que coincidir EXACTAMENTE con EXIGIDAS (nombre, base, ruta, tipo y sha256).
    C9: cada insumo se lee una sola vez y se devuelven esos bytes, que son los únicos que se usan después."""
    try:
        m = json.loads(manifiesto_bytes)
    except ValueError as exc:
        raise Rechazo(f"manifiesto ilegible ({exc}). No se lee ningún precio.") from exc
    entradas = m.get("entradas") if isinstance(m, dict) else None
    if not isinstance(entradas, list) or not entradas:
        raise Rechazo("manifiesto vacío o sin lista de entradas. No se lee ningún precio.")
    nombres = [x.get("nombre") if isinstance(x, dict) else None for x in entradas]
    if None in nombres or len(set(nombres)) != len(nombres):
        raise Rechazo("manifiesto con entradas repetidas o mal formadas. No se lee ningún precio.")
    faltan, sobran = sorted(set(EXIGIDAS) - set(nombres)), sorted(set(nombres) - set(EXIGIDAS))
    if faltan or sobran:
        raise Rechazo(f"manifiesto incompleto o con entradas de más (faltan {faltan}; sobran {sobran}). No se lee ningún precio.")
    distintas = [x["nombre"] for x in entradas
                 if (x.get("base"), x.get("ruta"), x.get("tipo"), x.get("sha256")) != EXIGIDAS[x["nombre"]]]
    if distintas or m.get("inicio_H_esperado") != INICIO_H_A:
        raise Rechazo(f"manifiesto distinto del fijado en el código: {distintas or ['inicio_H_esperado']}. No se lee ningún precio.")
    datos, malos = {}, {}
    for nombre, (base, ruta, tipo, h) in EXIGIDAS.items():
        p = raices[base] if base == "ventana" else Path(raices[base]) / ruta
        try:
            contenido = _leer_conjunto(p) if tipo == "conjunto" else _leer_archivo(p)
        except (OSError, ValueError) as exc:
            malos[nombre] = f"ilegible: {exc}"
            continue
        obs = hash_conjunto_bytes(contenido) if tipo == "conjunto" else sha_bytes(contenido)
        if obs != h:
            malos[nombre] = {"esperado": h, "observado": obs}
        datos[nombre] = contenido
    if malos:
        raise Rechazo(f"insumos que no coinciden con lo fijado en el código: {malos}. No se lee ningún precio.")
    return datos


# ------------------------------------------------------------------ panel real (solo con autorización), desde bytes

def _npz(b: bytes):
    return np.load(io.BytesIO(b), allow_pickle=False)


def _series(datos: dict) -> list:
    s = datos["series_calidad_757"]
    raras = [r for r in s if "/" in r or not r.endswith(".npz")]
    if raras:
        raise Rechazo(f"el conjunto de series contiene archivos que no son series: {sorted(raras)[:5]}")
    return [s[r] for r in sorted(s)]


def actividad_desde_bytes(datos: dict):
    """Solo `simbolo` y `estado`, nunca O, H, L, C ni QV: comprueba los mapeos antes de crear la salida."""
    syms, act = [], []
    for b in _series(datos):
        z = _npz(b)
        syms.append(str(z["simbolo"]))
        act.append(z["estado"] == 1)
    return syms, np.array(act)


def panel_real(datos: dict, universo, mapeos):
    """Series de calidad de E3 desde los bytes verificados: act = estado == 1. Aplica los mapeos de la Adenda 1 (C12)."""
    syms, O, C, QV, act = [], [], [], [], []
    for b in _series(datos):
        z = _npz(b)
        syms.append(str(z["simbolo"]))
        O.append(z["O"]), C.append(z["C"]), QV.append(z["QV"]), act.append(z["estado"] == 1)
    O, C, QV, act = (np.array(x) for x in (O, C, QV, act))
    syms2, O, C, QV, act, registro, origen = aplicar_mapeos(syms, O, C, QV, act, mapeos, universo.INICIO)
    comprobar_marcas(syms, syms2, origen, universo)
    P = universo.Panel(syms2, O, C, QV, act, mapeos_renombre=registro)
    antes = marcas(syms, universo)
    for k, org in enumerate(origen):  # contra lo que el propio universo.Panel infirió
        if (bool(P.fijo[k]), bool(P.apalancado[k])) != antes[org[0]]:
            raise RuntimeError(f"{syms2[k]}: universo.Panel cambió la marca de lista fija o de apalancado")
    return P, registro


def marcas(syms, universo) -> dict:
    """Las marcas que universo.Panel deriva SOLO del nombre (líneas de `apalancado` y `fijo`), por símbolo."""
    base = [universo.base_de(s) for s in syms]
    bases = set(base)
    return {s: (b in universo.LISTA_FIJA, any(b.endswith(suf) and b[:-len(suf)] in bases for suf in ("UP", "DOWN", "BULL", "BEAR")))
            for s, b in zip(syms, base)}


def comprobar_marcas(syms, syms2, origen, universo):
    """C12: ningún mapeo puede cambiar la marca de lista fija o de apalancado de una fila (por ejemplo, retirar la base
    de un token apalancado, o fusionar X e Y con marcas distintas)."""
    antes, despues = marcas(syms, universo), marcas(syms2, universo)
    malos = []
    for s2, org in zip(syms2, origen):
        esperadas = {antes[o] for o in org}
        if len(esperadas) != 1 or despues[s2] not in esperadas:
            malos.append({"fila": s2, "origen": list(org), "antes": sorted(esperadas), "despues": despues[s2]})
    if malos:
        raise Rechazo(f"los mapeos cambian marcas de lista fija o de apalancado: {malos[:5]}")


def aplicar_mapeos(syms, O, C, QV, act, mapeos, inicio):
    """Adenda 1 (v3 §2.2.4; §4.10 «renombre mapeado»), reglas 1, 1R y 2, en orden de fecha. r = unidades nuevas por
    unidad vieja. QV está en USDT y no cambia.
    Regla 2 (X → X): los precios de X anteriores a la reapertura (primer día activo > E) se dividen por r. La serie queda
      continua a través de r y las unidades de una posición, multiplicadas por r. Edad y listado no cambian.
    Regla 1 (X → Y): Y continúa a X en la fila de X: historia de X con precios / r hasta su último día activo y, desde el
      primer día activo de Y, los datos de Y. La fila pasa a llamarse Y (hereda edad y posiciones) y la fila original de Y
      se retira. Aborta si falta X o Y, si X vuelve a estar activo después de E, si Y estuvo activo antes del cese de X,
      o si el hueco entre ambos es ≥ 30 días (la regla mecánica de 30 días reiniciaría la edad que la regla 1 hereda).
    Regla 1R (reutilización del ticker X; Adenda 1, regla 1, última oración): desde `reutilizacion_desde` la fila X es un
      listado nuevo (otro activo). El tramo anterior pasa a una fila propia «X~HASTAaaaammddUSDT», que termina en su
      último día activo. Exige un corte de negociación que termine justo en esa fecha.
    Rechaza mapeos repetidos o de regla desconocida. Devuelve también el origen de cada fila final."""
    vistos = set()
    for m in mapeos:
        clave = (m.get("regla"), m.get("viejo_usdt"), m.get("nuevo_usdt"), m.get("E"), m.get("reutilizacion_desde"))
        if m.get("regla") not in (1, 2, "1R"):
            raise Rechazo(f"regla desconocida en la tabla de mapeos: {m}")
        if clave in vistos:
            raise Rechazo(f"mapeo repetido: {clave}")
        vistos.add(clave)
    syms, origen = list(syms), [(s,) for s in syms]
    O, C, QV, act = O.copy(), C.copy(), QV.copy(), act.copy()
    retirar, registro, extra = [], [], []

    def fecha(m):
        return m["reutilizacion_desde"] if m["regla"] == "1R" else m["E"]

    for m in sorted(mapeos, key=lambda m: (fecha(m), str(m["regla"]))):
        x = m["viejo_usdt"]
        if x not in syms:
            raise Rechazo(f"mapeo imposible: {x} no está en el panel")
        i = syms.index(x)
        if m["regla"] == "1R":
            k = (dt.date.fromisoformat(m["reutilizacion_desde"]) - inicio).days
            antes = np.flatnonzero(act[i, :k])
            if not 0 < k < act.shape[1] or not act[i, k] or antes.size == 0 or k - int(antes[-1]) < 2:
                raise Rechazo(f"{x}: no hay un corte que termine el {m['reutilizacion_desde']}; no se divide la serie")
            L = int(antes[-1])
            nombre = f"{x[:-4]}~HASTA{inicio + dt.timedelta(days=L):%Y%m%d}USDT"
            if nombre in syms:
                raise Rechazo(f"{nombre} ya existe en el panel")
            fila = [a[i].copy() for a in (O, C, QV, act)]
            for a in fila[:3]:
                a[k:] = np.nan
            fila[3][k:] = False
            O[i, :k], C[i, :k], QV[i, :k], act[i, :k] = np.nan, np.nan, np.nan, False
            extra.append((nombre, fila, origen[i]))
            registro.append({**m, "fila_listado_nuevo": x, "fila_tramo_anterior": nombre,
                             "ultimo_activo_tramo_anterior": (inicio + dt.timedelta(days=L)).isoformat()})
            continue
        y, r = m["nuevo_usdt"], float(m["r"])
        if y not in syms or not (r > 0 and math.isfinite(r)):
            raise Rechazo(f"mapeo imposible: {x} → {y} (r = {m['r']})")
        e = (dt.date.fromisoformat(m["E"]) - inicio).days
        if m["regla"] == 2:
            if x != y:
                raise Rechazo(f"regla 2 con símbolos distintos: {x} → {y}")
            despues = np.flatnonzero(act[i, e + 1:])
            if despues.size == 0:
                raise Rechazo(f"{x}: no hay reapertura después de {m['E']}")
            k = e + 1 + int(despues[0])
            antes = np.flatnonzero(act[i, :e + 1])
            if antes.size == 0 or k - int(antes[-1]) < 2:
                raise Rechazo(f"{x}: no hay un corte de negociación alrededor de E = {m['E']}; no se aplica r")
            O[i, :k] /= r
            C[i, :k] /= r
            registro.append({**m, "fila": x, "dia_reapertura": (inicio + dt.timedelta(days=k)).isoformat()})
            continue
        j = syms.index(y)
        activos_x = np.flatnonzero(act[i])
        if activos_x.size == 0 or activos_x[-1] > e:
            raise Rechazo(f"{x}: sin actividad o activo después de E = {m['E']}; no se mapea")
        activos_y = np.flatnonzero(act[j])
        if activos_y.size == 0 or activos_y[0] <= activos_x[-1]:
            raise Rechazo(f"{y}: sin actividad o activo antes del cese de {x}; no se mapea")
        k = int(activos_y[0])
        if k - int(activos_x[-1]) - 1 >= 30:
            raise Rechazo(f"{x} → {y}: hueco de {k - int(activos_x[-1]) - 1} días (≥ 30); la regla 1 no puede heredar la edad")
        O[i, :k], C[i, :k] = O[i, :k] / r, C[i, :k] / r
        O[i, k:], C[i, k:], QV[i, k:], act[i, k:] = O[j, k:], C[j, k:], QV[j, k:], act[j, k:]
        syms[i], syms[j] = y, f"#retirada:{y}"
        origen[i] = origen[i] + origen[j]
        retirar.append(j)
        registro.append({**m, "fila": y, "ultimo_activo_viejo": (inicio + dt.timedelta(days=int(activos_x[-1]))).isoformat(),
                         "primer_activo_nuevo": (inicio + dt.timedelta(days=k)).isoformat()})
    quedan = [s for s in range(len(syms)) if s not in set(retirar)]
    syms_f = [syms[s] for s in quedan] + [n for n, _, _ in extra]
    origen_f = [origen[s] for s in quedan] + [o for _, _, o in extra]
    O, C, QV, act = (np.vstack([A[quedan]] + [f[q][None, :] for _, f, _ in extra]) for q, A in enumerate((O, C, QV, act)))
    return syms_f, O, C, QV, act, registro, origen_f


