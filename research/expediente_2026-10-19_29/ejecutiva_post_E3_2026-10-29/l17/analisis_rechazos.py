"""L-17 · ¿Los 53 rechazos ocurrieron por la regla PREVISTA, o el validador rechaza «por accidente» (lo que haría circular la
prueba)? ¿Rechaza también entradas válidas (exceso de rigidez)? No modifica el validador ni sus pruebas: los importa tal cual.
  1. Cada vector negativo tiene una regla esperada (F1…F8), fijada aquí antes de leer el resultado. Se compara con la regla
     que efectivamente lo rechazó en `L17_autorizacion.json` (corrida anterior, no se repite).
  2. Controles positivos nuevos (variaciones válidas que DEBEN aceptarse): bordes de gramática, de semanas y de vigencia.
Clave descartable en memoria; tipo PRUEBA_SINTETICA; nada se guarda salvo el informe. No es una autorización.
Uso: /usr/bin/python3 -I -B analisis_rechazos.py <dir_l17_autorizacion> <L17_autorizacion.json> <salida.json>"""
import copy
import datetime as dt
import json
import sys

sys.path.insert(0, sys.argv[1])
import autorizacion_proto as A  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # noqa: E402

ESPERADA = {
    "produccion_rechaza_tipo_prueba": "F5", "BOM": "F1", "salto_final": "F1", "espacio_final": "F1", "no_canonico_indentado": "F1",
    "claves_desordenadas": "F1", "clave_repetida_mismo_valor": "F1", "clave_repetida_otro_valor": "F1", "NaN": "F1", "Infinity": "F1",
    "float_158.0": "F2", "exponente_1e2": "F1", "no_ascii_crudo": "F1", "escape_unicode_NUL": "F3", "escape_salto_en_id": "F3",
    "id_largo": "F3", "id_minusculas": "F3", "texto_libre_emisor": "F3", "campo_de_mas_raiz": "F2", "campo_de_mas_anidado": "F2",
    "campo_faltante": "F2", "null_indebido": "F2", "bool_por_int": "F2", "semanas_155": "F3", "hash_mayusculas": "F3",
    "hash_truncado": "F3", "fecha_imposible": "F3", "instante_sin_Z": "F3", "lista_en_lugar_de_objeto": "F2", "D2_R1_prima": "F4",
    "D4_160_semanas": "F4", "D7_reintento_i": "F4", "D1_negado_con_texto": "F4", "riesgo_omitido": "F4", "riesgo_repetido": "F4",
    "riesgos_desordenados": "F4", "ventana_otra": "F6", "orquestador_otro": "F6", "entorno_otro": "F6", "inicio_otro": "F6",
    "semanas_otras": "F6", "tipo_desconocido": "F5", "version_otra": "F3", "vigencia_larga": "F7", "cabeza_anterior": "F6",
    "nonce_consumido": "F6", "vencida": "F7", "todavia_no_vigente": "F7", "firma_otra_clave": "F8", "firma_de_otros_bytes": "F8",
    "firma_truncada": "F8", "firma_byte_cambiado": "F8", "clave_publica_otra": "F8"}
previo = json.load(open(sys.argv[2]))["detalle"]
filas, mal = [], []
for k, v in previo.items():
    if k == "positivo_prueba":
        continue
    real = v.split(" ")[1] if v.startswith("RECHAZO") else "ACEPTADA"
    filas.append({"vector": k, "esperada": ESPERADA[k], "real": real, "motivo": v})
    if real != ESPERADA[k]:
        mal.append(k)

# Controles positivos nuevos: deben ACEPTARSE
priv = Ed25519PrivateKey.generate()
pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
h = lambda c: c * 64  # noqa: E731
BASE = {"version": "E3-AUT-1", "tipo": "PRUEBA_SINTETICA", "emisor": "prueba", "emitida_utc": "2026-11-01T00:00:00Z",
        "caduca_utc": "2026-11-05T00:00:00Z",
        "evaluacion": {"id": "E3-PRUEBA-SINTETICA", "ventana_sha256": h("a"), "inicio_H": "2023-05-15", "fin_H": "2026-05-18", "semanas": 158},
        "codigo": {"lanzador_sha256": h("b"), "orquestador_sha256": h("c"), "entorno_sha256": h("d")},
        "insumos": {"manifiesto_sha256": h("e")}, "registro": {"cabeza_esperada": h("f"), "nonce": "0123456789abcdef0123456789abcdef"},
        "decisiones": dict(A.DECISIONES), "riesgos_aceptados": list(A.RIESGOS)}


def esperados(o):
    ev, cod = o["evaluacion"], o["codigo"]
    return {"ventana_sha256": ev["ventana_sha256"], "inicio_H": ev["inicio_H"], "fin_H": ev["fin_H"], "semanas": ev["semanas"],
            "lanzador_sha256": cod["lanzador_sha256"], "orquestador_sha256": cod["orquestador_sha256"], "entorno_sha256": cod["entorno_sha256"],
            "manifiesto_sha256": o["insumos"]["manifiesto_sha256"]}


def positivo(nombre, f, ahora=dt.datetime(2026, 11, 2, 12)):
    o = copy.deepcopy(BASE)
    f(o)
    b = A.canonico(o)
    try:
        A.validar(b, priv.sign(b), pub, modo="prueba", esperados=esperados(o), cabeza_actual=o["registro"]["cabeza_esperada"],
                  nonces_consumidos={"ffffffffffffffffffffffffffffffff"}, ahora=ahora)
        return {"control": nombre, "resultado": "ACEPTADA"}
    except A.Rechazo as e:
        return {"control": nombre, "resultado": f"RECHAZO {e}"}


positivos = [
    positivo("emisor_un_caracter", lambda o: o.update(emisor="x")),
    positivo("emisor_32_caracteres", lambda o: o.update(emisor="a" * 32)),
    positivo("id_64_caracteres", lambda o: o["evaluacion"].update(id="E" * 64)),
    positivo("semanas_156_borde", lambda o: o["evaluacion"].update(semanas=156)),
    positivo("semanas_600_borde", lambda o: o["evaluacion"].update(semanas=600)),
    positivo("vigencia_exacta_7_dias", lambda o: o.update(caduca_utc="2026-11-08T00:00:00Z")),
    positivo("ahora_igual_a_emitida", lambda o: None, ahora=dt.datetime(2026, 11, 1, 0, 0, 0)),
    positivo("ahora_igual_a_caduca", lambda o: None, ahora=dt.datetime(2026, 11, 5, 0, 0, 0)),
    positivo("hashes_y_nonce_distintos", lambda o: (o["codigo"].update(lanzador_sha256=h("1")), o["registro"].update(nonce="a1" * 16))),
    positivo("anio_bisiesto", lambda o: o["evaluacion"].update(inicio_H="2024-02-29")),
]
res = {"negativos": len(filas), "rechazados_por_la_regla_prevista": len(filas) - len(mal), "por_otra_regla": mal,
       "positivos_nuevos": len(positivos), "positivos_aceptados": sum(p["resultado"] == "ACEPTADA" for p in positivos),
       "positivos_rechazados": [p for p in positivos if p["resultado"] != "ACEPTADA"], "detalle_negativos": filas}
json.dump(res, open(sys.argv[3], "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: res[k] for k in ("negativos", "rechazados_por_la_regla_prevista", "por_otra_regla", "positivos_nuevos",
                                      "positivos_aceptados", "positivos_rechazados")}, ensure_ascii=False, indent=1))
