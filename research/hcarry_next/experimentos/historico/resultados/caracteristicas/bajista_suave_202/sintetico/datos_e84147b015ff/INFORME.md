# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `e84147b015ff0ade…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": 116.185602693693, "p_dif_mayor_que_cero": 0.76, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.7087843430196553 · eventos negativos: 0.12373737373737374 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 9.12% | 2.01% | 3372 | 78 | 100% | 1.6 |
| desarrollo | umbral | 9.09% | 1.69% | 3638 | 462 | 78% | 9.6 |
| validacion | rev5 | 6.62% | 0.17% | 755 | 34 | 100% | 2.4 |
| validacion | umbral | 6.34% | 0.31% | 749 | 62 | 98% | 4.4 |
| test | rev5 | 13.77% | 2.64% | 3589 | 88 | 100% | 2.4 |
| test | umbral | 14.19% | 1.65% | 3879 | 360 | 77% | 10.0 |

Bootstrap pareado en test (umbral − rev5): media anual 0.0036387951753572645, intervalo 90 % [-0.004508638010233756, 0.012357012532928986], P(> 0) = 0.76

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 13.94% | 14.85% | 253 |
| costes_x2 | 13.37% | 12.86% | -140 |
| costes_x3 | 13.00% | 11.55% | -393 |
| retraso_1h | 13.78% | 14.12% | 94 |
| retraso_3h | 13.79% | 14.09% | 85 |
| pata_adversa | 13.58% | 9.78% | -1028 |
| funding_x075 | 10.38% | 10.93% | 148 |
| nocional_min_perp_5 | 13.77% | 14.19% | 116 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'NO DESCARTADA', 'criterios_activos': [], 'banda': '> 7 %: solo habilita prospectiva'}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
