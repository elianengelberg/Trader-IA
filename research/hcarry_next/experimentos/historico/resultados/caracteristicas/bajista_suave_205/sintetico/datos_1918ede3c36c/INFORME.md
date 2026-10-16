# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `1918ede3c36c3963…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": 337.71083780022855, "p_dif_mayor_que_cero": 0.958, "estres_ok": false, "validacion_mismo_signo": true, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.6057521712995269 · eventos negativos: 0.10465768799102132 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 9.69% | 1.43% | 3593 | 77 | 100% | 1.7 |
| desarrollo | umbral | 8.62% | 0.74% | 3488 | 521 | 79% | 11.4 |
| validacion | rev5 | 7.58% | 2.37% | 859 | 39 | 100% | 2.8 |
| validacion | umbral | 8.05% | 0.91% | 1091 | 279 | 61% | 19.3 |
| test | rev5 | 1.28% | 6.89% | 375 | 71 | 100% | 2.3 |
| test | umbral | 2.70% | 3.22% | 1006 | 484 | 54% | 15.7 |

Bootstrap pareado en test (umbral − rev5): media anual 0.013796567263346075, intervalo 90 % [0.00044866768424478684, 0.02695282785489675], P(> 0) = 0.958

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 1.43% | 3.70% | 548 |
| costes_x2 | 0.99% | 0.71% | -66 |
| costes_x3 | 0.69% | -1.24% | -450 |
| retraso_1h | 1.28% | 2.69% | 339 |
| retraso_3h | 1.28% | 2.58% | 311 |
| pata_adversa | 0.78% | -1.00% | -414 |
| funding_x075 | 0.91% | 0.74% | -40 |
| nocional_min_perp_5 | 1.29% | 2.70% | 337 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': ['D1'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
