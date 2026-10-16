# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `513701d70481212a…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": 469.9389355777057, "p_dif_mayor_que_cero": 0.9815, "estres_ok": true, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.733920661472202 · eventos negativos: 0.27497194163860833 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 0.33% | 15.32% | 219 | 91 | 100% | 2.3 |
| desarrollo | umbral | 8.72% | 0.52% | 3370 | 317 | 62% | 7.0 |
| validacion | rev5 | 22.24% | 0.48% | 2465 | 36 | 100% | 2.4 |
| validacion | umbral | 20.55% | 0.65% | 2348 | 127 | 91% | 8.5 |
| test | rev5 | 7.92% | 2.01% | 1986 | 42 | 100% | 1.3 |
| test | umbral | 9.73% | 0.57% | 2652 | 293 | 81% | 8.9 |

Bootstrap pareado en test (umbral − rev5): media anual 0.016558208331996335, intervalo 90 % [0.0028262633973233243, 0.03171479291070202], P(> 0) = 0.9815

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 8.01% | 10.31% | 604 |
| costes_x2 | 7.65% | 8.53% | 230 |
| costes_x3 | 7.55% | 7.36% | -49 |
| retraso_1h | 7.93% | 9.73% | 469 |
| retraso_3h | 7.91% | 9.71% | 470 |
| pata_adversa | 7.49% | 7.76% | 71 |
| funding_x075 | 5.80% | 6.89% | 277 |
| nocional_min_perp_5 | 7.94% | 9.73% | 466 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': [], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
