# E3R · Plan de la ejecución confirmatoria única de E3 (H1 y H2)

**Estado:** preparado y probado solo con datos sintéticos. **No ejecutado.** Para ejecutarlo hace falta tu autorización expresa (§5).
**Fecha:** 2026-10-26.
**Ningún resultado de este plan autoriza capital** (v3 §6.5).

## 1. Por qué este experimento y no otro
De las 18 hipótesis con resultado del programa:
- 7 están refutadas;
- 8 no mostraron ventaja;
- 3 nunca se probaron (E3-H1, E3-H2 y E3-H3, «no evaluables»).

E3-H1/H2 (momentum transversal de 1 a 4 semanas en Binance spot) es la **única** línea que cumple todo esto:
- tiene fundamento publicado;
- tiene datos ya descargados y verificados, sin costo nuevo;
- tiene protocolo, código y calibración congelados desde el 2026-10-20.

Su resultado cambia decisiones concretas (§2).

**Alternativas descartadas:**
- **T-papel** sigue sola hasta su revisión del 2027-04-18; no requiere trabajo.
- **H-E1-BC** solo se confirma en SOL y ETH, y los retornos reservados de SOL no se pueden leer.
- **C8** (prima de varianza) requiere datos pagos.
- **Reabrir T, T-MULTI o H-CARRY** está prohibido.

## 2. Qué decide cada resultado (fijado antes de ver datos)
| Clasificación (v3 §6.5) | Consecuencia para el proyecto |
|---|---|
| **INVÁLIDO** (falla la validez previa, §10) | E3 queda cerrado definitivamente. No se intenta otra ventana ni otra adenda |
| **EN CONTRA** o **INSUFICIENTE** | Se cierra la línea C5. Caen con ella las extensiones que dependían de que H1 mostrara información: funding transversal y CTREND. Queda solo T-papel (prospectiva). Recomendación: pausar la investigación histórica nueva y no invertir más en la infraestructura de vivo hasta la revisión de T-papel |
| **NO CONCLUYENTE (H2 sin H1)** | Cierre (v3 §6.5). Igual que la fila anterior |
| **INFORMACIÓN SIN VENTAJA OPERABLE** o **VENTAJA NO ROBUSTA** | Sin capital. Puede habilitarse un seguimiento en papel solo informativo (decisión tuya). Las extensiones diferidas solo se prerregistran con datos nuevos |
| **RESPALDADA HISTÓRICAMENTE** | Sin capital. Habilita, cada una con autorización aparte: H3 (una corrida), la ventana ciega C (desde 2026-06-01) y la evaluación prospectiva P. El trabajo de ingeniería pasa a un ejecutor en papel para la cartera transversal |

**Sin repeticiones.** Cualquiera sea el resultado, no se corren variantes sobre estos datos. Toda corrida no planificada es exploratoria y no cambia ninguna clasificación (v3 §3.3).

## 3. Diseño: dónde está fijado cada elemento
| Elemento | Dónde | Resumen |
|---|---|---|
| Hipótesis falsable y fundamento | v3 §3.1, §6.1 | H1: E[IC] ≤ 0 en U100. H2: E[exceso neto frente a EW-U30] ≤ 0. Relevancia económica: δ_IC = 0,01 |
| Universo y exclusiones | v3 §4.4–4.6; Adenda R2 | Pares USDT con 30 días activos seguidos, edad ≥ 180 días y mediana de volumen ≥ 1 M USDT. Se excluyen estables, fiat, apalancados, volatilidad < 10 % y duplicados. R2 parte los cortes con salto ≥ ×10 sin mapeo |
| Datos, calidad y período | v3 §2, §9; F3 de E3 | Klines 1d de Binance Vision con checksum, 757 pares. Período: desde el inicio de H (P0) hasta la última formación del 2026-05-18. **Nada ≥ 2026-06-01** |
| Supervivencia | Adenda R (+ R1′); P0 | Evidencia interna del venue (filas de suspensión, colas en cero) en lugar del archivo web, que no alcanzaba |
| Desarrollo, validación y fuera de muestra | v3 §1, §6.5 | Histórico **con contaminación declarada**. La única evidencia independiente es la ventana C (ciega) y P (prospectiva), que esta corrida solo habilita |
| Referencia | v3 §4.12 | EW-U30 con el mismo motor y los mismos costos. Descriptivo: BTC comprar y mantener, y efectivo |
| Comisión, spread y deslizamiento | v3 §4.9, N15 | 10 pb más un tramo de 5 a 30 pb por liquidez. Liquidaciones a 40 pb. Estrés con costos ×2 (R1) |
| Latencia | R2 | Ejecución un día después, para la cartera y para EW-U30 |
| Funding | — | No aplica: spot, solo largos, sin apalancamiento |
| Ejecuciones parciales | — | **No se modelan** (limitación). Se supone ejecución completa a la apertura en pares con ≥ 1 M USDT diarios, con tramos de costo por liquidez. Vale solo para tamaños chicos frente a ese volumen |
| Órdenes fallidas y datos faltantes | v3 §4.10, §6.4, N21 | Compra sin apertura: el lugar queda en efectivo. Venta sin apertura: se reintenta. 30 días inactivos: liquidación contable, con estrés al −30 % (R6). Se cuentan las marcas obsoletas |
| Métricas principales | v3 §4.13, §5 | H1: IC̄ con Newey–West L = 4. H2: 52·ē con p = máx(boot ℓ13, boot ℓ26, NW13) e IC90 envolvente (Enmienda 2) |
| Riesgo y descriptivo | v3 §6.2; orquestador | Caída máxima, CVaR 5 %, peor semana, tiempo bajo el agua, volatilidad, Sharpe, Sortino, beta y correlación con BTC, exposición, rotación, entradas por semana y operaciones estimadas |
| Estabilidad por período | R3; orquestador | IC̄ y exceso por tercios (condición R3) y por año (descriptivo) |
| Sensibilidad a costos | R1; orquestador | Exceso con costos ×0, ×1 y ×2 |
| Tamaño de muestra y potencia | P0d; v3 §7 | H1 con 274 semanas: potencia 0,54–0,79 para IC 0,02 (umbral 2,5 %). Con 160 semanas: 0,35–0,56 |
| Sobreajuste, selección y multiplicidad | v3 §3.2–3.4, §6.3 | Una sola corrida y Holm m = 2. Robustez R1–R6 con nulo aleatorio de 2000 réplicas. Sharpe deflactado con N = 20. Grilla de 15 configuraciones solo descriptiva. Parámetros fijados el 2026-10-20 |
| Criterios de continuar, reformular o descartar | §2 de este plan; v3 §6.5 | Fijados arriba. **No se cambian después de ver resultados** |

**Operacionalizaciones que la v3 no fijaba** (fijadas en el encabezado del orquestador congelado, antes de cualquier dato):
- semillas de R5 y del diagnóstico §5.4;
- cómo «anular aportes» en el §6.4;
- la fuente de BTC;
- el conjunto de 20 configuraciones del Sharpe deflactado.

El exceso de timing de T (N19) **no se calcula**, porque T no se reabre.

## 4. La única decisión abierta: qué ventana
| | **Opción A: R1 literal** | **Opción B: R1 + R1′ (recomendada)** |
|---|---|---|
| Inicio de H | 2023-05-01 | 2021-02-22 |
| Semanas evaluables | 160 | 274 |
| Qué fija el inicio | DOTUP, DOTDOWN y TRXDOWN (apalancados, retirados el 2023-04-27) | BKRW (retirado el 2021-02-19) |
| Potencia de H1 (IC 0,02, al 2,5 %) | 0,35–0,56 | 0,54–0,79 |
| IC mínimo detectable al 80 % | 0,027–0,035 | 0,020–0,027 |
| Regímenes | 2023–2026 | Además, la subida de 2021 y la caída de 2022 (LUNA, FTT) |

**Por qué recomiendo B:**
1. La regla (ii) de inicio existe para que una salida no registrada no sesgue el **universo elegible**. Los apalancados **nunca** son elegibles (§4.5): una falla suya no puede sesgar nada. Esa es la intención escrita en la propia R1.
2. La elección sigue **ciega al resultado**. P0 solo leyó vectores de estado y listas; nadie calculó un retorno, un IC ni un exceso.
3. Con 160 semanas, un IC económicamente relevante (≈ 0,02) se detecta menos de la mitad de las veces. Un «insuficiente» casi no informaría.

**El costo de B:** sienta el precedente de corregir una regla después de ver qué ventana produce. Queda escrito y congelado con su motivo (`CORRECCION_R1prima_alcance_por_clase.md`, `86c8fd0b…`), y la opción A sigue disponible.

**Observación sin cambios:** BKRW es un estable atado al won y probablemente quedaría excluido por el filtro de volatilidad. R1′ no lo cubre, y **no** extiendo la regla. El inicio de B es, si acaso, conservador.

## 5. Autorización (exacta)
El orquestador (`ejecutar_E3R.py`, `3b64a04d…`) se niega a ejecutar salvo que el archivo de autorización contenga todo esto:
- la frase exacta;
- los sha256 de la opción elegida;
- **ningún** hash del P0 de la otra opción.

Además, la salida no puede existir de antes (ejecución única), y el registro se escribe antes de calcular.

**Frase:** `AUTORIZO LA EJECUCION UNICA DE E3 (H1 Y H2) CON LA V3 MAS LA ADENDA R Y LA ADENDA R2`

**Hashes comunes a las dos opciones:**
```
3b64a04dcb6b39d20cb218ff5f5ef0bd03c1dd45cd75e475b0640fb1ecfd8dce  ejecutar_E3R.py
87f60413725a8f0360f39b9b6343027cbda4233c1cd2d3bd1d94080f0bf6936a  ADENDA_R_auditoria_de_supervivencia_interna.md
6905afd4f579905474de548251bf43f0346047c7bca7dc59a1f7a74bf4bb090c  ADENDA_R2_cortes_con_salto_de_precio.md
```

**Opción A:**
```
a73c9755b0dc3ae02e5fcfad68e4512abb8a1e98b11666078fb2e737eb457d0f  P0_resultado.json
```

**Opción B:**
```
6d3f563275b5d251ffa87ec3b199b46d76712610a8ea9ea72b8b1b34d7fbe5d8  P0_resultado_R1prima.json
86c8fd0b0a3b2fe2728d277b9e106b5e46a651950c767df46a00b68c5fb4e848  CORRECCION_R1prima_alcance_por_clase.md
```

**Cómo autorizar:** respondé con la frase y la letra de la opción. Yo creo el archivo con tu mensaje textual y esos hashes, y ejecuto **una vez**:
```
python -I ejecutar_E3R.py real <dir_E3> <P0 elegido> <autorizacion.txt> <salida nueva>
```
- **Duración estimada:** 10–20 min.
- **Qué entrego después:** `RESULTADO_E3R.json` y un informe con la clasificación tal cual salga.

La guarda es un control de procedimiento, no una barrera de seguridad. El control real es que **no creo ese archivo sin tu mensaje**.

## 6. Qué no se hace en ningún caso
- No se leen datos ≥ 2026-06-01.
- No se modifica nada de E3: se verifica su manifiesto antes y después.
- No se corre H3 sin otra autorización.
- No se reabren T, T-MULTI ni H-CARRY.
- No se opera dinero real. **NO AUTORIZADO PARA OPERAR CON DINERO REAL.**
