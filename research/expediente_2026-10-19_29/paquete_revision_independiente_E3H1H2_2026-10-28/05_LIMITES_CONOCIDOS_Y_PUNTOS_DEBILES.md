# Límites conocidos y puntos débiles

**Qué es.** Lo que el autor sabe, o sospecha, que es débil en su propio trabajo. Sirve para orientar la revisión hacia los lugares más dudosos.

**Qué no es:**
- no es una lista exhaustiva;
- no es una prueba de que lo que no figura acá esté bien.

**Rutas:** las mismas de `02` y `03` (`EV`, `CB`, `REP`, `E3X`).

**Para cada ítem se indica:**
- de dónde sale;
- qué comprobación o decisión toca (T-n o M-n);
- si el autor estima que mueve la ventana A.

El revisor debe confirmar o refutar esa estimación, no adoptarla.

---

## A. Tabla de renombres (T-3)

### L-1 · Clasificación manual de los 117 pares del barrido

- **Dónde:** `CB/tabla/construir_tabla.py`, sección «clasificación de los 117 pares», con:
  - los diccionarios `CLASE`, `AIRDROP`, `CONVERSION_AL_RETIRAR` y `PARTE_DE`;
  - reglas por patrón (`OLD$`, `V1$` y una lista de símbolos).
- **Qué garantiza el script:** aborta si queda un par sin clase.
- **Qué no garantiza:** que cada clase sea correcta. Eso depende del juicio del autor.
- **Ejemplo:** `PHB→PHB` quedó sin clase en un primer intento y se agregó a mano a `PARTE_DE`.
- **Revisar:** `CB/tabla/clasificacion_barrido.json`, en especial los pares marcados como «airdrop» o «sin par USDT del viejo».

### L-2 · Recall de la búsqueda de renombres

- **Los tres barridos son del mismo autor**, con patrones elegidos por él:
  - relaciones con decimales y cambios de ticker;
  - las 1.636 páginas sin saludo;
  - la actividad.

  Un renombre redactado de otra forma puede escaparse a los tres.
- **Limitaciones del archivo:**
  - 929 páginas con título ilegible;
  - páginas de 2023 tituladas solo «Announcement».
- **Recall de la extracción congelada:** la conciliación congelada no registra como eventos varios retiros de pares USDT que sí tienen anuncio archivado:
  - GTO, BTCST, SRM y TRIBE, el 2022-11-28;
  - KEY, el 2023-02-10;
  - los cierres por canje de 2021–2023.
- **Estimación del autor:** no mueven A, porque una falla anterior al 2023-05-08 da un lunes ≤ 2023-05-15. **A verificar.**

### L-3 · Fechas efectivas de certeza media

**COCOS→COMBO (T044), TVK→VANRY (T047) y MFT→HIFI (T042):**
- solo está archivado el anuncio de **finalización**;
- E es la fecha de ese anuncio, no la hora de cese del par viejo;
- MFT→HIFI: último día activo de MFTUSDT 2023-01-02, primer día de HIFIUSDT 2023-01-12.

**BTCST (T010, regla 2):**
- el texto dice «1:10» sin decir qué lado es el viejo;
- se leyó 1 viejo = 10 nuevos por analogía con COCOS;
- anterior a A.

### L-4 · Reverse splits de tokens apalancados

- **18 entradas.** E **no sale del texto**: es el día siguiente al último día activo (`construir_tabla.py`, sección 3).
- **Sin aviso de finalización archivado (certeza media), 4 de las 18:** SUSHIDOWN, SXPDOWN, XLMDOWN y YFIDOWN.
- **Estimación del autor:** sin efecto, porque §4.5 excluye los apalancados de todo universo. **Pero** entran en (ii′) y (iv′) con R1 literal.

### L-5 · LUNA: reutilización del ticker (regla 1R)

- La fecha exacta del cambio de ticker LUNA→LUNC **no está archivada**: el texto dice «has since been renamed».
- La 1R se apoya en dos datos que sí están:
  - el corte de actividad del 2022-05-12 al 2022-05-31;
  - el anuncio de apertura de Terra 2.0.
- **Inconsistencia menor de redacción:** el hueco LUNA→LUNC figura como 119 días en `chequeo_actividad` (T065) y como «120 días después» en la nota de la entrada 1R. Es una diferencia de convención de conteo; no cambia ninguna clasificación.

### L-6 · Anuncios que el autor dejó fuera de la regla 1

| Caso | Tratamiento del autor | Decisión |
|---|---|---|
| BCC → BCHABC + BCHSV (T055) | Bifurcación | D-2 |
| RGT → TRIBE (T070) | Fusión en un par existente | — |
| BETH → WBETH (T056) y USDSB → USDS (T074) | Conversiones con solapamiento | — |

**Estimación del autor:** ninguno tiene efecto en A.

---

## B. Ventana y datos reales (T-6, T-7 y T-8)

### L-7 · Criterio (d), volumen, sin evaluar

- No se evaluó para **HIFI** en las 9 formaciones donde cambian (a) y (b), ni para **GFT** bajo la opción (b) de D-1.
- Evaluarlo exige leer QV real, que estaba prohibido.

### L-8 · Exclusiones posteriores al 2024-11-06

- El archivo web termina el 2024-11-06. No hay una fuente permitida que permita verificar que la lista de fallas posteriores esté completa.
- Es el punto ciego de (ii′); ver M-1 y M-4.

### L-9 · Alcance de «no se leyeron precios»

- **La guarda `SoloEstado`:**
  - la escribió el autor;
  - controla el acceso **por clave** del `.npz`.
- **Los bytes completos de las series sí se leen, para hashearlos:**
  - `generar_v3.py`;
  - `leer_y_verificar`;
  - `mapeos_sobre_estado_real.py`.
- La afirmación correcta es «no se decodificó ni se usó ningún arreglo de precio o volumen», no «no se leyeron esos bytes».

### L-10 · El archivo de ventana fijado se calculó con la tabla de 22

**Qué fija el v3:** `REP/ventana_A/ventana_A_pasada2.json` (`dcbd80ab…`).

**Coincide** con el recálculo con la tabla completa (`CB/verificaciones/ventana_tabla_completa.json`) en:
- inicio, semanas, evaluables y mínimo de elegibles;
- último inicio válido;
- (iv′).

**Difiere** en los conteos por año de salidas en alcance:

| Año | Archivo fijado (tabla de 22) | Tabla completa |
|---|---|---|
| 2021 | 10 | 9 |
| 2022 | 35 | 31 |
| 2023 | 19 (1 sin evidencia) | 18 (1 sin evidencia) |

**Qué controla el v3 del contenido:** el `veredicto` y el `inicio_H`, además del sha256. Un archivo de ventana con conteos «viejos» pasa la verificación.

---

## C. Orquestador v3 (T-2, T-4 y T-5)

### L-11 · `validez_previa` cuenta como etapa «sin estadísticos»

En esa etapa:
- se construyen los universos con precios y volúmenes;
- se corre `motor.simular` seis veces en memoria (una base y cinco cortes);
- se escribe `VALIDEZ_PREVIA.json`, con semanas evaluables e invariancia, sin retornos.

Un ERROR en esta etapa admite un reintento. Si eso es aceptable se discute en M-5.

### L-12 · La unicidad depende del registro de intentos

- El registro `INTENTOS_E3.jsonl` vive junto al script (`AQUI`, l. 64).
- Hay dos maneras de rehabilitar una ejecución con **otra** carpeta de salida:
  - borrar el registro;
  - copiar el árbol a otra ruta.
- `salida.exists()` solo protege la misma ruta.
- Es una garantía **de gobierno**, no técnica.

### L-13 · Fallo del registro después de escribir un resultado terminal

**Hallado al preparar este paquete. No se corrigió:** el árbol está congelado y modificarlo no está permitido.

- **EVALUADO** (l. 885–886, 889):
  - si `intentos.anotar(evento="EVALUADO")` falla después de escribir el RESULTADO, el `except BaseException` llama a `resultado_error` con la etapa «escritura»;
  - ese ERROR **sobrescribe** `RESULTADO_E3.json`;
  - la ejecución queda bloqueada (estadísticos iniciados), pero **se pierden los resultados ya calculados**.
- **INVALIDO** (l. 803–804, dentro de la etapa «validez_previa»):
  - si falla la anotación de INVALIDO y después la de ERROR funciona (un fallo transitorio), el INVALIDO queda sobrescrito por un ERROR **sin estadísticos**;
  - eso **habilita un reintento** con una autorización nueva;
  - la política declarada dice que después de un INVALIDO no hay otra ejecución.
- **INICIADO** (l. 859–860):
  - si `mkdir` funciona y la anotación de INICIADO falla, queda una carpeta de salida sin intento registrado;
  - otro intento, con otra salida, no se bloquea. Todavía no se calculó nada.
- **Ninguna prueba** cubre fallos del registro después de escribir un resultado.
- **A confirmar o refutar en T-5.**

### L-14 · Ventana entre la compilación y `SHA_PROPIO`

- `SHA_PROPIO` sale de leer `__file__` al importar (l. 57–58). Es una lectura **distinta** de la que usó Python para compilar el script.
- Si el archivo se reemplaza entre las dos lecturas, se ejecuta un código distinto del que se hasheó.
- Requiere acceso de escritura local durante el arranque.
- `cargar_modulos` cierra esta ventana para `universo`, `motor` e `inferencia`, pero **no** para el propio orquestador.

### L-15 · Enlaces simbólicos en directorios padre

**Qué se rechaza:**
- `_leer_archivo`: el componente final;
- `_leer_conjunto`: la raíz y las entradas internas.

**Qué no se rechaza:** los directorios padre (`e3`, `REPARACION` y `CIERRE`) pueden ser enlaces.

**Mitigación:** el contenido igual se verifica por hash.

### L-16 · La atomicidad se argumenta por construcción

- `escribir_atomico` sincroniza el archivo y usa `os.replace`, pero no sincroniza el directorio.
- No hay pruebas de corte de energía ni de disco lleno a mitad de la escritura.

### L-17 · Las frases de decisión las redactó el autor

**Qué exige el v3:**
- D-A, D-B y D-C, en **una sola** frase;
- D-1, solo con la lectura literal.

**Qué no exige:** ningún pronunciamiento expreso sobre:
- D-3 (158 frente a 160 semanas);
- D-4 (reintentos);
- D-5 (riesgos residuales);
- la revisión independiente.

Esa exigencia queda fuera del código, en el proceso de autorización.

---

## D. Pruebas (T-9 y T-10)

### L-18 · Las pruebas del v3 parchean hashes y frases

- **Qué parchean:** los sha256 fijados (con una sal de prueba) y las frases (con frases de prueba).
- **Cómo se controla aparte:**
  - la coincidencia con los hashes reales, en `test_exigidas_del_v3_coinciden_con_los_insumos_congelados`;
  - la verificación con los insumos reales, en T-8.
- **Riesgo:** que el parche oculte un acoplamiento entre una constante y su uso.

### L-19 · Los mutantes los eligió el autor

- Son 15, y cada uno lo detectan las pruebas que el mismo autor escribió pensando en él.
- **Que ninguno sobreviva no mide la cobertura frente a defectos que el autor no imaginó.** Ver las sugerencias de T-9 y el ítem L-13.

### L-20 · La suite del autor (v2) escribe valores reales en temporales

- Escribe la frase real del v2 y el hash real del v2.
- `reproducir.sh` la corre neutralizada, con el `conftest.py` de la revisión del 2026-10-26.

---

## E. Proceso y dependencias

### L-21 · Un solo agente

El mismo agente preparó:
- la reparación;
- la revisión del 2026-10-26, que, pese a su nombre, **no es independiente**;
- el cierre de bloqueantes;
- este paquete.

No hubo ninguna verificación cruzada humana ni de un tercero.

### L-22 · Lo que el autor no verificó

- **La potencia de 0,35–0,56:** se tomó de otros informes.
- **La historia de F3:** se verificó la huella, no la historia.
- **Si P0 se vio antes de congelar la Adenda R:** ni demostrable ni refutable.

### L-23 · Evidencia que no viaja en el paquete

**Qué falta:**
- los ZIP de Vision;
- los índices de Common Crawl;
- los registros de descarga.

**Cómo se controla:** solo por su sha256 en `registro/INVENTARIO_E3_COMPLETO.sha256`.

**Riesgo:** el entorno de origen es efímero.

### L-24 · El v3 se generó con plantillas

**Cómo se arma:** `CB/orquestador_v3/generar_v3.py` toma tres partes:
- `plantilla_cabecera.py`;
- el bloque de cálculo del v2;
- `plantilla_cola.py`.

**Qué inyecta:** los hashes.

**Revisar:** que lo regenere byte a byte (T-2) y que no inyecte nada más que lo declarado.

### L-25 · Los orquestadores v1 y v2 siguen siendo ejecutables

Detectado con `reproducir/auxiliar.py higiene` al probar este paquete.

**Las frases de autorización del v1 y del v2 figuran literalmente en documentos congelados:**
- v1: `E3R/PLAN_EJECUCION_UNICA_E3R.md`, `REP/orquestador_v2/DIFF_v1_v2.diff`, `REP/orquestador_v2/generar_v2.py` y la revisión del 2026-10-26 (sus copias y `verificaciones/diff_recalculado.diff`);
- v2: `REP/INFORME_REPARACION_E3H1H2.md` y su copia en la revisión.

**Por qué importa:**
- el v1 y el v2 no tienen registro de intentos (lo introdujo el v3, C11), así que una ejecución con ellos no deja rastro que bloquee al v3, ni al revés;
- que estén superados es una decisión de gobierno, **no está impuesta por el código**.

**Contraste con el v3:**
- en su código, la FRASE y la frase de reapertura están partidas en varias líneas, así que no aparecen literales en ningún archivo;
- la frase de D-1 aparece solo en el v3, en su plantilla y en el diff.

**Revisar en T-10 y M-4.**
