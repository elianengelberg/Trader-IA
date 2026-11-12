# Trader-IA: motor corregido y simulación histórica real (SIM-1)

**Fecha:** 2026-10-21 · **Alcance:** trabajo aislado en el scratchpad.
- Sin commits, push ni despliegues.
- Sin dinero real; `validada_para_operar` sin tocar.
- Las entregas anteriores no se modificaron. El repositorio sigue en `72ffae5`, con el árbol limpio.

## 0. Resumen y decisión
1. **El motor de backtest tenía tres defectos reales (D1–D3) y quedaron corregidos en la plataforma.**
   - Cada uno tiene una prueba que falla con el motor original y pasa con el corregido.
   - La suite completa pasa: 1956 → 1960.
   - El motor corregido reproduce **byte a byte** las 1748 operaciones registradas por E1.
   - No tiene look-ahead (prefijo y futuro alterado), ni piernas trabadas con llenados parciales, y es determinista.
   - Criterio de suficiencia técnica: **cumplido** (`CRITERIO_SUFICIENCIA_TECNICA.md`).
2. **Simulación histórica auténtica:**
   - Datos oficiales de data.binance.vision: 228 ZIP, todos verificados contra su `.CHECKSUM`.
   - Prerregistro congelado por hash **antes** de leer un solo retorno.
   - Desarrollo: BTC 1h 2017-08→2026-05 y ETH 1h 2017-08→2022-12.
   - Prueba final fuera de muestra (**OOS**): **ETH 1h 2023-01→2026-05, leída una sola vez**, con candado.
3. **Resultado: las estrategias del bot no tienen ventaja.**
   - En OOS, la primaria (P3 `breakout`) pierde −0,52 % por operación después de costos (IC90 −0,73 / −0,30): **EN CONTRA**.
   - P1 y S1: **EN CONTRA**. P2: **NO CONCLUYENTE** (n = 66).
   - Lo mismo en todos los períodos de desarrollo, en los dos activos y en las tres condiciones de mercado.
   - **Sin costos tampoco ganan:** el bruto por operación es ≈ 0 o negativo.
   - Sus entradas no superan entradas al azar de la misma duración.
4. **La causa es económica, no técnica.**
   - Las reglas de entrada a 1 h no anticipan el precio; el costo de ≈ 0,23 % por round trip convierte ese cero en una pérdida segura.
   - La mejora candidata M1 (filtrar por confianza alta) **no se promovió**: gana en BTC, donde nació la idea, y pierde −0,50 % en ETH.
5. **Decisión:**
   - Trader-IA queda **técnicamente apto para simular** con su motor corregido.
   - Sus estrategias actuales **no están validadas para operar**, ni deben estarlo.
   - No se recomienda capital, ni papel, ni más ajustes de estas reglas sobre BTC o ETH: ya no queda historia limpia para probarlos.

## 1. Defectos corregidos (técnicos)
| Defecto | Qué pasaba | Corrección (`tia/backtest/engine.py`) | Prueba |
|---|---|---|---|
| **D1** | Tras un rechazo o una cancelación, la salida o el stop reintentados reutilizaban el `client_order_id` y se suprimían como duplicados. La posición quedaba sin stop o no cerraba | Un id por barra para la salida y un id por colocación para el stop, como en `tia.runtime.live` | `test_stops_and_exits_survive_rejections`: en el original, 9 o más barras sin stop |
| **D2** | El stop se reemplazaba solo si cambiaba la cantidad. El break-even y el trailing movían el stop de la pierna, pero no la orden en el libro | Se compara también el nivel (`same_level`, como en la sesión en vivo) | `test_the_stop_in_the_book_follows_the_leg`: en el original, el stop del libro quedaba a otro nivel |
| **D3** | El resto de una entrada parcial seguía activo al cerrar. Se llenaba durante el cierre, el cierre cubría solo el tamaño viejo y la pierna esperaba para siempre una salida ya terminada (en E1 aparecía como round trips de más de 2000 barras) | Se cancela el resto al pedir la salida y en plano. Como red de seguridad, una salida terminada con posición restante libera la pierna | `test_partial_fills_leave_no_untracked_or_stuck_position`: en el original, «still held, waiting on a close that is filled» |
| Falla segura | Una pierna sin nivel de stop no se informaba | Contador `bars_with_leg_and_no_stop` y advertencia en `BacktestResult.warnings`, que hace falso `is_reliable()` | `test_a_leg_without_a_stop_level_is_reported` |

- `paper.py` solo agrega `resting_orders()`, de lectura. El parche completo tiene 76 líneas: `parche/parche_motor_D1_D3.diff`.
- **Evidencia:** `evidencia/S1b_*` (antes y después), `S0_linea_base_HEAD.txt` frente a `S1_suite_corregida.txt`, ruff limpio y mypy sin errores nuevos.
- **Paridad:** `S2_paridad_e1_principales.json`: P1 629, P2 139, P3 185, S1 795, todas idénticas.
- **Verificación sintética:** `S2_verificacion_sintetica_motor_corregido.json`: V1, V2, V3, V6 y DET, todas bien.

## 2. Datos
| | ETHUSDT 1h | BTCUSDT 1h |
|---|---|---|
| Archivos | 106 mensuales (nuevos) | 26 mensuales nuevos (2017-08→2019-09) + 80 mensuales y 16 diarios de E1 |
| Primera / última vela | 2017-08-17 04:00 / 2026-05-31 23:00 UTC | ídem |
| Velas / esperadas / faltantes | 76 909 / 77 036 / 127 (28 huecos, máx. 32 h) | 76 906 / 77 036 / 130 (30 huecos, máx. 32 h) |
| OHLC incoherentes; precios ≤ 0 | 0; 0 | 0; 0 |
| Conflictos excluidos | 0 | 3 (los conocidos de E1) |

- **Procedencia:**
  - `registro/descarga_vision.tsv`: URL, código HTTP 200, bytes y hora de cada uno de los 264 archivos;
  - `registro/verificacion_checksum.txt`: 132/132;
  - `reproduccion/SHA256_zips_usados.txt`: los 228 ZIP exactos.
- **Tratamiento:** el de E1. Sin relleno; un conflicto se trata como faltante; todo en UTC.
- **No se usaron:**
  - SOL ni otras altcoins, reservadas para E3-H1;
  - nada desde 2026-06-01, el período de H-CARRY.
- **Incidente 01** (`registro/INCIDENTE_01_endpoint_restringido.txt`):
  - Para obtener los filtros de ETHUSDT consulté por error `data-api.binance.vision`, contra la decisión documentada en E3 de no eludir el bloqueo geográfico de la API.
  - Borré la respuesta sin leerla. Los filtros se infirieron de los propios datos o se declararon como supuestos (efecto < 0,04 %).

## 3. Diseño (prerregistro `prerregistro/PRERREGISTRO_SIM1.md`)
- **Huellas:** fijadas a las 20:41:41Z, antes de leer retornos. La Adenda 1 (21:59:47Z) fija los resultados de desarrollo, sin cambios de código, antes de OOS.
- **Estrategia primaria: P3 `breakout`, solo largos.** Por qué:
  - era la única con bruto ≥ 0 en E1;
  - era la menos negativa;
  - su confianza mostraba un orden exploratorio.

  Las secundarias son P1, P2 y S1. Las reglas son las del bot (v1.1.0), sin cambios.
- **Entrada:** señal con confianza ≥ 0,55; orden de mercado a la apertura siguiente.
- **Salida:** stop protector inicial; break-even tras 1R; trailing de 2 ATR; objetivo; reversión de señal.
- **Tamaño:** el presupuesto de riesgo del bot (perfil conservador); en la práctica, ≈ 0,7–1,8 % del capital por posición.
- **Exposición:** una pierna por activo, sin apalancamiento ni cortos.
- **Costos:** 10 bps por lado, más 2 bps de deslizamiento base, más rango e impacto; stops al peor precio.
- **Sensibilidades:** comisión ×2, +1 vela de latencia, sin costos, gobernadores en vivo.
- **Referencias:**
  - comprar y mantener, efectivo, cruce de medias 20/50, volatilidad objetivo del 15 %;
  - nulo de entrada aleatoria emparejada (2000 réplicas).
- **Incertidumbre:** bootstrap por bloques de mes (B = 10 000), p unilateral, Holm entre las secundarias.
- **Selección:** la única mejora permitida, M1, se decidía con una regla fija y solo con desarrollo. Ningún umbral se eligió mirando OOS.

## 4. Desarrollo: qué mostró y qué se hizo con eso
Detalle completo en `resultados/dev/tablas_dev.md` y `DIAGNOSTICO_DEV.md`; este último se escribió antes de correr OOS, con la predicción de su resultado.

| Media neta / op. [IC90] | BTC 2017-08→2026-05 | ETH 2017-08→2022-12 |
|---|---|---|
| P3 | −0,29 % [−0,49; −0,09], n = 227 | −0,68 % [−0,95; −0,42], n = 165 |
| P1 | −0,22 % [−0,34; −0,11], n = 807 | −0,30 % [−0,46; −0,15], n = 496 |
| P2 | −0,53 % [−0,72; −0,33], n = 172 | −0,31 % [−0,74; +0,13], n = 100 |
| S1 | −0,29 % [−0,38; −0,19], n = 1018 | −0,26 % [−0,42; −0,12], n = 615 |

- **BTC 2017-08 → 2019-09, nunca usado:** también negativo en las cuatro configuraciones. E1 se replica hacia atrás.
- **Validez:** prefijo real idéntico, determinismo idéntico, 0 piernas sin stop, máximo de 44 barras por round trip. **No apareció ningún defecto técnico**, así que no se cambió código.
- **M1 no promovida:** BTC +0,20 % (n = 88), ETH −0,50 % (n = 65), IC90 combinado −0,33 / +0,14. La ordenación por confianza de BTC no sobrevive en otro activo.

## 5. Prueba final OOS-ETH (2023-01-01 → 2026-05-31; una sola lectura)
Validez: sin problemas. Detalle completo en `resultados/final/tablas_oos.md`.

**Por operación** (neto, % del nocional):

| | n | Media neta [IC90] | p | Bruto (sin costos) | Comisión ×2 | +1 vela | Acierto | Ganancia / pérdida media | p_nulo | Veredicto |
|---|---|---|---|---|---|---|---|---|---|---|
| **P3** | 120 | **−0,517 [−0,725; −0,297]** | 1,00 | −0,288 | −0,711 | −0,450 | 26 % | +1,79 / −1,32 | 0,97 | **EN CONTRA** |
| P1 | 359 | −0,339 [−0,478; −0,216] | 1,00 | −0,102 | −0,531 | −0,378 | 29 % | +1,84 / −1,23 | 0,81 | EN CONTRA |
| P2 | 66 | −0,180 [−0,554; +0,205] | 0,78 | +0,037 | −0,382 | −0,001 | 32 % | +1,89 / −1,15 | 0,28 | NO CONCLUYENTE |
| S1 | 441 | −0,335 [−0,454; −0,225] | 1,00 | −0,111 | −0,530 | −0,333 | 29 % | +1,83 / −1,23 | 0,79 | EN CONTRA |

**Capital** (cuenta simulada de 100 000 USDT desde el 2023-01-01):

| | Capital final | Retorno neto | Anual | Volatilidad | Sharpe [IC90] | Máx. caída | Exposición | Comisiones |
|---|---|---|---|---|---|---|---|---|
| **P3** | 99 565,85 | −0,43 % | −0,13 % | 0,08 % | −1,59 [−2,32; −0,88] | 0,44 % | 2,0 % | 176 USDT |
| P1 | 99 303,58 | −0,70 % | −0,20 % | 0,13 % | −1,52 [−2,42; −0,81] | 0,70 % | 8,6 % | 517 USDT |
| P2 | 99 806,00 | −0,19 % | −0,06 % | 0,13 % | −0,43 [−1,30; +0,48] | 0,28 % | 1,6 % | 241 USDT |
| S1 | 98 796,80 | −1,20 % | −0,35 % | 0,17 % | −2,04 [−2,64; −1,51] | 1,20 % | 10,3 % | 758 USDT |
| Comprar y mantener ETH | — | +67,9 % | +16,4 % | 61,6 % | 0,55 | 65,3 % | 100 % | — |
| Cruce de medias 20/50 | — | −32,5 % | −10,9 % | 41,2 % | −0,07 | 68,1 % | 51 % | — |
| Volatilidad objetivo 15 % | — | −2,2 % | −0,7 % | 17,2 % | 0,05 | 26,5 % | 100 % | — |

**Límites del Sharpe:**
- Con posiciones de ≈ 1 % del capital, la cuenta es casi todo efectivo. Su Sharpe y su caída miden poco de la regla; la medida que importa es la media neta por operación.
- El Sharpe de la cuenta se calcula sobre retornos diarios minúsculos. No se compara con el de comprar y mantener: el riesgo asumido es dos órdenes de magnitud menor.

**Por período** (n · media neta %):

| | 2023 | 2024 | 2025-01→2026-05 |
|---|---|---|---|
| P3 | 39 · −0,46 | 41 · −0,52 | 40 · −0,58 |
| P1 | 113 · −0,39 | 104 · −0,34 | 142 · −0,30 |
| P2 | 22 · −0,10 | 17 · +0,35 | 27 · −0,58 |
| S1 | 141 · −0,43 | 124 · −0,23 | 176 · −0,33 |

**Por condición de mercado** (retorno de 30 días antes de la entrada; n · media neta %):

| | Alcista > +10 % | Lateral | Bajista < −10 % |
|---|---|---|---|
| P3 | 43 · −0,53 | 56 · −0,41 | 21 · −0,78 |
| P1 | 140 · −0,40 | 166 · −0,19 | 39 · −0,67 |
| S1 | 161 · −0,36 | 197 · −0,24 | 69 · −0,52 |

**Costos:**
- El costo implícito es 0,22–0,24 % por round trip: 0,20 % de comisión y ≈ 0,02–0,04 % de deslizamiento.
- Duplicar la comisión resta ≈ 0,19 %.
- Ni con costo cero alguna configuración tiene un bruto claramente positivo. P2 llega a +0,04 % con n = 66; es ruido.

## 6. Por qué fracasa (causa)
- **Sin ventaja de entrada.** Una entrada al azar con las mismas duraciones rinde lo mismo o algo mejor (p_nulo de 0,28 a 0,97). P3 es peor que el azar en ETH, tanto en desarrollo como en OOS.
- **Estructura de salida.** Las tenencias son cortas (5–7 barras) con trailing de 2 ATR:
  - el 75 % de las salidas de P3 son por trailing, con una media de −1,2 %;
  - las que llegan al objetivo dan +2,3 %;
  - la tasa de acierto es del 26–32 %.
  - Con una relación ganancia/pérdida de ≈ 1,4, hace falta un acierto del 42 % para empatar. **Sin señal, esa estructura más el costo garantizan la pérdida.**
- **No es infraestructura.** El motor reproduce E1, no mira el futuro, no traba piernas y es determinista. Corregir D1–D3 cambió la mecánica de las órdenes, pero no puede crear una ventaja que las reglas no tienen.
- **Consistencia.** El signo es negativo en BTC 2017–2026, ETH 2017–2022 y ETH 2023–2026; en las tres condiciones de mercado; y en cada año de OOS (salvo P2 en 2024, con n = 17). Es una conclusión robusta, no un accidente de período.

## 7. Qué funciona, qué falla y qué no se puede concluir
**Funciona:**
- motor y simulación de órdenes, con D1–D3 corregidos;
- reproducibilidad: huellas idénticas entre procesos y paridad con E1;
- separación de períodos y candado de una sola lectura;
- datos con procedencia verificable;
- falla segura: advertencias y detención si la validez falla.

**Falla:**
- las cuatro configuraciones del bot como fuente de ganancia: P1, P3 y S1 **EN CONTRA** con datos nuevos;
- la idea de filtrar breakout por confianza (M1): no se traslada a ETH.

**No se puede concluir:**
- P2 (reversión) en ETH OOS: n = 66, IC que cruza 0. El punto es negativo y la ruta de desarrollo también; nada sugiere ventaja.
- Su variante con +1 vela es ≈ 0 en ETH (desarrollo −0,05 %, OOS −0,00 %) y en BTC (E1, −0,18 %). Es una observación repetida que **no** es una ventaja después de costos.
- El comportamiento en vivo con libro real: la simulación modela el diferencial y el impacto, pero no colas ni microestructura.

## 8. Mejoras futuras justificadas, en orden
1. **Integrar el parche D1–D3 al repositorio**, con su prueba (`parche/`). Corrige defectos reales del motor que usan todos los backtests. Requiere tu autorización para hacer commit.
2. **No invertir más en ajustar estas cuatro estrategias a 1 h sobre BTC o ETH.**
   - La historia de 1 h de ambos activos (2017-08 → 2026-05) ya está usada: cualquier ajuste nuevo sería sobreajuste.
   - Una regla nueva solo podría validarse de forma prospectiva o con otros activos, que hoy están reservados para E3-H1.
3. **Si alguna vez se rediseñan:** el cuello de botella es la falta de señal de entrada, no la salida ni el costo. Una nueva regla tendría que mostrar primero un bruto > 0,25 % por operación frente al nulo aleatorio, con un prerregistro propio.
4. **Opcional y bajo:** el motor tarda ≈ 8 min por 57 000 velas. Perfilarlo aceleraría la investigación, pero no cambia ninguna conclusión. No lo hice: sería perfeccionismo.
5. Las prioridades del programa siguen como en la hoja de ruta del 2026-10-21:
   - desbloquear **E3-H1**, que necesita la fuente de exclusiones que decidas;
   - mantener **T-papel** sin cambios.

## 9. Decisiones que te corresponden (con mi recomendación)
| Decisión | Recomendación | Consecuencia |
|---|---|---|
| Commit del parche D1–D3 y su prueba al repositorio | **Sí**, en una rama, con revisión | Todos los backtests futuros usan el motor corregido. Hoy el repositorio sigue con D1–D3 |
| Estrategias 1 h del bot (P1, P2, P3, S1) | **Archivarlas como EN CONTRA o NO CONCLUYENTE**; sin papel ni capital | Se cierra una línea con evidencia en 3 conjuntos independientes |
| D-G1 sobre H-E1-BC | **No iniciar** (se refuerza) | Su pata ETH quedó usada y fue negativa (M1 −0,50 %; ρ +0,12 en desarrollo y +0,07 en OOS). Solo quedaría SOL, que está reservada |
| `validada_para_operar` | **Sin cambios (falso)** | — |

## 10. Reproducción
- **Paquete:** `entrega_SIM1_2026-10-21.zip`, con `SHA256SUMS`.
- **Comando:** `bash reproduccion/REPRODUCIR.sh <clon de Trader-IA> <dir nuevo> [rapido]`. Hace lo siguiente:
  - aplica el parche sobre `72ffae5`;
  - crea el entorno con los hashes de E1;
  - descarga los 228 ZIP y los verifica dos veces;
  - corre las pruebas y la verificación sintética;
  - con el modo completo, corre además DEV y OOS y compara las operaciones.
- El paquete **no incluye datos crudos de terceros**: se descargan de la fuente oficial y se verifican contra los hashes registrados.
- Lo verificado desde una extracción limpia del ZIP está en `VERIFICACION_EXTRACCION_LIMPIA.txt`, **junto al ZIP**: se generó después de armarlo y contiene su SHA-256.
