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
CONGELADOS = {"universo.py": "2af45115238d0065d54f0c6230b16c71831293b235b72627e62d1d7c7d7491f7",
              "motor.py": "cadb805d2d882fcf909e0309cff85203ee383c6b8ed0ac08b89f4028ee999b2e",
              "inferencia.py": "7b28038621c1d366655d726bb885ca0105f1a25cfcdb9615e86a7fe39e85f3e1"}
PRUEBAS_MOTOR = "54f832d39422379f14bf5d0ad2f42bba9e8f0b4d40915ea72bcef0c968da04e5"  # HUELLAS_codigo_preparado.txt
INICIO_H_A = "2023-05-15"  # C7
SHA_VENTANA_A = "dcbd80abf5b0d4a2373d411c3db37cf4a2089dc8fcbcb193dce085b838d57e24"
EXIGIDAS = {  # C8: nombre → (base, ruta, tipo, sha256)
    "series_calidad_757": ("E3", "resultados/calidad/series", "conjunto", "6506fb03c211def710abe61a2493799000b80996c63000fcfc98da624cbaba79"),
    "estructural": ("E3", "resultados/estructural/estructural.json", "archivo", "14838dadec428483c91bf57abd1db6916d473bffe4e789ecbdd394de6351ec55"),
    "listas_fijas_por_lunes": ("E3", "resultados/estructural/listas_fijas_por_lunes.json", "archivo", "de6cca7735016e2734bfc53cab27eea89e765a763ab240789b609ba55a24a620"),
    "universo.py": ("E3", "codigo/universo.py", "archivo", CONGELADOS["universo.py"]),
    "motor.py": ("E3", "codigo/motor.py", "archivo", CONGELADOS["motor.py"]),
    "inferencia.py": ("E3", "codigo/inferencia.py", "archivo", CONGELADOS["inferencia.py"]),
    "pruebas_motor.py": ("E3", "codigo/pruebas_motor.py", "archivo", PRUEBAS_MOTOR),
    "conciliacion.py": ("E3", "codigo/conciliacion.py", "archivo", "6f764845598b4ecf6c3cffbc6c7b584f21e493403c7bcd14339f5f582c9273ad"),
    "resoluciones_manuales": ("reparacion", "segunda_pasada/resoluciones_manuales.json", "archivo", "41a13221dea70023126ce3fb6c311c9f41e2aef063820207c1f7e871d2873863"),
    "pasada2_conciliacion": ("reparacion", "segunda_pasada/salida_pasada2/conciliacion.json", "archivo", "7a0778e8c0ac55697cca3d0fd81da1a055e3a6700c06ca1d6867e905971e6456"),
    "pasada2_eventos": ("reparacion", "segunda_pasada/salida_pasada2/eventos.json", "archivo", "dbd5a85dd265e84e94d678636c4714ae0189d1800faf9c13c52f15ccda3808c6"),
    "pasada2_salidas": ("reparacion", "segunda_pasada/salida_pasada2/salidas.json", "archivo", "9c6fd418b3fee0236e63865c126228201654d46dff19a438007eea6354a0ec2e"),
    "eventos_omitidos": ("reparacion", "segunda_pasada/eventos_omitidos.json", "archivo", "823b30965a273f3e367c6d03abb45ed1b1b890fc90b2a7c5feb34f46b7562e12"),
    "mapeos_adenda1_completa": ("cierre", "tabla/mapeos_adenda1_completa.json", "archivo", "bd07e7f9654c4f73b1205d11382a14fa7f5f87122bc350d2726906dcc1ee400a"),
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


# ------------------------------------------------------------------ validez previa (v3 §10), sin estadísticos

def validez_previa(P, formaciones, universo, motor):
    """§10.8 bloqueo de fechas; §10.7 semanas evaluables; §10.5 invariancia al truncar (como pruebas_motor, sobre P)."""
    out = {"ultimo_dia_panel": (universo.INICIO + dt.timedelta(days=P.D - 1)).isoformat()}
    out["bloqueo_fechas"] = universo.INICIO + dt.timedelta(days=P.D - 1) <= ULTIMO_DIA_DATOS
    cache = {}
    ev = []
    for t in formaciones[:-1]:
        U = universo.universo(P, t)
        cache[(t, 30, (7, 14, 21, 28), frozenset())] = U
        ev.append(U is not None and U.get("n_elegibles", 0) >= 30)
    out["semanas"], out["evaluables"] = len(ev), int(sum(ev))
    out["no_evaluables_pct"] = round(100 * (len(ev) - sum(ev)) / len(ev), 1) if ev else None
    out["semanas_ok"] = sum(ev) >= 156 and out["no_evaluables_pct"] <= 20.0
    rng = np.random.default_rng(SEMILLA_CORTES)
    base = motor.simular(P, formaciones, motor.Config(), cache, registrar_pesos=True)
    cortes = []
    for c in sorted(rng.choice(np.arange(formaciones[20], formaciones[-10]), size=5, replace=False)):
        P2 = universo.Panel(P.sym, P.O.copy(), P.C.copy(), P.QV.copy(), P.act.copy())
        P2.O[:, c:] *= rng.uniform(0.2, 5, (P.S, 1))
        P2.C[:, c:] *= rng.uniform(0.2, 5, (P.S, 1))
        P2.QV[:, c:] = rng.uniform(0, 1e8, P2.QV[:, c:].shape)
        P2.act[:, c:] = rng.random(P2.act[:, c:].shape) < 0.5
        P2.C[:, c:] = np.where(P2.act[:, c:], P2.C[:, c:], np.nan)
        P2._derivados()
        F2 = [t for t in formaciones if t < c - 7]
        r2 = motor.simular(P2, F2 + [F2[-1] + 7], motor.Config(), {}, registrar_pesos=True)
        ok_u = all((a is None and b is None) or (a["U_inv"] == b["U_inv"] and a["U_pred"] == b["U_pred"]
                                                  and np.allclose(a["S"], b["S"]) and a["rk"] == b["rk"])
                   for a, b in zip(base["univs"][:len(F2)], r2["univs"][:len(F2)], strict=False))
        ok_o = base["objetivos"][:len(r2["objetivos"]) - 1] == r2["objetivos"][:-1]
        ok_p = all(set(a[1]) == set(b[1]) and all(abs(a[1][s] - b[1][s]) < 1e-12 for s in a[1])
                   for a, b in zip(base["pesos"][:len(F2)], r2["pesos"][:len(F2)], strict=False))
        cortes.append({"corte": (universo.INICIO + dt.timedelta(days=int(c))).isoformat(), "universos_y_senal": ok_u,
                       "objetivos": ok_o, "pesos": ok_p})
    out["invariancia_truncado"] = cortes
    out["invariancia_ok"] = all(x["universos_y_senal"] and x["objetivos"] and x["pesos"] for x in cortes)
    out["valido"] = bool(out["bloqueo_fechas"] and out["semanas_ok"] and out["invariancia_ok"])
    return out, cache


# ------------------------------------------------------------------ cálculo (idéntico en los dos modos)

def contribuciones(P, sim, formaciones, sim_ew):
    """R4 (N14): aporte_c = Σ_t w_{c,t} · (r_{c,t} − r_{EW,t}), bruto; r_{c,t} de apertura a apertura de la semana."""
    aporte = {}
    r_ew = dict(zip(formaciones[:-1], sim_ew["r"], strict=True))
    for t, pesos in sim["pesos"]:
        if t not in r_ew:
            continue
        for s, w in pesos.items():
            p0 = P.O[s, t] if P.act[s, t] else P.pval(s, t - 1)
            p1 = P.O[s, t + 7] if t + 7 < P.D and P.act[s, t + 7] else P.pval(s, min(t + 6, P.D - 1))
            if p0 and np.isfinite(p0) and np.isfinite(p1):
                aporte[s] = aporte.get(s, 0.0) + w * ((p1 / p0 - 1) - r_ew[t])
    return aporte


def exceso(sim, sim_ew):
    ev = sim["evaluable"] & sim_ew["evaluable"]
    return (sim["r"] - sim_ew["r"])[ev]


def intervalos(e, inferencia):
    """Los tres métodos de la regla del máximo; IC90 = envolvente (Enmienda 2, E2.2)."""
    b13 = inferencia.bootstrap_t(e, ell=13, B=9999, semilla=SEMILLA_H2)
    b26 = inferencia.bootstrap_t(e, ell=26, B=9999, semilla=SEMILLA_H2)
    nw = inferencia.newey_west(e, L=13)
    ic90 = (min(b13["ic90"][0], b26["ic90"][0], nw["ic90"][0]), max(b13["ic90"][1], b26["ic90"][1], nw["ic90"][1]))
    return b13, b26, nw, ic90


def p_h2(e, inferencia):
    b13, b26, nw, ic90 = intervalos(e, inferencia)
    p = max(b13["p_unilateral"], b26["p_unilateral"], nw["p_unilateral"])
    return {"p": p, "p_boot13": b13["p_unilateral"], "p_boot26": b26["p_unilateral"], "p_nw13": nw["p_unilateral"],
            "media_semanal": float(e.mean()), "anual": 52 * float(e.mean()), "ic90_semanal": ic90,
            "ic90_anual": (52 * ic90[0], 52 * ic90[1]), "n": int(e.size)}


def tercios(x):
    k = len(x) // 3
    return [x[:k], x[k:2 * k], x[2 * k:]]


def metricas(r):
    """Descriptivo §6.2 sobre retornos semanales (semanas evaluables)."""
    r = np.asarray(r, dtype=float)
    if r.size < 2:
        return None
    W = np.cumprod(1 + r)
    dd = W / np.maximum.accumulate(W) - 1
    bajo, racha = 0, 0
    for x in dd:
        racha = racha + 1 if x < 0 else 0
        bajo = max(bajo, racha)
    sd = float(np.std(r, ddof=1))
    neg = r[r < 0]
    cola = np.sort(r)[:max(1, int(math.ceil(0.05 * r.size)))]
    return {"semanas": int(r.size), "cagr": float(W[-1] ** (52 / r.size) - 1), "vol_anual": sd * math.sqrt(52),
            "sharpe_anual": float(r.mean() / sd * math.sqrt(52)) if sd > 0 else None,
            "sortino_anual": float(r.mean() / np.sqrt(np.mean(np.minimum(r, 0) ** 2)) * math.sqrt(52)) if neg.size else None,
            "caida_maxima": float(dd.min()), "cvar5_semanal": float(cola.mean()), "peor_semana": float(r.min()),
            "semanas_bajo_el_agua_max": bajo}


def sharpe_deflactado(e, sharpes):
    """N18 (Bailey y López de Prado, 2014): N = 20 configuraciones; V[SR] de los Sharpe semanales de sus excesos."""
    e = np.asarray(e, dtype=float)
    n, sr = e.size, float(e.mean() / e.std(ddof=1))
    g3 = float(np.mean((e - e.mean()) ** 3) / e.std() ** 3)
    g4 = float(np.mean((e - e.mean()) ** 4) / e.std() ** 4)
    N, v = 20, float(np.var(sharpes, ddof=1))
    gamma = 0.5772156649015329
    sr0 = math.sqrt(v) * ((1 - gamma) * _N.inv_cdf(1 - 1 / N) + gamma * _N.inv_cdf(1 - 1 / (N * math.e)))
    den = math.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2, 1e-12))
    return {"sr_semanal": sr, "sr0_semanal": sr0, "N": N, "V_SR": v, "asimetria": g3, "curtosis": g4,
            "dsr": _N.cdf((sr - sr0) * math.sqrt(n - 1) / den), "configuraciones_en_V": len(sharpes)}


def precio_val(P, s, d):
    return P.O[s, d] if P.act[s, d] else P.pval(s, d - 1)


def exposicion_y_rotacion(P, sim, formaciones):
    """Exposición = Σ pesos tras operar; rotación de un sentido = ½ Σ |w_post − w_pre| (pre = post anterior con deriva)."""
    expo, rot, entradas = [], [], []
    prev, obj_prev = None, None
    objetivos = dict(sim["objetivos"])
    for j, (t, w) in enumerate(sim["pesos"][:-1]):
        if not w:
            prev = None
            continue
        expo.append(sum(w.values()))
        if prev is not None:
            t0, w0 = prev
            crec = {s: precio_val(P, s, t) / precio_val(P, s, t0) for s in w0}
            Wn = (1 - sum(w0.values())) + sum(w0[s] * crec[s] for s in w0)
            pre = {s: w0[s] * crec[s] / Wn for s in w0}
            rot.append(0.5 * sum(abs(w.get(s, 0.0) - pre.get(s, 0.0)) for s in set(w) | set(pre)))
        T = set(objetivos.get(t, []))
        if obj_prev is not None:
            entradas.append(len(T - obj_prev))
        prev, obj_prev = (t, w), T
    return {"exposicion_media": float(np.mean(expo)) if expo else None,
            "rotacion_semanal_media": float(np.mean(rot)) if rot else None,
            "rotacion_anual": 52 * float(np.mean(rot)) if rot else None,
            "entradas_por_semana": float(np.mean(entradas)) if entradas else None,
            "operaciones_estimadas": int(2 * sum(entradas))}


def diagnostico_6_4(P, formaciones, ic, cache, base, ew, e, ic_medio, universo):
    """§6.4: conteos y efecto de anular los aportes (operacionalización fijada en el encabezado)."""
    sin_obs = []
    for t, v, _, _ in ic:
        if not np.isfinite(v):
            continue
        U = cache.get((t, 30, (7, 14, 21, 28), frozenset())) or universo.universo(P, t)
        up = np.array(U["U_pred"])
        m = np.array([bool(P.act[s, t + 6]) for s in up])
        y = np.array([math.log(P.pval(s, t + 6) / P.C[s, t - 1]) for s in up[m]])
        sin_obs.append(universo.spearman(np.asarray(U["S"])[m], y))
    ic_sin = float(np.nanmean(sin_obs)) if sin_obs else float("nan")
    dias = list(formaciones)
    con_evento = np.zeros(len(dias) - 1, dtype=bool)
    for sim in (base, ew):
        for _, d, _ in sim["eventos"]["liquidaciones"]:
            j = np.searchsorted(dias, d, side="right") - 1
            if 0 <= j < con_evento.size:
                con_evento[j] = True
        for j, (t, w) in enumerate(sim["pesos"][:-1]):
            if any(t + 7 < P.D and not P.act[s, t + 7] for s in w):
                con_evento[j] = True
    ev = base["evaluable"] & ew["evaluable"]
    e_sin = (base["r"] - ew["r"])[ev & ~con_evento]
    e_sin_media = float(e_sin.mean()) if e_sin.size else float("nan")
    return {"liquidaciones_estrategia": len(base["eventos"]["liquidaciones"]),
            "liquidaciones_ew": len(ew["eventos"]["liquidaciones"]),
            "marcas_obsoletas_H1": int(sum(x[3] for x in ic)),
            "compras_omitidas": base["eventos"]["compras_omitidas"], "ventas_diferidas": base["eventos"]["ventas_diferidas"],
            "ic_medio_sin_marcas_obsoletas": ic_sin, "semanas_h2_con_evento": int((ev & con_evento).sum()),
            "exceso_medio_sin_semanas_con_evento": e_sin_media,
            "etiqueta_dependiente": bool(np.sign(ic_sin) != np.sign(ic_medio) or np.sign(e_sin_media) != np.sign(e.mean()))}


def ejecutar(P, formaciones, universo, motor, inferencia, replicas_R5=2000, diag_B=999, cache=None,
             formaciones_miercoles=None, btc="BTCUSDT"):
    cache = {} if cache is None else cache
    Cfg = motor.Config
    base = motor.simular(P, formaciones, Cfg(), cache, registrar_pesos=True)
    ew = motor.simular(P, formaciones, Cfg(objetivo="ew"), cache, registrar_pesos=True)
    ic = motor.ic_semanal(P, formaciones, cache)
    serie_ic = np.array([x[1] for x in ic if np.isfinite(x[1])])
    h1 = inferencia.newey_west(serie_ic, L=4)
    e = exceso(base, ew)
    h2 = p_h2(e, inferencia)
    holm = inferencia.holm_dos(h1["p_unilateral"], h2["p"])
    rech1, rech2 = holm["rechaza"]["H1"], holm["rechaza"]["H2"]

    # §6.1 y §6.2
    if rech1:
        c1 = "INFORMACION CONFIRMADA" + (" · relevancia demostrada" if h1["ic90"][0] >= DELTA_IC else " · relevancia no demostrada")
    elif h1["ic90"][1] < DELTA_IC:
        c1 = "EN CONTRA (no relevancia)"
    else:
        c1 = "INSUFICIENTE"
    c2 = "VENTAJA NETA DE SELECCION" if rech2 else ("EN CONTRA (economico)" if h2["ic90_semanal"][1] < 0 else "INSUFICIENTE")

    # §6.3 robustez (siempre se calcula y se informa)
    excesos = {}

    def exc(nombre, cfg_kw, cfg_ew=None, F=None):
        F = formaciones if F is None else F
        s = motor.simular(P, F, Cfg(**cfg_kw), cache)
        b = motor.simular(P, F, Cfg(objetivo="ew", **(cfg_kw if cfg_ew is None else cfg_ew)), cache)
        excesos[nombre] = (exceso(s, b), s)
        return float(excesos[nombre][0].mean())

    bruto_s = motor.simular(P, formaciones, Cfg(mult_costo=0.0), cache)
    bruto_ew = motor.simular(P, formaciones, Cfg(objetivo="ew", mult_costo=0.0), cache)
    aporte = contribuciones(P, base, formaciones, bruto_ew)  # N14: r_EW bruto (v1 usaba el neto)
    mayor = max(aporte, key=lambda s: aporte[s]) if aporte else None
    rob = {
        "R1_costos_x2": exc("R1", {"mult_costo": 2.0}),
        "R2_un_dia_despues": exc("R2", {"demora": 1}),
        "R3_tercios_ic_pos": sum(float(np.mean(x)) > 0 for x in tercios(serie_ic)),
        "R3_tercios_exceso_pos": sum(float(np.mean(x)) > 0 for x in tercios(e)),
        "R4_sin_mayor_aporte": (P.sym[mayor] if mayor is not None else None),
        "R4_exceso": exc("R4", {"excluidos": frozenset({P.sym[mayor]})}) if mayor is not None else float("nan"),
        "R6_liquidaciones_menos_30": exc("R6", {"recorte_liq": 0.70}),
    }
    excesos["bruto"] = (exceso(bruto_s, bruto_ew), bruto_s)
    exc_bruto = float(excesos["bruto"][0].mean())
    nulos, rech_diag = [], 0
    for b in range(replicas_R5):
        s = motor.simular(P, formaciones, Cfg(objetivo="aleatorio", mult_costo=0.0, semilla_aleatoria=SEMILLA_R5 + b), cache)
        x = exceso(s, bruto_ew)
        nulos.append(float(x.mean()))
        rech_diag += inferencia.bootstrap_t(x, ell=13, B=diag_B, semilla=SEMILLA_DIAG)["p_unilateral"] <= 0.05
    p_nulo = (1 + sum(v >= exc_bruto for v in nulos)) / (replicas_R5 + 1)
    rob["R5_exceso_bruto"] = exc_bruto
    rob["R5_p_nulo"] = p_nulo
    rob["diag_5_4_tasa_rechazo"] = rech_diag / replicas_R5 if replicas_R5 else float("nan")
    robusta = (rob["R1_costos_x2"] > 0 and rob["R2_un_dia_despues"] > 0 and rob["R3_tercios_ic_pos"] >= 2
               and rob["R3_tercios_exceso_pos"] >= 2 and rob["R4_exceso"] > 0 and p_nulo <= 0.05
               and rob["R6_liquidaciones_menos_30"] > 0)

    # §6.5
    if rech1 and rech2:
        clase = "RESPALDADA HISTORICAMENTE" if robusta else "VENTAJA NO ROBUSTA"
    elif rech1:
        clase = "INFORMACION SIN VENTAJA OPERABLE"
    elif rech2:
        clase = "NO CONCLUYENTE (H2 sin H1)"
    elif c1.startswith("EN CONTRA"):
        clase = "EN CONTRA"
    else:
        clase = "INSUFICIENTE"

    # Descriptivo prescripto: grilla de sensibilidad (N17), 15 configuraciones; la base es k = 6, N = 30
    grilla = {}
    for k in (4, 6, 10):
        for n in (20, 30, 50):
            nombre = f"k{k}_N{n}"
            if (k, n) == (6, 30):
                excesos[nombre] = (e, base)
            else:
                exc(nombre, {"k": k, "banda": 2 * k, "N_inv": n}, {"N_inv": n})
    for h in (7, 14, 21, 28):
        exc(f"h{h}", {"horizontes": (h,)}, {})
    exc("sin_banda", {"banda": 6})
    if formaciones_miercoles is not None:
        exc("miercoles", {}, {}, formaciones_miercoles)
    for nombre in [x for x in excesos if x not in ("R1", "R2", "R4", "R6", "bruto")]:
        x, s = excesos[nombre]
        grilla[nombre] = {"exceso_anual": 52 * float(x.mean()), "sharpe_exceso_anual": float(x.mean() / x.std(ddof=1) * math.sqrt(52)),
                          "sharpe_cartera_anual": (metricas(s["r"][s["evaluable"]]) or {}).get("sharpe_anual")}
    sharpes = [float(x.mean() / x.std(ddof=1)) for x, _ in excesos.values()]

    # Descriptivo frente a BTC y al efectivo (§6.2), estabilidad por año, exposición y rotación
    ev = base["evaluable"] & ew["evaluable"]
    frente_btc = None
    if btc in P.sym:
        sb = P.sym.index(btc)
        precios = np.array([precio_val(P, sb, t) for t in formaciones])
        r_btc = precios[1:] / precios[:-1] - 1
        e_btc = (base["r"] - r_btc)[ev]
        _, _, _, ic90_btc = intervalos(e_btc, inferencia)
        rb = r_btc[ev]
        rs = base["r"][ev]
        frente_btc = {"exceso_anual": 52 * float(e_btc.mean()), "ic90_anual": (52 * ic90_btc[0], 52 * ic90_btc[1]),
                      "beta": float(np.cov(rs, rb)[0, 1] / np.var(rb, ddof=1)), "correlacion": float(np.corrcoef(rs, rb)[0, 1]),
                      "btc_comprar_y_mantener": metricas(rb)}
    anios = {}
    fechas = [universo.INICIO + dt.timedelta(days=t) for t in formaciones[:-1]]
    for (t, v, _, _), f in zip(ic, fechas, strict=False):
        if np.isfinite(v):
            anios.setdefault(f.year, {"ic": [], "exceso": []})["ic"].append(v)
    for j, f in enumerate(fechas):
        if ev[j]:
            anios.setdefault(f.year, {"ic": [], "exceso": []})["exceso"].append(float(base["r"][j] - ew["r"][j]))
    por_anio = {y: {"semanas": len(v["exceso"]), "ic_medio": float(np.mean(v["ic"])) if v["ic"] else None,
                    "exceso_anual": 52 * float(np.mean(v["exceso"])) if v["exceso"] else None} for y, v in sorted(anios.items())}

    return {
        "semanas_ic": int(serie_ic.size), "semanas_h2": h2["n"],
        "H1": {"ic_medio": h1["media"], "ee_nw": h1["ee"], "z": h1["z"], "p1": h1["p_unilateral"], "ic90": h1["ic90"],
               "clasificacion_6_1": c1},
        "H2": {**h2, "clasificacion_6_2": c2},
        "holm": holm, "robustez": rob, "robusta": robusta, "clasificacion_6_5": clase,
        "diagnostico_6_4": diagnostico_6_4(P, formaciones, ic, cache, base, ew, e, h1["media"], universo),
        "descriptivo": {"estrategia": metricas(base["r"][base["evaluable"]]), "ew_u30": metricas(ew["r"][ew["evaluable"]]),
                        "frente_a_btc": frente_btc, "frente_al_efectivo": metricas(base["r"][ev]),
                        "costos": {"x0": 52 * exc_bruto, "x1": h2["anual"], "x2": 52 * rob["R1_costos_x2"]},
                        "exposicion_y_rotacion": exposicion_y_rotacion(P, base, formaciones),
                        "por_anio": por_anio, "grilla_sensibilidad": grilla,
                        "sharpe_deflactado": sharpe_deflactado(e, sharpes),
                        "exceso_timing_T": "NO CALCULADO: T no se reabre (regla vigente)"},
        "nota": "Ninguna clasificación autoriza capital (v3 §6.5). Evidencia histórica con contaminación declarada (v3 §1).",
    }


# ------------------------------------------------------------------ modos

def modo_sintetico(salida: Path, momentum: float, replicas: int, e3: Path = E3_DEFECTO):
    universo, motor, inferencia = importar_congelados(e3)
    if sha(e3 / "codigo" / "pruebas_motor.py") != PRUEBAS_MOTOR:
        raise SystemExit("pruebas_motor.py no coincide con su huella")
    import pruebas_motor
    P = pruebas_motor.panel_sintetico(20261026, momentum=momentum)
    F = pruebas_motor.formaciones()
    validez, cache = validez_previa(P, F, universo, motor)
    Fm = universo.lunes(dt.date(2018, 9, 3), dt.date(2020, 12, 23), dia_semana=2)
    res = ejecutar(P, F, universo, motor, inferencia, replicas_R5=replicas, diag_B=199, cache=cache,
                   formaciones_miercoles=Fm, btc="C00USDT")
    res["validez_previa"] = validez
    salida.mkdir(parents=True, exist_ok=True)
    (salida / f"sintetico_momentum_{momentum}.json").write_text(json.dumps(res, indent=1, default=float, ensure_ascii=False))
    print(json.dumps({"validez": {k: validez[k] for k in ("semanas", "evaluables", "invariancia_ok", "bloqueo_fechas")},
                      **{k: res[k] for k in ("semanas_ic", "H1", "clasificacion_6_5")}}, default=float, ensure_ascii=False))


# ------------------------------------------------------------------ C11: estados terminales, escritura atómica e intentos

def escribir_atomico(p: Path, obj) -> str:
    """Escribe a un temporal, sincroniza y reemplaza: nunca queda un JSON a medio escribir. Devuelve el sha256."""
    p = Path(p)
    tmp = p.with_name(p.name + ".tmp")
    texto = json.dumps(obj, indent=1, default=float, ensure_ascii=False)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(texto)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)
    return sha_bytes(texto.encode("utf-8"))


class Intentos:
    """Registro de intentos de la ejecución única (una línea JSON por evento), con bloqueo exclusivo mientras dura un
    intento. El bloqueo lo libera el sistema si el proceso muere; el registro, en cambio, queda con el intento abierto."""

    def __init__(self, ruta: Path):
        self.f = open(ruta, "a+", encoding="utf-8")
        try:
            fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.f.close()
            raise Rechazo("otra ejecución de E3 está en curso: el registro de intentos está bloqueado") from exc
        self.f.seek(0)
        self.eventos = [json.loads(linea) for linea in self.f.read().splitlines() if linea.strip()]

    def anotar(self, **ev):
        ev = {"utc": dt.datetime.now(dt.UTC).isoformat(), **ev}
        self.f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        self.f.flush()
        os.fsync(self.f.fileno())
        self.eventos.append(ev)

    def cerrar(self):
        try:
            fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
        finally:
            self.f.close()


def permitir_intento(intentos: Intentos, sha_aut: str, texto: str):
    """C11: hay una sola ejecución con resultado. Se rechaza, ANTES de crear la salida:
      - si ya hay un EVALUADO o un INVALIDO;
      - si hay un intento INICIADO sin estado terminal (el proceso murió o el disco falló: revisión manual);
      - si el último ERROR ocurrió con estadísticos ya iniciados (reintentar sería una decisión metodológica);
      - si, tras un ERROR previo a los estadísticos, la autorización es la misma o no cita el sha256 de ese RESULTADO."""
    ev = intentos.eventos
    terminales = [e for e in ev if e["evento"] in ("EVALUADO", "INVALIDO")]
    if terminales:
        raise Rechazo(f"E3 ya tiene un resultado terminal ({terminales[-1]['evento']}, {terminales[-1]['utc']}): no hay otra ejecución")
    abiertos = ({e["id_intento"] for e in ev if e["evento"] == "INICIADO"}
                - {e["id_intento"] for e in ev if e["evento"] in ("ERROR", "EVALUADO", "INVALIDO")})
    if abiertos:
        raise Rechazo(f"hay un intento sin estado terminal ({sorted(abiertos)}): requiere revisión manual antes de cualquier otro")
    errores = [e for e in ev if e["evento"] == "ERROR"]
    if not errores:
        return None
    u = errores[-1]
    if u["estadisticos_iniciados"]:
        raise Rechazo(f"el ERROR previo ocurrió en la etapa «{u['etapa']}», con estadísticos iniciados: "
                      "reintentar es una decisión metodológica, no técnica")
    if any(e.get("sha_autorizacion") == sha_aut for e in ev):
        raise Rechazo("esta autorización ya se usó en un intento anterior: un reintento exige una autorización nueva")
    if f"REINTENTO TRAS ERROR {u['sha_resultado']}" not in texto:
        raise Rechazo(f"la autorización de reintento tiene que citar «REINTENTO TRAS ERROR {u['sha_resultado']}»")
    return u


def resultado_invalido(salida: Path, intentos: Intentos, id_intento: str, motivo: str, **extra):
    """C5: INVÁLIDO como resultado explícito, sin H1 ni H2."""
    res = {"veredicto": "INVALIDO", "motivo": motivo, "H1": None, "H2": None, **extra,
           "nota": "E3-H1/H2 NO EVALUABLES con esta ventana. No se busca otra ventana ni se cambia ninguna regla."}
    h = escribir_atomico(salida / "RESULTADO_E3.json", res)
    intentos.anotar(evento="INVALIDO", id_intento=id_intento, sha_resultado=h)
    raise FinTerminal(f"INVALIDO: {motivo}. Ver {salida / 'RESULTADO_E3.json'}")


def resultado_error(salida: Path, intentos: Intentos, id_intento: str, etapa: str, exc: BaseException):
    """C11: cualquier excepción después de crear la salida deja un ERROR explícito; nunca un éxito aparente ni un
    hueco. Si ni siquiera se puede escribir, el intento queda abierto y el siguiente se rechaza (revisión manual)."""
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    res = {"veredicto": "ERROR", "etapa": etapa, "tipo": type(exc).__name__, "mensaje": str(exc)[:2000],
           "traceback": tb, "sha_traceback": sha_bytes(tb.encode("utf-8")),
           "estadisticos_iniciados": etapa not in ETAPAS_SIN_ESTADISTICOS, "H1": None, "H2": None,
           "nota": "E3-H1/H2 SIN RESULTADO por un fallo técnico: no es EVALUADO ni INVALIDO. Reintentar exige una "
                   "autorización nueva que cite el sha256 de este archivo; con estadísticos iniciados, es una decisión "
                   "metodológica."}
    try:
        h = escribir_atomico(salida / "RESULTADO_E3.json", res)
    except BaseException as exc2:
        raise FinTerminal(f"ERROR en la etapa «{etapa}» y no se pudo escribir RESULTADO_E3.json ({exc2!r}); el intento "
                          "queda abierto en el registro: revisión manual") from exc
    intentos.anotar(evento="ERROR", id_intento=id_intento, etapa=etapa, tipo=type(exc).__name__,
                    estadisticos_iniciados=res["estadisticos_iniciados"], sha_resultado=h)
    raise FinTerminal(f"ERROR en la etapa «{etapa}»: {type(exc).__name__}: {exc}. Ver {salida / 'RESULTADO_E3.json'}") from exc


def modo_real(e3: Path, ventana: Path, autorizacion: Path, salida: Path, manifiesto: Path = None):
    e3, ventana, autorizacion, salida = Path(e3), Path(ventana), Path(autorizacion), Path(salida)
    if salida.exists():
        raise Rechazo(f"{salida} ya existe: la ejecución confirmatoria es única")
    aut_bytes = autorizacion.read_bytes() if autorizacion.is_file() else b""
    texto = aut_bytes.decode("utf-8", errors="replace")
    man_path = Path(manifiesto or MANIFIESTO)
    man_bytes = man_path.read_bytes() if man_path.is_file() else b""  # C9: el manifiesto también se lee una sola vez
    sha_aut, sha_man = sha_bytes(aut_bytes), sha_bytes(man_bytes)
    requeridos = {"FRASE": FRASE in texto, "orquestador_v3": SHA_PROPIO in texto,
                  "entradas_congeladas": bool(man_bytes) and sha_man in texto,
                  **{f"decision_{k}": f in texto for k, f in FRASES_DECISION.items()}}
    if not all(requeridos.values()):
        raise Rechazo(f"autorización ausente o incompleta: {requeridos}. No se lee ningún precio.")
    intentos = Intentos(INTENTOS)
    try:
        previo = permitir_intento(intentos, sha_aut, texto)
        raices = {"E3": e3, "reparacion": REPARACION, "cierre": CIERRE, "ventana": ventana}
        datos = leer_y_verificar(man_bytes, raices)                                   # C8 + C9
        vd = json.loads(datos["ventana_A"])
        if vd.get("veredicto") != "VALIDO" or vd.get("inicio_H") != INICIO_H_A:       # C7 (además del sha256 fijado)
            raise Rechazo(f"la ventana no es la A aprobada (veredicto {vd.get('veredicto')}, inicio {vd.get('inicio_H')})")
        fuentes = {n[:-3]: datos[n] for n in CONGELADOS}
        mods = cargar_modulos(fuentes)                                                  # C10
        universo, motor, inferencia = mods["universo"], mods["motor"], mods["inferencia"]
        mapeos = json.loads(datos["mapeos_adenda1_completa"])["mapeos"]               # C8: solo la entrada verificada
        syms, act = actividad_desde_bytes(datos)                                        # C12: antes de la salida, solo estado
        ceros = np.zeros(act.shape)
        syms2, _, _, _, _, reg_previo, origen = aplicar_mapeos(syms, ceros, ceros, ceros, act, mapeos, universo.INICIO)
        comprobar_marcas(syms, syms2, origen, universo)
        id_intento = f"{sha_aut[:16]}:{salida}"
        salida.mkdir(parents=True, exist_ok=False)
        intentos.anotar(evento="INICIADO", id_intento=id_intento, salida=str(salida), sha_autorizacion=sha_aut,
                        sha_orquestador=SHA_PROPIO, sha_manifiesto=sha_man, reintento_de=previo and previo["sha_resultado"])
        registro = {"inicio_utc": dt.datetime.now(dt.UTC).isoformat(), "estado": "EN_CURSO", "ventana": str(ventana),
                    "sha_ventana": sha_bytes(datos["ventana_A"]), "sha_orquestador": SHA_PROPIO, "sha_manifiesto": sha_man,
                    "sha_autorizacion": sha_aut, "inicio_H": INICIO_H_A, "mapeos_en_tabla": len(mapeos),
                    "mapeos_aplicados_en_la_comprobacion_previa": len(reg_previo), "reintento_de": previo and previo["sha_resultado"]}
        escribir_atomico(salida / "REGISTRO_EJECUCION.json", registro)  # antes de calcular
        etapa = "panel"
        try:
            P, registro_mapeos = panel_real(datos, universo, mapeos)
            inicio = dt.date.fromisoformat(INICIO_H_A)
            formaciones = universo.lunes(inicio, ULTIMA_FORMACION + dt.timedelta(days=7))
            etapa = "validez_previa"
            validez, cache = validez_previa(P, formaciones, universo, motor)
            escribir_atomico(salida / "VALIDEZ_PREVIA.json", {**validez, "mapeos_aplicados": registro_mapeos})
            if not validez["valido"]:
                resultado_invalido(salida, intentos, id_intento, "validez previa (v3 §10)", validez_previa=validez)
            etapa = "calculo"
            Fm = universo.lunes(inicio, ULTIMA_FORMACION + dt.timedelta(days=9), dia_semana=2)
            res = ejecutar(P, formaciones, universo, motor, inferencia, cache=cache, formaciones_miercoles=Fm)
            etapa = "escritura"
            res["veredicto"] = "EVALUADO"
            res["validez_previa"] = validez
            res["mapeos_aplicados"] = registro_mapeos
            res["registro"] = registro
            h = escribir_atomico(salida / "RESULTADO_E3.json", res)
            intentos.anotar(evento="EVALUADO", id_intento=id_intento, sha_resultado=h)
        except FinTerminal:
            raise
        except BaseException as exc:  # incluye SystemExit de código congelado y KeyboardInterrupt
            resultado_error(salida, intentos, id_intento, etapa, exc)
        print(json.dumps({k: res[k] for k in ("semanas_ic", "H1", "H2", "holm", "clasificacion_6_5")}, default=float,
                         ensure_ascii=False, indent=1))
    finally:
        intentos.cerrar()


if __name__ == "__main__":
    if sys.argv[1] == "sintetico":
        modo_sintetico(Path(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 50,
                       Path(sys.argv[5]) if len(sys.argv) > 5 else E3_DEFECTO)
    elif sys.argv[1] == "real":
        modo_real(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5]))
    else:
        raise SystemExit(__doc__)
