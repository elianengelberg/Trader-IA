# Parte metodológica: decisiones M-1…M-7

**Alcance.** Qué reglas convendría adoptar. El revisor da su **opinión fundada**; **decide el usuario**.

**Cómo está armada cada ficha:**
- la pregunta;
- las reglas congeladas que la gobiernan, con cita;
- lo **demostrado** (hechos verificables, sujetos a la parte técnica) y lo **interpretativo**, por separado;
- las opciones y lo que implica cada una;
- el pronunciamiento que se pide.

**Pronunciamientos obligatorios:** M-1, M-2, M-3 y M-4.

**Si falta evidencia** para un pronunciamiento obligatorio, el revisor lo registra como «evidencia insuficiente» y se detiene. No completa con supuestos.

**Rutas:**
- `EV` es `evidencia/`;
- `E3` es `EV/experimentos/E3_seleccion_posicion_2026-10-19`;
- `E3R` es `EV/experimentos/E3R_desbloqueo_2026-10-26`;
- `REP` es `EV/reparacion_E3H1H2_2026-10-26`;
- `CB` es `EV/cierre_bloqueantes_E3H1H2_2026-10-27`.

---

## M-1 · Adenda R (decisiones D-A, D-B y D-C) — OBLIGATORIO

**Pregunta.** ¿Hay que reabrir E3 y adoptar la Adenda R con R1 literal? Adoptarla implica tres cosas:
- reemplaza la v3 §4.11 (ii) por (ii′) y (iv) por (iv′), y deja de aplicar (iii);
- revierte la decisión expresa del CIERRE §2 («No se relajó la regla (iv)…»);
- dispensa la condición de reapertura del CIERRE §4 («una lista completa y verificable de las exclusiones y renombres de pares USDT… entre 2020-05 y 2026-05»).

**Reglas y documentos:**

| Documento | Qué contiene |
|---|---|
| `E3/PROTOCOLO_E3_v3_PROPUESTO.md` §2.3 y §4.11 | (i)–(iv) e INVÁLIDO con < 156 semanas evaluables |
| `E3/CIERRE_E3.md` §1, §2 y §4 | Cierre, decisión expresa sobre (iv) y condición de reapertura |
| `E3R/ADENDA_R_auditoria_de_supervivencia_interna.md` | R1–R5. §5: lo que el autor de R conocía al escribirla, y que adoptar R es «categoría B» |
| `E3R/CONGELACION_ADENDA_R.txt` y `E3R/REGISTRO_P0.txt` | Congelación a las 19:43:13Z; P0 a las 19:44:40Z; scripts de P0b y R1′ ya existentes |
| `REP/ventana_A/ventana_A_pasada2.json` | Componentes y conteos por año |
| `CB/verificaciones/ventana_tabla_completa.json` | Recálculo con la tabla completa |
| `CB/metodologia/COMPARACION_METODOLOGICA.md` | Comparación del autor; leerla críticamente |

**Demostrado** (sujeto a T-1, T-7 y T-6):
- **Con la v3 pura (M0) no hay ventana válida:** (iv) falla en todos los años (2025: 51/51 salidas sin anuncio; 2026: 26/26), porque el archivo web termina el 2024-11-06.
- **Con R y R1 literal:** inicio 2023-05-15 (lo fija (ii′) = (ii) de la propia v3), 158/158 semanas evaluables, mínimo 120 elegibles, último inicio válido 2023-05-29 (margen de 2 semanas), (iv′) = 2018.
- **En los artefactos no hay ningún retorno de estrategia, IC ni prueba con datos reales.**
- **Fragilidad**, según la sensibilidad de `REP/INFORME_REPARACION_E3H1H2.md` §3:
  - con una salida más sin evidencia en 2023, (iv′) pasa a 2024 → INVÁLIDO;
  - si los 5 casos C del 2023-09-22 se leyeran como no explicados → INVÁLIDO.

**Interpretativo** (lo que el revisor tiene que juzgar):
1. ¿R **corrige** un criterio que medía el archivo y no los datos, o **relaja** ad hoc un criterio congelado porque impedía correr la prueba?
2. ¿Cuánto pesa que R se haya escrito **después** de ver que M0 no corre, conociendo los conteos por año y que había «242 de 279» filas inválidas en el borde? El orden de congelación y ejecución de P0 no permite probar ni excluir que se viera P0 antes.
3. **Circularidad de (iv′):** certifica a Vision con marcas del propio Vision (vela parcial o cola de ceros). Una truncación sin rastro es indetectable.
4. **Punto ciego de (ii′):** las fallas posteriores al 2024-11-06 no son observables, y una sola en alcance con fecha ≥ 2023-05-29 invalidaría A.
5. ¿R1 literal (más conservadora, con los apalancados en alcance) frente a R1′ (por clase; ya descartada porque alarga la ventana y se eligió después de ver P0)?

**Opciones:**

| Opción | Qué implica |
|---|---|
| (1) No adoptar R | E3 sigue CERRADO · NO EVALUABLE (M3 del documento del autor) |
| (2) Adoptar R tal como está | Requiere autorización expresa de D-A, D-B y D-C |
| (3) Adoptar R con salvaguardas adicionales | Por ejemplo: evidencia externa de exclusiones posteriores al 2024-11-06 o análisis de sensibilidad preespecificados. Requiere una **adenda nueva**, congelada antes de cualquier resultado |
| (4) Otra que el revisor fundamente | — |

**Se pide:** opción recomendada y fundamento; opinión sobre los puntos 1–5; si el revisor considera que la evidencia alcanza para decidir.

---

## M-2 · GTO→GFT, LUNA→LUNC y UST→USTC (decisión D-1) — OBLIGATORIO

**Pregunta.** La regla 1 de la Adenda 1 («el listado **vigente** de X termina en la fecha efectiva. Y lo continúa con la relación de canje, y hereda la edad y las posiciones») ¿se aplica cuando el par USDT de X **no estaba vigente** en la fecha efectiva, o cuando Y empieza a cotizar ≥ 30 días después?

**Reglas:**
- `E3/ejecucion_E3/protocolo/ADENDA_1_reutilizacion_de_tickers.md` (reglas 1–4);
- v3 §2.2.3 (30 días de inactividad: listado nuevo);
- §4.10 (salida con liquidación contable).

**Demostrado** (sujeto a T-3), con citas en `CB/tabla/TABLA_RENOMBRES_COMPLETA.md`, entradas T062, T065 y T075:
- **GTO/USDT se retiró por anuncio** el 2022-11-28 03:00 UTC. El último día activo de GTOUSDT es el 2022-11-27.
- **El canje GTO→GFT es posterior:** calendario desde el 2023-01-18, completado con «1 GTO = 1 GFT».
- **GFT/USDT abrió el 2023-09-22**, 298 días sin par USDT.
- **LUNA viejo → LUNC:** el último día del LUNA viejo en LUNAUSDT es el 2022-05-12; LUNCUSDT empieza el 2022-09-09 (119 días).
- **UST → USTC:** 2022-05-12 → 2023-03-10 (301 días). UST y USTC están en la lista fija (§4.5): sin efecto.
- **Implementación:** el universo congelado reinicia la edad después de 30 días inactivos. Con el v3, una «continuidad» a través de esos huecos no transmitiría la edad sin una regla nueva; el v3 rechaza explícitamente la regla 1 con hueco ≥ 30 días.
- **Efecto en A, solo GFT**: con (a), la edad de GFTUSDT se cumple hacia 2024-03; con (b), hacia 2023-10, hasta ~21 formaciones antes. No se evaluó si GFT cumple el volumen mínimo.

**Opciones:**

| Opción | Qué implica |
|---|---|
| **(a) Lectura literal** | La regla 1 no aplica porque falta su premisa: salida de X (retiro de par, §4.10) y listado nuevo de Y. **Es lo que implementan la tabla y el v3**, que exige que la autorización contenga la frase de D-1 |
| **(b) Continuidad del activo** | Requiere una **regla nueva** (adenda) que permita heredar la edad a través de un hueco ≥ 30 días |

**Interpretativo:** ¿la opción (a) aplica las reglas generales (que el autor sostiene) o es en sí una regla nueva? ¿Hay algún caso intermedio (hueco < 30 días con el par de X ya retirado) que la tabla no contemple?

**Se pide:** opción recomendada y fundamento; si hace falta una adenda aclaratoria aunque se elija (a).

---

## M-3 · 158 frente a 160 semanas (decisión D-3) — OBLIGATORIO

**Pregunta.** Para los eventos de tokens apalancados de abril y mayo de 2023 (TRXDOWN, DOTUP, DOTDOWN y LINKUP), ¿la fecha efectiva es la del **título** de la página (2023-04-27, regla de extracción A3.1.5) o la del **cuerpo** (2023-05-09, 10 y 11, nota N5: «el día UTC en que cesa la negociación spot del par, según el texto»)?

**Reglas:**
- `E3/ejecucion_E3/protocolo/ADENDA_3_reglas_conciliacion.md` A3.1.5, A3.5 (a) («E corregida según el texto», prevista para los casos C) y A3.11 (qué listas se revisan a mano);
- `E3/ejecucion_E3/protocolo/NOTAS_IMPLEMENTACION_v3.md` N5.

**Demostrado** (sujeto a T-1):
- `REP/segunda_pasada/resoluciones_manuales.json` marca los 4 eventos como `fecha_corregida`, con cita del cuerpo. En la primera pasada eran T (3) y B (1, LINKUP).

**Variantes:**

| Variante | Inicio | Semanas | Margen hasta el último inicio válido (2023-05-29) | Veredicto |
|---|---|---|---|---|
| Fecha del cuerpo (N5), adoptada | 2023-05-15 | 158 | 2 semanas | VÁLIDO |
| Fecha del título (A3.1.5) | 2023-05-01 | 160 | 4 semanas | VÁLIDO |

Las cifras salen de `REP/INFORME_REPARACION_E3H1H2.md` §3 y de los archivos de ventana; verificarlas.

**Interpretativo:**
1. ¿A3.11 autoriza una corrección manual de fecha para eventos T o B, que no figuran en las listas de A3.11.1? ¿O A3.5 (a) se limita a los casos C?
2. N5 (nota de implementación) frente a A3.1.5 (adenda de reglas de lectura): ¿cuál prevalece?
3. La variante de 158 semanas es «conservadora» en el sentido de dejar fuera más período alrededor de las fallas, pero reduce el margen y la potencia. ¿Qué criterio debe primar?
4. Se eligió entre dos variantes válidas **sin ver resultados**, pero la elección se hizo en la reparación, no antes. ¿Es una bifurcación relevante?

**Se pide:** variante recomendada y fundamento. Cambiar a 160 semanas exige otra ventana fijada por hash, es decir, un v3 nuevo.

---

## M-4 · Riesgos residuales (decisión D-5) — OBLIGATORIO

**Pregunta.** ¿Son aceptables los riesgos residuales para una ejecución confirmatoria única? ¿Hacen falta salvaguardas adicionales antes de autorizar?

**Riesgos declarados:**
1. **Punto ciego posterior al 2024-11-06:** fallas T, D o C no observables.
2. **Circularidad de (iv′).**
3. **Fragilidad** de (iv′) y de la lectura de los 5 casos C (ver M-1).
4. **Margen de 2 semanas** (4 con la variante de 160).
5. **Recall incompleto de la extracción congelada:**
   - 929 páginas con título ilegible;
   - páginas de 2023 tituladas «Announcement»;
   - retiros USDT de 2022–2023 que no figuran como eventos (GTO, BTCST, SRM, TRIBE, KEY…). Según el autor, no mueven A.
6. **Cambios de símbolo sin anuncio archivado**, tratados con la regla 3 como salida más listado nuevo:
   - dentro del período archivado: TOMO→VIC, GAL→G, RNDR→RENDER, KLAY→KAIA y AGIX/OCEAN→FET;
   - posteriores: DAR, FTM, EOS, MKR, FXS y OM.
7. **Cortes de 1 día sin anuncio dentro de A** (SCR, USUAL, AXS): una redenominación con |log₁₀ r| < 1 no se detectaría.
8. **Mapeos de certeza media dentro de A:** COCOS→COMBO, TVK→VANRY y MFT→HIFI. Solo está archivado el anuncio de finalización, así que E es la fecha de ese anuncio.
9. **HIFI:** no se sabe si cumple el volumen mínimo en las 9 formaciones afectadas.
10. **Potencia baja** (0,35–0,56; `E3R/P0d_potencia_H1_segun_ventana.txt` y `REP/INFORME_REPARACION_E3H1H2.md`): un resultado INSUFICIENTE es probable y poco informativo.
11. **Todo el trabajo técnico lo hizo un solo agente.**
12. **Fallo del registro de intentos después de escribir un resultado terminal** (`05_LIMITES…`, L-13; se detectó al preparar este paquete y no se corrigió): puede destruir un EVALUADO o volver reintentable un INVALIDO. La implementación se juzga en T-5; acá se pide si el riesgo es aceptable.
13. **Las frases de decisión del v3 no exigen pronunciamiento sobre D-3, D-4 ni D-5** (`05_LIMITES…`, L-17).
14. **El v1 y el v2 siguen siendo ejecutables** con sus frases, que figuran en documentos congelados, y sin un registro de intentos compartido con el v3 (`05_LIMITES…`, L-25).

**Se pide**, para cada riesgo: aceptable, aceptable con salvaguarda (cuál), o inaceptable. Si se recomiendan salvaguardas que cambian lo que se ejecuta o se informa, indicar que requieren una adenda congelada antes de la ejecución.

---

## M-5 · Política de reintentos como regla de gobierno (D-4)

**Implementación:** ver T-5.

**Pregunta.** ¿Debe existir algún reintento después de un ERROR técnico?

**Hecho a considerar:** la etapa «validez_previa», que la política trata como «sin estadísticos», **simula la estrategia en memoria** (`motor.simular`) para comprobar la invariancia al truncar. No expone retornos, pero los calcula.

**Opciones:**

| Opción | Qué implica |
|---|---|
| (i) La implementada | Reintento solo si el ERROR ocurrió en «panel» o «validez_previa», con autorización nueva que cite el ERROR |
| (ii) Reintento solo si el ERROR ocurrió en «panel» | Antes de cualquier simulación |
| (iii) Ningún reintento | Un ERROR termina E3 como «SIN RESULTADO» |
| (iv) Otra | — |

Cualquier cambio exige un v3 nuevo, con hash nuevo.

**Se pide:** opción recomendada.

---

## M-6 · Metodología estadística

**Pregunta.** ¿La inferencia prerregistrada es adecuada para la decisión que se pretende tomar?

**Documentos:**
- `E3/PROTOCOLO_E3_v3_PROPUESTO.md`: H1, H2, Holm, clasificación §6 y robustez;
- `E3/ejecucion_E3/protocolo/ENMIENDA_2_fuente_archivada_inferencia_motor.md` y `NOTAS_IMPLEMENTACION_v3.md` (N13, N14, N17, N18…);
- `E3/ejecucion_E3/resultados/calibracion/DECISION_CALIBRACION.txt` y `calibracion*.json`;
- `E3R/P0d_potencia_H1_segun_ventana.txt`;
- el código de cálculo del v3, idéntico al del v2 (`ejecutar`, `p_h2`, `contribuciones`, `sharpe_deflactado`).

**Puntos a examinar:**
- **H1:** IC semanal de Spearman con Newey–West, L = 4, unilateral.
- **H2:** k = 6 frente a EW-U30, p₂ = máx(p_boot ℓ13, p_boot ℓ26, p_NW 13), IC90 como envolvente.
- **Holm** con m = 2.
- **Robustez:** R1–R6, con R4 contra el EW **bruto** (N14).
- **Sharpe deflactado:** N = 20.
- **Potencia** en 158 semanas.
- **Lectura del resultado:** «evidencia histórica con contaminación declarada» (v3 §1 y §7.3).

**Interpretativo:**
- ¿Esa inferencia es válida con series semanales autocorrelacionadas y universos que cambian?
- ¿La regla del máximo es conservadora?
- ¿La potencia justifica correr la prueba, o un INSUFICIENTE probable no la justifica?

**Se pide:** opinión. Cambiar la inferencia es una modificación metodológica que solo puede hacerse con una adenda congelada antes de cualquier resultado.

---

## M-7 · Bifurcación BCC → BCHABC + BCHSV (D-2, menor)

**Demostrado:** en 2018, BCC se reemplazó por dos activos, 1:1 cada uno (entrada T de la tabla con su cita).

**Tratamiento del autor:** no es un renombre, porque la regla 1 presupone un único Y. Se trata como salida de BCC y dos listados nuevos. **Sin efecto en A.**

**Se pide:** conformidad o una alternativa fundada.
