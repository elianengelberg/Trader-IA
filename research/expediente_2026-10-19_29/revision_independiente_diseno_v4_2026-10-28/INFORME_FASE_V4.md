# E3 v4: revisión independiente y bloqueantes

**Fecha:** 2026-10-28 (UTC).

**Autor de este informe:** el mismo agente que escribió:
- la reparación;
- el v3;
- la revisión adversarial anterior;
- el diseño v4.

**Este informe no es independiente.** La parte independiente está en `revisor/`, y sus límites se describen en el §2.

**Restricciones cumplidas en esta fase:**
- No se ejecutó E3 y no se calcularon ni consultaron retornos, IC ni estadísticos de H1 o H2.
- No se emitieron, firmaron ni consumieron autorizaciones.
- No se modificaron v1, v2, v3, T-MULTI ni el repositorio.
- No se borró nada.
- Las únicas ejecuciones fueron prototipos aislados con datos inventados.

**Rutas.** Todas las rutas relativas parten de:

`/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/revision_independiente_diseno_v4_2026-10-28/`

---

## 1. Estado reconstruido

### 1.1 Hechos verificados en esta fase, con evidencia reproducible

| Hecho | Evidencia |
|---|---|
| Repositorio en la rama `claude/algo-trading-simulation-platform-ngf7xo`, HEAD `72ffae5d2698440c8f1afaff12e07bd8adde66fb`, árbol de trabajo limpio a las 20:13Z | `registro/git_fin.txt` |
| Huellas de los árboles congelados idénticas al inicio (19:27:55Z) y al final (20:13:59Z), e iguales a las del final de la revisión anterior. Árboles: E3, E3R, REP, RV, CB, PK, PKD y las páginas de CommonCrawl | `registro/huellas_inicio.txt` y `registro/huellas_fin.txt`, mismo comando |
| Informe adversarial anterior sin cambios: `c861d4a3…`. Su manifiesto `f02c44a1…` da 24/24 OK | Comprobado de nuevo a las 20:14Z |
| El diseño v4 nunca existió como archivo. Se extrajo literal de la línea 32735 del registro de la sesión: sha256 `c41a5a08…`, 28 194 bytes | `fuente/PROCEDENCIA_DISENO.json` |
| Los 11 insumos del revisor dan 11/11 OK | `INSUMOS.sha256`, rutas relativas al scratchpad |
| El manifiesto del revisor da **50/50 OK** | `revisor/MANIFEST_REVISOR.sha256`: 52 líneas, 2 de comentario |
| El manifiesto del verificador de la matriz da 25/25 OK | `verificacion_matriz/MANIFEST.sha256` |
| R-1 reproducido por mí: con numpy, `pthread_sigmask` no difiere SIGTERM (`exit=143`) ni SIGINT (`KeyboardInterrupt`, `exit=130`) | `verificacion_autor/registro/R1_senales_reejecucion.txt` |
| **Nuevo.** La corrección de R-1 (manejador con `signal.signal`) funciona con hilos: **8 de 8 casos**. Se probó con numpy (4 hilos) y con un hilo Python vivo, SIGINT y SIGTERM, señal interna y externa. Las 20 escrituras con `fsync` se completaron y la señal se volvió a lanzar después (−2 / −15). El revisor la había probado solo con 1 hilo | `verificacion_autor/prototipos/p2b_handler_con_hilos.py` y `verificacion_autor/registro/R1_handler_con_hilos.txt` |

### 1.2 Correcciones a mi trabajo anterior

| Qué | Corrección |
|---|---|
| **M-3 de la revisión adversarial anterior** (`INFORME_REVISION_ADVERSARIAL_E3H1H2.md`, l. 52–56, 227 y 282–290) | Exageré la contradicción. Afirmé que (A) era «la única aplicación mecánica» y que la V-S3 no admitía corrección. Omití `ADENDA_3` l. 89–91: la muestra V-S3 es una de las listas de A3.11, que «se resuelven» y cuya segunda pasada «es definitiva». La conclusión correcta: 158 semanas sale de dos lecturas con base textual, (b) y (c), y 160 exige leer la V-S3 solo como control. La contradicción entre A3.1.5 y N5 es real, pero afecta solo a 4 eventos |
| Matriz v1 (`825f141e…`, sin modificar) | Tenía 6 afirmaciones refutadas: V91, V51, V40/41, V81, V07 y la rama R1′. Corregidas en `metodologia/MATRIZ_METODOLOGICA_v2.md` (`9687027f…`) |
| Heurística `alcance_pasada_N5` | Marcó 30 eventos. La discrepancia real es de 4 |
| Evidencia de la revisión anterior, marcada por el revisor en la fase 2, §5 | **L12:** la conclusión se sostiene, pero el registro se borró a mano y ese paso no está en el arnés. **«L-25, rechazos 4/4»** y **L-15:** no hay salida guardada, así que pasan a **no verificables**. **Fuera del manifiesto:** `copia_A/`, `tmp_pytest_v3/`, `tmp_patch/`, `arnes_L15/` y `arnes_L25_rechazos/`. **Modelo de fallos:** solo de proceso. **Ctrl-C:** solo monohilo |

### 1.3 Afirmaciones anteriores no verificadas

Se las trata como no verificadas, no como falsas.

- **V03:** «ningún retorno se calculó». Es una negativa sobre todo el proceso.
- **V19:** el orden entre la congelación de la Adenda R y P0. Se infiere de registros del mismo entorno.
- **V42 y V60:** son contrafácticos.
- **V63:** el efecto de los omitidos sobre (iv′) **no se calculó**.
- **V70 y V84:** HIFI, las formaciones y el recall de renombres dependen de volúmenes que no se leyeron.
- **V92:** es un juicio.

Fuente: `verificacion_matriz/VERIFICACION_MATRIZ.md`, l. 120.

### 1.4 Hipótesis declaradas

- El texto extraído del registro de la sesión es el que viste. No lo pude contrastar con la copia del servidor.
- La salida estándar del proceso llega a un registro fuera del contenedor. Esto importa para la corrección de R-2 y **no está verificado**.
- La etapa de simulación es determinista con el entorno fijado (R-9). **No está verificado.**

### 1.5 Recursos inaccesibles o no intentados

| Recurso | Situación |
|---|---|
| Revisor humano o de otra organización | No hay en este entorno |
| Lista oficial de exclusiones posterior al 2024-11-06 | No está en el material local. No intenté obtenerla en esta fase |
| Dispositivo que falle o corte de energía real | No intenté montarlo. La durabilidad solo se probó con un modelo |
| Tu herramienta de firma y tus claves | No deben estar a mi alcance |
| `cryptography` en el venv | No está instalado |

---

## 2. Dictamen independiente

**Qué existe:**
- **Una revisión adversarial del diseño por un agente separado**, guardada en `revisor/`. Se hizo en dos fases:
  - Fase 1, a ciegas: `DICTAMEN_FASE1.md`, `77c71f75…`, fijado a las 19:59:28Z. Según su registro, abrió el material del autor a las 19:59:53Z.
  - Fase 2, contraste: `DICTAMEN_FASE2.md`, `30d540d7…`.
  - Hizo 6 prototipos aislados y dejó 24 registros.
- **Una verificación de hechos de la matriz metodológica** por otro agente separado: `verificacion_matriz/`. Revisó 92 afirmaciones: 78 confirmadas, 6 refutadas y 8 no verificables.

**Veredicto del revisor:**
- **«Aceptable con correcciones»** para §A (L-13), §C (L-17) y §E (pruebas). R-1 y R-2 son obligatorias antes de codificar.
- **§B no cierra L-25** tal como está escrito.
- La fase 2 no cambió el veredicto: reforzó R-1, R-2, R-4, R-7 y R-13 y confirmó que las remisiones del diseño a la revisión anterior existen.

**Límites de independencia:**
- Es otro modelo de la misma familia.
- Corre en el mismo contenedor, como root.
- Lo lancé yo, con un encargo que escribí yo (`ENCARGO_REVISOR.md`).
- Cumple tu criterio literal: no escribió la reparación, el v3 ni el diseño, y trabajó primero sin mis conclusiones.
- **No es independiente en sentido fuerte.** Es probable que comparta puntos ciegos conmigo, y el propio revisor lo declara.
- **No evaluó la metodología (§D).**
- La verificación de la matriz comprueba hechos y citas. **No revisa las decisiones.**

**Qué no existe:** **ninguna revisión humana independiente**, ni del diseño ni de la metodología.

---

## 3. Hallazgos adversariales por severidad

Todos los ids R-n son del revisor. El detalle completo está en `revisor/DICTAMEN_FASE1.md` §4, con evidencia, reproducción, impacto, corrección y prueba de cada uno. Los registros que cito están en `revisor/registro/`.

### Alta

**R-1 · Señales**

| Campo | Contenido |
|---|---|
| Problema | `pthread_sigmask` no difiere SIGINT ni SIGTERM si el proceso tiene hilos, y `import numpy` crea 3. Diseño, §A.3, l. 52 |
| Evidencia | `11_p2_senales_hilos.txt`. Con numpy: SIGTERM da `exit=143` dentro de la sección crítica y SIGINT da `KeyboardInterrupt` |
| Reproducción | `<venv python> -I -B revisor/prototipos/p2_senales_hilos.py numpy SIGTERM` |
| Impacto | La ventana DECISION→PUBLICADO queda tan expuesta como en el v3. Una prueba monohilo daría un falso positivo |
| Corrección | Usar `signal.signal` con un manejador que registre la señal sin lanzar, instalado en el hilo principal. Volver a lanzar la señal tras PUBLICADO. SIGKILL queda para la reconciliación |
| Regresión | La de P2 y P2b con numpy y con un hilo vivo, para ambas señales y ambos orígenes |
| Verificación | Hallazgo reproducido por mí. **Corrección probada por mí, 8/8** (§1.1). La prueba es del autor: falta que la repita alguien que no lo sea |

**R-2 · DECISION no durable**

| Campo | Contenido |
|---|---|
| Problema | Una DECISION no durable no se distingue de «nunca se decidió». La reconciliación da ABANDONADO(simulación), que bajo la política (i) es reintentable. I-7 depende de la política y no del diseño. Además, §A.3 contradice a §A.7 en el caso EIO |
| Evidencia | `10b_p1_registro_encadenado_v2.txt`, §4 y §4b |
| Reproducción | Modelo de disco: `ETAPA(simulacion)` durable, después DECISION(INVALIDO) con EIO en `fsync` o ENOSPC, corte y reconciliación |
| Impacto | Una comprobación de validez puede repetirse después de un INVALIDO. Es el mismo defecto que I1 e I5 del v3, por otra vía |
| Corrección del revisor | Anunciar la DECISION a un canal externo **antes** de escribirla. Ante cualquier `OSError` del almacén: no escribir nada más, anunciar y salir |
| Regresión | Disco sombra con cuatro modos de pérdida aplicados a INVALIDO y a EVALUADO. Resultado esperado: estado terminal o bloqueo, nunca reintentable |
| Nota del autor | Ver A-1 y A-2 abajo |

**R-4 · Alcance de L-25**

| Campo | Contenido |
|---|---|
| Problema | §B protege la zona nueva. La zona de archivo sigue ejecutable: hay código v1, v2 y v3, 757 series extraídas, intérprete y un documento que satisface al v2. Diseño l. 125, 132, 161 y 353 |
| Evidencia | `03_entorno.txt` §9 y `23_p6_l25_estatico.txt`: el v2 queda 3/3 satisfecho con `INFORME_REPARACION_E3H1H2.md` (l. 272, 208 y 209) |
| Reproducción | `p6_l25_estatico.py`. Es estático: no ejecuta el v2 |
| Impacto | Las pruebas de aceptación pasarían con L-25 abierto |
| Corrección | Retirar la zona de archivo (B.4) o aplicar el **sellado por renombre**: guardar los bytes en `archivo_sellado/<sha256>` con un manifiesto firmado. Así desaparecen las rutas por nombre que usan v1 y v2. **Cualquiera de las dos requiere tu orden expresa** |
| Regresión | Las rutas que espera el v2 no se resuelven, y los manifiestos siguen validando byte a byte |
| Verificación | No reproducido por mí. El revisor coincide con L-25 de la revisión anterior y lo verificó (T-10) |

### Media

| Id | Defecto | Evidencia | Corrección | Regresión |
|---|---|---|---|---|
| R-3 | El ancla es manual y la máquina no la puede comprobar, así que I-9 no se puede ejecutar | Diseño l. 30, 85 y 114 | Emitir la cabeza a un canal; el usuario la registra al cierre; el lanzador compara al arrancar | Ancla distinta: rechazo. Almacén recreado vacío: rechazo |
| R-5 | La raíz de confianza no se puede verificar desde el proceso: lanzador, intérprete, numpy y `.pth`, que se ejecutan aun con `-I`. La promesa «contra un agente» es excesiva | `03_entorno.txt` §2–8 | Huella del entorno en la autorización; sha del lanzador verificado fuera del proceso; reescribir la promesa como «inadvertida» | Un `.pth` plantado se rechaza. El lanzador alterado no se puede detectar desde el proceso: hay que declararlo |
| R-6 | La reconciliación está subespecificada: definición de cola, escritura partida de la propia reconciliación, hueco de ceros, `flock`, objeto terminal huérfano, `intento_previo` tras ABANDONADO | `10_…` (falla), `10b_…` y `10c_…` | Cola = ninguna línea completa válida después; marcador `0x1E`; `flock` con `LOCK_NB`; objeto huérfano lleva a bloqueo; citar la línea ABANDONADO | `10b` y `10c`, más un orquestador vivo y un objeto huérfano |
| R-7 | La comparación de cabeza tiene que hacerse dentro del bloqueo. Si el archivo se borra y se recrea, dos procesos quedan con bloqueo exclusivo | `13_…` §2 y `14b_…` (sin comparación dentro: 2 ABIERTO) | Releer dentro del `flock` y comparar `st_ino` | P5 en dos fases y borrado del archivo durante un intento |
| R-8 | `link()` deja el temporal como un segundo nombre escribible del objeto | `13_…` §3 | Temporal con nombre aleatorio, `unlink` y `fsync` del directorio. Verificar todos los objetos al arrancar | Matar el proceso entre `link` y `unlink` lleva a bloqueo |
| R-9 | El determinismo se invoca para INVALIDO y se niega para EVALUADO. Las condiciones de numpy, BLAS e hilos no están fijadas | `15_…` §b–d; venv con numpy 2.4.6 frente a 2.5.3 en el sistema | Declarar la política; `OPENBLAS_NUM_THREADS=1`; fijar el entorno por hash | `VALIDEZ_PREVIA` byte a byte en 2 procesos con 2 configuraciones de hilos |
| R-10 | «No hay texto libre» es falso: se acepta `\u0000`. El canonicalizador no está fijado y Ed25519 no está en el venv | `12_…` §2–4: 32 de 34 negativos rechazados | Gramática por campo; canonicalizador fijado en el código; biblioteca Ed25519 fijada por hash | Los 34 negativos, más los de gramática y una prueba de interoperabilidad con tu herramienta de firma |

### Baja

| Id | Defecto | Corrección |
|---|---|---|
| R-11 | La serialización de los objetos no está fijada (`NaN`, `default=float`) | Fijar los bytes antes de la DECISION y verificar con un parser estricto |
| R-12 | La lista negra por hash y la detección por nombre son cosméticas | Declarar que la protección real es la ausencia de estructura. Agregar la prueba del mutante de un byte |
| R-13 | Faltan pruebas, enumeradas en `DICTAMEN_FASE1` §3.5 (a)–(g), y la independencia de los mutantes y del verificador se presupone | Incorporarlas a §E y declarar la independencia limitada |

### Hallazgos del autor sobre la corrección de R-2

Son del autor, así que no son independientes.

- **A-1 · Media.** La salida estándar como canal externo no está demostrada.
  - El registro de la sesión vive en el mismo contenedor (`/root/.claude/…`) y root puede escribirlo. No verifiqué que se replique fuera.
  - Propuesta: una regla de cierre por defecto. Un intento con `ETAPA(simulacion)` durable y sin estado terminal queda **INDETERMINADO**, que es bloqueante. Solo un registro externo que **pruebe que no se anunció ninguna DECISION** habilita un reintento.
  - Así el canal pasa de ser necesario para la seguridad a ser solo una vía para desbloquear.
- **A-2 · Alta, de dependencia.** La gravedad de R-2 depende de la política de reintentos (D-7).
  - Bajo (iii), que es la lectura literal, ningún intento es reintentable. R-2 deja de ser un riesgo de repetición y pasa a ser solo de trazabilidad: un EVALUADO perdido termina E3 sin resultado.
  - **La decisión D-7 tiene que tomarse antes de cerrar §A.**
- **A-3 · Media.** Si la firma se verifica en un paso previo con `/usr/bin/python3`, que tiene `cryptography` pero numpy 2.5.3, aparece una ventana TOCTOU entre la verificación y la ejecución.
  - La alternativa es instalar `cryptography` fijado en el venv. Requiere red y tu autorización.

### Hallazgos de procedimiento sobre mi revisión anterior

Vienen de `DICTAMEN_FASE2` §5.

| Id | Hallazgo |
|---|---|
| P-1 | El procedimiento de L12 no se puede reproducir con los comandos documentados |
| P-2 | «L-25, rechazos 4/4» y L-15 no tienen salida guardada |
| P-3 | Hay 5 carpetas fuera del manifiesto, entre ellas `copia_A`, de la que depende T-9 |
| P-4 | El cierre seguro de E6 es accidental: se debe a una excepción no controlada después del `flock` |

Ninguno invalida una conclusión sobre el v3, pero bajan el nivel de evidencia de P-2 a «no verificable».

---

## 4. Contradicciones metodológicas

El detalle, con citas, está en `metodologia/MATRIZ_METODOLOGICA_v2.md`. Para la matriz no se consultó ningún resultado de rendimiento.

| # | Regla original | Lectura literal | Alternativas | Consecuencia | ¿Regla nueva? |
|---|---|---|---|---|---|
| 1 | CIERRE l. 15, 19 y 30; §8 del informe de ejecución, l. 225–239, que recomienda (a) o (e) y no relajar (iv) | E3 está cerrado. Para reabrirlo hacen falta tu autorización y la lista completa, que no existe después del 2024-11-06 | No reabrir; reabrir con la Adenda R; reabrir con una adenda nueva con salvaguardas; obtener la lista por (a)–(d) | La Adenda R relaja (iv) a (iv′), que es circular, y se escribió conociendo que M0 fallaba | Sí: una dispensa o adenda firmada |
| 2 | R1 (ADENDA_R l. 22–26) frente a R1′ (`86c8fd0b…`) | R1 literal | R1′ | **Hecho:** R1′ se congeló a las 19:46:57Z del 26/10, después de P0, por motivos de potencia, y **su autor la retiró** (INFORME_DECISION l. 22 y 33). Con R1′ y la segunda pasada, el inicio quedaría fijado por (i) y (iv′): **no está calculado** | Elegir R1′ sería adoptar una regla posterior a P0 |
| 3 | N5 (NOTAS l. 16) frente a A3.1.5 (ADENDA_3 l. 18–19); la v3 prevalece (§0.2) | Afecta a 4 eventos de apalancados: título 2023-04-27, cese 2023-05-09/10/11 | (I) fecha del título, salvo las listas de A3.11; (II) N5 universal | Con R1 literal, las dos dan 2023-05-15 si la V-S3 puede corregir E | Una cláusula de precedencia para casos futuros |
| 4 | A3.11 l. 89–91 (V-S3 en las listas, «definitivo»); A3.6 l. 62 (V-S3 «a mano») | — | (a) la V-S3 es solo control: 160 semanas; (b) se resuelven las listas de A3.11, incluida DOTUP: 158; (c) N5 universal: 158 | (b) y (c) tienen base textual. (a) exige una lectura restrictiva | Sí, si se elige (a) |
| 5 | v3 §2.3 l. 106–107: «todas las exclusiones» | Universo completo | (a) ningún omitido; (b) búsqueda acotada a ≥ 2023-04-28, que es lo que se hizo; (c) búsqueda completa | Los omitidos anteriores (GTO, BTCST, SRM, TRIBE, KEY) no mueven (ii′). **Su efecto sobre (iv′) no está calculado** | Un procedimiento de búsqueda declarado |
| 6 | §2.2.3, §2.2.4 y §2.2.5; ADENDA_1 regla 1 | Conflicto interno de la v3 | (a) listado nuevo; (b) continuidad pese al hueco | Cambia la elegibilidad de GFT dentro de A. No está recalculado | Sí, una regla general |
| 7 | v3 l. 73 y §3.3 l. 175 y 180–183; ADENDA_R l. 61; PLAN l. 35 | **(iii): sin reintento** | (i) reintento tras ERROR en panel o validez; (ii) solo en panel | Bajo (iii), R-2 deja de ser un riesgo de repetición (A-2) | (i) y (ii) necesitan una regla que diga que un intento fallido no es una «ejecución» |
| 8 | v3 §7.1–7.2: no fija una potencia mínima | Se informa la potencia | Aceptar la potencia o fijar un umbral **antes** de cualquier resultado | Con 158 semanas: P(RESPALDADA) ≤ 0,13–0,17 suponiendo un exceso de 10 %/año, y ≤ 0,26–0,40 con 20 %/año (los dos son supuestos de la v3 §7.2, no estimaciones). H1, IC 0,02, α 0,025: 0,35–0,55. Margen de 2 semanas. Con una salida más sin evidencia en 2023, A pasa a INVÁLIDA (V83) | Un umbral sería una regla nueva |

**Alcance de una pasada completa.** Tiene que fijarse antes de correr nada.
- **N5:** los 47 eventos de `vs3`. Ya los leyó una vez el mismo agente, sin un protocolo de lectura congelado.
- **Segunda lectura:** debería abarcar los 47, no solo los que mueven la ventana, para que la regla se aplique de forma universal.
- **Omitidos, alternativa (c):** todas las páginas de exclusión del período de (i) en adelante, con el criterio escrito antes de buscar.

---

## 5. Matriz de pruebas

**Leyenda:**
- **Tipo de fallo:** **P** = matar o interrumpir el proceso; **D** = pérdida de persistencia (bytes escritos que no llegan al disco); **A** = adversario o agente.
- **«¿Falla en v3?»** indica si el escenario equivalente reproduce el defecto en el v3. Las pruebas de mecanismos nuevos usan como contraparte el escenario del v3 que reproduce el mismo efecto.

| Defecto | Prueba | Tipo | ¿Falla en v3? | ¿Circular? | Mutantes que debe matar | ¿Demostrable aquí? | Estado |
|---|---|---|---|---|---|---|---|
| L-13: INVALIDO pasa a ERROR reintentable | I1, I5 | P | Sí: `L13_resultados.json`, verificado por hash | No, si el verificador solo lee el almacén | Escribir ERROR después de DECISION | Sí | Evidencia del v3 vigente; falta la prueba del v4 |
| L-13: EVALUADO perdido | E1, E4, E7 | P | Sí | Ídem | Objeto antes de DECISION | Sí | Ídem |
| L-13: registro distinto del disco | E2, I2 | P | Sí | Ídem | Objeto con hash distinto del que cita la DECISION | Sí | Ídem |
| L-13: línea parcial | E6, `10b`, `10c` | P y D | Sí, con cierre seguro accidental | No | Reconciliación que trunca; lector «tolerante» | Sí | Prototipo del revisor OK |
| L-13: salida sin intento | K1, K2 | P | Sí | No | `mkdir` antes de ABIERTO | Sí | Ídem |
| L-13 / L-12: registro borrado | L12 | A | Sí, en la conclusión; el procedimiento es manual (P-1) | No | Ancla ignorada | Solo con un ancla que la máquina pueda leer (R-3) | **Pendiente:** hay que integrar el paso de borrado al arnés |
| R-1: señales con hilos | P2 y P2b | P | El diferido del v4 tal como está escrito falla. El v3 no difiere | **Sí, si es monohilo:** tiene que correr con numpy | Volver a `pthread_sigmask` | Sí | **Corrección OK, 8/8, prueba del autor** |
| R-2: DECISION no durable | Disco sombra con 4 modos de pérdida | **D** | El equivalente del v3 es I1/I5. El diseño tal como está falla en el modelo | No | Reconciliación que da ABANDONADO tras ETAPA(simulacion) | **Solo como modelo.** Un EIO real o un corte de energía no se probaron | Pendiente; depende de D-7 |
| R-6: reconciliación | `10b` y `10c`, más un orquestador vivo y un objeto huérfano | P y D | Sin reconciliación en el v3 (no aplica) | No | Cola sin marcador; reconciliación sin `flock` | Sí | Prototipo parcial |
| R-7: carrera de apertura | P5 en dos fases, borrado y recreación | A y P | C1 del v3 cubre solo el bloqueo retenido | No | Comparar la cabeza fuera del bloqueo | Sí | Prototipo OK |
| R-8: temporal y `link` | Matar entre `link` y `unlink` | P | No aplica | No | Temporal determinista | Sí | Pendiente |
| L-25: documento que satisface al v2 | P6 estático | A | Sí, 3/3 | No | — | Solo por lectura; **no se ejecuta el v2** | Verificado (estático) |
| L-25: zona de archivo ejecutable | Rutas del v2 sin resolver tras el sellado | A | Sí: hoy se resuelven | **Sí, si solo se prueba la zona nueva** (l. 353 del diseño) | Sellado incompleto | Sí, con datos sintéticos | **Bloqueado por D-9** |
| L-17: texto como autorización | 10 variantes | A | Sí, 9/10 aceptadas | No | Validar por `in texto` | Sí | Evidencia del v3 vigente |
| R-10: canonicalización | 34 negativos + gramática + interoperabilidad | A | No aplica | **La interoperabilidad necesita tu herramienta de firma** | Aceptar NUL, `1.0` o claves repetidas | Los negativos sí; la interoperabilidad no | 32/34 en el prototipo; faltan las gramáticas |
| R-5: raíz de confianza | `.pth` plantado, intérprete alterado | A | No aplica | **El lanzador no se puede verificar a sí mismo:** el procedimiento es externo | No comprobar los `.pth` | Parcial | Pendiente |
| T-9: suite que no detecta defectos | Mutantes | — | Sí: 47 pasan; R2, R3, R4 y R8 sobreviven | **La suite del v3 es circular** (`monkeypatch` sobre el mismo código) | Los de R-13 | Sí | Hace falta un verificador externo y mutantes elegidos por otro agente |
| R-9: determinismo | 2 procesos × 2 configuraciones de hilos | — | No aplica | No | — | Sí, pero **usaría datos reales de E3**: requiere tu autorización | Pendiente |

**Lo que no es demostrable en este contenedor:**
- la durabilidad real tras un corte de energía;
- la semántica de `fsync` con errores de dispositivo;
- que el ancla externa exista y se consulte;
- la integridad del lanzador desde dentro del proceso;
- independencia de mutantes y verificador más allá de «otro agente de la misma familia».

---

## 6. Plan P0/P1/P2

**P0: requisito para congelar la especificación y empezar la implementación aislada.**

| Id | Evidencia disponible | Evidencia faltante | Acción | Criterio de cierre | Depende de | Aprueba |
|---|---|---|---|---|---|---|
| P0-1 | Matriz v2 y verificación de hechos | Tus decisiones | Decidir D-1 a D-8 por escrito | Documento de decisiones con sha256, congelado **antes** de recalcular la ventana | — | Vos |
| P0-2 | R-4, P6 y `03_entorno` §9 | Tu orden | Decidir D-9: sellado por renombre, retiro, o aceptar L-25 abierto | Prueba sintética: las rutas del v2 no se resuelven y los manifiestos validan 100 % | — | Vos |
| P0-3 | R-1 (corrección 8/8) y R-2 (modelo) | La regla de R-2 elegida según D-7; una segunda revisión de la corrección | Escribir el diseño v4.1: §A.3 con manejador, §A.4 con INDETERMINADO o anuncio previo, coherencia entre §A.3 y §A.7 | El revisor (u otro) aprueba R-1 y R-2 en el v4.1, con regresión en disco sombra | P0-1 (D-7) | Revisor, y vos |
| P0-4 | Matriz v2 y `resoluciones_manuales.json` | Una segunda lectura de los 47 eventos con un protocolo congelado | Congelar el protocolo de lectura; un agente sin contexto lee los 47 eventos a ciegas respecto de la ventana | Acuerdo en todos los eventos que fijan E; los desacuerdos se resuelven por una regla escrita | P0-1 (D-3, D-4) | Vos |
| P0-5 | El archivo de ventana del v3 (tabla de 22, sin parámetros) | La ventana con las reglas decididas | Recalcular la ventana con los parámetros registrados, en aislamiento y sin retornos. **Antes, comprobar si el cálculo lee volúmenes:** si los lee, requiere tu autorización | Archivo de ventana con hash, parámetros y procedimiento, reproducido por un tercero | P0-1, P0-4 | Vos |
| P0-6 | R-13 y la matriz de pruebas (§5) | Pruebas faltantes y mutantes elegidos por otro agente | Completar los criterios de aceptación de §E | Cada defecto tiene una prueba no circular, un mutante y su tipo de fallo (P, D o A) | P0-3 | Revisor |
| P0-7 | §2 | — | Decidir D-10: ¿hace falta una revisión humana? | Decisión escrita | — | Vos |

**P1: correcciones de especificación antes de codificar, que no dependen de tus decisiones.**

| Id | Acción | Criterio de cierre |
|---|---|---|
| P1-1 | R-6: regla de cola, marcador `0x1E`, `flock` y fila de objeto huérfano | `10b` y `10c` más los dos casos nuevos en verde |
| P1-2 | R-7: comparación de cabeza dentro del bloqueo y comprobación de `st_ino` | P5 en dos fases: 1 ABIERTO; borrado: rechazo |
| P1-3 | R-8: temporal aleatorio y verificación de todos los objetos | Inyección entre `link` y `unlink`: bloqueo |
| P1-4 | R-10: gramáticas, canonicalizador fijado y biblioteca Ed25519 (decidir A-3) | 34 negativos más los de gramática; interoperabilidad con tu herramienta |
| P1-5 | R-5: huella del entorno; promesa reescrita como «inadvertida»; verificación externa del lanzador | `.pth` plantado: rechazo; procedimiento externo escrito |
| P1-6 | R-3: ancla que la máquina pueda leer (mecanismo según D-11) | Ancla distinta o almacén vacío: rechazo |
| P1-7 | R-9 y R-11: política de determinismo y serialización fijada | Verificador estricto de objetos |

**P2: después, o fuera del camino crítico.**

| Id | Acción | Criterio de cierre |
|---|---|---|
| P2-1 | Durabilidad real (dispositivo que falla o VM con corte) si el entorno lo permite | Ejecutar las pruebas D con un fallo real, o declararlas no probadas en el informe de aceptación |
| P2-2 | Sellar en un manifiesto nuevo, **sin borrar nada**, las carpetas que quedaron fuera del manifiesto (P-3); agregar el paso de borrado de L12 al arnés (P-1) | Manifiesto nuevo verificado |
| P2-3 | Lista de exclusiones posterior al 2024-11-06 (opciones a–d del §8) | Solo si querés extender E3; no cambia lo anterior |
| P2-4 | R-12: reescribir lo que se afirma de la lista negra y agregar el mutante de un byte | Prueba agregada |

**No se repite:**
- la evidencia del v3 (L13, L17, L25 estático, T-9), verificada por hash;
- R-1, reproducido.

**Quedan pendientes:** P-2 (salidas no guardadas) y todo lo marcado como modelo.

---

## 7. Decisiones que necesito que tomes

Ninguna se puede justificar por el rendimiento, y no se consultó ninguno.

| Id | Decisión | Opciones | Qué dice la evidencia (sin recomendación por resultados) |
|---|---|---|---|
| D-1 | Reabrir E3, adoptar la Adenda R y dispensar el CIERRE §4 | No / sí / sí con una adenda nueva | El §8 recomendó no relajar (iv). (iv′) es circular. La Adenda R se escribió conociendo que M0 fallaba |
| D-2 | R1 literal o R1′ | R1 / R1′ | R1′ es posterior a P0, motivada por potencia y retirada por su autor |
| D-3 | Precedencia entre N5 y A3.1.5 | (I) / (II) | Con R1 literal, no cambia el inicio. Hace falta para casos futuros |
| D-4 | ¿La V-S3 puede corregir E? | (a) 160 / (b) 158 / (c) 158 | (b) y (c) tienen base en A3.11 l. 89–91 |
| D-5 | Eventos omitidos | (a) / (b) / (c) | (b) es lo que se hizo. Su efecto sobre (iv′) no está calculado |
| D-6 | Continuidad: GTO, LUNA, UST | (a) listado nuevo / (b) continuidad | Conflicto interno de la v3. Hay que fijar una regla general |
| D-7 | Reintentos | (i) / (ii) / **(iii), la lectura literal** | Fija la gravedad de R-2 (A-2) |
| D-8 | Potencia y riesgos residuales | Aceptar / fijar un umbral antes / no ejecutar | P(RESPALDADA) ≤ 0,13–0,17 con 10 %/año y ≤ 0,26–0,40 con 20 %/año; margen de 2 semanas; fragilidad V83; punto ciego posterior al 2024-11-06 |
| D-9 | Zona de archivo (L-25) | Sellado por renombre / retiro / L-25 abierto declarado | Las dos primeras modifican rutas históricas y **requieren tu orden expresa**. El sellado preserva los bytes |
| D-10 | Revisión humana independiente | Sí / suficiente con el agente separado | El agente actual es de la misma familia, en el mismo contenedor y lanzado por el autor |
| D-11 | Mecanismo del ancla externa | Commit tuyo / nota tuya / otro | Un commit requiere tu autorización. La máquina tiene que poder leerlo (R-3) |

---

## 8. Estado final: **BLOQUEADO**

| Condición para implementar | Estado |
|---|---|
| 1. Una revisión independiente real | **Parcial.** Hay un agente separado de la misma familia; no hay revisión humana (D-10) |
| 2. Corrección justificada de los defectos críticos | R-1: **corrección probada** (por el autor). R-2: propuesta, depende de D-7. R-4: depende de D-9 |
| 3. Decisiones metodológicas documentadas | **Ninguna tomada** (D-1 a D-8) |
| 4. Ventana congelada con sus parámetros | **No.** Hay que recalcularla después de P0-1 y P0-4 |
| 5. Criterios de aceptación completos | **No** (P0-6) |

La matriz metodológica (`metodologia/MATRIZ_METODOLOGICA_v2.md`) está lista para que tomes las decisiones D-1 a D-11. Es el primer paso para desbloquear.

**E3 no está listo para ejecutarse.**
