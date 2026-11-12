# Resultado de la segunda lectura (protocolo SL-v1) y validez de la candidata A

**Fecha:** 2026-10-29 (UTC). Ningún retorno, IC ni estadístico se calculó ni se consultó.

## 1. Cadena de custodia

| Paso | UTC | Registro |
|---|---|---|
| Huellas de inicio (iguales al cierre de la fase v4) | 00:14:24 | `registro/huellas_inicio.txt` |
| SL-v1 congelado (protocolo, herramientas y copias de código congelado) | 00:24:56 | `registro/CONGELACION_SL-v1.txt` |
| Paquete ciego, escaneo Ω y control de reproducción | 00:25–00:26 | `registro/paquete_stdout.txt`, `omega_stdout.txt`, `control_pasada2_stdout.txt` |
| Lanzamiento del lector, con el encargo y el paquete fijados | 00:26:24 | `registro/LANZAMIENTO_LECTOR.txt` |
| Ronda 1 recibida | 00:40:24 | `registro/RECEPCION_RONDA1.txt` |
| Ronda 2 recibida y cálculo L2 | 00:59:08 | `registro/RECEPCION_RONDA2_Y_CALCULO.txt` |
| Adjudicación: lanzamiento y recepción | 01:00:11 / 01:02:21 | `registro/LANZAMIENTO_ADJUDICADOR.txt`, `RECEPCION_ADJUDICACION.txt` |

**Lector y adjudicador:**
- son agentes separados, con contexto nuevo;
- son de modelos distintos entre sí y del autor, pero de la **misma familia**;
- corren en el **mismo contenedor** y los lanzó el autor.

**Accesos:** el registro de archivos abiertos de los dos no muestra ninguna ruta fuera de lo permitido.

## 2. Control de reproducción (§8.1)

Corrí la conciliación congelada (`6f764845…`) con las resoluciones de la segunda pasada.
- `eventos.json`, `salidas.json` y `conciliacion.json` salieron **idénticos byte a byte** a los de la reparación.
- `ventana.json` coincide en todos los campos, salvo las rutas.
- **El circuito se reproduce.**

## 3. Ronda 1: los 47 eventos

- **47/47 concordantes** con la segunda pasada, en acción y fecha. No hubo discrepancias ni adjudicación.
- Las 4 fechas corregidas de los apalancados de 2023 (TRXDOWN 05-09, DOTUP y DOTDOWN 05-10, LINKUP 05-11) se reprodujeron a ciegas.
- También los 5 casos C como `AGREGA` y BKRW como `CORRIGE_PAR`.
- Enumerando las remociones por página, el lector encontró **TRXUP (2023-05-09) y LINKDOWN (2023-05-11)**: las dos omisiones que había agregado la reparación.

## 4. Ronda 2: escaneo Ω (169 candidatos en 108 páginas)

- **158 NO_SPOT:**
  - 126 en la barra lateral;
  - 22 de Liquid Swap;
  - 8 de futuros;
  - 1 de margen;
  - 1 canje que abre un par (PDA).
- **11 REMOCION_SPOT que no eran eventos de la conciliación:**

| Grupo | Par y E_N5 del lector | `clasificar` congelado |
|---|---|---|
| Canje con otro símbolo | MC 2023-11-07; PLA 2024-02-26; MATIC 2024-09-10 | A (no son fallas) |
| Redenominación con reapertura del mismo símbolo | QUICK 2023-07-17 (reabre 07-21); STRAX 2024-03-20 (reabre 03-28) | C explicada (no son fallas) |
| Tokens apalancados BLVT (anuncio «Updates on Binance Leveraged Tokens (BLVT) Services», 2024-02-19) | BNBUP, BNBDOWN, BTCUP, BTCDOWN, ETHUP y ETHDOWN, 2024-02-28 | **A** con E = 2024-02-28; **T (falla)** con E = la fecha de delisting (§5) |

**Corrección a una afirmación previa.** `REP/INFORME_REPARACION_E3H1H2.md` l. 64 dice: «Ninguna enumera un par X/USDT que no esté ya como evento». Eso vale para las páginas con **título** de exclusión. Pero el universo de la v3 §2.3 es «todas las exclusiones o remociones», y hay remociones spot de pares USDT en páginas con otro título (canjes y BLVT) que **no estaban en el universo**.

## 5. Ambigüedad decisiva y adjudicación (§6)

**El texto del anuncio BLVT fija dos fechas por par:**
- «Trading and subscription services for all BLVTs will be suspended at 2024-02-28 06:00 (UTC)»;
- «Delisting & Redemption Cessation Time»: 2024-04-01 (BNB), 04-02 (ETH) y 04-03 (BTC).

**La regla R-E de SL-v1 contiene dos frases que, para este texto, apuntan a fechas distintas:**
- la definición N5: «cesa la negociación spot» → 2024-02-28;
- la cláusula que **agregué yo** al redactar SL-v1: «En tokens apalancados, la fecha en que el token se "delista" es el cese de su negociación spot» → 2024-04-0x.
  - La escribí pensando en el anuncio de 2023, que da una sola fecha. No está en N5.

**Lecturas:**
- El lector eligió 2024-02-28 y dejó anotada la alternativa.
- Apliqué el mecanismo del §6: un adjudicador ciego, con X e Y en orden aleatorio (semilla 20261029, orden guardado en `privado/`).
- El adjudicador eligió la **fecha de delisting en los 6 casos**. Su razón: la cláusula es explícita y no tiene condiciones; tratarla como inaplicable sería «agregar una excepción que la regla no contiene». También dejó constancia de la tensión entre las dos frases.

**Cálculo con el código congelado** (`p0_pasada2.py` `d05c8dd5…`; Adenda R con R1 literal; resoluciones L2; `resoluciones_C` vacío; omitidos clasificados):

| Alternativa | (ii′) | Última falla en alcance | Inicio H | Semanas evaluables | Veredicto |
|---|---|---|---|---|---|
| E de los BLVT = 2024-02-28 (lector) | 2023-05-15 | LINKUP y LINKDOWN 2023-05-11 | 2023-05-15 | 158 (margen 2) | VÁLIDO |
| **E de los BLVT = delisting (adjudicado)** | **2024-04-08** | **BTCUP y BTCDOWN 2024-04-03 (T, en alcance)** | **2024-04-08** | **111** | **INVÁLIDO** |

**Orden en que lo hice, declarado:**
- calculé las dos alternativas (00:59) **antes** de lanzar al adjudicador (01:00), así que yo ya conocía la consecuencia de cada lectura;
- el adjudicador no la conocía: recibió solo la página, la regla R-E y las dos fechas, sin saber de dónde salía cada una;
- su elección fue en contra de la validez de A, así que ese orden no la favoreció.

**Robustez del resultado:**
- La v3 pura, que cuenta todas las fallas, da el mismo (ii) en las dos alternativas (`ii_v3_pura_lunes`): el resultado **no depende de R1 frente a R1′ ni del alcance**.
- (iv′) da 2018 en las dos.

## 6. Regla de decisión (§9) y recomendación

- **Por el §6**, la adjudicación resuelve a favor de la fecha de delisting, así que **A es INVÁLIDA**.
- **Por el §9**, aun tratando el punto como no resuelto, A seguiría siendo candidata solo si fuera VÁLIDA con **todas** las alternativas. No lo es.
- **Recomendación técnica: cerrar E3 sin cambiar la ventana.** Que siga NO EVALUABLE. No recurrir a B, a R1′ ni a reglas nuevas. Coincide con `DEC/INFORME_DECISION_E3H1H2.md` §7 R-2: «Si aparece una falla en alcance con E ≥ 2023-05-29, A es INVÁLIDO… sin recurrir a B ni a reglas nuevas».

**Lo que no hago.** Podría argumentarse que N5 prevalece sobre mi cláusula y que entonces A sería VÁLIDA. Elegir ahora esa lectura, **sabiendo que rescata la ventana**, sería exactamente el defecto que se le reprochó a R1′: corregir una regla después de ver su efecto. No lo hago.

**Si se considerara reabrir este punto,** sería una decisión metodológica humana, con el conocimiento de su consecuencia, y tendría que declararse así.

## 7. Límites

- El lector y el adjudicador no son independientes en sentido fuerte (misma familia, mismo contenedor, lanzados por el autor).
- El escaneo Ω cubre:
  - solo páginas archivadas en Common Crawl;
  - con publicación ≥ 2023-04-01 o sin publicación;
  - con expresiones regulares cuyo recall no está medido.
- La ambigüedad del §5 es un defecto de redacción de SL-v1, que es mío. Se declara y no se corrige después de conocer su efecto.
