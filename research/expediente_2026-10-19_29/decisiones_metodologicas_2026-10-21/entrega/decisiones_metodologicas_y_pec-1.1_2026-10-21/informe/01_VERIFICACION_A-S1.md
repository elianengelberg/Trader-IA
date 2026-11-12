# 01 — Verificación de A-S1 desde una extracción limpia

**ZIP:** `CALIBRACION_AS1_PEC-1.0_2026-10-21.zip`, SHA-256
`37af592c865dd0379d71fad2f6b52033c019e13b20920557867c6d93548f64e6`.
- Se encontró en el scratchpad y su **hash completo coincide**.
- No se reconstruyó ni se modificó nada: se extrajo en una carpeta nueva (`f1/a_s1/`), junto con r1 (`f1/r1/`, 80
  archivos OK).

**Clases de cada afirmación:**
- **[R] reproducido:** recalculado en esta fase con código nuevo o con una reejecución completa.
- **[I] inspeccionado:** leído en el código o en los archivos, sin recalcular.
- **[D] declarado:** consta solo en un registro o informe y no se puede comprobar desde aquí.

## 1. Integridad
| Comprobación | Resultado | Clase |
|---|---|---|
| SHA-256 completo del ZIP | Coincide | R |
| `unzip -t` | Sin errores | R |
| `sha256sum -c SHA256SUMS.txt` | 70 / 70 OK | R |
| Archivos en disco frente al manifiesto | 70 = 70; ninguno de más ni de menos; ninguna entrada no regular | R |

## 2. Correspondencia entre código, parámetros, semilla, datos crudos y resultados
`codigo/f1/recuento_a_s1.py` (escrito para esta fase; no reutiliza el verificador de A-S1):

| Comprobación | Resultado | Clase |
|---|---|---|
| 15 hashes de código registrados en `ejecuciones.jsonl` = `SHA256SUMS.txt` de r1 = archivos reales | 15 / 15 | R |
| Orquestador empaquetado = el registrado; salida empaquetada = la registrada (`76a99c6b…`) | Sí | R |
| Parámetros `28764d31…`: semilla 20261103, B = 1999, 2000 réplicas, procesos C1–C6, n ∈ {1612, 366, 731, 1096}; iguales en parámetros, celdas y resultado | Sí | R |
| Réplicas | **96 000** = 48 celdas × 2000 | R |
| Por regla | **24 celdas y 48 comprobaciones**. Primaria: 33 de 48 cumplen. Respaldo: 48 de 48 | R |
| Forma de los p | Primaria: p·2000 es entero (p = (1 + c)/(B + 1)); todos en (0, 1] | R |
| Cada fila del resultado frente al recuento desde los p crudos | 48 / 48 idénticas | R |
| **Reejecución completa de las 96 000 réplicas** desde extracciones nuevas de r1 y A-S1, con Python 3.11.17 (16:57–17:45 UTC) | `resultado_calibracion.json` y **las 48 celdas, idénticos byte a byte**; `verificacion.json` regenerado idéntico; 0 fallas (`evidencia/F1_reejecucion_completa.txt`) | R |
| Lecturas descriptivas de A-S1 (`descriptivo_posterior.json`, `multiplicidad_previa.json`) regeneradas desde la extracción | Idénticas byte a byte | R |

## 3. Definiciones exactas (del código r1, `pec/sintetico.py` `7b15c677…` y `pec/inferencia.py` `99d0d3e6…`) [I]
**Procesos.** Cada serie usa `random.Random("{proceso}-{n}-{semilla}")`.
- Después se **reescala** por su desvío muestral a σ = 1 %, **sin centrar**.
- T es invariante a la escala, y la media poblacional es 0 bajo H₀.

| Proceso | Definición exacta |
|---|---|
| C1 | t₃ i.i.d., reescalada a varianza 1 antes del reescalado final: z/√(χ²₃/3)·√(1/3) |
| C2 | GARCH(1,1): h = 0,05 + 0,10·e² + 0,85·h; e = √h·t₄; 500 de calentamiento |
| C3 | AR(1): v = 0,2·v + t₃; 200 de calentamiento |
| C4 | Exposición de Markov: se enciende con p = 0,005/día y se apaga con p = 1/6. x = (w − w̄)·r, con r = **C2 con semilla + 1 y σ = 1**. Si no hay ningún evento, la serie es 0 y la réplica es degenerada |
| C5 | K ~ Poisson(0,6) operaciones por día; x_d = Σ 0,015·t₄ |
| C6 | N(0,1) con varianza ×3 en un tercio contiguo, con inicio uniforme |

**Métricas.**
- **Por réplica:** `_replica` devuelve p:
  - primaria: `bootstrap_t(x, 20, B, semilla + r)`;
  - respaldo: `respaldo(x, B, semilla + r)` = máx de bootstrap-t ℓ = 20, bootstrap-t ℓ = 40 y Newey–West L = 20, con
    p = 1 − Φ(z);
  - una serie degenerada da p = 1.
- **Tasa por celda:** #{p ≤ α} / 2000, con α ∈ {0,025; 0,05}, comparando en coma flotante con `float(α)`. Las
  degeneradas cuentan como no rechazo.
- **Cumple:** tasa ≤ límite superior de la banda (0,032 o 0,0597). El sub-rechazo solo se informa.

## 4. Hallazgos
**F1-1. Las celdas de A-S1 no son independientes** [R, `evidencia/F1_dependencia_entre_celdas.json`]:
- **C4, réplica r, usa como rendimientos la serie exacta de C2, réplica r + 1,** con el mismo n (cociente constante 100).
- **La semilla del bootstrap es `random.Random(20261103 + r)` en los 6 procesos,** y la misma para ℓ = 20 y ℓ = 40.
  Los inicios de bloque son idénticos entre procesos con el mismo n.
- **Efecto:**
  - las estimaciones por celda **no cambian**, ni el veredicto, que se toma por celda;
  - la cifra de multiplicidad previa (≈ 62 %) suponía celdas independientes («las semillas son distintas por celda»).
    Esa frase es **inexacta para el bootstrap**, y el 62 % es solo una aproximación;
  - SEC-1.0 usa Bonferroni, que es válido con cualquier dependencia.

**F1-2. La reproducibilidad exacta depende del intérprete** [R, `evidencia/F1_python313_muestra.json`]:
- Con Python 3.13.16, de 4800 réplicas (100 por celda), **603 dan un p distinto en los últimos bits**: como mucho
  3,4·10⁻¹⁴ en términos relativos, siempre del componente Newey–West.
- **Ninguna decisión cambia** al 2,5 % ni al 5 %.
- La causa probable es que Python 3.12 cambió `sum()` de floats a suma compensada.
- **Consecuencia:** «idéntico byte a byte» vale con el intérprete registrado (3.11.17). Con otros, la reproducción es
  numéricamente equivalente.

**F1-3. N-6 sigue presente** [I]: el docstring de `sintetico.proceso` dice «centradas exactamente»; el código no centra.
Es solo documental.

## 5. Alcance real de la prueba de determinismo y de la verificación «independiente»
| Lo que A-S1 llamó… | Lo que realmente muestra | Lo que no muestra |
|---|---|---|
| «Recuento independiente» (`verificar_calibracion.py`) | Que la agregación del `main()` congelado coincide con un recuento hecho por otro camino de código | Independencia de autor, entorno o datos: mismo autor, misma sesión, misma máquina y el mismo código r1 para generar los datos |
| Equivalencia secuencial frente a paralelo | 96 réplicas (semilla 1, B = 199) idénticas; prueba de extremo a extremo byte a byte con una configuración reducida | Nada sobre la corrección estadística del código |
| 96 réplicas recalculadas | Determinismo de esas 96 en otro proceso | El 99,9 % restante (lo cubre ahora la reejecución completa) |
| **Esta fase** | Reejecución completa de 96 000 réplicas con 3.11 y una muestra con 3.13 | Otra persona, otra plataforma u otra implementación independiente |

**Conclusión:** A-S1 es **reproducible y determinista en este entorno**. No hay verificación independiente en sentido
estricto: el autor, la máquina y la cadena de confianza son los mismos. La corrección estadística del código se apoya en
las 72 pruebas de r1 y en el contraste con E3, no en la calibración.

## 6. Afirmaciones de `00_RESUMEN_CALIBRACION.md`
| Afirmación | Clase | Nota |
|---|---|---|
| Código r1 `a8056ced…` y parámetros `28764d31…` | R | §2 |
| 96 000 réplicas; 33 de 48 y 48 de 48; tablas por celda | R | §2 y la tabla regenerada |
| Holm: 7 en C4; 10 sub-rechazos; lectura posterior 2,86 % / 2,30 % | R | Regenerado e idéntico |
| «El `main()` congelado escribió el resultado» | R | La reejecución produce los mismos bytes por el mismo camino |
| «Una sola ejecución, 16:15:23–16:46:25, sin reanudaciones» | D | Consta en `ejecuciones.jsonl` y en `progreso.log`, que son registros locales |
| «Fijado por SHA-256 antes de ejecutar, 16:15:17» | D | Los hashes coinciden (R), pero el **orden temporal** depende de registros locales sin ancla externa (R-5 pendiente). Lo mismo vale para SEC-1.0 |
| «Ninguna evaluación pasada cambia (E3-H1 a E3-H3 NO_EVALUABLE)» | D | Coincide con el registro del programa de r1, que es una transcripción |
| «Una prueba perfecta incumpliría con ≈ 62 %» | R con reservas | El cálculo se reproduce, pero supone independencia (F1-1) |
| «La decisión no depende de ese defecto» | R | La primaria falla también con Holm (C4: p ≈ 10⁻¹⁹) |

**La decisión vinculante de A-S1 se sostiene:** la prueba primaria no queda validada y la regla de respaldo, sí.
