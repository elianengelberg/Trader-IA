# Verificación adversarial de la matriz metodológica E3

**Quién verifica.** Soy un agente separado, de la misma familia de modelos que el autor, lanzado por el autor y corriendo en el mismo contenedor. No soy una revisión humana ni una organización distinta. No comparto su contexto: partí del documento y de las fuentes primarias.

**Documento verificado:** `revision_independiente_diseno_v4_2026-10-28/metodologia/MATRIZ_METODOLOGICA.md`, 367 líneas, sha256 `825f141e9a392ad6c659493a60dcc20fd9d956d70dbd52a9e9e2f0d9c44ed207`. Lo registré al empezar y volví a calcularlo al terminar: no cambió.

**Límites que respeté.** No abrí `.npz` ni ZIP. No ejecuté orquestadores de E3, scripts de conciliación ni de cálculo de ventanas. No calculé retornos. No abrí `revisor/` ni nada bajo `/root/.claude/`. Solo escribí en `verificacion_matriz/`. Re-ejecuté `alcance_pasada_N5.py` y `potencia_analitica.py` (venv, `-B -I`) con la salida en mi carpeta. Lo demás fue leer texto y JSON con `grep`, `sed`, `sha256sum`, `stat` y `python3`.

**Convenciones.** Las rutas son relativas al scratchpad. `R1`…`R11` son archivos de `registro/` (índice al final). Número de línea de la matriz entre paréntesis. «Reparo» significa que el hecho es cierto pero hay algo que el lector necesita saber.

---

## 1. Tabla de afirmaciones

| ID | Matriz | Afirmación | Veredicto | Evidencia |
|---|---|---|---|---|
| V01 | l.16–26 | sha256 (16 car.) de las 7 fuentes | **CONFIRMADA** | `sha256sum` de las 7: coinciden 7/7 (R1, bloque «sha256»). La fecha «verificados el 2026-10-28» no se puede comprobar; sí que hoy coinciden. |
| V02 | l.9–14 | Siglas `E3`, `PROT`, `E3R`, `REP` | **CONFIRMADA** | Existen las cuatro carpetas. El v3 está en `E3/`, no en `PROT/` (la matriz no dice lo contrario). |
| V03 | l.28 | «Ningún retorno, IC ni estadístico de H1/H2 se calculó ni se consultó» | **NO VERIFICABLE** | Es una negativa sobre todo el proceso. Solo comprobé que los dos scripts no leen series ni precios (leí el código) y que sus salidas no tienen retornos. |
| V04 | l.28 | Para el alcance N5 «se leyeron páginas archivadas» | **CONFIRMADA** | `alcance_pasada_N5.py` l.19–35 lee `paginas/*.json`, `eventos.json` y `anuncios_clasificados.json`. |
| V05 | l.36 | v3 §0.2, l.32: «prevalece este documento sobre cualquier otro de E3» | **CONFIRMADA** | `grep -n` → l.32 (R1). |
| V06 | l.37 | NOTAS l.3: «no cambian ningún umbral […] prevalece la v3» | **CONFIRMADA** | R1, NOTAS l.3. |
| V07 | l.38 y l.147 | ADENDA_3 **l.9**: «no cambia categorías, umbrales, ventanas ni criterios…» | **REFUTADA** | El texto es exacto, pero está en la **l.8**; la l.9 está en blanco (R1: `A3 8:**Qué no cambia:**…`). Error de número de línea, aparece dos veces. |
| V08 | l.40 | «No existe ninguna regla de precedencia entre las notas (N5) y la Adenda 3» | **CONFIRMADA** | `grep` de «preceden/prevalec/jerarqu/rige…» en `PROT/` solo da NOTAS l.3 y ADENDA_1 l.10 (R8 §1). Hay indicios textuales que la matriz no cita: ver (c)-1. |
| V09 | l.50 | CIERRE l.15: «No se relajó la regla (iv) ni se recortó la ventana histórica» | **CONFIRMADA** | R1. Es un registro de lo que no se hizo (título del §2: «Qué NO se hizo»), no una regla: ver (a)-9. |
| V10 | l.51 | CIERRE l.19: «E3 no continúa. Reabrirlo […] requiere una autorización expresa» | **CONFIRMADA** | R1. |
| V11 | l.52 | CIERRE l.30: lista completa de exclusiones y renombres 2020-05 a 2026-05 | **CONFIRMADA** | R1. |
| V12 | l.53 | v3 §4.11, l.283–292: inicio de H = el más tardío de (i)–(iv) | **CONFIRMADA** | R1: l.283 encabezado, l.287 «Inicio de H», l.292 INVÁLIDO. |
| V13 | l.54 | v3 §2.3, l.135: fuentes no oficiales «requieren una adenda y tu autorización» | **CONFIRMADA** | R1, l.135. |
| V14 | l.58 | No hay anuncios archivados con E posterior al 2024-11-06 (Adenda R l.13) | **CONFIRMADA** | R1, ADENDA_R l.13; CIERRE l.10 dice lo mismo. |
| V15 | l.60 | Qué cambia la Adenda R: (ii′) l.36, (iv′) l.28–32 y 37, (iii) l.38 | **CONFIRMADA** | R1, ADENDA_R l.36–38; la regla R2 de la Adenda (evidencia interna) está en l.28–32. |
| V16 | l.70–73 | Evidencia a favor: (iv) falló por el archivo web; 228 pares; ninguna en D | **CONFIRMADA** | ADENDA_R l.13, 15, 16 (R1). |
| V17 | l.76 | Adenda R congelada a las 19:43:13Z | **CONFIRMADA** | `CONGELACION_ADENDA_R.txt`: `2026-10-26T19:43:13.957Z`. |
| V18 | l.77 | P0 calculado a las 19:44:40Z (`REGISTRO_P0.txt`) | **CONFIRMADA** | `REGISTRO_P0.txt` dice `19:44:40.432Z`; `p0_auditoria_interna.py` mtime 19:44:39.460; `P0_resultado.json` mtime 19:44:41.632 (R2 §2). **Reparo:** `REGISTRO_P0.txt` tiene mtime 19:47:23.061 y lista el hash de dos scripts posteriores; ver (a)-3. |
| V19 | l.78 | «El registro de la sesión no muestra cálculos con marcas de R antes de la congelación (M-6)» | **NO VERIFICABLE** | El registro de sesión no está a mi alcance. La atribución es exacta: M-6 dice «no muestra ningún cálculo con marcas de R antes de las 19:43:09Z» (`revision_adversarial…/INFORME…`, detalle de M-6). M-6 habla de P0 a las 19:44:38Z; la matriz, de 19:44:40Z. |
| V20 | l.81 | La Adenda R se escribió conociendo «que M0 fallaba» y los conteos por año (§5, l.68–71) | **CONFIRMADA** | ADENDA_R l.68–71: «cuentas de salidas por año», «242 de 279» (R1). «M0» no está definido en la matriz (en `COMPARACION_METODOLOGICA` es «no adoptar R»); que (iv) fallaba figura en CIERRE l.9–11. |
| V21 | l.82 | «(iv′) certifica a Vision con marcas de Vision» | **CONFIRMADA** | P0 oficial, suma de años: 220 salidas en alcance, 219 con SUSPENSION, 1 con COLA_CERO y 32 con ANUNCIO (R2 §5). La evidencia es casi toda interna. La Adenda R (l.30) sostiene que una truncación no produce esa fila; es un juicio. |
| V22 | l.83 | No hay observación posterior al 2024-11-06 | **CONFIRMADA** | Igual que V14. |
| V23 | l.84 | La premisa de ADENDA_R l.17 es incorrecta: las 4 fallas T quedan en alcance con R1 literal y BKRW no está en la lista fija (v3 l.233–236) | **CONFIRMADA** | ADENDA_R l.17 (cita exacta). `P0_resultado.json`: las 4 `en_alcance: true` (R2 §1). v3: `grep -c BKRW` = 0 (R1). **Reparo:** (a)-4 y (b)-1. |
| V24 | l.88 | R1 literal: VÁLIDO, 2023-05-01, 160/160 | **CONFIRMADA** | R2 §1. |
| V25 | l.89 | R1′: 2021-02-22, 274/274 | **CONFIRMADA** | R2 §1. |
| V26 | l.103 | R1, ADENDA_R l.22–26, y «esos pares nunca son elegibles (§4.5)» | **CONFIRMADA** | R1: l.22 y l.26. |
| V27 | l.104 | v3 §4.5 l.238: tokens apalancados, «La lista se congela en F3» | **CONFIRMADA** | R1, l.238. |
| V28 | l.107 | Las listas por lunes marcan 2 o 3 apalancados; TRXDOWN, DOTUP, DOTDOWN y LINKUP no figuran el 2023-04-24 ni el 2023-05-08 | **CONFIRMADA** | 2023-04-24: ADADOWN, BTCDOWN, ETHDOWN. 2023-05-08: BTCDOWN, ETHDOWN (R2 §3). **Reparo:** «2 o 3» vale para esos lunes; en los 439 lunes va de 0 a 30. |
| V29 | l.110–116 | Cronología de 5 horas (19:44:41; 19:46:10; 19:46:53; 19:46:57; 19:47:23) | **CONFIRMADA** | mtimes: 19:44:41.632; 19:46:10.237; 19:46:53.865; 19:46:57.953; 19:47:23.314 (R2 §2). Son fechas de modificación, que se pueden alterar. |
| V30 | l.118 | Citas de R1′: «casi duplica la información de H1» y «sienta el precedente de corregir una regla…» | **CONFIRMADA** | CORRECCION l.22 y l.23 (R1). |
| V31 | l.118 | R1′ se escribió después de ver P0 | **CONFIRMADA** | CORRECCION l.3; mtimes de V29. |
| V32 | l.127 | BKRW sigue en alcance porque no está en la lista fija de §4.5 | **CONFIRMADA** | BKRW figura en 0 de 439 lunes en `lista_fija`, `apalancados`, `baja_volatilidad_o_duplicado` y `elegibles` (R2 §3). **Reparo:** (b)-1. |
| V33 | l.131 | R1′ lo fija BKRWUSDT (T, E 2021-02-19), inicio 2021-02-22; no se recalculó con la segunda pasada | **CONFIRMADA** | `P0_resultado_R1prima.json`: `ii_prima 2021-02-22`, `ultima_falla_en_alcance 2021-02-19`. `ventana_A_pasada2.json` solo usa R1 literal. 2021-02-19 es viernes (R2 §6). |
| V34 | l.145 | N5, NOTAS l.16: «E = el día UTC en que cesa la negociación spot del par, según el texto» | **CONFIRMADA** | R1. La cita omite sin marcar «de un anuncio» después de «Fecha efectiva E». |
| V35 | l.146 | A3.1.5, ADENDA_3 l.18–20, cita textual | **CONFIRMADA** | R1. |
| V36 | l.148 | v3 l.119: categoría E, «mejor lectura documentada» | **CONFIRMADA** | R1, l.119. |
| V37 | l.150 | «Hecho verificado»: si el anuncio se publica antes del cese, A3.1.5 da la fecha de publicación y N5 la de cese; A3 «la contradice» | **CONFIRMADA** | Solo para los 4 apalancados: el título dice «…Leveraged Tokens (2023-04-27)» (R9) y el cuerpo «2023-04-27 06:45 Fellow Binancians… At 2023-05-09/10/11» (R4). En el resto, los títulos son del tipo «Binance Will Delist … on 2023-08-22» o «Notice of Removal of Trading Pairs - 2022-10-14» (R9) y la 2.ª pasada confirmó 37 de 47 eventos como cese según el texto (`resoluciones_manuales.json`). Ver (a)-1. |
| V38 | l.161 | 55 entradas en la primera pasada | **CONFIRMADA** | Re-ejecución: `"eventos": 55` (R3). |
| V39 | l.162 | En 30 el cuerpo tiene una fecha distinta de E: 20 A, 4 T, 1 B, 5 C | **CONFIRMADA** | Re-ejecución: `con_fecha_de_cese_distinta_en_el_cuerpo: 30`, `{"A":20,"T":4,"B":1,"C_no_explicada":5}`. El JSON nuevo es idéntico al original (R2/R3). Como conteo de candidatas. |
| V40 | l.162 | Esas 30 tienen «una fecha de **cese** distinta de E» | **REFUTADA** | El script cuenta **cualquier** fecha en una oración con el patrón de exclusión. Leí esas oraciones (R4). Solo los 4 apalancados (3 T + LINKUP) dan un cese spot distinto. Los otros 26 son: Margin («Binance Margin will delist… at 2023-04-17»), Simple Earn/Auto-Invest, «Delisted tokens may be converted into stablecoins… after 2023-11-22», pares **BUSD** del 2023-09-29 (los 5 C), y fechas de barra lateral o de publicación en 2020–2022. |
| V41 | l.163 | «15 son de 2023–2024 y tienen fechas posteriores a E, de semanas o meses» (lista 14 nombres) | **REFUTADA** | La lista tiene 14 nombres y el cómputo da 14: las únicas con fecha posterior ≥ 28 días son esas, con 91–93 días de diferencia (R10). Con ≥ 14 días hay 18 y con cualquier fecha posterior, 23. No hay un subconjunto natural de 15. Además, esas fechas son de conversión a stablecoins, no de cese (R4). |
| V42 | l.165 | Si esas fechas se leyeran como cese, A pasaría a B o T, y una T «posterior a 2023-05» dejaría < 156 semanas | **NO VERIFICABLE** | Contrafáctico. El umbral exacto es E ≥ 2023-05-29 (INFORME_REPARACION l.84), no «posterior a 2023-05». Ya vimos que esas fechas no son de cese (V40). |
| V43 | l.170 | (I): 2023-05-01, 160 semanas, es el P0 oficial | **CONFIRMADA** | R2 §1 y §6 (160 lunes). Ojo: (I) tal como se define («salvo los casos corregidos por las listas de A3.11») incluiría a DOTUP; los 160 valen solo con §4(a). La matriz lo aclara con «si los demás puntos se resuelven de forma estricta». |
| V44 | l.171, l.175 | (II): inicio ≥ 2023-05-15, «solo determinable después de la pasada completa»; la regla se aplicaría a los 55 eventos, «no a 4» | **CONFIRMADA** | El valor sale de `ventana_A_pasada2.json`: 2023-05-15, 158, VÁLIDO, margen 2 (R2 §5). **Reparo:** esa «pasada completa» ya existe: INFORME_REPARACION l.31 («Se releyeron los 55 eventos») y `resoluciones_manuales.json` (47 + 8 con cita). Ver (c)-4. |
| V45 | l.185 | A3.11, l.89: listas de revisión | **CONFIRMADA** | R1. |
| V46 | l.186–187 | A3.11, l.90 y l.91 | **CONFIRMADA** | R1. |
| V47 | l.188 | A3.5 (a), l.50: «E corregida» para casos C | **CONFIRMADA** | R1. |
| V48 | l.189 | A3.6, l.60: V-S2, «se usa la lectura corregida y se informa» | **CONFIRMADA** | R1. |
| V49 | l.190 | A3.6, l.62: V-S3 solo «se comparan a mano» | **CONFIRMADA** | R1. |
| V50 | l.193–195 | `vs3`: DOTUP `muestra_pasada1: true`; DOTDOWN, TRXDOWN y LINKUP `false`; los cuatro `fecha_corregida` | **CONFIRMADA** | R2 §4. 10 muestras `true` en total; las cuatro con `E_texto` 2023-05-10, 05-10, 05-09 y 05-11. |
| V51 | l.197 | «Ninguna de las 4 correcciones está prevista en el texto» | **REFUTADA** | Para DOTUP no es cierto. DOTUP está en la muestra V-S3, que A3.11 l.89 incluye en las listas de revisión. A3.11 l.90 dice «cada caso de cada lista se resuelve con una cita del texto archivado» y l.91 «Su resultado es el definitivo». Las cuatro caen además bajo N5 (E = cese «según el texto»). Ver (c)-2. |
| V52 | l.203 | (a) Estricta: 2023-05-01, 160 | **CONFIRMADA** | V24. |
| V53 | l.204 | (b) Solo DOTUP, E 2023-05-10: 2023-05-15, 158 | **CONFIRMADA** | 2023-05-10 es miércoles; lunes siguiente 2023-05-15; 158 lunes hasta 2026-05-18 (R2 §6). Coincide con la variante (B) de M-3 del autor. |
| V54 | l.219 | v3 l.106–107: «todas las exclusiones o remociones que afectan un par spot contra USDT» | **CONFIRMADA** | La frase está en l.107; l.106 es el encabezado (R1). Dentro del rango citado. |
| V55 | l.220 | INFORME_REPARACION l.40: «El código congelado no tiene mecanismo para agregarlos» | **CONFIRMADA** | R1. |
| V56 | l.223 | TRXUP y LINKDOWN solo en el cálculo de la ventana; no están en `salida_pasada2/eventos.json` | **CONFIRMADA** | R2 §5: en pasada1 y pasada2 `False`; en `ventana_A_pasada2.json` figuran con `omitido_por_la_extraccion: true`. |
| V57 | l.224 | GTO, BTCST, SRM, TRIBE (remoción del 2022-11-28) y KEY (2023-02-10): pares del panel, con remoción archivada, no figuran en ninguna pasada | **CONFIRMADA** | Los 5 están en `simbolos_usdt.json`, no son evento en ninguna pasada (R2 §5). Texto archivado: «will remove and cease trading … at 2022-11-28 03:00 (UTC): … BTCST/USDT, … GTO/USDT, … SRM/USDT, TRIBE/USDT» y «At 2023-02-10 03:00 (UTC): … KEY/USDT» (R8 §6). |
| V58 | l.225 | «Inclusión selectiva: 2 de al menos 7» | **CONFIRMADA** | 2 + 5 = 7 (V56, V57). **Reparo:** «selectiva» omite el criterio documentado: INFORME_REPARACION l.64 (se revisaron todas las páginas de exclusión con fecha ≥ 2023-04-28). Ver (b)-5. |
| V59 | l.227 | La v3 incluye todas las remociones; el procedimiento congelado no puede agregarlas; hay contradicción | **CONFIRMADA** | v3 l.107 («todas»); INFORME_REPARACION l.40. |
| V60 | l.238 | Con fechas de título, TRXUP y LINKDOWN tendrían E = 2023-04-27 y no mueven el inicio | **NO VERIFICABLE** | Contrafáctico. Es razonable (misma página, mismo título «(2023-04-27)») y coherente con INFORME_REPARACION l.90, pero nadie lo calculó. |
| V61 | l.239 | Con N5, E = 2023-05-09 y 2023-05-11; el inicio queda ≥ 2023-05-15 | **CONFIRMADA** | `eventos_omitidos.json` y `ventana_A_pasada2.json` (R2 §5). |
| V62 | l.240 | Los omitidos de 2022–2023 no afectan (ii′) «porque son anteriores» | **CONFIRMADA** | Solo con R1 literal (anteriores a 2023-05-15). Con R1′ son **posteriores** a 2021-02-19: ver (b)-1. |
| V63 | l.240 | «Su efecto sobre (iv′) no se calculó» | **NO VERIFICABLE** | Negativa de proceso. No encontré ningún cálculo. |
| V64 | l.254–256 | v3 §2.2.3 l.97–100, §2.2.4 l.101, §2.2.5 l.102, con citas | **CONFIRMADA** | R1. |
| V65 | l.257–258 | ADENDA_1 regla 1 (l.8) y regla 3 (l.10) | **CONFIRMADA** | R1. |
| V66 | l.264 | GTO→GFT: GTO/USDT removido el 2022-11-28; canje 1:1 completado el 2023-02-08; GFT/USDT abierto el 2023-09-22 (298 días) | **CONFIRMADA** | Remoción: V57. «distribution … at a ratio of 1 GTO = 1 GFT» en el texto archivado. `auditoria_por_simbolo`: GTO termina 2022-11-27, GFT empieza 2023-09-22: 298 días inactivos (R2 §6). El 2023-02-08 aparece como fecha del anuncio de finalización del canje. |
| V67 | l.265 | LUNA→LUNC: 119 días; el ticker LUNA se reutilizó | **CONFIRMADA** | `estructural.json`: LUNAUSDT último activo 2022-05-12, reanuda 2022-05-31, ratio de precio 3125; LUNCUSDT desde 2022-09-09: 119 días inactivos (R2 §6). |
| V68 | l.266 | UST→USTC: 301 días; UST y USTC están en la lista fija | **CONFIRMADA** | USTUSDT termina 2022-05-12, USTCUSDT empieza 2023-03-10: 301 (R2 §6). v3 l.234. |
| V69 | l.270 | §2.2.4 hereda la edad sin exigir que el listado esté vigente | **CONFIRMADA** | v3 l.101 no menciona «vigente». «Conflicto interno» es interpretación: ver (a)-7. |
| V70 | l.273 | «~21 formaciones; no lo recalculé» | **NO VERIFICABLE** | Depende de volúmenes (V ≥ 1 M USDT), que no puedo leer. |
| V71 | l.274–275 | LUNC listado nuevo con (a); USTC sin efecto | **CONFIRMADA** | V67, V68. |
| V72 | l.289 | v3 §3.3, l.175–176 | **CONFIRMADA** | «1 ejecución confirmatoria» está en l.175; l.176 es la viñeta siguiente. |
| V73 | l.290 | v3 §3.3, l.180–183 | **CONFIRMADA** | R1: l.180 y l.182. |
| V74 | l.292 | «La v3 no tiene ninguna regla de reintentos» | **CONFIRMADA** | `grep` «reintent/una sola ejecución…» en v3: solo l.73 («una sola ejecución») y l.277 (reintento de **ventas**) (R8 §2). Ver (c)-3. |
| V75 | l.292 | La C11 del orquestador v3 es una decisión de implementación | **CONFIRMADA** | `INFORME_CIERRE_BLOQUEANTES` l.155 define C11; no existe en la v3. |
| V76 | l.303 | L-13 (INVALIDO reintentable) y `validez_previa` simula la estrategia | **CONFIRMADA** | `INFORME_REVISION_ADVERSARIAL` L-13: «I1/I5 (INVALIDO→reintentable)». `ejecutar_E3_v3.py` l.387 (`def validez_previa`) y l.401 (`motor.simular(P, formaciones, …)`); l.95 la declara «sin estadísticos». Solo leí el código. |
| V77 | l.318 | v3 §7.1 l.460–465; §7.2 l.467–481, con la cita «si la regla de supervivencia acorta H…» | **CONFIRMADA** | R1: l.460, l.467, l.481; la cita está en l.479. |
| V78 | l.319 | v3 l.73: «nunca confirmación independiente» | **CONFIRMADA** | R1. |
| V79 | l.322–323 | «P0d se reproduce exactamente»: H1, IC 0,02, n = 160, α 0,025 → 0,35–0,56 | **CONFIRMADA** | `P0d_potencia_H1_segun_ventana.txt` l.2 y mi re-ejecución: `n = 160 … α 0.025: H1 IC 0,02 → [0.35, 0.56]`. La salida nueva es idéntica byte a byte a `potencia_analitica.txt` (R5). |
| V80 | l.325–329 | Tabla H2: 158 semanas 0,07–0,10 / 0,13–0,17; 274 semanas 0,10–0,15 / 0,16–0,23 | **CONFIRMADA** | R5. |
| V81 | l.330 | «P(RESPALDADA) ≤ la menor de las dos potencias, es decir ≤ ~0,10» | **REFUTADA** | El 0,10 sale solo de la columna α = 0,025. La misma lógica de la v3 (l.481) usa el rango completo. Con 158 semanas, H2 por sí sola llega a 0,13–0,17 con α 0,05, y RESPALDADA ≤ P(p₂ ≤ 0,05). Con 274 semanas es 0,16–0,23. Cota válida con cualquier dependencia: 0,126–0,171 (158) y 0,161–0,233 (274). Con independencia, 0,05–0,11 (158) y 0,10–0,20 (274). Cálculo en R6 (aritmética normal, sin datos). Un valor cercano a 0,10 es razonable como estimación con independencia a 158 semanas, pero no como cota. |
| V82 | l.331 | Las cifras de H1 de la v3 §7.2 usan un EE más conservador del que implican su n y su desvío | **CONFIRMADA** | R5: con n = 345 la fórmula da [0.64, 0.87] frente a «0,56–0,79» de la v3. v3 l.461: EE 0,007–0,0095; con sd 0,12–0,16 y n = 345 salen 0,0065–0,0086. Que sea «menor» es un juicio. |
| V83 | l.334–339 | Riesgos: circularidad de (iv′), punto ciego posterior al 2024-11-06, fragilidad (una salida más sin evidencia en 2023 → INVÁLIDA) | **CONFIRMADA** | V21 y V22. Fragilidad: segunda pasada, 2023: 19 en alcance, 1 sin evidencia (5,3 %); con 2 sería 10,5 % > 10 % (INFORME_REPARACION l.94). **Reparo:** con el P0 oficial (R1 literal, 1.ª pasada) 2023 tiene 22 en alcance: 2/22 = 9,1 % seguiría VÁLIDA (R2 §5). La fragilidad es propia de la ventana A de la 2.ª pasada. |
| V84 | l.338–339 | «el recall de renombres», «el volumen de HIFI» | **NO VERIFICABLE** | Dependen de tablas y volúmenes que no revisé. |
| V85 | l.341 | La v3 no exige una potencia mínima, solo que se informe | **CONFIRMADA** | v3 l.479 («se informa cuánto»); no hay umbral de potencia en v3 ni adendas. Sí hay un piso de 156 semanas (l.292). |
| V86 | l.357 | R1′ → «inicio determinado por BKRW (2021-02-22 en P0)» | **CONFIRMADA** | Para P0 sobre la 1.ª pasada (V33). Ya no vale con la 2.ª: ver (b)-1. |
| V87 | l.361 | Estricto → 2023-05-01, 160 (P0 oficial) | **CONFIRMADA** | V24. |
| V88 | l.362–363 | N5 universal + omitidos → ≥ 2023-05-15 (158 o menos, o INVÁLIDO) | **CONFIRMADA** | V44. |
| V89 | l.367 | «Se corrigieron 4 eventos, 3 de ellos fuera de las listas, y se agregaron 2 de al menos 7 omitidos» | **CONFIRMADA** | V50, V56–V58. |
| V90 | l.367 | «La ventana A fijada en el v3» tiene 158 semanas | **CONFIRMADA** | `ENTRADAS_CONGELADAS_V3.json`: `inicio_H_esperado: 2023-05-15`. «El v3» es aquí el orquestador; en el resto de la matriz «la v3» es el protocolo. |
| V91 | l.367 | Las 158 semanas «no salen de ninguna aplicación universal y coherente de estas reglas; salen de una aplicación parcial» | **REFUTADA** | Según los documentos que la matriz cita, la 2.ª pasada releyó los **55** eventos con N5 (INFORME_REPARACION l.31; `resoluciones_manuales.json`: 47 + 8 con cita), corrigió los que difieren y revisó las páginas de exclusión con fecha ≥ 2023-04-28 (l.64). Los 5 omitidos restantes tienen E ≤ 2023-02-10 y no pueden mover el inicio con R1 literal. Parcial fue solo el agregado de omitidos, y no hubo protocolo de lectura congelado. La propia síntesis de la matriz (l.362–363) dice que (II) da «≥ 2023-05-15 (158 o menos)»: 158 es exactamente ese valor. No re-ejecuté el escaneo por cuerpo que cita `COMPARACION_METODOLOGICA` l.64. Ver (c)-4 y la conclusión. |
| V92 | l.367 | «Fijar esa ventana en el v4 tal como está no es defendible» | **NO VERIFICABLE** | Es un juicio. Hay razones válidas (decisiones sin autorizar, lectura sin protocolo congelado, mismo agente), pero la premisa de V91 no se sostiene. |

---

## 2. Conteo

Cuento filas, no frases: 92 filas (algunas agrupan varias citas del mismo tipo). El conteo sale de `grep -c` sobre esta tabla (`registro/conteo_veredictos.txt`).

| Veredicto | Filas | IDs |
|---|---|---|
| CONFIRMADA | 78 | todas las demás (varias con «reparo») |
| REFUTADA | 6 | V07, V40, V41, V51, V81, V91 |
| NO VERIFICABLE | 8 | V03, V19, V42, V60, V63, V70, V84, V92 |

Resumen de las 6 refutadas:
- **V07:** la cita de ADENDA_3 está en la l.8, no en la l.9.
- **V40:** las 30 «fechas de cese distintas» son fechas candidatas; solo 4 son un cese spot distinto.
- **V41:** son 14 eventos, no 15; las fechas son de conversión a stablecoins.
- **V51:** DOTUP sí está previsto en A3.11 l.89–91.
- **V81:** P(RESPALDADA) no está acotada por ~0,10; la cota es 0,13–0,17 (158 semanas) o 0,16–0,23 (274).
- **V91:** las 158 semanas sí salen de una lectura N5 de los 55 eventos, como dice la propia tabla de decisión de la matriz para (II).

---

## 3. (a) Interpretaciones presentadas como hechos

1. **«Hecho verificado»: A3 contradice a N5 (matriz l.150).** Es una lectura, no un hecho. Lo comprobado es que en 4 de 55 eventos (los apalancados) el título lleva la fecha de publicación entre paréntesis y el cuerpo, otra de cese (R9). En los demás, la 2.ª pasada confirmó que la fecha de la 1.ª es la del cese. El propio A3 se declara implementación de N5 (título, «notas N5–N7») y la reparación lo trató así: «la extracción (A3.1.5) toma la fecha del título, que es la de publicación» (INFORME_REPARACION l.31). La matriz lo presenta como una contradicción general entre dos reglas.
2. **«En 30 el cuerpo tiene una fecha de cese distinta de E» (l.162).** Es la salida de una heurística de candidatas, no de lecturas de cese (V40, V41). Funciona como alarma y es la base de la advertencia de la sección 3 de la matriz. La cifra real de diferencias de cese spot es 4.
3. **«El orden de congelación es verificable» (l.75).** Descansa en fechas de modificación y en archivos que genera el mismo entorno. Además `REGISTRO_P0.txt` no es contemporáneo de lo que dice: declara `19:44:40.432Z`, pero su mtime es 19:47:23.061 y lista los hashes de `p0b_verificar_suspension.py` (mtime 19:45:18) y de `p0_auditoria_interna_R1prima.py` (mtime 19:47:23), que no existían a las 19:44:40 (R2 §2 y R11; los 5 hashes de ese archivo coinciden con los archivos actuales). Lo más simple es que se reescribió después de congelar R1′ (mtime a 1 ms del script de R1′). `COMPARACION_METODOLOGICA` (§5, en `cierre_bloqueantes_E3H1H2_2026-10-27/metodologia/`) dice que R se congeló «con los scripts de P0b y R1′ ya escritos (`REGISTRO_P0.txt`)»: esos mtimes sugieren lo contrario, aunque un archivo reescrito con el mismo contenido tendría el mismo hash. El orden congelación → P0 lo corroboran las mtimes de `p0_auditoria_interna.py` y `P0_resultado.json`, con un respaldo débil.
4. **«Su propia premisa es incorrecta» (l.84).** Para los 3 apalancados la premisa («por §4.5 no pueden entrar en un universo») es correcta; lo incorrecto es cómo R1 la implementó con las listas por lunes (CORRECCION l.7–10 lo dice). Para BKRW, la premisa falla en el mecanismo (no está en ninguna lista fija), pero BKRW no figura en `elegibles` en ninguno de los 439 lunes (R2 §3): en este panel nunca entró en un universo. El `PLAN_EJECUCION_UNICA_E3R.md` (l.84) ya lo notaba: «probablemente quedaría excluido por el filtro de volatilidad».
5. **«Selectiva… No es una regla aceptable» (l.225, l.235).** Es una valoración. La reparación aplicó un criterio explícito (INFORME_REPARACION l.64): revisar todas las páginas de exclusión con fecha ≥ 2023-04-28, que son las que pueden mover el inicio con R1 literal. Se podrá discutir, pero no es una elección ad hoc de 2 entre 7.
6. **«Es una inconsistencia menor del protocolo» (l.331).** Juicio. Los números (V82) son correctos.
7. **GTO→GFT: «(a) Literal» frente a «(b) Continuidad» (l.269–270).** Calificar (a) de «literal» es discutible. Adenda 1 regla 1 dice: «Y lo continúa con la relación de canje, y hereda la edad y las posiciones», sin condición de vigencia. v3 l.101 tampoco. La lectura (a) exige entender «el listado vigente de X termina en la fecha efectiva» como «solo si había uno vigente en E». Es una lectura posible; no la única literal.
8. **«Fijar esa ventana… no es defendible» (l.367).** Opinión; ver la conclusión.
9. **CIERRE §2 (l.50) puesto entre las «reglas originales».** Es el registro de lo que no se hizo «por decisión expresa»; la regla es CIERRE l.19 (V10).

---

## 4. (b) Alternativas razonables que la matriz omite

1. **R1′ combinada con la segunda pasada (rama BKRW).** La matriz dice que el inicio con R1′ lo fija BKRW (2021-02-22) y aclara que no se recalculó con la 2.ª pasada. No dice que la 2.ª pasada **descartó** BKRWUSDT: «El propio anuncio corrige el par: el removido es USDT/BKRW (otro símbolo), no BKRW/USDT. Error de identificación del par» (`resoluciones_manuales.json`, acción `descartar`; categoría `descartado` en `salida_pasada2/eventos.json`; R2 §4 y R7). `ventana_A_pasada2.json` no lista a BKRW entre las fallas. Con R1′ + 2.ª pasada las 6 fallas T quedan fuera por clase y BKRW desaparece, así que ningún componente de (ii′) fija el inicio. Aritméticamente, un inicio en (i) 2020-05-11 daría 315 lunes hasta 2026-05-18 (R2 §6). **No lo calculé ni lo propongo:** es otra regla elegida con conocimiento del efecto, y los omitidos (p. ej. KEY, 2023-02-10) dejarían de ser irrelevantes para (ii′) en esa rama (V62). Pero la rama «R1′ → BKRW» del árbol de decisión (l.357) está desactualizada.
2. **La historia B → A.** `PLAN_EJECUCION_UNICA_E3R.md` (20:04) recomendaba B (R1′, 274 semanas). `decision_E3H1H2_2026-10-26/INFORME_DECISION_E3H1H2.md` (21:58) dice «El 26/10 recomendé B. Fue un error», «B queda descartada en forma definitiva» y que el principio de R1′ «excluiría también a BKRW, y el inicio cambiaría otra vez. R1′ es una de varias operacionalizaciones posibles, cada una con su ventana». La reparación (C6) eliminó la ruta R1′ del orquestador v2. La matriz presenta «R1 literal o R1′» como decisión abierta sin citar ninguno de los tres documentos. Elegir R1′ hoy exigiría un orquestador nuevo y un manifiesto nuevo.
3. **Las opciones documentadas de reapertura.** CIERRE §4 remite al §8 de `INFORME_EJECUCION_E3.md`, con cinco opciones (a: compilación manual de la categoría 161, prevista en v3 §9; b: web.archive.org; c: confirmar las condiciones de uso; d: fuente no oficial; e: aceptar y cerrar, con evaluación prospectiva aparte). Ese informe concluyó: «No recomiendo relajar la regla (iv)… sería cambiar el protocolo después de ver la cobertura». Es el argumento central contra la Adenda R y la matriz no lo cita. Sus alternativas (a)/(b)/(c) de §1 omiten la compilación manual, que es la que cerraría el punto ciego.
4. **La Adenda R2 (cortes con salto de precio).** Está en el paquete «v3 + Adenda R» (R2 l.3), figura en la frase de autorización del plan y la reparación la **abandonó** (INFORME_REPARACION l.135, «R2 queda abandonada», porque contradice la regla 3 de la Adenda 1). Afecta a §6 de la matriz (LUNA tiene un corte de 18 días con ratio ×3125; BNX, VIDT) y es una decisión que el usuario debería ratificar. La matriz no la menciona.
5. **Un protocolo de lectura a ciegas para N5.** La matriz pide congelar uno antes de la pasada. Una alternativa intermedia: tratar la 2.ª pasada como borrador y exigir una relectura independiente de los 55 eventos (o de los 14–26 con fecha candidata distinta) contra un protocolo congelado. Costo bajo: los casos reales de diferencia son 4.
6. **Escaneo de páginas con título ilegible.** El recall de la extracción tiene el hueco de 929 páginas con título CSS (COMPARACION l.77; el aviso del 2022-11-28 está entre las tituladas «Announcement»). El argumento de que ningún omitido mueve el inicio depende del «escaneo por cuerpo de las 8.028 páginas» (COMPARACION l.64). La matriz no lo menciona ni como supuesto ni como verificación pendiente. No lo re-ejecuté.
7. **Capas C y P de la v3** (l.74–75) como vía para sumar evidencia sin tocar H, y la advertencia de v3 §7.3 (l.483–488) de que este experimento no puede sostener una decisión de capital. La matriz deja en «Te corresponde» si la potencia es informativa, pero no ubica estas dos capas.

---

## 5. (c) «No hay regla» que sí tiene respaldo en alguna fuente

1. **«No existe ninguna regla de precedencia entre N5 y A3» (l.40, y la alternativa III).** Literalmente cierto (no hay cláusula), pero hay respaldo textual para una lectura:
   - v3 prevalece sobre todo (§0.2 l.32; NOTAS l.3). La v3 define las categorías y (ii) por la **«fecha efectiva»** de la exclusión (§2.3, §4.11), y A3 l.8 declara que «no cambia categorías, umbrales, ventanas ni criterios». La extracción A3.1.5 queda como medio para obtener esa fecha, no como su definición.
   - A3 cita «notas N5–N7» como su base, y su «Qué no cambia» (l.8) **no** nombra a las notas. `CONGELACION_ADENDA_3.txt` l.3 dice que ningún archivo anterior congelado, notas incluidas, se modificó.
   - Las desviaciones respecto de las notas se declararon en una Enmienda (la 2 se titula «desviaciones e interpretaciones… respecto de la v3 y de las notas N1–N22»). A3 no declara ninguna respecto de N5.
   - A favor de (I): A3 es posterior y más específica. Es decir, hay argumentos para ambas lecturas y no es un vacío completo.
2. **«Ninguna de las 4 correcciones está prevista en el texto» (l.197).** DOTUP: A3.11 l.89–91 (la muestra V-S3 es una lista de revisión; cada caso «se resuelve con una cita del texto archivado»; «su resultado es el definitivo»). Los 4: N5. Las 3 restantes quedan fuera de las listas, y ahí la matriz acierta.
3. **«La v3 no tiene ninguna regla de reintentos» (l.292).** Cierto para la v3, pero la política (iii) tiene más respaldo del que la matriz muestra: v3 l.73 («una sola ejecución»); ADENDA_R l.61 («**una** ejecución confirmatoria»); `PLAN_EJECUCION_UNICA_E3R.md` l.35 («Sin repeticiones… Toda corrida no planificada es exploratoria y no cambia ninguna clasificación») y l.92 («la salida no puede existir de antes (ejecución única)»). Esos dos últimos son propuestas del autor, no reglas congeladas.
4. **«Hace falta… una pasada completa con N5» (l.167, l.171, l.175, l.363).** Ya hay una segunda pasada completa sobre los 55 eventos (V44, V91). Lo que no hay es un protocolo de lectura congelado antes de ella ni una lectura independiente. La matriz debería decirlo así.
5. **«Hace falta una dispensa escrita» (l.92).** La Adenda R l.73 y INFORME_REPARACION l.237 y l.266–267 ya prevén el mecanismo: la autorización del usuario tiene que nombrar expresamente la sustitución de (iv) por (iv′) y de la condición de CIERRE §4. Es un mecanismo, no una regla nueva, pero la matriz lo trata como un hueco.
6. **«Hace falta un procedimiento de búsqueda de omitidos» (l.242).** Existen `eventos_omitidos.py` y `verif_remociones.py` (REP/segunda_pasada), que cubren las páginas con fecha ≥ 2023-04-28 (V58). Falta uno que cubra todo el período y se congele antes de ejecutarse; ahí la matriz acierta.

---

## 6. Conclusión: ¿es fiable para que el usuario decida?

**En lo textual y numérico, sí, con seis correcciones.** De 92 filas, 78 se confirman (varias con reparo), 6 se refutan y 8 no se pueden verificar. Entre las 84 con veredicto, 78 coinciden con la fuente (93 %). Los errores son: un número de línea mal citado (V07), un conteo mal informado (V41), una cota de probabilidad subestimada (V81), una lectura de las citas de A3.11 que deja afuera a DOTUP (V51) y dos caracterizaciones que cambian el peso de los argumentos (V40, V91). Las citas de v3, notas, adendas 1/3, Adenda R, CIERRE y R1′ son correctas salvo V07. Los hashes, las horas, los JSON de P0, `vs3`, los omitidos y las cifras de potencia coinciden.

**Como mapa completo de alternativas y de riesgo, no todavía.** Hay tres puntos donde la matriz induce a decidir sobre una base distinta de la que muestran las fuentes:

1. **§3 (N5 frente a A3.1.5).** Presenta 30 eventos con «fecha de cese distinta» y una «pasada completa» pendiente. Las fechas candidatas son, salvo 4, de Margin, Earn, conversión a stablecoins o pares BUSD; y la pasada completa ya existe (sin protocolo congelado). La elección (I)/(II) del usuario afecta a 4 eventos y tiene un resultado conocido: 2023-05-01/160 (sin corregir) frente a 2023-05-15/158 (corrigiendo). La pregunta real es si acepta esas lecturas o exige una relectura independiente.
2. **§2 y árbol de decisión (R1′).** La rama «BKRW fija el inicio» está desactualizada (BKRW descartado en la 2.ª pasada y nunca elegible). La matriz tampoco cuenta que el autor recomendó B, se corrigió, y que la propia reparación quitó R1′ del orquestador.
3. **Conclusión final (l.367).** «No salen de ninguna aplicación universal y coherente… no es defendible» no está respaldada por lo que la reparación documenta para la rama R1 literal: la ventana A de 158 semanas es lo que da una lectura N5 de los 55 eventos más la revisión de todas las páginas de exclusión posteriores al 2023-04-28. Sigue siendo razonable decir que depende de decisiones que solo el usuario puede tomar (reabrir E3, sustituir (iv), tolerar el punto ciego posterior al 2024-11-06), de una lectura hecha por el mismo agente sin protocolo previo, de un margen de 2 semanas y de una potencia baja. Esa versión sí es defendible; la más fuerte, no.

**Qué puede usar sin reservas:** las decisiones 1 (reabrir/Adenda R), 5 (omitidos, con la corrección V58), 6 (continuidad), 7 (reintentos, sumando el respaldo de (c)-3) y 8 (potencia, usando la cota de V81). **Qué debería corregirse antes de decidir:** §3, la rama R1′ de §2 y el cierre de la síntesis.

**Límites de esta verificación:** soy del mismo modelo y lanzado por el autor; no re-ejecuté el escaneo por cuerpo de las 8.028 páginas; no pude comprobar el registro de la sesión ni nada que requiera precios o volúmenes; las marcas de tiempo son mtimes de archivos, que se pueden alterar.

---

## Anexo: archivos de `registro/`

| ID | Archivo | Qué es |
|---|---|---|
| R1 | `verif_citas.sh` → `salida_verif_citas.txt` | `sha256sum` de las fuentes y `grep -n` de cada cita citada con su número de línea |
| R2 | `comandos_adicionales.py` → `salida_comandos_adicionales.txt` | P0, mtimes, listas por lunes, `vs3`, omitidos, fallas de la ventana A, aritmética de fechas |
| R3 | `alcance_N5_reejecutado.json`, `salida_alcance_N5_reejecutado.txt` | Re-ejecución de `alcance_pasada_N5.py`; el JSON es idéntico al original |
| R4 | `oraciones_fechas_distintas_de_E.txt` | Las oraciones que generan las fechas candidatas ≠ E |
| R5 | `salida_potencia_reejecutada.txt` | Re-ejecución de `potencia_analitica.py`; idéntica al `.txt` original |
| R6 | `cota_conjunta.py` → `salida_cota_conjunta.txt` | Cota de P(RESPALDADA), aritmética normal pura |
| R7 | `salida_bkrw_pasada2.txt` | BKRWUSDT en la 2.ª pasada (`descartado`) |
| R8 | `busquedas_texto.sh` → `salida_busquedas_texto.txt` | Precedencia, reintentos, §8 del informe de ejecución, plan, remociones archivadas |
| R9 | `titulos_eventos.py` → `salida_titulos_eventos.txt` | Título limpio y origen de E de los eventos de la 1.ª pasada (el de los apalancados lleva «(2023-04-27)») |
| R10 | `conteo_fechas_posteriores.py` → `salida_conteo_fechas_posteriores.txt` | 23 / 18 / 14 eventos 2023–2024 con fecha candidata posterior a E (cualquiera / ≥ 14 d / ≥ 28 d) |
| R11 | `verif_registro_p0.sh` → `salida_verif_registro_p0.txt` | `sha256sum -c` de los hashes de `REGISTRO_P0.txt` (5/5 OK) y mtimes de esos archivos y del registro |
| — | `comparacion_reejecuciones.txt` | `cmp` byte a byte de las dos re-ejecuciones contra los originales (idénticas) y hash final de la matriz |
| — | `conteo_veredictos.txt` | Conteo por veredicto de la tabla |
| — | `LEEME_REGISTRO.txt` | Cómo reproducir cada archivo |
