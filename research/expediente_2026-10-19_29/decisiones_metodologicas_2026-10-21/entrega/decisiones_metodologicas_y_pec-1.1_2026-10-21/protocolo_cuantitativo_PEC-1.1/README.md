# protocolo_cuantitativo/: PEC-1.1 (sobre PEC-1.0 de r1), herramientas probadas con datos sintéticos

Python estándar (3.11 o superior). No usa ninguna dependencia externa; el contraste opcional con E3 usa numpy en un
subproceso. **No contiene ni lee datos de mercado.**

**Normas:** `PEC-1.1.md`. **Diferencias con PEC-1.0:** `CAMBIOS_PEC-1.1.md`. Todos los archivos de PEC-1.0 siguen en
este directorio, con sus mismos SHA-256, salvo este README.

| Ruta | Contenido |
|---|---|
| `pec/` | Módulos de PEC-1.0 sin cambios, más los de PEC-1.1: `prospectiva` (regla decisiva, δ, plan de miradas, política de faltantes) y `prerregistro_v11` |
| `esquemas/` | `prerregistro_v1.schema.json` (PEC-1.0) y `prerregistro_v1_1.schema.json` (PEC-1.1) |
| `plantillas/` | Ejemplos **sintéticos** 1.0 y 1.1 (activos y fechas ficticios; no son propuestas) y la tarjeta de hipótesis |
| `registro_programa/` | Las 39 hipótesis del programa (ninguna respaldada) |
| `calibracion/` | Script y parámetros de A-S1 (PEC-1.0), ya ejecutado; los resultados están en su ZIP (`37af592c…`) |
| `pruebas/` | 115 pruebas: 72 de PEC-1.0 y 43 de PEC-1.1 (`test_pec_1_1.py`) |

**Ejecutar las pruebas:**
```
cd pruebas && PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -p no:cacheprovider -q
```
- `PEC_PY_NUMPY=<intérprete con numpy>` activa el contraste diferencial con E3.
- Usá siempre `-B`: un `__pycache__` dentro del paquete lo modifica (`pruebas/test_higiene.py`).

Ninguna salida de estas herramientas con datos sintéticos es evidencia de rentabilidad.
