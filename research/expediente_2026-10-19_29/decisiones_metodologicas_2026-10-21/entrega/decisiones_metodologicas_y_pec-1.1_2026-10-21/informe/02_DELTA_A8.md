# 02 — δ (A8 / D-S4): qué es, cómo entra, alternativas y la decisión exacta que te toca

**Resultado de esta fase:** **δ no está determinado por ningún documento** y no lo fijo. Dejo:
- su definición exacta, con un defecto de unidades corregido en PEC-1.1;
- un marco de justificación económica;
- tres alternativas con sus consecuencias calculadas;
- el texto exacto de la decisión, para que la tomes vos.

Hasta que la tomes, PEC-1.1 deja δ en `null` y **la fase prospectiva sigue sin poder congelarse**.

## 1. Qué representa δ
δ es el **exceso aritmético anual neto mínimo que justificaría operar una estrategia.** La comparación es contra el
benchmark de exposición equivalente (MEC §2), con los costos modelados ya descontados. Si la ventaja real es menor que
δ, no vale la pena aunque exista.
- **Unidad:** fracción anual (0,05 = 5 %/año).
- **Variable:** la media μ del exceso diario x_d. En la escala diaria del estadístico, **δ_d = δ / 365,25** (365,25
  días por año; el mercado opera todos los días y es la convención de los tamaños calibrados).
- **Hipótesis que pretende detectar o descartar** (MEC §3):
  - relevancia: H₀ μ ≥ δ frente a H₁ μ < δ, que da «efecto relevante descartado»;
  - en la potencia, la alternativa de diseño es μ = δ.
- **No es el efecto esperado.** Es el menor efecto que te importaría. Elegirlo cerca de lo que una estrategia «parece
  dar», o para acortar n_max, es exactamente el sesgo que hay que evitar.

## 2. Dónde entra en el cálculo
| Uso | Fórmula | Código |
|---|---|---|
| Efecto relevante descartado (histórico y prospectivo) | IC90 superior (envolvente de la regla decisiva, escala diaria) < δ_d | `decision.categoria_historica`, `decision.mirada_prospectiva`; en PEC-1.1, `pec/prospectiva.py` |
| Tamaño máximo prospectivo | n_max = ⌈365,25 · R · (2,8016 · TE / δ)²⌉, con R = 1,0247 (5 miradas OBF) | `pec.potencia`, `pec.secuencial.inflacion` |
| Futilidad (no vinculante) | IC90 superior < δ_d en cualquier mirada | ídem |
| Control positivo (B11) | efecto plantado μ = δ y 2δ | Plan de evidencia §B11 |

**Defecto encontrado (PEC-1.0):** el prerregistro guarda `delta_anual`, pero `categoria_historica` y
`mirada_prospectiva` comparan δ **sin conversión** con un IC90 de la **media diaria**.
- Si alguien pasara 0,05 tal cual, cualquier IC diario quedaría por debajo, y se declararía «efecto relevante
  descartado» casi siempre.
- No hubo consecuencias: ninguna evaluación usó δ.
- **PEC-1.1** introduce `delta_diario(delta_anual)` y lo exige en las funciones nuevas. Las de PEC-1.0 no se modifican
  (no hay cambios retroactivos).

## 3. ¿Lo determinan los documentos existentes? No
- **Matriz de decisiones del expediente metodológico (D-S4):** propone «3 %, 5 % o 10 %/año» y dice «No lo decido yo:
  es económico».
- **r1 (`02_EXPEDIENTE_DECISIONES.md`, `AS1_CALIBRACION_Y_A8_DELTA.md`):** categoría C, «tu decisión económica».
- **Búsqueda en el expediente, r1, las propuestas v0.2 y la documentación del repositorio:** no hay ninguna declaración
  tuya de un umbral.
  - El único δ numérico del repositorio (5 pb por operación en `docs/PAPER_REALTIME_12H_FORENSIC_AUDIT.md`) es de otra
    estrategia (creación de mercado) y otra escala (por operación). No aplica.
- **El único dato de capital del proyecto** es «capital supuesto de 10 000 USDT» (MEC §2). Está puesto para razonar
  sobre lotes mínimos, no como capital real.

## 4. Marco de justificación propuesto (económico, fijado antes de ver datos)
**δ = (F/K + π) / (1 − d)**

| Término | Qué es | Quién lo aporta | Referencia |
|---|---|---|---|
| F | Costo fijo anual de operar la estrategia: datos, infraestructura y tiempo valorizado | **Vos (dato)** | — |
| K | Capital que asignarías | **Vos (dato)** | El proyecto solo tiene el supuesto de 10 000 USDT |
| π | Prima mínima por riesgo de modelo: que la regla deje de funcionar sin aviso | **Vos (preferencia)** | 2–3 %/año es una prima modesta |
| d | Deterioro esperado entre la confirmación y la operación | Conocimiento previo | 25–50 %. McLean y Pontiff (2016): los rendimientos de anomalías publicadas caen ≈ 26 % fuera de muestra y ≈ 58 % tras publicarse. Además, una confirmación temprana sobreestima el efecto (maldición del ganador) |

**Por qué este marco:**
- Usa solo magnitudes económicas, no la potencia.
- Hace explícito que δ depende del capital: el mismo costo fijo pesa diez veces más con 10 000 que con 100 000.
- **Conocimiento previo del programa:** 39 hipótesis, 18 con resultado, **ninguna respaldada**. Para las familias
  exploradas, el IR plausible es de 0,3 a 0,5 (r1 §5).
  - Esto **no** se usa para elegir δ: el δ económico no depende de lo que parezca alcanzable.
  - Sí anticipa la consecuencia: una ventaja típica de esas familias (IR 0,35 con TE 20 % da ≈ 7 %/año) quedaría por
    debajo de un δ alto o sería indetectable con uno bajo.

## 5. Alternativas y consecuencias
**Alternativas:**
| Alternativa | δ | Cuándo se justifica (con el marco) |
|---|---|---|
| A | 5 %/año | Capital grande o costos fijos despreciables (F/K ≈ 0), π = 2,5 % y d = 50 % |
| B | 10 %/año | F/K ≈ 2,5 % (por ejemplo, 250 USDT/año con K = 10 000), π = 2,5 % y d = 50 % |
| C | 15 %/año | F/K ≈ 5 % (500 USDT/año con K = 10 000), π = 2,5 % y d = 50 % |
| (3 %/año) | — | Solo con capital muy grande y sin prima de modelo. **Desaconsejado:** hace la confirmación inalcanzable con cualquier TE realista |

**Consecuencias.** `evidencia/F2_consecuencias_delta.json`, con la aritmética de r1 y la potencia analítica de la prueba
z; la potencia real con la regla decisiva está en la sección 6.

| δ \ TE | 5 % | 10 % | 15 % | 20 % |
|---|---|---|---|---|
| 3 % | 22 años | 89 | 201 | 357 |
| 5 % (A) | 8,0 | 32 | 72 | 129 |
| 10 % (B) | 2,0 | 8,0 | 18 | 32 |
| 15 % (C) | 0,9 | **3,6** | 8,0 | 14 |
| 20 % | 0,5 | 2,0 | **4,5** | 8,0 |

En negrita, los n_max dentro del rango calibrado por SEC-1.0 (1096 a 1826 días).

**Lectura:**
1. **n_max no depende de δ, sino de δ/TE.** Para que la confirmación prospectiva sea alcanzable en 3 a 5 años (el rango
   calibrado), la hipótesis necesita un IR de diseño δ/TE entre ≈ 1,27 y 1,64.
   - Con A haría falta un TE de 3–4 %; con B, de 6–8 %; con C, de 9–12 %.
   - Con un TE como el de T (≈ 20 %), ningún δ ≤ 20 % entra.
2. **Si n_max supera 1826 días:** PEC-1.1 lo declara de antemano «confirmación prospectiva no alcanzable en el rango
   calibrado» (MEC §7.1). **No se relaja α** y no se agranda δ para entrar.
3. **Si n_max es menor que 1096 días** (δ/TE > 1,64): también queda fuera del rango calibrado, y requiere una calibración
   nueva para n_max corto.
4. **Un δ más alto acorta n_max y facilita «efecto relevante descartado»**, pero descarta ventajas que podrían valer la
   pena. Uno más bajo hace casi todo inalcanzable. Por eso la elección tiene que ser económica.

## 6. Potencia real con la regla decisiva (SEC-1.0)
La tabla del §5 usa la aritmética de la prueba z. SEC-1.0 simuló la regla decisiva real (máx de tres valores p, 5
miradas OBF) en los dos puntos de diseño de la criba. Con el n_max de la fórmula, la potencia real es **75–80 %** en lugar
de 80 % (`03_SECUENCIAL_SEC-1.0.md` §4).
- C1 (colas t₃): 75–76 %.
- C2 (GARCH): ≈ 80 %.
- C5 (intradía): 76–77 %.

**Consecuencia para δ:** ninguna en la elección, que es económica. Al leer la tabla del §5 hay que suponer ≈ 5 puntos
menos de potencia.

**Para hipótesis dispersas (tipo C4):** la regla es muy conservadora, con un error real de ≈ 1 % frente al 2,5 %. Su
potencia será menor que la de la tabla, y no se simuló.

## 7. Recomendación técnica (no es la decisión)
1. **Un δ único para todo el programa,** fijado una vez y congelado en cada prerregistro posterior. Uno por hipótesis
   abre la puerta a ajustarlo a cada estrategia.
2. **Calcularlo con el marco del §4, con tus K y F reales.** Si no tenés esas cifras, la alternativa más coherente con
   el único capital del proyecto (10 000 USDT) y un costo fijo modesto es **B (10 %/año)**.
   - Es una propuesta. No la aplico en ningún lado, y fijarla **no habilita** la fase prospectiva: siguen faltando
     D-G1, B-4, D-G4, R-5 y un prerregistro PEC-1.1 válido.

## 8. Decisión exacta que te corresponde (texto para que lo completes vos)
> **Decisión A8 / D-S4.** Fijo δ = ___ % anual de exceso aritmético neto, después de los costos modelados en el MEC §2,
> de la cartera de mangas frente al benchmark de exposición equivalente.
> - Rige para **[todo el programa | la hipótesis ___]** desde el ___ (UTC).
> - Base: K = ___, F = ___/año, π = ___ %, d = ___ %.
> - Lo fijo sin haber visto datos nuevos de ninguna hipótesis que vaya a usarlo.
> - Firmado: ___ (propietario).

No completo ni firmo este texto en tu nombre.
