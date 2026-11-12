"""Prototipo (NO es E3) del almacén de ejecución v4.1 con política (iii), cero reintentos.

Contiene:
  - FsReal y FsSombra: el mismo interfaz de archivos; la sombra modela caché frente a disco y permite inyectar fallos;
  - registro encadenado con marcador 0x1E, lector con resincronización y COLA_DESCARTADA;
  - orquestador sintético (etapas, anuncio previo de la DECISION, objeto inmutable, PUBLICADO);
  - reconciliación y clasificación con tres valores sobre la decisión: inexistente (probada), persistida o incierta;
  - `puede_abrir`: única puerta para un intento; con la política (iii) se cierra para siempre tras el primer ABIERTO.
Los mutantes (MUTANTES) reproducen defectos conocidos para comprobar que las pruebas los detectan.
No importa ningún módulo de E3, no lee datos reales y escribe solo donde se le indique.
"""
import errno
import hashlib
import json
import os
import secrets

MARCA = b"\x1e"
GENESIS = "0" * 64
MUTANTES = set()  # se activan desde las pruebas


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class Choque(BaseException):
    """Muerte del proceso en este punto (SIGKILL u OOM): no corre ningún manejador."""


# ---------------------------------------------------------------- sistemas de archivos
class FsReal:
    def __init__(self, raiz):
        self.raiz = raiz

    def _p(self, r):
        return os.path.join(self.raiz, r)

    def leer(self, r):
        with open(self._p(r), "rb") as f:
            return f.read()

    def existe(self, r):
        return os.path.exists(self._p(r))

    def listar(self, d):
        return sorted(os.listdir(self._p(d))) if os.path.isdir(self._p(d)) else []

    def mkdir(self, d):
        os.makedirs(self._p(d), exist_ok=True)

    def anexar(self, r, datos):
        nuevo = not os.path.exists(self._p(r))
        fd = os.open(self._p(r), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            n = os.write(fd, datos)
            if n != len(datos):
                raise OSError(errno.EIO, "escritura corta")
            os.fsync(fd)
        finally:
            os.close(fd)
        if nuevo:
            self.fsync_dir(os.path.dirname(r))

    def crear_excl(self, r, datos):
        fd = os.open(self._p(r), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
        try:
            if os.write(fd, datos) != len(datos):
                raise OSError(errno.EIO, "escritura corta")
            os.fsync(fd)
        finally:
            os.close(fd)

    def enlazar(self, a, b):
        os.link(self._p(a), self._p(b))

    def borrar(self, r):
        os.unlink(self._p(r))

    def fsync_dir(self, d):
        fd = os.open(self._p(d), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class FsSombra:
    """Modelo: cada inodo tiene `cache` (lo que ve el proceso) y `disco` (lo durable). Las entradas de directorio también
    tienen versión en caché y en disco (se persisten con fsync_dir). `fallo` = (tipo, n_op, parámetro):
      choque_antes   · muere antes de la operación n;
      parcial        · en una escritura n: escribe un prefijo, lo deja en disco sin fsync y muere (escritura partida);
      EIO            · en el fsync n: falla; las páginas quedan «limpias» y esos bytes no llegan nunca al disco;
      ENOSPC         · en la escritura n: falla sin escribir;
      fsync_miente   · desde la operación n, fsync y fsync_dir devuelven OK sin persistir nada.
    """

    def __init__(self, fallo=None):
        self.inodos, self.dir_cache, self.dir_disco, self.n, self.fallo, self._ino = {}, {}, {}, 0, fallo, 0
        self.ops = []

    def _op(self, tipo):
        self.n += 1
        self.ops.append(tipo)
        f = self.fallo
        if f and f[0] == "choque_antes" and self.n == f[1]:
            raise Choque()
        return f if (f and self.n == f[1]) else None

    def _miente(self):
        return self.fallo and self.fallo[0] == "fsync_miente" and self.n >= self.fallo[1]

    def leer(self, r):
        return bytes(self.inodos[self.dir_cache[r]]["cache"])

    def existe(self, r):
        return r in self.dir_cache

    def listar(self, d):
        pre = d.rstrip("/") + "/"
        return sorted(k[len(pre):] for k in self.dir_cache if k.startswith(pre) and "/" not in k[len(pre):])

    def mkdir(self, d):
        pass  # los directorios existen y son durables en este modelo

    def _nuevo(self, r):
        self._ino += 1
        self.inodos[self._ino] = {"cache": bytearray(), "disco": b"", "perdido": None}
        self.dir_cache[r] = self._ino
        return self._ino

    def _escribir(self, ino, datos):
        f = self._op("write")
        if f and f[0] == "ENOSPC":
            raise OSError(errno.ENOSPC, "sin espacio")
        if f and f[0] == "parcial":
            k = max(1, min(len(datos) - 1, f[2]))
            i = self.inodos[ino]
            i["cache"] += datos[:k]
            i["disco"] = bytes(i["cache"])  # el prefijo llegó al disco por escritura diferida
            raise Choque()
        self.inodos[ino]["cache"] += datos

    def _fsync(self, ino):
        f = self._op("fsync")
        i = self.inodos[ino]
        if f and f[0] == "EIO":
            i["perdido"] = (len(i["disco"]), len(i["cache"]))  # páginas limpias: nunca llegan
            raise OSError(errno.EIO, "error de E/S en fsync")
        if self._miente():
            return
        c = bytes(i["cache"])
        if i["perdido"]:
            a, b = i["perdido"]
            c = c[:a] + b"\x00" * (b - a) + c[b:]
        i["disco"] = c

    def anexar(self, r, datos):
        ino = self.dir_cache.get(r) or self._nuevo(r)
        nuevo = r not in self.dir_disco
        self._escribir(ino, datos)
        self._fsync(ino)
        if nuevo:
            self.fsync_dir(os.path.dirname(r))

    def crear_excl(self, r, datos):
        self._op("open_excl")
        if r in self.dir_cache:
            raise FileExistsError(errno.EEXIST, r)
        ino = self._nuevo(r)
        self._escribir(ino, datos)
        self._fsync(ino)

    def enlazar(self, a, b):
        self._op("link")
        if b in self.dir_cache:
            raise FileExistsError(errno.EEXIST, b)
        self.dir_cache[b] = self.dir_cache[a]

    def borrar(self, r):
        self._op("unlink")
        del self.dir_cache[r]

    def fsync_dir(self, d):
        f = self._op("fsync_dir")
        if f and f[0] == "EIO":
            raise OSError(errno.EIO, "error de E/S en fsync de directorio")
        if self._miente():
            return
        pre = d.rstrip("/") + "/"
        for k in [k for k in self.dir_disco if k.startswith(pre)]:
            if k not in self.dir_cache:
                del self.dir_disco[k]
        for k, v in self.dir_cache.items():
            if k.startswith(pre):
                self.dir_disco[k] = v

    def tras_corte(self):
        """Estado después de un corte de energía: solo lo durable."""
        s = FsSombra()
        s._ino = self._ino
        for k, ino in self.dir_disco.items():
            if ino not in s.inodos:
                s.inodos[ino] = {"cache": bytearray(self.inodos[ino]["disco"]), "disco": self.inodos[ino]["disco"], "perdido": None}
            s.dir_cache[k] = s.dir_disco[k] = ino
        return s

    def tras_salida_sin_corte(self):
        """El proceso terminó (o murió) y el sistema siguió vivo: la caché se escribe, salvo las páginas perdidas por EIO."""
        s = FsSombra()
        s._ino = self._ino
        for k, ino in self.dir_cache.items():
            i = self.inodos[ino]
            c = bytes(i["cache"])
            if i["perdido"]:
                a, b = i["perdido"]
                c = c[:a] + b"\x00" * (b - a) + c[b:]
            if ino not in s.inodos:
                s.inodos[ino] = {"cache": bytearray(c), "disco": c, "perdido": None}
            s.dir_cache[k] = s.dir_disco[k] = ino
        return s


# ---------------------------------------------------------------- registro encadenado
REG = "almacen/registro.log"
OBJ = "almacen/objetos"


def linea(seq, prev, tipo, datos):
    cuerpo = json.dumps({"seq": seq, "prev": prev, "tipo": tipo, "datos": datos}, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=True, allow_nan=False).encode()
    return MARCA + cuerpo + b"\n"


def _parsear(seg: bytes):
    """seg empieza en MARCA; devuelve el dict si es un registro completo y bien formado, si no None."""
    if not (seg.startswith(MARCA) and seg.endswith(b"\n")) or seg.count(b"\n") != 1:
        return None
    try:
        r = json.loads(seg[1:-1].decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not (isinstance(r, dict) and set(r) == {"seq", "prev", "tipo", "datos"}) or linea(r["seq"], r["prev"], r["tipo"], r["datos"]) != seg:
        return None
    return r


def leer_registro(b: bytes):
    """Devuelve dict(estado, eventos, cabeza, fin_valido, cola). estado ∈ OK, COLA_CORTADA, CADENA_ROTA."""
    return _leer(b, 0, [], GENESIS, 0)


def _leer(b, pos, eventos, cabeza, seq):
    eventos = list(eventos)
    while pos < len(b):
        if b[pos:pos + 1] != MARCA:
            return _resto(b, pos, eventos, cabeza, seq)
        fin = b.find(b"\n", pos)
        sig = b.find(MARCA, pos + 1)
        if fin == -1 or (sig != -1 and sig < fin):
            return _resto(b, pos, eventos, cabeza, seq)
        seg = b[pos:fin + 1]
        r = _parsear(seg)
        if r is None:
            return _resto(b, pos, eventos, cabeza, seq)
        if r["seq"] != seq or r["prev"] != cabeza:
            return {"estado": "CADENA_ROTA", "eventos": eventos, "cabeza": cabeza, "fin_valido": pos, "motivo": "encadenamiento"}
        eventos.append(r)
        cabeza, seq, pos = sha(seg), seq + 1, fin + 1
    return {"estado": "OK", "eventos": eventos, "cabeza": cabeza, "fin_valido": pos, "cola": b""}


def _resto(b, pos, eventos, cabeza, seq):
    """Hay bytes que no forman un registro válido desde `pos`. Si después aparece un COLA_DESCARTADA encadenado que
    declara exactamente esos bytes, se saltan y se sigue. Si aparece cualquier otro registro completo, la cadena está rota.
    Si no aparece ninguno, es una cola cortada."""
    k = b.find(MARCA, pos + 1)
    while k != -1:
        fin = b.find(b"\n", k)
        if fin != -1:
            r = _parsear(b[k:fin + 1])
            if r is not None:
                d = r["datos"] if isinstance(r["datos"], dict) else {}
                if (r["tipo"] == "COLA_DESCARTADA" and r["seq"] == seq and r["prev"] == cabeza and d.get("desde") == pos
                        and d.get("longitud") == k - pos and d.get("sha") == sha(b[pos:k])):
                    return _leer(b, k, eventos, cabeza, seq)
                if "M5_cola_sin_marcador" in MUTANTES:
                    k = b.find(MARCA, k + 1)
                    continue
                return {"estado": "CADENA_ROTA", "eventos": eventos, "cabeza": cabeza, "fin_valido": pos, "motivo": "registro tras basura"}
        k = b.find(MARCA, k + 1)
    return {"estado": "COLA_CORTADA", "eventos": eventos, "cabeza": cabeza, "fin_valido": pos, "cola": b[pos:]}


class Almacen:
    def __init__(self, fs):
        self.fs = fs
        fs.mkdir("almacen")
        fs.mkdir(OBJ)

    def leer(self):
        return leer_registro(self.fs.leer(REG) if self.fs.existe(REG) else b"")

    def anexar(self, tipo, datos, cabeza_esperada):
        """CAS dentro del bloqueo: se relee el registro y se compara la cabeza antes de escribir (R-7)."""
        st = self.leer()
        if st["estado"] != "OK" or st["cabeza"] != cabeza_esperada:
            raise RuntimeError(f"CAS: estado {st['estado']} o cabeza distinta")
        ln = linea(len(st["eventos"]), st["cabeza"], tipo, datos)
        self.fs.anexar(REG, ln)
        return sha(ln)

    def publicar_objeto(self, contenido: bytes):
        h = sha(contenido)
        tmp = f"{OBJ}/.tmp-{secrets.token_hex(8)}"
        self.fs.crear_excl(tmp, contenido)
        try:
            self.fs.enlazar(tmp, f"{OBJ}/{h}")
        except FileExistsError:
            if self.fs.leer(f"{OBJ}/{h}") != contenido:
                raise RuntimeError("objeto existente con otros bytes")
        self.fs.fsync_dir(OBJ)
        self.fs.borrar(tmp)
        self.fs.fsync_dir(OBJ)
        return h


# ---------------------------------------------------------------- orquestador sintético
ETAPAS = ("panel", "validez", "simulacion")


class FalloAlmacen(Exception):
    pass


def serializar_objeto(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def orquestar(fs, canal, escenario, verdad, id_eval="EVAL-SINTETICA"):
    """escenario ∈ EVALUADO, INVALIDO, ERROR_panel, ERROR_validez, ERROR_simulacion.
    `canal` (lista) modela la salida estándar capturada fuera del proceso: sobrevive a cualquier fallo.
    `verdad` registra, para las pruebas, lo que el proceso llegó a hacer."""
    alm = Almacen(fs)
    st = alm.leer()
    if not puede_abrir(st, canal, id_eval, alm):
        raise RuntimeError("APERTURA RECHAZADA")
    cab = st["cabeza"]
    try:
        cab = alm.anexar("ABIERTO", {"evaluacion": id_eval, "nonce": "n-sintetico"}, cab)
        canal.append({"tipo": "ABIERTO_DURABLE", "evaluacion": id_eval, "cabeza": cab})
        verdad["datos_leidos"] = True  # recién acá se leerían datos
        for etapa in ETAPAS:
            cab = alm.anexar("ETAPA", {"etapa": etapa}, cab)
            if escenario == f"ERROR_{etapa}":
                raise ValueError(f"fallo de cálculo sintético en {etapa}")
            if etapa == "validez" and escenario == "INVALIDO":
                return _decidir(alm, canal, verdad, cab, "INVALIDO", {"veredicto": "INVALIDO", "motivo": "sintético"})
        return _decidir(alm, canal, verdad, cab, "EVALUADO", {"veredicto": "EVALUADO", "estadistico": 0.0123})
    except OSError as e:
        # Regla R-2: ante cualquier fallo del almacén, no escribir nada más; anunciar y salir.
        canal.append({"tipo": "FALLO_ALMACEN", "evaluacion": id_eval, "errno": e.errno, "decision_anunciada": verdad.get("anunciada")})
        return "SALIDA_POR_FALLO_DE_ALMACEN"
    except ValueError as e:
        if verdad.get("anunciada"):
            raise  # imposible por construcción: no se calcula nada después de anunciar
        try:
            cab = alm.anexar("ERROR", {"etapa": str(e).split()[-1]}, cab)
        except OSError as e2:
            canal.append({"tipo": "FALLO_ALMACEN", "evaluacion": id_eval, "errno": e2.errno, "decision_anunciada": None})
            return "SALIDA_POR_FALLO_DE_ALMACEN"
        canal.append({"tipo": "ERROR_DURABLE", "evaluacion": id_eval, "cabeza": cab})
        return "ERROR"


def _decidir(alm, canal, verdad, cab, tipo, obj):
    contenido = serializar_objeto(obj)
    h = sha(contenido)
    verdad["decision_calculada"] = tipo
    anuncio = {"tipo": "ANUNCIO_DECISION", "decision": tipo, "sha_objeto": h, "seq": len(alm.leer()["eventos"]), "cabeza": cab}
    if "M2_anuncio_tardio" not in MUTANTES:
        canal.append(anuncio)
        verdad["anunciada"] = tipo
    cab = alm.anexar("DECISION", {"tipo": tipo, "sha_objeto": h}, cab)
    if "M2_anuncio_tardio" in MUTANTES:
        canal.append(anuncio)
        verdad["anunciada"] = tipo
    verdad["objeto"] = contenido
    alm.publicar_objeto(contenido)
    cab = alm.anexar("PUBLICADO", {"sha_objeto": h}, cab)
    canal.append({"tipo": "PUBLICADO_DURABLE", "cabeza": cab})
    return tipo


# ---------------------------------------------------------------- puerta y reconciliación
def puede_abrir(st, canal, id_eval, alm=None):
    """Política (iii): un único ABIERTO por evaluación, para siempre. Se mira el registro Y el canal externo (ancla):
    si el ABIERTO se perdió del disco pero quedó anunciado, no se vuelve a abrir."""
    if st["estado"] != "OK":
        return False
    abiertos = [e for e in st["eventos"] if e["tipo"] == "ABIERTO"]
    if abiertos and "M8_reintento_tras_error" in MUTANTES and st["eventos"][-1]["tipo"] in ("ERROR", "RECONCILIADO"):
        return True  # política (i): un ERROR habilita otro intento
    if abiertos:
        return False
    if "M4_puerta_sin_canal" not in MUTANTES and any(c.get("tipo") == "ABIERTO_DURABLE" and c.get("evaluacion") == id_eval for c in canal):
        return False
    if alm is not None and alm.fs.listar(OBJ) and any(not n.startswith(".tmp-") for n in alm.fs.listar(OBJ)):
        return False  # objetos sin registro que los cite: inconsistencia
    return True


def clasificar(fs, canal, id_eval="EVAL-SINTETICA"):
    """Devuelve (clase, detalle). Clases:
      VACIO · ningún intento (solo esta clase permite abrir);
      EVALUADO / INVALIDO · decisión persistida y objeto verificado;
      TERMINAL_SIN_OBJETO(tipo) · decisión persistida, objeto ausente o alterado;
      DECISION_ANUNCIADA_NO_PERSISTIDA(tipo) · el canal prueba que se decidió; el registro no lo tiene;
      NO_DECIDIDO(motivo) · decisión inexistente PROBADA (ERROR durable, o canal con salida sin anuncio, o el proceso
                             no llegó a una etapa donde se pueda decidir);
      INCIERTO · no se puede probar si hubo decisión;
      BLOQUEADO(motivo) · cadena rota u objetos huérfanos.
    Con la política (iii) todas las clases salvo VACIO son terminales y ninguna admite otro ABIERTO."""
    st = leer_registro(fs.leer(REG) if fs.existe(REG) else b"")
    if st["estado"] == "CADENA_ROTA":
        return "BLOQUEADO", "cadena rota"
    ev = st["eventos"]
    tipos = [e["tipo"] for e in ev]
    nombres = [n for n in fs.listar(OBJ) if not n.startswith(".tmp-")]
    decisiones = [e for e in ev if e["tipo"] == "DECISION"]
    citados = {e["datos"]["sha_objeto"] for e in decisiones}
    if any(n not in citados for n in nombres):
        return "BLOQUEADO", "objeto sin DECISION que lo cite"
    canal_ev = [c for c in canal if c.get("evaluacion", id_eval) == id_eval]
    if "ABIERTO" not in tipos:
        if any(c.get("tipo") == "ABIERTO_DURABLE" for c in canal_ev) and "M4_puerta_sin_canal" not in MUTANTES:
            return "INCIERTO", "el canal registra un ABIERTO que el registro no tiene"
        return "VACIO", None
    if decisiones:
        d = decisiones[-1]["datos"]
        ruta = f"{OBJ}/{d['sha_objeto']}"
        if fs.existe(ruta) and sha(fs.leer(ruta)) == d["sha_objeto"]:
            return d["tipo"], "objeto verificado"
        return f"TERMINAL_SIN_OBJETO({d['tipo']})", None
    anuncios = [c for c in canal if c.get("tipo") == "ANUNCIO_DECISION"]
    if anuncios:
        return f"DECISION_ANUNCIADA_NO_PERSISTIDA({anuncios[-1]['decision']})", None
    if "ERROR" in tipos:
        return "NO_DECIDIDO", "ERROR durable"
    etapas = [e["datos"]["etapa"] for e in ev if e["tipo"] == "ETAPA"]
    ultima = etapas[-1] if etapas else None
    if ultima in (None, "panel") or "M1_abandonado" in MUTANTES:
        return "NO_DECIDIDO", f"última etapa durable: {ultima}"
    if any(c.get("tipo") in ("FALLO_ALMACEN", "ERROR_DURABLE") and not c.get("decision_anunciada") for c in canal_ev):
        return "NO_DECIDIDO", "el canal registra la salida sin anuncio de decisión"
    return "INCIERTO", f"última etapa durable: {ultima}, sin decisión ni prueba de que no la hubo"


def reconciliar(fs, canal, id_eval="EVAL-SINTETICA"):
    """Solo agrega líneas. Si hay cola cortada, agrega COLA_DESCARTADA (sin truncar). Después agrega una línea
    RECONCILIADO con la clase, salvo que la última línea ya sea esa misma reconciliación (idempotente)."""
    b = fs.leer(REG) if fs.existe(REG) else b""
    st = leer_registro(b)
    if st["estado"] == "CADENA_ROTA":
        return "BLOQUEADO", "cadena rota"
    if st["estado"] == "COLA_CORTADA":
        cola = st["cola"]
        ln = linea(len(st["eventos"]), st["cabeza"], "COLA_DESCARTADA", {"desde": st["fin_valido"], "longitud": len(cola), "sha": sha(cola)})
        fs.anexar(REG, ln)
        st = leer_registro(fs.leer(REG))
        assert st["estado"] == "OK", st["estado"]
    clase, det = clasificar(fs, canal, id_eval)
    if clase != "VACIO":
        ult = st["eventos"][-1] if st["eventos"] else None
        if not (ult and ult["tipo"] == "RECONCILIADO" and ult["datos"].get("clase") == clase):
            fs.anexar(REG, linea(len(st["eventos"]), st["cabeza"], "RECONCILIADO", {"clase": clase}))
    return clase, det
