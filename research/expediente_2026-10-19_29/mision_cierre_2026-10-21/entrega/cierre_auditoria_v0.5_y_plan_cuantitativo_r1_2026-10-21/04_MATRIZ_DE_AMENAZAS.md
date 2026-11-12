# 04 — Matriz de amenazas y controles priorizados

**Escalas:**
- Detección hoy: **Sí** (una prueba ejecutada lo demuestra), **Parcial** o **No**.
- Probabilidad e impacto: estimaciones de juicio (Alta, Media o Baja), no mediciones.

## 1. Matriz
| ID | Amenaza | Eslabón | Prob. | Impacto | Detección hoy | Evidencia | Control propuesto | Prioridad |
|---|---|---|---|---|---|---|---|---|
| A-01 | Pérdida del scratchpad efímero (con él, todos los paquetes) | — | **Alta** | **Crítico** | No aplica | El contenedor se libera tras un tiempo de inactividad | **Descargar** v0.5 y este ZIP (B-8) | **P0** |
| A-02 | Reescritura **coherente** de un registro local (diario de P4, registro de decisiones, registro de acciones) | 6 | Baja | Alto | **No** | v0.5 `test_inyeccion_en_el_registro` (límite) | Cabeza en O2 y sello diario en O5 | P2 |
| A-03 | Alteración conjunta de los artefactos de T y de sus manifiestos | 7, 10 | Baja | Alto | **No**, sin raíz | v0.5 N1: P1 da INCONCLUSO, nunca VERIFICADO | Tu firma (R-3) y publicar los commits (D-G6) | P1 |
| A-04 | Ejecutar varias veces y presentar la mejor | 6 | Media | Alto | Parcial: el uso único local se detecta; con acceso total al equipo se puede borrar el ancla local | v0.5 P4: restauración, truncamiento y pérdida del ancla | Ancla externa O2 | P2 |
| A-05 | Cambiar parámetros o reglas después de ver datos | 2 | Media | Alto | Parcial: un cambio **posterior al congelado** se detecta; un congelado **tardío**, no | `test_congelar_y_verificar` | Sello externo al congelar (O5) | P2 |
| A-06 | Rejilla de parámetros o variantes encubiertas | 2 | Media | Alto | Sí (en el prerregistro) | «parámetro con varios valores»; `variantes_permitidas = 0` | — | — |
| A-07 | Mirada al futuro en la lógica | 4, 8 | Media | Alto | Sí, para estrategias que siguen el contrato | B1/B2: barra actual, estadística global y serie truncada | Exigir B1/B2 en cada implementación | — |
| A-08 | Datos corruptos, huecos, duplicados, velas incompletas | 3 | Media | Medio | Sí | `pec.datos` (12 pruebas) | — | — |
| A-09 | Procedencia falsa o errónea de la fuente | 3 | Baja | Alto | **No**: solo hay sumas del mismo proveedor | R-1 NO_VERIFICADO | Segundo proveedor (B-4, paso 5) | P3 |
| A-10 | Sesgo de supervivencia | 3 | Baja (BTC/ETH); Alta con más activos | Alto | Declarativo | Campo obligatorio del prerregistro | Universo fijado con datos de la fecha de inicio | — |
| A-11 | Multiplicidad: muchas hipótesis, se informa la ganadora | 1, 10 | **Alta** (más de 25 intentos) | Alto | Parcial: Bonferroni dentro de la familia; registro del programa | `pec.programa`; esquema | Exigir la fase prospectiva para «confirmada»; informar siempre el recuento del programa | P2 |
| A-12 | Período contaminado presentado como independiente | 2 | Media | Alto | Sí: aviso o error en el prerregistro | `test_periodos_contaminados_y_reservado_para_btc` | — | — |
| A-13 | Miradas repetidas en la fase prospectiva | 6 | Media | Alto | Sí | O'Brien–Fleming verificado | — | — |
| A-14 | Prueba estadística mal calibrada (tamaño real > α) | 8 | **Media** | **Alto** | **No** | El MEC §1.2 lo documenta para P; la calibración no se ejecutó | **A-S1** | **P1** |
| A-15 | Implementación incorrecta de la prueba | 8 | Media | Alto | Parcial: cálculos a mano, dualidad exacta, contraste con E3 (mismo autor) | `test_inferencia.py`; el contraste encontró un defecto real (N-1) | Revisión por un tercero (B-7) | P3 |
| A-16 | Presellado sin calcular | 7 | Baja | Medio | No | Límite documentado en v0.5 | Reproducción independiente | P3 |
| A-17 | Elegir la reproducción favorable (código no determinista) | 9 | Media | Alto | Parcial: P4 verifica el determinismo si se pide | A14 lo exige el esquema | Reproductor independiente | P3 |
| A-18 | Clave raíz comprometida o en este equipo | 10 | Baja | Crítico | No: no se puede saber dónde está la clave | — | A13: clave fuera de línea; rotación; revocación por cambio de código revisado | P1 |
| A-19 | Alguien edita el verificador y agrega una raíz | 10 | Baja | Crítico | No, mientras el código no esté publicado y revisado | — | B-1 (commit publicado) y B-7 | P2 |
| A-20 | Claves o firmas degeneradas | 10 | Baja | Crítico | Sí | 807 casos; sondas F1 | — | — |
| A-21 | El paquete cambia durante su propia verificación | — | Baja | Medio | Sí, salvo enlaces y directorios vacíos | Etapa 13 de v0.5; **D-1**: corrección propuesta y probada | Aplicar 0001 de v0.5.1 en la próxima versión del arnés | P4 |
| A-22 | Escritura accidental en el repositorio o una operación de git | — | Baja | Alto | Sí | Huella fuerte antes y después (`evidencia/A2_*`, `G2_*`) | — | — |
| A-23 | Lectura accidental de datos de mercado | 3 | Baja | Medio | **No hay control técnico**: es una regla de conducta | Inventario sin SHA-256 de los ZIP con datos | Lector con ventana (B-4, paso 6) | P3 |
| A-24 | Cortes de energía y errores de E/S | 6 | Baja | Medio | Sí, simulados (102 y 72 escenarios por código) | v0.5 `14_*`, `10_*` | Prueba en hardware real (no simulable aquí) | P4 |
| A-25 | Cadena de suministro: dependencias alteradas | 4 | Baja | Alto | No | — | Lockfile con hashes por hipótesis; PEC no usa dependencias externas | P3 |
| A-26 | Fugas de temporales en TMPDIR (higiene) | — | Alta | Bajo | — | **D-2**: 66 directorios por ejecución completa de v0.5 | Limpieza en las pruebas (corrección propuesta) | P4 |
| A-27 | Un registro de acciones reconstruido presentado como contemporáneo | 6 | Media | Medio | — | **D-4**: las fechas son mtime y no están en orden | Registro de solo añadidos escrito al momento y anclado | P3 |

## 2. Controles priorizados (proporcionales a la amenaza)
| Prioridad | Control | Amenazas | Costo | Quién |
|---|---|---|---|---|
| **P0** | Descargar y conservar v0.5 y este ZIP fuera del scratchpad | A-01 | Minutos | Vos |
| **P1** | A-S1: calibración sintética de la prueba primaria | A-14 | 1,3–3,9 h de CPU | Yo, con tu autorización |
| **P1** | R-3: firma de T con una clave fuera de línea y política de raíces A13 | A-03, A-18 | 30 min | Vos |
| **P2** | R-5: ancla O2 + O5 | A-02, A-04, A-05, A-11 | 30 min tuyos + 1 día mío | Vos y yo |
| **P2** | B-1/D-G6: publicar el verificador y los congelados | A-19, A-03 | Minutos | Vos |
| **P3** | B-7: revisión por un tercero | A-15, A-16, A-17, todas | 3–5 días | Un tercero |
| **P3** | B-4 completo: segundo proveedor y lector con ventana | A-09, A-23 | Con la autorización | Yo |
| **P3** | Registro de acciones de solo añadidos, escrito al momento y anclado | A-27, A-02 | Bajo | Yo |
| **P3** | Lockfile con hashes | A-25 | Bajo | Yo |
| **P4** | Arnés v0.5.1: etapa 13 corregida y limpieza de temporales | A-21, A-26 | Bajo | Yo |

No se proponen más firmas, cifrados ni otros mecanismos criptográficos: ninguna amenaza de la lista los justifica.
