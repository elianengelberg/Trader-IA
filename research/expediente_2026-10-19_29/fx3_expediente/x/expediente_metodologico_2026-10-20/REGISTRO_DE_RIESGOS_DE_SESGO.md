# Registro de riesgos de sesgo (Trader-IA, 2026-10-20)

**Fuente del inventario:** `experimentos/E3_seleccion_posicion_2026-10-19/REGISTRO_HIPOTESIS_tras_cierre_E3.md` (SHA-256 `0e59229558c044c2928a033f3f31135cceb281159ea9ae7de09cbb5b646c56c0`), más las propuestas v0.1 y v0.2. **No se oculta ningún experimento desfavorable.**

## 1. Familia completa de hipótesis (probadas, abandonadas y propuestas)

| Grupo | Hipótesis | Estado | Datos que consumió | Rol hoy |
|---|---|---|---|---|
| Carry | H-CARRY (P1 UmbralFunding > rev. 5; P2 carry > 5 %) | CERRADA (insuficiente) | BTCUSDT spot 1h y perpetuo, mark, premium y funding, 2019-10 → 2026-05; test de uso único | Cerrada; solo la reabre su monitor (> 12 %) |
| Tendencia y volatilidad (F3) | V (volatilidad gestionada) | DESCARTADA | BTC 1d desarrollo 2017–2021 | Cerrada |
| | R (reversión diaria) | DESCARTADA (sin base: autocorrelación −0,06 > −0,10) | Ídem | Cerrada |
| | **T** (long/flat) | INSUFICIENTE; historia CERRADA | Desarrollo 2017–2021; fuera de muestra 2022-01 → 2026-05 (uso único **consumido**) | Solo papel |
| | T-papel | PROSPECTIVA, sin cortes | Desde 2026-10-18 | **Confirmatoria** (prospectiva) |
| | T-MULTI | INSUFICIENTE | 11 ETF 2011–2026-09 | Cerrada |
| | T-baja-rotación | PROSPECTIVA (sin protocolo) | — | Exploratoria |
| Bot (E1) | E1-P1 trend_following, E1-P2 mean_reversion, E1-P3 breakout, S1 fusión, S5 cortos, CONF | DESCARTADAS (en contra) | BTCUSDT 1h, 2019-10 → 2026-05 | Cerradas |
| | H-E1-BC (confianza de breakout) | EXPLORATORIA | Ídem | Exploratoria (confirmación solo en ETH y SOL) |
| | E1-MR-retraso | EXPLORATORIA | Ídem | Sin valor práctico |
| Descubrimiento (E2) | C3/E2-A (variables incrementales), C1/E2-B (funding extremo), C2/E2-C (Wikipedia) | INSUFICIENTE, INSUFICIENTE y EN CONTRA | BTC y ETH 1d y funding; Wikipedia | Cerradas; **variantes prohibidas** |
| Selección transversal (E3) | E3-H1, E3-H2, E3-H3 (momentum transversal) | CERRADAS · NO EVALUABLES | 1d de todos los pares USDT 2017–2026-05 (**solo calidad, sin retornos**) | Cerradas |
| Propuestas descartadas o diferidas | C4, C6, C7, C8, C9, **C10 (reversión tras extremos)**, C11, C12, C13, C14, LLM-hist, funding transversal, CTREND, **«reversión tras extremos o liquidaciones»** | Descartadas, diferidas o no independientes | — | No se prueban |
| **Nuevas** | **H-REV-SHOCK v0.1 y v0.2** | Propuesta, no aprobada | Ninguno todavía | **Candidata confirmatoria**, si se aprueba |
| | **H-EMA9-VWAP v0.1 y v0.2** | Propuesta, no aprobada | Ninguno todavía | **Candidata confirmatoria**, si se aprueba |
| Originales ausentes | H-REV-SHOCK «69758896…» y H-EMA9-VWAP «v1, 3114b565…» | **No recuperados** | Desconocido | No se puede afirmar nada |

**Recuento:** más de 25 hipótesis o variantes probadas o consideradas. **Ninguna** obtuvo «respaldada».

## 2. Confirmatorio frente a exploratorio
- **Confirmatorias** (si se aprueban): H-REV-SHOCK v0.2 y H-EMA9-VWAP v0.2, cada una con **una** configuración primaria. Familia de 2, con Bonferroni α = 0,025 por hipótesis (MEC §6). También T-papel, bajo su propio protocolo.
- **Exploratorias:** todo lo demás, incluidos los análisis secundarios, las variantes de estrés y los subperíodos. **Un resultado exploratorio solo puede motivar un prerregistro nuevo**, con datos no vistos.

## 3. Reapertura de familias descartadas (riesgo explícito)
- **H-REV-SHOCK pertenece a la familia «reversión tras extremos»** (C10 y «reversión tras extremos o liquidaciones»), que el registro marca como **DESCARTADA en la fase E3** por falta de evidencia rigurosa y de datos.
  - Regla del registro: «ninguna hipótesis descartada se reabre sin un prerregistro nuevo y una razón que no venga de mirar los mismos datos».
  - **Cumplimiento:** el prerregistro sería nuevo (v0.2) y la razón viene de tu pedido, no de mirar datos.
  - **Riesgo:** reabrir familias descartadas acumula intentos sobre los mismos activos y períodos. **Requiere tu decisión explícita (D-G5).**
- **H-EMA9-VWAP** es una regla de tendencia horaria en BTC, la misma familia amplia que **E1-P1** (descartada, en contra) aunque con otra regla. Se declara como **nuevo intento sobre la misma familia y los mismos datos de BTC**.

## 4. Períodos contaminados
| Datos | Período | Usado por | Consecuencia |
|---|---|---|---|
| BTC y ETH spot 1d | 2017-08 → 2021-12 | Desarrollo de T, V y R (F3), E2 | Desarrollo; conocido |
| BTC y ETH spot 1d | 2022-01 → 2026-05 | **T fuera de muestra (uso único consumido)**, E2 | E de H-REV-SHOCK **no es independiente** |
| BTCUSDT 1h | 2019-10 → 2026-05 | H-CARRY, **E1 (P1–P3)** | D y E de H-EMA9-VWAP (BTC) **no son independientes** |
| Funding de BTC y ETH | 2019/2020 → 2026 | H-CARRY, E2-B | No se usa en las propuestas |
| Todos los pares USDT 1d | 2017 → 2026-05 | E3 (solo calidad y estructura) | No se calcularon retornos; contaminación baja, pero los datos se vieron |
| Período reservado de H-CARRY | 2026-06-01 → 2026-10-13 | Solo como historia de la señal en T-papel (rama A) | **No se lee** en las propuestas |
| Prospectivo | ≥ 2026-10-14 | T-papel (sin cortes todavía) | La única ventana independiente |

**Ningún hash vuelve independiente un período.** Los hashes identifican artefactos; no eliminan el conocimiento previo de quien diseña.

## 5. Riesgos y mitigación
| Riesgo | Dónde | Mitigación propuesta | Riesgo residual |
|---|---|---|---|
| **Selección de hipótesis tras ver investigaciones previas** | Todas | Bonferroni dentro de la familia nueva; exigir la etapa prospectiva para «confirmada» | Alto en E (contaminado) |
| **Grados de libertad del diseñador** (umbral de shock, ventana, horario, temporalidad) | H-REV-SHOCK y H-EMA9-VWAP | Una sola configuración, fijada antes de cualquier dato; los cambios generan una versión nueva declarada | Medio: las elecciones conceptuales siguen siendo arbitrarias |
| **Compuerta por resultado de D** | v0.1 | **Eliminada** en v0.2 | — |
| **P usado como valor p** | v0.1 y T | MEC v0.2 (bootstrap-t calibrado); en T se documenta como limitación | T: ninguno práctico (P = 0,755, lejos de cualquier umbral) |
| **Miradas repetidas sin corrección** | T-papel (cortes de 24, 36… meses) | Enmienda D-T2, solo antes de la primera mirada y con tu aprobación | Si no se enmienda, error de tipo I acumulado mayor al nominal |
| **Dependencia entre BTC y ETH** | Todas | Conjunto con bootstrap por bloques del promedio, que conserva la dependencia cruzada | La información efectiva es menor que el doble |
| **Agrupamiento de eventos** | H-REV-SHOCK | n_eff ≈ eventos no agrupados; N_min = 30 | Potencia baja |
| **Costos subestimados** | H-EMA9-VWAP sobre todo; H-REV-SHOCK en los shocks | Estrés ×2 y ×3 y slippage de 15 pb (descriptivos); Etapa F | Spread real en eventos extremos desconocido |
| **Mirada al futuro** | Implementación | B1, B2 y B8 (truncamiento, perturbación futura, fin de ventana) | Bajo si las pruebas pasan |
| **Lectura del período reservado** | v0.1 (defecto) | Corregido en v0.2 (liquidación en el último cierre de E) | — |
| **Datos faltantes tratados mal** | H-EMA9-VWAP | Reglas explícitas; 38 barras (35 + 3 en conflicto) | Bajo |
| **Supervivencia** | No aplica a BTC y ETH | — | Aplicaría a cualquier ampliación a más activos (E3) |
| **Sesgo de publicación interno** (informar solo lo favorable) | Programa | Este registro, más el registro de ejecuciones de solo añadidos con todas las corridas | Bajo si se respeta |
| **Revisión independiente ausente** | Todo el expediente | Se declara; se proveen fórmulas para revisión externa | No mitigado |

## 6. Qué cambios requieren una versión nueva y otro protocolo
- **Cualquier cambio en:**
  - las reglas de señal, entrada o salida;
  - los umbrales;
  - la temporalidad;
  - los activos;
  - los períodos;
  - el benchmark o la métrica primaria;
  - la prueba o α;
  - N_min;
  - el tratamiento de los datos faltantes.
- **Si el cambio ocurre después de leer D**, la versión nueva lleva la advertencia «diseñada tras ver D» y su E pierde aún más independencia.
- **Si ocurre después de E**, E ya no puede volver a usarse para esa hipótesis. Solo queda la vía prospectiva.
