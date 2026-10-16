# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `b9aa3d5d152d4173…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -958.4068402061857, "p_dif_mayor_que_cero": 0.0, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.0291859122309942 · eventos negativos: 0.127665544332211 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 7.13% | 0.39% | 2623 | 99 | 100% | 2.2 |
| desarrollo | umbral | 2.34% | 2.06% | 1956 | 1101 | 82% | 25.9 |
| validacion | rev5 | 7.51% | 0.25% | 844 | 36 | 100% | 2.5 |
| validacion | umbral | 1.97% | 0.75% | 597 | 406 | 76% | 29.6 |
| test | rev5 | 7.96% | 0.26% | 2033 | 72 | 100% | 2.3 |
| test | umbral | 4.16% | 0.93% | 1635 | 649 | 85% | 21.3 |

Bootstrap pareado en test (umbral − rev5): media anual -0.03583445673003697, intervalo 90 % [-0.04494648672022838, -0.02686766974308837], P(> 0) = 0.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 8.08% | 5.56% | -642 |
| costes_x2 | 7.66% | 1.41% | -1546 |
| costes_x3 | 7.33% | -1.26% | -2083 |
| retraso_1h | 7.96% | 4.16% | -959 |
| retraso_3h | 7.94% | 4.16% | -953 |
| pata_adversa | 7.46% | 1.02% | -1587 |
| funding_x075 | 5.61% | 1.75% | -943 |
| nocional_min_perp_5 | 7.96% | 4.16% | -958 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'NO DESCARTADA', 'criterios_activos': [], 'banda': '> 7 %: solo habilita prospectiva'}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
