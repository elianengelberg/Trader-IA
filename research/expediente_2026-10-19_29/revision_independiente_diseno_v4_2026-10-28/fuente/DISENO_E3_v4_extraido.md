# E3 v4: diseño de correcciones para L-13, L-25 y L-17

**Decisión: DISEÑO BLOQUEADO POR CONTRADICCIONES METODOLÓGICAS.** La parte técnica (A, B, C y E) está completa y puede ir ya a revisión independiente. Lo que no se puede especificar todavía es la parte metodológica del v4: la ventana fijada en el código, sus metadatos y los valores de las decisiones de la autorización. Esos valores dependen de las decisiones que solo vos podés tomar (§D.6).

**Este diseño no es independiente.** Lo hizo el mismo agente que escribió la reparación, el v3 y la revisión adversarial.

En esta fase no escribí archivos, no ejecuté comandos y no modifiqué nada. Me apoyo en la evidencia de la revisión anterior (`INFORME_REVISION_ADVERSARIAL_E3H1H2.md`, sha256 `c861d4a3…`): los escenarios de la sección E.2 son E1, I1, K1, etc.; los de la sección E.3, las variantes de autorización.

---

## A. L-13: protocolo de persistencia

### A.1 Causas del defecto, según la evidencia

1. **El cierre está mal protegido.** La publicación de INVALIDO y EVALUADO está dentro de un `except BaseException` que convierte cualquier fallo posterior en un ERROR y escribe sobre el mismo archivo (I1, I5, E1, E4, E7).
2. **Hay dos almacenes sin orden de recuperación.** El archivo de resultado y el registro de intentos se actualizan en secuencia y nada define qué hacer si falla el segundo paso (E2, I2).
3. **Qué se expuso no queda registrado.** «Estadísticos iniciados» sale de una etiqueta en memoria, no de un registro durable.
4. **La salida la elige quien ejecuta y el intento se anota tarde.** La carpeta de salida es libre por intento, y el intento se anota después de crearla (K1, K2).
5. **El registro es frágil.** Vive en el árbol del código, se puede borrar (L12) y no tolera una línea a medio escribir (E6).

### A.2 Arquitectura propuesta

**Un almacén de ejecución único**, derivado de la identidad de la evaluación y fuera de los árboles de código y de datos:

| Componente | Diseño |
|---|---|
| `registro` | Solo se agrega. Cada línea tiene la forma `<longitud>\t<sha256 del contenido>\t<contenido JSON canónico>\n`. El contenido incluye `seq` y `hash_previo`, de modo que las líneas forman una cadena de hashes. Una cola cortada se detecta sin ambigüedad |
| `objetos/<sha256>` | Objetos inmutables, con el nombre igual a su hash: resultados, validez e informes de error. Se escriben a un temporal con `O_EXCL`, se sincronizan, se publican con `link()` (que falla si ya existe) y después se sincroniza el directorio. Nunca se sobrescriben. Si el nombre ya existe, se comparan los bytes |
| `bloqueo` | `flock` exclusivo durante todo el intento. Cada línea se agrega bajo el bloqueo y comparando antes la cabeza del registro |
| Ancla externa | El hash de la cabeza del registro, después de cada consumo y de cada cierre, se guarda fuera del entorno: en un commit tuyo, en tu registro personal o en un almacenamiento de escritura única. **Es lo único que detecta que el almacén entero se borró (L-12).** La elección del mecanismo es tuya |

**No hay carpeta de salida por intento.** Eso elimina K1 y K2.

### A.3 Eventos y orden

1. **Comprobaciones previas, sin efectos.** Autorización (§C), insumos, ventana, módulos y mapeos con `estado`. Un fallo aquí es un rechazo: no se escribe nada ni se consume nada.
2. **`ABIERTO` durable.** En una sola línea se registran el consumo de la autorización y la apertura del intento: sha256 de la autorización, nonce, cabeza previa y huella del entorno (intérprete, versiones y hashes del código ejecutado). **Ningún precio se lee antes de esta línea.**
3. **`ETAPA(e)` durable antes de entrar en cada etapa:**
   - `panel`: se cargan los precios;
   - `simulacion`: hoy se llama `validez_previa`;
   - `estadisticos`;
   - `publicacion`.

   Qué se expuso se deriva de la última etapa **registrada**, nunca de la memoria.
4. **`DECISION(tipo, sha_objeto)` durable**, con tipo EVALUADO o INVALIDO, en cuanto el veredicto existe en memoria y **antes** de escribir el objeto. Es una línea corta, la primera escritura después de decidir.
5. **Se escribe el objeto terminal.**
6. **`PUBLICADO(sha_objeto)` durable.**
7. **Ancla externa.**

**ERROR.** Solo se escribe si no hay una `DECISION` del intento: primero el objeto de error, después la línea `ERROR(etapa_max, sha_objeto)`. El manejador de excepciones consulta el registro, no una variable en memoria. Si ya hay una `DECISION`, **nunca** escribe un ERROR.

**Señales.** Durante los pasos 4 a 6, SIGINT y SIGTERM se difieren con `pthread_sigmask`. Una muerte del proceso con SIGKILL queda cubierta por la reconciliación.

### A.4 Reconciliación

Es una herramienta separada.
- No calcula nada.
- No requiere una autorización de ejecución.
- Solo agrega líneas.
- Es idempotente: correrla dos veces da lo mismo.
- Una cola cortada se marca con `COLA_DESCARTADA(sha de los bytes)`, sin truncar el archivo.

Qué hace según lo que encuentra en el intento abierto:

| Situación | Acción | Estado final |
|---|---|---|
| Hay `DECISION` y su objeto | `PUBLICADO_RECUPERADO` | El tipo terminal decidido |
| Hay `DECISION` y falta el objeto | `TERMINAL_SIN_OBJETO(tipo)` | Terminal: **nunca** admite reintento |
| No hay `DECISION`, pero sí un objeto de error huérfano | `ERROR_RECUPERADO` | ERROR, con la última etapa del registro |
| No hay nada | `ABANDONADO(etapa_max)` | Equivale a un ERROR en esa etapa |
| Hay dos objetos terminales o la cadena está rota | `BLOQUEO_PERMANENTE` | Lo decidís vos |

### A.5 Invariantes

| Id | Invariante |
|---|---|
| I-1 | Por evaluación hay a lo sumo una `DECISION`. Después de una `DECISION`, ningún evento abre un intento |
| I-2 | Un objeto publicado nunca se modifica ni se borra, y sus bytes coinciden con su nombre |
| I-3 | Toda línea que cita un objeto cita uno que existe y cuyo hash coincide, salvo en el caso `TERMINAL_SIN_OBJETO`, que queda declarado |
| I-4 | Cada intento cita exactamente una autorización, y cada nonce aparece a lo sumo en un `ABIERTO` |
| I-5 | Antes de cualquier lectura de precios existe un `ABIERTO` durable |
| I-6 | Antes de entrar en una etapa existe su `ETAPA` durable |
| I-7 | Un fallo después de una `DECISION` nunca produce un ERROR, y **INVALIDO nunca pasa a un estado reintentable** |
| I-8 | Un intento abierto bloquea cualquier intento nuevo hasta la reconciliación |
| I-9 | La cadena es válida. Si la cabeza difiere del ancla externa, todo queda bloqueado |
| I-10 | Un reintento, si la política lo admite, exige una autorización nueva ligada a la cabeza actual que cite el objeto de error y su etapa |

### A.6 Transiciones válidas

| Estado de partida | Acción | Estado de llegada |
|---|---|---|
| NUEVA | `ABIERTO` | ABIERTO(etapa = ninguna) |
| ABIERTO | `ETAPA(e)` | ABIERTO(etapa = e) |
| ABIERTO | `DECISION(t)` | DECIDIDO(t) |
| DECIDIDO(t) | `PUBLICADO` | CERRADO(t) |
| ABIERTO | `ERROR(e)` | CERRADO_ERROR(e) |
| ABIERTO o DECIDIDO | Fallo | Igual que antes, pero bloqueado, a la espera de la reconciliación |
| CERRADO_ERROR(e) | Política D-4 y autorización nueva | ABIERTO, otro intento |

CERRADO(EVALUADO) y CERRADO(INVALIDO) son absorbentes: de ahí no se sale.

**Residuo honesto.** Si falla justo la escritura de `DECISION(INVALIDO)`, la reconciliación ve la etapa `simulacion`. Con la política de reintentos (i), que permite reintentar después de un ERROR en esa etapa, se admitiría repetir una comprobación de validez **determinista**. Con las políticas (ii) o (iii) ese hueco desaparece. Por eso se exige una prueba de determinismo de esa etapa.

### A.7 Comportamiento ante fallos parciales por operación

| Operación | Fallo antes de quedar durable | Fallo después de quedar durable |
|---|---|---|
| `ABIERTO` | NUEVA: no se consumió nada ni se leyó nada. Si quedó una cola cortada, bloqueo y luego `COLA_DESCARTADA` | ABIERTO |
| `ETAPA(e)` | No se entra en la etapa. Queda ABIERTO en la etapa anterior y bloqueado | ABIERTO(e) |
| `DECISION` | El manejador escribe un ERROR en la etapa actual. Con estadísticos, no hay reintento | DECIDIDO: queda terminal pase lo que pase |
| Objeto terminal | DECIDIDO sin objeto: reconciliación → `TERMINAL_SIN_OBJETO` | DECIDIDO con objeto huérfano: reconciliación → publicado |
| `PUBLICADO` | DECIDIDO: reconciliación → publicado | CERRADO |
| Objeto o línea de ERROR | ABIERTO y bloqueado: reconciliación | CERRADO_ERROR |
| Ancla externa | Cerrado, pero con discrepancia con el ancla: bloqueo hasta que lo actualices | — |

---

## B. L-25: aislamiento de las versiones antiguas

### B.1 Preservar no es lo mismo que mantener ejecutable

- **Preservar** significa conservar los bytes y poder verificarlos (hashes, manifiestos, tarball sellado y copia externa).
- **Ser ejecutable** significa que, en el mismo entorno, conviven el código, los datos, un intérprete y una autorización satisfacible.

Hoy, en el scratchpad, se dan las cuatro cosas a la vez para el v1 y el v2. Además, para el v2 la autorización ya existe: `INFORME_REPARACION_E3H1H2.md`.

### B.2 Qué no se puede conseguir sin modificar la historia

- No se puede hacer que el v1 o el v2 consulten el registro del v4: su código está congelado.
- Tampoco se puede volver «no autorizante» un documento congelado: el v2 busca subcadenas en el archivo que se le pase.

**La única garantía técnica es que esos puntos de entrada no existan en ningún entorno donde haya datos y capacidad de ejecutar.**

### B.3 Arquitectura en dos zonas

**Zona de archivo (no operativa):**
- contiene los árboles congelados tal como están, los tarballs sellados y los manifiestos;
- **nunca** se usa para ejecutar.

**Zona de ejecución (nueva y dedicada):** se arma desde cero con:
1. el paquete del v4 (código y pruebas);
2. los datos importados desde el tarball sellado a un almacén **direccionado por contenido**, verificando cada hash. El v1 y el v2 esperan la estructura `resultados/calidad/series`, que en esta zona no existe;
3. el almacén de ejecución (§A.2) y su ancla;
4. el **lanzador**.

No contiene ningún árbol histórico.

**El lanzador es el único punto de entrada:**
- lee una vez los bytes del orquestador, comprueba que su sha256 esté en una lista blanca (fijada en el lanzador **y** en la autorización) y lo compila desde esos bytes (esto resuelve también L-14);
- el orquestador del v4 se niega a correr si no lo invocó el lanzador, mediante un token que solo existe en memoria.

**Auditoría previa automática, antes de cualquier comprobación de autorización.** El lanzador se niega a correr en cualquiera de estos casos:
- algún archivo de la zona tiene un sha256 de la lista de revocados: v1 (`3b64a04d…`), v2 (`01fc9344…`), sus copias y **también el v3** (`c089cc6a…`), porque tiene L-13;
- existe en las raíces conocidas algún `RESULTADO_E3*.json`, `REGISTRO_EJECUCION.json` o `VALIDEZ_PREVIA.json` de cualquier versión;
- el inicio del registro no contiene el acta de revocación.

**Acta de revocación.** La firmás vos. Lista los hashes revocados y declara expresamente que `INFORME_REPARACION_E3H1H2.md` y `PLAN_EJECUCION_UNICA_E3R.md` **no** son autorizaciones.

### B.4 Decisión que te corresponde

Si querés quitarles la ejecutabilidad del todo en la zona de archivo, hay que retirar las copias extraídas del scratchpad una vez verificados los tarballs sellados y las copias externas. Los bytes se preservan en el tarball. Eso es borrar artefactos, y no lo propongo hacer sin tu orden expresa.

### B.5 Límite

En un contenedor donde todo corre como root, ninguna medida resiste un uso deliberado. El diseño protege contra:
- la ejecución accidental;
- la ejecución iniciada por un agente;
- la confusión de documentos con autorizaciones;
- la doble ejecución entre versiones dentro de la zona controlada.

El resto es gobierno: el ancla externa y no emitir autorizaciones para versiones revocadas.

---

## C. L-17: autorización estructurada

### C.1 Formato

- Un único objeto JSON en **forma canónica** (RFC 8785 o una canonicalización equivalente fijada en el código):
  - UTF-8 sin BOM;
  - claves ordenadas;
  - sin espacios;
  - sin números de coma flotante;
  - sin claves repetidas.
- El archivo tiene que ser **exactamente** esos bytes, sin texto antes ni después.
- Va acompañado de una **firma Ed25519 separada** con una clave que **solo tenés vos**. La clave pública se fija en el código.

Con eso, ni yo ni otro agente podemos fabricar una autorización válida. El proyecto tiene un antecedente (SV-1, `confianza.py`) que habría que revisar antes de reutilizarlo.

### C.2 Campos obligatorios

No se admiten campos adicionales y todos los enumerados son cerrados.

| Bloque | Campos |
|---|---|
| `esquema` | `"E3-AUTORIZACION/1"` |
| `protocolo` | `id`, `version`, sha256 completo del protocolo v3, de la Adenda 1, la Adenda 3 y las notas, y de la Adenda R, o `null` si no se adopta |
| `evaluacion` | `id` (del que se deriva el almacén), `hipotesis: ["H1","H2"]`, `analisis` (la lista completa y fija: Holm, R1–R6, descriptivo), `alcance: "UN_INTENTO"`, `modo: "real"` |
| `codigo` | sha256 del lanzador, del orquestador y de cada módulo (`universo`, `motor`, `inferencia`, `pruebas_motor`, `conciliacion`) |
| `insumos` | sha256 del manifiesto y la lista **completa** `{nombre, tipo, sha256}`, que tiene que coincidir exactamente con el manifiesto |
| `ventana` | `id`, `inicio_H`, `ultima_formacion`, `semanas`, sha256 del archivo de ventana y los parámetros con que se calculó: `regla_E` (`TITULO_A3_1_5` o `TEXTO_N5`), `correcciones_fuera_de_listas` (`ADMITIDAS` o `NO_ADMITIDAS`), `eventos_omitidos` (`INCLUIDOS` o `EXCLUIDOS`), `alcance_R1` (`LITERAL` o `POR_CLASE`) y sha256 de la tabla de renombres |
| `decisiones` | `reapertura_E3`, `adenda_R` (`adoptada`, `reemplaza`, `anula`), `cierre_E3` (`revierte_s2_iv`, `dispensa_s4`), `continuidad_regla_1` (una regla general) más el caso de GTO→GFT, LUNA→LUNC y UST→USTC, `bifurcaciones` (BCC) y `evidencia_potencia` (sha256 del documento y si se acepta) |
| `politica_reintentos` | `id` (`SIN_REINTENTO`, `SOLO_PANEL` o `PANEL_Y_SIMULACION`) y `max_intentos` |
| `riesgos_residuales` | sha256 de la lista canónica de riesgos, `aceptados` (todos sus ids) y `rechazados: []` |
| `registro` | `cabeza_esperada` (`GENESIS` o el hash de la cabeza) e `intento_previo` (`null` o `{sha_objeto_error, etapa_max}`) |
| `emision` | `fecha_utc`, `caduca_utc`, `nonce` de 128 bits y `emisor` |

### C.3 Reglas de validación (todas tienen que cumplirse)

1. Los bytes son la forma canónica del objeto parseado. Cualquier otra cosa se rechaza: espacios, comentarios, claves repetidas, BOM o texto adicional.
2. El esquema es estricto: faltante, sobrante, tipo equivocado o enumerado desconocido se rechazan.
3. Cada hash tiene 64 caracteres hexadecimales en minúscula e **igual** al que calcula el lanzador sobre los bytes que efectivamente va a ejecutar o leer.
4. **Coherencia:**
   - `ventana` coincide con los metadatos que trae el propio archivo de ventana;
   - sin Adenda R no hay ventana A;
   - `politica_reintentos` es una de las que el código implementa;
   - `aceptados` contiene exactamente los ids de la lista;
   - `rechazados` no vacío es un rechazo.
5. **Estado:**
   - `cabeza_esperada` es igual a la cabeza actual;
   - el nonce no está en el registro;
   - la fecha está dentro de la vigencia;
   - la evaluación es la del almacén.
6. La firma es válida con la clave fijada.
7. Al aceptarse, se consume en el `ABIERTO`: el nonce y el sha256 de la autorización quedan registrados.

**Las negaciones, las citas y el texto libre no pueden pasar la validación**, porque no existe ningún campo de texto libre y los bytes tienen que ser exactamente la forma canónica.

---

## D. Metodología: reglas históricas, discrepancias y decisiones

### D.1 Las decisiones están anidadas

Cada decisión cambia qué preguntas quedan abiertas después:

1. **¿Reabrir E3 y adoptar la Adenda R?** Implica:
   - revertir el CIERRE §2 («no se relajó (iv)», «E3 no continúa»);
   - dispensar el CIERRE §4 (lista completa entre 2020-05 y 2026-05);
   - reemplazar (ii) por (ii′) y (iv) por (iv′) y dejar (iii) sin efecto.

   Si no se adopta, E3 sigue cerrado y lo demás no aplica.
2. **Si se adopta: ¿R1 literal o R1 por clase?** La R1 literal cuenta como «en alcance» a TRXDOWN, DOTUP, DOTDOWN y LINKUP, porque las listas fijas de F3 no los marcan como apalancados. Eso contradice su propio fundamento: §4.5 dice que los apalancados nunca son elegibles.
   - Con la R1 por clase, el inicio pasaría al 2021-02-22 y **la cuestión 158/160 desaparece**.
   - Pero la R1′ se redactó a las 19:46:53, después de P0 (19:44:41).
3. **Solo con la R1 literal: la regla de fecha efectiva.** Las tres variantes son:

| Variante | Qué supone | Inicio | Semanas |
|---|---|---|---|
| (A) Literal | E del título para todos los eventos (A3.1.5); sin correcciones fuera de las listas de A3.11; sin eventos agregados | 2023-05-01 | 160 |
| (B) | Solo se corrige DOTUP, el único evento de la muestra V-S3, aunque A3.6 no prevé corrección para V-S3 | 2023-05-15 | 158 |
| (C) Reparación | 4 correcciones (3 de ellas fuera de las listas) y 2 eventos que la extracción había omitido, agregados sin mecanismo congelado | 2023-05-15 | 158 |

   La contradicción de fondo es que A3.1.5 se presenta como «(N5)» pero dice lo contrario que N5.

### D.2 Condición contra la optimización

Si elegís la regla N5 (fecha del texto) o admitís correcciones, la regla se aplica a **todos** los eventos, no solo a los cuatro de abril de 2023. Eso exige una nueva pasada completa, cuyo resultado puede cambiar la ventana en cualquier sentido. Elegir una regla y aplicarla solo donde conviene es un sesgo.

**Contaminación ya existente.** Las longitudes de ventana bajo cada opción ya se conocen: 158, 160 y el inicio 2021-02-22. Los retornos no. Conviene que la decisión se funde en el texto de las reglas y quede escrita antes de recalcular nada.

### D.3 GTO→GFT, LUNA→LUNC y UST→USTC

Hay que separar cinco nociones de continuidad: identidad económica, ticker, par negociable, serie de datos y edad atribuible.

| Caso | Hechos verificados | Particularidad |
|---|---|---|
| GTO→GFT | El par GTO/USDT se retiró el 2022-11-28. El canje 1:1 se completó el 2023-02-08. GFT/USDT abrió el 2023-09-22: 298 días sin par USDT | Hay identidad económica, pero no continuidad del ticker, del par ni de la serie |
| LUNA→LUNC | 119 días sin par USDT | Además, el ticker LUNA se reutilizó para otro activo (regla 1R) |
| UST→USTC | 301 días sin par USDT | Está en la lista fija: sin efecto en el cálculo |

**Decisión tuya:** una **regla general**, por ejemplo «la regla 1 se aplica solo si el par de X estaba vigente en E y el hueco es menor de 30 días; si no, X sale e Y es un listado nuevo». Esa regla coincide con §2.2.3. La alternativa es la continuidad del activo, que exige una regla nueva. Lo que se decida se aplica a los tres casos y a cualquier caso futuro.

### D.4 Riesgos estadísticos residuales

- **Potencia sin script.** El documento de potencia supone que no hay autocorrelación adicional (incoherente con Newey–West, L = 4), está hecho para n = 160 y no incluye H2.
- **Punto ciego posterior al 2024-11-06.**
- **(iv′) es circular:** certifica a Vision con marcas del propio Vision.
- **Fragilidad:** una salida más sin evidencia en 2023 vuelve INVÁLIDA la ventana.
- **Recall de renombres no demostrado.**
- **Volumen de HIFI sin evaluar.**
- **Un solo agente en todo el trabajo.**

**Decisión tuya:** aceptar cada riesgo o exigir antes más evidencia, por ejemplo un script de potencia reproducible.

### D.5 Política de reintentos

| Política | Qué permite |
|---|---|
| (i) La implementada | Reintento después de un ERROR en `panel` o en `validez_previa` |
| (ii) Solo `panel` | Reintento solo antes de simular la estrategia |
| (iii) Ninguna | Un ERROR termina E3 sin resultado |

Ver el residuo de §A.6.

### D.6 Qué decisiones te corresponden

1. Reabrir E3, adoptar la Adenda R y dispensar el CIERRE §4.
2. R1 literal o R1 por clase.
3. Solo con la R1 literal:
   - la regla de fecha efectiva, de aplicación universal;
   - si se admiten correcciones fuera de las listas de A3.11;
   - si las discrepancias de V-S3 dan lugar a corrección;
   - si se admiten eventos omitidos.
4. La regla general de continuidad (D-1).
5. La política de reintentos (D-4).
6. La aceptación de los riesgos residuales y de la evidencia de potencia.

---

## E. Pruebas de aceptación

**Principio.** Las pruebas solas no prueban la integridad. Hace falta, además:
- un **verificador de invariantes independiente** del código bajo prueba, que lee solo el almacén;
- pruebas que **fallen contra el v3**: la prueba en rojo de cada defecto;
- mutantes elegidos por alguien que no sea el autor.

### E.1 Tabla de aceptación

**L-13: persistencia.**

| Aspecto | Contenido |
|---|---|
| Defecto original | INVALIDO→reintentable; EVALUADO destruido; registro distinto del disco; línea parcial; salida sin intento; registro borrado |
| Prueba que lo reproduce | El arnés de la revisión, escenarios B1–B3, E1–E7, I1–I5, K1, K2, L12 y C1, contra el v3. Tiene que fallar |
| Invariante | I-1 a I-10 |
| Prueba de la corrección | Ver detalle debajo de la tabla |
| Regresión | Ver detalle debajo de la tabla |
| Límites | La sincronización a disco se confía al sistema de archivos. Matar el proceso no equivale a un corte de energía. Se prueba en un solo tipo de sistema de archivos. L12 solo queda cubierto con un ancla externa |

*Prueba de la corrección:*
- **Matriz de fallos por operación × punto × tipo.**
  - Operaciones: `ABIERTO`, `ETAPA`, `DECISION`, objeto, `PUBLICADO`, ERROR, ancla y reconciliación.
  - Puntos: open, write parcial, flush, fsync, link, fsync del directorio y close.
  - Tipos: ENOSPC, EIO, SIGINT, SIGTERM, SIGKILL en un subproceso y línea parcial.
- **Comprobación tras cada caso:** el verificador evalúa los invariantes, compara los bytes de cada objeto contra los capturados al publicarlo y registra la decisión de una instancia nueva.
- **Secuencias aleatorias de fallos** con semilla registrada.
- **Determinismo** de la etapa de simulación.

*Regresión:*
- concurrencia;
- reconciliación: idempotencia, dos objetos terminales, cadena rota;
- discrepancia con el ancla;
- reintento por política: positivo, negativo y con cita equivocada;
- mutantes R2, R3, R4 y R8 de la revisión, y otros nuevos de un tercero.

**L-25: aislamiento.**

| Aspecto | Contenido |
|---|---|
| Defecto original | `INFORME_REPARACION` satisface al v2; el v1 casi; ningún registro compartido |
| Prueba que lo reproduce | El verificador estático de documentos como autorización y las pruebas de rechazo seguras |
| Invariante | En la zona de ejecución, el único punto de entrada es el lanzador. Ningún archivo tiene un hash revocado. Los datos solo existen en el almacén del v4 |
| Prueba de la corrección | Ver detalle debajo de la tabla |
| Regresión | Los manifiestos de la zona de archivo siguen validando, sin ningún byte cambiado |
| Límites | Como root no hay defensa contra un uso deliberado. Detectar ejecuciones previas fuera de las raíces conocidas depende de tu declaración |

*Prueba de la corrección:*
- la auditoría previa rechaza si se planta una copia del v1, del v2 o del v3 en la zona;
- el lanzador rechaza un orquestador con un byte cambiado;
- el v4 invocado directamente se niega a correr;
- se planta un `RESULTADO_E3.json` con la forma del v2, y el v4 se niega a correr;
- sin acta de revocación, se niega a correr;
- `ejecutar_E3_v2.py` no existe en la zona.

**L-17: autorización.**

| Aspecto | Contenido |
|---|---|
| Defecto original | Validación por subcadenas: se aceptan negaciones, citas y contradicciones |
| Prueba que lo reproduce | Las 10 variantes de la revisión, contra el v3. Hoy 9 se aceptan |
| Invariante | Se acepta si y solo si se cumplen las reglas 1 a 7 de §C.3 |
| Prueba de la corrección | Ver detalle debajo de la tabla |
| Regresión | Textos de autorización del v1, el v2 y el v3, rechazados por el v4. Generador de plantillas: su salida, con marcadores, no valida |
| Límites | La firma prueba que se tiene la clave, no la intención. El esquema garantiza falta de ambigüedad, no comprensión |

*Prueba de la corrección:* casos negativos, todos rechazados:
- las 10 variantes de la revisión;
- cada campo faltante, uno por prueba;
- un campo de más;
- una clave repetida;
- espacios o BOM;
- un tipo equivocado;
- un enumerado desconocido;
- cada hash alterado en un carácter, en mayúsculas o truncado;
- una ventana de 160 con un archivo de 158;
- `regla_E` distinta de la de los metadatos;
- sin Adenda R pero con ventana A;
- un riesgo rechazado o faltante;
- una política no implementada;
- una cabeza distinta;
- un nonce ya consumido;
- vencida;
- sin firma, con una firma inválida o con otra clave;
- de otra evaluación;
- un reintento sin intento previo o con un sha256 equivocado.

Fuzzing por mutación de una autorización válida.

El único caso positivo usa una **clave de prueba** que solo existe en el entorno de pruebas. El entorno real fija tu clave pública, así que esa autorización no sirve fuera de las pruebas.

**Metodología fijada en el código.**

| Aspecto | Contenido |
|---|---|
| Defecto original | El archivo de ventana se calculó con la tabla de 22 (L-10), sin los parámetros de las reglas |
| Prueba que lo reproduce | Comparar sus conteos con los de la tabla completa |
| Invariante | El archivo de ventana lleva sus parámetros, coincide con la autorización y se puede recalcular |
| Prueba de la corrección | Ver detalle debajo de la tabla |
| Regresión | — |
| Límites | (iv′) se recalcula con marcas de evidencia derivadas de los ZIP, que no se volvieron a derivar |

*Prueba de la corrección:*
- un tercero recalcula la ventana leyendo solo `estado`, con los parámetros decididos;
- si la regla elegida es N5, se cuentan todos los eventos cuya fecha de título difiere de la del texto, y tienen que figurar todos como releídos.

---

## Lista priorizada de cambios para el v4

**P0 (bloqueantes; en este orden de dependencia):**
1. Tus decisiones de §D.6 por escrito. Hasta entonces no se puede fijar la ventana.
2. Almacén de ejecución: registro encadenado, objetos inmutables, escritura anticipada de `ABIERTO`, `ETAPA` y `DECISION`, reconciliación y ancla externa (L-13 y L-12).
3. Autorización canónica y firmada, con consumo único y ligada a la cabeza del registro (L-17, N-1 y N-5).
4. Zona de ejecución aislada, lanzador con lista blanca, revocación del v1, el v2 y el v3, y auditoría previa (L-25 y N-2).
5. Archivo de ventana recalculado con la tabla completa y con sus parámetros como metadatos (L-10, N-6 y N-7).

**P1:**
6. Exposición por etapas registrada; la simulación deja de contar como «sin estadísticos» (L-11).
7. Orquestador ejecutado desde bytes verificados por el lanzador (L-14).
8. Contención de rutas con `realpath` y sin enlaces en ningún componente (L-15).
9. Sincronización del directorio después de publicar (L-16).
10. Comprobación de longitudes antes de `strict=True`, en la etapa de simulación (N-11).
11. Verificador independiente de invariantes, matriz de fallos, mutantes de un tercero y una prueba de integridad con los insumos reales separada y bien descrita (N-4).

**P2:**
12. Script de potencia reproducible para H1 y H2 (N-8).
13. Corrección documental de `MANIFIESTO_F3` (N-10).

---

## Conclusión

**DISEÑO BLOQUEADO POR CONTRADICCIONES METODOLÓGICAS.**

- Las secciones A, B, C y E se pueden revisar ya, de forma independiente.
- La especificación completa del v4 (ventana, metadatos y valores de las decisiones) espera tus decisiones de §D.6.
- Antes de implementar cualquier cosa, este diseño tiene que revisarlo una persona o un agente que no haya participado en la reparación ni en esta revisión.