# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `4e31b92121b7e762…` · datos: `026b33ac994c2bb7…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -319.8310788966628, "p_dif_mayor_que_cero": 0.0355, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: -0.07371250096820453 · eventos negativos: 0.14309764309764308 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 8.84% | 0.27% | 3279 | 101 | 100% | 2.2 |
| desarrollo | umbral | 6.08% | 0.76% | 2836 | 709 | 90% | 15.8 |
| validacion | rev5 | 6.85% | 0.32% | 779 | 32 | 100% | 2.3 |
| validacion | umbral | 5.31% | 0.73% | 805 | 241 | 88% | 17.4 |
| test | rev5 | 7.04% | 0.23% | 1754 | 36 | 100% | 1.1 |
| test | umbral | 5.78% | 0.57% | 1939 | 546 | 89% | 17.5 |

Bootstrap pareado en test (umbral − rev5): media anual -0.011835797766860915, intervalo 90 % [-0.022626957578442446, -0.0013228442324444095], P(> 0) = 0.0355

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 7.12% | 6.93% | -47 |
| costes_x2 | 6.88% | 3.52% | -839 |
| costes_x3 | 6.73% | 1.30% | -1335 |
| retraso_1h | 7.06% | 5.79% | -321 |
| retraso_3h | 7.06% | 5.75% | -332 |
| pata_adversa | 6.86% | 2.46% | -1090 |
| funding_x075 | 5.18% | 3.78% | -345 |
| nocional_min_perp_5 | 7.10% | 5.78% | -334 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': [], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
