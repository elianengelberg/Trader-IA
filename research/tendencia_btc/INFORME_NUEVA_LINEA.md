# Nueva línea de Trader-IA: búsqueda de una estrategia distinta del carry (2026-10-17)

**Resultado: ninguna candidata supera las puertas fijadas de antemano en desarrollo.**
- La mejor, la tendencia long/flat en BTC (T), muestra un valor de timing positivo pero **no significativo**: +14 %/año neto frente a la exposición estática equivalente, con P = 0,84 y un IC90 de −8 % a +37 %.
- Es frágil a costes y retrasos. **No avanza** a validación ni a test.
- **Esas ventanas (2022-01 → 2026-05) no se usaron** para esta línea y siguen disponibles.

**Categoría de todo lo de aquí:** histórico verificado (data.binance.vision, checksums), **solo desarrollo** (2017-08-17 → 2021-12-31). Nada prospectivo ni real.

## 1. Datos
- Velas **diarias** oficiales de spot de BTCUSDT y ETHUSDT: 106 + 106 archivos mensuales verificados contra su `.CHECKSUM`; 3 210 días cada uno.
- Sin días ausentes, repetidos, velas irregulares, OHLC incoherente ni precios ≤ 0 (`experimentos/calidad_datos.json`).
- **Contraste independiente:** en 2 435 días, la apertura y el cierre diarios coinciden **exactamente** con las velas horarias del pipeline de H-CARRY (archivos distintos).
- Manifiestos: BTC `datos/BTCUSDT/MANIFIESTO.json` y ETH `datos/ETHUSDT/MANIFIESTO.json`.
- Período reservado (2026-06 en adelante): no se descargó; el código lo impide.

## 2. Familias consideradas y selección (`FAMILIAS_ESTRATEGIA.md`, escrito antes de calcular)

| Familia | Decisión | Por qué |
|---|---|---|
| Tendencia long/flat (momentum de serie temporal) | Candidata principal a priori | Hipótesis económica (difusión lenta, manada), literatura, baja rotación esperada, falsable |
| Momentum con filtros; ruptura | No probadas | Variantes de la anterior: probarlas tras un fallo sería reciclarlo |
| Reversión a la media | Sin base | Autocorrelación diaria de retardo 1 = −0,06 (la regla exigía < −0,10) y ~30 bps de coste por ida y vuelta |
| Volatilidad gestionada | Probada; no pasa | Persistencia de la volatilidad de 30 días = 0,32 (< 0,5). Con la regla completa, Sharpe 0,92 frente a 0,96 de buy and hold (P = 0,38) |
| Corte transversal entre criptos | Excluida | Sin universo histórico verificable sin supervivientes |
| Estacionalidad | Excluida | Sin hipótesis económica sólida; riesgo de minería de datos |

**Secuencia de puertas** (cada regla, escrita antes de su cálculo):
1. **Cribado de familias:** BTC «sin base» (momentum positivo en 1 de 3 ventanas, t ≤ 0,40). Potencia baja: 47 observaciones.
2. **Regla completa en desarrollo** (desviación declarada para medir esa potencia): T, P = 0,842 < 0,90 → **no pasa**; V, P = 0,38 → **no pasa**.
3. **¿Señal o rotación?** T bruto, P = 0,885 < 0,90 → **no pasa** → cierre, sin la revisión T2.

**Selección múltiple:** en desarrollo se evaluaron 2 familias con 3 pruebas de regla (T neto, T bruto y V), más el cribado. No se ajustó ningún parámetro.

## 3. Implementación (`src/tendencia/`; 6 pruebas en `tests/`)
- **`datos.py`:** descarga verificada, reutilizando `hcarry.data.binance_vision` sin modificarlo. Lee las velas con su formato real: cierre −1 ms, o −1 µs en el spot desde 2025. Reporta la calidad y bloquea el período reservado.
- **`senal.py`:**
  - T: fracción de las ventanas {30, 90, 180} con rentabilidad pasada positiva (0, ⅓, ⅔, 1);
  - V: min(1; 0,50 / σ̂ de 30 días).
  - Ambas usan solo cierres ≤ d.
- **`backtest.py`:** long/flat en spot. Decide con el cierre de d y ejecuta en la apertura oficial de d + 1 (+ retraso). El coste es |valor negociado| × (10 + 5 bps). Efectivo al 0 %, sin apalancamiento ni cortos.
- **`metricas.py`, `estadistica.py`:** CAGR, volatilidad, Sharpe, Sortino, caída y su duración, rotación y desglose por año. Bootstrap por bloques (reutilizado de H-CARRY), bootstrap de la diferencia de Sharpe y nulo por desplazamiento circular.
- **Pruebas:** sin look-ahead en señales ni backtest; coste exacto de ida y vuelta; buy and hold; estática; casos límite de las señales; métricas; lectura oficial en µs y velas irregulares; bloqueo del período reservado.

## 4. Resultados históricos netos (desarrollo 2018-02-14 → 2021-12-31, BTCUSDT; costes base)

| | CAGR | Vol. | Sharpe | Caída máx. | Exposición | Operaciones | Costes |
|---|---|---|---|---|---|---|---|
| **T tendencia** | 53,4 % | 49 % | 1,12 | 50,2 % | 0,56 | 178 | 5,37 pp/año |
| V volatilidad | 41,5 % | 54 % | 0,92 | 58,6 % | 0,76 | 75 | 0,69 pp/año |
| Buy and hold | **54,5 %** | 75 % | 0,96 | 72,2 % | 1,00 | 1 | 0,04 |
| Estática con la exposición de T | 37,2 % | 42 % | 0,96 | 49,0 % | 0,56 | — | 0 |
| Efectivo (USDT al 0 %) | 0 % | 0 | — | 0 | 0 | 0 | 0 |

- **Por año, T frente a buy and hold:** 2018 −28 % / −57 %; 2019 +75 % / +95 %; 2020 +177 % / +303 %; 2021 +52 % / +60 %. T reduce las pérdidas en los años malos y se queda atrás en los buenos.
- **Por régimen ex ante** (rentabilidad de 90 días; media anualizada, T / buy and hold): alcista 121 % / 144 %; lateral 15 % / 26 %; bajista −13 % / +2 %.
- **Lectura:** el mejor Sharpe y la menor caída de T vienen sobre todo de su **menor exposición media** (0,56). La estática con la misma exposición tiene una caída parecida (49 %). Lo que T añade con el timing (+14 %/año) no es estadísticamente distinguible del azar.

## 5. Sensibilidad y estrés de T (descriptivo, solo desarrollo; `experimentos/sensibilidad_desarrollo.json`)

| Escenario | Exceso frente a la estática | P | CAGR |
|---|---|---|---|
| Base | +14,2 % | 0,84 | 53,4 % |
| Costes ×0,5 | +15,3 % | 0,86 | 55,2 % |
| Costes ×2 | +11,9 % | 0,79 | 49,9 % |
| Costes ×3 | +9,6 % | 0,75 | 46,6 % |
| Slippage de 25 bps | +11,1 % | 0,78 | 48,8 % |
| Retraso de 1 día | +11,3 % | 0,79 | 49,3 % |
| Retraso de 3 días | **+4,9 %** | 0,62 | 39,7 % |
| Sin costes (bruto) | +16,5 % | 0,885 | 56,9 % |

**Estrés:** los 10 peores días de buy and hold.
- El 2020-03-12: buy and hold −39,6 %; T −12,3 %, con exposición parcial.
- El 2018-11-19: T 0 %, fuera del mercado.
- Pero los días 2019-06-27, 2021-01-21 y 2019-07-16, T estaba plenamente expuesto y **perdió lo mismo**.
- Ejecutar en la apertura siguiente no evita el primer día de un crash.

**ETH (misma regla, solo descriptivo):** exceso de +24,6 %, P = 0,89; CAGR 68,7 % frente a 46,2 %; caída 64 % frente a 92 %. El mismo patrón limítrofe.

## 6. ¿Avanza, se revisa o se descarta?
- **V (volatilidad gestionada): se descarta.** Sin persistencia suficiente y sin mejora del Sharpe.
- **T (tendencia long/flat): no avanza con esta especificación.**
  - La razón concreta es la **potencia estadística**: 3,9 años de desarrollo con un efecto ruidoso; el IC90 abarca de −8 % a +37 %.
  - A eso se suma la **fragilidad**: 46 operaciones al año, y con 3 días de retraso queda en +4,9 %.
  - **No se rediseña con los mismos datos.** Solo tiene sentido reexaminarla, **sin cambiar la regla**, con datos nuevos e independientes (§7).
- **Mensaje honesto para la decisión:** ninguna de las estrategias evaluadas en H-CARRY ni en esta línea tiene, hoy, evidencia suficiente de ventaja neta sobre alternativas simples.
  - Buy and hold superó a T en CAGR.
  - La reducción de la caída se obtiene igual con menos exposición estática.

## 7. Siguiente paso concreto (propuesto, no ejecutado)

**Experimento T-IND: la misma regla T, sin cambios, con más datos independientes.**
1. **Desarrollo ampliado:** BTC/USD diario de 2013 a 2017, de la API pública oficial de otro exchange (por ejemplo, Bitstamp).
   - Categoría «histórico con procedencia limitada»: es oficial del exchange, pero sin checksums.
   - Criterio fijado de antemano: P ≥ 0,90 y nulo ≥ 0,90 en el desarrollo combinado (2013–2021).
2. **Si pasa:** prerregistrar validación (2022–23) y test (2024-01 → 2026-05). Esas ventanas no se usaron para la tendencia. Test de uso único, con cerrojo.
3. **Advertencias:**
   - 2013–2017 es otro mercado (menos líquido, era de Mt. Gox);
   - el diseñador conoce sus grandes tendencias, así que un resultado positivo convencería poco y uno negativo, mucho.
4. **Alternativa más limpia y lenta:** evaluación prospectiva en papel de T, sin cambios, durante 12 a 24 meses, con criterios prerregistrados.

Ambas opciones requieren tu decisión: la primera usa datos fuera de data.binance.vision; la segunda, tiempo.

## 8. Reproducir
```
cd research/tendencia_btc
export PYTHONPATH=src:../hcarry_next/src; PY=../hcarry_next/.venv/bin/python
$PY -B -m pytest -q                                              # 6 pruebas
$PY -B -c "from pathlib import Path; from tendencia.datos import descargar_1d as d; [d(Path(f'datos/{s}'), s) for s in ('BTCUSDT','ETHUSDT')]"
$PY -B experimentos/evidencia_inicial_desarrollo.py              # cribado de la familia 1
$PY -B experimentos/evidencia_volatilidad_desarrollo.py          # cribado de la familia 5
$PY -B experimentos/diagnostico_reglas_desarrollo.py             # reglas completas en desarrollo (≈ 6 s)
$PY -B experimentos/puerta_senal_vs_rotacion.py                  # puerta señal / rotación
$PY -B experimentos/sensibilidad_desarrollo.py                   # sensibilidad y estrés (descriptivo)
```
Una descarga nueva tiene otra fecha en el manifiesto. Para verificar que los datos son los mismos, compará los `sha256` de cada archivo; los hashes de los artefactos están en `ARTEFACTOS_SHA256.txt`.
