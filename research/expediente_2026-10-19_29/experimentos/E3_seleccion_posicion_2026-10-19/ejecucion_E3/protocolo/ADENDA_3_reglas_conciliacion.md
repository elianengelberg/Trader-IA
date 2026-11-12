# Adenda 3: reglas fijas de la conciliación de supervivencia (v3 §2.3 y §4.11; notas N5–N7; Enmienda 2, E2.1)

**Momento:** 2026-10-20.
- Se escribió **antes** de descargar las páginas archivadas y antes de cualquier clasificación de anuncios.
- Para depurar el extractor solo se leyeron **5 páginas de prueba**: CTR, VEN/VET, PIVX, una competencia en EUR y una promoción de tarjeta.
- No se usó ningún precio para evaluar E3.

**Qué no cambia:** la v3 (`279a865f…`), la Adenda 1 y la Enmienda 2. Esta adenda **no cambia** categorías, umbrales, ventanas ni criterios. Solo fija cómo se leen los casos que la v3 deja a «la mejor lectura documentada».

## A3.1 Extracción (`cc_clasificar.py`)
1. **Solo se usa el cuerpo del anuncio:**
   - empieza en la última aparición del título y se quita la cabecera «Binance <fecha de publicación>»;
   - termina en la primera de estas marcas: «Thanks for your support», «Binance Team», «Related Articles» o «Find us on Telegram».
   - *Motivo:* en las páginas de prueba, la barra lateral («Articles in this section») trae títulos de otros anuncios, con pares como WAVES/USDT o LINK/USDT. Si se leyeran, se atribuirían pares ajenos a cada anuncio.
2. **Tipo «corrección»:** el título combina el patrón de exclusión con «postpone», «cancel», «reschedul», «delay» o «update … delist».
3. **Títulos mixtos** (canje de red que además «adds … trading pair»): también generan registros de listado.
4. **Palabras que no son tokens** y se descartan: UTC, USD, NFT, API, KYC, VIP, P2P, ETF, EEA, UK, EU, FAQ, AM, PM, OTC, AMA, DEX, CEX.
5. **Fecha efectiva E** (N5):
   - la primera fecha del título;
   - si no hay, la primera fecha de una oración del cuerpo que contiene el patrón de exclusión y no menciona depósitos ni retiros.

## A3.2 Eventos y universo de anuncios
- **Evento** = (par USDT, E).
- **Fusión:** las filas del mismo par con E a ≤ 3 días son **un solo evento**, aunque vengan de páginas o URL distintas (Zendesk y binance.com).
  - E = la fecha tomada de un título, si alguna fila la tiene; si no, la más temprana.
  - Se conservan todas las URL.
- **Universo:** eventos con E ∈ [2018-01-01, 2026-05-31].
- **Fuera del universo** (v3 §2.3): una exclusión de token cuyo cuerpo enumera los pares, sin que USDT esté entre ellos. Se informa aparte.

## A3.3 Exclusión de token sin enumeración de pares, con XYZUSDT ausente del listado del bucket
1. **Hay evidencia documental de que XYZ/USDT existió** → **D** (falla).
   - Cuenta como evidencia cualquier página archivada con «XYZ/USDT» o «XYZUSDT» en su texto, o cualquier registro de listado de XYZUSDT.
2. **No hay evidencia, pero el listado del bucket conserva otro par de XYZ** (XYZ + otra cotización) → «sin par USDT documentado».
   - Queda fuera del universo y se informa aparte.
   - *Motivo:* el bucket conserva pares retirados, así que su ausencia, sin otra evidencia, indica que el par USDT no existía.
3. **No hay evidencia ni otro par de XYZ en el bucket** → lectura manual del texto:
   - si identifica a XYZ como un token negociado en el spot de Binance, es **D**;
   - si XYZ no es un token (error de extracción), se descarta y se documenta.

## A3.4 Sin fecha efectiva tras la extracción
1. Se lee el texto archivado a mano (N5: fecha explícita, o anuncio + N días).
2. Si sigue sin fecha, R = fecha de publicación (o, en su defecto, de captura) y E se desconoce dentro de [R, R + 60]. Se clasifica así:
   - **D** si el par no está o no tiene días activos ≤ R + 61;
   - **C** si tiene días activos en (R + 61, R + 90];
   - **A** si su último día activo L ≤ R + 61 cumple L ≥ R − 7;
   - **B** o **T** con E = R en los demás casos.

## A3.5 Casos C
**Todos** se leen a mano en el texto archivado. Resultados posibles:
- (a) **E corregida** según el texto, con cita, y el caso se reclasifica;
- (b) **C explicada:** hay un relisting o una corrección (postergación o cancelación) documentados;
- (c) en otro caso, **C no explicada** (falla).

## A3.6 Controles V-S2 y V-S3
- **Muestreo:** `numpy.random.default_rng(semilla).choice(n, min(n, k), replace=False)` sobre los registros ordenados por (par, fecha, url). Sin reemplazos ni nuevos sorteos.
- **V-S2** (semilla 20261025, k = 50):
  - se sortea entre los registros de listado USDT con fecha de apertura A ∈ [2018-01-01, 2026-05-31], sin duplicados (par, A);
  - **acierto:** un listado vigente del par empieza en [A − 3, A + 3], es decir, un día activo sin días activos en los 30 anteriores;
  - el sorteo y la regla de acierto son fijos;
  - los desaciertos se leen a mano; si el texto muestra que la fecha o el par extraídos estaban mal, se usa la lectura corregida y se informa;
  - **criterio:** ≥ 95 %.
- **V-S3** (semilla 20261026, k = 10): se sortea entre los eventos del universo y se comparan a mano el par, E y la categoría con el texto archivado.

## A3.7 Salidas observadas (N7)
- **Base** = símbolo − «USDT» (exchangeInfo no está disponible: A3.9).
- **«Con anuncio»** si en [L − 1, L + 365] hay al menos uno de estos:
  - un evento del mismo par;
  - una página de exclusión cuyos tokens del título incluyen la base (cualquier subtipo);
  - un renombre mapeado del símbolo.
- **Renombres mapeados:** la lista manual de renombres (Adenda 1) tomada de los candidatos de renombre o canje con cambio de ticker. Fija: símbolo viejo, nuevo, E, relación y cita. Las salidas del símbolo viejo por un renombre mapeado **no cuentan** como salidas.

## A3.8 Inicio de H (v3 §4.11)
- **(i)** El primer lunes de la primera racha de 13 semanas evaluables seguidas (`analisis_estructural.py`).
- **(ii)** El primer lunes posterior a la E de la última falla del universo (T, D o C no explicada).
- **(iii)** El 1 de enero del año de la E más temprana entre los eventos del universo. Es la lectura conservadora de «primer año con anuncios»: anuncios de exclusión, no cualquier anuncio.
- **(iv)** El 1 de enero del primer año Y ≥ 2018 tal que, para todo y ∈ [Y, 2026], las salidas sin anuncio son ≤ 10 % de las observadas. Un año sin salidas observadas cumple.
- **Inicio** = el primer lunes ≥ al más tardío de (i)–(iv).
- **H** = [inicio, 2026-05-18]. Es **INVÁLIDO** si tiene < 156 semanas evaluables o > 20 % no evaluables.

## A3.9 V-S4
`api.binance.com/api/v3/exchangeInfo` respondió **HTTP 451** el 2026-10-20 a las 02:11:26Z: el servicio no está disponible desde una ubicación restringida según las condiciones de elegibilidad de Binance.
- **No se prueban endpoints alternativos**: eludiría un control de acceso.
- **V-S4 queda NO EJECUTADO** y se informa como control no satisfecho.

## A3.10 V-S5
Se verifica en las series de calidad: el número de días con estado activo y ≤ 0 operaciones debe ser 0. El universo y los retornos solo usan días activos.

## A3.11 Orden y transparencia
1. **Primera pasada:** `conciliacion.py` sin resoluciones manuales. Produce las listas de revisión: casos E, todos los C, los D del punto 3 de A3.3, los desaciertos de V-S2, la muestra de V-S3 y los candidatos de renombre.
2. **Lectura manual:** cada caso de cada lista se resuelve con una cita del texto archivado, en `resoluciones_manuales.json`. **Se revisan todos los casos de cada lista, sin seleccionar.**
3. **Segunda pasada:** con ese archivo. Su resultado es el definitivo.
4. Se informa que la primera pasada fue vista antes de la lectura manual.
