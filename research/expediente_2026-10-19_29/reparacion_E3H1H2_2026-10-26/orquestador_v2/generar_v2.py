"""Genera `ejecutar_E3_v2.py` a partir del orquestador congelado `ejecutar_E3R.py` (3b64a04d…), sin modificarlo.

Cada cambio es un reemplazo de texto que debe aparecer exactamente una vez en el original; si no, aborta.
Uso: python -I generar_v2.py <ejecutar_E3R.py congelado> <salida ejecutar_E3_v2.py>
"""
import hashlib
import sys
from pathlib import Path

ORIG, SAL = Path(sys.argv[1]), Path(sys.argv[2])
src = ORIG.read_text()
if hashlib.sha256(src.encode()).hexdigest() != "3b64a04dcb6b39d20cb218ff5f5ef0bd03c1dd45cd75e475b0640fb1ecfd8dce":
    raise SystemExit("el orquestador de origen no es el congelado")

CAMBIOS = []


def cambio(nombre, viejo, nuevo):
    CAMBIOS.append((nombre, viejo, nuevo))


# --- C1: encabezado (qué cambia y modos)
cambio("C1 encabezado", src[:src.index('import datetime as dt')], '''"""E3 · orquestador v2 de la ejecución confirmatoria ÚNICA de la v3 (H1 y H2) en la ventana A. NO autoriza ninguna ejecución.

Base: `ejecutar_E3R.py` (3b64a04d…, congelado, sin modificar). Cambios, y solo estos (diff en DIFF_v1_v2.diff):
  C2. R4 (N14): el aporte de cada moneda se mide contra el retorno BRUTO de EW-U30 (antes, contra el neto).
  C3. Modo real: antes de leer cualquier precio verifica el sha256 exacto de cada insumo (conjunto de las 757 series,
      estructural, listas, segunda pasada, mapeos, ventana A y módulos congelados) contra `ENTRADAS_CONGELADAS.json`.
      Si algo no coincide, se detiene sin crear la salida y sin leer precios.
  C4. Panel: aplica los mapeos de la Adenda 1 (regla 1, renombre X → Y; regla 2, redenominación X → X con r) y deja de
      aplicar la Adenda R2. Los cortes sin anuncio archivado siguen la regla 3 (mismo listado si el corte dura < 30 días).
  C5. INVÁLIDO es un resultado explícito: si la ventana o la validez previa (v3 §10) fallan, escribe RESULTADO_E3.json
      con «INVALIDO» y el motivo, sin calcular H1 ni H2.
  C6. Solo la ventana A: se eliminan la opción B, R1′ y la elección entre varios P0. La autorización debe contener la
      FRASE nueva, el sha256 de este archivo y el de ENTRADAS_CONGELADAS.json (que fija, entre otros, el de la ventana A).
Todo lo demás (validez previa, H1, H2, Holm, robustez, descriptivo) es idéntico al v1.

Modos:
  sintetico <salida_dir> <momentum> [replicas_R5] [dir_ejecucion_E3]
      Panel sintético de `pruebas_motor.panel_sintetico` (sin datos reales). Prueba el camino completo.
  real <dir_ejecucion_E3> <ventana_A_pasada2.json> <autorizacion.txt> <salida_dir>
      SOLO con autorización explícita posterior. La salida no puede existir (ejecución única).
"""
''')

# --- C6: constantes
cambio("C6 constantes",
       'E3_DEFECTO = AQUI.parent / "E3_seleccion_posicion_2026-10-19" / "ejecucion_E3"',
       'E3_DEFECTO = AQUI.parent.parent / "experimentos" / "E3_seleccion_posicion_2026-10-19" / "ejecucion_E3"\n'
       'MANIFIESTO = AQUI / "ENTRADAS_CONGELADAS.json"')
cambio("C6 frase",
       'FRASE = "AUTORIZO LA EJECUCION UNICA DE E3 (H1 Y H2) CON LA V3 MAS LA ADENDA R Y LA ADENDA R2"',
       'FRASE = ("AUTORIZO LA EJECUCION UNICA DE E3 (H1 Y H2) EN LA VENTANA A CON LA V3, LA ADENDA R CON R1 LITERAL, "\n'
       '         "LA SEGUNDA PASADA Y LOS MAPEOS DE LA ADENDA 1")')

# --- C3 y C4: verificación de insumos y panel con mapeos (reemplaza panel_real y particionar)
ini = src.index("# ------------------------------------------------------------------ panel real")
fin = src.index("# ------------------------------------------------------------------ validez previa")
cambio("C3+C4 panel", src[ini:fin], '''# ------------------------------------------------------------------ insumos (C3), sin leer precios

def hash_conjunto(d: Path) -> str:
    """Receta de CIERRE_E3: sha256 de la salida de `find . -type f -print0 | sort -z | xargs -0 sha256sum`."""
    d = Path(d)
    rel = sorted(("./" + p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file()), key=lambda r: r.encode())
    return hashlib.sha256("".join(f"{sha(d / r[2:])}  {r}\\n" for r in rel).encode()).hexdigest()


def verificar_entradas(e3: Path, ventana: Path, manifiesto: Path = None) -> dict:
    """Compara cada insumo con su sha256 congelado. Lee bytes para el hash, no interpreta ningún precio.
    Si falta un insumo o un hash no coincide, aborta: la salida no se crea y no se lee ningún precio."""
    m = json.loads(Path(manifiesto or MANIFIESTO).read_text())
    raices = {"E3": Path(e3), "reparacion": AQUI.parent, "ventana": Path(ventana)}
    obs, malos = {}, {}
    for x in m["entradas"]:
        ruta = raices[x["base"]] if x["base"] == "ventana" else raices[x["base"]] / x["ruta"]
        if not ruta.exists():
            malos[x["nombre"]] = {"esperado": x["sha256"], "observado": "AUSENTE"}
            continue
        h = hash_conjunto(ruta) if x["tipo"] == "conjunto" else sha(ruta)
        obs[x["nombre"]] = h
        if h != x["sha256"]:
            malos[x["nombre"]] = {"esperado": x["sha256"], "observado": h}
    if malos:
        raise SystemExit(f"insumos que no coinciden con ENTRADAS_CONGELADAS.json: {malos}. No se lee ningún precio.")
    return {"manifiesto": sha(Path(manifiesto or MANIFIESTO)), "insumos": obs, "inicio_H_esperado": m["inicio_H_esperado"],
            "mapeos": m["mapeos"]}


# ------------------------------------------------------------------ panel real (solo en modo real, con autorización)

def panel_real(e3: Path, universo, mapeos):
    """Series de calidad de E3: act = estado == 1. Aplica los mapeos de la Adenda 1 (C4); no aplica la Adenda R2."""
    series = sorted((e3 / "resultados" / "calidad" / "series").glob("*.npz"))
    syms, O, C, QV, act = [], [], [], [], []
    for f in series:
        z = np.load(f)
        syms.append(str(z["simbolo"]))
        O.append(z["O"]), C.append(z["C"]), QV.append(z["QV"]), act.append(z["estado"] == 1)
    O, C, QV, act = (np.array(x) for x in (O, C, QV, act))
    syms, O, C, QV, act, registro = aplicar_mapeos(syms, O, C, QV, act, mapeos, universo.INICIO)
    return universo.Panel(syms, O, C, QV, act, mapeos_renombre=registro), registro


def aplicar_mapeos(syms, O, C, QV, act, mapeos, inicio):
    """Adenda 1, reglas 1 y 2 (v3 §2.2.4; §4.10 «renombre mapeado»), en orden de fecha efectiva E.
    r = unidades nuevas por unidad vieja. QV está en USDT y no cambia.
    Regla 2 (X → X): los precios de X anteriores a la reapertura (primer día activo > E) se dividen por r. La serie queda
      continua a través de r y las unidades de una posición, multiplicadas por r. Edad y listado no cambian.
    Regla 1 (X → Y): Y continúa a X en la fila de X: historia de X con precios / r hasta su último día activo y, desde el
      primer día activo de Y, los datos de Y. La fila pasa a llamarse Y (hereda edad y posiciones) y la fila original de Y
      se retira. Aborta si falta X o Y, si X vuelve a estar activo después de E, si Y estuvo activo antes del cese de X,
      o si no hay reapertura: no se une nada a ciegas."""
    syms = list(syms)
    O, C, QV, act = O.copy(), C.copy(), QV.copy(), act.copy()
    retirar, registro = [], []
    for m in sorted(mapeos, key=lambda m: (m["E"], m["regla"])):
        x, y, r = m["viejo_usdt"], m["nuevo_usdt"], float(m["r"])
        if x not in syms or y not in syms or not r > 0:
            raise SystemExit(f"mapeo imposible: {x} → {y} (r = {m['r']})")
        i, e = syms.index(x), (dt.date.fromisoformat(m["E"]) - inicio).days
        if m["regla"] == 2:
            if x != y:
                raise SystemExit(f"regla 2 con símbolos distintos: {x} → {y}")
            despues = np.flatnonzero(act[i, e + 1:])
            if despues.size == 0:
                raise SystemExit(f"{x}: no hay reapertura después de {m['E']}")
            k = e + 1 + int(despues[0])
            antes = np.flatnonzero(act[i, :e + 1])
            if antes.size == 0 or k - int(antes[-1]) < 2:
                raise SystemExit(f"{x}: no hay un corte de negociación alrededor de E = {m['E']}; no se aplica r")
            O[i, :k] /= r
            C[i, :k] /= r
            registro.append({**m, "fila": x, "dia_reapertura": (inicio + dt.timedelta(days=k)).isoformat()})
            continue
        j = syms.index(y)
        activos_x = np.flatnonzero(act[i])
        if activos_x.size == 0 or activos_x[-1] > e:
            raise SystemExit(f"{x}: sin actividad o activo después de E = {m['E']}; no se mapea")
        activos_y = np.flatnonzero(act[j])
        if activos_y.size == 0 or activos_y[0] <= activos_x[-1]:
            raise SystemExit(f"{y}: sin actividad o activo antes del cese de {x}; no se mapea")
        k = int(activos_y[0])
        O[i, :k], C[i, :k] = O[i, :k] / r, C[i, :k] / r
        O[i, k:], C[i, k:], QV[i, k:], act[i, k:] = O[j, k:], C[j, k:], QV[j, k:], act[j, k:]
        syms[i], syms[j] = y, f"#retirada:{y}"
        retirar.append(j)
        registro.append({**m, "fila": y, "ultimo_activo_viejo": (inicio + dt.timedelta(days=int(activos_x[-1]))).isoformat(),
                         "primer_activo_nuevo": (inicio + dt.timedelta(days=k)).isoformat()})
    quedan = [s for s in range(len(syms)) if s not in set(retirar)]
    return [syms[s] for s in quedan], O[quedan], C[quedan], QV[quedan], act[quedan], registro


''')

# --- C2: R4 contra el EW bruto (N14)
cambio("C2 R4 bruto",
       '''    aporte = contribuciones(P, base, formaciones, ew)
    mayor = max(aporte, key=lambda s: aporte[s]) if aporte else None''',
       '''    bruto_s = motor.simular(P, formaciones, Cfg(mult_costo=0.0), cache)
    bruto_ew = motor.simular(P, formaciones, Cfg(objetivo="ew", mult_costo=0.0), cache)
    aporte = contribuciones(P, base, formaciones, bruto_ew)  # N14: r_EW bruto (v1 usaba el neto)
    mayor = max(aporte, key=lambda s: aporte[s]) if aporte else None''')
cambio("C2 sin recálculo",
       '''    bruto_s = motor.simular(P, formaciones, Cfg(mult_costo=0.0), cache)
    bruto_ew = motor.simular(P, formaciones, Cfg(objetivo="ew", mult_costo=0.0), cache)
    excesos["bruto"]''',
       '''    excesos["bruto"]''')

# --- sintético: directorio de E3 opcional
cambio("sintetico e3",
       '''def modo_sintetico(salida: Path, momentum: float, replicas: int):
    universo, motor, inferencia = importar_congelados(E3_DEFECTO)
    if sha(E3_DEFECTO / "codigo" / "pruebas_motor.py") != PRUEBAS_MOTOR:''',
       '''def modo_sintetico(salida: Path, momentum: float, replicas: int, e3: Path = E3_DEFECTO):
    universo, motor, inferencia = importar_congelados(e3)
    if sha(e3 / "codigo" / "pruebas_motor.py") != PRUEBAS_MOTOR:''')

# --- C3, C5, C6: modo real
ini = src.index("def modo_real(")
fin = src.index('if __name__ == "__main__":')
cambio("C3+C5+C6 modo real", src[ini:fin], '''def resultado_invalido(salida: Path, motivo: str, **extra):
    """C5: INVÁLIDO como resultado explícito, sin H1 ni H2."""
    res = {"veredicto": "INVALIDO", "motivo": motivo, "H1": None, "H2": None, **extra,
           "nota": "E3-H1/H2 NO EVALUABLES con esta ventana. No se busca otra ventana ni se cambia ninguna regla."}
    (salida / "RESULTADO_E3.json").write_text(json.dumps(res, indent=1, default=float, ensure_ascii=False))
    raise SystemExit(f"INVALIDO: {motivo}. Ver {salida / 'RESULTADO_E3.json'}")


def modo_real(e3: Path, ventana: Path, autorizacion: Path, salida: Path, manifiesto: Path = None):
    if salida.exists():
        raise SystemExit(f"{salida} ya existe: la ejecución confirmatoria es única")
    manifiesto = Path(manifiesto or MANIFIESTO)
    texto = autorizacion.read_text() if autorizacion.exists() else ""
    requeridos = {"FRASE": FRASE in texto, "orquestador_v2": sha(Path(__file__)) in texto,
                  "entradas_congeladas": manifiesto.exists() and sha(manifiesto) in texto}
    if not all(requeridos.values()):
        raise SystemExit(f"autorización ausente o incompleta: {requeridos}. No se lee ningún precio.")
    entradas = verificar_entradas(e3, ventana, manifiesto)  # C3: antes de leer cualquier precio
    vd = json.loads(ventana.read_text())
    salida.mkdir(parents=True)
    registro = {"inicio_utc": dt.datetime.now(dt.UTC).isoformat(), "ventana": str(ventana), "sha_ventana": sha(ventana),
                "sha_orquestador": sha(Path(__file__)), "sha_autorizacion": sha(autorizacion), "entradas": entradas,
                "inicio_H": vd.get("inicio_H")}
    (salida / "REGISTRO_EJECUCION.json").write_text(json.dumps(registro, indent=1))  # antes de calcular
    if vd.get("veredicto") != "VALIDO" or vd.get("inicio_H") != entradas["inicio_H_esperado"]:
        resultado_invalido(salida, "la ventana A no es VÁLIDA o no es la congelada", ventana=vd.get("veredicto"))
    universo, motor, inferencia = importar_congelados(e3)
    mapeos = json.loads((AQUI.parent / entradas["mapeos"]).read_text())["mapeos"]
    P, registro_mapeos = panel_real(e3, universo, mapeos)
    inicio = dt.date.fromisoformat(vd["inicio_H"])
    formaciones = universo.lunes(inicio, ULTIMA_FORMACION + dt.timedelta(days=7))
    validez, cache = validez_previa(P, formaciones, universo, motor)
    (salida / "VALIDEZ_PREVIA.json").write_text(json.dumps({**validez, "mapeos_aplicados": registro_mapeos}, indent=1, default=float))
    if not validez["valido"]:
        resultado_invalido(salida, "validez previa (v3 §10)", validez_previa=validez)
    Fm = universo.lunes(inicio, ULTIMA_FORMACION + dt.timedelta(days=9), dia_semana=2)
    res = ejecutar(P, formaciones, universo, motor, inferencia, cache=cache, formaciones_miercoles=Fm)
    res["veredicto"] = "EVALUADO"
    res["validez_previa"] = validez
    res["mapeos_aplicados"] = registro_mapeos
    res["registro"] = registro
    (salida / "RESULTADO_E3.json").write_text(json.dumps(res, indent=1, default=float, ensure_ascii=False))
    print(json.dumps({k: res[k] for k in ("semanas_ic", "H1", "H2", "holm", "clasificacion_6_5")}, default=float,
                     ensure_ascii=False, indent=1))


''')
cambio("main sintetico",
       '        modo_sintetico(Path(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 50)',
       '        modo_sintetico(Path(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 50,\n'
       '                       Path(sys.argv[5]) if len(sys.argv) > 5 else E3_DEFECTO)')

out = src
for nombre, viejo, nuevo in CAMBIOS:
    n = out.count(viejo)
    if n != 1:
        raise SystemExit(f"{nombre}: el texto original aparece {n} veces")
    out = out.replace(viejo, nuevo)
SAL.write_text(out)
print(f"{len(CAMBIOS)} cambios aplicados → {SAL} ({hashlib.sha256(out.encode()).hexdigest()})")
