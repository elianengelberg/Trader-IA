# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `548a6478c974eb0f…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": 1729.5645095722757, "p_dif_mayor_que_cero": 1.0, "estres_ok": true, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.7309408273441506 · eventos negativos: 0.15881032547699214 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 7.96% | 5.99% | 2902 | 88 | 100% | 1.9 |
| desarrollo | umbral | 11.88% | 0.51% | 4583 | 273 | 79% | 5.6 |
| validacion | rev5 | 17.29% | 0.48% | 1949 | 41 | 100% | 2.7 |
| validacion | umbral | 15.97% | 0.53% | 1866 | 132 | 88% | 8.8 |
| test | rev5 | 9.59% | 7.82% | 2446 | 73 | 100% | 2.3 |
| test | umbral | 15.91% | 0.66% | 4293 | 244 | 70% | 7.2 |

Bootstrap pareado en test (umbral − rev5): media anual 0.05604297677471854, intervalo 90 % [0.02922175308477961, 0.08278805067524338], P(> 0) = 1.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 9.71% | 16.43% | 1844 |
| costes_x2 | 9.29% | 14.67% | 1458 |
| costes_x3 | 8.74% | 13.84% | 1372 |
| retraso_1h | 9.63% | 15.92% | 1720 |
| retraso_3h | 9.62% | 15.85% | 1704 |
| pata_adversa | 8.90% | 14.11% | 1405 |
| funding_x075 | 7.02% | 11.29% | 1118 |
| nocional_min_perp_5 | 9.55% | 15.91% | 1742 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': ['D1'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
