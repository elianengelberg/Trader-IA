# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `d4026560d4108253…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -152.6895866558134, "p_dif_mayor_que_cero": 0.069, "estres_ok": false, "validacion_mismo_signo": true, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.5751896972966072 · eventos negativos: 0.132996632996633 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 3.39% | 1.73% | 1187 | 36 | 100% | 0.8 |
| desarrollo | umbral | 3.76% | 1.52% | 1651 | 448 | 74% | 10.6 |
| validacion | rev5 | 8.62% | 1.83% | 976 | 41 | 100% | 2.9 |
| validacion | umbral | 8.73% | 0.57% | 1111 | 208 | 66% | 14.4 |
| test | rev5 | 23.35% | 0.31% | 6428 | 117 | 100% | 3.0 |
| test | umbral | 22.85% | 0.43% | 6358 | 223 | 98% | 5.7 |

Bootstrap pareado en test (umbral − rev5): media anual -0.004033585054853629, intervalo 90 % [-0.00900931904802235, 0.0003167793039340747], P(> 0) = 0.069

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 23.58% | 23.27% | -93 |
| costes_x2 | 22.89% | 22.00% | -269 |
| costes_x3 | 22.43% | 21.16% | -383 |
| retraso_1h | 23.35% | 22.81% | -164 |
| retraso_3h | 23.35% | 22.81% | -167 |
| pata_adversa | 22.48% | 21.44% | -314 |
| funding_x075 | 17.21% | 15.90% | -376 |
| nocional_min_perp_5 | 23.35% | 22.85% | -153 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': [], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
