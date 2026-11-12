# Entrega de integración del parche D1–D3 del motor de backtest

**Veredicto: APTO PARA REVISIÓN** (`INFORME_REVISION_TECNICA.md` §1).
- **No está integrado:** no hubo commits, push, despliegues ni trading.
- El repositorio original sigue intacto (`registro/00_*` frente a `registro/99_*`).

## Por dónde empezar
1. `INFORME_REVISION_TECNICA.md`: veredicto, identidad de la base, D1–D3, pruebas, riesgos y artefactos.
2. `PLAN_INTEGRACION.md`: pasos exactos, criterios de aceptación A1–A8 y reversión, sin ejecutar.
3. `bash reproducir.sh <repo Trader-IA> <dir nuevo> [rapido|completo]`: lo comprueba todo sin confiar en este texto.

## Contenido
| Ruta | Qué es |
|---|---|
| `parche/integracion_D1_D3_72ffae5.patch` | **El parche a integrar** (`git apply`) contra `72ffae5`: `engine.py` y `paper.py` (idénticos al parche de SIM1), más la prueba final |
| `parche/SHA256_archivos_resultantes.txt` | SHA-256 de los 3 archivos tras aplicar el parche |
| `parche/ARCHIVOS_QUE_CAMBIAN.txt` | Lista explícita: estado, líneas, blob antes y después |
| `parche/diff_legible_motor_con_funciones_completas.diff` | Diff del motor con cada función completa como contexto (`git diff -W`) |
| `parche/test_backtest_order_hygiene.py` | Pruebas finales (6), sha `f10baa10…` |
| `parche/origen_SIM1/` | El parche y las 4 pruebas tal como los entregó SIM1, para trazabilidad |
| `herramientas/` | `mutantes.py`, `correr_suite_ci.sh`, `comparar_suites.py` (integración = base prueba a prueba), `con_reloj.py`, `firmas.py`, `paridad_completa.py`, `sonda_churn.py`, `sonda_ioc.py` |
| `registro/` | Estado del repositorio al inicio y al final, identidad de SIM1, correspondencia parche-base, árbol parcheado, instalación y entorno |

## Índice de evidencia
Pruebas **finales**: E7–E18. Corridas intermedias: E1–E6, conservadas por trazabilidad.

| Archivo | Contenido |
|---|---|
| `E7_*`, `E8_*`, `E9_*` (.txt y .xml JUnit) | Suite completa como la CI: base 1956/1956; parche + pruebas SIM1 1960/1960; integración 1962/1962 |
| `E12_*` | Comparación de conjuntos: ninguna prueba de la base falta ni cambia de resultado |
| `E13_*` | Mutantes con las pruebas finales: 8/8 mueren |
| `E14_*` | Pruebas finales contra el motor original: 6/6 fallan por aserción |
| `E15_*` | Verificación sintética (look-ahead, rechazos, parciales, determinismo) con el árbol integrado |
| `E16_*` | ruff (CI) y mypy (informativo) en la base y en la integración |
| `E10_*`, `E11_*` | Usos en el repositorio y firmas públicas, base contra integración |
| `E17_*`, `E18_*` | Datos reales (BTC 1h de E1): paridad con E1 y salida completa idéntica entre los entornos CI y E1 |
| `E1_*`, `E2_*` | Primera corrida de las suites (rc=0). La línea de conteo no se imprimió por `-q -q` (addopts + CI); por eso se repitió en E7–E9 con JUnit |
| `E3_*` | Pruebas SIM1 exactas (`685cf4ec…`) contra el original (4/4 fallan) y una versión intermedia de las v2 |
| `E4_*` | Mutantes contra las pruebas de SIM1: M1, M5, M6 y M7 sobreviven (el hallazgo) |
| `E5_*` | Mutantes contra una versión intermedia de las v2 (M4 sobrevivía; corregido) |
| `E6_*` | Sonda: el stop no se re-coloca de más con D2 |
| `E19_*`, `E20_*`, `E24_*` | Dos pruebas de la base dependientes del reloj, entre 00:00 y ≈ 05:45 UTC; idénticas con y sin el parche; demostrado con el reloj fijado (R11) |
| `E21_*`, `E22_*`, `E23_*` | Una prueba de la base con un límite fijo de 10 s, inestable en una máquina lenta, en ambos árboles. La cobertura muestra que no ejecuta código del parche (R13) |
| `E25_*` | Las 4 corridas completas comparadas prueba a prueba: base = integración en todas |

## Datos de terceros
- No se incluyen.
- La paridad usa los klines BTCUSDT 1h de E1, verificados por E1 contra los `.CHECKSUM` de data.binance.vision. Su lista de hashes está en la entrega E1 y en `reproduccion/SHA256_zips_usados.txt` de SIM1.
- No se consultó ningún endpoint de Binance.
