"""Experimentos reproducibles: configuración JSON → datos → (estrés) → simulación → conciliación → métricas →
registro (JSONL) con la huella del código, de la configuración y de los datos.

Configuración:
  {"nombre": str,
   "datos": {"fuente": "sintetico", "semilla": int, ...ParamsSintetico}
            | {"fuente": "binance_vision", "directorio": ruta},
   "division": "desarrollo" | "validacion" | "test" | {"desde": "AAAA-MM-DD", "hasta": "AAAA-MM-DD"},
   "politica": {"nombre": str, "params": {...}},
   "costes": {...Costes}, "filtros": {...Filtros}, "motor": {...ParamsMotor},
   "estres": {"funding_factor": 1.0, "omitir_funding": 0.0, "semilla": 0}}"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
from dataclasses import replace
from pathlib import Path

from hcarry.conventions import ms
from hcarry.data.schema import Panel
from hcarry.estrategias import construir
from hcarry.lab.divisiones import DIVISIONES
from hcarry.metricas import calcular
from hcarry.model.conciliacion import conciliar
from hcarry.model.costes import Costes, Filtros
from hcarry.model.motor import ParamsMotor, Resultado, simular

RAIZ = Path(__file__).resolve().parents[3]
SRC = RAIZ / "src"


def canonico(obj) -> str:  # type: ignore[no-untyped-def]
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha(texto: str | bytes) -> str:
    return hashlib.sha256(texto.encode("utf-8") if isinstance(texto, str) else texto).hexdigest()


def huella_codigo() -> str:
    """SHA-256 del árbol src/ (rutas y contenidos ordenados)."""
    h = hashlib.sha256()
    for p in sorted(SRC.rglob("*.py")):
        h.update(str(p.relative_to(SRC)).encode())
        h.update(b"\0")
        h.update(p.read_bytes())
    return h.hexdigest()


def config_sin_nombre(cfg: dict) -> dict:
    return {k: v for k, v in cfg.items() if k not in ("nombre", "notas")}


_CACHE: dict[str, tuple[Panel, dict]] = {}


def cargar_datos(datos: dict) -> tuple[Panel, dict]:
    """Panel completo de la fuente y su identificación (id estable de los datos)."""
    clave = canonico(datos)
    if clave in _CACHE:
        return _CACHE[clave]
    if "nulo_semilla" in datos:  # mundo NULO: las tasas de funding se barajan en el tiempo (sin persistencia)
        base, ident = cargar_datos({k: v for k, v in datos.items() if k != "nulo_semilla"})
        rng = random.Random(int(datos["nulo_semilla"]))
        tasas = [e.tasa for e in base.funding]
        rng.shuffle(tasas)
        nulo = Panel(base.barras, [replace(e, tasa=f) for e, f in zip(base.funding, tasas)], base.origen + ":nulo",
                     base.notas + ["MUNDO NULO: funding permutado en el tiempo"])
        _CACHE[clave] = (nulo, {**ident, "id": sha(ident["id"] + f":nulo{datos['nulo_semilla']}")})
        return _CACHE[clave]
    fuente = datos["fuente"]
    if fuente == "sintetico":
        from hcarry.data.sintetico import ParamsSintetico, generar
        p = ParamsSintetico(**{k: v for k, v in datos.items() if k != "fuente"})
        panel = generar(p)
        ident = {"fuente": "sintetico", "id": sha(canonico(p.descripcion())), "sintetico": True}
    elif fuente == "binance_vision":
        from hcarry.data.binance_vision import construir_panel, sha_manifiesto
        d = Path(datos["directorio"])
        panel, inf = construir_panel(d, datos.get("desde", "2019-10-01"), datos.get("hasta", "2026-06-01"))
        if inf.bloqueante:
            raise ValueError("datos con incidencias bloqueantes: " + "; ".join(map(str, inf.incidencias[:10])))
        procedencia = inf.info["procedencia"]  # del MANIFIESTO: "historico_oficial" o "sintetico"
        ident = {"fuente": "binance_vision", "id": sha_manifiesto(d), "procedencia": procedencia,
                 "sintetico": procedencia != "historico_oficial",
                 "incidencias": [str(i) for i in inf.incidencias[:20]], "horas_rellenadas": inf.info["horas_rellenadas"]}
    else:
        raise ValueError(f"fuente desconocida: {fuente}")
    _CACHE[clave] = (panel, ident)
    return panel, ident


def aplicar_estres(panel: Panel, estres: dict | None) -> Panel:
    if not estres:
        return panel
    factor = float(estres.get("funding_factor", 1.0))
    omitir = float(estres.get("omitir_funding", 0.0))
    rng = random.Random(int(estres.get("semilla", 0)))
    funding = [replace(e, tasa=e.tasa * factor) for e in panel.funding if not (omitir and rng.random() < omitir)]
    return Panel(panel.barras, funding, panel.origen, panel.notas + [f"estrés: {canonico(estres)}"])


def rango_division(division) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    if isinstance(division, str):
        a, b = DIVISIONES[division]
    else:
        a, b = division["desde"], division["hasta"]
    return ms(a), ms(b)


class AccesoTestDenegado(PermissionError):
    pass


def comprobar_test(cfg: dict, ident: dict, registro: Path, prerregistro: Path | None) -> str:
    h = sha(canonico(config_sin_nombre(cfg)))
    if prerregistro is None or not prerregistro.exists():
        raise AccesoTestDenegado("el test exige un archivo de prerregistro")
    pre = json.loads(prerregistro.read_text(encoding="utf-8"))
    if h not in {sha(canonico(config_sin_nombre(c))) for c in pre["configuraciones"]}:
        raise AccesoTestDenegado(f"configuración {h[:12]} no prerregistrada")
    if registro.exists():
        for linea in registro.read_text(encoding="utf-8").splitlines():
            e = json.loads(linea)
            if e.get("division") == "test" and e.get("config_sha256") == h and e["datos"]["id"] == ident["id"]:
                raise AccesoTestDenegado(f"la configuración {h[:12]} ya se evaluó en test con estos datos ({e['id']})")
    return h


def correr(cfg: dict, registro: Path | None = None, prerregistro: Path | None = None,
           guardar: bool = True) -> tuple[Resultado, dict, dict]:
    """Ejecuta un experimento. Devuelve (resultado, métricas, entrada del registro)."""
    panel_total, ident = cargar_datos(cfg["datos"])
    if cfg.get("division") == "test" and registro is not None:
        comprobar_test(cfg, ident, registro, prerregistro)
    desde, hasta = rango_division(cfg["division"])
    panel = aplicar_estres(panel_total.recortar(desde, hasta), cfg.get("estres"))
    politica = construir(cfg["politica"]["nombre"], cfg["politica"].get("params"))
    r = simular(panel, politica, Costes(**cfg.get("costes", {})), Filtros(**cfg.get("filtros", {})),
                ParamsMotor(**cfg.get("motor", {})))
    desc = conciliar(r, panel)
    m = calcular(r)
    m["descomposicion"] = desc.__dict__
    codigo = huella_codigo()
    cfg_sha = sha(canonico(config_sin_nombre(cfg)))
    entrada = {
        "id": sha(cfg_sha + codigo + ident["id"])[:16], "fecha_utc": dt.datetime.now(dt.UTC).isoformat(),
        "nombre": cfg.get("nombre"), "codigo_sha256": codigo, "config_sha256": cfg_sha, "config": cfg,
        "division": cfg["division"], "datos": {**ident, "desde": panel.inicio, "hasta": panel.fin},
        "metricas": {k: v for k, v in m.items() if k not in ("parametros_politica",)},
        "categoria": "sintetico" if ident["sintetico"] else "historico",
        "aviso": ("SINTÉTICO: no es evidencia económica" if ident["sintetico"]
                  else "HISTÓRICO: datos oficiales de data.binance.vision verificados por checksum"),
    }
    if guardar and registro is not None:
        registro.parent.mkdir(parents=True, exist_ok=True)
        with registro.open("a", encoding="utf-8") as f:
            f.write(canonico(entrada) + "\n")
    return r, m, entrada
