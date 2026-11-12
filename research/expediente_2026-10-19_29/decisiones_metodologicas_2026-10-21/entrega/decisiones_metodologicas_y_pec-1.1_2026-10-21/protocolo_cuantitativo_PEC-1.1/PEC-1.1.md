# PEC-1.1 — Protocolo de Evaluación Cuantitativa, versión 1.1 (2026-10-21)

**Qué es:** la versión 1.1 del protocolo de r1 (PEC-1.0). Incorpora lo que A-S1 y SEC-1.0 demostraron sobre datos
sintéticos y corrige el defecto de unidades de δ.

**Qué no cambia:**
- PEC-1.0 no se modifica.
- Nada se aplica retroactivamente: T, T-MULTI, E1–E3 y H-CARRY se rigen por sus propios protocolos congelados.

**Lo que habilita:** prerregistros PEC-1.1. **No habilita la fase prospectiva** (§9).

## 1. Regla inferencial decisiva
- **Estadístico decisivo:** p = máx(p_ℓ20, p_ℓ40, p_NW).
  - p_ℓ20 y p_ℓ40: bootstrap-t por bloques circulares, centrado bajo H₀ (MEC §4), con ℓ = 20 y ℓ = 40.
  - p_NW: prueba t con error estándar de Newey–West (Bartlett, L = 20) y p = 1 − Φ(z).
  - Código: `pec.inferencia.respaldo` (`99d0d3e6…`), mediante `pec.prospectiva.inferencia_decisiva`.
- **Parámetros fijos:** B = 9999, y **una sola semilla congelada en el prerregistro** para todas las miradas y para
  ℓ = 20 y ℓ = 40.
- **Intervalo:** el IC90 es la **envolvente** de los tres intervalos.
- **Una serie degenerada** (sin variabilidad) no decide.
- **Validez:** si un componente es un valor p válido, el máximo también lo es (P(máx ≤ u) ≤ u). A-S1 lo comprobó: la
  regla cumple las 48 comprobaciones, mientras que el bootstrap-t ℓ = 20 solo cumple 33 de 48.

## 2. Métricas primarias y de respaldo
| Métrica | Papel |
|---|---|
| p de la regla del §1 y su IC90 envolvente | **Decisiva** |
| Bootstrap-t ℓ = 20 solo | **Descriptiva.** A-S1 no lo validó: sobre-rechaza en el proceso disperso C4 |
| p_ℓ40 y p_NW por separado | Descriptivos (componentes) |
| Media puntual, robustez (costos ×2, retraso, por activo, subperíodos), nulo emparejado | Descriptivos (MEC §7 nivel 3, §8). Nunca deciden |

## 3. Supuestos y procesos en que se calibró
**A-S1** (`CALIBRACION_AS1_PEC-1.0_2026-10-21.zip`, `37af592c…`):
- tamaño de cada prueba de tamaño fijo;
- procesos C1–C6: colas t₃, GARCH-t₄, AR(1)-t₃, exposición dispersa por eventos, intradía agregado y cambio de régimen;
- n ∈ {366, 731, 1096, 1612}, B = 1999;
- reproducida íntegramente byte a byte en esta versión.

**SEC-1.0:**
- **Especificación:** `b4064e8c…`. **Resultado:** `1de03994…`.
- **Qué calibró:** el procedimiento secuencial completo del §4 con B = 9999, en C1–C6, con n_max ∈ {1096, 1461, 1826}.
- **Resultado:** error global ≤ 2,70 % (cota superior con 95 % de confianza conjunta) y ≤ 2,46 % estimado. En C4,
  ≈ 1 %.

**Supuestos declarados:**
- estacionariedad débil y mezcla dentro de cada mirada;
- media poblacional constante bajo H₀;
- la calibración cubre **esos procesos**, no la distribución real de ningún mercado.

## 4. Diseño prospectivo y control del error global
- **K = 5 miradas.** La mirada k usa los **primeros n_k = round(k·n_max/5) días válidos** desde el inicio. Las fechas
  son exactamente `pec.prospectiva.calendario(inicio, n_max)`.
- **Fronteras:** Lan–DeMets tipo O'Brien–Fleming, α = 0,025 unilateral, evaluadas en t_k = n_k/n_max.
- **Confirmación:** se confirma en la primera mirada con p_k ≤ a_k = 1 − Φ(c_k).
  - Con B = 9999, **la mirada 1 no puede confirmar nunca**: p ≥ 10⁻⁴ > a_1 ≈ 5·10⁻⁷.
- **n_max** = ⌈365,25 · R · (2,8016 · TE/δ)²⌉, con R = 1,02472 (`pec.prospectiva.n_max_dias`). Se calcula; **no se elige
  a mano.**
  - **Si cae fuera de [1096, 1826] días, no se congela.**
  - Si es mayor, se declara de antemano «no alcanzable en el rango calibrado» (MEC §7.1). **No se relaja α ni se cambia δ
    para entrar.**
  - Si es menor, exige una calibración nueva.
- **Control del error global:** demostrado por SEC-1.0 para ese diseño. La potencia real con el n_max de la fórmula es
  ≈ 75–80 %, no 80 %.

## 5. δ
- **Definición:** δ es el exceso aritmético **anual** neto mínimo económicamente relevante, frente al benchmark de
  exposición equivalente (`potencia.unidad_delta = exceso_aritmetico_anual_neto`).
- **Escala de comparación:** se compara con intervalos de la media **diaria** mediante δ_d = δ/365,25
  (`pec.prospectiva.delta_diario`).
  - PEC-1.0 no convertía. Las funciones nuevas lo hacen y las viejas no se usan con PEC-1.1.
- **Quién lo fija:** el propietario (A8 / D-S4), antes de cualquier prerregistro que lo use. Hoy **no está fijado**.
- **Sin δ:** no hay fase prospectiva ni categoría «efecto relevante descartado».

## 6. Resultados ausentes, inválidos o inconclusos
| Situación | Mirada intermedia | Mirada final |
|---|---|---|
| Datos inválidos (validador V1–V9, integridad, candado) | **MIRADA_OMITIDA:** no se prueba, no se reprograma y no se recupera su α (conservador) | **INCONCLUSO_POR_DATOS** |
| Menos del 90 % de los n_k días previstos | MIRADA_OMITIDA | Menos del 90 % de n_max: INCONCLUSO_POR_DATOS |
| Entre el 90 % y el 100 % | Se evalúa con los días disponibles. Es una aproximación declarada, no calibrada | ídem |
| Más días de los previstos | Solo se usan los primeros n_k | ídem |
| Serie degenerada | CONTINUAR (no decide) | INCONCLUSO_POR_DATOS |
| Una mirada no realizada | Se registra como OMITIDA. Nunca se hace «más tarde» con otra frontera | — |

**Un dato inválido se corrige en el dato, no en la regla.** Corregirlo no reabre una mirada ya omitida.

## 7. Detenerse, continuar o declarar evidencia insuficiente
En cada mirada válida, en este orden:
1. p_k ≤ a_k: **CONFIRMADA_PROSPECTIVAMENTE** (nivel 4 del MEC). Se detiene.
2. IC90 envolvente superior < 0: **EN_CONTRA**. Se detiene.
3. IC90 envolvente superior < δ_d: **EFECTO_RELEVANTE_DESCARTADO**. Se detiene.
4. Si no, CONTINUAR. En la mirada 5: **NO_CONCLUYENTE**, y la hipótesis se cierra.

Las paradas 2 y 3 son de futilidad no vinculante: nunca confirman, así que no aumentan el error de tipo I. SEC-1.0 las
omitió, así que su error es una cota superior.

El IC90 de una mirada intermedia no está ajustado por las miradas. Solo se usa para la futilidad.

**Evaluación histórica única:** `pec.prospectiva.categoria_historica` (MEC §7, con δ convertido a escala diaria).

## 8. Relación entre la calibración sintética y la evaluación prospectiva
- **La calibración muestra** que, si la serie real se comporta como alguno de C1–C6, el procedimiento no confirma por
  azar más de ≈ 2,5 % de las veces.
- **No muestra:**
  - que la serie real se comporte así;
  - que haya ventaja;
  - nada sobre costos reales, capacidad o supervivencia.
- **Ningún resultado de A-S1 o SEC-1.0 es evidencia de rentabilidad.**
- **Una CONFIRMADA prospectiva:**
  - sigue exigiendo reproducción (A9/A14);
  - es un resultado sobre el papel;
  - no autoriza operar (etapa 7, otra autorización).

## 9. Condiciones que siguen pendientes para habilitar la fase prospectiva
| Requisito | Estado | Quién |
|---|---|---|
| Método calibrado (A-S1 + SEC-1.0) | **Cumplido** en PEC-1.1 | — |
| δ fijado (A8 / D-S4) | **Pendiente** | Propietario |
| Una hipótesis que pase la criba y su D-G1 | **Pendiente.** Ninguna candidata actual la pasa en el rango calibrado | Propietario |
| Prerregistro PEC-1.1 válido y congelado, con n_max en [1096, 1826] | Pendiente (depende de lo anterior) | — |
| B-4: fuente de datos autorizada, manifiesto y validador | **Pendiente** | Propietario |
| D-G4: dónde se escriben los registros | **Pendiente**. Antes del 2027-04-18 para T-papel | Propietario |
| R-5: ancla externa (O2 + O5) del prerregistro y de las miradas | **Pendiente** | Propietario |

**Hasta que se cumplan todos, la fase prospectiva sigue bloqueada.** El código lo hace cumplir: sin δ, o con n_max fuera
de rango, el prerregistro no se congela.

## 10. Archivos
**Nuevos:**
- `pec/prospectiva.py` y `pec/prerregistro_v11.py`;
- `esquemas/prerregistro_v1_1.schema.json`, que es igual a `construir_esquema_v11(v1)`;
- `plantillas/ejemplo_prerregistro_SINTETICO_v1_1.json`;
- `pruebas/test_pec_1_1.py`, con 43 pruebas;
- este documento y `CAMBIOS_PEC-1.1.md`.

**Sin cambios:** todos los archivos de PEC-1.0, con los mismos SHA-256 (`CAMBIOS_PEC-1.1.md`).
