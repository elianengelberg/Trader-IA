# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `6c70d0e9608ceade…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -467.74783429429954, "p_dif_mayor_que_cero": 0.0, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.06381371759647352 · eventos negativos: 0.11083052749719416 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 10.90% | 0.32% | 4110 | 98 | 100% | 2.0 |
| desarrollo | umbral | 9.09% | 0.89% | 3790 | 523 | 94% | 11.2 |
| validacion | rev5 | 9.31% | 0.19% | 1049 | 34 | 100% | 2.4 |
| validacion | umbral | 6.62% | 0.44% | 939 | 233 | 90% | 16.6 |
| test | rev5 | 10.47% | 0.26% | 2700 | 97 | 100% | 3.0 |
| test | umbral | 8.69% | 0.49% | 2464 | 356 | 96% | 11.2 |

Bootstrap pareado en test (umbral − rev5): media anual -0.016210071566848522, intervalo 90 % [-0.023005147025831115, -0.009866476379671123], P(> 0) = 0.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 10.67% | 9.47% | -319 |
| costes_x2 | 10.07% | 7.17% | -755 |
| costes_x3 | 9.68% | 5.66% | -1034 |
| retraso_1h | 10.37% | 8.70% | -440 |
| retraso_3h | 10.37% | 8.62% | -462 |
| pata_adversa | 9.83% | 6.07% | -969 |
| funding_x075 | 7.70% | 5.93% | -451 |
| nocional_min_perp_5 | 10.47% | 8.69% | -468 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'NO DESCARTADA', 'criterios_activos': [], 'banda': '> 7 %: solo habilita prospectiva'}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
