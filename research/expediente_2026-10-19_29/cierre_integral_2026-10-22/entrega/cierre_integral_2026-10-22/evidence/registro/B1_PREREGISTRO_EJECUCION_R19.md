# Prerregistro de la ejecución de R19, escrito ANTES de la primera corrida

- **Qué se ejecuta:** el plan congelado `plan_r19_enmienda1.json` (`a717249d…`), con las herramientas congeladas:
  - `sonda_r19_v2.py` (`2b68b873…`);
  - `r19_experimento.py` (`69253f71…`);
  - `r19_analisis.py` (`afa61795…`).
- **Origen:** todo se toma de la extracción limpia del paquete `410ae629…`.
- **Sin cambios:** ni los criterios ni el instrumento, ni antes ni después de ver resultados.

## Parámetros (los del plan, sin cambios)
| Parámetro | Valor |
|---|---|
| Árboles | `r19_cand` (01+02v3+03) y `r19_base` (`72ffae5`). Verificados contra el registro 03: HEAD, archivos, `live.py`, la prueba y todo el código `tia` |
| Prueba | `tests/integration/test_account_restore.py::test_partial_fills_and_fees_rebuild_identically_however_often` |
| Módulo | `tests/integration/test_account_restore.py`, 1 pasada por celda |
| K, quemadores de CPU | 0, 4, 8 (4 núcleos) |
| Bucle de fondo | Activo (park 0) y aparcado (park 1) |
| N | 20 corridas de la prueba sola por celda, más 1 del módulo: 12 celdas, 252 corridas |
| Orden | Aleatorio intercalado, semilla 20261022 |
| Calentamiento de los quemadores | 3 s |
| Espera extra | 120 s con el productor como estaba; después, 60 s con el bucle detenido |
| Límite por corrida | 1.200 s |
| Aislamiento | `unshare -n`, entorno mínimo, sin credenciales |

## Clasificación (la de `r19_analisis.py`, congelada)
- **`trabada`:** la cola no avanza en la ventana final, sin productor → H-SINC.
- **`error_escritura_no_inyectada`** → H-SINC.
- **`lenta_con_productor`** → H-ENT.
- **`lenta_sin_productor`** → Inconcluso.
- **`otra_falla`** → no se atribuye.

La decisión de la enmienda es H-SINC, NO REPRODUCIDO, H-ENT o INCONCLUSO, con los criterios (a) a (d).

## Mapeo a las categorías de esta misión (decidido ahora, antes de correr)
Se aplica en este orden de precedencia:
1. **BLOQUEADO:** la matriz no puede completarse (falla del entorno, del disco o del driver) y lo corrido no alcanza para decidir.
2. **INSTRUMENTO_INVALIDO:** se cumple cualquiera de estas condiciones:
   - (i) más del 5 % de las corridas (más de 12 de 252) terminan sin el JSON de la sonda o por el límite de tiempo;
   - (ii) alguna falla con «persistence writes still in flight» sin el registro del vaciado de esa prueba, es decir, el instrumento no la capturó;
   - (iii) una excepción de la propia sonda (`sonda_r19_v2` en una traza) en cualquier registro.
3. Si el instrumento es válido, se traduce la decisión de la enmienda:
   - **H-SINC → REPRODUCIDO**, defecto de sincronización de la persistencia, del producto. Corrección mínima en el producto, en una copia aparte, con prueba de regresión.
   - **H-ENT → REPRODUCIDO**, falla reproducida con su mecanismo: el bucle de fondo de la prueba con intervalo 0. Corrección mínima **de la prueba** (`_drive_by_hand`), en una copia aparte, repitiendo las celdas que fallaron.
   - **NO REPRODUCIDO → NO_REPRODUCIDO.** No se inventa un arreglo. Se determinan los controles que hacen falta para detectar y comunicar una persistencia incompleta.
   - **INCONCLUSO → RESULTADO_INCONCLUSO.**

## Evidencia por corrida que el instrumento congelado SÍ registra
- Identificador, árbol, K, park, réplica y semilla de orden.
- Duración, código de salida y prueba que falla, con su excepción.
- Por cada vaciado: escrituras pendientes por tipo al entrar, duración, resultado, si el bucle estaba vivo, ciclos de fondo y carga.
- Al vencer el plazo: la foto, el avance en la espera, el avance sin productor y la cabeza de la cola.
- Errores de escritura con su origen (inyectado o no).
- Procesos ejecutables y fracción de CPU de pytest.

## Lo que el instrumento congelado NO registra y cómo se cubre
- **Faltan:** escrituras generadas y completadas, la evolución temporal de la cola, la duración de `stop()` y si la reconstrucción quedó completa.
- **Cómo se cubre:** con una **corrida suplementaria, separada y posterior**, que **no decide nada**:
  - un registrador pasivo aparte (`registro_cola_r19.py`), escrito y hasheado antes de esa corrida;
  - matriz reducida: 2 árboles × K{0, 8} × park{0, 1} × 3 réplicas;
  - salida en otra carpeta.
- **Por qué no se mezcla con la principal:** agregar un instrumento a la corrida principal la desviaría del plan congelado.

## Desviaciones conocidas antes de correr
- El contenedor se reinició entre misiones; todos los archivos y hashes se reverificaron (registro B0).
- En `.git/config` de los dos árboles se deshabilitó el push al repositorio protegido. No cambia ningún archivo del árbol ni su estado.
