# Encargo al lector · segunda lectura de anuncios archivados (protocolo SL-v1, §2, §3, §5 y §7)

Vas a leer anuncios oficiales de Binance archivados en Common Crawl y extraer **hechos del texto**. No vas a calcular nada y no vas a decidir nada más allá de lo que el texto dice.

## Carpeta de trabajo

`D = /tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/cierre_decisivo_v4_2026-10-29/segunda_lectura`

## Restricciones (obligatorias)

**Solo podés leer:**
- `D/ENCARGO_LECTOR.md`;
- `D/paquete/` (ronda 1);
- `D/paquete_omega/` (ronda 2).

**Solo podés escribir en `D/lector/`.**

**No podés:**
- abrir ninguna otra ruta del sistema de archivos;
- en particular, abrir `D/privado/`, `D/calculo/`, `D/protocolo/`, `D/herramientas/`, `D/omision/`, otras carpetas del scratchpad, informes, resoluciones previas ni nada bajo `/root/.claude/`;
- usar la web;
- ejecutar programas del proyecto.

Podés usar herramientas de lectura y búsqueda de texto (Read, Grep, `python3 -I` para extraer el campo `texto` de un JSON o buscar dentro de él).

**Al terminar**, escribí en `D/lector/archivos_abiertos.txt` la lista de todos los archivos que abriste.

**No inventes.** Si el texto no alcanza para fijar un dato, poné `null` y explicá por qué en `nota`. Cada dato lleva una cita textual de la página, de 300 caracteres como máximo.

## Formato de las páginas

Cada página es un JSON con `titulo`, `texto`, `url`, `captura`, etc.

`texto` incluye menús y una barra lateral con títulos de **otros** anuncios. Solo vale el **cuerpo del anuncio**:
- empieza en el título;
- termina en «Thanks for your support», «Binance Team», «Related Articles» o «Find us on Telegram».

Lo que aparezca en la barra lateral o en «Articles in this section» **no cuenta**.

## Reglas de lectura

### R-E · Fecha efectiva E_N5

E_N5 es el día UTC en que **cesa la negociación spot del par X/USDT**, según el texto.
- Si el texto dice solo «en N días» desde el anuncio, E_N5 = fecha del anuncio + N.
- **No son E_N5:**
  - la fecha de publicación;
  - el cese de depósitos o retiros;
  - una conversión;
  - el cese de margen, futuros, bots, Earn, préstamos o Liquid Swap.
- En tokens apalancados (UP, DOWN, BULL, BEAR), la fecha en que el token se «delista» es el cese de su negociación spot.
- Si el **mismo** documento posterga o cancela, rige la fecha final que ese documento fija.

Anotá también, por separado, la primera fecha que aparezca en el **título** (`fecha_titulo`), aunque no sea E_N5.

### R-acción · `accion_par`, qué hace el texto con el par X/USDT del ítem

| Valor | Cuándo |
|---|---|
| `REMUEVE` | Remueve o cesa la negociación spot de X/USDT |
| `EXCLUYE_TOKEN` | Excluye el token X de la negociación spot sin enumerar pares, o enumerándolos con X/USDT entre ellos |
| `AGREGA` | Abre o agrega X/USDT y no lo remueve |
| `CANCELADA` | Cancela la remoción de X/USDT |
| `CORRIGE_PAR` | Aclara que el par removido es otro símbolo, no X/USDT |
| `NO_MENCIONA` | El cuerpo no menciona al par ni al token |
| `OTRA` | Otro caso; explicalo en `nota` |

## Ronda 1: los 47 ítems de `D/paquete/ITEMS.json`

Cada ítem trae `id`, `par` (por ejemplo `DOTUPUSDT` = DOTUP/USDT) y `paginas`, que pueden ser 1 o más copias del mismo anuncio. Leé todas las páginas del ítem.

Escribí `D/lector/lectura_L2.json` así:

```
{"lector": "<tu identificación>", "archivos_abiertos": [...],
 "items": [{"id": "L01", "par": "...", "paginas_leidas": ["..."], "titulo": "...", "fecha_titulo": "YYYY-MM-DD"|null,
            "accion_par": "...", "E_N5": "YYYY-MM-DD"|null, "regla_E": "FECHA_EXPLICITA"|"ANUNCIO_MAS_N_DIAS"|"NO_DETERMINABLE",
            "cita_E": "..."|null, "cita_accion": "...",
            "postergacion_cancelacion_correccion": {"hay": true|false, "cita": "..."|null},
            "reapertura": {"hay": true|false, "cita": "..."|null},
            "certeza": "alta"|"media"|"baja", "nota": "..."}],
 "remociones_por_pagina": [{"archivo": "...", "pares": [{"par": "XUSDT", "E_N5": "YYYY-MM-DD"|null, "cita": "..."}]}]}
```

- Los 47 ítems, en el orden de `ITEMS.json`.
- `remociones_por_pagina` enumera, para **cada** página leída (las 19 copias distintas), **todos** los pares X/USDT cuya negociación spot remueve el cuerpo, sean o no el par de algún ítem. Si una página no remueve ningún par X/USDT, poné `"pares": []`.
- Si el cuerpo excluye un token sin enumerar pares, incluí `TOKENUSDT` y explicalo en la cita.

**Escribí `lectura_L2.json` completo antes de empezar la ronda 2.**

## Ronda 2: candidatos de `D/paquete_omega/CANDIDATOS.json`

Un escaneo mecánico marcó 169 menciones de pares X/USDT cerca de palabras de remoción en 108 páginas. Casi todas deberían ser de futuros, margen, Liquid Swap o la barra lateral, pero **no lo des por supuesto**: verificá cada una en su página.

Escribí `D/lector/lectura_omega_L2.json` así:

```
{"items": [{"id": "O001", "par": "...", "archivo": "...",
            "resultado": "REMOCION_SPOT"|"NO_SPOT"|"NO_DETERMINABLE",
            "motivo": "FUTUROS"|"MARGEN"|"LIQUID_SWAP"|"BARRA_LATERAL"|"CANJE_O_RENOMBRE"|"OTRO_PRODUCTO"|"REMOCION_SPOT"|"OTRO",
            "E_N5": "YYYY-MM-DD"|null, "cita": "...",
            "postergacion_cancelacion": true|false, "reapertura": true|false, "nota": "..."}]}
```

`REMOCION_SPOT` vale solo si el **cuerpo** de ese anuncio remueve o cesa la negociación **spot** de X/USDT. Una remoción solo de margen, futuros o Liquid Swap es `NO_SPOT`.

## Entrega

Al terminar, respondé con un resumen breve:
- cuántos ítems leíste;
- cuántos con certeza baja o `null`;
- cuántos candidatos Ω resultaron `REMOCION_SPOT`;
- cualquier problema de acceso o de formato.

No incluyas opiniones sobre ventanas, semanas, validez ni resultados: no son parte de este encargo.
