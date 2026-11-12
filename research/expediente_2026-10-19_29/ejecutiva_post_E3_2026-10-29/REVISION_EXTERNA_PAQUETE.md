# Revisión externa: qué artefactos recibe el revisor y qué afirmaciones tiene que comprobar

**Revisor válido:**
- una persona, u otro sistema de **otro proveedor**, que no haya escrito ni encargado nada de E3, de la reparación, del v3, del v4/v4.1, de SL-v1 ni de E4;
- **no cuentan** el autor ni los agentes que este lanzó (revisor v4, verificador de la matriz, lector y adjudicador de SL-v1): son de la misma familia de modelos, corrieron en el mismo contenedor y los lanzó el autor.

**Acceso:** solo lectura de los artefactos; ninguna clave ni autorización; red no necesaria salvo para T2 (OpenTimestamps), si ya existiera.

## Artefactos que recibe (rutas relativas al scratchpad)

1. `cierre_decisivo_v4_2026-10-29/`, completo, con su `MANIFEST_CIERRE_DECISIVO.sha256` (sha `94d629c6…`, 527 archivos).
2. `ejecutiva_post_E3_2026-10-29/`, completo, con su manifiesto.
3. **Insumos congelados**, por hash (no hace falta que reciba los datos de mercado):
   - el prerregistro v3 `279a865f…`;
   - NOTAS, Adenda 1, Adenda 3 y Adenda R;
   - `p0_pasada2.py` `d05c8dd5…` y `conciliacion.py` `6f764845…`;
   - las páginas archivadas que usó SL-v1, copiadas en `segunda_lectura/paquete*/paginas/`.
4. **Para reproducir el cálculo de la ventana:** las 757 series. Solo `estado` y `NT`, sin precios.
   - Se pasan como tarball verificado (`…_DATOS.tar.gz`, sha `0562b919…`).
   - El revisor lo extrae en **su** entorno, nunca en el de ejecución.

## Afirmaciones concretas que tiene que comprobar (cada una con su procedimiento)

| # | Afirmación | Cómo comprobarla | Qué la refuta |
|---|---|---|---|
| A1 | La candidata A es INVÁLIDA según las reglas congeladas y la adjudicación de SL-v1 | Repetir `segunda_lectura/herramientas/calcular_ventana.py` con `calculo/omitidos/variante_BLVT/fallas_extra_L2.json` | Un inicio < 2023-05-30 o ≥ 156 semanas con esas entradas |
| A2 | El anuncio BLVT tiene dos fechas por par y la regla R-E de SL-v1 tiene dos frases que apuntan a fechas distintas | Leer la página de `adjudicacion/paquete/paginas/` y la R-E de `ENCARGO_LECTOR.md` | Que el texto tenga una sola fecha, o que R-E no contenga la cláusula de tokens apalancados |
| A3 | SL-v1 se congeló antes de leer, y la lectura y la adjudicación fueron ciegas | Horas y hashes de `registro/CONGELACION_SL-v1.txt`, `LANZAMIENTO_*`, `RECEPCION_*`. `ITEMS.json` y `CASOS.json` no traen fechas ni consecuencias | Hashes que no coinciden, u orden temporal inverso (las horas las generó el mismo entorno: es un límite declarado) |
| A4 | La conciliación congelada reproduce byte a byte la segunda pasada | Repetir el control (`calculo/control_pasada2`) | Cualquier diferencia en `eventos.json`, `salidas.json` o `conciliacion.json` |
| A5 | El escaneo Ω encontró remociones spot que la extracción no tenía como eventos (BLVT, MC, PLA, MATIC, QUICK, STRAX) | Releer esas 11 páginas | Que alguna no remueva un par spot X/USDT |
| A6 | La máquina de estados v4.1 no reabre después de leer datos ni clasifica mal, salvo con un disco que miente y sin ancla | Repetir `tecnico/r2_maquina/prueba_exhaustiva.py` y **escribir mutantes propios** | Una violación fuera del límite declarado, o un mutante propio que no se detecte |
| A7 | El validador L-17 rechaza cada vector negativo por la regla prevista y acepta las variaciones válidas | Repetir `ejecutiva_post_E3_2026-10-29/l17/analisis_rechazos.py` y agregar vectores | Un rechazo por una regla distinta de la prevista, o una entrada válida rechazada |
| A8 | La zona aislada tapa las 18 rutas protegidas sin modificar nada | Repetir `registro/prueba_zona_aislada.txt` en una copia | Archivos visibles dentro, o un cambio de hash afuera |
| A9 | El núcleo de E4 no mira el futuro, y su tasa de falsos positivos con efecto nulo ≈ α | Repetir `e4_xsrev_prospectivo/codigo/pruebas_sinteticas.py`. **Escribir una fuga deliberada** y comprobar que alguna prueba falla | Una fuga que no se detecte, o una tasa nula fuera de [0,005; 0,06] |
| A10 | El prerregistro de E4 coincide con P19 salvo los dos cambios declarados (prospectivo; IC como métrica principal) | Comparar `PRERREGISTRO_E4.md` §1–§8 con P19 | Otro cambio no declarado |

## Cuestiones que el revisor **no** decide (son tuyas)

- Reabrir E3.
- Autorizar el sellado.
- Autorizar el ancla y los push a `registros`.
- Autorizar el inicio de E4.
