# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `4e31b92121b7e762…` · datos: `4f161b7cbee62858…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": 683.5656067555901, "p_dif_mayor_que_cero": 0.9985, "estres_ok": false, "validacion_mismo_signo": true, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.6409532761160376 · eventos negativos: 0.17732884399551066 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 6.66% | 2.54% | 2436 | 101 | 100% | 2.1 |
| desarrollo | umbral | 7.27% | 1.14% | 3026 | 577 | 61% | 12.1 |
| validacion | rev5 | 15.40% | 0.38% | 1716 | 35 | 100% | 2.3 |
| validacion | umbral | 16.29% | 0.66% | 1861 | 113 | 89% | 7.6 |
| test | rev5 | 5.96% | 2.25% | 1477 | 35 | 100% | 1.2 |
| test | umbral | 8.63% | 1.31% | 2372 | 326 | 78% | 10.4 |

Bootstrap pareado en test (umbral − rev5): media anual 0.024920576156902203, intervalo 90 % [0.01039952761586853, 0.040217250979279036], P(> 0) = 0.9985

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 6.07% | 9.32% | 836 |
| costes_x2 | 5.81% | 7.24% | 363 |
| costes_x3 | 5.65% | 5.87% | 54 |
| retraso_1h | 5.96% | 8.64% | 688 |
| retraso_3h | 6.07% | 8.56% | 637 |
| pata_adversa | 5.83% | 5.64% | -48 |
| funding_x075 | 4.41% | 5.67% | 315 |
| nocional_min_perp_5 | 6.08% | 8.63% | 652 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': ['D1'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
