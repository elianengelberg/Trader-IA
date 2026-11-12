# E4 · Prerregistro v1: H-XS-REV-1 prospectiva (reversión transversal diaria, información)

**Estado: BORRADOR v1. No está congelado ni anclado.**
- Reemplaza al borrador v0 (`ejecutiva_post_E3_2026-10-29/e4_xsrev_prospectivo/PRERREGISTRO_E4.md`, sha `f28f336f…`), que queda sin cambios.
- Se congela con `CONGELACION_E4_v1.txt`, que lleva el sha256 de este archivo y de cada `codigo/*.py`, y se ancla afuera (§10), solo con tu autorización.
- Después de congelado, cualquier cambio exige una versión nueva, un T0 nuevo y datos nuevos.

**Origen:** P19 de `entrega_direccion_tecnica_2026-10-26/PROPUESTAS_TECNICAS.md` (sha del archivo `3aa6eb4c…`), escrita antes de este experimento.

**Cambios respecto de P19 (declarados):**
1. **Es prospectiva.** Los datos son posteriores al anclaje, sin desarrollo ni validación históricos.
2. **La métrica principal es la información (IC)**, no el retorno neto. P19 misma prevé que los costos se coman el efecto.
3. **La parte económica es solo larga**, con el quintil perdedor frente a pesos iguales. No hay venta corta, así que no hay funding ni préstamo.

Las dos opciones marcadas **[DECISIÓN]** son tuyas. El texto y el código usan la recomendada.

## 1. Hipótesis (falsable)

**H1-E4.** En el universo líquido de pares spot X/USDT de Binance, el retorno del día t−1 predice en sentido inverso, en la sección transversal, el retorno de la posición que se arma una barra horaria después. La media del IC diario de Spearman entre −r(t−1) y el retorno de 01:00 UTC de t a 01:00 UTC de t+1 es mayor que 0.

**H0:** media ≤ 0.

**[DECISIÓN 1] Retraso.**

| Opción | Qué significa | Estado |
|---|---|---|
| **1 h** | La barra de retraso de P19 con datos horarios, que P19 admite («OHLCV diario u horario»). Prueba la reversión de rezago 1 y evita el rebote entre compra y venta, porque la entrada es una hora después del cierre que forma la señal | Recomendada |
| 1 día (v0) | Prueba la reversión de rezago 2. Es un efecto distinto y presumiblemente más débil [Hip] | Alternativa |

Elegir 1 día es una constante del código (`RETRASO = "1d"`) más esta sección.

**Fundamento:** provisión de liquidez (Lehmann 1990; Jegadeesh 1990; Nagel 2012). En cripto la evidencia diaria es mixta: es una pregunta, no una apuesta (P19).

## 2. Datos

**Fuente:** Binance Vision, archivos diarios oficiales de pares spot USDT.
- `data/spot/daily/klines/<S>/1d/<S>-1d-<D>.zip` y `…/1h/<S>-1h-<D>.zip`, cada uno con su `.CHECKSUM` (sha256).
- Los archivos diarios se conservan desde 2017 (BTCUSDT y ETHUSDT: 3360 días desde el 2017-08-17).
- Se publican desde unas 2 h después de cerrar el día; algunos pares, más tarde.
- Ambos datos surgen de los metadatos del listado S3 del 2026-10-29 (`fuente/retencion_tamanos.json`).
- Binance regenera archivos viejos: las velas de 2017 tienen fecha de subida de 2023. Por eso vale **nuestra** copia con su manifiesto anclado.

**Licencia** (Binance Vision Dataset Terms v1.0, 2026-08-26, `fuente/Binance_Vision-Terms_of_Use.pdf`, sha `0ec62cd2…`):
- CC BY-NC-SA 4.0.
- Uso permitido: investigación personal no productiva.
- Prohibido: el uso para ejecución de trading propio en vivo y el uso comercial (§4.2–4.4).
- Hay que respetar los límites de descarga (§7).

**Período:**
- Días de formación desde T0, más los 31 días previos, que solo sirven para el universo y la señal del arranque.
- **T0** = el día UTC siguiente al del bloque de Bitcoin que confirma el ancla de `CONGELACION_E4_v1.txt`. Queda en `INICIO_E4.json`; el evaluador lo verifica y no lo acepta como argumento.

**Recolección:**
- `codigo/recolector.py`, por lotes (recomendado: mensual), en almacenamiento persistente.
- No abre los ZIP.
- Verifica cada `.CHECKSUM`.
- Guarda el ZIP y su `.CHECKSUM`.
- Escribe `MANIFIESTO.sha256` por día y lo encadena en `REGISTRO.jsonl`.
- Si hay un error de red, el día queda marcado y el proceso termina con código 2.
- Pausa de 0,2 s entre pedidos.
- La cabeza del registro se ancla en cada lote (§10).

**Separación:**
- No se usa ningún dato de los árboles congelados.
- Las series de E3 quedan tapadas por la zona aislada y por la guarda de rutas, que se aplica a datos, destino y salida.

## 3. Definiciones (implementadas en `codigo/nucleo.py`)

**Precios.** Para el día UTC d:
- cierre(d) = cierre de la vela 1d (precio a las 24:00 de d);
- entrada(d) = cierre de la primera vela 1h de d (precio a las 01:00 de d). Si no hay vela de las 00:00, falta.

**Día activo:** vela 1d con operaciones > 0 y cierre > 0.

**Retorno diario:** r(d) = cierre(d)/cierre(d−1) − 1, si d y d−1 son activos.

**Universo U(t),** solo con datos ≤ t−1:
- pares X/USDT activos los 30 días [t−30, t−1];
- se excluyen:
  - la lista fija: estables y fiat de la v0, más los envoltorios **WBTC, WBETH y BETH**;
  - los apalancados X{UP,DOWN,BULL,BEAR} cuando existe XUSDT;
  - **por paridad**: los 30 cierres en [0,97; 1,03]. Esto atrapa estables nuevas o no listadas;
- se toman los 100 de mayor mediana de volumen en USDT;
- si quedan menos de 30, el día no es evaluable.

**Señal:** s = −r(t−1), conocida a las 00:00 de t.

**Resultado:** entrada(t+1)/entrada(t) − 1. Se compra a las 01:00 de t y se vende a las 01:00 de t+1.

**IC_t:** Spearman con rangos promedio en los empates, sobre los pares de U(t) que tienen resultado.
- Un par sin resultado es una **salida**: sale del IC, se cuenta y en la cartera rinde 0.
- Las salidas cubren deslistados, suspensiones, archivos con checksum distinto, ilegibles o faltantes.
- **Renombres y cambios de símbolo:** el símbolo viejo sale y el nuevo entra cuando cumple 30 días activos. No hay mapeo ni empalme de series.

**Lectura de los archivos:**
- acepta CSV con o sin encabezado, y marcas en ms o µs (spot usa µs desde el 2025-01-01);
- exige que la vela sea del día del archivo;
- un archivo ilegible es un par-día faltante;
- si los ilegibles superan el 1 %, se aborta sin calcular nada y la mirada no se consume.

## 4. Miradas

**[DECISIÓN 2] Esquema de miradas.**

| Opción | Esquema | Estado |
|---|---|---|
| **Dos miradas fijas en el calendario** | 365 y 730 días de formación, con gasto de α de Lan-DeMets tipo O'Brien-Fleming | Recomendada |
| Una sola mirada a 365 días | Límite calibrado 2,006 | Alternativa |

Las fechas son T0 + 365 + 3 y T0 + 730 + 3, por el rezago de publicación.

**Mirada 1:**
- corta solo si cruza un límite (§6);
- si no corta, el resultado contiene **solo** `CONTINUAR` y el número de días evaluables. Ningún estadístico se calcula para mostrar, ni se guarda ni se imprime;
- si hay más del 20 % de días no evaluables, la mirada se **omite** y el α queda para la final.

**Reglas comunes:**
- Cero reintentos: el registro impide repetir una mirada o seguir después de una final.
- Una evaluación que aborta por datos o integridad (pasos 1 a 6 de `evaluar.py`) no calcula nada y no consume la mirada.
- `--solo-validar` se puede correr en cada lote para detectar a tiempo cambios de formato. Solo cuenta archivos.

## 5. Estadística

**Estadístico:** media del IC diario, error estándar de Newey-West (Bartlett, 5 rezagos) y t.

**Por qué los límites se calibran:**
- Con valores críticos normales, ese t rechaza de más: con 365 días, el α real es de 0,028 a 0,032 en lugar de 0,025 (`registro/alfa_preciso.json`, 100 000 simulaciones).
- Los límites se calibran por simulación determinista (semilla 20261029, 200 000 series gaussianas iid y sus antitéticas, numpy 2.4.6) **con los n observados**.

**Valores con los n planificados:**

| Esquema | Límite |
|---|---|
| Dos miradas | b1 = 3,097 (365) y b2 = 1,991 (730) |
| Una mirada | 2,006 (365) o 1,981 (730) |

La evaluación los recalcula con los días evaluables reales.

**Error real medido (`registro/alfa_preciso.json`):**

| Escenario | α real |
|---|---|
| Nulo gaussiano iid | 0,0256 |
| Colas t5 con AR(1) 0,1 | 0,027 |
| Colas t5 con AR(1) 0,2 | 0,029 |

Ese residuo es un límite declarado. Se informa la autocorrelación del IC de rezago 1 como diagnóstico, sin efecto en la clase.

**Intervalos repetidos:** media ± b_k·EE, con cobertura simultánea en las dos miradas.

**Dependencia:**
- La dependencia entre monedas queda dentro de cada IC diario: se agrega antes de la prueba, al estilo Fama-MacBeth.
- La dependencia entre días la cubre Newey-West.

## 6. Clasificación (fijada ahora)

| Clase | Condición en la mirada k | Lectura |
|---|---|---|
| INVÁLIDO (solo final) | Más del 20 % de días no evaluables, o menos del 80 % de los días planificados | Sin conclusión |
| RESPALDADA_INFORMACION | t ≥ b_k y sin fragilidad (§7) | Hay información transversal de reversión. **No es rentabilidad** |
| RESPALDADA_NO_ROBUSTA | t ≥ b_k con alguna fragilidad (§7) | Señal que no supera los criterios de P19 |
| EN_CONTRA_SIGNO_OPUESTO | t ≤ −b_k | Hay continuación, no reversión. Cierra H1-E4 |
| REFUTADA_IC_MINIMO | media + b_k·EE < 0,01 | Descarta un IC ≥ 0,01. **0,01 es un umbral de información fijado por convención, no económico.** La relevancia económica la decide solo el §8 |
| CONTINUAR (solo mirada 1) | Ninguna de las anteriores | Sin números |
| INSUFICIENTE (solo final) | Ninguna de las anteriores | **No equivale a refutar** |

## 7. Robustez (criterios de invalidación de P19)

Se calculan solo si la clase es RESPALDADA. Pueden rebajarla, nunca subirla, y no agregan pruebas: no gastan α.

| Criterio | Condición de fragilidad |
|---|---|
| (a) Pocos días extremos | La media del IC sin el 5 % de días con mayor \|IC\| es ≤ 0 |
| (b) Nombres ilíquidos | La media del IC entre los 50 más líquidos de U(t) es ≤ 0 |
| (c) Componente de mercado (beta × signo del mercado) | El promedio de las medias del IC en los días en que el mercado de la señal y el del resultado tienen igual y distinto signo es ≤ 0 |

## 8. Benchmark, costos y descarte económico (secundario)

**Cartera:**
- solo larga, con el quintil de mayor señal (los peores de ayer);
- pesos iguales;
- rebalanceo diario a las 01:00 UTC.

**Benchmark:**
- pesos iguales en U(t), con el mismo horario;
- sus costos de rebalanceo no se cargan, lo que es conservador para la estrategia.

**Costos por lado:**
- comisión taker de 7,5 bps (supone el descuento por pagar en BNB; sin descuento son 10);
- medio spread de 5 bps;
- costo diario = rotación × 2 × (comisión + medio spread);
- no hay funding, porque es spot y solo larga;
- no se modela el impacto: el tamaño es de investigación.

**Sensibilidad declarada** (no cambia ninguna clase):

| Comisión (bps) | Medio spread (bps) |
|---|---|
| 7,5 | 10 |
| 7,5 | 20 |
| 10 | 5 |

**Descarte rápido (P19):** si el diferencial bruto medio frente al benchmark es menor que 2 veces el costo diario medio, **no hay valor económico**, aunque haya información.

Se informan el neto y su t de Newey-West, sin umbral confirmatorio.

## 9. Potencia (aproximación normal con los límites calibrados; supuestos [Hip], no medidos)

Detalle en `registro/potencia_disenos.txt`.

- El desvío diario del IC tiene un **mínimo teórico** bajo H0 de ≈ 1/√99 ≈ 0,10 con 100 monedas independientes. La estructura de factores lo sube, y **no hay medición**.

| sd del IC | IC | Una mirada a 365 | Dos miradas: potencia total | Dos miradas: P(cortar en 365) |
|---|---|---|---|---|
| 0,15 | 0,02 | 0,62–0,71 | 0,90–0,95 | 0,21–0,29 |
| 0,20 | 0,02 | 0,39–0,46 | 0,68–0,76 | — |
| 0,25 | 0,02 | 0,27–0,32 | 0,49–0,57 | — |

Por eso se recomiendan dos miradas: la potencia no depende de acertar el desvío con una sola fecha.

## 10. Integridad y ancla (requieren tu autorización)

1. **Congelación:** `CONGELACION_E4_v1.txt` con el sha256 de este archivo y de **todos** los `codigo/*.py`.
   - El evaluador la verifica antes de importar el núcleo y rechaza código sin congelar.
   - Versiones fijas: Python 3.11 y numpy 2.4.6.
2. **Ancla mínima:**
   - `ots stamp` (OpenTimestamps 0.7.2) sobre `CONGELACION_E4_v1.txt`, que da el tiempo y es independiente de nosotros;
   - el sha256 de `CONGELACION_E4_v1.txt` va a **un testigo externo** antes de T0, lo que da la unicidad e impide elegir entre varias versiones selladas;
   - T0 sale del bloque que confirma el sello.
3. **Inicio:** `INICIO_E4.json` con el sha de la congelación, la hora del bloque y T0. Su sha256 va en el primer sello mensual y el evaluador exige que se lo pasen.
4. **Cada lote:** `ots stamp` del `REGISTRO.jsonl`. Su última línea encadena los manifiestos por día.
5. **Cada mirada:** se anota en `REGISTRO.jsonl` y se sella antes de comunicar el resultado.

## 11. Lo que E4 no puede concluir

- Rentabilidad, capital u operación real. Ninguna clase autoriza dinero real, y la licencia de los datos prohíbe usarlos para trading en vivo.
- Un INSUFICIENTE no es evidencia en contra.
- El resultado vale para el período observado. Una prueba económica neta exigiría otro prerregistro y otros datos.
