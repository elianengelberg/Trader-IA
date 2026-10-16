# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `8f24a18e461dff7a…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": 734.9332971031472, "p_dif_mayor_que_cero": 0.98, "estres_ok": true, "validacion_mismo_signo": true, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.6088481384516197 · eventos negativos: 0.1947250280583614 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | -0.51% | 7.85% | -88 | 72 | 100% | 1.8 |
| desarrollo | umbral | 3.86% | 0.55% | 1547 | 294 | 73% | 6.8 |
| validacion | rev5 | 0.34% | 3.63% | 69 | 39 | 100% | 2.9 |
| validacion | umbral | 4.30% | 0.55% | 564 | 139 | 67% | 10.0 |
| test | rev5 | 6.88% | 6.28% | 1760 | 72 | 100% | 2.4 |
| test | umbral | 9.72% | 0.56% | 2677 | 276 | 75% | 8.8 |

Bootstrap pareado en test (umbral − rev5): media anual 0.026149035890134287, intervalo 90 % [0.004195264259809222, 0.051878165763781285], P(> 0) = 0.98

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 7.04% | 10.33% | 858 |
| costes_x2 | 6.57% | 8.51% | 496 |
| costes_x3 | 6.26% | 7.31% | 265 |
| retraso_1h | 6.89% | 9.67% | 721 |
| retraso_3h | 6.90% | 9.68% | 720 |
| pata_adversa | 6.39% | 8.11% | 440 |
| funding_x075 | 5.32% | 6.24% | 230 |
| nocional_min_perp_5 | 6.88% | 9.72% | 735 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'NO DESCARTADA', 'criterios_activos': [], 'banda': 'no concluyente (6–7 %)'}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
