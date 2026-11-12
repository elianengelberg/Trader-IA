# 07 — Manifiesto de la evidencia

Generado por `auditoria/manifiesto_evidencia.py` a partir de los archivos reales; el SHA-256 de cada uno también figura en `SHA256SUMS.txt`.

**Clases:**
- **R:** REGENERADO por `ejecutar_verificacion.sh` (y comparado en la extracción limpia: `G6_*`);
- **U:** PRODUCIDO UNA VEZ en esta misión (el estado inicial y las ejecuciones largas no se repiten); comando indicado.

**Lo heredado de v0.5 no se copia:** se referencia por el SHA-256 de su ZIP (`5bf9bc5d…`). Lo que solo se inspeccionó se marca así en `01_RESULTADOS_AUDITORIA.md`.

| Archivo | Clase | Qué muestra | Cómo se produjo | SHA-256 |
|---|---|---|---|---|
| `A1_repo_estado_inicial.txt` | U | HEAD, rama, origin, commits sin publicar, `git status --porcelain --ignored` y su huella, `git diff --stat` al empezar | comandos git de solo lectura | `1c84c3109f529182…` |
| `A2_huella_fuerte_inicial.txt` | U | Huella fuerte del repositorio al empezar; idéntica a la del cierre de v0.5 (`91_*`) | `pruebas/estado_repositorio.sh` de v0.5 | `95708d259ea6fc2a…` |
| `A3_inventario_inicial.json` | U | Inventario de preservación: T y T-MULTI frente a HEAD, artefactos protegidos, 25 ZIP y 18 manifiestos | `auditoria/inventario_preservacion.py` | `147c6386bdcd000a…` |
| `A3_inventario_inicial.txt` | U | Resumen legible de A3: sin problemas | ídem | `03586db77635250a…` |
| `B1_zip_v05.txt` | R | ZIP v0.5: SHA-256, `verificar_zip.py`, `unzip -t` y comprobación independiente (lista, hashes, sin enlaces) | paso B1 | `681de80c0f915733…` |
| `B2_registro_acciones_v05.txt` | R | Cadena del registro de acciones de v0.5: válida; las fechas son mtime y no siguen el orden cronológico (D-4) | paso B2 | `dd623008d052bbe6…` |
| `B3_95_recalculado.txt` | U | `evidencia/95_*` de v0.5 recalculado con su propio script: idéntico byte a byte | `verificar_reproduccion_limpia.py` de v0.5 sobre el ZIP B y su extracción (temporales efímeros) | `07c05efa9c8520b6…` |
| `B4_etapa13_antes_despues.txt` | R | Etapa 13: 12 escenarios adversariales; v0.5 no detecta 3 (D-1); la corrección 0001 los detecta todos | paso B4 | `0ea65bf41d93f54d…` |
| `B5_afirmaciones_vs_evidencia_v05.md` | R | 27 cifras declaradas por v0.5 frente a su evidencia y a la colección real de pytest: 26 coinciden; C14 = D-3 | paso B5 | `b7808a6887b6bf56…` |
| `B5_afirmaciones_vs_reproduccion.md` | U | Las mismas 27 afirmaciones frente a la evidencia de la REPRODUCCIÓN de esta misión | `afirmaciones_vs_evidencia.py` sobre la reproducción | `451b2e98899f0719…` |
| `B6_estatico_v05.txt` | R | Análisis estático (AST): ningún módulo importa red; solo P4 lanza el proceso de cálculo; ACCION = NINGUNA | paso B6 | `4280e8e3a327ef4c…` |
| `B7_parches.txt` | U | Parches 0001–0007: `git apply` sobre HEAD y origin exportados y suite en las dos copias (de la reproducción) | copia de `60_*` y `61_*` de la reproducción | `ca0ec82262fff5cc…` |
| `B8_reproduccion_v05.txt` | U | Reproducción completa de v0.5 desde una extracción NUEVA del ZIP final: resumen, comparación con la evidencia del ZIP, fugas de TMPDIR y entradas no regulares | `ejecutar_todo.sh` de v0.5 (81 min con carga concurrente) | `f156fbcb6b845441…` |
| `C1_declaracion_T.txt` | R | Declaración de T: el `.bin` es la forma canónica del `.json`; los hashes coinciden con los archivos actuales; la copia es idéntica a v0.5 | paso C1 | `30df26e9f41e3716…` |
| `D2_temporales_antes_despues.txt` | U | D-2: temporales que dejan las sondas y el adaptador, antes (19 y 11) y después (0 y 0) de la corrección 0002 | sondas y pruebas de P1 con TMPDIR nuevos | `f35bf286e0b57a15…` |
| `F1_pruebas_protocolo.txt` | R | Las 72 pruebas del protocolo cuantitativo (sintéticas) | paso F1 | `2d163990c4da2403…` |
| `F2_ruff.txt` | R | Estilo del código nuevo | paso F2 | `82b3e6a6c090a576…` |
| `F4_calibracion_plan.txt` | R | Calibración: costo medido, prueba de humo, bloqueo sin autorización y SHA-256 de los parámetros. NO es la calibración | paso F4 | `027de4595e365ea9…` |
| `F5_criba_candidatas.txt` | R | IR requerido por horizonte, ventaja mínima por operación de las candidatas y tabla de δ | paso F5 | `14b5c1bff2e71132…` |
| `G1_repo_estado.txt` | R | Estado del repositorio al verificar y comparación de la huella fuerte con A2 (desviación I-1 identificada) | paso G1–G2 | `4b8af670b495cb64…` |
| `G2_huella_fuerte.txt` | R | Huella fuerte del repositorio al verificar | paso G1–G2 | `2480281365f6ff29…` |
| `G3_inventario.txt` | R | Inventario de preservación al verificar | paso G3–G4 | `03586db77635250a…` |
| `G4_inventario_comparado.txt` | R | Inventario final frente al inicial (A3): repositorio, T, T-MULTI, ZIP y manifiestos | paso G3–G4 | `a02e405cf673261b…` |
| `G5_paquete_intacto.txt` | R | Este paquete no cambió durante su propia verificación (lógica de la etapa 13 corregida) | paso G5 | `0059b8bb83f83d54…` |
| `G6_reproduccion_desde_zip.txt` | U | La verificación ejecutada desde una extracción limpia del ZIP candidato, comparada con la de la copia de trabajo | `ejecutar_verificacion.sh` en la extracción limpia | `03b59a6a541ac2d5…` |
| `I1_incidente_venv.txt` | U | Incidente I-1: un `.pyc` que creó esta misión en el `.venv` del repositorio, su reversión y la diferencia que queda | registro manual con `stat`, `sha256sum` y la huella | `b76e8444c0e698f0…` |
