# R-4 / L-25 · Aislamiento efectivo de la zona de archivo (propuesta, no ejecutada)

**Autor:** el mismo agente. **No es independiente.**

**Qué no hice:**
- no modifiqué, moví, renombré ni borré nada fuera de `cierre_decisivo_v4_2026-10-29/`;
- **el sellado real requiere tu orden expresa**, porque cambia rutas de árboles congelados.

## 1. Hechos del inventario

Fuente: `tecnico/r4_aislamiento/inventario.txt`, obtenido solo con lecturas: `find`, nombres y sha256.

| Qué | Copias |
|---|---|
| Datos reales extraídos (757 series `.npz` en `…/resultados/calidad/series`) | **2**: el árbol congelado `experimentos/E3_seleccion_posicion_2026-10-19/ejecucion_E3/` y `paquete_revision_independiente_E3H1H2_2026-10-28_DATOS/evidencia/…` |
| Datos reales empaquetados | `entrega_revision_independiente_2026-10-28/paquete_revision_independiente_E3H1H2_2026-10-28_DATOS.tar.gz` (31,7 MB). Hace falta extraerlo: es un acto deliberado |
| Conjuntos `series` sintéticos de pruebas | 306, todos con 3 a 41 archivos, dentro de `revision_adversarial_E3H1H2_2026-10-28/tmp_pytest_v3/` |
| Orquestadores | `ejecutar_E3R.py` (`3b64a04d…`) ×6, `ejecutar_E3_v2.py` (`01fc9344…`) ×6 y `ejecutar_E3_v3.py` (`c089cc6a…`) ×3, en 8 carpetas de primer nivel |
| Documento que satisface al v2 por subcadenas | `INFORME_REPARACION_E3H1H2.md` (`9b26ecb5…`) ×6 |

**Cómo resuelven sus rutas.** v1/E3R, v2 y v3 reciben la carpeta de E3 como argumento en el modo real (`modo_real(e3, ventana, autorizacion, salida)`):
- E3R l. 501;
- v2 l. 553;
- v3 l. 902.

Las tres leen `e3/resultados/calidad/series/*.npz` (E3R l. 76; v2 l. 99).

**Consecuencia:**
- retirar o sellar copias de **código** no alcanza, porque cualquier copia sirve;
- lo que hace posible una ejecución es que exista **algún** conjunto real de series con esa estructura de rutas, y hoy hay 2.

## 2. Propuesta en tres capas

| Capa | Medida | ¿Requiere tu orden? | Qué protege | Qué no protege |
|---|---|---|---|---|
| 1 · Zona de ejecución separada | La ejecución v4 corre en un entorno nuevo (otra sesión o contenedor) que contiene solo el lanzador, el orquestador v4 y los insumos copiados y verificados por hash. El lanzador rechaza el arranque si en su árbol hay un `ejecutar_E3*.py`, la estructura `resultados/calidad/series` fuera de la entrada declarada, o un archivo que contenga la FRASE del v2 | No (es diseño) | Que la ejecución v4 se confunda con otra o herede un estado previo | Una ejecución del v2 en la zona de archivo |
| 2 · Sellado por contenido de los datos reales | Las 1514 series de las 2 copias extraídas se renombran a `sellado/<sha256>`, sin extensión y en el mismo sistema de archivos (`os.replace`: no se copia ni se borra contenido). Un manifiesto `ruta → sha256` se firma o se ancla | **Sí**: cambia rutas dentro de árboles congelados (E3 y el paquete de datos) | Que **cualquier** copia de v1/v2/v3 corra sobre datos reales por descuido. Sin la estructura no se resuelve ninguna serie, tampoco pasando la carpeta como argumento | Un acto deliberado: restaurar desde el manifiesto o extraer el tarball |
| 3 · Revocación documental | Un acta firmada con los sha256 de v1/E3R, v2 y v3 y de la FRASE del v2. La autorización v4 cita su hash (L-17, F6) | Sí (la firma es tuya) | Trazabilidad: toda corrida del v2 es una ejecución no planificada y exploratoria (v3 §3.3) | Nada técnico |

**Alternativa a la capa 2:**
- empaquetar las 2 copias en un tar verificado y retirar las extraídas;
- es un borrado de copias, con los bytes preservados en el tar;
- requiere tu orden;
- es más fuerte que el renombre (hace falta extraer), pero es irreversible si el tar se pierde.

## 3. Evidencia en una réplica sintética

`tecnico/r4_aislamiento/demo_sellado_sintetico.py` → `tecnico/registro/R4_sellado_sintetico.txt`

| Comprobación | Resultado |
|---|---|
| Archivos que resuelve la ruta antes del sellado | 25 |
| Archivos que resuelve la ruta por defecto después | **0** |
| Archivos que resuelve después, pasando cualquier carpeta del árbol como argumento | **0** |
| Estructuras `series` con `.npz` después | 0 |
| Verificación del manifiesto | 100 % |
| Restauración | Byte a byte |

## 4. Límites declarados

- Contra root, o contra un agente que se proponga eludirlo, nada de esto es una garantía: puede restaurar desde el manifiesto o extraer el tarball. La protección es contra la ejecución **inadvertida** (R-5).
- Mientras no des la orden de la capa 2, **L-25 sigue abierto** en la zona de archivo. Las pruebas de aceptación tienen que decirlo y no pueden limitarse a la zona de ejecución (corrección de la l. 353 del diseño).
- Si la capa 2 renombra las series del árbol congelado de E3, cambia el hash de conjunto de ese árbol.
  - El manifiesto de sellado tiene que permitir recomputar los hashes originales; la demostración lo hace con la restauración.
  - Las huellas de los árboles congelados pasan a verificarse sobre la restauración.
  - Esto también requiere tu orden, porque cambia el procedimiento de verificación de la historia.
