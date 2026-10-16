# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `5acd0fc926f40d64…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -2.3279028592151008, "p_dif_mayor_que_cero": 0.5105, "estres_ok": false, "validacion_mismo_signo": true, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.5951735264144643 · eventos negativos: 0.20426487093153758 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 3.28% | 3.12% | 1146 | 37 | 100% | 0.9 |
| desarrollo | umbral | 3.70% | 1.79% | 1698 | 543 | 59% | 13.0 |
| validacion | rev5 | -1.97% | 3.47% | -170 | 51 | 100% | 3.8 |
| validacion | umbral | -0.09% | 1.13% | 141 | 174 | 44% | 12.8 |
| test | rev5 | 3.45% | 0.67% | 869 | 41 | 100% | 1.4 |
| test | umbral | 3.44% | 0.62% | 1116 | 336 | 78% | 11.1 |

Bootstrap pareado en test (umbral − rev5): media anual -8.474203368302148e-05, intervalo 90 % [-0.009048159083650403, 0.009035651714333594], P(> 0) = 0.5105

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 3.54% | 4.17% | 153 |
| costes_x2 | 3.26% | 2.01% | -301 |
| costes_x3 | 3.08% | 0.60% | -593 |
| retraso_1h | 3.42% | 3.45% | 7 |
| retraso_3h | 3.40% | 3.43% | 7 |
| pata_adversa | 3.16% | 2.08% | -259 |
| funding_x075 | 2.52% | 1.56% | -229 |
| nocional_min_perp_5 | 3.47% | 3.44% | -6 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': ['D1'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
