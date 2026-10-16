# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `bf231a0de65e270f…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": 562.3893933996969, "p_dif_mayor_que_cero": 0.958, "estres_ok": true, "validacion_mismo_signo": true, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.7225912173003617 · eventos negativos: 0.18714927048260382 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 1.77% | 8.57% | 646 | 57 | 100% | 1.4 |
| desarrollo | umbral | 6.39% | 0.44% | 2438 | 252 | 74% | 5.8 |
| validacion | rev5 | 9.52% | 4.00% | 1080 | 44 | 100% | 3.1 |
| validacion | umbral | 12.88% | 0.55% | 1478 | 85 | 82% | 5.9 |
| test | rev5 | 8.40% | 5.09% | 2162 | 97 | 100% | 2.9 |
| test | umbral | 10.53% | 0.38% | 2887 | 278 | 75% | 8.0 |

Bootstrap pareado en test (umbral − rev5): media anual 0.019511215369865668, intervalo 90 % [0.0008306584724386392, 0.04057636165318118], P(> 0) = 0.958

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 8.59% | 11.09% | 660 |
| costes_x2 | 8.00% | 9.46% | 382 |
| costes_x3 | 7.60% | 8.38% | 200 |
| retraso_1h | 8.38% | 10.51% | 560 |
| retraso_3h | 8.35% | 10.52% | 571 |
| pata_adversa | 7.85% | 8.77% | 239 |
| funding_x075 | 6.29% | 6.50% | 54 |
| nocional_min_perp_5 | 8.40% | 10.53% | 562 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'NO DESCARTADA', 'criterios_activos': [], 'banda': '> 7 %: solo habilita prospectiva'}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
