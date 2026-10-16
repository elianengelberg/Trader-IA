# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `4e31b92121b7e762…` · datos: `a46776671b78802b…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -483.54451945777873, "p_dif_mayor_que_cero": 0.001, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.0477652891581511 · eventos negativos: 0.25140291806958476 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | -0.73% | 2.84% | -139 | 90 | 100% | 2.2 |
| desarrollo | umbral | -3.81% | 11.86% | 1 | 1154 | 26% | 30.2 |
| validacion | rev5 | -0.25% | 0.57% | 5 | 29 | 100% | 2.1 |
| validacion | umbral | -4.36% | 4.82% | -22 | 460 | 28% | 34.7 |
| test | rev5 | -0.99% | 2.71% | -152 | 76 | 100% | 2.6 |
| test | umbral | -3.12% | 7.29% | 26 | 733 | 26% | 26.2 |

Bootstrap pareado en test (umbral − rev5): media anual -0.021789938914147617, intervalo 90 % [-0.03258785548096379, -0.010755370419427117], P(> 0) = 0.001

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | -0.83% | -1.52% | -159 |
| costes_x2 | -1.31% | -6.24% | -1092 |
| costes_x3 | -1.63% | -9.26% | -1651 |
| retraso_1h | -0.97% | -3.05% | -473 |
| retraso_3h | -0.94% | -3.06% | -480 |
| pata_adversa | -1.53% | -8.28% | -1473 |
| funding_x075 | -0.83% | -2.53% | -387 |
| nocional_min_perp_5 | -0.98% | -3.12% | -485 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': ['D1'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
