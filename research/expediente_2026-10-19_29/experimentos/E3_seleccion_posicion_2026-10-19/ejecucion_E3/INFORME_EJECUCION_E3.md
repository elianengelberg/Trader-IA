# E3: informe consolidado de A1, A2 y A3, y decisión de habilitación

**Fecha:** 2026-10-20 (UTC). **Protocolo:** `PROTOCOLO_E3_v3_PROPUESTO.md` (`279a865f…`), congelado sin cambios. **Directorio:** `scratchpad/experimentos/E3_seleccion_posicion_2026-10-19/ejecucion_E3/`.

---

## 0. Decisión

**E3 NO está habilitado para una evaluación confirmatoria.**

- **Motivo:** con las fuentes públicas y utilizables, la v3 declara la ventana histórica H **INVÁLIDA con Vision**.
  - La regla de inicio §4.11 (iv) no tiene solución: **en todos los años**, de 2018 a 2026, las salidas sin anuncio archivado superan el 10 %.
  - En 2025 y 2026 son el **100 %** (51 y 26 salidas), y eso no lo cambia ninguna lectura manual: la última fecha efectiva de un anuncio archivado es el 2024-11-06 (§4).
- **El backtest confirmatorio no se ejecutó.** No se calculó ningún retorno de estrategia, ningún IC de H1, ningún exceso de H2 o H3 ni el diagnóstico de §5.4 con datos reales.
- **El único uso confirmatorio de la historia sigue disponible**, por si se resuelve A3 (§8).

## 1. Estado de A1, A2 y A3

| | Estado | Detalle |
|---|---|---|
| **A1** Congelar la v3 | **Hecho** | La v3 quedó congelada sin cambios el 2026-10-20 a las 01:34:04Z (`protocolo/CONGELACION_v3.txt`). La v2 y los documentos anteriores siguen intactos y sus hashes coinciden con `SHA256SUMS`. Las desviaciones e interpretaciones quedan en documentos aparte, con fecha y hash (§6) |
| **A2** Datos de Binance Vision | **Hecho y verificado.** V-S4 sin ejecutar | Los 26 105 zips mensuales 1d de los pares USDT (2017-08 → 2026-05) tienen su `.CHECKSUM` verificado. Con BTC y ETH locales son 26 317 zips, el **100 %** de checksums correctos. La reparación con diarios no encontró archivos para ninguno de los 9 huecos internos. exchangeInfo respondió **HTTP 451** (ubicación restringida), así que **V-S4 no se ejecutó** (no se eludió el control) |
| **A3** Anuncios y supervivencia | **Insuficiente.** Resultado según la v3: **INVÁLIDO** | Fuente: Common Crawl (Enmienda 2). Se archivaron 8028 páginas de anuncios, del 2017-08 al 2025-02. La cobertura es parcial en todos los años y **nula desde 2024-11**. La conciliación de la primera pasada da **INVÁLIDO** por §4.11 (iv) |

## 2. Calidad de los datos (A2)

**Hechos observados:**
- **Listado del bucket:** 3745 símbolos, de los cuales 757 terminan en USDT.
  - 756 tienen archivos mensuales.
  - 663 tienen algún día activo hasta el 2026-05-31. Los 94 restantes se listaron después, como los tokens de acciones `…BUSDT`.
  - 228 dejan de tener archivos antes de 2026-05. El bucket **conserva pares retirados** (por ejemplo, BCCUSDT, VENUSDT, HNTUSDT, FTMUSDT y MATICUSDT).
- **Solicitudes:**
  - **Vision:** 53 006, todas registradas con URL, estado, bytes y SHA-256. Hubo 2 cortes de conexión transitorios (FLM 2023-03 y TOMO 2021-01) que se recuperaron al reintentar.
  - **Common Crawl:** 12 671. Hubo 53 errores transitorios (48 HTTP 503, 4 lecturas incompletas y 1 desconexión) y todos se recuperaron.
- **Integridad:** 0 fallos de checksum y 0 conflictos entre mensual y diario. No se descartó ninguna fila y ninguna fila cae fuera del rango 2017-07 → 2026-05.
- **Filas inválidas (279), que se tratan como días inactivos (N1):**
  - 278 tienen una duración distinta de 1 día y 1 tiene el OHLC incoherente. 242 caen en el borde de un listado (el día anterior al primer día activo o el posterior al último), 32 dentro de un corte con reanudación y 5 en otros lugares.
  - Afectan a 246 símbolos, 50 de ellos apalancados.
  - AXSUSDT tiene **2 fechas repetidas** (2026-02-10), que quedan como día inactivo.
- **Días no activos dentro de la vida de cada par:**
  - **3189 en meses sin archivo**, concentrados en 8 pares que dejaron de cotizar y volvieron: USDS (2100), FTT, USDC, USDP, TUSD, BCHUP/DOWN y CVC.
  - **293 son filas ausentes** dentro de un archivo presente.
  - **0 velas con 0 operaciones.**
- **Velas con 0 operaciones tras la última negociación** (el hallazgo del issue #201): solo **1** caso, KLAYUSDT con 1 fila. Las otras 227 colas no tienen velas. **V-S5:** 0 días activos con ≤ 0 operaciones.

**Inferencias, no verificadas:**
- Las filas de duración parcial son días de apertura, cierre o suspensión parcial.
- Los huecos de USDC, USDP y TUSD (2022-09 → 2023-03) corresponden a la conversión automática a BUSD.
- El de FTT (2022-11 → 2023-09), a su retiro y relisting.

## 3. Análisis estructural (sin retornos de estrategia)

| Año | Lunes | Evaluables (≥ 30 elegibles) | Mediana de elegibles | Salidas observadas (N7) |
|---|---|---|---|---|
| 2018 | 53 | 0 | 6 | 2 |
| 2019 | 52 | 0 | 16,5 | 3 |
| 2020 | 52 | 39 | 41 | 21 |
| 2021 | 52 | 52 | 173,5 | 20 |
| 2022 | 52 | 52 | 213 | 43 |
| 2023 | 52 | 52 | 168,5 | 24 |
| 2024 | 53 | 53 | 286 | 46 |
| 2025 | 52 | 52 | 248,5 | 51 |
| 2026 (a mayo) | 21 | 21 | 154 | 26 |

- **Componente (i):** la primera racha de 13 semanas evaluables empieza el **2020-05-11**. Desde ahí hasta el 2026-05-18 hay 315 semanas, todas evaluables.
- **Cortes con reanudación:** hay 34, con una mediana de 1 día. En 26 de ellos el precio salta más de 10 veces:
  - tokens DOWN, que hicieron *reverse splits* en 2021;
  - redenominaciones con anuncio archivado: COCOS (1000:1), DREP (100:1), SUN, QUICK y STRAX;
  - sin anuncio archivado: LUNA, BNX y VIDT. En LUNA, la reanudación del 2022-05-31 **reutiliza el ticker**: es el «LUNA 2.0», una inferencia coherente con el salto de ×3125.
- **Relistados tras ≥ 30 días** (cuentan como listados nuevos): BCHUP/DOWN, CVC, FTT, TUSD, USDC, USDP y USDS. USDS reaparece en 2026-04 tras casi 6 años. Que sea **otro activo con el mismo ticker** es una inferencia.
- **Listas fijas de F3**, con hash en `MANIFIESTO_F3.sha256`: lista fija, apalancados, baja volatilidad o duplicados y elegibles, para cada lunes (`resultados/estructural/listas_fijas_por_lunes.json`).

## 4. Supervivencia y anuncios (A3)

### 4.1 Fuentes evaluadas

| Fuente | Resultado | Uso |
|---|---|---|
| binance.com (categorías 161, 48 y 49) | Condiciones de uso ilegibles: HTTP 202, desafío anti-bots (N8) | No se automatiza |
| web.archive.org | Bloqueado por la política de red del entorno | No disponible |
| Telegram (canal oficial) | Sus condiciones prohíben el scraping | No se usa |
| api.binance.com/exchangeInfo | **HTTP 451**, ubicación restringida por las condiciones de elegibilidad | No se elude: V-S4 queda sin ejecutar |
| **Common Crawl** (`data.commoncrawl.org`) | Licencia de uso con fines de investigación; no toca binance.com | **Usado** (Enmienda 2) |

### 4.2 Cobertura del archivo (hechos)

- **Índice:** 96 capturas (CC-MAIN-2017-04 → 2026-39) en los 3 prefijos SURT, que dan 8028 URL únicas con HTTP 200.
- **Filas de índice por año de captura:**

| 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| 723 | 3759 | 7101 | 5291 | 12 107 | 11 096 | 7315 | 1295 | 356 | 121 |

- **Páginas por año de publicación:** 651 en 2017, 610 en 2018, 958 en 2019, 1671 en 2020, 2079 en 2021, 1180 en 2022, 604 en 2023, 135 en 2024 y **1 en 2025**.
- **Exclusiones:** 112 páginas (3, 12, 36, 23, 10, 16 y 12 de 2018 a 2024). La última fecha efectiva archivada es el **2024-11-06**. El último renombre archivado es el 2024-09-10.
- **Sonda de todo el dominio binance.com:**
  - CC-MAIN-2025-13 tiene 926 líneas, solo 102 con HTTP 200, y 39 anuncios en cualquier idioma;
  - CC-MAIN-2024-33 tiene 181 anuncios.
  - Ningún otro prefijo ni idioma compensa la falta.
  - *Inferencia:* el desafío anti-bots de binance.com también afecta al rastreador de Common Crawl.

### 4.3 Conciliación, primera pasada (`resultados/conciliacion_pasada1/`)

- **Eventos:** 55, de los cuales 42 están en el universo de anuncios.
- **Fuera del universo:**
  - 79 filas en las que el texto enumera los pares sin USDT (v3 §2.3);
  - 13 casos «sin par USDT documentado», en los que el bucket conserva otros pares del token (Adenda 3, A3.3.2).

| Año (E) | Total | A | B | T | C no explicada | D | (A+B)/total |
|---|---|---|---|---|---|---|---|
| 2019 | 1 | 1 | 0 | 0 | 0 | 0 | 100 % |
| 2020 | 12 | 12 | 0 | 0 | 0 | 0 | 100 % |
| 2021 | 1 | 0 | 0 | 1 | 0 | 0 | 0 % |
| 2022 | 2 | 2 | 0 | 0 | 0 | 0 | 100 % |
| 2023 | 16 | 7 | 1 | 3 | 5 | 0 | 50 % |
| 2024 | 10 | 10 | 0 | 0 | 0 | 0 | 100 % |
| 2025–2026 | 0 | — | — | — | — | — | — |

- **Fallas provisionales:**
  - **T:** BKRWUSDT 2021-02-19, y DOTUP, DOTDOWN y TRXDOWN 2023-04-27 (último día activo 2022-11-28, con archivos faltantes).
  - **C:** 5 pares de la página «Notice of **Addition &** Removal of Trading Pairs – 2023-09-22» (ARK, CREAM, FTT, GFT e IQ).
  - *Inferencia:* los C son un error de extracción (pares **agregados**, no retirados). FTT, de hecho, vuelve a cotizar el 2023-09-22. Se resolverían con la lectura manual (A3.5). Con ellos, (ii) da 2023-09-23.

**Salidas observadas (N7) y anuncios:**

| Año | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| Observadas | 2 | 3 | 21 | 20 | 43 | 24 | 46 | 51 | 26 |
| Sin anuncio | 2 | 2 | 8 | 20 | 36 | 16 | 36 | **51** | **26** |
| % sin anuncio | 100 | 67 | 38 | 100 | 84 | 67 | 78 | **100** | **100** |

**Inicio de H (§4.11):**
- (i) 2020-05-11;
- (ii) 2023-09-23 (provisional);
- (iii) 2019-01-01;
- (iv) **sin solución**.

En consecuencia, H queda vacía y el resultado es **INVÁLIDO**.

### 4.4 Por qué la conclusión no depende de la revisión manual pendiente

- **Pendientes de lectura manual** (Adenda 3, A3.11):
  - 5 casos C;
  - 8 filas sin fecha (BCN, CHAT, ICN y TRIG, 2018-10, en 2 copias);
  - 12 páginas sin par (COVER-Old, WAPI, páginas de categoría y otras);
  - la muestra de V-S3;
  - unos 25 renombres con cambio de ticker.
- **Lo que puede hacer esa lectura:**
  - corregir fechas de anuncios **ya archivados**;
  - marcar casos C como explicados;
  - descartar errores de extracción;
  - mapear renombres que **tengan anuncio archivado**.
- **Lo que no puede hacer:** agregar anuncios que no existen en el archivo.
- **Salidas de 2025 y 2026:** el último día activo de todas es posterior al 2024-11-07. Para contar como «con anuncio», una salida necesita un anuncio archivado con E ≥ L − 1, y la última E archivada es el 2024-11-06. Por lo tanto, **todas las salidas de 2025 y 2026 son «sin anuncio»** bajo cualquier lectura, y (iv) no tiene solución.
- **Años 2021–2024:** también fallan con holgura (67–100 %).
  - En 2024, para bajar del 10 %, al menos 32 de las 36 salidas sin anuncio tendrían que pasar a «con anuncio», o al menos 35 tendrían que ser renombres mapeados.
  - Solo hay unos 3–5 renombres archivados con fecha en 2024: MATIC→POL, PLA→PDA y STRAX.
- **Por eso no hice la segunda pasada manual.** Es una auditoría que no cambia la decisión, y pediste no abrirlas. Los resultados por categoría de la primera pasada son **provisionales**.

**Controles adicionales:**
- **V-S2:** 49 de 50 = **98 %**, cumple el ≥ 95 %. El desacierto es ETHBEARUSDT: anuncio del 2020-01-17, primer día activo el 2020-02-03. No se revisó.
- **V-S3:** no se revisó.
- **V-S4:** no ejecutado (HTTP 451).
- **V-S5:** 0, cumple.

## 5. Calibración estadística (solo con datos sintéticos)

**Datos de la calibración:**
- **Original (v3 §5.3):** `calibracion.json`, `9232876…`; semilla 20261023; 1000 simulaciones; B = 1999; n = 340.
- **Complementaria de la regla del máximo** (Enmienda 2, E2.2): `calibracion_regla_maximo.json`, `87742867…`; semilla 20261028; 2000 simulaciones; los tres valores p calculados sobre la misma serie.
- **Bandas de aceptación:** [3,6 %; 6,4 %] al 5 % y [1,5 %; 3,5 %] al 2,5 %.
- **Error de Monte Carlo:** 0,49 y 0,35 puntos con 2000 simulaciones; 0,69 y 0,49 puntos con 1000.

**Escenarios que sobre-rechazan bajo la nula (H2 y H3):**

| Calibración | Método | Proceso | Rechazo al 5 % | Al 2,5 % |
|---|---|---|---|---|
| Original | boot ℓ=13 | **G1** (t₃ i.i.d.) | **7,0 %** | **4,5 %** |
| Original | boot ℓ=26 | **G1** | 6,2 % | **3,9 %** |
| Complementaria | boot ℓ=26 | **G3** (GARCH-t₄) | **6,8 %** | 3,5 % (al borde) |
| Complementaria | NW 13 rezagos | **G5** (mezcla asimétrica) | **6,5 %** | **3,8 %** |
| Complementaria | boot ℓ=13 | G3 | 6,4 % (al borde) | 3,45 % |

**Regla prerregistrada p = máx(p_boot13, p_boot26, p_NW13)** (calibración complementaria):

| | G1 | G2 | G3 | G4 | G5 |
|---|---|---|---|---|---|
| Rechazo al 5 % | 4,85 % | 4,90 % | 5,50 % | 3,65 % | 4,70 % |
| Rechazo al 2,5 % | 2,35 % | 1,95 % | 2,55 % | 1,85 % | 2,15 % |
| Potencia (μ = 30 %/año, al 5 %) | 0,658 | 0,529 | 0,688 | 0,668 | 0,613 |
| Potencia de boot13 (referencia) | 0,692 | 0,566 | 0,720 | 0,709 | 0,652 |

- **En los cinco procesos probados, la regla del máximo controla el tamaño:** cae dentro de ambas bandas. Cuesta unos 3–5 puntos de potencia.
- **Diferencia entre las dos corridas de G1 con boot13** (7,0 % frente a 6,15 %): es de ≈ 1 error estándar de la diferencia, es decir, ruido de Monte Carlo.
- **H1 (Newey–West, L = 4):** 4,4 % y 2,2 %, dentro de las bandas, así que rige L = 4.
- **Alcance:** esto **no demuestra validez general**. Vale solo para G1–G5 con n = 340 y estos bloques. No dice nada del proceso real (regímenes, caídas agrupadas, dependencia larga) ni de otro n. El diagnóstico de §5.4 con carteras aleatorias reales **no se ejecutó**, porque requiere retornos reales y H es inválida.
- **Decisión de método:** se tomó con la regla prerregistrada **antes** de los datos reales, sin mirar ningún resultado real.

## 6. Desviaciones, interpretaciones y correcciones documentadas (la v3 se conserva intacta)

| Documento | Fecha (UTC) | SHA-256 | Contenido |
|---|---|---|---|
| `NOTAS_IMPLEMENTACION_v3.md` | 01:34 | `21c37596…` | N1–N22: concreciones técnicas |
| `ADENDA_1_reutilizacion_de_tickers.md` | 01:44:08 | `187111a0…` | Renombres, relistings y redenominaciones |
| `DECISION_CALIBRACION.txt` | 01:51:50 | `9ea031ba…` | Activa la regla del máximo (registro) |
| `ENMIENDA_2_fuente_archivada_inferencia_motor.md` | 02:01:27 | `6b204901…` | Common Crawl en lugar del Internet Archive; IC90 de H2/H3 como envolvente; interpretaciones del motor |
| `ADENDA_3_reglas_conciliacion.md` | 02:15:29 | `47c17145…` | Reglas fijas de la conciliación, fijadas **antes** de descargar las páginas |
| `CORRECCION_1_cc_anuncios_nombres.txt` | 03:54:51 | `dfae16b3…` | Corrección de recolección: colisión de nombres de archivo (181 páginas). El hash de `cc_anuncios.py` pasó de `6255236b…` a `67e0a4cb…` |
| `datos_exchangeinfo/LEEME.txt` | 02:11:26 | `0f4bdece…` | HTTP 451; no se elude |

- **Correcciones de código hechas antes de cada ejecución,** registradas en `REGISTRO_EJECUCIONES.jsonl`:
  - `analisis_estructural.py` falló con una semana sin candidatos; se corrigió.
  - `cc_clasificar.py` ahora recorta el cuerpo del anuncio, porque la barra lateral traía pares ajenos (A3.1).
- **Ninguna desviación** cambia hipótesis, métricas, umbrales, ventanas, universos, costos ni criterios, y ninguna se tomó a la vista de resultados reales de E3.

## 7. Limitaciones pendientes

1. **Supervivencia:** no existe una fuente pública, utilizable y permitida de los anuncios de exclusión de Binance con cobertura suficiente. La cobertura de Common Crawl es parcial en todos los años y nula desde 2024-11.
2. **V-S4 sin ejecutar** (HTTP 451). La base de cada símbolo se toma como símbolo − «USDT».
3. **La lectura manual de la Adenda 3 no se hizo:** casos C y E, V-S3 y renombres. Las categorías por año de §4.3 son provisionales; la conclusión no lo es (§4.4).
4. **Redenominaciones sin anuncio archivado** (LUNA, BNX y VIDT, y la reutilización de USDS): sin resolver.
5. **La calibración solo vale para procesos sintéticos con n = 340**; no hay diagnóstico con datos reales.
6. **Las limitaciones registradas al congelar la v3 siguen vigentes:** potencia baja de H2 (0,11–0,26, estimación analítica), historia que no es fuera de muestra, ninguna clasificación autoriza capital.

## 8. Qué haría falta para habilitar E3 (decisión tuya; nada de esto se hizo)

Haría falta una lista completa de las exclusiones y renombres de pares USDT entre 2020-05 y 2026-05, con su fecha efectiva y una fuente verificable. Opciones:

| Opción | Qué implica | Comentario |
|---|---|---|
| a) Compilación manual tuya de la categoría Delisting (161) de binance.com, en un navegador | La v3 §9 prevé la compilación manual. Se fija con hash antes de cualquier retorno | Es la más directa. Hay que cubrir **todos** los años desde 2020, no solo 2024–2026 |
| b) Habilitar `web.archive.org` en la red del entorno | Aplicaría la N8 original | Incierta: las capturas recientes de binance.com también pueden ser el HTTP 202 anti-bots (ya observado en la lista 161) |
| c) Confirmar que las condiciones de Binance permiten la lectura automatizada | Habilitaría automatizar binance.com | Requiere tu verificación y una adenda |
| d) Fuente no oficial o licenciada | Fuera de la v3; requiere adenda y autorización (§2.3) | Menos verificable |
| e) Aceptar el resultado y cerrar la historia de E3 | Queda «no evaluable con Vision»; se conserva el uso confirmatorio | Se podría prerregistrar una evaluación prospectiva aparte |

**Mi recomendación:** la (a) solo si podés obtener la lista completa a un costo razonable. Si no, la (e). No recomiendo relajar la regla (iv) ni recortar la ventana para «hacerla válida»: sería cambiar el protocolo después de ver la cobertura.

## 9. Archivos principales

Todos están en `ejecucion_E3/`.
- **Protocolo y adendas:** `protocolo/`, con `CONGELACION_v3.txt`, `CONGELACION_ADENDAS.txt` y `CONGELACION_ADENDA_3.txt`.
- **Código:** `codigo/` (descarga, calidad, universo, motor, inferencia, calibración, Common Crawl, clasificación, conciliación y análisis estructural).
- **Resultados:**
  - `resultados/calidad/` (resumen y auditoría por símbolo);
  - `resultados/estructural/` (estructura y listas fijas por lunes);
  - `resultados/conciliacion_pasada1/` (conciliación, eventos, salidas, fuera del universo y lista de revisión manual);
  - `resultados/calibracion/`.
- **Hashes y registros:**
  - `MANIFIESTO_F3.sha256`: incluye el hash del conjunto de los 26 105 zips de Vision (`cf27c8dd…`) y el de las 8028 páginas archivadas (`f12afb98…`).
  - `REGISTRO_EJECUCIONES.jsonl`, de solo añadidos: 7 entradas, 4 con datos sintéticos y 3 de F3 sin retornos.
  - `logs/`.
- **Registro de hipótesis nuevo**, que remite a la v3: `../REGISTRO_HIPOTESIS_tras_E3_v3_A1_A3.md`. E3-H1, H2 y H3 quedan como «PROPUESTA · NO EVALUABLE con las fuentes actuales».

## 10. Límites respetados

- **Repositorio:** HEAD en `692f2b2`, con las 8 entradas preexistentes intactas, verificado con `git status`. No hubo commits, push, merge, rebase, cherry-pick ni despliegues.
- **Archivos del repositorio:** solo se leyeron los datos locales de BTC y ETH, sin modificarlos.
- **Dinero:** no se usó dinero real ni se enviaron órdenes.
- **Datos:** ningún dato de precios posterior al 2026-05-31. De fechas posteriores solo se leyeron nombres de archivo en los listados del bucket. El anuncio archivado más reciente es una captura del 2025-02-09.
- **Otros experimentos:** E1, E2, T y T-MULTI no se tocaron.
