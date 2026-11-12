# PROPUESTA DE PRERREGISTRO: H-REV-SHOCK v0.1

> **PROPUESTA NUEVA · PENDIENTE DE APROBACIÓN · NO EJECUTADA**
> - Este documento **no** es el protocolo histórico de H-REV-SHOCK. El original (referencia citada `69758896…`) **no se encontró** en ninguna fuente accesible (`AUDITORIA_H-REV-SHOCK.md`).
> - Sus reglas son una **definición nueva**, redactada el 2026-10-20 a partir de la hipótesis conceptual del pedido, **sin mirar ningún dato** de precios ni resultados.
> - No autoriza ninguna ejecución. Antes de ejecutar hacen falta tres cosas: tu aprobación expresa, el congelado con hash del texto aprobado y la autorización de cada fase (§13).
> - Todo umbral o prueba marcado **[D-RS-n]** o **[D-MEC-n]** es una **decisión nueva pendiente de aprobación**.

## 1. Hipótesis
- **Conceptual:** un movimiento excepcional del mercado, seguido de señales de agotamiento, podría presentar una reversión aprovechable después de descontar todos los costos.
- **Operacional (H₁):** en BTCUSDT y ETHUSDT spot, una estrategia long/flat que compra tras un shock bajista diario excepcional y una señal de agotamiento (§3) obtiene un **exceso de timing neto** positivo frente a la estática con su misma exposición media (§7).
- **Nula (H₀):** ese exceso es ≤ 0.
- **Qué no es:**
  - no es E1-P2 (mean_reversion del bot), ni la familia R (reversión diaria incondicional), ni C10;
  - **no se supone** que sea rentable;
  - la evidencia previa sobre reversión incondicional fue débil o negativa: autocorrelación diaria de −0,06 en el desarrollo de T y E1-P2 en contra. Eso fija una **expectativa previa baja**, no un resultado.

## 2. Mercado, activos y temporalidad
- **Mercado:** Binance spot.
- **Activos:** BTCUSDT y ETHUSDT, cada uno con la mitad del capital (manga).
- **Posiciones:** solo largos o efectivo. **Sin cortos ni apalancamiento** (spot).
- **Temporalidad:** velas **diarias UTC** (apertura 00:00). **Horizonte:** de 1 a 10 días por operación.
- **Por qué diario** [D-RS-1]:
  - los datos ya están en disco y verificados (sin descarga para D y E);
  - menos parámetros que un shock intradía;
  - el costo pesa menos por operación.
  - Un shock intradía sería **otro experimento**.

## 3. Definición operacional (inequívoca)
**Notación** (por activo; d = día UTC):
- O_d, H_d, L_d y C_d: vela 1d oficial.
- **Día válido:** vela presente, OHLC coherente, precios > 0 y duración de 1 día (mismas reglas que `tendencia.datos.leer`).

1. **Movimiento:** r_d = ln(C_d / C_{d−1}). Solo existe si d y d − 1 son válidos.
2. **Volatilidad de referencia:** σ_d = desvío muestral (ddof = 1) de los 60 rendimientos r_{d−60} … r_{d−1}.
   - Excluye el propio día d, para que el shock no infle su vara de medida.
   - Si falta alguno de esos 60, no hay señal en d.
3. **Movimiento anormal:** z_d = r_d / σ_d.
4. **Shock bajista** el día s: **z_s ≤ −3,0** [D-RS-2].
   - Los shocks alcistas (z ≥ +3) se registran **solo de forma descriptiva** (no se puede abrir un corto).
5. **Ventana de agotamiento:** los días s + 1, s + 2 y s + 3 [D-RS-3].
   - Al cierre de cada día d de la ventana, se lleva **L\*** = min(L_s, …, L_{d−1}).
   - **Agotamiento confirmado** en el primer d de la ventana que cumple **(a) y (b)** [D-RS-4]:
     - (a) **sin mínimo nuevo:** L_d ≥ L\*;
     - (b) **cierre de giro:** C_d > C_{d−1}.
   - Si ningún día de la ventana cumple (a) y (b): **no hay operación**.
6. **Shocks consecutivos:** un shock nuevo (z_d ≤ −3) dentro de la ventana, antes del agotamiento, **la reinicia**. Pasa a s = d, con niveles nuevos (L\*, referencia C_{d−1}).
7. **Entrada:** si el agotamiento se confirma al cierre de e, se compra en la **apertura O_{e+1}** con el 100 % de la manga.
   - Si O_{e+1} falta, no hay entrada.
   - **Nivel de invalidación:** L\* = min(L_s, …, L_e).
   - **Referencia de recuperación:** REF = C_{s−1}, el cierre previo al shock vigente.
8. **Salida:** al cierre de cada día d en posición, se vende en la **apertura siguiente** O_{d+1}, por la primera condición que se cumpla:
   1. **Recuperación:** C_d ≥ REF.
   2. **Invalidación:** C_d < L\*.
   3. **Duración máxima:** d = (día de entrada) + 9, es decir, la posición se cierra a más tardar en la apertura del 11.º día, tras 10 días en posición [D-RS-5].
   - Las condiciones 1 y 2 no pueden darse a la vez.
   - Si la apertura de salida falta, se vende en la siguiente apertura disponible.
9. **Señales contradictorias o superpuestas:**
   - en posición, los shocks nuevos (bajistas o alcistas) **se ignoran** (sin piramidar);
   - tras una salida en la apertura del día x, el activo queda libre y un shock en x se evalúa al cierre de x;
   - **una sola posición por activo.**
10. **Tamaño:**
    - 100 % de la manga del activo invertida durante la posición;
    - fuera de ella, efectivo USDT al 0 %;
    - sin apalancamiento.

**Justificación conceptual de los parámetros** (ninguno se eligió mirando datos):
- **60 días:** unos 2 meses, una ventana habitual para escalar por volatilidad. Con 60 observaciones, el error relativo del desvío es ≈ 9 %.
- **z ≤ −3:** convención de «evento de 3 sigma». Bajo normalidad es el 0,13 % de los días; en cripto, por las colas pesadas, será más frecuente. **No hay datos permitidos que justifiquen otro umbral** y no se optimiza.
- **Ventana de 3 días:** limita la espera y deja que la caída siga 1 o 2 días.
- **Agotamiento (a) + (b):** la definición mínima de «la presión vendedora se detuvo», sin indicadores adicionales.
- **Recuperación a C_{s−1}:** mide la reversión completa del shock.
- **Invalidación en L\*:** si se rompe el mínimo, el agotamiento era falso.
- **10 días:** la hipótesis es de corto plazo; limita la exposición a la deriva.

## 4. Datos y requisitos de calidad
- **Fuente:** data.binance.vision, `spot/monthly/klines/{BTCUSDT,ETHUSDT}/1d`, con `.CHECKSUM`.
- **D y E:** **se usan los archivos ya verificados de T.** Manifiestos `5a0805a7e22797637c400a1e939ec6c2d10e0cdc26410566f212708211b6367b` y `3998305bb38909a08a94f6365317695f930dea4ea10933b19a22e17b40998f6a`; 3210 días por activo, 0 faltantes. **No hace falta descargar nada.**
- **P (papel):** archivos diarios oficiales prospectivos. Requiere una **autorización de descarga** [A-RS-3].
- **Sin relleno ni interpolación.**
- **Período INVÁLIDO para un activo:**
  - falta un archivo mensual sin su complemento oficial;
  - más del 0,5 % de días inválidos;
  - un checksum falla.

## 5. Períodos
| Fase | Ventana | Uso |
|---|---|---|
| **D (desarrollo)** | Primer día con 60 rendimientos previos (2017-10-17, con datos desde el 2017-08-17) → 2021-12-31 | Verificar la implementación con datos reales y describir. **No se cambia ningún parámetro por sus resultados.** Compuerta opcional [D-RS-7]: si D da P(conjunto) < 0,10, no se gasta E |
| **E (evaluación histórica, uso único)** | 2022-01-01 → 2026-05-31 | **Una sola ejecución** con candado (el script se niega si el resultado existe). Decide «respaldada en E» |
| **P (prospectiva, papel)** | Desde la aprobación. Historia de la señal solo con días ≥ 2026-10-14; primer día evaluable ≈ 2026-12-14 [D-RS-8] | La única evidencia independiente. Cortes de 12 y 24 meses |

- **Período reservado de H-CARRY (2026-06-01 → 2026-10-13):** no se lee, ni siquiera como historia, salvo autorización expresa.
- **Contaminación declarada de E:** quien diseña conoce el régimen de 2022–2026, y T (fuera de muestra) y E1 ya usaron esos datos. **E no es independiente:** su resultado es «histórico con contaminación declarada».
- **El mismo período nunca se usa para elegir parámetros y afirmar que generalizan:** los parámetros están fijados aquí, antes de D.

## 6. Ejecución y costos
- **Decisión** con el cierre UTC del día; **ejecución** en la apertura oficial siguiente (latencia de 1 barra).
- **Comisión:** 10 pb por lado (taker estándar de Binance spot, sin descuento en BNB). **Slippage y spread:** 5 pb por lado. **Ida y vuelta: 30 pb.**
- **Estrés** (descriptivo): costos ×2 y ×3; ejecución con un día extra de retraso (apertura d + 2).
- **No hay costo de financiamiento** (sin apalancamiento). Efectivo al 0 %.

## 7. Benchmark y métricas
- **Benchmark primario:** **estática con la misma exposición media** ε_a de la estrategia en el activo a.
  - Rinde ε_a · r_{a,d} cada día, con rebalanceo diario y sin costos; es la misma construcción que en T.
  - Corrige la deriva alcista: una estrategia expuesta pocos días no «gana» solo por estar comprada.
- **Exceso diario:** x_{a,d} = R^{estrategia}_{a,d} − ε_a · r_{a,d}. **Conjunto:** x_d = ½ (x_{BTC,d} + x_{ETH,d}).
- **Métrica primaria:** **media diaria del exceso conjunto × 365** (exceso de timing anualizado, neto de costos).
- **Secundarias (descriptivas):**
  - el exceso por activo;
  - número de operaciones, de operaciones ganadoras y retorno neto medio por operación;
  - **nulo de entradas aleatorias emparejadas** (§8);
  - estrés de costos y de retraso;
  - subperíodos de E (2022–2023 y 2024-01 → 2026-05);
  - exposición, caída máxima y Sharpe de la estrategia y de los benchmarks (estática, buy and hold, efectivo);
  - número de shocks alcistas (solo descriptivo).

## 8. Marco estadístico común (MEC v0.1, idéntico en H-EMA9-VWAP)
1. **Una sola métrica primaria por hipótesis:** el exceso de timing anualizado del conjunto.
2. **Incertidumbre:** bootstrap **por bloques circulares** de la serie diaria de exceso.
   - Bloques de 20 días, B = 2000, semilla 20261020 (como T).
   - **P** = fracción de medias bootstrap > 0; **IC90** por percentiles.
   - La dependencia temporal y la autocorrelación la absorben los bloques.
   - Bloques de 10 y 40 días, solo descriptivos [D-MEC-1].
3. **Nulo de entradas aleatorias emparejadas** (secundario): 1000 réplicas.
   - Mismo número de operaciones por activo, mismas duraciones y mismos costos.
   - Entradas uniformes en días elegibles, sin superposición.
   - Se informa el percentil del exceso observado.
4. **Variantes:** **una sola configuración** primaria.
   - Las variantes de estrés y de subperíodo son descriptivas y **no deciden**.
   - Cualquier otra configuración es **otro experimento**, que requiere aprobación y se cuenta.
5. **Multiplicidad entre hipótesis** [D-MEC-2]: si H-REV-SHOCK y H-EMA9-VWAP se evalúan en E en la misma ronda, se aplica **Holm con m = 2** sobre p = 1 − P.
   - Una hipótesis llega a «respaldada» solo si p ≤ 0,025, o p ≤ 0,05 si la otra ya rechazó.
6. **Criterios de E** [D-MEC-3]:
   - **INVÁLIDO:** falla de datos (§4) o de integridad (hashes, candado).
   - **INCONCLUSO POR DATOS:** menos de **20 operaciones** en E entre los dos activos [D-RS-6].
   - **RESPALDADA EN E:** P(conjunto) ≥ 0,95 (umbral ajustado por Holm), exceso conjunto con costos ×2 > 0, exceso del mismo signo en BTC y ETH y percentil ≥ 0,90 en el nulo emparejado.
   - **NO RESPALDADA:** P(conjunto) < 0,10.
   - **EVIDENCIA INSUFICIENTE:** cualquier otro caso.
7. **Separación de conclusiones** (no se mezclan):
   - (i) **retorno positivo observado:** solo una estimación puntual > 0; no es evidencia;
   - (ii) **ventaja respaldada en E:** el criterio 6; es histórica y contaminada;
   - (iii) **robustez fuera de muestra:** «respaldada» en P a los 24 meses, con los mismos criterios;
   - (iv) **viabilidad operativa:** fills reales, slippage medido y capacidad. **Fuera de alcance y no autorizada.**
   - **Ningún valor de P aislado** prueba rentabilidad. Superar al benchmark en una muestra **no** es rentabilidad demostrada.
8. **Potencia: no calculada con datos.** Es solo una ilustración analítica, con supuestos no medidos [Hip].
   - Años necesarios para detectar un exceso μ con un tracking error anual TE (unilateral 5 %, potencia 80 %): **años ≈ (2,49 · TE/μ)²**.
   - TE/μ = 0,5 → 1,6 años; TE/μ = 1 → 6,2; TE/μ = 2 → 25.
   - Con E de 4,42 años solo se detectaría μ ≥ ≈ 1,18 · TE.
   - **No se promete potencia.** El conteo de eventos (F0, §13) permitiría estimarla mejor.

## 9. Riesgo y exposición
- **Exposición máxima:** 100 % de cada manga (50 % del capital por activo). Sin apalancamiento ni cortos, una posición por activo.
- **Sin límites adicionales:** no hay stop de capital ni límite de caída. Las salidas son las de §3.
- **Eventos extremos:** **no se excluyen** (las caídas son la señal). No se ajustan días de caídas de Binance; si faltan datos, aplican las reglas de §3 (sin entrada o salida en la apertura siguiente disponible).

## 10. Controles contra el look-ahead, el sobreajuste y la selección
- **Señal:** usa solo datos ≤ cierre de d. σ excluye el día d. La ejecución es en d + 1.
- **Pruebas antes de cualquier dato real** (con datos sintéticos):
  1. invariancia al truncar la serie en 5 cortes al azar;
  2. control positivo, con una reversión plantada que debe detectarse;
  3. control negativo, con un paseo aleatorio, para medir la tasa de rechazo;
  4. contabilidad de costos;
  5. máquina de estados (casos de §3.5–3.9).
- **Código congelado con hash antes de leer D.** Datos con manifiesto. **Candado de uso único para E.** Registro de ejecuciones de solo añadidos.
- **Prohibido:**
  - cambiar parámetros tras ver D o E;
  - elegir subperíodos o activos a posteriori;
  - repetir E.

## 11. Auditoría y reproducción
- **Cada ejecución registra:** el hash del prerregistro aprobado, del código y de los manifiestos; la semilla; el entorno (Python 3.11, biblioteca estándar) y la salida JSON con sus hashes.
- **Reproducción:** comando único y determinista. Lo verifica un segundo proceso que recalcula desde los datos.
- **Revisión independiente por otro modelo:** **no realizada** (no hay ninguna disponible ni autorizada en este entorno). No se finge.

## 12. Limitaciones conocidas de antemano
- Probablemente **pocos eventos:** la potencia será baja y lo más probable es «insuficiente».
- BTC y ETH están muy correlacionados: los shocks tienden a coincidir, así que hay menos información independiente de la que sugiere el conteo.
- La regla de agotamiento es una de muchas posibles; un resultado negativo **no** refuta otras definiciones.
- Costos supuestos, no medidos.

## 13. Fases y autorizaciones necesarias (nada de esto está autorizado)
| Fase | Qué | Requiere |
|---|---|---|
| A-RS-0 | Aprobar este texto (con o sin cambios) y congelarlo con hash | Tu aprobación |
| F0 (opcional) | Contar shocks y agotamientos en D, **sin mirar retornos posteriores**, para estimar potencia [D-RS-9] | Autorización; si cambiara un umbral por el conteo, se declara como una versión nueva |
| A-RS-1 | Implementación, pruebas sintéticas y congelado del código | Autorización |
| A-RS-2 | Ejecutar D y luego E (una vez) | Autorización expresa de ejecución |
| A-RS-3 | Papel prospectivo (descarga diaria de datos oficiales) | Autorización y ubicación de los registros fuera del repositorio |

## 14. Decisiones pendientes de aprobación
| ID | Decisión propuesta |
|---|---|
| D-RS-1 | Temporalidad diaria |
| D-RS-2 | Umbral z ≤ −3,0 con σ de 60 días |
| D-RS-3 | Ventana de agotamiento de 3 días |
| D-RS-4 | Agotamiento = sin mínimo nuevo + cierre de giro |
| D-RS-5 | Duración máxima de 10 días |
| D-RS-6 | Mínimo de 20 operaciones en E |
| D-RS-7 | Compuerta de D (P < 0,10 detiene) |
| D-RS-8 | Historia para P solo desde 2026-10-14 |
| D-RS-9 | Conteo de eventos F0 |
| D-MEC-1 | Bloques de 20 días (10 y 40 descriptivos) |
| D-MEC-2 | Holm m = 2 entre hipótesis |
| D-MEC-3 | Criterios de decisión de §8.6, incluido el percentil ≥ 0,90 del nulo emparejado |
