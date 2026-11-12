# Registro de hipótesis de Trader-IA (estado al 2026-10-19)

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

## Pistas y variantes que no se pueden probar con los mismos datos
| ID | Hipótesis | Estado | Nota |
|---|---|---|---|
| H-E1-BC | La confianza de breakout ordena los retornos | EXPLORATORIA | ρ = +0,22 en BTC; 1 de 4 miradas. Protocolo en `PROTOCOLO_H_E1_BC_BORRADOR.md`; confirmación solo en ETH y SOL |
| T-baja-rotación | T con menos operaciones | PROSPECTIVA | Motivada por T-MULTI (los costos se comen el bruto): no se prueba con los datos que la motivaron |
| E1-MR-retraso | Las entradas de MR retrasadas 1 barra pierden menos (−0,18 % frente a −0,52 %) | EXPLORATORIA (sin valor práctico) | Solo descriptiva: sugiere que la entrada de MR «agarra cuchillos que caen» |

## Propuestas en E2 (ver `INVESTIGACION_E2.md`)
| ID | Hipótesis | Estado |
|---|---|---|
| C3 | Volumen, volatilidad, funding, prima o drawdown aportan información incremental a 7 y 28 días | PROPUESTA (compuerta; datos locales) |
| C1 | Funding o prima extremos como timing contrario de spot | PROPUESTA (datos locales) |
| C2 | La atención (vistas de Wikipedia) predice retornos a 1–4 semanas | PROPUESTA (requiere descarga) |
| C5 | Momentum transversal entre criptos (solo largos) | PROPUESTA (requiere un universo histórico) |
| C6 | Valor relativo BTC/ETH por reversión del cociente | PROPUESTA (baja prioridad) |
| C7 | Régimen on-chain (MVRV-Z) | PROPUESTA (baja prioridad) |
| C8 | Prima de riesgo de varianza | PROPUESTA (otra infraestructura) |
| C9 | Ventanas macro como gestión de riesgo | PROPUESTA (baja prioridad) |
| C10 | Reversión tras movimientos extremos | PROPUESTA (baja prioridad) |
| C13 | IA de selección o abstención sobre una señal base | PROPUESTA condicionada a que C3 encuentre información |
| C4 | T sin cambios en otras criptos | PROPUESTA (baja potencia adicional) |
| C11 | Lead-lag entre criptos de minutos | DESCARTADA en esta fase (alta frecuencia) |
| C12 | Estacionalidad o calendario | DESCARTADA en esta fase (sin mecanismo; minería de datos) |
| C14 | Carry o base con vencimiento | CERRADA (sigue la regla de H-CARRY) |
| LLM-hist | Juicio de un LLM sobre noticias históricas | DESCARTADA para backtest (el modelo conoce el futuro); solo prospectiva |
