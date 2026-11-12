# 05 — Plan cuantitativo: Protocolo de Evaluación Cuantitativa PEC-1.0

**Objetivo del programa:** descubrir si existe una estrategia con ventaja estadística real **después de costos**.
- Un resultado válido puede ser que **no la haya**, o que **no sea detectable** en un horizonte útil.
- El protocolo no está diseñado para que algo gane.

**Separación estricta:**
- PEC-1.0 aplica solo a hipótesis **futuras**.
- No toca T, T-papel, T-MULTI, H-CARRY ni sus congelados.
- No reabre nada por iniciativa propia.
- No usó ningún dato de mercado: todo lo construido se probó con datos **sintéticos**.
- Ninguna prueba de infraestructura es evidencia de rentabilidad.

**Base:** el MEC v0.2 y el Plan de evidencia del expediente metodológico (`33ba77c1…`), que ya resolvían la mayor parte
del diseño. PEC-1.0 los **implementa**, toma las decisiones técnicas pendientes (02, categoría B) y cubre lo que faltaba:
- apalancamiento, margen y liquidación;
- funding;
- validación de datos ejecutable;
- mirada al futuro genérica;
- criba de detectabilidad;
- presupuesto y parada;
- registro del programa.

## 1. Qué está construido y probado (sin datos reales)
`protocolo_cuantitativo/`: Python estándar sin dependencias externas; **72 pruebas pasan**
(`evidencia/F1_pruebas_protocolo.txt`).

| Módulo | Qué hace | Cómo se verificó |
|---|---|---|
| `pec/inferencia.py` | Bootstrap-t por bloques circulares centrado bajo H₀ (MEC §4), Newey–West y regla de respaldo | Valores a mano; dualidad p ↔ IC **exacta**; contraste diferencial con la implementación de E3 (`7b280386…`), que encontró y permitió corregir un defecto propio (N-1) |
| `pec/secuencial.py` | Fronteras de Lan–DeMets tipo O'Brien–Fleming, potencia y factor de inflación | Valores publicados (4,8769 / 3,3569 / 2,6803 / 2,2898 / 2,0310) y Monte Carlo independiente de 40 000 trayectorias |
| `pec/potencia.py` | Años necesarios, δ mínimo, δ por operación, criba de detectabilidad | Reproduce las cifras de los documentos del proyecto (Plan §4.2–§4.4) |
| `pec/contabilidad.py` | MEC §2 (long/flat, f y s, liquidación al cierre de la ventana, benchmark de exposición equivalente), funding, margen aislado y liquidación | Referencia a mano (B5); suma de operaciones = Δ capital (B9); identidad x̄ = cov(w, r) a 1e-14 |
| `pec/datos.py` | Validador V1–V9 (compuerta INVÁLIDO) | 12 pruebas: serie limpia, defectos inyectados y casos de borde |
| `pec/mirada_futuro.py` | B1 (truncamiento) y B2 (futuro alterado de dos maneras) para cualquier estrategia | Detecta mirar la barra actual (B2) y una estadística global (B1 y B2); deja pasar una estrategia causal |
| `pec/metricas.py` | Rendimiento neto, volatilidad, Sharpe descriptivo, caída máxima, exposición, rotación, acierto y estabilidad por subperíodo | Valores a mano |
| `pec/decision.py` | Categorías del MEC §7 (con precedencia) y miradas prospectivas (§7.1) | Tabla de casos; sin δ no hay «efecto descartado» ni fase prospectiva |
| `pec/prerregistro.py` + `esquemas/prerregistro_v1.schema.json` | Esquema, semántica (17 comprobaciones: errores que impiden congelar y avisos), huella y congelamiento | 31 pruebas con mutaciones del ejemplo sintético |
| `pec/programa.py` + `registro_programa/` | Registro de las 39 hipótesis del programa; bloquea iniciar las cerradas o no aprobadas | Pruebas |
| `calibracion/` | Calibración del MEC §5, **bloqueada** sin A-S1; parámetros congelados (`28764d31…`) | Prueba de humo y prueba del bloqueo |

## 2. Ciclo de vida de una hipótesis
| Etapa | Entrada | Trabajo | Salida (fijada de antemano) | Autorización |
|---|---|---|---|---|
| 0. Tarjeta | Idea con mecanismo | `plantillas/TARJETA_…` (§A) | Registrada en el programa | — |
| 1. Criba | Tarjeta | `criba_detectabilidad` con el IR plausible **sin datos** | DETECTABLE, o NO_DETECTABLE (no se inicia, salvo que se acepte por escrito «no concluyente») | — |
| 2. Prerregistro | Criba superada | JSON PEC-1.0 válido; congelado; sellado y anclado (R-5) | Hash congelado | D-G1 de la hipótesis |
| 3. Pruebas sintéticas | Prerregistro congelado | Implementación + B1/B2/B5/B9 + validador sobre fixtures | Todas pasan; código congelado por hash | — |
| 4. Datos | Etapa 3 cerrada | B-4: descarga, manifiesto, sumas, V1–V9, segundo proveedor | VÁLIDO, o INVÁLIDO (no se evalúa) | B-4 |
| 5a. Histórico (opcional) | Datos válidos **no contaminados** | Una única evaluación con candado (P4) | Una categoría del MEC §7 | Autorización expresa |
| 5b. Prospectiva (por defecto) | Prerregistro con δ y calendario | Papel con miradas OBF, registros anclados | CONFIRMADA / EFECTO DESCARTADO / NO CONCLUYENTE | D-G4, R-5 |
| 6. Reproducción | Resultado favorable | Otra persona u otro entorno, con código determinista | REPRODUCIDO, o no | A9/A14 |
| 7. Viabilidad | Confirmada y reproducida | Ejecución simulada: spread, profundidad, latencia, capacidad | Informe separado. **No autoriza operar** | Otra autorización |

**Precondición del método:** la calibración A-S1 debe estar aprobada antes de cualquier etapa 5. Hoy no lo está.

## 3. Requisitos de la misión → regla PEC → dónde se hace cumplir
| Requisito | Regla PEC-1.0 | Dónde se aplica | Prueba |
|---|---|---|---|
| Hipótesis económica y mecanismo causal | Campos obligatorios: mecanismo, por qué existiría, por qué no estaría arbitrada | Esquema (texto mínimo) + tarjeta (juicio humano) | `test_errores_de_esquema` |
| Universo y frecuencia | Activos, mercado, exchange, frecuencia (enumerada), supervivencia | Esquema | ídem |
| Reglas exactas de entrada, salida y riesgo | Texto + **una sola** configuración; cero variantes | Esquema + semántica | «varios valores» |
| Separación temporal | desarrollo < validación < prueba final, sin solaparse; la prospectiva empieza desde 2026-10-14 | Semántica | «se solapan», «antes de 2026-10-14» |
| Anticipación | B1 y B2 obligatorias en cada implementación; ejecución en la apertura siguiente | `mirada_futuro`; esquema (`momento`) | 3 pruebas |
| Supervivencia | Campo obligatorio; universo fijado en la fecha de inicio | Esquema; B-4 paso 7 | — |
| Faltantes, duplicados, velas incompletas | Umbral ≤ 5 % (MEC: 0,5 %); duplicados idénticos: una copia; conflictos: INVÁLIDO; velas incompletas: excluir | `datos.py`; esquema | 12 pruebas |
| Comisión, spread, slippage, latencia, funding | Obligatorios en `ejecucion`; un perpetuo sin funding es un error | Esquema + semántica; `contabilidad` | `test_funding_y_liquidacion` |
| Apalancamiento, margen, liquidación | Con apalancamiento > 1, el margen de mantenimiento es obligatorio; liquidación por el extremo adverso de la barra | Semántica; `simular_apalancada` | ídem |
| Benchmarks y alternativa sin operar | Exposición equivalente (primario), comprar y mantener, efectivo | Esquema (mínimo 3) | — |
| Rentabilidad neta, volatilidad, caída máxima, exposición, rotación, estabilidad | Todas se informan; ninguna decide | `metricas.py` | `test_metricas_descriptivas` |
| Tamaño de muestra y potencia | N_min ≥ 30; TE, IR plausible, horizonte y criba | Esquema + semántica | `test_criba_de_detectabilidad` |
| Multiplicidad y selección | Bonferroni dentro de la familia declarada; registro del programa; reabrir exige D-G5 | Semántica; `programa.py` | «Bonferroni», «D-G5» |
| Robustez y sensibilidad | Al menos una de: costos ×2 o ×3, retraso de 1 barra, por activo, subperíodos, sin funding. Es **descriptiva** (nivel 3) | Esquema; `decision.py` | `test_sin_delta…` |
| Aceptación, rechazo e inconclusión fijadas de antemano | MEC §7 y §7.1, con precedencia | `decision.py` | `test_categorias_historicas` (7 casos) y `test_mirada_prospectiva` |
| Reproducción independiente y registro | REPRODUCIDO por otra persona; determinismo; todas las reproducciones; registros anclados | Esquema + semántica (A14) | «A14» |

## 4. Decisiones técnicas que fija PEC-1.0
Detalle y criterio en `02_EXPEDIENTE_DECISIONES.md`:
- **D-S1:** bootstrap-t, ℓ = 20, B = 9999.
- **D-S2:** Bonferroni.
- **D-S3:** máx(p_ℓ20, p_ℓ40, p_NW).
- **D-S5:** O'Brien–Fleming.
- **D-S6:** el nulo emparejado es descriptivo.
- **D-S7:** sin compuerta por resultado.
- **A3:** la robustez no veta.
- **A6:** «todas».
- **A9/A14:** REPRODUCIDO, independiente y determinista.
- **A10:** 0 reintentos, determinismo y límite de tiempo.
- **A13:** política de raíces.

**No fija δ** (A8): es tuya.

## 5. Hallazgo cuantitativo central: el límite de detectabilidad
`evidencia/F5_criba_candidatas.txt`, calculado con `pec.potencia` y `pec.secuencial`. R = 1,0247 para 5 miradas OBF.

| Horizonte prospectivo | IR neto mínimo para confirmar (α = 0,025; potencia 80 %; 5 miradas) |
|---|---|
| 1 año | 2,84 |
| 2 años | 2,01 |
| 3 años | **1,64** |
| 5 años | 1,27 |
| 10 años | 0,90 |
| T, como referencia | Su IR ≈ 0,35 necesitaría unos 66 años |

**Consecuencia:**
- Una hipótesis cuya razón de información neta plausible sea, como las de tendencia en un solo activo, del orden de
  0,3–0,5 **no puede confirmarse** en ningún horizonte útil: el resultado esperable es «no concluyente».
- Esto no es un defecto del protocolo: es el límite de la información disponible. Ya lo decía el dictamen («el problema
  no es de implementación sino de información»).
- El programa debe **filtrar por detectabilidad antes de gastar datos**, no después.

## 6. Priorización de hipótesis

**Estado del programa** (registro del programa):
- 39 entradas;
- 18 con un resultado registrado;
- **ninguna respaldada**.

**Líneas cerradas que se respetan:**
- H-CARRY: detenida;
- T: fuera de muestra consumido;
- T-MULTI: no se reabre;
- E1, E2 y E3: cerradas o descartadas, con sus variantes prohibidas.

| Línea | Estado | Criba (con las cifras de su propia propuesta) | Recomendación |
|---|---|---|---|
| **T-papel** | Prospectiva en curso, congelada | No aplica: protocolo propio; detecta solo un efecto grande o un fracaso grueso (D-T3) | **Seguir sin cambios.** Antes del corte del **2027-04-18** hace falta D-G4/D-T1 (dónde se escribe) |
| **H-REV-SHOCK v0.2** | Propuesta, no aprobada; reabre la familia descartada C10 | Para confirmar en 3 años: **≥ 7,9 % neto por evento** (≈ 6,8 eventos/año) o ≥ 4,6 % con 20 eventos/año. Señal/ruido por evento ≥ 0,37–0,63 | **No iniciar.** Exige creer en una ventaja por evento enorme, sobre una familia ya descartada (D-G5) y sobre datos contaminados |
| **H-EMA9-VWAP v0.2** | Propuesta, no aprobada; misma familia amplia que E1-P1 (en contra) | Para 3 años: **≥ 0,34 % neto ≈ 0,64 % bruto por operación**, con 30 pb de costo; ETH 1h no está disponible | **No iniciar como confirmatoria** salvo que aceptes de antemano «no concluyente» como resultado probable. Si se inicia: **solo prospectiva** (D-G2), con δ fijado |
| **Hipótesis nuevas** | — | Deben pasar la criba con un IR plausible justificado **sin datos** | **No propongo ninguna hoy.** Ninguna idea de la familia ya explorada (tendencia o reversión en BTC/ETH) tiene un IR plausible ≥ 1,6, y abrir más sin pasar la criba solo agrega multiplicidad |

**Dónde podría haber detectabilidad** (orientación para la tarjeta, no una propuesta):
- mecanismos con **muchas apuestas independientes por año** y un costo bajo frente a la ventaja: muchos activos poco
  correlacionados, o una frecuencia alta con costos medidos;
- primas por riesgo con una fuente económica clara.

Cada una trae sus propios problemas: supervivencia, capacidad, costos reales o riesgo de cola. Cada una exige datos
nuevos (B-4) y una tarjeta que pase la criba antes de cualquier descarga.

## 7. Presupuesto de complejidad y reglas de parada
| Regla | Valor |
|---|---|
| Hipótesis confirmatorias activas a la vez | Como máximo **2**, en una familia declarada (Bonferroni α = 0,025/m) |
| Configuraciones por hipótesis | **1** (`variantes_permitidas = 0`); cualquier cambio es una hipótesis nueva en el registro |
| Hipótesis nuevas que entran | Como máximo **1 por semestre**, y solo con la criba superada |
| Parada por hipótesis | INVÁLIDO → se corrige el dato, no la regla. EN_CONTRA o EFECTO DESCARTADO → cerrada. NO_CONCLUYENTE en n_max → cerrada. Futilidad no vinculante |
| Parada del programa | Si las **2** próximas confirmatorias que pasen la criba terminan sin respaldo, se **pausa** el programa para una revisión estratégica, sin más hipótesis de esas familias |
| Qué merece una investigación posterior | Solo una CONFIRMADA prospectivamente **y** REPRODUCIDA (niveles 4 + reproducción). La etapa 7 (viabilidad) se autoriza aparte |

## 8. Qué falta para empezar, y el próximo paso de mayor valor
- **Para empezar:**
  - A-S1 (calibración);
  - δ (A8);
  - D-G1 de alguna hipótesis que pase la criba;
  - B-4 (datos);
  - D-G4 (registros);
  - R-5 (ancla) para la fase prospectiva.
- **Próximo paso de mayor valor:** autorizar A-S1, que valida el método para cualquier hipótesis futura sin tocar
  datos. Antes, como condición de supervivencia del trabajo, **descargar los ZIP** (B-8). La lista completa está en `06`.
