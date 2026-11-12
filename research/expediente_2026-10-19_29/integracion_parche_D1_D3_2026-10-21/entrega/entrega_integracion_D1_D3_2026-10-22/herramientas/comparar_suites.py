"""Compara la suite de la base y la del árbol integrado, corridas en el mismo momento y entorno (JUnit).

Criterio de «sin regresiones»:
  1. Ninguna prueba de la base falta en el integrado.
  2. Las 6 pruebas nuevas existen y pasan.
  3. Toda prueba de la base tiene el mismo resultado en ambos árboles, salvo las SENSIBLES AL ENTORNO documentadas,
     que también fallan sin el parche y no ejecutan código del parche:
       - dos dependientes del reloj (fallan / se omiten entre las 00:00 y ≈ 05:45 UTC; evidencia E20, E24);
       - una con un tiempo límite fijo de 10 s para vaciar escrituras de persistencia (evidencia E21–E23).
Las pruebas de la base que no pasan se informan siempre, aunque no hagan fallar el criterio.
Uso: python comparar_suites.py <base.xml> <integrado.xml>
"""
import sys
import xml.etree.ElementTree as ET

NUEVAS = {
    "test_stops_and_exits_survive_rejections", "test_a_rejected_close_is_sent_again_and_closes",
    "test_the_stop_in_the_book_follows_the_leg", "test_partial_fills_leave_no_untracked_or_stuck_position",
    "test_a_close_that_leaves_position_is_released_and_retried", "test_a_leg_without_a_stop_level_is_reported",
}
SENSIBLES_AL_ENTORNO = {
    "test_five_restored_entries_for_the_symbol_refuse_the_sixth_after_the_restart": "reloj (E20, E24)",
    "test_a_day_that_hit_the_loss_limit_still_refuses_entries_after_a_restart": "reloj (E20, E24)",
    "test_rejects_and_partials_over_hundreds_of_bars_keep_the_invariants_and_the_record_whole": "límite de 10 s (E21–E23)",
}


def resultados(path):
    out = {}
    for c in ET.parse(path).getroot().iter("testcase"):
        if c.find("failure") is not None or c.find("error") is not None:
            estado = "falla"
        elif c.find("skipped") is not None:
            estado = "omitida"
        else:
            estado = "pasa"
        out[(c.get("classname"), c.get("name"))] = estado
    return out


def main(base_xml, integ_xml):
    b, i = resultados(base_xml), resultados(integ_xml)
    faltan = sorted(set(b) - set(i))
    nuevas = {k: v for k, v in i.items() if k not in b}
    distintas = sorted(k for k in set(b) & set(i) if b[k] != i[k])
    distintas_no_explicadas = [k for k in distintas if k[1] not in SENSIBLES_AL_ENTORNO]
    print(f"base: {len(b)} pruebas, {sum(v == 'pasa' for v in b.values())} pasan · "
          f"integrado: {len(i)} pruebas, {sum(v == 'pasa' for v in i.values())} pasan")
    print("pruebas de la base que faltan en el integrado:", faltan or "ninguna")
    print("pruebas nuevas:", sorted(k[1] for k in nuevas), "· todas pasan:", all(v == "pasa" for v in nuevas.values()))
    print("pruebas de la base con otro resultado en el integrado:",
          [(k[1], b[k], i[k], SENSIBLES_AL_ENTORNO.get(k[1], "NO DOCUMENTADA")) for k in distintas] or "ninguna")
    for nombre, arbol in (("base", b), ("integrado", i)):
        no = sorted((k[1], v) for k, v in arbol.items() if v != "pasa" and k[1] not in NUEVAS)
        print(f"pruebas de la base que no pasan en el árbol {nombre}:",
              [(n, v, SENSIBLES_AL_ENTORNO.get(n, "NO DOCUMENTADA")) for n, v in no] or "ninguna")
    no_documentadas = [k[1] for k, v in b.items() if v != "pasa" and k[1] not in SENSIBLES_AL_ENTORNO]
    ok = (len(b) == 1956 and not faltan and set(k[1] for k in nuevas) == NUEVAS
          and all(v == "pasa" for v in nuevas.values()) and not distintas_no_explicadas and not no_documentadas)
    print("SIN REGRESIONES FRENTE A LA BASE" if ok else "HAY DIFERENCIAS NO EXPLICADAS: revisar")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
