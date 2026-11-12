# Matriz de decisiones pendientes (2026-10-20)

**Cómo leerla:** cada decisión es independiente; **no** se pide aprobar en bloque. «Recomendación» es mi juicio como revisor. La columna «Tipo» indica si la decisión es estadística (E), económica (Ec), convencional (C), de procedimiento (P) o de autorización (A).

## G. Programa
| ID | Decisión | Opciones | Recomendación | Fundamento | Impacto | Tipo / autorización |
|---|---|---|---|---|---|---|
| **D-G0** | **Preservar el expediente fuera del scratchpad** | (a) Lo descargás tú; (b) almacenamiento externo que indiques; (c) nada | **(a) o (b) cuanto antes** | El scratchpad es **efímero**: el contenedor se libera tras un tiempo de inactividad. Los hashes no sirven si los archivos se pierden | Sin esto, todo este trabajo puede desaparecer | P / tuya |
| D-G1 | Seguir con cada hipótesis | Por hipótesis: aprobar v0.2, aprobar con cambios, rechazar o abandonar | Decidir **por separado**. H-REV-SHOCK solo si aceptás D-G5. H-EMA9-VWAP con expectativa baja por el costo | §4 del plan: potencia y costos | Determina todo lo demás | P / A-G1 |
| D-G2 | Camino | (a) D → E → P; (b) solo P (prospectivo); (c) F0 o el conteo de D primero, y luego (a) o (b) | **(c)**: medir la factibilidad sin P&L antes de gastar E | E está contaminado; la factibilidad evita gastar el uso único en una prueba casi seguro inconclusa | Tiempo y uso del período histórico | P / A-RS-1, A-EV-3 |
| D-G3 | Ampliar a otros activos, exchanges o mercados | Sí (experimento nuevo) o no por ahora | **No por ahora** | Supervivencia (E3), correlación con BTC; cada ampliación es otra hipótesis | Más potencia, más riesgo de sesgo | P / nueva aprobación |
| D-G4 | Dónde viven los registros prospectivos (T-papel y las nuevas fases P) | (a) Dentro del repositorio (requiere tu autorización de escritura); (b) un repositorio o rama aparte; (c) almacenamiento que indiques | **(b) o (c)**, persistente y con hash encadenado | No tocar el repositorio principal; el scratchpad es efímero | Condición para cualquier corte | P / tuya |
| D-G5 | Reabrir la familia «reversión tras extremos», descartada en E3 | Reabrir con v0.2, o mantenerla descartada | **Tu decisión.** Si la reabrís, el resultado se lee como un nuevo intento sobre una familia ya descartada | Regla del registro de hipótesis | Multiplicidad del programa | P / tuya |
| D-G6 | Publicar los commits locales `f518ac1` y `692f2b2` | Publicar o no | Recomiendo publicarlos **en algún momento**: sin eso, los congelados de T fuera de muestra y de T-MULTI no son verificables desde fuera | Verificabilidad externa | Nada técnico cambia | P / tuya (prohibido sin tu orden) |

## S. Marco estadístico (MEC v0.2)
| ID | Decisión | Opciones | Recomendación | Fundamento | Impacto | Tipo / autorización |
|---|---|---|---|---|---|---|
| D-S1 | Prueba primaria | (a) Bootstrap-t centrado con ℓ = 20 y B = 9999; (b) P percentil (v0.1); (c) HAC Newey–West | **(a)**, con (c) dentro de la regla de respaldo | MEC §1 y §4: P no es un valor p | Validez del error de tipo I | E / tuya |
| D-S2 | Multiplicidad entre las dos hipótesis | Bonferroni 0,025 cada una; Holm; sin ajuste | **Bonferroni** | Válido aunque se ejecuten en momentos distintos | α efectivo | E / tuya |
| D-S3 | Regla de respaldo si la calibración falla | máx(p_{ℓ20}, p_{ℓ40}, p_NW); otro ℓ; detener | **máx(…)**, recalibrado | Ya se usó en E3 con buen tamaño | Pierde algo de potencia | E / tuya |
| D-S4 | **δ: efecto mínimo económicamente relevante** | 3 %, 5 % o 10 %/año de exceso neto | **No lo decido yo:** es **económico**. Referencia: el costo de oportunidad y el riesgo que estés dispuesto a asumir | Define «efecto relevante descartado» y n_max | Duración prospectiva | Ec / tuya |
| D-S5 | Diseño prospectivo | Gasto de α O'Brien–Fleming con n_max; cortes fijos sin corrección; sin límite | **O'Brien–Fleming** | Controla las miradas repetidas | Validez prospectiva | E / tuya |
| D-S6 | Nulo emparejado | Solo descriptivo (v0.2); dentro del criterio (v0.1) | **Solo descriptivo** | No está calibrado; MEC §8 | Criterio más limpio | E / tuya |
| D-S7 | Compuerta de D | Sin compuerta por resultado (v0.2); P < 0,10 (v0.1) | **Sin compuerta por resultado**; solo factibilidad | Sesgo de selección | — | E / tuya |
| A-S1 | **Autorizar la calibración sintética** (Etapa B10–B12) | Sí o no | Sí, cuando se aprueben D-S1 a D-S3 | No usa datos reales | Requisito para validar el MEC | A |

## T
| ID | Decisión | Opciones | Recomendación | Fundamento | Impacto | Tipo / autorización |
|---|---|---|---|---|---|---|
| D-T1 | Corte del 2027-04-18 (informativo) | Autorizar la escritura en el repositorio, o una ubicación externa (D-G4) | **Ubicación externa** | No tocar el repositorio | Sin esto no hay corte | P / tuya |
| D-T2 | Miradas repetidas desde los 24 meses | (a) No enmendar y documentar la limitación; (b) enmendar antes de la primera mirada | **(a)**: el propio protocolo dice que un cambio de reglas es una hipótesis nueva | Integridad del congelado | Cualquier «respaldada» desde los 36 meses se lee con esa advertencia | E / tuya |
| D-T3 | Expectativa sobre T | Aceptar que el papel solo detecta un efecto grande (≈ 9 años para +19 %/año) o un fracaso grueso | **Aceptarlo explícitamente** | Plan §4.3: unos 65 años para +7 %/año | Evita esperar del papel una confirmación que no puede dar | Ec / tuya |

## RS. H-REV-SHOCK v0.2
| ID | Decisión | Recomendación | Tipo |
|---|---|---|---|
| D-RS-1 | Velas diarias | Aprobar | C |
| D-RS-2 | z ≤ −3, con σ RMS de 60 días | Aprobar | C |
| D-RS-3 | Ventana de agotamiento de 3 días | Aprobar | C |
| D-RS-4 | Agotamiento = sin mínimo nuevo + cierre de giro | Aprobar (heurística declarada) | C |
| D-RS-5 | Duración máxima de 10 días | Aprobar | C |
| D-RS-6 | N_min = 30 | Aprobar antes de F0 | E |
| D-RS-8 | Historia de P desde el 2026-10-14 | Aprobar | P |
| D-RS-10 | Exigir 60 rendimientos completos | Aprobar | C |
| D-RS-C2 | REF fija en el primer shock del grupo (cambio conceptual respecto de la v0.1) | Aprobar, o volver a la v0.1 | C (conceptual) |
| A-RS-1 | **F0** (conteos en D, sin P&L ni fechas) | Autorizar si aprobás D-G1 y D-G5 | A |
| A-RS-2 | Implementación y pruebas sintéticas | Tras la Etapa A | A |
| A-RS-3 | Ejecutar D | Tras B | A |
| A-RS-E | **Ejecutar E (una vez)** | Solo si F0 proyecta N ≥ 30 | A |
| A-RS-4 | Papel prospectivo y descarga diaria | Tras D-G4 | A |

## EV. H-EMA9-VWAP v0.2
| ID | Decisión | Recomendación | Tipo |
|---|---|---|---|
| D-EV-1 | Velas de 1 h | Aprobar | C |
| D-EV-2 | Señales con apertura de 02:00 a 18:00 UTC | Aprobar | C |
| D-EV-3 | Una entrada por sesión | Aprobar | C |
| D-EV-4 | VWAP como stop; sin objetivo | Aprobar | C |
| D-EV-5 | Plazo de publicación en el papel | Fijar antes de P | P |
| D-EV-6 | Invalidez con más del 0,5 % de barras faltantes | Aprobar | C |
| D-EV-8 | Historia de P desde el 2026-10-14 | Aprobar | P |
| D-EV-9 | N_min = 100 | Aprobar | E |
| **A-EV-1** | **Descargar ETHUSDT 1h (2019-10 → 2026-05)** | Autorizar solo si aprobás D-G1 para esta hipótesis | A |
| A-EV-2 | Implementación y pruebas sintéticas | Tras la Etapa A | A |
| A-EV-3 | Ejecutar D (incluye el conteo de frecuencia sin P&L) | Tras B | A |
| A-EV-E | **Ejecutar E (una vez)** | Tras C | A |
| A-EV-4 | Papel prospectivo | Tras D-G4 | A |

## Lo que NO está en discusión (restricciones vigentes)
- Dinero real, live, despliegues, credenciales, bases de datos, sistema operativo de trading y la simulación de 12 h: **sin cambios**.
- Repetir T fuera de muestra: **prohibido**.
- Escribir en el repositorio y operaciones de git que lo alteren: **prohibidas**.
