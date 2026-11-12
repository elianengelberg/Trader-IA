# Marco estadístico común (MEC v0.2)

> **Estado (2026-10-20): PROPUESTO, NO VALIDADO TODAVÍA.**
> - El nombre del archivo es el que pediste. La «validación» que contiene es **analítica**: revisión de fórmulas y supuestos.
> - La **calibración con datos sintéticos (§5) no se ejecutó**: requiere autorización (A-S1). Hasta que se ejecute y pase sus criterios, este marco **no está validado empíricamente**.
> - Reemplaza al MEC v0.1 de las propuestas v0.1, que **se conservan sin cambios**.
> - **No se aplica retroactivamente a T:** la decisión registrada de T se rige por su propio prerregistro congelado.

## 1. Diagnóstico del criterio actual: P ≠ valor p

### 1.1 Qué es P exactamente
Implementación usada por T (`research/hcarry_next/src/hcarry/lab/estadistica.py:20`, `bootstrap_media`):
- Se remuestrea la serie diaria de exceso x₁…x_n con **bloques circulares de longitud ℓ = 20, sin centrar** y se calculan B = 2000 medias x̄*_b.
- **P = #{x̄*_b > 0} / B.** IC90 = percentiles 5 % y 95 % de las x̄*_b.
- Los prerregistros v0.1 usaban **1 − P como valor p** y le aplicaban Holm.

### 1.2 Por qué 1 − P no garantiza el control del error de tipo I
- **Aproximación asintótica:** si √n(x̄* − x̄) ≈ N(0, σ̂²_B), entonces 1 − P = Pr*(x̄* ≤ 0) ≈ Φ(−√n x̄/σ̂_B). Es el valor p de una prueba z con error estándar bootstrap: una equivalencia **solo de primer orden**. Puede fallar por cuatro motivos:
  1. **Varianza subestimada con ℓ fijo.** Si la dependencia (persistencia de la volatilidad o de la exposición) dura más que ℓ, el bootstrap por bloques subestima la varianza de x̄ y la prueba rechaza de más.
  2. **No está studentizado.** El método de percentiles no corrige la asimetría ni las colas pesadas; su error de cobertura es O(n^{-1/2}) (frente a O(n^{-1}) del bootstrap-t en el caso i.i.d.).
  3. **Series dispersas:** en una estrategia por eventos (H-REV-SHOCK), x_d es casi siempre ≈ −ε·r_d y a veces grande. La aproximación normal puede ser mala aunque n sea grande, porque el número efectivo de eventos es chico.
  4. **No se construye bajo H₀:** P mide la incertidumbre alrededor de x̄, no la distribución del estadístico bajo la nula.
- **Evidencia empírica del propio proyecto:** en la calibración de E3 (procesos sintéticos, n = 340), incluso un bootstrap-t **centrado y studentizado** con ℓ = 13 rechazó un **7,0 %** al nivel del 5 % con t₃ i.i.d. (`ejecucion_E3/resultados/calibracion/calibracion.json`, `9232876…`). Si el método más cuidadoso necesitó calibración, el percentil no studentizado no puede suponerse válido.

**Conclusión:**
- P es una **medida descriptiva de incertidumbre** («probabilidad bootstrap de exceso positivo»), no un valor p.
- **Holm sobre 1 − P no es válido sin calibración.**

### 1.3 Consecuencia para T (sin reinterpretar nada)
- T fuera de muestra registró P = 0,755, es decir 1 − P = 0,245.
- Cualquier prueba válida razonable estaría lejos de rechazar al 5 %. **La conclusión registrada (EVIDENCIA INSUFICIENTE) no depende de este defecto.**
- Las reglas congeladas de T **no se cambian**. La limitación se documenta (`REGISTRO_DE_RIESGOS_DE_SESGO.md`).

## 2. Variable económica (definición única, para todas las estrategias)

**Notación por manga a (BTC o ETH), con capital inicial K_a = K/2:**
- Comisión **f** y slippage **s** por lado, en tanto por uno: f = 0,0010 y s = 0,0005.
- **Compra** a la apertura O con todo el efectivo W: precio efectivo O·(1+s); unidades q = W / (O·(1+s)·(1+f)).
- **Venta:** se cobra q·O·(1−s)·(1−f).
- **Valor de la manga:** W_t = efectivo + q·C_t, marcado al cierre de cada barra.
  - Diario (H-REV-SHOCK): marcas en C_d.
  - Horario (H-EMA9-VWAP): marcas en C_h; la marca diaria es el cierre de la barra de las 23:00 UTC.
- **Rendimiento de la manga:** R_t = W_t / W_{t−1} − 1, **simple**. Los logaritmos se usan solo en las señales, nunca en el P&L.
- **Exposición** w_t = q·C_{t−1}/W_{t−1} durante la barra t: la fracción invertida al empezar la barra. En la barra de entrada vale ≈ 1 desde la apertura.
- **ε_a** = media de w_t en la ventana evaluada. Es la exposición media efectiva: fracción del tiempo invertido, ponderada por valor.
- **Benchmark primario:** la estática con exposición constante ε_a, rebalanceada en cada barra sin costos, B_t = ε_a·r_t con r_t = C_t/C_{t−1} − 1.
  - **Diario:** directamente.
  - **Horario:** compuesto dentro del día, 1 + B_d = Π_h (1 + ε_a r_h).
- **Exceso diario:** x_{a,d} = R_{a,d} − B_{a,d}. **Conjunto:** x_d = ½(x_{BTC,d} + x_{ETH,d}).
  - Por definición equivale a una cartera 50/50 rebalanceada a diario entre mangas: es una convención declarada.
- **Identidad útil:** sin costos y en frecuencia de barra, x̄ = (1/n) Σ (w_t − ε) r_t = cov_muestral(w, r).
  - **El exceso mide si la exposición se correlaciona con el rendimiento contemporáneo**: eso es timing. Los costos lo reducen.
- **Referencias descriptivas, claramente separadas del benchmark primario:** buy and hold (compra en la primera apertura con costo de entrada) y efectivo al 0 %.

**Casos especiales (iguales en ambas propuestas):**
- **Barras faltantes:** no hay marca. El rendimiento entre dos marcas válidas se asigna a la barra válida siguiente, igual para la estrategia y el benchmark (mismos cortes temporales).
- **Ejecución imposible:** si falta la apertura prevista, la compra no se hace y la venta se hace en la siguiente apertura válida, dentro de la ventana.
- **Fin de la ventana:** toda posición abierta se **liquida al último cierre válido de la ventana**, con costos de salida. **Nunca se lee una barra posterior al fin de la ventana**; en E, nada a partir del 2026-06-01 (período reservado de H-CARRY).
  - Se informa además la valuación a mercado sin costo de salida (descriptiva).
- **Lotes y redondeo:** cantidades continuas en coma flotante de 64 bits. Se declara que se ignoran los lotes mínimos de Binance (≤ 1 pb con el capital supuesto de 10 000 USDT; no medido).

## 3. Hipótesis

| | H₀ | H₁ | Uso |
|---|---|---|---|
| Primaria | μ = E[x_d] ≤ 0 | μ > 0 | «ventaja respaldada» |
| Contra-hipótesis | μ ≥ 0 | μ < 0 | «en contra» |
| Relevancia | μ ≥ δ | μ < δ | «efecto relevante descartado»; δ es el efecto mínimo económicamente relevante [D-S4] |

## 4. Prueba primaria propuesta: bootstrap-t por bloques circulares, centrado bajo H₀
Es el mismo procedimiento que el protocolo E3 v3 §5.2, cuyo código y prueba de dualidad ya existen: `ejecucion_E3/codigo/inferencia.py`, `7b28038621c1d366655d726bb885ca0105f1a25cfcdb9615e86a7fe39e85f3e1`. Habrá que volver a verificarlo antes de usarlo.

1. **Estadístico:** T = √n·x̄ / σ̂_C, con σ̂²_C = (ℓ/n)·Σ_{i=1}^{n}(B̄_i − x̄)², donde B̄_i es la media del bloque circular que empieza en i.
2. **Serie bajo H₀:** x̃_t = x_t − x̄, con media exacta 0.
3. **Réplica:**
   - k = ⌈n/ℓ⌉ bloques completos de x̃ con inicio uniforme; ē* es la media de los n* = kℓ valores;
   - σ̂*² = ℓ/(k−1)·Σ_j (B̄*_j − ē*)²;
   - T* = √n*·ē*/σ̂*.
4. **Valor p unilateral:** p = (1 + #{T* ≥ T}) / (B + 1), con **B = 9999**.
5. **Intervalos percentil-t (duales):** IC90 = [x̄ − T*₍₀,₉₅₎·σ̂_C/√n, x̄ − T*₍₀,₀₅₎·σ̂_C/√n] e IC95 análogo.
   - Rechazar H₀ al 2,5 % equivale a que el extremo inferior del IC95 sea > 0.
6. **Parámetros [D-S1]:**
   - **ℓ = 20 días** en las series diarias. Las horarias se agregan primero a días, así que también ℓ = 20 días.
   - **Semillas:** 20261101 para H-REV-SHOCK y 20261102 para H-EMA9-VWAP. Son distintas de todas las semillas usadas antes.
7. **Regla de respaldo, también prerregistrada:** si la calibración (§5) muestra sobre-rechazo en algún proceso pertinente, se usa p = máx(p_{ℓ=20}, p_{ℓ=40}, p_NW).
   - p_NW es la prueba t con el error estándar de Newey–West (núcleo de Bartlett, L = 20).
   - **Es válida** porque, si al menos un componente es un valor p válido, P(máx ≤ u) ≤ u.
   - Su intervalo es la envolvente de los tres intervalos.
   - **La regla de respaldo también debe pasar la calibración.**
8. **Qué NO se hace:**
   - elegir ℓ, B o el método mirando los datos reales;
   - usar P como valor p;
   - sustituir esta prueba por el nulo de entradas aleatorias (§8).

## 5. Calibración con datos sintéticos (diseño; **no ejecutada**, requiere A-S1)
- **Procesos de la serie diaria de exceso:** todos con media exactamente 0 bajo H₀ y desvío diario del 1 % (o el que se fije).

| ID | Proceso | Qué representa |
|---|---|---|
| C1 | t₃ i.i.d. | Colas pesadas |
| C2 | GARCH(1,1), α = 0,10, β = 0,85, innovaciones t₄ | Agrupamiento de volatilidad |
| C3 | AR(1), φ = 0,2, t₃ | Autocorrelación |
| C4 | **Disperso por eventos:** exposición de Markov encendida/apagada (P(encender) = 0,5 %/día, duración media de 6 días) independiente de r_t GARCH-t₄; x = (w − w̄)·r | Tipo H-REV-SHOCK |
| C5 | **Intradía agregado:** x_d = suma de K ~ Poisson(0,6) excesos por operación t₄ con desvío del 1,5 %, centrados | Tipo H-EMA9-VWAP |
| C6 | Cambio de régimen: varianza ×3 en un tercio contiguo de la muestra | Regímenes 2020–2022 |

- **Tamaños:** n = 1612 (E), 366, 731 y 1096 (cortes prospectivos).
- **Réplicas:** 2000 simulaciones por proceso y tamaño, B = 1999 dentro de cada una; semilla 20261103.
- **Criterio de aceptación:** tasa de rechazo al 2,5 % y al 5 % **≤ al límite superior** de la banda de ±2 errores de Monte Carlo.
  - Al 5 % la banda es [4,03 %, 5,97 %]; al 2,5 % es [1,80 %, 3,20 %].
  - Un sub-rechazo se acepta y se informa (cuesta potencia).
- **Potencia (descriptiva):** se informa con μ igual al δ fijado [D-S4] y con μ = 2δ.
- **Qué muestra la calibración:** que el código es correcto y que el tamaño está controlado **en esos procesos**.
- **Qué no muestra:** validez general en datos reales, ni nada sobre los costos o la supervivencia.

## 6. Multiplicidad
- **Familia confirmatoria:** {H-REV-SHOCK, H-EMA9-VWAP} en E.
- **Bonferroni:** α = **0,025 unilateral por hipótesis** [D-S2]. Es válido aunque las dos se ejecuten en momentos distintos. Holm exige tener los dos valores p a la vez; solo se usaría si E se ejecuta en una misma ronda y lo decides así.
- **Análisis secundarios** (por activo, estrés, subperíodos, nulo emparejado, ℓ alternativos): **descriptivos, no deciden**.
- **Multiplicidad a nivel programa:** el proyecto ya probó o propuso más de 25 hipótesis relacionadas (`REGISTRO_DE_RIESGOS_DE_SESGO.md`). Un «respaldada» histórico aislado debe leerse con esa familia en mente, y **solo la fase prospectiva lo confirma**.

## 7. Niveles de conclusión (no se mezclan)

| Nivel | Nombre | Criterio |
|---|---|---|
| 1 | Retorno neto observado | x̄ > 0 (estimación puntual). **No es evidencia** |
| 2 | Ventaja estadística histórica (E, contaminada) | p ≤ 0,025, con datos válidos y N ≥ N_min |
| 3 | Robustez | Con nivel 2 alcanzado: estimación puntual > 0 con costos ×2, con una barra de retraso, en cada activo y en cada subperíodo. Es descriptiva: si falla, el nivel 2 se informa «no robusto» |
| 4 | Confirmación prospectiva independiente | Prueba secuencial del §7.1, en el papel, con α = 0,025 |
| 5 | Viabilidad operativa | Etapa F: fills, spread, slippage, latencia y capacidad medidos. **Fuera de alcance; no autorizado** |

**Categorías de E** (se informa una sola):
- **INVÁLIDO:** falla de datos o de integridad (hashes, candado, ventana).
- **INCONCLUSO POR DATOS:** menos de N_min operaciones [D-RS-6, D-EV-9].
- **RESPALDADA EN E:** nivel 2.
- **EN CONTRA:** extremo superior del IC90 < 0.
- **EFECTO RELEVANTE DESCARTADO:** extremo superior del IC90 < δ, sin ser «en contra».
- **INSUFICIENTE:** cualquier otro caso.
- **«No respaldada»** significa INSUFICIENTE, EN CONTRA o EFECTO RELEVANTE DESCARTADO. Solo las dos últimas son **evidencia de ausencia**; la primera es **ausencia de evidencia**.

### 7.1 Prueba prospectiva con miradas repetidas
- **Diseño:** grupal secuencial con gasto de α de **Lan–DeMets tipo O'Brien–Fleming**, α total = 0,025 unilateral [D-S5].
- **Fracción de información** t_k = n_k / n_max, con n_max el número de días que da potencia del 80 % para δ (fórmula del §9 del plan).
- **Umbral en cada mirada:** el valor crítico del gasto de α aplicado al estadístico bootstrap-t del §4.
- **Futilidad no vinculante:** se puede detener si el IC90 queda por debajo de δ (efecto relevante descartado), sin gastar α.
- **Supuesto:** incrementos aproximadamente independientes (teorema del límite central funcional para series débilmente dependientes). Es una aproximación y se declara.
- **Si n_max es impracticable** (por ejemplo, décadas), se declara **ex ante** que la confirmación prospectiva no es alcanzable en un horizonte útil. **No se relaja α.**

## 8. Nulo de entradas aleatorias emparejadas: auditoría y redefinición

**Problemas del nulo v0.1** (mismas duraciones observadas, entradas uniformes):
1. **Las duraciones son endógenas:** dependen de los stops y objetivos y, por lo tanto, del camino del precio tras la entrada real. Si se fijan y se trasplantan a otras fechas, se importa información del resultado real.
2. **Las entradas reales se concentran en regímenes** (tras shocks, en sesiones alcistas). Las aleatorias uniformes comparan con otros regímenes; mezclan timing con prima de régimen.
3. **No está calibrado.** Exigir un percentil ≥ 0,90 dentro del criterio de decisión combinaba dos pruebas sin controlar el error. **Se elimina del criterio.**

**Redefinición (solo descriptiva):**
- **Qué se conserva:**
  - número de entradas por activo y por año calendario;
  - elegibilidad (días u horas válidos, sin posición abierta, horario de entrada);
  - **las mismas reglas de salida aplicadas desde la entrada aleatoria**, de modo que las duraciones sean endógenas al camino aleatorio y no copiadas;
  - mismos costos.
- **Qué se aleatoriza:** solo el momento de entrada, uniforme sobre los instantes elegibles del mismo año, sin superposición (muestreo secuencial con rechazo).
- **H-REV-SHOCK:** los niveles de salida que dependen del shock (REF y L\*) no existen en una entrada aleatoria. Se usan análogos fijados de antemano: REF = C_{entrada−1}·(1 + |r̄_shock|) y L\* = mínimo de los 3 días previos. **Esto lo hace aún más aproximado** (ver la propuesta v0.2).
- **H-EMA9-VWAP:** la entrada aleatoria se elige entre barras que cumplen (a)–(c) (horario, sin posición, sesión completa), con salidas por VWAP o fin de sesión.
- **Réplicas:** 1000, con semilla fija.
- **Qué contrasta:** si las condiciones de entrada agregan valor frente a entradas en momentos elegibles al azar con la misma lógica de salida.
- **Qué no demuestra:** ni ventaja económica ni significación calibrada. **No es prueba primaria.**

## 9. Compuertas (sin mirar resultados)
- **Integridad:** hashes del protocolo, del código y de los manifiestos; candado de uso único.
- **Calidad de datos:** umbrales de §4 de cada propuesta.
- **Factibilidad:** número esperado de operaciones en E ≥ N_min, estimado **solo con conteos**: F0 en H-REV-SHOCK; la frecuencia de señales de D en H-EMA9-VWAP, contada sin P&L. Requiere autorización.
- **Se elimina la compuerta de futilidad «P < 0,10 en D» de las v0.1.**
  - Decidir qué avanza a E según un resultado de D sesga la familia de hipótesis que llegan a E (selección por resultado).
  - D no es independiente de E (mismo diseñador, mismo mercado).
  - Si se quisiera una regla de futilidad, tendría que calibrarse su efecto en el error de toda la cadena D → E, y no hay base para hacerlo.

## 10. Supuestos y limitaciones
- **Estacionariedad débil y mezcla de la serie de exceso:** necesarias para el bootstrap por bloques; los regímenes de cripto la ponen en duda (por eso el proceso C6).
- **ε se estima en la misma muestra:** su efecto en la varianza es de orden menor y se ignora (declarado).
- **El conjunto** promedia dos activos muy correlacionados: la información efectiva es menor que el doble.
- **Los costos son supuestos**, no medidos.

## 11. Fórmulas y supuestos para revisar (también por otros modelos)

**Fórmulas:**
- **Exceso diario:** x_d = R_d − B_d (§2).
- **Prueba:** T, σ̂_C, T* y p (§4); intervalos percentil-t (§4.5).
- **Potencia:** años ≈ ((z_{1−α} + z_{1−β})·TE/δ)², con z_{0,975} + z_{0,80} = 2,8016.
- **Por operación:** δ_op ≈ 2,8016·s_op/√N.

**Puntos de posible desacuerdo metodológico** (los explicito; no hubo revisión independiente):
1. Bootstrap-t con ℓ fijo frente a selección automática de ℓ (Politis–White).
   - **Recomiendo ℓ fijo:** la selección automática depende de los datos. No favorece el resultado, pero complica la calibración.
2. Benchmark de exposición equivalente frente a buy and hold como primario.
   - **Recomiendo el primero:** es la pregunta de timing. Buy and hold responde «¿conviene más que mantener?», que es otra pregunta.
3. Bonferroni frente a Holm entre las dos hipótesis.
   - **Recomiendo Bonferroni:** no requiere simultaneidad.
4. Prueba en frecuencia diaria frente a por operación (H-REV-SHOCK).
   - **Recomiendo la diaria**, por coherencia con el benchmark, con la de operación como descriptiva.
   - Con pocos eventos, la de operación es más interpretable; el desacuerdo es razonable.
5. El efecto mínimo relevante δ es una decisión **económica**, no estadística [D-S4].
