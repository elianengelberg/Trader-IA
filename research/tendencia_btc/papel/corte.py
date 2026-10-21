"""Ejecuta un CORTE de la evaluación en papel (rama A) de forma verificable. NO cambia reglas ni código congelado: vive
fuera de src/ (la huella 73b22f3e… no cambia) y llama a las funciones congeladas de ``tendencia.papel``.

Corrige los defectos operativos detectados el 2026-10-17 (papel/VERIFICACION_OPERATIVA_2026-10-17.md):
  D1  historia de la señal incompleta → la señal no existe y el código la trata como exposición 0 sin avisar;
  D2  datos obsoletos o no publicados hasta el corte → se evaluaban menos días sin aviso (o error con ventana vacía);
  D3  sin registro de decisiones (decisión, precio de referencia, momento de disponibilidad);
  D4  ``descargar`` fallaba si ningún día del rango estaba publicado;
  D5  el monitor del carry con un corte a mitad de mes divide por 90 días aunque falte el mes en curso (sesgo);
  D6  revisiones de archivos oficiales ya registrados no se detectaban;
  D7  repetir un corte EVALUADO volvía a descargar y a escribir datos y manifiestos ANTES de comprobar que lo estaba;
  D8  nada verificaba que los resultados y REGISTRO.jsonl fueran coherentes (ni su cadena de hashes): una interrupción
      entre el reemplazo de resultado.json y el registro quedaba en silencio;
  D9  dos ejecuciones simultáneas sobre la misma carpeta de cortes no se coordinaban;
  D10 una fecha no canónica (``20270418``, que Python 3.11 acepta) abría otro corte para el mismo día.
Cada corte se guarda en ``papel/cortes/<corte>/`` (datos con su manifiesto, resultado y decisiones) y se anota en
``papel/cortes/REGISTRO.jsonl`` (solo se añade; encadenado por hash). Cada ejecución toma un cerrojo exclusivo sobre la
carpeta de cortes y, antes de consultar la fuente o escribir nada, verifica (solo lectura) que todo el estado compartido
sea coherente; si no lo es, se detiene sin reparar nada. Un corte EVALUADO es inmutable: repetirlo se detiene igual.
Repetir un corte provisional lo actualiza sin duplicar el registro.

Uso: PYTHONPATH=src:../hcarry_next/src ../hcarry_next/.venv/bin/python -B papel/corte.py AAAA-MM-DD"""

from __future__ import annotations

import contextlib
import csv
import datetime as dt
import fcntl
import hashlib
import json
import os
import secrets
import statistics as st
import sys
from pathlib import Path

from hcarry.data.binance_vision import _bajar_verificado, _escribir_manifiesto, ruta_mensual

from tendencia import papel as P
from tendencia.backtest import Costes, simular
from tendencia.datos import leer
from tendencia.senal import tsmom

AQUI = Path(__file__).resolve().parent
CONGELADO = {"reglas": "d2e4e1fb43b8219b80e19736ba7a9abed22d6e858f0b8955171496fa06e74939",
             "codigo": "73b22f3e3a8f21513d5533fb11a7553becae30b87c8736fb6880bccc36c11d2b"}
RAMA = "A"  # decisión del usuario del 2026-10-17 (PRERREGISTRO_PAPEL.md, adenda 1)
HISTORIA_DESDE = {"A": "2026-04-20", "B": "2026-10-14"}
SIMBOLOS = {"T_BTC": "BTCUSDT", "T_ETH": "ETHUSDT"}
PROVISIONALES = ("SIN OBSERVACIONES PROSPECTIVAS", "NO EVALUABLE")
CAMPOS_REGISTRO = ("corte", "ejecutado_utc", "estado", "resultado_sha256", "linea_anterior_sha256")
PROCEDIMIENTO = "papel/VERIFICACION_OPERATIVA_2026-10-17.md (procedimiento manual)"


class CorteBloqueado(RuntimeError):
    """El corte no se ejecuta y no se toca ningún archivo: ya está EVALUADO u otra ejecución tiene el cerrojo."""


class CorteInconsistente(CorteBloqueado):
    """D8: el estado compartido (resultados y REGISTRO.jsonl) no es coherente o no puede leerse con seguridad. Se detiene
    todo sin consultar la fuente, sin escribir nada y sin reparar nada."""


def _inconsistente(corte: str, archivo: Path, tipo: str, detalle: str) -> CorteInconsistente:
    return CorteInconsistente(f"corte {corte}: {archivo}: {tipo}: {detalle}. No se consulta la fuente, no se modifica "
                              f"ningún archivo y no se repara nada: ver {PROCEDIMIENTO}")


def _es_sha(x: object) -> bool:
    return isinstance(x, str) and len(x) == 64 and all(c in "0123456789abcdef" for c in x)


def _es_estado(x: object) -> bool:
    return isinstance(x, str) and (x == "EVALUADO" or x.startswith(PROVISIONALES))


def _leer_resultado(p: Path, corte: str) -> tuple[str, str]:
    """(estado, SHA-256 del texto) de un resultado.json, sin efectos secundarios. Ilegible, incompleto, con un estado
    desconocido o de otro corte: CorteInconsistente; nunca se trata como si no existiera."""
    try:
        texto = p.read_text(encoding="utf-8")
        previo = json.loads(texto)
        estado, de = previo["estado"], previo["corte_exclusivo"]
    except (OSError, ValueError, TypeError, KeyError) as e:  # ValueError incluye JSON y UTF-8 inválidos
        raise _inconsistente(corte, p, "resultado ilegible", f"no puede interpretarse ({e!r})") from e
    if de != corte or not _es_estado(estado):
        raise _inconsistente(corte, p, "resultado inesperado", f"estado o corte inesperado ({estado!r}, {de!r})")
    return estado, hashlib.sha256(texto.encode()).hexdigest()


def _linea_valida(x: object) -> bool:
    if not (isinstance(x, dict) and all(k in x for k in CAMPOS_REGISTRO)):
        return False
    try:
        dt.date.fromisoformat(x["corte"])
    except (TypeError, ValueError):
        return False
    return (isinstance(x["ejecutado_utc"], str) and _es_estado(x["estado"]) and _es_sha(x["resultado_sha256"])
            and (x["linea_anterior_sha256"] is None or _es_sha(x["linea_anterior_sha256"])))


def _leer_registro(registro: Path) -> list[tuple[str, dict]]:
    """(texto, objeto) de cada línea de REGISTRO.jsonl, sin efectos secundarios: campos requeridos, tipos y cadena
    ``linea_anterior_sha256`` (la primera es null; cada una, el SHA-256 de la anterior). Un registro que no existe está
    vacío; uno ilegible o con una línea inválida, incompleta o fuera de la cadena: CorteInconsistente."""
    if not (registro.exists() or registro.is_symlink()):
        return []
    try:
        texto = registro.read_text(encoding="utf-8")
    except (OSError, ValueError) as e:
        raise _inconsistente("desconocido", registro, "registro ilegible", repr(e)) from e
    if texto and not texto.endswith("\n"):
        raise _inconsistente("desconocido", registro, "línea incompleta",
                             "la última línea no termina en salto de línea (escritura interrumpida)")
    lineas: list[tuple[str, dict]] = []
    anterior = None
    for n, crudo in enumerate(texto.split("\n")[:-1], 1):
        try:
            x = json.loads(crudo)
        except ValueError:
            x = None
        if not _linea_valida(x):
            raise _inconsistente("desconocido", registro, "línea inválida",
                                 f"línea {n}: no es un objeto JSON con {list(CAMPOS_REGISTRO)} de tipos válidos")
        if x["linea_anterior_sha256"] != anterior:
            raise _inconsistente(x["corte"], registro, "cadena rota",
                                 f"línea {n}: linea_anterior_sha256 no es el SHA-256 de la línea {n - 1} (registro "
                                 "editado, truncado, reordenado o escrito por dos procesos a la vez)")
        anterior = hashlib.sha256(crudo.encode()).hexdigest()
        lineas.append((crudo, x))
    return lineas


def _verificar_estado(raiz: Path, corte: str) -> list[tuple[str, dict]]:
    """D8: verificación de SOLO LECTURA de todo el estado compartido, con el cerrojo tomado y antes de consultar la fuente
    o escribir nada. Cada resultado EVALUADO tiene exactamente una entrada EVALUADO con su SHA-256 y ninguna posterior;
    cada entrada EVALUADO, su resultado EVALUADO; ningún resultado contradice el estado con que se registró su contenido.
    Si el corte pedido ya está EVALUADO (y todo es coherente), CorteBloqueado. Devuelve las líneas del registro."""
    registro = raiz / "REGISTRO.jsonl"
    lineas = _leer_registro(registro)
    resultados = {}
    for sub in sorted(raiz.iterdir()):
        p = sub / "resultado.json"
        if sub.is_dir() and (p.exists() or p.is_symlink()):
            resultados[sub.name] = (p, *_leer_resultado(p, sub.name))
    evaluados: dict[str, tuple[int, dict]] = {}
    for n, (_, x) in enumerate(lineas, 1):
        c = x["corte"]
        if c in evaluados:
            raise _inconsistente(c, registro, "entrada posterior a la evaluación",
                                 f"línea {n}: el corte ya figura EVALUADO en la línea {evaluados[c][0]} (duplicado)")
        if x["estado"] == "EVALUADO":
            evaluados[c] = (n, x)
        if c in resultados and x["resultado_sha256"] == resultados[c][2] and x["estado"] != resultados[c][1]:
            raise _inconsistente(c, resultados[c][0], "estado contradictorio",
                                 f"la línea {n} registra este mismo contenido como {x['estado']!r}")
    for c, (n, x) in evaluados.items():
        if c not in resultados:
            raise _inconsistente(c, raiz / c / "resultado.json", "entrada EVALUADO sin resultado",
                                 f"la línea {n} del registro lo da por EVALUADO y el archivo no existe")
        p, estado, sha = resultados[c]
        if estado != "EVALUADO":
            raise _inconsistente(c, p, "resultado contradice el registro",
                                 f"el archivo dice {estado!r} y la línea {n} lo da por EVALUADO")
        if sha != x["resultado_sha256"]:
            raise _inconsistente(c, p, "hash distinto", f"el SHA-256 del archivo ({sha[:12]}…) no es el de la entrada "
                                 f"EVALUADO de la línea {n} ({x['resultado_sha256'][:12]}…)")
    for c, (p, estado, _) in resultados.items():
        if estado == "EVALUADO" and c not in evaluados:
            raise _inconsistente(c, p, "EVALUADO sin entrada en el registro",
                                 f"{registro} no tiene su línea (¿interrupción entre el reemplazo y el registro?)")
    if corte in evaluados:
        raise CorteBloqueado(f"corte {corte}: ya está EVALUADO ({raiz / corte / 'resultado.json'}); es inmutable: no se "
                             "recalcula, no se consulta la fuente y no se modifica ningún archivo")
    return lineas


@contextlib.contextmanager
def _cerrojo(raiz: Path):  # type: ignore[no-untyped-def]
    """D9: cerrojo exclusivo (``fcntl.flock``) sobre la carpeta de cortes. Coordina a las ejecuciones de este script que
    usan la MISMA carpeta: cortes, temporales de hcarry dentro de ellos y REGISTRO.jsonl. No espera: si está tomado, se
    detiene sin tocar nada. Lo libera el sistema al cerrar el descriptor o al morir el proceso; no hay archivo de
    cerrojo que borrar. Es consultivo (no frena a otros programas ni ediciones a mano), no coordina copias distintas del
    repositorio y no es fiable en sistemas de archivos de red."""
    raiz.mkdir(exist_ok=True)  # solo en la primera ejecución: crea la carpeta de cortes vacía (no hay cortes que tocar)
    fd = os.open(raiz, os.O_RDONLY)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise CorteBloqueado(f"{raiz}: otra ejecución de papel/corte.py tiene el cerrojo; no se consulta la fuente "
                                 "ni se modifica ningún archivo: reintentá cuando termine") from e
        yield
    finally:
        os.close(fd)


def _fsync(p: Path) -> None:
    fd = os.open(p, os.O_RDONLY)  # vale para archivos y carpetas
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _sincronizar(d: Path) -> None:
    """fsync de cada archivo y carpeta del corte (datos y .CHECKSUM que escribe hcarry, manifiestos, tablas) y de la
    carpeta de cortes, para que estén en disco ANTES de resultado.json. Mejora la durabilidad; no la garantiza si el
    disco o el sistema de archivos no respetan fsync."""
    for p in [*sorted(d.rglob("*")), d, d.parent]:
        _fsync(p)


def _escribir_atomico(destino: Path, texto: str) -> None:
    """Escribe en un temporal del MISMO directorio, lo sincroniza, lo pone en su lugar con ``os.replace`` y sincroniza la
    carpeta: quien lea ``destino`` ve el contenido anterior o el nuevo completo, nunca uno a medias. Garantiza solo ESTE
    archivo, no toda la evaluación, y depende del sistema de archivos (renombrado atómico dentro de un mismo volumen).
    Ante un error borra el temporal y propaga el error original; si falla después del reemplazo, el resultado ya está
    en su lugar sin su línea en el registro, y la siguiente ejecución lo detecta (D8)."""
    tmp = destino.with_name(f".{destino.name}.{secrets.token_hex(8)}.tmp")
    fh = tmp.open("x", encoding="utf-8")  # creación exclusiva: nunca pisa otro archivo
    try:
        with fh:
            fh.write(texto)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, destino)
        _fsync(destino.parent)
    except BaseException as e:
        try:
            tmp.unlink(missing_ok=True)
        except OSError as e2:
            e.add_note(f"no se pudo borrar el temporal {tmp}: {e2!r}")
        raise


def _dia(fecha: str, delta: int) -> str:
    return (dt.date.fromisoformat(fecha) + dt.timedelta(days=delta)).isoformat()


def preparar(dir_corte: Path, corte: str, rama: str, abrir=P._abrir_http) -> dict:  # type: ignore[no-untyped-def]
    mans = {}
    for k, s in SIMBOLOS.items():
        destino = dir_corte / "datos" / s
        destino.mkdir(parents=True, exist_ok=True)  # D4: el manifiesto se escribe aunque no haya nada publicado
        mans[k] = P.descargar(destino, s, HISTORIA_DESDE[rama], corte, permitir_reservado=(rama == "A"), abrir=abrir)
    return mans


def _datos_sha(man: dict) -> str:
    """Hash del CONTENIDO (ruta y SHA-256 de cada archivo), estable aunque el manifiesto lleve la fecha de descarga."""
    return hashlib.sha256(json.dumps(sorted((a["ruta"], a["sha256"]) for a in man["archivos"])).encode()).hexdigest()


def _registrados(raiz: Path, simbolo: str, excluir: Path, base: Path | None) -> dict[str, str]:
    """Hashes ya registrados de cada archivo oficial: estado inicial y cortes anteriores (D6)."""
    out: dict[str, str] = {}
    manifiestos = ([base / simbolo / "MANIFIESTO.json"] if base else []) + sorted(raiz.glob(f"*/datos/{simbolo}/MANIFIESTO.json"))
    for m in manifiestos:
        if m.exists() and excluir not in m.parents:
            for a in json.loads(m.read_text(encoding="utf-8"))["archivos"]:
                out.setdefault(a["ruta"], a["sha256"])
    return out


def verificar(dir_corte: Path, raiz: Path, corte: str, rama: str, mans: dict, base: Path | None
              ) -> tuple[list[str], dict]:
    problemas, velas = [], {}
    if P.hash_prerregistro() != CONGELADO["reglas"]:
        problemas.append("reglas distintas de las congeladas")
    if P.huella_codigo() != CONGELADO["codigo"]:
        problemas.append("código distinto del congelado")
    inicio = P.primera_ejecucion(rama)
    for k, s in SIMBOLOS.items():
        man = mans[k]
        if man["ausentes"]:
            problemas.append(f"{s}: no publicados todavía o inexistentes: {[a.rsplit('-1d-', 1)[1][:10] for a in man['ausentes']][:5]}")
        for ruta, sha in _registrados(raiz, s, dir_corte, base).items():
            nuevo = next((a["sha256"] for a in man["archivos"] if a["ruta"] == ruta), None)
            if nuevo is not None and nuevo != sha:
                problemas.append(f"{s}: archivo oficial revisado tras registrarse: {ruta}")
        if not man["archivos"]:
            continue
        v, inf = leer(dir_corte / "datos" / s, permitir_reservado=(rama == "A"), permitir_prospectivo=True)
        velas[k] = v
        for campo in ("dias_ausentes", "repetidas", "duracion_irregular", "ohlc_incoherente", "precio_no_positivo"):
            if inf[campo]:
                problemas.append(f"{s}: {campo} {inf[campo][:5]}")
        if v[0].dia != HISTORIA_DESDE[rama]:
            problemas.append(f"{s}: la historia empieza el {v[0].dia}, no el {HISTORIA_DESDE[rama]}")
        if v[-1].dia != _dia(corte, -1):
            problemas.append(f"{s}: datos obsoletos: último día {v[-1].dia}; el corte exige {_dia(corte, -1)}")
        if corte > inicio:
            w = tsmom([x.c for x in v])
            i = next((n for n, x in enumerate(v) if x.dia == _dia(inicio, -1)), None)
            if i is None or w[i] is None:
                problemas.append(f"{s}: sin señal en el cierre previo al inicio ({_dia(inicio, -1)}): historia incompleta")
    return problemas, velas


def decisiones(v, corte: str, rama: str) -> list[dict]:  # type: ignore[no-untyped-def]
    """Registro diario (D3) derivado con las MISMAS funciones congeladas que ``evaluar``."""
    inicio = P.primera_ejecucion(rama)
    obj = tsmom([x.c for x in v])
    s = simular(v, obj, inicio, corte)
    bh = simular(v, [1.0] * len(v), inicio, corte)
    est = simular(v, [st.fmean(s.exposicion)] * len(v), inicio, corte, costes=Costes(0, 0), banda=0.0)
    pos = {x.dia: n for n, x in enumerate(v)}
    ops = {o["dia"]: o for o in s.operaciones}
    filas = []
    for j, d in enumerate(s.dias):
        n = pos[d]
        filas.append({"dia": d, "decision_con_cierre_de": v[n - 1].dia, "cierre_usado": v[n - 1].c,
                      "disponible_desde_utc": f"{d}T00:00:00Z", "exposicion_objetivo": obj[n - 1],
                      "precio_referencia_apertura": v[n].o, "valor_operado": ops.get(d, {}).get("valor", 0.0),
                      "coste": ops.get(d, {}).get("coste", 0.0), "equity_cierre": s.equity[j],
                      "exposicion_cierre": s.exposicion[j], "equity_buy_and_hold": bh.equity[j],
                      "equity_estatica": est.equity[j]})
    return filas


def monitor(dir_corte: Path, corte: str, rama: str, abrir=P._abrir_http) -> dict:  # type: ignore[no-untyped-def]
    """Monitor del carry en el último corte de MES COMPLETO ≤ corte (D5): ventana de 90 días cubierta por los archivos
    mensuales oficiales; informativo, no activa nada."""
    cm = corte[:8] + "01"
    desde = _dia(cm, -90)
    f = dir_corte / "funding_BTCUSDT"
    f.mkdir(parents=True, exist_ok=True)
    archivos, faltan = [], []
    a, m = int(desde[:4]), int(desde[5:7])
    while f"{a}-{m:02d}" < cm[:7]:
        rel = ruta_mensual("funding", "BTCUSDT", a, m)
        r = _bajar_verificado(f, rel, abrir, 4)
        if r:
            archivos.append({"ruta": rel, **r})
        else:
            faltan.append(rel)
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    _escribir_manifiesto(f, {"procedencia": "historico_oficial", "uso": "monitor del carry", "archivos": archivos,
                             "ausentes": faltan})
    base = P.monitor_carry(f, cm, rama=rama) if archivos else {"estado": "sin archivos de funding publicados"}
    return {"ventana_desde": desde, "ventana_hasta_exclusivo": cm, "fuente": "fundingRate mensual oficial (checksum)",
            "anualizacion": "suma de tasas observadas en la ventana × 365 / 90", "tipo": "tasas observadas, no estimadas",
            "meses_no_publicados": faltan, **base,
            "accion": "ninguna: informativo; cruzar el 12 % no activa H-CARRY ni modifica sus reglas"}


def _canon(x: dict) -> str:
    return json.dumps(x, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n"


def ejecutar(corte: str, rama: str = RAMA, raiz: Path = AQUI / "cortes", abrir=P._abrir_http,  # type: ignore[no-untyped-def]
             base: Path | None = AQUI.parent / "datos_papel") -> dict:
    if dt.date.fromisoformat(corte).isoformat() != corte:  # D10: un solo nombre por corte, antes de tocar nada
        raise ValueError(f"corte {corte!r}: usar la forma canónica AAAA-MM-DD")
    with _cerrojo(raiz):  # D9: todo lo que lee o escribe el estado compartido ocurre con el cerrojo tomado
        lineas = _verificar_estado(raiz, corte)  # D7 y D8: solo lectura, antes de consultar la fuente o escribir nada
        return _evaluar(corte, rama, raiz, abrir, base, lineas)


def _evaluar(corte: str, rama: str, raiz: Path, abrir, base: Path | None,  # type: ignore[no-untyped-def]
             lineas: list[tuple[str, dict]]) -> dict:
    inicio = P.primera_ejecucion(rama)
    d = raiz / corte
    salida, registro = d / "resultado.json", raiz / "REGISTRO.jsonl"
    mans = preparar(d, corte, rama, abrir)
    problemas, velas = verificar(d, raiz, corte, rama, mans, base)
    tablas: dict[str, list[dict]] = {}
    res: dict = {"corte_exclusivo": corte, "rama": rama, "inicio": inicio, "reglas_sha256": P.hash_prerregistro(),
                 "codigo_sha256": P.huella_codigo(), "problemas": problemas,
                 "datos_sha256": {SIMBOLOS[k]: _datos_sha(m) for k, m in mans.items()}}
    if corte <= inicio:
        res["estado"] = f"SIN OBSERVACIONES PROSPECTIVAS: la primera ejecución es el {inicio}"
    elif problemas:
        res["estado"] = "NO EVALUABLE (ver problemas): no se calcula ningún resultado"
    else:
        ev = P.evaluar({k: d / "datos" / s for k, s in SIMBOLOS.items()}, corte, rama)
        res["estado"] = "EVALUADO"
        res["evaluacion"] = {k: v for k, v in ev.items() if k not in ("T_BTC", "T_ETH")}
        res["evaluacion"]["metricas"] = {k: ev[k] for k in ("T_BTC", "T_ETH")}
        res["dias_calendario"] = (dt.date.fromisoformat(corte) - dt.date.fromisoformat(inicio)).days
        tablas = {s: decisiones(velas[k], corte, rama) for k, s in SIMBOLOS.items()}
        res["decisiones_sha256"] = {s: hashlib.sha256(json.dumps(f, sort_keys=True).encode()).hexdigest()
                                    for s, f in tablas.items()}
    res["monitor_carry"] = monitor(d, corte, rama, abrir)
    texto = _canon(res)
    sha = hashlib.sha256(texto.encode()).hexdigest()
    # Un resultado EVALUADO es terminal (D7): todo lo que lo acompaña se escribe y se sincroniza antes; resultado.json va
    # al final, de una vez, como marca de corte completo, y después su línea en el registro (ya leído y verificado con el
    # cerrojo tomado). Si algo falla tras el reemplazo, la siguiente ejecución lo detecta (D8). Uno provisional (sin
    # observaciones / no evaluable) se actualiza y el registro conserva el hash de cada versión.
    for s, filas in tablas.items():
        with (d / f"decisiones_{s}.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(filas[0]))
            w.writeheader()
            w.writerows(filas)
    _sincronizar(d)
    _escribir_atomico(salida, texto)
    if all((x["corte"], x["resultado_sha256"]) != (corte, sha) for _, x in lineas):
        anterior = hashlib.sha256(lineas[-1][0].encode()).hexdigest() if lineas else None
        linea = json.dumps({"corte": corte, "ejecutado_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                            "estado": res["estado"], "resultado_sha256": sha, "linea_anterior_sha256": anterior},
                           ensure_ascii=False)
        with registro.open("a", encoding="utf-8") as fh:
            fh.write(linea + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        _fsync(raiz)
    return res


if __name__ == "__main__":
    try:
        r = ejecutar(sys.argv[1])
    except CorteInconsistente as e:
        print(f"INCONSISTENTE: {e}", file=sys.stderr)
        sys.exit(2)
    except CorteBloqueado as e:
        sys.exit(f"DETENIDO: {e}")
    print(json.dumps({k: r[k] for k in ("corte_exclusivo", "estado", "problemas")}, ensure_ascii=False, indent=1))
    print(json.dumps(r["monitor_carry"], ensure_ascii=False, indent=1))
    if "evaluacion" in r:
        print("decisión prerregistrada:", r["evaluacion"]["decision"])
