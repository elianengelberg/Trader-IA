# Registro de cambios · reparación metodológica de E3-H1/H2 · 2026-10-26

**Área aislada:** `reparacion_E3H1H2_2026-10-26/` (dentro del scratchpad).

**Qué no se tocó** (verificado al final con las mismas recetas que al retomar):

| Objeto | Huella | Estado |
|---|---|---|
| Árbol congelado de E3 | `4909ef95…` | igual |
| Árbol de E3R (incluye el orquestador congelado `3b64a04d…`) | `649a72f5…` | igual |
| `CIERRE_E3_MANIFIESTO.sha256` | — | verifica |
| Repositorio protegido | HEAD `72ffae5`, índice `37490035…` | 0 cambios |

- No se ejecutó E3-H1/H2 ni se calculó ningún retorno o métrica de estrategia con precios reales.
- No hubo commits, push, PR, merge ni deploy. No hubo conexión a Testnet ni a exchanges. No se creó ningún archivo de autorización.

**Ningún artefacto congelado se sobrescribió.** Cuando una reparación necesitó cambiar uno, se creó una versión nueva con su propia procedencia y su hash:

| Congelado (sin cambios) | Versión nueva |
|---|---|
| `ejecutar_E3R.py` | `orquestador_v2/ejecutar_E3_v2.py`, generado por `generar_v2.py` con reemplazos verificados, más `DIFF_v1_v2.diff` |
| `p0_auditoria_interna.py` | `ventana_A/p0_pasada2.py`: tres cambios declarados en su encabezado; reproduce exactamente el P0 congelado con los insumos de la primera pasada |
| `conciliacion.py` | Sin versión nueva: se ejecutó tal cual. Para importar su función `clasificar` se usó una copia verificada por hash (`segunda_pasada/copia_congelada/`) |

## Orden de los trabajos

| # | Paso | Artefactos | Nota |
|---|---|---|---|
| 1 | Huellas al retomar | `registro/huella_E3_al_retomar.txt`, `huella_E3R_al_retomar.txt` | |
| 2 | Relectura de los 55 eventos de la primera pasada contra el texto archivado (N5) | `herramientas/fechas_efectivas.py` → `segunda_pasada/fechas_efectivas_en_texto.json`, `eventos_fechas_en_texto.txt` | Motivo: el desacierto de V-S3 (DOTUP) mostró que la fecha del título es la de publicación |
| 3 | Cobertura de las 112 páginas de exclusión; búsqueda de remociones de pares USDT omitidas dentro de A | `segunda_pasada/cobertura_tokens_exclusion.txt`, `verif_remociones.py` → `verificacion_remociones_en_A.txt` | Única omisión: TRXUP y LINKDOWN |
| 4 | Lectura de los 164 candidatos de renombre | `herramientas/frases_renombres.py` → `segunda_pasada/renombres_frases.txt`; `candidatos_renombre_indice.txt` | |
| 5 | Búsqueda de renombres no clasificados como tales | `herramientas/renombres_omitidos.py` → `segunda_pasada/renombres_omitidos_busqueda.txt` | Halla BCHABC→BCH y XZC→FIRO, y los *reverse splits* de tokens apalancados |
| 6 | Cambios de símbolo dentro de A, solo con actividad | `herramientas/escaneo_cambios_simbolo.py` → `segunda_pasada/escaneo_cambios_simbolo_A.txt`; `herramientas/actividad_simbolos.py` | Sin precios |
| 7 | Clasificación de los 164 candidatos y tabla de mapeos | `renombres/clasificar_candidatos.py` → `clasificacion_renombres.json`, `CLASIFICACION_RENOMBRES.md`, `mapeos_adenda1.json` | El script aborta si una cita no aparece literalmente en el texto archivado |
| 8 | Tratamiento de los 34 cortes con reanudación | `renombres/cortes_34.py` → `cortes_34.json` | |
| 9 | Resoluciones manuales en el formato del código congelado | `segunda_pasada/construir_resoluciones.py` → `resoluciones_manuales.json` (`41a13221…`) | Verifica cada cita |
| 10 | Reproducción de la primera pasada | `verificaciones/reproduccion_pasada1/` | 5 de 5 salidas idénticas byte a byte a las congeladas |
| 11 | Segunda pasada con `conciliacion.py` congelado | `segunda_pasada/salida_pasada2/` | 1.ª corrida: V-S3 revisados 6/10, porque el código vuelve a sortear la muestra sobre el universo de la segunda pasada. Se registró la revisión de los 47 eventos (ya releídos) y se repitió: 10/10 |
| 12 | Eventos omitidos, clasificados con la función congelada `clasificar` | `segunda_pasada/eventos_omitidos.py` → `eventos_omitidos.json` | |
| 13 | Ventana A | `ventana_A/p0_pasada2.py`: control con la primera pasada → `control_pasada1.json` (idéntico al P0 congelado); `ventana_A_pasada2.json`; `sensibilidad_sin_omitidos.json` | |
| 14 | Documento caso por caso | `segunda_pasada/documentar_caso_por_caso.py` → `SEGUNDA_PASADA_CASO_POR_CASO.md`, `sin_par_y_tokens.json` | Corrección propia: SKY se había rotulado «par USDT en el bucket», pero ese SKYUSDT es otro activo (de 2025): se reclasificó por A3.3.2 |
| 15 | Orquestador v2 | `orquestador_v2/generar_v2.py` → `ejecutar_E3_v2.py` (`01fc9344…`), `DIFF_v1_v2.diff`; `generar_manifiesto.py` → `ENTRADAS_CONGELADAS.json` (`8ee3bc07…`) | |
| 16 | Pruebas sintéticas | `orquestador_v2/pruebas/test_orquestador_v2.py` | Corrección propia: dos fallos del v1 se debían a un `TypeError` del adaptador de la prueba (`numpy.int64` en `timedelta`), no al defecto; se corrigió el adaptador y se verificó que los 6 fallos del v1 son por la razón sustantiva |
| 17 | Diferencial sintético v1 frente a v2, *preflight* del v2 contra insumos reales sin leer precios, pruebas congeladas del motor sobre una copia del código | `verificaciones/` | |
| 18 | Reproducción de la segunda pasada y de la ventana desde cero | `verificaciones/reproduccion_pasada2/` | Idéntica; en la ventana solo cambian las rutas absolutas registradas |
| 19 | Limpieza | — | Se borraron dos temporales (`_ant.txt`, `_tmp.txt`), un `__pycache__` creado por `py_compile` y la caché de ruff, con rutas literales |
