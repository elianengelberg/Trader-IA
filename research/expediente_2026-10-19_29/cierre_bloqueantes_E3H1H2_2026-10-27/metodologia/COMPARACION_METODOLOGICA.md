# E3-H1/H2: metodología congelada frente a la Adenda R

**Fecha:** 2026-10-27.

**Propósito:** separar lo que es ingeniería (corregible sin tu permiso, porque solo lleva el código a lo que dicen las reglas congeladas) de lo que es metodología (cambia una regla o revierte una decisión, y solo vos podés aprobarlo).

**Qué no hace este documento:**
- no adopta la Adenda R;
- no modifica ninguna regla congelada;
- no autoriza nada.

---

## 1. Las alternativas

| Id | Alternativa | Estado documental |
|---|---|---|
| **M0** | **v3 congelada** (`PROTOCOLO_E3_v3_PROPUESTO.md`, `279a865f…`) con notas N1–N20, Adenda 1, Adenda 3 y Enmienda 2 | Vigente. Con ella E3 quedó **CERRADO · NO EVALUABLE** (`CIERRE_E3.md`, 2026-10-20, decisión tuya) |
| **M1** | **M0 + Adenda R con R1 literal** (`ADENDA_R_auditoria_de_supervivencia_interna.md`, `87f60413…`) | **Propuesta**, congelada el 2026-10-26 a las 19:43:13Z, antes de P0. **No adoptada.** La propia adenda dice que adoptarla es «una decisión estratégica (categoría B)» que no le corresponde a quien la escribió |
| M1′ | M1 con R1′ (alcance por clase) | Descartada en la decisión anterior: alarga la ventana (B, desde 2021-02-22) y se eligió después de ver P0. No se reconsidera aquí |
| M2 | M0 + una lista completa y verificable de exclusiones y renombres 2020-05…2026-05 (CIERRE §4) | No disponible: el archivo web termina el 2024-11-06. Requeriría otra fuente, y la v3 §2.3 exige una adenda y tu autorización para fuentes no oficiales |
| M3 | Mantener E3 cerrado (pausa de la familia transversal) | Es el estado actual |

---

## 2. Qué reglas cambia cada alternativa

| Regla | M0 (v3 congelada) | M1 (Adenda R, R1 literal) |
|---|---|---|
| (i) 13 semanas seguidas evaluables | 2020-05-11 | Sin cambio: 2020-05-11 |
| (ii) última falla T/D/C no explicada de §2.3 | Todas las fallas → **2023-05-15** | (ii′): solo fallas «en alcance» (no en lista fija ni apalancados, según `listas_fijas_por_lunes.json`) → **2023-05-15**. Con R1 literal, los 6 tokens apalancados de mayo de 2023 siguen en alcance, así que (ii′) = (ii) |
| (iii) 1 de enero del primer año con anuncios en el archivo | 2019-01-01 (no limita) | **Se deja de aplicar** (Adenda R, R3) |
| (iv) en todos los años, salidas sin anuncio ≤ 10 % | **Falla en todos los años** (2025: 51/51; 2026: 26/26), porque el archivo termina el 2024-11-06 | (iv′): salidas en alcance sin evidencia **interna** (ANUNCIO o SUSPENSION, vela parcial con `estado` = 3, o COLA_CERO, fila con 0 operaciones) ≤ 10 % → **2018** |
| Contabilidad de fallas de §2.3 | Todas | Solo en alcance (R1) |
| Inicio de H | Ninguno válido → **INVÁLIDO** | **2023-05-15** (lo fija (ii′) = (ii)) |
| Semanas evaluables, umbrales, señal, universos, costos, inferencia, robustez | — | Sin cambio (Adenda R, R5) |

**Recalculado de forma independiente en esta fase** (`verificaciones/ventana_tabla_completa.json`, leyendo solo `estado`):
- con la tabla completa de la Adenda 1, M1 da el mismo resultado: 2023-05-15, 158/158 semanas evaluables, mínimo 120 elegibles, último inicio válido 2023-05-29 y (iv′) = 2018;
- la tabla completa saca 5 salidas de (iv′) por ser renombres mapeados (A3.7) y suma la del LUNA viejo. Los conteos de 2022 pasan de 35 a 31 salidas en alcance, sin ninguna sin evidencia; los de 2023, de 19 a 18, con 1 sin evidencia (NBTUSDT).

---

## 3. Qué decisiones previas revierte cada una

| Decisión previa (fuente) | M0 | M1 |
|---|---|---|
| «No se relajó la regla (iv) ni se recortó la ventana histórica», registrada como **decisión expresa** (CIERRE §2) | La respeta | **La revierte**: (iv) se reemplaza por (iv′) |
| «E3 no continúa. Reabrirlo… requiere una autorización expresa» (CIERRE §2) | La respeta | **Requiere** esa autorización |
| Condición de reapertura: «una lista completa y verificable de las exclusiones y renombres de pares USDT… 2020-05 a 2026-05» (CIERRE §4) | — | **No se cumple**: la lista de exclusiones termina el 2024-11-06. La de renombres ahora está completa **solo para el período archivado** (ver la tabla completa). Adoptar M1 implica **dispensar** esta condición |
| E3-H1/H2/H3 «CERRADA · NO EVALUABLE» (`REGISTRO_HIPOTESIS_tras_cierre_E3.md`) | Se mantiene | Habría que actualizar el registro antes de ejecutar |
| (iii) de la v3 | Se aplica | **Se anula** |

---

## 4. Qué evidencia respalda cada opción

**A favor de M1:**
1. **(iv) mide el archivo web, no los datos.** Falla porque Common Crawl no tiene anuncios posteriores al 2024-11-06, no porque Vision tenga salidas truncadas.
2. **Ninguna exclusión anunciada y archivada quedó en la categoría D** (par ausente en Vision).
3. **Evidencia interna de salidas reales:** casi todas las salidas en alcance tienen vela parcial o cola de ceros (SUSPENSION y COLA_CERO, datos del propio motor del venue). La única sin evidencia es NBTUSDT, en 2023.
4. **El inicio de A no depende de R:** lo fija la (ii) de la propia v3.
5. **Recall dentro de A:**
   - el escaneo por cuerpo de las 8.028 páginas no encontró exclusiones spot USDT con fecha ≥ 2023-04-28 sin contabilizar;
   - la tabla completa de renombres verificó 107 citas;
   - con la tabla completa, la única diferencia en los criterios (a) y (b) dentro de A es HIFI, en 9 formaciones.

**A favor de M0 (no adoptar R):**
1. Es lo **congelado** y lo que decidiste expresamente el 2026-10-20.
2. **(iv′) es parcialmente circular:** certifica a Vision con marcas del propio Vision. Una truncación «limpia», sin vela parcial ni cola, no deja rastro.
3. **(ii′) no puede ver fallas posteriores al 2024-11-06.** Las fallas T, D y C se detectan con anuncios, y después de esa fecha no hay ninguno archivado.
4. **Margen de 2 semanas:** una sola falla en alcance no observada, con fecha efectiva ≥ 2023-05-29, invalida A.
5. **Fragilidad de (iv′)** (sensibilidad del informe de reparación, coherente con el recálculo):
   - con **una** salida más sin evidencia en 2023, (iv′) pasa a 2024 y A queda INVÁLIDA;
   - si los 5 casos C de 2023-09-22 se hubieran leído como no explicados, también. El texto dice lo contrario, pero es una lectura manual (A3.5).
6. **La extracción congelada tiene huecos de recall:**
   - 929 páginas con título CSS ilegible;
   - páginas de 2023 tituladas «Announcement»;
   - retiros de pares USDT de 2022–2023 (GTO, BTCST, SRM y TRIBE el 2022-11-28; KEY el 2023-02-10) que no figuran como eventos.
   - No mueven A (cualquier falla con fecha < 2023-05-08 cae antes del inicio), pero muestran que la conciliación no es exhaustiva.

**M2:** no hay evidencia disponible con las fuentes permitidas.

**M3:** no requiere evidencia nueva.

---

## 5. Riesgos de sesgo, selección y fuga de información

| Riesgo | M0 | M1 |
|---|---|---|
| **Supervivencia** (salidas truncadas tratadas como reales) | Controlado por (iv), pero ese control es inaplicable con el archivo disponible: el experimento no corre | Acotado al 10 %/año en alcance y medido por R6 (−30 % en cada liquidación contable); no eliminado. El punto ciego después del 2024-11-06 es real |
| **Regla elegida después de ver su consecuencia** | No | **Sí, en el criterio de validez**: R se escribió después de que (iv) diera INVÁLIDO. Se conocían los conteos por año y que había «242 de 279» filas inválidas en el borde. Se congeló 87 s antes de ejecutar P0, con los scripts de P0b y R1′ ya escritos (`REGISTRO_P0.txt`). No hay prueba de que se viera P0 antes de congelar, ni forma de excluirlo |
| **Fuga de información sobre el resultado** (H1/H2) | Ninguna | **Ninguna demostrable**: en los artefactos de E3, E3R, la reparación, la revisión y este cierre no hay ningún retorno de estrategia, IC, exceso ni prueba con datos reales. R decide **si** la prueba corre, no **qué** da. F3 sí usó precios para la calidad (saltos de precio en los cortes), pero no retornos de estrategia |
| **Selección de la muestra** | — | La ventana 2023-05-15…2026-05-18 sale de reglas (la (ii) de la v3), no de una elección. El riesgo está en adoptar la regla de validez condicionado a que M0 no corre |
| **Bifurcación de caminos** | — | Ya se descartaron explícitamente R1′ (ventana B) y R2. Cada alternativa más que se evalúe y se descarte aumenta este riesgo. Por eso la tabla de mapeos aplica solo lo que exige la Adenda 1 y deja la lectura de GTO→GFT como decisión explícita (D-1) |
| **Potencia** | — | Baja (0,35–0,56 según el informe de reparación; no la recalculé). Un INSUFICIENTE informaría poco |

---

## 6. Decisiones que requieren tu aprobación explícita

| Id | Decisión | Opciones | Qué hace el v3 |
|---|---|---|---|
| **D-A** | Reabrir E3 (CIERRE §2) | Sí / No (M3) | Exige la frase `reapertura_y_adenda_R` en la autorización |
| **D-B** | Adoptar la Adenda R con R1 literal: (ii)→(ii′), (iv)→(iv′), sin (iii) | Sí (M1) / No (M0: E3 sigue NO EVALUABLE) | Ídem |
| **D-C** | Dispensar la condición del CIERRE §4 y revertir la decisión expresa del §2 sobre (iv) | Sí / No | Ídem (la misma frase lo nombra) |
| **D-1** | **GTO→GFT, LUNA→LUNC y UST→USTC: el par USDT de X no estaba vigente en la fecha efectiva, o Y empieza ≥ 30 días después** | (a) **Lectura literal (recomendada):** la regla 1 no aplica; salida de X y listado nuevo de Y. Es lo que implementa la tabla / (b) Continuidad del activo: exige una **adenda nueva**, porque la regla mecánica de 30 días del universo congelado reiniciaría la edad | Exige la frase `D1_lectura_literal`. Si elegís (b), me detengo: es una modificación metodológica |
| D-2 | BCC → BCHABC + BCHSV (2018): bifurcación, un X y dos Y | Salida y dos listados nuevos (lectura de la tabla) / otra | Sin efecto en A |
| D-3 | Fechas de los 4 eventos de apalancados (N5, texto) frente a A3.1.5 (título) | 158 semanas (texto, conservador) / 160 semanas (título) | Fijado en la ventana A (158). Cambiarlo exige otra ventana |
| D-4 | Política de reintento tras un ERROR técnico | La implementada: solo antes de los estadísticos, con autorización nueva que cite el ERROR / ninguna / otra | Implementada; podés endurecerla |
| D-5 | Aceptar los riesgos residuales de §5 (punto ciego después de 2024-11-06, margen de 2 semanas, fragilidad de (iv′)) | Sí / No | — |
| D-6 | Revisión humana o de un tercero antes de autorizar | Sí / No | — |
| D-7 | Autorizar la ejecución única | Sí / No | Exige FRASE + sha256 del v3 + sha256 del manifiesto + D-A/B/C + D-1 |

**Nada de esto lo decidí yo.** El v3 no puede ejecutarse sin que esas decisiones figuren por escrito en una autorización tuya, que no creé.
