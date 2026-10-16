# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `4e31b92121b7e762…` · datos: `00c010c505f04f83…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -371.88619803465735, "p_dif_mayor_que_cero": 0.0, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: -0.0018037828179170755 · eventos negativos: 0.09567901234567901 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 7.34% | 0.25% | 2635 | 44 | 100% | 0.9 |
| desarrollo | umbral | 6.75% | 0.66% | 2886 | 503 | 93% | 11.1 |
| validacion | rev5 | 8.84% | 0.19% | 1000 | 35 | 100% | 2.4 |
| validacion | umbral | 6.98% | 0.62% | 927 | 164 | 95% | 11.7 |
| test | rev5 | 9.05% | 0.27% | 2328 | 87 | 100% | 2.7 |
| test | umbral | 7.62% | 0.55% | 2195 | 328 | 94% | 10.2 |

Bootstrap pareado en test (umbral − rev5): media anual -0.013232445241249963, intervalo 90 % [-0.02038500051848391, -0.006780255808858798], P(> 0) = 0.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 9.23% | 8.29% | -246 |
| costes_x2 | 8.69% | 6.28% | -617 |
| costes_x3 | 8.32% | 4.97% | -852 |
| retraso_1h | 9.06% | 7.64% | -371 |
| retraso_3h | 9.08% | 7.63% | -377 |
| pata_adversa | 8.64% | 5.24% | -866 |
| funding_x075 | 6.57% | 4.96% | -405 |
| nocional_min_perp_5 | 9.05% | 7.62% | -372 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'NO DESCARTADA', 'criterios_activos': [], 'banda': '> 7 %: solo habilita prospectiva'}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
