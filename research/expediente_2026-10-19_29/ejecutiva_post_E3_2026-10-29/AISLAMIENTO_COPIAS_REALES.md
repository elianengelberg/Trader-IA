# Aislamiento de las copias reales de las series (R-4 / L-25)

## 1. Qué se protege (rutas verificadas hoy en disco, `registro/verificacion_copias.txt`)

`S` = `/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad`

| # | Ruta | Contenido verificado |
|---|---|---|
| R1 | `S/experimentos/E3_seleccion_posicion_2026-10-19/ejecucion_E3/resultados/calidad/series` | 757 `.npz`, hash de conjunto `6506fb03…` (igual al congelado) |
| R2 | `S/paquete_revision_independiente_E3H1H2_2026-10-28_DATOS/evidencia/experimentos/E3_seleccion_posicion_2026-10-19/ejecucion_E3/resultados/calidad/series` | 757 `.npz`, hash de conjunto `6506fb03…` |
| T | `S/entrega_revision_independiente_2026-10-28/paquete_revision_independiente_E3H1H2_2026-10-28_DATOS.tar.gz` | 31 769 544 bytes, sha256 `0562b919…` (contiene las series; hay que extraerlo) |
| O1–O15 | Las 15 copias de orquestadores, enumeradas una por una con su sha256 en `registro/verificacion_copias.txt` | E3R `3b64a04d…` ×6, v2 `01fc9344…` ×6, v3 `c089cc6a…` ×3. Las 15 están presentes y con su hash |

**Hecho clave:**
- v1/E3R, v2 y v3 reciben la carpeta de E3 **por argumento** (`modo_real(e3, …)`) y leen `e3/resultados/calidad/series/*.npz`.
- Cualquier copia de código sirve con cualquiera de las dos copias de datos.

## 2. Qué está COMPROBADO hoy (sin modificar nada en disco)

| Medida | Evidencia | Resultado |
|---|---|---|
| **Zona de ejecución aislada** (`zona_aislada/ejecutar_aislado.sh`): un espacio de montaje privado que tapa R1, R2, T y O1–O15 con vacíos de solo lectura, comprueba el tapado **antes** de ejecutar y aborta con código 99 si no es efectivo | `registro/prueba_zona_aislada.txt` | **Dentro:** R1 y R2 con 0 archivos, v2 con 0 bytes, escritura rechazada (sistema de solo lectura). **Afuera, antes y después:** R1 y R2 `6506fb03…`, v2 `01fc9344…`, 757 + 757 `.npz` y 0 montajes filtrados al espacio global |
| **Guarda de rutas** del próximo experimento (`e4_xsrev_prospectivo/codigo/guarda_rutas.py`) | `e4_xsrev_prospectivo/registro/prueba_guarda.json` | Rechaza: ruta directa, subarchivo, enlace simbólico, enlace a la carpeta padre, ruta relativa con «..», orquestador v2, estructura `resultados/calidad/series` y enlace duro (probado con un archivo protegido **sintético**, para no tocar el ctime de uno congelado). Acepta una carpeta de datos nueva |
| Recolector y evaluador de E4 | `e4_xsrev_prospectivo/registro/prueba_punta_a_punta.json` | Se niegan a usar un destino protegido |

**Límite de lo comprobado:**
- protege todo lo que se lance **a través** de `ejecutar_aislado.sh` y todo código que use la guarda;
- **no** impide que alguien ejecute a mano, fuera de la zona, una de las 15 copias sobre R1 o R2;
- para eso hace falta el sellado del §3, que requiere tu orden.

## 3. Lo que queda PENDIENTE y requiere tu autorización: sellado por renombre del directorio

**Operación exacta** (dos renombres de directorio en el mismo sistema de archivos):
- no copia, no borra y no modifica ningún `.npz`;
- es reversible con el renombre inverso.

```bash
S=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad
R1=$S/experimentos/E3_seleccion_posicion_2026-10-19/ejecucion_E3/resultados/calidad/series
R2=$S/paquete_revision_independiente_E3H1H2_2026-10-28_DATOS/evidencia/experimentos/E3_seleccion_posicion_2026-10-19/ejecucion_E3/resultados/calidad/series
hc() { (cd "$1" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -c1-64); }
# 1) hashes antes (tienen que dar 6506fb03… los dos; si no, ABORTAR)
[ "$(hc $R1)" = 6506fb03c211def710abe61a2493799000b80996c63000fcfc98da624cbaba79 ] && [ "$(hc $R2)" = 6506fb03c211def710abe61a2493799000b80996c63000fcfc98da624cbaba79 ] || exit 1
# 2) sellado: renombre atómico del directorio (el contenido no se toca)
mv -T "$R1" "$R1.SELLADO_6506fb03" && mv -T "$R2" "$R2.SELLADO_6506fb03"
# 3) hashes después, sobre las rutas nuevas (tienen que seguir siendo 6506fb03…), y comprobación de que la ruta vieja ya no existe
hc "$R1.SELLADO_6506fb03"; hc "$R2.SELLADO_6506fb03"; test ! -e "$R1" && test ! -e "$R2" && echo SELLADO_OK
# Reversión (si la pedís): mv -T "$R1.SELLADO_6506fb03" "$R1" && mv -T "$R2.SELLADO_6506fb03" "$R2"
```

**Consecuencias, que tenés que aceptar de forma explícita:**
1. Las 15 copias de orquestadores dejan de encontrar series en la ruta que usan, también cuando se les pasa la carpeta E3 como argumento. Una ejecución accidental falla al leer, sin calcular nada.
2. **Cambian las huellas de conjunto** de dos árboles congelados (`E3` y `PKD`), porque el hash incluye las rutas relativas. El contenido sigue verificando `6506fb03…` en la ruta nueva.
   - Todo procedimiento que recalcule la huella de esos árboles tiene que aplicar antes la reversión, o comparar contra las huellas nuevas registradas en el momento del sellado.
3. El tarball T sigue intacto. Para usar sus datos hay que extraerlo: es un acto deliberado, no accidental.
4. Contra un actor deliberado con privilegios de root, nada de esto es una garantía: puede renombrar de vuelta. La protección es contra la ejecución **inadvertida**.
5. Los permisos no cambian. No se usa `chattr` ni `chmod`: como root no protegen y alteran metadatos.

**Recomendación:**
- autorizar el sellado (§3) **y** usar siempre la zona aislada (§2) para el experimento siguiente;
- si no autorizás el sellado, el aislamiento queda **parcial** (solo lo lanzado por la zona) y L-25 sigue abierto para ejecuciones manuales directas.
