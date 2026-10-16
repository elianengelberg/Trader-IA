# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `6bf26fe61fba7888…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -1266.3742379177256, "p_dif_mayor_que_cero": 0.0, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.025447950901956062 · eventos negativos: 0.2244668911335578 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 4.46% | 0.61% | 1597 | 77 | 100% | 1.8 |
| desarrollo | umbral | -2.88% | 9.46% | 783 | 1674 | 61% | 43.3 |
| validacion | rev5 | 4.03% | 0.50% | 506 | 63 | 100% | 4.5 |
| validacion | umbral | -2.80% | 3.69% | 252 | 518 | 57% | 38.9 |
| test | rev5 | 4.08% | 0.60% | 1043 | 60 | 100% | 2.0 |
| test | umbral | -1.25% | 3.66% | 720 | 991 | 59% | 34.5 |

Bootstrap pareado en test (umbral − rev5): media anual -0.05256521247158277, intervalo 90 % [-0.06267787484127123, -0.04249382488322417], P(> 0) = 0.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 4.24% | 0.90% | -804 |
| costes_x2 | 3.81% | -5.42% | -2131 |
| costes_x3 | 3.51% | -9.41% | -2897 |
| retraso_1h | 4.09% | -1.29% | -1276 |
| retraso_3h | 4.09% | -1.31% | -1283 |
| pata_adversa | 3.46% | -7.77% | -2544 |
| funding_x075 | 2.97% | -1.97% | -1158 |
| nocional_min_perp_5 | 4.08% | -1.25% | -1266 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': ['D1'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
