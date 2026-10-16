# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `5be948c0fb0336c6…` (copia aportada por el usuario)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -211.27399123024952, "p_dif_mayor_que_cero": 0.0225, "estres_ok": false, "validacion_mismo_signo": true, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.7347328838214758 · eventos negativos: 0.1739618406285073 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 7.08% | 5.68% | 2584 | 79 | 100% | 1.8 |
| desarrollo | umbral | 10.76% | 0.75% | 4283 | 409 | 75% | 8.5 |
| validacion | rev5 | 15.62% | 2.22% | 1741 | 42 | 100% | 2.8 |
| validacion | umbral | 17.58% | 0.38% | 1981 | 93 | 80% | 6.1 |
| test | rev5 | 4.16% | 0.68% | 1059 | 57 | 100% | 1.9 |
| test | umbral | 3.30% | 0.36% | 1030 | 283 | 88% | 9.4 |

Bootstrap pareado en test (umbral − rev5): media anual -0.00832020011846764, intervalo 90 % [-0.01470314282683531, -0.0014964449452793207], P(> 0) = 0.0225

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 4.30% | 3.90% | -98 |
| costes_x2 | 3.93% | 2.09% | -446 |
| costes_x3 | 3.68% | 0.91% | -665 |
| retraso_1h | 4.17% | 3.27% | -220 |
| retraso_3h | 4.16% | 3.23% | -228 |
| pata_adversa | 3.77% | 1.72% | -496 |
| funding_x075 | 3.08% | 1.15% | -462 |
| nocional_min_perp_5 | 4.16% | 3.30% | -211 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'DESCARTADA', 'criterios_activos': ['D1'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
