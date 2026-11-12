# Informe de decisión — cierre de D1/D2, guarda de versión y R19 (2026-10-22)

- **Qué es:** una revisión de ingeniería. **No** es una validación de rentabilidad ni una autorización para operar.
- **Lo que no se hizo:** ninguna rama en el repositorio original, ningún commit, push, PR, merge ni deploy, ningún trading real. `validada_para_operar` no se tocó.
- **Dónde se trabajó:** todo en copias aisladas bajo `cierre_D1_D2_R19_2026-10-22/`.
- **Repositorio original y congelados:** idénticos al inicio y al final (`registro/00` y `99`).

## Resumen
| Fase | Resultado |
|---|---|
| 1. Corrección documental | **Hecha.** Revisión **v3r3** con las correcciones D1, D2 y «local, no CI». Parches, pruebas, entornos y evidencia de r2 sin cambios, byte a byte. Reproducción completa desde una extracción limpia: **código 0, «TERMINADA SIN DIFERENCIAS»**, 0 líneas MAL |
| 2. Guarda de versión | **Propuesta como parche 05 independiente, no integrada.** Pasa con 01+02v3 (7/7), falla con 02v3 sin 01 (5 de 5 pruebas de comportamiento) y detecta 9 de 9 mutantes de protección, más 2 de evasión. Falsos positivos: **0 de 300** corridas del motor correcto (20 semillas × 3 conjuntos de datos × 5 escenarios) |
| 3. R19 | **Detenida antes de ejecutar.** El criterio H-SINC del plan no distingue las hipótesis (validación sintética). Propongo una corrección, la enmienda 1, validada y congelada. **Sin resultados nuevos de R19** |
| 4. Decisión | Integración lista para una rama aislada y revisión humana, con las mismas condiciones que antes, en un único commit 01+02v3. Detalle en §5 y §6 |

## 1. Cambios documentales y hashes (fase 1)
- **Origen:** extracción nueva de `entrega_integracion_D1_D3_v3r2_2026-10-22.zip` (`d912c88a…5cbd5155`), con suma externa OK y 98 de 98 sumas internas.
- **r2 no se tocó:** sus hashes son iguales al final (`registro/01` y `99`).
- **Nueva revisión:** `entrega_integracion_D1_D3_v3r3_2026-10-22.zip`, SHA-256 `25902649d6d0789598870769670f2e7a5c707f1856e1e1538bd4f74d37877c4a`, 705.169 bytes, 104 entradas en `SHA256SUMS`. Suma externa en `.zip.sha256`.

| Corrección | Qué dice ahora | Dónde |
|---|---|---|
| D1 | «**01 y 02v3 son técnicamente separables, pero deben integrarse y revertirse juntos mediante un único commit, porque 02v3 sin 01 puede declarar una versión de motor incorrecta.**» El plan agrega una comprobación de que el commit contiene exactamente los 8 archivos. Nuevo riesgo **R4c** | Plan, informe, LEEME, acciones, matriz de riesgos, comandos |
| D2 | Un documento nuevo separa **hechos** (H1–H10) de **inferencias** (I1–I4). «0 fallas, salvo R19 bajo carga» pasa a «la completa tuvo 1 falla en 3 de las 6 horas, sin nombre registrado (hecho); se atribuye a R19 por inferencia». Una falla futura es «compatible con R19», no «R19» | `FALLAS_INTERMITENTES_HECHOS_E_INFERENCIAS.md`, matriz de parches, evidencia, informe, riesgos, plan §4 |
| Local frente a CI | «Sin restricciones, como la CI de hoy» pasa a «**reproducción local; GitHub Actions todavía no se ejecutó**». La misma aclaración en las filas «como la CI» de la evidencia | Comparación, evidencia, informe §1 |

- **Diferencias exactas:** `fase1/CAMBIOS_r3_v3r2_a_v3r3.diff`.
  - 15 archivos: 10 modificados (9 `.md` y `reproducir.sh`) y 5 nuevos (`FALLAS_…md`, `CAMBIOS_REVISION_r3.md`, `U1_*`, `U2_*` y `sonda_version.py`).
  - Byte a byte iguales a r2: `parches/`, `pruebas/`, `entorno/`, `registro/`, las 51 evidencias y las 12 herramientas.
- **Reproducción limpia:** `fase1/VERIFICACION_EXTRACCION_LIMPIA_v3r3.txt`, con `env -i` y solo las variables de red: **código 0**. Resultados:
  - suites locales: base 1956/1956, obligatoria 1978/1978, completa 1978/1978, sin regresiones;
  - D1–D3 contra el original: 8/8 fallan; integradas, 8/8 pasan; trazabilidad 14/14;
  - mutantes D1–D3: 10, ninguno vivo; trazabilidad: 0 vivos;
  - el resto: ruff, alembic, parche 04, reloj a 5 horas, persistencia 3/3 y paridad con E1 (mismas huellas).
  - **Paso nuevo 4b** (verifica D1 desde la extracción): 02v3 aplica sin 01; declara 1.1.0 sin D1–D3; sus 14 pruebas de trazabilidad pasan igual; git permite revertir cada parche por separado; la lista de 8 archivos del commit único es exacta.

## 2. La guarda (fase 2), sin integrar
Detalle en `fase2/JUSTIFICACION_GUARDA_VERSION.md`.

- **Qué es:** un archivo de prueba nuevo, `tests/integration/test_engine_version_contract.py`, en el parche `05_propuesta_guarda_version_motor.patch` (`9fc829ad…ceb8ba47`). Aplica sobre la base, sobre 02v3 solo, sobre 01+02v3 y sobre la completa.
- **Cómo evita ser circular:**
  - lee la versión **solo** para saber si hay promesa;
  - todo lo demás lo observa en la venue (un proveedor de papel que solo registra);
  - no usa `order_hygiene`, el estado privado, la huella, `resting_orders()` ni conteos de operaciones.

| Requisito de la misión | Resultado |
|---|---|
| Falla con 02v3 sin 01 | **Sí:** 5 de 5 pruebas de comportamiento fallan (D1, D2, D3 en el cierre, D3 red de seguridad, todo junto) |
| Pasa con 01+02v3 | **Sí:** 7 de 7. También con 01+02v3 declarando 1.2.0 |
| Detecta mutantes que quitan protecciones | **M1–M6 y M8–M10: 9 de 9 detectados.** M7, que quita el aviso del informe, queda fuera de alcance: no es una regla de la venue y la cubre la prueba de 01 |
| No es circular | Dos mutantes de evasión: 02v3 sin 01 **con** contadores `order_hygiene` falsos, o **con** `resting_orders()`. **Los dos fallan** |
| No depende de un número de operaciones | Ninguna aserción compara cantidades de operaciones. Los límites salen del mecanismo: 6 o 7 barras medidas frente a 9; 0 barras sin cobertura frente a 1 |
| Etiqueta | Sin versión, o < 1.1.0: se omite. ≥ 1.1.0: se exige. Ilegible («1.1.0-dev»): falla (falla cerrado) |
| Falsos positivos | **Medidos: 0 de 300** en el motor correcto, con otras semillas (1–20) y otros datos (BTC 1h, BTC 1m, ETH 1m). Determinista (3 repeticiones idénticas). Pasa también sin versiones fijadas. **Por diseño:** falla, ruidosamente, si cambia el contrato de venue (cierres que no sean de mercado reduce-only), con etiquetas de pre-lanzamiento o si se deja de construir la venue por ese nombre. Detalle en `JUSTIFICACION_GUARDA_VERSION.md` §5 |
| Potencia | Con 02v3 sin 01, la guarda falla en 30 de 30 casos (datos × semilla) |
| Sin interferencias | Suite completa local con 05 sobre la completa: **1985/1985**, sin regresiones (las 1978 más 7). Ruff limpio |

**Recomendación sobre la guarda:**
- integrarla como **commit aparte justo después del commit único 01+02v3**, con revisión propia;
- con ella, una integración o reversión que deje 02v3 sin 01 pone la CI en rojo;
- no protege contra revertir solo 02v3 (R4) ni contra borrar la guarda;
- **no reemplaza** el commit único.

## 3. R19 (fase 3): resultados completos y límites
Detalle en `fase3/R19_RESULTADOS_Y_LIMITES.md` y `fase3/PLAN_R19_ENMIENDA_1.md`.

- **Precondiciones verificadas y registradas** (`registro/03`):
  - árboles aislados;
  - prueba y ayudantes idénticos por AST;
  - `live.py` idéntico;
  - hashes del código y de las herramientas;
  - sin red (`unshare -n`);
  - sin credenciales;
  - solo papel y SQLite temporal.
- **Detenida antes de ejecutar.**
  - La validación sintética del instrumento mostró que con el bucle de fondo activo la foto de escrituras pendientes puede tener miles de reconciliaciones del propio bucle que **drenan bien**: 1.916, el 99,5 % del bucle, y la cola avanzaba.
  - El criterio del plan («alguna no termina en 120 s» → H-SINC) habría llamado H-SINC a un caso H-ENT.
- **Corrección propuesta (enmienda 1):**
  - «trabada» pasa a significar que **la cola no avanza**, con el productor detenido;
  - los errores inyectados se separan de los no inyectados;
  - la espera extra se hace solo cuando la pide `settle()`, para no alterar resultados;
  - se agrega el resultado «NO REPRODUCIDO» y una medida continua;
  - el orden de las corridas es aleatorio e intercalado;
  - las corridas se aíslan de la red;
  - (b), los errores de FK y la comparación de árboles quedan definidos.
- **Validación:** cada camino se clasificó bien con pruebas sintéticas, y la mecánica del driver funcionó.
- **Límites:** **no hay resultados nuevos de R19.** Lo único que se sabe sigue siendo lo de v3r2, como hechos más inferencias (D2). No se atribuye ninguna falla a R19.

## 4. Estado de los parches
| Parche | SHA-256 | Estado |
|---|---|---|
| 01: D1–D3 y pruebas | `1944f433…2e60bf` | Sin cambios. Obligatorio. Se reverificó en la reproducción limpia de r3: 8 de 8 fallan contra el original y 8 de 8 pasan; mutantes 10 de 10 |
| 02v3: trazabilidad corregida | `d5c90091…cf6a62` | Sin cambios. Obligatorio. **Un único commit con 01.** Es técnicamente separable: sin 01 declara 1.1.0 falsamente (paso 4b). 14 de 14; mutantes 0 vivos |
| 03: pruebas sensibles al entorno | `0be65ea6…94e33a` | Sin cambios. Recomendado. Independiente: aplica y se revierte solo. No cubre R19 |
| 04: CI con versiones fijadas | `8d396356…306dd5` | Sin cambios. Opcional |
| 05: guarda de versión (nuevo) | `9fc829ad…ceb8ba47` | **Propuesta.** Opcional, con revisión aparte. No integrada |
| 02 original | `32a42a5d…` | No integrar |

## 5. Riesgos que bloquean, por separado
**A. Integración (fusionar en la rama base)**
1. **R7 / A7:** la CI real de GitHub (python y frontend) nunca corrió. Todo lo verde es local.
2. **A8:** falta la revisión humana del diff.
3. **R4c (D1):** 01+02v3 en un único commit, revertible solo junto. Git no lo impone; la guarda 05 lo respaldaría.
4. **R19, condicional:** si la primera CI falla con «persistence writes still in flight», no se fusiona en rojo y no se atribuye a R19 sin evidencia. La investigación está **pendiente de tu aprobación** de la enmienda 1.

*No bloquean la integración* (pendientes y documentados): R15, R22, R24, R14, R20, R21, R23, R-M10; M7 fuera del alcance de la guarda.

**B. Uso productivo del almacén de backtests** (despliegue, no integración)
1. **R24:** el guardado no se probó contra PostgreSQL.
2. **R4c:** sin el commit único, o sin la guarda, el almacén podría recibir resultados etiquetados 1.1.0 de un motor sin D1–D3. La huella del motor sí los separa de los genuinos, pero la etiqueta engaña.
3. **R15:** solo si hay escritores concurrentes. Hay que confirmar que no los hay.
4. **R21**, aceptado: una re-corrida legítima tras un cambio de entorno se rechaza (HTTP 400). Hace falta un procedimiento.

**C. Operación en vivo** (además de todo lo anterior)
| Riesgo | Por qué |
|---|---|
| R3 | El vivo no tiene las capas 2 y 3 de D3, y no hay prueba de equivalencia entre backtest y vivo |
| R17 | Sin stop durante un cierre por parciales |
| R18 | Una reversión rechazada no se reintenta (por inspección, el mismo patrón en el vivo) |
| R9 (vivo) | Sesión contra una venue real no verificada |
| R6 | Tolerancia del nivel de stop distinta (muy baja) |
| **R19** | Si resultara H-SINC, sería un defecto de la persistencia de `tia.runtime.live`: registros incompletos al detenerse bajo carga. **Hoy no se sabe**, así que bloquea el vivo hasta resolverlo |
| Puertas no técnicas | No hay validación de rentabilidad. `validada_para_operar` y las autorizaciones operativas no cambian |

## 6. Plan de integración y reversión actualizado
Ver `PLAN_INTEGRACION_Y_REVERSION_ACTUALIZADO.md`. En síntesis:
1. Rama local.
2. **01+02v3 en un único commit**, comprobando los 8 archivos.
3. (Opcional, con autorización aparte) **05 en el commit siguiente.**
4. 03 en otro commit.
5. Verificación local.
6. Push, que dispara la primera CI real.
7. PR en borrador.
8. 04 en un PR aparte.
9. Merge solo con la CI real en verde y revisión.

**Reversión:** en orden inverso (03, 05, la unidad 01+02v3), nunca solo una parte de la unidad. No hay que tocar datos.

## 7. Qué requiere tu decisión
1. Adoptar **v3r3** como candidata, en lugar de v3r2. Solo cambian documentos.
2. Revisar y decidir la **guarda 05**: integrarla o no, y en qué commit.
3. **Aprobar, corregir o rechazar la enmienda 1 de R19** y autorizar su ejecución (≈ 70–80 min de CPU local, sin red y sin tocar repositorios).
4. Por separado y después: las autorizaciones 1–8 del plan (rama, commits, push, PR, merge).
