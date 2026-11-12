# Informe final: integración controlada, corrección de bloqueantes y simulación realista (Trader-IA)

**Fecha:** 2026-10-25, de 18:12 a 20:30 UTC aproximadamente.
**Estado de autorización: NO AUTORIZADO PARA OPERAR CON DINERO REAL.**

## Lo esencial

- **Repositorio protegido:** `/home/user/Trader-IA` (`/home/tia/Trader-IA` no existe). Está intacto:
  - HEAD `72ffae5`;
  - índice `37490035…` antes y después;
  - 0 cambios; mismas refs, mismo reflog (13 entradas); 0 tags, 0 stash.
- **Lo que no se hizo:** ningún commit, push, PR, merge ni deploy; ninguna orden real; ninguna credencial.
- **Candidato integrado en clones aislados:** árbol **`17332e1c510d0004f7744bde0a68f008f01652b7`**.
  - Base 72ffae5 + 01, 02v3, 05v2, 03, 04, 08, 07, 09, 10, 11, 12, 13 y 15.
  - 06v3 se conserva solo como evidencia; 14 es opcional y no se incluye.
- **Corregido y verificado aquí:**
  - R18 (ventana sin stop, tolerancia 0);
  - R15 (PostgreSQL: de 266 éxitos falsos a 0);
  - R19 (de 2 falsos «completo» a 0);
  - R24-H1 (migración reversible, PostgreSQL);
  - el gate de CI (v4: 0 aprobados en falso en 48 casos);
  - la prueba que fallaba de 00:00 a 05:55 UTC (parche 03, demostrado con reloj desplazado y mutante);
  - 4 defectos nuevos (N1, N2, N5, N7).
- **R25 (stop protector en Binance): corregido en el código, pero BLOQUEANTE para el vivo** hasta que la testnet confirme que Binance acepta el `STOP_LOSS`. No se simuló una respuesta de Binance como prueba de compatibilidad; la compuerta de activación ahora **exige** ese registro de testnet.
- **CI local equivalente sobre el árbol final** (`logs/J_main`, `logs/J_pg`):
  - job python: 2038 pruebas, 2028 pasan y 10 omitidas de PostgreSQL permitidas;
  - job postgresql: 2038 de 2038, 0 omitidas;
  - en los dos: ruff OK, gate v4 `pass`, guarda 7 de 7, árbol de procedencia = candidato;
  - migraciones SQLite OK y PostgreSQL arriba, abajo y arriba OK.
  - **La CI remota no corrió** (falta autorización para el push).
- **Simulación integral en papel:** candidato 15 de 15 escenarios (semillas 7 y 8); base 10 de 15; E15 (reversión de versión) es segura.
- **Evaluación cuantitativa: ventaja no demostrada.** 1.1.0 y 1.2.0 dan resultados idénticos en 12 de 12 corridas sobre datos sintéticos (el camino de R18 no se activa ahí). El evaluador dice `insufficient_evidence`.

## 1. Tabla final de estados

| Ítem | Estado | Una línea |
|---|---|---|
| **P0 / R25** | **CORREGIDO_PARCIALMENTE**; **BLOQUEANTE** para el vivo con Binance | STOP → `STOP_LOSS` con pruebas y la compuerta exige testnet. Falta el registro de testnet |
| **R15** | **CORREGIDO_Y_VERIFICADO** | Inserción atómica, `FOR UPDATE` y resultados `CREATED`/`REPEATED`/conflicto. PostgreSQL 16.15: 0 éxitos dados a escritores descartados (base 266) |
| **R17** | **PENDIENTE** | Decisión de diseño (T8): el cierre en curso cuenta como cobertura; el resto no tiene stop propio |
| **R18** | **CORREGIDO_Y_VERIFICADO** (papel y backtest) | Tolerancia 0 medida al emparejar. Re-protección tras cierre rechazado, al llenarse la entrada y al reiniciar |
| **R19** | **CORREGIDO_Y_VERIFICADO** (sesión viva) | `flush` = sin escrituras en vuelo **y** sin fallas, con libro de escrituras y pérdidas identificadas. El motor de escenarios sigue pendiente (N3) |
| **R22** | **PENDIENTE** (aceptado antes) | Sin cambios |
| **R24-H1** | **CORREGIDO_Y_VERIFICADO** | `kind` de 64, migración 0008 reversible que se niega a cortar datos. PostgreSQL y SQLite |
| **R24-H2** | **PENDIENTE** | Sin definición en ninguna fuente; no se inventó |
| **R24-H3** | **PENDIENTE** | Ídem |
| **P2** | **CORREGIDO_Y_VERIFICADO** (local) | El gate v4 exige la guarda 05v2 (hash y 7 de 7) sobre la suite completa de esta corrida. Falta la CI real |
| **R3** | **PENDIENTE** | Fuera del alcance (paridad D3 del vivo) |
| **R6** | **PENDIENTE** (aceptado) | Sin cambios |
| **N1** (nuevo) | **CORREGIDO_Y_VERIFICADO** (transporte simulado) | Un error de transporte después de enviar = estado desconocido; sin reintento; se reconcilia |
| **N2** (nuevo) | **CORREGIDO_Y_VERIFICADO** | Colisión del client id del stop al reponerlo en la misma barra |
| **N3** (nuevo) | **PENDIENTE** | El `flush` del motor de escenarios dice `True` con fallas |
| **N4** (nuevo) | **PENDIENTE** (por inspección) | Ids de stop por barra en el motor de escenarios |
| **N5** (nuevo) | **CORREGIDO_Y_VERIFICADO** | Posición restaurada sin stop durante su primer emparejamiento (lo encontró E13) |
| **N6** (nuevo) | **PENDIENTE** (requiere autorización) | Docker no reenvía el SIGTERM y la gracia es de 10 s. Parche 14 opcional |
| **N7** (nuevo) | **CORREGIDO_Y_VERIFICADO** | El árbol de procedencia del gate omitía los archivos versionados que coinciden con `.gitignore` |
| **N8** (nuevo) | **PENDIENTE** (decisión T2) | Sin re-protección en `PAUSED` y `SAFE_MODE` |
| **N9** (nuevo) | **PENDIENTE** (decisión T5) | Una escritura perdida durante la sesión no bloquea las entradas |
| **Dinero real** | **BLOQUEANTE** | NO AUTORIZADO |

Detalle en `MATRIZ_RIESGOS.md`. Pruebas en `MATRIZ_PRUEBAS.md`. Decisiones en `DECISIONES_PENDIENTES.md`.

## 2. Separación de la evidencia

| Categoría | Qué entra |
|---|---|
| **Cambios de código** (parches de esta misión) | **08:** `binance_live.py`, `validate_binance.py`, `gate_probes.py`, `runtime/live.py`, `backtest/engine.py` (`ENGINE_VERSION` 1.2.0). **09:** `persistence/repositories.py` y `__init__.py`. **10:** `models.py`, migración `0008`, `repositories.py`. **11:** `runtime/live.py`. **12:** `ci.yml`, `scripts/ci_gate.py`, `ci_gate_policy.json`, `ci_provenance.py`. **13:** `runtime/live.py`. **15:** `binance_live.py`. Más pruebas nuevas y adaptadas (ver `MATRIZ_PRUEBAS.md` §3) |
| **Pruebas pasadas** (locales) | Suite completa: 2038 (job python: 2028 + 10 omitidas permitidas; job postgresql: 2038). Pruebas nuevas que fallaban sin el arreglo: 18 de 25 (R25 y R18) y 4 de 6 (N1). Arnés del gate: 47 casos + N04b. Mutante de la prueba horaria |
| **Verificado con PostgreSQL real** (16.15, desechable) | R15 (880 carreras por árbol); R24-H1 (6 tipos, de punta a punta); 07 (4 pruebas); 10 pruebas de PostgreSQL en la suite; migraciones arriba, abajo y arriba; job postgresql completo |
| **Verificado en testnet** | **Nada** |
| **Solo simulado** (papel) | E01–E15: reacción del vivo a un venue que rechaza stops (E04b), cierre rechazado (E08), parciales y respuesta perdida (E09), caídas (E10), persistencia incompleta (E12), apagado y reinicio (E13), orden ajena (E14). SIGTERM del contenedor reproducido con dash fuera de Docker |
| **No comprobable aquí** | Que Binance acepte `STOP_LOSS` con esos parámetros; el comportamiento real de errores de red de Binance; GitHub Actions; Docker; una base de producción |
| **Requiere autorización humana** | Commit, push, PR o merge; corrida de la CI real; credenciales de testnet; parche 14 (producción); decisiones T1–T12; cualquier uso de dinero real |

## 3. Respuestas

### 3.1 ¿Qué puede integrarse en una rama aislada?

- **La cadena completa hasta el parche 15** (árbol `17332e1c…`), como una rama aislada con un solo commit, **cuando lo autorices**. Su contenido:
  - las unidades A (01+02v3) y B (05v2);
  - 03 (pruebas de reloj y persistencia) y 04 (CI con versiones fijadas);
  - 07 (pruebas del almacén en PostgreSQL);
  - 08–13 y 15 (R25, R18, R15, R24-H1, R19, gate v4 con job postgresql, re-protección al reiniciar y transporte ambiguo).
- **Antes de mezclar:** la CI real en verde (jobs python, postgresql y frontend) y una revisión humana del diff.
- **No integrar:** 06v3 (reemplazado); los v1 de 12 (en `parches/historico/`).
- **Aparte, con autorización de producción:** 14 (Docker).
- **Cómo:** `reproducir.sh` reconstruye el árbol desde el repositorio de origen, con solo lectura; `INSTRUCCIONES_CI.md` §9 da los pasos.

### 3.2 ¿Qué defectos impiden una ejecución o una persistencia fiables?

- **Papel y backtest:** ningún bloqueante conocido después de los parches. Quedan riesgos acotados:
  - N3 y N4 en el motor de escenarios (corridas simuladas desde la API);
  - R17 (decisión de diseño);
  - N9: una escritura perdida durante la sesión no frena las entradas hasta la sesión siguiente.
- **Vivo con Binance:**
  - **R25** sigue bloqueante: falta la confirmación en testnet del `STOP_LOSS`. N1 tampoco tiene confirmación de testnet;
  - **N8:** no se repone el stop en `PAUSED` ni en `SAFE_MODE`;
  - faltan las decisiones de política T1, T4, T5 y T7 (qué hacer con una posición sin stop que no se puede proteger, límites de reintento, escrituras perdidas).
- **Producción en Docker:** **N6**. Un `docker stop` mata la sesión sin flush ni liberación del lease, hasta integrar el 14.

### 3.3 ¿Qué falta para una futura evaluación con dinero real?

1. CI real en verde sobre el árbol integrado, revisión humana firmada y protección de rama exigiendo el gate.
2. Testnet:
   - `validate_binance.py --account --order --stop --testnet` con un registro `protective_stop_accepted: true`;
   - pruebas de transporte ambiguo y de reconciliación contra el venue de prueba.
3. Decisiones T1–T9 tomadas por el propietario, implementadas y probadas; el parche 14 autorizado.
4. Un período de operación en papel y luego en testnet, con reconciliación diaria, sin posiciones desprotegidas ni registros incompletos.
5. Una evaluación cuantitativa **prerregistrada** sobre datos auténticos que demuestre ventaja después de costos (hoy: **ventaja no demostrada**).
6. Las definiciones de R24-H2, R24-H3 y D1–D17, si existen.
7. Una autorización explícita y separada para dinero real. Este trabajo **no** la da.

## 4. Seguridad y estado final

- **Trabajo aislado:** todo se hizo en clones `--no-local` dentro del scratchpad, con el push apuntando a `no-push://`.
- **PostgreSQL:** desechable (unshare, socket propio). Bases creadas y borradas por prueba; servidor detenido al final.
- **Repositorio protegido:** el índice se midió antes y después de cada paso que lo leía; siempre `37490035…`. Estado final en `VERIFICACION_FINAL.txt`.
- **`validada_para_operar`:** no existe en el repositorio protegido (0 coincidencias, incluidos los archivos ignorados). Nada lo creó ni lo modificó.
- **Compuerta de activación:** solo se volvió más estricta (exige el registro de testnet del stop).
- **No se tocó:**
  - T, T-MULTI, H-CARRY, E1, E3-H1 ni T-papel;
  - `fuera_de_muestra_T.py` (no se invocó);
  - los retornos reservados (no se leyeron);
  - los endpoints de exchanges (ninguno contactado);
  - las entregas previas ni sus evidencias (los parches previos se copiaron y sus hashes coinciden con el MANIFEST del paquete de cierre).
- **El paquete no contiene:** secretos, bases de datos, sockets, enlaces simbólicos ni `__pycache__`.

## 5. Contenido del paquete

| Archivo | Qué es |
|---|---|
| `INFORME_FINAL.md` | Este informe |
| `MATRIZ_RIESGOS.md` | Estado por riesgo y defecto, con evidencia y lo que falta |
| `MATRIZ_PRUEBAS.md` | Pruebas, experimentos, CI local, arnés del gate, dependencia horaria |
| `DECISIONES_PENDIENTES.md` | Fase M: T1–T12, D1–D17 y R24-H2/H3 no recuperados |
| `SIMULACION_INTEGRAL.md` | Fase K: E01–E15, base frente a candidato, semillas 7 y 8 |
| `RESULTADOS_CUANTITATIVOS.md` | Fase L: ventaja no demostrada |
| `INSTRUCCIONES_CI.md` | Equivalencia con el workflow, omisiones, fallas, arnés del gate, cómo correr la CI real |
| `parches/` | `CADENA.txt` (orden, sha256 y árbol esperado); 08–13 y 15; `14_OPCIONAL`; `previos/` (01, 02v3, 03, 04, 05v2, 07, sin modificar); `historico/` (12 v1, sustituido) |
| `reproducir.sh` | Reconstruye y verifica el candidato en un clon nuevo. No opera sobre el origen |
| `herramientas/` | Scripts de los experimentos, tal como se corrieron (con rutas absolutas de esta máquina) |
| `logs/`, `registro/` | Evidencia cruda y registros por fase |
| `MANIFEST.sha256`, `VERIFICACION_FINAL.txt` | Integridad y verificación final |
