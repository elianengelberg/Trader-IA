# Decisiones técnicas de H-CARRY Next

Cada decisión: qué se eligió, alternativas, debilidades y qué la refutaría.

## D-01 Aritmética en coma flotante con cantidades en lotes enteros
- **Elegido:** importes en `float`, cantidades como número entero de lotes (paso 0,001 BTC).
- **Alternativa:** `Fraction` exacta (rev. 5). Es exacta pero 20–50 veces más lenta; impide barridos de parámetros y estrés.
- **Mitigación:** conciliación independiente en cada cierre (tolerancia 1e-6 del capital) y regresión exacta contra las cifras documentadas de rev. 5 (10 014,94; 0,2022473335).
- **Debilidad:** errores de redondeo del orden de 1e-9 por operación; irrelevantes frente a costes de bps.
- **Refutación:** que alguna conciliación falle o que las cifras de rev. 5 dejen de reproducirse.

## D-02 Slippage como coste explícito sobre el nocional a precio de apertura
- **Elegido:** convención S12 de rev. 5. Se ejecuta a la apertura y el slippage se cobra aparte.
- **Alternativa:** ejecutar a un precio peor. Es equivalente a primer orden, pero hace menos transparente la descomposición.
- **Debilidad:** no modela la profundidad. Para eso están el impacto ∝ √(nocional/volumen) y el estrés de pata adversa.

## D-03 Orden temporal: funding → liquidación por salto → decisión y ejecución en la apertura → liquidación en la barra → valoración
- **Elegido:** el funding de la hora t se liquida sobre la posición mantenida durante la hora anterior, igual que en rev. 5.
- **Debilidad:** la decisión usa los precios de apertura y ejecuta a esos mismos precios, sin latencia.
- **Control:** estrés `retraso_barras` (la decisión de t se ejecuta en t + k con los precios de entonces).
- **Refutación:** que el resultado cambie de signo con un retraso de 1 h.

## D-04 Modelo de liquidación
- **Elegido:** margen de mantenimiento fijo (1 %). Se liquida cuando el mark máximo de la hora alcanza P_liq, o al mark de apertura si hay un salto. El saldo negativo lo absorbe el fondo de seguros (asiento explícito). El spot descubierto se vende en la siguiente apertura y hay 24 h de enfriamiento.
- **No modelado:** tramos de margen reales, ADL, comisión de liquidación (parámetro, 0 por defecto), liquidación parcial y reequilibrio dentro de la hora.
- **Consecuencia:** las variantes apalancadas (ρ < 1) dependen de este modelo. Su ventaja no se acepta sin un modelo de margen por tramos y datos reales intrahorarios.

## D-05 Fuente de datos: archivos mensuales de data.binance.vision
- **Por qué:** es oficial, trae un checksum SHA-256 por archivo, es reproducible y no necesita claves.
- **Estado:** la política de red del entorno lo deniega (403), igual que a todas las bolsas. **No se intentó ningún rodeo.**
- **Alternativas descartadas por ahora:** CSV de terceros en GitHub, sin procedencia verificable; la API REST, también bloqueada.

## D-06 Divisiones fijas y test protegido
- **Divisiones:** desarrollo 2019-10 → 2022, validación 2023 → 2024-01, test 2024-02 → 2026-05 (la ventana prerregistrada de rev. 5). El período reservado es inaccesible por código.
- **Guarda del test:** exige un prerregistro con el hash de la configuración y rechaza una segunda evaluación con los mismos datos.
- **Debilidad:** es una guarda procedimental. Quien controle el código puede saltársela, aunque la huella del código queda en el registro.

## D-07 Protocolo con regla de selección fija y mundos nulos
- **Selección:** se elige el mejor de cada familia en desarrollo (39 candidatos), se exige superar a la referencia en validación y la regla de decisión del test es estricta e incluye costes ×2.
- **Riesgo:** sobreajuste por elegir el máximo de muchos candidatos. Se mitiga con validación, test y mundos nulos (funding barajado), que miden la tasa de falsos descubrimientos de la familia `UmbralFunding`.
- **Refutación:** que el protocolo declare mejoras de `UmbralFunding` en mundos nulos con frecuencia apreciable.

## D-08 R0 conservada como opción; la referencia de Next usa «omitir»
- rev. 5 detenía la simulación ante una ampliación inviable. Next ejecuta la parte viable y lo registra.
- Para reproducir el veredicto de rev. 5 se usa `al_inviable="detener"`.

## D-09 Rentabilidad sobre el capital total como métrica principal
- El monitor de funding del repositorio anualiza sobre el nocional. Pero un carry delta-neutral inmoviliza capital en las dos patas, así que el rendimiento sobre el equity es APR/(1 + ρ).
- Con la estructura de rev. 5 (ρ = 1), superar el 6 % de D1 exige ≥ 12 % de APR neto sobre el nocional (`python -m hcarry estructura`).

## D-10 Generador sintético
- **Modelo:** régimenes de Markov, prima con reversión a la media y funding con la fórmula de Binance (prima media + ajuste acotado de interés), así que la tasa modal es el interés.
- **Uso:** solo prueba maquinaria y protocolo; no está calibrado contra datos reales.
- **Debilidad:** las conclusiones sintéticas dependen de los supuestos del generador.

## D-11 Sin dependencias de ejecución
- Solo la biblioteca estándar; las pruebas usan pytest e hypothesis.
- El motor procesa unas 30 000 horas por segundo, lo que basta para barridos de cientos de configuraciones.

## D-12 Alternativa a UmbralFunding: predecir el funding con la prima (`UmbralPrima`)
- **Hipótesis:** el funding de Binance es una función mecánica de la prima media del intervalo, f = P̄ + clamp(I − P̄, ±0,05 %). La prima ya es observable ANTES de la liquidación. Predecir el próximo funding con la prima de las últimas horas cerradas reacciona antes que la media de funding pasados.
- **Datos:** con datos reales se usa el índice de prima oficial (`premiumIndexKlines`, opcional). Si falta, se usa F/S − 1 como aproximación; es peor, porque el índice de Binance usa precios de impacto y un índice compuesto.
- **Debilidades:**
  - el tope y el interés son supuestos (S1);
  - con F/S − 1 la predicción tiene ruido;
  - en el generador sintético el funding sale EXACTAMENTE de esa fórmula, así que la ventaja sintética de esta política está sobreestimada por construcción.
- **Refutación:** que no mejore a su línea base fuera de muestra con datos reales, o que su ventaja desaparezca con retraso o con costes ×2.

## D-13 Sensibilidad al generador: variante «bajista suave»
- El generador base tiene régimenes bajistas con funding negativo profundo y persistente, lo que favorece estructuralmente a las reglas de salida.
- La variante «bajista suave» (prima media −0,03 % en el régimen bajista) deja el funding cerca del interés.
- Si una conclusión solo se sostiene en la variante base, depende de ese supuesto y no se considera robusta.

## D-14 Procedencia de los datos imposible de falsear por accidente
- Todo directorio de datos exige un `MANIFIESTO.json` con `procedencia` ∈ {`historico_oficial`, `sintetico`}. `construir_panel` verifica cada archivo contra el manifiesto y etiqueta el panel con la procedencia.
- Los archivos fabricados llevan una marca en el comentario del zip. `importar` los etiqueta como sintéticos aunque tengan checksums válidos y rechaza las copias mezcladas. Si un manifiesto dice «histórico» y contiene un archivo marcado, se rechaza.
- El evaluador histórico elige la carpeta de salida (`resultados/historico/` o `resultados/sintetico/`) a partir del manifiesto. Con datos sintéticos su conclusión es siempre EVIDENCIA INSUFICIENTE.
- **Debilidad:** una copia aportada manipulada a la vez en datos y `.CHECKSUM` no se detecta. Es la vía 2 de `experimentos/historico/FUENTES_ALTERNATIVAS.md`. La mitigación es la vía 1 (descarga directa) o comprobar al azar algunos hashes contra la fuente.

## D-15 Prerregistro de la validación histórica
- Están fijados antes de ver datos:
  - las políticas y sus parámetros (UmbralFunding sin optimizar);
  - los costes, las sensibilidades y el diagnóstico previo con su predicción;
  - los filtros de calidad y los criterios de las tres conclusiones.
- Hash `90642cd1…` (`experimentos/historico/PRERREGISTRO_VALIDACION_HISTORICA.md`).
- **Alternativa descartada:** usar los parámetros que elige el protocolo en desarrollo como comparación principal. Es legítimo, porque la elección se hace solo en desarrollo, pero añade grados de libertad. Puede correrse como análisis secundario y exploratorio con `python -m hcarry protocolo`.

## D-16 La importación no atribuye el origen de los datos
- `importar` no puede saber quién aportó una copia. El campo `via` describe la importación («importación de una copia externa verificada contra sus .CHECKSUM oficiales» o «importación de archivos FABRICADOS…») y no la atribuye a nadie.
- Antes escribía «copia aportada por el usuario» también para archivos que yo había fabricado. El ensayo afectado se conserva con un `ERRATA.md`.
- Los cambios de código posteriores al prerregistro se documentan en una adenda **antes** de ver datos, con una verificación de que no alteran ningún cálculo: el ensayo sintético se reproduce bit a bit.

## D-17 Huecos de los archivos mensuales: diarios oficiales, nunca otra fuente
- Una hora ausente en un archivo mensual se busca en el archivo **diario** de la misma serie y del mismo emisor, con su `.CHECKSUM`. Nunca se toma de otra fuente.
- Se usa solo para horas ausentes. En las horas comunes, el diario debe coincidir en precios (D1).
- Las velas irregulares por paradas del exchange se excluyen: la hora queda sin datos y cuenta en C3.
- Lectura estricta documentada: solo con mensuales, la muestra no habría sido apta.

## D-18 Orden de trabajo frente a la misión del 2026-10-16
- **Prevalece el prerregistro:** el test es 2024-02 → 2026-05, de uso único.
- El diagnóstico y el desarrollo de candidatos se hicieron solo en 2020–2022, antes del test.
- El período reservado no se tocó.
- Tras el test, toda la muestra es exploratoria.

## D-19 No se sumaron candidatos al test
El techo con oráculo de las reglas de salida en desarrollo era de 0,17 pp/año. Variar el tamaño según el funding es apalancamiento, con un riesgo que el motor no modela.

## D-20 Recomendación: detener la línea, con un criterio de reapertura
- **Motivo:** el carry no supera al efectivo desde 2022, y el funding se comprimió en todo el mercado.
- **Reapertura:** con un funding de 90 días de BTCUSDT > 12 % anual, mediante una prueba prospectiva prerregistrada. Ver `ESTADO_EJECUTIVO_HISTORICO.md`.
