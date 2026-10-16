# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `ffa8f6b1e2310629…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -1102.5908790880349, "p_dif_mayor_que_cero": 0.0, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: -0.022576957244115514 · eventos negativos: 0.1074635241301908 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 7.18% | 0.32% | 2609 | 72 | 100% | 1.6 |
| desarrollo | umbral | 3.01% | 1.13% | 1959 | 971 | 84% | 22.8 |
| validacion | rev5 | 6.15% | 0.24% | 705 | 34 | 100% | 2.4 |
| validacion | umbral | 1.64% | 1.11% | 540 | 382 | 77% | 27.8 |
| test | rev5 | 6.31% | 0.42% | 1610 | 73 | 100% | 2.3 |
| test | umbral | 1.82% | 1.79% | 1187 | 760 | 84% | 25.5 |

Bootstrap pareado en test (umbral − rev5): media anual -0.04308859023247549, intervalo 90 % [-0.0538267554175477, -0.032751570170166264], P(> 0) = 0.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 6.46% | 3.46% | -747 |
| costes_x2 | 6.00% | -1.38% | -1773 |
| costes_x3 | 5.68% | -4.48% | -2389 |
| retraso_1h | 6.31% | 1.78% | -1112 |
| retraso_3h | 6.31% | 1.81% | -1104 |
| pata_adversa | 5.87% | -2.78% | -2059 |
| funding_x075 | 4.63% | 0.59% | -975 |
| nocional_min_perp_5 | 6.31% | 1.82% | -1103 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'NO DESCARTADA', 'criterios_activos': [], 'banda': 'no concluyente (6–7 %)'}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
