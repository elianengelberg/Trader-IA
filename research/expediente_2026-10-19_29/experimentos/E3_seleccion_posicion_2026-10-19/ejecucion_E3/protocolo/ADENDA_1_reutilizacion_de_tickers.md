# Adenda 1 a las notas de implementación: reutilización de tickers y redenominaciones

**Momento:** después de leer **solo el listado S3** (nombres de símbolos y meses con archivo) y **antes** de leer cualquier precio, volumen o retorno. Ningún umbral, ventana ni criterio cambia.

**Qué motivó la adenda:** el listado muestra símbolos cuyo rango de archivos atraviesa cambios de activo conocidos públicamente. Por ejemplo, LUNAUSDT tiene archivos de 2020-08 a 2026-09: el ticker pasó a designar otro token en 2022. Con la sola regla de «30 días inactivos» (v3 §2.2.3), un corte de menos de 30 días entre dos activos distintos se leería como un único listado, y una venta diferida podría ejecutarse al precio del activo nuevo.

**Interpretación de la v3 §2.2.4** (renombres «solo con un anuncio oficial: símbolo viejo, símbolo nuevo, fecha y relación de canje»), aplicada sin excepciones:
1. **Renombre con cambio de símbolo** (X → Y): el listado vigente de X **termina** en la fecha efectiva. Y lo continúa con la relación de canje, y hereda la edad y las posiciones. Si después X vuelve a negociarse, ese tramo es un **listado nuevo** (otro activo), aunque el corte haya durado menos de 30 días.
2. **Redenominación o canje con el mismo símbolo** (X → X con relación r ≠ 1): es el caso X = Y de la regla anterior. Las posiciones se ajustan por r y la serie de precios se trata como continua solo a través de esa relación.
3. **Si no hay anuncio**, rigen las reglas de la v3 §2.2.3 tal cual (30 días). En F3 se hace un control de calidad, solo con datos de actividad: se listan **todos** los cortes de actividad seguidos de una reanudación (de cualquier duración), y para cada uno se busca un anuncio de renombre, canje, redenominación o suspensión. Los cortes sin anuncio se informan como limitación; **no** se corrigen con reglas inventadas.
4. **Todos los mapeos** (X, Y, fecha efectiva, relación y fuente archivada) se fijan con hash en F3, antes de calcular cualquier retorno de estrategia.
