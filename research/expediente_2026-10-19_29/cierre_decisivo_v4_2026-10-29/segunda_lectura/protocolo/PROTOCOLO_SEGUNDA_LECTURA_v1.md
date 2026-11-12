# Protocolo SL-v1: segunda lectura de los 47 eventos y recálculo de la validez de A

**Versión:** SL-v1.

**Estado:** se congela con su sha256 y hora UTC en `registro/CONGELACION_SL-v1.txt` **antes** de:
- armar el paquete;
- correr el escaneo Ω;
- lanzar al lector.

No se modifica después. Una corrección exigiría un SL-v2 nuevo, con su propio motivo, y la conservación del SL-v1.

**Autor:** el agente autor de la reparación, del v3 y del diseño v4. **No es independiente.** La lectura la hace otro agente (§3).

**Qué no hace este protocolo:**
- no calcula retornos, IC ni estadísticos de H1 o H2;
- no lee O, H, L, C ni QV;
- no crea ni consume autorizaciones;
- no modifica árboles congelados: trabaja sobre copias verificadas por hash y escribe solo en `cierre_decisivo_v4_2026-10-29/`.

**Qué no puede cambiar:**
- la ventana se obtiene de las reglas;
- ninguna regla se elige por la ventana que produce.

---

## 1. Objeto

1. Volver a leer, con un lector distinto del autor y sin información sobre la ventana, los **47 eventos con fecha** del universo de anuncios. Son las claves de `eventos` en:
   - `reparacion_E3H1H2_2026-10-26/segunda_pasada/resoluciones_manuales.json`, sha256 `41a13221…`;
   - que coinciden con las 47 claves con fecha de la primera pasada (`resultados/conciliacion_pasada1/eventos.json`, `bdc3239c…`).
2. Detectar remociones de pares spot X/USDT que la extracción haya omitido (§7).
3. Recalcular, con el código congelado y sin cambios, la conciliación y la ventana conforme a la Adenda R con la regla R1 literal (§8).
4. Aplicar la regla de decisión sobre la candidata A (§9), fijada en este documento.

## 2. Reglas de lectura fijadas antes de leer

### R-E · Fecha efectiva

Se aplica N5 (`NOTAS_IMPLEMENTACION_v3.md`, l. 16): «el día UTC en que cesa la negociación spot del par, según el texto».

- Si el texto da solo la fecha del anuncio y «en N días», E = anuncio + N.
- **No son E:**
  - la fecha de publicación;
  - el cese de depósitos o retiros;
  - una conversión;
  - el cese de margen, futuros, bots, Earn o préstamos;
  - la fecha de la barra lateral.
- En tokens apalancados, el «delist» del token es el cese de su negociación spot.
- Si una postergación o cancelación del **mismo** documento cambia la fecha, rige la fecha final que ese documento fija.

Por qué rige N5 y no la regla del extractor (A3.1.5): ver el dictamen D-3. En síntesis:
- la Adenda 3 «no cambia criterios» (l. 8);
- A3.1.5 está en la sección del extractor y se rotula «(N5)»;
- la v3 prevalece (§0.2) y no define la fecha efectiva.

El lector anota **también** la primera fecha del título, para transparencia, pero no la usa como E.

### R-acción · Qué hace el texto con el par X/USDT del ítem

| Valor | Cuándo |
|---|---|
| `REMUEVE` | El texto remueve o cesa la negociación spot del par X/USDT |
| `EXCLUYE_TOKEN` | El texto excluye el token X de la negociación spot sin enumerar pares, o enumerándolos con X/USDT entre ellos |
| `AGREGA` | El texto abre o agrega el par X/USDT y no lo remueve |
| `CANCELADA` | El texto cancela la remoción del par |
| `CORRIGE_PAR` | El texto aclara que el par removido es otro símbolo, no X/USDT |
| `NO_MENCIONA` | El cuerpo no menciona al par ni al token |
| `OTRA` | Cualquier otro caso, con nota |

### R-cuerpo

- Vale el cuerpo del anuncio (A3.1.1): desde el título, sin la cabecera, hasta «Thanks for your support», «Binance Team», «Related Articles» o «Find us on Telegram».
- La barra lateral y los títulos de otros anuncios **no** cuentan.

### R-fuente

- Solo las copias locales de las páginas archivadas que trae el paquete (`paquete/paginas/`), verificadas por hash.
- Prohibido usar: la web, otros documentos del proyecto, lecturas previas, informes o la memoria de otros casos.
- Si el texto no alcanza, el valor es `null`, con la regla `NO_DETERMINABLE`. **No se infiere ni se completa.**

### R-cita

Cada campo con contenido lleva una cita textual de la página, de 300 caracteres como máximo.

## 3. Lector

- **Quién:** un agente separado, con contexto nuevo, que no escribió la reparación, el v3, el diseño v4 ni este protocolo.
- **Límite que se declara:** es de la misma familia de modelos, corre en el mismo contenedor y lo lanza el autor. **No es una revisión humana ni independiente en sentido fuerte.**
- **Ceguera:**
  - recibe solo `paquete/` y este protocolo, sin el §9 (regla de decisión) ni el §8 (cálculo);
  - **no** recibe fechas de pasadas anteriores, categorías, últimos días activos, ventanas, semanas ni potencia.
- **Prohibiciones:**
  - abrir cualquier ruta fuera de `paquete/` y de su carpeta de salida;
  - ejecutar programas del proyecto;
  - leer precios.
- Registra la lista de archivos que abrió.

## 4. Paquete

`herramientas/preparar_paquete.py` arma el paquete:

| Contenido | Dónde |
|---|---|
| Por ítem: `id` (L01…L47, ordenado por par y archivo), `par` y `paginas` | `paquete/ITEMS.json` |
| Las URL de la primera pasada mapeadas a sus archivos, más el archivo fuente de la segunda pasada | Lista `paginas` de cada ítem |
| Copias de las páginas, con sha256 | `PAGINAS.sha256` |
| Mapa ítem → clave | `privado/mapa_items.json`, fuera del paquete |

## 5. Salida del lector y conversión

**Salida:** `lector/lectura_L2.json`, con esta estructura:

```
{"lector": str, "archivos_abiertos": [..],
 "items": [{"id", "par", "paginas_leidas": [..], "titulo", "fecha_titulo", "accion_par", "E_N5", "regla_E",
            "cita_E", "cita_accion", "postergacion_cancelacion_correccion": {"hay": bool, "cita"},
            "reapertura": {"hay": bool, "cita"}, "certeza": "alta|media|baja", "nota"}],
 "remociones_por_pagina": [{"archivo", "pares": [{"par", "E_N5", "cita"}]}]}
```

`remociones_por_pagina` enumera, en **cada** página leída, todos los pares X/USDT cuya negociación spot se remueve, sean o no el par del ítem.

**Conversión.** La aplica `herramientas/construir_resoluciones_L2.py` con reglas fijas, copiadas de su encabezado:
- `REMUEVE` o `EXCLUYE_TOKEN` con E: «confirmar» si E = E1 (la E de la primera pasada); «fecha_corregida» si no.
  - Excepción A3.5 (b): si la categoría de la primera pasada es C no explicada y hay reapertura, postergación o cancelación documentada, el resultado es «C_explicada».
- `AGREGA` o `CANCELADA`: «C_explicada» si la categoría de la primera pasada es C no explicada; «descartar» si no.
- `CORRIGE_PAR`: «descartar».
- Cualquier otro caso: `NO_DETERMINABLE`.

## 6. Comparación y discrepancias

- **Concordante:** la acción convertida y, si es una corrección, su E coinciden con la segunda pasada de la reparación.
- **Discrepante:** cualquier otra diferencia. Se adjudica.
  - **Quién:** un tercer agente, distinto del autor y del lector, con contexto nuevo.
  - **Qué recibe:** la página, las reglas del §2 y las dos lecturas rotuladas X e Y, en orden aleatorio con semilla 20261029. No recibe su origen ni el §9.
  - **Qué elige:** X, Y o `NO_DETERMINABLE`, con cita.
  - **Qué se registra:** el orden X/Y.
- **Sin resolver tras la adjudicación:** no se elige. Se calcula la ventana con cada alternativa (§9).
- **Si hay más de 4 casos sin resolver:** el resultado es **BLOQUEANTE** y se informa sin calcular combinaciones.

## 7. Eventos omitidos (regla de D-5)

1. **Dentro de las páginas leídas.** Cada par de `remociones_por_pagina` que no sea ya un evento de esa página es un candidato.
2. **Escaneo Ω** (`herramientas/escaneo_omega.py`, regla fija en su encabezado). Barre:
   - las páginas con publicación ≥ 2023-04-01 o sin publicación;
   - las menciones X/USDT o XUSDT con una palabra de remoción a ≤ 250 caracteres;
   - excluyendo los pares que ya son eventos de esa página.

   Los candidatos con la etiqueta FUT, MARGEN u OTRO también se leen, pero en lote, para confirmar que no son spot.
3. **Lectura de los candidatos.** El mismo lector, en una segunda ronda, con las reglas del §2, y sin ver la ventana.
4. **Clasificación.** Las remociones confirmadas de pares X/USDT con E ∈ [2018-01-01, 2026-05-31] se clasifican con la función congelada `clasificar` mediante `herramientas/clasificar_omitidos_L2.py`:

   | Categoría | Tratamiento |
   |---|---|
   | T, D, o C sin explicación | Falla, que se suma a (ii′) |
   | A o B | No se suman: solo podrían agregar evidencia ANUNCIO a (iv′), así que omitirlas es conservador |

5. **Por qué el escaneo empieza en 2023-04-01.** Una falla en alcance con E ≥ 2023-05-29 invalida A. Una falla anterior a 2023-05-12 no mueve el inicio. El margen de 6 semanas cubre anuncios publicados antes de su E.
   - Las remociones con E anterior **no pueden** mover (ii′) más allá del inicio actual.
   - **No pueden** empeorar (iv′): (iv′) solo cuenta como evidencia los eventos A o B (`p0_pasada2.py`, l. 66), así que agregar eventos solo puede bajar los casos SIN_EVIDENCIA.

## 8. Cálculo

Lo hace `herramientas/calcular_ventana.py`.

**Pasos:**
1. **Control de reproducción.** Con las resoluciones de la segunda pasada y los omitidos de la reparación, la salida tiene que reproducir `ventana_A_pasada2.json` (`dcbd80ab…`) en los componentes, las fallas, el inicio, las semanas y el veredicto. Si no lo reproduce, se detiene todo.
2. **Cálculo L2:**
   - `conciliacion.py` (`6f764845…`) sobre `resoluciones_L2.json`;
   - después, `p0_pasada2.py` (`d05c8dd5…`) con un `resoluciones_C_vacio.json` (`{}`) y `fallas_extra_L2.json`.
   - **Por qué vacío:** `p0_pasada2.py` (l. 107) descarta una falla «C no explicada» si `resoluciones_C.json` marca su par como «agregado». Si se usara el de P0, quedaría pisada la relectura de los 5 casos C. Con `{}`, la condición de esas fallas sale solo de la conciliación L2. En el control del paso 1 se usa el original, para reproducir exactamente.

**Parámetros fijos:**
- Adenda R con R1 literal (alcance por las listas de cada lunes);
- (i), (ii′) y (iv′);
- (iii) no aplicada;
- fin de H el 2026-05-18;
- ≥ 156 semanas evaluables y ≤ 20 % no evaluables.

**Registro.** Comandos, intérprete, entradas y salidas con sha256, y salida estándar y de error.

## 9. Regla de decisión sobre A (no la recibe el lector)

Fijada antes de leer. Coincide con la del `INFORME_DECISION_E3H1H2.md`, §7 R-2: «si aparece una falla en alcance con E ≥ 2023-05-29, A es INVÁLIDO: E3 queda NO EVALUABLE, sin recurrir a B ni a reglas nuevas».

| Resultado del cálculo L2 | Qué se informa |
|---|---|
| **VÁLIDO** | «A sigue siendo candidata» con la ventana que dan las reglas, aunque su inicio difiera del 2023-05-15. **No es una autorización** |
| **INVÁLIDO** | Se recomienda **cerrar E3 sin cambiar la ventana**: sin B, sin R1′ y sin reglas nuevas |
| Alternativas sin resolver (§6) | A sigue siendo candidata **solo si es VÁLIDA con todas**. Si alguna da INVÁLIDO, se recomienda el cierre |
| Control del §8.1 falla o hay más de 4 casos sin resolver | **BLOQUEANTE** |

## 10. Qué queda fuera y se declara

| Tema | Tratamiento |
|---|---|
| Secciones `sin_fecha`, `tokens_sin_par`, `renombres` y `vs2` | Se usan las de la segunda pasada sin cambios. Su relectura no está en el alcance. Los renombres solo afectan a (iv′) por A3.7 |
| Remociones con E posterior al 2024-11-06 | No hay anuncios archivados. Es un punto ciego: no se detectan y no se suponen |
| `resoluciones_C.json` | Solo en el control del §8.1. En el cálculo L2 se reemplaza por `{}` (§8.2), así que la relectura de los 5 casos C decide sola |
