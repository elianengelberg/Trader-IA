"""E3 · F3 (calidad de datos y reconstrucción estructural). NO calcula retornos de estrategia (N22: no importa motor.py).

Uso:  python -I calidad.py <dir_datos_vision> <dir_btc_eth_locales> <dir_salida>

Produce:
  - series diarias por símbolo (npz) con estado por día: 0 sin fila · 1 activo · 2 fila con 0 operaciones · 3 fila inválida
    · 4 conflicto mensual/diario;
  - auditoría por símbolo (archivos, checksums, huecos, filas inválidas, episodios de listado, cortes y reanudaciones,
    cola de velas con 0 operaciones tras la última negociación);
  - resumen por año y clasificación de cada día faltante: fallo de descarga · ausencia de archivo · fila ausente en archivo
    presente · suspensión (inactivo con reanudación) · tras el fin de cotización.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np

INICIO = dt.date(2017, 7, 1)
FIN = dt.date(2026, 5, 31)
D = (FIN - INICIO).days + 1
DIA_MS, DIA_US = 86_400_000, 86_400_000_000


def idx(d: dt.date) -> int:
    return (d - INICIO).days


def fecha(i: int) -> dt.date:
    return INICIO + dt.timedelta(days=int(i))


def leer_zip(ruta: Path):
    """Filas (fecha, O, H, L, C, qv, ntrades, valida) de un zip de Vision; sin suponer encabezado (N2)."""
    filas, descartadas = [], 0
    with zipfile.ZipFile(ruta) as z:
        nombres = z.namelist()
        if len(nombres) != 1:
            raise ValueError(f"zip con {len(nombres)} miembros: {ruta.name}")
        texto = z.read(nombres[0]).decode("utf-8", errors="replace")
    for r in csv.reader(io.StringIO(texto)):
        if not r:
            continue
        try:
            ot, o, h, l, c, _vb, ct, qv, nt = int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), int(r[6]), float(r[7]), int(float(r[8]))
        except (ValueError, IndexError):
            descartadas += 1
            continue
        us = ot > 10**14
        dur = ct - ot + 1
        fecha_d = dt.datetime.fromtimestamp(ot / (1e6 if us else 1e3), dt.timezone.utc).date()
        alineado = (ot % (DIA_US if us else DIA_MS)) == 0
        valida = (dur == (DIA_US if us else DIA_MS)) and alineado and min(o, h, l, c) > 0 and l <= min(o, c) and h >= max(o, c) and qv >= 0 and nt >= 0
        filas.append((fecha_d, o, h, l, c, qv, nt, valida))
    return filas, descartadas


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def procesar_simbolo(s: str, dirs_mensual: Path, dirs_diario: Path | None, fallos_descarga: set):
    a = {k: np.full(D, np.nan) for k in ("O", "H", "L", "C", "QV")}
    nt = np.full(D, -1, dtype=np.int64)
    estado = np.zeros(D, dtype=np.int8)
    aud = {"simbolo": s, "zips_mensuales": 0, "checksum_ok": 0, "checksum_falla": [], "filas_descartadas": 0,
           "fechas_repetidas": 0, "filas_invalidas": 0, "fuera_de_rango": 0, "conflictos_mensual_diario": 0,
           "meses_con_archivo": [], "dias_reparados_con_diarios": 0, "fallos_descarga": sorted(fallos_descarga)}
    vistos = {}

    def cargar(ruta: Path, origen: str):
        filas, desc = leer_zip(ruta)
        aud["filas_descartadas"] += desc
        cuenta = {}
        for f in filas:
            cuenta[f[0]] = cuenta.get(f[0], 0) + 1
        for f in filas:
            d = f[0]
            if not (INICIO <= d <= FIN):
                aud["fuera_de_rango"] += 1
                continue
            i = idx(d)
            if cuenta[d] > 1:
                aud["fechas_repetidas"] += 1
                estado[i] = 3
                continue
            if (i, "m") in vistos and origen == "d":
                prev = vistos[(i, "m")]
                if prev[1:7] != f[1:7]:
                    aud["conflictos_mensual_diario"] += 1
                    estado[i] = 4
                continue
            vistos[(i, origen[0])] = f
            if not f[7]:
                aud["filas_invalidas"] += 1
                estado[i] = 3
                continue
            for k, v in zip(("O", "H", "L", "C", "QV"), f[1:6]):
                a[k][i] = v
            nt[i] = f[6]
            estado[i] = 1 if f[6] > 0 else 2
            if origen == "d":
                aud["dias_reparados_con_diarios"] += 1

    for z in sorted(dirs_mensual.glob(f"{s}-1d-*.zip")):
        chk = z.with_name(z.name + ".CHECKSUM")
        ok = chk.exists() and chk.read_text().split()[0].strip().lower() == sha(z)
        aud["zips_mensuales"] += 1
        aud["meses_con_archivo"].append(z.name.split("-1d-")[1][:7])
        if ok:
            aud["checksum_ok"] += 1
            cargar(z, "m")
        else:
            aud["checksum_falla"].append(z.name)
    if dirs_diario is not None and dirs_diario.exists():
        for z in sorted(dirs_diario.glob(f"{s}-1d-*.zip")):
            chk = z.with_name(z.name + ".CHECKSUM")
            if chk.exists() and chk.read_text().split()[0].strip().lower() == sha(z):
                cargar(z, "d")
            else:
                aud["checksum_falla"].append(z.name)
    return a, nt, estado, aud


def episodios(estado: np.ndarray):
    """Listados vigentes por actividad (v3 §2.2.3): termina tras ≥ 30 días seguidos inactivos; sin anuncios (A3 bloqueado)."""
    act = np.flatnonzero(estado == 1)
    if act.size == 0:
        return [], []
    eps, cortes = [], []
    ini = prev = int(act[0])
    for i in act[1:]:
        i = int(i)
        hueco = i - prev - 1
        if hueco >= 30:
            eps.append((ini, prev))
            ini = i
        elif hueco >= 1:
            cortes.append((prev, i, hueco))
        prev = i
    eps.append((ini, prev))
    return eps, cortes


def main(dir_vision: Path, dir_local: Path, salida: Path):
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "series").mkdir(exist_ok=True)
    usdt = json.loads((dir_vision / "listados" / "simbolos_usdt.json").read_text())
    det = json.loads((dir_vision / "resultado_descarga_mensual.json").read_text())["detalle"]
    fallos = {}
    for r in det:
        if r["estado"] in ("fallo_descarga", "checksum_falla"):
            s = r["key"].split("/")[4]
            fallos.setdefault(s, set()).add(r["key"].rsplit("-1d-", 1)[1][:7])
    auditoria, resumen_anual = [], {}
    for s in usdt:
        if s in ("BTCUSDT", "ETHUSDT"):
            dm = dir_local / s / "spot" / "monthly" / "klines" / s / "1d"
        else:
            dm = dir_vision / "data" / "spot" / "monthly" / "klines" / s / "1d"
        dd = dir_vision / "data" / "spot" / "daily" / "klines" / s / "1d"
        a, nt, estado, aud = procesar_simbolo(s, dm, dd, fallos.get(s, set()))
        eps, cortes = episodios(estado)
        aud["episodios"] = [(fecha(i).isoformat(), fecha(j).isoformat()) for i, j in eps]
        aud["cortes_con_reanudacion"] = [(fecha(i).isoformat(), fecha(j).isoformat(), h) for i, j, h in cortes]
        if eps:
            ult = eps[-1][1]
            cola = estado[ult + 1:]
            aud["cola_tras_ultimo_activo"] = {"dias": int(cola.size), "filas_cero_operaciones": int((cola == 2).sum()),
                                              "sin_fila": int((cola == 0).sum())}
            # Clasificación de los días no activos entre el primer y el último día activo
            prim = eps[0][0]
            meses_arch = set(aud["meses_con_archivo"])
            clase = {"sin_archivo_mensual": 0, "fila_ausente_en_archivo": 0, "cero_operaciones": 0, "invalida_o_conflicto": 0,
                     "fallo_descarga": 0}
            for i in range(prim, ult + 1):
                if estado[i] == 1:
                    continue
                m = fecha(i).strftime("%Y-%m")
                if m in fallos.get(s, set()):
                    clase["fallo_descarga"] += 1
                elif estado[i] == 2:
                    clase["cero_operaciones"] += 1
                elif estado[i] in (3, 4):
                    clase["invalida_o_conflicto"] += 1
                elif m not in meses_arch:
                    clase["sin_archivo_mensual"] += 1
                else:
                    clase["fila_ausente_en_archivo"] += 1
            aud["dias_no_activos_dentro_de_la_vida"] = clase
            aud["primer_activo"], aud["ultimo_activo"] = fecha(prim).isoformat(), fecha(ult).isoformat()
            aud["dias_activos"] = int((estado == 1).sum())
            for i, j in eps:
                y0 = fecha(i).year
                resumen_anual.setdefault(y0, {"altas": 0, "bajas": 0})["altas"] += 1
                if j < idx(dt.date(2026, 5, 1)):
                    resumen_anual.setdefault(fecha(j).year, {"altas": 0, "bajas": 0})["bajas"] += 1
        np.savez_compressed(salida / "series" / f"{s.encode('unicode_escape').decode('ascii').replace(chr(92), '_')}.npz",
                            simbolo=np.array(s), O=a["O"], H=a["H"], L=a["L"], C=a["C"], QV=a["QV"], NT=nt, estado=estado)
        auditoria.append(aud)
    (salida / "auditoria_por_simbolo.json").write_text(json.dumps(auditoria, ensure_ascii=False, indent=0))
    tot = {k: sum(x.get(k, 0) if not isinstance(x.get(k, 0), list) else len(x.get(k)) for x in auditoria)
           for k in ("zips_mensuales", "checksum_ok", "checksum_falla", "filas_descartadas", "fechas_repetidas", "filas_invalidas",
                     "conflictos_mensual_diario", "dias_reparados_con_diarios", "fuera_de_rango")}
    clases = {}
    for x in auditoria:
        for k, v in x.get("dias_no_activos_dentro_de_la_vida", {}).items():
            clases[k] = clases.get(k, 0) + v
    resumen = {"simbolos_usdt": len(usdt), "con_algun_dia_activo": sum(1 for x in auditoria if x.get("episodios")),
               "totales": tot, "dias_no_activos_dentro_de_la_vida": clases,
               "simbolos_con_cortes_reanudados": sum(1 for x in auditoria if x.get("cortes_con_reanudacion")),
               "simbolos_con_mas_de_un_episodio": sum(1 for x in auditoria if len(x.get("episodios", [])) > 1),
               "colas_con_velas_cero_operaciones": sum(1 for x in auditoria if x.get("cola_tras_ultimo_activo", {}).get("filas_cero_operaciones", 0) > 0),
               "altas_y_bajas_por_anio": dict(sorted(resumen_anual.items()))}
    (salida / "resumen_calidad.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1))
    print(json.dumps(resumen, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
