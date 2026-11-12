# Cambios de la revisión r3 respecto de r2 (solo documentación)

- **Origen:** extracción nueva de `entrega_integracion_D1_D3_v3r2_2026-10-22.zip` (`d912c88a59b878520501ff221fd78d2d2eef870ae0b681d2108441ab8cbd5155`), verificada: suma externa OK y 98 de 98 sumas internas.
- **r2 no se modificó** y se conserva junto a r3.
- **Diferencias exactas:** `CAMBIOS_r3_v3r2_a_v3r3.diff` (`diff -ruN` de r2 a r3, sin los `SHA256SUMS`).

## Lo que no cambia, byte a byte
- `parches/`: los 5 parches, `SHA256_archivos_resultantes_*_v3.txt` y `ARCHIVOS_MODIFICADOS.txt`.
- `pruebas/`, `entorno/`, `registro/`.
- Toda la evidencia de r2 en `evidencia/`.
- Todas las herramientas de r2 en `herramientas/`.
- **La decisión B** y la recomendación de integrar 01+02v3 más 03.

## Correcciones
| # | Qué decía r2 | Qué dice r3 | Archivos |
|---|---|---|---|
| C1 (discrepancia documental D1 de la revisión de cierre; no confundir con el defecto D1 del motor) | «**02v3 no aplica sin 01:** comparten `engine.py`» y «unidad inseparable» | **01 y 02v3 son técnicamente separables, pero deben integrarse y revertirse juntos mediante un único commit, porque 02v3 sin 01 puede declarar una versión de motor incorrecta.** El plan agrega una comprobación de que el commit único contiene exactamente los 8 archivos. Nuevo riesgo R4c | `PLAN_INTEGRACION_Y_REVERSION.md`, `INFORME_DECISION_FINAL.md`, `LEEME.md`, `ACCIONES_QUE_REQUIEREN_AUTORIZACION.md`, `MATRIZ_RIESGOS.md`, `COMANDOS_DE_VERIFICACION.md` |
| C2 (discrepancia documental D2) | «0 en la integración (salvo R19…)», «completa: 0, salvo R19 bajo carga», «es R19, preexistente» | Se separan **hechos comprobados** (conteos, nombres registrados, cargas registradas) de **inferencias** (que las fallas sin nombre sean R19, que la causa sea la carga, que el mecanismo sea el bucle de fondo). Una falla futura es «compatible con R19», no «R19», hasta tener evidencia del mecanismo | `FALLAS_INTERMITENTES_HECHOS_E_INFERENCIAS.md` (nuevo), `MATRIZ_REVISION_PARCHES.md`, `EVIDENCIA_EJECUCIONES.md`, `INFORME_DECISION_FINAL.md`, `MATRIZ_RIESGOS.md`, `PLAN_INTEGRACION_Y_REVERSION.md` §4 |
| C3 (fila local como si fuera la CI) | «Sin restricciones, como la CI de hoy», «Suites completas (comando de la CI; JUnit)» | «**reproducción local**; GitHub Actions todavía no se ejecutó». La misma aclaración en las filas «como la CI» de `EVIDENCIA_EJECUCIONES.md` | `COMPARACION_BASE_VS_INTEGRACION.md`, `EVIDENCIA_EJECUCIONES.md`, `INFORME_DECISION_FINAL.md` §1 |

## Agregados
| Archivo | Para qué |
|---|---|
| `FALLAS_INTERMITENTES_HECHOS_E_INFERENCIAS.md` | C2 |
| `CAMBIOS_REVISION_r3.md`, `CAMBIOS_r3_v3r2_a_v3r3.diff` | Este registro y sus diferencias exactas |
| `evidencia/U1_unidad_y_reversion.txt`, `evidencia/U2_02v3_sin_01.txt` | Evidencia de C1, tomada sin cambios de la revisión de cierre (`revision_cierre_D1_D3_2026-10-22.zip`, `8e6979ad…`) |
| `herramientas/sonda_version.py` | Sonda de solo lectura: versión, huella y si el motor tiene D1–D3. La usa el paso 4b |
| `reproducir.sh`, paso 4b | Verifica C1 desde una extracción limpia: 02v3 aplica sin 01, declara 1.1.0 sin D1–D3 y sus 14 pruebas pasan igual; git permite revertir cada uno por separado; la lista de 8 archivos del paso 1.3 es exacta |

## Fuera de r3, a propósito
- **Ninguna guarda técnica** contra la etiqueta falsa: si se propone, va como parche aparte, con su revisión.
- **Ninguna corrección de R19.**
- **Ningún resultado nuevo de R19:** r3 solo corrige cómo se describe lo que ya estaba registrado.
