### DEV-BTC

Velas: 4000 · 2022-08-01T00:00:00+00:00 → 2023-01-14T15:00:00+00:00

**Por operación** (neto en % del nocional; IC90 por bootstrap de bloques mensuales)

| Config. | n | Media neta | IC90 | p (media ≤ 0) | Mediana | Acierto | Ganancia media | Pérdida media | F. beneficio | Bruto (S4) | Costo implícito | Comisión ×2 (S2) | +1 vela (S3) | Gobernadores (S6) | Veredicto |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P3 | 9 | -0.051 | [-1.153, +0.790] | +0.590 | -0.344 | +0.33 | +1.964 | -1.058 | +0.93 | +0.186 | +0.237 | -0.251 | — | — | — |
| S1 | 74 | +0.014 | [-0.440, +0.273] | +0.510 | -0.458 | +0.42 | +2.051 | -1.455 | +1.02 | +0.249 | +0.235 | -0.248 | — | — | — |
| M1 (q=0.739) | 3 | +0.554 | [-0.798, +3.259] | +0.299 | -0.344 | +0.33 | +3.259 | -0.798 | +2.04 | — | — | — | — | — | — |

**Capital** (cuenta de 100 000 USDT; curva diaria desde la primera decisión)

| Config. | Capital final | Retorno neto total | Anualizado | Volatilidad anual | Sharpe | IC90 Sharpe | Sortino | Máx. caída | Exposición (velas en mercado) | Comisiones (USDT) | Comisión / nocional |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P3 | 99,996.56 | -0.003 % | -0.008 % | +0.037 % | -0.21 | [-2.88, +2.19] | -0.05 | +0.034 % | 1.3 % | 10.00 | +0.200 % |
| S1 | 100,020.18 | +0.020 % | +0.045 % | +0.158 % | +0.29 | [-1.39, +1.65] | +0.23 | +0.115 % | 11.1 % | 84.63 | +0.200 % |
| M1 | 100,005.44 | +0.005 % | +0.012 % | +0.025 % | +0.50 | [-2.88, +2.28] | +0.13 | +0.009 % | 0.5 % | 3.50 | +0.201 % |

**Contra el azar** (entrada aleatoria emparejada: mismas duraciones, estratificado por trimestre)

| Config. | Media | Media del nulo | Banda90 del nulo | Exceso | p_nulo |
|---|---|---|---|---|---|
| P3 | -0.051 | -0.170 | [-1.275, +0.833] | +0.119 | +0.478 |
| S1 | +0.014 | -0.188 | [-0.563, +0.158] | +0.202 | +0.164 |
| M1 | +0.554 | -0.007 | [-2.171, +2.204] | +0.561 | +0.338 |

**Por período** (n · media neta %)

| Config. | 2017-08→2019-09 | 2019-10→2021-12 | 2022 | 2023→2026-05 |
|---|---|---|---|---|
| P3 | 0 · — | 0 · — | 8 · -0.042 | 1 · -0.122 |
| S1 | 0 · — | 0 · — | 61 · -0.073 | 13 · +0.424 |
| M1 | 0 · — | 0 · — | 3 · +0.554 | 0 · — |

**Por condición de mercado** (retorno de 30 días antes de la entrada; n · media neta %)

| Config. | alcista (> +10 %) | lateral | bajista (< −10 %) | ρ confianza–neto |
|---|---|---|---|---|
| P3 | 2 · -1.233 | — | 4 · -0.596 | -0.133 |
| S1 | 25 · +0.048 | 5 · -0.878 | 19 · -0.327 | +0.055 |
| M1 | — | — | 2 · -0.798 | -0.500 |

**Referencias** (misma ventana; comisión de 10 bps y deslizamiento de 2 bps donde operan)

| Referencia | Retorno total | Anualizado | Volatilidad | Sharpe | Máx. caída | Exposición | Operaciones |
|---|---|---|---|---|---|---|---|
| buy_and_hold | +93.2 % | +342.0 % | +75.9 % | +2.34 | +44.1 % | +100.0 % | 1 |
| efectivo | +0.0 % | +0.0 % | +0.0 % | — | +0.0 % | +0.0 % | 0 |
| cruce_medias_20_50_long_flat | +29.5 % | +79.3 % | +56.5 % | +1.32 | +43.8 % | +55.2 % | 43 |
| volatilidad_objetivo_15 | +12.2 % | +29.7 % | +15.1 % | +1.80 | +11.1 % | +98.5 % | 1 |

### DEV-ETH

Velas: 3672 · 2022-08-01T00:00:00+00:00 → 2022-12-31T23:00:00+00:00

**Por operación** (neto en % del nocional; IC90 por bootstrap de bloques mensuales)

| Config. | n | Media neta | IC90 | p (media ≤ 0) | Mediana | Acierto | Ganancia media | Pérdida media | F. beneficio | Bruto (S4) | Costo implícito | Comisión ×2 (S2) | +1 vela (S3) | Gobernadores (S6) | Veredicto |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P3 | 12 | +0.140 | [-0.194, +1.076] | +0.225 | -0.148 | +0.50 | +1.951 | -1.672 | +1.17 | +0.371 | +0.231 | -0.061 | — | — | — |
| S1 | 85 | +0.314 | [-0.014, +0.516] | +0.060 | -0.487 | +0.44 | +2.442 | -1.326 | +1.42 | +0.539 | +0.225 | +0.118 | — | — | — |
| M1 (q=0.653) | 4 | +0.028 | [-0.887, +2.772] | +0.387 | -0.148 | +0.50 | +1.493 | -1.438 | +1.04 | +0.255 | +0.228 | -0.172 | — | — | — |

**Capital** (cuenta de 100 000 USDT; curva diaria desde la primera decisión)

| Config. | Capital final | Retorno neto total | Anualizado | Volatilidad anual | Sharpe | IC90 Sharpe | Sortino | Máx. caída | Exposición (velas en mercado) | Comisiones (USDT) | Comisión / nocional |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P3 | 100,021.57 | +0.022 % | +0.052 % | +0.062 % | +0.85 | [+0.26, +1.99] | +0.32 | +0.024 % | 1.9 % | 14.93 | +0.200 % |
| S1 | 100,163.42 | +0.163 % | +0.398 % | +0.249 % | +1.59 | [-0.15, +2.93] | +1.47 | +0.090 % | 14.8 % | 113.61 | +0.200 % |
| M1 | 100,001.60 | +0.002 % | +0.004 % | +0.032 % | +0.12 | [-2.72, +2.44] | +0.02 | +0.016 % | 0.5 % | 5.26 | +0.200 % |

**Contra el azar** (entrada aleatoria emparejada: mismas duraciones, estratificado por trimestre)

| Config. | Media | Media del nulo | Banda90 del nulo | Exceso | p_nulo |
|---|---|---|---|---|---|
| P3 | +0.140 | -0.403 | [-1.307, +0.393] | +0.543 | +0.149 |
| S1 | +0.314 | -0.289 | [-0.657, +0.101] | +0.603 | +0.005 |
| M1 | +0.028 | -0.177 | [-1.421, +1.115] | +0.205 | +0.383 |

**Por período** (n · media neta %)

| Config. | 2017-08→2019-12 | 2020→2021 | 2022 |
|---|---|---|---|
| P3 | 0 · — | 0 · — | 12 · +0.140 |
| S1 | 0 · — | 0 · — | 85 · +0.314 |
| M1 | 0 · — | 0 · — | 4 · +0.028 |

**Por condición de mercado** (retorno de 30 días antes de la entrada; n · media neta %)

| Config. | alcista (> +10 %) | lateral | bajista (< −10 %) | ρ confianza–neto |
|---|---|---|---|---|
| P3 | 3 · +1.692 | 2 · -1.076 | 2 · -0.140 | -0.217 |
| S1 | 25 · +0.681 | 13 · -0.283 | 18 · -0.279 | +0.119 |
| M1 | 1 · +2.772 | 2 · -1.076 | 1 · -0.510 | +0.000 |

**Referencias** (misma ventana; comisión de 10 bps y deslizamiento de 2 bps donde operan)

| Referencia | Retorno total | Anualizado | Volatilidad | Sharpe | Máx. caída | Exposición | Operaciones |
|---|---|---|---|---|---|---|---|
| buy_and_hold | +3.9 % | +10.0 % | +75.4 % | +0.50 | +72.9 % | +100.0 % | 1 |
| efectivo | +0.0 % | +0.0 % | +0.0 % | — | +0.0 % | +0.0 % | 0 |
| cruce_medias_20_50_long_flat | +133.3 % | +707.5 % | +51.4 % | +4.32 | +25.7 % | +44.7 % | 31 |
| volatilidad_objetivo_15 | +2.0 % | +4.9 % | +15.2 % | +0.39 | +22.7 % | +98.3 % | 1 |

### Regla de promoción de M1

```
{
 "q": {
  "DEV-BTC": 0.739,
  "DEV-ETH": 0.653
 },
 "medias_netas_M1_pct": {
  "DEV-BTC": 0.55421531958619,
  "DEV-ETH": 0.027730063101347464
 },
 "n": {
  "DEV-BTC": 3,
  "DEV-ETH": 4
 },
 "bootstrap_combinado": {
  "P_media_mayor_0": 0.6242424242424243,
  "ic90": [
   -0.851481328156398,
   3.259038818562021
  ],
  "replicas_validas": 495
 },
 "promovida": false,
 "q_para_OOS_ETH": null
}
```

### OOS-ETH (prueba final, una sola lectura)

Velas: 627 · 2023-01-01T00:00:00+00:00 → 2023-01-14T15:00:00+00:00

**Por operación** (neto en % del nocional; IC90 por bootstrap de bloques mensuales)

| Config. | n | Media neta | IC90 | p (media ≤ 0) | Mediana | Acierto | Ganancia media | Pérdida media | F. beneficio | Bruto (S4) | Costo implícito | Comisión ×2 (S2) | +1 vela (S3) | Gobernadores (S6) | Veredicto |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P3 | 0 | — | — | — | — | — | — | — | — | — | — | — | — | — | INSUFICIENTE (muestra) |
| S1 | 6 | -0.556 | [-0.556, -0.556] | +1.000 | -0.754 | +0.33 | +0.564 | -1.116 | +0.25 | -0.320 | +0.236 | -0.755 | — | — | INSUFICIENTE (muestra) |

**Capital** (cuenta de 100 000 USDT; curva diaria desde la primera decisión)

| Config. | Capital final | Retorno neto total | Anualizado | Volatilidad anual | Sharpe | IC90 Sharpe | Sortino | Máx. caída | Exposición (velas en mercado) | Comisiones (USDT) | Comisión / nocional |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P3 | 100,000.00 | +0.000 % | +0.000 % | +0.000 % | — | — | — | -0.000 % | 0.0 % | 0.00 | — % |
| S1 | 99,973.80 | -0.026 % | -0.681 % | +0.090 % | -7.62 | [-7.62, -7.62] | -3.38 | +0.026 % | 12.2 % | 9.27 | +0.200 % |

**Contra el azar** (entrada aleatoria emparejada: mismas duraciones, estratificado por trimestre)

| Config. | Media | Media del nulo | Banda90 del nulo | Exceso | p_nulo |
|---|---|---|---|---|---|
| S1 | -0.556 | -0.397 | [-1.563, +0.877] | -0.159 | +0.597 |

**Por período** (n · media neta %)

| Config. | 2023 | 2024 | 2025-01→2026-05 |
|---|---|---|---|
| P3 | 0 · — | 0 · — | 0 · — |
| S1 | 6 · -0.556 | 0 · — | 0 · — |

**Por condición de mercado** (retorno de 30 días antes de la entrada; n · media neta %)

| Config. | alcista (> +10 %) | lateral | bajista (< −10 %) | ρ confianza–neto |
|---|---|---|---|---|
| P3 | — | — | — | — |
| S1 | — | — | — | +0.371 |

**Referencias** (misma ventana; comisión de 10 bps y deslizamiento de 2 bps donde operan)

| Referencia | Retorno total | Anualizado | Volatilidad | Sharpe | Máx. caída | Exposición | Operaciones |
|---|---|---|---|---|---|---|---|
| buy_and_hold | -5.0 % | — % | +74.5 % | -1.49 | +11.4 % | +100.0 % | 1 |
| efectivo | +0.0 % | — % | +0.0 % | — | +0.0 % | +0.0 % | 0 |
| cruce_medias_20_50_long_flat | -5.0 % | — % | +45.1 % | -2.80 | +10.6 % | +33.5 % | 3 |
| volatilidad_objetivo_15 | -0.6 % | — % | +14.1 % | -1.05 | +2.5 % | +81.7 % | 1 |

```
{
 "primaria": "P3",
 "alfa": 0.05,
 "holm_secundarias": {
  "S1": {
   "p": 1.0,
   "umbral_holm": 0.05,
   "rechaza_nulo": false
  }
 },
 "veredicto": {
  "P3": "INSUFICIENTE (muestra)",
  "S1": "INSUFICIENTE (muestra)"
 },
 "consecuencia": "ningún resultado cambia validada_para_operar ni habilita capital"
}
```

