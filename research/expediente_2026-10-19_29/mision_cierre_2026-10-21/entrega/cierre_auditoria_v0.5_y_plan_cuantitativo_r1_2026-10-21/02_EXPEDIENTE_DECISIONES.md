# 02 — Expediente de decisiones: resolución

**Fuentes leídas íntegramente:**
- `EXPEDIENTE_DE_DECISIONES_PENDIENTES.md` (v0.5);
- `MATRIZ_DE_DECISIONES_PENDIENTES.md`, `MARCO_ESTADISTICO_VALIDADO.md` (MEC v0.2), `PLAN_DE_EVIDENCIA_SUFFICIENTE.md`,
  `DICTAMEN_METODOLOGICO_GENERAL.md` y `REGISTRO_DE_RIESGOS_DE_SESGO.md` (expediente metodológico `33ba77c1…`);
- `DISENO_ANCLA_EXTERNA.md` y `trazabilidad_T/` (v0.5).

**Categorías:**
| Categoría | Significado |
|---|---|
| **A** | Resolver ahora: técnico, reversible, especificado y autorizado. Hecho |
| **B** | Decisión técnica tomada por mí, con criterio documentado. Aplica a hipótesis **futuras** (PEC-1.0), nunca a T ni a T-MULTI |
| **C** | Requiere tu autorización. No se ejecutó; el documento está preparado |
| **D** | Requiere evidencia o un tercero. No se simuló; se define cómo obtenerla |
| **E** | No es necesario para la siguiente fase |

**Criterio de desempate** entre alternativas seguras y equivalentes: la más simple, conservadora y reproducible.

## 1. Tabla de resolución
| ID | Problema que resuelve | ¿Bloquea la fase siguiente? | Evidencia | Qué falta | Recomendación y por qué | Riesgo | Cat. | Qué hice | Si se pospone |
|---|---|---|---|---|---|---|---|---|---|
| **R-1** | Procedencia de `contraste_btc` | No: T no depende de él y P1 lo trata como NO_VERIFICADO | Productor localizado; cobertura explicada (v0.5) | Leer bytes de datos (B-4); un segundo proveedor | Mantener NO_VERIFICADO. Reproducirlo solo si un documento se apoya en él; aun así sería la misma fuente (Binance) | Ninguno si nada se apoya en él | **E** | Nada | Nada cambia |
| **R-2** | Cobertura horaria parcial | No | Causa resuelta en v0.5 (descarga desde 2019-10) | — | Aceptar y documentar | — | **A** (cerrado) | Confirmado por inspección | — |
| **R-3 / A12** | Autenticidad de T (hoy INCONCLUSO) | No para la fase nueva. Sí para cerrar T como VERIFICADO | Declaración: el `.bin` es la forma canónica y los hashes coinciden (`evidencia/C1_*`) | **Tu clave fuera de este equipo** y tu firma | Firmar y publicar `f518ac1`/`692f2b2` (D-G6) | Firmar con una clave de este equipo no daría independencia; por eso no se hizo | **C** | `documentos_para_autorizar/R3_declaracion_T/` | T sigue INCONCLUSO; no se degrada |
| **D-G6** | Verificabilidad externa de los congelados de T y T-MULTI | No | Commits locales sin publicar | Tu autorización (irreversible) | Publicar, junto con B-1 opción (a) | Exposición pública del historial | **C** | Plan en `B1_PLAN_PARCHES_Y_COMMITS.md` | Sin fecha pública verificable |
| **R-4 / B-3** | Integración real del ejecutor | No | Ejecutor aislado probado (32 pruebas; 10 de 10 mutaciones; reproducido en esta misión) | R-5, D-G4, tu autorización | No integrar en el papel de T; solo en ejecutores prospectivos nuevos, después de R-5 | Fallar abierto sin ancla (se exige fallar cerrado) | **C** | Análisis en `B3_B4_B7_*.md` | La fase prospectiva nueva no puede usar el uso único con ancla externa |
| **R-5 / B-2** | Ancla externa | Sí, para resultados prospectivos con uso único verificable | Cliente y contrato C1–C8 probados contra un doble | Elegir el servicio y su custodio | **O2** (repositorio git con rama protegida, administrado por vos) **+ O5** (OpenTimestamps) | Ver el documento §5 | **C** | `R5_ANCLA_EXTERNA.md` | Los registros siguen siendo solo locales (amenaza A-02) |
| **R-6 / A-S1** | El MEC no está validado empíricamente | **Sí:** ninguna evaluación confirmatoria debe usar la prueba sin calibrar | Diseño MEC §5; script y parámetros congelados (`28764d31…`); prueba de humo | Tu autorización explícita (estaba prohibida por una orden anterior y no está levantada) | Autorizar: 1,3–3,9 h de CPU, solo datos sintéticos | Ninguno sobre datos ni sobre T | **C** | Script listo y bloqueado; costo medido | El marco sigue «propuesto, no validado» |
| **D-S1** | Prueba primaria | Sí | MEC §1–§4; implementación nueva contrastada con E3 | — | Bootstrap-t por bloques circulares, centrado bajo H₀, ℓ = 20, B = 9999. Es la única opción del expediente con un valor p válido en principio; P (percentil) no es un valor p | Si falla la calibración, D-S3 | **B** | Implementado (`pec/inferencia.py`) y fijado en el esquema | — |
| **D-S2** | Multiplicidad | Sí | MEC §6 | — | Bonferroni α_familia/m, con la familia declarada antes. No exige simultaneidad (Holm sí) | Algo de potencia | **B** | El validador del prerregistro lo exige | — |
| **D-S3** | Regla de respaldo | Solo si falla la calibración | MEC §4.7 | — | p = máx(p_ℓ20, p_ℓ40, p_NW), también calibrada. Es válida porque el máximo de valores p válidos es válido | Pierde potencia | **B** | Implementado (`respaldo`) | — |
| **D-S4 / A8** | δ, el efecto mínimo relevante | **Sí** para la fase prospectiva y para «efecto descartado» | Tabla de años por δ y TE (`evidencia/F5_*`) | **Tu decisión económica** | No lo elijo. Criterios y procedimiento en `AS1_CALIBRACION_Y_A8_DELTA.md` | Elegirlo para desbloquear sería un sesgo | **C** | Sin δ, el sistema no deja congelar una fase prospectiva (probado) | La fase prospectiva no puede empezar |
| **D-S5** | Miradas repetidas en la fase prospectiva | Sí, para la prospectiva | MEC §7.1 | — | Gasto de α de Lan–DeMets tipo O'Brien–Fleming | Supone incrementos aproximadamente independientes (declarado) | **B** | Implementado y verificado contra valores publicados y un Monte Carlo independiente | — |
| **D-S6** | Nulo de entradas aleatorias emparejadas | No | MEC §8 | — | Solo descriptivo: no está calibrado | — | **B** | El esquema no lo admite como criterio | — |
| **D-S7** | Compuerta por resultado del desarrollo | No | MEC §9 | — | Sin compuerta por resultado; solo factibilidad (sesgo de selección) | — | **B** | — | — |
| **A1/A2** | R1 y R3 de T | No | T es NO_CANDIDATA | — | Dejarlas NO_DEFINIDO para T. Definirlas ahora sería post hoc y no cambia nada | — | **E** | Nada | — |
| **A3** | ¿La robustez veta? | No | — | — | No veta: la robustez es descriptiva (nivel 3 aparte) | Un diagnóstico mal calibrado bloquearía una ventaja real | **B** | `decision.py` la informa sin cambiar la categoría | — |
| **A4/A7** | Definiciones posteriores a la ventana | No | — | — | Permitidas, marcadas `post_hoc`, sin efecto en la candidatura (el estado actual) | — | **B** | Sin cambios | — |
| **A5** | Etapa siguiente de T | No | T NO_CANDIDATA | — | No definirla hasta que haya una candidata | — | **E** | Nada | — |
| **A6** | Combinación R1/R3 | No | — | — | «Todas» (conservadora; la mutación «alguna» se detecta) | — | **B** | Sin cambios | — |
| **A9** | ¿VERIFICADO alcanza o se exige REPRODUCIDO? | Sí, para resultados que puedan llevar a capital | — | Un reproductor independiente (D) | Para resultados **futuros**: REPRODUCIDO, hecho por otra persona o en otro entorno. Para T histórico: VERIFICADO es el máximo posible | — | **B** (la política) / **D** (el reproductor) | El esquema exige `reproduccion.exigida = REPRODUCIDO` | — |
| **A10** | Parámetros de P4 en uso real | Sí, para la integración | — | — | 0 reintentos, verificación de determinismo y un límite de tiempo explícito | Más reintentos permiten elegir el resultado | **B** | Fijado en PEC-1.0 | — |
| **A11** | Reabrir hipótesis descartadas | Sí, para H-REV-SHOCK | Registro del programa | Tu decisión (D-G5) | Por defecto **no reabrir**. Si se reabre, se lee como un intento más sobre una familia ya descartada | Multiplicidad | **C** | `pec.programa` impide iniciarla sin aprobación registrada (probado) | — |
| **A13** | Política de raíces | Sí, para R-3 y R-5 | — | Tus claves | Una clave del propietario fuera de línea; la del ancla, en la plataforma del ancla; ninguna en este equipo; rotación con solapamiento; revocación por cambio de código revisado | Una sola clave para todo es un punto único de falla | **B** (la política) / **C** (las claves) | Documentado | — |
| **A14** | Política de reproducción | Sí | `DISENO_ANCLA_EXTERNA.md` §9 | Un reproductor | Código determinista, reproductor independiente y presentar **todas** las reproducciones | Sin esto se puede elegir la reproducción favorable | **B** | El validador del prerregistro lo exige (probado) | — |
| **B-1** | Aplicar los parches y hacer commits | No para la fase nueva | Parches comprobados de nuevo (`evidencia/B7_*`) | Tu autorización | Plan exacto, con la opción (a) o (b) según D-G6 | Publicar es irreversible | **C** | `B1_PLAN_PARCHES_Y_COMMITS.md` | El verificador solo existe en ZIP |
| **B-4** | Leer datos reales | **Sí**, para cualquier evaluación | Plan de 7 controles | Tu autorización; licencias | Autorizar solo lo que declare un prerregistro congelado y anclado | Contaminación si se lee antes de congelar | **C** | Plan en `B3_B4_B7_*.md`; validador listo | No hay evaluación posible |
| **B-6** | Backtests, descargas, repetir T, dinero real | — | — | — | Siguen prohibidos | — | — | — | — |
| **B-7** | Revisión por un tercero | No para empezar; **sí** para afirmar validez | — | Un revisor independiente | Alcance y 8 preguntas preparados | Todo lo hizo el mismo autor | **D** | `B3_B4_B7_*.md` | Toda conclusión queda sin revisión independiente |
| **B-8 / D-G0** | Conservar los paquetes fuera del scratchpad | **Sí, urgente:** el scratchpad es efímero | — | Que descargues los ZIP | Descargar v0.5 y este paquete hoy | Pérdida total del trabajo | **C** | — | Riesgo de perder todo |
| **D-G1** | Seguir con cada hipótesis | Sí | Criba de detectabilidad (05 §6) | Tu decisión | H-REV-SHOCK v0.2: **no iniciar** (no detectable y reabre una familia descartada). H-EMA9-VWAP v0.2: no iniciar salvo que aceptes de antemano «no concluyente» como resultado probable | — | **C** | Criba hecha con las cifras de las propias propuestas | — |
| **D-G2** | Camino D → E → P frente a solo P | Sí | Plan §2 | D-G1 | Si alguna sigue: **solo prospectiva**. El histórico está contaminado y solo detectaría un fracaso grueso | — | **B** (recomendación) / **C** (depende de D-G1) | — | — |
| **D-G3** | Ampliar activos o mercados | No | — | — | No por ahora: cada ampliación es otra hipótesis | — | **E** | — | — |
| **D-G4 / D-T1** | Dónde viven los registros prospectivos | **Sí**, y para el corte de T-papel del **2027-04-18** | — | La ubicación | El mismo repositorio de O2 (rama `registros`), con hash encadenado | Sin ubicación no hay corte | **C** | — | El corte de T del 2027-04-18 no tendría dónde escribirse |
| **D-G5** | Reabrir «reversión tras extremos» | Solo para H-REV-SHOCK | — | Tu decisión | No reabrir | Multiplicidad | **C** | Bloqueo en `pec.programa` | — |
| **D-T2** | Enmendar las miradas repetidas de T-papel | No | — | — | **No enmendar** (integridad del congelado); la limitación queda documentada | Error de tipo I acumulado mayor desde los 36 meses | **B** | Nada que cambiar | — |
| **D-T3** | Expectativa sobre T-papel | No | Plan §4.3 | — | Aceptar que solo detecta un efecto grande o un fracaso grueso | — | **E** | — | — |

## 2. Resumen
| Categoría | IDs |
|---|---|
| **A** | R-2 |
| **B** | D-S1, D-S2, D-S3, D-S5, D-S6, D-S7, A3, A4/A7, A6, A9 (política), A10, A13 (política), A14, D-G2 (recomendación), D-T2 |
| **C** | R-3/A12, D-G6, R-4/B-3, R-5/B-2, R-6/A-S1, D-S4/A8, A11/D-G5, A13 (claves), B-1, B-4, B-8/D-G0, D-G1, D-G4/D-T1 |
| **D** | A9 (reproductor independiente), B-7 |
| **E** | R-1, A1/A2, A5, D-G3, D-T3 |

Las autorizaciones, agrupadas en una lista breve y accionable, están en `06_AUTORIZACIONES_PENDIENTES.md`.
