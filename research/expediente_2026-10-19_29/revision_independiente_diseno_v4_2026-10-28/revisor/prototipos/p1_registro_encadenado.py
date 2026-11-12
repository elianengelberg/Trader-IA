"""P1 (revisor) · Registro encadenado del diseño §A.2/§A.4 puesto a prueba. NO es E3: eventos y datos inventados.

Pone a prueba:
  1. qué detecta la cadena sin ancla: cola partida a mitad de línea, bit cambiado, línea del medio borrada, reorden,
     línea duplicada, y la ÚLTIMA línea borrada entera (truncamiento en un límite de línea);
  2. que ningún prefijo de una línea válida parsea como línea válida (k = 1 … len-1);
  3. reconciliación con `COLA_DESCARTADA` anexada DESPUÉS de la basura, sin truncar, y un lector que resincroniza
     verificando el sha de los bytes saltados; doble cola partida (la reconciliación misma muere a medio escribir);
     idempotencia; qué pasa si la basura contiene un salto de línea (no es cola partida: es corrupción);
  4. MODELO de disco (no es ext4 real): `write` entra en caché, `fsync` puede fallar una vez con EIO y, como hace Linux
     desde 4.13, las páginas quedan limpias (los datos siguen visibles en caché pero no llegan al disco). Se compara
     el protocolo tal como está escrito (ancla tras consumo y cierre) con una variante de ancla "write-ahead" antes de
     DECISION. También ENOSPC en la escritura de DECISION.
Uso: /usr/bin/python3 -I -B p1_registro_encadenado.py <dir_trabajo>
"""
import errno
import hashlib
import json
import os
import sys

GENESIS = "GENESIS"


def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def linea(contenido: dict) -> bytes:
    c = canon(contenido)
    return f"{len(c)}\t{sha(c)}\t".encode() + c + b"\n"


def parsear(seg: bytes):
    """seg: bytes de una línea SIN el salto final. Devuelve (ok, contenido, motivo)."""
    try:
        n, hh, c = seg.split(b"\t", 2)
        n = int(n)
    except ValueError:
        return False, None, "formato"
    if len(c) != n:
        return False, None, f"longitud declarada {n} != {len(c)}"
    if sha(c) != hh.decode("ascii", "replace"):
        return False, None, "sha no coincide"
    try:
        cont = json.loads(c)
    except ValueError:
        return False, None, "json"
    if not isinstance(cont, dict) or canon(cont) != c or "seq" not in cont or "hash_previo" not in cont:
        return False, None, "no canónico o sin campos de cadena"
    return True, cont, ""


def _resincronizar(data, pos, cabeza, seq):
    """Busca, después de la basura que empieza en `pos`, una línea COLA_DESCARTADA que encadene con `cabeza` y cuyo sha
    cubra EXACTAMENTE los bytes saltados. Devuelve (contenido, posición siguiente) o None."""
    s = data.find(b"\n", pos)
    while s >= 0:
        s += 1
        nl2 = data.find(b"\n", s)
        if nl2 < 0:
            return None
        ok2, c2, _ = parsear(data[s:nl2])
        if (ok2 and c2.get("evento") == "COLA_DESCARTADA" and c2["hash_previo"] == cabeza and c2["seq"] == seq + 1
                and c2.get("sha_bytes_descartados") == sha(data[pos:s]) and c2.get("n_bytes_descartados") == s - pos):
            return c2, nl2 + 1
        s = data.find(b"\n", s)
    return None


def _hay_linea_completa(data, pos):
    s = pos
    while True:
        nl = data.find(b"\n", s)
        if nl < 0:
            return False
        if parsear(data[s:nl])[0]:
            return True
        s = nl + 1


class Registro:
    """Escritor/lector sobre un 'dispositivo' (archivo real o modelo de disco)."""

    def __init__(self, dev):
        self.dev = dev

    def leer(self, con_resincronizacion=True):
        data = self.dev.leer()
        pos, cabeza, seq, lineas = 0, GENESIS, 0, []
        while pos < len(data):
            nl = data.find(b"\n", pos)
            ok, cont, motivo = parsear(data[pos:nl]) if nl >= 0 else (False, None, "sin salto final")
            if ok and cont["hash_previo"] == cabeza and cont["seq"] == seq + 1:
                lineas.append(cont)
                cabeza, seq, pos = sha(canon(cont)), seq + 1, nl + 1
                continue
            if ok:
                return lineas, {"estado": "CADENA_ROTA", "desde": pos, "cabeza": cabeza,
                                "detalle": f"hash_previo/seq no encadenan (seq {cont['seq']}, esperado {seq + 1})"}
            if con_resincronizacion:
                r = _resincronizar(data, pos, cabeza, seq)
                if r is not None:
                    cont, pos = r
                    lineas.append(cont)
                    cabeza, seq = sha(canon(cont)), seq + 1
                    continue
            # REGLA v2 (tras el fallo de la primera versión con la doble cola): es COLA_CORTADA si y solo si en el resto
            # del archivo no hay NINGUNA línea completa bien formada (parsear ok). Si la hay, es corrupción o escritura
            # posterior a una corrupción: CADENA_ROTA (bloqueo). Un torn write de la propia reconciliación deja
            # «basura + '\n' + prefijo de línea», que esta regla sí clasifica como cola.
            if not _hay_linea_completa(data, pos):
                return lineas, {"estado": "COLA_CORTADA", "desde": pos, "cabeza": cabeza, "detalle": motivo,
                                "contiene_salto": b"\n" in data[pos:]}
            return lineas, {"estado": "CADENA_ROTA", "desde": pos, "cabeza": cabeza, "detalle": "basura seguida de una línea completa: " + motivo}
        return lineas, {"estado": "OK", "cabeza": cabeza, "seq": seq}

    def anexar(self, evento, **campos):
        lineas, est = self.leer()
        if est["estado"] != "OK":
            raise RuntimeError(f"no se anexa sobre un registro en estado {est['estado']}")
        cont = {"seq": est["seq"] + 1, "hash_previo": est["cabeza"], "evento": evento, **campos}
        self.dev.escribir(linea(cont))
        self.dev.fsync()
        return sha(canon(cont))

    def reconciliar(self):
        """Idempotente: solo actúa si hay cola cortada (bytes finales SIN salto). Anexa '\\n' + COLA_DESCARTADA(sha de
        TODOS los bytes saltados, incluido ese salto). Una línea completa pero inválida NO es cola cortada: es
        corrupción y se deja en BLOQUEO."""
        lineas, est = self.leer()
        if est["estado"] != "COLA_CORTADA":
            return est["estado"]
        data = self.dev.leer()
        basura = data[est["desde"]:] + b"\n"
        cont = {"seq": len(lineas) + 1, "hash_previo": est["cabeza"], "evento": "COLA_DESCARTADA",
                "sha_bytes_descartados": sha(basura), "n_bytes_descartados": len(basura),
                "contenia_salto": est.get("contiene_salto", False)}  # un torn write canónico nunca contiene '\n': se deja constancia
        self.dev.escribir(b"\n" + linea(cont))
        self.dev.fsync()
        return "COLA_DESCARTADA_ANEXADA"


class Archivo:
    def __init__(self, p):
        self.p = p
        open(p, "ab").close()

    def leer(self):
        return open(self.p, "rb").read()

    def escribir(self, b):
        with open(self.p, "ab") as f:
            f.write(b)

    def fsync(self):
        fd = os.open(self.p, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def reemplazar(self, data):
        with open(self.p, "wb") as f:
            f.write(data)


class DiscoModelo:
    """Caché de páginas vs. disco. `escribir` deja páginas sucias en caché. `fsync`: si `fallar_una_vez`, devuelve EIO
    y marca las páginas sucias como limpias (no llegan al disco, pero siguen legibles en caché y no se reintentan);
    si no, vuelca SOLO las páginas sucias (lo anterior «limpio» no se vuelve a escribir). `corte()` deja la caché igual
    al disco (reinicio)."""

    def __init__(self):
        self.cache, self.disco, self.sucias = bytearray(), bytearray(), []
        self.fallar_una_vez = False
        self.enospc = False
        self.fsyncs = []

    def leer(self):
        return bytes(self.cache)

    def escribir(self, b):
        if self.enospc:
            raise OSError(errno.ENOSPC, "No space left on device")
        self.sucias.append((len(self.cache), bytes(b)))
        self.cache += b

    def fsync(self):
        if self.fallar_una_vez:
            self.fallar_una_vez = False
            self.sucias = []  # páginas marcadas limpias: nunca se reintentarán
            self.fsyncs.append("EIO")
            raise OSError(errno.EIO, "Input/output error")
        for off, b in self.sucias:
            if len(self.disco) < off:
                self.disco += b"\x00" * (off - len(self.disco))
            self.disco[off:off + len(b)] = b
        self.sucias = []
        self.fsyncs.append("ok")

    def corte(self):
        self.cache = bytearray(self.disco)


def construir(reg):
    reg.anexar("ABIERTO", nonce="nonce-de-prueba-1", sha_autorizacion="a" * 64)
    reg.anexar("ETAPA", etapa="panel")
    reg.anexar("ETAPA", etapa="simulacion")
    return reg.anexar("DECISION", tipo="INVALIDO", sha_objeto="b" * 64)


def ultimo(lineas):
    u = lineas[-1]
    return u["evento"] + "(" + str(u.get("etapa", u.get("tipo", u.get("etapa_max", "")))) + ")"


def main(d):
    os.makedirs(d, exist_ok=True)
    out = {}

    # ---- 1. qué detecta la cadena sin ancla
    dev = Archivo(os.path.join(d, "reg1.log"))
    reg = Registro(dev)
    cabeza_real = construir(reg)
    data = dev.leer()
    lb = data.split(b"\n")[:-1]
    casos = {}
    dev.reemplazar(data[:-40]); casos["cola_partida_mitad_de_linea"] = reg.leer()[1]["estado"]
    mod = bytearray(data); mod[len(lb[0]) + 1 + 60] ^= 1
    dev.reemplazar(bytes(mod)); casos["bit_cambiado_linea_2"] = reg.leer()[1]["estado"]
    dev.reemplazar(b"\n".join(lb[:1] + lb[2:]) + b"\n"); casos["linea_media_borrada"] = reg.leer()[1]["estado"]
    dev.reemplazar(b"\n".join([lb[0], lb[2], lb[1], lb[3]]) + b"\n"); casos["reorden"] = reg.leer()[1]["estado"]
    dev.reemplazar(data + lb[3] + b"\n"); casos["duplicado_final"] = reg.leer()[1]["estado"]
    dev.reemplazar(b"\n".join(lb[:3]) + b"\n")
    l3, e3 = reg.leer()
    casos["ultima_linea_borrada_entera"] = {"estado": e3["estado"], "ultimo_evento_visible": ultimo(l3),
                                            "cabeza_leida_igual_a_la_real": e3.get("cabeza") == cabeza_real,
                                            "conclusion": "indetectable sin ancla externa: parece que DECISION nunca se escribió"}
    out["1_deteccion_sin_ancla"] = casos

    # ---- 2. ningún prefijo de una línea válida parsea
    L = lb[3]
    out["2_prefijos"] = {"longitud_linea": len(L), "prefijos_que_parsean": [k for k in range(1, len(L)) if parsear(L[:k])[0]]}

    # ---- 3. reconciliación con cola partida, sin truncar
    res3 = {}
    for nombre, basura in (("prefijo_de_linea_sin_salto", lb[3][:30]),
                           ("ceros_sin_salto", b"\x00" * 57),
                           ("basura_con_salto_dentro", b"12\tdeadbeef\t{\"x\":1}\n99\tzz")):
        dev3 = Archivo(os.path.join(d, f"reg3_{nombre}.log"))
        reg3 = Registro(dev3)
        reg3.anexar("ABIERTO", nonce="n", sha_autorizacion="a" * 64)
        reg3.anexar("ETAPA", etapa="panel")
        buena = dev3.leer()
        dev3.escribir(basura)
        antes = reg3.leer()[1]["estado"]
        r1, r2 = reg3.reconciliar(), reg3.reconciliar()
        lineas, est = reg3.leer()
        intacto = dev3.leer().startswith(buena + basura)
        try:
            reg3.anexar("ABANDONADO", etapa_max="panel")
            lineas2, est2 = reg3.leer()
            fin = {"estado_final": est2["estado"], "eventos": [x["evento"] for x in lineas2]}
        except RuntimeError as exc:
            fin = {"estado_final": "no se puede anexar", "motivo": str(exc)}
        res3[nombre] = {"estado_antes": antes, "reconciliacion_1": r1, "reconciliacion_2_idempotente": r2,
                        "estado_despues": est["estado"], "bytes_originales_intactos": intacto,
                        "lector_sin_resincronizacion": reg3.leer(con_resincronizacion=False)[1]["estado"], **fin}
    dev3 = Archivo(os.path.join(d, "reg3_doble.log"))
    reg3 = Registro(dev3)
    reg3.anexar("ABIERTO", nonce="n", sha_autorizacion="a" * 64)
    dev3.escribir(b"77\tabc")
    reg3.reconciliar()
    dev3.reemplazar(dev3.leer()[:-25])  # la propia línea COLA_DESCARTADA quedó partida
    antes = reg3.leer()[1]["estado"]
    reg3.reconciliar()
    lineas, est = reg3.leer()
    res3["doble_cola_partida"] = {"estado_antes": antes, "estado_despues": est["estado"], "eventos": [x["evento"] for x in lineas]}
    out["3_reconciliacion"] = res3

    # ---- 4. modelo de disco: fsync que falla una vez (EIO) en DECISION
    def protocolo(disco, ancla_write_ahead):
        reg = Registro(disco)
        ancla = []  # canal externo (lo que el proceso comunicó fuera del almacén)
        ancla.append(("tras_consumo", reg.anexar("ABIERTO", nonce="n", sha_autorizacion="a" * 64)))  # §A.2
        reg.anexar("ETAPA", etapa="panel")
        reg.anexar("ETAPA", etapa="simulacion")
        if ancla_write_ahead:
            ancla.append(("anuncio_DECISION", "INVALIDO"))
        disco.fallar_una_vez = True
        try:
            reg.anexar("DECISION", tipo="INVALIDO", sha_objeto="b" * 64)
            r = "ok"
        except OSError as exc:
            r = "OSError " + errno.errorcode[exc.errno]
        lineas, _ = reg.leer()  # manejador §A.3: consulta el registro (caché), no la memoria
        ve = any(x["evento"] == "DECISION" for x in lineas)
        err = False
        if not ve:
            try:
                reg.anexar("ERROR", etapa_max="simulacion", sha_objeto="c" * 64)
                err = True
            except OSError:
                pass
        en_cache = ultimo(lineas)
        disco.corte()
        lineas, est = reg.leer()
        u = ultimo(lineas)
        recon = ("ABANDONADO(simulacion) = ERROR(simulacion) -> reintentable bajo la politica (i)" if u == "ETAPA(simulacion)" else u)
        return {"anexar_DECISION": r, "fsyncs": disco.fsyncs, "manejador_ve_DECISION_en_cache": ve, "manejador_escribio_ERROR": err,
                "ultimo_evento_en_cache_antes_del_corte": en_cache, "ultimo_evento_en_disco_tras_corte": u,
                "estado_cadena_en_disco": est["estado"], "reconciliacion_segun_A4": recon, "ancla": ancla,
                "ancla_detecta_perdida_de_DECISION": any(a[0] == "anuncio_DECISION" for a in ancla) and u != "DECISION(INVALIDO)"}
    out["4_modelo_disco_fsync_EIO_en_DECISION"] = {"diseno_tal_como_esta": protocolo(DiscoModelo(), False),
                                                    "variante_ancla_write_ahead": protocolo(DiscoModelo(), True)}

    # ---- 4b. ENOSPC en la escritura de DECISION (write falla; nada entra en caché)
    def enospc(ancla_write_ahead):
        disco = DiscoModelo()
        reg = Registro(disco)
        reg.anexar("ABIERTO", nonce="n", sha_autorizacion="a" * 64)
        reg.anexar("ETAPA", etapa="simulacion")
        disco.enospc = True
        ancla = ["anuncio_DECISION INVALIDO"] if ancla_write_ahead else []
        try:
            reg.anexar("DECISION", tipo="INVALIDO", sha_objeto="b" * 64)
            r = "ok"
        except OSError as exc:
            r = "OSError " + errno.errorcode[exc.errno]
        lineas, _ = reg.leer()
        ve = any(x["evento"] == "DECISION" for x in lineas)
        try:
            reg.anexar("ERROR", etapa_max="simulacion", sha_objeto="c" * 64)
            err = True
        except OSError:
            err = False
        disco.corte()
        lineas, _ = reg.leer()
        u = ultimo(lineas)
        return {"anexar_DECISION": r, "manejador_ve_DECISION": ve, "ERROR_escrito": err, "ultimo_evento": u, "ancla": ancla,
                "ancla_detecta": bool(ancla) and u != "DECISION(INVALIDO)"}
    out["4b_modelo_disco_ENOSPC_en_DECISION"] = {"diseno_tal_como_esta": enospc(False), "variante_ancla_write_ahead": enospc(True)}

    # ---- 4c. sin corte: reconciliación sobre la caché tras EIO y corte POSTERIOR (hueco de ceros)
    disco = DiscoModelo()
    reg = Registro(disco)
    reg.anexar("ABIERTO", nonce="n", sha_autorizacion="a" * 64)
    reg.anexar("ETAPA", etapa="simulacion")
    disco.fallar_una_vez = True
    try:
        reg.anexar("DECISION", tipo="INVALIDO", sha_objeto="b" * 64)
    except OSError:
        pass
    reg.anexar("TERMINAL_SIN_OBJETO", tipo="INVALIDO")  # la reconciliación corre sin reinicio: lee la caché
    antes = reg.leer()[1]["estado"]
    disco.corte()
    lineas, est = reg.leer()
    out["4c_reconciliacion_sobre_cache_y_corte_posterior"] = {"estado_sin_corte": antes, "estado_tras_corte": est["estado"],
                                                             "detalle": est.get("detalle"), "ultimo_valido": ultimo(lineas),
                                                             "bytes_disco_tienen_hueco_de_ceros": b"\x00" * 16 in bytes(disco.disco)}
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1])
