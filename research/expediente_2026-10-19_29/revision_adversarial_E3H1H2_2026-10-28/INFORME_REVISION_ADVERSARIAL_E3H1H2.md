# Revisión adversarial de E3-H1/H2 (orquestador v3)

**Fecha:** 2026-10-28.
**Revisor:** Claude, el mismo agente.
**Carpeta:** `revision_adversarial_E3H1H2_2026-10-28/`.

## 0. Independencia, alcance y niveles de evidencia

**Esta revisión no es independiente.**
- La hizo el mismo agente, en la misma sesión, que escribió la reparación, el v3, la «revisión» del 2026-10-26, el cierre y el paquete.
- Se hizo en modo adversarial, intentando refutar, pero **no satisface el requisito de revisión independiente** que fijó el usuario.
- Todos los hallazgos son reproducibles con los scripts de `arnes/`, para que un tercero los confirme o los refute.

**Niveles de evidencia** que se usan en todo el informe:

| Sigla | Nivel | Significado |
|---|---|---|
| **VD** | Verificado directamente | Inspeccioné el artefacto o ejecuté la prueba y registré el resultado |
| **R** | Reproducido | Volví a ejecutar el procedimiento en un entorno documentado (§E) |
| **I** | Inferido | Se desprende de la evidencia, pero no lo verifiqué directamente |
| **NR** | No resuelto | Falta evidencia, hay una contradicción o no pude hacer la comprobación de forma segura |

**Qué no hice:**
- No ejecuté E3-H1/H2 ni llamé a ningún orquestador en modo `real` con insumos reales y una autorización.
- No creé ninguna autorización que el sistema pueda aceptar. Solo usé frases y hashes de prueba con sal, rechazables por el código real.
- No leí arreglos de precio ni de volumen.
- No abrí el paquete de datos: solo calculé su sha256.
- Para renombres y ventana leí `estado` y `simbolo` de las series originales, con una guarda.
- Para las huellas de los árboles se leyeron bytes de series y ZIP solo para hashearlos, sin decodificarlos.
- No modifiqué el repositorio, los árboles congelados ni artefactos de otras misiones (§E.5).
- No corregí ningún defecto.

---

## A. Resumen ejecutivo

### Hallazgos críticos

1. **L-13 confirmado: la integridad del resultado terminal depende de que la escritura del registro no falle.** (R, 18 escenarios con fallos inyectados)
   - Si la anotación de **INVALIDO** en el registro falla, por una falla transitoria de disco o por un **Ctrl-C** en el momento justo, el INVALIDO se sobrescribe con un ERROR «sin estadísticos» (escenarios I1 e I5). Una instancia nueva **acepta una segunda ejecución completa** con una autorización nueva. Esto contradice «no hay otra ejecución después de INVALIDO».
   - Si falla la anotación de **EVALUADO**, el resultado calculado **se sobrescribe y se pierde** (E1, E4 y E7).
   - Si la línea se escribe y luego se informa un error, el registro cita un sha256 que **ya no existe en disco** (E2 e I2).
2. **L-25 confirmado y agravado: un documento congelado ya es una autorización válida para el v2.** (VD estático; I en cuanto a la ejecución, que no corrí)
   - `reparacion_E3H1H2_2026-10-26/INFORME_REPARACION_E3H1H2.md` (sha256 `9b26ecb5…`) contiene, completos, los tres elementos que exige el v2: la frase (línea 272), el sha256 del v2 (línea 208) y el de su manifiesto (línea 209).
   - Pasado como archivo de autorización a `ejecutar_E3_v2.py real`, superaría el control. Una reimplementación estática exacta de la condición da 3 de 3.
   - El v2 no tiene registro de intentos ni las defensas del v3. Ninguna versión bloquea a las otras.
3. **L-17 confirmado y agravado: el control de autorización del v3 es una búsqueda de subcadenas.** (R)
   - Acepta autorizaciones que **niegan** la frase («NO AUTORIZO…»).
   - Acepta autorizaciones que **citan las frases para rechazarlas**.
   - Acepta autorizaciones que contradicen D-3, D-4 o D-5.
   - No exige ningún pronunciamiento sobre D-3, D-4 ni D-5.
4. **M-3 tiene una contradicción no resuelta en las reglas congeladas.** (VD documental)
   - A3.1.5 fija E = «la primera fecha del título», con la etiqueta «(N5)».
   - N5 define E como el día en que cesa la negociación «según el texto».
   - La reparación corrigió la fecha de 3 eventos (TRXDOWN, DOTDOWN y LINKUP) que **no estaban en ninguna lista de revisión de A3.11**. Solo DOTUP estaba en la muestra V-S3, y A3.6 no prevé corrección para V-S3.
   - La reparación agregó 2 eventos que la extracción había omitido, sin un mecanismo congelado para hacerlo.
   - **Que la ventana tenga 158 o 160 semanas no lo determinan las reglas congeladas.**
5. **La R1 literal de la Adenda R contradice su propio fundamento.** (VD)
   - El fundamento de la R1 es que los apalancados quedan fuera de alcance porque «nunca son elegibles».
   - Pero las listas fijas de F3 marcan como apalancados solo 2 o 3 tokens por semana. TRXDOWN, DOTUP, DOTDOWN y LINKUP no figuran.
   - En consecuencia, cuentan como fallas «en alcance» y **fijan el inicio de la ventana A**, aunque §4.5 los excluye de todo cálculo.

### Riesgos que impiden continuar

- Los tres defectos técnicos (1, 2 y 3) comprometen la integridad del resultado o permiten ejecuciones por rutas que eluden los controles obligatorios.
- Hay contradicciones metodológicas abiertas (4 y 5) y otras de M-1.

### Limitaciones de esta auditoría

- **Falta de independencia** (§0).
- **No hay hashes de referencia del usuario.** El encargo no incluye los SHA-256 completos; el único ancla es el `SHA256SUMS` del mismo agente.
- **Los artefactos de E3 no están en el repositorio:** su integridad descansa en hashes producidos por el mismo agente.
- **No corrí** las suites del v2 ni los 15 mutantes del autor (incluyen pruebas que calculan estadísticos), **ni** el criterio (d) de volumen.
- **Mi búsqueda de renombres** solo detecta tickers entre paréntesis.

### Decisión final

**NO APTO — REQUIERE CORRECCIONES TÉCNICAS** y **NO APTO — REQUIERE DECISIONES METODOLÓGICAS**.

Se detiene la recomendación de autorización (criterio 9 del encargo). En §F.4 está lo que haría falta para reanudar.

---

## B. Matriz técnica T-1…T-10

| Punto | Requisito | Evidencia primaria | Prueba realizada | Resultado | Limitaciones | Veredicto |
|---|---|---|---|---|---|---|
| **T-1** Integridad | La evidencia es la generada y los hashes citados coinciden | Tarballs; `MANIFEST_PAQUETE`; árboles originales; manifiestos congelados de E3 | Ver detalle debajo de la tabla | Todo coincide; diferencias solo de forma | Detalle debajo de la tabla | **APROBADO** con limitaciones |
| **T-2** Diff v2→v3 | Solo los cambios declarados; cálculo idéntico | v2 `01fc9344…`, v3 `c089cc6a…`, `DIFF_v2_v3.diff` | Ver detalle debajo de la tabla | Cálculo idéntico salvo `strict=True` | Detalle debajo de la tabla | **APROBADO** (con riesgo N-11) |
| **T-3** Renombres como extracción | Citas en el cuerpo; r, E y apertura bien leídas; sin faltantes | Tabla, 8.028 páginas, `cc_clasificar.py` (`effe8a2e…`) | Ver detalle debajo de la tabla | Citas en el cuerpo: 60/107 mecánicamente; muestra manual correcta; sin faltantes hallados | Detalle debajo de la tabla | **NO VERIFICADO** (parcial) |
| **T-4** Ruta real | Orden: autorización → registro → insumos → ventana → módulos → mapeos → `mkdir`; nada antes de `mkdir` consume | `modo_real`, l. 828–894 | Lectura y escenarios K1, K2 y L-17 (centinela antes de leer insumos) | El orden se cumple. Antes de `mkdir` ningún rechazo crea la salida, aunque el registro puede quedar creado vacío | Ver L-13 (K1 y K2) y L-14 | **APROBADO** con observaciones |
| **T-5** Reintentos (implementación) | Ninguna segunda ejecución después de EVALUADO o INVALIDO; los ERROR se manejan según la política | `permitir_intento`, `resultado_*`, `Intentos` | 18 escenarios con fallos inyectados (§E.2) y 2 mutantes propios | **Falla:** INVALIDO→ERROR reintentable (I1, I5); EVALUADO destruido (E1, E4, E7); registro inconsistente (E2, I2); sin pruebas negativas de reintento | — | **RECHAZADO** |
| **T-6** Sin precios | Los scripts del cierre leen solo `estado` y `simbolo` | 3 scripts de `verificaciones/` y `tabla/` | Ver detalle debajo de la tabla | Se cumple en los scripts del cierre | Detalle debajo de la tabla | **APROBADO** (alcance: cierre) |
| **T-7** Ventana A | Inicio 2023-05-15, 158/158, (iv′) = 2018 | `ventana_A_pasada2.json` (`dcbd80ab…`) | Ver detalle debajo de la tabla | Coincide; con inicio 2023-05-01 serían 160 | Detalle debajo de la tabla | **APROBADO** aritméticamente; **NR** metodológicamente (M-3) |
| **T-8** Mapeos sobre la actividad | Mapeos coherentes con la actividad real | `mapeos_adenda1_completa.json`, series (`estado`) | Reimplementación propia para los 23 mapeos de regla 1, leyendo solo `estado` y `simbolo` | 23 de 23 coherentes: X inactivo, Y empieza después, hueco < 30 días, iguales a `chequeo_actividad` | No recalculé reglas 2 y 1R, los criterios (a) y (b) en A, HIFI ni el criterio (d) | **APROBADO** (parcial) |
| **T-9** Pruebas y mutación | Las suites prueban lo que dicen; los mutantes relevantes mueren | Suite del v3, `mutantes.py` | Ver detalle debajo de la tabla | Suite verde con defectos confirmados (L-13 y L-17); 4 de 7 mutantes propios sobreviven | Detalle debajo de la tabla | **RECHAZADO** (cobertura insuficiente) |
| **T-10** Higiene | Ninguna autorización existente; frases solo en el código | Todo el paquete y las copias | Ver detalle debajo de la tabla | Para el v3, sin documentos-autorización; **para el v2, sí** | — | **RECHAZADO** (por la ruta del v2) |

**Detalle de T-1.**
- *Pruebas realizadas:*
  - sha256 completo de los tarballs: A `83b565d7ce5ad27df67f2f23d7aaddd7f1811e6cc20915f99262da02675f47e3` y B `0562b919b7e318abd34e753e04247bb6305c1405ad7ca5894858e320c69f8d1d`;
  - listado del tarball A antes de extraerlo: sin rutas absolutas ni `..`, y un único enlace relativo;
  - extracción en una copia aislada;
  - `MANIFEST_PAQUETE`: 400 de 400 y ningún archivo fuera de la lista;
  - comparación archivo por archivo con los **originales**: E3R y el cierre sin diferencias; en la reparación y la revisión, solo un directorio vacío no copiado y el enlace, que pasó de absoluto a relativo; los 80 archivos de E3 incluidos, idénticos;
  - manifiestos propios de E3: `SHA256SUMS` 8 de 8; `CIERRE_E3_MANIFIESTO` 171 de 171 entradas verificadas (excluí 6 líneas que contienen `.npz` o series); `MANIFIESTO_F3` 38 de 38 archivos;
  - hash del conjunto de páginas: coincide con las dos recetas (`f12afb98…` y `43c90bfa…`);
  - índice de Common Crawl: `01b36a79…`;
  - huellas iguales al inicio y al final;
  - Git: `72ffae5d…`, sin cambios.
- *Resultado:* coincide. La única diferencia es documental: el comentario de `MANIFIESTO_F3` describe su receta de forma inexacta (N-10).
- *Limitaciones:*
  - el usuario no entregó hashes; el ancla es del mismo agente;
  - el tarball B no se abrió;
  - no se verificaron los ZIP de Vision (son datos de mercado);
  - E3 no está en el repositorio y no hay rama `main`: la rama por defecto es la de Claude, en `72ffae5d…`, según la API de GitHub.

**Detalle de T-2.**
- *Pruebas realizadas:*
  - `patch -o` del diff del autor sobre el v2: el resultado tiene **exactamente** el sha256 del v3;
  - diff propio;
  - el bloque `validez_previa`…`modo_sintetico` (341 líneas en cada versión) solo difiere en `strict=True` (`contribuciones`);
  - revisión de los fragmentos restantes: corresponden a C7–C13.
- *Limitaciones:*
  - no regeneré el v3 con `generar_v3.py`, porque exige leer bytes de las series;
  - `strict=True` puede convertir en ERROR, después de los estadísticos y sin reintento posible, una diferencia de longitudes que antes se truncaba (N-11). No es verificable sin datos reales.

**Detalle de T-3.**
- *Pruebas realizadas:*
  - las 107 citas, contra el **cuerpo** que delimita la regla congelada;
  - lectura manual de GTO (retiro y canje), MFT→HIFI, LUNA y BNX;
  - búsqueda propia con otro método.
- *Resultado:*
  - las 107 citas están en sus páginas;
  - **solo 60 caen dentro del cuerpo**: en 32 páginas el título archivado es basura CSS y en el resto es solo «Announcement», así que A3.1.1 no puede delimitar el cuerpo;
  - la muestra manual es correcta;
  - la búsqueda propia halló 81 pares, 55 no vistos por el autor; revisé los 8 sospechosos y son ruido (airdrops, barra lateral, etiquetas). No encontré renombres faltantes.
- *Limitaciones:*
  - el script del autor solo verifica la página, no el cuerpo (N-3);
  - mi patrón exige tickers entre paréntesis;
  - no revisé los 117 pares uno por uno.

**Detalle de T-6.**
- *Pruebas realizadas:* lectura de las guardas `SoloEstado`, búsqueda de accesos a O, H, L, C, QV y `ratio_precio`, y mi propia ejecución con una guarda (`arreglos_leidos = ['estado', 'simbolo']`).
- *Limitaciones:*
  - `ventana_tabla_completa.py` usa los conteos de elegibles de `estructural.json` (F3), que se calcularon en su momento con volumen;
  - las series se leen enteras para hashearlas (L-9).

**Detalle de T-7.**
- *Pruebas realizadas:* aritmética propia de los lunes, (ii′) desde las fallas en alcance y (iv′) recalculado.
- *Limitaciones:* (iv′) se recalculó con las **marcas de evidencia del autor**. No volví a derivar SUSPENSION ni COLA_CERO, porque exigiría leer los ZIP.

**Detalle de T-9.**
- *Pruebas realizadas:*
  - suite del v3 en la copia, sin el paquete de datos y con un plugin que **bloquea todo cálculo**: 47 passed y 4 bloqueadas a propósito;
  - 7 mutantes propios: 3 detectados y 4 sobrevivientes (reutilizar una autorización, reintentar sin citar el ERROR, escritura no atómica y registro de EVALUADO antes del resultado).
- *Resultado:*
  - `test_exigidas…` **no** compara contra los insumos reales; el `02` y el `00` lo describen mal (N-4);
  - la suite pasa en verde aunque los defectos de L-13 y L-17 están confirmados.
- *Limitaciones:* no corrí las suites del v2 ni los 15 mutantes del autor.

**Detalle de T-10.**
- *Pruebas realizadas:* reimplementación estática de las condiciones de autorización del v1, el v2 y el v3, aplicada a cada archivo.
- *Resultado:*
  - ningún archivo satisface al v3;
  - **`INFORME_REPARACION` satisface al v2** (y lo mismo su copia en la revisión);
  - `PLAN_EJECUCION_UNICA_E3R.md` contiene todo lo que exige el v1, salvo que nombra las dos ventanas.

---

## C. Matriz de riesgos L-1…L-25 y hallazgos nuevos

**Severidad:** Crítica, Alta, Media o Baja.

| Riesgo | Afirmación original | Evidencia encontrada | Intento de refutación | Conclusión | Severidad | Acción requerida |
|---|---|---|---|---|---|---|
| **L-1** | La clasificación de los 117 pares es manual | `construir_tabla.py` (`CLASE`, `AIRDROP`, `PARTE_DE`) | Búsqueda propia: nada nuevo | Confirmado (VD). Es juicio del autor | Media | Revisión humana de los 117 |
| **L-2** | El recall de la búsqueda de renombres es limitado | 32 páginas con título basura; títulos «Announcement» | Búsqueda propia: no halló faltantes | Confirmado: el recall no está demostrado (I) | Media | Documentar; aceptarlo o no es decisión |
| **L-3** | E de certeza media en COCOS, TVK y MFT | Actividad desde `estado`: E = primer día de Y | Coherente con la actividad | Confirmado (R). Convención general, no excepción | Baja | — |
| **L-4** | E de los apalancados no sale del texto | `construir_tabla.py` §3: E = último día activo + 1 | — | Confirmado (VD). Sin efecto en el cálculo; sí en (ii′) y (iv′) con la R1 literal | Baja | — |
| **L-5** | La fecha del renombre de LUNA no está archivada | Cita «has since been renamed»; hueco 119 frente a 120 | — | Confirmado (VD). Inconsistencia menor | Baja | — |
| **L-6** | BCC, RGT, BETH y USDSB quedan fuera de la regla 1 | Tabla | — | Confirmado (VD). Criterio general razonado (un único Y no preexistente) | Baja | Decisión D-2 |
| **L-7** | El criterio (d) no se evaluó para HIFI ni GFT | Prohibido leer QV | — | Confirmado (NR) | Media | Decisión del usuario |
| **L-8** | No hay fuente para exclusiones posteriores al 2024-11-06 | Archivo hasta 2024-11-06 | — | Confirmado (NR) | Alta (interpretación) | M-1 y M-4 |
| **L-9** | «No se leyeron precios» significa «no se decodificaron» | Hash de bytes completos | — | Confirmado (VD) | Baja | Redacción precisa |
| **L-10** | El archivo de ventana fijado se calculó con la tabla de 22 | 2021: 10/9; 2022: 35/31; 2023: 19/18 | — | Confirmado (VD). El v3 solo controla `veredicto` e `inicio_H` | Media | Fijar en un v4 el archivo coherente con la tabla completa |
| **L-11** | `validez_previa` cuenta como «sin estadísticos» | `motor.simular` × 6 en memoria; escribe `VALIDEZ_PREVIA.json` | Mutante R1 detectado | Confirmado (VD) | Media | Decisión D-4 |
| **L-12** | La unicidad depende del registro | Escenario L12: con el registro borrado, una nueva instancia hace otra ejecución completa | — | **Confirmado (R)** | **Alta** | Registro fuera del árbol, anclado o firmado |
| **L-13** | Fallo del registro después de un resultado terminal | 18 escenarios (§E.2) | Intenté refutarlo con una muerte del proceso: E3 e I3 bloquean y conservan el archivo | **Confirmado (R)**: I1/I5 (INVALIDO→reintentable), E1/E4/E7 (EVALUADO destruido), E2/I2 (registro inconsistente), E6 (línea parcial → excepción no controlada, bloqueo), K1/K2 (salida sin INICIADO → otra ejecución) | **Crítica** | Corrección en un v4 (§F.4) |
| **L-14** | Ventana entre la compilación y `SHA_PROPIO` | l. 57–58: lectura separada de `__file__` | No ejecutado (requiere una carrera) | Confirmado estáticamente (I) | Baja | Ejecutar desde bytes verificados por un lanzador |
| **L-15** | Enlaces simbólicos en directorios padre | Prueba: `enlaces/sub_enlazado/a.json` se lee | — | **Confirmado (R)**. El contenido igual se verifica por hash | Baja | `realpath` contra raíces permitidas |
| **L-16** | Atomicidad por construcción | Sin `fsync` del directorio; mutante R3 sobrevive | — | Confirmado (VD y R) | Media | `fsync` del directorio y prueba de escritura no atómica |
| **L-17** | Faltan las decisiones D-3, D-4 y D-5 | 10 variantes de autorización (§E.3) | — | **Confirmado y agravado (R)**: acepta negaciones, citas para rechazar y contradicciones | **Crítica** | Autorización estructurada (§F.4) |
| **L-18** | Las pruebas parchean hashes y frases | `test_exigidas` no toca los insumos reales | — | Confirmado. Además, la descripción es inexacta (N-4) | Media | Prueba de integridad real separada y documentada |
| **L-19** | Los mutantes los eligió el autor | 4 de 7 mutantes propios sobreviven | — | **Confirmado (R)** | Alta | Pruebas negativas de la política |
| **L-20** | La suite del v2 escribe la frase real | `test_orquestador_v2.py` l. 193 y 298 | — | Confirmado (VD) | Baja | Correrla siempre neutralizada |
| **L-21** | Un solo agente | Esta revisión es del mismo agente | — | Confirmado | **Alta** | Revisor independiente real |
| **L-22** | Dependencias no verificadas | Ver M-6 | — | Parcialmente resuelto: potencia NR; F3, archivos sí y descarga NR; P0 inferido | Media | Ver M-6 |
| **L-23** | Evidencia que no viaja en el paquete | ZIP, índices y registros solo por hash | — | Confirmado | Media | Conservación externa |
| **L-24** | El v3 se generó con plantillas | `patch` reproduce el v3 exacto | No corrí `generar_v3.py` | Diff verificado (R); generador **NR** | Baja | — |
| **L-25** | El v1 y el v2 son ejecutables | Rechazos seguros corridos; análisis estático de los documentos | Busqué si algún documento ya era una autorización | **Confirmado y agravado**: `INFORME_REPARACION` satisface al v2 (VD estático); ningún registro compartido; mismo nombre de salida en el v2 y el v3 | **Crítica** | Aislamiento (§F.4) |

**Hallazgos nuevos** (no figuraban en `05`):

| Id | Hallazgo | Nivel | Severidad |
|---|---|---|---|
| N-1 | Autorización por subcadenas: negaciones y citas aceptadas (ver L-17) | R | Crítica |
| N-2 | Documento congelado = autorización válida del v2 (ver L-25) | VD | Crítica |
| N-3 | Solo 60 de 107 citas son atribuibles mecánicamente al cuerpo (A3.1.1); el script del autor no lo comprueba | R | Media |
| N-4 | `test_exigidas` no verifica los insumos reales. El `00` y el `02` lo describen mal, y las suites **no** necesitan el paquete de datos | VD | Media |
| N-5 | La política de reintentos no tiene pruebas negativas (mutantes R2 y R8). La «autorización nueva» se cumple con cambiar un byte | R | Alta |
| N-6 | M-3: correcciones de E fuera de las listas de A3.11; A3.6 no prevé corrección para V-S3; eventos agregados sin mecanismo congelado; conflicto entre A3.1.5 y N5 | VD | Alta (metodológica) |
| N-7 | La R1 literal contradice su fundamento: apalancados no listados por F3 fijan el inicio de A | VD | Alta (metodológica) |
| N-8 | El archivo de potencia no tiene script. Supone «sin autocorrelación adicional» (inconsistente con NW, L = 4), es solo para H1 y usa n = 160 | VD | Media |
| N-9 | No hay rama `main`. E3 no está versionado: el ancla de integridad la produjo el mismo agente | VD | Media |
| N-10 | El comentario de `MANIFIESTO_F3` describe mal su receta de hash | VD | Baja |
| N-11 | `strict=True` cambia el modo de falla del cálculo: un truncamiento pasa a ser un ERROR no reintentable | VD | Media |

---

## D. Matriz metodológica M-1…M-7

| | Regla histórica | Alternativas | Consecuencias | Evidencia disponible | Solo puede resolverlo el usuario |
|---|---|---|---|---|---|
| **M-1 Adenda R** | Ver detalle debajo de la tabla | (1) No adoptar R: E3 cerrado. (2) Adoptar R con R1 literal. (3) Adoptar R con R1 por clase (R1′). (4) Adoptar R con salvaguardas preespecificadas | Ver detalle debajo de la tabla | Ver detalle debajo de la tabla | Ver detalle debajo de la tabla |
| **M-2 GTO→GFT** | Adenda 1, regla 1: «el listado **vigente** de X termina en E; Y lo continúa». §2.2.3: 30 días sin actividad = listado nuevo | (a) Lectura literal: salida de GTO y listado nuevo de GFT. (b) Continuidad del activo, con una regla nueva | Ver detalle debajo de la tabla | VD: GTO/USDT retirado el 2022-11-28 03:00 (cuerpo de la página); canje 1:1 completado el 2023-02-08; GFT/USDT el 2023-09-22 (298 días) | Adoptar (a) o (b), y escribir la aclaración |
| **M-3 158/160** | §4.11 (ii): semana siguiente a la última falla. A3.1.5: E = primera fecha del título «(N5)». N5: E = cese de la negociación según el texto. A3.11: solo se corrigen los casos de sus listas. A3.6 V-S3: control sin regla de corrección | Ver detalle debajo de la tabla | Reproducibilidad: (A) es la única aplicación mecánica de la extracción congelada. Potencia: la diferencia es de 2 semanas (~1,3 %), despreciable. Comparabilidad: (B) y (C) dependen de lecturas manuales hechas en la reparación | VD: resoluciones, `vs3` (solo DOTUP `muestra_pasada1: True`), eventos omitidos, aritmética de 158 y 160 (R) | **Contradicción entre A3.1.5 y N5:** el pronunciamiento queda detenido. Hace falta una decisión expresa sobre la regla de E y sobre si se admiten correcciones fuera de las listas |
| **M-4 Riesgos residuales** | v3 §1 y §7.3: «evidencia histórica con contaminación declarada» | Ejecutar con salvaguardas o no ejecutar | Ver detalle debajo de la tabla | §A, §B, §C | Aceptar o no cada riesgo |
| **M-5 Reintentos** | C11 (implementada) | (i) La implementada. (ii) Solo después de un ERROR en «panel». (iii) Ninguno | Ver detalle debajo de la tabla | R (§E.2) | Elegir (i), (ii) o (iii) |
| **M-6 Potencia, F3 y P0** | — | — | Ver detalle debajo de la tabla | Ver detalle debajo de la tabla | Si acepta la evidencia de potencia y de P0 o exige más |
| **M-7 Renombres e inclusión** | Adenda 1 (reglas 1–4), A3.7 | — | Ver detalle debajo de la tabla | T-3 y T-8 | Revisar y aceptar los 117 y la convención de E |

**Detalle de M-1 (Adenda R).**
- *Reglas históricas afectadas:*
  - v3 §4.11 (i)–(iv);
  - CIERRE §2: «No se relajó la regla (iv)… E3 no continúa», por decisión expresa;
  - CIERRE §4: para reabrir, «haría falta una lista completa y verificable… 2020-05 a 2026-05».
- *Qué cambia exactamente la Adenda R:*
  - reemplaza (ii) por (ii′), es decir, fallas **en alcance**;
  - reemplaza (iv) por (iv′), es decir, evidencia interna: ANUNCIO, SUSPENSION o COLA_CERO;
  - deja (iii) sin efecto;
  - redefine la contabilidad de §2.3 por alcance (R1).
- *Consecuencias:*
  - (1): sin prueba;
  - (2): ventana A de 158 semanas y margen de 2;
  - (3): inicio 2021-02-22 (VD, `P0_resultado_R1prima.json`), pero es posterior a ver P0;
  - con R hay contradicción formal con el CIERRE §2 y §4: requiere una decisión expresa de reapertura y dispensa.
  - **(iv′) es circular:** certifica a Vision con marcas de Vision. Una truncación sin marca es indetectable.
  - **(ii′) es ciega** después del 2024-11-06.
  - **R1 literal es incoherente con su fundamento** (N-7).
- *Evidencia disponible:*
  - VD: textos de R, CIERRE y v3;
  - VD: listas fijas de F3;
  - VD: P0 y R1′;
  - I: la congelación es anterior a P0 (registro de la sesión, M-6).
- *Solo puede resolverlo el usuario:*
  - reabrir E3;
  - adoptar R o no;
  - R1 literal o R1′, con la incoherencia a la vista;
  - dispensar el CIERRE §4.

**Detalle de M-2 (GTO→GFT).** Hay que distinguir cinco nociones de continuidad:

| Noción | ¿Hay continuidad? |
|---|---|
| Identidad económica | **Sí**: el mismo proyecto, canje 1:1 |
| Ticker | No |
| Par negociable | No: ningún par USDT durante 298 días |
| Serie de datos | No |
| Edad atribuible | Según §2.2.3, se reinicia |

**Recomendación general**, para que la decida el usuario:
- La regla 1 se aplica solo si el par de X estaba **vigente en E** y el hueco entre el último día de X y el primero de Y es **< 30 días**. Esa es la frontera de §2.2.3.
- En cualquier otro caso, X sale (§4.10) e Y es un listado nuevo.
- La regla es aplicable sin conocer resultados y coincide con la opción (a).
- Conviene escribirla como aclaración, porque el texto congelado no define «vigente».

**Implicaciones de la recomendación:**
- **LUNA→LUNC:** hueco de 119 días, más la reutilización del ticker (regla 1R). Con la regla: listado nuevo.
- **UST→USTC:** 301 días. Está en la lista fija (§4.5): sin efecto.

**Detalle de M-3 (158 frente a 160).** Las tres variantes posibles:

| Variante | Qué supone | Inicio | Semanas |
|---|---|---|---|
| (A) Literal | E del título para todos los eventos; sin correcciones fuera de las listas; sin eventos agregados | 2023-05-01 | 160 |
| (B) | Corrección solo del caso de la muestra V-S3 (DOTUP, 2023-05-10) | 2023-05-15 | 158 |
| (C) Reparación | 4 correcciones y 2 eventos agregados | 2023-05-15 | 158 |

**Detalle de M-4 (riesgos residuales).** Hay dos tipos de riesgo.

*Riesgos que **invalidan** la ejecución:*
- L-13, L-25 y L-17;
- las contradicciones abiertas de M-1 y M-3;
- N-7.

*Riesgos que la **permiten pero limitan la interpretación**:*
- el punto ciego posterior al 2024-11-06;
- la circularidad de (iv′);
- la fragilidad (una salida más sin evidencia en 2023 → INVÁLIDO);
- la potencia baja (N-8);
- el recall de renombres;
- los cambios de símbolo sin anuncio (regla 3);
- el volumen de HIFI;
- el sesgo de selección: el universo es lo que Vision conserva;
- la dependencia entre las marcas evaluadas y el método: (iv′) usa marcas de la misma fuente cuya supervivencia evalúa.

**Detalle de M-5 (reintentos).**
- *Consecuencias:*
  - la (i) tiene hoy defectos (L-13) y simula la estrategia antes del ERROR;
  - la (ii) o la (iii) son más coherentes con «ejecución única».
- *Evidencia a conservar siempre:*
  - el RESULTADO original, sin sobrescribir;
  - el traceback;
  - el registro completo;
  - los hashes del entorno y de la autorización;
  - toda la cadena de intentos citada en la autorización siguiente.

**Detalle de M-6 (potencia, historia de F3 y P0).** Para cada afirmación que depende de informes anteriores:

- **Potencia 0,35–0,56:**
  - `P0d_potencia_H1_segun_ventana.txt` **no tiene script ni insumos**;
  - es analítica, supone desvío semanal de 0,12–0,16 y «sin autocorrelación adicional»;
  - es para n = 160 y solo para H1. **NR.**
  - *Falta:* el script, la justificación del desvío y la potencia de H2.
- **Historia de F3:**
  - VD: `MANIFIESTO_F3` (38 archivos y conjunto de páginas) y el CIERRE (series `6506fb03…` iguales a las de hoy);
  - **NR:** la cadena de descarga, porque los ZIP no se verificaron (son datos de mercado) y los registros de descarga no viajan.
- **P0 antes de congelar R:**
  - el registro de la sesión (marcas de tiempo del sistema) no muestra ningún cálculo con marcas de R antes de las 19:43:09Z;
  - la congelación es de las 19:43:13Z y P0 de las 19:44:38Z;
  - **I:** el registro lo genera el mismo entorno. Hubo conocimiento previo de conteos agregados, declarado en R §5.
  - *Falta:* un sello externo, como un commit o una marca de tiempo de un tercero.

**Detalle de M-7 (renombres e inclusión).**
- *Consecuencias:*
  - las reglas son coherentes y aplicables sin resultados;
  - los casos de certeza media siguen una **convención general**, no excepciones: E = fecha del anuncio de finalización = primer día de Y;
  - el cálculo usa la actividad, no E, así que el efecto es bajo;
  - las bifurcaciones y fusiones se excluyen por un criterio general;
  - el apalancado tiene E por convención y sin efecto;
  - reproducibilidad: la tabla se reproduce byte a byte según el autor; los 117 requieren revisión humana.
- *Evidencia disponible:* T-3 y T-8.

---

## E. Registro de reproducción

### E.1 Entorno y estado

| Elemento | Valor |
|---|---|
| Sistema | Linux 6.18.44 |
| Python | 3.11.17 |
| numpy | 2.4.6 |
| pytest | 9.1.1 |
| GNU patch | 2.7.6 |
| Copia aislada | `copia_A/` (tarball A extraído; huella del árbol estable durante toda la revisión: `2e36820851aa799a…`) |
| Huellas al inicio y al final | `registro/huellas_inicio_revisor.txt` y `registro/huellas_fin_revisor.txt`. **Idénticas:** E3 `4909ef95…`, E3R `649a72f5…`, reparación `9bcacf49…`, revisión `a6fb7f6b…`, cierre `e495daa2…`, páginas `f12afb98…` |
| Git | HEAD `72ffae5d2698440c8f1afaff12e07bd8adde66fb`, 0 cambios, índice `37490035…` |
| Directorios del scratchpad | 240 al inicio y al final; ninguno borrado |

### E.2 L-13: inyección de fallos

- **Script:** `arnes/arnes_L13.py` (`8694b150…`).
- **Resultados:** `registro/L13_resultados.json` (`5f13ef0f…`).
- **Directorio de trabajo:** `arnes_L13_SINTETICO_SIN_DATOS_SIN_CALCULO/`.

**Comando** (cada escenario en un proceso nuevo):

```
python -B -I arnes/arnes_L13.py correr   <copia_A>/…/ejecutar_E3_v3.py <base>/<escenario> <escenario>
python -B -I arnes/arnes_L13.py observar <copia_A>/…/ejecutar_E3_v3.py <base>/<escenario>
```

| Escenario | RESULTADO en disco | Registro | Instancia nueva |
|---|---|---|---|
| B1 EVALUADO sin fallo | EVALUADO | INICIADO, EVALUADO | Rechazada |
| B2 INVALIDO sin fallo | INVALIDO | INICIADO, INVALIDO | Rechazada |
| B3 ERROR en panel | ERROR (panel) | INICIADO, ERROR | Permitida, por diseño |
| **E1** falla la anotación de EVALUADO | **ERROR (escritura): el EVALUADO se perdió** | INICIADO, ERROR | Rechazada |
| **E2** se anota EVALUADO y luego falla | ERROR | INICIADO, EVALUADO (sha **≠ disco**), ERROR | Rechazada |
| E3 muere antes de la anotación de EVALUADO | EVALUADO, intacto | INICIADO | Rechazada (revisión manual) |
| **E4** falla la escritura del RESULTADO | ERROR (escritura) | INICIADO, ERROR | Rechazada |
| E5 fallan las anotaciones de EVALUADO y de ERROR | ERROR | INICIADO | Rechazada |
| E6 línea parcial y muerte | EVALUADO | INICIADO + línea ilegible | **Excepción no controlada** (fail-closed) |
| **E7** Ctrl-C al anotar EVALUADO | **ERROR (escritura)** | INICIADO, ERROR | Rechazada |
| **I1** falla la anotación de INVALIDO | **ERROR (validez_previa, sin estadísticos)** | INICIADO, ERROR | **PERMITIDA: segunda ejecución completa** |
| **I2** se anota INVALIDO y luego falla | ERROR | INICIADO, INVALIDO (sha **≠ disco**), ERROR | Rechazada |
| I3 muere antes de la anotación de INVALIDO | INVALIDO, intacto | INICIADO | Rechazada |
| I4 fallan las anotaciones de INVALIDO y de ERROR | ERROR | INICIADO | Rechazada |
| **I5** Ctrl-C al anotar INVALIDO | **ERROR (validez_previa, sin estadísticos)** | INICIADO, ERROR | **PERMITIDA** |
| **K1** muere entre `mkdir` y INICIADO | Salida vacía | Vacío | **Permitida** (otra salida) |
| **K2** falla la anotación de INICIADO | Salida vacía | Vacío | **Permitida** |
| **L12** registro borrado después de EVALUADO | EVALUADO | (borrado) | **PERMITIDA** |
| C1 concurrencia (bloqueo retenido) | — | — | Rechazada: «otra ejecución en curso» |

### E.3 L-17: variantes de autorización

- **Script:** `arnes/arnes_L17.py` (`e131ff7f…`).
- **Resultados:** `registro/L17_resultados.json` (`b259d66b…`).

| Variante | Resultado |
|---|---|
| Control completo | Aceptado |
| Sin D-1 | Rechazado |
| Negación de la frase | **Aceptado** |
| Negación de las decisiones | **Aceptado** |
| Frases citadas para rechazarlas | **Aceptado** |
| D-3 = 160 | **Aceptado** |
| D-4 sin reintentos | **Aceptado** |
| Riesgos inaceptables | **Aceptado** |
| Sin mención de D-3, D-4 ni D-5 | **Aceptado** |
| Otra ventana declarada | **Aceptado** (el código corre igual la A) |

### E.4 Resto de las reproducciones

| Qué | Script | Resultado | Archivo |
|---|---|---|---|
| L-25 rechazos seguros (v1 y v2, autorización inexistente o de prueba, E3 inexistente) | En línea | 4 de 4 rechazos; ninguna salida creada | — |
| L-25 documentos como autorización | `arnes/L25_documentos_como_autorizacion.py` (`2f1e6cb9…`) | `INFORME_REPARACION` = autorización válida del v2 | `registro/L25_documentos_como_autorizacion.json` (`09be24d5…`) |
| T-2 diff | `diff -u` + `patch -o` | v3 exacto | `registro/diff_v2_v3_revisor.diff` (`fe1f7a97…`) |
| T-3 citas en el cuerpo | `arnes/T3_citas_en_cuerpo.py` (`17a258ef…`) | 107 en la página; 60 en el cuerpo | `registro/T3_citas_en_cuerpo.json` (`e722dbf0…`) |
| T-3 búsqueda propia | `arnes/T3_busqueda_propia.py` (`23c67d07…`) | 81 pares, 55 no vistos, 0 renombres reales en los revisados | `registro/T3_busqueda_propia.json` (`5e3c3ae4…`) |
| T-7 y T-8 | `arnes/T7_T8_estado.py` (`95d867f2…`) | 158 y 160; (iv′) = 2018; 23 de 23 mapeos coherentes; `arreglos_leidos = ['estado', 'simbolo']` | `registro/T7_T8_estado.json` (`b5ebbbcf…`) |
| T-9 suite del v3 (`PYTHONPATH=arnes python -B -m pytest -p guarda_revisor -p no:cacheprovider …`) | `arnes/guarda_revisor.py` (`063f682e…`) | 47 passed y 4 bloqueadas | `registro/suite_v3_con_guarda.txt` (`a3c81d06…`) |
| T-9 mutantes propios | `arnes/mutantes_revisor.py` (`90a1065f…`) | 3 detectados y 4 sobrevivientes. R5 es un control sin cambios y no cuenta | `registro/mutantes_revisor.txt` (`83fff8ee…`) |
| L-15 enlaces | En línea | El padre enlazado se acepta; los finales, rechazados | — |
| M-6 orden de R y P0 | Lectura del registro de la sesión | Sin cálculos con marcas de R antes de las 19:43:09Z | — |

### E.5 Lo que no se ejecutó, y por qué

| Qué | Motivo |
|---|---|
| Suites del v2 y los 15 mutantes del autor | Incluyen pruebas que calculan estadísticos, aunque sea con datos sintéticos |
| `generar_v3.py`, `ventana_tabla_completa.py` y `mapeos_sobre_estado_real.py` del autor | Leen bytes de las series para hashearlas; los sustituí por comprobaciones propias con `estado` |
| Extracción del paquete de datos | Prohibida en la revisión técnica |
| Cualquier modo `real` con una autorización válida | Prohibido |

**Archivos de prueba que contienen «EVALUADO» o «INVALIDO»:** están dentro de `arnes_L13_SINTETICO_SIN_DATOS_SIN_CALCULO/`. Solo contienen `STUB_SIN_CALCULO` y se crearon con autorizaciones de prueba **no aceptables** por el v3 real. **No son resultados de E3.**

---

## F. Dictámenes (separados; ninguno es una autorización)

### F.1 Dictamen técnico: **RECHAZADO**

El código y sus controles **no** son suficientemente correctos para considerar una ejecución restringida:
- **L-13:** compromete la integridad del resultado y permite repetir después de un INVALIDO.
- **L-25:** hay una ruta (v2) que elude los controles obligatorios, con una autorización válida ya presente en un documento congelado.
- **L-17:** el control de autorización acepta textos que niegan o contradicen lo que autorizan.

### F.2 Dictamen metodológico: **NO APROBADO**

**Contradicciones no resueltas:**
1. La Adenda R frente al CIERRE §2 y §4: requiere una decisión expresa.
2. A3.1.5 frente a N5, más las correcciones fuera de las listas de A3.11 y los eventos agregados sin mecanismo. 158 o 160 no está determinado.
3. La R1 literal frente a su fundamento.

**Decisiones pendientes del usuario:**
- D-A, D-B y D-C;
- R1 o R1′;
- D-1, con la aclaración de «vigente»;
- D-3, con su nueva formulación (regla de E y correcciones fuera de lista);
- D-4;
- D-5;
- aceptación de la evidencia de potencia.

### F.3 Dictamen sobre la autorización: **NO**

No hay evidencia suficiente para que el usuario evalúe autorizar una única ejecución restringida a la ventana A. Se detiene la recomendación hasta cumplir §F.4 y obtener una revisión **independiente** real.

### F.4 Qué haría falta para reanudar (no implementado)

**L-13: corregir en un v4 con hash nuevo.**
- *Correcciones:*
  - el resultado terminal es de **escritura única**: nunca se sobrescribe un `RESULTADO_E3.json` existente;
  - INVALIDO y EVALUADO se deciden y publican fuera del `except BaseException`;
  - si falla el registro después de un terminal, el intento queda abierto (revisión manual) y **no** se convierte en ERROR;
  - el registro tiene líneas con suma de verificación y un rechazo controlado ante una línea parcial;
  - el registro vive fuera del árbol del código, anclado en un registro externo de solo agregado o firmado;
  - se rechaza cualquier salida de cualquier versión previa.
- *Pruebas:*
  - los 18 escenarios de §E.2 como regresión, verificando los bytes del RESULTADO;
  - el Ctrl-C en cada anotación;
  - las pruebas negativas de reintento (mutantes R2, R4 y R8).

**L-25: aislamiento sin tocar la historia.**
- *Correcciones:*
  - ejecutar solo desde un árbol nuevo que contenga únicamente el v4 y los insumos verificados, sin el código del v1 ni del v2;
  - dejar un acta de revocación del v1 y del v2;
  - que el v4 se niegue a correr si existe cualquier `RESULTADO_E3*.json` o `REGISTRO_EJECUCION.json` de versiones previas.
- *Prueba:* que una ejecución del v2 previa bloquee al v4.

**L-17: autorización estructurada.**
- *Correcciones:*
  - un JSON con campos explícitos: versión, sha256 del código y del manifiesto, D-A/B/C, D-1, D-3 (que debe coincidir con la ventana fijada), D-4, D-5 (con el hash de la lista de riesgos aceptados), la fecha y un nonce;
  - validación **exacta** del esquema completo, sin búsqueda de subcadenas;
  - un archivo que contenga cualquier otra cosa se rechaza.
- *Prueba:* las 10 variantes de §E.3 tienen que dar rechazo, salvo el control.

**Metodología:** que el usuario resuelva por escrito las tres contradicciones de §F.2 antes de cualquier v4, para que la ventana fijada en el código refleje esa decisión.

**Revisión independiente:** un revisor que no sea este agente.

---

## Decisión final

**NO APTO — REQUIERE CORRECCIONES TÉCNICAS** · **NO APTO — REQUIERE DECISIONES METODOLÓGICAS**

La decisión de autorizar cualquier ejecución corresponde exclusivamente al usuario.
