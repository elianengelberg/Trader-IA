# Matriz final de aceptación y bloqueos residuales

**Estado de E3: BLOQUEADO** para ejecución. Esta matriz no lo cambia.

**Abreviaturas de responsable:**
- **AUT:** el agente autor (no independiente);
- **REV2:** el segundo revisor real;
- **USU:** vos.

**Resultados posibles:**
- **CUMPLIDO (preliminar):** hay evidencia del autor o de agentes de la misma familia, y falta REV2;
- **PARCIAL:** está cubierta solo una parte;
- **ABIERTO:** sin evidencia todavía.

| # | Criterio | Evidencia | Resultado | Responsable | Bloqueo restante |
|---|---|---|---|---|---|
| C1 | Revisión independiente real | Revisor del diseño v4 (fase anterior), verificador de la matriz, y lector y adjudicador de SL-v1: todos de la misma familia, en el mismo contenedor y lanzados por el autor | **PARCIAL** | REV2 y USU | Falta un revisor real (lista A) y tu criterio D-10 |
| C2 | R-1 corregido | Corrección con manejador: 8/8 (fase v4) y 0/72 violaciones con procesos reales; la batería detecta el diseño anterior (9/48 violaciones de S-2) | **CUMPLIDO (preliminar)** | AUT y REV2 | N-R1-5 (grupo de procesos, `pthread_kill`, `fsync` largo, SIGSEGV); verificación de REV2 |
| C3 | R-2: máquina de estados con decisión inexistente, persistida o incierta, sin repetición automática | `tecnico/MAQUINA_ESTADOS_v4_1.md`; 722 casos en disco sombra; 6 corrupciones; 5/5 mutantes | **CUMPLIDO (preliminar)**, condicionado a C8 | AUT y REV2 | Límite demostrado: sin ancla y con un disco que miente no hay garantía; dispositivo real no probado (N-R2-5) |
| C4 | R-4 / L-25: aislamiento efectivo, incluidas las rutas alternativas | Inventario: 2 conjuntos reales extraídos, 15 orquestadores y 6 documentos. Propuesta en 3 capas. Réplica sintética: 0 rutas resolubles y restauración byte a byte | **ABIERTO** | USU (D-9) | El sellado real exige tu orden. Sin ella, **L-25 sigue abierto** |
| C5 | L-13: persistencia verificada antes de cualquier ejecución | INV-2, INV-3, INV-5 e INV-6 en el prototipo; comprobación previa N-L13-3 especificada | **PARCIAL** | AUT (implementación) y REV2 | N-L13-3 se implementa con el lanzador; tiene que fallar ante ENOSPC, un ABIERTO previo, un ancla distinta o un temporal plantado |
| C6 | L-17: autorización inequívoca | Validador v4.1: 53/54 rechazos (solo el positivo de prueba); decisiones con valor único; vínculo con la cabeza, el nonce y los hashes | **PARCIAL** | USU (B7, B8) y AUT | Interoperabilidad con tu herramienta (N-L17-3); Ed25519 en el intérprete del orquestador (A-3) |
| C7 | Decisiones metodológicas documentadas | `DICTAMEN_D1_D8.md`: D-1(b), D-2, D-3, D-6 y D-7 RESUELTAS; D-4 y D-5 según SL-v1; D-1(c) y D-8 PENDIENTES | **PARCIAL** | USU | D-1(c), D-8 y la ratificación B5 |
| C8 | Ancla externa que la máquina pueda comprobar (R-3) | Las pruebas la muestran **necesaria** (N-R2-3) | **ABIERTO** | USU (D-11, A-1) | Mecanismo sin elegir; preservación de la salida estándar sin verificar |
| C9 | Segunda lectura con protocolo congelado | SL-v1 congelado antes de leer; lector ciego; 47/47 concordantes; 13 omisiones confirmadas; ambigüedad de los BLVT adjudicada a ciegas (§6) | **CUMPLIDO (preliminar)** | AUT, lector, adjudicador y REV2 | Verificación de REV2 (A1–A5). Defecto declarado de SL-v1: la cláusula de tokens apalancados de R-E |
| C10 | Ventana recalculada con parámetros, entradas, salidas, hashes y registros | Control de reproducción idéntico byte a byte. L2 con la fecha adjudicada: inicio 2024-04-08, 111 semanas, **INVÁLIDA**. L2 con la otra lectura: VÁLIDA (158). Registros en `segunda_lectura/calculo/*/registro_calculo.json` | **CUMPLIDO: A NO ES VÁLIDA** | AUT y REV2 | **Ninguna ventana candidata.** Recomendación: cerrar E3 sin cambiar la ventana |
| C11 | Criterios de aceptación completos | `tecnico/PLAN_PRUEBAS_NEGATIVAS.md`, con estado por prueba | **PARCIAL** | AUT y REV2 | Pendientes: N-R1-5, N-R2-4, N-R2-6, N-R4-4, N-R4-5, N-L13-3, N-L17-2, N-L17-3 y N-L17-4 |
| C12 | Preservación: repositorio, árboles congelados y evidencias originales | Huellas iguales al inicio (00:14:24Z) y al final (01:04:56Z) en 10 árboles y las páginas; git en `72ffae5`, sin cambios; protocolo y herramientas congelados 9/9 OK | **CUMPLIDO** | AUT | — |
