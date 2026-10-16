# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `ad385d768a1e6f69…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": 2188.0208645154926, "p_dif_mayor_que_cero": 1.0, "estres_ok": true, "validacion_mismo_signo": true, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.6750518415185173 · eventos negativos: 0.09708193041526375 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 9.06% | 2.46% | 3359 | 96 | 100% | 2.0 |
| desarrollo | umbral | 10.56% | 0.50% | 4049 | 236 | 90% | 4.8 |
| validacion | rev5 | -10.91% | 11.82% | -1151 | 25 | 100% | 2.0 |
| validacion | umbral | -0.58% | 1.20% | 75 | 152 | 28% | 11.3 |
| test | rev5 | -6.41% | 17.37% | -1378 | 55 | 100% | 2.0 |
| test | umbral | 3.18% | 0.77% | 930 | 199 | 44% | 6.6 |

Bootstrap pareado en test (umbral − rev5): media anual 0.09744155101452055, intervalo 90 % [0.06219876162144473, 0.13228526600055263], P(> 0) = 1.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | -6.11% | 3.59% | 2222 |
| costes_x2 | -6.67% | 2.37% | 2047 |
| costes_x3 | -6.91% | 1.50% | 1889 |
| retraso_1h | -6.26% | 3.19% | 2159 |
| retraso_3h | -6.24% | 3.15% | 2147 |
| pata_adversa | -6.77% | 1.69% | 1906 |
| funding_x075 | -4.76% | 1.53% | 1436 |
| nocional_min_perp_5 | -6.29% | 3.18% | 2161 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': ['D1'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
