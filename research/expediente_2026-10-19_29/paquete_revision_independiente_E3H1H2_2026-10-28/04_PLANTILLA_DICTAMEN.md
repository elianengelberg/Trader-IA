# Dictamen de la revisión independiente de E3-H1/H2

> **Plantilla.** El revisor la completa en una copia (`DICTAMEN_REVISION_INDEPENDIENTE_E3H1H2.md`), no en este archivo.
>
> **Orden obligatorio:**
> 1. Parte 0;
> 2. Parte I (técnica);
> 3. Parte II (metodológica);
> 4. Parte IV (dictámenes).
>
> **La Parte III** (contradicciones y evidencia insuficiente) se completa **en el momento** en que aparece un problema. **Si se activa la regla de detención, el dictamen termina ahí.**

---

## Parte 0 · Identidad, independencia y restricciones

| Campo | Respuesta |
|---|---|
| Revisor (nombre o identificador) | |
| Fecha de inicio y de fin (UTC) | |
| ¿Participó en E3, E3R, la reparación, la revisión del 2026-10-26 o el cierre del 2026-10-27? (sí / no; si sí, en qué) | |
| ¿Tiene algún interés en el resultado de E3-H1/H2? | |
| sha256 de `MANIFEST_PAQUETE.sha256` recibido | |
| `sha256sum -c MANIFEST_PAQUETE.sha256`: resultado (OK / fallas) | |
| ¿Se extrajo el paquete de datos? ¿Validó su manifiesto? | |
| Entorno (sistema operativo, Python, numpy, pytest) | |

**Declaración de restricciones** (marcar cada una):

- [ ] No ejecuté E3-H1/H2 ni llamé a `ejecutar_E3_v2.py real` o `ejecutar_E3_v3.py real` con insumos reales y una autorización.
- [ ] No creé, guardé ni usé ninguna autorización. No escribí la FRASE real ni las frases de decisión en ningún archivo.
- [ ] No leí arreglos de precio ni de volumen (O, H, L, C ni QV) ni precios derivados. Si leí las series, fue solo `estado` y `simbolo`, con la guarda.
- [ ] No modifiqué la evidencia: trabajé sobre una copia.
- [ ] Separé la parte técnica de la metodológica: ninguna opinión de la Parte II se apoya en un punto técnico que no haya CONFIRMADO en la Parte I.

---

## Parte I · Comprobaciones técnicas

**Veredicto por punto:**
- **CONFIRMADO:** lo verifiqué yo y coincide;
- **REFUTADO:** lo verifiqué y no coincide;
- **NO VERIFICABLE:** no pude verificarlo, con el motivo.

**Toda afirmación lleva su evidencia:** el archivo y la línea, o el comando y su salida, o el hash.

**Regla de detención:** un REFUTADO o un NO VERIFICABLE en T-1, T-2, T-4 o T-5 abre una entrada en la Parte III.

| Punto | Veredicto | Evidencia | Observaciones (y L-n de `05` que confirma o refuta) |
|---|---|---|---|
| T-1 Integridad y procedencia | | | |
| T-2 Diff v2→v3 | | | |
| T-3 Tabla de renombres como extracción | | | L-1 … L-6 |
| T-4 Ruta de ejecución real | | | L-14, L-15 |
| T-5 Reintentos: implementación | | | L-11, L-12, **L-13** |
| T-6 Sin precios ni volúmenes | | | L-9 |
| T-7 Ventana A con la tabla completa | | | L-10 |
| T-8 Mapeos sobre la actividad real | | | L-7 |
| T-9 Pruebas y mutación | | | L-18, L-19 |
| T-10 Higiene de autorizaciones | | | L-20, L-25 |

**Detalle exigido en algunos puntos:**

- **T-2.** Cada cambio no declarado que se haya encontrado, con su línea. Si el revisor regeneró el v3 con `generar_v3.py`, el sha256 obtenido.
- **T-3:**
  - entradas revisadas a mano, con su id, si la cita está en el cuerpo y si r, E y la apertura están bien leídas;
  - el método propio de búsqueda de faltantes y su resultado;
  - si coincide o no con la estimación del autor de que los faltantes no mueven A.
- **T-5.** Para cada secuencia de L-13: si se reproduce, cómo (prueba propia en una copia) y qué efecto tiene sobre la política declarada.
- **T-9.** Los mutantes propios: descripción, si sobrevivieron y qué prueba los detectó.

**Hallazgos técnicos nuevos** (no listados en `05`):

| Id | Descripción | Evidencia | Gravedad (bloqueante / importante / menor) |
|---|---|---|---|
| | | | |

**Conclusión técnica** (sin opinar sobre metodología): ¿el v3 implementa lo que declara, incluida la lectura literal de D-1, sin camino que esquive las guardas?

---

## Parte II · Opiniones metodológicas

**Cada opinión indica:**
- en qué puntos de la Parte I se apoya (todos CONFIRMADOS);
- qué reglas congeladas cita;
- qué parte es interpretación propia.

**Lo que hace el revisor:** recomienda.
**Lo que hace el usuario:** decide.

### M-1 · Adenda R (D-A, D-B y D-C) — obligatorio

| Pregunta | Pronunciamiento |
|---|---|
| Opción recomendada: (1) no adoptar R; (2) adoptarla tal como está; (3) adoptarla con salvaguardas (cuáles); (4) otra | |
| ¿R corrige un criterio que medía el archivo, o relaja ad hoc un criterio congelado? Fundamento | |
| Peso de que R se escribiera después de ver que M0 no corre (y de la imposibilidad de probar el orden respecto de P0) | |
| Circularidad de (iv′) | |
| Punto ciego de (ii′) después del 2024-11-06 | |
| R1 literal frente a R1′ | |
| ¿Adoptar R revierte legítimamente el CIERRE §2 y dispensa el CIERRE §4, o exige otra cosa? | |
| ¿La evidencia alcanza para decidir? Si no alcanza → Parte III | |

### M-2 · GTO→GFT, LUNA→LUNC y UST→USTC (D-1) — obligatorio

| Pregunta | Pronunciamiento |
|---|---|
| Opción recomendada: (a) lectura literal; (b) continuidad, con una adenda nueva | |
| ¿La opción (a) aplica las reglas vigentes o es en sí una regla nueva? | |
| ¿Hace falta una adenda aclaratoria aunque se elija (a)? | |
| Casos intermedios no contemplados (por ejemplo, un hueco < 30 días con el par viejo ya retirado) | |
| ¿La evidencia alcanza? Si no alcanza → Parte III | |

### M-3 · 158 frente a 160 semanas (D-3) — obligatorio

| Pregunta | Pronunciamiento |
|---|---|
| Variante recomendada: fecha del cuerpo (N5; 158 semanas; margen de 2) o fecha del título (A3.1.5; 160; margen de 4) | |
| ¿A3.11 y A3.5 (a) autorizan corregir la fecha de eventos T o B? | |
| ¿Qué prevalece, N5 o A3.1.5? | |
| ¿Es relevante haber elegido entre dos variantes válidas durante la reparación y no antes? | |
| ¿Verificó las cifras de las dos variantes? (resultado de T-7 u otra comprobación) | |
| ¿La evidencia alcanza? Si no alcanza → Parte III | |

### M-4 · Riesgos residuales (D-5) — obligatorio

**Calificación de cada riesgo:**
- **A:** aceptable;
- **S:** aceptable con salvaguarda (decir cuál, y si requiere una adenda congelada antes de ejecutar);
- **I:** inaceptable.

| # | Riesgo (según `03`, M-4) | A / S / I | Fundamento y salvaguarda |
|---|---|---|---|
| 1 | Punto ciego posterior al 2024-11-06 | | |
| 2 | Circularidad de (iv′) | | |
| 3 | Fragilidad de (iv′) y de los 5 casos C | | |
| 4 | Margen de 2 semanas (4 con 160) | | |
| 5 | Recall incompleto de la extracción | | |
| 6 | Cambios de símbolo sin anuncio archivado (regla 3) | | |
| 7 | Cortes de 1 día sin anuncio dentro de A | | |
| 8 | Mapeos de certeza media dentro de A | | |
| 9 | Volumen de HIFI sin evaluar | | |
| 10 | Potencia baja | | |
| 11 | Un solo agente | | |
| 12 | Fallo del registro después de un resultado terminal (L-13) | | |
| 13 | Frases de decisión sin D-3, D-4 ni D-5 (L-17) | | |
| 14 | El v1 y el v2 siguen siendo ejecutables (L-25) | | |
| — | Riesgos nuevos que identifique el revisor | | |

**Juicio de conjunto:** ¿los riesgos residuales son compatibles con una ejecución confirmatoria única?

### M-5 · Reintentos como regla de gobierno (D-4)

| Pregunta | Pronunciamiento |
|---|---|
| Opción recomendada: (i) la implementada; (ii) solo «panel»; (iii) ninguno; (iv) otra | |
| ¿«validez_previa» debe contar como etapa sin estadísticos? | |

### M-6 · Metodología estadística

| Pregunta | Pronunciamiento |
|---|---|
| H1: IC de Spearman semanal, Newey–West, L = 4 | |
| H2: regla del máximo de tres valores p; IC90 como envolvente | |
| Holm con m = 2; robustez R1–R6; Sharpe deflactado con N = 20 | |
| Potencia en 158 semanas: ¿justifica la ejecución? | |
| ¿La inferencia es válida con autocorrelación y universos que cambian? | |
| ¿Recomienda cambios? (Solo con una adenda congelada antes de cualquier resultado) | |

### M-7 · Bifurcación BCC (D-2)

| Pregunta | Pronunciamiento |
|---|---|
| Conformidad o alternativa fundada | |

---

## Parte III · Contradicciones y evidencia insuficiente

**Regla de detención.** Ante una **contradicción** entre documentos, código y datos, o ante **evidencia insuficiente** para un punto técnico crítico (T-1, T-2, T-4 o T-5) o para un pronunciamiento obligatorio (M-1 a M-4):
1. registrarla acá **en ese momento**;
2. **detenerse**: no seguir con los puntos que dependen de ella;
3. **no emitir** recomendación sobre la autorización (Parte IV, dictamen 3 = «NO SE EMITE»).

| Id | Punto (T-n o M-n) | Tipo (contradicción / evidencia insuficiente) | Qué dice cada fuente, con cita | Qué haría falta para resolverla | ¿Detuvo el dictamen? |
|---|---|---|---|---|---|
| X-1 | | | | | |

**Punto en el que se detuvo la revisión** (si corresponde):

**Puntos que quedaron sin revisar por la detención:**

---

## Parte IV · Dictámenes (separados)

**Tres dictámenes que no se mezclan:**
- el 1 no puede depender de opiniones metodológicas;
- el 2 no puede apoyarse en un punto técnico no CONFIRMADO;
- el 3 solo puede emitirse si la Parte III no tiene entradas que detengan el dictamen.

### Dictamen 1 · Técnico

Una de estas opciones:
- [ ] **CONFORME:** el v3 y la evidencia hacen lo que declaran.
- [ ] **CONFORME CON OBSERVACIONES**, sin bloqueantes. Listar las observaciones.
- [ ] **NO CONFORME:** listar los bloqueantes.
- [ ] **NO SE EMITE:** detenido en la Parte III.

**Fundamento:**

### Dictamen 2 · Metodológico (opinión; decide el usuario)

| Decisión | Recomendación del revisor |
|---|---|
| D-A, D-B y D-C (Adenda R) | |
| D-1 (GTO→GFT y otros) | |
| D-2 (BCC) | |
| D-3 (158 / 160) | |
| D-4 (reintentos) | |
| D-5 (riesgos residuales) | |

**Fundamento:**

### Dictamen 3 · ¿Corresponde que el usuario evalúe una autorización?

**Este dictamen no autoriza nada.** Solo dice si, a juicio del revisor, la evidencia está en condiciones de que el usuario **considere**, por separado, autorizar una única ejecución restringida a la ventana A.

Una de estas opciones:
- [ ] **SÍ**, con estas condiciones previas:
- [ ] **NO**, por estos motivos:
- [ ] **NO SE EMITE:** detenido en la Parte III.

**Condiciones previas que el revisor considera necesarias** (por ejemplo: corregir L-13 en un v4, una adenda de salvaguardas o una verificación adicional):

---

## Firma

| Campo | Valor |
|---|---|
| Revisor | |
| Fecha (UTC) | |
| sha256 de este dictamen completo | (calcularlo después de cerrar el archivo y comunicarlo aparte) |
