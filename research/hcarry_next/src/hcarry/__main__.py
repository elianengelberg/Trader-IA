"""CLI de H-CARRY Next (solo simulación; ningún comando envía órdenes).

  python -m hcarry estructura
  python -m hcarry descargar  --destino datos/binance_vision --desde 2019-10 --hasta 2026-06     (necesita red)
  python -m hcarry completar-diarios --directorio datos/binance_vision   (horas ausentes de los mensuales)
  python -m hcarry importar   --origen COPIA_APORTADA --destino datos/binance_vision     (verifica .CHECKSUM oficiales)
  python -m hcarry calidad    --directorio datos/binance_vision [--salida informe_calidad.md]
  python -m hcarry fabricar-sintetico --destino DIR [--semilla N]   (SINTÉTICO en formato oficial, para ensayos)
  python -m hcarry validar    --directorio datos/binance_vision --desde 2019-10-01 --hasta 2026-06-01
  python -m hcarry historico  --datos DIR [--resultados experimentos/historico/resultados]   (prerregistrado)
  python -m hcarry correr     CONFIG.json [--registro experimentos/registro.jsonl] [--prerregistro P.json]
  python -m hcarry protocolo  --salida DIR (--sintetico SEMILLA [--nulo] | --binance-vision DIRECTORIO)"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hcarry", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("estructura", help="aritmética de la estructura de capital")
    d = sub.add_parser("descargar", help="data.binance.vision con checksums (requiere red)")
    d.add_argument("--destino", type=Path, required=True)
    d.add_argument("--desde", required=True)
    d.add_argument("--hasta", required=True)
    cd = sub.add_parser("completar-diarios", help="completa horas ausentes de los mensuales con diarios oficiales")
    cd.add_argument("--directorio", type=Path, required=True)
    cd.add_argument("--hasta", default="2026-06-01")
    im = sub.add_parser("importar", help="importa una copia oficial aportada (zips + .CHECKSUM)")
    im.add_argument("--origen", type=Path, required=True)
    im.add_argument("--destino", type=Path, required=True)
    ca = sub.add_parser("calidad", help="informe de calidad y filtros de aceptación")
    ca.add_argument("--directorio", type=Path, required=True)
    ca.add_argument("--desde")
    ca.add_argument("--hasta", default="2026-06-01")
    ca.add_argument("--salida", type=Path)
    fa = sub.add_parser("fabricar-sintetico", help="archivos SINTÉTICOS con formato oficial (ensayo del pipeline)")
    fa.add_argument("--destino", type=Path, required=True)
    fa.add_argument("--semilla", type=int, default=1)
    fa.add_argument("--variante", default="base")
    v = sub.add_parser("validar", help="construye y valida el panel")
    v.add_argument("--directorio", type=Path, required=True)
    v.add_argument("--desde", required=True)
    v.add_argument("--hasta", required=True)
    h = sub.add_parser("historico", help="validación prerregistrada rev. 5 frente a UmbralFunding")
    h.add_argument("--datos", type=Path, required=True)
    h.add_argument("--resultados", type=Path, default=Path("experimentos/historico/resultados"))
    c = sub.add_parser("correr", help="un experimento a partir de una configuración JSON")
    c.add_argument("config", type=Path)
    c.add_argument("--registro", type=Path, default=Path("experimentos/registro.jsonl"))
    c.add_argument("--prerregistro", type=Path)
    p = sub.add_parser("protocolo", help="protocolo completo desarrollo → validación → test")
    p.add_argument("--salida", type=Path, required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--sintetico", type=int, metavar="SEMILLA")
    g.add_argument("--binance-vision", type=Path, metavar="DIRECTORIO")
    p.add_argument("--nulo", action="store_true", help="barajar el funding (mundo nulo)")
    a = ap.parse_args(argv)

    if a.cmd == "estructura":
        from hcarry.analisis import tabla_markdown
        print(tabla_markdown())
    elif a.cmd == "descargar":
        from hcarry.data.binance_vision import descargar
        man = descargar(a.destino, a.desde, a.hasta)
        print(f"{len(man['archivos'])} archivos verificados contra su .CHECKSUM en {a.destino}")
    elif a.cmd == "completar-diarios":
        from hcarry.data.binance_vision import completar_con_diarios
        man = completar_con_diarios(a.directorio, a.hasta)
        c = man["complementos_diarios"][-1]
        print(f"{c['archivos_nuevos']} diarios oficiales verificados; días con horas ausentes: "
              f"{ {k: len(v) for k, v in c['dias_con_horas_ausentes'].items()} }; no publicados: {len(man['ausentes_diarios'])}")
    elif a.cmd == "importar":
        from hcarry.data.binance_vision import importar
        man = importar(a.origen, a.destino)
        print(f"{len(man['archivos'])} archivos verificados contra su .CHECKSUM oficial e importados en {a.destino}")
    elif a.cmd == "calidad":
        from hcarry.data import calidad
        inf = calidad.evaluar(a.directorio, a.desde, a.hasta)
        texto = calidad.markdown(inf)
        if a.salida:
            a.salida.write_text(texto, encoding="utf-8")
            a.salida.with_suffix(".json").write_text(json.dumps(inf, ensure_ascii=False, indent=1, default=str),
                                                     encoding="utf-8")
        print(texto)
        return 0 if inf["apto"] else 1
    elif a.cmd == "fabricar-sintetico":
        from hcarry.data.fabricar import fabricar_sintetico
        from hcarry.data.sintetico import ParamsSintetico, generar
        man = fabricar_sintetico(generar(ParamsSintetico(semilla=a.semilla, variante=a.variante)), a.destino)
        print(f"{len(man['archivos'])} archivos SINTÉTICOS en formato oficial en {a.destino}")
    elif a.cmd == "validar":
        from hcarry.data.binance_vision import construir_panel
        panel, inf = construir_panel(a.directorio, a.desde, a.hasta)
        print(json.dumps({"barras": len(panel.barras), "funding": len(panel.funding), "bloqueante": inf.bloqueante,
                          "incidencias": [str(i) for i in inf.incidencias], "info": inf.info}, ensure_ascii=False,
                         indent=1, default=str))
        return 1 if inf.bloqueante else 0
    elif a.cmd == "historico":
        from hcarry.lab import historico
        s = historico.evaluar(a.datos, a.resultados)
        print(json.dumps({k: s[k] for k in ("categoria", "calidad_apta", "conclusion", "destino")}, ensure_ascii=False,
                         indent=1, default=str))
    elif a.cmd == "correr":
        from hcarry.lab.experimento import correr
        cfg = json.loads(a.config.read_text(encoding="utf-8"))
        _, m, e = correr(cfg, a.registro, a.prerregistro)
        print(json.dumps({"id": e["id"], "aviso": e["aviso"], "metricas": m}, ensure_ascii=False, indent=1,
                         default=str))
    elif a.cmd == "protocolo":
        from hcarry.lab import protocolo as P
        if a.sintetico is not None:
            datos = {"fuente": "sintetico", "semilla": a.sintetico}
            etiqueta = f"sintetico{a.sintetico}"
        else:
            datos = {"fuente": "binance_vision", "directorio": str(a.binance_vision)}
            etiqueta = "binance_vision"
        if a.nulo:
            datos = P.nulo(datos, 1)
            etiqueta += "_nulo"
        out = P.ejecutar(datos, a.salida, etiqueta)
        print(json.dumps({k: out[k] for k in ("protocolo_sha256", "seleccionados", "test")}, ensure_ascii=False,
                         indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
