# PROPUESTA DE PRERREGISTRO: H-EMA9-VWAP v0.2

> **PROPUESTA NUEVA · PENDIENTE DE APROBACIÓN · NO EJECUTADA · NO CONGELADA**
> - **No** es la «v1» histórica (citada como `3114b565…`, **no recuperada**) ni la reconstruye.
> - **No reemplaza** a la v0.1 (`fase_documental_2026-10-20/PROPUESTA_PRERREGISTRO_H-EMA9-VWAP_v0.1.md`, SHA-256 `6a22ccbfdf536e4b4f8f202ef8f655fabbc436e612af06c844757f5e9ccab63a`), que se conserva intacta.
> - Redactada sin mirar precios ni resultados.
> - Estadística: `MARCO_ESTADISTICO_VALIDADO.md` (MEC v0.2), sin calibrar todavía.

## 0. Cambios respecto de la v0.1

| # | Tipo | Cambio | Motivo |
|---|---|---|---|
| C1 | Técnico | El benchmark y la exposición se calculan **en frecuencia horaria**: exposición constante ε rebalanceada cada hora y compuesta dentro del día (MEC §2) | La v0.1 restaba ε·r_diario a un rendimiento intradía. Mezclaba frecuencias y cargaba al benchmark con las horas 00–03, en las que la estrategia no puede estar |
| C2 | Técnico | **Barra faltante o en conflicto con una posición abierta:** salida forzada en la apertura de la siguiente barra válida | En la v0.1, con la sesión incompleta el VWAP queda indefinido y la regla de salida no estaba especificada |
| C3 | Técnico | **Fin de la ventana:** la última sesión de E (2026-05-31) se liquida en el **cierre de la barra de las 23:00**, con costos | La v0.1 vendía en la apertura de las 00:00 del 2026-06-01, que está en el **período reservado**: era un defecto |
| C4 | Estadístico | Prueba primaria bootstrap-t (MEC §4), α = 0,025; P solo descriptivo | MEC §1 |
| C5 | Estadístico | El nulo emparejado se redefine (MEC §8) y sale del criterio de decisión | MEC §8 |
| C6 | Estadístico | Sin compuerta por resultado de D; se usan compuertas de datos y factibilidad | MEC §9 |
| C7 | Análisis | Sensibilidad aritmética al costo y a la frecuencia (§6) | El costo es la amenaza central |
| C8 | Datos | Las 38 barras inutilizables de BTC (35 faltantes + 3 en conflicto, ya incluidas en las 38) se tratan como **barras faltantes**, no como archivos ausentes; regla de invalidez explícita | Distinguir archivos de observaciones |

**Hipótesis y reglas de entrada:** sin cambios conceptuales respecto de la v0.1.

## 1. Hipótesis
- **H₁:** en BTCUSDT y ETHUSDT spot a 1 h, la regla intradía de §3 tiene un exceso de timing neto μ > 0 frente a la estática horaria con la misma exposición media.
- **H₀:** μ ≤ 0.
- Estar por encima del VWAP **no basta**: la entrada exige además la retoma de la EMA(9) y una EMA ascendente.
- **Contexto previo:** E1-P1 (otra regla de tendencia del bot, a 1 h) dio en contra después de costos. Expectativa previa baja.

## 2. Mercado y horario
- **Mercado:** Binance spot, BTCUSDT y ETHUSDT, cada uno con media manga.
- **Posiciones:** largo o efectivo; sin cortos ni apalancamiento.
- **Velas:** 1 h UTC [D-EV-1].
- **Sesión:** el día UTC, solo para anclar el VWAP (convención declarada en un mercado 24/7).
- **Horario de señales:** barras con apertura de 02:00 a 18:00 UTC; ejecución de 03:00 a 19:00 [D-EV-2].

## 3. Reglas (por activo; t = barra horaria)
- **Columnas de la vela de Binance:** 1 = O, 2 = H, 3 = L, 4 = C, **5 = volumen base V**, **7 = volumen en USDT QV**.
- **Barra válida:** presente, cerrada, OHLC coherente, precios > 0, duración de 1 h y sin conflicto entre el archivo mensual y el diario.

1. **EMA:** α = 0,2. EMA inicial = media de los 9 primeros cierres válidos; luego EMA_t = 0,2·C_t + 0,8·EMA_{t−1}, continua entre sesiones.
   - **Calentamiento:** 50 barras válidas sin señales.
   - **Tras cualquier barra faltante o inválida:** la EMA sigue con el siguiente cierre válido, sin interpolar. Señales bloqueadas durante las **9 barras válidas** siguientes.
2. **VWAP_t = Σ QV_i / Σ V_i** sobre las barras de la sesión con i ≤ t. Indefinido si Σ V_i = 0.
3. **Sesión íntegra hasta t:** todas las barras de 00:00 a t de esa sesión son válidas.
4. **Entrada** (al cierre de t, compra en O_{t+1}), si se cumple todo lo siguiente:
   - (a) la apertura de t está entre 02:00 y 18:00;
   - (b) no hay posición abierta y no hubo otra entrada en la sesión [D-EV-3];
   - (c) la sesión está íntegra hasta t y la EMA no está bloqueada;
   - (d) C_t > VWAP_t y EMA_t > VWAP_t;
   - (e) C_{t−1} ≤ EMA_{t−1} y C_t > EMA_t;
   - (f) EMA_t > EMA_{t−1}.
   - Si la barra t + 1 falta o es inválida, no hay entrada.
5. **Salida** (por la primera condición que se cumpla):
   1. C_t < VWAP_t → venta en O_{t+1} (stop por VWAP);
   2. t es la barra de las 23:00 → venta en O de las 00:00 del día siguiente (cierre obligatorio de sesión);
   3. **barra faltante o inválida en posición** (llega t′ válida después de un hueco) → venta en O_{t′} (C2);
   4. **fin de la ventana** → venta en C de la última barra válida de la ventana, con costos (C3).
   - **Sin objetivo de ganancia ni stop fijo** [D-EV-4].
   - Si la apertura de salida falta, la venta se hace en la siguiente apertura válida.
6. **Mangas independientes.** Una posición por activo. No hay prioridad entre BTC y ETH.
7. **Tamaño:** 100 % de la manga en posición; el resto, efectivo al 0 %.
8. **Papel:** si la barra t no se publica en el plazo [D-EV-5], no genera señal y no se recupera después.

## 4. Datos y validez
- **BTCUSDT 1h (2019-10 → 2026-05):** ya en disco y verificado. Son 96 archivos (80 mensuales + 16 diarios), con los mismos SHA-256 que en H-CARRY y E1.
  - Hay **38 barras inutilizables de 58 440** (0,065 %): 35 faltantes y **3 horas en conflicto** entre el archivo mensual y el diario, tratadas como faltantes.
    - El desglose sale de la adenda 1 del prerregistro de E1: «las horas faltantes pasan de 35 a 38».
    - Siguen la regla 3.5.3 y **no invalidan el período**.
- **ETHUSDT 1h:** **no disponible.** Hace falta autorización de descarga (A-EV-1). Sin ETH **no se ejecuta** la versión especificada, y no hay alternativa silenciosa «solo BTC».
- **Período INVÁLIDO para un activo** [D-EV-6]:
  - más del 0,5 % de barras faltantes o inválidas;
  - un archivo mensual sin su complemento diario;
  - un checksum que falla.
- **Sesiones afectadas:** las que tienen alguna barra faltante pierden las entradas a partir del hueco. Se informa cuántas son.

## 5. Períodos y contaminación
| Fase | Ventana | Uso |
|---|---|---|
| D | 2019-10-01 → 2021-12-31 | Verificar la implementación y contar la frecuencia de señales (factibilidad). Sin selección de parámetros ni compuerta por resultado |
| E | 2022-01-01 → 2026-05-31 | Uso único, con candado. Liquidación final según C3 |
| P | Desde la aprobación, con historia desde el 2026-10-14 [D-EV-8] | Prueba secuencial (MEC §7.1) |

- **E está contaminado:** E1 evaluó reglas horarias de tendencia en BTC entre 2019-10 y 2026-05. **No es independiente.**

## 6. Costos: sensibilidad aritmética (sin datos) [Hip]
- **Costo de ida y vuelta** c = 2·(f + s) = 30 pb base; 45 pb con estrés ×1,5 y 60 pb con ×2.
- **Para empatar**, cada operación debe ganar **más de c en bruto**.
- **Costo anual aproximado** sobre la manga, sin composición: N operaciones por año × c.

| N/año por manga | c = 20 pb | c = 30 pb (base) | c = 45 pb | c = 60 pb |
|---|---|---|---|---|
| 50 | 10 % | 15 % | 22 % | 30 % |
| 100 | 20 % | 30 % | 45 % | 60 % |
| 200 | 40 % | 60 % | 90 % | 120 % |
| 300 | 60 % | 90 % | 135 % | 180 % |

- **Lectura:** con una entrada por sesión como máximo, el techo es de unas 365 operaciones por año. La frecuencia real se conocerá en D, con un conteo sin P&L.
  - Por encima de unas 100 operaciones por año, la regla necesita una ventaja bruta por operación del mismo orden que el costo. Eso es **implausible a priori** para una regla de cruce simple, aunque se declara como juicio, no como dato.
- **Fijo:** esto no se usa para elegir parámetros. La frecuencia **no** se ajustará después de ver D: hacerlo sería otro experimento.
- **c = 20 pb** representa un descuento de comisión que **no** está en el supuesto base: es solo descriptivo.

## 7. Métricas y decisión
- **Primaria:** media diaria del exceso conjunto (MEC §2, en frecuencia horaria, compuesto por día).
- **Prueba:** bootstrap-t, ℓ = 20 días, B = 9999, semilla 20261102, α = 0,025.
- **Categorías:** las del MEC §7. **N_min = 100** operaciones en E entre los dos activos [D-EV-9].
- **Descriptivas:**
  - por activo; frecuencia; duración media; retorno bruto y neto por operación;
  - fracción del bruto que se lleva el costo; motivos de salida; sesiones afectadas por huecos;
  - P (probabilidad bootstrap); nulo emparejado (MEC §8);
  - estrés de costos (×1,5, ×2, ×3) y de retraso (+1 barra);
  - subperíodos; buy and hold y efectivo.

## 8. Potencia (aritmética con supuestos, sin datos) [Hip]
- **Supuesto:** un desvío por operación de unas 6 h con volatilidad horaria del 0,7 % da s_op ≈ 1,7 %.
- **Efecto mínimo detectable por operación** (80 %, α = 0,025):
  - N = 100 → 0,48 %;
  - N = 300 → 0,28 %;
  - N = 500 → 0,21 %;
  - N = 1000 → 0,15 %.
- **Lectura:** con cientos de operaciones en E, la prueba puede detectar ventajas netas del orden de 20–30 pb por operación. Eso exige ventajas brutas de unos 50–60 pb, porque hay que sumar el costo de 30 pb.
- **Esta potencia es la de la pregunta neta**, y depende de supuestos que **no** se midieron.

## 9. Controles, auditoría y reproducción
- **Pruebas sintéticas (Etapa B):** las de `PLAN_DE_EVIDENCIA_SUFFICIENTE.md`. Incluyen:
  - el VWAP calculado a mano, con columnas 5 y 7 intercambiadas a propósito para comprobar que la prueba lo detecta;
  - la EMA frente a una referencia;
  - huecos con posición abierta;
  - cierre de sesión;
  - liquidación final;
  - marcas de tiempo en µs desde 2025;
  - control positivo y control negativo.
- **Congelado:** el texto y el código se congelan con hash antes de leer D. E tiene candado de uso único. Registros fuera del repositorio.
- **Revisión independiente por otro modelo:** no realizada.

## 10. Decisiones pendientes (además de MEC D-S*)
| ID | Decisión | Recomendación |
|---|---|---|
| D-EV-1 | Velas de 1 h | Aprobar |
| D-EV-2 | Señales con apertura de 02:00 a 18:00 UTC | Aprobar |
| D-EV-3 | Una entrada por sesión | Aprobar (limita el costo) |
| D-EV-4 | Sin objetivo ni stop fijo; el VWAP como stop | Aprobar |
| D-EV-5 | Plazo de publicación en el papel | Fijar antes de P |
| D-EV-6 | Invalidez si faltan más del 0,5 % de las barras | Aprobar |
| D-EV-8 | Historia de P desde el 2026-10-14 | Aprobar |
| D-EV-9 | N_min = 100 | Aprobar |
| A-EV-1 | Descargar ETHUSDT 1h de 2019-10 a 2026-05 | Tu decisión. Sin ella, el experimento no corre |
