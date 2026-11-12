# E3: notas de implementación de la v3 (escritas ANTES de descargar cualquier dato de altcoins)

**Qué son:** concreciones técnicas de puntos que la v3 deja sin fijar. **No cambian** ningún umbral, ventana, universo, horizonte, costo ni criterio de decisión. Si una nota contradijera la v3, prevalece la v3. Todas se fijan con su SHA-256 en `CONGELACION_v3.txt`, antes de descargar datos.

## Datos y calendario
- **N1.** Fechas en UTC. La vela 1d de d tiene apertura a las 00:00 de d.
  - La unidad de tiempo (ms o µs) se detecta por magnitud (> 10¹⁴ ⇒ µs).
  - **Duración válida:** cierre − apertura = 86 400 000 − 1 ms (o su equivalente en µs). Cualquier otra duración ⇒ día inactivo (v3 §2.2).
- **N2.** Los CSV de Vision se leen sin suponer encabezado: una primera fila no numérica se descarta y se cuenta.
  - **Columnas:** 0 apertura, 1 O, 2 H, 3 L, 4 C, 5 volumen base, 6 cierre, 7 volumen en USDT, 8 operaciones.
  - Una fecha repetida dentro de un mismo archivo ⇒ esas filas se marcan como inválidas y el día queda inactivo.
- **N3.** **Volatilidad anual** de la regla de exclusión (v3 §4.5) = desvío de los retornos logarítmicos diarios entre días activos consecutivos × √365.
- **N4.** **«Primer lunes de formación de cada mes»** (v3 §4.8) = un lunes t cuyo mes calendario difiere del de la formación anterior.

## Supervivencia y anuncios
- **N5.** **Fecha efectiva E** de un anuncio = el día UTC en que cesa la negociación spot del par, según el texto. Si el texto da solo la fecha del anuncio y «en N días», E = anuncio + N. Si no se puede fijar, el caso es «E» (ambiguo) y se resuelve según la v3 §2.3.
- **N6.** **Clasificación de un anuncio** (par s, fecha E):
  - **C:** s tiene algún día activo en (E + 1, E + 30].
  - **D:** s no está en el listado del bucket o no tiene ningún día activo ≤ E + 1.
  - Si no es C ni D, L = último día activo de s ≤ E + 1:
    - **A:** L ≥ E − 7;
    - **B:** L < E − 7 y existen todos los archivos mensuales de s desde el mes de L hasta el mes de E (o hasta 2026-05);
    - **T:** L < E − 7 y falta alguno de esos archivos.
  - Un C con un relisting documentado posterior queda como «C explicada».
- **N7.** **«Salida observada»** = fin de un listado vigente: último día activo L seguido de ≥ 30 días inactivos, con L ≤ 2026-05-01, para que los 30 días sean observables.
  - La salida es **«con anuncio»** si algún anuncio compilado (exclusión del par, exclusión completa del token base o renombre de ese símbolo) tiene su E en [L − 1, L + 365].
  - Si no, es **«sin anuncio»**.
  - Las salidas por renombre mapeado no cuentan como salidas.
- **N8.** **Fuente de anuncios.**
  - Las condiciones de uso de Binance no se pudieron leer: la página devuelve un desafío anti-bots (HTTP 202 sin contenido). Una referencia secundaria indica que las de Binance.US prohíben el scraping automatizado.
  - El robots.txt de binance.com permite a cualquier agente la raíz `/` y los sitemaps, y prohíbe `/bapi/` y `/api/`.
  - **Decisión** (v3 §9: «si no lo permiten, la compilación es manual»): **no** se automatiza la lectura de binance.com.
  - La compilación usa **copias archivadas en el Internet Archive** (Wayback Machine; API CDX pública), que la autorización admite como «evidencia archivada verificable».
  - Cada caso registra la URL original, la URL archivada y la fecha de captura.
  - Si el archivo no alcanza, la limitación se informa y se aplican las reglas de inicio de la v3 §4.11 (iii)–(iv) y de validez; **no** se sustituye por otra fuente.

## Calibración, inferencia y descriptivos
- **N9.** **H1:** proceso de calibración AR(1) con φ = 0,1 e innovaciones **normales**, desvío marginal 0,14, n = 340 y 500 observaciones de arranque descartadas.
- **N10.** **H2 y H3:** procesos de la v3 §5.3, con 500 observaciones de arranque descartadas para G2 y G3.
  - Las innovaciones t se estandarizan a varianza 1.
  - G3: ω = 0,05² · (1 − 0,10 − 0,85).
  - G4 tiene desvío ≈ 4,9 %; se usa tal cual (media exactamente 0 por construcción).
- **N11.** **Newey–West:** γ̂_h = (1/n) Σ_{t>h} (x_t − x̄)(x_{t−h} − x̄).
- **N12.** **Nulo aleatorio (R5):** cada semana se asigna a las monedas de U30 un orden uniformemente aleatorio, que reemplaza a rk. Misma mecánica que la cartera.
  - Comparación **bruta**: costos 0 para la réplica y para EW-U30.
- **N13.** **Diagnóstico de la v3 §5.4:** semilla 20261027 y B = 999, por réplica.
- **N14.** **Aporte de cada moneda (R4)** = Σ_t w_{c,t} · (r_{c,t} − r_{EW,t}), en bruto:
  - w_{c,t} = peso de c en la cartera tras ejecutar en t;
  - r_{c,t} = retorno bruto de apertura a apertura de c entre t y t + 7;
  - r_{EW,t} = retorno bruto de EW-U30 en esa semana.
- **N15.** **Tramo de una liquidación contable** por inactividad: 30 pb de spread y slippage más 10 pb de comisión (el par ya no es elegible).
- **N16.** **R6:** el recorte del −30 % se aplica a las liquidaciones contables de la cartera **y** de EW-U30 (el mismo motor).
- **N17.** **Grilla de sensibilidad (v3 §3.4, ítem 29), solo descriptiva:**
  - para k ∈ {4, 10}, la banda de permanencia es 2k;
  - N define el universo invertible U_N (las primeras N por V) y su referencia EW-U_N;
  - los tramos se asignan por la posición de V, y las posiciones > 30 pagan 30 pb;
  - «cada horizonte»: S se calcula con un solo h;
  - «sin banda»: permanencia con rango ≤ k;
  - «miércoles»: formación el miércoles a las 00:00 con datos hasta el martes, ejecución en la apertura del miércoles;
  - se informan el exceso neto anualizado frente a EW-U_N y el Sharpe.
- **N18.** **Sharpe deflactado** (Bailey y López de Prado, 2014), descriptivo:
  - N = configuraciones evaluadas (20, o 21 con H3);
  - V[SR] = varianza muestral de los Sharpe semanales del exceso en esas configuraciones;
  - se usan la asimetría y la curtosis del exceso semanal.
- **N19.** **Exceso de timing de T** (descriptivo, v3 §6.2):
  - se calcula con el código congelado de T (`tendencia.senal.tsmom`, `backtest.simular`, `Costes()`) sobre los archivos locales de BTC y ETH, sin modificarlos;
  - el exceso diario es la regla menos la estática con la misma exposición media, en la ventana H;
  - se agrega por semana (lunes a domingo), compuesto, y se promedia entre BTC y ETH.
- **N20.** **BTCUSDT y ETHUSDT:** se leen de `research/tendencia_btc/datos/` (solo lectura), verificando cada `.CHECKSUM`.
- **N21.** **Fin de la ventana H:** las posiciones abiertas al 2026-05-25 se valúan en W de esa apertura; no se liquidan.
- **N22.** **Etapas:** el código de calidad (`calidad.py`) no importa el módulo de rendimiento (`motor.py`). Una prueba lo comprueba analizando los imports.
