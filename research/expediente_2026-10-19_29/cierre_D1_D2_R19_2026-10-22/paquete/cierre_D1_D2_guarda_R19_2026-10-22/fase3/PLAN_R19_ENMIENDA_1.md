# PLAN_R19 — enmienda 1 (propuesta metodológica, **no ejecutada**)

## Por qué me detuve
- La misión pedía ejecutar `PLAN_R19.md`, salvo que su diseño no permitiera distinguir las hipótesis: en ese caso, detenerse y proponer una corrección antes de ejecutar.
- Antes de congelar nada validé el instrumento con pruebas **sintéticas**, fuera de los árboles del experimento.
- Esa validación mostró que **un criterio de decisión del plan confunde las dos hipótesis**. Por eso **no ejecuté la matriz**.
- Lo que sigue es la corrección propuesta. Está validada con las mismas pruebas sintéticas y congelada con hashes, lista para correr si la aprobás.

## El defecto que impide distinguir H-ENT de H-SINC
- **Criterio original:** H-SINC si «alguna escritura de la foto no termina en 120 s».
- **Supuesto oculto:** que las escrituras pendientes al vencer el plazo son pocas, así que si alguna no termina en 120 s está trabada.
- **Lo que mostró la validación** (`validacion_sonda/v2/`, prueba `test_lenta_con_productor`):
  - las escrituras eran lentas pero todas terminaban, y el bucle de fondo giraba con intervalo 0;
  - en 0,3 s la foto juntó 1.916 escrituras pendientes; el 99,5 % eran reconciliaciones del propio bucle;
  - la cola **siguió avanzando**: 15 escrituras terminaron en la espera y 10 más al detener el bucle;
  - aun así quedaron más de 1.800 sin terminar, solo por volumen.
- **Consecuencia:** con el criterio original, ese caso, que es exactamente H-ENT (lentitud causada por el productor de la prueba), se habría clasificado como **H-SINC**.
- **Por qué podría pasar en el experimento real:** bajo K=8 cada escritura a SQLite es más lenta y el bucle sigue generando reconciliaciones, así que la foto puede ser grande. Con el criterio original, el resultado dependería del tamaño de la cola, no del mecanismo.

## Correcciones
| # | Qué | Original | Enmienda 1 | Evidencia |
|---|---|---|---|---|
| E1 | Criterio de «trabada» (H-SINC) | Alguna escritura de la foto no termina en 120 s | **La cola no avanza.** Después de 120 s con el productor como estaba, se detiene el bucle de fondo y se esperan 60 s más. Es **trabada** solo si en esa ventana final no terminó **ninguna** escritura de la foto. Se registra la cabeza de la cola (la escritura más antigua sin terminar) con su tipo y la cadena de `await` donde está parada | Validación: la cola lenta queda como lenta; la trabada a propósito queda como trabada, con su cabeza (`order`, parada en `persist → Event.wait`) |
| E2 | Errores de escritura | La sonda v1 registraba todas las excepciones sin separar las inyectadas | Cada excepción se clasifica: **inyectada** si es la que lanzan las pruebas (`RuntimeError("database unavailable during <tipo>")`, `test_account_restore.py:75,85`, `test_funding_recovery.py:74`); si no, **no inyectada** (H-SINC) | Validación: `boom` sale como no inyectada; `database unavailable during fill`, como inyectada |
| E3 | Espera extra y resultado de la prueba | v1 esperaba hasta 120 s en **cualquier** vaciado vencido, también el que hace `stop()` (`live.py:1288`). Eso le da tiempo extra a las escrituras y puede hacer pasar el `settle()` siguiente: **el instrumento podía cambiar resultados** | La espera extra se hace **solo** si el vaciado lo pidió `settle()`, cuyo resultado se afirma en la línea siguiente: la prueba ya falló y esperar no cambia nada. El de `stop()` se registra sin esperar | Validación: un vaciado pedido por otro llamador queda «omitida» y la prueba sigue igual |
| E4 | Resultado sin fallas | No estaba previsto | **NO REPRODUCIDO** si no hay ninguna falla de las clases de R19. Se informa como **medida continua y descriptiva**, que no decide, la duración del vaciado afirmado por `settle()` por celda (mediana, máximo y cuántas veces ≥ 8 s frente al límite de 10 s) | — |
| E5 | Qué se registra en cada corrida | Resultado y duración por prueba; el nombre de la prueba que falla solo en el log | La prueba exacta, la excepción y el informe de pytest. En cada vaciado: la prueba, quién lo pidió, el plazo, las pendientes por tipo, si el bucle estaba vivo, la carga y los ciclos de fondo. Carga antes, con quemadores y después; código de salida | Pedido de la misión |
| E6 | Orden de las corridas | Celda por celda, con los quemadores encendidos toda la celda: confunde celda con hora | **Orden aleatorio intercalado** de las 252 corridas, con semilla fija (20261022). Quemadores por corrida, con 3 s de calentamiento, y apagado garantizado | — |
| E7 | Aislamiento | No explícito | Cada pytest corre con `unshare -n` (solo la interfaz `lo`) y un entorno mínimo: sin credenciales, sin proxies, `HOME` y `TMPDIR` propios | Verificado: con `unshare -n` una conexión TCP a 1.1.1.1:443 da `Network is unreachable` |
| E8 | Criterio (b), «la tasa crece con K» | Sin definir | Con el bucle activo y los dos árboles juntos: fallas(K0) ≤ fallas(K4) ≤ fallas(K8) y fallas(K8) > fallas(K0). Descriptivo: con 20 por celda la potencia es baja | — |
| E9 | Errores de FK | «En los logs» | La expresión regular `FOREIGN KEY\|IntegrityError\|ForeignKeyViolation` sobre el log de cada corrida | — |
| E10 | Candidata frente a base | Sin método | Corridas con falla de R19 y bucle activo: candidata frente a base, prueba exacta de Fisher (descriptiva) | — |

## Clasificación de cada falla (implementada en `herramientas/r19_analisis.py`)
| Clase | Condición | Cuenta para |
|---|---|---|
| `trabada` | «persistence writes still in flight», y en la ventana final, sin productor, no terminó ninguna escritura de la foto | H-SINC |
| `error_escritura_no_inyectada` | Una excepción de escritura que no es la inyectada | H-SINC |
| `lenta_con_productor` | Venció el plazo con el bucle de fondo vivo y girando, y la cola siguió avanzando | H-ENT |
| `lenta_sin_productor` | Venció sin bucle vivo (aparcado o ya detenido) y la cola avanzó | Inconcluso |
| `otra_falla` | Cualquier otra cosa | **Nada.** No se atribuye a R19 |

**Ninguna falla se atribuye a R19 sin la medición del vaciado de esa misma prueba.**

## Decisión
- **H-SINC:** si hay alguna falla `trabada`, algún error de escritura no inyectado (en cualquier corrida, también las del módulo) o algún error de FK.
- **NO REPRODUCIDO:** si no hay ninguna falla de R19 en las corridas de la prueba sola.
- **H-ENT:** si se cumplen las cuatro:
  - (a) todas las fallas de R19 son `lenta_con_productor`, con el bucle activo;
  - (b) la tasa crece con K, según E8;
  - (c) ninguna `trabada`;
  - (d) 0 fallas de R19 con el bucle aparcado, en las 3 cargas.
- **INCONCLUSO:** en cualquier otro caso.
- **Qué se hace con cada resultado:** lo mismo que en `PLAN_R19.md`. H-ENT lleva a un parche de pruebas aparte; H-SINC se reporta como defecto de producto y no se toca; los otros se informan.

## Lo que no cambia
- Los árboles: la candidata (01+02v3+03) y la base `72ffae5`. La prueba de R19 y los ayudantes que usa son idénticos por AST. La única diferencia es que `build()` en 03 agrega un parámetro opcional, cuyo valor por defecto da el mismo camino.
- `live.py` es idéntico en los dos árboles.
- La prueba objetivo, K ∈ {0, 4, 8}, el control aparcado, N = 20 por celda, una pasada del módulo por celda, y los 120 s de espera extra.
- **Límite que la enmienda no resuelve:** solo se comparan intervalo 0 y bucle aparcado; el intervalo de producción (5 s y 10 s) no se prueba.

## Cómo correrlo (cuando lo apruebes; ≈ 70–80 min de CPU, sin tocar repositorios)
```bash
H=<este paquete>/herramientas
python3 -I $H/r19_experimento.py plan_r19_enmienda1.json <salida_nueva>
python3 -I $H/r19_analisis.py <salida_nueva> <salida_nueva>/resultados.json
```
- **No correr nada pesado en paralelo:** la carga es un factor del experimento.
