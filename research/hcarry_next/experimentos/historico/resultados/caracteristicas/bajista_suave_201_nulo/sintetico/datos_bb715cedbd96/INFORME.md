# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `bb715cedbd963357…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -355.5564004932876, "p_dif_mayor_que_cero": 0.0075, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.061165279098558116 · eventos negativos: 0.10101010101010101 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 10.41% | 0.20% | 3876 | 63 | 100% | 1.3 |
| desarrollo | umbral | 10.27% | 0.50% | 4093 | 316 | 98% | 6.6 |
| validacion | rev5 | 9.70% | 0.28% | 1107 | 50 | 100% | 3.5 |
| validacion | umbral | 8.06% | 0.66% | 1071 | 181 | 94% | 12.8 |
| test | rev5 | 11.22% | 0.25% | 2899 | 79 | 100% | 2.4 |
| test | umbral | 9.88% | 0.82% | 2751 | 285 | 96% | 8.8 |

Bootstrap pareado en test (umbral − rev5): media anual -0.012068675290783032, intervalo 90 % [-0.021263955318853743, -0.0036763257033268944], P(> 0) = 0.0075

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 11.38% | 10.49% | -238 |
| costes_x2 | 10.88% | 8.67% | -584 |
| costes_x3 | 10.55% | 7.47% | -804 |
| retraso_1h | 11.22% | 9.89% | -355 |
| retraso_3h | 11.23% | 9.84% | -372 |
| pata_adversa | 10.57% | 8.17% | -631 |
| funding_x075 | 8.22% | 6.81% | -363 |
| nocional_min_perp_5 | 11.22% | 9.88% | -356 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': [], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
