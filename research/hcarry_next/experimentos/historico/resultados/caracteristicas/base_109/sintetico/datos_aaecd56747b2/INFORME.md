# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `aaecd56747b200d2…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": 262.1399021963098, "p_dif_mayor_que_cero": 0.731, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.6176605124394302 · eventos negativos: 0.11896745230078563 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 6.58% | 2.26% | 2375 | 72 | 100% | 1.6 |
| desarrollo | umbral | 7.71% | 0.79% | 2939 | 258 | 85% | 5.7 |
| validacion | rev5 | 4.17% | 1.45% | 489 | 33 | 100% | 2.4 |
| validacion | umbral | 4.03% | 0.62% | 556 | 143 | 86% | 10.3 |
| test | rev5 | 8.06% | 4.74% | 2061 | 73 | 100% | 2.2 |
| test | umbral | 9.07% | 0.56% | 2508 | 297 | 84% | 8.9 |

Bootstrap pareado en test (umbral − rev5): media anual 0.009268876767335062, intervalo 90 % [-0.011134615224931768, 0.03367500813583493], P(> 0) = 0.731

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 8.22% | 9.67% | 380 |
| costes_x2 | 8.21% | 7.87% | -88 |
| costes_x3 | 7.43% | 6.68% | -193 |
| retraso_1h | 8.07% | 9.07% | 259 |
| retraso_3h | 8.08% | 9.06% | 253 |
| pata_adversa | 8.13% | 7.81% | -82 |
| funding_x075 | 6.03% | 5.98% | -15 |
| nocional_min_perp_5 | 8.06% | 9.07% | 262 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'NO DESCARTADA', 'criterios_activos': [], 'banda': '> 7 %: solo habilita prospectiva'}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
