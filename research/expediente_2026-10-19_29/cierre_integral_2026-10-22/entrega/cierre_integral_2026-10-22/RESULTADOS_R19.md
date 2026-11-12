# R19: resultados del experimento con la enmienda 1 congelada (2026-10-22)

## Clasificación: **NO_REPRODUCIDO**
- La falla de R19 («persistence writes still in flight» en `test_partial_fills_and_fees_rebuild_identically_however_often`) **no se reprodujo en ninguna de las 252 corridas**: 240 de la prueba sola y 12 del módulo completo.
- El instrumento es **válido** según la regla prerregistrada.
- **No hay defecto que corregir y no se inventó ningún arreglo.**

| Capa | Resultado | Evidencia |
|---|---|---|
| Ejecución | 252 de 252 corridas, de 22:13:44 a 22:46:29 UTC; orden aleatorio intercalado, semilla 20261022; `unshare -n` | `evidence/R19_corrida_principal/` (`corridas.jsonl`, `orden.json`, 252 JSON y 252 logs), `evidence/registro/B2_ejecucion_R19.txt` |
| Validez del instrumento (regla de `evidence/registro/B1_PREREGISTRO_EJECUCION_R19.md`) | (i) 0 corridas sin JSON y 0 por límite de tiempo; (ii) 0 fallas sin su registro de vaciado; (iii) 0 trazas de la sonda; 0 códigos inesperados → **INSTRUMENTO VÁLIDO** | `evidence/R19_validez_instrumento.json` |
| Decisión de la enmienda (`r19_analisis.py`, congelado) | **NO REPRODUCIDO**: 0 fallas de las clases de R19 en la prueba sola, ni con el bucle activo (K0, K4 y K8: 0, 0 y 0) ni aparcado (0). 0 trabadas, 0 errores de escritura no inyectados, 0 errores de FK. Candidata frente a base: 0/60 y 0/60 (Fisher p = 1,0) | `evidence/R19_resultados_analisis.json`, `evidence/R19_analisis_salida.txt` |
| Mapeo prerregistrado | NO REPRODUCIDO → **NO_REPRODUCIDO** | `evidence/registro/B1_PREREGISTRO_EJECUCION_R19.md` (`aaa47d55…`), escrito antes de la primera corrida |

## Evidencia separada: lo anterior frente a lo nuevo
| | Antes (v3r2, R10; no se modifica) | Ahora (esta misión) |
|---|---|---|
| Qué se corrió | 4 repeticiones por árbol, con carga **no controlada** de otros trabajos (paridad y mutantes) | 252 corridas; carga controlada con 0, 4 y 8 quemadores; bucle activo y aparcado; orden aleatorio |
| Fallas | Base 2 de 4 y candidata 1 de 4, con cargas 5,15 y 3,48 | **0 de 252** |
| Mecanismo registrado | Ninguno | Por corrida: vaciados, pendientes, ciclos de fondo y carga. Suplementaria: evolución de la cola |

## Medida continua (descriptiva; prerregistrada como **no decisoria**)
Duración del vaciado que afirma `settle()`, en la prueba sola, 20 corridas por celda:

| Árbol | K | Bucle | Mediana | p90 | Máximo | ≥ 8 s | Margen mínimo frente a 10 s | Ciclos de fondo (mediana) |
|---|---|---|---|---|---|---|---|---|
| base | 0 | activo | 7,007 s | 8,229 | **9,013** | 3/20 | **0,99 s** | 152.696 |
| candidata | 0 | activo | 6,742 s | 8,146 | **8,909** | 3/20 | **1,09 s** | 148.557 |
| base | 4 | activo | 0,089 | 0,111 | 0,167 | 0 | 9,83 | 1.001 |
| candidata | 4 | activo | 0,087 | 0,257 | 2,180 | 0 | 7,82 | 1.008 |
| base | 8 | activo | 0,284 | 0,326 | 0,936 | 0 | 9,06 | 2.439 |
| candidata | 8 | activo | 0,300 | 1,080 | 4,490 | 0 | 5,51 | 2.700 |
| base y candidata | 0, 4, 8 | aparcado | 0,05–0,12 | ≤ 0,16 | ≤ 0,26 | 0 | ≥ 9,74 | 0 |

**Corrida suplementaria** (`evidence/R19_suplementaria/`, `R19_suplementaria_resumen.txt`):
- registrador pasivo `registro_cola_r19.py` (`60e9ca3c…`, hasheado antes de usarlo); 24 corridas; no decide nada.
- **K0, bucle activo:**
  - 12.444–14.462 escrituras programadas por prueba (mediana) y hasta unas 9.600 pendientes a la vez;
  - primer vaciado de 6,6–7,6 s;
  - **todas** las escrituras terminaron, y `persistence_flushed` quedó en verdadero en 3 de 3.
- **K8, bucle activo:** unas 200 escrituras, hasta 800 pendientes, vaciado de 0,2–1,3 s.
- **Aparcado:** 31 escrituras y vaciado de 0,05–0,15 s.
- **Evolución de la cola:** con K0 y el bucle activo sube de 31 a cientos o miles en fracciones de segundo y baja a 0 antes de `stop()`. Ver las muestras en el resumen.

## Lectura: hechos e inferencias
**Hechos (de esta corrida):**
- 0 fallas en 252 corridas;
- todas las escrituras terminan;
- ninguna cola trabada;
- ningún error no inyectado;
- con el bucle aparcado, el vaciado tarda menos de 0,3 s en todas las cargas;
- con el bucle activo y **sin** carga, tarda unos 7 s, con un margen mínimo de unos 1 s frente al límite de 10 s;
- con quemadores, el bucle hace 50–150 veces menos ciclos y el vaciado es más corto.

**Inferencias (no verificadas):**
- El tiempo de vaciado lo fija sobre todo el **productor de la prueba** (el bucle con intervalo 0), porque `flush_persistence` espera también las escrituras que se programan mientras espera. No lo fija la carga de CPU.
- Por eso la inferencia I2 de v3r3 («la carga es la causa») **no queda apoyada** por esta corrida: la carga de CPU pura **acorta** el vaciado.
- Las fallas de R10 siguen **sin explicación**: ocurrieron con otra carga (procesos de paridad y mutantes) que los quemadores no reproducen.

## Límites que permanecen
1. **Los quemadores son CPU pura.** No reproducen la carga de R10 (otros procesos Python con memoria e E/S) ni una máquina más lenta, como un runner de CI.
2. **El margen con K0 es estrecho** (unos 1 s). En una máquina más lenta, el vaciado con el bucle activo podría superar 10 s. Es una **inferencia de riesgo**: no se observó.
3. **N = 20 por celda:** 0/20 es compatible con una tasa de falla de hasta 16,8 % por celda (cota superior exacta del IC 95 %, Clopper-Pearson). Con las 120 corridas de bucle activo juntas, la cota es de 3,0 %.
4. **No se probó el intervalo de producción** (5 s y 10 s).

## Corrección
- **No corresponde:** no se reprodujo. No se integra ningún arreglo del producto ni de la prueba.
- **Lo que haría falta** para detectar y comunicar una persistencia incompleta (propuesta, no implementada):

| Control | Hoy | Falta |
|---|---|---|
| Al detener | `stop()` marca `persistence_flushed=False`, deja `last_error` («N persistence write(s) still in flight… the record may be incomplete»), que la instantánea expone, y registra `persistence_flush_incomplete` con los pendientes | Exponer `persistence_flushed` y los pendientes como campo propio del estado o la API (no solo dentro de `last_error`), y un evento de incidente persistido |
| Durante la sesión | Nada | Métrica de profundidad de la cola y antigüedad de la escritura más vieja sin terminar (la «cabeza», como en la sonda). Alerta si la cola crece durante N ciclos (productor más rápido que consumidor) |
| Al reiniciar | La reconstrucción de la cuenta informa `complete` | Si la sesión anterior terminó con `persistence_flushed=False`, bloquear entradas hasta conciliar (hoy depende del resultado de la reconstrucción) |
| En las pruebas | `settle()` con 10 s y el bucle de fondo con intervalo 0 | Opcional, con revisión: conducir los ciclos a mano en las pruebas que hacen `start()` y ciclos manuales (el patrón de 03). **No se aplica** porque H-ENT no quedó confirmada; queda como riesgo de intermitencia en CI (R19) |
