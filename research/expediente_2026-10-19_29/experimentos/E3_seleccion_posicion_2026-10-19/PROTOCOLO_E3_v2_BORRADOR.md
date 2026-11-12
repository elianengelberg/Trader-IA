# Prerregistro E3, versión 2: momentum transversal long-only (borrador para revisión; NO EJECUTAR, NO CONGELADO)

**Estado (2026-10-20):**
- No se descargó ningún dato, no se ejecutó ninguna prueba, no se instaló nada y no se modificó el repositorio.
- Esta versión **reemplaza** a `PROTOCOLO_E3_BORRADOR.md` (v1), que queda sin cambios como registro.
- Las afirmaciones de `INFORME_E3.md` sobre el período reservado (§2.8 y §4.3) quedan **corregidas** por el §1 de este documento.

**Etiquetas:** [Hip] supuesto o estimación mía · [Doc] verificado en documentación oficial o pública · [TIA] hecho del proyecto · [Pub] literatura.

## Cambios respecto de v1
| Punto de la revisión | v1 | v2 |
|---|---|---|
| 1. Período reservado | Trataba [2025-01-01, 2026-06-01) como reserva fuera de muestra | **Retiro esa afirmación.** No es fuera de muestra. Propongo tres capas honestas: histórica (con contaminación declarada), ventana ciega corta (opcional, con autorización) y prospectiva (la única confirmación independiente) |
| 2. Supervivencia | 10 anuncios como control de validez | Reconstrucción desde los propios datos de negociación (operaciones > 0), conciliación con **todas** las exclusiones oficiales de pares USDT, más una muestra de listados y 10 controles en profundidad. Fuentes alternativas y sus límites |
| 3. Multiplicidad | Holm m = 3 con el filtro dentro | Tres hipótesis exactas: H1 y H2 en la familia base (Holm) y H3 subordinada (gatekeeping serial). Inventario de las 30 decisiones que podrían generar pruebas y registro obligatorio de ejecuciones |
| 4. Especificación | Reglas resumidas | Fórmulas y algoritmo completos, incluidos huecos, velas sin operaciones, exclusiones y renombres |
| 5. Criterios | Mezclados | Predictivo, económico y robustez por separado. Justificación del 0,01 y del 90 %. Potencia y límites |
| 6. Filtro de tendencia | Hipótesis H3 en paralelo | **Fuera de la base.** Prueba incremental posterior, habilitada solo si la base es «respaldada» |
| 7. Datos | Estimación general | Archivos, rutas, pares, períodos, tamaños, número de solicitudes y fuentes de los anuncios |

---

## 1. Uso previo de los datos y períodos (punto 1)

### 1.1 Qué se consultó o se usó, por línea
| Línea | Activos | Datos | Período | Uso |
|---|---|---|---|---|
| T, desarrollo (con los cribados V y R) | BTC (y ETH en desarrollo) | Spot 1d | 2017-08-17 → 2021-12-31 (métricas desde 2018-02-14) | Diseño, cribado y sensibilidad |
| T, fuera de muestra | BTC, ETH | Spot 1d | 2022-01-01 → 2026-05-31 | **Evaluado** |
| T-MULTI | 12 ETF (11 evaluados) | Diario más dividendos | 2011-01-03 → 2026-09-30 (evaluación desde 2013-01-02) | **Evaluado** |
| T-papel | BTC, ETH | Spot 1d diario | 2026-04-20 → 2026-10-16 | Historia de la señal: **no evaluada**, pero descargada; se registraron el último cierre y la exposición de T. Sin observaciones prospectivas al 2026-10-18 |
| Monitor del carry (T-papel) | BTC | Funding | 2026-07-03 → 2026-09-30 | Consultado como **agregado** (6,5 %/año), dentro del reservado de H-CARRY |
| H-CARRY | BTC (spot y perpetuo 1h: velas, mark, prima, funding) | 1h | 2020-01 → 2026-05: desarrollo 2020-01 → 2022-12; validación 2023-01 → 2024-01; **test 2024-02 → 2026-05 (consumido)** | **Evaluado** |
| H-CARRY, exploratorio posterior | ETH y SOL (funding), DTB3, Aave | Varios | 2019-12/2020-01 → 2026-05 | Exploratorio |
| E1 | BTC | Spot 1h | 2019-10-01 → 2026-05-31 | **Evaluado** |
| E2 | BTC, ETH; funding de BTC y ETH; prima de BTC; Wikipedia | Spot 1d; funding; 1h | Precios 2017-08 → 2026-05; funding y prima 2020-01 → 2026-05; vistas 2015-07 → 2026-05 | **Evaluado** |
| E3, diseño | — | Ninguno: solo literatura e inventario de archivos locales (nombres, fechas y tamaños; ningún precio) | — | — |
| **Altcoins (todo menos BTC y ETH)** | — | — | — | **Nunca descargadas ni usadas** por el proyecto |

### 1.2 Conocimiento de quienes diseñan
- **El asistente** tiene conocimiento general del mercado cripto hasta aproximadamente **junio de 2026** (su fecha de corte declarada). Eso incluye qué narrativas y monedas subieron o cayeron en 2017–2025, aunque no series semanales precisas.
- **El usuario y los revisores** vivieron el período completo.
- **La literatura** que motiva la hipótesis cubre 2013–2023.

### 1.3 ¿Es [2025-01-01, 2026-06-01) fuera de muestra? **No.**
1. BTC y ETH ya se **evaluaron** en ese tramo: T fuera de muestra, test de H-CARRY (BTC), E1 (BTC 1h) y E2.
2. Quienes diseñan conocen el período cualitativamente: qué monedas y narrativas ganaron.
3. Que el proyecto no haya bajado las altcoins es real, pero **no basta** para llamarlo fuera de muestra.

v1 lo presentaba como reserva fuera de muestra: **esa afirmación se retira.** En sentido estricto, **ningún período anterior a junio de 2026 está intacto.**

### 1.4 Alternativa honesta: tres capas
| Capa | Ventana | Qué es | Qué puede concluir |
|---|---|---|---|
| **H: histórica** (una sola ejecución) | Desde el primer lunes evaluable (§4.9; estimo 2019-H2 [Hip]) hasta el **lunes 2026-05-18**, con el último retorno terminando en la apertura del 2026-05-25. ≈ 330–360 semanas | Datos de altcoins nunca usados por el proyecto, con reglas fijadas por la literatura antes de verlos. **Contaminación declarada:** conocimiento cualitativo del período; BTC y ETH reutilizados | «Evidencia histórica»: nunca «confirmación independiente» |
| **C: ventana ciega corta** (opcional; se abre solo si H da «respaldada») | [2026-06-01, último lunes antes de la congelación). Unas 20 semanas | **Altcoins nunca vistas**, posterior al corte de conocimiento del asistente. Coincide con el reservado de H-CARRY, cuyo cierre lo dejó «intacto para una hipótesis nueva, con autorización». BTC y ETH: precios ya descargados para T-papel como historia, sin evaluar | Solo detecta **contradicciones groseras** (efecto mínimo de la correlación ≈ 0,08). No confirma. El usuario y los revisores sí vivieron ese período |
| **P: prospectiva** | Desde la congelación, con reglas idénticas | **La única evaluación independiente** | Con una correlación verdadera de 0,03 hacen falta ≈ 2–3,5 años para confirmarla; con 0,02, ≈ 4–8 años [Hip] |

**Por qué no propongo una pseudo-reserva interna:**
- Por ejemplo, reservar 2025-01 → 2026-05.
- Costaría ≈ 20–25 % de las semanas de H, con una pérdida de potencia de ≈ 10 puntos.
- No compraría independencia, porque el tramo también es conocido.
- Su único valor sería protegernos de iterar sobre H; eso ya lo garantiza esta regla: **una ejecución, todo registrado y cualquier variante posterior es exploratoria.**

**Para C hacen falta dos autorizaciones tuyas:**
1. usar el reservado de H-CARRY para esta hipótesis;
2. descargar esos datos.

Si no las das, se pasa directo de H a P.

---

## 2. Universo histórico y supervivencia (punto 2)

### 2.1 Principio
El universo de cada fecha se reconstruye **desde los propios registros de negociación** (velas diarias con operaciones), **no** desde listas actuales de símbolos. Los anuncios oficiales sirven para **verificar** esa reconstrucción y para **mapear renombres**. No reemplazan los datos.

### 2.2 Fuentes oficiales
| Fuente | Para qué | Notas [Doc] |
|---|---|---|
| **data.binance.vision**, klines 1d mensuales de spot y su `.CHECKSUM` | Precios, volumen en USDT y **número de operaciones** por día | Ruta `data/spot/monthly/klines/{SÍMBOLO}/1d/{SÍMBOLO}-1d-{AAAA-MM}.zip`. Columnas: open time, OHLC, volume, close time, **quote asset volume**, **number of trades**, taker volumes. **Desde 2025-01-01 las marcas de tiempo del spot están en microsegundos** |
| Listado del bucket (prefijos por símbolo) | Conjunto de símbolos con archivos | El README dice «all symbols are supported». **No** dice si conserva los excluidos: **por verificar** (§2.4) |
| Anuncios oficiales de Binance: Delisting (`binance.com/en/support/announcement/list/161`), New Cryptocurrency Listing (`…/list/48`), Latest Binance News (`…/list/49`, renombres y canjes) | Conciliación de exclusiones, listados y renombres | La categoría Delisting mezcla exclusiones de tokens, «Notice of Removal of Spot Trading Pairs» (pares sueltos; el token puede seguir en otros pares), futuros, margen y Alpha. Solo cuentan las de **pares spot contra USDT** |
| `GET /api/v3/exchangeInfo` (instantánea actual) | Separar el activo base del de cotización en símbolos vigentes; estados TRADING, HALT y BREAK | No es histórica. Solo sirve para interpretar símbolos, nunca para el universo |

**Hallazgo que cambia la regla** [Doc: issue #201 de binance-public-data, respuesta del mantenedor, 2022-12-16]:
- tras la exclusión de un símbolo, Vision puede seguir publicando velas **con el último precio arrastrado y 0 operaciones**;
- **que exista un archivo no prueba que el par cotizara.** La reconstrucción exige **número de operaciones > 0**.

### 2.3 Reglas de reconstrucción (fijadas ahora)
1. **Conjunto de símbolos:** todos los prefijos del bucket bajo `data/spot/monthly/klines/` cuyo nombre termina en `USDT`.
   - Base = nombre menos «USDT».
   - Si exchangeInfo da otro par base/cotización para ese símbolo, manda exchangeInfo.
2. **Día activo** del par s en d: existe la vela 1d de d, con **operaciones > 0**, precios > 0 y OHLC coherente (L ≤ O, C ≤ H).
   - Una vela con 0 operaciones = **día inactivo** (precio arrastrado), igual que un día sin vela.
3. **Primer día activo** = listado efectivo del par.
   - **Fin de cotización** = último día activo antes de 30 días seguidos inactivos, o antes del final de los datos.
   - Si vuelve a estar activo después, es un **listado nuevo**: la edad se reinicia, salvo que un anuncio documente una suspensión temporal.
4. **Renombres y canjes:** se mapean solo con un anuncio oficial que dé el símbolo viejo, el nuevo, la fecha y la relación de canje.
   - Un renombre mapeado conserva la edad y la posición (unidades × relación).
   - Uno no mapeado se trata como exclusión al último día activo, más un listado nuevo.
5. **Exclusión de un par USDT con el token vigente en otros pares:** para este universo es una **salida** (solo se opera contra USDT).
6. **Archivos:**
   - si falta un archivo mensual, o su checksum falla, se usan los diarios oficiales de ese mes (con su `.CHECKSUM`);
   - si para un mismo día el mensual y el diario discrepan en OHLC u operaciones, ese día se trata como **inactivo** (misma regla que la adenda 1 de E1).
7. **Unidades de tiempo:** se detectan ms o µs por magnitud (cambio del 2025-01-01). Toda vela debe durar 1 día exacto; si no, el día es inactivo.

### 2.4 Verificación de la reconstrucción (una comprobación, no una prueba de completitud)
Se hace en la etapa de calidad (F3), **antes** de calcular cualquier retorno de estrategia. Todo se guarda con hash.

| Control | Qué | Criterio |
|---|---|---|
| **V-S1: conciliación de exclusiones (todas)** | Cada anuncio oficial de exclusión de token o de remoción de un par **spot contra USDT**, con fecha efectiva entre 2018-01-01 y 2026-05-31 | ≥ 95 % del total y ≥ 90 % en cada año calendario deben tener el par en los datos, con su último día activo entre 7 días antes y 1 día después de la fecha efectiva |
| **V-S2: listados (muestra)** | 50 anuncios de listados nuevos con par USDT, elegidos al azar con semilla fija **antes** de mirar precios | ≥ 95 % con el primer día activo dentro de ±3 días del inicio anunciado |
| **V-S3: 10 controles en profundidad** | 10 exclusiones al azar de V-S1, revisadas a mano: continuidad de precios, días inactivos y que no haya velas activas tras la fecha efectiva | 10 de 10 coherentes, o una explicación documentada para cada desvío |
| **V-S4: vigentes** | Símbolos USDT con estado TRADING en exchangeInfo | 100 % presentes en el listado del bucket |
| **V-S5: precios arrastrados** | Velas con 0 operaciones tras el fin de cotización | Se cuentan y se confirma que **ninguna** entra en el universo ni en los retornos |
| **V-S6: estructura** | Pares activos por mes; altas y bajas por año | Se informan. Las bajas por año deben ser > 0 en todos los años con exclusiones anunciadas |

**Decisiones fijadas ahora:**
- Si V-S1 falla **solo** en los primeros años, el inicio de H pasa al primer año calendario desde el que se cumplen ≥ 95 % acumulado y ≥ 90 % en cada año. Esto reduce la potencia, y se informa cuánto.
- Si V-S1 falla en general (< 95 % del total), la prueba queda **INVÁLIDA con Vision**, sin interpretar.
- Los anuncios con fechas ambiguas o sin el par USDT explícito se informan como «no conciliables» y quedan fuera del denominador (y se cuentan).

### 2.5 Si Binance Vision no conserva los pares excluidos
- **Hasta donde pude verificar, no hay otra fuente oficial de Binance con velas de pares excluidos.**
  - La API REST de velas sirve símbolos vigentes; que rechace los excluidos es [Hip, no lo probé para no hacer consultas de datos].
  - exchangeInfo no es histórico.
- **Alternativas, todas no oficiales:**

| Fuente | Qué es | Limitaciones |
|---|---|---|
| **Tardis.dev** [Doc] | Captura por un tercero del feed WebSocket **oficial** de Binance | Pares de alta capitalización desde 2019-03-30 y **todos los pares desde 2021-03-05**: un universo completo solo desde 2021-03, ≈ 270 semanas y menos potencia. Pago (salvo el primer día de cada mes). Habría que construir las velas diarias desde trades (gran volumen) y no son idénticas a las de Binance. Hay que verificar si incluye los pares excluidos |
| Kaiko, CoinAPI, CryptoCompare | Proveedores comerciales | Costo, licencias que restringen la redistribución, metodologías propias |
| CoinMarketCap o CoinGecko (instantáneas históricas) | Agregados de varios exchanges | No son precios de Binance; condiciones de uso y raspado; servirían para verificar, no para operar |

- Cualquier alternativa exige **una adenda nueva y tu autorización**, con costo y licencia evaluados antes.

---

## 3. Hipótesis y multiplicidad (punto 3)

### 3.1 Las tres hipótesis confirmatorias y sus métricas primarias
| | Hipótesis exacta | Métrica primaria | Prueba |
|---|---|---|---|
| **H1 (predictiva)** | En U100, la señal S (§4.5) tiene una correlación de rangos media **positiva** con el retorno de la semana siguiente | IC̄ = media de los IC_t de Spearman en las semanas evaluables de H | t con Newey–West de 4 rezagos; p₁ unilateral |
| **H2 (selección neta)** | La cartera base de 6 monedas de U30 (§4.6–4.8) rinde, **neta de costos**, más que EW-U30 con la misma mecánica y costos | Media anualizada (× 52) del exceso semanal neto | Bootstrap circular por bloques de 13 semanas, 10 000 réplicas, semilla 20261020; p₂ = 1 − P(media > 0) |
| **H3 (incremental, subordinada)** | Agregar el filtro de momentum absoluto (§6) a la cartera base aumenta el rendimiento más allá de su menor exposición | Media anualizada del exceso de timing frente a la base escalada a la misma exposición media | Igual que H2; p₃ |

**Control del error de familia (5 %):**
- **Familia base {H1, H2}: Holm al 5 %.** Se compara el p menor con 0,025 y el otro con 0,05.
- **H3: gatekeeping serial.** Se prueba al 5 % **solo si H1 y H2 rechazan** y la base pasa la robustez (§5.3).
  - Este procedimiento controla el error de familia en las tres hipótesis ([Pub\*] Dmitrienko et al., gatekeeping serial).
  - Exigir robustez para abrir la compuerta solo la vuelve más estricta.
- **Por qué no Holm m = 3 sobre todo:** H3 está lógicamente subordinada; no tiene sentido sin una base válida. Con el gatekeeping, H1 y H2 conservan los umbrales 0,025 y 0,05 sin aumentar el error de familia.
  - Si preferís Holm m = 3 (con H3 = 1 cuando no se habilita), el procedimiento también es válido y más conservador. **Decidilo antes de congelar.**

**No son hipótesis, y no tienen p ni decisión:**
- las comparaciones con BTC buy and hold, con el efectivo y con la exposición equivalente (§5.2);
- la sensibilidad (§3.3, ítem 29).

**La robustez** (§5.3) son condiciones que **solo endurecen** la conclusión: no pueden rescatar una hipótesis que no rechazó.

### 3.2 Registro de ejecuciones (obligatorio)
- Cada cálculo de cualquier métrica de **rendimiento o predicción** sobre datos reales se anota en `REGISTRO_EJECUCIONES.jsonl`, que solo admite añadidos. Cada entrada lleva:
  - fecha;
  - hash del código, de la configuración y del manifiesto de datos;
  - propósito: confirmatoria, robustez, sensibilidad o exploratoria.
- **Lo planificado:**
  - 1 ejecución confirmatoria (H1, H2 y el nulo aleatorio);
  - 6 de robustez;
  - 1 de H3 (solo si se habilita);
  - 1 de sensibilidad (la grilla fija del ítem 29).
- **Toda otra ejecución es exploratoria:**
  - se cuenta y se informa;
  - **no puede cambiar ninguna clasificación**;
  - solo puede motivar una hipótesis **nueva**, que se prueba en datos prospectivos.
- Los Sharpe que se informen van con su versión deflactada ([Pub\*] Bailey y López de Prado), usando como número de intentos el total del registro.

### 3.3 Decisiones que podrían generar pruebas adicionales (todas fijadas ahora)
| # | Decisión | Valor fijado | Alternativas que **no** se prueban (salvo el ítem 29) |
|---|---|---|---|
| 1 | Mercado y cotización | Binance spot, pares USDT | Otros exchanges; pares BTC, BUSD o FDUSD |
| 2 | Inicio de H | Regla del §4.9 y del §2.4 | Fechas elegidas a mano |
| 3 | Fin de H | Lunes 2026-05-18 (retorno hasta el 2026-05-25) | — |
| 4 | Día activo | Operaciones > 0 y OHLC válido | Volumen > 0 sin mirar operaciones |
| 5 | Edad mínima | 180 días activos desde el primer día activo | 90 o 365 |
| 6 | Huecos en la formación | 30 días activos seguidos hasta t | Tolerancias |
| 7 | Liquidez | Mediana de 30 días de `quote asset volume` | Media; 60 o 90 días; volumen en base |
| 8 | Piso de liquidez | ≥ 1 000 000 USDT | Otros pisos |
| 9 | Universo invertible | Top 30 | 20, 50 (solo en el ítem 29) |
| 10 | Universo predictivo | Top 100 | U30 o todo |
| 11 | Stablecoins, fiat y materias primas | Lista del §4.4 más volatilidad < 10 % anual | Otras listas o umbrales |
| 12 | Tokens apalancados | Sufijos UP, DOWN, BULL, BEAR sobre una base existente | — |
| 13 | Duplicados | Correlación de 90 días > 0,98: queda el más líquido | Otros umbrales |
| 14 | Renombres | Solo con anuncio oficial | Detección automática |
| 15 | Horizontes de la señal | 7, 14, 21 y 28 días | Uno solo; > 4 semanas (solo en el ítem 29) |
| 16 | Combinación | Media de rangos percentiles | Media de retornos; z-scores |
| 17 | Período de salto | Ninguno | Saltar 1 día o 1 semana |
| 18 | Formación y ejecución | Domingo 23:59:59.999, ejecución en la **apertura del lunes** | Otro día de la semana (solo en el ítem 29: miércoles) |
| 19 | k | 6 | 4, 10 (ítem 29) |
| 20 | Banda de permanencia | Rango ≤ 12 | Sin banda (ítem 29) |
| 21 | Pesos y rebalanceo | Lugares fijos; reposición con lo vendido; vuelta a 1/6 el primer lunes de cada mes o si algún peso > 1/3 | Rebalanceo semanal completo |
| 22 | Costos | 10 pb más tramo de spread y slippage (§4.8) | Otros supuestos (solo ×2 en R1) |
| 23 | Precio de ejecución | Apertura oficial del día | Cierre; VWAP |
| 24 | Fin de cotización con posición abierta | Salida al último cierre activo | Recorte (solo en R6) |
| 25 | Referencia principal | EW-U30 con la **misma mecánica y costos** | EW sin costos; ponderada por capitalización |
| 26 | Métrica de H1 | Spearman semanal, retorno de apertura a apertura | Pearson; retorno de cierre a cierre |
| 27 | Inferencia | Newey–West con 4 rezagos; bootstrap circular de 13 semanas, 10 000 réplicas; semillas fijas | Otros rezagos o bloques |
| 28 | Umbrales de decisión | §5 | Cualquier otro |
| 29 | **Grilla de sensibilidad (única, descriptiva, posterior)** | k ∈ {4, 6, 10} × N ∈ {20, 30, 50}; cada horizonte por separado; sin banda; formación el miércoles | Nada fuera de esta grilla |
| 30 | Tratamiento de BTC y ETH | Dentro del universo como cualquier moneda | Excluirlos |

---

## 4. Especificación reproducible (punto 4)

### 4.1 Notación y calendario
- **d:** día UTC.
- **Vela de d:** apertura O_d a las 00:00 y cierre C_d a las 23:59:59.999.
- **Formación:** cada **lunes t** a las 00:00 UTC, con datos de días ≤ t − 1 (hasta el domingo).
- **Ejecución:** en **O_t**, la apertura del lunes.
- **Semana de tenencia:** de O_t a O_{t+7}.

### 4.2 Precios de valuación
- **P_val(s, d)** = C_d si d es activo; si no, el último C de un día activo anterior.
- Las velas con 0 operaciones **nunca** aportan precios nuevos.

### 4.3 Elegibilidad en t
Un par s es elegible en t si cumple todo lo siguiente:
- (a) sus días t−30 … t−1 están **todos activos**;
- (b) su primer día activo (o el del predecesor mapeado) es ≤ t − 180;
- (c) no está excluido por el §4.4;
- (d) **V(s, t)** = mediana de `quote asset volume` de los días t−30 … t−1 es ≥ 1 000 000 USDT.

### 4.4 Exclusiones (en t, sin mirar al futuro)
- **Base en la lista fija:**
  - USDC, BUSD, TUSD, USDP, PAX, DAI, FDUSD, USDS, USDSB, UST, USTC, SUSD, PAXG, XAUT, AEUR, EURI, USD1;
  - cualquier código ISO-4217 de moneda fiat (EUR, GBP, AUD, BRL, TRY, RUB, NGN, UAH, ZAR, IDR, VND, etc.);
  - BIDR, IDRT, BVND.
- **Volatilidad anual** de los retornos logarítmicos diarios de los días activos de [t−90, t−1] < 10 %, calculada con ≥ 60 días activos (con menos, no se aplica esta regla; la (b) ya exige edad).
- **Tokens apalancados:** base = X + sufijo ∈ {UP, DOWN, BULL, BEAR}, donde X es la base de otro par USDT del conjunto de símbolos.
  - La lista resultante se congela en F3, con hash, antes de calcular retornos.
- **Duplicados:** si dos candidatos tienen una correlación de Pearson de los retornos diarios en [t−90, t−1] > 0,98 (con ≥ 60 días activos en común), se excluye el de **menor** V.
  - Se aplica en orden de V descendente.

### 4.5 Universos y señal
- **Orden de liquidez:** los elegibles se ordenan por V descendente; los empates, por símbolo ascendente.
  - **U30** = los 30 primeros; **U100** = los 100 primeros (o todos, si hay menos).
- **Retornos de formación:** para h ∈ {7, 14, 21, 28}, R_{s,h} = ln(C_{t−1} / C_{t−1−h}). Por la regla (a) y la (b), ambos cierres son de días activos.
- **Rango percentil dentro del universo U** (U100 para H1 y U30 para la cartera), con n = |U|:
  - p_{s,h} = (rango ascendente de R_{s,h} − 1) / (n − 1), con rangos promedio en los empates.
- **Señal:** S_s = (p_{s,7} + p_{s,14} + p_{s,21} + p_{s,28}) / 4.
- **Orden de la señal:** por S descendente; empates por V descendente y después por símbolo.
  - **rk(s)** = posición en U30 (1 = la mejor).

### 4.6 Selección de 6 entre 30, con permanencia entre los 12 primeros
- **Conjunto objetivo T_t:**
  1. **Se quedan:** las que están en cartera, siguen en U30_t y tienen rk ≤ 12.
  2. **Entran:** recorriendo U30_t por rk ascendente, las que no están en cartera, hasta completar 6.
- **Salen:** las de la cartera que no están en T_t, incluidas las que dejaron U30 por cualquier motivo.

### 4.7 Pesos y rebalanceo
- **Valor de la cartera en la ejecución:** W = efectivo + Σ unidades × O_t (o P_val si s no tiene apertura activa).
- **Caso general:**
  - lo obtenido de las ventas, neto de costos, se reparte **en partes iguales** entre las entradas;
  - las que se quedan **no** se tocan.
- **Vuelta a pesos iguales** (todas las de T_t a W/6, neto de costos de cada operación) en dos casos:
  - el **primer lunes de formación de cada mes calendario**;
  - si en la ejecución algún peso es > 1/3.
- **Sin apalancamiento.** El efectivo residual (redondeo o falta de apertura) queda en USDT, al 0 %.
- **Lugar vacante:** si una entrada no tiene apertura activa en t, su parte queda en efectivo hasta la formación siguiente.

### 4.8 Ejecución y costos
- Precio de ejecución: **O_t** (apertura oficial del lunes).
- **Costo por lado** sobre el valor negociado:
  - comisión de 10 pb (Binance VIP 0 sin descuento BNB; la tabla de Binance global se confirma antes de congelar);
  - más spread y slippage según el orden de liquidez en t: posiciones 1–2: 5 pb; 3–10: 10 pb; 11–30: 20 pb;
  - las monedas fuera de U30 que se venden usan 30 pb.
- **Compras:** unidades = asignación / (O_t × (1 + c)). **Ventas:** se cobra unidades × O_t × (1 − c).

### 4.9 Datos faltantes, exclusiones y semanas no evaluables
- **Venta sin apertura activa en t:** se vende en la primera apertura activa posterior. Si no la hay en 30 días, se vende al último cierre activo (fin de cotización).
  - Lo obtenido se reasigna en la formación siguiente.
- **Fin de cotización con posición abierta:** se vende al **último cierre activo** con el costo de su tramo; el dinero queda en efectivo hasta la formación siguiente.
  - Estrés en R6: −30 % sobre ese valor.
- **Renombres mapeados:** la posición continúa con la relación de canje, sin costo.
- **Semana evaluable:** en t hay ≥ 30 elegibles.
  - En una semana no evaluable no hay entradas, salidas por la banda ni vuelta a pesos iguales: solo salidas por fin de cotización.
  - Esa semana no entra en ninguna prueba; sí en la curva descriptiva.
- **Inicio de H:** el primer lunes t₀ con 13 semanas seguidas evaluables, en un año que cumpla V-S1.
  - Si más del 20 % de las semanas entre t₀ y el fin no son evaluables, el resultado es **INVÁLIDO**.

### 4.10 Referencias
- **EW-U30:** el mismo motor con T_t = U30_t.
  - Entran y salen al cambiar la composición; lo vendido se reparte entre las que entran.
  - Vuelve a 1/30 el primer lunes de cada mes, o si algún peso es > 2/30.
  - Mismos costos.
- **BTC buy and hold:** BTCUSDT comprada en O_{t₀}, una sola operación.
- **Efectivo:** 0 %.
- **Exposición equivalente:** la base está siempre invertida, así que su exposición equivalente es EW-U30. Para H3, ver §6.

### 4.11 Cálculo de las métricas
- **H1:** IC_t = Spearman(S_s, y_s) entre las s de U100_t con O_t activa.
  - y_s = ln(O_{s,t+7} / O_{s,t}), con O_{s,t+7} = la primera apertura activa en [t+7, t+14].
  - Si s deja de cotizar antes, se usa su último cierre activo. Si sigue listada pero no tiene apertura activa en [t+7, t+14], se usa P_val(s, t+6), su último cierre activo anterior a t+7.
  - IC̄ es la media de las semanas evaluables; se informa también el número medio de monedas por semana.
- **H2:** r_t = W_{t+7} / W_t − 1 para la cartera y para EW-U30, ambas netas. W_t es el valor en O_t **antes** de operar, así que los costos de t quedan dentro de r_t. El exceso semanal es e_t = r_cartera − r_EW. La métrica es 52 × media(e_t).
- **Nulo aleatorio (para R5):**
  - cada semana, S se reemplaza por una permutación aleatoria (semilla 20261021, 2000 réplicas), con la misma mecánica;
  - se compara el exceso **bruto**, sin costos, para que la mayor rotación del azar no sesgue la comparación;
  - p_nulo = fracción de réplicas con exceso bruto ≥ el de la estrategia.

---

## 5. Criterios separados (punto 5)

### 5.1 Predictivo (H1)
| Resultado | Condición |
|---|---|
| **INFORMACIÓN CONFIRMADA (histórica)** | H1 rechaza con Holm |
| **EN CONTRA (sin información relevante)** | Límite superior del IC90 bilateral de IC̄ (= límite unilateral del 95 %) < **0,01** |
| **INSUFICIENTE** | Cualquier otro caso |

**Por qué 0,01:** es el menor efecto **económicamente relevante** [Hip].
- Para una cartera del quintil superior, la ganancia bruta esperada frente al universo es ≈ IC × σ_cs × E[z | quintil superior] × 52 (aproximación lineal de la «ley fundamental»).
- Con σ_cs (dispersión transversal semanal) de 8–12 % y E[z] = 1,40, **IC 0,01 ≈ 6–9 %/año bruto**.
- El lastre relativo de costos frente a EW-U30 es ≈ 3,5–5 %/año [Hip].
- Por lo tanto:
  - **IC ≈ 0,005–0,007 es el punto de equilibrio**;
  - **0,01 es el menor valor con ganancia neta plausible**;
  - debajo de 0,01 el efecto no compensaría la incertidumbre de los costos.

**Por qué el IC90:**
- Su límite superior es el límite unilateral del 95 %. «En contra» es entonces una **prueba de equivalencia (TOST) al 5 %**: si la correlación verdadera fuera 0,01, la probabilidad de descartarla por error es ≤ 5 %.
- Es simétrica con el 5 % de error al confirmar.
- Un intervalo del 80 % descartaría más a menudo, pero con 10 % de descartes erróneos de efectos relevantes.
- El 0,01 y el 90 % quedan fijos. Si los revisores proponen otros valores, se cambian **antes** de congelar.

**Consecuencia honesta** (§5.5):
- aun si la correlación verdadera es 0, «en contra» saldría solo ≈ 28–40 % de las veces;
- lo más probable sería «insuficiente».

**Regla de decisión, separada de la estadística:** si H1 no queda **confirmada**, no se sigue con la familia (ni ventana ciega, ni papel, ni variantes). Se registra como insuficiente o en contra.

### 5.2 Rentabilidad neta frente a referencias
| Resultado | Condición |
|---|---|
| **VENTAJA NETA DE SELECCIÓN (histórica)** | H2 rechaza con Holm |
| **EN CONTRA (económico)** | Límite superior del IC90 de 52 × media(e_t) < 0 |
| **INSUFICIENTE** | Cualquier otro caso |

**Comparaciones descriptivas, sin decisión, con IC90 por el mismo bootstrap:**
- **frente a BTC buy and hold:** exceso neto. Está dominado por el beta de las altcoins frente a BTC, no por el mecanismo; su potencia es casi nula (tracking error ≈ 50–60 %/año [Hip]);
- **frente al efectivo:** retorno absoluto;
- **para todas:** CAGR, volatilidad, Sharpe (y su versión deflactada), Sortino, caída máxima, CVaR del 5 % semanal, peor semana, tiempo bajo el agua y beta frente a BTC;
- **independencia:** correlación del exceso de selección e_t con BTC y con el exceso de timing de T (reglas congeladas).

### 5.3 Robustez de la base (solo endurece; se evalúa si H2 rechaza y se informa siempre)
| | Condición |
|---|---|
| R1 | Exceso neto > 0 con **costos ×2** |
| R2 | Exceso neto > 0 con **ejecución un día después** (apertura del martes), aplicada igual a la cartera y a EW-U30 |
| R3 | IC̄ > 0 y exceso neto > 0 en **al menos 2 de 3 tercios** consecutivos de las semanas evaluables |
| R4 | Sin la moneda que más aporta al exceso acumulado (re-simulado con ella no elegible), el exceso neto sigue > 0 |
| R5 | p_nulo ≤ 0,05 (selección aleatoria, exceso bruto) |
| R6 | Exceso neto > 0 con −30 % en las salidas por fin de cotización |

**ROBUSTA** si se cumplen las seis. Si no, **NO ROBUSTA** y se informa cuál falla.

### 5.4 Clasificación conjunta y qué permite
| Clasificación | Condición | Qué permite |
|---|---|---|
| **INVÁLIDO** | Falla la validez (§8) | Nada. Se documenta |
| **RESPALDADA HISTÓRICAMENTE** | H1 confirmada, H2 con ventaja neta y ROBUSTA | Habilita H3 (§6), la ventana C (con autorización) y P |
| **INFORMACIÓN SIN VENTAJA OPERABLE** | H1 confirmada, pero no la fila anterior | Solo P de la **base** como seguimiento de información (decisión tuya). Sin capital |
| **INSUFICIENTE / EN CONTRA** | H1 no confirmada | Cierre de la familia con estas reglas |

**Ninguna clasificación autoriza capital.**

### 5.5 Potencia y lo que no podrá concluir
**H1**, con ≈ 330–360 semanas, un desvío de IC_t de 0,12–0,16 [Hip] y Newey–West, da un error estándar de IC̄ ≈ 0,007–0,0095:

| IC verdadero | Potencia (umbral 0,025) | Potencia (umbral 0,05) | P(«en contra») |
|---|---|---|---|
| 0 | — | — | 0,28–0,40 |
| 0,005 | — | — | 0,13–0,17 |
| 0,01 | 0,18–0,28 | 0,28–0,40 | ≤ 0,05 |
| 0,02 | 0,56–0,79 | 0,68–0,87 | ≈ 0 |
| 0,03 | 0,88–0,99 | 0,93–0,99 | ≈ 0 |

El efecto mínimo detectable con 80 % es **IC ≈ 0,020–0,027**, es decir ≈ 12–23 %/año bruto según σ_cs.

**H2:** con un tracking error de ≈ 25–35 %/año [Hip] y ≈ 6,5–7 años, el error estándar es ≈ 10–14 %/año y el **efecto mínimo detectable ≈ 28–39 %/año**. Potencia para un exceso neto verdadero de 10 %/año: 0,11–0,17; de 20 %/año: 0,30–0,52.

**No podrá concluir:**
1. que una ventaja neta **realista** (5–20 %/año) exista o no exista: H2 casi seguro dará «insuficiente» en ese rango;
2. nada sobre la comparación con BTC;
3. que un resultado favorable sea **independiente** del conocimiento del período;
4. la capacidad, la ejecución real y el decaimiento futuro;
5. si la correlación verdadera está entre 0 y 0,02: en ese rango, lo más probable es «insuficiente».

---

## 6. Filtro de tendencia: prueba incremental posterior (punto 6)
- **Fuera de la estrategia base.** La base usa solo rangos relativos (S). El filtro usa el **nivel absoluto** A_s = (R_{s,7} + R_{s,14} + R_{s,21} + R_{s,28}) / 4. Las dos señales no se combinan en la base.
- **Compuerta, fijada ahora:** H3 se ejecuta **solo si** la base es **RESPALDADA HISTÓRICAMENTE** (§5.4). Si no, H3 queda **NO HABILITADA** y no se calcula.
- **El código y los parámetros de H3 se congelan junto con este protocolo.** Se ejecuta una vez, después de registrar con hash la clasificación de la base.
- **Variante filtrada F:**
  - mismo T_t, misma mecánica y mismos pesos que la base;
  - pero cada moneda de T_t con A_s ≤ 0 en t **no se compra o se vende**, y su parte queda en efectivo, **sin reemplazo**;
  - se reevalúa cada semana;
  - mismos costos, incluidos los de pasar a efectivo y volver.
- **Métrica:**
  - ē = exposición media de F en H;
  - exceso de timing semanal = r_F − ē × r_base (ambas netas);
  - anualizado × 52;
  - inferencia como H2, con p₃.
- **Criterios:**

| Resultado | Condición |
|---|---|
| **FAVORABLE** | p₃ ≤ 0,05 (gatekeeping), exceso con costos ×2 > 0 y caída máxima de F < la de la base |
| **EN CONTRA** | Límite superior del IC90 < +2 %/año (el mismo umbral de relevancia de E2-B) |
| **INSUFICIENTE** | Cualquier otro caso |

- **Potencia** [Hip]: el error estándar es ≈ 8–12 %/año (cartera de altcoins más volátil que BTC), así que el **efecto mínimo detectable es ≈ 22–34 %/año**. Lo esperable es «insuficiente».
- **No podrá concluir:** que el filtro reduzca el riesgo de cola de forma significativa, porque las caídas son pocas y la potencia para métricas de caída es mínima.
- **Si es FAVORABLE,** F entra en P **como estrategia aparte** de la base, nunca en su lugar.

---

## 7. Datos y autorización (punto 7)

### 7.1 Qué se descargaría (A2: histórico)
| Elemento | Ruta | Cantidad estimada [Hip] | Tamaño |
|---|---|---|---|
| Listado de símbolos | Listado del bucket `data.binance.vision`, prefijo `data/spot/monthly/klines/` con delimitador `/`. **Por verificar:** es el listado S3 que usa la propia web | 1–5 solicitudes | < 1 MB |
| Listado por símbolo USDT | Prefijo `data/spot/monthly/klines/{S}/1d/` | 600–1000 solicitudes | 15–35 MB (XML) |
| Klines 1d mensuales | `data/spot/monthly/klines/{S}/1d/{S}-1d-{AAAA-MM}.zip`, de 2017-08 a **2026-05**, para todo S terminado en USDT | 21 000–50 000 archivos (≈ 2,2 KB cada uno, medido en los archivos locales de BTC) | 46–110 MB |
| Checksums | `….zip.CHECKSUM` | Igual número (≈ 88 B cada uno) | 2–4 MB |
| Reparaciones (condicional) | `data/spot/daily/klines/{S}/1d/{S}-1d-{AAAA-MM-DD}.zip` más `.CHECKSUM`, solo para meses sin archivo mensual o con checksum fallido | Desconocido; se informa | Pequeño |
| exchangeInfo (instantánea) | `GET https://api.binance.com/api/v3/exchangeInfo` | 1 | Unos MB |
| **BTCUSDT y ETHUSDT** | **No se vuelven a bajar.** Se reutilizan los locales (2017-08 → 2026-05, ya verificados) | 0 | 0 |

- **Total:** ≈ 65–150 MB y ≈ 43 000–101 000 solicitudes.
- A ≤ 5 solicitudes por segundo, con espera ante 429 o 5xx: **≈ 2,5–6 h**.
- Gratis. Sin dependencias nuevas: la biblioteca estándar más numpy del entorno de E1.
- **Período:** hasta **2026-05-31**. **No** se descarga nada del 2026-06 en adelante hasta que autorices C.
- **No se descarga:** futuros, funding, trades, aggTrades, otros intervalos, otros exchanges ni datos pagos.

### 7.2 Anuncios oficiales (A3)
| Categoría | URL oficial [Doc] | Para qué | Volumen estimado [Hip] |
|---|---|---|---|
| Delisting | `https://www.binance.com/en/support/announcement/list/161` | V-S1, V-S3 | Cientos de anuncios (2018–2026), de los que entran solo los de spot contra USDT |
| New Cryptocurrency Listing | `…/list/48` | V-S2 (muestra de 50) | — |
| Latest Binance News | `…/list/49` | Renombres y canjes | Decenas |

- **Método:**
  - lectura de las páginas públicas, a ritmo bajo, guardando para cada anuncio el título, la URL, la fecha, la fecha efectiva y los pares;
  - antes de empezar, reviso las condiciones de uso de Binance sobre acceso automatizado;
  - si no lo permiten, la compilación es **manual** (estimo varias horas).
- **La compilación se completa y se fija con hash antes de calcular cualquier retorno.**

### 7.3 Autorizaciones, por separado
| | Decisión | Cuándo |
|---|---|---|
| A1 | Aprobar este protocolo, con los cambios de la revisión: incluye elegir entre gatekeeping y Holm m = 3, y confirmar el 0,01 y el 90 % | Antes de todo |
| A2 | Descarga histórica del §7.1 | Después de A1 y de congelar |
| A3 | Lectura y compilación de anuncios oficiales (§7.2), incluido el método si es automatizado | Con A2 |
| A4 | Ventana ciega C: usar el reservado de H-CARRY para esta hipótesis y descargar los datos de 2026-06 → congelación | Solo si H da «respaldada» |
| A5 | Evaluación prospectiva P | Solo si H da «respaldada» (o «información sin ventaja», si querés seguirla) |

---

## 8. Validez (antes de interpretar; si falla, se detiene)
1. **Checksums:** 100 % verificados; 0 discrepancias sin resolver.
2. **Supervivencia:** V-S1 a V-S6 (§2.4).
3. **Listas congeladas en F3:** apalancados, duplicados en la primera aparición, renombres y anuncios conciliados, con hash antes de cualquier retorno.
4. **Separación de etapas por código:** la etapa de calidad no importa funciones de rendimiento; se demuestra con una prueba.
5. **Sin mirada al futuro:**
   - comprobaciones automáticas: ninguna formación en t usa días ≥ t;
   - ninguna ejecución usa precios anteriores a t;
   - invariancia al truncar los datos en 5 cortes al azar (semilla 20261022): universos, señales, conjuntos objetivo y pesos idénticos hasta cada corte.
6. **Pruebas sintéticas:**
   - con un nulo verdadero, el rechazo de H1 debe ser ≤ 7 % en 500 simulaciones;
   - con un IC plantado de 0,03, la detección debe ser ≥ 70 % (coherente con §5.5);
   - el bootstrap de H2 debe estar calibrado bajo el nulo (rechazo 3–7 %).
7. **Semanas no evaluables:** ≤ 20 % dentro de H.
8. **Bloqueo de fechas:** cualquier lectura ≥ 2026-06-01 falla sin A4; se demuestra con una prueba.

## 9. Fuera de alcance
- Cortos y perpetuos.
- Otros exchanges o cotizaciones.
- Aprendizaje automático o CTREND.
- Funding transversal.
- Tamaño.
- Combinar la señal con T.
- Cualquier variante fuera del ítem 29 del §3.3.
- Cualquier otra familia.

## 10. Restricciones
- E1, E2, T, T-MULTI y sus artefactos: sin cambios.
- Repositorio: sin cambios; sin commits ni pushes.
- Sin dinero real.
- Este documento no se congela ni se ejecuta hasta tu decisión explícita.

## Fuentes de documentación consultadas
- Binance public data (README; estructura, columnas y marcas en µs desde 2025): https://github.com/binance/binance-public-data/
- Issue #201 (velas tras la exclusión, con precio arrastrado y 0 operaciones): https://github.com/binance/binance-public-data/issues/201
- Anuncios de Binance, categoría Delisting (y enlaces a las demás): https://www.binance.com/en/support/announcement/list/161
- Tardis.dev, cobertura de Binance spot: https://docs.tardis.dev/historical-data-details/binance
- Estados de símbolo en exchangeInfo (TRADING, HALT, BREAK): https://developers.binance.com/docs/zh-CN/binance-spot-api-docs/rest-api/general-endpoints
