# Cierre de revisión de la candidata v3r2 (D1–D3) — 2026-10-22

- **Alcance:** verificación y revisión. **No se modificó** la entrega v3r2, el repositorio original ni ningún experimento congelado.
- **No se hizo:** ninguna rama, commit, push, PR, merge, deploy ni operación.
- **Encontré dos discrepancias.** Me detuve antes de corregir nada: las correcciones están **propuestas, no aplicadas** (§2).

## 1. Identidad de la candidata (desde una extracción nueva) — `registro/01`, `02`
| Comprobación | Resultado |
|---|---|
| SHA-256 del ZIP | `d912c88a59b878520501ff221fd78d2d2eef870ae0b681d2108441ab8cbd5155`, coincide con lo declarado; 677.262 bytes |
| Archivo de suma externa | `e62a711b…`, coincide; `sha256sum -c` OK |
| Registro externo de reproducción | `fd9ce645…`, coincide |
| Manifiesto interno | 98 de 98 verifican; no sobra ni falta ningún archivo; la extracción es idéntica a la carpeta publicada junto al ZIP |
| Contenido duplicado | 1 par (`S_comparacion_CI_libre.txt` = `S_comparacion_base_vs_completa.txt`). **Explicado:** sus JUnit de origen son distintos (4 hashes distintos) y el comparador imprime solo resultados, que fueron idénticos |
| Parches | 01 `1944f433…`, 02v3 `d5c90091…`, 03 `0be65ea6…`, 04 `8d396356…` y 02 original `32a42a5d…`: los cinco coinciden |

**Sin discrepancias de identidad.**

## 2. Discrepancias encontradas (reportadas; nada modificado)

### D1 — Falso: «02v3 no aplica sin 01». La inseparabilidad no está garantizada técnicamente
- **Dónde:** `PLAN_INTEGRACION_Y_REVERSION.md`, línea 13 («**02v3 no aplica sin 01:** comparten `engine.py`»). La misma frase estaba en el plan de v2.
- **Evidencia** (`evidencia/U1_unidad_y_reversion.txt`, `U2_02v3_sin_01.txt`), con aplicaciones reales sobre clones nuevos y sin commits:
  - 02v3 **aplica** sobre `72ffae5` sin 01 (código 0): sus fragmentos de `engine.py` no se solapan con los de 01;
  - desde 01+02v3+03 se puede revertir **solo 01** (código 0) o **solo 02v3** (código 0).
- **Qué produce 02v3 sin 01:**
  - un motor que registra `engine_version = 1.1.0`, versión definida como «order hygiene D1-D3», pero **sin D1–D3**: 5 operaciones frente a 13 del motor correcto, en el mismo escenario;
  - las **14 pruebas de trazabilidad pasan** igual; solo fallan las 8 de D1–D3, que se van con 01.
  - Una integración o reversión parcial podría pasar la CI con una etiqueta de versión falsa.
  - La huella del motor sí cambia, así que el almacén no mezcla esos resultados con los genuinos de 1.1.0.
- **Lo que sigue siendo cierto:**
  - 01 sin 02v3 reabre R4: el mismo `run_id` para motores distintos;
  - el plan ya recomienda **un solo commit** para 01+02v3 y prohíbe revertir una parte.
  - La inseparabilidad es **procedimental**, no técnica.
- **Corrección propuesta (no aplicada):**
  - (a) *Documental, mínima:* reemplazar la línea 13 por «02v3 aplica técnicamente sin 01 y produce un motor etiquetado 1.1.0 sin D1–D3. La inseparabilidad la garantiza solo integrarlos en **un único commit** y revertirlos juntos».
  - (b) *Guarda técnica, opcional y con revisión aparte:* una prueba en `test_backtest_provenance.py` que exija que un motor que declara 1.1.0 tenga D1–D3 (por ejemplo, el atributo `order_hygiene` después de `run()`). Así 02v3 sin 01 fallaría su propia suite.

### D2 — Atribución no verificada de fallas a R19
- **Dónde:** `MATRIZ_REVISION_PARCHES.md`, línea 57 («… 0 en la integración (salvo R19…)»), y `EVIDENCIA_EJECUCIONES.md`, fila 25 («completa: 0, salvo R19 bajo carga»).
- **Evidencia:** `evidencia/R9_*` de v3r2 muestra 1 falla de la integración en 3 de las 6 horas, **sin el nombre de la prueba**. La atribución a R19 se **infiere** de `R10_*`, donde la única falla nombrada de la integración sí fue la de R19.
- **Corrección propuesta (no aplicada):** decir «1 falla en 3 de 6 horas, sin nombre registrado; atribuida a R19 por inferencia (R10)». El plan R19 exige `-rA` para que no vuelva a pasar.

### Observación O1 (no es una discrepancia)
`COMPARACION_BASE_VS_INTEGRACION.md` rotula una fila «Sin restricciones, como la CI de hoy» sin decir explícitamente «local». El informe §4 sí lo deja claro. Propuesta: agregar «(corrida local)».

## 3. Unidad 01 + 02v3 y reversión independiente de 03 — `evidencia/U1_*`
| Prueba | Resultado |
|---|---|
| 03 aplica sobre la base sin 01 ni 02v3 | Sí (código 0): **03 es independiente** |
| Revertir solo 03 desde 01+02v3+03 | Código 0; el resultado es **idéntico byte a byte** a la obligatoria v3 registrada (01+02v3) |
| Revertir la unidad 01+02v3 (02v3 y después 01) dejando 03 | Código 0; quedan solo los 3 archivos de 03 |
| Revertir solo 01 o solo 02v3 | Posible: **ver D1** |

**Conclusión:**
- 03 se integra y se revierte por separado.
- 01+02v3 es inseparable **por lógica** (R4; etiqueta de versión), **no por git**: hay que imponerlo con un único commit.

## 4. Pruebas locales frente a CI real
- Revisé todas las menciones de CI en los documentos de v3r2 (grep).
- Ninguna afirma que la CI de GitHub esté en verde. El informe §4 separa lo reproducido localmente de lo que solo una corrida real verifica, y A7 figura como **pendiente** en el plan.
- Única mejora de redacción: O1.

## 5. Visibilidad de los riesgos pedidos
| Riesgo | En la matriz | En la lista de pendientes del informe | Marcado como resuelto en algún lado |
|---|---|---|---|
| R15 | Pendiente (no resuelto) | Sí | No |
| R17 | Pendiente (no resuelto) | Sí | No |
| R18 | Pendiente (no resuelto) | Sí | No |
| R19 | Pendiente (no resuelto), severidad media | Sí | No |
| R22 | Pendiente (aceptado) | Sí | No |
| R24 | Pendiente | Sí | No |

## 6. R19
Ver `PLAN_R19.md`: hipótesis H-ENT y H-SINC, instrumento listo y probado, matriz de 12 celdas con 20 repeticiones, criterios fijados antes de correr y comandos.
- **No se amplió el parche 03.** Cualquier parche para R19 irá aparte, con evidencia y revisión propias.
- La prueba de humo (una corrida sin carga) muestra el mecanismo: 146.491 ciclos de fondo y 6,7 s de vaciado de 10 s con el bucle activo, frente a 0 y 0,05 s con el bucle aparcado. **No es una conclusión.**

## 7. Recomendación final
**La integración está lista para pasar a una rama aislada y a revisión humana, con una condición previa:** resolver D1.
- **Mínimo:** que la rama lleve 01+02v3 en **un único commit**, como ya dice el plan, y que el revisor sepa que la unidad no la impone git.
- **Preferible:** corregir la línea falsa del plan (D1a) antes de que nadie dependa de ella.
- El código, las pruebas, los mutantes, la paridad con E1 y la reproducción limpia de v3r2 respaldan los parches. D1 y D2 son errores de documentación, no de código. Sobre D1 hay un riesgo procedimental que el commit único neutraliza.

**Riesgos que bloquean la integración** (fusionar en la rama base):
1. **R7 / A7:** CI real de GitHub en verde, tanto el trabajo python como el frontend. Nunca corrió.
2. **A8:** revisión humana del diff.
3. **D1:** 01+02v3 en un único commit, revertible solo junto.
4. **R19, condicional:** si la primera CI real falla por R19, no se fusiona en rojo. Se compara con la base y se aplica `PLAN_R19.md`.

**No bloquean la integración**, pendientes y documentados: R15, R22, R24, R14, R20, R21, R23, R-M10, D2 y O1.

**Riesgos que bloquean exclusivamente cualquier operación en vivo** (no la integración):

| Riesgo | Por qué importa solo en vivo |
|---|---|
| R3 | `tia.runtime.live` no tiene las capas 2 y 3 de D3, y no hay prueba de equivalencia backtest–vivo |
| R17 | Durante un cierre por parciales, el resto de la posición queda sin stop: es la regla que el vivo aplica igual |
| R18 | Una reversión rechazada no se reintenta: mismo patrón en el vivo por inspección, sin prueba |
| R9 (parte vivo) | Sesión en vivo contra una venue real: no verificada |
| R6 | Tolerancia del nivel de stop distinta en backtest y vivo (muy baja) |
| Puertas no técnicas | No hay validación de rentabilidad; `validada_para_operar` y las autorizaciones operativas no cambian con esta integración |

**Bloquean el uso productivo del almacén de backtests** (despliegue, no integración ni vivo):
- R24: el guardado no se probó contra PostgreSQL;
- R15: solo si alguna vez hay escritores concurrentes.

## 8. Lo que requiere tu decisión o autorización
1. Autorizar una **revisión documental r3** de la candidata con D1a, D2 y O1 corregidos. Es solo documentación: parches, pruebas y hashes de código sin cambios.
2. Decidir si querés la **guarda técnica D1b** como cambio aparte con revisión propia.
3. Autorizar la **ejecución del plan R19**: ≈ 1 h de CPU, sin tocar repositorios.
4. Después, y por separado: crear la rama aislada, el commit único 01+02v3, el commit de 03, el push (dispara la primera CI), el PR y el merge. Detalle en `ACCIONES_QUE_REQUIEREN_AUTORIZACION.md` de v3r2.

## 9. Estado de seguridad — `registro/00` y `99`
- El repositorio original está **idéntico** antes y después: HEAD, índice, refs, reflog, árbol, stash y 0 cambios.
- Los 8 manifiestos de congelados verifican.
- Las entregas anteriores (v1, v2, v3r1 y v3r2) siguen con sus hashes.
- Todo lo de esta revisión ocurrió en clones aislados dentro de `cierre_revision_D1_D3_2026-10-22/`.
