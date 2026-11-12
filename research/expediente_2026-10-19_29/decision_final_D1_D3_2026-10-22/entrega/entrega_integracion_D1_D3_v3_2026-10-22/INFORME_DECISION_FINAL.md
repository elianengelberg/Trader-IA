# Decisión final de integración D1–D3 — revisión independiente (v3)

**Fecha:** 2026-10-22. **Base:** `72ffae5d2698440c8f1afaff12e07bd8adde66fb`.
- Es una revisión de ingeniería. **No es una validación de rentabilidad**, no autoriza a operar y no es evidencia de ventaja estadística.
- No se hizo ningún commit, push, PR, merge ni deploy. El repositorio original no se tocó (`registro/00` y `99`).

## 1. Decisión: **B — LISTO CON CORRECCIONES**
- **El defecto:** el parche 02 de la entrega v2 permitía una sobrescritura silenciosa entre resultados de procedencias distintas. Afecta a la prioridad 2.
- **La corrección:** mínima, se hizo en una copia aislada y se verificó (parche `02v3`).
- **Después de corregirla no queda ningún bloqueante técnico conocido** para integrar 01 + 02v3. Quedan:
  - riesgos residuales documentados como pendientes: R7, R15, R17, R18, R19, R24;
  - la primera corrida real de CI, que tiene que ocurrir antes de fusionar.

**Recomendación inequívoca: integrar 01 + 02v3 como unidad inseparable, más 03.**
- **No integrar el 02 original.**
- El 04 (CI con versiones fijadas) es opcional y queda a tu criterio, porque cambia la configuración de CI. Lo recomiendo.

**Por qué no A.** Elegir A habría sido certificar el 02 original. Las suites pasaban, pero la garantía que el informe v2 afirmaba («el guardado nunca sobrescribe un resultado de otra procedencia») no se cumplía para todo lo que la procedencia no registra.

**Por qué no C:**
- no hay problemas de integridad: los hashes, la aplicación de los parches y la reproducción coinciden;
- no hay problemas de seguridad;
- no hay regresiones: 1956/1956 → 1978/1978 en dos entornos, y la paridad con E1 da 0 diferencias no explicadas;
- no hay problemas de validez de los experimentos: E1, E3-H1, T-MULTI y T-papel están intactos.

## 2. Qué se revisó y cómo
- **Patches desde el ZIP v2** (`793e8d6a…`): verificados contra sus hashes declarados y leídos completos. Ver `MATRIZ_REVISION_PARCHES.md`.
- **Cobertura de la procedencia** (`evidencia/R11_*`):
  - los 57 módulos `tia.*` cargados al correr un backtest están dentro de la huella del motor;
  - los 27 campos de `BacktestConfig` entran en el `run_id`.
- **Sustitución de partes del motor:** la sonda `herramientas/sonda_misma_procedencia.py` reemplaza en memoria una pieza del motor (el proveedor de ejecución) por una variante. Así se simula «algo que la procedencia no registra» y se mide si el guardado lo acepta.
- **Compatibilidad histórica con código real de las dos versiones** (`R5_*`): la API de `72ffae5` escribe, la corregida lee, escribe y re-corre, y la vieja vuelve a leer.
- **Parche 03** (`R8_*`, `api/state.py`):
  - las líneas que quita y las aserciones que agrega;
  - si las condiciones que corrige pueden darse en producción.
- **CI:** cada paso de `ci.yml` reproducido localmente (§4).
- **Comprobaciones repetidas con los archivos finales:**
  - suites en dos entornos;
  - mutantes;
  - paridad con E1 en dos entornos;
  - reproducción desde la extracción limpia del ZIP v3 (registro externo).

## 3. El defecto del parche 02 y su corrección
- **Síntoma** (`evidencia/R1_*`):
  - dos corridas con la misma procedencia registrada (versión, huella del motor, datos y universo iguales) y números distintos (9 frente a 8 operaciones);
  - el 02 original **aceptó** el segundo guardado y dejó una sola fila con los números del último.
- **Causa:**
  - el guardado comparaba solo la procedencia registrada;
  - la procedencia no puede registrar todo lo que cambia números: un redespliegue con otras versiones de numpy o Python (la CI hoy resuelve 3 paquetes distintos a los fijados) o una pieza sustituida por quien llama al motor.
- **Corrección** (`parches/02v3_*`; diferencia exacta en `evidencia/R6_*`):
  - bajo el mismo `run_id` y la misma procedencia, `BacktestRepository.save` compara los números guardados (`bars`, `trades`, `total_return_pct`, `max_drawdown_pct`, `sharpe`, `equity_curve`; NaN = NULL) y **rechaza** si difieren;
  - se corrigió el comentario de `engine.py`, que sobrestimaba lo que cubre el id, y la frase de `ARCHITECTURE.md`.
- **Verificación:**
  - la misma sonda ahora es **RECHAZADA** y se conserva el primer resultado (`R3_*`);
  - la prueba nueva falla con el 02 original (`R2_*`);
  - las 14 pruebas de trazabilidad pasan;
  - mutantes de trazabilidad: 14, 0 vivos, 1 equivalente (`R4_*`);
  - números del motor idénticos (paridad con E1).
- **Efecto aceptado (R21):** una re-corrida legítima después de un cambio de entorno que cambie números se rechaza en voz alta (HTTP 400) en lugar de sobrescribir.

## 4. CI: qué reproduce lo local y qué exige una corrida real
- **`ci.yml` nunca corrió.** No se afirma que la CI esté en verde.

| Paso de `ci.yml` | Reproducción local | Resultado |
|---|---|---|
| `pip install -e ".[api,db,postgres,redis,llm,dev]"` (sin versiones fijadas) | Venv nuevo con Python 3.11.17 y el mismo comando | Código 0; 74 paquetes; **3 distintos a los fijados**: alembic 1.20.1, coverage 7.17.0, python-dateutil 3.0.0 |
| `ruff check packages tests scripts` | Con las versiones fijadas y sin fijar | Código 0 |
| `python -m pytest tests -q` (con `PYTHONPATH`) | Mismo comando más JUnit, en los dos entornos | Base 1956/1956; integración 1978/1978; sin regresiones |
| `alembic upgrade head` sobre SQLite vacío | Mismo comando y variable | Código 0, versión 0007 |
| frontend: `npm ci`, `typecheck`, `build` | Node 22.22.0, npm 10.9.4 | Código 0 en los tres. Los parches no tocan `frontend/` |

**Lo que solo una corrida real puede verificar:**
- que el workflow se dispare y se ejecute (`on: push / pull_request`, `permissions`);
- las acciones `actions/checkout@v4`, `setup-python@v5` y `setup-node@v4`;
- la imagen `ubuntu-latest` y su parche de Python 3.11;
- el comportamiento de `cache: pip` sin un archivo de dependencias declarado;
- la resolución de dependencias en ese momento (sin el parche 04);
- los límites de tiempo (30 y 15 min; localmente la suite tarda unos 6 min);
- la red hacia PyPI y npm desde el runner.

**Restricciones no conectadas a la CI.** `entorno/ci-py311.txt` no estaba en `ci.yml`.
- **Solución mínima:** parche 04 (opcional), que agrega `constraints/ci-py311.txt` y dos líneas en `ci.yml`: `-c constraints/ci-py311.txt` y `cache-dependency-path`.
- **Verificado localmente:** YAML válido, y el paso «Install» tal cual instala las 74 versiones fijadas.
- **Mantenimiento:** el archivo se regenera a propósito (instrucciones en su encabezado).

**Si la primera corrida de CI falla:**
- compararla con la base: correr la CI también sobre `72ffae5`, o leer `evidencia/S_*`;
- si falla `persistence writes still in flight` en una prueba de `test_account_restore`, `test_funding_*` o `test_adverse_recovery` que **no** está en el parche 03, es R19, preexistente;
- no se fusiona con rojo: se re-corre y, si persiste, se aplica el seguimiento de R19.

## 5. Auditoría de las afirmaciones de v2 frente a la evidencia
| Afirmación de v2 | Veredicto hoy |
|---|---|
| Las 8 pruebas D1–D3 fallan con el original y pasan con el parche | **Respaldada** (repetida) |
| Mutantes D1–D3: 10, 0 vivos | **Respaldada.** M10 solo por cobertura, ya declarado |
| «El guardado nunca sobrescribe un resultado de otra procedencia» | **Insuficiente:** cierta para la procedencia registrada, falsa para lo no registrado. **Corregida en 02v3** |
| «Una fila escrita exactamente como la escribía 72ffae5 convive» | **Sobrestimada en v2:** la fila era simulada; solo la fórmula del id se verificó contra el motor real. **Hoy respaldada con la API real** (`R5_*`) |
| La trazabilidad no altera números | **Respaldada:** E17 = v2 = v3 en dos entornos |
| Paridad con E1: 45 / 5 / 4 / 0 | **Respaldada** (repetida con el motor v3) |
| Sin regresiones | **Respaldada,** también con las versiones sin fijar de hoy |
| Causas de B3 (reloj 5 h 55 m; bucle de fondo) | **Respaldada** |
| R19: «pasaron hoy, sin holgura medida» | **Incompleta:** hoy falló bajo carga, en la base y en la integración. Sube a severidad media |
| Frontend y migraciones no verificados | Cierto entonces; **hoy verificados localmente** |
| Comentario «everything that decides the numbers is in the id» | **Sobrestimado.** Corregido en 02v3 |

## 6. Riesgos
Ver `MATRIZ_RIESGOS.md`. Lo pendiente, explícitamente no resuelto:
- R7: CI sin corrida real;
- R15: guardado no atómico;
- R17: sin stop durante un cierre parcial;
- R18: reversión rechazada sin reintento;
- R19: patrón latente en otras pruebas, ahora observado;
- R22: huella sobre archivos en disco;
- R24: sin prueba contra PostgreSQL;
- R3: el vivo sin las capas 2 y 3 de D3;
- R8: sin firma digital.

## 7. Integración local controlada
- **Árboles preparados:** `fin_obligatoria` (01 + 02v3) y `fin_completa` (01 + 02v3 + 03), aplicados en cadena sobre clones nuevos de `72ffae5`, con archivos resultantes registrados (`parches/SHA256_archivos_resultantes_*_v3.txt`).
- **Corridas:**
  - suites;
  - lint;
  - trazabilidad;
  - regresión D1–D3;
  - mutantes;
  - compatibilidad histórica;
  - migraciones;
  - frontend;
  - paridad.
- Ver `EVIDENCIA_EJECUCIONES.md` y `COMPARACION_BASE_VS_INTEGRACION.md`.
- Orden de los cambios y reversión: `PLAN_INTEGRACION_Y_REVERSION.md`.
- Lo que necesita tu autorización: `ACCIONES_QUE_REQUIEREN_AUTORIZACION.md`.
