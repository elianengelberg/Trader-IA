# R19: qué se hizo, qué no y por qué (2026-10-22)

## Resumen
- **La matriz de `PLAN_R19.md` no se ejecutó. No hay resultados nuevos de R19.**
- Antes de correrla validé el instrumento con pruebas sintéticas, en un árbol aparte. Esa validación mostró que el criterio de H-SINC del plan («alguna escritura de la foto no termina en 120 s») **no distingue** una cola trabada de una cola larga que drena despacio, que es justo lo que predice H-ENT.
- La misión pide detenerse en ese caso, así que me detuve y propongo una corrección: `PLAN_R19_ENMIENDA_1.md`. Está validada y congelada con hashes (`registro/03_R19_precondiciones_y_congelamiento.txt`). Se ejecuta solo con tu aprobación.

## Lo que se verificó antes de detenerme (hechos)
| Comprobación | Resultado |
|---|---|
| Árboles aislados | `r19_base` = `72ffae5`, sin cambios; `r19_cand` = completa registrada (01+02v3+03). Clones con `--no-local`; el original solo se lee |
| La prueba de R19 y sus ayudantes, base frente a candidata | Idénticos por AST: la prueba, `settle`, `persister`, `register_run`, `_db` y `engine_for`. `build()` difiere solo por un parámetro opcional de 03 (`start=None`), que con su valor por defecto toma el mismo camino. `live.py` es idéntico byte a byte |
| Otras diferencias en `persistence/` | Solo `BacktestRepository`, `_comparable` y `_provenance` (02v3); la prueba de R19 no los usa |
| Entorno | Python 3.11.17, venv_A, igual al freeze de referencia (74 paquetes) |
| Sin operación real | `FakeMarketData`, `PaperExecutionProvider` sin rechazos ni parciales, SQLite en `tmp_path` y `activation=None`. Cada corrida va con `unshare -n` (solo `lo`; una conexión TCP da `Network is unreachable`) y un entorno mínimo, sin credenciales ni proxies |
| Hashes | Plan original `356b6d0d…`, sonda v1 `d0057aa9…`, arnés v1 `ad2735fc…`. Enmienda, plan JSON y herramientas v2: ver el registro 03 |

## La validación que encontró el defecto (pruebas sintéticas, no el experimento)
| Prueba sintética | Qué simula | Criterio original | Enmienda 1 |
|---|---|---|---|
| `test_lenta_con_productor` (bucle activo) | Escrituras lentas que **terminan** y el bucle de fondo con intervalo 0 | Foto de 1.916 escrituras (99,5 % reconciliaciones del bucle); 15 terminan en la espera y 10 más al detener el bucle; quedan más de 1.800 → **«no terminan»: H-SINC (incorrecto)** | La cola avanza: **`lenta_con_productor` → H-ENT (correcto)** |
| `test_trabada` | Una escritura que no termina nunca | H-SINC (correcto) | Ninguna escritura termina en la ventana final sin productor: **`trabada`**. La cabeza de la cola es `order`, parada en `persist → Event.wait` (correcto) |
| `test_lenta_con_productor` (aparcado) | Lo mismo, sin bucle | Correcto | `lenta_sin_productor` (correcto) |
| Errores | Un `RuntimeError("database unavailable during fill")` inyectado y un `ValueError("boom")` | La sonda v1 no los separaba | El inyectado se marca como inyectado y `boom` como no inyectado (correcto) |
| Vaciado pedido por otro llamador | Por ejemplo, el de `stop()` | La sonda v1 esperaba 120 s más: **podía cambiar el resultado** de un `settle()` posterior | Sin espera extra; la prueba sigue igual (correcto) |

## Lo que se sabe hoy de R19
Viene de la evidencia de v3r2. Ver `FALLAS_INTERMITENTES_HECHOS_E_INFERENCIAS.md` en la entrega r3.

**Hechos:**
- `test_partial_fills_and_fees_rebuild_identically_however_often` falló con «persistence writes still in flight»: en la base en 2 de 4 corridas, con cargas de 5,15 y 3,48, y en la integración en 1 de 4, con carga de 5,15.
- Pasó en las 5 corridas con carga ≤ 2,50.
- Es preexistente: falla también en la base.

**Inferencias, sin verificar:**
- que la causa sea la carga;
- que el mecanismo sea el bucle de fondo (H-ENT) y no un problema de sincronización (H-SINC).

## Límites de la evidencia
- **Ninguna falla se atribuye a R19.** No hay corridas nuevas con evidencia del mecanismo.
- El humo de la revisión anterior (1 corrida, sin carga) solo mostró que el bucle de fondo gira y alarga el vaciado. No es una conclusión.
- La enmienda no prueba el intervalo de producción (5 s y 10 s); solo compara el intervalo 0 con el bucle aparcado.
- Con 20 corridas por celda, la tendencia con K es descriptiva: la potencia es baja.

## Qué hace falta para cerrarlo
1. Tu aprobación de `PLAN_R19_ENMIENDA_1.md`, o tus cambios.
2. Correrlo con la máquina sin otra carga, ≈ 70–80 min:
   ```bash
   python3 -I r19_experimento.py plan_r19_enmienda1.json <salida_nueva>
   python3 -I r19_analisis.py <salida_nueva> <salida_nueva>/resultados.json
   ```
3. Según la decisión:
   - **H-ENT:** un parche de pruebas aparte (`_drive_by_hand`).
   - **H-SINC:** un defecto de producto en `tia.runtime.live`, que se reporta y no se toca.
   - **NO REPRODUCIDO o INCONCLUSO:** se informa, sin cambios.
