# Plan de pruebas negativas: R-1, R-2, R-4, L-13 y L-17

**Autor:** el mismo agente. **No es independiente.**

**Estados:**
- **EJECUTADA:** se corrió en esta fase, en un área aislada, y la salida está guardada;
- **HEREDADA:** verificada en una fase anterior por hash; no se repite;
- **PENDIENTE:** falta y se puede hacer aquí;
- **NO DEMOSTRABLE AQUÍ:** necesita un recurso que este contenedor no tiene.

**Tipos de fallo:**
- **P:** muerte o interrupción del proceso;
- **D:** pérdida de persistencia;
- **A:** adversario, o agente que no se propone eludir el control.

**Regla de no circularidad.** Cada prueba nombra el mutante que tiene que matar:
- sobre el v3 (defecto original), o
- sobre el diseño v4 tal como estaba.

Una prueba que no mata a su mutante no cuenta.

## R-1 · Señales

| Id | Prueba | Tipo | Mutante | Estado y resultado | Registro |
|---|---|---|---|---|---|
| N-R1-1 | `pthread_sigmask` con 1 hilo, con un hilo previo y con numpy | P | Diseño v4 (`pthread_sigmask`) | HEREDADA (revisor) y **reproducida**: con numpy, SIGTERM da `exit=143` dentro de la sección crítica y SIGINT da `KeyboardInterrupt` | `revisor/registro/11_…`, `verificacion_autor/registro/R1_senales_reejecucion.txt` (fase v4) |
| N-R1-2 | Manejador con numpy (4 hilos) y con un hilo vivo; SIGINT y SIGTERM; señal interna y externa; 20 `write`+`fsync` | P | — | EJECUTADA (fase v4): **8/8 diferidas**, sección completada y señal re-entregada | `verificacion_autor/registro/R1_handler_con_hilos.txt` (fase v4) |
| N-R1-3 | Proceso real con almacén v4.1 en ext4 y numpy; SIGINT, SIGTERM, SIGHUP y SIGQUIT × 12 momentos (semilla 20261029); invariante S-2 «DECISION ⇒ PUBLICADO» | P | Modo `mascara` | EJECUTADA: **manejador 0/48 violaciones; máscara 9/48 violaciones de S-2** | `tecnico/registro/R1_R2_senales_proceso.json` |
| N-R1-4 | Señal no manejada (SIGUSR1) y SIGKILL × 12 | P | — | EJECUTADA: 0 violaciones de S-1, S-3 y S-5 (sin repetición; clase coherente) | Ídem |
| N-R1-5 | Señal al **grupo** de procesos (Ctrl-C de terminal); `pthread_kill` a un hilo de BLAS; señal durante un `fsync` largo; ráfaga de señales; SIGSTOP/SIGCONT; SIGSEGV en código C; señal antes de instalar el manejador | P | — | **PENDIENTE** | — |

**Límite.** 12 momentos por combinación son evidencia preliminar, **no una garantía universal**.

## R-2 · Decisión inexistente, persistida o incierta

| Id | Prueba | Tipo | Mutante | Estado y resultado | Registro |
|---|---|---|---|---|---|
| N-R2-1 | Disco sombra exhaustivo: 5 escenarios × cada operación × {choque, escritura partida, ENOSPC, EIO, `fsync` que miente} × {corte, sin corte, canal perdido}; invariantes INV-1…7 | D y P | M1, M2, M4, M5, M8 | EJECUTADA: **722 casos, 0 violaciones fuera del límite declarado; 5/5 mutantes detectados** | `tecnico/registro/R2_exhaustiva.json` |
| N-R2-2 | Corrupción: byte cambiado, línea borrada, hueco de ceros (con objeto y sin objeto), cola cortada, cola partida de la reconciliación | D y A | M5 | EJECUTADA: BLOQUEADO en las 4 alteraciones del medio; recuperación con COLA_DESCARTADA en las 2 colas | Ídem |
| N-R2-3 | Límite: `fsync` que miente y canal perdido a la vez | D | — | EJECUTADA: 15 casos de reapertura tras leer datos y 14 de NO_DECIDIDO con una decisión calculada. **Conclusión: el ancla externa es obligatoria** | Ídem |
| N-R2-4 | Concurrencia: comparación de cabeza dentro del `flock` y `st_ino` frente a borrado y recreación, integradas al prototipo con FsReal | A y P | Comparación fuera del bloqueo | PENDIENTE (el mecanismo es HEREDADO del revisor, P4/P5) | `revisor/registro/13_…`, `14b_…` |
| N-R2-5 | Dispositivo que falla de verdad (dm-flakey o dm-error), corte de energía real, disco con caché volátil | D | — | **NO DEMOSTRABLE AQUÍ** (no hay control de dispositivos) | — |
| N-R2-6 | Que la salida estándar del proceso llegue a un registro externo al contenedor (supuesto A-1) | D y A | — | **PENDIENTE**: requiere que verifiques dónde queda la transcripción | — |

## R-4 / L-25 · Aislamiento

| Id | Prueba | Tipo | Mutante | Estado y resultado | Registro |
|---|---|---|---|---|---|
| N-R4-1 | Inventario de rutas ejecutables: orquestadores, conjuntos de series y documentos que satisfacen al v2 | A | — | EJECUTADA: 2 conjuntos reales extraídos, 1 tarball, 15 orquestadores y 6 documentos | `tecnico/r4_aislamiento/inventario.txt` |
| N-R4-2 | El documento de la reparación satisface al v2 por subcadenas | A | — | HEREDADA: P6 estático del revisor, 3/3 | `revisor/registro/23_…` |
| N-R4-3 | Sellado por contenido en una réplica sintética: ninguna ruta resuelve, manifiesto 100 %, restauración byte a byte | A | Sellado incompleto (se deja una copia) | EJECUTADA en la réplica | `tecnico/registro/R4_sellado_sintetico.txt` |
| N-R4-4 | Sellado real de las 2 copias y nuevo inventario: 0 conjuntos `series` reales resolubles | A | — | **BLOQUEADA**: requiere tu orden (D-9) | — |
| N-R4-5 | El lanzador v4 rechaza un árbol de ejecución con un `ejecutar_E3*.py`, una estructura `series` no declarada o la FRASE del v2 | A | Lanzador sin auditoría previa | PENDIENTE (se implementa con el v4) | — |

## L-13 · Persistencia del resultado

| Id | Prueba | Tipo | Estado y resultado |
|---|---|---|---|
| N-L13-1 | Escenarios del v3: I1, I5 (INVALIDO pasa a ERROR reintentable), E1, E4, E7 (EVALUADO perdido), E2, I2, E6, K1, K2, C1 y L12 | P y A | HEREDADA: evidencia del defecto en el v3, verificada por hash en la revisión anterior |
| N-L13-2 | Equivalentes en el v4.1 | P y D | EJECUTADA en el prototipo: INV-2, INV-3, INV-5 e INV-6 sobre 722 casos y 72 procesos reales |
| N-L13-3 | Comprobación previa de persistencia **antes de cualquier ejecución futura**: registro OK y anclado; ningún `ABIERTO` en el registro ni en el canal; prueba de `write`+`fsync`+relectura en el directorio del almacén; espacio libre suficiente para el peor objeto × 2; objetos verificados por hash; ningún temporal residual | D y A | PENDIENTE: se implementa con el lanzador. Cada condición necesita su negativo (disco lleno simulado con ENOSPC, `ABIERTO` previo, ancla distinta, temporal plantado) |

## L-17 · Autorización inequívoca

| Id | Prueba | Tipo | Estado y resultado | Registro |
|---|---|---|---|---|
| N-L17-1 | Validador v4.1 (`tecnico/l17_autorizacion/`): 54 vectores (bytes, esquema, gramática, decisiones con valor único, tipo, vínculos, vigencia y firma) | A | EJECUTADA: **53 rechazados, 1 aceptado** (el positivo de prueba), y producción rechaza el tipo de prueba. Cierra los dos casos que el prototipo del revisor aceptaba (`\u0000` y texto libre) | `tecnico/registro/L17_autorizacion.json` |
| N-L17-2 | Las 10 variantes de texto de la revisión anterior contra el validador v4.1 | A | PENDIENTE: trivial, porque no son JSON canónico; se corre con la implementación | — |
| N-L17-3 | Interoperabilidad con tu herramienta de firma: los bytes que produce tienen que ser idénticos a la forma canónica | — | **NO DEMOSTRABLE AQUÍ**: requiere tu herramienta | — |
| N-L17-4 | Ed25519 disponible en el intérprete del orquestador (el venv no tiene `cryptography`) | — | PENDIENTE: decisión A-3, que es instalarla fijada (con red y tu autorización) o verificar en un paso previo con `/usr/bin/python3`, que cambia el entorno | — |

**Aclaración sobre N-L17-1:**
- la clave es descartable y vivió solo en memoria;
- no se guardó ningún archivo de clave ni de firma;
- los objetos son del tipo PRUEBA_SINTETICA, que el modo de producción rechaza;
- no se emitió ninguna autorización.
