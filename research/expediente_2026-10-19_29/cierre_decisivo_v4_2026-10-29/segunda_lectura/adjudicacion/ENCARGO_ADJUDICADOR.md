# Encargo al adjudicador (protocolo SL-v1, §6)

Vas a decidir, aplicando reglas de lectura fijas, cuál de dos lecturas de una fecha es la correcta según el texto de un anuncio archivado de Binance. No vas a calcular nada.

**Carpeta:** `A = /tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/cierre_decisivo_v4_2026-10-29/segunda_lectura/adjudicacion`

## Restricciones (obligatorias)

**Solo podés leer:**
- `A/ENCARGO_ADJUDICADOR.md`;
- `A/paquete/CASOS.json`;
- la página de `A/paquete/paginas/`.

**Solo podés escribir:**
- `A/adjudicacion.json`;
- `A/archivos_abiertos.txt`.

**No podés:**
- abrir ninguna otra ruta;
- usar la web;
- ejecutar programas del proyecto.

Podés usar `python3 -I` solo para leer el campo `texto` del JSON de la página y buscar dentro de él.

**No inventes:** cada elección lleva una cita textual del cuerpo del anuncio, de 300 caracteres como máximo.

## La página

Es un JSON con `titulo` y `texto`. Solo vale el **cuerpo del anuncio**:
- desde el título;
- hasta «Thanks for your support», «Binance Team», «Related Articles» o «Find us on Telegram».

La barra lateral no cuenta.

## Reglas de lectura (copia literal de las que usó el lector)

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

## Qué tenés que decidir

`A/paquete/CASOS.json` trae 6 casos. Cada uno tiene:
- el par;
- dos lecturas de E_N5, rotuladas X e Y. El orden es aleatorio y no indica nada.

Para cada caso, elegí:
- `"X"`;
- `"Y"`;
- `"NO_DETERMINABLE"`: si las reglas, aplicadas a este texto, no permiten elegir una sola sin agregar un criterio que las reglas no contienen. Explicá por qué.

Escribí `A/adjudicacion.json` así:

```
{"adjudicador": "<tu identificación>",
 "casos": [{"caso": "...", "eleccion": "X"|"Y"|"NO_DETERMINABLE", "cita": "...", "razonamiento": "..."}],
 "observacion_sobre_las_reglas": "..."}
```

Al terminar, respondé con un resumen breve de tus elecciones y del motivo.
