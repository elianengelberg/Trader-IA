# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `09ae889f657f69eb…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": 153.38822037288628, "p_dif_mayor_que_cero": 0.6645, "estres_ok": false, "validacion_mismo_signo": true, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.7660520558414838 · eventos negativos: 0.2564534231200898 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | -1.21% | 15.41% | -343 | 51 | 100% | 1.2 |
| desarrollo | umbral | 4.79% | 0.52% | 1942 | 395 | 59% | 8.8 |
| validacion | rev5 | 13.03% | 0.21% | 1465 | 42 | 100% | 3.0 |
| validacion | umbral | 13.10% | 0.21% | 1476 | 42 | 100% | 3.0 |
| test | rev5 | 8.45% | 4.57% | 2138 | 66 | 100% | 2.0 |
| test | umbral | 9.04% | 0.45% | 2427 | 258 | 83% | 7.7 |

Bootstrap pareado en test (umbral − rev5): media anual 0.0053891857384510845, intervalo 90 % [-0.010204689395132534, 0.023942555730941173], P(> 0) = 0.6645

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 8.59% | 9.56% | 254 |
| costes_x2 | 8.17% | 8.01% | -43 |
| costes_x3 | 7.90% | 6.99% | -234 |
| retraso_1h | 8.44% | 9.03% | 154 |
| retraso_3h | 8.44% | 9.02% | 149 |
| pata_adversa | 8.28% | 8.01% | -69 |
| funding_x075 | 6.20% | 5.69% | -130 |
| nocional_min_perp_5 | 8.45% | 9.04% | 153 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'NO DESCARTADA', 'criterios_activos': [], 'banda': '> 7 %: solo habilita prospectiva'}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
