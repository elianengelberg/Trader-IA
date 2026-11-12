# Matriz metodológica E3, v2 (corrige la v1 según la verificación separada)

**Autor:** el mismo agente de la reparación y del diseño v4. **No es independiente.**

**Origen de esta versión:**
- La v1 (`MATRIZ_METODOLOGICA.md`, sha256 `825f141e…`, que no se modificó) la verificó un agente separado, de otro modelo: `verificacion_matriz/VERIFICACION_MATRIZ.md` (sha256 `189c8a00…`).
- Esa verificación dio 92 afirmaciones: 78 confirmadas, 6 refutadas y 8 no verificables.
- Las 6 refutaciones las comprobé yo contra las fuentes antes de corregir (§E de esta matriz).

**Ningún retorno, IC ni estadístico de H1/H2 se calculó ni se consultó.**

## Cambios respecto de la v1

| Id | Corrección | Cómo la verifiqué |
|---|---|---|
| V91 | **Retiro la conclusión «las 158 semanas no salen de ninguna aplicación universal».** La segunda pasada releyó con N5 los 47 eventos del universo, no solo la muestra: 37 confirmados, 4 con fecha corregida, 5 C explicados y 1 descartado | `vs3` tiene 47 entradas y solo 10 con `muestra_pasada1: true` |
| V51 | La corrección de DOTUP **sí** tiene base textual: la muestra V-S3 es una de las listas de A3.11 cuyos casos «se resuelven con una cita» y cuya segunda pasada «es definitiva» (`ADENDA_3`, l. 89–91). Con DOTUP sola (E 2023-05-10), el inicio ya es 2023-05-15 | — |
| V40 / V41 | **N5 frente a A3.1.5 afecta solo a 4 eventos**, todos del mismo anuncio de apalancados (título con la fecha de publicación 2023-04-27). Mi heurística marcó 30, pero las fechas extra son de retiros, conversión a stablecoins, Margin o la barra lateral. Eran 14 eventos con fecha posterior, no 15 | Leí YFII (2023-11-22: retiros), ANT (2024-05-21: conversión) y HNT (2022-10-06: publicación) |
| V81 | La cota de P(RESPALDADA) es **≤ 0,13–0,17** con 158 semanas y ≤ 0,16–0,23 con 274. Con Holm, m = 2, hace falta que ambas se rechacen: el p mayor tiene que ser ≤ 0,05, así que vale la potencia de H2 a α = 0,05 | — |
| V07 | La cita «no cambia categorías…» de la Adenda 3 está en la l. 8 | — |
| R1′ | La rama «R1′ → BKRW fija el inicio» estaba desactualizada: la segunda pasada **descartó** BKRWUSDT (el anuncio corrige el par a USDT/BKRW). Además, R1′ fue **retirada por el propio autor**: `INFORME_DECISION_E3H1H2.md` l. 33, «El 26/10 recomendé B. **Fue un error.**»; l. 22, «La ventana **B queda descartada en forma definitiva**» | Verificado |
| Omitidos | «Selectiva» estaba exagerado. La reparación revisó todas las páginas de exclusión con fecha ≥ 2023-04-28 (`REP/INFORME_REPARACION_E3H1H2.md`, l. 64): un criterio declarado y acotado a lo que puede mover A | — |

---

## Matriz de decisiones

### 1. Reapertura de E3 y adopción de la Adenda R

**Reglas originales:**

| Regla | Ubicación |
|---|---|
| «No se relajó la regla (iv)» | `CIERRE_E3`, l. 15 |
| «**E3 no continúa.** Reabrirlo […] requiere una autorización expresa» | `CIERRE_E3`, l. 19 |
| «Haría falta una lista completa y verificable…» | `CIERRE_E3`, l. 30, que remite al §8 de `INFORME_EJECUCION_E3.md` (l. 225–239) |

El §8 del informe de ejecución propone cinco opciones:

| Opción | Qué implica |
|---|---|
| (a) | Compilación manual de la categoría Delisting |
| (b) | `web.archive.org` |
| (c) | Lectura automatizada autorizada |
| (d) | Fuente no oficial, con adenda |
| (e) | Cerrar |

Recomienda **(a) si es razonable, si no (e), y «no relajar la regla (iv)»**.

**Interpretación literal:** E3 está cerrado. Para reabrirlo hacen falta tu autorización expresa y la lista completa, que no existe después del 2024-11-06.

**Alternativas:**

| Alternativa | Qué implica |
|---|---|
| No reabrir | (e): E3 queda NO EVALUABLE |
| Reabrir con la Adenda R tal como está | Revertir el CIERRE §2 en lo que toca a (iv) y dispensar el §4. El mecanismo de dispensa está previsto en `ADENDA_R` l. 73 («requiere tu autorización expresa») |
| Reabrir con la Adenda R más salvaguardas | Una adenda nueva, congelada antes de cualquier resultado |
| Obtener la lista por (a)–(d) | Según el §8 |

**Evidencia a favor de la Adenda R** (`ADENDA_R` §1, l. 7–19):
- (iv) falla por la cobertura del archivo web, no por Vision;
- ninguna exclusión archivada quedó en la categoría D;
- BKRW nunca figura en `elegibles` en ninguno de los 439 lunes, según el verificador.

Por lo tanto, la premisa de §1 («ninguno puede entrar en un universo») **es correcta en los hechos**. El defecto está en cómo la R1 la operacionalizó (punto 2).

**Evidencia en contra:**
- se escribió conociendo que M0 fallaba y los conteos por año (§5, l. 68–71);
- (iv′) es circular;
- no hay observación posterior al 2024-11-06;
- el autor del §8 recomendó **no** relajar (iv).

**Orden entre la congelación y P0:**
- `CONGELACION_ADENDA_R.txt` y `REGISTRO_P0.txt` declaran 19:43:13Z y 19:44:40Z;
- `REGISTRO_P0.txt` se reescribió después: su fecha de modificación es 19:47:23 y lista scripts posteriores;
- el registro de la sesión no muestra cálculos con las marcas de R antes de la congelación.

Todo esto es **inferido**: el registro lo genera el mismo entorno.

**¿Hace falta una regla nueva?** Una dispensa escrita y firmada, o una adenda.

**Te corresponde:** reabrir o no; adoptar la Adenda R o no; dispensar o no el CIERRE §4.

### 2. R1 literal frente a R1′

**Reglas originales:**
- R1 (`ADENDA_R`, l. 22–26): fuera de alcance si el par figura en las listas de F3 del último lunes ≤ L o E. Fundamento: «nunca son elegibles (§4.5)».
- v3 §4.5, l. 238: «La lista se congela en F3».

**Hechos:**
- Las listas por lunes no contienen a TRXDOWN, DOTUP, DOTDOWN ni LINKUP (verificado en 2023-04-24 y 2023-05-08), así que con la R1 literal quedan en alcance.
- La R1′ (`86c8fd0b…`) se congeló después de P0 y está motivada por la potencia (su propio texto).
- Se recomendó en `PLAN_EJECUCION_UNICA_E3R.md` (l. 68 y 77) y **el autor la retiró** («Fue un error»: `INFORME_DECISION`, l. 33; «B descartada en forma definitiva»: l. 22).

**Consecuencias:**
- **R1 literal:** el inicio lo fijan las fallas de apalancados de 2023-04/05 (punto 3).
- **R1′ con la segunda pasada** (BKRW descartado): no quedan fallas en alcance conocidas, así que (ii′) dejaría de ser la restricción. El inicio lo fijarían (i) = 2020-05-11 y (iv′). **No lo recalculé.** Es inferido a partir de la lista de fallas de la primera pasada: 4 T (3 apalancados más BKRW), 5 C explicadas y ninguna D.

**¿Hace falta una regla nueva?** Elegir R1′ es adoptar una regla posterior a P0, que el propio autor ya descartó.

**Te corresponde:** R1 literal o R1′.

### 3. A3.1.5 frente a N5

**Reglas originales:**

| Regla | Ubicación |
|---|---|
| N5: E = «el día UTC en que cesa la negociación spot del par, según el texto» | `NOTAS`, l. 16 |
| A3.1.5: «**Fecha efectiva E** (N5): la primera fecha del título» | `ADENDA_3`, l. 18–19 |
| La Adenda 3 «no cambia […] criterios» y en «Qué no cambia» no nombra a las notas | `ADENDA_3`, l. 8 |
| La v3 prevalece | v3 §0.2, l. 32 |
| La v3 usa «fecha efectiva» sin definirla | — |

**Hechos:**
- La discrepancia afecta a **4 eventos**: TRXDOWN, DOTUP, DOTDOWN y LINKUP. Su título trae la fecha de publicación (2023-04-27) y el cuerpo, el cese (2023-05-09/10/11).
- La segunda pasada releyó con N5 los 47 eventos del universo.

**Interpretaciones:**
- **(I) A3.1.5 como regla operativa:** E del título, salvo lo que se resuelva en las listas de A3.11.
- **(II) N5 como definición:** corregir donde difieran.

Con la R1 literal, las dos llevan al **mismo inicio, 2023-05-15**, siempre que la resolución de la muestra V-S3 (punto 4) pueda corregir E.

**¿Hace falta una regla nueva?** Conviene una cláusula de precedencia entre N5 y A3.1.5 para casos futuros. Para A no cambia el resultado.

### 4. Correcciones fuera de las listas de A3.11 y la muestra V-S3

**Reglas originales:**

| Regla | Ubicación |
|---|---|
| Listas de revisión, entre ellas «la muestra de V-S3» | A3.11, l. 89 |
| «Se revisan todos los casos de cada lista» | A3.11, l. 90 |
| «Su resultado es el definitivo» | A3.11, l. 91 |
| V-S3: «se comparan a mano», sin consecuencia propia | A3.6, l. 62 |
| V-S2: «se usa la lectura corregida» | A3.6, l. 60 |

**Hechos:**
- DOTUP estaba en la muestra V-S3 (`muestra_pasada1: true`). Su corrección a 2023-05-10, por sí sola, fija el inicio en 2023-05-15.
- Las otras 3 correcciones y las 37 confirmaciones son de eventos fuera de la muestra. Su base es N5 y la v3, no A3.11.

**Variantes:**

| Variante | Resultado |
|---|---|
| (a) La V-S3 es solo un control y no corrige | 2023-05-01, 160 semanas (= P0 de la primera pasada) |
| (b) Se resuelven los casos de las listas de A3.11, incluida DOTUP | 2023-05-15, 158 semanas |
| (c) Lectura N5 universal, como hizo la reparación | 2023-05-15, 158 semanas |

**158 semanas es el resultado de (b) y de (c). 160 exige leer la V-S3 como un control sin corrección.**

**Riesgo que sí queda:** las lecturas de la segunda pasada las hizo el mismo agente, sin un protocolo de lectura congelado de antemano y conociendo qué estaba en juego. No cambian el inicio más allá de DOTUP, pero conviene que un tercero las verifique.

**Te corresponde:** elegir (a), (b) o (c).

### 5. Eventos omitidos

**Reglas originales:**
- universo = «todas las exclusiones o remociones» de pares USDT (v3 §2.3, l. 106–107);
- el código congelado no tiene mecanismo para agregar eventos (`REP/INFORME_REPARACION_E3H1H2.md`, l. 40).

**Hechos:**
- La reparación revisó todas las páginas de exclusión con fecha ≥ 2023-04-28 (l. 64) y agregó TRXUP y LINKDOWN solo al cálculo de la ventana.
- Las remociones anteriores a esa fecha (GTO, BTCST, SRM, TRIBE, KEY) no están como eventos. Por construcción **no pueden mover (ii′)**. Su efecto sobre (iv′) no se calculó.
- El escaneo por cuerpo en el que se apoya la reparación **no se volvió a ejecutar** (L-2: 929 títulos ilegibles).

**Alternativas:**

| Alternativa | Qué implica |
|---|---|
| (a) | Ningún omitido: procedimiento congelado |
| (b) | Búsqueda acotada a lo que puede mover A (lo que hizo la reparación, con criterio declarado) |
| (c) | Búsqueda completa para (iv′) |

**¿Hace falta una regla nueva?** Un procedimiento de búsqueda declarado.

**Te corresponde:** elegir (a), (b) o (c).

### 6. Continuidad: GTO→GFT, LUNA→LUNC y UST→USTC

**Reglas originales:**

| Regla | Ubicación |
|---|---|
| Listado vigente: termina con 30 días inactivos | v3 §2.2.3, l. 97–100 |
| Renombres: «el nuevo hereda la edad y las posiciones», solo con un anuncio oficial | v3 §2.2.4, l. 101 |
| Par USDT removido: cuenta como salida | v3 §2.2.5, l. 102 |
| Regla 1: «el listado vigente de X **termina** en la fecha efectiva. Y lo continúa […] y hereda la edad y las posiciones» | `ADENDA_1`, l. 8 |

**Hechos** (citas del cuerpo, verificadas en la revisión adversarial):

| Caso | Hechos |
|---|---|
| GTO→GFT | GTO/USDT removido el 2022-11-28; canje 1:1 completado el 2023-02-08; GFT/USDT el 2023-09-22 |
| LUNA→LUNC | 119 días, más la reutilización del ticker LUNA |
| UST→USTC | 301 días; está en la lista fija |

**Dos lecturas, ambas con apoyo textual:**
- **(a)** En E no había un listado vigente de X (§2.2.3 y §2.2.5), así que Y es un listado nuevo.
- **(b)** La herencia (§2.2.4 y la regla 1) no está condicionada a que el listado esté vigente, así que hay continuidad a pesar del hueco.

Las dos chocan con alguna regla (§2.2.3 o §2.2.4): **es un conflicto interno de la v3**.

**Efecto:** solo cambia la elegibilidad temporal de GFT dentro de A; no lo recalculé.

**¿Hace falta una regla nueva?** Sí, una aclaración general.

**Te corresponde:** elegir (a) o (b), como regla general.

### 7. Reintentos

**Reglas originales:**

| Regla | Ubicación |
|---|---|
| H = «una sola ejecución» | v3 §1, l. 73 |
| «1 ejecución confirmatoria»; «cualquier otra ejecución es exploratoria […] no cambia ninguna clasificación» | v3 §3.3, l. 175 y 180–183 |
| «**una** ejecución confirmatoria» | `ADENDA_R`, l. 61 |
| «**Sin repeticiones.** […] Toda corrida no planificada es exploratoria» | `PLAN_EJECUCION_UNICA_E3R.md`, l. 35 |

**Interpretación literal:** no hay reintento confirmatorio (política (iii)). Las políticas (i) y (ii) necesitan una regla nueva que diga que un intento fallido no es una «ejecución».

**Te corresponde:** elegir (i), (ii) o (iii).

### 8. Riesgos residuales y potencia

**Reglas originales:**
- v3 §7.1, l. 460–465: los supuestos [Hip];
- v3 §7.2, l. 467–481: «todas las potencias bajan, y se informa cuánto»;
- la v3 no fija una potencia mínima.

**Hechos** (`potencia_analitica.py`, reproducido byte a byte por el verificador):
- P0d se reproduce: H1, IC 0,02, n = 160, α 0,025 da 0,35–0,56.
- H2, exceso de 10 %/año: 0,07–0,10 (α 0,025) y 0,13–0,17 (α 0,05) con 158 semanas.
- **Cota: P(RESPALDADA) ≤ 0,13–0,17** con 158 semanas.

**Riesgos residuales:**
- la circularidad de (iv′);
- el punto ciego posterior al 2024-11-06;
- un margen de 2 semanas;
- el recall de renombres;
- el volumen de HIFI;
- lecturas manuales hechas por un solo agente.

**Te corresponde:** decidir si una ejecución con esta potencia es informativa para tu decisión, y aceptar o no cada riesgo. Un umbral mínimo de potencia sería una regla nueva y tendría que fijarse antes de cualquier resultado.

---

## Síntesis corregida

```
1. ¿Reabrir y adoptar la Adenda R?   (§8 del informe de ejecución: no relajar (iv))
   ── no ──▶ E3 cerrado: opción (e)
   ── sí ──▶ 2. ¿R1 literal o R1′? (R1′ retirada por su autor como error)
             ── R1′ ──▶ con la segunda pasada, (ii′) deja de restringir: inicio por (i) y (iv′), no recalculado
             └─ R1 literal ─▶ 4. ¿La muestra V-S3 puede corregir E?
                              ── sí, (b) o (c) ──▶ 2023-05-15, 158 semanas (margen de 2 semanas)
                              └─ no, (a) ──▶ 2023-05-01, 160 semanas
5 (omitidos), 6 (continuidad), 7 (reintentos) y 8 (riesgos) se deciden en cualquier rama.
```

**Conclusión corregida.** Hay dos lecturas razonables del procedimiento congelado, (b) y (c), y las dos dan 158 semanas. Las 160 exigen una lectura restrictiva de la V-S3.

**Lo que sigue sin resolver:**
- la ventana depende de decisiones que no autorizaste (1, 2 y 4);
- las lecturas manuales las hizo el mismo agente, sin un protocolo de lectura congelado;
- el margen es de 2 semanas;
- la potencia es baja;
- el archivo de ventana fijado en el v3 se calculó con la tabla de 22 (L-10) y no registra sus parámetros. Hay que recalcularlo y registrarlos antes de fijarlo en el v4.

## §E. Comprobaciones propias de las refutaciones

- `resoluciones_manuales.json` → `vs3`: 47 entradas; resultados: confirmar 37, C_explicada 5, fecha_corregida 4, descartar 1; `muestra_pasada1: true` en 10.
- BKRWUSDT: «descartar», con la cita «…to correct the BKRW/USDT trading pair to the USDT/BKRW trading pair». En `salida_pasada2/eventos.json`, categoría «descartado».
- `ADENDA_3`: la l. 8 tiene «Qué no cambia» y la l. 9 está en blanco.
- YFII (2023-11-22), ANT (2024-05-21) y HNT (2022-10-06): retiros, conversión a stablecoins y marca de publicación. No son el cese spot.
- `INFORME_DECISION_E3H1H2.md`: l. 33 («Fue un error») y l. 22 («B queda descartada en forma definitiva»).
- `INFORME_EJECUCION_E3.md` §8: l. 225–239.
- `REP/INFORME_REPARACION_E3H1H2.md`: l. 64 (revisión de las páginas con fecha ≥ 2023-04-28).
