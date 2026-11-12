# Revisión adversaria independiente del cierre integral de Trader-IA (paquete del 2026-10-22)

**Fecha de la revisión:** 2026-10-25, de 17:21 a 17:55 UTC.

**Directorio aislado:** `/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/revision_adversaria_2026-10-25/`. Las rutas relativas de este informe parten de ahí.

**Objeto:** `cierre_integral_2026-10-22.zip` (`ea670f91…`), su `INFORME_CIERRE_FINAL.md` y los parches 05v2 y 06v3, junto con las unidades de v3r3 que integra (01, 02v3, 03 y 04).

**Repositorio:**
- La ruta que da el pedido, `/home/tia/Trader-IA`, **no existe** en este entorno.
- El repositorio de la sesión es `/home/user/Trader-IA`: HEAD `72ffae5`, remoto `elianengelberg/Trader-IA`.
- Se trabajó **solo en lectura** sobre él, verificado al final (§9).

**Marcas de evidencia:**
- **[R]** reproducido en esta revisión;
- **[A]** verificado solo sobre artefactos del paquete;
- **[I]** por inspección de código;
- **[GH]** API de GitHub, solo lectura.

---

## 1. Veredicto ejecutivo: **APROBABLE CON CONDICIONES** (solo para integración técnica en una rama aislada)

**Qué se sostiene con evidencia independiente:**
- El paquete es íntegro.
- Sus suites se reproducen **exactamente**, con un venv nuevo desde PyPI.
- La unidad A (01 + 02v3) cambia los 8 archivos declarados y se revierte de forma **funcional**, también con datos ya escritos.
- La guarda 05v2 detecta, por la razón correcta, las combinaciones inválidas de A y B.
- R15 está confirmado y R25 está confirmado.

**Qué no se sostiene tal como está escrito:**
1. **«06v3 falla cerrado»:** es falso fuera de la forma actual del código. Con 18 casos adversarios, **8 aprueban lo que deberían rechazar**.
2. **«14 pruebas de trazabilidad contra PostgreSQL»:** solo **5** usaron PostgreSQL.
3. **«`ci.yml` nunca corrió»:** la CI real corrió y dio **verde sobre la base** (run 108). Nunca corrió sobre los parches.
4. **R18, «la pierna queda protegida por su stop»:** falso. Tras un cierre por reversión rechazado, la posición llega al emparejamiento de la barra siguiente **sin stop ni cierre**: 21 de 21 casos en el backtest; en el vivo, por inspección.

**Decisiones:**
- **A (rama aislada):** sí, con condiciones (§7).
- **B (merge a la rama protegida):** **no todavía**.
- **C (trading real):** **no**; R25 lo bloquea.

---

## 2. Resumen de hallazgos

| ID | Severidad | Estado | Evidencia | Impacto | Acción recomendada |
|---|---|---|---|---|---|
| H1 | **Alta** | Confirmado [R] | `logs/I_r25_runtime.txt`, `casos/test_r25_runtime.py`, `logs/I_sonda_adaptador_*.json` | El adaptador real rechaza `STOP` sin enviar nada. La sesión del vivo **sigue en RUNNING** con la posición abierta y 0 stops en el venue; reintenta y falla en cada barra; `unprotected_positions=0`; `last_error` vacío; solo avisos. Ninguno de los 27 checks de activación verifica el stop (`validate_binance.py` solo prueba LIMIT) | Bloquea el vivo sobre Binance. Corregir, probar en testnet y agregar un check de activación |
| H2 | Media | Confirmado [R] | `logs/C2_gate_adversario.txt` y `.json`, `casos/gate_adversario.py` | El gate 06v3 **aprueba sin la guarda** cuando el motor promete 1.1.0 en ejecución y `ENGINE_VERSION` está declarado dos veces (lee la **primera**), dentro de `if`/`try`, por tupla o importado. También aprueba una corrida con el **99,6 % omitido**, un **subconjunto de 4 pruebas** y **7 pruebas triviales** con el nombre de la guarda | El gate no es robusto a refactorizaciones ni a corridas parciales. No integrar 06v3 como control fuerte sin corregirlo |
| H3 | Media | Confirmado [R] en el backtest; [I] en el vivo | `logs/C1_ventana_reversion_paciente.txt`, `logs/C1_ventana_barrido.txt`, `casos/ventana_reversion2.py` | Con la estrategia «paciente» de las pruebas de 01 y el primer cierre rechazado, **21 de 21** cierres por reversión rechazados dejan la posición **sin stop ni cierre** al emparejar la barra siguiente. El precio no cruzó el nivel en estos datos, así que no hay impacto observado. La guarda tolera 1 barra (`MAX_BARS_UNCOVERED`) y la higiene tolera **8 barras** medidas **después** del sync: ninguna lo detecta | Contradice la matriz para R18. Corregir el orden (no cancelar el stop hasta confirmar el cierre, o reponerlo en la misma barra) y endurecer las pruebas |
| H4 | Media | Confirmado [R] | `logs/H_r15.txt`, `logs/H_r15_sonda_paquete.json`, `logs/H_r15_intercalados*.json` | R15 se reproduce: **35 de 50** carreras aceptan las dos escrituras (el informe decía 32 de 50). **Los dos escritores reciben «aceptado»** y gana el último. También con **otra procedencia** y el mismo `run_id` (12 de 20, alcanzable usando el repositorio directo). Con ≥ 5 ms de separación casi no ocurre (0 de 20; 1 de 20 a 20 ms) | Necesita atomicidad en la base, no solo en la aplicación (§7) |
| H5 | Media | Confirmado [R] | `logs/G_r19_instrumento.txt`, `casos/flush_con_fallos.py` | `flush_persistence()` devuelve `True` con **2 de 3 escrituras perdidas**. `persistence_flushed=True` significa «nada pendiente», no «todo guardado». Las fallas son solo un aviso en el log | Los controles de R19 deben contar fallas, no solo pendientes |
| H6 | Media (documental) | Confirmado [R] | `logs/F2_pg_pruebas.txt` (log del servidor) | De las 14 pruebas de trazabilidad, solo **5** usan `_store` y ejecutaron escrituras en PostgreSQL (5 bases, 9 `INSERT`). 8 no tocan ninguna base y 1 usa su propio SQLite | Corregir el informe y la matriz: R24 se apoya en 5 + 4 (07) pruebas, no en 14 + 4 |
| H7 | Baja-media (documental) | Confirmado [GH] | `logs/J_github_actions.txt` | `ci.yml` **sí corrió**: run 108 sobre `72ffae5`, verde en python y frontend. Nunca sobre los parches | Corregir R7 y A7. Usar el run 108 como línea base de la primera CI con parches |
| H8 | Media | Confirmado [R] (medida) | `logs/G_r19_instrumento.txt`, `logs/D_bucle_r19.txt`, `logs/D_analisis_conteos.txt` | La prueba de R19 tarda **3,2–7,4 s** sola con la máquina libre y 5,5–7,0 s en las suites del paquete corridas sin otra suite simultánea (E3 y E4). Bajo **0,2–0,5 s** con mis 4 suites en paralelo. La relación con la carga **no es estricta**: E1 del paquete tardó 5,8–7,3 s corriendo en parte en paralelo. En el bucle con carga de hasta 5,09 pasó **30 de 30**; dos sesiones de pytest duraron 10,5 y 10,1 s (carga 1,8 y 3,6) | El margen frente a 10 s es menor cuando el productor tiene CPU libre (p. ej., un runner ocioso). R19 sigue NO_REPRODUCIDO: no es «resuelto» |
| H9 | Baja | Confirmado [R] | `logs/C2_gate_adversario.txt` (J7) | Con otro intérprete, el gate aprueba y registra el `pip freeze` de **ese** intérprete (21 paquetes, `480fcee9…`), no el del que corrió las pruebas (74, `a1a96cac…`) | La procedencia puede describir un entorno distinto del probado |
| H10 | Baja | Confirmado [R] | K7 y J6 en `logs/C2_gate_adversario.txt` | Con `SyntaxError` en el motor o sin JUnit, el gate termina con rc 1 (cerrado) pero **sin escribir `provenance.json`** | Se pierde la evidencia de la corrida roja |
| H11 | Baja | Confirmado [R] | `logs/F2_pg_pruebas.txt` (c) | El módulo 07 se **omite** sin `TIA_TEST_POSTGRESQL_URL`, y el `ci.yml` propuesto no define un servicio PostgreSQL | La CI propuesta nunca ejecuta R24. El gate acepta esas omisiones (H2/J1) |
| H12 | Baja | Confirmado [R] | `logs/C1_ventana_sin_stop.txt` | Con rechazos aleatorios del 30 % (que incluyen los stops), quedan barras sin stop porque el stop rechazado se reintenta en la barra siguiente. En 2 de ellas el precio cruzó el nivel. El informe del backtest no las cuenta (`bars_with_leg_and_no_stop` solo cuenta piernas sin nivel) | Modelado fiel, pero invisible en el informe. Agregar un contador |
| H13 | Baja | Confirmado [A] | `registro/A4_extraccion_integridad.txt` | El manifiesto lo genera el mismo autor y no está firmado: prueba coherencia interna, no autoría ni procedencia (R8) | Firma o anclaje externo si se exige procedencia |
| H14 | Info | Confirmado [R] | `logs/D_residuos_y_orden.txt` | Las suites dejan `.hypothesis/` (ignorado). El orden de los módulos nuevos no cambia el resultado (29 de 29 en orden directo e inverso) | Limpiar `.hypothesis` en CI (ya es efímera) |

---

## 3. Matriz de afirmaciones del informe original

| Afirmación original | Resultado | Evidencia independiente | Limitaciones |
|---|---|---|---|
| ZIP `ea670f91…` y manifiesto `ce2612a9…` íntegros; 825 archivos | **Confirmada** [R] | SHA-256 recalculados. 825 de 825 verifican. El ZIP tiene 826 archivos (825 más el manifiesto). Sin rutas absolutas, `..`, enlaces, duplicados, setuid ni bases. La extracción es idéntica a la carpeta publicada | Manifiesto sin firma (H13) |
| Árboles A `5d6a0954…`, A+B `4ef14d31…`, A+B+03 `84f9e349…`, final `0477c6a2…` | **Confirmada** [R] | Reconstruidos desde los parches **extraídos**. Son **IDs de objetos *tree* de git en SHA-1** (formato del repo: sha1), calculados con `git add -A` y `git write-tree`. **No son SHA-256**. A+03 sin B: `a94be41a…` | Dependen de `.gitignore` y de los modos de archivo |
| Suites 1956 / 1978 / 1978 / 1985 sin fallas | **Confirmada** [R] | Venv **nuevo** desde PyPI (74 paquetes, `freeze a1a96cac…`, idéntico al del paquete). 0 omitidas, 0 xfail, 0 duplicados. Deltas: +22 (14 de trazabilidad y 8 de higiene), +0 (03 solo modifica pruebas), +7 (guarda). Nodeids y resultados idénticos a los JUnit del paquete | Corrieron 4 en paralelo (carga ~3,5) en una máquina local, no en CI |
| Guarda 7/7 | **Confirmada** [R] | 7 de 7 en el árbol final, también dos veces seguidas. En 02v3 sin 01 falla 5 de 7 por comportamiento; en base sin A y en 01 sin 02v3, 5 de 7 por «no engine_version» | — |
| 05v2: 25 de 26 mutantes por la razón correcta; M7 fuera de alcance | **Plausible** [A] | Los 26 casos no se re-ejecutaron. Sí se confirmaron N1, N2 y N3 (arriba) y la lógica leída. M7 (aviso del informe) es razonable fuera de alcance | La guarda tolera 1 barra sin protección y por eso no ve H3 |
| Robustez: 300 corridas, 0 falsos positivos, determinista | **Parcialmente reproducida** | **30 de 300** (semillas 1–2) re-ejecutadas: idénticas, clave por clave, a la evidencia [R]. Las 270 restantes solo se verificaron en los artefactos: 300 filas, 0 saltos en el motor correcto [A] | No se re-ejecutaron las 300 |
| 06v3 lee `ENGINE_VERSION` del código y **falla cerrado**; 11 de 11 | **Refutada en su generalidad** | Los 11 casos se sostienen, pero 8 de 18 casos nuevos fallan **abierto** (H2) | Hoy el motor usa la forma simple, así que el defecto está **latente** |
| 06 v1 no pasaba ruff; 06v3 limpio | **Confirmada** [R] | `ruff 0.17.1`, «All checks passed». Los `noqa` silencian exactamente S603 (git resuelto, justificado) y S314 (justificado con una suposición que el código no verifica) | — |
| Unidad A: exactamente 8 archivos, revisión línea por línea, reversión sin problemas | **Confirmada**, con un agregado [R] | 8 archivos (6 modificados y 2 nuevos). **Reversión funcional con datos** (SQLite): A escribe; base, tras revertir, lee y escribe; A vuelve a leer y reescribir, sin errores ni pisadas (`logs/E_reversion_datos/`) | Reversión con datos no probada en PostgreSQL |
| R24: PostgreSQL 16.15, migraciones OK, 14 pruebas de trazabilidad en PostgreSQL, 07 4/4 | **Parcial** | `SELECT version()` = 16.15, sin TCP, `fsync=on`. **upgrade → idempotente → downgrade base → upgrade**: OK (22 tablas). **Solo 5 de 14** escriben en PostgreSQL (H6). 07: 4/4 con 6 `INSERT` reales; sin la variable se omite | Local; no en CI ni en el entorno objetivo |
| R19 NO_REPRODUCIDO (0 de 252) | **Consistente** | 30 de 30 bajo carga de suites; las 4 suites completas pasan. El mecanismo (productor más rápido con CPU libre) es coherente con H8 | Mis 30 corridas no tienen la sonda; no reemplazan el experimento |
| R15 confirmado (32 de 50) | **Confirmada y ampliada** | 35 de 50, más intercalados y otra procedencia (H4) | Sonda en un mismo proceso con 2 conexiones |
| R25: el adaptador rechaza `STOP`; el vivo queda sin stop, solo con avisos | **Confirmada en dos niveles** [R] | Adaptador real con transporte simulado: 0 pedidos. Runtime con un venue que rechaza `STOP` igual que el adaptador: RUNNING, 0 stops, `unprotected_positions=0`, `last_error=''`, `protected=False` en la instantánea | Sin red: no hay evidencia del venue (X) |
| R18 «la pierna queda protegida por su stop» | **Refutada** | H3 | En los datos de ejemplo no hubo cruce del nivel en la ventana |
| R7 «`ci.yml` nunca corrió» / CI = ninguna | **Inexacta** | Run 108 verde sobre la base [GH] | Ninguna corrida sobre los parches |
| Repositorio protegido intacto; incidencia `.ruff_cache` revertida | **Confirmada para el estado actual** [R] | Estado idéntico. `.ruff_cache` ausente. Índice sin reescribir (mismo hash del archivo `.git/index`, con mtime del 2026-10-21) | La creación y el borrado de `.ruff_cache` solo constan en el registro 99 y la transcripción; no se pueden re-verificar |
| Sin secretos | **Confirmada** [R] | Escaneo amplio (claves privadas, AWS, GitHub, Slack, JWT, Bearer, URLs con credenciales, correos, IPs privadas, cadenas de 64 caracteres): 0 hallazgos reales. Las 4 credenciales «con forma» son sintéticas. Las 603 cadenas de alta entropía son IDs de órdenes y corridas de prueba y claves base64 de Hypothesis | — |

---

## 4. Resultados de las pruebas (todo en esta máquina salvo lo marcado [GH])

**Entorno:** Linux 6.18.44, 4 CPU, Python 3.11.17 y venv nuevo (`venv/`, 74 paquetes, `freeze` `a1a96cac94471aac46ac7e5374846d0e3ffe93f046df198b71c95fec6869766e`); PostgreSQL 16.15; ruff 0.17.1.

**Comando de suite:**
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/tia/src TMPDIR=<propio> venv/bin/python -B -m pytest tests -q -p no:cacheprovider -rsxX --junitxml=logs/D_<n>.xml`
(`casos/suite.sh`; las 4 suites en paralelo).

| Suite | Árbol (write-tree) | rc | Pruebas (pasan / fallan / errores / omitidas) | Duración | JUnit sha256 | Log sha256 |
|---|---|---|---|---|---|---|
| base | `44850cfc…` | 0 | 1956 (1956/0/0/0) | 315 s | `ed4bd56bd9700705…` | `a2efee0116d4df82…` |
| A = 01+02v3 | `5d6a0954…` | 0 | 1978 (1978/0/0/0) | 358 s | `468bc72b6ad29fb1…` | `a8af82bf8fc3059c…` |
| A+03 (sin B) | `a94be41a…` | 0 | 1978 (1978/0/0/0) | 365 s | `3e16d1a3e03b7511…` | `a8af82bf8fc3059c…` |
| final A+B+03+04+06v3 | `0477c6a2…` | 0 | 1985 (1985/0/0/0) | 376 s | `a380c5ea6328bc11…` | `4b93e77b7d19c804…` |

**Otras pruebas:**
- **Orden:** 29 de 29 en orden directo e inverso.
- **Ruff** como la CI: limpio.
- **Gate:** 18 casos, **8 desenlaces inseguros** (`logs/C2_gate_adversario.txt`).
- **R4c:** 3 combinaciones inválidas, todas en rojo por la razón correcta.
- **Robustez:** 30 de 30 idénticas.
- **Migraciones en PostgreSQL:** up, idem, down, up: OK.
- **PostgreSQL:** trazabilidad 14 de 14 (5 con escrituras reales en PostgreSQL); 07: 4/4.
- **R15:** 35 de 50 más intercalados.
- **R19:** bucle 30 de 30 bajo carga; llamada sola 3,2–7,4 s.
- **flush con fallos:** `True` con 2 de 3 perdidas.
- **R25:** adaptador y runtime.
- **Reversión con datos:** 7 pasos sin error.
- **[GH]:** run 108 sobre `72ffae5`, success.

**No ejecutadas, y por qué:**
- Las 300 corridas completas de robustez: solo 30 (tiempo; las demás contrastadas en los artefactos).
- Los 26 mutantes de la guarda: dependen del arnés de la misión anterior; confirmé los 3 de combinación de unidades.
- La CI real sobre los parches: exige push, no autorizado.
- Testnet o venue: sin red ni autorización.
- La reversión con datos en PostgreSQL.
- El experimento R19 con sonda: no se repitió.

---

## 5. Hallazgos adversarios nuevos (no cubiertos por la suite original)

1. **Gate 06v3 (H2):** 18 casos con veredicto fijado de antemano.
   - **K1** `ENGINE_VERSION` duplicado (primero 1.0.0, después 1.1.0): el gate lee 1.0.0 y aprueba sin guarda.
   - **K2/K3** dentro de `if`/`try`, **K4** tupla, **K5** importado: el gate lee `None` y aprueba.
   - **J1** 1978 de 1985 omitidas, **J2** solo 4 pruebas, **J5** 7 triviales con el nombre de la guarda: aprueba.
   - **Bien cerrados:** K0, K6 (los comentarios y docstrings no lo engañan), K7 (sintaxis rota; rc 1 sin evidencia), K8 (no UTF-8), K9 (expresión), K10 (anotada), J3 (xfail), J4 (duplicada), J6 (sin JUnit; rc 1 sin evidencia).
   - **Por qué importa:** el gate existe para sobrevivir a cambios futuros; un refactor común (K5) lo desactiva en silencio.
2. **Ventana sin protección tras un cierre por reversión rechazado (H3):**
   - En `engine.py` el orden es: 2b, sync del stop (l. 478), y después el paso 3, reversión (l. 558), donde `_request_exit` cancela el stop; si el cierre se rechaza, la barra sigue con `continue`.
   - En el vivo el orden es el mismo: `_manage_position` (l. 1873) va antes de `_process_bar` (l. 1895), que llama a `_close_position` (l. 2064).
   - Las pruebas de 01 miden la protección **después** del sync y toleran 8 barras; la guarda tolera 1.
3. **Semántica de `flush_persistence` (H5):** `asyncio.wait` y `_swallow` (aviso). Un `flushed=True` puede ocultar pérdidas.
4. **R15 con intercalados y otra procedencia (H4):** la ventana de carrera es de pocos milisegundos, pero existe, y **ningún escritor se entera de que perdió**.
5. **R25 en runtime (H1):** la sesión no cambia de estado, no cuenta la posición como desprotegida y no deja error.
6. **Dependencia de la carga de la prueba R19 (H8):** con CPU libre suele ser más lenta (relación no estricta).
7. **Reversión funcional con datos:** **sin defecto** (resultado negativo útil).
8. **Procedencia del gate con otro intérprete (H9):** la evidencia describe otro entorno.

---

## 6. Riesgos pendientes

| Riesgo | Evidencia | Severidad | Activación | Impacto | Detección actual | Mitigación | Prueba faltante | Condición objetiva de cierre |
|---|---|---|---|---|---|---|---|---|
| **R25** | H1 [R] | Alta | Toda posición del vivo sobre Binance (testnet o real) | Posición sin stop en el venue durante toda su vida | Aviso de log por barra; `protected=False` en la instantánea | Ninguna en el código | Prueba de contrato: la intención exacta del stop del vivo contra el adaptador; runtime: posición desprotegida → acción | Mapeo STOP→`STOP_LOSS` (o `STOP_LOSS_LIMIT`) con pruebas; capacidades veraces; falla del stop → `unprotected_positions` + bloqueo de entradas o cierre; check de activación que coloque y cancele un stop en testnet; evidencia X de testnet |
| **R18 / ventana H3** | H3 [R] backtest, [I] vivo | Media | Cierre por reversión rechazado | Una barra sin stop ni cierre; pérdida no acotada en esa barra | Ninguna (tolerancias de 1 y 8 barras) | — | Prueba que mire el venue **al emparejar** con tolerancia 0 tras un cierre rechazado | Stop mantenido hasta confirmar el cierre, o repuesto en la misma barra; la prueba nueva en verde en backtest y vivo |
| **R15** | H4 [R] | Media | Dos guardados casi simultáneos del mismo `run_id` | Un resultado se sobrescribe y su escritor cree que quedó guardado | Ninguna | — | Concurrencia en PostgreSQL con N escritores y verificación de qué recibe cada uno | Ver §7: «exactamente uno aceptado» en 1.000 de 1.000 carreras de las clases que deben rechazar, e idempotencia en la idéntica |
| **R19** | Paquete [A] más H5 y H8 [R] | Media | Runner ocioso (más lento) y carga no reproducida | Prueba intermitente; en producción, un registro posiblemente incompleto marcado como completo | `last_error` al detener si hay pendientes | — | Conteo de fallas de escritura; profundidad de la cola; prueba con el bucle conducido a mano | `persistence_flushed` = sin pendientes **y** sin fallas, expuesto en la API; métrica de cola; bloqueo de entradas al reiniciar si el stop anterior no vació; experimento en un runner tipo CI |
| **R24** | 5 + 4 pruebas en PostgreSQL [R] | Baja | Uso con PostgreSQL | Diferencias de dialecto en el almacén | 07 local | — | 07 en la CI con un servicio PostgreSQL | Job de CI con `services: postgres` y 07 sin omitir; el gate exige 0 omitidas en 07 |
| **R4c** | Guarda [R] | Media | 02v3 sin 01, o reversión parcial | Etiqueta falsa 1.1.0 | 05v2 en rojo (local) | Un único commit para A | CI real con B | B integrado y verde en la CI real; protección de rama exigiendo el check |
| **R17** | Matriz v3r3 [A] | Baja | Cierre que avanza por llenados parciales | Resto sin stop | Ninguna nueva | — | Escenario parcial con el venue mirado al emparejar | Prueba en verde |
| **R3** | [A] | Baja | Vivo | Capas 2 y 3 de D3 ausentes | — | — | Paridad vivo/backtest de D3 | Paridad demostrada |
| **R6** | [I] (`engine.py:979-982` frente a `live.py:3433`) | Muy baja | Precios con stops muy bajos o muy altos | Reposición distinta | — | — | — | Aceptado; unificar la tolerancia si se toca |
| **A7** (CI real) | Run 108 [GH] solo base | Media | — | Diferencias de entorno | — | 04 (versiones fijadas) | Push autorizado del árbol esperado | Run verde sobre `0477c6a2…` (o el árbol que se integre), con el gate corregido |
| **A8** (revisión humana) | — | Media | — | — | — | — | — | Revisión firmada del diff de A y B |
| **Gate 06v3** | H2, H9, H10 [R] | Media | Refactor de la versión; corrida parcial | Aprueba sin guarda | — | — | Los 18 casos de `casos/gate_adversario.py` | 18 de 18 seguros |

No se dan probabilidades numéricas para producción: no hay datos que las sostengan.

---

## 7. Plan de corrección priorizado (diseño; nada se aplicó al repositorio)

**Bloqueantes (para el vivo y el dinero real):**
- **R25:**
  - mapear `OrderType.STOP` a `STOP_LOSS` (stopPrice, sin timeInForce) o usar `STOP_LOSS_LIMIT` con límite de peor precio;
  - declarar solo las capacidades que se traducen;
  - en el vivo, si el stop falla: incrementar `unprotected_positions`, registrar un incidente, poner `last_error` y **detener entradas y cerrar o alertar** según política;
  - check de activación `protective_stop_roundtrip` en testnet.
  - *Regresión:* `casos/test_r25_runtime.py` debe pasar con el adaptador corregido, y una prueba de contrato enviar la intención exacta del vivo.
- **Ventana H3:**
  - no cancelar el stop hasta que el venue acepte el cierre, o reponerlo en la misma barra si el cierre se rechaza;
  - aplicarlo en backtest y en vivo.
  - *Regresión:* `casos/ventana_reversion2.py` con 0 barras sin protección al emparejar; bajar `MAX_BARS_UNCOVERED` a 0 para ese caso.

**Necesarios antes de integrar en la rama aislada:**
- Corregir el informe y la matriz: H6 (R24: 5 + 4), H7 (R7 y A7), H3/R18, y la generalidad de «06v3 falla cerrado».
- Decidir sobre 06v3: no integrarlo, o integrarlo como **no confiable** hasta corregir H2, H9 y H10.
- Diseño propuesto para el gate:
  - leer **todas** las asignaciones a `ENGINE_VERSION` (`ast.walk`, cualquier nivel, tuplas incluidas) y fallar si hay más de una o si hay un import;
  - mejor aún: que la propia guarda registre la versión observada como propiedad del JUnit (`record_testsuite_property`) y el gate la compare con la del código;
  - exigir los **7 nombres exactos** de la guarda;
  - exigir 0 omitidas fuera de una lista explícita, o un mínimo de pruebas recolectadas por módulo;
  - ligar el JUnit a la corrida (hash del árbol y `sys.executable` como propiedades);
  - escribir `provenance.json` también ante errores;
  - registrar el hash del archivo de la guarda.

**Necesarios antes del merge:**
- CI real verde sobre el árbol exacto.
- Revisión humana.
- Job de PostgreSQL para 07.
- R15 corregido o aceptado explícitamente, con alcance documentado.
- Pruebas que miren el venue al emparejar.

**Antes de considerar trading real** (además de los bloqueantes):
- **R15 atómico**, cualquiera de dos diseños:
  - (a) `INSERT … ON CONFLICT (run_id) DO NOTHING RETURNING`; si no inserta, `SELECT … FOR UPDATE` y comparar la procedencia y los números dentro de la misma transacción.
  - (b) Columna con el hash de procedencia y números, y `UPDATE … WHERE hash = :esperado` (CAS).
  - *Criterio de aceptación:* 1.000 carreras por clase en PostgreSQL con **exactamente un** aceptado en las clases que deben rechazar, y el perdedor recibe un error.
  - *Riesgos:* bloqueos y deadlocks (orden fijo de las operaciones) y diferencias con SQLite (usar `BEGIN IMMEDIATE`).
- **R19:** controles de persistencia (fallas y pendientes) expuestos en la API, bloqueo de entradas al reiniciar si no vació, y métrica de cola.
- Validación en testnet (X) de todo el camino de órdenes.

**Mejoras no bloqueantes:**
- Contador de barras sin stop por stop rechazado (H12).
- Justificación verificable de S314.
- Limpieza de `.hypothesis`.
- Firma del manifiesto (H13).

---

## 8. Decisión final

- **A. Integración técnica en una rama aislada: APROBABLE CON CONDICIONES.**
  - Integrar A (01 + 02v3, un único commit) y B (05v2), y opcionalmente 03.
  - Condiciones: corregir los documentos (§7); **no** contar 06v3 como control que falla cerrado (dejarlo fuera o marcarlo como no confiable); y que la primera CI real sobre ese árbol sea el criterio de avance.
  - Las suites, los árboles y la reversión funcional sostienen esta decisión.
- **B. Merge a la rama protegida: NO TODAVÍA.**
  - Faltan la CI real sobre los parches (A7), la revisión humana (A8), decidir H3/R18 y R15, y el gate corregido si se lo quiere usar como requisito.
- **C. Habilitación de trading real: NO.**
  - R25 (alta) está abierto y confirmado en runtime; H3, R15 y los controles de R19 siguen pendientes.
  - Además, nada de esto es evidencia de rentabilidad: los resultados de backtest y de papel no garantizan resultados futuros.

**¿Pasar a la integración incremental?** Sí, **solo a la A**, en una rama aislada y con las condiciones de arriba. B y C quedan cerradas por los bloqueantes.

---

## 9. Integridad del trabajo

**Repositorio protegido** (`/home/user/Trader-IA`):
- **Estado inicial** (`registro/A2_repo_protegido_inicial.txt`) y **final** (`registro/L_repo_protegido_final.txt`) **idénticos**: HEAD `72ffae5`, árbol `44850cfc…`, refs, 0 tags, 0 stash, índice `07e0c86b…`, 0 cambios, 18 ignorados, reflog `6d55854c…` (13 entradas).
- **Sin cambios:** el archivo `.git/index` conserva el mismo SHA-256 (`37490035…`): las lecturas usaron `--no-optional-locks`. No hay `.ruff_cache` ni archivos nuevos.
- Sin commits, push, PR, merge, deploy ni trading. No se usó red hacia exchanges, ni credenciales reales. La API de GitHub se usó solo para leer.

**Incidencias propias:**
1. **Disco lleno** durante R15: la sonda de intercalados creaba una base por intento.
   - PostgreSQL desechable se detuvo al no poder escribir el WAL.
   - Borré **solo** el directorio de datos de mi instancia y conservé su log (`logs/F_pg_servidor_instancia1.log`).
   - Repetí la sonda borrando cada base después de usarla (`registro/H0_incidente_disco.txt`).
   - No se tocó ninguna base compartida: el cluster del sistema siguió apagado.
2. **Una hipótesis mía refutada:** «la suite completa acelera la prueba de R19». Quedó registrada en `logs/G_r19_instrumento.txt`; el factor real es la carga (H8).

**Limitaciones del entorno:**
- Sin red al venue.
- CI no autorizada.
- Disco limitado (unos 2 GB).
- El contenedor se reinició antes de esta revisión; no hubo procesos previos activos.

**Archivos nuevos:** listados con su SHA-256 en `MANIFEST_REVISION.sha256`. Están en `casos/` (pruebas adversarias), `logs/`, `registro/` y este informe.
