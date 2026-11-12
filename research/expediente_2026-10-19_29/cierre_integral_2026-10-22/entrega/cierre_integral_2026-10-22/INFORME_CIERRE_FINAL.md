# Informe de cierre integral: TRADER-IA v3r3 + guarda 05 + R19 + integración controlada (2026-10-22)

**Base:** `72ffae5d2698440c8f1afaff12e07bd8adde66fb`.

**Insumos verificados:**
- paquete `cierre_D1_D2_guarda_R19_2026-10-22.zip` (`410ae629de17957fc6fb60701f94aee9c73631bc3e9238c67a4c75983efba3c5`);
- v3r3 (`25902649d6d0789598870769670f2e7a5c707f1856e1e1538bd4f74d37877c4a`).

**Sin commits, push, ramas, PR, merge ni deploy. Sin trading real. `validada_para_operar` no se tocó.**

**Cómo leer la evidencia:**
- **L** = local, en esta máquina.
- **CI** = GitHub Actions real. **No hay ninguna:** la CI real no corrió.
- **X** = externa (venue, testnet, entorno objetivo). **No hay ninguna.**

Los resultados anteriores (v3r2, v3r3, paquete `410ae629`) están congelados y no se reescriben. Lo nuevo de esta misión está en `evidence/` y en `logs/`, separado.

## Resumen ejecutivo
1. **Integridad:** el paquete y v3r3 coinciden con los hashes informados. 67/67 y 104/104 archivos verifican, sin archivos de más ni de menos (`evidence/registro/A1_*`).
2. **R19: NO_REPRODUCIDO.**
   - 0 fallas en 252 corridas, con el instrumento válido según la regla prerregistrada.
   - Con el bucle activo y sin carga, el vaciado tarda unos 7 s (máximo 9,0 s) frente al límite de 10 s: **margen de unos 1 s**.
   - No se corrigió nada. Los controles que harían falta para detectar persistencia incompleta quedan propuestos (`RESULTADOS_R19.md`).
3. **Guarda 05:**
   - la v1 del paquete tenía 5 defectos demostrados: se omitía sin versión registrada, con la forma corta «1.1» y con B sin A, y daba un falso positivo con un cierre límite reduce-only;
   - **05v2** los corrige: 25 de 26 casos dan lo esperado, por la razón correcta. El restante es M7, fuera de alcance por diseño;
   - robustez: 0 falsos positivos en 300 corridas;
   - contra 02v3 sin 01 falla en todas las combinaciones.
4. **Unidad A (01 + 02v3):** exactamente 8 archivos, revisados línea por línea. La integración se simuló sin commits: aplica en cualquier orden con el mismo árbol, revertir B devuelve A, revertir A devuelve la base y no hay cambios ajenos. **Lista para revisión humana**; falta la CI real.
5. **R24, PostgreSQL 16.15 desechable y aislado:**
   - migraciones OK;
   - las 14 pruebas de trazabilidad pasan contra PostgreSQL;
   - el módulo 07 (transacciones, recuperación, NaN, rechazo) pasa 4/4.
6. **R15 confirmado en PostgreSQL:** con dos guardados simultáneos, 32 de 50 veces se aceptan los dos. Pendiente, con diseño propuesto.
7. **Nuevo, R25 (Binance):**
   - el adaptador rechaza el stop protector del vivo (`OrderType.STOP` sin traducción) aunque declara que soporta stops. Reproducido con una sonda sin red;
   - **por inspección**, el vivo sigue sin stop en el venue. No lo resuelve ningún parche, ni R19 ni la guarda 05;
   - **bloquea el vivo sobre Binance.**
8. **Gate de CI (06v3):** se corrigieron dos defectos propios demostrados. 06 v1 fallaba el lint de su propia CI y 06v2 fallaba abierto si no podía importar el motor. 06v3 da 11/11 en las pruebas del gate.
9. **Repositorio protegido intacto; dinero real bloqueado** (`evidence/registro/99_*`).
   - Una incidencia, aislada y revertida: un `ruff --config` mío dejó un `.ruff_cache/` ignorado en su raíz.
   - No tocó archivos rastreados ni el estado de git. Lo quité, y el estado final es idéntico al inicial.

## A. Verificación inicial
| Comprobación | Resultado | Evidencia |
|---|---|---|
| SHA-256 del paquete | `410ae629…` coincide; 884.784 bytes | `evidence/registro/A1_integridad_paquete.txt` |
| Extracción limpia del paquete | 68 archivos; 67/67 en `SHA256SUMS`; sin sobrantes ni faltantes; 0 bytecode y 0 enlaces | ídem |
| v3r3 dentro del paquete | `25902649…` coincide; 104/104; idéntica a la carpeta publicada | ídem |
| Repositorio protegido al inicio | HEAD `72ffae5`, 0 cambios, refs y reflog idénticos al cierre anterior | `evidence/registro/A2_*` |
| Congelados (T-MULTI, T-papel, H-CARRY, E1, E2, E3) | 8/8 manifiestos OK; 0 cambios en `research/tendencia_btc` | ídem |
| Entregas previas | v3, v3r2, revisión, paquete y v3r3: idénticas al registro | ídem |
| Protección | Clones con push deshabilitado (`no-push://…`); el push de prueba se rechaza | `evidence/registro/A3_*` |

## B. R19 (detalle: `RESULTADOS_R19.md`)
- **Diseño y criterio:** la enmienda 1, congelada y verificada por hash antes de correr. El preregistro de ejecución (`evidence/registro/B1_*`, `aaa47d55…`) se escribió **antes** de la primera corrida.
- **Ejecución:**
  - 252 corridas en orden aleatorio intercalado (semilla 20261022), con `unshare -n`;
  - carga de 0, 4 y 8 quemadores, con el bucle activo y aparcado, en la base y en la candidata;
  - 240 corridas de la prueba sola y 12 del módulo completo.
- **Validez:** (i) 0 % sin JSON o por límite; (ii) 0 fallas sin su registro de vaciado; (iii) 0 trazas de la sonda → **válido**.
- **Decisión congelada:** NO REPRODUCIDO → **NO_REPRODUCIDO**.
- **Medida continua (no decisoria):** vaciado de 7,0 y 6,7 s de mediana (base y candidata) con K0 y el bucle activo; máximos de 9,01 y 8,91 s; 3/20 corridas ≥ 8 s en cada árbol.
- **Suplementaria (registro pasivo):** con K0, 12–14 mil escrituras por prueba y hasta unas 9.600 pendientes, todas completadas; `persistence_flushed=True`.
- **Límites:** quemadores de CPU pura; N = 20 por celda (cota del 16,8 %); intervalo de producción sin probar; la causa de las fallas de R10 sigue sin explicar.
- **Corrección:** **no necesaria por evidencia de defecto; no se inventó ninguna.** Los controles de detección y comunicación (exponer `persistence_flushed`, profundidad y antigüedad de la cola, alerta, bloqueo al reiniciar) quedan **propuestos y pendientes**.

## C. Guarda 05
**Detalle:** `evidence/C_guarda/MATRIZ_MUTANTES_GUARDA.md` y `evidence/C_guarda/robustez/COMPARACION_v1_v2.txt`.

**Verificación independiente sobre los árboles de la extracción limpia de v3r3:**
- v1 y v2 pasan 7/7 en la obligatoria y en la completa;
- en 02v3 sin 01, las dos dan 5 fallas y 2 pasan;
- en la base y en 01 sin 02v3, **v1 se omite (2 pasan, 5 omitidas) y v2 falla (5 fallas)**.

**Mutantes (26 casos):**
- 4 de combinación de unidades;
- 9 de protección: M1–M6, M8–M10;
- M7, fuera de alcance;
- 2 de interfaz: E1 y E2;
- 2 de mecanismo de cierre: C1 y C2;
- 8 de etiquetas: L1–L8.

**Cómo se evalúan:** cada detección debe fallar con el texto previsto, no con cualquier falla.

| | v1 (paquete) | v2 (esta misión) |
|---|---|---|
| Dan lo esperado | 20 de 26 | **25 de 26** |
| Defectos | N2 y N3 vivos (B sin A; 02v3 revertido solo); L6 vivo («1.1» sin D1–D3); L7 omitido («1.1» con D1–D3); C1 falso positivo | ninguno |
| M7 (aviso del informe, no regla del venue) | no detectado | no detectado (alcance: lo cubre la prueba de 01) |

**Robustez:** 300 corridas en el motor correcto (3 datos × 20 semillas × 5 escenarios) y 150 en 02v3 sin 01.
- 0 falsos positivos con v1 y con v2.
- Potencia por escenario: d1 30/30, d2 30/30, d3_parciales 13/30, d3_ioc 30/30 y todo_junto 30/30.
- La guarda completa falla en el 100 % de las combinaciones de datos y semilla.
- **Determinismo:** dos ejecuciones independientes dan filas idénticas en todas las claves.

**Cambio de v1 a v2:**
- `guarda_v1_a_v2.diff`;
- sin versión registrada, **falla** (no se omite);
- la forma corta se normaliza (1.1 = 1.1.0);
- «cierre» es toda orden reduce-only que no sea un stop.

**No se debilitó ninguna comprobación.**

## D. D1 / R4c / D2 (documental, sobre v3r3)
- **D1 / R4c:** el paso 4b de la reproducción limpia (Fase E) confirma de nuevo los puntos de abajo. Con B integrada, **05v2 detecta esa combinación** (N1, E1, E2, C2, L4 y L6 en rojo, por la razón correcta).
  - 02v3 aplica sin 01;
  - sin 01 declara 1.1.0 en un motor sin D1–D3;
  - las 14 pruebas de trazabilidad pasan igual;
  - git permite revertir cada uno por separado.
- **D2:** `evidence/D_D2_y_CI_en_v3r3.txt`.
  - Los documentos de v3r3 separan hechos (H1–H10) e inferencias (I1–I4) y tienen la sección «Qué no guarda».
  - No queda ninguna atribución directa a R19.
  - Todos dicen que GitHub Actions no corrió.
- **v3r3 no se modificó.**

## E. Suites desde una extracción limpia
Detalle: `evidence/E_resumen/RESUMEN_SUITES.md`. Todas las corridas son **locales**: con Python 3.11.17 y las 74 versiones fijadas (`freeze` `a1a96cac…`), en un venv **nuevo** creado desde PyPI por `reproducir.sh`, con `env -i` y desde la extracción limpia de v3r3.

| Suite | Pruebas | Resultado |
|---|---|---|
| Base `72ffae5` | 1956 | 1956 pasan |
| 01 + 02v3 | 1978 | 1978 pasan (22 nuevas; sin regresiones) |
| 01 + 02v3 + 03 | 1978 | 1978 pasan |
| **Final: A + 05v2 + 03 + 04 + 06v3** (árbol `0477c6a2…`) | **1985** | 1985 pasan (= 1978 + las 7 de la guarda) |

**Además:**
- D1–D3 contra el motor original: 8/8 fallan por aserción.
- Paso 4b (R4c), mutantes (10 + 14, 0 vivos), reloj fijado a 5 horas, persistencia 3/3, alembic y paridad con E1: **reproducción completa sin diferencias**.
- Los conteos coinciden exactamente con 1956, 1978 y 1985: no hay diferencias sin explicar.

**Correcciones demostradas en esta fase (antes → después):**
1. **06 v1 → 06v2 (lint).**
   - Con 06 v1, `ruff check packages tests scripts` (el paso de lint de su propio `ci.yml`) falla con 5 errores en `scripts/ci_gate.py`: la CI real fallaría antes de correr las pruebas.
   - 06v2 sigue los idiomas del repositorio y deja ruff limpio.
2. **06v2 → 06v3 (el gate fallaba abierto).**
   - 06v2 leía `ENGINE_VERSION` importando el motor. Ante cualquier `ImportError` dejaba de exigir la guarda.
   - Con un intérprete sin dependencias, **aprobaba un JUnit con las 7 pruebas de la guarda omitidas**: 06v2 dio 10/11 casos.
   - 06v3 lee la versión de la fuente del checkout, sin importarla, y falla cerrado si no puede leerla: **11/11** (`evidence/E_gate/`).
   - Lo destapó un defecto de mi propio arnés, que resolvía el enlace del venv. Lo corregí, y la primera corrida queda como evidencia.
   - Ninguna comprobación se debilitó. Los veredictos esperados de los 9 casos originales no cambiaron.

## F. Integración simulada y diferencias
**Simulación:** `evidence/F_simulacion/SIMULACION_INTEGRACION.txt`, con 0 problemas.
- A cambia exactamente 8 archivos, idénticos a los registrados en v3r3, y declara `ENGINE_VERSION` 1.1.0.
- B agrega solo la guarda.
- Revertir B da exactamente el árbol de A; revertir A (02v3 y después 01) da exactamente el de `72ffae5`.
- No quedan cambios ajenos.
- B sin A, o con A a medias, pone la guarda en rojo.
- 02v3 antes que 01 da el mismo árbol.
- 03 aplica sobre A+B.

**Árboles esperados:** en `PLAN_INTEGRACION.md` §0.

**Diferencias, leídas línea por línea:** `evidence/F_diferencias/REVISION_DIFERENCIAS.md`. Los parches nuevos (05v2, 06v3 y 07) se revisaron al escribirlos; 06v3 está reescrito dos veces por defectos demostrados (ver §E). 07 aplica sobre el árbol final.

## G. CI, PostgreSQL y riesgos
- **CI real: NO EJECUTADA.**
  - El parche **06v3** (opcional) prepara un gate que liga la corrida al commit, al árbol, a Python, a `pip freeze` y a los hashes de `ci.yml`, de las restricciones y de `pyproject.toml`. También guarda la evidencia como artefacto y **falla** si la guarda no corrió y pasó 7/7 cuando el motor declara ≥ 1.1.0.
  - Lee la versión del motor de la fuente, falla cerrado y se probó localmente con el JUnit real y 10 variantes, una de ellas con otro intérprete: 11/11 (`evidence/E_gate/`).
  - Las pruebas locales **no** sustituyen la CI real.
- **R24:** verificado localmente con PostgreSQL 16.15 (`evidence/G_R24/`).
  - Instancia desechable, sin TCP, con socket local y `fsync=on`.
  - Las 14 pruebas existentes de trazabilidad corrieron contra PostgreSQL: se crearon 5 bases en el servidor.
  - El módulo 07 pasa 4/4; sin la variable se omite, y nunca cae a SQLite.
  - Migraciones (alembic) desde cero en la base y en la completa.
  - No es la CI ni el entorno de producción.
- **R15:** confirmado (32/50). **R17 y R18:** pendientes; R18, por inspección. **R3:** identificado, pendiente. **R6:** identificado y aceptado. **R21:** verificado en PostgreSQL. **R25 (Binance):** nuevo, reproducido en el adaptador. Ver `MATRIZ_RIESGOS.md`.

## H. Paquete
- **Estructura:** `INFORME_CIERRE_FINAL.md`, `MATRIZ_RIESGOS.md`, `RESULTADOS_R19.md`, `PLAN_INTEGRACION.md`, `MANIFEST.sha256`, `patches/`, `tests/`, `logs/`, `evidence/`, `reproduction/` y `config/` (sin secretos).
- **Cómo reproducir:** `reproduction/COMANDOS_REPRODUCCION.md`.
- **Verificación del ZIP:** desde una extracción limpia independiente (`VERIFICACION_EXTRACCION_LIMPIA.txt`, junto al ZIP).

## Incidencias de esta misión (hechos, sin atenuar)
1. **`.ruff_cache/` en el repositorio protegido.**
   - El 2026-10-22 a las 22:17:56 corrí `ruff check --config /home/user/Trader-IA/pyproject.toml <archivo del scratchpad>`, y ruff creó su caché en la raíz del repositorio protegido: 3 archivos, ignorados por `.gitignore`.
   - Lo detectó el registro 99: 19 ignorados frente a 18.
   - Sin cambios en archivos rastreados, el índice, HEAD, las refs, el reflog ni el stash.
   - Quité solo ese directorio. El estado final es **idéntico** al inicial, incluida la lista de ignorados (`evidence/registro/99_*`).
2. **Arnés del gate:** resolvía el enlace del venv y corría otro intérprete. Lo corregí, y la corrida defectuosa se conserva como evidencia. Ese error destapó el defecto real del gate 06v2 (§E).
3. **06 v1 y 06v2** (parches propios de esta misión) tenían defectos, demostrados y corregidos en 06v3 (§E). No se integran.
4. **Conteo de mutantes de la guarda:** un borrador decía 27 casos. Son **26**; la matriz se corrigió antes del empaquetado.
5. **Reinicio del contenedor** entre la Fase E y la corrección del gate: el directorio de trabajo se conservó completo y las corridas largas ya habían terminado. Las corridas posteriores (06v2 y 06v3) se hicieron con la máquina sin otra carga.

## Decisiones que requieren tu autorización (ninguna se ejecutó)
1. Crear una rama local en el repositorio protegido y aplicar A en **un único commit**, con el árbol esperado `5d6a0954…`.
2. Aplicar B (05v2) en un commit aparte, con el árbol esperado `4ef14d31…`.
3. Aplicar 03, y opcionalmente 04 + 06v3 y 07.
4. **Push** (dispara la primera CI real) y **PR en borrador**.
5. Merge, solo con la CI real en verde, la revisión humana y el árbol esperado.
6. Corregir R15 (cambia 02v3: requiere reabrir la unidad A) y R25 (adaptador de Binance y vivo; requiere testnet).
7. Implementar los controles de persistencia propuestos para R19.

## I. Tabla de decisión
**Tipos de evidencia:** **L** = local (esta máquina); **CI** = GitHub Actions real; **X** = externa (venue, testnet, entorno objetivo).

| Área | Estado exigido | **Estado** | Evidencia (tipo) |
|---|---|---|---|
| Integridad del paquete | Verificado / discrepancia | **Verificado** | `410ae629…` y `25902649…` coinciden; 67/67 y 104/104; extracción limpia (L) |
| v3r3 | Aprobada como candidata / bloqueada | **Aprobada como candidata** (documental y técnica) | Reproducción completa desde una extracción limpia sin diferencias; D2 sin atribuciones a R19 ni CI declarada (L) |
| R19 | Reproducido / no reproducido / inconcluso / bloqueado | **No reproducido** (NO_REPRODUCIDO) | 0/252 corridas, instrumento válido, decisión congelada; además, la prueba pasó en 6 suites completas (L). Margen de unos 1 s con K0: riesgo de intermitencia en un runner más lento (inferencia) |
| Corrección R19 | Verificada / parcial / pendiente / no necesaria | **No necesaria** para un defecto (no reproducido); los **controles de detección y comunicación quedan pendientes** (propuestos, no implementados) | `RESULTADOS_R19.md` |
| Guarda 05 | Verificada / parcial / bloqueada | **Verificada: 05v2** (v1 rechazada) | 26 mutantes: v2 da 25/26 por la razón correcta (M7 fuera de alcance); robustez con 0 FP en 300 corridas; determinista; ruff limpio (L). **No corrió en la CI** |
| Unidad 01 + 02v3 | Lista para revisión / bloqueada | **Lista para revisión** | 8 archivos exactos, revisados línea por línea; suites, mutantes, simulación de integración y reversión (L). Falta la revisión humana (A8) y la CI real (A7) |
| R4c | Verificado / pendiente | **Pendiente** (mitigado) | Con B integrada, 05v2 lo detecta (N1, E1, E2, C2, L4 y L6 en rojo; L), y 06v3 exige la guarda 7/7 (L). Git sigue permitiéndolo; la detección efectiva depende de la CI real |
| CI real | Aprobada / fallida / no ejecutada | **No ejecutada** | Ninguna evidencia CI. Preparados: 04 y 06v3 (gate que liga commit, árbol, entorno y evidencia; L) |
| PostgreSQL R24 | Verificado / bloqueado / pendiente | **Verificado localmente** (almacén de backtest, PostgreSQL 16.15 desechable); **pendiente en CI y en el entorno objetivo** | Migraciones, 14 pruebas de trazabilidad y 07 4/4 contra PostgreSQL (L). No se usó SQLite como sustituto |
| R18 | Corregido y verificado / pendiente | **Pendiente** | Identificado por inspección (`live.py:2062-2064`); sin corrección ni prueba |
| R15 y R17 | Verificados / pendientes / no identificados | **R15: verificado como defecto (confirmado en PostgreSQL, 32/50) y pendiente. R17: identificado, pendiente** | Sonda R15 (L); R17 según la matriz de v3r3, sin prueba nueva |
| R3 y R6 | Identificados / no identificados | **Identificados** (R3 pendiente, fuera de alcance; R6 aceptado, por inspección) | `engine.py:979-982` frente a `live.py:3433` |
| Binance: protección de posiciones (R25) | — | **Defecto reproducido en el adaptador; pendiente; independiente de R19 y de la guarda 05** | Sonda sin red (L); consecuencia en el vivo por inspección; sin X (testnet) |
| Repositorio protegido | Intacto / discrepancia | **Intacto** (tras revertir una discrepancia propia: `.ruff_cache/` ignorado, ver «Incidencias») | `evidence/registro/99_*`: estado idéntico al inicio, incluidos los ignorados; congelados 8/8; entregas previas idénticas (L) |
| Trading real | Bloqueado | **Bloqueado** | Sin token ni compuerta tocados; `validada_para_operar` no se tocó y su valor no se puede afirmar (no se encontró la marca); R25 bloquea además el vivo sobre Binance |
