# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `97dd1e60a1442ad8…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": 1366.5292052315126, "p_dif_mayor_que_cero": 0.9955, "estres_ok": true, "validacion_mismo_signo": true, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.7359635845671768 · eventos negativos: 0.19584736251402918 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 6.02% | 8.86% | 2169 | 84 | 100% | 1.8 |
| desarrollo | umbral | 11.33% | 0.56% | 4398 | 308 | 72% | 6.1 |
| validacion | rev5 | 5.00% | 5.75% | 614 | 69 | 100% | 4.9 |
| validacion | umbral | 14.34% | 0.43% | 1648 | 96 | 57% | 6.5 |
| test | rev5 | 0.09% | 13.18% | 83 | 54 | 100% | 1.9 |
| test | umbral | 5.73% | 0.56% | 1629 | 317 | 64% | 10.1 |

Bootstrap pareado en test (umbral − rev5): media anual 0.05476322022903254, intervalo 90 % [0.019619875224654842, 0.09341904871927989], P(> 0) = 0.9955

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 0.20% | 6.39% | 1508 |
| costes_x2 | -0.13% | 4.43% | 1095 |
| costes_x3 | -0.39% | 3.14% | 839 |
| retraso_1h | 0.11% | 5.72% | 1358 |
| retraso_3h | 0.12% | 5.72% | 1356 |
| pata_adversa | -0.31% | 3.55% | 919 |
| funding_x075 | 0.23% | 3.95% | 891 |
| nocional_min_perp_5 | 0.09% | 5.73% | 1367 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'DESCARTADA', 'criterios_activos': ['D1', 'D4'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
