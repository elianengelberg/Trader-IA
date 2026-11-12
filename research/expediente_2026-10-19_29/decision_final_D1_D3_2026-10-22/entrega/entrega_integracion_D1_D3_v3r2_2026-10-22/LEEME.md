# Entrega v3 (revisión r2) — decisión final de integración D1–D3 (2026-10-22)

> La revisión r1 de este paquete (`entrega_integracion_D1_D3_v3_2026-10-22.zip`, `f4d69ad7…`) falló en la reproducción limpia por una ruta relativa en `herramientas/compat_historica.py`. r2 corrige solo esa herramienta (y estas referencias); los parches y las pruebas son los mismos. r1 se conserva y no se usa.

**Decisión: B — LISTO CON CORRECCIONES.**
- Recomendación: integrar **01 + 02v3** (unidad inseparable) **+ 03**.
- El 04 (CI con versiones fijadas) es opcional.
- No integrar el 02 original.
- Nada se integró, publicó ni operó.
- Es una revisión de ingeniería: no valida rentabilidad ni autoriza a operar.

## Orden de lectura
1. `INFORME_DECISION_FINAL.md`: decisión, defecto encontrado, CI y auditoría de afirmaciones.
2. `MATRIZ_REVISION_PARCHES.md`: cada parche frente a cada comprobación pedida.
3. `MATRIZ_RIESGOS.md`: resueltos, pendientes y aceptados.
4. `COMPARACION_BASE_VS_INTEGRACION.md` y `EVIDENCIA_EJECUCIONES.md`: comandos, códigos de salida y resultados.
5. `MATRIZ_MUTANTES.md`.
6. `PLAN_INTEGRACION_Y_REVERSION.md` y `ACCIONES_QUE_REQUIEREN_AUTORIZACION.md`.
7. `COMANDOS_DE_VERIFICACION.md` y `reproducir.sh`.

## Contenido
| Carpeta | Qué hay |
|---|---|
| `parches/` | `01_*` (sin cambios desde v2), `02v3_*_CORREGIDO`, `03_*` (sin cambios), `04_*` (nuevo, CI); `originales_v2/02_*` (el 02 de v2, **no integrar**); `SHA256_archivos_resultantes_{obligatoria,completa}_v3.txt`; `ARCHIVOS_MODIFICADOS.txt` |
| `pruebas/` | Pruebas definitivas: `test_backtest_order_hygiene.py` (8), `test_backtest_provenance.py` (14), `opcional_03/` |
| `evidencia/` | `R*` revisión (defecto, corrección, compatibilidad, cobertura, B3); `S*` suites; `CI_*` pasos de la CI; `M*` mutantes; `P*` paridad con E1 |
| `entorno/` | `ci-py311.txt`, freezes de los entornos (incluido el sin restricciones de hoy) y la deriva frente a las restricciones |
| `registro/` | `00` estado inicial del repositorio original; `01` verificación de la entrega v2; `99` estado final y archivos congelados |
| `herramientas/` | Todo lo usado: sondas (solo miden), mutantes, paridad, comparadores, compatibilidad, cobertura, congelados |

## Integridad
- `SHA256SUMS` cubre cada archivo de esta carpeta.
- El hash del ZIP va fuera, en `entrega_integracion_D1_D3_v3r2_2026-10-22.zip.sha256`.
- **Sin firma digital:** los hashes prueban integridad, no autoría.
