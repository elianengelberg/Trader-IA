# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `4e31b92121b7e762…` · datos: `56403fad235e33bd…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -738.7583990879739, "p_dif_mayor_que_cero": 0.0, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: -0.06373525212736394 · eventos negativos: 0.15123456790123457 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 10.60% | 0.29% | 4003 | 114 | 100% | 2.4 |
| desarrollo | umbral | 7.56% | 1.08% | 3527 | 891 | 91% | 19.4 |
| validacion | rev5 | 8.86% | 0.35% | 993 | 32 | 100% | 2.2 |
| validacion | umbral | 5.01% | 0.91% | 846 | 316 | 90% | 22.8 |
| test | rev5 | 10.39% | 0.30% | 2678 | 85 | 100% | 2.6 |
| test | umbral | 7.57% | 0.84% | 2414 | 564 | 92% | 17.6 |

Bootstrap pareado en test (umbral − rev5): media anual -0.02592171389825209, intervalo 90 % [-0.03654308055838566, -0.015572647591462025], P(> 0) = 0.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 10.51% | 8.75% | -464 |
| costes_x2 | 9.99% | 5.23% | -1225 |
| costes_x3 | 9.65% | 2.94% | -1696 |
| retraso_1h | 10.33% | 7.50% | -739 |
| retraso_3h | 10.38% | 7.49% | -755 |
| pata_adversa | 9.74% | 3.83% | -1503 |
| funding_x075 | 7.57% | 4.72% | -719 |
| nocional_min_perp_5 | 10.39% | 7.57% | -739 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'NO DESCARTADA', 'criterios_activos': [], 'banda': '> 7 %: solo habilita prospectiva'}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
