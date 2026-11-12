# E3: decisiones recomendadas, inconsistencias abiertas y correcciones indispensables (revisión acotada, 2026-10-20)

**Alcance:**
- No modifica la v2 ni los cambios propuestos para la v3, y no congela nada.
- Sin datos ni pruebas. Todas las cifras de potencia son aritmética con supuestos [Hip].

## D1. Multiplicidad: **Holm (m = 2) para H1 y H2, y compuerta serial hacia H3** (la opción de la v2)

| Procedimiento | Regla | Error de familia | Umbral efectivo de H1 | Coherencia con las reglas de decisión |
|---|---|---|---|---|
| P1: Holm m = 3 (H3 entra con p = 1 si no se habilita) | Umbrales 0,0167, 0,025 y 0,05 | Fuerte, ≤ 5 % | 0,0167 (0,025 en el segundo paso) | Válido, pero **dominado**: castiga a H1 y H2 por una H3 que solo puede probarse si las dos ya rechazaron |
| **P2: Holm m = 2 más compuerta serial** | H1 y H2 con Holm (el p menor contra 0,025 y el otro contra 0,05); H3 al 5 % solo si H1 y H2 rechazan y la base es robusta | Fuerte, ≤ 5 % (ver abajo) | 0,025 (0,05 si H2 ya rechazó) | H3 subordinada, como corresponde. H1 y H2 sin un orden impuesto de antemano |
| P3: secuencia fija H1 → H2 → H3, cada una al 5 % | Se detiene en la primera que no rechaza | Fuerte, ≤ 5 % | 0,05 | Coherente con la jerarquía, pero **sube** el umbral efectivo de H1 respecto de lo ya revisado |

**Control del error en P2:**
- **Si alguna de H1 o H2 es nula verdadera:** H3 solo se prueba si las dos rechazaron, así que cualquier error en H3 ya implica un error en {H1, H2}. Ese error está acotado por Holm al 5 %.
- **Si H1 y H2 son falsas y H3 es verdadera:** P(error) ≤ P(p₃ ≤ 0,05) ≤ 5 %.
- Vale para cualquier dependencia entre las pruebas.
- Exigir robustez para abrir la compuerta solo reduce la probabilidad de probar H3.

**Orden:**
- H1 y H2 se prueban como familia (Holm las ordena por su p, no por preferencia).
- La **interpretación** es jerárquica y ya estaba fijada: H2 sin H1 es «no concluyente» y cierra la familia (corrección A8).
- H3 va última.

**Por qué no las otras:**
- **P1:** controla el mismo error con menos potencia, sin ningún beneficio inferencial.
- **P3:** también es válida. Su única diferencia práctica es **aumentar la probabilidad de confirmar H1**, justamente el criterio que no debe guiar la elección. P2 conserva los umbrales que ya revisaste.

## D2. El 0,01: margen de relevancia económica, no nivel de significación

**Apariciones:**
- en la v2: líneas 17, 322, 325, 327, 331–332, 335, 338, 388 y 468;
- en v1: línea 101;
- en `INFORME_E3.md`: líneas 128, 140, 361 y 423 (la 361 menciona además el período ya retirado);
- en los cambios para la v3: líneas 264 y 276.

En todas significa lo mismo: **el menor IC̄ (correlación de rangos media semanal) que se considera económicamente relevante.**
- **No es** un nivel de significación: α es 5 % en todos los casos.
- **No es** el umbral para confirmar H1: H1 se confirma con IC > 0.

**Coherencia:**
1. **Con el IC90:** su extremo superior es el límite unilateral del 95 %, así que «en contra» es una prueba **unilateral de no relevancia al 5 %**. La v2 la llama «equivalencia (TOST)»: es **incorrecto**, porque una TOST necesita dos márgenes. Hay que corregir el nombre.
2. **Con el error estándar:** usa el **mismo** de Newey–West que el contraste de H1 (4 rezagos, u 8 si la calibración lo exige). No tiene relación con el bootstrap de H2.
3. **Con Holm:** las conclusiones de «en contra» quedan **fuera** del control de familia. Es aceptable porque su única consecuencia es el cierre, que es también el destino de «insuficiente». Hay que **declararlo**.
4. **Brecha que se informa, sin criterio nuevo:** con los errores esperados (≈ 0,007–0,0095), confirmar H1 implica un IC̄ puntual ≳ 0,012–0,019, pero el límite inferior puede quedar por debajo de 0,01.
   - El informe dirá «relevancia demostrada» solo si el límite inferior del IC90 es ≥ 0,01;
   - si no, dirá «información detectable, relevancia no demostrada».

**Formulación propuesta, sin relajar nada:**
> δ_IC = 0,01 es el margen de relevancia económica, en unidades de IC̄. **EN CONTRA (H1):** IC̄ + 1,645 · EE_NW < δ_IC, una prueba unilateral de no relevancia al 5 % que queda fuera de la familia de Holm. **INFORMACIÓN CONFIRMADA:** H1 (IC > 0) rechazada con Holm. Si además el extremo inferior del IC90 es ≥ δ_IC, la relevancia queda demostrada; si no, no.

## D3. Liquidaciones: confirmado que no son precios ejecutables, con tres restos por corregir
- **Los cambios para la v3** (§5.3) dicen explícitamente que el último precio negociado es una **liquidación contable, no un precio ejecutable**, registrada el día 30 de inactividad, sin mirar al futuro.
- **Pero la v2 conserva redacciones de ejecución:**
  - §4.9: «se **vende** al último cierre activo»;
  - §3.3, ítem 24: «salida al último cierre activo»;
  - R6: «salidas por fin de cotización».
  - Deben decir «liquidación contable al último precio negociado (no ejecutable)».
- **Cómo se informa:**
  - **principal:** liquidación contable al último precio negociado, menos el costo de su tramo, rotulada como supuesto;
  - **estrés R6:** −30 % sobre ese valor, como condición de robustez (exceso neto > 0).
- **Cómo se detecta si determinan el resultado** (descriptivo, sin criterio nuevo):
  1. cantidad de liquidaciones (estrategia y EW-U30) y de marcas obsoletas (H1 y H2);
  2. aporte de esos eventos al exceso acumulado de H2 y a IC̄;
  3. etiqueta **«resultado dependiente de liquidaciones o marcas obsoletas»** si, al anular esos aportes, cambia el signo de la estimación puntual de H2 o de IC̄.
  - No cambia la clasificación: la defensa ya prerregistrada es R6.

## D4. Bootstrap: coherente, con tres detalles técnicos por fijar
**Lo que verifiqué:**
- **Centrado bajo el nulo:** al restar ē a cada observación, la media de cada réplica baja exactamente en ē y la varianza por bloques no cambia. Entonces T* = (ē*_sin centrar − ē) / (σ̂*/√n).
- **Una sola distribución para todo:** el valor p (bajo H₀) y el intervalo percentil-t (alrededor de ē) usan **la misma** distribución de T*. Son duales.
- **Sin sesgo en el esquema circular:** cada observación tiene la misma probabilidad de entrar, también en el último bloque recortado, así que E*[ē*] = ē exactamente.
- **Varianza consistente:** la varianza exacta del bootstrap de √n·ē* es σ̂²_C, el mismo estimador del estadístico observado.

**Detalles que hay que fijar:**
1. **Bloques completos:** k = ⌈n/13⌉ bloques enteros, réplica de largo k·13 y estadístico escalado por √(k·13). Un bloque recortado distorsiona σ̂*.
2. **Divisor k − 1** en σ̂*² = ℓ/(k−1) · Σ(B̄*_j − ē*)². Con k, se subestima en ≈ 4 % y se infla T*.
3. **Cuantiles por estadístico de orden:**
   - q*_{0,95} = T*₍₉₅₀₀₎ y q*_{0,975} = T*₍₉₇₅₀₎, con B = 9999;
   - con p = (1 + #{T* ≥ T}) / (B + 1), se cumple **exactamente** que p ≤ 0,05 ⇔ el extremo inferior del IC90 > 0 (y lo mismo al 0,025).

**Qué demuestra la calibración sintética:**
- que el código del contraste es correcto;
- que su tamaño es cercano al nominal (±2 errores de Monte Carlo) para n = 340 y bloques de 13, con colas pesadas, autocorrelación, GARCH y asimetría en los dos sentidos;
- y fija de antemano una regla que solo puede volverlo más conservador.

**Qué no demuestra:**
- que el tamaño sea correcto para el proceso **real** de los excesos (cambios de régimen, caídas agrupadas, dependencia larga);
- nada sobre potencia realista, supervivencia, costos, liquidaciones ni mirada al futuro.
- El diagnóstico con carteras aleatorias aporta evidencia parcial con datos reales, pero su media nula es solo aproximada.

## D5. Potencia: de dónde sale el 0,11–0,17, y su consecuencia
**Supuestos [Hip], ninguno medido:**
1. **Tracking error** de la cartera de 6 monedas frente a EW-U30 de **25–35 %/año**: volatilidad idiosincrática semanal ≈ 10–12 % frente a la canasta, dividida por √6.
2. **Duración:** 6,5–7 años; por lo tanto, EE = tracking error / √años ≈ **9,4–13,7 %/año**.
3. Aproximación normal de la media, sin autocorrelación adicional.
4. Contraste unilateral a **α = 0,025**, el primer paso de Holm.

Con μ = 10 %/año: potencia = 1 − Φ(1,96 − μ/EE) = **0,17 (EE 10 %) a 0,11 (EE 14 %)**.

**Lo que hace variar la cifra:**
- Si H2 se prueba en el segundo paso (α = 0,05): **0,18–0,26**.
- Si la volatilidad idiosincrática semanal real fuera 14–20 % (plausible en altcoins): tracking error ≈ 41–59 %/año y potencia **0,06–0,09**.
- Si la regla de supervivencia acorta la ventana, la potencia baja más.

**Probabilidad de un resultado «respaldado»** con una ventaja real del 10 %/año y un IC de 0,02 (coherente con ese neto): está acotada por la menor de las dos potencias, **≤ 0,11–0,26**, y es menor aún con la robustez.

**¿Sirve para decidir una inversión? No.** El diseño puede aportar evidencia para una **decisión de investigación**:
- confirmar o descartar que existe información transversal en monedas líquidas (H1 tiene ≈ 80 % de potencia para IC ≳ 0,02–0,027);
- cerrar la familia si sale «en contra».

No puede aportar evidencia suficiente para comprometer capital:
- la ventaja neta realista (5–20 %/año) queda casi seguro en «insuficiente»;
- la historia está contaminada por el conocimiento del período;
- la ejecución real no se observa.

Incluso en el mejor caso, la confirmación independiente exige papel prospectivo de **≈ 2–3,5 años** (con IC 0,03) a **4–8 años** (con IC 0,02). El protocolo ya dice que ninguna clasificación autoriza capital: es coherente.

## D6. ¿Merece E3 la fase de datos? Recomendación
- **Sí, como pregunta de investigación barata**, y solo si aceptás de antemano que:
  - el producto esperable es información sobre el mecanismo, no una estrategia invertible;
  - el resultado más probable para la rentabilidad neta es «insuficiente»;
  - si H1 no se confirma, la familia se cierra sin variantes.
- **Costo:** datos gratuitos, unas horas de descarga, sin dependencias nuevas.
- **Valor:** es la única fuente de información no probada que es viable con datos oficiales y gratuitos, y su prueba predictiva tiene potencia útil.
- **No**, si lo que necesitás es una candidata para capital en uno o dos años. E3 no puede darla. Hoy la única línea en ese camino es T en papel.

## Inconsistencias que siguen abiertas
| # | Dónde | Inconsistencia |
|---|---|---|
| I1 | v2 §3.1 y §7.3 (A1) | La elección de multiplicidad sigue abierta → se cierra con D1 |
| I2 | v2 §5.1 | «Prueba de equivalencia (TOST)» es un nombre incorrecto; no se declara que «en contra» queda fuera de Holm; no se dice qué error estándar usa el IC90 si la calibración cambia los rezagos |
| I3 | v2 §4.9, §3.3-24, §5.3-R6 | Redacción de «venta» para lo que es una liquidación contable |
| I4 | Cambios v3 §1.2 | Bloque recortado, divisor k y convención de cuantiles sin fijar |
| I5 | v2 §5.5 | La potencia de H2 se da solo para α = 0,025, sin listar los supuestos ni la cota conjunta |
| I6 | `INFORME_E3.md` | Partes superadas que siguen como texto vigente: período 2019–2024 con reserva 2025–2026, Holm m = 3 con la capa de efectivo, efecto mínimo de H2 de 35–45 % y fila 1 del ranking. No se edita (es un registro), pero la v3 debe declararlas reemplazadas |

## Correcciones indispensables antes de congelar (las únicas)
1. **Multiplicidad:** fijar P2 (D1) y quitar la opción abierta de §3.1 y A1.
2. **0,01:** reemplazar el texto por la formulación de D2.
3. **Liquidaciones:** unificar la redacción como «liquidación contable al último precio negociado (no ejecutable)» en §4.9, el ítem 24 y R6. Agregar la etiqueta descriptiva de dependencia (D3).
4. **Bootstrap:** bloques completos con escala √(k·ℓ), divisor k − 1 y cuantiles por estadístico de orden (D4), también para H3 y los intervalos descriptivos.
5. **Potencia:** reemplazar el párrafo de H2 por el de D5: supuestos, α por paso, sensibilidad al tracking error, cota conjunta y «no sirve para decidir una inversión».
6. **Cabecera de la v3:** lista de las secciones de `INFORME_E3.md` y de la v1 que quedan reemplazadas (I6).

**Nada de esto cambia** umbrales, ventanas, universos, horizontes ni criterios. Tampoco agrega pruebas.
