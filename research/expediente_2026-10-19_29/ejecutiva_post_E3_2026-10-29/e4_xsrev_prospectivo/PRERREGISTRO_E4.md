# E4 · Prerregistro: H-XS-REV-1 prospectiva (reversión transversal diaria, información)

**Estado: BORRADOR v0. No está congelado ni anclado.** Se congela con su sha256 en `CONGELACION_E4.txt` y se ancla afuera (§9) solo con tu autorización. Después, cualquier cambio exige una versión nueva y reinicia T0.

**Origen de la hipótesis:** P19 de `entrega_direccion_tecnica_2026-10-26/PROPUESTAS_TECNICAS.md`, escrita el 2026-10-26, antes de este experimento. Las especificaciones se toman de ahí. Lo que cambia, y por qué:
- **La evaluación es prospectiva.** Así no se superpone con ningún dato histórico (ni el de E3 ni ningún otro) y no hereda el problema de supervivencia que dejó a E3 NO EVALUABLE: el universo se arma día a día con lo que existía ese día.
- **La métrica principal pasa a ser la información (IC) y no el retorno neto.** La propia P19 prevé que los costos de rotación diaria se coman el efecto («lo honesto es esperar un descarte»). El retorno neto queda como descarte rápido económico.

## 1. Hipótesis (falsable)

**H1-E4.** En el universo líquido de pares spot X/USDT de Binance, el rango del retorno del día t−1 predice **en sentido inverso** el rango del retorno del día t+1, con un día de retraso. La media del IC diario de Spearman entre −r(t−1) y r(t+1) es mayor que 0.

**H0:** media ≤ 0.

**Fundamento:** provisión de liquidez (Lehmann 1990; Jegadeesh 1990; Nagel 2012). En cripto la evidencia a horizonte diario es mixta y el signo no está establecido: es una pregunta, no una apuesta (P19).

## 2. Datos (permitidos y separados)

- **Fuente:** Binance Vision, archivos públicos diarios `data/spot/daily/klines/<SÍMBOLO>/1d/<SÍMBOLO>-1d-<DÍA>.zip`, con su `.CHECKSUM` oficial.
- **Período:** solo días **≥ T0**, más los 31 días previos que hacen falta para armar el universo de T0.
  - **T0** es el primer día UTC completo posterior a: (a) la congelación y el anclaje del prerregistro, y (b) el arranque del recolector.
  - Los 31 días previos solo sirven para el universo y la señal del arranque. No hay resultado de ninguno de ellos.
- **No se usa** ningún dato de los árboles congelados: las series de E3 quedan tapadas por la zona aislada y la guarda de rutas.
- **Destino:** una carpeta nueva, verificada por la guarda.
- El recolector no abre los ZIP: nadie mira datos antes de la evaluación única.

## 3. Definiciones (implementadas en `codigo/nucleo.py`)

**Día activo:** existe la vela 1d, con operaciones > 0 y cierre > 0.

**Retorno:** r(d) = cierre_d / cierre_{d−1} − 1, si d−1 y d son activos.

**Universo U(t):**
- pares X/USDT que no estén en la lista fija de exclusiones: stablecoins, fiat, BIDR, IDRT y BVND;
- se excluyen también los tokens apalancados X{UP,DOWN,BULL,BEAR} cuando existe XUSDT;
- tienen que estar activos los 30 días [t−30, t−1];
- se toman los 100 con mayor mediana de volumen en USDT de esos días;
- todo con datos ≤ t−1;
- si quedan menos de 30, el día no es evaluable.

**Señal:** s = −r(t−1).

**Resultado:** r(t+1), con un día de retraso: la cartera se arma al cierre de t y se cierra al cierre de t+1.

**IC_t:** Spearman entre s y r(t+1), con los pares que tienen los dos valores.

**Salidas:**
- un par sin vela en t+1 sale del IC y se cuenta;
- en la cartera rinde 0, porque se liquida al último cierre;
- se informa el número de salidas.

## 4. Período de evaluación y mirada única

- **365 días de formación** desde T0.
- **Una sola evaluación**, no antes de T0 + 365 + 3 días (por el rezago de publicación). No hay miradas intermedias del IC.
- El evaluador se niega a correr antes de tiempo, dos veces o con un prerregistro alterado (probado).
- **Cero reintentos confirmatorios** (política D-7). Si algo falla después de empezar la evaluación, el resultado es NO EVALUABLE y no se repite.

## 5. Estadística

- **Media del IC diario**, con error estándar de Newey-West (5 rezagos) y estadístico t.
- **Prueba principal:** unilateral, α = 0,025 (t > 1,96).
- **Potencia analítica** (sin datos; supuestos [Hip] en `registro/potencia_E4.txt`), con 365 días y un IC verdadero de 0,02: entre 0,41 y 0,97, según el desvío diario del IC (0,10–0,20) y la autocorrelación (0–0,1).
  - Con un IC de 0,03: entre 0,74 y 1,0.
  - El IC mínimo detectable con 80 % va de 0,015 a 0,032.

## 6. Clasificación (fijada ahora)

| Clase | Condición | Lectura |
|---|---|---|
| INVÁLIDO | Más del 20 % de los días no evaluables, o menos de 250 evaluables | Sin conclusión |
| RESPALDADA_INFORMACION | t > 1,96 | Hay información transversal de reversión. **No es rentabilidad** |
| EN_CONTRA_SIGNO_OPUESTO | t < −1,96 | Hay continuación, no reversión. Es informativo y cierra H1-E4 |
| REFUTADA_TAMANO_RELEVANTE | Cota superior (media + 1,96 EE) < 0,01 | Descarta un efecto de tamaño económicamente relevante |
| INSUFICIENTE | Cualquier otro caso | **No equivale a refutar.** La prueba no distinguió el efecto del ruido |

## 7. Benchmark, costos y descarte económico (secundario)

**Benchmark de información:** IC = 0. En los datos sintéticos el nulo da una tasa de falsos positivos de 0,025 (`registro/pruebas_sinteticas.json`).

**Cartera secundaria:**
- **Composición:** solo larga, con el quintil de mayor señal (los peores del día anterior), pesos iguales, rebalanceo diario.
- **Benchmark:** pesos iguales en U(t).
- **Costos por lado:**
  - comisión taker de 7,5 bps;
  - medio spread de 5 bps (fijo; sensibilidad con 10 y 20);
  - latencia de un día (incluida en la definición);
  - sin funding, porque es spot y solo larga.
- **Descarte rápido (P19):** si el diferencial bruto medio frente al benchmark es menor que 2 veces el costo medio diario de ida y vuelta, la hipótesis **no tiene valor económico**, aunque haya información.

## 8. Contra el sobreajuste y la selección retrospectiva

- Una sola especificación, sin búsqueda de parámetros: retrospectiva de 1 día, quintiles, pesos iguales, 100 monedas y 30 días de ventana.
- Las sensibilidades de costos se declaran ahora y no sirven para elegir.
- **Registro encadenado** (`REGISTRO.jsonl`) de cada recolección y de la evaluación. Los resultados negativos se informan igual que los positivos.
- **Sin reformulaciones dentro del período.** Una versión nueva reinicia T0 y no usa los datos ya recolectados para evaluar.

## 9. Congelación y ancla (requieren tu autorización)

1. **Congelación:** `sha256sum PRERREGISTRO_E4.md` en `CONGELACION_E4.txt`, junto con los sha256 de `codigo/*.py`.
2. **Ancla externa** (ver `ANCLA_EXTERNA_R2.md`):
   - OpenTimestamps sobre `CONGELACION_E4.txt`;
   - commit en la rama protegida `registros` (D-G4 de la hoja de ruta del 2026-10-21).
   - T0 se fija recién cuando el ancla está confirmada.

## 10. Lo que E4 **no** puede concluir

- Rentabilidad, capital u operación real: ninguna clase autoriza dinero real (igual que la v3 §6.5).
- Un INSUFICIENTE no es evidencia en contra.
- El resultado vale para el período observado. No sustituye una prueba económica neta, que exigiría otro prerregistro.
