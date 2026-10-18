# T-MULTI: la regla T, sin cambios, en 12 ETF no cripto (2013-01 → 2026-09): informe de decisión

**Categoría:** histórico con **procedencia limitada**: Yahoo como fuente primaria y Nasdaq como contraste; no es una fuente oficial con checksums. **No es prospectivo.** La regla T (`73b22f3e…`) y el experimento en papel no cambiaron.

## 1. Diseño definitivo y evidencia temporal
- **Diseño:** `PRERREGISTRO_T_MULTI.md` (`7781e725…`) y `experimentos/t_multi.py` (`17d6b947…`), congelados en el **commit local `f518ac1`** el 2026-10-17 a las 20:29:05 UTC. **No está publicado.**
- **Orden verificable:**
  - antes del commit, `datos_multi/` no existía;
  - la primera respuesta de los servidores trae `Date: Sat, 17 Oct 2026 20:29:14 GMT`, 9 s **después** del commit;
  - al evaluar, el prerregistro y el script no tenían cambios respecto del commit (registrado en el resultado).
  - **Límite:** la fecha del commit la declara el autor. Solo publicarlo la haría verificable desde afuera.
- **Regla:** T es **un único ensamble** de 1, 3 y 6 meses (`FAMILIAS_ESTRATEGIA.md`), con horizontes de {30, 90, 180} días corridos. **No hay variantes que comparar.**
  - El adaptador reproduce `tsmom` **exactamente** con BTC y ETH, y la métrica reproduce `_exceso` exactamente (autoprueba).
  - Decisión al cierre y ejecución en la apertura siguiente con `simular` congelado; 5 bps por lado.
- **Métrica:** E = exceso de timing frente a la estática con la misma exposición media, normalizado a 10 % de volatilidad ex ante, con el mismo peso por clase.
  - Incertidumbre: bootstrap por bloques de 60 sesiones y Newey–West con 60 retardos; para decidir se toma el menor P y el mayor límite superior.
- **Cambios respecto del borrador, todos anteriores al congelado:**
  - fuente primaria Yahoo y contraste Nasdaq, porque Stooq y FRED no eran alcanzables;
  - precedencia explícita de «sin ventaja relevante»;
  - variante descriptiva sin costes;
  - límites de plausibilidad de los dividendos (≤ 15 % y ≤ 20 % anual) y montos nulos ignorados;
  - bloqueo si falta alguna serie de Yahoo.
  - Todo se probó con datos sintéticos, incluido un escenario con tendencia inyectada, que el circuito detectó como «respaldada».

## 2. Procedencia, cobertura y validación
- **36 respuestas HTTP 200** (12 ETF × Yahoo, precios de Nasdaq y dividendos de Nasdaq). Están guardadas con su SHA-256 y su cabecera `Date` en `datos_multi/MANIFIESTO.json` (`c64f3bf4…`, 8,4 MB, sin versionar).
- **Cobertura:** 3 959 sesiones de referencia del 2011-01-03 al 2026-09-30; **0 faltantes** en los 12 ETF; sin sesiones inválidas ni repetidas.
- **Ajustes:**
  - el factor de rendimiento total reconstruido con los dividendos del proveedor coincide con su `adjclose` con un error máximo de **1,2·10⁻⁶**;
  - el split 1:8 de USO del 2020-04-29 está recogido;
  - no hay saltos de más del 35 %.
- **Contraste con Nasdaq:**
  - precios: 2 502 días comunes (≈ 2016-10 → 2026-09); entre el 99,96 y el 100 % coinciden con un margen de ±0,5 %;
  - dividendos: Nasdaq solo los entregó para SHY, IEF y TLT.
- **Exclusión de TLT, aplicada tal como estaba congelada:** el 91,4 % de sus dividendos de Yahoo tiene pareja en Nasdaq, y se exige el 95 %.
  - Las 16 diferencias son todas de **2011–2012**: faltan en el historial de Nasdaq. Desde 2013 coinciden todas, así que la causa probable es un hueco de la fuente de contraste.
  - No agregué una variante con TLT, porque sería un cambio posterior al congelado.
  - Con 11 ETF (bonos: SHY, IEF y LQD) el experimento era ejecutable (`VALIDACION.json`: `770e8dcb…`).

## 3. Resultados y benchmarks
**Primario** (3 457 sesiones; ninguna excluida por falta de clase):

| | E (%/año a 10 % de vol.) | IC90 bootstrap | P bootstrap / Newey–West |
|---|---|---|---|
| **Conjunto (11 ETF)** | **−0,48 %** | −1,55 % / +0,65 % | **0,239 / 0,242** |
| Renta variable | −0,84 % | −2,00 % / +0,48 % | 0,144 |
| Bonos | −1,46 % | −3,48 % / +0,67 % | 0,125 |
| Materias primas | +0,86 % | −0,58 % / +2,43 % | 0,833 |

- Sin cada clase: sin renta variable −0,30 %; sin bonos +0,01 %; sin materias primas −1,15 %.
- **Contribución de cada activo a E** (es una identidad: suman exactamente −0,48 pp): SHY **−0,60**, EFA −0,09, IWM −0,08, SPY −0,08, SLV −0,04, EEM −0,03, GLD +0,04, IEF +0,05, LQD +0,06, DBC +0,14, USO +0,15.

**Frente a los benchmarks** (CAGR neto, Sharpe, caída máxima; 2013-01 → 2026-09):

| ETF | T | Estática (misma exposición) | Buy and hold | Exposición T | Operaciones |
|---|---|---|---|---|---|
| SPY | 9,3 % · 0,95 · 17 % | 11,5 % · 0,91 · 27 % | 14,8 % · 0,91 · 34 % | 0,77 | 467 |
| IWM | 4,9 % · 0,43 · 29 % | 7,2 % · 0,57 · 29 % | 10,3 % · 0,57 · 41 % | 0,66 | 636 |
| EFA | 3,1 % · 0,36 · 18 % | 5,3 % · 0,52 · 24 % | 7,5 % · 0,52 · 34 % | 0,67 | 518 |
| EEM | 2,6 % · 0,27 · 29 % | 3,5 % · 0,35 · 25 % | 5,2 % · 0,35 · 40 % | 0,59 | 528 |
| SHY | 0,5 % · 0,51 · 5 % | 1,0 % · 0,95 · 4 % | 1,3 % · 0,95 · 6 % | 0,71 | 526 |
| IEF | 0,5 % · 0,14 · 13 % | 0,6 % · 0,17 · 14 % | 0,9 % · 0,17 · 24 % | 0,56 | 595 |
| LQD | 1,2 % · 0,30 · 14 % | 1,5 % · 0,33 · 16 % | 2,3 % · 0,33 · 25 % | 0,61 | 547 |
| GLD | 4,2 % · 0,41 · 26 % | 3,9 % · 0,45 · 24 % | 6,4 % · 0,45 · 39 % | 0,57 | 575 |
| SLV | −0,4 % · 0,10 · 50 % | 3,4 % · 0,29 · 37 % | 4,4 % · 0,30 · 64 % | 0,50 | 599 |
| USO | 3,8 % · 0,28 · 55 % | −0,6 % · 0,07 · 76 % | −4,5 % · 0,07 · 95 % | 0,53 | 566 |
| DBC | 3,4 % · 0,35 · 40 % | 1,6 % · 0,22 · 39 % | 2,3 % · 0,22 · 62 % | 0,53 | 559 |

- **Renta variable y bonos:** T rinde menos que la estática y que buy and hold; solo reduce la caída máxima frente a buy and hold.
- **Materias primas con tendencias largas** (USO, DBC; GLD frente a la estática): T rinde más.
- **El efectivo** rinde 0 %.

## 4. Incertidumbre, robustez y limitaciones
- **Robusto al método:** con bloques de 20 y de 120, P = 0,23–0,24. Newey–West coincide (0,242). Con un retraso de 1 sesión, E = −0,52 %.
- **Correlación:** 0,48 dentro de cada clase y 0,12 entre clases → **3,5 activos efectivos**, en línea con lo supuesto en el diseño.
- **Costes:** E es exactamente lineal en el coste: −0,29 pp por bp por lado.
  - **Sin costes**, E = **+0,97 %** (IC90 −0,06 % / +2,06 %, P = 0,938); con costes ×2, −1,93 % (P = 0,007); con ×3, −3,38 %.
  - El resultado se anula con **≈ 3,3 bps** por lado (interpolación aritmética).
  - Los 5 bps se fijaron como «conservadores»: el costo real de SPY, IEF o SHY probablemente es menor. **Con un coste realista algo menor, el signo podría cambiar.** Es una inferencia, no un resultado prerregistrado.
- **SHY domina el resultado negativo:** su volatilidad es de 1,4 %, así que la normalización multiplica ≈ 7 veces el peso de sus costes. Es una consecuencia del diseño fijado de antemano (por eso el prerregistro advertía sobre SHY).
- **T opera mucho:** unas 38 veces por año y activo, en pasos de ⅓.
- **Otras limitaciones:**
  - un solo período (2013–2026);
  - el diseñador conoce a grandes rasgos sus tendencias;
  - procedencia no oficial, con el contraste de Nasdaq solo para ≈ 10 años de precios y 3 ETF de dividendos;
  - TLT excluido;
  - long/flat sin divisas.

## 5. Veredicto prerregistrado: **EVIDENCIA INSUFICIENTE**
- **No es «respaldada»:** P = 0,24 < 0,95; con costes ×2 el resultado es negativo; y sin materias primas también es negativo.
- **No es «sin ventaja relevante»:** el límite superior es +0,65 %, por encima del umbral de 0,5 %, **por poco**.
- **Lo que sí queda excluido** (con un 95 % unilateral): una ventaja **neta** transferible de 0,65 %/año o más a 10 % de volatilidad. Eso incluye el tamaño estimado en cripto, ≈ 1,24 %.
- **Lo que no queda excluido:** un valor **bruto** de timing de ≈ +1 %/año (P = 0,94), que los costes eliminan con la rotación de T.

## 6. Archivos y Git
- **Commit local `f518ac1`, no publicado:** `PRERREGISTRO_T_MULTI.md` y `experimentos/t_multi.py`.
- **Creados después, sin versionar:**
  - `datos_multi/`: respuestas crudas, `MANIFIESTO.json` y `VALIDACION.json`;
  - `experimentos/t_multi.json`, el resultado (`9bb4a55c…`);
  - este informe.
- **Sin cambios:** `src/`, las reglas, el experimento en papel y `ARTEFACTOS_SHA256.txt`.
- **Git:** sin push. La rama local va 1 commit por delante de origin.

## 7. Recomendación
Aplico la consecuencia declarada de antemano: **se cierra la investigación histórica de T.**
- **El experimento en papel sigue sin cambios**, como único control, sin costo.
- **No conviene ajustar parámetros de T con estos datos.** Una versión de menor rotación sería una **hipótesis nueva** motivada por este resultado: solo podría evaluarse de forma prospectiva y con su propio prerregistro.
- **Conclusión para el proyecto:** ninguna de las estrategias evaluadas (H-CARRY, V, T) muestra una ventaja neta demostrada. **No hay base para asignar capital real.**
