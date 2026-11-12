"""Compara la suite de la base con la de un árbol integrado (JUnit), prueba a prueba.

Criterio «sin regresiones»:
  1. Ninguna prueba de la base falta en el integrado.
  2. Toda prueba nueva (ausente en la base) pasa.
  3. Toda prueba de la base tiene el mismo resultado en ambos árboles, salvo las SENSIBLES AL ENTORNO documentadas
     (B3: dos por el reloj de pared, una por la carrera con el bucle de fondo), que pueden diferir.
  4. --corregidas: además, las tres sensibles al entorno PASAN en el integrado (parche opcional 03 aplicado).
Las pruebas que no pasan se listan siempre, con su causa documentada o «NO DOCUMENTADA».
Uso: python comparar_suites_v2.py <base.xml> <integrado.xml> [--corregidas]"""
import sys
import xml.etree.ElementTree as ET

SENSIBLES_AL_ENTORNO = {
    "test_five_restored_entries_for_the_symbol_refuse_the_sixth_after_the_restart": "reloj de pared antes de ≈05:55 UTC (B3)",
    "test_a_day_that_hit_the_loss_limit_still_refuses_entries_after_a_restart": "reloj de pared antes de ≈05:55 UTC (B3)",
    "test_rejects_and_partials_over_hundreds_of_bars_keep_the_invariants_and_the_record_whole": "carrera con el bucle de fondo de start() (B3)",
}


def resultados(path):
    out, raiz = {}, ET.parse(path).getroot()
    for c in raiz.iter("testcase"):
        if c.find("error") is not None:
            estado = "error"
        elif c.find("failure") is not None:
            estado = "falla"
        elif c.find("skipped") is not None:
            estado = "omitida"
        else:
            estado = "pasa"
        out[(c.get("classname"), c.get("name"))] = estado
    return out


def main(base_xml, integ_xml, corregidas=False):
    b, i = resultados(base_xml), resultados(integ_xml)
    faltan = sorted(set(b) - set(i))
    nuevas = {k: v for k, v in i.items() if k not in b}
    distintas = sorted(k for k in set(b) & set(i) if b[k] != i[k])
    distintas_no_explicadas = [k for k in distintas if k[1] not in SENSIBLES_AL_ENTORNO]
    cuenta = lambda d, e: sum(v == e for v in d.values())  # noqa: E731
    for n, d in (("base", b), ("integrado", i)):
        print(f"{n}: {len(d)} pruebas · {cuenta(d, 'pasa')} pasan · {cuenta(d, 'falla')} fallan · {cuenta(d, 'error')} errores · {cuenta(d, 'omitida')} omitidas")
    print("pruebas de la base que faltan en el integrado:", faltan or "ninguna")
    print(f"pruebas nuevas: {len(nuevas)} · todas pasan: {all(v == 'pasa' for v in nuevas.values())}")
    for k, v in sorted(nuevas.items()):
        print(f"   {v:7s} {k[0]}::{k[1]}")
    print("pruebas de la base con otro resultado en el integrado:",
          [(k[1], b[k], i[k], SENSIBLES_AL_ENTORNO.get(k[1], "NO DOCUMENTADA")) for k in distintas] or "ninguna")
    for n, d in (("base", b), ("integrado", i)):
        no = sorted((k[1], v) for k, v in d.items() if v != "pasa" and k in b)
        print(f"pruebas de la base que no pasan en el árbol {n}:",
              [(x, v, SENSIBLES_AL_ENTORNO.get(x, "NO DOCUMENTADA")) for x, v in no] or "ninguna")
    no_documentadas = [k[1] for k, v in list(b.items()) + [(k, i[k]) for k in i if k in b]
                       if v != "pasa" and k[1] not in SENSIBLES_AL_ENTORNO]
    ok = not faltan and nuevas and all(v == "pasa" for v in nuevas.values()) and not distintas_no_explicadas and not no_documentadas
    if corregidas:
        sens = {k: v for k, v in i.items() if k[1] in SENSIBLES_AL_ENTORNO}
        print("sensibles al entorno en el integrado (deben pasar con el parche 03):", sorted((k[1], v) for k, v in sens.items()))
        ok = ok and len(sens) == 3 and all(v == "pasa" for v in sens.values())
    print("SIN REGRESIONES FRENTE A LA BASE" if ok else "HAY DIFERENCIAS NO EXPLICADAS: revisar")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], "--corregidas" in sys.argv[3:]))
