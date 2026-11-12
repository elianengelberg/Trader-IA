# Prerregistro E3, versión 3 (PROPUESTA; NO CONGELADA; NO EJECUTAR)
## Momentum transversal long-only en Binance spot: experimento de investigación

**Estado (2026-10-20):**
- Es una propuesta para decidir la congelación. No se descargó ningún dato, no se ejecutó ninguna prueba, no se instaló nada y no se modificó el repositorio.
- Si la aprobás, se congela **este** documento con su SHA-256 antes de descargar cualquier archivo de altcoins.

**Propósito y alcance de decisión:**
- E3 es un **experimento de investigación**, no la evaluación de una candidata a inversión.
- **Ninguna** clasificación de este protocolo autoriza capital.
- Los resultados solo informan decisiones de investigación: seguir en papel, cerrar la familia o diseñar una hipótesis nueva prospectiva.

**Etiquetas:** [Hip] supuesto o estimación sin datos · [Doc] verificado en documentación · [TIA] hecho del proyecto · [Pub] literatura (\* = citado de memoria).

---

## 0. Correcciones y jerarquía de documentos

### 0.1 Las seis correcciones indispensables y dónde quedan
| # | Corrección | Sección |
|---|---|---|
| 1 | Multiplicidad: Holm (m = 2) para H1 y H2, y H3 solo si las dos rechazan. **Demostración** del control del error de familia y su alcance | §3.2 y Anexo A |
| 2 | Distinción entre la **evidencia predictiva** de H1 (IC > 0) y la **relevancia económica** (margen δ_IC = 0,01) | §6.1 |
| 3 | Tratamiento contable de las liquidaciones (no son precios ejecutables), estrés del −30 % y etiqueta de dependencia | §4.10 y §6.4 |
| 4 | Especificación reproducible del bootstrap: centrado, studentizado, bloques completos, divisor k − 1 y cuantiles por estadístico de orden | §5.2–5.3 |
| 5 | Supuestos de potencia, sensibilidad, cota conjunta y **limitación para decisiones de inversión** | §7 |
| 6 | Jerarquía de versiones y documentos | §0.2 |

**Ningún umbral, ventana, universo, horizonte ni criterio cambió** respecto de la v2 y de las propuestas revisadas. Los cambios corrigen la validez, cierran ambigüedades o son más estrictos.

### 0.2 Jerarquía de documentos (regla de precedencia)
**Si hay conflicto, prevalece este documento sobre cualquier otro de E3.** Los documentos anteriores se conservan sin cambios, como registro.

| Documento | SHA-256 (inicio) | Estado | Qué conserva su valor |
|---|---|---|---|
| **`PROTOCOLO_E3_v3_PROPUESTO.md`** (este) | Se fija al congelar | **Vigente** si se aprueba | Todo el protocolo |
| `DECISIONES_FINALES_E3.md` | `757f8a16…` | Integrado aquí | Registro de la revisión |
| `CAMBIOS_PROPUESTOS_v3.md` | `502938d9…` | Integrado aquí | Registro de la revisión |
| `PROTOCOLO_E3_v2_BORRADOR.md` | `2131e676…` | **Reemplazado** | El §1.1 (uso previo de datos, con su detalle completo) sigue siendo el registro; aquí se resume sin cambios de contenido |
| `PROTOCOLO_E3_BORRADOR.md` (v1) | `074b99a5…` | **Reemplazado** | Nada normativo |
| `INFORME_E3.md` | `e07fc2b7…` | Informe de investigación | **Siguen valiendo:** §1 (punto de partida), §2.1–2.4 (literatura y lectura crítica), §3 (otras familias), §4.1–4.2 (inventario), §7 (largo plazo) y las fuentes. **Quedan reemplazados por este documento:** §0 (potencia económica 35–45 %/año; capa de efectivo como candidata paralela), §2.5–2.8 (especificación, comparaciones y evaluación), §4.3 (períodos reservados: la reserva 2025–2026 **no** es fuera de muestra), §5 filas 1–2 (experimento mínimo con el período 2019–2024), §6 (dos candidatas en paralelo) y §8 (fases y criterios) |
| `REGISTRO_HIPOTESIS_tras_E3_revision.md` | `068873f5…` | Vigente hasta la congelación | Al congelar se crea una versión nueva que remite a este documento |
| E1, E2, T, T-MULTI y sus artefactos | (sus manifiestos) | **Congelados, intactos** | — |

---

## 1. Uso previo de los datos y períodos (resumen sin cambios de contenido; el detalle completo está en el §1.1 de la v2)

| Línea | Activos | Datos | Período | Uso |
|---|---|---|---|---|
| T, desarrollo (con los cribados V y R) | BTC (y ETH) | Spot 1d | 2017-08-17 → 2021-12-31 | Diseño, cribado y sensibilidad |
| T, fuera de muestra | BTC, ETH | Spot 1d | 2022-01-01 → 2026-05-31 | **Evaluado** |
| T-MULTI | 12 ETF | Diario más dividendos | 2011-01-03 → 2026-09-30 | **Evaluado** |
| T-papel | BTC, ETH | Spot 1d diario | 2026-04-20 → 2026-10-16 | Historia de la señal, no evaluada; se registraron el último cierre y la exposición |
| Monitor del carry | BTC | Funding | 2026-07-03 → 2026-09-30 | Agregado consultado (6,5 %/año) |
| H-CARRY | BTC spot y perpetuo 1h | 1h | 2020-01 → 2026-05 (test 2024-02 → 2026-05, consumido) | **Evaluado** |
| H-CARRY, exploratorio posterior | ETH y SOL (funding), DTB3, Aave | Varios | → 2026-05 | Exploratorio |
| E1 | BTC | Spot 1h | 2019-10-01 → 2026-05-31 | **Evaluado** |
| E2 | BTC, ETH, funding, prima, Wikipedia | Varios | → 2026-05 | **Evaluado** |
| **Altcoins** | — | — | — | **Nunca usadas** por el proyecto |

**Conocimiento de quienes diseñan:**
- el asistente, en términos generales, hasta ≈ junio de 2026;
- el usuario y los revisores vivieron el período;
- la literatura cubre 2013–2023.

**Ningún período anterior a junio de 2026 está intacto.**

**Capas de evaluación:**

| Capa | Ventana | Qué puede concluir |
|---|---|---|
| **H: histórica** (una sola ejecución) | Desde el inicio fijado en §4.11 hasta el **lunes 2026-05-18** | «Evidencia histórica con contaminación declarada», **nunca** confirmación independiente |
| **C: ventana ciega** (opcional) | [2026-06-01, lunes previo a la congelación), unas 20 semanas. Requiere tu autorización (coincide con el reservado de H-CARRY) y que H dé «respaldada» | Solo contradicciones groseras |
| **P: prospectiva** | Desde la congelación, con reglas idénticas | Es la **única** evaluación independiente |

---

## 2. Universo histórico y supervivencia

### 2.1 Fuentes [Doc]
- **data.binance.vision**, klines 1d mensuales de spot con `.CHECKSUM`.
  - Ruta: `data/spot/monthly/klines/{S}/1d/{S}-1d-{AAAA-MM}.zip`.
  - Columnas: OHLC, `quote asset volume` y `number of trades`.
  - Desde 2025-01-01 las marcas de tiempo están en µs.
- **Listado del bucket**, como conjunto de símbolos. No está documentado que conserve los pares excluidos.
- **Anuncios oficiales de Binance:**
  - Delisting `…/announcement/list/161`;
  - New Cryptocurrency Listing `…/list/48`;
  - Latest Binance News `…/list/49`.
- **exchangeInfo**, instantánea actual. Solo para separar el activo base de la cotización.
- **Hallazgo** (issue #201): tras una exclusión puede haber velas con el precio arrastrado y **0 operaciones**. **Que exista un archivo no prueba que el par cotizara.**

### 2.2 Reconstrucción
1. **Símbolos:** los prefijos terminados en `USDT`. Base = símbolo − «USDT», salvo que exchangeInfo indique otra cosa.
2. **Día activo:** vela 1d existente, con operaciones > 0, precios > 0, OHLC coherente, duración de 1 día y sin discrepancia entre el archivo mensual y el diario.
3. **Listado vigente:**
   - empieza en el primer día activo;
   - termina tras 30 días seguidos inactivos, salvo una suspensión documentada en un anuncio;
   - si vuelve a cotizar, es un listado nuevo.
4. **Renombres:** solo con un anuncio oficial (símbolo viejo, símbolo nuevo, fecha y relación de canje). El nuevo hereda la edad y las posiciones.
5. **Par USDT removido con el token vigente en otros pares:** cuenta como salida.
6. **Archivos:** si falta un mensual o su checksum falla, se usan los diarios oficiales. Si para un mismo día discrepan, ese día es inactivo.

### 2.3 Conciliación (en F3, antes de calcular cualquier retorno de estrategia)
**Universo de anuncios:**
- todas las exclusiones o remociones que afectan un **par spot contra USDT**, con fecha efectiva entre 2018-01-01 y 2026-05-31;
- también las exclusiones de token completo, salvo que el texto liste los pares y USDT no esté.

**Categorías** (todas se informan; **todas en el denominador**):

| Cat. | Definición | ¿Falla? |
|---|---|---|
| A | Último día activo entre la fecha efectiva − 7 días y + 1 día | No |
| B | Último día activo antes de la fecha efectiva − 7 días, con todos los archivos mensuales presentes hasta la fecha efectiva | No |
| T | Igual que B, pero falta algún archivo entre el último día activo y la fecha efectiva (truncado) | **Sí** |
| C | Días activos después de la fecha efectiva + 1 día | **Sí**, salvo un relisting o una corrección documentados |
| D | El par no aparece en el listado o no tiene archivos | **Sí** |
| E | Ambiguo | Se resuelve con la mejor lectura documentada y se clasifica en A–D. Si no tiene datos, es D |

**Informe por año calendario:**
- totales y cada categoría (C, separada en explicada y no explicada);
- cobertura conservadora (A + B) / total;
- salidas sin anuncio;
- fecha del primer anuncio disponible en el archivo web.

**Controles adicionales:**
- **V-S2:** 50 listados USDT al azar (semilla 20261025), con ≥ 95 % de primeros días activos dentro de ±3 días del anuncio;
- **V-S3:** 10 exclusiones al azar (semilla 20261026), revisadas a mano;
- **V-S4:** todos los USDT con estado TRADING presentes en el listado;
- **V-S5:** ninguna vela con 0 operaciones en el universo ni en los retornos.

**Regla de validez:** dentro de la ventana H **no puede haber ninguna falla** (T, D o C no explicada). El inicio de H se fija en §4.11. Si la ventana resultante tiene < 156 semanas evaluables, el resultado es **INVÁLIDO con Vision**.

**Si Vision no alcanza:** no hay otra fuente oficial de Binance. Las alternativas no oficiales (Tardis.dev, con todos los pares solo desde 2021-03-05; Kaiko; CoinAPI; agregadores) requieren una adenda y tu autorización.

---

## 3. Hipótesis y multiplicidad

### 3.1 Hipótesis confirmatorias (definidas sin condiciones, antes de los datos)
| | H₀ (nula) | Alternativa | Métrica primaria | Valor p |
|---|---|---|---|---|
| **H1** (predictiva) | E[IC_t] ≤ 0 en U100 | > 0 | IC̄ (§4.13) | p₁: Newey–West (§5.1) |
| **H2** (selección neta) | E[e_t] ≤ 0, siendo e_t el exceso semanal neto frente a EW-U30 | > 0 | 52 · ē | p₂: bootstrap-t bajo H₀ (§5.2) |
| **H3** (filtro incremental) | E[x_t] ≤ 0, siendo x_t el exceso de timing (§8) | > 0 | 52 · x̄ | p₃: igual que p₂ |

### 3.2 Procedimiento (corrección 1)
α = 0,05. Se ordenan p₁ y p₂ (p₍₁₎ ≤ p₍₂₎):
1. **Holm sobre {H1, H2}:**
   - si p₍₁₎ ≤ 0,025, se rechaza la hipótesis correspondiente, y la otra se rechaza si su p ≤ 0,05;
   - si p₍₁₎ > 0,025, no se rechaza ninguna.
2. **H3**, solo si se rechazan **H1 y H2** y además la base es **ROBUSTA** (§6.3). En ese caso se rechaza si p₃ ≤ 0,05. Si no, H3 queda **NO HABILITADA** y no se calcula.

**Control del error de familia:**
- **Teorema** (Anexo A): si cada p_i es un valor p válido bajo su nula (P(p_i ≤ u) ≤ u para u ∈ {0,025; 0,05}), entonces P(rechazar al menos una nula verdadera entre H1, H2 y H3) ≤ 0,05, en **las 8 configuraciones** de nulas verdaderas o falsas y con **cualquier** dependencia entre las pruebas.
  - El procedimiento coincide exactamente con unas **pruebas cerradas**, con pruebas locales de Bonferroni.
  - La exigencia de robustez solo quita rechazos.
- **Alcance:** la familia son **solo los rechazos de H1, H2 y H3**. Quedan **fuera**, sin afirmación controlada por familia:
  - las etiquetas «en contra» y «relevancia demostrada» (§6.1);
  - las condiciones de robustez, incluido el nulo aleatorio R5 (§6.3);
  - la sensibilidad y lo descriptivo;
  - la ventana C y la evaluación P (etapas posteriores, cada una con sus reglas).
- **Aproximación:** p₁, p₂ y p₃ son asintóticos o de bootstrap. El error de familia es ≤ 0,05 más su distorsión de tamaño, que la calibración (§5.3) acota en procesos sintéticos y la regla conservadora protege.

**Por qué este procedimiento:**
- es el mismo de la v2; no se eligió por favorecer resultados;
- la secuencia fija H1 → H2 → H3, también válida, daría **más** potencia a H1 y H2 (umbral 0,05) y no se adopta;
- Holm m = 3 es válido pero está **dominado**: castiga a H1 y H2 por una H3 que solo puede probarse si las dos rechazaron.
- **Orden:** H1 y H2 forman la familia base, y Holm las ordena por su p. La lectura es jerárquica: «H2 sin H1» cierra la familia (§6.5). H3 va última, porque solo tiene sentido con la base respaldada.

### 3.3 Registro de ejecuciones
- `REGISTRO_EJECUCIONES.jsonl` solo admite añadidos. Cada entrada lleva fecha, hashes del código, la configuración y los datos, y su propósito.
- **Lo planificado:**
  - 1 ejecución confirmatoria (H1 y H2);
  - 4 re-simulaciones de robustez (R1, R2, R4, R6);
  - 1 lote del nulo aleatorio (R5, 2000 réplicas, y el diagnóstico de §5.4);
  - 1 grilla de sensibilidad (15 configuraciones);
  - 1 de H3 (solo si se habilita).
- **Cualquier otra ejecución es exploratoria:**
  - se cuenta;
  - no cambia ninguna clasificación;
  - solo puede motivar una hipótesis nueva prospectiva.
- **Sharpe deflactado:** número de intentos = configuraciones evaluadas, 20 (21 con H3). Las réplicas del nulo no cuentan.

### 3.4 Decisiones que podrían generar pruebas adicionales (todas fijadas)
| # | Decisión | Valor fijado |
|---|---|---|
| 1 | Mercado | Binance spot, pares USDT |
| 2–3 | Ventana H | Inicio según §4.11; última formación el lunes 2026-05-18 |
| 4 | Día activo | Operaciones > 0 y OHLC válido (§2.2) |
| 5 | Edad mínima | **180 días calendario** desde el primer día activo del listado vigente |
| 6 | Huecos en la formación | 30 días activos seguidos (t−30 … t−1) |
| 7–8 | Liquidez | Mediana de 30 días de `quote asset volume` ≥ 1 000 000 USDT |
| 9–10 | Universos | U30 (invertible) y U100 (predictivo), por liquidez |
| 11–14 | Exclusiones | §4.5 |
| 15–17 | Señal | Horizontes de 7, 14, 21 y 28 días; media de rangos percentiles en U100; sin período de salto |
| 18 | Calendario | Formación con datos hasta el domingo; ejecución en la apertura del lunes |
| 19–21 | Cartera | k = 6; permanencia con rango ≤ 12; lugares fijos con reposición; vuelta mensual a pesos iguales o con un peso > 1/3 |
| 22–23 | Costos y ejecución | §4.9; precio ejecutable = apertura de un día activo |
| 24 | Fin de cotización | **Liquidación contable** al último precio negociado (§4.10) |
| 25 | Referencia | EW-U30 con la misma mecánica y costos |
| 26 | Métrica de H1 | Spearman semanal; retorno **calendario fijo de 7 días, de cierre a cierre** |
| 27 | Inferencia | §5 (Newey–West de 4 rezagos; bootstrap-t por bloques de 13, B = 9999) |
| 28 | Umbrales | §6 |
| 29 | **Sensibilidad (única, descriptiva)** | k ∈ {4, 6, 10} × N ∈ {20, 30, 50}; cada horizonte por separado; sin banda; formación el miércoles |
| 30 | BTC y ETH | Dentro del universo |

---

## 4. Especificación reproducible

### 4.1 Calendario
- **Formación:** lunes t a las 00:00 UTC, con días ≤ t − 1.
- **Ejecución:** apertura del lunes.
- **Semana de tenencia:** de la apertura de t a la apertura de t + 7.

### 4.2 Día activo: §2.2.

### 4.3 Precios
| | Definición | Uso |
|---|---|---|
| **P_val(s, τ)** | Último precio negociado ≤ τ: el cierre del último día activo ≤ τ | Valuación, pesos, el tope de 1/3, H1 y las curvas. **Nunca** es un precio de transacción |
| **P_exe(s, d)** | Apertura O_d de un **día activo** d | **Única** base de las compras y ventas |

### 4.4 Elegibilidad en t (todas las condiciones)
- (a) t−30 … t−1, todos días activos;
- (b) t − (primer día activo del listado vigente) ≥ **180 días calendario**;
- (c) no excluida (§4.5);
- (d) V(s, t) = mediana de `quote asset volume` en t−30 … t−1 ≥ 1 000 000 USDT.

### 4.5 Exclusiones
- **Lista fija:**
  - USDC, BUSD, TUSD, USDP, PAX, DAI, FDUSD, USDS, USDSB, UST, USTC, SUSD, PAXG, XAUT, AEUR, EURI, USD1;
  - los códigos ISO-4217 de moneda fiat;
  - BIDR, IDRT, BVND.
- **Volatilidad anual** de los días activos de [t−90, t−1] < 10 %, con ≥ 60 días activos.
- **Tokens apalancados:** X + {UP, DOWN, BULL, BEAR}, con X la base de otro par USDT. La lista se congela en F3.
- **Duplicados:** correlación de 90 días > 0,98 con ≥ 60 días en común. Se excluye el de menor V, en orden de V descendente.

### 4.6 Universos y señal
- **U100 y U30:** las elegibles ordenadas por V descendente (empates por símbolo). U100 = las primeras 100 (o todas); U30 = las primeras 30.
- **Retornos de formación:** R_{s,h} = ln(C_{s,t−1} / C_{s,t−1−h}), con h ∈ {7, 14, 21, 28}.
- **Rangos dentro de U100:** p_{s,h} = (rango ascendente − 1) / (n₁₀₀ − 1), con rangos promedio en los empates.
- **Señal:** S_s = media de los cuatro p_{s,h}. **Una sola S para H1 y H2.**
- **rk(s):** posición de s dentro de U30 según S descendente (empates por V descendente y después por símbolo).

### 4.7 Selección
- **T_t:** las de la cartera que siguen en U30_t con rk ≤ 12, más las mejores rk de U30_t no tenidas, hasta completar 6.
- **Salen:** las demás.

### 4.8 Pesos y rebalanceo
- **W_t:** Σ unidades × (P_exe(s, t) si existe; si no, P_val(s, t)) + efectivo.
- **Caso general:**
  - lo cobrado de las ventas, neto de costos, se reparte en partes iguales entre las entradas;
  - las que se quedan no se tocan.
- **Vuelta a pesos iguales:** el primer lunes de formación de cada mes, o si algún peso es > 1/3.
  - Primero se venden las sobreponderadas hasta W/6.
  - Después se compran las subponderadas con el efectivo disponible.
  - Si falta efectivo por los costos, las compras se escalan en la misma proporción.
- **Sin apalancamiento.** El efectivo queda en USDT al 0 %.

### 4.9 Ejecución y costos
- **Costo por lado:** c = 10 pb de comisión + tramo según la posición de **liquidez V** en t:
  - posiciones 1–2: 5 pb;
  - 3–10: 10 pb;
  - 11–30: 20 pb;
  - fuera de U30 o no elegible: 30 pb.
- **Compras:** unidades = asignación / (P_exe · (1 + c)).
- **Ventas:** cobro = unidades · P_exe · (1 − c).
- Las ventas diferidas usan el tramo de t.

### 4.10 Aperturas faltantes y liquidaciones (corrección 3)
| Caso | Regla |
|---|---|
| Compra sin P_exe(s, t) | No se ejecuta. El lugar queda en efectivo hasta la formación siguiente |
| Venta sin P_exe(s, t) | Se reintenta en cada apertura activa siguiente. Mientras tanto se valúa a P_val. Lo cobrado queda en efectivo hasta la formación siguiente |
| **Par inactivo 30 días seguidos** (o fin de la ventana) | **Liquidación contable**, registrada **ese día**: unidades · P_val · (1 − c_tramo de t). **No es un precio ejecutable:** representa vender en las últimas operaciones y es un **supuesto** declarado. El lugar queda ocupado por la posición congelada hasta ese día, sin mirar al futuro (las reglas no leen anuncios) |
| Par USDT removido con el token vigente en otros pares | Igual que el caso anterior |
| Renombre mapeado | La posición continúa con la relación de canje, sin costo |
| **Estrés R6** | El mismo cálculo, con el valor de cada liquidación contable × 0,70 (−30 %) |

### 4.11 Semanas evaluables e inicio de H
- **Semana evaluable:** ≥ 30 elegibles en t.
  - En una semana no evaluable no hay entradas, salidas por la banda ni vuelta a pesos iguales; solo liquidaciones.
  - Esa semana queda fuera de las pruebas y dentro de lo descriptivo.
- **Inicio de H:** el **más tardío** de:
  - (i) el primer lunes con 13 semanas seguidas evaluables;
  - (ii) la semana siguiente a la fecha efectiva de la última **falla** de §2.3;
  - (iii) el 1 de enero del primer año con anuncios en el archivo web;
  - (iv) el 1 de enero del primer año desde el cual, en todos los años de la ventana, las salidas sin anuncio son ≤ 10 % de las observadas.
- **INVÁLIDO** si más del 20 % de las semanas de H no son evaluables, o si H tiene < 156 semanas evaluables.

### 4.12 Referencias
- **EW-U30:** el mismo motor con T_t = U30_t. Vuelve a pesos iguales el primer lunes de cada mes, o si algún peso es > 2/30. Mismos costos.
- **BTC buy and hold:** una compra en O_{t₀} con 15 pb.
- **Efectivo:** 0 %.

### 4.13 Métricas
- **H1:** IC_t = Spearman(S_s, y_s) entre s ∈ U100_t, con y_s = ln( P_val(s, cierre del domingo t+6) / C_{s,t−1} ).
  - Es un horizonte **calendario fijo de 7 días, idéntico para todas**. C_{s,t−1} siempre existe por la regla (a).
  - **Casos especiales:**
    - par suspendido el domingo t+6: marca obsoleta (último precio negociado);
    - par que deja de cotizar en la semana: último precio negociado y después efectivo;
    - renombre: precio del símbolo nuevo × relación de canje.
  - Las marcas obsoletas y las salidas se cuentan y se informan; **ninguna se excluye**.
  - Sesgo conocido: el rebote entre compra y venta en C_{t−1} juega **en contra** de H1.
  - IC̄ = media de las semanas evaluables.
- **H2:** r_t = W_{t+7} / W_t − 1 (valores en la apertura **antes** de operar, netos) para la cartera y para EW-U30. e_t = r_cartera − r_EW.
- **Nulo aleatorio (R5):**
  - S se reemplaza por una permutación aleatoria cada semana (semilla 20261021, 2000 réplicas), con la misma mecánica;
  - se compara el exceso **bruto**;
  - p_nulo = (1 + #{réplicas con exceso bruto ≥ el de la estrategia}) / 2001.

---

## 5. Inferencia (corrección 4)

### 5.1 H1
- **Estadístico:** z = IC̄ / EE_NW.
  - EE²_NW = [γ̂₀ + 2 Σ_{h=1}^{L} (1 − h/(L+1)) γ̂_h] / n, con núcleo de Bartlett, **L = 4** y sin preblanqueo.
  - p₁ = 1 − Φ(z).
- **IC90** = IC̄ ± 1,645 · EE_NW, con el **mismo** EE que el contraste.
- Si la calibración (§5.3) exige L = 8 o la regla del máximo, el IC90 usa el **mayor** de los EE.

### 5.2 H2 y H3: bootstrap-t por bloques circulares bajo H₀
Serie e_1 … e_n (el exceso semanal; para H3, x_t). Se fija ℓ = 13, k = ⌈n/ℓ⌉, n* = k·ℓ y B = 9999. Semillas: 20261020 para H2 y 20261024 para H3.

1. **Estadístico observado:** T = √n · ē / σ̂_C.
   - σ̂²_C = (ℓ/n) · Σ_{i=1}^{n} (B̄_i − ē)²;
   - B̄_i es la media de e_i … e_{i+ℓ−1}, con índices circulares (todas las posiciones de inicio).
   - σ̂²_C es exactamente la varianza bootstrap de √n*·ē*.
2. **Serie bajo H₀:** ẽ_t = e_t − ē, con media exactamente 0.
3. **Réplica b:**
   - k bloques **completos** de ẽ, con inicio uniforme en {1, …, n} y lectura circular;
   - ē*_b = media de los n* valores;
   - σ̂*²_b = ℓ/(k−1) · Σ_{j=1}^{k} (B̄*_{b,j} − ē*_b)², con divisor **k − 1** para que E*[σ̂*²] = σ̂²_C;
   - T*_b = √n* · ē*_b / σ̂*_b.
4. **Valor p:** p = (1 + #{b : T*_b ≥ T}) / (B + 1).
5. **Intervalo percentil-t**, con estadísticos de orden T*₍₁₎ ≤ … ≤ T*₍₉₉₉₉₎:
   - IC90 = [ē − T*₍₉₅₀₀₎ · σ̂_C/√n , ē − T*₍₅₀₀₎ · σ̂_C/√n];
   - IC95 = [ē − T*₍₉₇₅₀₎ · σ̂_C/√n , ē − T*₍₂₅₀₎ · σ̂_C/√n].
6. **Coherencia exacta:**
   - p ≤ 0,05 ⇔ T > T*₍₉₅₀₀₎ ⇔ el extremo inferior del IC90 es > 0;
   - p ≤ 0,025 ⇔ T > T*₍₉₇₅₀₎ ⇔ el extremo inferior del IC95 es > 0;
   - centrar no cambia σ̂* y desplaza ē* exactamente en ē, así que el contraste y el intervalo salen de **la misma** distribución.
- **Lo descriptivo** (frente a BTC y al efectivo) usa el mismo intervalo, sin valor p.

### 5.3 Calibración (control de validez, antes de los datos reales)
**Procesos sintéticos:** n = 340, media 0, desvío semanal 5 %, 1000 simulaciones con B = 1999 y semilla 20261023.

| Proceso | Descripción |
|---|---|
| G1 | t de Student con 3 grados de libertad |
| G2 | AR(1) con φ = 0,2 e innovaciones t(3) |
| G3 | GARCH(1,1) con α = 0,10, β = 0,85 e innovaciones t(4) |
| G4 | Mezcla 90 % N(−0,6 %, 3,5 %) + 10 % N(+5,4 %, 10 %) |
| G5 | Espejo de G4 |

**H1:** proceso AR(1) con φ = 0,1, desvío 0,14 y n = 340.

**Bandas de aceptación** (±2 errores de Monte Carlo):
- rechazo al 5 % en **[3,6 %, 6,4 %]**;
- rechazo al 2,5 % en **[1,5 %, 3,5 %]**.

**Si la calibración falla:**
- **Rechaza menos que la banda:** se acepta y se informa.
- **Rechaza más en H2 o H3:** se repite con ℓ = 26. Si persiste, p = máx(p_ℓ₁₃, p_ℓ₂₆, p_NW), con p_NW el t de Bartlett con 13 rezagos.
- **Rechaza más en H1:** L = 8. Si persiste, p₁ = máx(p_{L4}, p_{L8}).
- **Validez de la regla del máximo:** si al menos uno de los componentes es un valor p válido, P(máx ≤ u) ≤ P(componente válido ≤ u) ≤ u. La regla solo puede subir el p.

**Qué demuestra la calibración:**
- que el código es correcto;
- que el tamaño es cercano al nominal en esos procesos, con este n y estos bloques.

**Qué no demuestra:**
- que el tamaño sea correcto para el proceso **real** (regímenes, caídas agrupadas, dependencia larga);
- nada sobre potencia realista, supervivencia, costos, liquidaciones ni mirada al futuro.

### 5.4 Diagnóstico con datos reales (antes de calcular el exceso de la estrategia)
- Se aplica el contraste de H2 al **exceso bruto** de las 2000 carteras aleatorias de R5 frente a EW-U30 bruto (B = 999).
- Por simetría, su media esperada es ≈ 0.
- Se informa la tasa de rechazo al 5 %. Si supera el **9 %**, se aplica la regla del máximo de §5.3.

---

## 6. Criterios

### 6.1 H1: evidencia predictiva frente a relevancia económica (corrección 2)
**δ_IC = 0,01** es el **margen de relevancia económica**, en unidades de IC̄ (correlación de rangos media semanal).
- **No es** un nivel de significación (α = 5 % en todo el protocolo).
- **No es** el umbral para confirmar H1.
- **Justificación** [Hip]:
  - ganancia bruta del quintil superior ≈ IC · σ_cs · 1,40 · 52, con σ_cs = 8–12 % semanal;
  - IC 0,01 ≈ 6–9 %/año bruto, frente a un lastre de costos relativo de ≈ 3,5–5 %/año;
  - 0,01 es el menor IC con ganancia neta plausible.

| Afirmación | Condición | ¿Control de familia? | Consecuencia |
|---|---|---|---|
| **Información confirmada** | H1 (IC ≤ 0) rechazada por el procedimiento de §3.2 | **Sí** | Habilita las etapas según §6.5 |
| **Relevancia económica demostrada** | Además, extremo inferior del IC90 ≥ δ_IC | **No** (descriptiva) | Ninguna adicional. Solo cambia la redacción: «relevancia demostrada» o «información detectable, relevancia no demostrada» |
| **En contra** (no relevancia) | Extremo superior del IC90 < δ_IC, una prueba **unilateral** de no relevancia al 5 % (no es TOST) | **No** | Cierre: el mismo destino que «insuficiente» |
| **Insuficiente** | Cualquier otro caso | — | Cierre |

**Con los errores esperados** (≈ 0,007–0,0095):
- confirmar H1 implica un IC̄ puntual ≳ 0,012–0,019, pero no garantiza un extremo inferior ≥ 0,01;
- con IC verdadero = 0, «en contra» saldría ≈ 28–40 % de las veces, y lo más probable es «insuficiente».

### 6.2 H2: rentabilidad neta frente a la referencia
| Afirmación | Condición |
|---|---|
| **Ventaja neta de selección** | H2 rechazada por §3.2 |
| **En contra (económico)** | Extremo superior del IC90 < 0 (fuera de la familia) |
| **Insuficiente** | Cualquier otro caso |

**Descriptivo, sin decisión:**
- frente a BTC (exceso dominado por el beta de las altcoins);
- frente al efectivo;
- CAGR, volatilidad, Sharpe y su versión deflactada, Sortino, caída máxima, CVaR del 5 % semanal, peor semana, tiempo bajo el agua y beta;
- correlación de e_t con BTC y con el exceso de timing de T.

### 6.3 Robustez de la base (siempre se calcula y se informa; solo afecta la clasificación si H1 y H2 rechazan)
| | Condición |
|---|---|
| R1 | Exceso neto > 0 con costos ×2 |
| R2 | Exceso neto > 0 con ejecución un día después, igual para la cartera y para EW-U30 |
| R3 | IC̄ > 0 en ≥ 2 de 3 tercios consecutivos de las semanas evaluables, y por separado exceso neto > 0 en ≥ 2 de 3 tercios |
| R4 | Exceso neto > 0 al re-simular con la moneda de mayor aporte no elegible para todo (universos, cartera y EW-U30). Aporte = Σ_t w_{c,t} · (r_{c,t} − r_{EW,t}), bruto |
| R5 | p_nulo ≤ 0,05 (es una condición, no una afirmación) |
| R6 | Exceso neto > 0 con las liquidaciones contables al −30 % |

**ROBUSTA** si se cumplen las seis.

### 6.4 Liquidaciones y precios obsoletos: cómo se informan (corrección 3)
- **Escenario principal**, siempre rotulado: «liquidación contable al último precio negociado (supuesto; no es un precio ejecutable)».
- **Estrés:** R6 (−30 %), con su exceso y su intervalo.
- **Diagnóstico** (descriptivo, sin criterio nuevo):
  1. cantidad de liquidaciones, en la estrategia y en EW-U30, y de marcas obsoletas, en H1 y H2;
  2. aporte de esos eventos al exceso acumulado de H2 y a IC̄;
  3. etiqueta **«resultado dependiente de liquidaciones o marcas obsoletas»** si, al anular esos aportes, cambia el signo de la estimación puntual de H2 o de IC̄.
- La defensa prerregistrada es R6. La etiqueta no cambia la clasificación, pero debe figurar junto a ella.

### 6.5 Clasificación de la base
| Clasificación | Condición | Qué habilita |
|---|---|---|
| **INVÁLIDO** | Falla la validez (§10) | Nada |
| **RESPALDADA HISTÓRICAMENTE** | H1 y H2 rechazadas y ROBUSTA | H3; la ventana C (con autorización); P |
| **VENTAJA NO ROBUSTA** | H1 y H2 rechazadas, pero no ROBUSTA | Solo P informativo de la base (decisión tuya) |
| **INFORMACIÓN SIN VENTAJA OPERABLE** | H1 rechazada; H2 no | Solo P informativo de la base (decisión tuya) |
| **NO CONCLUYENTE (H2 sin H1)** | H2 rechazada; H1 no | **Cierre** |
| **EN CONTRA** | Según §6.1 | **Cierre** |
| **INSUFICIENTE** | Cualquier otro caso | **Cierre** |

**Ninguna clasificación autoriza capital.**

---

## 7. Potencia, límites y cierre (corrección 5)

### 7.1 Supuestos [Hip, ninguno medido]
1. **Desvío del IC semanal:** 0,12–0,16 con ~100 monedas; con ≈ 330–360 semanas, el EE de IC̄ es ≈ 0,007–0,0095.
2. **Tracking error** de la cartera frente a EW-U30: 25–35 %/año (volatilidad idiosincrática semanal ≈ 10–12 % frente a la canasta, dividida por √6).
3. **Duración:** 6,5–7 años, con EE de H2 ≈ 9,4–13,7 %/año.
4. Aproximación normal, sin autocorrelación adicional.
5. Umbral según el paso de Holm: 0,025 o 0,05.

### 7.2 Cifras
| | Umbral 0,025 | Umbral 0,05 |
|---|---|---|
| H1, IC verdadero 0,02 | 0,56–0,79 | 0,68–0,87 |
| H1, IC 0,03 | 0,88–0,99 | 0,93–0,99 |
| H2, neto 10 %/año | **0,11–0,17** | 0,18–0,26 |
| H2, neto 20 %/año | 0,30–0,52 | 0,41–0,64 |

**Efecto mínimo detectable con 80 %:** IC ≈ 0,020–0,027; H2 ≈ 28–39 %/año.

**Sensibilidad:**
- si la volatilidad idiosincrática semanal real fuera 14–20 %, el tracking error sería ≈ 41–59 %/año y la potencia de H2 para un 10 %/año, **0,06–0,09**;
- si la regla de supervivencia acorta H, todas las potencias bajan, y se informa cuánto.

**Cota conjunta:** con una ventaja real del 10 %/año (y un IC de ≈ 0,02), P(RESPALDADA) ≤ la menor de las potencias de H1 y H2, es decir **≤ 0,11–0,26**, y menos con la robustez.

### 7.3 Limitación para decisiones de inversión
**Este experimento no puede producir evidencia suficiente para comprometer capital:**
- una ventaja neta realista (5–20 %/año) quedará casi seguro en «insuficiente»;
- la historia está contaminada por el conocimiento del período;
- no se observa la ejecución real;
- las liquidaciones son supuestos.

**Sí puede informar una decisión de investigación:**
- si hay información transversal en monedas líquidas (H1);
- o si conviene cerrar la familia.

Incluso con una base respaldada, la confirmación independiente exige papel prospectivo de ≈ 2–3,5 años (IC 0,03) a 4–8 años (IC 0,02) [Hip].

### 7.4 Cláusula de cierre
**Si H1 no se confirma, o H2 sale insuficiente, no se agrega nada para compensar:**
- ni períodos, universos, horizontes, k ni bandas;
- ni costos alternativos ni combinaciones con T;
- ni umbrales más laxos ni otra inferencia.

La grilla de sensibilidad no puede usarse para afirmar nada. La única continuación posible es una **hipótesis nueva**, con prerregistro propio y **solo prospectiva**.

---

## 8. H3: filtro de momentum absoluto (incremental, subordinado)
- **Fuera de la base:** A_s = (R_{s,7} + R_{s,14} + R_{s,21} + R_{s,28}) / 4, el nivel absoluto, que no entra en S.
- **Se ejecuta solo si** la base es RESPALDADA HISTÓRICAMENTE (§3.2 y §6.5), una vez y después de registrar con hash la clasificación de la base.
- **Variante F:** mismo T_t, misma mecánica y mismos pesos.
  - Cada s ∈ T_t con A_s ≤ 0 no se compra, o se vende; su parte queda en efectivo, **sin reemplazo**.
  - Se reevalúa cada semana, con los mismos costos.
- **Métrica:**
  - x_t = r_F − ē · r_base (ambas netas), con ē = exposición media de F en H;
  - es una construcción de referencia, como la «estática equivalente» de T; no es una regla operable;
  - p₃ por §5.2.
- **Criterios:**

| Resultado | Condición |
|---|---|
| **FAVORABLE** | p₃ ≤ 0,05, x̄ > 0 con costos ×2 y caída máxima de F < la de la base |
| **EN CONTRA** | Extremo superior del IC90 < +2 %/año (fuera de la familia) |
| **INSUFICIENTE** | Cualquier otro caso |

- **Potencia** [Hip]: EE ≈ 8–12 %/año, así que el **efecto mínimo detectable es ≈ 22–34 %/año**.
- **Si es FAVORABLE:** F entra en P como estrategia **aparte**.

---

## 9. Datos y autorización
| Elemento | Detalle | Estimación [Hip] |
|---|---|---|
| Listado de símbolos | Bucket `data/spot/monthly/klines/` (es el listado S3 de la propia web, **por verificar**) | 1–5 solicitudes |
| Listado por símbolo | `data/spot/monthly/klines/{S}/1d/` | 600–1000 solicitudes; 15–35 MB |
| Klines 1d mensuales y `.CHECKSUM` | 2017-08 → **2026-05**, todos los S terminados en USDT | 21 000–50 000 pares de archivos; ≈ 50–115 MB |
| Reparaciones | Diarios de `data/spot/daily/klines/…`, solo si falta un mensual o falla su checksum | Pocas |
| exchangeInfo | `GET https://api.binance.com/api/v3/exchangeInfo` | 1 |
| BTCUSDT y ETHUSDT | Se reutilizan los archivos locales verificados | 0 |

- **Total:** ≈ 65–150 MB y 43 000–101 000 solicitudes. A ≤ 5 solicitudes por segundo, con espera ante errores: ≈ 2,5–6 h.
- Gratis, sin dependencias nuevas. **Nada ≥ 2026-06-01.**
- **Anuncios:** categorías 161, 48 y 49 de binance.com. Antes de leerlas de forma automática se revisan las condiciones de uso; si no lo permiten, la compilación es manual. Todo se fija con hash antes de calcular retornos.

**Autorizaciones, por separado:**

| | Decisión | Cuándo |
|---|---|---|
| A1 | Aprobar y congelar **este** documento | Antes de todo |
| A2 | Descarga del cuadro de arriba | Después de A1 |
| A3 | Compilación de anuncios | Con A2 |
| A4 | Ventana C | Solo si H da RESPALDADA |
| A5 | Evaluación P | Solo si H da RESPALDADA (o, si lo decidís, VENTAJA NO ROBUSTA o INFORMACIÓN SIN VENTAJA, como seguimiento informativo) |

---

## 10. Validez (antes de interpretar; si falla, se detiene)
1. **Checksums:** 100 % verificados.
2. **Supervivencia:** §2.3 y la regla de §4.11.
3. **Listas congeladas en F3**, con hash, antes de cualquier retorno: apalancados, duplicados, renombres y conciliación.
4. **Separación de etapas:** la etapa de calidad no importa funciones de rendimiento; se demuestra con una prueba.
5. **Sin mirada al futuro:**
   - comprobaciones automáticas;
   - invariancia al truncar en 5 cortes al azar (semilla 20261022): universos, señales, T_t y pesos.
6. **Calibración** de §5.3, aplicada y documentada.
7. **Semanas no evaluables** ≤ 20 % y ≥ 156 semanas evaluables en H.
8. **Bloqueo de fechas:** ninguna lectura ≥ 2026-06-01 sin A4; se demuestra con una prueba.

## 11. Fuera de alcance
- Cortos y perpetuos.
- Otros exchanges o cotizaciones.
- Aprendizaje automático o CTREND.
- Funding transversal.
- Tamaño.
- Combinar la señal con T.
- Variantes fuera del ítem 29.
- Otras familias.

## 12. Restricciones
- E1, E2, T, T-MULTI y sus artefactos, intactos.
- Repositorio sin cambios; sin commits ni pushes.
- Sin dinero real.
- No se congela ni se ejecuta sin tu decisión explícita.

---

## Anexo A: demostración del control del error de familia

**Notación:**
- I ⊆ {1, 2, 3} es el conjunto de índices con H_i verdadera (nula cierta).
- E_i = {rechazar H_i}.
- G = evento «base ROBUSTA»: cualquier evento que dependa de los datos.
- α = 0,05.

**Procedimiento:**
- E₁ y E₂ salen de Holm sobre (p₁, p₂).
- E₃ = E₁ ∩ E₂ ∩ G ∩ {p₃ ≤ α}.

**Supuestos:**
- **(S1)** Validez marginal: P_{H_i}(p_i ≤ u) ≤ u para u ∈ {α/2, α}.
- **(S2)** Las hipótesis son enunciados sobre parámetros, fijados antes de los datos y **no condicionados** a otras pruebas.
- **(S3)** La familia son solo E₁, E₂ y E₃.

No se supone nada sobre la dependencia entre p₁, p₂ y p₃.

**Lema 1 (Holm).** Para cualquier I con I ∩ {1, 2} ≠ ∅: P(∪_{i∈I∩{1,2}} E_i) ≤ α.

*Demostración:*
- Si una sola es verdadera, digamos H₁, rechazarla exige p₁ ≤ α/2 (si se rechaza en el primer paso) o p₁ ≤ α después de rechazar H₂ con p₂ ≤ α/2. En cualquier caso exige p₁ ≤ α, así que P(E₁) ≤ α.
- Si las dos son verdaderas, cualquier rechazo exige p₍₁₎ ≤ α/2, así que P ≤ P(p₁ ≤ α/2) + P(p₂ ≤ α/2) ≤ α.
- (Holm, 1979: validez con cualquier dependencia.) ∎

**Lema 2.** E₃ ⊆ E₁ ∩ E₂ y E₃ ⊆ {p₃ ≤ α}. Es inmediato por definición. ∎

**Teorema.** Para cada I ⊆ {1, 2, 3}: P(∪_{i∈I} E_i) ≤ α.

| I (nulas verdaderas) | Unión de errores | Cota | Argumento |
|---|---|---|---|
| ∅ | ∅ | 0 | No hay nulas verdaderas |
| {1} | E₁ | ≤ α | Lema 1 |
| {2} | E₂ | ≤ α | Lema 1 |
| {1, 2} | E₁ ∪ E₂ | ≤ α | Lema 1 |
| {3} | E₃ | ≤ P(p₃ ≤ α) ≤ α | Lema 2 y (S1) |
| {1, 3} | E₁ ∪ E₃ = E₁ | ≤ α | Lema 2 (E₃ ⊆ E₁) y Lema 1 |
| {2, 3} | E₂ ∪ E₃ = E₂ | ≤ α | Lema 2 y Lema 1 |
| {1, 2, 3} | E₁ ∪ E₂ ∪ E₃ = E₁ ∪ E₂ | ≤ α | Lema 2 y Lema 1 |

∎

**Equivalencia con unas pruebas cerradas** (Marcus, Peritz y Gabriel, 1976 [Pub\*]). Se toman como pruebas locales de nivel α:
- φ_{1} = 1[p₁ ≤ α], φ_{2} = 1[p₂ ≤ α], φ_{3} = 1[p₃ ≤ α];
- φ_{1,2} = φ_{1,2,3} = 1[mín(p₁, p₂) ≤ α/2] (Bonferroni sobre {1, 2});
- φ_{1,3} = φ_{1}, φ_{2,3} = φ_{2}.

Cada una es válida para su intersección por (S1). Las pruebas cerradas rechazan:
- **H₁** ⇔ p₁ ≤ α y mín(p₁, p₂) ≤ α/2, que es la regla de Holm;
- **H₂**, de forma simétrica;
- **H₃** ⇔ p₃ ≤ α, p₁ ≤ α, p₂ ≤ α y mín(p₁, p₂) ≤ α/2, que es «Holm rechaza H₁ y H₂, y p₃ ≤ α».

El procedimiento propuesto es esa regla intersectada con G, así que sus rechazos son un **subconjunto** de los de las pruebas cerradas y hereda el control fuerte.

**Consecuencias para la potencia:**
- **H1 y H2:** la misma potencia que Holm m = 2. La compuerta no les cuesta nada.
- **H3:** nivel completo de 0,05 cuando se habilita. P(se habilite) = P(RESPALDADA), que es baja (§7).
- **Comparación** (H1 con IC 0,02 / H2 con 20 %/año):

| Procedimiento | Potencia H1 | Potencia H2 | Estado |
|---|---|---|---|
| Holm m = 3 (primer paso, 0,0167) | 0,49–0,74 | 0,24–0,45 | Peor, sin beneficio |
| **Este procedimiento** (primer paso, 0,025; segundo, 0,05) | 0,56–0,79 / 0,68–0,87 | 0,30–0,52 / 0,41–0,64 | **Adoptado** |
| Secuencia fija (0,05) | 0,68–0,87 | 0,41–0,64 | No adoptado: sería la opción más favorable al éxito |

**Lo que el teorema no cubre:**
- las etiquetas «en contra» y «relevancia demostrada»;
- R5 como afirmación;
- la ventana C y la evaluación P;
- la sensibilidad;
- cualquier análisis exploratorio;
- la distorsión de tamaño de los valores p aproximados (acotada solo empíricamente, en §5.3–5.4).

## Fuentes de documentación
- https://github.com/binance/binance-public-data/
- https://github.com/binance/binance-public-data/issues/201
- https://www.binance.com/en/support/announcement/list/161
- https://docs.tardis.dev/historical-data-details/binance
- https://developers.binance.com/docs/zh-CN/binance-spot-api-docs/rest-api/general-endpoints
