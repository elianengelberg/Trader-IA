"""P4 (revisor) · `flock` entre procesos, carrera de borrado/recreación, `link()`/`O_EXCL` y `fsync` del directorio.
NO es E3. Archivos de prueba inventados.

Pone a prueba (§A.2 «bloqueo» y «objetos»):
  1. un segundo proceso NO obtiene LOCK_EX|LOCK_NB mientras el primero lo tiene; al morir el primero con SIGKILL, el
     bloqueo se libera;
  2. si el archivo bloqueado se borra y se vuelve a crear (L-12 parcial), un segundo proceso obtiene SU PROPIO bloqueo
     sobre el inodo nuevo: dos «exclusivos» a la vez. Comprobación mitigante: fstat(fd).st_ino == stat(ruta).st_ino tras
     bloquear (cierra la ventana salvo la carrera entre esa comprobación y el uso);
  3. `link()` falla con EEXIST si el nombre ya existe (publicación sin sobrescritura); O_EXCL falla si el temporal ya
     existe (un temporal huérfano de un intento anterior bloquea el nombre); fsync de un descriptor de directorio funciona.
Uso: /usr/bin/python3 -I -B p4_flock_link_excl.py <dir_trabajo>
"""
import errno
import fcntl
import json
import os
import signal
import subprocess
import sys
import time

HIJO = r"""
import fcntl, json, os, sys, time
ruta, modo = sys.argv[1], sys.argv[2]
fd = os.open(ruta, os.O_RDWR | os.O_CREAT, 0o644)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    ok = True
except OSError as exc:
    ok = f"EWOULDBLOCK({exc.errno})"
print(json.dumps({"bloqueo": ok, "inodo_fd": os.fstat(fd).st_ino, "inodo_ruta": os.stat(ruta).st_ino}), flush=True)
if modo == "retener":
    time.sleep(30)
"""


def hijo(ruta, modo):
    p = subprocess.Popen([sys.executable, "-I", "-B", "-c", HIJO, ruta, modo], stdout=subprocess.PIPE, text=True)
    primera = json.loads(p.stdout.readline())
    return p, primera


def main(d):
    os.makedirs(d, exist_ok=True)
    out = {}
    ruta = os.path.join(d, "bloqueo")

    # 1. exclusión entre procesos y liberación al morir
    fd = os.open(ruta, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    p, r = hijo(ruta, "probar")
    p.wait()
    out["1_segundo_proceso_mientras_el_primero_retiene"] = r["bloqueo"]
    os.close(fd)  # libera
    p, r = hijo(ruta, "retener")
    out["1_hijo_retiene"] = r["bloqueo"]
    fd = os.open(ruta, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        out["1_padre_mientras_hijo_retiene"] = True
    except OSError as exc:
        out["1_padre_mientras_hijo_retiene"] = f"EWOULDBLOCK({exc.errno})"
    p.send_signal(signal.SIGKILL)
    p.wait()
    t0 = time.monotonic()
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            out["1_padre_tras_SIGKILL_del_hijo"] = f"bloqueo obtenido tras {time.monotonic() - t0:.3f}s"
            break
        except OSError:
            if time.monotonic() - t0 > 5:
                out["1_padre_tras_SIGKILL_del_hijo"] = "NO liberado en 5 s"
                break
            time.sleep(0.01)
    os.close(fd)

    # 2. borrado y recreación del archivo bloqueado
    fd = os.open(ruta, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    ino_a = os.fstat(fd).st_ino
    os.unlink(ruta)
    open(ruta, "ab").close()  # alguien recrea el registro (vacío)
    p, r = hijo(ruta, "probar")
    p.wait()
    out["2_tras_borrar_y_recrear"] = {"A_sigue_bloqueando_inodo": ino_a, "B_obtiene_bloqueo": r["bloqueo"],
                                     "B_inodo": r["inodo_fd"], "dos_exclusivos_a_la_vez": r["bloqueo"] is True,
                                     "mitigacion_A_detecta_fstat_vs_stat": os.fstat(fd).st_ino != os.stat(ruta).st_ino}
    os.close(fd)

    # 3. link() / O_EXCL / fsync del directorio
    objetos = os.path.join(d, "objetos")
    os.makedirs(objetos, exist_ok=True)
    contenido = b"objeto de prueba\n"
    nombre = os.path.join(objetos, "nombre_igual_a_su_hash")
    tmp = os.path.join(objetos, ".tmp_nombre_igual_a_su_hash")
    fdt = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    os.write(fdt, contenido)
    os.fsync(fdt)
    os.close(fdt)
    os.link(tmp, nombre)
    dfd = os.open(objetos, os.O_RDONLY)
    os.fsync(dfd)
    os.close(dfd)
    out["3_publicacion_inicial"] = {"existe": os.path.exists(nombre), "fsync_directorio": "ok"}
    try:
        os.link(tmp, nombre)
        out["3_link_sobre_existente"] = "NO falló"
    except OSError as exc:
        out["3_link_sobre_existente"] = errno.errorcode[exc.errno]
    try:
        os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        out["3_O_EXCL_con_temporal_huerfano"] = "NO falló"
    except OSError as exc:
        out["3_O_EXCL_con_temporal_huerfano"] = errno.errorcode[exc.errno] + " (un temporal huérfano con nombre determinista bloquea el reintento)"
    # sobrescribir el objeto publicado vía el temporal (mismo inodo): link() no protege el CONTENIDO
    with open(tmp, "r+b") as f:
        f.seek(0)
        f.write(b"OBJETO")
    out["3_contenido_publicado_tras_escribir_por_el_temporal"] = open(nombre, "rb").read()[:6].decode()
    out["3_nota"] = ("link() crea un segundo nombre del MISMO inodo: mientras exista el temporal, escribir por él altera el objeto "
                     "publicado. Hay que unlink() el temporal tras publicar y, como root, el modo 0444 no impide escribir.")
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1])
