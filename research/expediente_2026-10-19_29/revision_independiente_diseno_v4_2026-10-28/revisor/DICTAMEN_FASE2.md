# Dictamen de fase 2 (contraste con la revisión adversarial del autor)

**Fecha:** 2026-10-28 (UTC). **Revisor:** el mismo agente de la fase 1, con las mismas limitaciones de independencia (§0 de `DICTAMEN_FASE1.md`: misma familia de modelos, mismo contenedor, lanzado por el autor).

**`DICTAMEN_FASE1.md` quedó fijado antes de abrir cualquier material de esta fase:** sha256 `77c71f7500c5d4cbaa035bef3ad7d19be377592d5b821a6eff5b7272841025be` (`registro/06_cierre_fase1_sha.txt`, 19:59:28Z; el primer acceso a la carpeta del autor es de las 19:59:53Z, `registro/20_fase2_apertura.txt`). No lo modifiqué después; el hash se vuelve a listar en `MANIFEST_REVISOR.sha256`.

## 1. Qué leí en esta fase

- `revision_adversarial_E3H1H2_2026-10-28/INFORME_REVISION_ADVERSARIAL_E3H1H2.md`: sha256 `c861d4a33ff68c3bfa81f0155be2d792a03a1b1dd42107384e7fcfedb3cf0898`, `OK` (`20_fase2_apertura.txt`).
- Su `MANIFEST_REVISION_ADVERSARIAL.sha256`: todas las entradas verificaron `OK`, ningún fallo (`21_fase2_manifiesto_autor.txt`).
- Los arneses `arnes_L13.py`, `arnes_L17.py`, `L25_documentos_como_autorizacion.py`, `mutantes_revisor.py`, `guarda_revisor.py` (leídos como texto; **no los ejecuté**: `arnes_L13.py` y `arnes_L17.py` llaman a `modo_real` del v3 con stubs, y eso está fuera de lo que puedo correr).
- Sus registros: `L13_resultados.json`, `L17_resultados.json`, `L25_documentos_como_autorizacion.json`, `mutantes_revisor.txt`, `suite_v3_con_guarda.txt`, y los `correr.txt`/`observar.txt` de los escenarios (`22_…`, `22b_…`, `24_…`, `25_…`).
- Una sola comprobación propia nueva, estática y sin ejecutar nada: `prototipos/p6_l25_estatico.py` (`23_p6_l25_estatico.txt`), que reproduce la condición por subcadenas del v2 y del v3 contra `INFORME_REPARACION_E3H1H2.md` imprimiendo solo booleanos y números de línea.

## 2. En qué coincido con el autor

| Afirmación del autor | Evidencia del autor que revisé | Mi comprobación | Coincido |
|---|---|---|---|
| L-13: si falla la anotación de INVALIDO, el INVALIDO se reescribe como ERROR «sin estadísticos» y una instancia nueva **acepta otra ejecución completa** (I1, I5) | `L13_resultados.json`: I1 e I5 → `RESULTADO_en_disco.veredicto = ERROR`, `etapa = validez_previa`, `estadisticos_iniciados = false`, `nueva_instancia = "PERMITIDO: corrió completo"` (`22b`) | Por lectura del v3 es exactamente lo que hacen L803-804 + L887-890 (`01_citas_v3.txt`; fase 1 §3.1) | Sí |
| L-13: si falla la anotación de EVALUADO, el resultado se pierde (E1, E4, E7) | E1/E4/E7 → `veredicto = ERROR`, `etapa = escritura`; registro `[INICIADO, ERROR]` | Idem (L885-886, L889) | Sí |
| L-13: el registro puede citar un sha256 que no está en disco (E2, I2) | E2: `EVALUADO coincide_con_disco = false`; I2: `INVALIDO coincide_con_disco = false` | Es la consecuencia de los dos almacenes sin orden (fase 1 §3.1, causa 2) | Sí |
| E6: una línea parcial produce una excepción no controlada (fail-closed) | E6: `registro = [INICIADO, LINEA_PARCIAL]`, `nueva_instancia = EXCEPCIÓN NO CONTROLADA JSONDecodeError` | L755 (`json.loads` por línea, después del `flock` de L750) | Sí; agrego que es un cierre **accidental**, no diseñado |
| K1/K2: salida creada sin INICIADO → otra ejecución permitida | K1/K2: `registro = []`, `nueva_instancia = PERMITIDO` | L859 (`mkdir`) antes de L860 (`INICIADO`) | Sí |
| L12: con el registro borrado, otra ejecución completa | `observar.json` de L12: `registro = "NO EXISTE"`, `nuevo_intento = PERMITIDO` | Ver §5.1 sobre el procedimiento | Sí en la conclusión |
| C1: con el bloqueo retenido, el segundo proceso se rechaza | `C1_concurrencia/correr.json`: «otra ejecución de E3 está en curso» | Mi P4/P5 (`13`, `14b`) confirman la semántica de `flock` | Sí |
| L-17: el control acepta negaciones, citas y contradicciones; 9 de 10 variantes aceptadas | `L17_resultados.json`: 9 × «AUTORIZACION ACEPTADA», 1 × `Rechazo` (sin D-1); ninguna salida creada | L837-841 (`in texto`) | Sí |
| L-25: `INFORME_REPARACION_E3H1H2.md` satisface tal cual al v2 (frase l. 272, sha del v2 l. 208, sha del manifiesto l. 209); ningún documento satisface al v3 | `L25_documentos_como_autorizacion.json`: `documentos_aceptados_tal_cual` = ese informe y su copia, `v2`, 3 de 3 | `23_p6_l25_estatico.txt`: v2 `3/3 = true`, v3 `false` en los 5 elementos; `24_…`: líneas `[272]`, `[208]`, `[209]`; sha del documento `9b26ecb5…` igual al que cita | Sí |
| T-9: la suite del v3 pasa (47) con los defectos presentes; 4 pruebas bloqueadas por la guarda; mutantes R2, R3, R4 y R8 sobreviven, R1, R6 y R7 se detectan, R5 es control | `suite_v3_con_guarda.txt`: `4 failed, 47 passed`; `mutantes_revisor.txt`: coincide | Las 4 que fallan son las que la guarda bloquea (la suite original las tiene, `test_orquestador_v3.py` L378-396 y L626-633) | Sí |
| Las referencias del diseño v4 a «B1–B3, E1–E7, I1–I5, K1, K2, L12 y C1», «10 variantes, hoy 9 se aceptan» y «mutantes R2, R3, R4 y R8» | Existen con esos nombres y esos resultados | — | Sí: las remisiones del diseño están respaldadas |

## 3. En qué discrepo

### 3.1 El modelo de fallos del autor es de proceso, no de durabilidad, y el diseño hereda ese límite sin decirlo donde importa

`arnes_L13.py` L80-106 inyecta en `Intentos.anotar` cuatro modos: `antes` (excepción antes de `write`), `despues` (`write`+`fsync` reales y luego excepción), `matar` (`os._exit`), `interrumpir` (`KeyboardInterrupt` sincrónica), `parcial` (25 bytes y `os._exit`). Son todos fallos **del proceso** con el estado del sistema operativo intacto. No hay ningún escenario donde `write` tenga éxito y los bytes **no lleguen al disco** (EIO en `fsync` con páginas limpias, o corte antes del `fsync`). El informe lo reconoce en los límites de §E.1 del diseño («Matar el proceso no equivale a un corte de energía»), pero ni el informe ni el diseño proponen el modelo de disco sombra que lo cubriría, y es barato (`10b_…` §4). Mi R-2 y R-13(b) de la fase 1 se mantienen y quedan **reforzados**: el autor probó 18 escenarios y ninguno toca el hueco que hace falso I-7.

### 3.2 El «Ctrl-C» del autor es monohilo

E7 e I5 lanzan `KeyboardInterrupt` dentro de `anotar` (L98-99). Es un modelo correcto de SIGINT **en un proceso con un solo hilo**. El remedio que el diseño propone (`pthread_sigmask`, §A.3) pasaría una prueba construida así y falla en el proceso real con numpy (`11_p2_senales_hilos.txt`). Mi R-1 se mantiene; el arnés del autor no la habría detectado.

### 3.3 La concurrencia probada es la fácil

C1 prueba «bloqueo retenido → rechazo» (`arnes_L13.py` L216-226). No prueba la carrera de dos fases (leer la cabeza, perder el bloqueo, retomarlo con una vista vieja), que es la que exige que la comparación de cabeza ocurra **dentro** del bloqueo (`14b_…`: sin CAS, 2 ABIERTO). Mi R-7 se mantiene.

### 3.4 Sobre L-25, el autor diagnostica bien y receta a un lado del problema

El diagnóstico (§A.2 del informe, T-10) es correcto y lo confirmé. Pero la receta de §F.4 («aislamiento sin tocar la historia»: árbol nuevo, acta de revocación, que el v4 se niegue si hay resultados previos; prueba: «que una ejecución del v2 previa bloquee al v4») **no hace al v2 no ejecutable**: protege al v4 del v2, no al proyecto del v2. La prueba propuesta verifica lo primero. El diseño v4 hereda esa receta en §B.3 y acota el invariante de aceptación a «la zona de ejecución» (diseño L353). Esto es el origen de mi R-4 (Alta) y lo confirmo con la propia evidencia del autor: hoy, en el scratchpad, están las cuatro condiciones de ejecutabilidad (`03_entorno.txt` §9) y el documento que lo satisface (`23_…`). La única salida honesta es la que el informe y el diseño dejan como aparte: la decisión del usuario sobre la zona de archivo (B.4) o la alternativa no destructiva de sellado por renombre (fase 1, R-4).

### 3.5 Severidad de L-14

El informe la da como Baja («requiere una carrera»). Coincido en que la explotación requiere una carrera, pero el diseño la usa como argumento para que el lanzador compile desde bytes (§B.3), y eso traslada el mismo problema un nivel arriba: el lanzador no puede verificarse a sí mismo (R-5). No es una discrepancia sobre el v3, sino sobre lo que el remedio promete.

## 4. Qué encontré que el autor no vio

Todo esto está desarrollado en `DICTAMEN_FASE1.md`; acá solo lo mapeo contra el informe:

| Hallazgo mío | ¿Lo toca el informe del autor? |
|---|---|
| R-1 `pthread_sigmask` no difiere señales con hilos; numpy los crea | No. Los escenarios de Ctrl-C son monohilo (§3.2) |
| R-2 DECISION no durable ≡ «no decidido»; el ancla no la cubre; I-7 depende de la política | No. Ningún escenario pierde bytes ya escritos (§3.1). El informe pide «registro anclado o firmado» (L-12) pero no dónde ni cuándo |
| R-3 ancla manual, no consultable por la máquina | No |
| R-4 L-25: defecto de alcance | No; es consecuencia de su propia receta (§3.4) |
| R-5 raíz de confianza (lanzador, intérprete, numpy, `.pth`) | No. El informe no menciona `.pth`, `-I` ni el intérprete |
| R-6 reconciliación: definición de cola, torn write propio, hueco pegado, `flock`, objeto terminal huérfano, `intento_previo` tras ABANDONADO | No; el informe no diseña la reconciliación, solo pide «rechazo controlado ante una línea parcial» (§F.4) |
| R-7 CAS dentro del bloqueo; borrado/recreación | Parcialmente: C1 cubre el bloqueo retenido, no la carrera |
| R-8 `link()`/temporal/0444 como root | No |
| R-9 determinismo invocado para INVALIDO y negado para EVALUADO; condiciones (numpy, BLAS, hilos) sin fijar | No. El informe no discute determinismo |
| R-10 «sin texto libre» falso; canonicalizador y biblioteca Ed25519 sin fijar | No aplica al v3; el informe propone «JSON con campos explícitos» sin gramáticas ni canonicalización (§F.4). Las 10 variantes de L-17 son contra el v3, no contra un validador v4 |
| R-11 serialización de objetos (`NaN`) | No |
| R-12 lista negra por hash y nombres: cosméticas | No; el informe las propone (§F.4) |

## 5. Conclusiones del autor que no están respaldadas por su evidencia, o solo parcialmente

### 5.1 L12: la conclusión está respaldada; el procedimiento, no

El informe presenta L12 como escenario de §E.2, reproducible con los dos comandos `correr`/`observar` (informe L369-374). Pero `arnes_L13.py` **no tiene** ningún escenario L12 (`ESCENARIOS`, L121-140; `grep L12` sin resultados en el arnés, `22_…`). En el directorio `L12_registro_borrado_tras_EVALUADO/`, `correr.json` dice `"escenario": "B1_evaluado_sin_fallo"` y `observar.json` dice `"registro": "NO EXISTE"`, pero hoy ese directorio **sí** contiene `INTENTOS_E3.jsonl` (1205 bytes) con `INICIADO` y `EVALUADO` del intento 2 (`id_intento … /salida_2`, `25_…`). Reconstrucción: se corrió B1, alguien borró el registro a mano, y `observar` lo recreó con el segundo intento. El borrado no está en el arnés ni en el informe (`grep borrad` solo da las filas de las tablas, `24_…`). La conclusión («con el registro borrado, otra ejecución completa») es cierta y la evidencia guardada la sostiene; la afirmación implícita de que se reproduce con los comandos documentados no.

### 5.2 «L-25 rechazos seguros: 4 de 4 rechazos; ninguna salida creada» no tiene salida guardada

Tabla E.4 del informe, fila «L-25 rechazos seguros»: script «En línea», archivo «—». En `arnes_L25_rechazos/` hay solo los tres insumos de prueba (`aut_prueba.txt`, `p0_sintetico.json`, `ventana_sintetica.json`; `25_…`) y ningún registro de salida; la carpeta tampoco está en el manifiesto del autor. La afirmación es plausible (por lectura, el v1 y el v2 rechazan antes de crear nada si falta la autorización: E3R L462-472, v2 L514-518) pero **no verificable** desde lo que el autor dejó. Lo mismo para «L-15 enlaces: En línea, —» (`arnes_L15/real/sub/a.json` existe; la salida no).

### 5.3 «Pasado como archivo de autorización a `ejecutar_E3_v2.py real`, superaría el control»

Marcado honestamente como **I** (inferido). Lo confirmo como inferencia sólida: la condición del v2 es literalmente `FRASE in texto` y `sha(...) in texto` (v2 L515-516) y la reimplementación estática da 3 de 3 (suya y mía). Sigue sin ejecutarse, y así tiene que quedar.

### 5.4 Carpetas fuera del manifiesto

`copia_A/` (28 MB), `tmp_pytest_v3/` (181 MB), `tmp_patch/`, `arnes_L15/`, `arnes_L25_rechazos/` no están en `MANIFEST_REVISION_ADVERSARIAL.sha256` (`25_…`: 0 coincidencias). El manifiesto cubre el informe, los arneses y `registro/`; el entorno de reproducción que el informe describe (§E.1: `copia_A` con huella estable) no queda sellado. No invalida nada, pero contradice la pretensión de «todos los hallazgos son reproducibles con los scripts de `arnes/`»: para T-9 hace falta `copia_A` y su contenido no está anclado.

### 5.5 «E6: fail-closed»

Respaldado por el artefacto, pero conviene decir que el cierre es un efecto colateral de una excepción no controlada **después** de tomar el `flock` (L750→L755). Un v3 que hubiera envuelto ese `json.loads` en un `try` «para robustez» habría convertido el fail-closed en fail-open. El diseño v4 lo corrige de verdad con la cola descartada, siempre que se especifique como en R-6.

## 6. ¿Cambia algo del dictamen de fase 1?

- **No cambia el veredicto.** Sigue siendo *aceptable con correcciones* para A, C y E, con R-1 y R-2 obligatorias, y *L-25 no cerrado* por §B tal como está.
- **Se refuerzan** R-1, R-2, R-4, R-7 y R-13: la evidencia del autor es consistente con mis hallazgos y, en los tres primeros, muestra precisamente el límite del modelo de fallos que los dejó fuera.
- **Se confirma** que las remisiones del diseño a la revisión del autor (escenarios, variantes, mutantes) existen y dicen lo que el diseño dice que dicen.
- **Sin cambios** en la lista de hallazgos: no encontré en el material del autor nada que refute un hallazgo mío ni que agregue uno nuevo contra el diseño, salvo las observaciones de procedimiento de §5, que son sobre el informe y no sobre el diseño.

## 7. Límites de esta fase

- No ejecuté los arneses del autor (ejecutan `modo_real` del v3 con stubs). Verifiqué sus resultados leyendo los JSON que dejó y cruzándolos con el código; donde el resultado depende de haber corrido algo, confío en su registro, cuya integridad verifiqué por hash.
- La comprobación L-25 propia es estática y por subcadenas, igual que la del autor; no prueba que el v2 **corra**, prueba que su control no lo detendría.
- Misma familia de modelos y mismo contenedor que el autor: es probable que compartamos puntos ciegos. Lo que ninguno de los dos vio no aparece en este documento.
