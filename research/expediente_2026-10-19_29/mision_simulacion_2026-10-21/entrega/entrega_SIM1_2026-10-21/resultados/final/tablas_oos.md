### OOS-ETH (prueba final, una sola lectura)

Velas: 30226 · 2023-01-01T00:00:00+00:00 → 2026-05-31T23:00:00+00:00

**Por operación** (neto en % del nocional; IC90 por bootstrap de bloques mensuales)

| Config. | n | Media neta | IC90 | p (media ≤ 0) | Mediana | Acierto | Ganancia media | Pérdida media | F. beneficio | Bruto (S4) | Costo implícito | Comisión ×2 (S2) | +1 vela (S3) | Gobernadores (S6) | Veredicto |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P3 | 120 | -0.517 | [-0.725, -0.297] | +1.000 | -0.935 | +0.26 | +1.793 | -1.322 | +0.47 | -0.288 | +0.230 | -0.711 | -0.450 | -0.517 | EN CONTRA |
| P1 | 359 | -0.339 | [-0.478, -0.216] | +1.000 | -0.819 | +0.29 | +1.843 | -1.229 | +0.61 | -0.102 | +0.237 | -0.531 | -0.378 | -0.333 | EN CONTRA |
| P2 | 66 | -0.180 | [-0.554, +0.205] | +0.783 | -0.702 | +0.32 | +1.887 | -1.145 | +0.77 | +0.037 | +0.218 | -0.382 | -0.001 | -0.180 | NO CONCLUYENTE |
| S1 | 441 | -0.335 | [-0.454, -0.225] | +1.000 | -0.803 | +0.29 | +1.830 | -1.231 | +0.61 | -0.111 | +0.224 | -0.530 | -0.333 | -0.335 | EN CONTRA |

**Capital** (cuenta de 100 000 USDT; curva diaria desde la primera decisión)

| Config. | Capital final | Retorno neto total | Anualizado | Volatilidad anual | Sharpe | IC90 Sharpe | Sortino | Máx. caída | Exposición (velas en mercado) | Comisiones (USDT) | Comisión / nocional |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P3 | 99,565.85 | -0.434 % | -0.127 % | +0.080 % | -1.59 | [-2.32, -0.88] | -0.58 | +0.442 % | 2.0 % | 176.28 | +0.200 % |
| P1 | 99,303.58 | -0.696 % | -0.204 % | +0.134 % | -1.52 | [-2.42, -0.81] | -0.83 | +0.696 % | 8.6 % | 516.61 | +0.200 % |
| P2 | 99,806.00 | -0.194 % | -0.057 % | +0.132 % | -0.43 | [-1.30, +0.48] | -0.11 | +0.278 % | 1.6 % | 240.53 | +0.200 % |
| S1 | 98,796.80 | -1.203 % | -0.353 % | +0.173 % | -2.04 | [-2.64, -1.51] | -1.11 | +1.203 % | 10.3 % | 757.52 | +0.200 % |

**Contra el azar** (entrada aleatoria emparejada: mismas duraciones, estratificado por trimestre)

| Config. | Media | Media del nulo | Banda90 del nulo | Exceso | p_nulo |
|---|---|---|---|---|---|
| P3 | -0.517 | -0.276 | [-0.489, -0.054] | -0.241 | +0.966 |
| P1 | -0.339 | -0.264 | [-0.407, -0.119] | -0.075 | +0.811 |
| P2 | -0.180 | -0.313 | [-0.680, +0.061] | +0.133 | +0.280 |
| S1 | -0.335 | -0.270 | [-0.399, -0.143] | -0.065 | +0.792 |

**Por período** (n · media neta %)

| Config. | 2023 | 2024 | 2025-01→2026-05 |
|---|---|---|---|
| P3 | 39 · -0.458 | 41 · -0.516 | 40 · -0.577 |
| P1 | 113 · -0.386 | 104 · -0.337 | 142 · -0.304 |
| P2 | 22 · -0.104 | 17 · +0.353 | 27 · -0.578 |
| S1 | 141 · -0.431 | 124 · -0.231 | 176 · -0.333 |

**Por condición de mercado** (retorno de 30 días antes de la entrada; n · media neta %)

| Config. | alcista (> +10 %) | lateral | bajista (< −10 %) | ρ confianza–neto |
|---|---|---|---|---|
| P3 | 43 · -0.534 | 56 · -0.407 | 21 · -0.778 | +0.066 |
| P1 | 140 · -0.398 | 166 · -0.191 | 39 · -0.668 | -0.063 |
| P2 | 13 · -0.152 | 30 · -0.158 | 23 · -0.225 | -0.050 |
| S1 | 161 · -0.357 | 197 · -0.236 | 69 · -0.517 | -0.087 |

**Referencias** (misma ventana; comisión de 10 bps y deslizamiento de 2 bps donde operan)

| Referencia | Retorno total | Anualizado | Volatilidad | Sharpe | Máx. caída | Exposición | Operaciones |
|---|---|---|---|---|---|---|---|
| buy_and_hold | +67.9 % | +16.4 % | +61.6 % | +0.55 | +65.3 % | +100.0 % | 1 |
| efectivo | +0.0 % | +0.0 % | +0.0 % | — | +0.0 % | +0.0 % | 0 |
| cruce_medias_20_50_long_flat | -32.5 % | -10.9 % | +41.2 % | -0.07 | +68.1 % | +51.2 % | 346 |
| volatilidad_objetivo_15 | -2.2 % | -0.7 % | +17.2 % | +0.05 | +26.5 % | +99.8 % | 1 |

```
{
 "primaria": "P3",
 "alfa": 0.05,
 "holm_secundarias": {
  "P2": {
   "p": 0.7834,
   "umbral_holm": 0.016666666666666666,
   "rechaza_nulo": false
  },
  "P1": {
   "p": 1.0,
   "umbral_holm": 0.025,
   "rechaza_nulo": false
  },
  "S1": {
   "p": 1.0,
   "umbral_holm": 0.05,
   "rechaza_nulo": false
  }
 },
 "veredicto": {
  "P3": "EN CONTRA",
  "P1": "EN CONTRA",
  "P2": "NO CONCLUYENTE",
  "S1": "EN CONTRA"
 },
 "consecuencia": "ningún resultado cambia validada_para_operar ni habilita capital"
}
```

