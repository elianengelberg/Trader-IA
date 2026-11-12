# E3-H1/H2 · Reparación metodológica, sin ejecutar el experimento · 2026-10-26

**NO SE EJECUTÓ E3-H1/H2. NO AUTORIZADO PARA OPERAR.**
- Ningún retorno ni métrica de estrategia se calculó con precios reales.
- No hubo Testnet, credenciales, dinero real, commits, push, PR, merge ni deploy.
- No se creó ningún archivo de autorización.
- Los congelados quedaron intactos (punto 7).

Rotulado de las afirmaciones:
- **[H]** hecho verificado por un script o un hash;
- **[I]** inferencia;
- **[J]** juicio.

## Resumen

| Pregunta | Respuesta |
|---|---|
| Veredicto (punto 9) | **A sigue siendo candidata válida**, bajo la Adenda R (R1 literal), con la segunda pasada definitiva. Con la v3 pura ninguna ventana es válida: (iv) no se cumple en ningún año, y eso no cambió [H] |
| Ventana A | Inicio **2023-05-15**, última formación **2026-05-18**. **158 semanas evaluables de 158** (0 % no evaluables), con ≥ 120 elegibles en cada semana. **Margen: 2 semanas** [H] |
| Respecto de la decisión anterior | A pierde 2 semanas (eran 160). La segunda pasada corrigió, según el texto archivado, la fecha efectiva de las exclusiones de tokens apalancados que fijan el inicio. La corrección acorta la ventana: no la favorece [H] |
| Qué invalidaría A | Cualquier falla nueva en alcance con fecha efectiva ≥ 2023-05-29 [H]. En el archivo no queda ninguna sin resolver [H]. Después del 2024-11-06 el archivo no tiene cobertura: el residual se declara (punto 8) |
| Recomendación (punto 10) | Preparar una solicitud **nueva**, solo para A, después de una revisión independiente del diff del orquestador y de la tabla de mapeos. No ejecutar sin tu autorización explícita posterior |

---

## 1. La segunda pasada, caso por caso

**Documento completo:** `segunda_pasada/SEGUNDA_PASADA_CASO_POR_CASO.md`. Trae, para cada caso, fuente archivada (archivo, captura y WARC), cita, fecha, par, tipo, decisión, justificación y certeza. **Todas** las citas se verificaron literalmente contra el texto archivado local: los scripts abortan si falta una.

**Cómo se hizo:**
- Se releyeron los **55 eventos** de la primera pasada, no solo los de las listas de revisión. El motivo: el desacierto de V-S3 en DOTUP mostró que la extracción (A3.1.5) toma la fecha del **título**, que es la de publicación.
- Las resoluciones están en `resoluciones_manuales.json` (`41a13221…`), con el formato exacto que lee `conciliacion.py` congelado (`6f764845…`). Ese código corrió **sin cambios**.
- Antes se comprobó que el entorno reproduce **byte a byte** las 5 salidas congeladas de la primera pasada [H].

| Lista | Casos | Resultado |
|---|---|---|
| Eventos (claves con fecha) | 47 | **37 confirmados.** **4 fechas corregidas** por N5: DOTUP y DOTDOWN 2023-04-27 → 2023-05-10; TRXDOWN → 2023-05-09; LINKUP → 2023-05-11 (cita: «At 2023-05-09 06:00 (UTC) : TRXUP, TRXDOWN At 2023-05-10 06:00 (UTC) : DOTUP, DOTDOWN At 2023-05-11 06:00 (UTC) : LINKUP, LINKDOWN»). **5 C explicados** por A3.5 b (ARK, CREAM, FTT, GFT e IQ: el texto **abre** esos pares USDT y remueve los BUSD). **1 descartado** (BKRW: el anuncio corrige el par a USDT/BKRW) |
| Sin fecha | 8 (BCN, CHAT, ICN, TRIG × 2 URL) | E = 2018-10-12 según el cuerpo. Siguen fuera del universo por A3.3.2 (sin par USDT documentado y con otros pares en el bucket) |
| Sin par | 12 | Resueltos uno por uno (§4 del documento): COVER-old (canje 1:1); remoción 2021-09-09 (AAVEBRL, EOSAUD, ICPRUB: fuera, A3.2); conversión a BUSD de tokens ya excluidos; WAPI ×2 (no son tokens); BCHSV duplicado y FTX ×2 (cubiertos por eventos A); 2 páginas índice de «Delisting» (solo navegación: **la ausencia de contenido no se toma como prueba de que no hubo eventos**); 2 avisos de conversión (sus 27 tokens se revisan uno por uno) |
| Eventos omitidos por la extracción | 2 | **TRXUP (T, E 2023-05-09) y LINKDOWN (T, E 2023-05-11)**, del mismo anuncio. El código congelado no tiene mecanismo para agregarlos: se clasificaron con su función `clasificar` (copia verificada por hash) y se suman a (ii). No mueven el inicio |
| C | 5 | Ver «Eventos» |
| D sin evidencia ni otro par | 0 | La lista del código está vacía. NSBT, SGB, SOLO y XYM, que venían de los avisos de conversión, se leyeron a mano (punto 2) |
| V-S2 | 1 desacierto | ETHBEARUSDT: el texto de listado es correcto. Hubo una suspensión documentada (reanudación el 2020-02-03). A3.6 no permite corregir: **49/50 = 98 % ≥ 95 %** |
| V-S3 | 10 | Muestra de la primera pasada: 10/10 revisados. El código vuelve a sortear sobre el universo de la segunda pasada; como se releyeron los 47, el resultado es 10/10 |
| Candidatos de renombre | 164 (114 títulos) | Ver punto 4. Más **2 renombres** que la extracción no clasificó: BCHABC→BCH y XZC→FIRO |

**Resultado de la segunda pasada** (`segunda_pasada/salida_pasada2/`) [H]:
- 51 eventos; 41 en el universo; 9 fuera por falta de par USDT documentado; 1 descartado.
- En el universo: 32 A, **4 T** (los apalancados de 2023-05), 5 C explicados, **0 D, 0 C no explicados**.
- 16 salidas reconocidas como renombre mapeado.
- **Última falla:** LINKUPUSDT, T, 2023-05-11.

## 2. Estado y evidencia de cada pendiente

| Pendiente | Estado | Evidencia | Certeza |
|---|---|---|---|
| 12 sin par | Resueltos | Positiva: cita de cada página. Para las 2 páginas índice, ausencia de contenido; se descartan como fuente, no como prueba | alta |
| 8 sin fecha | Resueltos | Positiva: fecha explícita en el cuerpo | alta |
| 11 controles de muestreo (1 V-S2, 10 V-S3) | Resueltos | Positiva | alta |
| 164 renombres | Resueltos | Positiva para los 22 mapeos y para los canjes sin cambio de símbolo. Negativa por regla para los no mapeados | alta, salvo 3 «media» (punto 4) |
| **NSBT, SGB, SOLO, XYM** | **No son D** (A3.3.3) | **Positiva de airdrop**: «Binance will support the Songbird (SGB) Airdrop Program for XRP (XRP) holders»; NSBT y XYM, programas de airdrop; SOLO, ídem. Además, **ausencia** de cualquier par en el bucket y de menciones de pares en las 8028 páginas. Esa ausencia no se usa sola: lo que decide es la identificación positiva como airdrop | alta |
| Otros 23 tokens de los avisos de conversión | 11 con par USDT en el bucket (su salida se audita como salida observada). 11 sin evidencia de par USDT y con otros pares en el bucket (A3.3.2). SKY, en la fila siguiente | Los pares en el bucket son positivos; los demás, regla A3.3.2 | alta |
| SKY | A3.3.2 | El SKYUSDT del bucket empieza el 2025-09-17: es otro activo (MKR→SKY). Corregí mi primera clasificación | media-alta |
| Eventos que mueven el inicio o el final de A | Ninguno pendiente en el archivo | Se revisaron todas las páginas de exclusión con fecha ≥ 2023-04-28. Ninguna enumera un par X/USDT que no esté ya como evento; los títulos parecidos a exclusiones son de futuros, margen, bots o etiquetas [H] | alta dentro del archivo |

**¿El protocolo permite seguir?**
- Dentro del archivo, sí: no queda ningún caso sin resolver.
- Fuera del archivo (2024-11-06 → 2026-05) no hay anuncios. La v3 pura no lo permite, porque (iv) falla. Solo la Adenda R lo permite, con evidencia interna. Es la misma condición que ya estaba sobre la mesa; no apareció ninguna nueva.

## 3. Validez de A: límites, semanas y margen

`ventana_A/ventana_A_pasada2.json` (`dcbd80ab…`) sale de `p0_pasada2.py`. Antes de usarlo se verificó que, con los insumos de la primera pasada, **reproduce exactamente el P0 congelado** (tablas, fallas, salidas y ventana) [H].

| Componente | Regla congelada | Valor | Qué lo fija |
|---|---|---|---|
| (i) | 13 semanas evaluables seguidas (v3 §4.11) | 2020-05-11 | `estructural.json` |
| (ii) de la v3 = (ii′) de la Adenda R con R1 literal | Lunes siguiente a la última falla T/D/C no explicada; las 6 están en alcance | **2023-05-15** | Las 6 fallas T de los tokens apalancados: TRXUP y TRXDOWN el 2023-05-09; DOTUP y DOTDOWN el 2023-05-10; LINKUP y LINKDOWN el **2023-05-11** |
| (iii) de la v3 | 1 de enero del año del primer evento del universo | 2019-01-01 | BCHSV, 2019-04-22. La Adenda R no lo aplica |
| (iv) de la v3 | En todos los años, ≤ 10 % de salidas sin anuncio | **Ningún año cumple**: 2025, 51/51 sin anuncio; 2026, 26/26 | → **la v3 pura es INVÁLIDA** |
| (iv′) de la Adenda R | En todos los años, ≤ 10 % de salidas en alcance sin evidencia interna; las de renombres mapeados no cuentan (A3.7) | 2018 | El único año con alguna sin evidencia es 2023: **1 de 19** (NBTUSDT, 2023-02-28), un 5,3 % |
| **Inicio** | El más tardío | **2023-05-15** | (ii′) |
| **Final** | Última formación (v3 §4.11) | **2026-05-18** | — |
| Semanas | ≥ 156 evaluables y ≤ 20 % no evaluables | **158 / 158**; 0 % no evaluables; mínimo de elegibles: 120 (umbral: 30) | — |
| **Margen** | — | **2 semanas.** El último inicio que todavía deja 156 es el 2023-05-29 | Una falla en alcance con E ≥ 2023-05-29 invalida A |

**Sensibilidad** (sin cambiar ninguna regla; solo para mostrar de qué depende el veredicto):

| Variante | Inicio | Semanas | Veredicto |
|---|---|---|---|
| Fecha del título de la primera pasada (A3.1.5, 2023-04-27) en lugar de la del texto (N5) | 2023-05-01 | 160 | VÁLIDO |
| Sin los 2 eventos omitidos | 2023-05-15 | 158 | VÁLIDO |
| Sin excluir las salidas por renombre mapeado | (iv′) = 2018 | 158 | VÁLIDO |
| Si los 5 C se hubieran leído como no explicados (el texto dice lo contrario) | 2023-09-25 | < 156 | INVÁLIDO |
| Con una salida más sin evidencia en 2023 (2 de 19 = 10,5 %) | (iv′) = 2024 | < 156 | INVÁLIDO |

**[I]** El veredicto no depende de la elección entre título y texto para la fecha efectiva. Sí depende de la lectura de los 5 C, que es textual y de certeza alta, y de que en 2023 haya como máximo una salida sin evidencia, que es un hecho de los datos.

## 4. Renombres y redenominaciones

**Archivos:**
- clasificación: `renombres/CLASIFICACION_RENOMBRES.md` y `clasificacion_renombres.json`;
- tabla de mapeos congelada: `renombres/mapeos_adenda1.json` (`aeb8b5f2…`);
- los 34 cortes: `renombres/cortes_34.json`.

**Decisiones sobre los 164 candidatos (114 títulos):**
- 14 renombres con par USDT, más 2 hallados fuera de la lista (BCHABC→BCH y XZC→FIRO): mapeo por la regla 1;
- 6 redenominaciones: mapeo por la regla 2;
- 63 sin mapeo necesario: canjes de red o de contrato con el mismo símbolo, listados que mencionan un canje, y DOT, que en Binance solo se negoció ya redenominado;
- 12 renombres válidos cuyo símbolo viejo **no tiene par USDT**, como HSR→HC, GNT→GLM o BCHA→XEC: se registran y no afectan al universo;
- 17 anuncios complementarios, de actualización o de finalización;
- 2 que no son renombres: tokens de acciones y cierre de la red BEP2.

**Mapeos dentro de A o que la afectan** (r = unidades nuevas por unidad vieja; la serie es continua con P_nuevo ≈ P_viejo / r):

| Viejo → nuevo | Regla | r | E (texto) | Apertura (texto) | En los datos | Certeza | Cita |
|---|---|---|---|---|---|---|---|
| COCOS → COMBO | 1 | 1 | 2023-06-02 | — | Último día 2023-05-28; primero 2023-06-02 | **media**: solo está archivado el anuncio de finalización; no da la hora de cese | «The distribution of COMBO (COMBO) was conducted at a ratio of 1 COCOS = 1 COMBO» |
| **QUICK** | 2 | 1000 | 2023-07-17 | 2023-07-21 | Corte del 2023-07-16 al 2023-07-21 | alta | «at a ratio of 1 old QUICK = 1,000 new QUICK» |
| MC → BEAMX | 1 | 100 | 2023-11-07 | 2023-11-14 | 2023-11-06 → 2023-11-14 | alta | «…at a ratio of 1 MC = 100 BEAMX» |
| TVK → VANRY | 1 | 1 | 2023-12-01 | — | 2023-11-26 → 2023-12-01 | **media**: solo el anuncio de finalización | «The distribution was conducted at a ratio of 1 TVK = 1 VANRY» |
| PLA → PDA | 1 | 1 | 2024-02-26 | 2024-03-01 | 2024-02-25 → 2024-03-01 | alta | «PLA tokens will assume the ticker of PDA on Binance» |
| **STRAX** | 2 | 10 | 2024-03-20 | 2024-03-28 | Corte del 2024-03-19 al 2024-03-28 | alta | «at a ratio of 1 old STRAX = 10 new STRAX» |
| MATIC → POL | 1 | 1 | 2024-09-10 | 2024-09-13 | 2024-09-09 → 2024-09-13 | alta | «…at a ratio of 1 MATIC = 1 POL» |

En los 22 mapeos el cruce con la actividad es coherente. El script usa solo fechas de actividad y aborta si alguno no cuadra [H].

**Los 8 cortes que partía R2:**

| Corte | Tratamiento con las reglas congeladas | Efecto en A |
|---|---|---|
| QUICK, STRAX | Regla 2 con anuncio: continuidad a través de r. R2 los convertía en listados nuevos, con edad 0 | Dentro de A: corregido |
| DREP (100:1), SUN (1:1000), COCOS (1000:1) | Regla 2 con anuncio | Previos a A |
| **LUNA, VIDT, BNX** | **Sin anuncio archivado → regla 3**: mismo listado (corte < 30 días). Se informa como limitación; **no se inventa r** | LUNA y VIDT: ninguno (cumplen 180 días de edad en ambos casos y quedan fuera de toda ventana de la señal). **BNX**: con la regla 3 conserva su edad; con R2 habría sido inelegible hasta el 2023-08-21. La señal (≤ 28 días con 30 días activos seguidos) y las posiciones (H empieza después) no cruzan el corte |

**R2 queda abandonada** [J]. Contradice la regla 3 de la Adenda 1 («no se corrigen con reglas inventadas»), y los cortes que importaban dentro de A tienen anuncio.

**Los otros 26 cortes:**
- 18 son de tokens apalancados, excluidos de todo universo. 15 tienen un anuncio archivado de *reverse split* [H].
- 8 no tienen salto ×10 [H]:
  - AUD y AEUR: lista fija de exclusión;
  - BTCST: regla 2 con anuncio; certeza **media** en el sentido de «1:10»; es previo a A;
  - NBT y KEY: previos a A;
  - **SCR, USUAL y AXS: dentro de A, cortes de 1 día, sin anuncio archivado.** Regla 3 (limitación).

**Cambios de símbolo sin anuncio archivado.** Se detectaron dentro de A solo con actividad, y se aplica la regla 3: el viejo sale con liquidación contable (§4.10) y el nuevo es un listado nuevo. **No se unen series sin evidencia:**
- TOMO→VIC, GAL→G, RNDR→RENDER y KLAY→KAIA: dentro del período del archivo, pero sin anuncio capturado;
- DAR→D, FTM→S, EOS→A, MKR→SKY, FXS→FRAX y OM→MANTRA: posteriores al archivo;
- la fusión AGIX/OCEAN→FET.

**[I]** Su efecto es de composición del universo, no de precio ficticio. Los nuevos símbolos quedan inelegibles 180 días.

## 5. Corrección de R4 y verificación de insumos

**Orquestador v2:** `orquestador_v2/ejecutar_E3_v2.py` (`01fc9344…`), archivo nuevo. Lo genera `generar_v2.py` a partir del congelado (`3b64a04d…`, intacto), con 9 reemplazos que deben coincidir exactamente una vez. El diff completo está en `DIFF_v1_v2.diff`.

| Cambio | Qué hace |
|---|---|
| **C2 · R4 (N14)** | Confirmado: N14 define el aporte con «r_{EW,t} = retorno **bruto** de EW-U30 en esa semana». El v1 pasaba el EW **neto** (`contribuciones(P, base, formaciones, ew)`). El v2 simula `bruto_ew` antes y pasa ese |
| **C3 · Hash exacto de los insumos** | En modo real, **antes de leer cualquier precio**, compara 15 insumos con `ENTRADAS_CONGELADAS.json` (`8ee3bc07…`): el conjunto de las 757 series (`6506fb03…`, con la receta de CIERRE reimplementada y verificada), estructural, listas, los 5 módulos congelados, las salidas de la segunda pasada, las resoluciones, los eventos omitidos, los mapeos y la ventana A. Si falta un insumo, sobra uno o un hash no coincide, se detiene **sin crear la salida y sin leer precios** |
| **C4 · Mapeos de la Adenda 1** | Reglas 1 y 2 en el panel; sin R2. Aborta ante cualquier inconsistencia: símbolo ausente; solapamiento; viejo activo después de E; regla 2 sin corte o sin reapertura |
| **C5 · INVÁLIDO explícito** | Si la ventana o la validez previa fallan, escribe `RESULTADO_E3.json` con «INVALIDO», el motivo, H1 = H2 = null |
| **C6 · Solo la ventana A** | Sin opción B, sin R1′ y sin elegir entre varios P0. La autorización debe contener la frase nueva, el sha256 del v2 y el del manifiesto, que fija la ventana |

**Preflight contra los insumos reales**, con `np.load` bloqueado: los 15 insumos coinciden con el manifiesto. Sin autorización, el modo real se detiene sin crear nada [H].

## 6. Pruebas ejecutadas y resultados

**Pruebas del orquestador.** `orquestador_v2/pruebas/test_orquestador_v2.py` corrió en 2,4 s: **28 pasan y 6 fallan, como se exige, en el v1** (`xfail(strict=True)`: si una pasara en el v1, la suite fallaría). Una guarda impide abrir cualquier serie real.

| Prueba | v1 | v2 | Razón por la que falla el v1 (verificada sin el xfail) |
|---|---|---|---|
| R4 mide contra el EW bruto | falla | pasa | Recibe el EW neto: 120 de 120 semanas difieren |
| Serie alterada → se detiene sin leer precios | falla | pasa | El v1 lee precios |
| Ventana INVÁLIDA → resultado explícito | falla | pasa | El v1 sale sin `RESULTADO_E3.json` |
| Regla 2: continuidad y edad (caso QUICK) | falla | pasa | El v1 crea `R2X0QQQUSDT` (edad 0) |
| Regla 1: hereda edad y fila (caso MC→BEAMX) | falla | pasa | El v1 no mapea: X y Y quedan separados |
| Corte sin anuncio → regla 3 (caso BNX) | falla | pasa | El v1 parte la serie con R2 |
| Bordes del v2 | — | pasan | Cadena regla 2 → regla 1 (caso COCOS); 5 mapeos imposibles abortan; 7 alteraciones de insumos (estructural, listas, serie faltante, serie extra, mapeos, ventana, motor); 4 autorizaciones incompletas; salida existente; insumos correctos que pasan la guarda (sin falsos rechazos) |
| Controles | pasan | pasan | Aritmética de `contribuciones` con bordes. Caso construido donde **la moneda excluida en R4 cambia entre EW neto y EW bruto** (el defecto puede ser material) |
| Tabla de mapeos real | — | pasa | 22 mapeos válidos; ningún símbolo sin anuncio archivado (RNDR, TOMO, BNX, LUNA…) está mapeado |

**Otras verificaciones** [H]:
- **Diferencial sintético v1 frente a v2**, completo y con momentum 0 y 0,02: 186 campos idénticos. En esos paneles el arreglo de R4 no cambia la moneda excluida; el defecto queda demostrado por la prueba directa y por el caso construido.
- **Pruebas congeladas del motor de E3** (`pruebas_motor.py`, sobre una copia verificada del código): `todo_ok: true`.
- **Reproducción desde cero:**
  - primera pasada: 5 de 5 salidas idénticas a las congeladas;
  - segunda pasada: 5 de 5 idénticas, más la clasificación y las resoluciones;
  - ventana A: idéntica salvo las rutas absolutas registradas;
  - P0 de control: idéntico al congelado.
- **ruff:** el v2 tiene los mismos avisos de estilo que el v1 (nombres `O`, variables de bucle sin usar). No hay categorías nuevas.
- **Ninguna prueba calculó retornos reales:**
  - las pruebas usan series sintéticas o árboles temporales;
  - el barrido estático muestra que, sobre datos reales, solo se leyó `estado` (en `p0_pasada2.py`; `conciliacion.py` lee además `NT`);
  - el único código que lee O, C y QV (`panel_real` del v2) nunca corrió sobre datos reales.

## 7. Hashes, procedencia y estado de Git

**Artefactos nuevos.** Todos están en `MANIFEST.sha256` (verificable con `sha256sum -c`). Procedencia paso a paso en `registro/REGISTRO_DE_CAMBIOS.md`.

| Artefacto | sha256 |
|---|---|
| `segunda_pasada/resoluciones_manuales.json` | `41a13221dea70023126ce3fb6c311c9f41e2aef063820207c1f7e871d2873863` |
| `segunda_pasada/salida_pasada2/conciliacion.json` · `eventos.json` · `salidas.json` | `7a0778e8…` · `dbd5a85d…` · `9c6fd418…` |
| `segunda_pasada/eventos_omitidos.json` | `823b3096…` |
| `renombres/mapeos_adenda1.json` | `aeb8b5f2b33938717eb2acbe4b68fa581d92caa71841ed748384599aefbdf917` |
| `renombres/clasificacion_renombres.json` | `a9907bd4…` |
| `ventana_A/ventana_A_pasada2.json` | `dcbd80ab…` |
| `orquestador_v2/ejecutar_E3_v2.py` | `01fc934459b791fd5fbd451aa1c6931fc9e6764b9361e5caea46314cc5ee6f68` |
| `orquestador_v2/ENTRADAS_CONGELADAS.json` | `8ee3bc075f21648f8dae70296e23c0c0858bd5a706f17f205d9115d28c333627` |

**Originales intactos** [H]:

| Objeto | Huella | Estado |
|---|---|---|
| Árbol de E3 | `4909ef95…` | antes = después |
| Árbol de E3R | `649a72f5…` | antes = después |
| Directorio `experimentos/` | `8e875f5b…` | antes = después de las pruebas |
| `CIERRE_E3_MANIFIESTO.sha256` | — | verifica sin fallas |
| 8028 páginas archivadas | `f12afb98…` | coincide |
| 757 series | `6506fb03…` | coincide |
| `conciliacion.py` | `6f764845…` | sin cambios |
| `ejecutar_E3R.py` | `3b64a04d…` | sin cambios |

**Git (repositorio protegido)** [H]:
- HEAD `72ffae5`, rama `claude/algo-trading-simulation-platform-ngf7xo`;
- `git --no-optional-locks status`: 0 cambios; 0 stashes;
- índice `37490035…`, igual que al empezar;
- nada se escribió en el repositorio.

**Límites de la reproducción:**
- Se usó el venv local (Python 3.11, numpy 2.4.6), que reproduce byte a byte las salidas de F3.
- No se volvieron a descargar los WARC: se verificó el conjunto de páginas por hash.
- La ventana A guarda rutas absolutas de este entorno.

## 8. Riesgos y requisitos abiertos

1. **A depende de la Adenda R** [H]. Con la v3 pura, (iv) no se cumple en ningún año, y la condición de reapertura de `CIERRE_E3.md` §4 tampoco se cumple. Tu autorización tiene que nombrar **expresamente** las dos sustituciones.
2. **Margen de 2 semanas** [H]. Además, (iv′) aguanta en 2023 con una sola salida sin evidencia de 19; con dos, A cae.
3. **No hay archivo después del 2024-11-06** [H]:
   - un par ausente de Vision (falla D) no se puede detectar;
   - los renombres posteriores (FTM→S, EOS→A, MKR→SKY, FXS→FRAX, OM→MANTRA y DAR→D) se tratan como salida más listado nuevo, por la regla 3;
   - **[J]** es conservador en el precio, pero cambia la composición del universo (los nuevos símbolos quedan inelegibles 180 días). Se declara y no se corrige.
4. **Tres mapeos con certeza media**:
   - COCOS→COMBO y TVK→VANRY: solo está archivada la finalización, con relación 1:1 y fecha; falta la hora de cese;
   - BTCST: sentido de «1:10»; previo a A.
5. **Cortes de 1 día dentro de A sin anuncio** (SCR, USUAL, AXS) [I]. Una redenominación con |log₁₀ r| < 1 no se detectaría.
6. **Código posterior a la congelación de E3** (v2, mapeos, guarda). Lo mitigan 28 pruebas, 6 regresiones demostradas, el diff completo y la reproducción. **Falta una revisión independiente del diff y de la tabla de mapeos** [J].
7. **V-S4 sigue sin ejecutarse**, porque exchangeInfo responde HTTP 451 [H].
8. **Potencia baja** [I]: la estimada para A era 0,35–0,56 con 160 semanas; con 158 prácticamente no cambia (√(158/160) ≈ 0,994 en el estadístico). Un INSUFICIENTE informaría poco. Se acepta y se informa (v3 §7.2); no justifica cambiar la ventana.
9. **Cambio respecto del plan anterior** [H]. La ventana y el orquestador cambiaron. La autorización preparada antes (v1, «ADENDA R2») **no sirve**: el v2 no la acepta.

## 9. Veredicto

**A sigue siendo candidata válida**:
- inicio 2023-05-15; final 2026-05-18;
- 158 semanas evaluables, 0 % no evaluables;
- margen de 2 semanas;
- bajo la v3 con la Adenda 1, la Adenda 3 (segunda pasada definitiva) y la Adenda R con R1 literal.

**Con una condición explícita:** con la v3 congelada pura, sin la Adenda R, la ventana es INVÁLIDA, y la segunda pasada no cambia eso. No se cambió ninguna definición, umbral, filtro ni universo para ganar semanas. La única corrección que movió el inicio lo atrasó.

## 10. Recomendación sobre una nueva solicitud de autorización

**Sí, recomiendo preparar una solicitud nueva, solo para A** [J]. **No antes de:**
1. una revisión independiente de `DIFF_v1_v2.diff` y de `mapeos_adenda1.json`. Tiene que cubrir en particular los dos mapeos de certeza media y la decisión de abandonar R2 (BNX);
2. que la solicitud nombre expresamente:
   - la sustitución de (iv) por (iv′) y de la condición de reapertura de CIERRE §4;
   - el residual sin archivo posterior al 2024-11-06 y el tratamiento por la regla 3 de los cambios de símbolo sin anuncio;
   - el margen de 2 semanas y la potencia baja.

**Contenido técnico que la solicitud debería tener** (lo exige la guarda del v2):
- la frase nueva del v2: «AUTORIZO LA EJECUCION UNICA DE E3 (H1 Y H2) EN LA VENTANA A CON LA V3, LA ADENDA R CON R1 LITERAL, LA SEGUNDA PASADA Y LOS MAPEOS DE LA ADENDA 1»;
- el sha256 del v2 (`01fc9344…`);
- el sha256 del manifiesto (`8ee3bc07…`).

No creé ese archivo.

**Que las pruebas pasen no significa que el experimento esté listo.** Están listas la ventana, los mapeos y la guarda. Faltan la revisión independiente y tu decisión sobre la sustitución de (iv). No ejecuté nada y espero tu autorización explícita.
