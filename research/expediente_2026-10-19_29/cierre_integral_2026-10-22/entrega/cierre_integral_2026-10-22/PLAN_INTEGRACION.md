# Plan de integración y reversión (cierre integral, 2026-10-22) — propuesta, **no ejecutada**

**Base:** `72ffae5d2698440c8f1afaff12e07bd8adde66fb`.

Ningún paso de este plan se ejecutó sobre el repositorio protegido. Cada bloque marcado **[AUTORIZACIÓN n]** necesita tu autorización explícita y por separado. La secuencia completa se **simuló** sin commits (`evidence/F_simulacion/`).

## 0. Unidades
| Orden | Unidad | Parche | SHA-256 | Depende de | Carácter |
|---|---|---|---|---|---|
| 1 | **A** = 01 + 02v3 (D1–D3 y trazabilidad), **un único commit**, exactamente 8 archivos | `01_…patch`, `02v3_…patch` (v3r3) | `1944f433…2e60bf`, `d5c90091…cf6a62` | — | Obligatoria |
| 2 | **B** = guarda de versión **05v2** | `patches/05v2_guarda_version_motor.patch` | `911a8d9d…1950e3` | A | Recomendada; reemplaza a 05 v1 |
| 3 | 03: pruebas de reloj y persistencia | `03_…patch` (v3r3) | `0be65ea6…94e33a` | — (aplica sobre A+B) | Recomendada |
| 4 | 04: CI con versiones fijadas | `04_…patch` (v3r3) | `8d396356…306dd5` | — | Opcional |
| 5 | **06v3**: gate de CI (procedencia y guarda) | `patches/06v3_opcional_gate_ci_procedencia.patch` | `f697d482…4b038f` | 04 y B | Opcional |
| 6 | 07: pruebas del almacén contra PostgreSQL (opt-in) | `patches/07_opcional_pruebas_almacen_postgresql.patch` | `100a3d5b…e0fcc1` | A | Opcional |
| — | 05 v1 | (paquete anterior) | `9fc829ad…` | — | **No integrar:** reemplazado por 05v2 |
| — | 06 (v1) | `evidence/E_gate/06v1_superado/` | `931ff4f8…7c09ec` | — | **No integrar:** falla el lint de su propia CI (5 errores de ruff) |
| — | 06v2 | `evidence/E_gate/06v2_superado/` | `f454add6…2554b9` | — | **No integrar:** falla abierto (si no puede importar el motor, deja de exigir la guarda); reemplazado por 06v3 |
| — | 02 original | v3r3 `originales_v2/` | `32a42a5d…` | — | **No integrar** (R4b) |

**Árboles esperados**, calculados en la simulación con `git write-tree` sobre el contenido; sirven para comparar con el commit que corra la CI:

| Estado del contenido | Árbol (`git write-tree`) | Dónde se calculó |
|---|---|---|
| Base `72ffae5` | `44850cfcbf53c3f8223d38a92031f4402f8ffb32` | `evidence/F_simulacion/SIMULACION_INTEGRACION.txt` |
| Tras **A** (01 + 02v3) | `5d6a09549a8314f6e6e9386f82a52ca7628510d1` | ídem. También da el mismo árbol aplicando 02v3 antes que 01 |
| Tras **A + B** (05v2) | `4ef14d31d686f4b0521207bd1e011d96e6c74822` | ídem |
| Tras A + B + 03 | `84f9e349526d061771de74ae799d4ecd6e3732ce` | ídem |
| Tras A + B + 03 + 04 + **06v3** (todo lo propuesto salvo 07) | `0477c6a20c5e3831c2da3bf723948b7baafaa518` | `logs/E/E4_armado_arbol_final_v3.txt` (árbol sobre el que corrieron ruff, la suite final y el gate) |
| (superado) A + B + 03 + 04 + 06v2 | `92fee676526f1231040f349bc08c3158cf1d1c3f` | `logs/E/E3_armado_arbol_final_v2.txt`: ruff limpio, suite 1985/1985 y gate pass, pero el gate **falla abierto** |
| (superado) A + B + 03 + 04 + 06 v1 | `b1ff3fe3413631ceef3bc670ea2776df7f619874` | `logs/E/E2_armado_arbol_final.txt`: suite 1985/1985 y gate pass, pero **ruff falla** |

Los hashes completos de los parches están en `MANIFEST.sha256`. Los de 01, 02v3, 03 y 04 son los de v3r3 (`25902649…`). Si el commit que corre la CI tiene otro árbol, **no** es lo que se verificó aquí.

## 1. Pasos
```bash
cd /home/user/Trader-IA; E=<extracción de v3r3>/parches; P=<este paquete>/patches
# 1.1 Precondiciones (solo lectura)
test -z "$(git status --porcelain)" && test "$(git rev-parse HEAD)" = 72ffae5d2698440c8f1afaff12e07bd8adde66fb
# 1.2 Rama local                                                            [AUTORIZACIÓN 1]
git switch -c fix/backtest-d1-d3-and-engine-provenance 72ffae5d2698440c8f1afaff12e07bd8adde66fb
# 1.3 Unidad A: 01 y luego 02v3, UN commit, exactamente 8 archivos          [AUTORIZACIÓN 2]
git apply --check $E/01_*.patch && git apply $E/01_*.patch && git apply --check $E/02v3_*.patch && git apply $E/02v3_*.patch
sha256sum -c $E/SHA256_archivos_resultantes_obligatoria_v3.txt
git add -A packages tests docs && git commit -m "Backtest: order hygiene D1-D3 and engine provenance (one unit)"
diff <(git show --name-only --format= HEAD | LC_ALL=C sort) <(printf "%s\n" docs/ARCHITECTURE.md packages/tia/src/tia/api/state.py packages/tia/src/tia/backtest/engine.py packages/tia/src/tia/backtest/result.py packages/tia/src/tia/execution/paper.py packages/tia/src/tia/persistence/repositories.py tests/integration/test_backtest_provenance.py tests/unit/test_backtest_order_hygiene.py | LC_ALL=C sort)
test "$(git rev-parse HEAD^{tree})" = 5d6a09549a8314f6e6e9386f82a52ca7628510d1   # árbol esperado tras A
# 1.4 Unidad B: guarda 05v2                                                  [AUTORIZACIÓN 3]
git apply --check $P/05v2_*.patch && git apply $P/05v2_*.patch && git add tests/integration/test_engine_version_contract.py
git commit -m "Tests: tie engine_version to D1-D3 as seen at the venue; fail without a recorded version"
test "$(git rev-parse HEAD^{tree})" = 4ef14d31d686f4b0521207bd1e011d96e6c74822   # árbol esperado tras A+B
# 1.5 Parche 03                                                              [AUTORIZACIÓN 4]
# 1.6 (opcional) 04 y 06v3, en un PR aparte                                   [AUTORIZACIÓN 5]
# 1.7 (opcional) 07                                                          [AUTORIZACIÓN 6]
# 1.8 Verificación local antes de publicar (no publica nada): ruff, suite completa, guarda
# 1.9 Push: dispara la primera CI real                                       [AUTORIZACIÓN 7]
# 1.10 PR en borrador                                                        [AUTORIZACIÓN 8]
# 1.11 Merge, solo con la CI real en verde, revisión humana y el árbol esperado  [AUTORIZACIÓN 9]
```

## 2. Criterios para fusionar
| # | Criterio | Estado |
|---|---|---|
| A1–A6 | Archivos, hashes, ruff, suites sin regresiones, D1–D3 contra la base, mutantes | **Verificados localmente** en esta misión (ver `INFORME_CIERRE_FINAL.md` §E) |
| A7 | **CI real de GitHub Actions en verde**, python y frontend, sobre el commit cuyo árbol es el esperado | **No ejecutada** |
| A8 | Revisión humana del diff | Pendiente. La revisión de este informe es local |
| A9 | Guarda 05v2: 7/7 en la CI real, no omitidas. Con 06v3 lo exige el gate | Pendiente |
| A10 | Una falla de la primera CI se nombra y se compara con la base; no se atribuye sin evidencia | Procedimiento |

## 3. Reversión
- **Orden inverso:** 07 y 06v3 si se integraron; 03; **B**; **A entera**.
- **Simulado:**
  - revertir B devuelve exactamente el árbol de A;
  - revertir A devuelve exactamente el árbol de `72ffae5`.
- **Con B (05v2) en la rama:**
  - revertir solo A, o solo 02v3, pone la guarda en **rojo**;
  - por eso B se revierte **antes** que A.
- **Datos:** no hay que tocar la base de datos. La procedencia es JSON extra en `conditions` y la API vieja la lee.

## 4. Lo que la integración no resuelve
Ver `MATRIZ_RIESGOS.md`. Para la integración bloquean:
- la CI real;
- la revisión humana;
- seguir el procedimiento de A (un único commit).

R24, R15, R3, R17, R18 y R6 no bloquean la integración del backtest, pero sí el uso productivo del almacén o el vivo, según el caso.
