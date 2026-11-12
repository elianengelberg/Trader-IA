# ruff: noqa: E501  (la tabla DESCRIPCION son datos: una fila por archivo de evidencia)
"""Genera 07_MANIFIESTO_EVIDENCIA.md a partir de los archivos REALES de evidencia/: SHA-256, qué muestra, cómo se
produjo y su clase. Un archivo de evidencia sin descripción, o una descripción sin archivo, es un error.
Uso: python3 -I manifiesto_evidencia.py <paquete> [--pendiente <archivo> ...]   (solo para el ZIP candidato)"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

R = "REGENERADO por `ejecutar_verificacion.sh` (y comparado en la extracción limpia: `G6_*`)"
U = "PRODUCIDO UNA VEZ en esta misión (el estado inicial y las ejecuciones largas no se repiten); comando indicado"
DESCRIPCION = {
    "A1_repo_estado_inicial.txt": (U, "HEAD, rama, origin, commits sin publicar, `git status --porcelain --ignored` y su huella, `git diff --stat` al empezar", "comandos git de solo lectura"),
    "A2_huella_fuerte_inicial.txt": (U, "Huella fuerte del repositorio al empezar; idéntica a la del cierre de v0.5 (`91_*`)", "`pruebas/estado_repositorio.sh` de v0.5"),
    "A3_inventario_inicial.json": (U, "Inventario de preservación: T y T-MULTI frente a HEAD, artefactos protegidos, 25 ZIP y 18 manifiestos", "`auditoria/inventario_preservacion.py`"),
    "A3_inventario_inicial.txt": (U, "Resumen legible de A3: sin problemas", "ídem"),
    "B1_zip_v05.txt": (R, "ZIP v0.5: SHA-256, `verificar_zip.py`, `unzip -t` y comprobación independiente (lista, hashes, sin enlaces)", "paso B1"),
    "B2_registro_acciones_v05.txt": (R, "Cadena del registro de acciones de v0.5: válida; las fechas son mtime y no siguen el orden cronológico (D-4)", "paso B2"),
    "B3_95_recalculado.txt": (U, "`evidencia/95_*` de v0.5 recalculado con su propio script: idéntico byte a byte", "`verificar_reproduccion_limpia.py` de v0.5 sobre el ZIP B y su extracción (temporales efímeros)"),
    "B4_etapa13_antes_despues.txt": (R, "Etapa 13: 12 escenarios adversariales; v0.5 no detecta 3 (D-1); la corrección 0001 los detecta todos", "paso B4"),
    "B5_afirmaciones_vs_evidencia_v05.md": (R, "27 cifras declaradas por v0.5 frente a su evidencia y a la colección real de pytest: 26 coinciden; C14 = D-3", "paso B5"),
    "B5_afirmaciones_vs_reproduccion.md": (U, "Las mismas 27 afirmaciones frente a la evidencia de la REPRODUCCIÓN de esta misión", "`afirmaciones_vs_evidencia.py` sobre la reproducción"),
    "B6_estatico_v05.txt": (R, "Análisis estático (AST): ningún módulo importa red; solo P4 lanza el proceso de cálculo; ACCION = NINGUNA", "paso B6"),
    "B7_parches.txt": (U, "Parches 0001–0007: `git apply` sobre HEAD y origin exportados y suite en las dos copias (de la reproducción)", "copia de `60_*` y `61_*` de la reproducción"),
    "B8_reproduccion_v05.txt": (U, "Reproducción completa de v0.5 desde una extracción NUEVA del ZIP final: resumen, comparación con la evidencia del ZIP, fugas de TMPDIR y entradas no regulares", "`ejecutar_todo.sh` de v0.5 (81 min con carga concurrente)"),
    "C1_declaracion_T.txt": (R, "Declaración de T: el `.bin` es la forma canónica del `.json`; los hashes coinciden con los archivos actuales; la copia es idéntica a v0.5", "paso C1"),
    "D2_temporales_antes_despues.txt": (U, "D-2: temporales que dejan las sondas y el adaptador, antes (19 y 11) y después (0 y 0) de la corrección 0002", "sondas y pruebas de P1 con TMPDIR nuevos"),
    "F1_pruebas_protocolo.txt": (R, "Las 72 pruebas del protocolo cuantitativo (sintéticas)", "paso F1"),
    "F2_ruff.txt": (R, "Estilo del código nuevo", "paso F2"),
    "F4_calibracion_plan.txt": (R, "Calibración: costo medido, prueba de humo, bloqueo sin autorización y SHA-256 de los parámetros. NO es la calibración", "paso F4"),
    "F5_criba_candidatas.txt": (R, "IR requerido por horizonte, ventaja mínima por operación de las candidatas y tabla de δ", "paso F5"),
    "G1_repo_estado.txt": (R, "Estado del repositorio al verificar y comparación de la huella fuerte con A2 (desviación I-1 identificada)", "paso G1–G2"),
    "G2_huella_fuerte.txt": (R, "Huella fuerte del repositorio al verificar", "paso G1–G2"),
    "G3_inventario.txt": (R, "Inventario de preservación al verificar", "paso G3–G4"),
    "G4_inventario_comparado.txt": (R, "Inventario final frente al inicial (A3): repositorio, T, T-MULTI, ZIP y manifiestos", "paso G3–G4"),
    "G5_paquete_intacto.txt": (R, "Este paquete no cambió durante su propia verificación (lógica de la etapa 13 corregida)", "paso G5"),
    "G6_reproduccion_desde_zip.txt": (U, "La verificación ejecutada desde una extracción limpia del ZIP candidato, comparada con la de la copia de trabajo", "`ejecutar_verificacion.sh` en la extracción limpia"),
    "I1_incidente_venv.txt": (U, "Incidente I-1: un `.pyc` que creó esta misión en el `.venv` del repositorio, su reversión y la diferencia que queda", "registro manual con `stat`, `sha256sum` y la huella"),
}


def main(paq: Path, pendientes: list[str]) -> int:
    ev = paq / "evidencia"
    presentes = sorted(p.name for p in ev.iterdir() if p.is_file())
    sin_desc = [n for n in presentes if n not in DESCRIPCION]
    sin_archivo = [n for n in DESCRIPCION if n not in presentes and n not in pendientes]
    lineas = ["# 07 — Manifiesto de la evidencia", "",
              "Generado por `auditoria/manifiesto_evidencia.py` a partir de los archivos reales; el SHA-256 de cada uno "
              "también figura en `SHA256SUMS.txt`.", "",
              "**Clases:**",
              f"- **R:** {R};",
              f"- **U:** {U}.", "",
              "**Lo heredado de v0.5 no se copia:** se referencia por el SHA-256 de su ZIP (`5bf9bc5d…`). Lo que solo "
              "se inspeccionó se marca así en `01_RESULTADOS_AUDITORIA.md`.", "",
              "| Archivo | Clase | Qué muestra | Cómo se produjo | SHA-256 |", "|---|---|---|---|---|"]
    for n in presentes:
        clase, que, como = DESCRIPCION.get(n, ("?", "SIN DESCRIPCIÓN", "?"))
        h = hashlib.sha256((ev / n).read_bytes()).hexdigest()
        lineas.append(f"| `{n}` | {'R' if clase == R else 'U' if clase == U else '?'} | {que} | {como} | `{h[:16]}…` |")
    for n in pendientes:
        lineas.append(f"| `{n}` | U | {DESCRIPCION[n][1]} | PENDIENTE: se agrega tras la extracción limpia del ZIP candidato | — |")
    (paq / "07_MANIFIESTO_EVIDENCIA.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"{len(presentes)} archivos; sin descripción: {sin_desc or 'ninguno'}; descritos sin archivo: {sin_archivo or 'ninguno'}")
    return 1 if sin_desc or sin_archivo else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), sys.argv[3::2] if "--pendiente" in sys.argv else []))
