# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `4e31b92121b7e762…` · datos: `ade0a59aafe84739…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -241.68495295491084, "p_dif_mayor_que_cero": 0.0635, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.586176744262324 · eventos negativos: 0.10072951739618406 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 6.53% | 1.84% | 2317 | 34 | 100% | 0.8 |
| desarrollo | umbral | 7.61% | 0.64% | 2987 | 350 | 84% | 7.6 |
| validacion | rev5 | 6.24% | 0.28% | 724 | 41 | 100% | 2.9 |
| validacion | umbral | 5.38% | 0.38% | 692 | 116 | 94% | 8.3 |
| test | rev5 | 11.28% | 1.05% | 2927 | 96 | 100% | 2.9 |
| test | umbral | 10.38% | 0.71% | 2921 | 417 | 82% | 12.6 |

Bootstrap pareado en test (umbral − rev5): media anual -0.00816676280595604, intervalo 90 % [-0.01593182077916241, 0.0006132776328002045], P(> 0) = 0.0635

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 11.48% | 11.25% | -63 |
| costes_x2 | 10.88% | 8.66% | -586 |
| costes_x3 | 10.48% | 7.08% | -887 |
| retraso_1h | 11.29% | 10.34% | -256 |
| retraso_3h | 11.30% | 10.34% | -258 |
| pata_adversa | 10.80% | 8.26% | -667 |
| funding_x075 | 8.12% | 7.06% | -272 |
| nocional_min_perp_5 | 11.28% | 10.38% | -242 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'NO DESCARTADA', 'criterios_activos': [], 'banda': '> 7 %: solo habilita prospectiva'}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
