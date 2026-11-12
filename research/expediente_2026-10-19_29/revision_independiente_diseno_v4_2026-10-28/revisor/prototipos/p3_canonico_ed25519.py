"""P3 (revisor) · Canonicalización estricta (§C.1/§C.3 regla 1) y firma Ed25519 separada, con datos de PRUEBA.
NO es E3: esquema «PRUEBA-REVISOR/1», clave generada en memoria y descartada. Ninguna frase ni hash real de E3.

Pone a prueba:
  1. que `json.loads` por sí solo NO rechaza BOM ni claves repetidas (así que la regla 1 descansa en la comparación de
     bytes tras re-serializar, o en `object_pairs_hook`);
  2. la batería de negativos de §E (L-17) más casos que el diseño no enumera: -0, 1.0, 1e2, 1e400, entero gigante,
     escape \\u00e9 frente a é crudo, sustituto suelto, NUL, null donde no se admite, campo anidado de más;
  3. equivalencia entre `json.dumps(sort_keys, separators)` y una canonicalización JCS mínima independiente, y el caso
     en que DIVERGEN (orden de claves por UTF-16 frente a punto de código), que obliga a «fijar en el código» en lugar
     de invocar RFC 8785 a secas;
  4. firma Ed25519 separada: válida solo sobre los bytes exactos; falla con '\\n' final, con otra clave, truncada, o
     sobre el mismo objeto serializado de otra forma.
Uso: /usr/bin/python3 -I -B p3_canonico_ed25519.py
"""
import json
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ESQUEMA = {  # cerrado y pequeño, solo para la prueba
    "esquema": ("str", {"PRUEBA-REVISOR/1"}),
    "evaluacion": ("str", None),
    "semanas": ("int", None),
    "hash_insumo": ("hex64", None),
    "politica": ("str", {"SIN_REINTENTO", "SOLO_PANEL"}),
    "intento_previo": ("nullable_hex64", None),
}


def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sin_repetidas(pares):
    claves = [k for k, _ in pares]
    if len(set(claves)) != len(claves):
        raise ValueError("clave repetida")
    return dict(pares)


def validar(b: bytes):
    """Devuelve (acepta, motivo). Regla 1: los bytes son la forma canónica del objeto parseado. Regla 2: esquema estricto."""
    try:
        if not isinstance(b, bytes):
            return False, "no son bytes"
        texto = b.decode("utf-8")  # estricto: un sustituto suelto codificado no es UTF-8 válido
        obj = json.loads(texto, object_pairs_hook=sin_repetidas)
        if not isinstance(obj, dict):
            return False, "no es un objeto"
        if any(isinstance(v, float) for v in obj.values()):
            return False, "coma flotante"
        if canon(obj) != b:
            return False, "bytes no canónicos"
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        return False, f"rechazo al parsear: {type(exc).__name__}: {str(exc)[:60]}"
    if set(obj) != set(ESQUEMA):
        return False, f"campos: faltan {sorted(set(ESQUEMA) - set(obj))}, sobran {sorted(set(obj) - set(ESQUEMA))}"
    for k, (tipo, enum) in ESQUEMA.items():
        v = obj[k]
        if tipo == "str" and not isinstance(v, str):
            return False, f"{k}: tipo"
        if tipo == "int" and (not isinstance(v, int) or isinstance(v, bool)):
            return False, f"{k}: tipo"
        if tipo in ("hex64", "nullable_hex64"):
            if v is None and tipo == "nullable_hex64":
                continue
            if not (isinstance(v, str) and len(v) == 64 and all(c in "0123456789abcdef" for c in v)):
                return False, f"{k}: no es sha256 hex minúscula"
        if enum and v not in enum:
            return False, f"{k}: enumerado desconocido"
    return True, "ok"


def jcs_minimo(obj) -> bytes:
    """Canonicalización independiente al estilo RFC 8785 para el subconjunto sin flotantes: claves ordenadas por
    unidades UTF-16, sin espacios, escapes mínimos."""
    def esc(s):
        out = []
        for ch in s:
            o = ord(ch)
            if ch == '"':
                out.append('\\"')
            elif ch == "\\":
                out.append("\\\\")
            elif ch == "\b":
                out.append("\\b")
            elif ch == "\f":
                out.append("\\f")
            elif ch == "\n":
                out.append("\\n")
            elif ch == "\r":
                out.append("\\r")
            elif ch == "\t":
                out.append("\\t")
            elif o < 0x20:
                out.append(f"\\u{o:04x}")
            else:
                out.append(ch)
        return '"' + "".join(out) + '"'

    def ser(x):
        if x is None:
            return "null"
        if x is True:
            return "true"
        if x is False:
            return "false"
        if isinstance(x, int):
            return str(x)
        if isinstance(x, str):
            return esc(x)
        if isinstance(x, list):
            return "[" + ",".join(ser(v) for v in x) + "]"
        if isinstance(x, dict):
            claves = sorted(x, key=lambda k: k.encode("utf-16-be"))
            return "{" + ",".join(esc(k) + ":" + ser(x[k]) for k in claves) + "}"
        raise TypeError(type(x))
    return ser(obj).encode("utf-8")


def main():
    out = {}
    base = {"esquema": "PRUEBA-REVISOR/1", "evaluacion": "prueba-ñandú", "semanas": 158, "hash_insumo": "0" * 64,
            "politica": "SIN_REINTENTO", "intento_previo": None}
    B = canon(base)
    out["positivo"] = {"bytes": B.decode(), "acepta": validar(B)}

    # 1. json.loads solo
    out["1_json_loads_solo"] = {
        "acepta_BOM": json.loads(b"\xef\xbb\xbf" + B) == base,
        "acepta_clave_repetida_ultima_gana": json.loads('{"a":1,"a":2}') == {"a": 2},
        "acepta_NaN": json.loads('{"a":NaN}')["a"] != json.loads('{"a":NaN}')["a"],
        "acepta_espacios_y_salto_final": json.loads(B.decode() + " \n") == base,
    }

    # 2. negativos
    def variante(**cambios):
        o = dict(base)
        for k, v in cambios.items():
            if v is ...:
                o.pop(k)
            else:
                o[k] = v
        return canon(o)
    textos = {
        "BOM": b"\xef\xbb\xbf" + B,
        "salto_final": B + b"\n",
        "espacio_inicial": b" " + B,
        "espacios_internos": json.dumps(base, sort_keys=True, ensure_ascii=False).encode(),
        "claves_desordenadas": json.dumps(base, separators=(",", ":"), ensure_ascii=False).encode(),
        "clave_repetida_mismo_valor": B.replace(b'"semanas":158', b'"semanas":158,"semanas":158'),
        "clave_repetida_otro_valor": B.replace(b'"semanas":158', b'"semanas":158,"semanas":160'),
        "flotante_1.0": B.replace(b'"semanas":158', b'"semanas":158.0'),
        "exponente_1e2": B.replace(b'"semanas":158', b'"semanas":1e2'),
        "menos_cero": B.replace(b'"semanas":158', b'"semanas":-0'),
        "NaN": B.replace(b'"semanas":158', b'"semanas":NaN'),
        "1e400": B.replace(b'"semanas":158', b'"semanas":1e400'),
        "entero_gigante": B.replace(b'"semanas":158', b'"semanas":' + b"9" * 5000),
        "escape_u00f1_en_lugar_de_crudo": B.replace("ñ".encode(), b"\\u00f1"),
        "ensure_ascii_True": json.dumps(base, sort_keys=True, separators=(",", ":")).encode(),
        "sustituto_suelto_escapado": B.replace(b'"prueba-', b'"\\ud800prueba-'),
        "sustituto_suelto_crudo": B.replace("ñ".encode(), b"\xed\xa0\x80"),
        "NUL_escapado": B.replace(b'"prueba-', b'"\\u0000prueba-'),
        "texto_antes": b"AUTORIZO " + B,
        "texto_despues": B + b" fin",
        "comentario": B[:-1] + b'/*x*/}',
        "campo_de_mas": variante(extra=1),
        "campo_de_mas_anidado": B.replace(b'"semanas":158', b'"semanas":158,"z":{"x":1}'),
        "campo_faltante": variante(politica=...),
        "null_donde_no_se_admite": variante(hash_insumo=None),
        "enumerado_desconocido": variante(politica="PANEL_Y_SIMULACION"),
        "tipo_equivocado_str_por_int": variante(semanas="158"),
        "bool_por_int": variante(semanas=True),
        "hash_mayusculas": variante(hash_insumo="A" * 64),
        "hash_truncado": variante(hash_insumo="0" * 63),
        "hash_un_caracter_cambiado": variante(hash_insumo="0" * 63 + "1"),
        "lista_en_lugar_de_objeto": b"[" + B + b"]",
        "objeto_vacio": b"{}",
        "vacio": b"",
    }
    out["2_negativos"] = {k: validar(v) for k, v in textos.items()}
    out["2_todos_rechazados"] = all(not r[0] for r in out["2_negativos"].values())

    # 3. equivalencia con JCS mínimo
    casos = [base, {"b": [1, 2, {"d": None, "c": "x\ty\u0001 "}], "a": "é\"\\"}, {"ñ": 1, "n": 2, "Z": 3, "z": 4}]
    out["3_equivalencia_subconjunto"] = [canon(c) == jcs_minimo(c) for c in casos]
    diverg = {"￿": 1, "\U00010000": 2}
    orden = lambda b: [hex(ord(k)) for k in json.loads(b)]  # noqa: E731
    out["3_divergencia_orden_claves_fuera_del_BMP"] = {"python_sort_keys": orden(canon(diverg)), "jcs_utf16": orden(jcs_minimo(diverg)),
                                                        "iguales": canon(diverg) == jcs_minimo(diverg),
                                                        "nota": "irrelevante si TODAS las claves del esquema son ASCII; por eso hay que fijarlo"}

    # 4. Ed25519 separada
    k = Ed25519PrivateKey.generate()
    pub = k.public_key()
    otra = Ed25519PrivateKey.generate().public_key()
    firma = k.sign(B)

    def verifica(pk, f, m):
        try:
            pk.verify(f, m)
            return True
        except InvalidSignature:
            return False
    out["4_ed25519"] = {
        "firma_bytes": len(firma),
        "valida_sobre_bytes_exactos": verifica(pub, firma, B),
        "valida_con_salto_final": verifica(pub, firma, B + b"\n"),
        "valida_mismo_objeto_otra_serializacion": verifica(pub, firma, json.dumps(base, sort_keys=True).encode()),
        "valida_con_otra_clave": verifica(otra, firma, B),
        "valida_firma_un_byte_cambiado": verifica(pub, bytes([firma[0] ^ 1]) + firma[1:], B),
        "nota": "la firma prueba posesión de la clave sobre esos bytes; no dice nada de la validez metodológica",
    }
    try:
        pub.verify(firma[:-1], B)
        out["4_ed25519"]["valida_firma_truncada"] = True
    except Exception as exc:  # noqa: BLE001
        out["4_ed25519"]["valida_firma_truncada"] = f"False ({type(exc).__name__})"
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    sys.exit(main())
