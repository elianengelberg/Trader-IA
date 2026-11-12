# Cierre D1/D2, guarda de versión y R19 (2026-10-22)

**Nada de esto se integró, publicó ni operó.** Todo está en copias aisladas. Los cambios propuestos están separados y se pueden verificar.

## Orden de lectura
1. `INFORME_DECISION.md`: las cuatro fases, el estado de los parches, los riesgos por destino y lo que requiere tu decisión.
2. `PLAN_INTEGRACION_Y_REVERSION_ACTUALIZADO.md`.
3. `fase1/`: la revisión documental **v3r3**:
   - el ZIP y su `.sha256`;
   - el registro de la reproducción limpia (`VERIFICACION_EXTRACCION_LIMPIA_v3r3.txt`);
   - qué cambió y las diferencias exactas frente a r2.
4. `fase2/`: la **guarda de versión** (parche 05, propuesta):
   - `JUSTIFICACION_GUARDA_VERSION.md`;
   - la prueba;
   - el parche;
   - la evidencia: mutantes, márgenes, robustez, determinismo, aplicación y suite;
   - las herramientas.
5. `fase3/`: **R19**:
   - `R19_RESULTADOS_Y_LIMITES.md`;
   - `PLAN_R19_ENMIENDA_1.md`, la corrección propuesta y **no ejecutada**;
   - el plan JSON congelado;
   - las herramientas v2;
   - la validación sintética del instrumento.
6. `registro/`:
   - `00`: estado inicial del repositorio original y de los congelados;
   - `01`: entregas previas;
   - `02`: identidad de v3r2;
   - `03`: precondiciones y congelamiento de R19;
   - `99`: estado final.
7. `COMANDOS_VERIFICACION.md`.

## Integridad
- `SHA256SUMS` cubre cada archivo de esta carpeta.
- El hash del ZIP de este paquete va fuera, en su `.sha256`.
- **Sin firma digital:** los hashes prueban integridad, no autoría.
