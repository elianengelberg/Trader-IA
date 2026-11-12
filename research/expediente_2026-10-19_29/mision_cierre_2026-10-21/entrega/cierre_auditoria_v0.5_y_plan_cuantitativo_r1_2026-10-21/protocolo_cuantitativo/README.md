# protocolo_cuantitativo/: PEC-1.0, herramientas probadas con datos sintéticos

Python estándar (3.11 o superior). No usa ninguna dependencia externa; el contraste opcional con E3 usa numpy en un
subproceso. **No contiene ni lee datos de mercado.**

| Ruta | Contenido |
|---|---|
| `pec/` | `inferencia`, `secuencial`, `potencia`, `contabilidad`, `datos`, `mirada_futuro`, `metricas`, `decision`, `prerregistro`, `programa`, `sintetico` |
| `esquemas/prerregistro_v1.schema.json` | Esquema del prerregistro |
| `plantillas/` | Tarjeta de hipótesis, guía del prerregistro y un ejemplo **sintético** (activo y fechas ficticios; no es una propuesta) |
| `registro_programa/HIPOTESIS_PROGRAMA.json` | Las 39 hipótesis del programa, transcritas del registro de riesgos (ninguna respaldada) |
| `calibracion/` | Calibración del MEC §5: **bloqueada** sin la autorización A-S1; parámetros congelados |
| `pruebas/` | 72 pruebas; `referencia_E3/` es la implementación de E3 (`7b280386…`), copiada sin cambios para el contraste |

**Ejecutar las pruebas:**
```
cd pruebas && PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -p no:cacheprovider -q
```
- `PEC_PY_NUMPY=<intérprete con numpy>` activa el contraste diferencial con E3; si no hay ninguno, la prueba se omite.
- Usá siempre `-B`: un `__pycache__` dentro del paquete lo modifica (`pruebas/test_higiene.py`).

**Uso previsto:** en 05_PLAN_CUANTITATIVO.md. Ninguna salida de estas herramientas con datos sintéticos es evidencia
de rentabilidad.
