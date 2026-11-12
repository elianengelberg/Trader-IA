"""Prototipo (NO es E3 y NO emite autorizaciones) del validador de autorización inequívoca v4.1 (L-17, R-10).

Reglas (todas deben cumplirse; cualquier falla es un rechazo con motivo):
  F1 bytes: UTF-8 estricto, solo ASCII, sin BOM, sin salto final; JSON sin claves repetidas ni NaN/Infinity;
     los bytes son exactamente la forma canónica (sort_keys, separadores compactos, ensure_ascii) del objeto leído;
  F2 esquema cerrado: exactamente las claves previstas, en todos los niveles; tipos exactos (bool no vale como int);
  F3 gramática por campo (no hay texto libre): ids, hashes, nonce, fechas y emisor con expresiones regulares fijas;
  F4 decisiones: cada una admite un único valor (el que el orquestador implementa); cualquier otro valor se rechaza;
     los riesgos aceptados tienen que ser exactamente el conjunto declarado, ordenado y sin repetidos;
  F5 tipo: «E3_CONFIRMATORIA» en producción; «PRUEBA_SINTETICA» solo en modo prueba (producción la rechaza);
  F6 vínculos: hashes de ventana, lanzador, orquestador, entorno y manifiesto iguales a los calculados sobre los bytes reales;
     cabeza_esperada igual a la cabeza actual del registro; nonce no consumido;
  F7 tiempo: emitida ≤ ahora ≤ caduca, y caduca − emitida ≤ 7 días (defensa blanda: depende del reloj, se declara);
  F8 firma Ed25519 separada sobre los bytes exactos, con la clave pública de confianza.
Uso: biblioteca; la prueba está en prueba_autorizacion.py (usa /usr/bin/python3, que tiene `cryptography`)."""
import datetime as dt
import json
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

HEX64 = re.compile(r"^[0-9a-f]{64}$")
FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
INSTANTE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
ID = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,63}$")
NONCE = re.compile(r"^[0-9a-f]{32}$")
EMISOR = re.compile(r"^[a-z0-9._-]{1,32}$")
DECISIONES = {"D1": "REABRIR_EJECUCION_CON_ADENDA_R", "D2": "R1_LITERAL", "D3": "N5", "D4": "N5_UNIVERSAL",
              "D5": "SL_V1_S7", "D6": "LISTADO_NUEVO", "D7": "CERO_REINTENTOS", "D8": "ACEPTA_POTENCIA_DECLARADA"}
RIESGOS = sorted(["FRAGILIDAD_2023", "IV_PRIMA_CIRCULAR", "LECTURAS_MISMA_FAMILIA", "MARGEN_2_SEMANAS", "PUNTO_CIEGO_POST_2024_11_06"])
ESQUEMA = {"version": str, "tipo": str, "emisor": str, "emitida_utc": str, "caduca_utc": str,
           "evaluacion": {"id": str, "ventana_sha256": str, "inicio_H": str, "fin_H": str, "semanas": int},
           "codigo": {"lanzador_sha256": str, "orquestador_sha256": str, "entorno_sha256": str},
           "insumos": {"manifiesto_sha256": str},
           "registro": {"cabeza_esperada": str, "nonce": str},
           "decisiones": {k: str for k in DECISIONES},
           "riesgos_aceptados": list}


class Rechazo(Exception):
    pass


def canonico(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _sin_repetidas(pares):
    d = {}
    for k, v in pares:
        if k in d:
            raise Rechazo(f"F1 clave repetida: {k}")
        d[k] = v
    return d


def _const(x):
    raise Rechazo(f"F1 número no finito: {x}")


def _esquema(obj, esq, ruta=""):
    if not isinstance(obj, dict) or set(obj) != set(esq):
        raise Rechazo(f"F2 claves distintas en {ruta or 'raíz'}: {sorted(set(obj) ^ set(esq)) if isinstance(obj, dict) else type(obj).__name__}")
    for k, t in esq.items():
        if isinstance(t, dict):
            _esquema(obj[k], t, f"{ruta}.{k}")
        elif type(obj[k]) is not t:
            raise Rechazo(f"F2 tipo de {ruta}.{k}: {type(obj[k]).__name__}")


def validar(datos: bytes, firma: bytes, clave_publica: bytes, *, modo, esperados, cabeza_actual, nonces_consumidos, ahora):
    # F1
    if datos.startswith(b"\xef\xbb\xbf") or datos.endswith((b"\n", b" ")):
        raise Rechazo("F1 BOM o espacio/salto final")
    try:
        texto = datos.decode("ascii")
    except UnicodeDecodeError:
        raise Rechazo("F1 bytes no ASCII")
    try:
        obj = json.loads(texto, object_pairs_hook=_sin_repetidas, parse_constant=_const)
    except Rechazo:
        raise
    except ValueError as e:
        raise Rechazo(f"F1 JSON inválido: {e.__class__.__name__}")
    try:
        if canonico(obj) != datos:
            raise Rechazo("F1 no es la forma canónica")
    except ValueError:
        raise Rechazo("F1 valor no serializable en forma canónica")
    # F2
    _esquema(obj, ESQUEMA)
    # F3
    ev, cod, reg = obj["evaluacion"], obj["codigo"], obj["registro"]
    checks = [(obj["version"] == "E3-AUT-1", "version"), (EMISOR.match(obj["emisor"]), "emisor"),
              (INSTANTE.match(obj["emitida_utc"]), "emitida_utc"), (INSTANTE.match(obj["caduca_utc"]), "caduca_utc"),
              (ID.match(ev["id"]), "evaluacion.id"), (HEX64.match(ev["ventana_sha256"]), "ventana_sha256"),
              (FECHA.match(ev["inicio_H"]), "inicio_H"), (FECHA.match(ev["fin_H"]), "fin_H"),
              (156 <= ev["semanas"] <= 600, "semanas"), (NONCE.match(reg["nonce"]), "nonce"),
              (HEX64.match(reg["cabeza_esperada"]), "cabeza_esperada"), (HEX64.match(obj["insumos"]["manifiesto_sha256"]), "manifiesto")]
    checks += [(HEX64.match(cod[k]), k) for k in cod]
    for ok, campo in checks:
        if not ok:
            raise Rechazo(f"F3 gramática: {campo}")
    try:
        t0 = dt.datetime.strptime(obj["emitida_utc"], "%Y-%m-%dT%H:%M:%SZ")
        t1 = dt.datetime.strptime(obj["caduca_utc"], "%Y-%m-%dT%H:%M:%SZ")
        dt.date.fromisoformat(ev["inicio_H"]), dt.date.fromisoformat(ev["fin_H"])
    except ValueError:
        raise Rechazo("F3 fecha imposible")
    # F4
    for k, v in DECISIONES.items():
        if obj["decisiones"][k] != v:
            raise Rechazo(f"F4 decisión {k} = {obj['decisiones'][k]!r}: el orquestador solo implementa {v!r}")
    if obj["riesgos_aceptados"] != RIESGOS:
        raise Rechazo("F4 riesgos aceptados distintos del conjunto declarado")
    # F5
    if obj["tipo"] != {"produccion": "E3_CONFIRMATORIA", "prueba": "PRUEBA_SINTETICA"}[modo]:
        raise Rechazo(f"F5 tipo {obj['tipo']!r} no admitido en modo {modo}")
    # F6
    for campo, valor in (("ventana_sha256", ev["ventana_sha256"]), ("inicio_H", ev["inicio_H"]), ("fin_H", ev["fin_H"]),
                         ("semanas", ev["semanas"]), ("lanzador_sha256", cod["lanzador_sha256"]),
                         ("orquestador_sha256", cod["orquestador_sha256"]), ("entorno_sha256", cod["entorno_sha256"]),
                         ("manifiesto_sha256", obj["insumos"]["manifiesto_sha256"])):
        if esperados[campo] != valor:
            raise Rechazo(f"F6 {campo} no coincide con lo calculado")
    if reg["cabeza_esperada"] != cabeza_actual:
        raise Rechazo("F6 cabeza del registro distinta (autorización de otro estado)")
    if reg["nonce"] in nonces_consumidos:
        raise Rechazo("F6 nonce ya consumido")
    # F7
    if not (t0 <= ahora <= t1) or (t1 - t0) > dt.timedelta(days=7):
        raise Rechazo("F7 fuera de vigencia")
    # F8
    try:
        Ed25519PublicKey.from_public_bytes(clave_publica).verify(firma, datos)
    except (InvalidSignature, ValueError):
        raise Rechazo("F8 firma inválida")
    return obj
