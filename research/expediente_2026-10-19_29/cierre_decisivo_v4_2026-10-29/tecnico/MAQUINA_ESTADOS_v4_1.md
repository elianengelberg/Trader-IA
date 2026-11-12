# Máquina de estados v4.1 de una ejecución E3 (R-2, D-7)

**Autor:** el mismo agente del diseño v4. **No es independiente.** Tiene que revisarla un tercero (§9 del informe).

**Prototipo:** `tecnico/r2_maquina/proto_v4.py`. No es E3: usa datos inventados y no lee datos reales.

**Política:** D-7 = (iii), **cero reintentos**. Es la lectura literal de:
- v3 l. 73: «una sola ejecución»;
- §3.3 l. 175 y 180–183;
- ADENDA_R l. 61;
- PLAN l. 35: «Sin repeticiones».

## 1. Definición de «ejecución»

**Una ejecución** es un intento cuyo `ABIERTO` quedó durable en el registro o anunciado en el canal externo. Es la única por evaluación. Desde ese momento no hay reintento posible: cualquier final distinto de EVALUADO o INVALIDO deja a E3 **NO EVALUABLE (fallo de ejecución)**.

**Antes de `ABIERTO`** está la comprobación previa (preflight). No lee datos de mercado y puede fallar y repetirse sin consumir nada:
- integridad del registro y del ancla;
- hashes del lanzador, el orquestador, el entorno y los insumos;
- validación de la autorización (L-17);
- espacio libre;
- prueba de `write` + `fsync` en el directorio del almacén;
- ausencia de un `ABIERTO` previo en el registro y en el canal.

Todo lo que pueda fallar por infraestructura se pone ahí.

## 2. Eventos y orden

```
preflight ─▶ ABIERTO ─▶ [canal: ABIERTO_DURABLE] ─▶ (lectura de datos) ─▶ ETAPA(panel) ─▶ ETAPA(validez)
   ├─(INVALIDO)──────────────────────────────────────────────▶ [canal: ANUNCIO_DECISION] ─▶ DECISION ─▶ objeto ─▶ PUBLICADO
   └─▶ ETAPA(simulacion) ─(EVALUADO)─▶ [canal: ANUNCIO_DECISION] ─▶ DECISION ─▶ objeto ─▶ PUBLICADO
Error de cálculo antes de anunciar ─▶ ERROR(etapa) durable ─▶ [canal: ERROR_DURABLE] ─▶ fin
OSError del almacén en cualquier punto ─▶ [canal: FALLO_ALMACEN] ─▶ fin, sin escribir nada más
```

**Registro:**
- encadenado: `prev` = sha256 de la línea anterior;
- cada línea empieza con el marcador `0x1E`, que nunca aparece crudo en JSON ASCII;
- formato canónico.

**Escrituras:**
- cada línea se agrega con comparación de cabeza dentro del bloqueo (R-7) y con `fsync` del archivo;
- cuando el archivo es nuevo, también `fsync` del directorio.

**Objeto:**
- temporal con nombre aleatorio y `O_EXCL`, `fsync`, `link` a su sha256, `fsync` del directorio, `unlink` del temporal y otro `fsync` del directorio (R-8);
- serialización canónica con `allow_nan=False` (R-11).

**Señales:**
- SIGINT, SIGTERM, SIGHUP y SIGQUIT se instalan al arrancar con un manejador que solo anota la señal (R-1);
- se revisan en puntos seguros. Antes del anuncio se escribe ERROR(senal) y se sale. Después del anuncio se termina la publicación y recién entonces se vuelve a entregar la señal;
- SIGKILL, OOM y las señales no manejadas las cubre la reconciliación.

## 3. Clasificación con valor explícito para la decisión

La reconciliación:
- solo agrega líneas;
- ante una cola cortada agrega `COLA_DESCARTADA` con el sha y la longitud de **todos** los bytes saltados, sin truncar;
- es idempotente.

| Condición del registro y del canal | Clase | Decisión | ¿Terminal? |
|---|---|---|---|
| Cadena rota, o un objeto sin DECISION que lo cite | BLOQUEADO | — | Sí, requiere revisión humana |
| Sin `ABIERTO` en el registro ni en el canal | VACIO | — | No: **la única clase que permite abrir** |
| Sin `ABIERTO` en el registro, pero el canal lo registra | INCIERTO | — | Sí |
| DECISION durable y objeto verificado (hash = nombre = DECISION) | EVALUADO / INVALIDO | **Persistida** | Sí |
| DECISION durable, objeto ausente o alterado | TERMINAL_SIN_OBJETO(tipo) | Persistida, sin resultado verificable | Sí: NO EVALUABLE |
| Sin DECISION, con ANUNCIO_DECISION en el canal | DECISION_ANUNCIADA_NO_PERSISTIDA(tipo) | **Existió, sin persistir** | Sí: NO EVALUABLE |
| Sin DECISION: ERROR durable; o el canal registra la salida sin anuncio; o la última etapa durable es anterior a `validez` | NO_DECIDIDO | **Inexistente, probada** | Sí: NO EVALUABLE (fallo) |
| Sin DECISION, última etapa `validez` o `simulacion`, y nada prueba que no hubo decisión | INCIERTO | **Incierta** | Sí: NO EVALUABLE |

**Prohibición de repetición automática:**
- `puede_abrir()` es verdadera solo en VACIO;
- la reconciliación nunca escribe `ABIERTO`;
- una autorización nueva tendría que citar la cabeza actual (L-17, F6), y con (iii) el lanzador solo acepta autorizaciones si la clase es VACIO.

## 4. Evidencia (preliminar, del autor)

| Prueba | Qué cubre | Resultado | Registro |
|---|---|---|---|
| Disco sombra exhaustivo | 5 escenarios × cada operación × {choque, escritura partida, ENOSPC, EIO en `fsync`, `fsync` que miente} × {corte, salida sin corte, corte con canal perdido} = **722 casos** | **0 violaciones** de INV-1…INV-7, salvo el límite del §5 | `tecnico/registro/R2_exhaustiva.json` |
| Corrupción explícita | Byte cambiado, línea del medio borrada, hueco de ceros pegado a una línea válida (con objeto y sin objeto), cola cortada, cola partida de la propia reconciliación | BLOQUEADO en las 4 alteraciones del medio. En las 2 colas cortadas se recupera con COLA_DESCARTADA y conserva la clase | Ídem |
| Mutantes | M1 (todo intento sin DECISION se trata como abandonado, que es el diseño v4 tal como estaba); M2 (anuncio después de escribir); M4 (puerta sin canal); M5 (lector sin resincronización por marcador); M8 (reintento tras ERROR, que es la política (i)) | **5 de 5 detectados** | Ídem |
| Procesos reales en ext4 con numpy (4 hilos) | Manejador frente a máscara: SIGINT, SIGTERM, SIGHUP, SIGQUIT, SIGUSR1 (no manejada) y SIGKILL, × 12 momentos al azar (semilla 20261029) | **Manejador: 0 violaciones en 72 corridas.** Máscara: **9 violaciones de S-2**, DECISION sin PUBLICADO | `tecnico/registro/R1_R2_senales_proceso.json` |

## 5. Límites demostrados (no son defectos que el diseño pueda cerrar solo)

- **`fsync` que miente y canal perdido a la vez.** 15 casos violan INV-1: se reabre después de leer datos, porque el `ABIERTO` se perdió y no hay ningún registro externo. 14 violan INV-3: una decisión calculada queda como NO_DECIDIDO.
  - Con el canal disponible, 0 violaciones.
  - Conclusión: **el ancla externa (R-3) es necesaria, no opcional**. Su preservación fuera del contenedor tiene que verificarse (A-1), y hoy no está verificada.
- **No probado aquí:**
  - dispositivo que falla de verdad (dm-flakey o dm-error) y corte de energía real;
  - concurrencia con la comparación de cabeza dentro del bloqueo en el prototipo integrado (el mecanismo lo probó el revisor en P4 y P5);
  - señales al grupo de procesos, a un hilo concreto, durante un `fsync` largo, ráfagas, SIGSTOP/SIGCONT y SIGSEGV en código C.
- **Doce corridas por combinación no son una garantía universal.** Son evidencia preliminar con una batería que sí detecta el defecto conocido.
