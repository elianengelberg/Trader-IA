# Comparación entre la base (`72ffae5`) y la integración propuesta (01 + 02v3 [+ 03])

## Suites completas (comando de la CI; JUnit)
| Entorno | Base | Obligatoria (01+02v3) | Completa (01+02v3+03) | Prueba a prueba |
|---|---|---|---|---|
| Restricciones (venv_A / venv_B) | 1956/1956 (código 0, 319,9 s) | 1978/1978 (código 0, 376,3 s) | 1978/1978 (código 0, 365,9 s) | Sin regresiones; 22 nuevas pasan; en la completa pasan las 3 sensibles |
| Sin restricciones, como la CI de hoy | 1956/1956 (código 0, 346,9 s) | — | 1978/1978 (código 0, 391,7 s) | Sin regresiones |

- **22 pruebas nuevas:** 8 de D1–D3 y 14 de trazabilidad.
- **Ninguna prueba de la base** falta ni cambia de resultado.

## Lo que cambia por diseño
| Aspecto | Base | Integración | Evidencia |
|---|---|---|---|
| Resultados con rechazos o llenados parciales | Afectados por D1–D3 | Corregidos. El mismo pedido por la API da 13 operaciones con la base y 12 con la integración | `R5_compat_resumen.txt` |
| `run_id` | `bt(dataset, símbolo, digest)` | Además: versión y huella del motor, huella de datos, universo, estrategias, `liquidate_at_end`, `is_out_of_sample` | `R11_*`; pruebas |
| Guardado | Upsert ciego por `run_id` | Rechaza otra procedencia, y otros números bajo la misma procedencia | `R1_*`, `R3_*` |
| `GET /api/backtests` | Sin `engine_version` | `engine_version` (`null` en las filas viejas) | `R5_*` |
| Advertencias del backtest | — | «N bars held a position with no stop level…» cuando corresponde | 01 |
| Esquema y migraciones | 0007 | 0007, sin cambios | `CI_alembic.txt` |
| Frontend | — | Sin cambios (0 archivos) | `CI_frontend.txt` |

## Lo que no cambia (verificado)
- **Números del motor con E1:** los mismos con v2, v3 y E17, en dos entornos (P1, P2, P3, S1: operaciones, equity, métricas, decisiones y registro de decisiones).
  - La trazabilidad y su corrección no alteran ningún número.
- **Lint limpio** y **migraciones** iguales.
- **Sesión en vivo, papel en tiempo real, market making:** sin cambios de código. Los parches no tocan `tia/runtime`, `tia/live`, `tia/mm` ni la configuración.
