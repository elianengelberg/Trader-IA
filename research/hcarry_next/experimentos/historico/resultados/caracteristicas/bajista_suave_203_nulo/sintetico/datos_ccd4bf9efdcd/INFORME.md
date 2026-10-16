# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `ccd4bf9efdcd716c…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -999.2064398901857, "p_dif_mayor_que_cero": 0.0, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: -0.024613522031013753 · eventos negativos: 0.18462401795735128 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 1.97% | 0.34% | 699 | 40 | 100% | 0.9 |
| desarrollo | umbral | -2.98% | 9.70% | 332 | 1268 | 42% | 32.9 |
| validacion | rev5 | 2.71% | 0.34% | 343 | 51 | 100% | 3.7 |
| validacion | umbral | -2.42% | 2.77% | 158 | 431 | 55% | 32.2 |
| test | rev5 | 2.25% | 0.37% | 576 | 40 | 100% | 1.3 |
| test | umbral | -2.03% | 4.67% | 400 | 832 | 51% | 29.2 |

Bootstrap pareado en test (umbral − rev5): media anual -0.042731266050080256, intervalo 90 % [-0.05116650585951771, -0.03486462350319313], P(> 0) = 0.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 2.33% | -0.22% | -605 |
| costes_x2 | 2.08% | -5.54% | -1737 |
| costes_x3 | 1.91% | -8.93% | -2411 |
| retraso_1h | 2.26% | -1.97% | -988 |
| retraso_3h | 2.24% | -2.03% | -996 |
| pata_adversa | 1.96% | -6.31% | -1874 |
| funding_x075 | 1.64% | -1.69% | -777 |
| nocional_min_perp_5 | 2.26% | -2.03% | -1002 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': ['D1'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
