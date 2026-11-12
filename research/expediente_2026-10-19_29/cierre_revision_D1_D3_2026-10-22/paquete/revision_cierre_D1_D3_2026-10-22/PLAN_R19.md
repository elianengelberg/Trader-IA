# Plan mínimo para reproducir R19 bajo carga (preparado, **no ejecutado**)

## Qué es R19 y qué se sabe hoy
- **La prueba:** `tests/integration/test_account_restore.py::test_partial_fills_and_fees_rebuild_identically_however_often`.
- **Cómo falló:** con «persistence writes still in flight» (límite de 10 s de `settle()`). Bajo carga de CPU ≈5 falló en la base (2 de 4) y en la integración (1 de 4); con carga ≤2,5 pasó siempre (`evidencia/R10_*` de v3r2).
- **Patrón:** el mismo que la prueba que corrige 03. Llama a `start()`, que lanza el bucle propio de la sesión con intervalo 0, y después hace los ciclos a mano.
- **Humo de hoy, una corrida sin carga** (`evidencia/U3_humo_r19/`). Muestra el mecanismo, **no** concluye:

| | Bucle de fondo activo | Aparcado (control) |
|---|---|---|
| Ciclos de fondo | 146.491 | 0 |
| Espera de vaciado más larga | 6,74 s | 0,05 s |
| Duración de la prueba | 6,95 s | 0,24 s |
| Resultado | Pasa, con 3,3 s de margen sin carga | Pasa |

## Las dos hipótesis y cómo distinguirlas
- **H-ENT (limitación del entorno sobre un artefacto de la prueba):**
  - el bucle de fondo, que en producción no existe con intervalo 0 (vivo 5 s, papel 10 s), compite por la CPU con las escrituras;
  - bajo carga, vaciar la cola tarda más de 10 s;
  - las escrituras **terminan**, solo tarde, y el registro queda completo.
- **H-SINC (problema de sincronización de la persistencia, del producto):**
  - alguna escritura **no termina nunca** (tarea trabada o bloqueo), falla con una excepción no inyectada, o llega en un orden que el registro no tolera;
  - o la prueba falla aunque no haya productor concurrente.

## Instrumento (listo y probado)
- **`herramientas/sonda_r19.py`, plugin de pytest:** solo mide y no cambia el resultado de ninguna prueba. Registra:
  - ciclos de fondo frente a manuales;
  - en cada `flush_persistence`: pendientes al entrar, duración y resultado;
  - **si vence el plazo**, la foto de las escrituras pendientes en ese instante y si terminan en los 120 s siguientes;
  - excepciones de escritura;
  - resultado y duración de cada prueba, y la carga del sistema.
  - **Control opcional `R19_PARK=1`:** aparca el bucle de fondo después de `start()`, igual que `_drive_by_hand` en 03.
- **`herramientas/r19_carga.sh`:**
  - corre N repeticiones bajo K procesos que queman CPU, con apagado garantizado por `trap` y `timeout`;
  - deja un JSON y un log por corrida y un `resumen.csv`;
  - no toca ningún repositorio.

## Matriz (mínima)
| Factor | Niveles |
|---|---|
| Árbol | Candidata completa (01+02v3+03) y base `72ffae5`. La prueba de R19 es idéntica en ambos |
| Carga K (quemadores de CPU, 4 núcleos) | 0, 4, 8 |
| Bucle de fondo | Activo (`R19_PARK=0`) y aparcado (`R19_PARK=1`) |
| Repeticiones N | 20 por celda; 12 celdas, 240 corridas, ≈ 1 h |
| Variante de carga, opcional | `taskset -c 0` (un solo núcleo) en lugar de quemadores |

**Selección:**
- la prueba sola;
- además, una pasada de cada celda con el módulo entero (`test_account_restore.py`), por las interacciones.
- Siempre con `-rA`, para que cada falla quede **nombrada**. Es la lección de D2: no volver a atribuir fallas sin nombre.

## Criterios de decisión, fijados antes de correr
1. **H-ENT confirmada** si se cumplen las cuatro:
   - (a) hay fallas solo con el bucle activo;
   - (b) su tasa crece con K;
   - (c) en **todas** las fallas, las escrituras de la foto terminan después (`no_terminaron` = 0) y no hay errores de escritura;
   - (d) con el bucle aparcado, 0 fallas en las 3 cargas.
2. **H-SINC** si se da **cualquiera** de estas:
   - alguna escritura de la foto no termina en 120 s;
   - hay una excepción de escritura no inyectada;
   - hay fallas con el bucle aparcado y escrituras trabadas;
   - aparecen errores de orden (FK) en los logs.
3. **Inconcluso** si hay fallas con el bucle aparcado, pero todas drenan (lentitud pura bajo carga):
   - se mide la distribución del tiempo de vaciado y se informa;
   - **no** se sube el límite como «arreglo».

## Qué se hace con el resultado (no ahora)
- **Con H-ENT:**
  - un parche de **pruebas** aparte (no se amplía 03), con `_drive_by_hand` en las pruebas que conducen los ciclos a mano;
  - cada archivo con su propia evidencia antes y después en esta misma matriz;
  - revisión separada.
- **Con H-SINC:** es un defecto de producto en `tia.runtime.live`. Se reporta con la evidencia y **no** se toca en esta línea de trabajo.
- **Inconcluso:** se reporta. No hay cambio sin una decisión tuya.

## Comandos (ejecutables; no tocan el repositorio original)
```bash
S=<scratchpad>; W=$S/cierre_revision_D1_D3_2026-10-22; PY=$S/cierre_D1_D3_2026-10-22/entorno/venv_A/bin/python
T="tests/integration/test_account_restore.py::test_partial_fills_and_fees_rebuild_identically_however_often"
# árboles (clones aislados de 72ffae5; candidata con los parches de v3r2)
git clone -q --no-local /home/user/Trader-IA $W/r19_base && git -C $W/r19_base checkout -q --detach 72ffae5d2698440c8f1afaff12e07bd8adde66fb
git clone -q --no-local $W/r19_base $W/r19_cand && for p in 01 02v3 03; do git -C $W/r19_cand apply $W/extraccion/entrega_integracion_D1_D3_v3r2_2026-10-22/parches/${p}_*.patch; done
# las 12 celdas
for A in r19_cand r19_base; do for K in 0 4 8; do for PARK in 0 1; do
  bash $W/herramientas/r19_carga.sh $W/$A $PY $W/r19_resultados/$A/K${K}_park${PARK} 20 $K $PARK "$T"
done; done; done
# resumen por celda: fallas, ciclos de fondo, vaciado máximo, escrituras que no terminaron, errores
for f in $W/r19_resultados/*/*/resumen.csv; do echo "$f"; awk -F, 'NR>1{n++; if($5!="-")fa++; if($9>0)nt++; if($10>0)er++; if($7>m)m=$7} END{print "  corridas",n,"fallas",fa+0,"no_terminaron>0:",nt+0,"errores:",er+0,"vaciado máx",m}' "$f"; done
```
