# E3 · Cierre decisivo del diseño v4

**Fecha:** 2026-10-29 (UTC).

**Autor:** el agente autor de la reparación, del v3 y del diseño v4. **No es independiente.**

**Restricciones cumplidas:**
- no se ejecutó E3, H1 ni H2;
- no se calculó ni se consultó ningún retorno;
- no se leyeron precios ni volúmenes: la conciliación y la ventana congeladas leen solo `estado` y `NT`;
- no se crearon, emitieron ni consumieron autorizaciones;
- no se modificaron el repositorio, los árboles congelados ni T-MULTI;
- no se borró nada.

Todo el trabajo está en `cierre_decisivo_v4_2026-10-29/`.

## Dictamen: **BLOQUEADO**, con recomendación de **cerrar E3 sin cambiar la ventana**

**Motivo principal, verificable:**
- La candidata A **no supera la segunda lectura conforme a la Adenda R**.
- La búsqueda de omitidos, con una regla congelada antes de leer, encontró 6 remociones de tokens apalancados BLVT (BNB, ETH y BTC UP/DOWN) que no estaban en el universo de eventos.
- El anuncio fija dos fechas por par: cese del trading el 2024-02-28 y delisting el 2024-04-01/02/03.
- El adjudicador ciego del protocolo eligió el delisting. Con esa fecha, los 6 BLVT son fallas T en alcance, y la ventana conforme a la Adenda R (código congelado, R1 literal) empieza el **2024-04-08 con 111 semanas: INVÁLIDA**. La v3 pura da lo mismo.
- La regla de decisión fijada antes de leer (SL-v1 §9, igual que `INFORME_DECISION` §7 R-2) manda **cerrar sin cambiar la ventana**. Aun tratando la fecha como no resuelta, A no es válida con todas las alternativas.

**Lo que no hice y por qué.** Con la otra lectura (cese del trading), A sería VÁLIDA con 158 semanas.
- La ambigüedad viene de una cláusula de **mi** protocolo, que agregué al redactarlo y que no está en N5.
- Elegir ahora la lectura que rescata la ventana, sabiendo que la rescata, repetiría el defecto de R1′.
- No lo hago y no lo recomiendo. Si se quisiera reabrir este punto, sería una decisión metodológica humana tomada con conocimiento de su efecto, y tendría que declararse así.

**Otros motivos de bloqueo,** que seguirían vigentes aunque A fuera válida:
- no hay revisión independiente fuerte;
- L-25 sigue abierto hasta que des la orden de sellar las 2 copias reales extraídas;
- el ancla externa, que las pruebas muestran necesaria, no tiene mecanismo ni verificación;
- D-1(c) y D-8 están pendientes.

## Entregables

| Pedido | Archivo |
|---|---|
| Dictamen de D-1 a D-8 | `DICTAMEN_D1_D8.md` |
| Protocolo congelado de la segunda lectura | `segunda_lectura/protocolo/PROTOCOLO_SEGUNDA_LECTURA_v1.md` (sha256 `26ad1cf7…`, congelado a las 00:24:56Z) y `registro/CONGELACION_SL-v1.txt` |
| Resultado de la segunda lectura y ventana | `segunda_lectura/RESULTADO_SL-v1.md`. Registros: `segunda_lectura/calculo/{control_pasada2,L2,L2_variante_BLVT}/registro_calculo.json` |
| Plan de pruebas negativas: R-1, R-2, R-4, L-13 y L-17 | `tecnico/PLAN_PRUEBAS_NEGATIVAS.md`, `tecnico/MAQUINA_ESTADOS_v4_1.md`, `tecnico/PROPUESTA_R4_AISLAMIENTO.md`. Código y salidas en `tecnico/` |
| Matriz de aceptación y bloqueos residuales | `MATRIZ_ACEPTACION.md` |
| Evidencia que tiene que verificar un segundo revisor y cuestiones que requieren revisión humana | `LISTA_SEGUNDO_REVISOR_Y_REVISION_HUMANA.md` |
| Potencia (D-8) | `metodologia/potencia_D8.py` y `potencia_D8.txt` |
| Manifiesto y comprobación de no cambios | `MANIFEST_CIERRE_DECISIVO.sha256`, `registro/huellas_inicio.txt`, `registro/huellas_fin.txt`, `registro/git_fin.txt` |

## Estado de cada decisión

| Decisión | Estado | Síntesis |
|---|---|---|
| D-1 Reapertura | (b) solo el diseño: **RESUELTA** por tus instrucciones. (c) ejecución: **PENDIENTE DE DECISIÓN HUMANA**, sin ventana que la sostenga | Hoy no hay una candidata válida |
| D-2 R1 o R1′ | **RESUELTA**: R1 literal | R1′ es posterior a P0, motivada por potencia y retirada por su autor. Con SL-v1 el resultado tampoco depende de esto |
| D-3 Regla de fecha | **RESUELTA**: N5 | La Adenda 3 «no cambia criterios»; A3.1.5 es la heurística del extractor |
| D-4 158 o 160 | **RESUELTA**: 158 por N5, **sin efecto** | A no sobrevive a SL-v1 |
| D-5 Omitidos | **RESUELTA**: regla SL-v1 §7 aplicada | 13 remociones confirmadas. Los 6 BLVT invalidan A con la fecha adjudicada |
| D-6 Continuidad | **RESUELTA**: (a) listado nuevo | Lectura literal ya implementada. Afecta solo a GFT |
| D-7 Reintentos | **RESUELTA**: cero reintentos (iii), formalizada y probada en el prototipo | El ancla es necesaria |
| D-8 Potencia | **PENDIENTE DE DECISIÓN HUMANA**, subordinada al cierre | P(RESPALDADA) ≤ 0,13–0,17; H1 0,35–0,55 con 158 semanas. Un INSUFICIENTE apenas informa |

## Evidencia técnica (preliminar, del autor y de agentes de la misma familia)

| Tema | Resultado |
|---|---|
| R-1 | Manejador: 0 violaciones en 72 corridas con procesos reales y numpy. El diseño anterior viola S-2 en 9 de 48 |
| R-2 | 722 casos en disco sombra sin violaciones fuera del límite; 5/5 mutantes detectados. **Límite:** sin ancla externa y con un disco que miente, se puede reabrir o clasificar mal (15 y 14 casos) |
| L-17 | 53/54 vectores rechazados |
| R-4 | Inventario hecho. Sellado demostrado en una réplica sintética |

## Decisiones humanas imprescindibles (lista mínima)

1. **Cerrar E3 sin cambiar la ventana** (recomendado). Que siga NO EVALUABLE, sin reabrir para ejecución, sin B, R1′ ni reglas nuevas. Si decidís reabrir el punto de la fecha de los BLVT, tiene que constar que es una decisión metodológica tomada **conociendo** que rescata la ventana.
2. **Sellar las 2 copias reales extraídas de las series (D-9),** aunque E3 se cierre. Mientras existan con su estructura de rutas, cualquiera de los 15 orquestadores puede correr por descuido y contaminar la historia. Requiere tu orden, porque cambia rutas de árboles congelados (`tecnico/PROPUESTA_R4_AISLAMIENTO.md`).
3. Solo si, en contra de la recomendación, quisieras sostener una ejecución:
   - D-1(c) y D-8;
   - el mecanismo del ancla y la verificación de A-1;
   - el criterio de independencia (D-10) y un segundo revisor real;
   - la herramienta de firma y Ed25519 (A-3).
