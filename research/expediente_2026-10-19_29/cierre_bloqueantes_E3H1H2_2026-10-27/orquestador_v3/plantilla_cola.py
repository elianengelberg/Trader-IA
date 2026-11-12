

# ------------------------------------------------------------------ C11: estados terminales, escritura atómica e intentos

def escribir_atomico(p: Path, obj) -> str:
    """Escribe a un temporal, sincroniza y reemplaza: nunca queda un JSON a medio escribir. Devuelve el sha256."""
    p = Path(p)
    tmp = p.with_name(p.name + ".tmp")
    texto = json.dumps(obj, indent=1, default=float, ensure_ascii=False)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(texto)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)
    return sha_bytes(texto.encode("utf-8"))


class Intentos:
    """Registro de intentos de la ejecución única (una línea JSON por evento), con bloqueo exclusivo mientras dura un
    intento. El bloqueo lo libera el sistema si el proceso muere; el registro, en cambio, queda con el intento abierto."""

    def __init__(self, ruta: Path):
        self.f = open(ruta, "a+", encoding="utf-8")
        try:
            fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.f.close()
            raise Rechazo("otra ejecución de E3 está en curso: el registro de intentos está bloqueado") from exc
        self.f.seek(0)
        self.eventos = [json.loads(linea) for linea in self.f.read().splitlines() if linea.strip()]

    def anotar(self, **ev):
        ev = {"utc": dt.datetime.now(dt.UTC).isoformat(), **ev}
        self.f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        self.f.flush()
        os.fsync(self.f.fileno())
        self.eventos.append(ev)

    def cerrar(self):
        try:
            fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
        finally:
            self.f.close()


def permitir_intento(intentos: Intentos, sha_aut: str, texto: str):
    """C11: hay una sola ejecución con resultado. Se rechaza, ANTES de crear la salida:
      - si ya hay un EVALUADO o un INVALIDO;
      - si hay un intento INICIADO sin estado terminal (el proceso murió o el disco falló: revisión manual);
      - si el último ERROR ocurrió con estadísticos ya iniciados (reintentar sería una decisión metodológica);
      - si, tras un ERROR previo a los estadísticos, la autorización es la misma o no cita el sha256 de ese RESULTADO."""
    ev = intentos.eventos
    terminales = [e for e in ev if e["evento"] in ("EVALUADO", "INVALIDO")]
    if terminales:
        raise Rechazo(f"E3 ya tiene un resultado terminal ({terminales[-1]['evento']}, {terminales[-1]['utc']}): no hay otra ejecución")
    abiertos = ({e["id_intento"] for e in ev if e["evento"] == "INICIADO"}
                - {e["id_intento"] for e in ev if e["evento"] in ("ERROR", "EVALUADO", "INVALIDO")})
    if abiertos:
        raise Rechazo(f"hay un intento sin estado terminal ({sorted(abiertos)}): requiere revisión manual antes de cualquier otro")
    errores = [e for e in ev if e["evento"] == "ERROR"]
    if not errores:
        return None
    u = errores[-1]
    if u["estadisticos_iniciados"]:
        raise Rechazo(f"el ERROR previo ocurrió en la etapa «{u['etapa']}», con estadísticos iniciados: "
                      "reintentar es una decisión metodológica, no técnica")
    if any(e.get("sha_autorizacion") == sha_aut for e in ev):
        raise Rechazo("esta autorización ya se usó en un intento anterior: un reintento exige una autorización nueva")
    if f"REINTENTO TRAS ERROR {u['sha_resultado']}" not in texto:
        raise Rechazo(f"la autorización de reintento tiene que citar «REINTENTO TRAS ERROR {u['sha_resultado']}»")
    return u


def resultado_invalido(salida: Path, intentos: Intentos, id_intento: str, motivo: str, **extra):
    """C5: INVÁLIDO como resultado explícito, sin H1 ni H2."""
    res = {"veredicto": "INVALIDO", "motivo": motivo, "H1": None, "H2": None, **extra,
           "nota": "E3-H1/H2 NO EVALUABLES con esta ventana. No se busca otra ventana ni se cambia ninguna regla."}
    h = escribir_atomico(salida / "RESULTADO_E3.json", res)
    intentos.anotar(evento="INVALIDO", id_intento=id_intento, sha_resultado=h)
    raise FinTerminal(f"INVALIDO: {motivo}. Ver {salida / 'RESULTADO_E3.json'}")


def resultado_error(salida: Path, intentos: Intentos, id_intento: str, etapa: str, exc: BaseException):
    """C11: cualquier excepción después de crear la salida deja un ERROR explícito; nunca un éxito aparente ni un
    hueco. Si ni siquiera se puede escribir, el intento queda abierto y el siguiente se rechaza (revisión manual)."""
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    res = {"veredicto": "ERROR", "etapa": etapa, "tipo": type(exc).__name__, "mensaje": str(exc)[:2000],
           "traceback": tb, "sha_traceback": sha_bytes(tb.encode("utf-8")),
           "estadisticos_iniciados": etapa not in ETAPAS_SIN_ESTADISTICOS, "H1": None, "H2": None,
           "nota": "E3-H1/H2 SIN RESULTADO por un fallo técnico: no es EVALUADO ni INVALIDO. Reintentar exige una "
                   "autorización nueva que cite el sha256 de este archivo; con estadísticos iniciados, es una decisión "
                   "metodológica."}
    try:
        h = escribir_atomico(salida / "RESULTADO_E3.json", res)
    except BaseException as exc2:
        raise FinTerminal(f"ERROR en la etapa «{etapa}» y no se pudo escribir RESULTADO_E3.json ({exc2!r}); el intento "
                          "queda abierto en el registro: revisión manual") from exc
    intentos.anotar(evento="ERROR", id_intento=id_intento, etapa=etapa, tipo=type(exc).__name__,
                    estadisticos_iniciados=res["estadisticos_iniciados"], sha_resultado=h)
    raise FinTerminal(f"ERROR en la etapa «{etapa}»: {type(exc).__name__}: {exc}. Ver {salida / 'RESULTADO_E3.json'}") from exc


def modo_real(e3: Path, ventana: Path, autorizacion: Path, salida: Path, manifiesto: Path = None):
    e3, ventana, autorizacion, salida = Path(e3), Path(ventana), Path(autorizacion), Path(salida)
    if salida.exists():
        raise Rechazo(f"{salida} ya existe: la ejecución confirmatoria es única")
    aut_bytes = autorizacion.read_bytes() if autorizacion.is_file() else b""
    texto = aut_bytes.decode("utf-8", errors="replace")
    man_path = Path(manifiesto or MANIFIESTO)
    man_bytes = man_path.read_bytes() if man_path.is_file() else b""  # C9: el manifiesto también se lee una sola vez
    sha_aut, sha_man = sha_bytes(aut_bytes), sha_bytes(man_bytes)
    requeridos = {"FRASE": FRASE in texto, "orquestador_v3": SHA_PROPIO in texto,
                  "entradas_congeladas": bool(man_bytes) and sha_man in texto,
                  **{f"decision_{k}": f in texto for k, f in FRASES_DECISION.items()}}
    if not all(requeridos.values()):
        raise Rechazo(f"autorización ausente o incompleta: {requeridos}. No se lee ningún precio.")
    intentos = Intentos(INTENTOS)
    try:
        previo = permitir_intento(intentos, sha_aut, texto)
        raices = {"E3": e3, "reparacion": REPARACION, "cierre": CIERRE, "ventana": ventana}
        datos = leer_y_verificar(man_bytes, raices)                                   # C8 + C9
        vd = json.loads(datos["ventana_A"])
        if vd.get("veredicto") != "VALIDO" or vd.get("inicio_H") != INICIO_H_A:       # C7 (además del sha256 fijado)
            raise Rechazo(f"la ventana no es la A aprobada (veredicto {vd.get('veredicto')}, inicio {vd.get('inicio_H')})")
        fuentes = {n[:-3]: datos[n] for n in CONGELADOS}
        mods = cargar_modulos(fuentes)                                                  # C10
        universo, motor, inferencia = mods["universo"], mods["motor"], mods["inferencia"]
        mapeos = json.loads(datos["mapeos_adenda1_completa"])["mapeos"]               # C8: solo la entrada verificada
        syms, act = actividad_desde_bytes(datos)                                        # C12: antes de la salida, solo estado
        ceros = np.zeros(act.shape)
        syms2, _, _, _, _, reg_previo, origen = aplicar_mapeos(syms, ceros, ceros, ceros, act, mapeos, universo.INICIO)
        comprobar_marcas(syms, syms2, origen, universo)
        id_intento = f"{sha_aut[:16]}:{salida}"
        salida.mkdir(parents=True, exist_ok=False)
        intentos.anotar(evento="INICIADO", id_intento=id_intento, salida=str(salida), sha_autorizacion=sha_aut,
                        sha_orquestador=SHA_PROPIO, sha_manifiesto=sha_man, reintento_de=previo and previo["sha_resultado"])
        registro = {"inicio_utc": dt.datetime.now(dt.UTC).isoformat(), "estado": "EN_CURSO", "ventana": str(ventana),
                    "sha_ventana": sha_bytes(datos["ventana_A"]), "sha_orquestador": SHA_PROPIO, "sha_manifiesto": sha_man,
                    "sha_autorizacion": sha_aut, "inicio_H": INICIO_H_A, "mapeos_en_tabla": len(mapeos),
                    "mapeos_aplicados_en_la_comprobacion_previa": len(reg_previo), "reintento_de": previo and previo["sha_resultado"]}
        escribir_atomico(salida / "REGISTRO_EJECUCION.json", registro)  # antes de calcular
        etapa = "panel"
        try:
            P, registro_mapeos = panel_real(datos, universo, mapeos)
            inicio = dt.date.fromisoformat(INICIO_H_A)
            formaciones = universo.lunes(inicio, ULTIMA_FORMACION + dt.timedelta(days=7))
            etapa = "validez_previa"
            validez, cache = validez_previa(P, formaciones, universo, motor)
            escribir_atomico(salida / "VALIDEZ_PREVIA.json", {**validez, "mapeos_aplicados": registro_mapeos})
            if not validez["valido"]:
                resultado_invalido(salida, intentos, id_intento, "validez previa (v3 §10)", validez_previa=validez)
            etapa = "calculo"
            Fm = universo.lunes(inicio, ULTIMA_FORMACION + dt.timedelta(days=9), dia_semana=2)
            res = ejecutar(P, formaciones, universo, motor, inferencia, cache=cache, formaciones_miercoles=Fm)
            etapa = "escritura"
            res["veredicto"] = "EVALUADO"
            res["validez_previa"] = validez
            res["mapeos_aplicados"] = registro_mapeos
            res["registro"] = registro
            h = escribir_atomico(salida / "RESULTADO_E3.json", res)
            intentos.anotar(evento="EVALUADO", id_intento=id_intento, sha_resultado=h)
        except FinTerminal:
            raise
        except BaseException as exc:  # incluye SystemExit de código congelado y KeyboardInterrupt
            resultado_error(salida, intentos, id_intento, etapa, exc)
        print(json.dumps({k: res[k] for k in ("semanas_ic", "H1", "H2", "holm", "clasificacion_6_5")}, default=float,
                         ensure_ascii=False, indent=1))
    finally:
        intentos.cerrar()


if __name__ == "__main__":
    if sys.argv[1] == "sintetico":
        modo_sintetico(Path(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 50,
                       Path(sys.argv[5]) if len(sys.argv) > 5 else E3_DEFECTO)
    elif sys.argv[1] == "real":
        modo_real(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5]))
    else:
        raise SystemExit(__doc__)
