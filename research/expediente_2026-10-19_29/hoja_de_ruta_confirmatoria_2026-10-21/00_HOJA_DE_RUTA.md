# Hoja de ruta hacia una primera hipótesis confirmatoria defendible (2026-10-21)

**Alcance.** Análisis sin datos de mercado, sin commits, push, anclajes ni operaciones reales.
- Usa el registro del programa (39 hipótesis), los documentos de E1–E3 y de r1, y el diseño calibrado de PEC-1.1.
- Toda cifra viene de un documento citado o de `evidencia/H1–H2`, calculadas con `codigo/`.
- La literatura es la revisión de E3 (`INFORME_E3.md` §2–3, con sus fuentes). No se volvió a consultar.

## 0. Recomendación priorizada
| # | Qué | Por qué | Quién decide |
|---|---|---|---|
| **1** | **Desbloquear la única prueba histórica pendiente que puede producir evidencia útil ya: E3-H1, momentum transversal (información), con su protocolo v3 congelado (`279a865f…`)** | Es la de mayor valor informativo por unidad de tiempo (§3). Ya está diseñada, congelada y calibrada; **nadie miró sus resultados**. Su único bloqueo es un dato | **Vos**: reapertura acotada de E3, fuente de la lista de exclusiones, B-4 acotado |
| **2** | **D-G4 y R-5:** rama `registros` protegida más OpenTimestamps (§5), **antes** de la ejecución de E3 y antes del 2027-04-18 | Sin ancla externa, ningún «fijado antes» es verificable desde fuera, ni el de E3 ni los cortes de T-papel | **Vos** |
| **3** | **D-G1: no iniciar** H-REV-SHOCK v0.2, H-EMA9-VWAP v0.2 ni H-E1-BC | Con su IR plausible, la confirmación económica es improbable (3–7 %); además reabren familias descartadas o vienen de lecturas secundarias (§2) | **Vos** (recomendación: no) |
| **4** | **δ: 10 % solo como valor provisional de trabajo; no fijarlo todavía** | No está en el camino crítico: E3-H1 no usa δ. Su justificación depende de tu capital y tus costos fijos, que no constan (§4) | **Vos**, cuando aportes K y F |
| 5 | T-papel sin cambios | Es la única prospectiva en curso; detecta solo efectos grandes (D-T3) | — |
| 6 | (Opcional, baja) C8, prima de varianza: solo un estudio de viabilidad documental | Prima con fundamento sólido, pero exige datos pagos, infraestructura nueva y tiene colas extremas | Vos, si querés abrir una línea nueva |

**No recomiendo** activar ninguna hipótesis para desbloquear la fase prospectiva, relajar reglas de E3 ni agregar infraestructura antes de saber si hay información.

## 1. Diagnóstico: por qué hoy no hay ninguna hipótesis confirmable
**Potencia de la prueba económica** con el diseño calibrado: 5 miradas O'Brien–Fleming y α = 0,025
(`evidencia/H1_potencia_y_delta.json`, prueba z). La regla real rinde entre 0 y 5 puntos menos (SEC-1.0).

| IR neto \ horizonte | 3 años | 4 años | 5 años |
|---|---|---|---|
| 0,35 (≈ T) | 0,09 | 0,10 | 0,12 |
| 0,5 | 0,13 | 0,16 | 0,20 |
| 1,0 | 0,40 | 0,51 | 0,60 |
| 1,27 | 0,58 | 0,71 | 0,80 |
| 1,64 | 0,80 | 0,90 | 0,95 |

**Lectura:**
- Las familias exploradas (tendencia o reversión en BTC/ETH) tienen un IR neto plausible de 0,3–0,5 (r1 §5). Con eso, una confirmación económica prospectiva tiene un 9–20 % de potencia **aun si el efecto existe**.
- El programa lleva 0 hipótesis respaldadas de 18 con resultado.
- **El cuello de botella no es la infraestructura, sino la información disponible por unidad de tiempo:** pocas apuestas independientes por año.
- r1 §6 ya lo anticipaba: solo hay esperanza en mecanismos con **muchas apuestas independientes** (muchos activos) o en primas con fuente económica clara.

## 2. Evaluación de las hipótesis existentes
| Hipótesis | Fundamento económico | Efecto plausible y potencia | Datos | Riesgos de sesgo | Veredicto |
|---|---|---|---|---|---|
| **E3-H1**: momentum transversal, **información** (correlación de rangos semanal en U100) | Subreacción y flujos que persiguen rendimientos entre monedas. A favor: LTW 2022, Zaremba, CTREND (Fieberg 2025), más fuertes en monedas grandes. En contra: Grobys 2019 y 2026 (sin momentum entre sobrevivientes), Han et al. (débil con costos), decaimiento tras la publicación | Potencia del 80 % con un IC de 0,020–0,027. Es justo el umbral económico: un IC de 0,01 da ≈ 7 %/año bruto y los costos son ≈ 4–8 %/año. Potencia 0,56–0,79 con IC 0,02 y 0,88–0,99 con IC 0,03 (v3 §7) | 26 105 ZIP de Binance Vision **ya descargados y con hash**. **Falta:** la lista de exclusiones 2020-05 → 2026-05 | Supervivencia (el bloqueo, controlado por la regla §4.11 iv). Contaminación **declarada y baja**: E3 vio la calidad de los datos, no los retornos. Multiplicidad: Holm m = 2 con compuerta | **Prioridad 1 (desbloquear)** |
| E3-H2: momentum transversal, **económica** (top 6 de U30 frente a EW-U30, long-only) | Ídem, con costos y banda | Efecto mínimo detectable 28–39 %/año. Con un neto realista de 10 %/año, potencia de 0,11–0,17 | Ídem | Ídem; concentración en una moneda | Corre en la **misma** ejecución única que H1 (v3). Solo sería informativa si el efecto es enorme |
| E3-H3: capa de efectivo | Timing de la cartera | Subordinada a H1 y H2 | Ídem | — | Solo si H1 y H2 rechazan |
| T-papel | Tendencia en BTC/ETH | IR ≈ 0,35; detecta solo efectos grandes | En curso | — | Seguir sin cambios |
| T, T-MULTI | Tendencia | Cerradas: INSUFICIENTE | — | Fuera de muestra consumido | No reabrir |
| H-CARRY | Carry de funding | Cerrada; el monitor abre solo si el funding supera 12 %/año (6,5 % el 2026-10-01) | — | Test consumido | Solo por su monitor |
| H-REV-SHOCK v0.2 | Ventas forzadas y provisión de liquidez | Exige ≥ 7,9 % neto por evento en 3 años. La regla decisiva tiene un tamaño de ≈ 1 % en el proceso disperso (C4) | BTC/ETH contaminados: solo prospectiva | Reabre la familia C10 descartada (D-G5) | **No iniciar** |
| H-EMA9-VWAP v0.2 | Tendencia intradía | Exige ≥ 0,34 % neto por operación. IR plausible bajo | ETH 1h no disponible; BTC contaminado | Misma familia amplia que E1-P1 (en contra) | **No iniciar** |
| H-E1-BC | La confianza del breakout ordena los retornos | ρ = 0,22, pero es 1 de 4 lecturas secundarias: ≈ 34 % de probabilidad de falso positivo | ETH/SOL 1h (no vistos) | La estrategia base (breakout) salió EN CONTRA: aunque se confirme, no tiene valor económico | **No iniciar** |
| T-baja-rotación | Tendencia | Sin protocolo | — | Familia de T | No |
| C8: prima de varianza | Prima de seguro, documentada en BTC | Sin rentabilidades netas publicadas; colas extremas | Pagos; infraestructura nueva | — | Solo un estudio de viabilidad documental, opcional |
| Funding transversal, CTREND | Extensiones de la familia transversal | — | — | Multiplicidad | E3 las difirió: solo si H1 muestra información |

## 3. Valor informativo comparado (`evidencia/H2_valor_informativo.json`)
Con priors escépticos explícitos: π = 0,10 o 0,25 de que el mecanismo exista con el tamaño detectable.

| Camino | Tiempo | P(respaldo) | VPP (un «respaldo» es real) | Si no hay efecto |
|---|---|---|---|---|
| **E3-H1 histórica**, IC real 0,02–0,03 | **Días**, una vez que exista la lista | 0,08–0,27 | **0,71–0,93** | 28–41 % de refutarla limpiamente (IC90 superior < 0,01), lo que cierra la familia |
| Económica prospectiva, IR 0,35–0,5 | 5 años | 0,03–0,07 | 0,24–0,73 | Casi siempre NO_CONCLUYENTE |
| Económica prospectiva, IR 1,0 (sin candidata plausible) | 5 años | 0,08–0,17 | 0,71–0,89 | — |

**Conclusión:**
- E3-H1 es el único camino en el que **los dos resultados informan** y que se resuelve en días.
- Su resultado no confirma rentabilidad: E3 v3 §7.3 dice que no sirve para comprometer capital. Sí decide si vale la pena gastar 2–8 años en una confirmación prospectiva (v3 §7.3: ≈ 2–3,5 años con IC 0,03 y 4–8 años con IC 0,02).

**Después de E3 (reglas fijadas ahora, sin mirar nada):**
- **H1 respaldada:** diseñar una confirmación prospectiva del mismo mecanismo con PEC-1.1. Ahí, y no antes, se justifica extender PEC con una métrica de información y su calibración. Requiere δ, D-G1, B-4, D-G4 y R-5.
- **H1 no respaldada o refutada:** cerrar la familia transversal según la cláusula v3 §7.4: nada se agrega para compensar. Sin otra candidata, corresponde la **pausa del programa** (regla de r1 §7), y como mucho el estudio documental de C8.

**Si no podés obtener la lista** (opción e de E3): E3-H1 queda NO_EVALUABLE para siempre en la historia. La alternativa es una prueba prospectiva de información de 2–8 años, que solo vale la pena si querés sostener un programa largo.

## 4. δ = 10 %: ¿tiene justificación económica real?
δ = (F/K + π)/(1 − d), con π = 2,5 % (`evidencia/H1_potencia_y_delta.json`).

| K (USDT) \ F anual, d | F 0, d 0,5 | F 250, d 0,5 | F 1000, d 0,5 | F 2600 (≈ 52 h a 50/h), d 0,5 |
|---|---|---|---|---|
| 10 000 | 5,0 % | **10,0 %** | 25,0 % | 57,0 % |
| 25 000 | 5,0 % | 7,0 % | 13,0 % | 25,8 % |
| 50 000 | 5,0 % | 6,0 % | 9,0 % | 15,4 % |
| 100 000 | 5,0 % | 5,5 % | 7,0 % | **10,2 %** |

Con d = 0,25 todos los valores bajan (por ejemplo, 6,7 % con K = 10 000 y F = 250).

**Veredicto:**
1. **10 % solo se justifica en combinaciones concretas:** K ≈ 10 000 con costos fijos mínimos (≈ 250/año, es decir, automatizado), o K ≈ 100 000 con tu tiempo valorizado. No es un valor universal.
2. **Si K ≈ 10 000 y valorizás tu tiempo de seguimiento,** el δ económico es 25–57 %. Ninguna estrategia plausible lo alcanza, y la pregunta pasa a ser si conviene invertir tiempo en el programa.
3. **Frente a las alternativas:**
   - 5 % hace inalcanzable la confirmación con cualquier TE ≥ 4 %;
   - 15–20 % acorta n_max pero descarta ventajas que, con capital grande, sí valdrían la pena.
4. **δ no está en el camino crítico:** E3-H1 es una prueba de información sin δ. δ solo hace falta para una prospectiva económica PEC-1.1 y para la categoría «efecto relevante descartado».

**Recomendación:** mantener 10 % como **valor provisional rotulado**. Fijarlo definitivamente solo cuando aportes K y F reales, y antes de cualquier prerregistro prospectivo. Fijado así no habilita nada.

## 5. D-G4 y R-5: recomendación concreta
**D-G4: dónde viven los registros.**
- **Ubicación:** este repositorio de GitHub, en una **rama dedicada `registros`** creada desde `72ffae5`, para que los registros convivan con el código que referencian.
- **Contenido:**
  1. T-papel: `research/tendencia_btc/papel/cortes/REGISTRO.jsonl`, que solo admite añadidos según la adenda 2, más el resultado de cada corte. Los ZIP y `.CHECKSUM` ya están ignorados.
  2. La adenda de E3 con la lista de exclusiones y su hash, y las salidas de la ejecución única, si autorizás la prioridad 1.
  3. Los prerregistros PEC-1.1 congelados y cada mirada.
  4. `anclas/`, con las pruebas de OpenTimestamps.
- **Reglas** (un ruleset de GitHub sobre `registros`):
  - prohibido el push forzado y el borrado;
  - historia lineal;
  - solo vos podés actualizar la rama, **sin excepción para administradores**;
  - un registro por commit, nunca enmendado;
  - el mensaje lleva el SHA-256 del registro y el del anterior (cadena de hashes).
- **Preservación** (3 copias, 2 medios, 1 fuera del sitio):
  - GitHub;
  - tu clon local;
  - un `git bundle` mensual en un almacenamiento tuyo.
  - Los 5 ZIP de entregas (v0.5, r1, A-S1, DECISIONES, ADENDA), que hoy **solo** existen en el scratchpad efímero y como adjuntos: guardalos en dos lugares. Opcionalmente, como activos de una *Release* de GitHub, que los preserva y los fecha sin agrandar la historia de git.

**R-5: ancla externa.**
- **O2:** la rama protegida anterior. Es un registro público, fechado por el servidor y resistente a reescrituras. Su límite es que la controlan GitHub y vos.
- **O5:** OpenTimestamps.
  - Procedimiento: `ots stamp anclas/ANCLAS_<fecha>.txt` (la lista de SHA-256); commitear el `.ots`; horas después, `ots upgrade`; verificar con `ots verify`.
  - Ventajas: es gratis, no depende de GitHub ni de vos y queda anclado en la cadena de Bitcoin.
  - Límite: prueba existencia antes de una fecha, no autoría (eso es R-3).
- **Qué anclar, en orden:**
  1. los SHA-256 de los 5 ZIP de entregas, de la especificación y el resultado de SEC-1.0 y de `PEC-1.1.md`;
  2. el prerregistro y la adenda de T-papel con `ARTEFACTOS_SHA256.txt`. Ya son públicos por el push del 2026-10-21, pero OpenTimestamps agrega un tiempo independiente de GitHub;
  3. **la adenda de E3, con el hash de la lista, ANTES de la ejecución única**;
  4. cada corte de T-papel y cada mirada futura.
- **Límite honesto:** anclar ahora **no puede probar** que los criterios de A-S1 y SEC-1.0 se fijaron antes de sus corridas; eso depende de registros locales. Solo protege lo que viene. Por eso tiene que **preceder** a la próxima evaluación.
- **Lo que tenés que hacer vos:**
  - crear la rama y el ruleset;
  - autorizar los push a `registros`;
  - autorizar el anclaje externo (salida de red a los calendarios de OpenTimestamps y el cliente en un entorno aislado).

## 6. Requisitos mínimos y bloqueos reales de la prioridad 1
| Requisito | Tipo | Estado |
|---|---|---|
| Lista completa y verificable de exclusiones y renombres de pares USDT, de 2020-05 a 2026-05, con fecha efectiva | **Bloqueo real (dato externo)** | Falta. E3 §8: (a) compilación manual tuya de la categoría Delisting de binance.com, cubriendo **todos** los años, recomendada; (b) web.archive.org, incierta; (c) confirmar que Binance permite la lectura automatizada; (d) fuente con licencia, menos verificable |
| Reapertura acotada de E3, solo para resolver A3 y ejecutar una vez la v3 | Autorización tuya | Pendiente. Lo exige el cierre de E3 |
| B-4 acotado: leer los 26 105 ZIP de Vision ya descargados (con hash), solo para esa ejecución | Autorización tuya | Pendiente |
| D-G4 + R-5, antes de la ejecución | Autorización tuya | Pendiente (§5) |
| La adenda que congela la lista; volver a comprobar la regla §4.11 (iv); ejecución única de la v3; informe | Trabajo técnico mío | Listo para hacerse; **no requiere infraestructura nueva** |

**Regla de validez, fijada:** si con la lista completa la ventana H no cumple §4.11 (iv), o queda con menos de 156 semanas, E3 sigue **INVÁLIDO con Vision**. No se relaja ni se recorta.

## 7. Decisiones tuyas, en orden, con la consecuencia de cada respuesta recomendada
1. **D-G4 + R-5 → rama `registros` protegida + OpenTimestamps.** Desde entonces, todo «fijado antes» es verificable desde fuera. Cada corte o mirada pasa a ser un push autorizado en su momento.
2. **E3 → reapertura acotada + compilación manual de la lista.**
   - Con la lista completa: una ejecución única en días, con evidencia de información transversal.
   - Si la lista no se puede completar: E3 queda NO_EVALUABLE y el programa no tiene ninguna vía histórica.
3. **B-4 → lectura acotada de los datos de Vision ya descargados.** Solo esa ejecución; nada nuevo.
4. **D-G1 → «no iniciar»** H-REV-SHOCK v0.2, H-EMA9-VWAP v0.2 y H-E1-BC. No queda ninguna confirmatoria activa hasta el resultado de E3.
5. **δ → 10 % provisional; aportá K y F para fijarlo.** Nada se habilita mientras tanto.
