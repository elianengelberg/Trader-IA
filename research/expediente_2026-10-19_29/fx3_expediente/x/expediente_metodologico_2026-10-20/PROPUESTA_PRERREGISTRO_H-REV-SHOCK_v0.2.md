# PROPUESTA DE PRERREGISTRO: H-REV-SHOCK v0.2

> **PROPUESTA NUEVA · PENDIENTE DE APROBACIÓN · NO EJECUTADA · NO CONGELADA**
> - **No** reconstruye el original histórico de H-REV-SHOCK. Ese original (citado como `69758896…`) **no se recuperó**.
> - **No reemplaza** a la v0.1 (`fase_documental_2026-10-20/PROPUESTA_PRERREGISTRO_H-REV-SHOCK_v0.1.md`, SHA-256 `6e3875630f823918ff438743a321ff0d4ecba5469b9f1fe52bbc964342bb8e1f`), que se conserva intacta como registro.
> - Redactada sin mirar precios ni resultados. No autoriza nada.
> - Estadística: `MARCO_ESTADISTICO_VALIDADO.md` (MEC v0.2), **todavía sin calibrar**.

## 0. Cambios respecto de la v0.1

| # | Tipo | Cambio | Motivo |
|---|---|---|---|
| C1 | Técnico | σ_d = **RMS** de los 60 rendimientos previos (media cero), en lugar del desvío alrededor de la media | La v0.1 centraba el numerador en 0 y el denominador en la media. Con 60 días, la media estimada es ruido: su error estándar es ≈ σ/√60 ≈ 0,13σ, mayor que la deriva diaria real |
| C2 | **Conceptual** | En shocks consecutivos, la **referencia de recuperación queda en el cierre previo al PRIMER shock** del grupo; L\* sigue siendo el mínimo acumulado | En la v0.1, cada shock nuevo **bajaba** la meta, y la «reversión» medía solo el último tramo. La v0.2 mide la reversión del movimiento completo. **Cambia la regla operativa, no la hipótesis conceptual** |
| C3 | Técnico | **Fin de la ventana:** liquidación al último cierre válido dentro de ella, con costos | La v0.1 podía leer la apertura del **2026-06-01**, que está en el período reservado de H-CARRY: era un defecto |
| C4 | Técnico | Contabilidad de la manga, exposición y benchmark definidos con fórmulas (MEC §2) | La v0.1 los dejaba en palabras y mezclaba la exposición media con los rendimientos sin una definición matemática |
| C5 | Estadístico | Prueba primaria **bootstrap-t centrado** (MEC §4), α = 0,025 unilateral (Bonferroni). P solo descriptivo | 1 − P no es un valor p calibrado (MEC §1) |
| C6 | Estadístico | El percentil del nulo emparejado **sale del criterio**; el nulo se redefine como descriptivo (MEC §8) | No estaba calibrado, usaba duraciones endógenas y mezclaba regímenes |
| C7 | Estadístico | **Se elimina la compuerta «P < 0,10 en D».** Se usan compuertas de integridad, datos y factibilidad (MEC §9) | Seleccionar por resultados intermedios sesga la familia de hipótesis que llega a E |
| C8 | Estadístico | Categorías nuevas: EN CONTRA y EFECTO RELEVANTE DESCARTADO; N_min = 30 [D-RS-6] | Separar la ausencia de evidencia de la evidencia de ausencia |
| C9 | Procedimiento | F0 especificado (§8): qué lee, qué produce y qué revela | La v0.1 lo mencionaba sin especificarlo |

## 1. Hipótesis (sin cambios conceptuales)
- **H₁:** en BTCUSDT y ETHUSDT spot, una estrategia long/flat que compra tras un shock bajista diario excepcional seguido de agotamiento obtiene un **exceso de timing neto μ > 0** frente a la estática con su misma exposición media (MEC §2–3).
- **H₀:** μ ≤ 0.
- **No es** E1-P2, ni R, ni C10, y no se supone rentable. La evidencia previa sobre reversión incondicional es débil o negativa: la expectativa previa es baja.

## 2. Mercado, activos y temporalidad
- **Mercado:** Binance spot, BTCUSDT y ETHUSDT, cada uno con media manga.
- **Posiciones:** largo o efectivo; sin cortos ni apalancamiento.
- **Velas:** diarias UTC [D-RS-1]. **Horizonte:** de 1 a 10 días.

## 3. Reglas (definición completa, por activo)
- **Día válido:** vela presente, OHLC coherente, precios > 0 y duración de 1 día.
- **r_d** = ln(C_d/C_{d−1}), si d y d − 1 son válidos.

1. **σ_d = √( (1/60)·Σ_{j=1}^{60} r²_{d−j} ).** Exige los 60 rendimientos de los 60 días previos; si falta alguno, no hay señal en d [D-RS-10].
2. **z_d = r_d / σ_d.** **Shock bajista:** z_d ≤ −3,0 [D-RS-2]. Los shocks alcistas (z ≥ +3) solo se cuentan, de forma descriptiva.
3. **Estado REPOSO.** Al cierre de d, si hay shock: pasa a VIGILANCIA con
   - s = d;
   - **REF = C_{d−1}**, el cierre previo al primer shock del grupo;
   - **L\* = L_d**;
   - fin de ventana f = d + 3 [D-RS-3].
4. **VIGILANCIA.** Al cierre de cada d ∈ (s, f]:
   - (i) **Shock nuevo** (z_d ≤ −3): s = d y f = d + 3. **REF no cambia** (C2). L\* = min(L\*, L_d).
   - (ii) **Agotamiento** si L_d ≥ L\* **y** C_d > C_{d−1} [D-RS-4]. Orden: (ii) se evalúa **antes** de actualizar L\* con L_d; por la condición, L\* no cambia. Se fija e = d y se ordena la **compra en O_{e+1}**.
   - (iii) Si no ocurre (i) ni (ii): L\* = min(L\*, L_d). Si d = f, vuelve a REPOSO, sin operación.
5. **Entrada:** compra en O_{e+1} con todo el efectivo de la manga (MEC §2).
   - Si O_{e+1} falta o cae fuera de la ventana: **no hay entrada** y vuelve a REPOSO.
   - Niveles de la posición: REF y L\* tal como estaban en e.
6. **POSICIÓN.** Al cierre de cada d desde el día de entrada, por la primera condición que se cumpla:
   - **C_d ≥ REF** → venta en O_{d+1} (recuperación);
   - **C_d < L\*** → venta en O_{d+1} (invalidación);
   - **d = (día de entrada) + 9** → venta en O_{d+1} (duración máxima de 10 días) [D-RS-5].
   - Si la apertura de venta falta, se vende en la siguiente apertura válida.
   - **Si la venta caería después del último día de la ventana:** liquidación al **último cierre válido** de la ventana, con costos (C3).
7. **En posición, los shocks se ignoran.** Una sola posición por activo y sin piramidar. Tras vender en O_x, el activo pasa a REPOSO y el cierre de x se evalúa normalmente.
8. **Mangas independientes:** el efectivo de una no financia a la otra. El conjunto es el promedio de los excesos diarios (MEC §2).

**Justificación de los parámetros** (conceptual; ninguno elegido con datos):
- **60 días:** unos 2 meses. El error relativo del RMS con 60 observaciones es ≈ 9 %.
- **z ≤ −3:** convención de «evento de 3 sigma». **No hay datos permitidos que justifiquen otro valor.** Si F0 mostrara muy pocos eventos, cambiar el umbral sería una **v0.3 declarada**, nunca un ajuste silencioso.
- **3 días, agotamiento con dos condiciones y 10 días:** igual que en la v0.1. Son heurísticas simples y no un mecanismo identificado. Se declara.

## 4. Datos
- **D y E:** los archivos 1d ya verificados de T (manifiestos `5a0805a7e22797637c400a1e939ec6c2d10e0cdc26410566f212708211b6367b` y `3998305bb38909a08a94f6365317695f930dea4ea10933b19a22e17b40998f6a`; 0 días faltantes). **Sin descarga.**
- **P:** archivos diarios oficiales prospectivos. Requiere autorización de descarga y una ubicación fuera del repositorio [A-RS-4].
- **Período INVÁLIDO** si falta un archivo mensual sin complemento, si hay más del 0,5 % de días inválidos o si falla un checksum. **Sin relleno.**

## 5. Períodos y contaminación
| Fase | Ventana | Uso |
|---|---|---|
| D | 2017-10-17 → 2021-12-31 | Verificar la implementación con datos reales y describir la frecuencia. **No cambia ningún parámetro.** Sin compuerta por resultado |
| E | 2022-01-01 → 2026-05-31 | **Uso único**, con candado. Categoría según MEC §7 |
| P | Historia desde el 2026-10-14; primer día con señal posible el **2026-12-14** (requiere 60 rendimientos) [D-RS-8] | Prueba secuencial (MEC §7.1) |

- **E está contaminado:** quien diseña conoce 2022–2026, y T y E1 usaron esos datos. **No es una validación independiente.**
- **D tampoco es ciego:** se conoce la existencia de las caídas de 2018, 2020-03 y 2021-05.

## 6. Costos y ejecución
- **Costos:** 10 pb de comisión + 5 pb de slippage por lado; ida y vuelta, 30 pb.
- **Ejecución:** a la apertura siguiente al cierre de decisión.
- **Estrés** (descriptivo): costos ×2 y ×3; un día extra de retraso.
- **Advertencia:** el spread en los días de shock puede ser mucho mayor que 5 pb, justo cuando esta estrategia opera. El estrés ×3 puede quedarse corto.

## 7. Métricas y decisión
- **Primaria:** μ̂ = media diaria del exceso conjunto (MEC §2), anualizada × 365 solo para informarla.
- **Prueba:** bootstrap-t, ℓ = 20 días, B = 9999, semilla 20261101, p unilateral, α = 0,025 (MEC §4 y §6).
- **Categorías:** INVÁLIDO, INCONCLUSO POR DATOS (N < 30), RESPALDADA EN E, EN CONTRA, EFECTO RELEVANTE DESCARTADO o INSUFICIENTE (MEC §7).
- **Descriptivas:**
  - por activo; número de shocks bajistas y alcistas;
  - shocks con agotamiento;
  - operaciones y sus motivos de salida;
  - retorno neto por operación con su IC;
  - P (probabilidad bootstrap);
  - nulo emparejado (MEC §8);
  - costos ×2 y ×3, retraso;
  - subperíodos;
  - buy and hold y efectivo.

## 8. F0: conteo de factibilidad (solo con autorización expresa, A-RS-1)
- **Qué lee:** solo las velas 1d de BTCUSDT y ETHUSDT de **D** (2017-08-17 → 2021-12-31), ya en disco. **No lee E.**
- **Qué calcula:** la máquina de estados §3.1–3.4 hasta la **señal de entrada**. **No** simula posiciones, salidas ni P&L, y no mira ningún precio posterior a e + 1.
- **Qué produce:** por activo y por año, solo números:
  - shocks bajistas;
  - grupos de shocks;
  - agotamientos (entradas potenciales);
  - shocks alcistas.
  - **Sin fechas**, para revelar lo mínimo.
- **Qué revela:**
  - la frecuencia de eventos en 2017–2021, y por lo tanto una proyección de N en E;
  - nada sobre el rendimiento posterior. Sí revela que los eventos se agrupan en años conocidos, algo que el diseñador ya sabe.
- **Uso:** compuerta de factibilidad.
  - Si la proyección de N en E es < 30, **no se ejecuta E** (sería INCONCLUSO casi seguro). La hipótesis queda «no evaluable con datos de BTC y ETH».
  - Cambiar el umbral para conseguir más eventos sería una **v0.3 declarada**, con la advertencia de que se eligió con conteos de D.

## 9. Potencia (aritmética con supuestos, sin datos) [Hip]
- **Efecto mínimo detectable por operación** (80 %, α = 0,025): δ_op ≈ 2,8016·s_op/√N.
- **Supuesto de s_op:** con un desvío diario del 4 % y unos 10 días, s_op ≈ 12,6 %.
  - N = 30 → δ_op ≈ 6,4 % por operación;
  - N = 50 → 5,0 %;
  - N = 100 → 3,5 %.
- **Lectura:** con pocos eventos, E solo podría detectar reversiones **muy grandes**. Lo esperable, aunque haya efecto, es INSUFICIENTE.
- **Prospectivamente:** a unas pocas operaciones por año entre los dos activos [Hip, a confirmar con F0], confirmar un efecto moderado llevaría **décadas**.
  - Es una limitación estructural de usar solo BTC y ETH.
  - Ampliar a más activos sería **otro experimento** (decisión D-G3), no un ajuste.

## 10. Controles, auditoría y reproducción
- **Pruebas sintéticas (Etapa B):** las de `PLAN_DE_EVIDENCIA_SUFFICIENTE.md`, con sus criterios. Incluyen:
  - truncamiento;
  - máquina de estados con shocks consecutivos (verificar que REF no cambia);
  - aperturas faltantes;
  - liquidación al final de la ventana;
  - contabilidad de la manga;
  - control positivo y control negativo.
- **Congelado:** el texto aprobado y el código se congelan con hash **antes** de leer D. E tiene candado de uso único. Registros de solo añadidos, **fuera del repositorio**. Detalle en `PLAN_DE_AUDITORIA_Y_REPRODUCCION.md`.
- **Revisión independiente por otro modelo:** **no realizada**.

## 11. Decisiones pendientes (además de MEC D-S*)
| ID | Decisión | Recomendación |
|---|---|---|
| D-RS-1 | Temporalidad diaria | Aprobar |
| D-RS-2 | z ≤ −3 con σ RMS de 60 días | Aprobar (convencional) |
| D-RS-3 | Ventana de 3 días que se reinicia con cada shock | Aprobar |
| D-RS-4 | Agotamiento = sin mínimo nuevo + cierre de giro | Aprobar (heurística declarada) |
| D-RS-5 | Duración máxima de 10 días | Aprobar |
| D-RS-6 | N_min = 30 | Aprobar o fijar otro **antes** de F0 |
| D-RS-8 | Historia de P desde el 2026-10-14 | Aprobar (evita el período reservado) |
| D-RS-10 | Exigir los 60 rendimientos completos | Aprobar (no hay huecos en D ni en E) |
| D-RS-C2 | REF fija en el primer shock del grupo (cambio conceptual) | Aprobar o volver a la regla de la v0.1 |
| A-RS-1 | Autorizar F0 | Tu decisión |
