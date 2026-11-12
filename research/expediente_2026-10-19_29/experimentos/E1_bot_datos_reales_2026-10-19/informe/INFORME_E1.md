# E1: las estrategias del bot con datos reales. Informe (2026-10-19)

**Veredicto prerregistrado:** las tres estrategias dan **EVIDENCIA EN CONTRA de una ventaja neta**.
- `trend_following`, `mean_reversion` y `breakout` pierden en promedio por operación después de costos, con el IC90 entero por debajo de 0.
- Su timing no se distingue de una entrada aleatoria con la misma frecuencia, la misma exposición y las mismas duraciones.
- La fusión (el bot tal como opera) da lo mismo.

Convenciones: **[H]** hecho reproducible · **[I]** inferencia · **[N]** hipótesis no probada · **[L]** limitación.

## 1. Pregunta
¿Alguna de las 3 estrategias, sin cambios y en long/flat (lo que spot permite), tiene en BTCUSDT a 1 h:
- una expectativa neta positiva por operación después de costos,
- y un timing mejor que una entrada aleatoria emparejada?

## 2. Evidencia y procedencia
- **[H] Datos:**
  - velas oficiales de 1 h de BTCUSDT spot (data.binance.vision) del 2019-10-01 al 2026-05-31 UTC: 96 archivos, cada uno verificado contra su `.CHECKSUM`;
  - huella de la lista: `4931ee70…a7ba9`;
  - 58 402 velas, sin relleno; faltan 38 de 58 440, en 19 huecos de como mucho 5 h. Incluyen 3 horas en las que el archivo mensual y el diario difieren, tratadas como faltantes (adenda 1).
- **[H] Código del bot:** `tia` en HEAD `692f2b2`, sin cambios: `library.py` `a1b8844…`, `engine.py` `5471094…`.
- **[H] Entorno aislado:** Python 3.11.17, pydantic 2.13.5, pydantic-settings 2.15.0, numpy 2.4.6 y structlog 26.1.0. Las ruedas se verificaron contra el SHA-256 de PyPI y se instalaron con `--require-hashes`, con versiones de al menos dos semanas.
- **[H] Prerregistro:** escrito y con hash fijado antes de evaluar datos reales, con dos adendas también previas a cualquier resultado (`prerregistro/`).

## 3. Reglas e instrumento
- **[H] Reglas:** las estrategias tal como están codificadas (v1.1.0):
  - **trend:** EMA 12/26/50, ADX ≥ 22 y DI a favor; stop a 2 ATR y objetivo a 3 ATR;
  - **mean reversion:** RSI ≤ 30, %B ≤ 0,05, z < −1 y ADX ≤ 25; stop a 1,5 ATR y objetivo en la media de Bollinger;
  - **breakout:** Donchian de 20 barras con volumen ≥ 1,3×; stop a 2 ATR y objetivo a 3 ATR.
  - Además: filtro de régimen, confianza mínima de 0,55, break-even a 1R, trailing a 2 ATR y el tamaño de posición del perfil «conservative».
  - Una señal SHORT significa no operar.
- **[H] El backtester del repositorio tenía 3 defectos mecánicos**, ausentes de la sesión en vivo, que impedían representar las salidas del bot. Se corrigieron en una subclase aislada (`MotorE1`) copiando la lógica de `tia.runtime.live`:
  - **D1:** un stop o una salida rechazados quedaban suprimidos como duplicados para siempre.
  - **D2:** el break-even y el trailing no movían el stop activo.
  - **D3:** el resto de una entrada parcial, llenado junto con la salida, dejaba la posición trabada.
  - **Cuánto pesan:** con el motor original, P1 hace **24** operaciones; con el corregido, **629**. El original deja de operar tras el primer atasco.
- **[H] Verificación previa, con datos sintéticos:**
  - sin look-ahead (invariancia de prefijo y perturbación del futuro);
  - réplica independiente de 300/300 decisiones por estrategia;
  - ninguna posición pasa más de 1 barra seguida sin stop;
  - 0 piernas huérfanas con llenados parciales al 90 %.
  - **Con datos reales:** invariancia de prefijo superada, 0 cortos y 0 piernas huérfanas.
- **[H] Costos:**
  - 10 bps de comisión por lado;
  - deslizamiento del simulador: 2 bps base, más el 5 % del rango de la barra (≈ 4,2 bps por lado de media) y el impacto.
  - En total, ≈ **0,33 % por ida y vuelta**, del cual el 0,20 % son comisiones.
  - Las órdenes a mercado se ejecutan en la apertura siguiente y los stops, al peor precio entre el stop y la apertura.

## 4. Referencias (mismas barras, 2019-10 → 2026-05)
| Serie | Rentabilidad total | Anualizada | Caída máx. | Sharpe | Exposición |
|---|---|---|---|---|---|
| Buy and hold | +797 % | +39,0 % | 77,2 % | 0,84 | 100 % |
| Efectivo | 0 % | 0 % | 0 % | — | 0 % |
| Cruce de medias 20/50, long/flat | +4,1 % | +0,6 % | 69,8 % | 0,22 | 52,5 % |
| Volatilidad objetivo 15 % | +33,4 % | +4,4 % | 34,9 % | 0,34 | 99,9 % |
| P1 trend (bot, solo largos) | −1,2 % | −0,18 % | 1,4 % | −1,03 | 8,4 % |
| S1 fusión (bot) | −2,2 % | −0,33 % | 2,4 % | −1,70 | 10,1 % |

- **[I]** Las curvas del bot son casi planas porque su tamaño de posición es **≈ 1 % del capital** por operación: perfil «conservative» con volatilidad objetivo del 10 % y convicción mínima.
- La comparación de la curva con buy and hold mide sobre todo la exposición. **La métrica que decide es el retorno neto por operación.**

## 5. Resultados netos y riesgo
| Config. | Operaciones | Media neta/op. | IC90 (bootstrap mensual) | IC90 (trimestral) | Acierto | Media bruta/op.¹ | Nulo aleatorio: media | p_nulo | Veredicto |
|---|---|---|---|---|---|---|---|---|---|
| **P1 trend** | 629 | **−0,237 %** | −0,341 / −0,135 | −0,356 / −0,119 | 33 % | −0,037 % | −0,245 % | 0,45 | **en contra** |
| **P2 mean rev.** | 139 | **−0,519 %** | −0,724 / −0,310 | −0,698 / −0,334 | 17 % | −0,319 % | −0,303 % | 0,94 | **en contra** |
| **P3 breakout** | 185 | **−0,198 %** | −0,381 / −0,017 | −0,411 / −0,001 | 34 % | +0,002 % | −0,254 % | 0,32 | **en contra** (al límite) |
| S1 fusión | 795 | −0,294 % | −0,384 / −0,209 | −0,384 / −0,199 | 30 % | −0,094 % | −0,255 % | 0,75 | secundaria |

¹ Después del deslizamiento simulado y antes de comisiones.

- **[H] Holm:** ningún p_signo ni p_nulo pasa. Los p_signo son 0,96, 1,00 y 1,00.
- **[H] Distribución de P1:**
  - cuantiles 5/25/50/75/95: −2,44 / −1,24 / −0,66 / +0,51 / +2,97 %;
  - ganancia media +1,65 % y pérdida media −1,17 %, cuando con un 33 % de aciertos haría falta una relación mayor de 2,0;
  - factor de beneficio 0,70; peor racha de 13 pérdidas;
  - tenencia media de 7,8 h, unas 94 operaciones por año.
- **[H] Salidas de P1:**
  - 147 por objetivo (+2,15 % de media);
  - 454 por trailing (−0,96 %);
  - 12 por el stop protector (−2,40 %).

## 6. Robustez
| Media neta/op. | Base | Comisión ×2 | +1 barra de retraso | Costos mínimos² | Gobernadores en vivo |
|---|---|---|---|---|---|
| P1 | −0,237 % | −0,421 % | −0,221 % | +0,007 % | −0,237 % (idéntico) |
| P2 | −0,519 % | −0,716 % | −0,183 % | −0,309 % | idéntico |
| P3 | −0,198 % | −0,436 % | −0,306 % | +0,046 % | idéntico |
| S1 | −0,294 % | −0,488 % | −0,157 % | −0,054 % | idéntico |

² Comisión 0, deslizamiento base 0 e impacto 0. Queda solo el componente de rango, ≈ 4 bps por lado.

- **[H] Subperíodos y regímenes:** la media es negativa en los 3 subperíodos (2019-10→2021, 2022, 2023→2026-05) y en los 3 regímenes ex ante (alcista, lateral, bajista), en las cuatro configuraciones.
- **[H] Gobernadores:** nunca se activaron. Con tamaños de ≈ 1 % del capital la caída máxima no pasa del 2,4 %, así que su neutralización no cambió nada.

## 7. Hallazgos previos, contrastados
- **El short perjudica.** [H] Confirmado en parte. Con cortos hipotéticos (S5, sin costo de préstamo), las operaciones cortas rinden **peor** que las largas:
  - P1: −0,30 % frente a −0,23 %;
  - P3: −0,60 % frente a −0,20 %;
  - fusión: −0,41 % frente a −0,28 %.
  - Pero las largas también pierden: quitar los cortos no crea una ventaja.
- **La reversión a la media no tiene ventaja.** [H] Confirmado a 1 h con datos reales: −0,52 % por operación, peor que el azar (p_nulo 0,94).
- **El score de confianza no está calibrado.** [H] Confirmado en trend, mean reversion y la fusión: Spearman de −0,02, −0,08 y −0,02, con IC que incluyen 0, y bandas sin orden.
  - **[N] La excepción es breakout:** Spearman +0,22 (IC90 0,11 / 0,32). La banda 0,55–0,65 rinde −0,67 % y la de 0,65 o más rinde ≈ +0,1 %.
  - Es un hallazgo **posterior**: uno de 4 análisis secundarios sin ajustar. Con 4 miradas, la probabilidad de un falso positivo así ronda el 30 %.

## 8. Riesgos de sesgo y el argumento más fuerte en contra
- **[L] Alcance:**
  - un solo activo y un solo período;
  - 1 h, mientras que el bot opera a 1 m;
  - sin la marea HTF, el filtro de spread ni la exploración de la sesión en vivo;
  - el modelo de deslizamiento es conservador para órdenes chicas.
- **[L] Correcciones del instrumento:**
  - el motor se corrigió en tres puntos; D3 apareció durante la segunda ejecución real;
  - **historia completa:** se hicieron 3 ejecuciones reales. La 1.ª se detuvo por velas en conflicto; la 2.ª, por la validez (D3), y de ella solo se miraron cantidades, duraciones y contadores, ningún retorno. Las dos están documentadas en las adendas 1 y 2.
- **Argumento más fuerte en contra:** «Con costos de maker (0–2 bps y sin deslizamiento), P1 y P3 quedarían ≈ +0,1 % por operación».
  - **Respuesta [I]:**
    - Ese bruto (≈ +0,09 % en P1) es el mismo que obtiene el **nulo aleatorio** antes de costos (≈ +0,08 %). Es la deriva alcista de BTC durante unas 8 h de tenencia, no un timing.
    - Buy and hold captura esa deriva sin rotación y sin costos de entrada y salida.
    - Y a 1 m, la relación entre costo y movimiento es peor que a 1 h.
- **Otro contraargumento: «Con la marea HTF el bot evitaría las entradas contra la tendencia».**
  - **Respuesta [I]:** también pierde en el régimen alcista (P1: −0,17 %), así que un filtro de tendencia por sí solo difícilmente cambia el signo.
  - **[N]** Esto no se probó.

## 9. Veredicto
- **[H] P1, P2 y P3: EVIDENCIA EN CONTRA de una ventaja neta.** Criterio prerregistrado: el límite superior del IC90 de la media neta por operación es menor que 0.
  - P3 está **al límite** (−0,017 % con bloques mensuales, −0,001 % con trimestrales). Su conclusión correcta es «sin ventaja neta, y posiblemente pequeña pérdida».
- **[I] Lo que esto significa para el proyecto:**
  - las estrategias del bot no pagan sus costos ni muestran información de timing en 6,7 años de BTC a 1 h;
  - **no hay base para operar con dinero real ni para ajustar parámetros** sobre estos datos;
  - optimizar ahora sería minería de datos.

## 10. Próximo paso recomendado (uno)
**Retirar las tres estrategias intradía como candidatas a dinero real, y no hacer más backtests de variantes sobre BTC.**

Si querés seguir buscando, el único experimento con algún valor informativo es **una confirmación prerregistrada y acotada de la única pista posterior**: «breakout con confianza ≥ 0,65 tiene media neta > 0».
- **Datos nuevos:** ETHUSDT spot a 1 h de data.binance.vision, 2019-10 → 2026-05, unos 80 archivos con su `.CHECKSUM` (≈ 4 MB, el tamaño de los de BTC).
- **Requisitos:** tu autorización para la descarga y el mismo `MotorE1`.
- **Advertencia:** su probabilidad a priori es baja (≈ 30 % de falso positivo). Lo más probable es que confirme el resultado negativo.

**Por separado, mantenimiento recomendado** (requiere tu autorización para tocar el repositorio): corregir D1–D3 en `tia/backtest/engine.py`. Cualquier backtest hecho con ese motor sobrestima o trunca la muestra de forma arbitraria; con P1 deja 24 operaciones en lugar de 629.

## 11. Archivos y reproducción
- **Prerregistro y hashes:** `prerregistro/PRERREGISTRO_E1.md` y `prerregistro/HUELLAS_ANTES_DE_EJECUTAR.txt`.
- **Código:** `codigo/e1.py`, `codigo/e1_comun.py`, `codigo/e1_verificacion.py`, `codigo/diag_motor.py`, `codigo/diag_d3.py` y `codigo/tablas.py`.
- **Resultados:**
  - `resultados/real/` con `resultado_e1.json`, `operaciones_por_configuracion.json`, `validez.json`, `manifiesto_datos.json`, `tablas.md` y `SHA256SUMS`;
  - verificación: `resultados/verificacion_backtester_sintetico.json`.
- **Ejecuciones inválidas, conservadas sin analizar:** `logs/06a_*` y `resultados/real_intento2_INVALIDO_D3/`.

Para reproducir:
```
cd codigo
PYTHONPATH=/home/user/Trader-IA/packages/tia/src:. ../entorno/venv/bin/python -B e1_verificacion.py <salida.json>
PYTHONPATH=/home/user/Trader-IA/packages/tia/src:. ../entorno/venv/bin/python -B e1.py --salida <directorio nuevo>
python3 -I tablas.py <directorio nuevo>/resultado_e1.json
```
Duración: ≈ 45 min con 4 núcleos. Sin red, salvo el venv ya instalado.

Sin commits, push, merges, deploys ni operaciones. El repositorio sigue en `692f2b2`, sin cambios nuevos.
