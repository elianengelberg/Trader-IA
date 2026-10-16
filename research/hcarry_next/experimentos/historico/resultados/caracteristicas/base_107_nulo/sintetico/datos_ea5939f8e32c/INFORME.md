# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `ea5939f8e32c3d43…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -1397.2941828695948, "p_dif_mayor_que_cero": 0.0, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": false}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.015106887243208687 · eventos negativos: 0.19612794612794612 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 1.28% | 0.77% | 487 | 58 | 100% | 1.4 |
| desarrollo | umbral | -3.50% | 11.02% | 239 | 1316 | 43% | 34.2 |
| validacion | rev5 | 0.84% | 0.75% | 123 | 39 | 100% | 2.8 |
| validacion | umbral | -3.24% | 4.06% | 44 | 387 | 36% | 28.9 |
| test | rev5 | 3.25% | 0.40% | 853 | 72 | 100% | 2.4 |
| test | umbral | -2.72% | 6.70% | 454 | 1048 | 54% | 36.8 |

Bootstrap pareado en test (umbral − rev5): media anual -0.059572734504062586, intervalo 90 % [-0.06837016971548024, -0.05063067192037619], P(> 0) = 0.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 3.40% | -0.46% | -918 |
| costes_x2 | 2.94% | -7.10% | -2277 |
| costes_x3 | 2.64% | -11.28% | -3061 |
| retraso_1h | 3.25% | -2.73% | -1399 |
| retraso_3h | 3.25% | -2.68% | -1388 |
| pata_adversa | 2.85% | -10.22% | -2901 |
| funding_x075 | 2.37% | -2.89% | -1220 |
| nocional_min_perp_5 | 3.25% | -2.72% | -1397 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'DESCARTADA', 'criterios_activos': ['D1'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
