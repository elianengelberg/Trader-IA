# Expediente de investigación del 2026-10-19 al 2026-10-29 (solo simulación)

**Qué es:** el trabajo de esas sesiones de Claude Code, que vivía en el área temporal de un contenedor efímero y se pasó acá el 2026-11-12 para que no se pierda.

**Cómo está armado:**
- Cada carpeta conserva su **nombre original**. Las rutas que los documentos dan «relativas al scratchpad» valen desde esta carpeta.
- Los informes de las primeras fases pueden citar rutas absolutas del contenedor viejo, `/tmp/claude-0/…/scratchpad/`. Equivalen a esta carpeta.

**Qué no hay acá:**
- Nada de esto opera, despliega ni usa credenciales.
- Ninguna clase de resultado autoriza dinero real.
- Los parches al código de la aplicación están **solo como archivos `.patch`**; no se aplicaron a `packages/`.

## Líneas y estado

| Línea | Carpetas | Estado | Entrada |
|---|---|---|---|
| E1 · bot con datos reales | `experimentos/E1_bot_datos_reales_2026-10-19` | Cerrada | `informe/INFORME_E1.md` |
| E2 · descubrimiento | `experimentos/E2_descubrimiento_2026-10-19` | Cerrada | `INVESTIGACION_E2.md` |
| Metodología: P1, P2 y P4, PEC-1.0/1.1, calibración AS1, hoja de ruta | ZIP `*_2026-10-20.zip` y `*_2026-10-21.zip` con sus `SHA256SUMS_DEL_ZIP*.txt`; `expediente_metodologico_2026-10-20`, `fase_documental_2026-10-20`, `fx3_expediente`, `calibracion_AS1_2026-10-21`, `decisiones_metodologicas_2026-10-21`, `mision_cierre_2026-10-21`, `hoja_de_ruta_confirmatoria_2026-10-21` | Cerrada | `hoja_de_ruta_confirmatoria_2026-10-21/00_HOJA_DE_RUTA.md` |
| Motor · D1–D3, R19, integración controlada, parches 01–25 | `mision_simulacion_2026-10-21`, `integracion_parche_D1_D3_2026-10-21`, `cierre_D1_D3_2026-10-22`, `cierre_D1_D2_R19_2026-10-22`, `cierre_revision_D1_D3_2026-10-22`, `decision_final_D1_D3_2026-10-22`, `cierre_integral_2026-10-22`, `revision_adversaria_2026-10-25`, `entrega_iniciativa_tecnica_2026-10-25`, `entrega_integracion_controlada_2026-10-25`, `entrega_direccion_tecnica_2026-10-26` | Parches **no aplicados**, pendientes de tu decisión | `entrega_direccion_tecnica_2026-10-26/INFORME_DIRECCION_TECNICA.md` y `PROPUESTAS_TECNICAS.md` |
| E3 · selección transversal (H1 y H2) | `experimentos/E3_seleccion_posicion_2026-10-19`, `experimentos/E3R_desbloqueo_2026-10-26`, `decision_E3H1H2_2026-10-26`, `reparacion_E3H1H2_2026-10-26`, `revision_independiente_E3H1H2_2026-10-26`, `cierre_bloqueantes_E3H1H2_2026-10-27`, `paquete_revision_independiente_E3H1H2_2026-10-28`, `revision_adversarial_E3H1H2_2026-10-28`, `revision_independiente_diseno_v4_2026-10-28`, `cierre_decisivo_v4_2026-10-29` | **Cerrada administrativamente: NO EVALUABLE.** La candidata A es INVÁLIDA (111 semanas, por debajo de 156) y la ventana no se cambió | `ejecutiva_post_E3_2026-10-29/CIERRE_ADMINISTRATIVO_E3.md` |
| E4 · H-XS-REV-1 prospectiva | `ejecutiva_post_E3_2026-10-29/e4_xsrev_prospectivo` (v0) y `revision_adversarial_E4_2026-10-29` (v1) | **Activa.** El prerregistro v1 es un borrador, ni congelado ni anclado; hay 4 decisiones pendientes | `revision_adversarial_E4_2026-10-29/REVISION_ADVERSARIAL_E4.md` |

## E4: cómo seguir desde el repositorio

**Código y prerregistro:**
- `revision_adversarial_E4_2026-10-29/e4_v1/codigo/`
- `revision_adversarial_E4_2026-10-29/e4_v1/PRERREGISTRO_E4_v1.md`

**Pruebas (solo datos sintéticos):**
- `e4_v1/pruebas/pruebas_v1.py`
- `e4_v1/pruebas/prueba_punta_a_punta_v1.py`. Usa `/dev/shm` y la lista `PROTEGIDOS.tsv` de `ejecutiva_post_E3_2026-10-29/zona_aislada/`.

**Rutas del contenedor viejo:** los comandos de la §6 del informe usan `S=/tmp/claude-0/…/scratchpad`. Desde el repositorio son `S=research/expediente_2026-10-19_29`.

**Entorno que usaron las pruebas:** Python 3.11 y numpy 2.4.6.

**Lo protegido ya no está acá:** las series reales de E3 que `PROTEGIDOS.tsv` protegía **no se versionan**, así que no existen en un clon. La guarda de rutas sigue funcionando: una ruta que no existe no bloquea nada.

## Qué quedó afuera y por qué (`_inventario/`)

| Archivo | Contenido |
|---|---|
| `SELECCION_VERSIONADA.tsv` | Lo que se versionó: tamaño y ruta |
| `EXCLUIDOS_DENTRO_DE_LAS_FUENTES.tsv` | Lo excluido dentro de las carpetas seleccionadas, con su motivo y su sha256 o huella de árbol. La huella es el sha256 de las líneas «sha256  ruta» ordenadas, y sirve para verificar una copia que se recupere |
| `PAGINAS_ARCHIVADAS_NO_VERSIONADAS.tsv` | Las 128 páginas de anuncios de Binance que usó la segunda lectura de E3: URL y sha256. Es texto de terceros y no se publica |
| `ENTRADAS_NO_SELECCIONADAS.tsv` | Las entradas del área temporal que no se pasaron, con su número de archivos (sin entornos ni cachés) y su tamaño. Son copias de trabajo del repositorio, extracciones duplicadas, salidas de corridas, entornos y temporales |
| `seleccion.py` y `inventario.py` | Los scripts que hicieron la selección y el inventario |

**Lo excluido:**
- **Datos de terceros**, como hasta ahora en `research/.gitignore`:
  - velas y checksums de Binance Vision;
  - páginas archivadas;
  - series `.npz` derivadas;
  - tarballs con datos.
- **Entornos virtuales y ruedas.**
- **Copias duplicadas** de árboles que ya están incluidos (`copia_A`, `copia_aislada`, `extraccion*`, `evidencia/` del paquete de revisión).
- **Temporales de prueba.**
- **Dos archivos de más de 5 MB.**

Por eso algunos `MANIFEST*.sha256` internos listan archivos que acá no están. El inventario dice cuáles.

## Datos y licencias

**Binance Vision.** Hay resultados derivados de datos de Binance Vision (operaciones simuladas, listas y auditorías por símbolo). Sus términos (versión 1.0 del 2026-08-26) los licencian **CC BY-NC-SA 4.0**:
- **Atribución:** datos de Binance Vision (data.binance.vision).
- **Licencia de los derivados:** cuando se redistribuyen, la misma.
- **Uso:** no comercial.
- **Prohibido:** usarlos para operar en vivo.

**Wikipedia.** Las vistas de páginas de E2 vienen de la API pública de Wikimedia.
