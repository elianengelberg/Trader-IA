# Registro de hipótesis de Trader-IA (estado al 2026-10-19, tras la investigación E3)

> Versión nueva. La anterior (`../E2_descubrimiento_2026-10-19/ronda_E2/informe/REGISTRO_HIPOTESIS_tras_E2.md`) se conserva sin cambios. Esta versión agrega las propuestas y descartes de la fase de investigación E3 (`INFORME_E3.md`). **No se ejecutó ninguna prueba nueva.**

> Historia: la versión tras E2 agregó los resultados de E2-A, E2-B y E2-C (`../E2_descubrimiento_2026-10-19/ronda_E2/informe/INFORME_E2.md`) y sus consecuencias (C13). La versión original es `../E2_descubrimiento_2026-10-19/REGISTRO_HIPOTESIS.md`.

Estados posibles:
- **DESCARTADA:** evidencia en contra, o sin base;
- **INSUFICIENTE:** probada, sin conclusión;
- **CERRADA:** por decisión del proyecto;
- **PROSPECTIVA:** solo se evalúa con datos futuros;
- **EXPLORATORIA:** pista posterior, sin confirmar;
- **PROPUESTA:** sin probar.

Ninguna hipótesis descartada se reabre sin un prerregistro nuevo y una razón que no venga de mirar los mismos datos.

## Probadas
| ID | Hipótesis | Estado | Evidencia [TIA] | Artefactos |
|---|---|---|---|---|
| H-CARRY | Carry de funding delta neutral (BTC) con ventaja neta | CERRADA (insuficiente) | Test: +3,76 % frente a un comparador del 5 % | `research/hcarry_next/INFORME_CIERRE_HCARRY.md` |
| V | Volatilidad gestionada en BTC diario | DESCARTADA | Persistencia de 0,32 (< 0,5); Sharpe 0,92 frente a 0,96; P = 0,38 | `research/tendencia_btc/INFORME_NUEVA_LINEA.md` |
| R | Reversión diaria en BTC | DESCARTADA (sin base) | Autocorrelación de retardo 1 de −0,06 (la regla exigía < −0,10) | ídem |
| T | Tendencia long/flat 1/3/6 meses (BTC y ETH), histórica | INSUFICIENTE · historia CERRADA | Fuera de muestra +7,0 %/año, IC90 −8,8 / +22,9, P = 0,755 | `INFORME_FUERA_DE_MUESTRA_T.md` |
| T-papel | T sin cambios, prospectiva | PROSPECTIVA (en curso) | Inicio el 2026-10-18; revisiones el 2027-04-18, el 2027-10-19 y el 2028-10-18 | `papel/PRERREGISTRO_PAPEL.md` |
| T-MULTI | T sin cambios en 11 ETF | INSUFICIENTE (excluida una ventaja neta ≥ 0,65 %/año) | E = −0,48 %, IC90 −1,55 / +0,65, P = 0,24 | `INFORME_T_MULTI.md`, paquete v2 |
| E1-P1 | trend_following del bot (BTC 1 h, solo largos) | DESCARTADA (en contra) | −0,237 %/op., IC90 −0,341 / −0,135; p_nulo 0,45 | `experimentos/E1_bot_datos_reales_2026-10-19/` |
| E1-P2 | mean_reversion del bot | DESCARTADA (en contra) | −0,519 %/op., IC90 −0,724 / −0,310; p_nulo 0,94 | ídem |
| E1-P3 | breakout del bot | DESCARTADA (en contra, al límite) | −0,198 %/op., IC90 −0,381 / −0,017; p_nulo 0,32 | ídem |
| E1-S1 | Fusión de las 3 (el bot como opera) | DESCARTADA (descriptiva) | −0,294 %/op., IC90 −0,384 / −0,209 | ídem |
| E1-S5 | El lado corto del bot (hipotético, sin costo de préstamo) | DESCARTADA | Peor que el largo en las 4 configuraciones; no ejecutable en spot | ídem |
| E1-CONF | La confianza del bot ordena los retornos (trend, MR, fusión) | DESCARTADA | Spearman −0,02, −0,08 y −0,02, con IC que incluyen 0 | ídem |
| C3 / E2-A | VOL30, VOLUMEN_Z30, FUNDING7, PRIMA7 o DD90 aportan información lineal incremental sobre el momentum de T a 7 y 28 días (BTC y ETH) | INSUFICIENTE (en sustancia, nula); compuerta **cerrada** | p de familia 1,0; 9/10 ΔR² < 0; único > 0: DD90 h7 +0,09 % (p 0,14), que **no** se persigue. Datos reutilizados | `../E2_descubrimiento_2026-10-19/ronda_E2/informe/INFORME_E2.md` |
| C1 / E2-B | Funding extremo (P10/P90 expansivos de F7) como timing contrario de spot | INSUFICIENTE (estimación puntual negativa); **archivada** | Exceso neto −0,10 %/año, IC90 −10,4 / +9,2, P 0,52; ×2 −1,10 %. BTC +1,75 y ETH −1,94. Efecto mínimo detectable ≈ 15 %/año. Datos reutilizados | ídem |
| C2 / E2-C | Cambio de 4 semanas en las vistas de Wikipedia «Bitcoin» mejora el pronóstico de BTC a 7 días frente al momentum | DESCARTADA (en contra) | t de CW −1,39, p 0,918; ΔR² −5,2 % (IC90 descriptivo −9,6 / −1,6); 2018-03 → 2026-05. Datos nuevos | ídem |

## Pistas y variantes que no se pueden probar con los mismos datos
| ID | Hipótesis | Estado | Nota |
|---|---|---|---|
| H-E1-BC | La confianza de breakout ordena los retornos | EXPLORATORIA | ρ = +0,22 en BTC; 1 de 4 miradas. Protocolo en `PROTOCOLO_H_E1_BC_BORRADOR.md`; confirmación solo en ETH y SOL |
| T-baja-rotación | T con menos operaciones | PROSPECTIVA | Motivada por T-MULTI (los costos se comen el bruto): no se prueba con los datos que la motivaron |
| E1-MR-retraso | Las entradas de MR retrasadas 1 barra pierden menos (−0,18 % frente a −0,52 %) | EXPLORATORIA (sin valor práctico) | Solo descriptiva: sugiere que la entrada de MR «agarra cuchillos que caen» |

## Propuestas restantes de E2 (ver `INVESTIGACION_E2.md`; C1, C2 y C3 ya se probaron, arriba)
| ID | Hipótesis | Estado |
|---|---|---|
| C5 | Momentum transversal entre criptos (solo largos) | **PRIORIDAD 1 en E3** → E3-H1 y E3-H2 (abajo) |
| C6 | Valor relativo BTC/ETH por reversión del cociente | PROPUESTA (baja prioridad) |
| C7 | Régimen on-chain (MVRV-Z) | PROPUESTA (baja prioridad) |
| C8 | Prima de riesgo de varianza | PROPUESTA: solo un estudio de viabilidad documental (E3) |
| C9 | Ventanas macro como gestión de riesgo | PROPUESTA (baja prioridad) |
| C10 | Reversión tras movimientos extremos | DESCARTADA en E3 (sin evidencia rigurosa; faltan datos) |
| C13 | IA de selección o abstención sobre una señal base | **SIN BASE**: C3 (E2-A) no encontró información incremental |
| C4 | T sin cambios en otras criptos | NO INDEPENDIENTE de T (E3): no se prueba |
| C11 | Lead-lag entre criptos de minutos | DESCARTADA en esta fase (alta frecuencia) |
| C12 | Estacionalidad o calendario | DESCARTADA en esta fase (sin mecanismo; minería de datos) |
| C14 | Carry o base con vencimiento | CERRADA (sigue la regla de H-CARRY) |
| LLM-hist | Juicio de un LLM sobre noticias históricas | DESCARTADA para backtest (el modelo conoce el futuro); solo prospectiva |

## Variantes prohibidas tras E2 (para no reabrir por la puerta de atrás)
- Otros umbrales, ventanas u horizontes para F7, o la prima como señal de colas (C1).
- Otros artículos, idiomas o métricas de Wikipedia; otros horizontes de atención (C2).
- DD90 a 7 días, o cualquier subconjunto de las 5 variables elegido por su resultado en E2-A (C3).
- Versiones no lineales o por régimen de las mismas variables, sobre los mismos datos.
Reabrir cualquiera exige un prerregistro nuevo, con datos no vistos y una razón que no venga de estos resultados.

## Fase de investigación E3 (2026-10-19; sin datos ni pruebas)
| ID | Hipótesis | Estado | Nota |
|---|---|---|---|
| E3-H1 (C5) | La señal compuesta de momentum de 1–4 semanas ordena el retorno de la semana siguiente en el universo líquido de Binance spot (U100) | **PROPUESTA: prioridad 1** | Protocolo en `PROTOCOLO_E3_BORRADOR.md`; requiere autorización de descarga (altcoins, hasta 2024-12) |
| E3-H2 (C5) | La cartera long-only top 6 de U30, con banda y costos, supera a EW-U30 | **PROPUESTA** | Potencia baja (efecto mínimo ≈ 35–45 %/año [Hip]) |
| E3-H3 | La capa de efectivo por momentum absoluto agrega valor de timing a la cartera de E3-H2 | **PROPUESTA (expectativa baja)** | Potencia ≈ E2-B |
| C8 (prima de varianza) | Venta de volatilidad en BTC | PROPUESTA: solo un estudio de viabilidad documental | Fuente más independiente; requiere infraestructura y datos pagos |
| Funding transversal | El funding relativo extremo predice un rendimiento relativo menor | DIFERIDA | Solo como interacción si E3-H1 muestra información; sin estudios publicados |
| CTREND o aprendizaje automático transversal | Tendencia multihorizonte con volumen | DIFERIDA | Extensión de C5 solo si la versión simple muestra información |
| C4 (T en altcoins), momentum temporal multihorizonte, rupturas diarias | Tendencia propia | **NO INDEPENDIENTES** de T | Siguen T-papel; no se reabren |
| Reversión transversal de corto plazo | Provisión de liquidez | DESCARTADA en esta fase | Vive en pares ilíquidos; costos |
| Reversión tras extremos o liquidaciones | Ventas forzadas | DESCARTADA en esta fase | Sin evidencia rigurosa; R y E1-MR en contra; faltan datos |
| Tamaño, MAX, valor o red, deriva tras listados, emisión de stablecoins, sector o narrativa | Varios | DESCARTADAS en esta fase | Supervivencia, evidencia contradictoria o datos no disponibles en el tiempo; la deriva tras listados se usa como regla de exclusión |

**Períodos reservados fijados en E3:** [2025-01-01, 2026-06-01) para E3, sin descargar; el de H-CARRY, [2026-06-01, 2026-10-14), sigue intacto.
