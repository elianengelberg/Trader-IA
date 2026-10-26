<!-- Copia publicada del informe de la revisión independiente (2026-10-26). Original: INFORME_REVISION_INDEPENDIENTE_V3.md,
     SHA-256 8d60de48b1bd28722295043123449094b38a03921c68aae51d046a76bb812ae6, dentro del paquete de evidencia
     trader-ia-revision-independiente-v3-2026-10-26.zip (SHA-256 913a19babf84c16fa5ce82ae5f1d62c511ff67909b635f4e5acfcf8f1207a023),
     que NO se publica en el repositorio. Única modificación: las rutas absolutas del espacio de trabajo se reemplazaron
     por «<espacio de trabajo>/». Las rutas logs/, evidencia/ y revisores/ son relativas a ese paquete. -->

# Trader-IA — Revisión técnica independiente de `candidata/v3` (2026-10-26)

**Objeto:** la rama local `candidata/v3`, construida sobre v2, antes de decidir si se publica en una rama de revisión y se corre la CI remota.

**Método:**
- El informe v3 se trató como una lista de afirmaciones por verificar.
- La evidencia se reconstruyó desde los artefactos originales:
  - el ZIP v3;
  - el ZIP v2 (`8805229e…`);
  - el repositorio protegido;
  - los parches.
- La suite se volvió a correr en un entorno nuevo, con un venv instalado desde PyPI y un PostgreSQL desechable propio.
- Tres revisores separados, que no leyeron ningún informe de v3, auditaron el código de D26/D25, R19/H11 y market maker/filtros/respuestas ambiguas.
- Lo que esos revisores declaran como demostrado lo volví a verificar en el código, y re-ejecuté sus pruebas con mi propio entorno (§7).

**Límites respetados:**
- No hubo push, fetch hacia GitHub, merge, PR, commit, deploy ni publicación.
- No se usaron credenciales, Testnet ni dinero real.
- `validada_para_operar` no se tocó.
- No se modificó el repositorio protegido, los experimentos congelados, las entregas anteriores ni el directorio de la entrega v3.
- No se aplicó ningún parche al repositorio protegido.
- No se implementó ninguna corrección: todo lo que se escribió son pruebas que **observan** defectos, en copias.

Rutas: la raíz de esta revisión es `<espacio de trabajo>/revision_independiente_v3_2026-10-26/`. Las rutas relativas de este informe parten de ahí.

---

## 1. Veredicto ejecutivo

1. **La entrega v3 es íntegra y reproducible.** Coinciden:
   - el SHA-256 completo del ZIP y el manifiesto;
   - los parches;
   - la reconstrucción con `git am` sobre `c6339e3`, tree por tree en los 6 commits;
   - el commit 1, igual al árbol que sale del ZIP v2 con sus propios 32 parches.

   Los 21 archivos que cambia v3 son los declarados. La suite completa da lo mismo que declara la entrega: 2 322 aprobadas, 2 xfail, 0 fallas y 0 saltadas, idéntico caso por caso en los 2 324 casos.
2. **Las seis correcciones de v3 hacen lo que dicen y no encontré regresiones.** Aun así, la candidata **no está lista para integrarse a la rama protegida**:
   - las propias correcciones tienen huecos demostrados (H11, B1, D3);
   - dos pruebas nuevas de PostgreSQL no están aisladas, y una puede ser destructiva en un servidor compartido;
   - 4 de 15 mutantes adicionales sobreviven.
3. **La revisión independiente encontró defectos graves del camino live que v3 no informa.** La mayoría ya existían en v2; v3 no los introdujo. Los cuatro más importantes:
   - **(a)** los fills posteriores al envío nunca se registran: un stop que salta no se contabiliza y el límite de pérdida no lo ve;
   - **(b)** al ajustar el stop, el sistema cancela el stop válido antes de colocar el nuevo; si el venue rechaza el nuevo, la posición queda sin protección ni salida;
   - **(c)** el market maker live y la sesión live pueden correr a la vez sobre la misma cuenta, sin exclusión;
   - **(d)** el apagado no entra en los 10 s de `docker stop`, y con la base particionada se cuelga.
4. **Publicar en una rama de revisión y correr la CI remota:** hay evidencia suficiente para hacerlo, **pero solo tras tres condiciones previas** (§9):
   - elegir la base, porque `c6339e3` está 4 commits detrás de la última punta remota conocida;
   - decidir la identidad de autor de los commits;
   - aceptar que lo publicado describe defectos abiertos.

   Publicar no habilita nada: ni trading ni merge.
5. **Testnet: no todavía.** **Dinero real: no.** **Rentabilidad: no evaluable**: ninguna prueba de software dice nada de eso.

---

## 2. Artefactos examinados, hashes completos y limitaciones de acceso

| Artefacto | Ruta | SHA-256 / identificador completo | Verificación |
|---|---|---|---|
| ZIP v3 | `<espacio de trabajo>/trader-ia-cierre-tecnico-v3-2026-10-26.zip` (2 909 829 bytes) | `13e492851fa6f4363608f9cd8fa0dc5d74109ef9b899a8d48aa2291783d12443` | Recalculado; igual al `.sha256` lateral. El `.sha256` mismo: `da3f6d32d2f7d6000244dd077f3e2c01d4a7fefedf6c212d48db51f69d220d71` |
| `MANIFEST.sha256` (dentro del ZIP) | `cierre_tecnico_v3_2026-10-26/MANIFEST.sha256` | `67e891e04858d31ec7fa43ce01b3c97f1d14f8ac53e8d128f9aa9e9e38b431db` | 330 líneas, 0 mal formadas y 0 rutas repetidas. Contra la extracción: 0 faltan, 0 sobran, 0 hash distinto. El ZIP tiene 331 miembros con el manifiesto, todos archivos regulares, sin rutas absolutas, `..`, duplicados (incluso por mayúsculas o NFC), enlaces ni cifrado; CRC OK. Idéntico al directorio de la entrega (`logs/A1_zip_y_manifiesto.txt`) |
| Base | repo protegido | commit `c6339e3fcd6041cb6c4ad7f5545f0ff306a4fd2f`, tree `40db17b1b14884f241335d40b93fe4d717a434ad` | |
| Commit 1 (v2) | rama candidata | `090087fa0c87779670df1c947116c47bb6dc3cef`, tree `c56419157a81f844e04acfe557f6404867ae6d77` | Igual al árbol armado desde el **ZIP v2** (`8805229e94fa53452aa135d34d4758f9627d83d2a7aea7199b303990d0d962ce`) con sus 32 parches y `git apply`; huella `cfeeda976970d0e0c7ec2cea22a62bc29d6d853f32736e526e5f2e7fbc28cd05`, 1 086 archivos (`logs/A3_commit1_igual_v2.txt`) |
| Commit 2 (H11) | | `16c09929699c66e1b431681cfa09f837e9ec2e19`, tree `f8e048ce14bbd99b07ac25ace0c4958fdba09966` | `git am` del parche 0002: tree igual |
| Commit 3 (B1+B2) | | `05c7c0d0b8e6a7b4c18a8b3f2bfba60e7d89033a`, tree `578d948152f16155d5b34a3676c42a46f9726b17` | ídem |
| Commit 4 (D21) | | `bcf3a6e235d6d0e7fdd6e6251ef4225fb01fa1e3`, tree `5a7825bba14d49d4e26719c42b966c0417ad6f66` | ídem |
| Commit 5 (D3) | | `ad338011410f26323ad20bf191613422941f45e3`, tree `adf3bcf2f3557a7e94eb49e96820d971951f1a3e` | ídem |
| **Punta (CI)** | | **`e6a80c1caa3d7a18005ed694390ef0ad5ad6d05b`**, tree **`ef1983b6c87414478a8ed139ea79e91919f46c0e`** | ídem. El bundle verifica contra `c6339e3` y da los mismos 6 commits (`logs/A2_reconstruccion_desde_zip.txt`) |
| Contenido de la punta | `_trabajo/arbol_punta` (`git archive` de la reconstrucción) | huella `6f5580dae66687123058a74064e9a10684943ffe04280af1e3f422897f9e502e` (1 098 archivos) | Igual a la declarada. Árbol de solo lectura desde que se creó; recalculada al cerrar, igual (`logs/D2_entorno.txt`) |
| Parches | `patches/candidata_v3/` | `3f9aa949…1d40`, `101c3c34…25ad`, `7a7d60ce…ea42`, `25f727f7…f2a6`, `391929f8…9ca3`, `8d611e74…9156`; bundle `30e879a037966ddc70fb81bd9cd99b67c48642890fbe54c9a901a90f0c1ee2cc` (valores completos en `SHA256SUMS`) | `sha256sum -c`: 7 OK |
| Repositorio protegido | `…/mision_integral_r6_2026-10-21/clon_github_c6339e3` | huella de archivos `f2d9951ea7c166a21abde15f436c7b63e6a4ae225d11ca79e27c69aaa8338bd5` (1 082 archivos); metadatos `62f23107ffaa295bdec9c080dc4a29ee04fdd894007a547f650752380cc3dc57`; índice `9d4a1152531bfd0a5cff3f3bd26c9dcecef7709132136e23d149f4e3b6e86b9b` | Tomada antes de cualquier `git`, al empezar y al terminar (`evidencia/00_estado_inicial.txt`, `evidencia/90_estado_final.txt`). Detalles abajo |
| Experimentos congelados | `decision_autonoma_e3_h1_2026-10-22/{h_rev_prosp,h_rev_prosp_v1_1,h_rev_prosp_v1_2}` | listas `a92a0cc3…d482`, `ba116b8e…86d6`, `d9a3c7d9…4d17a` | 16/16, 15/15 y 15/15 OK |
| Entregas anteriores | `cierre_bloqueantes_2026-10-22`, `cierre_bloqueantes_v2_2026-10-25`, directorio v3 | `f36f810fd5cc4933febf57501c70bcbbde21b60bd9bd6d1cc2eca6077f7af7bf`, `86005e8350ecb4c9ec8773efe1cb52ce12f0358f9f5d43f7ce32f931cc67b551`, `af23f39a3207138d6ee2fff12953dfcda868b0a1a8e8f07273c42a78a5c07d45` (sin `_trabajo`) | Iguales al principio y al final. Los 21 ZIP de entregas tienen los mismos SHA-256 |

**Evidencia de que el repositorio protegido no cambió**, y su límite:
- Sigue en `HEAD c6339e3`, desacoplado:
  - `git status --porcelain --ignored` vacío;
  - 0 stash;
  - 162 commits alcanzables;
  - una sola ref (`refs/remotes/origin/claude/algo-trading-simulation-platform-ngf7xo` → `72ffae5…`).
- La huella `f2d9951e…` ya figura en el estado inicial de la entrega del 2026-10-22 y en el de v2, y coincide hoy.
- **Límite:** esos registros los produjo la misma cadena de trabajo en este mismo entorno. No hay un ancla externa, ni firma ni GitHub, que lo confirme de forma independiente.

**Limitaciones de acceso:**
- **Sin acceso a GitHub.** Ni lectura ni escritura del estado remoto: no puedo afirmar nada sobre permisos, protección de ramas, runners ni la punta actual del remoto.
  - La última punta conocida es la del clon local: `72ffae5`, 4 commits después de `c6339e3`.
  - Esos 4 commits tocan 22 archivos de `research/` y ninguno de los 77 de la serie.
  - La serie aplica limpia sobre `72ffae5` y da exactamente el mismo diff (`logs/A6_aplicar_sobre_72ffae5.txt`).
- **Sin demonio Docker.** No hay `docker stop` real.
- **Sin Testnet ni credenciales.** Nada del venue real está verificado: solo la documentación oficial y venues simulados.
- **Los hashes no tienen firma.** Los commits tampoco (`firma=N`). Prueban consistencia interna, no autoría.

---

## 3. Matriz de afirmaciones verificadas

| # | Afirmación del informe v3 | Evidencia examinada | Resultado | Discrepancia | Confianza |
|---|---|---|---|---|---|
| 1 | Rama `candidata/v3`, base `c6339e3` | repo candidato (solo lectura) y reconstrucción | Confirmada | `c6339e3` no es la última punta remota conocida (`72ffae5`, +4 commits de `research/`) | Alta |
| 2 | Punta `e6a80c1`, tree `ef1983b6…` | `git rev-parse e6a80c1^{tree}` | Confirmada | **No hay discrepancia.** `e6a80c1` es el **commit** y `ef1983b6` es el **tree** de ese commit: son dos objetos distintos de git, no dos valores en conflicto | Alta |
| 3 | ZIP `13e49285…2443` | SHA-256 recalculado | Igual: `13e492851fa6…7d12443` | — | Alta |
| 4 | Manifiesto `67e891e0…31db`, 330 archivos | inspección propia (§2) | Igual | El manifiesto no lista su propio hash (es correcto que no lo haga) | Alta, autoatestado |
| 5 | Tree reproducible con `git am` sobre `c6339e3` | reconstrucción en un clon nuevo, sin origin | 6 de 6 trees iguales; bundle igual | — | Alta |
| 6 | Solo cambios declarados | `git diff --stat` v2→punta; commit 1 contra el ZIP v2 | 21 archivos, +2 273/−42, igual a la lista §7 de v3. Sin binarios ni cambios de modo. Sin secretos: la única credencial nueva es la contraseña desechable del contenedor de servicio de la CI (`tia_ci_throwaway`, pública a propósito). El único workflow tiene `permissions: contents: read` y no despliega | — | Alta |
| 7 | Repositorio protegido sin cambios, huella `f2d9951e…` | §2 | Confirmada | Sin ancla externa | Media-alta |
| 8 | 2 322 aprobadas, 2 xfail, 0 fallidas, 0 saltadas | recuento propio del JUnit entregado y re-ejecución independiente: venv nuevo, mi cluster, `pytest tests` | 2 324 casos, **idénticos caso por caso** (`logs/B3_*`, `logs/B2_completa.*`) | — | Alta |
| 9 | Dos xfail (D26, R24-O1) | lectura de las pruebas | Los dos son `strict=True`: si pasaran, la corrida falla | El xfail de D26 no usa `raises=` ni compara el mensaje: **cualquier** falla de esa prueba cuenta como «esperada». Podría enmascarar otra regresión en ese camino. Es acotado, porque otras pruebas cubren el stop | Alta |
| 10 | PostgreSQL 155 + 1, en UTC y en Buenos Aires | re-ejecución propia | UTC: 155 + 1 (dentro de la suite completa). Buenos Aires: **primer intento 1 falla**; repetido sin otra carga, 155 + 1 | La falla viene de una prueba no aislada: cuenta los advisory locks de **todo el cluster**. Reproducida a voluntad (`logs/B6_aislamiento_prueba_pg_locks.txt`). Ver M1 | Alta |
| 11 | Controles críticos: 39 archivos, 392 casos | recuento propio a partir de la lista declarada | 41 entradas con 2 repetidas (`test_pg_concurrency`, `test_pg_types`): 39 únicos, 392 casos, 390 + 2 xfail. En la re-ejecución, igual | Ninguna | Alta |
| 12 | 19 de 19 mutantes muertos | lectura del runner; 15 mutantes propios adicionales | Cierto, pero el runner corre **solo la prueba elegida para cada mutante**: muestra que cada corrección tiene una prueba, no mide cobertura. De los 15 adicionales, **11 muertos y 4 vivos** (§4, M2) | «19/19» no equivale a cobertura | Alta |
| 13 | Las pruebas nuevas fallan en v2 por el motivo correcto (H11, SAFE_MODE, B1, B2) | re-ejecución propia: v2 desde su ZIP + solo los archivos de prueba nuevos; clasificación caso por caso (`logs/B4_clasificacion.txt`) | **Por comportamiento:** H11 a nivel `AppState` (2 en SQLite + 2 en PG + 1 en `test_pg_concurrency`), SAFE_MODE 2, B1 14, B2 2, `exec` en compose 2, y `run()` sin tope 1. **Por errores secundarios** (v2 no tiene el módulo o la función): 10 del lock en sí (5 en SQLite y 5 en PG, contando los hijos que importan el módulo), 3 de `AttributeError: _session_slot`, el archivo D21 entero (colección), la guardia de CI entera (colección) y 2 del apagado («the server did not come up», porque el lanzador importa una función nueva). El clasificador automático marca 5 de estos casos como «de comportamiento»; leídos a mano son secundarios: la guardia falla con `FileNotFoundError scripts/ci_check_junit.py`, los dos «holder killed» porque el hijo no puede importar el módulo, y los dos del servidor porque no arranca | Coherente con lo que v3 reclama: no reclamaba rojo para D21 ni para la guardia. **Agregado:** adapté el control del apagado para v2 y el servidor v2 sigue vivo 8 s después de SIGTERM con el stream abierto, sin registro de stop (`logs/B4_rojo_v2_d3_control_en_v2.txt`) | Alta |
| 14 | Emulación de CI: 14 pasos correctos y 6 no emulados | `logs/ci_v3/emulacion/pasos.jsonl` del paquete v3 | Confirmado. Los 6 son `actions/checkout`, `actions/setup-python` y `actions/upload-artifact`, en los jobs `python` y `postgres` | Abarca **2 de los 4 jobs**. `frontend` se corrió a mano con npm; `drift` aparte. El contenedor de servicio, el runner, los triggers y `concurrency` no se ejercitaron. Ninguna de las dos cosas es falsa en el informe, pero «14 de 20» no es «la CI» | Alta |
| 15 | No se publicó ni desplegó nada | refs del repo protegido y del candidato | El repo protegido no tiene refs nuevas y el candidato no tiene remoto | No puedo verificar el lado de GitHub | Media |
| 16 | D26 crítico | revisor D26/D25 + código | **Confirmado y ampliado** (C4) | — | Alta |
| 17 | D25 alto | revisor + código | **Confirmado y más grave** (C2): también ocurre al **ajustar** un stop válido | Severidad subestimada | Alta |
| 18 | R19: el plazo de 10 s se venció 2 de 6 veces | JSON crudos de `logs/r19_v4/` del paquete v3 | Confirmado: `sqlite_sin_sub/L2_1` y `L2_3`, segundo vaciado, 63 y 11 escrituras pendientes al vencer | Es el vaciado de `stop_run` en una carga de prueba (`test_restart_recovery`), **no** un apagado por SIGTERM. Las corridas «L0» de `sqlite_sin_sub` tuvieron loadavg de 2,6 a 4,6 en 2 núcleos (`logs/D2_entorno.txt`: `nproc` 2): no eran reposo | Alta |
| 19 | D3: apagado de ≤ 5 s más el vaciado | revisor R19/H11 (mediciones con el comando literal del compose) + código | El tope de 5 s se cumple: 5,6 s medidos por `run()` | Lo que acota es la espera de conexiones; el cierre de la aplicación sigue **sin tope**. Medido: 15,6 a 18 s con PostgreSQL lento. Con la base particionada, seguía colgado al tope de 40 s de la medición (SIGKILL a los 40,0 s; no se midió más allá). Ningún compose fija `stop_grace_period` | Alta |
| 20 | H11 corregido | revisor + 15 mutantes + código | El lock excluye | Ventana de unos 30 s hasta detectar la pérdida. Lock retenido unas 2 h ante una partición. Reclamo de `arm_live` sin prueba (mutante vivo). Fila sellada antes del reclamo (§5.4) | Alta |
| 21 | Cronología | fechas de los miembros del ZIP y de los commits | Coherente: armado 17:56, suite hasta 18:22, parches 18:16, mutantes 18:25, emulación 18:47, integridad 18:49, empaquetado 19:01. Los 6 commits tienen la misma fecha (17:56:00) | El ZIP trae 4 logs (`candidata_commit_{8246627,b38108b,cce71c0,ea5d4ac}.txt`) de armados viejos cuyos commits ya no existen. Ningún documento los cita | Alta |
| 22 | Pruebas destructivas o cambios de estado | código de las pruebas y scripts de la entrega | Declarados en v3: SIGKILL de procesos hijos, carga de CPU y `dd` con fsync, `DROP DATABASE` en clusters desechables, `chmod -R a-w` de copias | **No declarado:** `test_a_terminated_backend…` ejecuta `pg_terminate_backend` sobre **todos** los advisory locks del servidor, sin filtrar por base. Con un rol superusuario sobre un servidor compartido, mataría conexiones ajenas (M1) | Alta |

---

## 4. Hallazgos por prioridad

Notación:
- **[v3]** introducido o tocado por v3; **[pre]** ya existía en v2.
- **[nuevo]** no figura en el informe v3; **[decl.]** v3 lo declaraba.
- **Estado:** DEMOSTRADO (prueba ejecutada o camino de código determinista), PLAUSIBLE (probable, no demostrado), NO VERIFICADO (necesita el venue real o Docker).

Las referencias a código son relativas a `packages/tia/src/tia/` del tree `ef1983b6…`.

### Críticos (bloquean operar en real; no bloquean publicar una rama de revisión)

**C1. Los fills que llegan después de enviar una orden nunca se registran.** [pre] [nuevo] DEMOSTRADO.
- `GET /api/v3/order` no devuelve `fills`. Lo confirmé en la documentación oficial: la respuesta trae `executedQty` y `cummulativeQuoteQty`, sin `fills`. Los fills con su comisión están en `myTrades`.
- El adaptador solo arma fills desde la respuesta de envío (`data/providers/binance_live.py:716-719`).
- `runtime/live.py` nunca llama a `get_fills`/`myTrades` (0 llamadas; verificado con `grep`).
- Cuando el stop de protección salta, `_poll_protective` lo ve FILLED sin fills y lo marca «failed … filled, unfilled» (`runtime/live.py:3874-3881`). El round trip no se cierra, el P&L no se registra y la sesión queda en HALT.
- En modo live, la conciliación de saldo registra la pérdida como **retiro**, y el límite de pérdida no la ve.
- Lo mismo pasa con una entrada limit que se llena después.
- Evidencia: pruebas b1, b4, b8 y b11 del revisor (`revisores/d26_d25/`); re-ejecutadas por mí, 26 de 26.

**C2. D25 es más grave que lo declarado: ajustar el stop puede dejar la posición sin protección y sin salida.** [pre] [decl. parcial] DEMOSTRADO.
- `_sync_protective_stop` **cancela el stop vigente antes de colocar el reemplazo** (`runtime/live.py:3672-3677`, verificado). Si el venue rechaza el nuevo con -2010 («would trigger immediately»), el stop anterior, que era válido, ya no existe.
- No hay salida a mercado y los reintentos no tienen tope: uno por vela, con un id nuevo cada vez. En la prueba d2, el precio quedó 3,45 % por debajo del stop sin una sola venta.
- El bloqueo de entradas suprime también la salida por señal contraria (d8).
- El motor paper llena ese mismo stop en la vela siguiente (d6): paper y live divergen justo en este punto.

**C3. D26 confirmado y más amplio.** [pre] [decl. y ampliado] DEMOSTRADO.
- Con la comisión en BTC y una diferencia mayor a un lote, no se coloca ningún stop, y `protection_status` queda en «none», el mismo valor que significa «sin posición» (b2).
- Con una diferencia menor a un lote, el round trip nunca se cierra (b1b): `_track_round_trip` espera vender la cantidad bruta (`runtime/live.py:4331`), y el polvo que queda bloquea las entradas de las sesiones siguientes (b7).
- `fee_asset` no se lee en ninguna parte de `runtime/live.py` (0 apariciones, verificado). Las comisiones en BTC o BNB se registran en unidades crudas, como si fueran USD (b3b: 600 veces menos).
- Evaluación de la propuesta «cantidad neta + comisión valuada en quote + no armar si no se puede valuar»:
  - Resuelve el stop de posiciones grandes y la unidad de la comisión en BTC.
  - **No** resuelve el polvo, C1, el reinicio con igualdad exacta (`runtime/live.py:917-923`) ni la paridad con paper.
  - «No armar» es un chequeo único. El activo de la comisión puede cambiar a mitad de sesión (BNB activado, desactivado o agotado), así que hace falta una regla **por fill** (b10).

**C4. Sin exclusión entre el market maker live y la sesión live sobre la misma cuenta.** [pre] [decl. como P-07, «media»; acá alto o crítico] DEMOSTRADO.
- `start_mm_live` solo comprueba `self._mm_live.is_running` (`api/state.py:1790`, verificado). No mira la sesión, el slot de H11 ni `_session_lock`. `arm_live` y paper tampoco miran al market maker.
- Las pruebas P1a y P1b muestran los dos arrancando sobre la misma clave.
- Consecuencias demostradas con una cuenta simulada:
  - la sesión vende inventario del market maker con `emergency_flatten` (P1g);
  - el market maker vende la base de la sesión (P1e);
  - cada lado frena tarde, por reconciliación.
- Mitigación actual: los dos requieren `TIA_LIVE__ENABLED=true` (por omisión `false`) y una acción del operador; el market maker además requiere `TIA_MM__ENABLED`. **Crítico si se habilitan los dos.**

### Altos

- **A1. Respuestas ambiguas con huecos.** [pre; v3 cambió la clasificación] DEMOSTRADO en la lógica.
  - **Entrada:** si la entrada recibe un 5XX y la consulta por client id **también** falla, nunca se vuelve a preguntar. La posición queda en el venue sin rastrear y sin stop, con HALT y `position_unverified` (P3c).
  - **Salida:** si la salida recibe un 5XX y la consulta también, el `ProviderUnavailableError` **escapa** de `_submit_exit`: el handler solo captura `ReconciliationError` (`runtime/live.py:4043-4047`, verificado). En el ciclo siguiente se envían un STOP y una MARKET con ids nuevos, y puede haber doble salida si hay base libre (P3d).
  - **Stop:** un stop dado por ausente mientras estaba en vuelo (-2013) termina en un stop sin rastrear o en dos stops (P3b). PLAUSIBLE en el venue real.
- **A2. B1 incompleto: `-1006` se trata como rechazo.** [v3] DEMOSTRADO en la clasificación.
  - La documentación oficial: «-1006 UNEXPECTED_RESP … Execution status unknown.».
  - El código solo trata como UNKNOWN el 5XX y el `-1007` (`data/providers/binance_live.py:280`).
  - NO VERIFICADO: con qué estado HTTP llega `-1006`. Si llega con 5XX, ya queda cubierto.
- **A3. La idempotencia por client id que asume el adaptador es falsa para órdenes ya llenadas.** [pre] PLAUSIBLE en el venue; la documentación lo confirma.
  - Documentación oficial: «A unique id among open orders … Orders with the same newClientOrderID can be accepted only when the previous one is filled».
  - El docstring de `data/providers/binance_live.py:23-27` afirma que el venue rechaza el duplicado. Un reenvío con el mismo id de una orden que ya se llenó **se acepta**.
- **A4. `emergency_flatten` vende todos los activos de la cuenta, no solo el símbolo de la sesión** (BNB y otros). [pre] DEMOSTRADO en simulación; el bucle está verificado en `runtime/live.py:1719-1751` y `data/providers/binance_live.py:530-548`.
- **A5. El apagado no entra en 10 s y tiene esperas sin tope.** [pre; v3 corrigió parte] DEMOSTRADO por el revisor; código verificado.
  - Las esperas con tope suman unos 55 s.
  - `_mark_stopping` y `_record_stop` escriben en la base sin timeout (`api/state.py:286-289`, verificado). Con la base particionada, el apagado sigue colgado a los 40 s.
  - El escenario se para antes que la sesión que toca dinero.
  - Ningún compose fija `stop_grace_period` ni `init`.
- **A6. H11: ventanas y restos.** [v3] DEMOSTRADO por el revisor; re-ejecutado por mí.
  - Perdido el lock, la sesión sigue tomando entradas hasta el próximo heartbeat (30 s, `runtime/live.py:735`).
  - Ante una partición de red, el backend retiene el lock hasta que vence el keepalive TCP, unas 2 h por omisión.
  - El reclamo de `arm_live` no tiene ninguna prueba: el mutante X-H11-7 sobrevive.
- **A7. Dos market makers en el mismo proceso por carrera** (`api/state.py:1790` contra `1878`, sin lock). El que queda sin referencia no lo alcanza ni el stop ni el apagado (P1c). [pre] DEMOSTRADO.

### Medios

- **M1. Dos pruebas nuevas de PostgreSQL no están aisladas.** [v3] [nuevo] DEMOSTRADO por mí.
  - `test_the_holding_connection_is_not_left_idle_in_a_transaction` cuenta los advisory locks de todo el servidor: falla si otro rol tiene un lock en otra base (`logs/B6_*`).
  - `test_a_terminated_backend_is_reported_as_a_lost_exclusion` hace `SELECT pg_terminate_backend(pid) FROM pg_locks WHERE locktype = 'advisory' AND granted`:
    - con un rol no superusuario, falla en cuanto hay locks ajenos;
    - con un superusuario sobre un servidor compartido, **termina conexiones de otras aplicaciones**, entre ellas una instancia real de Trader-IA que tenga su slot.
  - En el contenedor de servicio de la CI, que es dedicado, no hace daño.
- **M2. Huecos de cobertura en las propias correcciones de v3.** [v3] [nuevo] DEMOSTRADO. Sobreviven 4 de los 15 mutantes adicionales:
  - X-H11-3: el heartbeat no verifica la exclusión; la prueba llama a `_verify_session_slot()` directamente.
  - X-H11-2: una sesión que termina sola no libera el slot.
  - X-H11-7: `arm_live` no reclama el slot.
  - X-B2-1: el stop ignora `minQty`.

  De los otros 11, 10 mueren por comportamiento. X-D21-3 muere por un `AttributeError` del parser, no por el rechazo diseñado: el arranque igual se impide, pero por una caída (`logs/B5_*`).
- **M3. Sin cotas temporales para el primer stop.** Después de cada entrada, el stop recién se coloca al cierre de la vela siguiente. Mientras tanto, el estado es «none» y no hay bloqueo (H7 del revisor). [pre] DEMOSTRADO.
- **M4. Filtros.** [pre/v3] DEMOSTRADO en lo local.
  - Paper-live no usa los filtros del venue.
  - No se refrescan durante la sesión.
  - `minNotional` vacío se acepta.
  - Las órdenes reduce-only quedan exentas del notional mínimo (`execution/filters.py:148`). Con `applyMinToMarket`, una salida MARKET de menos de USD 5 la rechazaría el venue (PLAUSIBLE).
  - No se cargan `MARKET_LOT_SIZE`, `maxQty`, `PERCENT_PRICE_BY_SIDE` ni `MAX_NUM_ALGO_ORDERS`.
- **M5. El equity de una corrida terminada se escribe con el `run_id` de la siguiente** (`api/state.py:976-984`, verificado). El vaciado final no ve la cola de la corrida reemplazada. [pre] DEMOSTRADO.
- **M6. Recuperación al arrancar: se sella la fila de otra sesión antes de reclamar el slot** (`api/state.py:3101` antes de `3113`, verificado). Una sesión viva de otro proceso queda marcada como terminada; si ese proceso muere después, la sesión no se reanuda. [v3 la expone: el reclamo va después] DEMOSTRADO.
- **M7. Market maker.**
  - Las órdenes UNKNOWN quedan vivas después de `stop()` (P3f).
  - Un 401/403 en una cancelación cierra la orden localmente aunque siga en el venue (P3g).
  - El orphan sweep cancela las cotizaciones de otro maker vivo (P1d).

  [pre] DEMOSTRADO en simulación.
- **M8. El xfail de D26 no fija el modo de falla** (`raises=` o mensaje): puede enmascarar otra falla en ese camino. [v3]

### Bajos

- **B1. Logs huérfanos en el ZIP.** Los cuatro logs de commits de armados viejos que ya no existen (#21). [v3]
- **B2. R3/R6: la búsqueda de v3 está incompleta y su propuesta interpreta.** [v3] Ver §6.
- **B3. `ConnectTimeout` y `PoolTimeout` se tratan como UNKNOWN** aunque la orden nunca salió. Es conservador: frena de más. [v3]
- **B4. PID 1 en el compose.**
  - Un SIGTERM durante `alembic upgrade` se pierde (sh es PID 1).
  - Con Python como PID 1 no se recogen procesos zombis.
  - Un segundo SIGTERM hace que uvicorn saltee el cierre de la aplicación.

  [v3] DEMOSTRADO con `unshare` por el revisor.
- **B5. La URL de la base, con la contraseña, se usa como clave de un diccionario en memoria** (`persistence/session_lock.py:105-106`, `_raw_url`). No encontré filtración: se buscó la contraseña de prueba en todas las salidas, con 0 coincidencias. `_mask` no oculta `?password=`. [v3/pre]
- **B6. BTC-USD figura como shortable en spot.** Una señal SHORT termina en un -2010 y la sesión pasa a SAFE_MODE (d9). [pre]
- **B7. Identidad de los commits.** Autor y committer son «Trader-IA candidata local (Claude) <noreply@anthropic.com>», todos con la misma fecha y sin firma. Es una decisión antes de publicar. [v3]

---

## 5. Análisis técnico por tema

Matriz de riesgos residuales. «Bloqueo» dice exactamente qué se bloquea y qué pasa si el bloqueo falla.

| Riesgo | Escenario de fallo | Impacto | Detección | Protección actual | Evidencia | Mitigación propuesta | Prueba que lo cierra | Decisión tuya |
|---|---|---|---|---|---|---|---|---|
| C1 fills sin registrar | El stop salta en el venue | P&L y límite de pérdida ciegos; capital mal calculado; sesión en HALT | Sí: incidente «filled, unfilled» y `position_unverified` | HALT de nuevas órdenes. **Si falla:** nada contabiliza la pérdida | b1, b4, b8, b11; código; documentación oficial | Leer `myTrades` (o el user stream) por cada orden terminal con `executedQty > 0`; reconstruir los fills y la comisión desde ahí | Las pruebas b1/b4/b8/b11 pasan a fallar (el defecto desaparece); en Testnet, un stop-out registrado | Autorizar el diseño y la implementación |
| C2 / D25 | Al ajustar, el venue rechaza el nuevo stop (-2010) | Posición sin protección y sin salida, sin tope de tiempo | Sí: incidente `protection_failed` | Bloqueo de entradas. **Si falla:** el bloqueo también impide la salida por reversión | d1, d2, d7, d8; código | Colocar antes de cancelar (o `cancelReplace` con el modo adecuado); validar el nivel contra el último precio antes de enviar; política explícita: (a) mantener el stop viejo, (b) salir a mercado con tope de una salida, (c) pedir confirmación | d1 y d2 pasan a fallar; en Testnet, un -2010 al ajustar | Elegir la política (era D25) |
| C3 / D26 | Comisión en BTC o BNB | Sin stop (diferencia > 1 lote), polvo que bloquea para siempre, comisiones mal valuadas | Parcial: HALT; las comisiones mal valuadas, **no** | HALT | b1b, b2, b3b, b5, b7, b10 | Comisión por fill desde `myTrades`, cantidad neta, valuación en quote con la fuente explícita, regla para el polvo (umbral y reconocimiento) | El xfail de D26 pasa y se elimina; b2, b7 y b10 pasan a fallar | Decisión contable (era D26) |
| C4 market maker y sesión | Los dos sobre la misma cuenta | Ventas cruzadas de inventario, stops ajenos, conciliaciones falsas | Tarde, por reconciliación | Solo la configuración y el operador | P1a, P1b, P1e, P1g | Lock por cuenta del venue (no por base) para los dos caminos, más un lock propio del market maker entre procesos | P1a y P1b pasan a fallar | Decidir si pueden coexistir; si sí, con cuentas separadas |
| A1 y A3 ambiguos | 5XX y consulta fallida; reenvío con el mismo id de una orden llenada | Posición sin rastrear; posible doble salida o doble stop | Parcial | HALT en la entrada; en la salida, **ninguna** (la excepción escapa) | P3b, P3c, P3d; código; documentación | Reintentar la consulta con backoff y bloquear hasta resolver; capturar `ProviderUnavailableError` en las salidas; no reenviar sin una lectura positiva de ausencia más una espera | P3b, P3c y P3d pasan a fallar; Testnet: 503 inducido | Autorizar la implementación |
| A2 `-1006` | El venue responde -1006 con 4XX | Una orden ejecutada se toma como rechazada | No | Ninguna | P3a; documentación | Tratar -1006 como UNKNOWN | Una prueba de clasificación | — (técnica) |
| A4 flatten | La cuenta tiene otros activos | Venta de activos ajenos a la sesión | No | Ninguna | b9, b9b; código | Limitar el flatten al símbolo de la sesión | b9 y b9b pasan a fallar | — (técnica) |
| A5 apagado | `docker stop` con escenario, stream y base lenta, o con la base caída | SIGKILL a mitad del vaciado; registro en `stopping`; cuelgue | Sí, al reiniciar (R19) | El tope de 5 s solo para conexiones. **Si falla:** SIGKILL | Mediciones del revisor; código | Timeout en `_mark_stopping` y `_record_stop`; detener primero lo que toca dinero; `stop_grace_period` medido; `init: true` o tini | `docker stop` real con escenario, stream y base lenta | Fijar el plazo y el orden |
| A6 H11 | El lock se pierde o hay una partición | Dos sesiones durante ≤ 30 s; reinicio bloqueado hasta unas 2 h | ≤ 30 s con la base sana; **ninguna** con la base caída | Bloquea entradas; sigue gestionando posiciones | Pruebas del revisor (re-ejecutadas) | Verificar al decidir cada entrada, no solo al hacer heartbeat; keepalive TCP o `tcp_user_timeout` en la conexión del lock; prueba de `arm_live` | Matar el mutante X-H11-7; una prueba de ventana menor a una vela | Aceptar la ventana residual |
| R3/R6 | — | — | — | — | §6 | — | Definición escrita | Definir o retirar |

### 5.1 D26
Arriba, C3. La propuesta de v3 es necesaria pero no suficiente: falta la regla por fill y la fuente de la comisión (C1 está en el medio).

### 5.2 D25
- Arriba, C2. Una cantidad válida y un precio válido son condiciones distintas.
- B2 corrige la cantidad, pero el precio solo se redondea al tick: no se compara con el último precio antes de enviar, ni se cargan los filtros de precio (`PERCENT_PRICE_BY_SIDE`, `minPrice`/`maxPrice`).

### 5.3 R19 y el apagado
- **Los dos vaciados vencidos:** consta en §3 #18. La causa es contención de CPU bajo L2: cada escritura fue 2,7 a 3 veces más lenta, con ~1 200 escrituras en serie, y la media de 8,4 a 8,8 ms supera los 8,33 ms que permiten vaciar en 10 s. Al vencer quedaban 63 y 11 escrituras pendientes (`revisores/r19_h11/`).
- **La señal:** con `exec`, sí le llega al proceso correcto.
- **Configurado contra medido:**
  - el tope de 5 s está configurado y medido (5,6 s);
  - el apagado total no tiene tope ni está medido con Docker.
- **Al apagar:**
  - las órdenes y el stop en el venue **no se cancelan**: la idea es reanudar;
  - las escrituras pendientes se abandonan y se cuentan;
  - con SIGKILL se pierde la cola en memoria.
- No subí el plazo de gracia como sustituto: primero hay que acotar las esperas sin tope y cambiar el orden.

### 5.4 H11
- **Alcance:** en PostgreSQL, por base. En SQLite, por archivo del host (funciona entre espacios de montaje sobre el mismo volumen). No es por cuenta del venue.
- **Procesos reales:** solo las pruebas «CHILD» del lock usan procesos separados. Las de «dos AppState» corren en un mismo proceso.
- **Huecos:** los de A6 y M6.

### 5.5 Exclusión con el market maker
Arriba, C4. No está implementada, no está probada y no está documentada como requisito de arranque.

### 5.6 Filtros y respuestas ambiguas
- **Filtros:** la sesión live no arranca sin ellos (verificado; hay mutantes muertos que lo cubren). Lo demás, en M4.
- **Respuestas ambiguas:** A1, A2 y A3. Lo que funciona bien: un timeout o un 5XX al enviar el stop se resuelve por client id y queda un solo stop (d5, d5b).

### 5.7 Clasificación pedida
1. **Defectos demostrados:**
   - críticos: C1, C2, C3, C4;
   - altos: A1 a A7 (A3 con su parte en el venue PLAUSIBLE);
   - medios: M1, M2, M5, M6, M7.
2. **Riesgos plausibles no demostrados:**
   - el comportamiento del venue en A1/A3 (-2013 en vuelo);
   - el estado HTTP de -1006;
   - el notional de las salidas chicas;
   - unlock fallido que deja el lock colgado;
   - PgBouncer en modo transacción.
3. **Decisiones de diseño pendientes:**
   - política de D25;
   - contabilidad de D26;
   - coexistencia del market maker y la sesión;
   - orden y plazo del apagado;
   - política de polvo;
   - R3/R6;
   - las decisiones D1, D4, D6–D9, D18–D20, D23, D24 y D27 heredadas.
4. **Limitaciones de la evidencia:**
   - los venues son simulados;
   - sin Testnet;
   - sin Docker;
   - sin GitHub;
   - sin firma;
   - la custodia de los hashes la hizo la misma cadena de trabajo.

---

## 6. R3/R6 y demás decisiones pendientes

**R3/R6 siguen sin una definición autorizada. No los cierro.**
- En el repositorio protegido aparecen con **al menos dos significados distintos y sin relación**:
  - los ítems R1–R7 de un simulacro del market maker en Testnet (`docs/MARKET_MAKING_PHASE4_LIVE_ARCHITECTURE.md:610-612, 729-730`; `scripts/validate_mm_live_service_testnet.py:941, 956`);
  - los requisitos R3/R6 de un paquete de revisión de investigación (`research/hcarry_next/recuperado/VERSIONES_INTERMEDIAS_NO_FINALES/PAQUETE_REVISION_HCARRY_REV5.md:104, 107`).
- La búsqueda de v3 omite el segundo.
- Ninguno corresponde con claridad a la lista de riesgos (R15, R17, R18, R19, R22, R24) donde figuran R3 y R6.
- La propuesta de v3 (`evidence/r3_r6/PROPUESTA_R3_R6_v3.md` §3) dice no atribuir significado, pero después asocia R3 con B1/B2 y R6 con H11. Eso es interpretación y **no** sirve para cerrarlos.
- **Decisión tuya:**
  - (a) dar la definición original;
  - (b) redefinirlos por escrito con un criterio de cierre;
  - (c) retirarlos por escrito.

**Otras decisiones pendientes** (sin cambio respecto de v3, salvo donde se indica):
- D1, D4, D6–D9, D18–D20, D23, D24.
- D25: ahora incluye el caso del ajuste.
- D26: ahora incluye la regla por fill y el polvo.
- D27.
- Nuevas:
  - coexistencia del market maker y la sesión;
  - política de polvo;
  - orden y plazo del apagado;
  - base e identidad de la publicación.

---

## 7. Pruebas realizadas

**Entorno:**
- Linux en la nube, 2 núcleos, CPython 3.11.15.
- Venv **nuevo** (`_trabajo/venv`) instalado desde PyPI con `ci/constraints-py311.txt` del árbol: `pip freeze` igual a las constraints, 74 paquetes.
- PostgreSQL 16.15 desechable (`reproduccion/pg_aislado.sh`):
  - puerto 55433, solo 127.0.0.1;
  - zona del servidor Buenos Aires;
  - roles no superusuario `revision` (suite) y `revisor_h11` (revisor).

| # | Qué | Comando (resumido) | Resultado | Log |
|---|---|---|---|---|
| 1 | Estado inicial de solo lectura | `reproduccion/estado_solo_lectura.sh` | todo igual a lo registrado | `evidencia/00_estado_inicial.txt` |
| 2 | ZIP y manifiesto | `reproduccion/verificar_zip.py` | §2 | `logs/A1_*` |
| 3 | Reconstrucción desde el ZIP | `reproduccion/reconstruir_desde_zip.sh` (clon nuevo, sin origin) | 6 de 6 trees iguales, bundle OK | `logs/A2_*` |
| 4 | Commit 1 contra el ZIP v2 | `git archive c6339e3` + `git apply` de los 32 parches v2 | tree `c5641915…`, huella `cfeeda97…` | `logs/A3_*` |
| 5 | Cambios v2→v3 | `git diff` | 21 archivos | `logs/A4_*`, `logs/A5_diff_produccion_v2_a_v3.patch` |
| 6 | Sobre la punta remota local | `git am` sobre `72ffae5` (clon desechable) | aplica limpio, mismo diff | `logs/A6_*` |
| 7 | Lint | `ruff check` | OK | `logs/B2_ruff.txt` |
| 8 | Suite completa, UTC, con PostgreSQL | `pytest tests` | **2 322 + 2 xfail, 0 fallas, 0 saltadas**, igual caso por caso | `logs/B2_completa.*`, `logs/B3_*` |
| 9 | `tests/postgres` en Buenos Aires | `TZ=America/Argentina/Buenos_Aires pytest tests/postgres` | 1.º intento: 154 + 1 xfail + **1 falla** (aislamiento, #10). 2.º, sin otra carga: **155 + 1** | `logs/B2_postgres_tz_ba*.txt` |
| 10 | Aislamiento de la prueba de locks | `reproduccion/aislamiento_pg_locks.sh`: un advisory lock en otra base mientras corre la prueba | falla siempre | `logs/B6_*` |
| 11 | Rojo sobre v2 | `reproduccion/rojo_sobre_v2.sh` + `clasificar_rojo.py` | §3 #13 | `logs/B4_*` |
| 12 | Control del apagado en v2 | prueba de control adaptada | el servidor v2 sigue vivo a los 8 s, sin registro | `logs/B4_rojo_v2_d3_control_en_v2.txt` |
| 13 | 15 mutantes adicionales | `reproduccion/mutantes_extra.py`; 2.ª pasada para H11, sin otra carga y con la línea de base sin mutar en verde | 11 muertos y 4 vivos | `logs/B5_*` |
| 14 | Pruebas del revisor del market maker | `pytest tests/auditoria` | 23 de 23 (observan los defectos) | `logs/C1_*` |
| 15 | Pruebas del revisor D26/D25 | `pytest test_audit_d26.py test_audit_d25.py` | 26 de 26 (26 PASSED, rc 0) | `logs/C2_*` |
| 16 | Pruebas del revisor R19/H11 | `pytest test_auditoria_*` (SQLite y PostgreSQL) | 6 de 6 | `logs/C3_*` |
| 17 | Mediciones de apagado del revisor | `revisores/r19_h11/scripts/apagado_real.py` | **no re-ejecutadas** por mí; datos en `revisores/r19_h11/salidas/apagado/` | — |
| 18 | Documentación oficial | errors, http-return-codes, query order/myTrades, newClientOrderId | citas en §4 | Fuentes |
| 19 | Estado final de solo lectura | `reproduccion/estado_solo_lectura.sh` | igual al inicial | `evidencia/90_estado_final.txt` |

**Cambios de estado** (todos en recursos desechables de esta revisión):
- **Escritos:**
  - copias de árboles en `_trabajo/` (excluido del ZIP);
  - el venv nuevo;
  - el cluster PostgreSQL desechable, donde las pruebas crearon y borraron bases (destruido al final);
  - 3 copias de árbol de los revisores, que solo agregaron archivos de prueba.
- **Procesos:**
  - servidores uvicorn de prueba con SIGTERM y SIGKILL;
  - un proxy TCP del revisor;
  - un `pg_advisory_lock` de 25 s como superusuario del cluster desechable (comando en `reproduccion/aislamiento_pg_locks.sh`).
- **No se tocó:**
  - el cluster del sistema (metadatos iguales);
  - el repositorio protegido;
  - las entregas anteriores, incluida la v3;
  - los experimentos congelados.

---

## 8. Matriz de aprobación A–G

| | Etapa | Estado | Fundamento |
|---|---|---|---|
| **A** | Integridad de la entrega | **APROBADO** | Hashes completos, manifiesto, reconstrucción exacta, sin cambios no declarados, suite reproducida. Salvedades: sin firma ni ancla externa, y cuatro logs huérfanos |
| **B** | Calidad técnica de la candidata | **NO APROBADO** (para integrarse a la rama protegida) | Es mejor que v2 y no encontré regresiones. Pero tiene huecos demostrados en sus propias correcciones (A2, A6, M2, B4), las pruebas de M1 no están aisladas, y deja abiertos C1–C4 del camino live. **Sí es apta como objeto de revisión** |
| **C** | Publicar `candidata/v3` en una rama de revisión | **APROBADO, solo tras las condiciones previas de §9** | Reproducible, sin secretos ni pasos de despliegue, reversible (se borra la rama). No habilita nada. Lo que falta decidir es la base, la identidad de autor y la visibilidad de lo que se publica. Los permisos de GitHub no están verificados |
| **D** | Correr la CI remota | **APROBADO, en las mismas condiciones** | Workflow con `permissions: contents: read` y sin despliegue. Conteos esperados conocidos (§9). Plan de falla definido |
| **E** | Binance Testnet | **NO APROBADO** | C1–C4 hacen que una corrida en Testnet frene o mida mal en lo mismo que se quiere validar. Primero hay que corregirlos en local y que sus pruebas pasen a verde. Además hacen falta credenciales de Testnet y tu autorización explícita |
| **F** | Operar con dinero real | **NO APROBADO** | C1–C4, Testnet sin validar, R3/R6 sin definición, decisiones de riesgo pendientes, `docker stop` real sin medir |
| **G** | Evidencia de rentabilidad de la estrategia | **NO EVALUABLE** | Esta revisión no contiene, ni puede contener, evidencia de rentabilidad. Una suite en verde no dice nada sobre ganar dinero |

---

## 9. Próximo paso recomendado: publicar y correr la CI **solo tras las condiciones previas**

**Condiciones de entrada (decisiones tuyas):**
1. **Base:**
   - **(a)** `c6339e3`, exactamente lo validado acá. Es lo que recomiendo para la primera corrida.
   - **(b)** la punta remota actual. Antes hay que leerla, re-aplicar la serie y volver a correr la suite local sobre ese árbol.
2. **Identidad de los commits:** mantener «Trader-IA candidata local (Claude)», o re-firmarlos con tu identidad. En ese caso cambian los hashes de commit, pero no el tree `ef1983b6…`, que sigue siendo el control.
3. **Visibilidad:** aceptar que la rama y los mensajes de commit describen defectos abiertos (D25/D26). Si el repositorio es público, quedan públicos.
4. Una persona con acceso de escritura confirma que en el repositorio no hay otros workflows ni reglas que desplieguen algo ante un push. En el árbol hay uno solo (`ci.yml`), sin despliegue.

**Comandos exactos** (para quien tenga acceso; **no los ejecuté**):
```bash
git clone https://github.com/elianengelberg/trader-ia trader-ia-revision   # clon NUEVO, no el protegido
cd trader-ia-revision
git log -1 --format='%H' origin/claude/algo-trading-simulation-platform-ngf7xo   # anotar la punta remota real
git checkout -b revision/candidata-v3 c6339e3fcd6041cb6c4ad7f5545f0ff306a4fd2f   # opción (a)
git am /ruta/a/patches/candidata_v3/000*.patch
test "$(git rev-parse 'HEAD^{tree}')" = ef1983b6c87414478a8ed139ea79e91919f46c0e && echo TREE_OK
git push origin revision/candidata-v3        # ← la única acción externa; requiere tu autorización
```
- **Permisos necesarios:** escritura sobre el repositorio para crear una rama, y Actions habilitado.
- **No incluye:** PR, merge ni cambios en ramas protegidas.

**Criterios objetivos de salida (CI en verde):**
- **Job `python`:**
  - `ruff` OK;
  - 2 168 casos (2 167 aprobados y 1 xfail, D26);
  - guardia JUnit con rc 0;
  - `tz-ba` con 62 casos;
  - migraciones SQLite OK.
- **Job `postgres`:**
  - zona de la base aplicada;
  - 156 casos (155 + 1 xfail, R24-O1) en UTC y en Buenos Aires;
  - guardia con rc 0;
  - `upgrade`, `downgrade -1` y `upgrade` → `0008 (head)`.
- **Job `frontend`:** `npm ci`, `typecheck` y `build` OK.
- Ninguna prueba saltada y ningún xfail fuera de la lista.

**Si falla:**
- No re-correr a ciegas ni empujar arreglos sin una nueva autorización.
- Bajar los JUnit (`upload-artifact`) y comparar caso por caso con `logs/B2_completa.junit.xml`.
- Clasificar la falla:
  - **entorno o runner**, por ejemplo los tiempos de las pruebas con servidor real (`test_shutdown_with_open_stream`, 15 s);
  - **contra código.**
- En la CI, las dos pruebas de M1 deberían pasar, porque el servicio es dedicado. Si fallan, la causa probable es otra conexión en el servidor.

**Después de la CI, antes de cualquier Testnet:** corregir en local C1–C4, A1–A7, M1 y M2. Una por una, con pruebas que hoy observan el defecto y que pasen a fallar, y con nueva revisión.

---

## 10. Decisiones que requieren tu autorización explícita

1. Publicar `revision/candidata-v3`: base, identidad y visibilidad (§9).
2. Correr la CI remota.
3. Abrir un PR o hacer merge. **No recomendado todavía:** B no está aprobado.
4. Corregir C1–C4 y A1–A7. D25 y D26 cambian el comportamiento financiero; C4 decide si el market maker y la sesión pueden coexistir.
5. Política de polvo, orden y plazo del apagado, y `stop_grace_period`/`init` en el compose de producción.
6. Definir o retirar R3/R6.
7. Testnet, con credenciales de Testnet, después del punto 4.
8. Habilitar trading real: **no autorizado y no recomendado.**

---

Fuentes oficiales consultadas el 2026-10-26 con la herramienta de lectura web (las citas textuales están en §4):
- [Error codes](https://developers.binance.com/docs/binance-spot-api-docs/errors) — -1006 y -1007 «execution status unknown».
- [HTTP return codes](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/http-return-codes) — 5XX «NOT treat this as a failure operation; the execution status is UNKNOWN».
- [Account endpoints](https://developers.binance.com/docs/zh-CN/binance-spot-api-docs/rest-api/account-endpoints) — la consulta de orden no trae `fills`; `myTrades` trae `commission` y `commissionAsset`.
- [Trade endpoints](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/trade) — `newClientOrderId` es único solo entre órdenes abiertas.
- [Filters](https://developers.binance.com/docs/binance-spot-api-docs/filters).
