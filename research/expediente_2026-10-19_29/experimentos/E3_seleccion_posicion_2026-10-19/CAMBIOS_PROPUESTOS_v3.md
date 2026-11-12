# E3: cambios propuestos a la v2 (revisión metodológica final; NO CONGELADO)

**Alcance:**
- Este documento contiene **solo los cambios propuestos** a `PROTOCOLO_E3_v2_BORRADOR.md` y su justificación.
- La v2 no se modificó: su hash sigue en `SHA256SUMS`.
- No se descargó nada, no se ejecutó ninguna prueba, no se instaló nada y el repositorio sigue igual.
- Si aprobás estos cambios, la v3 será la v2 con ellos aplicados, y recién entonces se congela.

**Regla que seguí:**
- **Ningún umbral se mueve para mejorar las probabilidades de éxito** (ver §8).
- Los cambios corrigen la validez, cierran ambigüedades o vuelven el protocolo **más estricto**.

---

## Resumen
| # | Punto | Sección de la v2 | Problema | Cambio | Efecto sobre la probabilidad de éxito |
|---|---|---|---|---|---|
| 1 | H2: inferencia | §3.1, §5.2, §6, §8.6, §3.3-27 | p₂ = 1 − P(réplicas > 0) no es un contraste construido bajo H₀ | Contraste de **bootstrap-t por bloques circulares bajo H₀** (serie centrada, estadístico studentizado); IC90 percentil-t como su dual; calibración sintética obligatoria | Neutro o más estricto |
| 2 | Supervivencia | §2.4, §4.9 | Umbrales del 95 %/90 % y ambiguos fuera del denominador | Todo se informa por año en 6 categorías; los ambiguos entran en el denominador; **cero fallas dentro de la ventana H** | Más estricto |
| 3 | H1: horizonte | §4.11, §3.3-26 | Retornos de 7 a 14 días o truncados, mezclados | **Horizonte calendario fijo de 7 días**, de cierre a cierre, con marcas definidas para huecos y exclusiones | Neutro (sesgo de microestructura conservador) |
| 4 | Antigüedad | §3.3-5 frente a §4.3(b) | «180 días activos» frente a «180 días calendario» | **Una sola definición:** 180 días **calendario** desde el primer día activo del listado vigente | Neutro |
| 5 | Precios | §4.2, §4.7–4.9 | Mezcla de precio de valuación y precio ejecutable; liquidación sin fecha de registro | P_val y P_exe separados; reglas para aperturas faltantes; **liquidación contable** de pares excluidos sin mirar al futuro | Neutro o más estricto |
| 6 | Potencia y cierre | §5.5, §5.1 | Ya explícita; falta prohibir compensaciones | Cláusula de cierre: si sale «insuficiente», no hay pruebas ni variantes nuevas | Más estricto |
| 7 | Auditoría | Varias | 14 contradicciones o ambigüedades (§7) | Correcciones puntuales | Neutro o más estricto |

---

## 1. H2: contraste válido bajo H₀ (reemplaza p₂ = 1 − P)

### 1.1 Por qué el método actual no sirve
- El bootstrap de la v2 remuestrea la serie e_t **sin centrar**. Su distribución está centrada en la media muestral ē, no en 0.
- La proporción de réplicas con media ≤ 0 aproxima un valor p solo si la distribución es simétrica y aproximadamente normal (método percentil, de primer orden).
- Con retornos semanales de altcoins (colas pesadas, asimetría, volatilidad que se agrupa), puede estar descalibrada en cualquier dirección.
- Viola las dos reglas básicas de un contraste por bootstrap ([Pub\*] Hall y Wilson, 1991):
  1. remuestrear de modo que se cumpla H₀;
  2. usar un estadístico (aproximadamente) pivotal, es decir, studentizado.

### 1.2 Método propuesto (criterio principal de H2 y H3)
- **Hipótesis:** H₀: μ ≤ 0 frente a H₁: μ > 0, con μ = E[e_t] (exceso semanal neto). Se contrasta en la frontera μ = 0.
- **Estadístico observado:** T = ē / (σ̂_C / √n). σ̂²_C es la varianza de largo plazo por bloques circulares de longitud ℓ = 13:
  - σ̂²_C = (ℓ / n) · Σ_{i=1}^{n} (B̄_i − ē)²;
  - B̄_i = media de e_i … e_{i+ℓ−1}, con índices circulares.
- **Bootstrap bajo H₀:**
  1. Se centra la serie: ẽ_t = e_t − ē (así su media es exactamente 0 y se cumple H₀).
  2. Bootstrap circular por bloques ([Pub\*] Politis y Romano, 1992): k = ⌈n/ℓ⌉ bloques de ℓ = 13, recortado a n.
  3. En cada réplica b: T*_b = ē*_b / (σ̂*_b / √n), con σ̂*²_b = (ℓ / k) · Σ_{j=1}^{k} (B̄*_{b,j} − ē*_b)², la varianza entre los bloques remuestreados ([Pub\*] la studentización por bloques de Götze y Künsch, 1996).
  4. B = 9 999 réplicas, semilla 20261020.
- **Valor p:** p₂ = (1 + #{b : T*_b ≥ T}) / (B + 1).
- **IC90 (dual, para «en contra» y lo descriptivo):** percentil-t. Con q*_α = cuantiles de T*:
  - IC90 = [ē − q*_{0,95} · σ̂_C/√n, ē − q*_{0,05} · σ̂_C/√n];
  - por construcción, p₂ ≤ 0,05 ⇔ límite inferior del IC90 > 0 (salvo la granularidad de B).
- **H3** usa exactamente el mismo método sobre su serie de exceso de timing.
- **Las comparaciones descriptivas** (BTC, efectivo) usan el mismo IC90 percentil-t, sin valor p.

**Por qué este método y no otro:**
- El bootstrap-t con bloques es preciso de segundo orden para medias de series débilmente dependientes, mientras que la aproximación normal y el percentil son de primer orden ([Pub\*] Götze y Künsch; Lahiri, 2003).
- Respeta la dependencia (bloques de un trimestre) sin suponer normalidad.
- Centrar es válido porque, en el bootstrap circular, E*[ē*] = ē exactamente.
- Un t de Newey–West con referencia normal sería la alternativa simple, pero menos fiable con colas pesadas y n ≈ 340. Queda como **red de seguridad conservadora** (§1.3).

### 1.3 Calibración (es un control de validez antes de los datos reales: §8.6 de la v2, reemplazado)
**Procesos sintéticos fijados ahora:** n = 340, media verdadera exactamente 0, desvío semanal del 5 % (≈ 36 %/año, del orden del tracking error supuesto), 1000 simulaciones por proceso con B = 1999 réplicas internas y semilla 20261023.

| Proceso | Descripción |
|---|---|
| G1 | i.i.d. t de Student con 3 grados de libertad, escalada |
| G2 | AR(1) con φ = 0,2 e innovaciones t(3) |
| G3 | GARCH(1,1) con α = 0,10, β = 0,85 e innovaciones t(4) |
| G4 | Asimetría positiva: mezcla 90 % N(−0,6 %, 3,5 %) + 10 % N(+5,4 %, 10 %), con media exactamente 0 |
| G5 | Espejo de G4 (asimetría negativa) |

**Criterios** (±2 errores estándar de Monte Carlo con 1000 simulaciones):
- tasa de rechazo al 5 % dentro de **[3,6 %, 6,4 %]**;
- al 2,5 %, dentro de **[1,5 %, 3,5 %]**.

| Resultado de la calibración | Regla |
|---|---|
| Rechaza **menos** que la banda (conservador) | Se acepta y se informa |
| Rechaza **más** que la banda, en cualquier proceso | Se repite con ℓ = 26 |
| Sigue rechazando de más | Se usa p₂ = máx(p_boot(ℓ=13), p_boot(ℓ=26), p_NW), siendo p_NW el t de Newey–West (Bartlett, 13 rezagos, referencia normal). Esta regla solo puede **subir** el p |

- **Potencia** (informativa, sin criterio): tasa de rechazo con μ = +30 %/año en G1–G5.
- **Diagnóstico con datos reales** (sin decisión salvo la regla conservadora):
  - se aplica el mismo contraste al **exceso bruto** de las 2000 carteras aleatorias de R5 frente a EW-U30 bruto, con B = 999;
  - por simetría, su media esperada es ≈ 0;
  - la tasa de rechazo al 5 % se informa;
  - si supera el **9 %**, se aplica la regla de máximo de arriba.
  - Se calcula **antes** del exceso de la estrategia, dentro de la ejecución registrada.

**H1 se mantiene** con un t de Newey–West (Bartlett, 4 rezagos, sin preblanqueo, referencia N(0,1)). La serie IC_t es acotada y casi normal. Su calibración se armoniza:
- proceso AR(1) con φ = 0,1, desvío 0,14 y n = 340, en 1000 simulaciones;
- mismas bandas de [3,6 %, 6,4 %] al 5 % y [1,5 %, 3,5 %] al 2,5 %;
- si rechaza de más, se usan 8 rezagos; si persiste, el máximo de los dos p.

---

## 2. Supervivencia: informe completo y regla sin tolerancia dentro de la ventana

### 2.1 ¿Pueden los umbrales de la v2 ocultar una selección sesgada? **Sí, por cinco vías:**
1. **Faltantes que no son al azar.** Los pares que no figuran suelen ser los que colapsaron. Un 5 % de faltantes en el total, o un 10 % en un año, concentrados en colapsos, sesga hacia arriba los retornos con peso igual: Ammann et al. estiman 62 %/año de sesgo en carteras de peso igual. EW-U30 y H1 (correlación de rangos, peso igual por moneda) son sensibles a eso.
2. **Ambiguos fuera del denominador.** Los anuncios más viejos o menos claros tienden a ser los de años con archivos más débiles. Excluirlos eleva la cobertura justo donde está el problema.
3. **Archivos truncados que parecen fin anticipado.** Si Vision no tiene los últimos meses de un par que se derrumbó, su último día activo cae antes de la fecha anunciada. La v2 lo vería como «fin anticipado» legítimo, cuando en realidad **falta el derrumbe**.
4. **Exclusiones sin anuncio o anuncios ausentes** del archivo web en los primeros años: los anuncios no las pueden detectar.
5. **El listado del bucket como única fuente de símbolos.** Si omite en bloque los pares excluidos, la conciliación lo detecta, pero solo si el archivo de anuncios llega a esos años.

### 2.2 Categorías por anuncio (todas se informan y **todas entran en el denominador**)
**Universo de anuncios:**
- todos los de la categoría Delisting con fecha efectiva entre 2018-01-01 y 2026-05-31 que **eliminen un par spot contra USDT**;
- también las exclusiones de token completo, salvo que el texto liste explícitamente los pares y USDT no figure.

| Categoría | Definición | ¿Falla? |
|---|---|---|
| **A: conciliado** | Par presente; último día activo entre la fecha efectiva − 7 días y + 1 día | No |
| **B: fin anticipado con archivos** | Último día activo antes de la fecha efectiva − 7 días, **y** existen los archivos de todos los meses hasta la fecha efectiva (con velas de 0 operaciones o sin negociación documentada) | No (se informa) |
| **T: truncado** | Último día activo antes de la fecha efectiva − 7 días, **y** faltan archivos de algún mes entre el último día activo y la fecha efectiva | **Sí** |
| **C: actividad posterior** | Días activos después de la fecha efectiva + 1 día | **Sí**, salvo un relisting o una corrección de fecha documentados en otro anuncio oficial |
| **D: sin datos** | El par no está en el listado del bucket o no tiene ningún archivo | **Sí** |
| **E: ambiguo** | El anuncio no permite fijar el par o la fecha | Se resuelve con la mejor lectura documentada y después se clasifica en A–D. **No sale del denominador.** Si no tiene datos, cuenta como D |

**Tabla que se entrega, por año calendario:**

| Columna | Contenido |
|---|---|
| Total | Anuncios relevantes |
| A, B, T, C (explicadas / no explicadas), D, E | Cuántos de cada categoría (E: cómo se resolvió cada uno) |
| Cobertura conservadora | (A + B) / total, con los ambiguos dentro |
| Cobertura sin ambiguos | Solo informativa |
| Salidas sin anuncio | Pares cuyo fin de cotización no corresponde a ningún anuncio |
| Primer anuncio disponible | Fecha más antigua que muestra el archivo web de la categoría |

### 2.3 Regla de validez (reemplaza las decisiones del §2.4 de la v2 y la frase «en un año que cumpla V-S1» del §4.9)
1. **Falla** = categoría T, D o C no explicada.
2. **Dentro de la ventana H no puede haber ninguna falla.** El inicio de H es el más tardío de estos cuatro:
   - el que surge de la regla de semanas evaluables (§4.9 de la v2);
   - la semana siguiente a la fecha efectiva de la **última falla**;
   - el 1 de enero del primer año con anuncios en el archivo web;
   - el 1 de enero del primer año desde el cual, en todos los años de la ventana, las salidas sin anuncio son ≤ 10 % de las salidas observadas. Si son más, los anuncios no alcanzan para verificar esos años.
3. **Si la ventana resultante tiene < 156 semanas evaluables (3 años): INVÁLIDO con Vision.** Se pasa a la §2.5 de la v2 (fuentes alternativas, con adenda y autorización).
4. **No hay umbrales porcentuales que toleren fallas** dentro de la ventana. El 95 % y el 90 % de la v2 se eliminan.
5. V-S2 (50 listados), V-S3 (10 controles en profundidad), V-S4 y V-S5 se mantienen. Los 10 casos son una comprobación, no prueba de completitud.

**Por qué es más estricta:**
- una falla anterior a la ventana no sesga H, porque ese par nunca habría estado en su universo;
- una falla dentro de la ventana sí, y no se puede corregir sin sus datos;
- adelantar el inicio es honesto, pero **cuesta potencia**: lo informo y no lo compenso (§6).

---

## 3. H1: horizonte fijo y comparable (reemplaza el §4.11 «H1» y el ítem 26 del §3.3)
- **Retorno adelantado de calendario fijo de 7 días, de cierre a cierre:**
  - y_s = ln( P_val(s, t+6) / C_{s,t−1} );
  - C_{s,t−1} = cierre del domingo previo a la formación. Por la regla de elegibilidad (a), t−1 es un día activo, así que **siempre existe**;
  - P_val(s, t+6) = último precio negociado al cierre del domingo t+6 (§5).
  - **Todos** los activos se miden en el mismo intervalo [domingo t−1 23:59:59.999, domingo t+6 23:59:59.999]: misma duración y mismo instante final.
- **Casos fijados de antemano:**

| Caso | Tratamiento |
|---|---|
| Activo en t+6 | P_val = C_{t+6} |
| Inactivo en t+6 pero sigue listado (suspensión) | P_val = último cierre activo ≤ t+6 (**marca obsoleta**): el valor que se le asignaría a una tenencia. Se cuenta y se informa; **no se excluye**, porque excluirlo sería condicionar a información futura |
| Deja de cotizar durante la semana (exclusión del par o del token) | P_val = último cierre activo. El resto de la semana vale 0 % (efectivo), así que la duración sigue siendo 7 días. Se cuenta y se informa |
| Renombre mapeado durante la semana | P_val del símbolo nuevo × relación de canje |
| Sin apertura futura | Ya no se usa ninguna apertura futura en H1 |
| Sin precio de ejecución en t | Irrelevante para H1: la referencia es C_{t−1}, siempre disponible. H1 es predictiva, no operable |

- **Por qué de cierre a cierre y no de apertura a apertura:**
  - evita excluir monedas por no tener apertura el lunes (exclusión con información posterior a la formación);
  - evita duraciones variables (la v2 admitía de 7 a 14 días);
  - el cierre del domingo y la apertura del lunes son el mismo instante en un mercado 24/7.
- **Sesgo conocido:** el cierre C_{t−1} termina la señal y empieza el retorno. El rebote entre compra y venta induce una correlación negativa espuria **en contra** de H1. Es conservador y se declara.
- **Señal única para H1 y H2** (ver la auditoría, A9): S se calcula una vez sobre U100. H2 ordena U30 por esa misma S. Así H1 valida exactamente la señal que H2 opera.

---

## 4. Antigüedad: una sola definición
- **Contradicción:**
  - el ítem 5 del §3.3 de la v2 decía «180 días **activos** desde el primer día activo»;
  - el §4.3(b) decía «primer día activo ≤ t − 180» (días **calendario**).
- **Definición única propuesta:** edad(s, t) = t − primer día activo del **listado vigente** de s, en **días calendario**. Es elegible con edad ≥ 180.
  - **Listado vigente:** se reinicia tras 30 o más días seguidos inactivos (§2.3, regla 3, de la v2), salvo una suspensión documentada por anuncio.
  - Un renombre mapeado hereda el primer día activo del predecesor.
- **Por qué calendario:**
  - el efecto de listado que motiva la regla se mide en tiempo calendario;
  - las inactividades recientes ya las controla la regla (a) (30 días activos seguidos);
  - contar días activos agregaría una segunda condición de huecos y un grado de libertad sin justificación.
- Se corrige el ítem 5 del §3.3 en consecuencia.

---

## 5. Precio de valuación frente a precio ejecutable (reemplaza el §4.2, completa el §4.7–4.9)

### 5.1 Definiciones
| Precio | Definición | Uso |
|---|---|---|
| **P_val(s, τ)**, valuación | Último precio negociado en o antes del instante τ: el cierre del último día activo ≤ τ. Las velas con 0 operaciones no aportan precios | Valor de la cartera, pesos, el tope de 1/3, H1 y las curvas descriptivas. **Nunca** es un precio de transacción |
| **P_exe(s, d)**, ejecutable | Apertura oficial O_d de un **día activo** d | **Única** base de las compras y ventas. El costo por tramo modela el spread y el impacto sobre O_d |

### 5.2 Supuestos para aperturas faltantes
| Caso | Regla |
|---|---|
| **Compra** sin P_exe(s, t) (lunes inactivo) | No se ejecuta. El lugar queda en efectivo hasta la formación siguiente. Sin reintento a mitad de semana |
| **Venta** decidida en t sin P_exe(s, t) | Se reintenta en la apertura de cada día activo siguiente, P_exe(s, d′). Mientras tanto se valúa a P_val. Lo cobrado queda en efectivo hasta la formación siguiente. El costo es el del tramo de liquidez de s **en t** |
| Valor W_t para repartir y comprobar pesos | Σ unidades × (P_exe(s, t) si existe; si no, P_val(s, t)) + efectivo |
| Vuelta a pesos iguales | 1) ventas de las sobreponderadas hasta W/6; 2) compras de las subponderadas con el efectivo disponible; 3) si los costos dejan efectivo insuficiente, todas las compras se escalan en la misma proporción. Determinista |

### 5.3 Pares que dejan de cotizar: liquidación contable, sin mirar al futuro
- Como las reglas no leen anuncios, el motor **no sabe** que un par fue excluido hasta que lo observa inactivo.
- **Regla:**
  - una posición inactiva se valúa a P_val (precio congelado);
  - la venta se intenta en cada apertura activa;
  - **si se acumulan 30 días seguidos inactivos** (o se termina la ventana), se registra **ese día** una **liquidación contable** al último precio negociado: unidades × P_val × (1 − c_tramo).
- **No es un precio ejecutable:** representa vender en las últimas operaciones, y se declara como supuesto.
- **R6** (estrés): −30 % sobre ese valor.
- **El lugar queda ocupado** por la posición congelada hasta la liquidación, y recién se repone en la formación siguiente. Ese efectivo inmóvil es el costo realista de no reaccionar a anuncios.
- La exclusión de un par USDT con el token vigente en otros pares recibe el mismo trato.
- En H1, la misma lógica: el último precio negociado y después efectivo (§3).

---

## 6. Potencia y cierre: cláusula nueva (se agrega al §5.5)
- **Se mantiene explícito:**
  - H2 tiene potencia de **0,11–0,17 para una ventaja neta verdadera del 10 %/año**, y de 0,30–0,52 para un 20 %/año;
  - **lo más probable para una ventaja moderada es «insuficiente»**;
  - H1 detecta correlaciones de rangos ≳ 0,02–0,027.
  - Si la regla de supervivencia (§2.3) adelanta el inicio, la potencia **baja** y se informa cuánto.
- **Cláusula de cierre:**
  - si H1 no queda confirmada, **o** H2 sale insuficiente, **no** se agrega nada para compensar:
    - ni períodos, universos, horizontes, k ni bandas;
    - ni costos alternativos ni combinaciones con T o con el filtro;
    - ni umbrales más laxos ni métodos de inferencia alternativos;
  - la grilla de sensibilidad (ítem 29) **no** puede usarse para afirmar nada;
  - la única continuación posible de la familia es una **hipótesis nueva**, con prerregistro propio, evaluada **solo de forma prospectiva**.

---

## 7. Auditoría: contradicciones y ambigüedades encontradas
| # | Dónde | Problema | Corrección |
|---|---|---|---|
| A1 | §3.3-5 frente a §4.3(b) | Antigüedad en días activos frente a calendario | §4 de este documento |
| A2 | §3.1, §5.2, §6, §8.6, §3.3-27 | Valor p de H2 (y H3) no construido bajo H₀; calibración «3–7 %» sin procesos ni α definidos | §1 |
| A3 | §4.11 frente a §3.3-26 | H1 «de apertura a apertura» con ventanas de 7 a 14 días y retornos truncados | §3 |
| A4 | §4.9 «en un año que cumpla V-S1» frente a §2.4 | Dos reglas de inicio distintas | §2.3: una sola regla |
| A5 | §5.3 «se evalúa si H2 rechaza y se informa siempre» | Contradicción interna | **Se calcula e informa siempre.** Solo afecta la clasificación cuando H1 y H2 rechazan |
| A6 | §3.2 «1 confirmatoria (H1, H2 y el nulo)» más «6 de robustez» | El nulo (R5) se contaba dos veces, y R3 no requiere otra simulación | Ejecuciones planificadas: 1 confirmatoria (H1 y H2); 4 re-simulaciones de robustez (R1, R2, R4, R6); 1 lote del nulo (R5, 2000 réplicas, más el diagnóstico de §1.3); 1 grilla de sensibilidad (**15 configuraciones**: 9 + 4 + 1 + 1); 1 de H3 si se habilita |
| A7 | §3.2, Sharpe deflactado | «Número de intentos = total del registro» era ambiguo | N de intentos = configuraciones evaluadas: 1 + 4 + 15 (+ 1 con H3) = 20–21. Las réplicas del nulo no cuentan como intentos |
| A8 | §5.4 | No cubre H2 rechaza y H1 no. Llama «sin ventaja operable» a H1 + H2 sin robustez | Nueva fila: **VENTAJA NO ROBUSTA** (H1 y H2 rechazan, robustez falla) → solo papel informativo. **H2 sin H1** → «no concluyente», **cierre** (el mecanismo no tiene respaldo; es la prueba de mayor potencia) |
| A9 | §4.5 | S se calculaba distinto en U100 (H1) y en U30 (H2): H1 no validaba la señal operada | S una sola vez en U100; U30 se ordena por esa S |
| A10 | §3.1 Holm | No decía el procedimiento escalonado | Holm m = 2: si el p menor > 0,025, no se rechaza ninguna; si ≤ 0,025, se rechaza y el otro se compara con 0,05. El gatekeeping hacia H3 exige los dos rechazos (sin cambios) |
| A11 | §5.3 R3 y R4 | R3: ¿los mismos 2 tercios para IC y exceso? R4: ¿la moneda se quita también de la referencia? | R3: cada métrica por separado, ≥ 2 de 3. R4: la moneda queda no elegible para **todo** (universos, estrategia y EW-U30) y se re-simulan las dos. Aporte = Σ_t w_{c,t} · (r_{c,t} − r_{EW,t}) bruto |
| A12 | §4.8 | «Posiciones 1–2 / 3–10 / 11–30» se confundía con rk (el orden por la señal); «30 pb» para las que están fuera de U30 era ambiguo | Los tramos son por orden de **liquidez V** en t. Fuera de U30: 30 pb de spread y slippage **más** 10 pb de comisión. Las ventas diferidas usan el tramo de t |
| A13 | §4.10 | BTC buy and hold sin costo de entrada | Una compra en O_{t₀} con 10 + 5 pb |
| A14 | §8.6 | Sin semilla para las simulaciones sintéticas; banda de H1 «≤ 7 %» sin α | Semilla 20261023; bandas de §1.3 para H1 y H2 |

**Revisé y no encontré contradicción en:**
- la compuerta de H3 (§3.1 = §5.4 = §6);
- el uso de C y P (§1.4 = §5.4 = §7.3);
- el fin de H (2026-05-18) frente al bloqueo del 2026-06-01;
- la regla de elegibilidad (a) frente a R_{s,28}, cuyos cierres caen dentro de los 30 días activos;
- la referencia del filtro, ē × r_base: usa ē de todo el período, como la «estática equivalente» de T. Es una construcción de referencia, no una regla operable, y se declara.

---

## 8. Umbrales y parámetros que **no** cambian
- **Decisión de H1:** α 5 %; Holm; «en contra» con el límite superior del IC90 < 0,01.
- **Decisión de H2:** «en contra» con el límite superior del IC90 < 0.
- **Robustez:** R1 costos ×2; R2 1 día de demora; R3 ≥ 2 de 3 tercios; R4 sin la mejor moneda; R5 p_nulo ≤ 0,05; R6 −30 %.
- **H3:** p₃ ≤ 0,05 con la compuerta; «en contra» < +2 %/año; caída máxima menor.
- **Universo y cartera:** piso de liquidez 1 M USDT; 30 días activos; 180 días (ahora calendario, sin ambigüedad); U30 y U100; k = 6; permanencia ≤ 12; reposición y vuelta mensual a pesos iguales; tope de 1/3.
- **Costos y señal:** 10 pb más tramos; horizontes de 7–28 días; formación del lunes.
- **Validez:** ≤ 20 % de semanas no evaluables.
- **Más estrictos que antes:** la regla de supervivencia (§2.3), la regla conservadora de calibración (§1.3), el cierre de «H2 sin H1» (A8) y la cláusula de cierre (§6).
- **Ninguno se relajó.**

## 9. Decisiones que siguen abiertas para vos (sin cambios)
1. Gatekeeping serial (mi recomendación) o Holm m = 3 para H3.
2. Confirmar el 0,01 y el IC90 (fijados en la v2; no los toqué).
3. Aprobar estos cambios para armar la v3. Después, por separado, la congelación y la autorización de datos (A1–A3).
