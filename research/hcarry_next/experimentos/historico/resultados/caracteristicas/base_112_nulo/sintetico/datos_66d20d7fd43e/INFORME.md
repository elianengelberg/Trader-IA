# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `4e31b92121b7e762…` · datos: `66d20d7fd43e1b71…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -1047.8340222207917, "p_dif_mayor_que_cero": 0.0, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.020213817037785416 · eventos negativos: 0.16666666666666666 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 10.18% | 0.33% | 3768 | 76 | 100% | 1.6 |
| desarrollo | umbral | 5.10% | 1.30% | 2912 | 1147 | 85% | 25.7 |
| validacion | rev5 | 9.24% | 0.43% | 1071 | 46 | 100% | 3.2 |
| validacion | umbral | 4.20% | 1.00% | 896 | 432 | 83% | 31.0 |
| test | rev5 | 10.53% | 0.37% | 2701 | 72 | 100% | 2.2 |
| test | umbral | 6.50% | 0.76% | 2284 | 719 | 90% | 22.7 |

Bootstrap pareado en test (umbral − rev5): media anual -0.03714812729882914, intervalo 90 % [-0.047653283611932065, -0.02637810876833698], P(> 0) = 0.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 10.68% | 8.01% | -700 |
| costes_x2 | 10.17% | 3.52% | -1693 |
| costes_x3 | 9.72% | 0.64% | -2265 |
| retraso_1h | 10.46% | 6.51% | -1027 |
| retraso_3h | 10.46% | 6.47% | -1035 |
| pata_adversa | 9.75% | 0.36% | -2339 |
| funding_x075 | 7.78% | 3.02% | -1192 |
| nocional_min_perp_5 | 10.51% | 6.50% | -1044 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': [], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
