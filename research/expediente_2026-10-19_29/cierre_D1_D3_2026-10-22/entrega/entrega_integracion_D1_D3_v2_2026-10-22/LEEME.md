# Entrega v2 — integración D1–D3 con trazabilidad del motor (2026-10-22)

**Base:** `72ffae5d2698440c8f1afaff12e07bd8adde66fb`.
- Reemplaza, para revisión, a `entrega_integracion_D1_D3_2026-10-22.zip` (`f9495ad8…`). Esa entrega no se modificó.
- **Nada de esto se integró, publicó ni operó.**

## Por dónde empezar
1. `RESUMEN_EJECUTIVO.md`: una página.
2. `INFORME_TECNICO_FINAL.md`: fases A–F, causas, evidencia y riesgos residuales.
3. `PLAN_INTEGRACION_Y_REVERSION.md`: pasos exactos (no ejecutados), criterios de aceptación y reversión.
4. `MATRIZ_MUTANTES.md`: cada mutante con su defecto, la prueba que lo detecta, la aserción, el resultado con el original y el resultado con la integración.
5. `COMANDOS_DE_VERIFICACION.md` y `reproducir.sh`: cómo repetirlo todo.

## Contenido
| Carpeta | Qué hay |
|---|---|
| `parches/` | `01_obligatorio_*` (D1–D3 + pruebas definitivas), `02_obligatorio_*` (trazabilidad), `03_opcional_*` (pruebas sensibles al entorno); `SHA256_archivos_resultantes_{obligatoria,completa}.txt`; `ARCHIVOS_MODIFICADOS.txt` |
| `pruebas/` | Pruebas definitivas tal como quedan en el árbol: `test_backtest_order_hygiene.py` (8), `test_backtest_provenance.py` (12); `opcional_03/` |
| `evidencia/` | `B3_*` reloj y persistencia; `C_*` trazabilidad; `D_*` D1–D3 y mutantes; `E_*` paridad con E1; `F_*` parches y suites completas |
| `entorno/` | `ci-py311.txt` (restricciones, 74 paquetes), `freeze_*` de los tres entornos, registros de instalación |
| `registro/` | `00` estado inicial del repositorio original; `01`–`03` integridad de la entrega anterior; `04` entorno; `99` estado final y archivos congelados |
| `herramientas/` | Todas las herramientas usadas: sondas (solo miden), mutantes, paridad, comparadores, verificador de congelados |

## Integridad
- `SHA256SUMS` cubre cada archivo de esta carpeta.
- El hash del ZIP va **fuera** del ZIP, en `entrega_integracion_D1_D3_v2_2026-10-22.zip.sha256`.
- **Sin firma digital:** los hashes prueban integridad, no autoría.
