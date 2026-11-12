"""Pruebas negativas del validador (L-17). NO emite autorizaciones: la clave es descartable, vive solo en memoria y nunca se
guarda; los objetos son de tipo PRUEBA_SINTETICA con hashes inventados, y además se comprueba que el modo producción los
rechaza. Uso: /usr/bin/python3 -I -B prueba_autorizacion.py <salida.json>"""
import copy
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # noqa: E402

import autorizacion_proto as A  # noqa: E402

h = lambda c: c * 64  # noqa: E731  hashes inventados
priv = Ed25519PrivateKey.generate()
pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
otra = Ed25519PrivateKey.generate()
AHORA = dt.datetime(2026, 11, 2, 12, 0, 0)
BASE = {"version": "E3-AUT-1", "tipo": "PRUEBA_SINTETICA", "emisor": "prueba", "emitida_utc": "2026-11-01T00:00:00Z",
        "caduca_utc": "2026-11-05T00:00:00Z",
        "evaluacion": {"id": "E3-PRUEBA-SINTETICA", "ventana_sha256": h("a"), "inicio_H": "2023-05-15", "fin_H": "2026-05-18", "semanas": 158},
        "codigo": {"lanzador_sha256": h("b"), "orquestador_sha256": h("c"), "entorno_sha256": h("d")},
        "insumos": {"manifiesto_sha256": h("e")}, "registro": {"cabeza_esperada": h("f"), "nonce": "0123456789abcdef0123456789abcdef"},
        "decisiones": dict(A.DECISIONES), "riesgos_aceptados": list(A.RIESGOS)}
ESPERADOS = {"ventana_sha256": h("a"), "inicio_H": "2023-05-15", "fin_H": "2026-05-18", "semanas": 158, "lanzador_sha256": h("b"),
             "orquestador_sha256": h("c"), "entorno_sha256": h("d"), "manifiesto_sha256": h("e")}


def firmar(b, clave=priv):
    return clave.sign(b)


def val(datos, firma=None, modo="prueba", cabeza=h("f"), nonces=(), ahora=AHORA, clave=pub):
    try:
        A.validar(datos, firma if firma is not None else firmar(datos), clave, modo=modo, esperados=ESPERADOS,
                  cabeza_actual=cabeza, nonces_consumidos=set(nonces), ahora=ahora)
        return "ACEPTADA"
    except A.Rechazo as e:
        return f"RECHAZO {e}"


def mod(f):
    o = copy.deepcopy(BASE)
    f(o)
    return A.canonico(o)


c = A.canonico(BASE)
casos = {"positivo_prueba": val(c), "produccion_rechaza_tipo_prueba": val(c, modo="produccion")}
neg = {
    "BOM": b"\xef\xbb\xbf" + c, "salto_final": c + b"\n", "espacio_final": c + b" ", "no_canonico_indentado": json.dumps(BASE, indent=1, sort_keys=True).encode(),
    "claves_desordenadas": json.dumps(BASE, separators=(",", ":")).encode(),
    "clave_repetida_mismo_valor": c[:-1] + b',"version":"E3-AUT-1"}', "clave_repetida_otro_valor": c[:-1] + b',"tipo":"E3_CONFIRMATORIA"}',
    "NaN": c.replace(b'"semanas":158', b'"semanas":NaN'), "Infinity": c.replace(b'"semanas":158', b'"semanas":Infinity'),
    "float_158.0": c.replace(b'"semanas":158', b'"semanas":158.0'), "exponente_1e2": c.replace(b'"semanas":158', b'"semanas":1.58e2'),
    "no_ascii_crudo": c.replace(b'"prueba"', '"prüeba"'.encode()), "escape_unicode_NUL": mod(lambda o: o.update(emisor="pru\u0000eba")),
    "escape_salto_en_id": mod(lambda o: o["evaluacion"].update(id="E3\nX")), "id_largo": mod(lambda o: o["evaluacion"].update(id="E" * 65)),
    "id_minusculas": mod(lambda o: o["evaluacion"].update(id="e3-prueba")), "texto_libre_emisor": mod(lambda o: o.update(emisor="Juan Pérez")),
    "campo_de_mas_raiz": mod(lambda o: o.update(nota="x")), "campo_de_mas_anidado": mod(lambda o: o["registro"].update(extra="x")),
    "campo_faltante": mod(lambda o: o["codigo"].pop("entorno_sha256")), "null_indebido": mod(lambda o: o["evaluacion"].update(fin_H=None)),
    "bool_por_int": mod(lambda o: o["evaluacion"].update(semanas=True)), "semanas_155": mod(lambda o: o["evaluacion"].update(semanas=155)),
    "hash_mayusculas": mod(lambda o: o["codigo"].update(orquestador_sha256=h("C"))), "hash_truncado": mod(lambda o: o["codigo"].update(orquestador_sha256=h("c")[:63])),
    "fecha_imposible": mod(lambda o: o["evaluacion"].update(inicio_H="2023-02-30")), "instante_sin_Z": mod(lambda o: o.update(emitida_utc="2026-11-01T00:00:00")),
    "lista_en_lugar_de_objeto": mod(lambda o: o.update(insumos=[h("e")])),
    "D2_R1_prima": mod(lambda o: o["decisiones"].update(D2="R1_PRIMA")), "D4_160_semanas": mod(lambda o: o["decisiones"].update(D4="A3_1_5_TITULO")),
    "D7_reintento_i": mod(lambda o: o["decisiones"].update(D7="REINTENTO_I")), "D1_negado_con_texto": mod(lambda o: o["decisiones"].update(D1="NO REABRIR_EJECUCION_CON_ADENDA_R")),
    "riesgo_omitido": mod(lambda o: o["riesgos_aceptados"].pop()), "riesgo_repetido": mod(lambda o: o["riesgos_aceptados"].append(A.RIESGOS[0])),
    "riesgos_desordenados": mod(lambda o: o["riesgos_aceptados"].reverse()),
    "ventana_otra": mod(lambda o: o["evaluacion"].update(ventana_sha256=h("9"))), "orquestador_otro": mod(lambda o: o["codigo"].update(orquestador_sha256=h("8"))),
    "entorno_otro": mod(lambda o: o["codigo"].update(entorno_sha256=h("7"))), "inicio_otro": mod(lambda o: o["evaluacion"].update(inicio_H="2023-05-01")),
    "semanas_otras": mod(lambda o: o["evaluacion"].update(semanas=160)), "tipo_desconocido": mod(lambda o: o.update(tipo="E3_EXPLORATORIA")),
    "version_otra": mod(lambda o: o.update(version="E3-AUT-2")), "vigencia_larga": mod(lambda o: o.update(caduca_utc="2026-11-30T00:00:00Z")),
}
for k, b in neg.items():
    casos[k] = val(b)
casos.update({
    "cabeza_anterior": val(c, cabeza=h("0")), "nonce_consumido": val(c, nonces=[BASE["registro"]["nonce"]]),
    "vencida": val(c, ahora=dt.datetime(2026, 11, 6)), "todavia_no_vigente": val(c, ahora=dt.datetime(2026, 10, 31)),
    "firma_otra_clave": val(c, firma=firmar(c, otra)), "firma_de_otros_bytes": val(c, firma=firmar(c + b" ")),
    "firma_truncada": val(c, firma=firmar(c)[:-1]), "firma_byte_cambiado": val(c, firma=bytes([firmar(c)[0] ^ 1]) + firmar(c)[1:]),
    "clave_publica_otra": val(c, clave=otra.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)),
})
aceptados = [k for k, v in casos.items() if v == "ACEPTADA"]
res = {"casos": len(casos), "aceptados": aceptados, "esperado_aceptado": ["positivo_prueba"], "ok": aceptados == ["positivo_prueba"], "detalle": casos,
       "nota": "clave descartable en memoria; ningún archivo de clave ni de firma se guardó; tipo PRUEBA_SINTETICA rechazado en producción"}
with open(sys.argv[1], "w") as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
print(json.dumps({k: res[k] for k in ("casos", "aceptados", "ok")}, ensure_ascii=False))
