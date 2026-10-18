# Revisión crítica del resultado fuera de muestra de T y siguiente experimento (2026-10-17)

**Alcance.** Es una revisión **posterior y descriptiva** de un resultado ya consumido: no cambia la decisión prerregistrada (EVIDENCIA INSUFICIENTE) ni el experimento original (prerregistro `94a16556…`, script `941b6e11…`, resultado `4f8fafde…`).
- Los cálculos están en `experimentos/revision_fuera_de_muestra_T.py` → `experimentos/revision_fuera_de_muestra_T.json`.
- No se descargó nada ni se corrió ninguna prueba nueva. El experimento en papel no se tocó.

## 1. Qué está verificado, qué es inferencia y qué depende de supuestos

| Afirmación | Estado | Evidencia |
|---|---|---|
| Exceso conjunto +7,0 %/año, IC90 −8,8 % / +22,9 %, P = 0,755 | **Hecho verificado** | Recalculado con el código congelado: idéntico al JSON. Reimplementado de forma independiente, leyendo los zip y verificando sus SHA-256: la diferencia diaria máxima con el código congelado es **0,0** en BTC y en ETH |
| Desarrollo +19,4 % frente a fuera de muestra +7,0 % | Hecho (las dos cifras) | Diferencia 12,3 pp, error 18,5 pp, **z = 0,67, p = 0,50** (BTC z = 0,30; ETH z = 0,82) |
| «El efecto se encogió por la selección en desarrollo» | **Inferencia, no demostrada** | La diferencia no es distinguible del azar. El resultado fuera de muestra es compatible con el efecto de desarrollo **y** con cero |
| Robustez frente a costes ×2 y retraso de 1 día | Hecho para el signo; **no para la significación** | Costes ×2: +4,4 %, P = 0,66. Retraso: +7,7 %, P = 0,79 |
| Frente a buy and hold, «sobre todo por estar menos expuesta en 2022» | **Incorrecta en parte; corregida** | Ver abajo |
| «≈ 52 años» y «como mucho ≈ 9 %» | **Aritmética correcta, pero condicionada a supuestos; el «como mucho» era falso** | Ver §3 |
| «T es la única candidata con signo positivo fuera de muestra» | **Imprecisa; corregida** | El carry de H-CARRY también fue positivo en test (+3,76 %), aunque por debajo de su comparador del 5 %. T es la única que supera a **su** benchmark |

**Buy and hold, descompuesto** (CAGR neto, 2022-01 → 2026-05):

| | Buy and hold | Estática (misma exposición media) | T | Exposición media | Timing |
|---|---|---|---|---|---|
| BTC, período completo | 11,1 % | 9,4 % | 18,8 % | **−1,7 pp** | **+9,4 pp** |
| BTC, 2022 | −64,4 % | −39,7 % | −30,1 % | +24,7 pp | +9,6 pp |
| ETH, período completo | −12,9 % | −0,5 % | 3,0 % | **+12,3 pp** | +3,5 pp |
| ETH, 2022 | −67,6 % | −35,7 % | −29,2 % | +31,9 pp | +6,5 pp |

- En 2022, T tuvo una exposición objetivo media de 0,16 en BTC y 0,22 en ETH, frente a 0,54 y 0,48 de la estática.
- **Lectura correcta:** en 2022 la menor exposición explica la mayor parte de la diferencia. En todo el período, en cambio, la ventaja de BTC sobre buy and hold viene del timing (no significativo); la estática por sí sola rindió menos que buy and hold. En ETH, la ventaja viene sobre todo de la exposición.
- El Sharpe de la estática es igual al de buy and hold (0,46 en BTC): toda la mejora de Sharpe de T (0,71) es timing.

## 2. Método estadístico
- **Qué es P.** Es la fracción de 2 000 remuestreos por **bloques circulares** de 20 días cuya media del exceso diario es > 0.
  - **No** es la probabilidad de que la ventaja sea real, ni un p-valor.
  - Equivale, aproximadamente, a 1 − p unilateral: P = 0,755 ≈ p ≈ 0,25.
- **Qué es el IC90.** Es el intervalo de percentiles 5–95 de esas medias, anualizado × 365. Es una media **aritmética** diaria, no un CAGR.
- **Dependencia temporal.** El exceso diario casi no tiene autocorrelación (ACF en el retardo 1: −0,09; en el 20: −0,03); su varianza sí está agrupada (ACF de los cuadrados en el retardo 1: 0,22).
  - El error es casi el mismo con cualquier método: iid 10,2 %; Newey–West con 7 a 60 retardos, 9,6–9,7 %; bootstrap con bloques de 5 a 60, 9,2–9,7 %.
  - **P se mantiene entre 0,748 y 0,758 con bloques de 1 a 60.** Solo con bloques de 120 o 250 días (13 y 6 bloques en total, una estimación poco fiable) sube a 0,81–0,86. **La decisión no depende del bloque.**
- **Correlación BTC–ETH.** La correlación de sus excesos es de **0,69**; equivalen a **1,2 activos efectivos**, no a 2. El método la respeta: remuestrea días completos del promedio, así que conserva la correlación. ETH agrega poca información.
- **Observaciones efectivas.**
  - Para la media diaria son unas **1 600–1 800** (≈ 4,4 años): la dependencia no las reduce.
  - Pero la información económica es menor: T cruzó la exposición del 50 % solo 62 veces en BTC y 87 en ETH, y el exceso lo dominan pocos regímenes (la caída de 2022, la subida de 2023–2024).
  - **Supuesto no verificable con estos datos:** que el efecto sea estable entre regímenes. Si no lo es, la incertidumbre real es mayor que el IC90.
- **Otros supuestos.**
  - La estática usa la exposición media **realizada** en la ventana. No es invertible a priori, pero aísla el timing.
  - La estática no paga costes y T sí: el sesgo juega en contra de T.

## 3. ¿Son defendibles «52 años» y «9 %»?
**La aritmética es correcta, pero son cifras condicionales, no conclusiones.**
- **52 años** = (1,645 × σ₁ / μ)², con μ = +7,05 % (suponer que el efecto verdadero es igual a la estimación puntual), σ₁ = 31 % de error con un año (medido en **desarrollo**) y una potencia del 50 %.
  - Con la variabilidad fuera de muestra, σ₁ = 17–20 %, salen **16–22 años**.
  - Con un 80 % de potencia, **37–120 años**.
- **9 %** = probabilidad de P ≥ 0,95 a los 24 meses, con esos mismos μ y σ₁.
  - Un Monte Carlo con la regla completa del papel (P conjunto ≥ 0,95, P de BTC ≥ 0,90 y costes ×2 > 0, con trayectorias remuestreadas de las series fuera de muestra) da **8,4 %**.
  - Con la variabilidad fuera de muestra y la aproximación normal, **12,5–14,3 %**.
  - **«Como mucho» era falso:** si el efecto fuera el de desarrollo, la probabilidad sería **22–48 %** (34 % por Monte Carlo).
  - Con un efecto nulo, el papel tiene un 2,8 % de falsos positivos y un 13,9 % de probabilidad de detener a los 12 meses.
- **Formulación defendible:** «si el efecto verdadero fuera de ≈ +7 %/año, el papel tendría ≈ 8–14 % de probabilidad de respaldarlo a los 24 meses; la incertidumbre dominante es el tamaño del efecto, no el plazo».

## 4. ¿Conviene ampliar el universo de mercados?
**Sí, con condiciones.** Es la única manera de obtener una respuesta con potencia razonable. Con supuestos explícitos (§5), una ampliación tendría **49–75 %** de probabilidad de respaldar un efecto de 1 %/año a 10 % de volatilidad, frente a ≈ 8 % del papel a 24 meses.

Límites que hay que aceptar:
- **Prueba otra cosa:** la *transferibilidad* del timing de T, no la ventaja en cripto. Un resultado nulo no refuta T en cripto; uno positivo vuelve más creíble que el mecanismo sea general.
- **No es evidencia del todo nueva:** el momentum de series temporales está documentado en esos mercados (Moskowitz, Ooi y Pedersen, 2012; Hurst, Ooi y Pedersen, 2017). Solo el período **posterior a la publicación** es fuera de muestra frente a esa literatura. El diseñador conoce a grandes rasgos las tendencias de 2013–2026 (bonos en 2022, oro en 2024–2025, petróleo en 2014 y 2020), así que el universo debe fijarse con una regla mecánica, sin excluir nada después.
- **Dependencia:** los excesos de los índices de renta variable están muy correlacionados. Con 12 activos en 3 clases, los activos efectivos serían ≈ 2,6–5,2 según la correlación (supuesta, no medida). Por eso hay que ponderar por clase y remuestrear días completos.
- **Divisas:** un long/flat no tiene un lado largo natural (EUR/USD frente a USD/EUR), y el resultado dependería de esa elección arbitraria. **Quedan fuera** de la métrica primaria.
- **Calendarios y horizontes:** el código congelado cuenta barras; en cripto son días corridos, en bolsa son sesiones. Para que la regla no cambie, los horizontes deben seguir siendo 30, 90 y 180 días **corridos** (un adaptador, probado para que reproduzca `tsmom` exactamente en cripto). La anualización debe hacerse × 252, no × 365.
- **Datos:** no hay una fuente oficial con checksums como data.binance.vision. La procedencia sería «limitada», con validación contra los emisores. Los costes son menores (5 bps por lado) y otros los horarios.

## 5. Experimento propuesto: **T-MULTI** (borrador; no está congelado ni ejecutado)
1. **Hipótesis:** el exceso de timing de T frente a su estática, promediado entre clases y normalizado por riesgo ex ante, es > 0 en mercados no cripto, después de 2012.
   - **Unidad estadística:** la sesión de NYSE; la sección transversal de cada sesión se agrega en una sola serie diaria.
2. **Universo** (fijado ahora, antes de cualquier dato): el ETF estadounidense más antiguo y líquido de cada exposición amplia, emitido antes del 2007-12-31.

   | Clase | ETF |
   |---|---|
   | Renta variable | SPY, IWM, EFA, EEM |
   | Bonos | SHY, IEF, TLT, LQD |
   | Materias primas | GLD, SLV, USO, DBC |

   - **Fuera:** divisas, cripto (ya probada), sectores, países, ETF apalancados o inversos.
3. **Inclusión y exclusión:** se decide solo con los datos, **antes** de calcular ningún resultado de T.
   - Datos continuos desde 2012-01-03.
   - Sin huecos de más de 5 sesiones salvo feriados de NYSE; OHLC coherente; precios > 0.
   - Ajuste por distribuciones validado contra el rendimiento total publicado por el emisor (diferencia ≤ 0,5 pp en 3 años de muestra); si no, se reconstruye con sus distribuciones.
   - Si se excluyen más de 2 de los 12 ETF, el experimento no se corre.
4. **Fechas:** datos de 2012-01-03 a 2026-09-30; evaluación del **2013-01-02 al 2026-09-30** (≈ 13,75 años). Frecuencia diaria.
5. **Regla y ejecución:**
   - T sin cambios: horizontes de 30, 90 y 180 días corridos; exposición 0, ⅓, ⅔ o 1.
   - Decisión con el cierre ajustado de d y ejecución en la apertura ajustada de la sesión siguiente, con `simular` congelado; solo se opera si cambia el objetivo.
   - **Costes:** 5 bps por lado (comisión, medio spread y slippage; conservador para estos ETF). Estrés ×2 y ×3, y retraso de 1 sesión. Efectivo al 0 %, como en cripto: el exceso de timing apenas depende de la tasa.
6. **Benchmarks por activo:** la estática con la misma exposición media (atribución, primario), buy and hold del mismo ETF con rendimiento total, y efectivo.
7. **Métrica primaria:** E = 252 × media de X_t.
   - X_t es el promedio de las 3 clases de la media, sobre los activos disponibles, de (0,10 / σ̂ᵢ,ₜ₋₁) × (rᵀ − rᴱ).
   - σ̂ es la volatilidad realizada de las 252 sesiones previas (ex ante). Se mide en %/año a 10 % de volatilidad.
8. **Incertidumbre:**
   - Bootstrap circular de X_t por bloques de **60 sesiones**, 5 000 remuestreos, semilla 20261017; P e IC90 como hoy.
   - Sensibilidad con bloques de 20 y 120 y con Newey–West de 60 retardos.
   - **La decisión usa el menor de los dos P** (el del bootstrap y el de Newey–West).
9. **Decisión:**
   - **VENTAJA TRANSFERIBLE RESPALDADA:** P ≥ 0,95, E con costes ×2 > 0, **y** E > 0 al excluir cada una de las 3 clases por turno. Así no puede sostenerla una sola clase.
   - **SIN VENTAJA RELEVANTE:** límite superior del IC90 < 0,5 %/año a 10 % de volatilidad (el efecto mínimo que valdría la pena; el cripto fuera de muestra equivale a ≈ 1,2 %).
   - **EVIDENCIA INSUFICIENTE:** cualquier otro caso.
10. **Activos correlacionados y datos faltantes:**
    - Pesos iguales por clase.
    - Remuestreo de días completos.
    - Se informa el número efectivo de activos.
    - Un activo sin dato ese día no se rellena: se promedia con los disponibles de su clase. Un día sin ninguna clase completa no entra.
11. **Selección y comparaciones múltiples:**
    - Una sola estadística primaria y una sola ejecución.
    - Los resultados por activo y por clase son descriptivos y se informan **todos**; no se excluye ni se ajusta nada después de verlos.
    - **El prerregistro se commitea en GitHub antes de descargar ningún dato**, para que la fecha sea verificable.
12. **Potencia** (con supuestos):
    - σ de 3,7 %/√año por activo a 10 % de volatilidad, medida en cripto fuera de muestra; correlaciones dentro y entre clases de (0,3; 0,05) a (0,7; 0,2).
    - P(respaldada) = 20–31 % si E = 0,5 %; **49–75 %** si E = 1 %; 64–89 % si E = 1,24 % (el tamaño de cripto).
    - P(sin ventaja) = 20–31 % si E = 0.
13. **Consecuencias declaradas de antemano:**
    - **Respaldada:** T pasa a ser una candidata seria; el papel sigue igual.
    - **Sin ventaja:** se despriorizan T y la familia de tendencia.
    - **Insuficiente:** se deja de trabajar históricamente con T; solo queda el papel.
14. **Fuente de datos** (sin descargar todavía):
    - Stooq, OHLCV diario público y sin clave, con un manifiesto SHA-256 al descargar.
    - Validación contra las distribuciones y el NAV publicados por los emisores (SPDR, iShares, Invesco, USCF).
    - **Requiere tu decisión:** la fuente nueva, comprobar la red y commitear el prerregistro antes de descargar.
    - **Sin verificar:** si Stooq ajusta por dividendos. Lo resuelve la puerta del punto 3.

## Reproducir
```
cd research/tendencia_btc; PYTHONPATH=src:../hcarry_next/src ../hcarry_next/.venv/bin/python -B experimentos/revision_fuera_de_muestra_T.py
```
