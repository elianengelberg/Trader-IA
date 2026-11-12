# Dictamen metodológico general (Trader-IA, 2026-10-20)

**Naturaleza:** auditoría documental y diseño. **No se ejecutó ningún backtest, conteo sobre datos reales, simulación, descarga ni cambio en el repositorio.** Hubo dos cálculos:
- aritmética de potencia y costos sobre supuestos, más una cifra derivada del IC ya registrado de T (`evidencia/02`);
- verificaciones de integridad de solo lectura (`evidencia/01` y `03`).

**Revisión independiente por otro modelo:** **no realizada.**

## 1. Estado por línea

| Línea | Estado actual | Evidencia existente | Principal limitación | Siguiente paso | Autorización requerida | Conclusión defendible hoy |
|---|---|---|---|---|---|---|
| **T** | Fuera de muestra **ejecutado una vez** (2026-10-17); papel congelado **sin cortes** | Exceso +7,05 %/año, IC90 −8,82 / +22,87, P = 0,755 → **EVIDENCIA INSUFICIENTE**. Artefactos íntegros por hash | **Potencia:** confirmar +7 %/año en papel llevaría unos 65 años (TE ≈ 20 %); miradas repetidas sin corrección desde los 24 meses | Esperar al corte informativo del **2027-04-18** | D-T1 / D-G4 (dónde escribir el corte) | **No hay evidencia de ventaja ni de su ausencia**; el papel solo puede detectar un efecto grande o un fracaso grueso |
| **H-REV-SHOCK** | Original **no recuperado**; propuestas v0.1 y **v0.2 (nueva)**, no aprobadas | **Ninguna** | Pocos eventos esperables, potencia baja; reabre una familia descartada (C10) | Decidir D-G1 y D-G5; luego Etapa A (congelar) y F0 (factibilidad) | A-G1, D-G5, A-RS-1 | **Nada** sobre su rentabilidad |
| **H-EMA9-VWAP** | Original «v1» **no recuperado**; v0.1 y **v0.2 (nueva)**, no aprobadas; **ETH 1h no disponible** | **Ninguna** (E1-P1, otra regla horaria, dio en contra: es contexto, no evidencia) | **Costo:** 30 pb por operación, del mismo orden que la ventaja detectable; contaminación por E1 | Decidir D-G1; si sigue, A-EV-1 (ETH) y Etapa A | A-G1, A-EV-1 | **Nada** sobre su rentabilidad |

## 2. Autoauditoría de los documentos previos

Revisé íntegramente los nueve documentos pedidos. Sus hashes coinciden con lo registrado (`evidencia/01_integridad_inicial.txt`). **Los documentos previos no se modificaron:** las correcciones están en este expediente.

| # | Gravedad | Documento | Defecto | Corrección |
|---|---|---|---|---|
| F1 | **Alta** | Propuestas v0.1 (MEC v0.1) | 1 − P usado como valor p, y Holm sobre él, sin calibración | MEC v0.2 §1 y §4: bootstrap-t centrado y calibrado; P solo descriptivo |
| F2 | **Alta** | Propuestas v0.1 | Salidas en la apertura siguiente al final de E: podían **leer el 2026-06-01** (período reservado) | v0.2: liquidación en el último cierre válido de la ventana |
| F3 | Media | Propuestas v0.1 | El percentil del nulo emparejado (≥ 0,90) entraba en el criterio sin calibrar. «No respaldada» = P < 0,10 mezclaba ausencia de evidencia con evidencia de ausencia | MEC v0.2 §7 y §8 |
| F4 | Media | Propuestas v0.1 | Compuerta de futilidad P < 0,10 en D: sesgo de selección | Eliminada; solo compuertas de factibilidad (MEC §9) |
| F5 | Media | H-REV-SHOCK v0.1 | σ con desvío alrededor de la media, pero z con el numerador centrado en 0 | v0.2: RMS |
| F6 | Media (conceptual) | H-REV-SHOCK v0.1 | Un shock consecutivo **bajaba** la meta de recuperación | v0.2 C2, declarado como cambio conceptual (D-RS-C2) |
| F7 | Media | H-EMA9-VWAP v0.1 | Benchmark diario contra una estrategia horaria; salida indefinida si la sesión queda incompleta con una posición abierta | v0.2 C1 y C2 |
| F8 | Baja | Propuestas v0.1 | Factor de potencia 2,49 (α = 0,05), cuando con Bonferroni corresponde 2,80 | v0.2 |
| F9 | Baja | `DIAGNOSTICO_DISCREPANCIA_DATOS_308.md` y matriz v1 | «38 faltantes y 3 en conflicto» podía leerse como 41. **Las 3 están incluidas en las 38** (adenda 1 de E1: «pasan de 35 a 38») | Aclarado aquí y en H-EMA9-VWAP v0.2; el documento original no se modifica |
| F10 | Baja | MEC v0.1 | «Los bloques absorben la dependencia»: una afirmación excesiva | MEC v0.2 §1.2 y §10 |
| F11 | Baja | `REGISTRO_ACCIONES_Y_DECISIONES.jsonl` (fase documental) | Algunas marcas de tiempo aproximadas (ya declaradas allí) | Sin cambios; aquí se registran marcas exactas |
| F12 | Proceso | Propuestas v0.1 | No advertían que H-REV-SHOCK **reabre** una familia descartada en E3 | D-G5 |
| F13 | Proceso | Todo | No advertía que **el scratchpad es efímero** | D-G0 |
| F14 | Proceso | Documentos de T | No se explicitaba la falta de corrección por miradas repetidas en el papel | Plan §4.5 y D-T2 |

**Lo que se sostiene de los documentos previos:**
- el cierre de T (cifras verificadas contra el JSON original);
- el diagnóstico de los 308 archivos;
- las auditorías de recuperación de los originales;
- la matriz v1, salvo F9 y F10.

## 3. Juicios centrales
1. **El problema no es de implementación sino de información.** Con BTC y ETH, en los horizontes disponibles, la potencia para efectos moderados es baja.
   - **T:** confirmar +7 %/año exigiría unos 65 años de papel; un efecto como el de desarrollo, unos 9.
   - **H-REV-SHOCK:** probablemente pocos eventos.
   - **H-EMA9-VWAP:** potencia aceptable, pero un costo del orden del efecto detectable.
2. **El período 2022–2026 ya no puede dar evidencia independiente** para ninguna regla sobre BTC y ETH. Las E históricas de las propuestas solo pueden:
   - (a) detectar un fracaso grueso;
   - (b) dar una «ventaja histórica contaminada», que solo la fase prospectiva confirmaría.
3. **La vía prospectiva es la única independiente.** Para que sea concluyente necesita:
   - un δ económico fijado por vos (D-S4);
   - una prueba secuencial con gasto de α;
   - aceptar de antemano que puede terminar en «no concluyente».
4. **Recomendación de priorización** (juicio, no dato):
   - (i) preservar el expediente (D-G0);
   - (ii) decidir D-G1 y D-G5;
   - (iii) aprobar el MEC (D-S1 a D-S5) y autorizar su calibración sintética (A-S1), que no toca datos reales;
   - (iv) solo después, factibilidad (F0 y el conteo de D).
   - No veo justificación metodológica para gastar las E históricas antes de esos pasos.

## 4. Desacuerdos metodológicos explícitos (para revisión por ChatGPT u otro revisor)
1. **Prueba primaria en frecuencia diaria (exceso de timing) frente a por operación**, en H-REV-SHOCK. Recomiendo la diaria por coherencia con el benchmark. Con pocos eventos, la de operación es más interpretable.
2. **ℓ fijo (20) frente a ℓ elegido con los datos.** Recomiendo el fijo, con la regla de respaldo calibrada.
3. **Benchmark de exposición equivalente frente a buy and hold.** Elegí el primero porque responde a la pregunta de timing; buy and hold responde otra pregunta.
4. **Bonferroni frente a Holm.** Elegí Bonferroni por la secuencialidad.
5. **No enmendar el papel de T (D-T2).** Lo recomiendo por la integridad del congelado, aunque así se acepta un error de tipo I acumulado mayor desde los 36 meses.
6. **El nulo emparejado de H-REV-SHOCK con niveles análogos (MEC §8)** es débil. Un revisor podría preferir eliminarlo. Lo mantengo solo como descriptivo.
7. **δ (D-S4)** es una decisión económica que no corresponde al revisor estadístico.
