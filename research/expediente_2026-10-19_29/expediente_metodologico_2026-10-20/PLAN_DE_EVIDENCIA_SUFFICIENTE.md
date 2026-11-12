# Plan de evidencia suficiente (Trader-IA, 2026-10-20)

> - **Documento de diseño.** No se ejecutó ninguna etapa empírica.
> - El nombre del archivo respeta el que pediste («SUFFICIENTE»).
> - Las cifras de potencia son **aritmética sobre supuestos declarados**, más una sola cifra derivada del resultado ya registrado de T. **No se usó ningún dato de precios.** Fuente: `evidencia/02_aritmetica_potencia_costos.txt`.

## 1. Principio
- **Evidencia suficiente** = una conclusión que un auditor pueda reproducir y que controle el error. El resultado puede ser:
  - (a) ventaja respaldada;
  - (b) en contra, o efecto relevante descartado;
  - (c) **no concluyente dentro del horizonte disponible**.
- **(c) es un resultado válido.** El plan **no** relaja α, ni repite E, ni agrega variantes para salir de (c).
- **Lo que vuelve concluyente un programa** es la evidencia **independiente** (prospectiva u otra fuente externa aprobada), no más pruebas sobre el mismo período contaminado.

## 2. Etapas, con criterios de entrada y de salida fijados de antemano

| Etapa | Entrada | Trabajo | Salida (criterio de paso) | Autorización |
|---|---|---|---|---|
| **A. Integridad y especificación** | Propuestas v0.2 y MEC v0.2 | Resolver las decisiones de `MATRIZ_DE_DECISIONES_PENDIENTES.md`. **Una configuración primaria por hipótesis.** Congelar el texto aprobado con SHA-256 | Texto aprobado y congelado; cero ambigüedades abiertas; originales ausentes, propuestas y versiones aprobadas claramente separados | A-G1 (aprobación por hipótesis) |
| **B. Pruebas sintéticas** | A cerrada | Implementar y probar con datos **sintéticos** (§3). Calibrar la prueba (MEC §5) | **Todas** las pruebas de §3 pasan; la calibración cumple las bandas o activa la regla de respaldo, también calibrada; el código queda congelado con hash | A-S1 (calibración), A-RS-2 y A-EV-2 (implementación) |
| **C. Desarrollo histórico** | B cerrada | D para verificar la implementación con datos reales, la frecuencia y la factibilidad. **Sin seleccionar parámetros** | Implementación coherente (las invariantes de §3 también con datos reales); factibilidad N_E proyectado ≥ N_min | A-RS-1 (F0), A-RS-3 y A-EV-3 (ejecutar D) |
| **D. Evaluación histórica única** | C cerrada, protocolo y código congelados, datos con manifiesto | **E una sola vez**, con candado. Regla de MEC §7 | Categoría registrada con hashes, entorno y semilla. **Contaminación declarada en el resultado** | Autorización expresa de E |
| **E. Prospectiva (papel)** | D registrada, o directamente desde A si así lo decides | Papel con reglas congeladas y prueba secuencial (MEC §7.1) | Rechazo con gasto de α, futilidad no vinculante, o n_max alcanzado | A-RS-4 y A-EV-4 (descarga prospectiva y ubicación de los registros) |
| **F. Viabilidad operativa** | Solo si E da confirmación | Medir fills, spread, slippage, latencia y capacidad (§6) | Informe separado | Otra autorización. **No autoriza live ni dinero real** |

**Notas:**
- La Etapa C **no** tiene compuerta por resultado (MEC §9).
- El paso de C a D depende de la integridad y la factibilidad, **no de la rentabilidad de D**.
- **Posible atajo** (decisión D-G2): ir de A y B directamente a E (papel) y prescindir de D y E históricas. Se evita la contaminación; se pierde la detección temprana de un fracaso grueso.

## 3. Etapa B: pruebas sintéticas y criterios de aceptación (diseño; no ejecutadas)
| ID | Prueba | Criterio de aceptación |
|---|---|---|
| B1 | **Truncamiento:** señales, posiciones y P&L calculados con la serie hasta t, frente a la serie completa, en 20 cortes al azar (semilla fija) | Idénticos hasta t − 1, bit a bit |
| B2 | **Mirada al futuro inyectada:** se altera C_{t+1} y se comprueba que no cambia ninguna decisión en t | Cero cambios |
| B3 | **Datos faltantes:** huecos de 1, 5 y 30 barras; conflictos; aperturas ausentes | Siguen exactamente §3 de cada propuesta (entrada omitida, salida diferida, bloqueo de señales) |
| B4 | **Ejecución en la barra siguiente:** precio, costo y momento | Coinciden con un cálculo a mano en 10 casos fijados |
| B5 | **Costos y composición:** unidades q, cobro y W_t (MEC §2) | Error ≤ 1e−12 frente a una referencia independiente |
| B6 | **Máquina de estados** (H-REV-SHOCK): shocks consecutivos, REF fija y L\* acumulado; agotamiento; las tres salidas | Casos de borde fijados de antemano, todos correctos |
| B7 | **VWAP y EMA** (H-EMA9-VWAP): Σ QV/Σ V; columnas 5 y 7 intercambiadas a propósito (la prueba debe fallar); EMA frente a una referencia; marcas en µs | Error ≤ 1e−12; el intercambio se detecta |
| B8 | **Fin de la ventana:** liquidación en el último cierre válido; ninguna lectura posterior | Lecturas fuera de la ventana = 0 (instrumentado) |
| B9 | **Contabilidad:** suma de los P&L por operación = variación de W | Diferencia ≤ 1e−9 |
| B10 | **Calibración de la prueba primaria** (MEC §5) | Bandas cumplidas |
| B11 | **Control positivo:** efecto plantado de tamaño δ y 2δ | Se informa la potencia (sin umbral; es descriptiva) |
| B12 | **Control negativo:** paseo aleatorio, con los mismos costos | x̄ ≈ −costo; tasa de rechazo dentro de la banda |

Estas pruebas **detectan defectos**; **no** son evidencia de rentabilidad.

## 4. Pregunta central: ¿cuánta evidencia hace falta?

### 4.1 Fórmula
- **Años necesarios** para rechazar H₀ con potencia 1 − β frente a un exceso real δ:
  **años ≈ ((z_{1−α} + z_{1−β}) · TE / δ)²**
  - TE: desvío anualizado del exceso diario, que ya incluye la dependencia si se estima con HAC o por bloques.
  - Con α = 0,025 unilateral y potencia del 80 %, el factor es **2,8016**.
- **Número efectivo de observaciones:** n_eff = n / (1 + 2Σ_k ρ_k). En estrategias por eventos, n_eff ≈ el número de operaciones **no agrupadas**: los eventos simultáneos en BTC y ETH cuentan casi como uno.

### 4.2 Tabla general (supuestos, no datos)
| TE/δ | 0,5 | 1 | 1,5 | 2 | 3 |
|---|---|---|---|---|---|
| Años (α = 0,025; 80 %) | 2,0 | 7,8 | 17,7 | 31,4 | 70,6 |

- **Efecto mínimo detectable en E** (4,42 años): δ_min ≈ **1,33 · TE**.

### 4.3 T (la única línea con una cifra registrada para estimar TE)
- **TE implícito en el IC90 registrado** (aproximación normal del IC percentil): **≈ 20,2 %/año**.

| δ supuesto | Años necesarios (α = 0,025; 80 %) |
|---|---|
| +7,05 %/año (estimación fuera de muestra) | **≈ 65** |
| +10 %/año | ≈ 32 |
| +19,4 %/año (desarrollo, probablemente inflado) | ≈ 8,6 |

- **Conclusión defendible:** el papel de T **no puede confirmar** un efecto del orden estimado fuera de muestra en ningún horizonte práctico. Solo puede:
  - (i) confirmar un efecto grande, cercano al de desarrollo, en unos 9 años;
  - (ii) detectar un fracaso grueso (la regla de detener a los 12 meses).
- Esto coincide con lo que ya decían los documentos de T (potencia baja) y **no se resuelve relajando umbrales**.

### 4.4 H-REV-SHOCK y H-EMA9-VWAP
- **TE desconocido.** No se estima con datos sin autorización (F0 y D).
- **Ilustraciones por operación** (supuestos de las propuestas v0.2):
  - **H-REV-SHOCK:** con s_op ≈ 12,6 % y N = 30, se detectarían ≥ 6,4 % por operación; con N = 100, ≥ 3,5 %.
    - Hay pocos eventos por año: **la confirmación prospectiva de un efecto moderado probablemente no es alcanzable** con solo BTC y ETH.
  - **H-EMA9-VWAP:** con s_op ≈ 1,7 % y N = 300, se detectarían ≥ 0,28 % netos por operación.
    - La potencia es mejor, **pero el costo de 30 pb es del mismo orden**.

### 4.5 Miradas repetidas
- **Sin corrección, el error de tipo I se infla:** con K miradas al 5 %, la cota de Bonferroni es K·5 % (25 % con 5 miradas).
- **Las propuestas usan gasto de α de O'Brien–Fleming** (MEC §7.1) y un n_max calculado **antes** de empezar.
- **T no tiene esa corrección:** su protocolo congelado permite declarar «respaldada» en cada corte desde los 24 meses («36…», sin límite). **Es una limitación documentada.**
  - Corregirla exigiría una enmienda **antes de la primera mirada** (decisión D-T2). No se hace sin tu aprobación.

### 4.6 Fuentes independientes (cada una sería un experimento NUEVO; no se incorporan)
| Opción | Qué aporta | Costo y riesgo |
|---|---|---|
| Más tiempo prospectivo | Independencia real | Años o décadas (§4.3–4.4) |
| Otro exchange (mismos activos) | Microestructura distinta | Precios muy correlacionados con Binance: poca independencia |
| Más activos cripto | Más eventos | Supervivencia (E3 mostró que no hay anuncios suficientes para reconstruirla) y correlación con BTC |
| Otros mercados (ETF, como T-MULTI) | Independencia del régimen cripto | Otra pregunta; T-MULTI ya dio INSUFICIENTE para T |

- **Recomendación:** no ampliar hasta tener el resultado de A–B y, en su caso, de D–E. Cada ampliación necesita su propio prerregistro y tu aprobación (D-G3).

## 5. Etapa E (prospectiva): protocolo mínimo
- **Datos:** posteriores al corte fijado (historia desde el 2026-10-14; P empieza en la fecha de aprobación).
- **Fuente:** archivos oficiales con checksum, descargados por un ejecutor que se niega a evaluar si faltan datos o si alguna huella no coincide (como `papel/corte.py` de T).
- **Registro:** solo de añadidos, encadenado por hash y **fuera del repositorio** (ubicación por decidir, D-G4).
- **Interrupciones:**
  - un día o una barra sin datos sigue las reglas de faltantes;
  - un fallo del ejecutor se reintenta sin mirar resultados;
  - nunca se rellena.
- **Cortes:** en fechas de calendario fijadas al aprobar. En cada uno se aplica la prueba secuencial (MEC §7.1).
- **Parada:**
  - rechazo con gasto de α → «confirmada prospectivamente»;
  - futilidad no vinculante (IC90 < δ) → «efecto relevante descartado»;
  - n_max sin rechazo → «no concluyente».
- **Auditoría independiente:** un segundo proceso recalcula desde los archivos oficiales y compara los hashes de la salida (Plan de auditoría §4).
- **Sin miradas fuera de calendario.** Si alguna ocurre, se registra.

## 6. Etapa F (viabilidad): qué evidencia haría falta
- **Medición en papel en tiempo real de la ejecución simulada**, sin enviar órdenes:
  - spread observado en el momento de la señal;
  - profundidad del libro para el tamaño previsto;
  - latencia entre la publicación de la vela y la decisión;
  - capacidad: impacto estimado con el libro.
- **Se separa de la rentabilidad.** No autoriza operaciones reales, ni cambios en el sistema de trading, ni live.
- **La simulación de 12 h existente no se modifica.**

## 7. Qué resultados darían evidencia suficiente
- **A favor:**
  1. nivel 2 en E (p ≤ 0,025, sin invalidez) **y**
  2. nivel 3 (robusto) **y**
  3. nivel 4 (confirmación prospectiva con gasto de α).
  - **Solo con los tres** es defendible decir «ventaja después de costos, con evidencia independiente».
  - Aun así, **no** prueba viabilidad operativa (nivel 5).
- **En contra:** EN CONTRA o EFECTO RELEVANTE DESCARTADO en E, o futilidad prospectiva.
- **No concluyente:** cualquier otro caso. Es un resultado legítimo y se informa como tal.
