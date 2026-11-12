# Resultados cuantitativos (Fase L)

**Conclusión: ventaja no demostrada.** Los datos disponibles no permiten afirmar una ventaja, y esta fase no se diseñó para buscarla. La comparación mide algo más acotado: si el cambio de motor 1.1.0 → 1.2.0 (R18) altera los resultados, con los costos y fricciones del simulador.

## 1. Qué se midió y qué no

- **Medido:** el mismo backtest con el motor de A+B (`ENGINE_VERSION` 1.1.0) y con el candidato (1.2.0), frente a las referencias pasivas que calcula el evaluador del repositorio.
- **Datos:** `data/fixtures/BTC-USD_1h.csv`, sha256 `404801b2dc24b28b903a598424493a302da99dd8ce371e55cbe7c8bfa9cb0d05`, 700 barras.
  - **Son SINTÉTICAS** (`generate_fixtures.py`, semilla fija).
  - No sirven para afirmar ventaja.
  - No se usaron para elegir parámetros.
- **No medido:**
  - Datos reales: no se descargaron ni se leyeron retornos reservados (SOL/altcoins).
  - Hipótesis congeladas: T, T-MULTI, H-CARRY, E1, E3-H1 y T-papel no se reabrieron, no se tocaron y no se invocó `fuera_de_muestra_T.py`.
  - Conjunto de evaluación final: no se miró ninguno.
- **Reglas fijadas antes de correr** (`herramientas/fase_l_cuantitativa.py`):
  - configuración por defecto del motor y de la estrategia;
  - solo varían la tasa de rechazo (el factor que R18 toca) y la semilla del simulador;
  - 4 tasas × 3 semillas = 12 corridas por motor;
  - el veredicto es el del evaluador (`evaluate_experiment`), sin umbrales propios.

## 2. Costos y fricciones del simulador (valores por defecto, sin ajustar)

| Parámetro | Valor |
|---|---|
| Comisión taker / maker | 7,5 / 2,5 bps |
| Deslizamiento base | 2,0 bps |
| Coeficiente de impacto | 0,35 |
| Participación máxima | 10 % |
| Latencia de envío / confirmación | 120 / 60 ms |
| Probabilidad de llenado parcial | 0,15 |
| Probabilidad de rechazo | variada: 0; 0,01 (defecto); 0,05; 0,2 |

## 3. Resultados (`logs/L_cuantitativa/motor_A.json`, `motor_dev.json`; tabla en `registro/L_cuantitativa.txt`)

| Rechazo | Semilla | Trades | Retorno % | Máx. DD % | Sharpe | Igual entre motores |
|---|---|---|---|---|---|---|
| 0,00 | 1 / 2 / 3 | 17 / 14 / 14 | −0,0961 / −0,1014 / −0,0634 | 0,1108 / 0,1161 / 0,0778 | −7,16 / −7,25 / −5,23 | sí / sí / sí |
| 0,01 | 1 / 2 / 3 | 17 / 14 / 14 | −0,0961 / −0,1014 / −0,0634 | 0,1108 / 0,1161 / 0,0778 | −7,16 / −7,25 / −5,23 | sí / sí / sí |
| 0,05 | 1 / 2 / 3 | 17 / 13 / 14 | −0,0961 / −0,1066 / −0,0634 | 0,1108 / 0,1290 / 0,0778 | −7,16 / −6,68 / −5,23 | sí / sí / sí |
| 0,20 | 1 / 2 / 3 | 17 / 13 / 14 | −0,0961 / −0,1067 / −0,0899 | 0,1108 / 0,1291 / 0,1043 | −7,16 / −6,68 / −6,16 | sí / sí / sí |

- **Referencias del evaluador** (retorno %, mismas en todas las corridas salvo la entrada aleatoria):
  - comprar y mantener: −0,52;
  - cruce de medias: −0,72;
  - volatilidad objetivo: −0,37;
  - siempre fuera: 0,00;
  - entrada aleatoria: entre −4,00 y −1,20.
- **Veredicto del evaluador:** `insufficient_evidence` en las 24 corridas.
- **Higiene de órdenes:** `bars_with_leg_and_no_stop = 0` y `exits_done_with_position_left = 0` en todas.

## 4. Lectura

- **12 de 12 corridas idénticas entre motores.** Es lo esperable: con esta estrategia y estos datos, ninguna salida es «signal reversed» (las salidas son stop protector, objetivo, trailing y break-even), así que el camino que cambia R18 (un cierre por reversión rechazado) **nunca se ejecutó**.
- La comparación de métricas, por lo tanto, **no informa** sobre R18. Su efecto se mide en las pruebas dirigidas con tolerancia 0 (`tests/unit/test_backtest_protection_window.py`) y en la simulación (E08), no en un rendimiento.
- Con 13 a 17 operaciones sobre 700 barras sintéticas, el evaluador declara evidencia insuficiente. **No se puede afirmar ventaja ni ausencia de ventaja.**
- El retorno es negativo y está por encima de las referencias pasivas, que también son negativas en estos datos. No significa nada: es una sola serie sintética.

## 5. Qué haría falta para una evaluación con sentido

- Un prerregistro nuevo, con hipótesis, métrica, umbral y datos fijados antes de mirar.
- Datos auténticos con procedencia verificada, separados en desarrollo, validación y prueba, con la prueba mirada **una sola vez**.
- Suficientes operaciones para la potencia que fije el prerregistro.
- Nada de eso se hizo aquí, ni corresponde a esta misión.
