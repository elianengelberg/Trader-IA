# Verificación operativa de la evaluación en papel (2026-10-17, 15:40 UTC)

Rama `claude/algo-trading-simulation-platform-ngf7xo`, último commit publicado `c6339e3`. Reglas `d2e4e1fb…` y código de `src/` `73b22f3e…`, verificados.

## A. Estado operativo
- **¿Está funcionando? Todavía no hay nada que funcione en el tiempo, y no hace falta.** El diseño es una evaluación **diferida y determinista**:
  - las reglas y el código quedaron congelados en el commit `89278f7` (2026-10-17 05:23 UTC), antes de cualquier dato evaluado;
  - las observaciones las genera el mercado y las publica data.binance.vision con checksum;
  - cada corte las recalcula de forma idéntica.
- **Automático:** nada. No hay proceso, cron ni servicio.
- **Manual:** un comando por corte (`papel/corte.py AAAA-MM-DD`), y opcionalmente cuando se quiera.
- **Observaciones prospectivas válidas: cero.** La primera ejecución es el **2026-10-18**, con la decisión tomada al cierre del 2026-10-17. A la hora de esta verificación esa vela aún no cerró: el ensayo en seco lo confirma («SIN OBSERVACIONES») y señala que el 2026-10-17 no está publicado. Las primeras observaciones serán evaluables cuando se publiquen los archivos diarios del 2026-10-17 y el 2026-10-18.
- **Fechas:**
  - congelación verificable por el commit `89278f7` y su publicación en GitHub (la fecha del commit la declara el autor; el registro de la publicación lo guarda GitHub);
  - historia de la señal: 2026-04-20 → 2026-10-17, **no cuenta como resultado** (la ventana evaluada empieza el 2026-10-18);
  - revisiones de abril de 2027 (informativa) y de octubre de 2027 (con consecuencias, corte **2027-10-19**; ver C3).

## B. Integridad y seguridad
- **Datos:**
  - 180 + 180 archivos diarios oficiales de historia, que al volver a bajarlos coinciden **byte a byte** con el manifiesto commiteado;
  - sin huecos, repeticiones, velas irregulares ni precios inválidos;
  - marcas en µs del spot validadas;
  - funding de julio a septiembre de 2026, idéntico al registrado.
- **Sin look-ahead:** la decisión del día d usa solo cierres ≤ d − 1 y se ejecuta en la apertura de d (pruebas de propiedad: el futuro alterado no cambia el pasado). El registro de decisiones guarda el cierre usado y el momento de disponibilidad (d a las 00:00 UTC).
- **Costes y ejecución:**
  - 10 + 5 bps sobre el valor negociado, en la apertura oficial siguiente al cierre de la decisión. El spread queda incluido en el slippage.
  - **Limitación del protocolo, no corregible sin cambiar reglas:** ejecutar a la apertura inmediata es ligeramente optimista frente a una orden enviada minutos después. El único estrés con consecuencias es costes ×2; los retrasos no forman parte de los criterios. Queda como **hipótesis futura separada**: un protocolo con un retraso de ejecución explícito.
- **El benchmark estático** usa la exposición media realizada de la propia estrategia. Es un benchmark de **atribución** (timing frente a exposición), no una estrategia operable.
- **Seguridad:**
  - ningún módulo envía órdenes, usa claves ni toca producción;
  - el monitor del carry es una función pura que solo informa;
  - en esta verificación **no se operó, no se desplegó y no se tocó ningún proceso**.
  - El commit `c25bbd8` («Paper start…», del 2026-10-13) pertenece a otro componente del repositorio y no se modificó.

## C. Defectos encontrados (todos antes de la primera observación; las reglas y el código congelado no cambian)

| # | Severidad | Evidencia | Impacto | Corrección |
|---|---|---|---|---|
| C1 | **Alta** | Rama A con datos desde el 2026-10-14 (el comando documentado era de la rama B): 365 días evaluados y exposición media de 0,33 con la señal inexistente 180 días, **sin aviso** | Resultados inválidos en silencio | `papel/corte.py` descarga la historia completa y bloquea si falta la señal en el cierre previo al inicio. Prueba `test_historia_incompleta_bloquea…` |
| C2 | Media | Un corte posterior a los datos evaluaba 119 de 365 días sin aviso; con la ventana vacía, `ValueError` | Corte mal etiquetado o caída | Bloquea con «datos obsoletos» o «no publicados». Pruebas `test_datos_obsoletos_bloquean` y `test_sin_observaciones…` |
| C3 | Media | Con el código congelado, el corte 2027-10-18 da 11,99 «meses» → informativo | La regla de falsación de 12 meses no se aplicaría en la fecha prevista | Corte operativo **2027-10-19** (adenda 2). Prueba `test_el_corte_del_2027_10_18_no_decide…` |
| C4 | Baja | `descargar` fallaba si ningún día del rango estaba publicado (FileNotFoundError) | Caída en un caso normal (vela aún no publicada) | El ejecutor crea la carpeta antes |
| C5 | Baja | Monitor a mitad de mes: 82 % de cobertura dividido por 90 días = 5,2 % (sesgado; con los días cubiertos, ≈ 6,3 %) | Cifra engañosa, aunque no dispara | El ejecutor usa el último corte de mes completo e informa la ventana y el método. Prueba `test_monitor_usa_meses_completos…` |
| C6 | Baja | No había registro de decisiones ni detección de revisiones de archivos oficiales | Menor auditabilidad | `decisiones_<SIMBOLO>.csv` y comparación con los hashes ya registrados. Pruebas `test_corte_evaluado_registra…` y `test_revision_de_un_archivo…` |
| C7 | Media | Hallado en la revisión del diff: al repetir un corte EVALUADO, `preparar()` y el monitor volvían a consultar la fuente y a escribir datos y manifiestos **antes** de comprobar el estado. Con un archivo histórico que respondía 404, el manifiesto de BTC quedaba con 255 archivos y 1 ausente, sin coincidir con su `datos_sha256` (aunque `resultado.json` no se sobrescribía) | La evidencia de un corte cerrado podía alterarse | Comprobación temprana y escritura con reemplazo atómico (ver abajo). Pruebas `test_reintento_…`, `test_un_resultado_existente_ilegible…` y `test_un_fallo_antes_del_reemplazo…` |
| C8 | Media | Riesgo residual de C7: nada verificaba la coherencia entre `resultado.json` y `REGISTRO.jsonl`, ni la cadena `linea_anterior_sha256`. Una caída entre el reemplazo y la línea del registro, o un corte de energía después de una ejecución exitosa (sin `fsync`), dejaba un corte EVALUADO sin registrar **en silencio**; una línea EVALUADO sin su resultado permitía **reevaluar** sin aviso | Rastro de auditoría incompleto o reevaluación no detectada | Verificación de solo lectura de todo el estado compartido al comienzo de cada ejecución, sin reparación automática, y `fsync` antes y después de la marca (ver abajo). Pruebas `test_una_inconsistencia…`, `test_un_fallo_tras_el_reemplazo…`, `test_muerte_real…` y `test_todo_se_sincroniza…` |
| C9 | Media | Riesgo residual de C7: dos ejecuciones sobre la misma carpeta de cortes no se coordinaban. Sin cerrojo, en la prueba de carrera: con el mismo corte, 8 de 8 corridas terminaron con un proceso caído por el temporal de nombre fijo de hcarry; con cortes distintos, 8 de 8 dejaron la cadena del registro bifurcada **sin ningún error visible** | Datos reescritos tras evaluar, registro bifurcado o duplicado | Cerrojo exclusivo `fcntl.flock` sobre la carpeta de cortes (ver abajo). Pruebas `test_con_el_cerrojo_tomado…`, `test_dos_procesos_a_la_vez…` y `test_el_cerrojo_se_libera…` |
| C10 | Media | Hallado en la revisión final: Python 3.11 acepta `20270418` como fecha, y el ejecutor la usaba tal cual como nombre del corte. Se podía evaluar dos veces el mismo día con nombres distintos: el registro y la verificación trabajan por nombre. Además, el monitor calculaba mal su ventana | Segunda evaluación del mismo corte sin detectarla | Solo se acepta la forma canónica `AAAA-MM-DD`, y se valida antes de tomar el cerrojo o de crear nada. Prueba `test_una_fecha_no_canonica…` |

**Pruebas:**
- `tendencia_btc`: **19/19**, de las cuales 9 son nuevas y reproducen C1–C6 con una fuente oficial **simulada** (no son rendimiento);
- `hcarry_next`: 81/81;
- lint limpio; huellas congeladas intactas; originales recuperados, 9/9.

**Ensayo en seco con datos reales** (scratchpad, fuera del registro del ensayo): «SIN OBSERVACIONES», 2026-10-17 no publicado, sin revisiones, monitor del 6,5 %.

### C7: corrección acotada (2026-10-17, 16:05 UTC; solo `papel/corte.py` y sus pruebas)
- **Comprobación temprana.** Es lo primero que hace `ejecutar()` después de validar la fecha (desde C8–C9, después de tomar el cerrojo y como parte de la verificación de todo el estado): lee `cortes/<corte>/resultado.json` sin efectos secundarios.
  - **EVALUADO:** se detiene con `CorteBloqueado` («corte AAAA-MM-DD: ya está EVALUADO…»); la línea de comandos imprime `DETENIDO: …` y sale con código 1.
  - **Ilegible o incompleto** (JSON o UTF-8 inválidos, no es un objeto, sin `estado`, estado desconocido, otro corte, una carpeta en su lugar): también se detiene. Nunca se trata como un corte nuevo.
  - **Solo continúa** si no existe o si es provisional («SIN OBSERVACIONES…» o «NO EVALUABLE…») del mismo corte. El comportamiento de los cortes provisionales no cambia.
- **Garantía exacta:** si `resultado.json` dice EVALUADO, un nuevo intento **no consulta la fuente, no crea carpetas y no escribe, renombra ni borra nada**, sea cual sea la fuente (distinta, caída o sin publicar). No depende de la red ni de los datos, porque ocurre antes de usarlos. Supone una sola ejecución a la vez: desde C9 lo asegura el cerrojo.
- **Orden de escritura** (el vigente tras C8–C9). Como un resultado EVALUADO pasa a ser terminal, lo que lo acompaña se hace antes:
  1. con el cerrojo tomado, se lee y verifica todo el estado compartido, incluido `REGISTRO.jsonl` (C8);
  2. se descargan los datos y se escriben las tablas de decisiones;
  3. se sincroniza todo el corte (C8);
  4. se escribe `resultado.json`, al final, como marca de corte completo;
  5. se añade la línea al registro y se sincroniza.
- **Alcance de `os.replace`.** `resultado.json` se escribe en un temporal del mismo directorio (`.resultado.json.<aleatorio>.tmp`, creación exclusiva, `fsync`) y se pone en su lugar con `os.replace`. Un lector ve el archivo anterior o el nuevo completo, nunca uno a medias. Ante un error se borra el temporal y se propaga el error original; si el borrado falla, se añade como nota sin ocultar el original.
  - La garantía cubre **solo este archivo**: no hace atómica la evaluación ni las tablas, el registro o los datos.
  - Depende del sistema de archivos: un renombrado dentro de un mismo volumen.
  - Desde C8 también se sincroniza la carpeta después del reemplazo; los límites están en la sección C8–C9.
- **Pruebas (16 casos nuevos y 1 ajustado en `tests/test_papel_corte.py`; fuentes simuladas y carpetas temporales):**
  - ajustado: repetir el corte evaluado de 12 meses ahora se detiene y no duplica el registro;
  - reintento con otra fuente;
  - reintento con la fuente caída (por red y sin publicar);
  - siete formas de `resultado.json` ilegible;
  - resultado nuevo completo y sin temporales;
  - fallos al escribir, reemplazar, escribir las tablas o leer el registro;
  - error original conservado si no se puede borrar el temporal.
  - Comparación: **todas** las rutas bajo la raíz de cortes (datos, `.CHECKSUM`, manifiestos, resultado, tablas, `REGISTRO.jsonl`, carpetas y ocultos) con SHA-256, tamaño y mtime en ns, antes y después. Una fuente espía comprueba que no se consulte.
  - **Resultado:** `tendencia_btc` 35/35 y `hcarry_next` 81/81; ruff limpio; huellas congeladas intactas.
  - **Mutaciones** (copias en el scratchpad): sin la comprobación temprana, con escritura directa, con las tablas o la lectura del registro después del resultado, con una limpieza que oculta el error, con lo ilegible tratado como nuevo y sin borrar el temporal. **Las siete mutaciones hacen fallar las pruebas**, y cada falla corresponde a la condición que se reintrodujo.
- **Riesgos residuales tras C7:**
  - **Ejecución concurrente:** resuelto por C9 en una misma carpeta de cortes (cerrojo); los límites, abajo.
  - **Caída entre el reemplazo y la línea del registro:** ahora la detecta C8 en la siguiente ejecución, de cualquier corte. Sigue sin repararse sola: requiere el procedimiento manual.
  - **Borrar o editar `resultado.json` a mano:** ahora C8 lo detecta como entrada sin resultado o como hash distinto. No lo impide.
  - **Tablas huérfanas** (sigue igual): si falla algo antes del reemplazo, las tablas pueden quedar junto a un resultado provisional o sin resultado, nunca junto a uno EVALUADO. Las sobrescribe la siguiente ejecución que evalúe.
  - **Un `kill -9` durante la escritura** puede dejar un `.resultado.json.*.tmp` (sigue igual). Nunca se confunde con el resultado ni bloquea.

### C8–C9: coherencia del registro, cerrojo y durabilidad (2026-10-17, 18:10 UTC; solo `papel/corte.py` y sus pruebas)
**Formato previo inspeccionado.** En el repositorio no hay ningún corte ni registro: `papel/cortes/` nunca existió y `corte.py` nunca se commiteó. Los cuatro registros de ensayos anteriores, en el scratchpad (entre ellos el ensayo en seco con datos reales hecho con la primera versión del ejecutor), usan el mismo esquema de cinco campos, la cadena es válida y la última línea termina en salto de línea: **los cuatro pasan la verificación**. Ningún formato legítimo queda rechazado. Los `resultado.json` de `hcarry_next/experimentos` son de otro sistema y el ejecutor no los lee.

**Cerrojo (C9).** Es lo primero, después de validar la fecha: `fcntl.flock` exclusivo y sin espera sobre la propia carpeta `papel/cortes/`, sin archivo de cerrojo. Se mantiene durante toda la operación: verificación, descargas (incluidos los temporales `<archivo>.tmp` de hcarry, que viven dentro del corte), tablas, resultado y registro.
- Si está tomado, la ejecución se detiene con «otra ejecución de papel/corte.py tiene el cerrojo» (código de salida 1), sin consultar la fuente ni tocar nada.
- Lo libera el sistema operativo al cerrar el descriptor, al terminar o al morir el proceso, incluso con `SIGKILL`. Nunca hay que borrar un archivo para liberarlo.
- **Primera ejecución:** si `papel/cortes/` no existe, se crea vacía (sin crear carpetas intermedias) y recién después se toma el cerrojo. Como la carpeta no existía, no había ningún corte que tocar.
- **Límites:**
  - es **consultivo**: solo coordina ejecuciones de este script sobre la **misma** carpeta; no frena ediciones a mano ni a otros programas (por ejemplo, `estado_inicial.py`, que escribe en `datos_papel/`, fuera del cerrojo);
  - **no coordina copias distintas del repositorio** (por ejemplo, dos sesiones en la nube): ahí la protección es de procedimiento: traer los cambios antes de ejecutar, publicar el corte enseguida, un solo operador; un conflicto de git en `REGISTRO.jsonl` lo dejaría a la vista;
  - no es fiable en sistemas de archivos de red, y no existe en Windows.

**Verificación de coherencia (C8).** Se hace con el cerrojo tomado y **antes** de consultar la fuente, crear la carpeta de un corte nuevo o escribir nada. Es estrictamente de solo lectura y abarca **todos** los cortes, no solo el pedido. Detecta:
- **en el registro:** una línea que no termina en salto de línea (escritura interrumpida), una línea que no es JSON o le faltan campos o tienen tipos inválidos, un registro que no es UTF-8, y una cadena `linea_anterior_sha256` rota (línea editada, reordenada, truncada o bifurcada por dos procesos);
- **en los resultados:** un `resultado.json` ilegible, incompleto, con un estado desconocido, de otro corte, una carpeta o un enlace roto en su lugar. **Nunca se trata como si no existiera**;
- **entre ambos:**
  - un resultado EVALUADO sin su entrada;
  - una entrada EVALUADO sin su resultado;
  - un resultado que dice provisional con una entrada EVALUADO;
  - un SHA-256 distinto del de la entrada EVALUADO;
  - una segunda entrada (duplicado o reevaluación) después de la EVALUADO;
  - una línea con el mismo hash que el resultado pero otro estado.

Ante cualquiera de estos casos lanza `CorteInconsistente`; la línea de comandos imprime `INCONSISTENTE: corte …: archivo …: tipo: detalle` y sale con **código 2**. **Bloquea todos los cortes**, incluso el pedido cuando la inconsistencia está en otro, para que salga a la luz en la siguiente ejecución, sea cual sea. **No existe reparación automática:** no se recalcula, no se reescribe y no se añade ninguna línea.

**No detecta:**
- la edición de campos de la **última** línea del registro que no sean el hash ni el estado (por ejemplo, `ejecutado_utc`), porque ninguna línea posterior la ancla; git sí la dejaría a la vista;
- la alteración de datos, manifiestos o tablas de un corte ya evaluado; quedan como evidencia, con sus hashes en `resultado.json` (`datos_sha256`, `decisiones_sha256`), pero la verificación no los recalcula;
- la falta de línea de una versión **provisional**: es tolerada, porque esas versiones pueden cambiar y la siguiente ejecución de ese corte la registra;
- el borrado simultáneo de `resultado.json` **y** de su línea, ni un registro reemplazado entero por otro coherente.

**Procedimiento manual (cada caso requiere autorización explícita; nada de esto lo hace el código):**
1. **Resultado EVALUADO sin entrada** (caída entre el reemplazo y la línea):
   - verificar que `resultado.json` es legible y que sus `reglas_sha256` y `codigo_sha256` son los congelados;
   - verificar que su `datos_sha256` coincide con los manifiestos del corte y que las tablas coinciden con `decisiones_sha256`;
   - con autorización, añadir una sola línea con el formato habitual, la hora real del registro y la cadena correcta, y documentar el incidente.
   - Si algo no coincide, no añadir nada: tratar el corte como evidencia dañada.
2. **Entrada EVALUADO sin resultado, o resultado con otro hash:**
   - recuperar el `resultado.json` exacto desde git;
   - si no está, regenerarlo **sin red** en una carpeta aparte, a partir de los datos y `.CHECKSUM` del propio corte, y aceptarlo solo si su SHA-256 es el de la entrada;
   - si no se logra, declarar perdido el corte y documentarlo. **Nunca** volver a evaluarlo con datos nuevos.
3. **Línea incompleta, cadena rota o duplicado:**
   - comparar con la última versión del registro en git;
   - una línea incompleta al final corresponde a la última ejecución: con autorización, quitar solo ese fragmento y seguir con el caso 1;
   - una cadena rota o un duplicado indican una edición o una ejecución concurrente: revisar a mano qué ejecución es la válida antes de tocar nada.

**Durabilidad (`fsync`).** El orden de escrituras no cambió; se agregaron puntos de sincronización:
- `fsync` de cada archivo y carpeta del corte (datos y `.CHECKSUM` de hcarry, manifiestos, tablas) y de la carpeta de cortes, **antes** de escribir `resultado.json`;
- `fsync` del temporal, `os.replace` y `fsync` de la carpeta del corte;
- solo después, la línea del registro con su `fsync` y el de la carpeta de cortes.
- Así, tras un corte de energía no debería quedar una línea EVALUADO sin su resultado ni un resultado sin sus datos. Lo que sí puede quedar —un resultado sin su línea— se detecta.
- **Límites:**
  - **no es una transacción multiarchivo**: entre el reemplazo y la línea del registro sigue habiendo una ventana; C8 la detecta, no la evita;
  - `fsync` depende de que el disco, la virtualización y el sistema de archivos lo respeten (cachés de escritura sin batería, sistemas de red); en macOS, `fsync` no vacía la caché del disco (haría falta `F_FULLFSYNC`);
  - si falla un `fsync` después del reemplazo, la ejecución se detiene con ese error y la siguiente lo detecta, salvo que la línea ya estuviera escrita (entonces el estado es coherente, aunque su durabilidad no consta).

**Pruebas (`tests/test_papel_corte.py`: 47 casos, 22 de ellos nuevos para C8–C9; fuentes simuladas y carpetas temporales, sin datos de mercado).** Cada una compara todas las rutas y contenidos (SHA-256, tamaño, mtime en ns, carpetas y enlaces) antes y después, y usa una fuente espía para comprobar que no se consulte.
- **Doce inconsistencias**: EVALUADO sin entrada, entrada sin resultado, hash distinto, resultado que contradice el registro, estado contradictorio, duplicado, cadena editada, cadena reordenada, línea truncada (sin salto y con salto), campo ausente y registro que no es UTF-8.
  - Cada una se ejecuta cuatro veces, alternando el mismo corte y uno nuevo: siempre `CorteInconsistente`, cero consultas, árbol idéntico, sin crear la carpeta del corte nuevo y sin reparar nada.
- **Enlace roto** en lugar de `resultado.json`: no se trata como si no existiera.
- **Fallos simulados después del reemplazo** (abrir el registro, `fsync` de la carpeta, `fsync` del registro) y **fallos antes** (tablas, sincronización, escritura del temporal, reemplazo).
- **Muerte real** de un proceso con `os._exit` justo después del reemplazo, sin ningún `except` ni `finally`: la siguiente ejecución lo detecta sin tocar nada y el cerrojo del proceso muerto queda libre.
- **Cerrojo ocupado por otro proceso** detenido a mitad de `preparar()`: otro proceso y otro descriptor del mismo proceso se detienen sin tocar nada, con el mismo corte y con otro. Al liberarse, todo sigue en orden.
- **Dos procesos lanzados a la vez**, con el mismo corte y con cortes distintos.
  - Medido aparte, en 10 + 10 corridas: con cerrojo, siempre hubo disputa y el estado final fue coherente; sin cerrojo, ver la fila C9.
- **Liberación del cerrojo** tras `SIGKILL` y al terminar normalmente; no queda ningún archivo de cerrojo.
- **Orden de los `fsync`**, verificado con `/proc/self/fd`.
- **Resultado:** `tendencia_btc` 57/57 (el archivo del ejecutor, 47/47, tres corridas estables), `hcarry_next` 81/81, ruff limpio, huellas congeladas intactas.
- **Mutaciones** (copias en el scratchpad): se quitó por separado cada una de las 16 reglas nuevas (la verificación entera, el cerrojo, la cadena, los duplicados, cada sentido de la coherencia, el hash, la contradicción de estado, el salto final, la validación de campos, los enlaces rotos, cada `fsync` y el orden verificación → descarga). **Cada mutación hace fallar exactamente las pruebas de esa regla.**
- **No probado:**
  - un corte de energía real ni discos que no respetan `fsync`;
  - sistemas de archivos de red, macOS y Windows;
  - dos copias distintas del repositorio;
  - procesos de otros programas que no usan el cerrojo.

## D. Validez estadística
- **Hoy no puede concluirse nada:** no hay observaciones.
- **El protocolo exige:**
  - ≥ 12 meses (corte 2027-10-19) para la única decisión temprana posible, **detener** si P(exceso > 0) < 0,10;
  - ≥ 24 meses (corte 2028-10-18) para poder declarar una ventaja, con P ≥ 0,95, P(BTC) ≥ 0,90 y costes ×2.
- **Potencia** (`papel/potencia.json`): con el efecto de desarrollo hacen falta ≈ 7 años para P ≥ 0,95; con la mitad del efecto, ≈ 28. Un año da un error de ± 31 %/año sobre el exceso conjunto.
- **Un resultado favorable al principio no demuestra nada:**
  - el ruido es varias veces mayor que el efecto;
  - la estimación de desarrollo está probablemente inflada (se eligió tras verla);
  - un solo régimen de mercado puede dominar 12–24 meses;
  - mirar en varios cortes aumenta los falsos positivos si se interpretan fuera de los criterios.

## E. Próximo paso
**Una única acción:** autorizar el commit y push de esta corrección operativa:
- `papel/corte.py`, con las correcciones C7–C9;
- `tests/test_papel_corte.py`;
- la adenda 2;
- este informe.

Así el **procedimiento de evaluación queda congelado antes de la primera observación**. Después **no hace falta modificar nada**: corresponde dejar correr el experimento y ejecutar `papel/corte.py 2027-04-18` en la revisión informativa.
