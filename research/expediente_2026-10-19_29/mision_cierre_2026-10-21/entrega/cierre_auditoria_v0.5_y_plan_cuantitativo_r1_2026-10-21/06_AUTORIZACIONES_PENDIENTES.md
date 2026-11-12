# 06 — Autorizaciones pendientes, en orden de prioridad

Cada fila dice qué autorizar, qué hay preparado, qué responder y si es reversible. Nada de esto se hizo.

| # | Qué | Por qué ahora | Preparado | Qué responder | ¿Reversible? |
|---|---|---|---|---|---|
| **1** | **Descargar** este ZIP y el de v0.5 (B-8 / D-G0) | El scratchpad es efímero: si se libera el contenedor, se pierde todo | Los dos ZIP, con su SHA-256 en `00_RESUMEN_EJECUTIVO.md` | Nada: descargalos y verificá el SHA-256 | — |
| **2** | **A-S1:** calibración sintética de la prueba primaria | Sin ella, ninguna evaluación confirmatoria futura es válida | Script bloqueado; parámetros congelados (`28764d31…`); costo de 1,3–3,9 h de CPU | «Autorizo A-S1» (y una referencia) | Sí: solo datos sintéticos |
| **3** | **A8 / D-S4:** fijar δ, el exceso neto anual mínimo relevante | Sin δ no hay fase prospectiva ni «efecto descartado» | Criterios y tabla en `documentos_para_autorizar/AS1_CALIBRACION_Y_A8_DELTA.md` | «δ = X %/año, desde AAAA-MM-DD» | Sí, mientras ningún prerregistro lo use |
| **4** | **R-3 / A12:** firmar la declaración de T | Es lo único que puede llevar a T de INCONCLUSO a VERIFICADO | `documentos_para_autorizar/R3_declaracion_T/` (bytes comprobados) | La clave pública (64 hex), la firma (128 hex) y la fecha. **Nunca la clave privada** | La firma, sí (se revoca la raíz) |
| **5** | **D-G6:** publicar los commits `f518ac1` y `692f2b2` | Da la fecha pública de los congelados de T y T-MULTI | `B1_PLAN_PARCHES_Y_COMMITS.md` (opción a) | «Autorizo publicar» o «no publicar» | **No** |
| **6** | **R-5:** ancla externa O2 + O5 | Uso único verificable y detección de reescrituras de los registros | `R5_ANCLA_EXTERNA.md` | Crear el repositorio, la protección y el token; luego «autorizo el adaptador» y, aparte, «autorizo sellar hashes en OpenTimestamps» | O2, sí. **Los sellos, no** |
| **7** | **D-G4 / D-T1:** dónde se escriben los registros prospectivos | El corte de T-papel es el **2027-04-18** | Recomendación: el repositorio de O2, rama `registros` | La ubicación | Sí |
| **8** | **B-1:** aplicar los parches 0001–0007 en una rama | Que el verificador exista en el repositorio y pueda revisarse | Procedimiento exacto y reversión | «Aplicar con base (a) o (b)» y, por separado, «publicar» | Sí, hasta publicar |
| **9** | **D-G1 / D-G5:** destino de H-REV-SHOCK v0.2 y H-EMA9-VWAP v0.2 | La criba indica que no son detectables en un horizonte útil | `05_PLAN_CUANTITATIVO.md` §6 | «No iniciar» (mi recomendación), o «iniciar X aceptando “no concluyente”» | Sí, antes de leer datos |
| **10** | **B-7:** designar a un revisor independiente | Todo lo hizo el mismo autor | Alcance y 8 preguntas en `B3_B4_B7_INTEGRACION_DATOS_REVISION.md` | Nombre o perfil del revisor | — |
| **11** | **B-4:** leer datos reales | Solo cuando un prerregistro congelado y anclado lo declare | Plan de 7 controles; validador listo | «Autorizo leer exactamente lo que declara H-…» | Leer, no |
| **12** | **B-3:** integrar el ejecutor en un ejecutor prospectivo nuevo | Después de R-5 | Análisis y pasos en `B3_B4_B7_*.md` | «Autorizo en entorno de prueba» | Sí, hasta el primer uso real |

**No pido decisiones de implementación.** Las técnicas reversibles ya están tomadas y documentadas:
D-S1, D-S2, D-S3, D-S5, D-S6, D-S7, A3, A4/A7, A6, A9, A10, A13 (política), A14 y D-T2 (`02_EXPEDIENTE_DECISIONES.md`).
