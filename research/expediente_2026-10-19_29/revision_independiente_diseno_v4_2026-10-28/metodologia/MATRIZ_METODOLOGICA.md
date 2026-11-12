# Matriz metodológica E3: fuentes primarias, alternativas y decisiones pendientes

**Autor:** el mismo agente que escribió la reparación y el diseño v4. **No es independiente.**

**Fecha:** 2026-10-28.

**Rutas** (relativas al scratchpad):

| Sigla | Ruta |
|---|---|
| `E3` | `experimentos/E3_seleccion_posicion_2026-10-19` |
| `PROT` | `E3/ejecucion_E3/protocolo` |
| `E3R` | `experimentos/E3R_desbloqueo_2026-10-26` |
| `REP` | `reparacion_E3H1H2_2026-10-26` |

**Hashes (sha256, primeros 16 caracteres) de las fuentes, verificados el 2026-10-28:**

| Fuente | Hash |
|---|---|
| v3 `PROTOCOLO_E3_v3_PROPUESTO.md` | `279a865f6471afe5` |
| `CIERRE_E3.md` | `503a2e09f5325680` |
| `NOTAS_IMPLEMENTACION_v3.md` | `21c37596a487de5f` |
| `ADENDA_1_reutilizacion_de_tickers.md` | `187111a00a245162` |
| `ADENDA_3_reglas_conciliacion.md` | `47c171453d2250d3` |
| `ADENDA_R_auditoria_de_supervivencia_interna.md` | `87f60413725a8f03` |
| `CORRECCION_R1prima_alcance_por_clase.md` | `86c8fd0b0a3b2fe2` |

**Ningún retorno, IC ni estadístico de H1/H2 se calculó ni se consultó.** Solo se leyeron textos, JSON de la conciliación, listas fijas y fechas de actividad. Para el alcance de la pasada con N5 se leyeron páginas archivadas.

---

## 0. Jerarquía de las fuentes (hechos)

| Regla | Ubicación |
|---|---|
| «Si hay conflicto, prevalece este documento [la v3] sobre cualquier otro de E3» | v3 §0.2, l. 32 |
| Las notas N1–N22 «no cambian ningún umbral […] Si una nota contradijera la v3, prevalece la v3» | `NOTAS`, l. 3 |
| La Adenda 3 «**no cambia** categorías, umbrales, ventanas ni criterios. Solo fija cómo se leen los casos que la v3 deja a "la mejor lectura documentada"» | `ADENDA_3`, l. 9 |

**No existe ninguna regla de precedencia entre las notas (N5) y la Adenda 3.**

---

## 1. Reapertura de E3 y Adenda R

**Reglas originales:**

| Regla | Ubicación |
|---|---|
| «No se relajó la regla (iv) ni se recortó la ventana histórica» | `CIERRE_E3`, l. 15 |
| «**E3 no continúa.** Reabrirlo […] requiere una autorización expresa» | `CIERRE_E3`, l. 19 |
| «Haría falta una lista completa y verificable de las exclusiones y renombres de pares USDT […] entre 2020-05 y 2026-05» | `CIERRE_E3`, l. 30 |
| Inicio de H = el más tardío de (i)–(iv) | v3 §4.11, l. 283–292 |
| Fuentes alternativas no oficiales «requieren una adenda y tu autorización» | v3 §2.3, l. 135 |

**Interpretación literal:**
- E3 está cerrado y solo se reabre con tu autorización expresa.
- La condición del §4 no se cumple: no hay anuncios archivados con E posterior al 2024-11-06 (Adenda R, l. 13).

**Qué cambia la Adenda R** (`E3R`, l. 20–46): reemplaza (ii) por (ii′) (fallas **en alcance**, l. 36) y (iv) por (iv′) (evidencia interna: ANUNCIO, SUSPENSION o COLA_CERO, l. 28–32 y 37), y deja de aplicar (iii) (l. 38).

**Alternativas:**

| Alternativa | Qué implica |
|---|---|
| (a) No reabrir | E3 sigue NO EVALUABLE |
| (b) Reabrir y adoptar la Adenda R tal como está | Hay que revertir expresamente el CIERRE §2 en lo que toca a (iv) y dispensar el §4 |
| (c) Reabrir con la Adenda R más salvaguardas | Una adenda nueva, congelada antes de cualquier resultado. Por ejemplo, evidencia externa de exclusiones posteriores al 2024-11-06 (v3 §2.3, l. 135) |

**Evidencia a favor de la Adenda R** (`E3R` §1, l. 7–19):
- (iv) falló por la cobertura del archivo web, no porque Vision esté incompleto;
- 228 pares dejan de tener archivos antes de 2026-05;
- ninguna exclusión archivada quedó en D.

El orden de congelación es verificable:
- la Adenda R se congeló a las 19:43:13Z (`CONGELACION_ADENDA_R.txt`);
- P0 se calculó a las 19:44:40Z (`REGISTRO_P0.txt`);
- el registro de la sesión no muestra cálculos con las marcas de R antes de la congelación (revisión adversarial, M-6). Esto es **inferido**: el registro lo genera el mismo entorno.

**Evidencia en contra:**
- La Adenda R se escribió conociendo que M0 fallaba y los conteos de salidas por año (§5, l. 68–71).
- (iv′) certifica a Vision con marcas de Vision.
- No hay observación posterior al 2024-11-06.
- **Su propia premisa es incorrecta** (§1, l. 17): afirma que las 4 fallas T (DOTUP, DOTDOWN, TRXDOWN y BKRW) no pueden entrar en un universo «por las listas fijas de §4.5». La R1 literal las deja en alcance (punto 2), y BKRW no está en la lista fija de §4.5 (v3, l. 233–236).

**Consecuencias, siempre con la primera pasada:**
- (a): no hay prueba;
- (b) con R1 literal: P0 oficial = **VÁLIDO, inicio 2023-05-01, 160/160** (`E3R/P0_resultado.json`);
- (b) con R1′: inicio 2021-02-22, 274/274 (`E3R/P0_resultado_R1prima.json`).

**¿Hace falta una regla nueva?** Sí, para (b): una dispensa escrita. Para (c): una adenda.

**Te corresponde:** reabrir o no; adoptar la Adenda R o no; dispensar o no el CIERRE §4.

---

## 2. R1 literal frente a R1 por clase (R1′)

**Reglas originales:**

| Regla | Ubicación |
|---|---|
| R1: fuera de alcance si el par figura en `lista_fija` o `apalancados` de las listas fijas de F3 del último lunes ≤ L (o ≤ E). Fundamento: «esos pares nunca son elegibles (§4.5)» | `ADENDA_R`, l. 22–26 |
| Tokens apalancados = X + {UP, DOWN, BULL, BEAR}. «La lista se congela en F3» | v3 §4.5, l. 238 |

**Hechos verificados:**
- Las listas por lunes de F3 marcan como apalancados solo 2 o 3 tokens: los que superaron los demás filtros. TRXDOWN, DOTUP, DOTDOWN y LINKUP no figuran en los lunes 2023-04-24 ni 2023-05-08.
- **Cronología** (fechas de modificación de los archivos y registros de congelación):

| Hora (2026-10-26, UTC) | Hecho |
|---|---|
| 19:44:41 | P0 |
| 19:46:10 | `P0d_potencia` |
| 19:46:53 | `CORRECCION_R1prima…md` |
| 19:46:57 | Congelación de R1′ |
| 19:47:23 | `P0_resultado_R1prima.json` |

- **R1′ se escribió después de ver P0**, y su propio texto la motiva por la potencia: «la ventana más larga casi duplica la información de H1»; «sienta el precedente de corregir una regla después de ver qué hace con la ventana».

**Interpretación literal:** se usan las listas por lunes. Los apalancados que no eran candidatos quedan en alcance y fijan (ii′).

**Alternativa:** pertenencia por clase (R1′), según el fundamento escrito en la propia R1 y la premisa de §1.

**Evidencia:**
- *A favor de la literal:* es el texto congelado, y la R1′ es posterior y está motivada por la potencia.
- *A favor de la R1′:* la intención escrita de la R1 y de la Adenda R §1.
- *En ambos casos:* **BKRW sigue en alcance**, porque no está en la lista fija de §4.5.

**Consecuencias:**
- R1 literal: el inicio lo fijan las fallas de apalancados de 2023-04/05;
- R1′: lo fija BKRWUSDT (T, E 2021-02-19), con inicio 2021-02-22. Esto es de P0 sobre la primera pasada, **no se recalculó** con la segunda.

**¿Hace falta una regla nueva?** Elegir R1′ es adoptar una regla posterior a P0. El riesgo de precedente está declarado en su propio texto.

**Te corresponde:** elegir R1 literal o R1′.

---

## 3. A3.1.5 frente a N5 (fecha efectiva)

**Reglas originales:**

| Regla | Ubicación |
|---|---|
| N5: «E = el día UTC en que cesa la negociación spot del par, según el texto» | `NOTAS`, l. 16 |
| A3.1.5: «**Fecha efectiva E** (N5): la primera fecha del título; si no hay, la primera fecha de una oración del cuerpo…» | `ADENDA_3`, l. 18–20 |
| La Adenda 3 «no cambia […] criterios» | `ADENDA_3`, l. 9 |
| Categoría E (ambiguo): «se resuelve con la mejor lectura documentada» | v3 §2.3, l. 119 |

**Hecho verificado:** cuando un anuncio se publica antes del cese, A3.1.5 da la fecha de publicación y N5 da la de cese. **A3 se presenta como implementación de N5, pero en esos casos la contradice.**

**Interpretaciones:**

| | Lectura | Fundamento |
|---|---|---|
| (I) | A3.1.5 es la regla operativa. E es la del título, salvo los casos corregidos por las listas de A3.11 | Es más específica y posterior |
| (II) | N5 es la definición y A3.1.5 una aproximación. Hay que corregir **todos** los casos en que difieren | — |
| (III) | No hay precedencia entre las notas y la adenda | Hace falta una regla explícita |

**Alcance de una pasada completa con N5** (medido, no ejecutado: `alcance_pasada_N5.json`, script `alcance_pasada_N5.py`):
- 55 entradas de la primera pasada;
- en **30** el cuerpo tiene una fecha de cese distinta de E: 20 A, 4 T, 1 B y 5 C;
- de ellas, 15 son de 2023–2024 y tienen en el cuerpo fechas **posteriores** a E, de semanas o meses (YFII; BTS, PERL y WTC; ANT, MULTI y XMR; BOND, DOCK, MDX y POLS; KP3R, OOKI y UNFI).

Si alguna de esas fechas se leyera como el cese, la salida pasaría de A a B o T, y una T en alcance posterior a 2023-05 dejaría la ventana en < 156 semanas.

Por eso el protocolo de lectura (qué oración cuenta como cese de la negociación spot y qué se excluye: Convert, retiros, margen o futuros) **tiene que congelarse antes de la pasada**.

**Consecuencias:**
- (I): inicio 2023-05-01, 160 semanas. Es el P0 oficial, si los demás puntos se resuelven de forma estricta.
- (II): inicio ≥ 2023-05-15, solo determinable después de la pasada completa; puede resultar INVÁLIDO.

**¿Hace falta una regla nueva?** Sí: una cláusula de precedencia entre N5 y A3.1.5 y un protocolo de lectura.

**Te corresponde:** elegir (I) o (II). Si elegís (II), la regla se aplica a los 55 eventos y a cualquier evento agregado (punto 5), no a 4.

---

## 4. Correcciones fuera de A3.11 y discrepancias de V-S3

**Reglas originales:**

| Regla | Ubicación |
|---|---|
| Listas de revisión: casos E, todos los C, los D de A3.3.3, los desaciertos de V-S2, la muestra de V-S3 y los candidatos de renombre | `ADENDA_3` A3.11, l. 89 |
| «Se revisan todos los casos de cada lista, sin seleccionar» | `ADENDA_3` A3.11, l. 90 |
| «Su resultado es el definitivo» | `ADENDA_3` A3.11, l. 91 |
| «E corregida» solo para casos C | A3.5 (a), l. 50 |
| Para V-S2: «se usa la lectura corregida y se informa» | A3.6, l. 60 |
| Para V-S3: solo «se comparan a mano», sin consecuencia | A3.6, l. 62 |

**Hechos verificados** (`REP/segunda_pasada/resoluciones_manuales.json`, sección `vs3`):
- DOTUP: `muestra_pasada1: true`;
- DOTDOWN, TRXDOWN y LINKUP: `muestra_pasada1: false`;
- los cuatro: `fecha_corregida`.

**Interpretación literal:** solo se corrige lo que está en las listas y con una consecuencia prevista. **Ninguna de las 4 correcciones está prevista en el texto.**

**Alternativas:**

| Alternativa | Qué corrige | Resultado (R1 literal) |
|---|---|---|
| (a) Estricta | Nada | 2023-05-01, 160 semanas |
| (b) Admitir correcciones en V-S3 | Solo DOTUP, E 2023-05-10 | 2023-05-15, 158 semanas |
| (c) Corregir cualquier evento detectado | — | Equivale al punto 3 (II), con pasada universal |

**¿Hace falta una regla nueva?** Sí, para (b) o (c).

**Te corresponde:** elegir (a), (b) o (c).

---

## 5. Eventos omitidos por la extracción

**Reglas originales:**

| Regla | Ubicación |
|---|---|
| Universo de anuncios = «todas las exclusiones o remociones que afectan un par spot contra USDT» | v3 §2.3, l. 106–107 |
| «El código congelado no tiene mecanismo para agregarlos» | `REP/INFORME_REPARACION_E3H1H2.md`, l. 40 |

**Hechos verificados:**
- La reparación sumó TRXUP y LINKDOWN (`eventos_omitidos.json`) **solo al cálculo de la ventana**. No están en `salida_pasada2/eventos.json`.
- GTO, BTCST, SRM y TRIBE (remoción del 2022-11-28) y KEY (2023-02-10) son pares del panel, con remoción archivada, y **no figuran en ninguna pasada**.
- **La inclusión de omitidos fue selectiva: 2 de al menos 7.**

**Interpretación literal:** según la v3, que prevalece, el universo incluye todas las remociones. El procedimiento congelado no puede agregarlas. Hay contradicción entre la definición y el procedimiento.

**Alternativas:**

| Alternativa | Qué implica |
|---|---|
| (a) Excluir todos los omitidos | Procedimiento congelado |
| (b) Incluir todos los que encuentre una búsqueda sistemática definida antes de ejecutarla | Universal |
| (c) Selectiva, como hizo la reparación | **No es una regla aceptable** |

**Consecuencias:**
- Con fechas de título, TRXUP y LINKDOWN tendrían E = 2023-04-27 y no mueven el inicio (2023-05-01).
- Con N5 fijan E en 2023-05-09 y 2023-05-11, y el inicio queda ≥ 2023-05-15.
- Los de 2022–2023 (GTO y los demás) no afectan (ii′), porque son anteriores. Su efecto sobre (iv′) no se calculó.

**¿Hace falta una regla nueva?** Sí: un procedimiento de búsqueda de omitidos.

**Te corresponde:** elegir (a) o (b).

---

## 6. Continuidad: GTO→GFT, LUNA→LUNC y UST→USTC

**Reglas originales:**

| Regla | Ubicación |
|---|---|
| Listado vigente: termina «tras 30 días seguidos inactivos»; «si vuelve a cotizar, es un listado nuevo» | v3 §2.2.3, l. 97–100 |
| Renombres: «solo con un anuncio oficial […] El nuevo hereda la edad y las posiciones» | v3 §2.2.4, l. 101 |
| «Par USDT removido con el token vigente en otros pares: cuenta como salida» | v3 §2.2.5, l. 102 |
| Regla 1: «el listado vigente de X **termina** en la fecha efectiva. Y lo continúa…» | `ADENDA_1`, l. 8 |
| Regla 3: si no hay anuncio, rigen los 30 días | `ADENDA_1`, l. 10 |

**Hechos** (verificados en la revisión adversarial, citas del cuerpo):

| Caso | Hechos |
|---|---|
| GTO→GFT | GTO/USDT removido el 2022-11-28; canje 1:1 completado el 2023-02-08; GFT/USDT abierto el 2023-09-22 (298 días) |
| LUNA→LUNC | 119 días; además, el ticker LUNA se reutilizó (regla 1R) |
| UST→USTC | 301 días; está en la lista fija |

**Interpretaciones:**
- **(a) Literal:** en E ya no había un listado vigente de X (terminó por §2.2.3 y §2.2.5). Y es un listado nuevo.
- **(b) Continuidad del activo:** §2.2.4 hereda la edad sin exigir que el listado esté vigente. Choca con §2.2.3, así que es un **conflicto interno de la v3** para este caso.

**Consecuencias:**
- Solo cambia la elegibilidad temporal de GFT dentro de A. El autor estima ~21 formaciones; no lo recalculé.
- LUNC: listado nuevo con (a).
- USTC: sin efecto.

**¿Hace falta una regla nueva?** Sí: una aclaración general de «vigente» y de los huecos de 30 días o más.

**Te corresponde:** elegir (a) o (b), como regla general.

---

## 7. Política de reintentos

**Reglas originales:**

| Regla | Ubicación |
|---|---|
| «1 ejecución confirmatoria (H1 y H2)» | v3 §3.3, l. 175–176 |
| «Cualquier otra ejecución es exploratoria: se cuenta; no cambia ninguna clasificación» | v3 §3.3, l. 180–183 |

**La v3 no tiene ninguna regla de reintentos.** La C11 del orquestador v3 es una decisión de implementación.

**Interpretación literal:** un segundo intento es «otra ejecución», es decir, exploratoria. Por lo tanto: **no hay reintento confirmatorio**, que es la política (iii).

**Alternativas:**

| Política | Qué permite | Qué requiere |
|---|---|---|
| (ii) | Reintento solo después de un ERROR en «panel», antes de simular la estrategia | Una regla que diga que un intento sin simulación no es una «ejecución» |
| (i) | La implementada | Lo mismo, más aceptar el residuo de A.6 del diseño |

**Evidencia:** L-13 (un INVALIDO convertido en reintentable en el v3) y que la etapa `validez_previa` simula la estrategia.

**¿Hace falta una regla nueva?** Sí, para (i) o (ii).

**Te corresponde:** elegir (i), (ii) o (iii).

---

## 8. Riesgos residuales y potencia

**Reglas originales:**

| Regla | Ubicación |
|---|---|
| Supuestos [Hip, ninguno medido] | v3 §7.1, l. 460–465 |
| Cifras de potencia; «si la regla de supervivencia acorta H, todas las potencias bajan, y se informa cuánto» | v3 §7.2, l. 467–481 |
| H «nunca confirmación independiente» | v3 §1, l. 73 |

**Hechos, reproducidos con `potencia_analitica.py` y los supuestos de la v3 §7.1, sin datos:**
- **P0d se reproduce exactamente:** H1, IC 0,02, n = 160, α 0,025 da 0,35–0,56.
- **Dato nuevo, H2** (exceso de 10 %/año, tracking error de 25–35 %):

| Semanas | α 0,025 | α 0,05 |
|---|---|---|
| 158 | 0,07–0,10 | 0,13–0,17 |
| 274 | 0,10–0,15 | 0,16–0,23 |

- P(RESPALDADA) ≤ la menor de las dos potencias, es decir **≤ ~0,10** con una ventaja real de 10 %/año.
- Las cifras de H1 de la v3 §7.2 usan un error estándar más conservador que el que implican su n y su desvío. Es una inconsistencia menor del protocolo.

**Riesgos que no son de potencia:**
- la circularidad de (iv′);
- el punto ciego posterior al 2024-11-06;
- la fragilidad: una salida más sin evidencia en 2023 vuelve INVÁLIDA la ventana;
- el recall de renombres;
- el volumen de HIFI;
- que todo el trabajo técnico lo hizo un solo agente.

**Interpretación literal:** la v3 no exige una potencia mínima, solo que se informe.

**¿Hace falta una regla nueva?** Solo si querés un umbral mínimo de potencia. En ese caso, tiene que fijarse antes de cualquier resultado.

**Te corresponde:**
- si una ejecución con esta potencia es informativa para tu decisión;
- aceptar o no cada riesgo.

---

## Síntesis: las decisiones están anidadas

```
1. ¿Reabrir y adoptar la Adenda R?
   ── no ──▶ E3 cerrado (fin)
   ── sí ──▶ 2. ¿R1 literal o R1′?
             ── R1′ ──▶ inicio determinado por BKRW (2021-02-22 en P0).
             │          Los puntos 3–5 siguen aplicando a todos los eventos, pero solo alteran
             │          el inicio si una falla en alcance queda después de 2021-02-19.
             └─ literal ─▶ 3+4+5: ¿procedimiento congelado estricto o lectura N5 universal?
                           ── estricto ──▶ 2023-05-01, 160 semanas (P0 oficial)
                           └─ N5 universal + búsqueda de omitidos ──▶ ≥ 2023-05-15
                              (158 o menos, o INVÁLIDO), solo después de la pasada completa
6, 7 y 8 se deciden en cualquier rama.
```

**Las 158 semanas de la ventana A fijada en el v3 no salen de ninguna aplicación universal y coherente de estas reglas.** Salen de una aplicación parcial: se corrigieron 4 eventos, 3 de ellos fuera de las listas, y se agregaron 2 de al menos 7 omitidos. **Fijar esa ventana en el v4 tal como está no es defendible.**
