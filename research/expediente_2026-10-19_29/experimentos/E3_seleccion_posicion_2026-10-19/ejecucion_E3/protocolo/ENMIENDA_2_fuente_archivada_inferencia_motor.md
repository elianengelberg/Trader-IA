# Enmienda 2 (desviaciones e interpretaciones documentadas respecto de la v3 y de las notas N1–N22)

**Momento:** 2026-10-20, antes de compilar anuncios y antes de usar precios para evaluar E3.
- Hasta este punto solo se leyeron: el listado S3 de símbolos y meses; dos archivos de prueba del módulo de calidad (BTCUSDT y 0GUSDT, sin calcular ningún retorno); y, de Common Crawl, una sonda de 2 capturas del índice y 4 páginas.
- **Ninguna prueba de E3 se calculó con datos reales.**

La v3 congelada (`279a865f…`) **no se modifica**. Esta enmienda registra lo que la v3 deja sin fijar o lo que no se pudo hacer como estaba previsto.

## E2.1 Fuente de anuncios: Common Crawl en lugar del Internet Archive (desviación de la nota N8)
- **Motivo:** web.archive.org está bloqueado por la política de red del entorno (conexión cortada en cada intento, registrado por el proxy). La alternativa ya descartada en la N8 sigue descartada: binance.com, cuyas condiciones de uso no se pudieron leer y que responde con un desafío anti-bots. Telegram prohíbe el scraping.
- **Nueva fuente:** **Common Crawl** (`data.commoncrawl.org`), un archivo público de capturas web.
  - Sus condiciones de uso otorgan una licencia de acceso y uso para fines lícitos y de investigación.
  - Accederlo **no toca binance.com** ni elude ningún control de acceso.
  - El índice se consulta por rangos HTTP sobre los `cluster.idx` y `cdx-*.gz` publicados, porque `index.commoncrawl.org` también está bloqueado.
  - Las páginas se leen como registros WARC por rango.
  - Cada solicitud queda registrada con URL, rango, estado, bytes y SHA-256.
- **Prefijos SURT consultados** en todas las capturas con fecha entre 2017-06 y 2026-06:
  - `com,binance)/en/support/announcement`;
  - `com,binance,support)/hc/en-us/articles`;
  - `com,zendesk,binance)/hc/en-us/articles`.
- **Extracción (reglas fijas):**
  - De cada URL única con HTTP 200 se toma la captura **más antigua**.
  - Se extraen el título, la fecha de publicación (si está), el texto y, por patrones, los pares `XXX/USDT`, los tokens entre paréntesis, las fechas `AAAA-MM-DD` o `AAAA/MM/DD` con hora UTC, y el tipo.
  - **Tipos:** exclusión de token; remoción de pares; renombre, canje o redenominación; listado; otros.
  - **Se descartan** los anuncios de futuros, margen, Earn, Convert o Alpha que no afectan pares spot.
  - Los casos que las reglas no resuelven son «E» (ambiguos) y se informan uno por uno.
- **Cobertura:** Common Crawl es una **muestra**; puede faltar una parte de los anuncios. No se infiere nada sobre los que faltan. La regla de inicio de la v3 §4.11 (iii)–(iv) y la de ≥ 156 semanas se aplican **sin cambios**. Si la cobertura no alcanza, el resultado es el que fija la v3 (ventana recortada o INVÁLIDO).

## E2.2 Intervalo de H2 y H3 bajo la regla del máximo (la v3 §5.3 no lo especifica)
- La calibración original (`calibracion.json`, `9232876…`) activó la regla prerregistrada p = máx(p_boot13, p_boot26, p_NW13).
- La v3 fija el intervalo para H1 bajo esa regla (§5.1), pero **no** para H2 y H3.
- **Se fija:** IC90 = **envolvente** [mín de los tres extremos inferiores; máx de los tres extremos superiores].
  - Es dual con la regla del máximo para la confirmación: p_máx ≤ 0,05 ⇔ el mínimo de los extremos inferiores > 0, porque cada método es dual con su propio intervalo.
  - Es conservadora para «en contra».
- **Reemplaza** la frase «método de mayor amplitud» de `DECISION_CALIBRACION.txt`, que se conserva sin cambios como registro.
- **Calibración complementaria** (`calibracion_regla_maximo.json`; semilla 20261028; 2000 simulaciones por proceso; los tres valores p sobre la misma serie):

| Proceso | p_boot13 | p_boot26 | p_NW13 | **máx** | Banda |
|---|---|---|---|---|---|
| Rechazo al 5 % | 4,7–6,4 % | 4,75–6,8 % | 4,7–6,5 % | **3,65–5,5 %** | [3,6 %; 6,4 %] |
| Rechazo al 2,5 % | 2,3–3,45 % | 2,3–3,5 % | 2,25–3,8 % | **1,85–2,55 %** | [1,5 %; 3,5 %] |

  - Solo vale para esos cinco procesos sintéticos; **no demuestra validez general**.
  - Costo en potencia (μ = 30 %/año, al 5 %): ≈ 3–5 puntos frente a p_boot13.

## E2.3 Interpretaciones del motor (la v3 §4.7–4.10 no las fija; se aplican igual a la cartera, a EW-U30 y al nulo)
1. **Orden diario de eventos:**
   1. valuación de W en el día de ejecución, **antes de operar**;
   2. liquidaciones contables;
   3. ventas pendientes;
   4. operaciones de la formación.
2. **Momento de la liquidación contable:** se registra al inicio del día d cuando hay ≥ 30 días inactivos seguidos hasta d − 1, es decir, al cierre del día 30 de inactividad, sin mirar al futuro.
3. **Fondos para las entradas:** en el caso general se reparte en partes iguales **todo el efectivo disponible**. Es lo cobrado en las ventas más el efectivo de liquidaciones o lugares vacantes anteriores, coherente con la v3 §4.10: «lo cobrado queda en efectivo hasta la formación siguiente». Si solo hay ventas de la misma formación, coincide con la redacción de la v3 §4.8.
4. **Venta pendiente que vuelve a quedar entre los objetivos:** se cancela y la posición se mantiene.
5. **Semana no evaluable:** no actualiza el mes de referencia de la vuelta mensual a pesos iguales.
6. **Nulo R5:** orden aleatorio uniforme de las monedas de U30 cada semana (nota N12).

## E2.4 Lo que esta enmienda NO hace
- No cambia hipótesis, métricas, umbrales, ventanas, universos, costos ni criterios.
- No usa ningún resultado con datos reales.
