# Ensayo del protocolo en mundos SINTÉTICOS

**No es evidencia económica.** Mide qué elige, promueve y declara el protocolo cuando el mundo lo genera `hcarry.data.sintetico`. En los mundos nulos el funding está barajado en el tiempo (sin persistencia).

Mundos: 12 normales y 12 nulos.

## Mundos normales (12)

| familia | seleccionada en desarrollo | promovida a test | componente DEMOSTRADO | CAGR test mediano (si promovida) | supera a la referencia rev. 5 en test |
|---|---|---|---|---|---|
| apalancada | 6 | 4 | 3 | 8.25% | 4/4 |
| rho_vol | 7 | 3 | 1 | 3.89% | 2/3 |
| escala_vol | 11 | 3 | 1 | 1.05% | 2/3 |
| umbral | 12 | 7 | 5 | 5.80% | 6/7 |
|  | parámetros elegidos: umbral_v21_e0.05_s0.0 ×3, umbral_v21_e0.05_s0.03 ×2, umbral_v21_e0.1_s0.0 ×4, umbral_v21_e0.1_s0.03 ×2, umbral_v63_e0.05_s0.03 ×1 | | | | |
| umbral_apalancado | 12 | 8 | 6 | 8.25% | 8/8 |
|  | parámetros elegidos: umbral_v21_e0.05_s0.03_rho05 ×2, umbral_v21_e0.05_s0.0_rho05 ×4, umbral_v21_e0.1_s0.03_rho05 ×2, umbral_v21_e0.1_s0.0_rho05 ×4 | | | | |

Referencia rev. 5 en test: CAGR mediano 5.77% (mín -6.41%, máx 9.59%). Siempre ρ = 0,5: mediano 7.12%.

## Mundos NULOS (12)

| familia | seleccionada en desarrollo | promovida a test | componente DEMOSTRADO | CAGR test mediano (si promovida) | supera a la referencia rev. 5 en test |
|---|---|---|---|---|---|
| apalancada | 12 | 9 | 9 | 7.26% | 9/9 |
| rho_vol | 12 | 2 | 2 | 9.16% | 2/2 |
| escala_vol | 12 | 0 | 0 | — | 0/0 |
| umbral | 12 | 2 | 0 | 7.18% | 0/2 |
|  | parámetros elegidos: umbral_v63_e0.05_s0.0 ×6, umbral_v63_e0.15_s0.0 ×2, umbral_v63_e0.1_s0.0 ×4 | | | | |
| umbral_apalancado | 12 | 1 | 0 | 7.96% | 1/1 |
|  | parámetros elegidos: umbral_v63_e0.05_s0.03_rho05 ×1, umbral_v63_e0.05_s0.0_rho05 ×7, umbral_v63_e0.15_s0.0_rho05 ×2, umbral_v63_e0.1_s0.0_rho05 ×2 | | | | |

Referencia rev. 5 en test: CAGR mediano 5.37% (mín -0.99%, máx 10.53%). Siempre ρ = 0,5: mediano 6.31%.

## Por mundo

| mundo | ref. dev / val / test | promovidos | componentes demostrados |
|---|---|---|---|
| semilla101 | 7.1% / 15.6% / 4.2% | siempre_rho05 vs referencia, umbral_v21_e0.1_s0.0 vs referencia, umbral_v21_e0.1_s0.0_rho05 vs siempre_rho05 | siempre_rho05 |
| semilla101_nulo | 7.1% / 7.5% / 8.0% | siempre_rho05 vs referencia, rho_vol vs siempre_rho05, umbral_v63_e0.05_s0.0 vs referencia | siempre_rho05, rho_vol |
| semilla102 | 0.3% / 22.2% / 7.9% | — | — |
| semilla102_nulo | 6.2% / 7.2% / 5.8% | siempre_rho05 vs referencia | siempre_rho05 |
| semilla103 | 6.3% / -2.6% / 0.3% | escala_vol vs referencia, umbral_v21_e0.05_s0.03 vs referencia, umbral_v21_e0.1_s0.03_rho05 vs siempre_rho05 | umbral_v21_e0.05_s0.03, umbral_v21_e0.1_s0.03_rho05 |
| semilla103_nulo | 2.4% / 2.6% / 3.2% | siempre_rho05 vs referencia | siempre_rho05 |
| semilla104 | 5.8% / -7.6% / 4.7% | escala_vol vs referencia, umbral_v21_e0.1_s0.03 vs referencia, umbral_v21_e0.1_s0.03_rho05 vs siempre_rho05 | — |
| semilla104_nulo | 2.7% / 1.2% / 2.4% | — | — |
| semilla105 | -1.2% / 13.0% / 8.5% | — | — |
| semilla105_nulo | 4.2% / 4.6% / 4.9% | siempre_rho05 vs referencia | siempre_rho05 |
| semilla106 | 9.1% / -10.9% / -6.4% | rho_vol vs siempre_rho05, escala_vol vs referencia, umbral_v21_e0.1_s0.0 vs referencia, umbral_v21_e0.1_s0.0_rho05 vs siempre_rho05 | escala_vol, umbral_v21_e0.1_s0.0, umbral_v21_e0.1_s0.0_rho05 |
| semilla106_nulo | -0.7% / -0.3% / -1.0% | — | — |
| semilla107 | -0.5% / 0.3% / 6.9% | rho_vol vs siempre_rho05, umbral_v21_e0.05_s0.0 vs referencia, umbral_v21_e0.05_s0.0_rho05 vs siempre_rho05 | umbral_v21_e0.05_s0.0, umbral_v21_e0.05_s0.0_rho05 |
| semilla107_nulo | 1.3% / 0.8% / 3.2% | — | — |
| semilla108 | 10.6% / 3.3% / 2.9% | siempre_rho05 vs referencia, rho_vol vs siempre_rho05 | rho_vol |
| semilla108_nulo | 6.3% / 6.5% / 6.7% | siempre_rho05 vs referencia, umbral_v63_e0.05_s0.0 vs referencia, umbral_v63_e0.1_s0.0_rho05 vs siempre_rho05 | siempre_rho05 |
| semilla109 | 6.6% / 4.2% / 8.1% | siempre_rho05 vs referencia, umbral_v21_e0.05_s0.0_rho05 vs siempre_rho05 | siempre_rho05, umbral_v21_e0.05_s0.0_rho05 |
| semilla109_nulo | 7.2% / 6.1% / 6.3% | siempre_rho05 vs referencia, rho_vol vs siempre_rho05 | siempre_rho05, rho_vol |
| semilla110 | 6.0% / 5.0% / 0.1% | umbral_v21_e0.05_s0.03 vs referencia, umbral_v21_e0.05_s0.03_rho05 vs siempre_rho05 | umbral_v21_e0.05_s0.03, umbral_v21_e0.05_s0.03_rho05 |
| semilla110_nulo | 4.5% / 4.0% / 4.1% | siempre_rho05 vs referencia | siempre_rho05 |
| semilla111 | 1.8% / 9.5% / 8.4% | umbral_v21_e0.05_s0.0 vs referencia, umbral_v21_e0.05_s0.0_rho05 vs siempre_rho05 | umbral_v21_e0.05_s0.0, umbral_v21_e0.05_s0.0_rho05 |
| semilla111_nulo | 4.8% / 5.7% / 5.8% | siempre_rho05 vs referencia | siempre_rho05 |
| semilla112 | 8.0% / 17.3% / 9.6% | siempre_rho05 vs referencia | siempre_rho05 |
| semilla112_nulo | 10.2% / 9.2% / 10.5% | siempre_rho05 vs referencia | siempre_rho05 |
