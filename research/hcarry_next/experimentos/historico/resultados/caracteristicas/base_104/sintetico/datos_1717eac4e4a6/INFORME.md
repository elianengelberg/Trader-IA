# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `1717eac4e4a61cf4…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": 108.65883561309056, "p_dif_mayor_que_cero": 0.641, "estres_ok": false, "validacion_mismo_signo": true, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.7840766359661893 · eventos negativos: 0.24551066217732884 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 5.83% | 11.38% | 2116 | 92 | 100% | 2.3 |
| desarrollo | umbral | 12.03% | 0.49% | 4656 | 241 | 66% | 5.2 |
| validacion | rev5 | -7.57% | 9.48% | -781 | 26 | 100% | 2.1 |
| validacion | umbral | 2.02% | 0.17% | 246 | 24 | 46% | 1.8 |
| test | rev5 | 4.67% | 3.38% | 1185 | 68 | 100% | 2.2 |
| test | umbral | 5.10% | 0.48% | 1463 | 281 | 82% | 9.1 |

Bootstrap pareado en test (umbral − rev5): media anual 0.0041624930956969276, intervalo 90 % [-0.009994303389353117, 0.021408499279401597], P(> 0) = 0.641

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 4.81% | 5.71% | 224 |
| costes_x2 | 4.38% | 3.90% | -116 |
| costes_x3 | 4.09% | 2.72% | -333 |
| retraso_1h | 4.65% | 5.09% | 108 |
| retraso_3h | 4.65% | 5.05% | 101 |
| pata_adversa | 4.03% | 3.20% | -202 |
| funding_x075 | 3.43% | 2.85% | -140 |
| nocional_min_perp_5 | 4.67% | 5.10% | 109 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': [], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
