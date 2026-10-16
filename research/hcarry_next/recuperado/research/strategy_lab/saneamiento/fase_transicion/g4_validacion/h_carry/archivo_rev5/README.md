# Transformaciones aplicadas al borrador H-CARRY 1.1 durante la rev. 5

Copias literales, en `.txt` para que no se importen ni se ejecuten por accidente, de los scripts que modificaron `protocolo_hcarry_v1_1_borrador.json`. El protocolo 1.0 (`protocolo_hcarry.json`) no se tocó: los dos últimos scripts lo comprueban por su hash.

| Orden | Script | Transición del borrador |
|---|---|---|
| 1 | `protocolo_rev5.py.txt` | rev. 4 → rev. 5 (`556209bb…`) |
| 2 | `protocolo_rev5_cierre.py.txt` | `556209bb…` → `cfaefb10…` (cierre técnico) |
| 3 | `protocolo_rev5_decisiones.py.txt` | `cfaefb10…` → `c1f6b110…` (decisiones provisionales del 2026-10-16) |

- **Comprobaciones de no cambio.** Los scripts 2 y 3 comprueban con `assert` que no cambian:
  - criterios, umbrales, costes, capital ni ventana;
  - además, en el script 3: reequilibrio, comparador y D2–D4.
- **Limitación para el revisor.** Las versiones intermedias del borrador (`556209bb…` y `cfaefb10…`) **no se conservaron** como archivo. Esas comprobaciones las ejecutó el autor y no pueden repetirse. Lo que el revisor sí puede comprobar directamente es que los criterios, umbrales, costes, capital y ventana del borrador vigente coinciden con `config` de `plan_protocolo_rev5.json`, que construye el código.
- **Uso original:** `python -B <script> h_carry/protocolo_hcarry_v1_1_borrador.json`, desde la raíz de `g4_validacion`. Cada script imprimía el nuevo SHA-256.
