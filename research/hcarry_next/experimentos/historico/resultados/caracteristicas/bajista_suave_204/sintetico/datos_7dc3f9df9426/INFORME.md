# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `7dc3f9df942668d1…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -24.17510113487151, "p_dif_mayor_que_cero": 0.4245, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.6939116066850836 · eventos negativos: 0.2564534231200898 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 0.51% | 2.88% | 194 | 26 | 100% | 0.7 |
| desarrollo | umbral | 3.83% | 2.38% | 1826 | 671 | 47% | 15.9 |
| validacion | rev5 | 11.31% | 1.20% | 1284 | 51 | 100% | 3.5 |
| validacion | umbral | 10.27% | 1.23% | 1319 | 271 | 65% | 18.6 |
| test | rev5 | 11.00% | 1.90% | 2826 | 70 | 100% | 2.1 |
| test | umbral | 10.91% | 1.16% | 2958 | 290 | 83% | 8.9 |

Bootstrap pareado en test (umbral − rev5): media anual -0.0008230976308670183, intervalo 90 % [-0.010357459448442697, 0.008535313886256399], P(> 0) = 0.4245

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 11.15% | 11.52% | 100 |
| costes_x2 | 10.71% | 9.71% | -266 |
| costes_x3 | 10.42% | 8.51% | -500 |
| retraso_1h | 10.99% | 10.90% | -25 |
| retraso_3h | 10.99% | 10.91% | -20 |
| pata_adversa | 10.57% | 8.90% | -440 |
| funding_x075 | 8.09% | 8.19% | 26 |
| nocional_min_perp_5 | 11.00% | 10.91% | -24 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': ['D1'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
