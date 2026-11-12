"""Revisión adversarial · L-17: ¿qué textos de autorización acepta el control del v3?

Mismo aislamiento que arnes_L13.py: FRASE, FRASES_DECISION y SHA_PROPIO reemplazados por valores de prueba; ningún texto
contiene la FRASE real ni el sha256 real. El flujo se detiene con una excepción centinela en `leer_y_verificar`, que es
lo primero que ocurre después de aceptar la autorización y de `permitir_intento`: no se crea la salida ni se lee nada.
Uso: python -B -I arnes_L17.py <v3.py> <base>"""
import importlib.util
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("arnes_L13", AQUI / "arnes_L13.py")
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)


class Centinela(Exception):
    pass


def main(v3: Path, base: Path):
    base.mkdir(parents=True, exist_ok=True)
    V, real = A.cargar(v3, base, "v3_L17")

    def detener(*a):
        raise Centinela("AUTORIZACION ACEPTADA (detenido antes de leer insumos)")
    V.leer_y_verificar = detener
    man = base / "manifiesto_prueba.json"
    man.write_bytes(b'{"prueba": "sin valor"}')
    sha_man = A.sha_b(man.read_bytes())
    F, R, D1 = A.FRASE_PRUEBA, A.DECISIONES_PRUEBA["reapertura_y_adenda_R"], A.DECISIONES_PRUEBA["D1_lectura_literal"]
    variantes = {
        "control_completa": [F, V.SHA_PROPIO, sha_man, R, D1],
        "control_sin_D1": [F, V.SHA_PROPIO, sha_man, R],
        "negacion_de_la_frase": ["NO " + F, V.SHA_PROPIO, sha_man, R, D1],
        "negacion_de_las_decisiones": [F, V.SHA_PROPIO, sha_man, "NO " + R, "NO " + D1],
        "frases_citadas_para_rechazarlas": [f"El usuario NO firma «{F}» ni «{R}» ni «{D1}».", V.SHA_PROPIO, sha_man],
        "contradice_D3_elige_160_semanas": [F, V.SHA_PROPIO, sha_man, R, D1, "DECISION D-3: 160 SEMANAS (FECHA DEL TITULO)"],
        "contradice_D4_sin_reintentos": [F, V.SHA_PROPIO, sha_man, R, D1, "DECISION D-4: NINGUN REINTENTO"],
        "rechaza_riesgos_D5": [F, V.SHA_PROPIO, sha_man, R, D1, "DECISION D-5: RIESGOS RESIDUALES INACEPTABLES"],
        "sin_mencion_de_D3_D4_D5": [F, V.SHA_PROPIO, sha_man, R, D1],
        "otra_ventana_declarada": [F.replace("PRUEBA", "PRUEBA"), V.SHA_PROPIO, sha_man, R, D1, "VENTANA B, INICIO 2024-01-01"],
    }
    out = {}
    for nombre, lineas in variantes.items():
        aut = base / f"aut_{nombre}.txt"
        aut.write_text("\n".join(lineas) + "\n")
        assert real["FRASE"] not in aut.read_text() and real["SHA"] not in aut.read_text()
        try:
            V.modo_real(base / "e3_inexistente", base / "ventana_inexistente", aut, base / f"salida_{nombre}", man)
            out[nombre] = "SIN EXCEPCIÓN (inesperado)"
        except Centinela as exc:
            out[nombre] = str(exc)
        except SystemExit as exc:
            out[nombre] = f"{type(exc).__name__}: {str(exc)[:160]}"
        out[nombre + "__salida_creada"] = (base / f"salida_{nombre}").exists()
    print(json.dumps(out, ensure_ascii=False, indent=1))
    (base / "resultado_L17.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
