# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `67200fe20ee7e959…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": 1585.3704615571278, "p_dif_mayor_que_cero": 1.0, "estres_ok": true, "validacion_mismo_signo": true, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.7651626140018665 · eventos negativos: 0.25224466891133557 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 6.29% | 8.94% | 2338 | 133 | 100% | 3.0 |
| desarrollo | umbral | 13.29% | 0.40% | 5216 | 269 | 63% | 5.4 |
| validacion | rev5 | -2.57% | 7.46% | -226 | 53 | 100% | 3.9 |
| validacion | umbral | 6.64% | 0.58% | 830 | 133 | 44% | 9.5 |
| test | rev5 | 0.34% | 11.46% | 136 | 48 | 100% | 1.6 |
| test | umbral | 6.83% | 0.94% | 1896 | 283 | 59% | 8.8 |

Bootstrap pareado en test (umbral − rev5): media anual 0.06258353637431593, intervalo 90 % [0.03255259897893463, 0.09322702501665833], P(> 0) = 1.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 0.43% | 7.41% | 1712 |
| costes_x2 | 0.14% | 5.64% | 1332 |
| costes_x3 | 0.03% | 4.48% | 1070 |
| retraso_1h | 0.34% | 6.84% | 1588 |
| retraso_3h | 0.32% | 6.78% | 1578 |
| pata_adversa | -0.03% | 4.06% | 978 |
| funding_x075 | 0.23% | 4.57% | 1044 |
| nocional_min_perp_5 | 0.34% | 6.83% | 1586 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': ['D1'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
