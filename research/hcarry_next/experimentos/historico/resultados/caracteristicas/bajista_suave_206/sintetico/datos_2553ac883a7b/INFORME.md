# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `2553ac883a7b8f36…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -176.28907065762542, "p_dif_mayor_que_cero": 0.102, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.6549708528468994 · eventos negativos: 0.2362514029180696 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 5.22% | 5.76% | 1919 | 108 | 100% | 2.4 |
| desarrollo | umbral | 7.99% | 1.89% | 3204 | 505 | 54% | 10.8 |
| validacion | rev5 | 14.95% | 0.69% | 1662 | 32 | 100% | 2.1 |
| validacion | umbral | 14.33% | 0.50% | 1645 | 116 | 93% | 7.8 |
| test | rev5 | 16.70% | 0.56% | 4398 | 67 | 100% | 1.9 |
| test | umbral | 16.08% | 0.70% | 4340 | 227 | 89% | 6.5 |

Bootstrap pareado en test (umbral − rev5): media anual -0.005309791953142209, intervalo 90 % [-0.012287248073227761, 0.0016669155915855663], P(> 0) = 0.102

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 16.85% | 16.55% | -84 |
| costes_x2 | 16.42% | 15.14% | -364 |
| costes_x3 | 16.15% | 14.21% | -547 |
| retraso_1h | 16.70% | 16.09% | -172 |
| retraso_3h | 16.69% | 16.08% | -174 |
| pata_adversa | 16.31% | 14.21% | -591 |
| funding_x075 | 12.25% | 11.02% | -332 |
| nocional_min_perp_5 | 16.70% | 16.08% | -176 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'NO DESCARTADA', 'criterios_activos': [], 'banda': '> 7 %: solo habilita prospectiva'}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
