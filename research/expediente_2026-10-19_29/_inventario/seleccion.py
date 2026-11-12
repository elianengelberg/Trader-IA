"""Selección curada del scratchpad para versionar en research/expediente_2026-10-19_29/.
Modo `plan`: lista lo que entra y lo que sale (con motivo) y totales. Modo `copiar <destino>`: copia lo que entra.
Uso: python3 -I -B seleccion.py <scratchpad> plan <salida_dir> | copiar <destino>"""
import os
import shutil
import sys

FUENTES = [
    # (entrada del scratchpad, línea)
    ("experimentos/E1_bot_datos_reales_2026-10-19", "E1"),
    ("experimentos/E2_descubrimiento_2026-10-19", "E2"),
    ("expediente_metodologico_2026-10-20", "metodologia"),
    ("fase_documental_2026-10-20", "metodologia"),
    ("fx3_expediente", "metodologia"),
    ("hoja_de_ruta_confirmatoria_2026-10-21", "metodologia"),
    ("calibracion_AS1_2026-10-21/entrega", "metodologia"),
    ("decisiones_metodologicas_2026-10-21/entrega", "metodologia"),
    ("mision_cierre_2026-10-21/entrega", "metodologia"),
    ("mision_simulacion_2026-10-21/entrega", "motor"),
    ("mision_simulacion_2026-10-21/INFORME_SIM1.md", "motor"),
    ("mision_simulacion_2026-10-21/CRITERIO_SUFICIENCIA_TECNICA.md", "motor"),
    ("integracion_parche_D1_D3_2026-10-21/entrega", "motor"),
    ("integracion_parche_D1_D3_2026-10-21/entrega_build", "motor"),
    ("cierre_D1_D3_2026-10-22/entrega", "motor"),
    ("cierre_D1_D2_R19_2026-10-22/paquete", "motor"),
    ("cierre_revision_D1_D3_2026-10-22/paquete", "motor"),
    ("cierre_revision_D1_D3_2026-10-22/INFORME_CIERRE_REVISION.md", "motor"),
    ("cierre_revision_D1_D3_2026-10-22/PLAN_R19.md", "motor"),
    ("cierre_revision_D1_D3_2026-10-22/COMANDOS_REPRODUCCION.md", "motor"),
    ("decision_final_D1_D3_2026-10-22/entrega", "motor"),
    ("cierre_integral_2026-10-22/entrega", "motor"),
    ("revision_adversaria_2026-10-25", "motor"),
    ("entrega_iniciativa_tecnica_2026-10-25", "motor"),
    ("entrega_integracion_controlada_2026-10-25", "motor"),
    ("entrega_direccion_tecnica_2026-10-26", "motor_y_E3"),
    ("experimentos/E3_seleccion_posicion_2026-10-19", "E3"),
    ("experimentos/E3R_desbloqueo_2026-10-26", "E3"),
    ("decision_E3H1H2_2026-10-26", "E3"),
    ("reparacion_E3H1H2_2026-10-26", "E3"),
    ("revision_independiente_E3H1H2_2026-10-26", "E3"),
    ("cierre_bloqueantes_E3H1H2_2026-10-27", "E3"),
    ("paquete_revision_independiente_E3H1H2_2026-10-28", "E3"),
    ("entrega_revision_independiente_2026-10-28/SHA256SUMS", "E3"),
    ("revision_adversarial_E3H1H2_2026-10-28", "E3"),
    ("revision_independiente_diseno_v4_2026-10-28", "E3"),
    ("cierre_decisivo_v4_2026-10-29", "E3"),
    ("ejecutiva_post_E3_2026-10-29", "E3_cierre_y_E4"),
    ("revision_adversarial_E4_2026-10-29", "E4"),
]
# ZIP de entrega canónicos (pequeños, sin datos de terceros, con su SHA256SUMS): se versionan tal cual.
ZIPS = ["SOLUCION_FINAL_TRADER_IA_v0.5_2026-10-20.zip", "AUDITORIA_PARALELA_P1_P2_P4_2026-10-20.zip",
        "CIERRE_FINAL_P1_P2_P4_2026-10-20.zip", "SOLUCION_VERIFICADA_P1_P2_P4_2026-10-20.zip",
        "CIERRE_AUDITORIA_v0.5_Y_PLAN_CUANTITATIVO_r1_2026-10-21.zip", "CALIBRACION_AS1_PEC-1.0_2026-10-21.zip",
        "DECISIONES_METODOLOGICAS_Y_PEC-1.1_2026-10-21.zip", "ADENDA_CIERRE_PEC-1.1_2026-10-21.zip",
        "HOJA_DE_RUTA_CONFIRMATORIA_2026-10-21.zip", "SHA256SUMS_DEL_ZIP.txt", "SHA256SUMS_DEL_ZIP_ADENDA.txt",
        "SHA256SUMS_DEL_ZIP_CALIBRACION.txt", "SHA256SUMS_DEL_ZIP_DECISIONES.txt", "SHA256SUMS_DEL_ZIP_HOJA.txt"]
DIRS_FUERA = {  # nombre de carpeta → motivo
    "venv": "entorno virtual", ".venv": "entorno virtual", "venv_ots": "entorno virtual", "ruedas_ots": "ruedas de pip",
    "node_modules": "dependencias", "__pycache__": "caché", "site-packages": "dependencias", ".git": "repositorio anidado",
    "pgdata": "base de datos de prueba", ".mypy_cache": "caché", ".pytest_cache": "caché", ".ruff_cache": "caché",
    "pytest-of-root": "temporales de pytest", "copia_A": "copia duplicada de árboles ya incluidos",
    "copia_aislada": "copia duplicada de árboles ya incluidos", "evidencia": None,  # ver regla especial
    "datos_vision": "datos de terceros (Binance Vision)", "datos_anuncios": "datos de terceros (páginas archivadas)",
    "entorno": "ruedas de pip", "tmp_guarda": "temporales de prueba", "tmp_e2e": "temporales de prueba",
    ".vacios": "temporales", "tmp_pytest_v3": "temporales de pytest", "tmp_patch": "temporales", "trabajo": "copias de trabajo",
    "logs": None,  # ver regla especial
}
EXT_FUERA = {".zip": "archivo comprimido (datos o duplicado)", ".checksum": "checksum de datos de terceros",
             ".npz": "series derivadas de datos de terceros", ".body": "página web archivada (terceros)",
             ".db": "base de datos de corrida", ".whl": "rueda de pip", ".tar": "archivo comprimido", ".gz": "archivo comprimido",
             ".tgz": "archivo comprimido", ".pack": "objeto git", ".bin": "binario", ".pdf": "documento de terceros"}
TOPE = 5 * 1024 * 1024


def motivo_dir(rel, nombre):
    if nombre == "evidencia" and rel.startswith("paquete_revision_independiente_E3H1H2_2026-10-28"):
        return "copias de árboles ya incluidos (evidencia del paquete de revisión)"
    if nombre == "extraccion" or nombre.startswith("extraccion_"):
        return "extracción duplicada de un ZIP o paquete"
    if nombre == "logs" and rel.startswith(("revision_adversaria_2026-10-25", "experimentos/E1_")):
        return "registros crudos de corridas (grandes)"
    if nombre == "paginas" and "/fixture_" not in rel:
        return "páginas web archivadas de terceros (anuncios de Binance; se conservan URL y sha256)"
    if nombre.startswith("tmp"):
        return "temporales de prueba"
    if nombre == "logs" or nombre == "evidencia":
        return None
    return DIRS_FUERA.get(nombre)


def recorrer(S):
    dentro, fuera = [], []
    for z in ZIPS:
        p = os.path.join(S, z)
        if os.path.isfile(p):
            dentro.append((z, os.path.getsize(p)))
    for f, _ in FUENTES:
        base = os.path.join(S, f)
        if os.path.isfile(base):
            dentro.append((f, os.path.getsize(base)))
            continue
        for raiz, dirs, archivos in os.walk(base):
            rel_raiz = os.path.relpath(raiz, S)
            for d in list(dirs):
                m = motivo_dir(os.path.join(rel_raiz, d), d)
                if m:
                    fuera.append((os.path.join(rel_raiz, d) + "/", m))
                    dirs.remove(d)
            for a in archivos:
                rel = os.path.join(rel_raiz, a)
                p = os.path.join(S, rel)
                if os.path.islink(p):
                    fuera.append((rel, "enlace simbólico"))
                    continue
                t = os.path.getsize(p)
                e = os.path.splitext(a)[1].lower()
                if e in EXT_FUERA:
                    fuera.append((rel, EXT_FUERA[e]))
                elif t > TOPE:
                    fuera.append((rel, f"archivo de más de 5 MB ({t / 1048576:.1f} MB)"))
                else:
                    dentro.append((rel, t))
    return dentro, fuera


if __name__ == "__main__":
    S, modo = sys.argv[1], sys.argv[2]
    dentro, fuera = recorrer(S)
    if modo == "plan":
        out = sys.argv[3]
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "dentro.tsv"), "w") as f:
            for r, t in sorted(dentro):
                f.write(f"{t}\t{r}\n")
        with open(os.path.join(out, "fuera.tsv"), "w") as f:
            for r, m in sorted(fuera):
                f.write(f"{m}\t{r}\n")
        print(f"dentro: {len(dentro)} archivos, {sum(t for _, t in dentro) / 1048576:.1f} MB · fuera: {len(fuera)} entradas")
    elif modo == "copiar":
        dst = sys.argv[3]
        for r, _ in dentro:
            d = os.path.join(dst, r)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(os.path.join(S, r), d)
        print(f"copiados {len(dentro)} archivos a {dst}")
