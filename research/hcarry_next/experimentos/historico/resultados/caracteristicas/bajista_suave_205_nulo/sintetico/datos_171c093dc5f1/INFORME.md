# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `171c093dc5f1b4a8…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -961.7775179525852, "p_dif_mayor_que_cero": 0.0, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.05131627551111746 · eventos negativos: 0.15179573512906847 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 6.04% | 0.40% | 2184 | 78 | 100% | 1.7 |
| desarrollo | umbral | 1.36% | 1.21% | 1540 | 1087 | 78% | 26.2 |
| validacion | rev5 | 5.97% | 0.27% | 686 | 38 | 100% | 2.7 |
| validacion | umbral | 1.51% | 1.17% | 568 | 393 | 81% | 28.8 |
| test | rev5 | 6.65% | 0.39% | 1692 | 76 | 100% | 2.4 |
| test | umbral | 2.77% | 1.21% | 1395 | 765 | 79% | 25.7 |

Bootstrap pareado en test (umbral − rev5): media anual -0.03704262074210255, intervalo 90 % [-0.04689073980562238, -0.027631813455094006], P(> 0) = 0.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 6.81% | 4.44% | -595 |
| costes_x2 | 6.33% | -0.48% | -1651 |
| costes_x3 | 6.01% | -3.63% | -2285 |
| retraso_1h | 6.65% | 2.86% | -939 |
| retraso_3h | 6.63% | 2.87% | -931 |
| pata_adversa | 6.13% | -1.93% | -1933 |
| funding_x075 | 4.86% | 0.95% | -948 |
| nocional_min_perp_5 | 6.65% | 2.77% | -963 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': [], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
