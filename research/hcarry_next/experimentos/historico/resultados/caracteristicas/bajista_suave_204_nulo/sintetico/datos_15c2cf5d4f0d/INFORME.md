# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `15c2cf5d4f0d8e89…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -1179.6887900960974, "p_dif_mayor_que_cero": 0.0, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: -0.04051603105649912 · eventos negativos: 0.1941638608305275 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 3.02% | 0.19% | 1048 | 29 | 100% | 0.7 |
| desarrollo | umbral | 1.05% | 1.78% | 1614 | 1268 | 77% | 30.8 |
| validacion | rev5 | 6.63% | 0.30% | 802 | 74 | 100% | 5.3 |
| validacion | umbral | 1.72% | 1.57% | 614 | 426 | 83% | 31.1 |
| test | rev5 | 6.32% | 0.30% | 1619 | 73 | 100% | 2.3 |
| test | umbral | 1.51% | 0.98% | 1172 | 839 | 75% | 28.5 |

Bootstrap pareado en test (umbral − rev5): media anual -0.04626279934545732, intervalo 90 % [-0.05426654342135518, -0.03876479662937323], P(> 0) = 0.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 6.48% | 3.34% | -779 |
| costes_x2 | 6.01% | -2.04% | -1928 |
| costes_x3 | 5.70% | -5.48% | -2611 |
| retraso_1h | 6.32% | 1.49% | -1185 |
| retraso_3h | 6.35% | 1.45% | -1202 |
| pata_adversa | 5.85% | -3.32% | -2175 |
| funding_x075 | 4.63% | -0.41% | -1207 |
| nocional_min_perp_5 | 6.32% | 1.51% | -1180 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': ['D1'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
