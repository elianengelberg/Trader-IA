# Ensayo del protocolo en mundos SINTÉTICOS

**No es evidencia económica.** Mide qué elige, promueve y declara el protocolo cuando el mundo lo genera `hcarry.data.sintetico`. En los mundos nulos el funding está barajado en el tiempo (sin persistencia).

Mundos: 20 normales y 20 nulos; variantes del generador: ['bajista_suave', 'base'].

## Variante bajista_suave: mundos normales (8)

| familia | seleccionada en desarrollo | promovida a test | componente DEMOSTRADO | CAGR test mediano (si promovida) | supera a la referencia rev. 5 en test |
|---|---|---|---|---|---|
| apalancada | 8 | 6 | 4 | 16.70% | 6/6 |
| rho_vol | 8 | 0 | 0 | — | 0/0 |
| escala_vol | 8 | 1 | 1 | 3.99% | 1/1 |
| umbral | 8 | 2 | 2 | 6.99% | 2/2 |
|  | parámetros elegidos: umbral_v63_e0.05_s0.0 ×2, umbral_v63_e0.05_s0.03 ×3, umbral_v63_e0.1_s0.0 ×3 | | | | |
| umbral_apalancado | 8 | 5 | 3 | 11.72% | 5/5 |
|  | parámetros elegidos: umbral_v63_e0.05_s0.03_rho05 ×4, umbral_v63_e0.1_s0.0_rho05 ×4 | | | | |
| prima | 8 | 1 | 0 | 7.98% | 1/1 |
|  | parámetros elegidos: prima_v72_e0.05_s0.0 ×1, prima_v72_e0.1_s0.0 ×5, prima_v72_e0.1_s0.03 ×2 | | | | |
| prima_apalancada | 7 | 1 | 0 | 9.07% | 1/1 |
|  | parámetros elegidos: prima_v72_e0.05_s0.0_rho05 ×1, prima_v72_e0.1_s0.03_rho05 ×3, prima_v72_e0.1_s0.0_rho05 ×3 | | | | |

Referencia rev. 5 en test: CAGR mediano 11.14% (mín 1.28%, máx 23.35%); caída mediana 1.47%. Siempre ρ = 0,5: CAGR mediano 12.96%.

## Variante bajista_suave: mundos NULOS (8)

| familia | seleccionada en desarrollo | promovida a test | componente DEMOSTRADO | CAGR test mediano (si promovida) | supera a la referencia rev. 5 en test |
|---|---|---|---|---|---|
| apalancada | 8 | 6 | 5 | 12.42% | 5/6 |
| rho_vol | 8 | 0 | 0 | — | 0/0 |
| escala_vol | 8 | 0 | 0 | — | 0/0 |
| umbral | 8 | 0 | 0 | — | 0/0 |
|  | parámetros elegidos: umbral_v63_e0.05_s0.0 ×2, umbral_v63_e0.05_s0.03 ×1, umbral_v63_e0.1_s0.0 ×2, umbral_v63_e0.1_s0.03 ×3 | | | | |
| umbral_apalancado | 8 | 1 | 0 | 7.24% | 1/1 |
|  | parámetros elegidos: umbral_v21_e0.05_s0.03_rho05 ×1, umbral_v21_e0.05_s0.0_rho05 ×1, umbral_v63_e0.05_s0.03_rho05 ×1, umbral_v63_e0.05_s0.0_rho05 ×2, umbral_v63_e0.15_s0.03_rho05 ×1, umbral_v63_e0.1_s0.03_rho05 ×1, umbral_v63_e0.1_s0.0_rho05 ×1 | | | | |
| prima | 8 | 0 | 0 | — | 0/0 |
|  | parámetros elegidos: prima_v72_e0.1_s0.0 ×8 | | | | |
| prima_apalancada | 8 | 1 | 0 | 7.68% | 1/1 |
|  | parámetros elegidos: prima_v72_e0.05_s0.0_rho05 ×2, prima_v72_e0.1_s0.03_rho05 ×1, prima_v72_e0.1_s0.0_rho05 ×5 | | | | |

Referencia rev. 5 en test: CAGR mediano 8.05% (mín 2.25%, máx 11.22%); caída mediana 0.28%. Siempre ρ = 0,5: CAGR mediano 9.88%.

## Variante base: mundos normales (12)

| familia | seleccionada en desarrollo | promovida a test | componente DEMOSTRADO | CAGR test mediano (si promovida) | supera a la referencia rev. 5 en test |
|---|---|---|---|---|---|
| apalancada | 6 | 4 | 3 | 8.25% | 4/4 |
| rho_vol | 7 | 3 | 1 | 3.89% | 2/3 |
| escala_vol | 11 | 3 | 1 | 1.05% | 2/3 |
| umbral | 12 | 7 | 5 | 5.80% | 6/7 |
|  | parámetros elegidos: umbral_v21_e0.05_s0.0 ×3, umbral_v21_e0.05_s0.03 ×2, umbral_v21_e0.1_s0.0 ×4, umbral_v21_e0.1_s0.03 ×2, umbral_v63_e0.05_s0.03 ×1 | | | | |
| umbral_apalancado | 12 | 8 | 6 | 8.25% | 8/8 |
|  | parámetros elegidos: umbral_v21_e0.05_s0.03_rho05 ×2, umbral_v21_e0.05_s0.0_rho05 ×4, umbral_v21_e0.1_s0.03_rho05 ×2, umbral_v21_e0.1_s0.0_rho05 ×4 | | | | |
| prima | 12 | 8 | 3 | 5.42% | 7/8 |
|  | parámetros elegidos: prima_v72_e0.1_s0.0 ×11, prima_v72_e0.1_s0.03 ×1 | | | | |
| prima_apalancada | 12 | 8 | 3 | 6.85% | 8/8 |
|  | parámetros elegidos: prima_v72_e0.05_s0.0_rho05 ×1, prima_v72_e0.1_s0.03_rho05 ×2, prima_v72_e0.1_s0.0_rho05 ×9 | | | | |

Referencia rev. 5 en test: CAGR mediano 5.77% (mín -6.41%, máx 9.59%); caída mediana 5.65%. Siempre ρ = 0,5: CAGR mediano 7.12%.

## Variante base: mundos NULOS (12)

| familia | seleccionada en desarrollo | promovida a test | componente DEMOSTRADO | CAGR test mediano (si promovida) | supera a la referencia rev. 5 en test |
|---|---|---|---|---|---|
| apalancada | 12 | 9 | 9 | 7.26% | 9/9 |
| rho_vol | 12 | 2 | 2 | 9.16% | 2/2 |
| escala_vol | 12 | 0 | 0 | — | 0/0 |
| umbral | 12 | 2 | 0 | 7.18% | 0/2 |
|  | parámetros elegidos: umbral_v63_e0.05_s0.0 ×6, umbral_v63_e0.15_s0.0 ×2, umbral_v63_e0.1_s0.0 ×4 | | | | |
| umbral_apalancado | 12 | 1 | 0 | 7.96% | 1/1 |
|  | parámetros elegidos: umbral_v63_e0.05_s0.03_rho05 ×1, umbral_v63_e0.05_s0.0_rho05 ×7, umbral_v63_e0.15_s0.0_rho05 ×2, umbral_v63_e0.1_s0.0_rho05 ×2 | | | | |
| prima | 12 | 0 | 0 | — | 0/0 |
|  | parámetros elegidos: prima_v72_e0.1_s0.0 ×12 | | | | |
| prima_apalancada | 12 | 0 | 0 | — | 0/0 |
|  | parámetros elegidos: prima_v72_e0.05_s0.0_rho05 ×1, prima_v72_e0.1_s0.0_rho05 ×11 | | | | |

Referencia rev. 5 en test: CAGR mediano 5.37% (mín -0.99%, máx 10.53%); caída mediana 0.43%. Siempre ρ = 0,5: CAGR mediano 6.31%.

## Por mundo

| mundo | ref. dev / val / test | promovidos | componentes demostrados |
|---|---|---|---|
| base_semilla101 | 7.1% / 15.6% / 4.2% | siempre_rho05 vs referencia, umbral_v21_e0.1_s0.0 vs referencia, umbral_v21_e0.1_s0.0_rho05 vs siempre_rho05, prima_v72_e0.1_s0.0 vs referencia, prima_v72_e0.1_s0.0_rho05 vs siempre_rho05 | siempre_rho05 |
| base_semilla101_nulo | 7.1% / 7.5% / 8.0% | siempre_rho05 vs referencia, rho_vol vs siempre_rho05, umbral_v63_e0.05_s0.0 vs referencia | siempre_rho05, rho_vol |
| base_semilla102 | 0.3% / 22.2% / 7.9% | — | — |
| base_semilla102_nulo | 6.2% / 7.2% / 5.8% | siempre_rho05 vs referencia | siempre_rho05 |
| base_semilla103 | 6.3% / -2.6% / 0.3% | escala_vol vs referencia, umbral_v21_e0.05_s0.03 vs referencia, umbral_v21_e0.1_s0.03_rho05 vs siempre_rho05, prima_v72_e0.1_s0.0 vs referencia, prima_v72_e0.1_s0.0_rho05 vs siempre_rho05 | umbral_v21_e0.05_s0.03, umbral_v21_e0.1_s0.03_rho05, prima_v72_e0.1_s0.0, prima_v72_e0.1_s0.0_rho05 |
| base_semilla103_nulo | 2.4% / 2.6% / 3.2% | siempre_rho05 vs referencia | siempre_rho05 |
| base_semilla104 | 5.8% / -7.6% / 4.7% | escala_vol vs referencia, umbral_v21_e0.1_s0.03 vs referencia, umbral_v21_e0.1_s0.03_rho05 vs siempre_rho05, prima_v72_e0.1_s0.0 vs referencia, prima_v72_e0.1_s0.0_rho05 vs siempre_rho05 | — |
| base_semilla104_nulo | 2.7% / 1.2% / 2.4% | — | — |
| base_semilla105 | -1.2% / 13.0% / 8.5% | prima_v72_e0.1_s0.0 vs referencia | — |
| base_semilla105_nulo | 4.2% / 4.6% / 4.9% | siempre_rho05 vs referencia | siempre_rho05 |
| base_semilla106 | 9.1% / -10.9% / -6.4% | rho_vol vs siempre_rho05, escala_vol vs referencia, umbral_v21_e0.1_s0.0 vs referencia, umbral_v21_e0.1_s0.0_rho05 vs siempre_rho05, prima_v72_e0.1_s0.0 vs referencia, prima_v72_e0.1_s0.0_rho05 vs siempre_rho05 | escala_vol, umbral_v21_e0.1_s0.0, umbral_v21_e0.1_s0.0_rho05, prima_v72_e0.1_s0.0, prima_v72_e0.1_s0.0_rho05 |
| base_semilla106_nulo | -0.7% / -0.3% / -1.0% | — | — |
| base_semilla107 | -0.5% / 0.3% / 6.9% | rho_vol vs siempre_rho05, umbral_v21_e0.05_s0.0 vs referencia, umbral_v21_e0.05_s0.0_rho05 vs siempre_rho05, prima_v72_e0.1_s0.0 vs referencia, prima_v72_e0.1_s0.03_rho05 vs siempre_rho05 | umbral_v21_e0.05_s0.0, umbral_v21_e0.05_s0.0_rho05 |
| base_semilla107_nulo | 1.3% / 0.8% / 3.2% | — | — |
| base_semilla108 | 10.6% / 3.3% / 2.9% | siempre_rho05 vs referencia, rho_vol vs siempre_rho05 | rho_vol |
| base_semilla108_nulo | 6.3% / 6.5% / 6.7% | siempre_rho05 vs referencia, umbral_v63_e0.05_s0.0 vs referencia, umbral_v63_e0.1_s0.0_rho05 vs siempre_rho05 | siempre_rho05 |
| base_semilla109 | 6.6% / 4.2% / 8.1% | siempre_rho05 vs referencia, umbral_v21_e0.05_s0.0_rho05 vs siempre_rho05, prima_v72_e0.1_s0.0_rho05 vs siempre_rho05 | siempre_rho05, umbral_v21_e0.05_s0.0_rho05 |
| base_semilla109_nulo | 7.2% / 6.1% / 6.3% | siempre_rho05 vs referencia, rho_vol vs siempre_rho05 | siempre_rho05, rho_vol |
| base_semilla110 | 6.0% / 5.0% / 0.1% | umbral_v21_e0.05_s0.03 vs referencia, umbral_v21_e0.05_s0.03_rho05 vs siempre_rho05, prima_v72_e0.1_s0.0 vs referencia, prima_v72_e0.1_s0.0_rho05 vs siempre_rho05 | umbral_v21_e0.05_s0.03, umbral_v21_e0.05_s0.03_rho05, prima_v72_e0.1_s0.0, prima_v72_e0.1_s0.0_rho05 |
| base_semilla110_nulo | 4.5% / 4.0% / 4.1% | siempre_rho05 vs referencia | siempre_rho05 |
| base_semilla111 | 1.8% / 9.5% / 8.4% | umbral_v21_e0.05_s0.0 vs referencia, umbral_v21_e0.05_s0.0_rho05 vs siempre_rho05, prima_v72_e0.1_s0.03 vs referencia, prima_v72_e0.1_s0.03_rho05 vs siempre_rho05 | umbral_v21_e0.05_s0.0, umbral_v21_e0.05_s0.0_rho05 |
| base_semilla111_nulo | 4.8% / 5.7% / 5.8% | siempre_rho05 vs referencia | siempre_rho05 |
| base_semilla112 | 8.0% / 17.3% / 9.6% | siempre_rho05 vs referencia | siempre_rho05 |
| base_semilla112_nulo | 10.2% / 9.2% / 10.5% | siempre_rho05 vs referencia | siempre_rho05 |
| bajista_suave_semilla201 | 3.4% / 8.6% / 23.3% | siempre_rho05 vs referencia, umbral_v63_e0.05_s0.03_rho05 vs siempre_rho05 | siempre_rho05 |
| bajista_suave_semilla201_nulo | 10.4% / 9.7% / 11.2% | siempre_rho05 vs referencia | siempre_rho05 |
| bajista_suave_semilla202 | 9.1% / 6.6% / 13.8% | siempre_rho05 vs referencia | siempre_rho05 |
| bajista_suave_semilla202_nulo | 10.9% / 9.3% / 10.5% | siempre_rho05 vs referencia | siempre_rho05 |
| bajista_suave_semilla203 | 3.3% / -2.0% / 3.5% | escala_vol vs referencia, umbral_v63_e0.05_s0.03 vs referencia, umbral_v63_e0.05_s0.03_rho05 vs siempre_rho05 | escala_vol, umbral_v63_e0.05_s0.03, umbral_v63_e0.05_s0.03_rho05 |
| bajista_suave_semilla203_nulo | 2.0% / 2.7% / 2.2% | siempre_rho05 vs referencia | — |
| bajista_suave_semilla204 | 0.5% / 11.3% / 11.0% | siempre_rho05 vs referencia | — |
| bajista_suave_semilla204_nulo | 3.0% / 6.6% / 6.3% | siempre_rho05 vs referencia | siempre_rho05 |
| bajista_suave_semilla205 | 9.7% / 7.6% / 1.3% | siempre_rho05 vs referencia, umbral_v63_e0.05_s0.03_rho05 vs siempre_rho05 | umbral_v63_e0.05_s0.03_rho05 |
| bajista_suave_semilla205_nulo | 6.0% / 6.0% / 6.7% | — | — |
| bajista_suave_semilla206 | 5.2% / 15.0% / 16.7% | siempre_rho05 vs referencia | siempre_rho05 |
| bajista_suave_semilla206_nulo | 10.6% / 8.9% / 10.4% | siempre_rho05 vs referencia | siempre_rho05 |
| bajista_suave_semilla207 | 6.7% / 15.4% / 6.0% | umbral_v63_e0.1_s0.0 vs referencia, umbral_v63_e0.1_s0.0_rho05 vs siempre_rho05, prima_v72_e0.1_s0.0 vs referencia, prima_v72_e0.1_s0.0_rho05 vs siempre_rho05 | umbral_v63_e0.1_s0.0, umbral_v63_e0.1_s0.0_rho05 |
| bajista_suave_semilla207_nulo | 8.8% / 6.9% / 7.0% | umbral_v63_e0.1_s0.03_rho05 vs siempre_rho05, prima_v72_e0.1_s0.0_rho05 vs siempre_rho05 | — |
| bajista_suave_semilla208 | 6.5% / 6.2% / 11.3% | siempre_rho05 vs referencia, umbral_v63_e0.1_s0.0_rho05 vs siempre_rho05 | siempre_rho05 |
| bajista_suave_semilla208_nulo | 7.3% / 8.8% / 9.0% | siempre_rho05 vs referencia | siempre_rho05 |
