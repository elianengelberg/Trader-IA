# Cierre integral: Trader-IA v3r3 + guarda 05 + R19 + integración controlada (2026-10-22)

**Empezá por `INFORME_CIERRE_FINAL.md`**, que al final tiene la tabla de decisión.

| Ruta | Qué es |
|---|---|
| `INFORME_CIERRE_FINAL.md` | Resumen, fases A–I, decisiones que requieren autorización y tabla final |
| `RESULTADOS_R19.md` | R19: clasificación (NO_REPRODUCIDO), validez del instrumento, medidas y límites |
| `MATRIZ_RIESGOS.md` | Estado de cada riesgo y tipo de evidencia: L local, CI remota (ninguna), X externa (ninguna) |
| `PLAN_INTEGRACION.md` | Unidades A y B, orden, árboles esperados, reversión y criterios para fusionar. **No ejecutado** |
| `MANIFEST.sha256` | SHA-256 de cada archivo del paquete (`sha256sum -c MANIFEST.sha256`) |
| `patches/` | **Nuevos:** `05v2_guarda_version_motor.patch` (unidad B), `06v3_opcional_gate_ci_procedencia.patch` (06 v1 y 06v2, superados, quedan en `evidence/E_gate/06v1_superado/` y `06v2_superado/`), `07_opcional_pruebas_almacen_postgresql.patch` y `guarda_v1_a_v2.diff`. **Copias byte a byte de v3r3** en `patches/v3r3/`: 01, 02v3, 03, 04 y las listas de archivos resultantes |
| `tests/` | El contenido de las pruebas que agregan los parches: la guarda v2, el gate de CI y el módulo PostgreSQL. La guarda v1 del paquete anterior va en `tests/referencia/`, solo para comparar |
| `evidence/` | Evidencia de esta misión, por fase (`C_guarda`, `D_*`, `E_*`, `F_*`, `G_R24`, `G_binance`, `R19_*`) y los registros `evidence/registro/` (A1–A3, B0–B4, E0, 99) |
| `logs/` | Salidas de las suites (Fase E), de la reproducción limpia de v3r3 y del gate |
| `reproduction/` | `COMANDOS_REPRODUCCION.md` y las herramientas de esta misión |
| `config/` | `ci.yml` propuesto (04 + 06v3), restricciones de versiones, `pip freeze` del entorno local, configuración de pytest, el plan R19 congelado y el escaneo de secretos. Sin secretos ni credenciales |

**Qué no está acá:**
- los resultados anteriores, que siguen en sus paquetes congelados (`410ae629…` y v3r3 `25902649…`);
- las bases SQLite temporales de las corridas R19 (187 MB);
- los árboles de trabajo.

**No se hizo:** commit, push, rama, PR, merge, deploy ni trading real.
